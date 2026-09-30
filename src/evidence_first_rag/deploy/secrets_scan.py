"""`deploy-v0.1` Section 8.1: `DP-003`'s image, workflow and artifact half.

`DP-003` asks that the image, the workflows and the deploy's artifact hold no
secret. The app-settings half is `azure_checks.dp003_settings`. This module
reads the other three with two tests:

- **The job's own secrets, by value.** The deploy job holds the database
  passwords it read from Key Vault. Each is looked for, as an exact substring,
  in every file of the image, every workflow file and every artifact file. No
  pattern can miss a value the job actually knows.
- **Credential-shaped strings**, by every credential rule the repository
  scanner defines — `private-key`, `issued-credential`, `assigned-secret` and
  `url-credentials`, the four it files under "never add credentials or
  secrets" (`scripts/checks/scan_sensitive_strings.py`). These catch a secret
  the job does not hold, such as an Anthropic key, which `DP-015` keeps the job
  from ever reading. In the image they are applied to this repository's own files
  under `/app` and to the image's configuration only. A base image and its
  installed packages ship test vectors and certificate bundles that have the
  shape without being a secret, and a scan that always fails decides nothing.
  The known-value test still covers the whole filesystem.

The image's configuration must also set none of the secret settings
(`ANTHROPIC_API_KEY`, the database passwords): each app gets its secrets from
Key Vault references at run time, never from the image.

A finding names where it is and which test found it, never the value.

The record names what it read — the image, each workflow file, each artifact
file — and states what it does not cover. The scan runs at one point in the
deploy, so a file a later step writes into the uploaded artifact is not among
its targets; `passed` is a verdict over `scanned` and over nothing else
(#253 B3).
"""

import argparse
import importlib.util
import json
import pathlib
import subprocess
import sys
import tarfile

# Relative to the working directory, like the sibling module's `RECORDS`: the
# deploy job installs this package, so `__file__` is under site-packages and
# says nothing about where the checkout is, while the job runs from its root.
SCANNER = pathlib.Path("scripts/checks/scan_sensitive_strings.py")

# The secrets the checks step holds, by the environment variables it exports.
KNOWN_VALUE_VARIABLES = ("PGPASSWORD", "MVP_PROVISIONING_PASSWORD", "MVP_RUNTIME_PASSWORD")

# Settings an image must never carry: each is a Key Vault reference at run time.
SECRET_SETTINGS = frozenset(
    {
        "ANTHROPIC_API_KEY",
        "MVP_RUNTIME_PASSWORD",
        "MVP_PROVISIONING_PASSWORD",
        "PGPASSWORD",
        "POSTGRES_PASSWORD",
    }
)

# The scanner's credential rules, all four of them. `assigned-secret` is the
# only one that catches a password value written under a password-shaped name,
# which is the shape of a secret this job does not hold and so cannot look for
# by value.
SHAPE_RULES = ("private-key", "issued-credential", "assigned-secret", "url-credentials")

# This repository's files in the image (Dockerfile `WORKDIR /app`).
OWN_PREFIX = "app/"

# What a passing record does not stand for. The scan reads its targets when it
# runs; a file written into the uploaded artifact by a later step — the deploy
# record, the rollback records — was not there to be read (#253 B3).
LIMITATIONS = (
    "Only the targets named in `scanned` were read. A file the deploy writes"
    " after this scan and uploads with the artifact — the deploy record and the"
    " rollback records — is outside this record, and `passed` says nothing"
    " about it. The deploy job scans those in a second run, recorded as"
    " `secret-scan-record.json`.",
    "The image is read through `docker export`: the final filesystem, as raw"
    " bytes. Content a later layer removed, and content inside a compressed"
    " file, are not read.",
    # #260 N9: the record, not only the docstring, says where the shape
    # rules ran.
    "The credential-shape rules were applied to files under `/app` and to the"
    " image configuration only: the base image's packages ship test vectors"
    " and certificate bundles that have a credential's shape. Every other file"
    " in the image was read for the known values alone.",
)


def _scanner(path=None):
    spec = importlib.util.spec_from_file_location("scan_sensitive_strings", path or SCANNER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _shape_rules(path=None):
    return [(name, find) for name, _clause, find in _scanner(path).RULES if name in SHAPE_RULES]


def known_values(environment) -> list:
    """The secret values the job holds, as (variable, value), empty ones left
    out. A finding names the variable, never the value, so a reader of the
    record can tell which of the passwords was found and which were sought
    (#254 N8)."""
    return [(name, environment[name]) for name in KNOWN_VALUE_VARIABLES if environment.get(name)]


def scan_text(text, where, values, findings, shapes=None, path=None):
    """Append a finding for each known value in `text`, and for each shape
    hit when `shapes` is given. `path` is what the shape rules are told the
    file is, since some of them read its suffix."""
    for name, value in values:
        if value in text:
            findings.append({"where": where, "test": f"known value {name}"})
    if shapes:
        target = pathlib.PurePosixPath(path or where)
        for number, line in enumerate(text.splitlines(), 1):
            for name, find in shapes:
                for _hit in find(line, target):
                    findings.append({"where": f"{where}:{number}", "test": name})


def scan_image_filesystem(tar_stream, values, findings, shapes) -> int:
    """Every regular file of an exported container filesystem. Returns how
    many of this repository's own files the shape rules read."""
    own_files = 0
    with tarfile.open(fileobj=tar_stream, mode="r|*") as archive:
        for member in archive:
            if not member.isfile():
                continue
            handle = archive.extractfile(member)
            if handle is None:
                continue
            text = handle.read().decode("utf-8", errors="replace")
            name = member.name.lstrip("./")
            own = name.startswith(OWN_PREFIX)
            own_files += own
            scan_text(text, f"image:/{name}", values, findings, shapes if own else None, name)
    return own_files


def scan_image_config(config, values, findings, shapes):
    """The image's environment, labels and entrypoint."""
    for entry in config.get("Env") or []:
        name, _, value = entry.partition("=")
        if name in SECRET_SETTINGS:
            findings.append({"where": f"image config Env {name}", "test": "secret setting in image"})
        # The whole entry, so a secret under a secret-shaped name is seen as
        # one (#254 N4).
        scan_text(entry, f"image config Env {name}", values, findings, shapes)
    for key, value in (config.get("Labels") or {}).items():
        scan_text(f"{key}={value}", f"image config Label {key}", values, findings, shapes)
    for field in ("Entrypoint", "Cmd"):
        scan_text(" ".join(config.get(field) or []), f"image config {field}", values, findings, shapes)


def scan_files(paths, label, values, findings, shapes) -> list:
    """Scan each path that exists, and return the ones actually read, so the
    record names its targets rather than implying them (#253 B3)."""
    read = []
    for path in paths:
        path = pathlib.Path(path)
        if not path.is_file():
            continue
        text = path.read_bytes().decode("utf-8", errors="replace")
        scan_text(text, f"{label}:{path.as_posix()}", values, findings, shapes, path.as_posix())
        read.append(path.as_posix())
    return read


def _docker(*arguments, **options):
    return subprocess.run(["docker", *arguments], check=True, **options)


def scan_image(image, values, findings, shapes):
    inspected = json.loads(_docker("image", "inspect", image, capture_output=True, text=True).stdout)
    scan_image_config(inspected[0].get("Config") or {}, values, findings, shapes)
    container = _docker("create", image, "true", capture_output=True, text=True).stdout.strip()
    try:
        exported = subprocess.Popen(["docker", "export", container], stdout=subprocess.PIPE)
        try:
            own_files = scan_image_filesystem(exported.stdout, values, findings, shapes)
        finally:
            exported.stdout.close()
            if exported.wait() != 0:
                raise RuntimeError("docker export failed")
    finally:
        _docker("rm", container, capture_output=True)
    if not own_files:
        # The shape test read nothing of this repository's (#254 N3).
        raise RuntimeError(f"no file under /{OWN_PREFIX} in the image")


def main(argv=None, environment=None) -> int:
    import os

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--image", help="omitted: the image is not scanned (the record run, #254 B3)")
    parser.add_argument("--workflows", default=".github/workflows", help="'none': no workflow is scanned")
    parser.add_argument("--artifacts", nargs="*", default=[])
    parser.add_argument("--scanner", default=str(SCANNER))
    parser.add_argument("--out", default="secret-scan.json")
    arguments = parser.parse_args(argv)

    values = known_values(os.environ if environment is None else environment)
    findings, error = [], None
    # Each target is entered only once it has been read, so a scan that stops
    # partway names what it covered and not what it was asked to cover.
    scanned = {"image": None, "workflows": [], "artifacts": []}
    # #260 N10: what was asked for and not there, so "scanned and clean" and
    # "never there" read differently. An absent artifact is recorded, not
    # failed: a narrowed or first run legitimately writes fewer files.
    missing = [path for path in arguments.artifacts if not pathlib.Path(path).is_file()]
    if not values:
        # Without the job's secrets the known-value test would pass vacuously.
        error = "none of the job's secrets was provided"
    try:
        # Inside the try: a scanner that cannot be loaded is a scan that did
        # not run, which is a failed case with a record, not a traceback.
        shapes = _shape_rules(arguments.scanner)
        if arguments.workflows != "none":
            scanned["workflows"] = scan_files(
                sorted(pathlib.Path(arguments.workflows).glob("*")), "workflow", values, findings, shapes
            )
            if not scanned["workflows"]:
                # A typo or a moved directory must not pass over nothing.
                raise FileNotFoundError(f"no workflow file under {arguments.workflows}")
        scanned["artifacts"] = scan_files(arguments.artifacts, "artifact", values, findings, shapes)
        if arguments.image:
            scan_image(arguments.image, values, findings, shapes)
            scanned["image"] = arguments.image
    except Exception as failure:  # noqa: BLE001 - an unfinished scan is a failed case, recorded
        error = f"the scan itself failed: {type(failure).__name__}"
    finally:
        result = {
            "DP-003 image, workflows, artifact": {
                "passed": not findings and error is None,
                "known_values": [name for name, _ in values],
                "scanned": scanned,
                "missing": missing,
                "findings": findings,
                "limitations": list(LIMITATIONS),
                "error": error,
            }
        }
        with open(arguments.out, "w", encoding="utf-8") as handle:
            json.dump(result, handle, indent=2)
    print(json.dumps(result))
    # 1 is a finding: a value may be in a file. 2 is a scan that did not
    # finish: nothing was found, and nothing was cleared either (#260 N11).
    if findings:
        return 1
    return 2 if error is not None else 0


if __name__ == "__main__":
    sys.exit(main())
