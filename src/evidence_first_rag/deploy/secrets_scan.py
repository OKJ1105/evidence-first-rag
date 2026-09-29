"""`deploy-v0.1` Section 8.1: `DP-003`'s image, workflow and artifact half.

`DP-003` asks that the image, the workflows and the deploy's artifact hold no
secret. The app-settings half is `azure_checks.dp003_settings`. This module
reads the other three with two tests:

- **The job's own secrets, by value.** The deploy job holds the database
  passwords it read from Key Vault. Each is looked for, as an exact substring,
  in every file of the image, every workflow file and every artifact file. No
  pattern can miss a value the job actually knows.
- **Credential-shaped strings**, by the repository scanner's `private-key`,
  `issued-credential` and `url-credentials` rules
  (`scripts/checks/scan_sensitive_strings.py`). These catch a secret the job
  does not hold, such as an Anthropic key, which `DP-015` keeps the job from
  ever reading. In the image they are applied to this repository's own files
  under `/app` and to the image's configuration only. A base image and its
  installed packages ship test vectors and certificate bundles that have the
  shape without being a secret, and a scan that always fails decides nothing.
  The known-value test still covers the whole filesystem.

The image's configuration must also set none of the secret settings
(`ANTHROPIC_API_KEY`, the database passwords): each app gets its secrets from
Key Vault references at run time, never from the image.

A finding names where it is and which test found it, never the value.
"""

import argparse
import importlib.util
import io
import json
import pathlib
import subprocess
import sys
import tarfile

ROOT = pathlib.Path(__file__).resolve().parents[3]
SCANNER = ROOT / "scripts" / "checks" / "scan_sensitive_strings.py"

# The secrets the checks step holds, by the environment variables it exports.
KNOWN_VALUE_VARIABLES = ("MVP_PROVISIONING_PASSWORD", "MVP_RUNTIME_PASSWORD")

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

SHAPE_RULES = ("private-key", "issued-credential", "url-credentials")

# This repository's files in the image (Dockerfile `WORKDIR /app`).
OWN_PREFIX = "app/"


def _scanner():
    spec = importlib.util.spec_from_file_location("scan_sensitive_strings", SCANNER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _shape_rules():
    return [(name, find) for name, _clause, find in _scanner().RULES if name in SHAPE_RULES]


def known_values(environment) -> list:
    """The secret values the job holds, empty ones left out."""
    return [environment[name] for name in KNOWN_VALUE_VARIABLES if environment.get(name)]


def scan_text(text, where, values, findings, shapes=None, path=None):
    """Append a finding for each known value in `text`, and for each shape
    hit when `shapes` is given. `path` is what the shape rules are told the
    file is, since some of them read its suffix."""
    for index, value in enumerate(values):
        if value in text:
            findings.append({"where": where, "test": f"known value {index + 1}"})
    if shapes:
        target = pathlib.PurePosixPath(path or where)
        for number, line in enumerate(text.splitlines(), 1):
            for name, find in shapes:
                for _hit in find(line, target):
                    findings.append({"where": f"{where}:{number}", "test": name})


def scan_image_filesystem(tar_stream, values, findings, shapes):
    """Every regular file of an exported container filesystem."""
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
            scan_text(text, f"image:/{name}", values, findings, shapes if own else None, name)


def scan_image_config(config, values, findings, shapes):
    """The image's environment, labels and entrypoint."""
    for entry in config.get("Env") or []:
        name, _, value = entry.partition("=")
        if name in SECRET_SETTINGS:
            findings.append({"where": f"image config Env {name}", "test": "secret setting in image"})
        scan_text(value, f"image config Env {name}", values, findings, shapes)
    for key, value in (config.get("Labels") or {}).items():
        scan_text(str(value), f"image config Label {key}", values, findings, shapes)
    for field in ("Entrypoint", "Cmd"):
        scan_text(" ".join(config.get(field) or []), f"image config {field}", values, findings, shapes)


def scan_files(paths, label, values, findings, shapes):
    for path in paths:
        path = pathlib.Path(path)
        if not path.is_file():
            continue
        text = path.read_bytes().decode("utf-8", errors="replace")
        scan_text(text, f"{label}:{path.as_posix()}", values, findings, shapes, path.as_posix())


def _docker(*arguments, **options):
    return subprocess.run(["docker", *arguments], check=True, **options)


def scan_image(image, values, findings, shapes):
    inspected = json.loads(_docker("image", "inspect", image, capture_output=True, text=True).stdout)
    scan_image_config(inspected[0].get("Config") or {}, values, findings, shapes)
    container = _docker("create", image, "true", capture_output=True, text=True).stdout.strip()
    try:
        exported = subprocess.Popen(["docker", "export", container], stdout=subprocess.PIPE)
        try:
            scan_image_filesystem(exported.stdout, values, findings, shapes)
        finally:
            exported.stdout.close()
            if exported.wait() != 0:
                raise RuntimeError("docker export failed")
    finally:
        _docker("rm", container, capture_output=True)


def main(argv=None, environment=None) -> int:
    import os

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--image", required=True)
    parser.add_argument("--workflows", default=".github/workflows")
    parser.add_argument("--artifacts", nargs="*", default=[])
    parser.add_argument("--out", default="secret-scan.json")
    arguments = parser.parse_args(argv)

    values = known_values(os.environ if environment is None else environment)
    shapes = _shape_rules()
    findings, error = [], None
    if not values:
        # Without the job's secrets the known-value test would pass vacuously.
        error = "none of the job's secrets was provided"
    try:
        scan_files(sorted(pathlib.Path(arguments.workflows).glob("*")), "workflow", values, findings, shapes)
        scan_files(arguments.artifacts, "artifact", values, findings, shapes)
        scan_image(arguments.image, values, findings, shapes)
    except Exception as failure:  # noqa: BLE001 - an unfinished scan is a failed case, recorded
        error = f"the scan itself failed: {type(failure).__name__}"
    finally:
        result = {
            "DP-003 image, workflows, artifact": {
                "passed": not findings and error is None,
                "known_values": len(values),
                "findings": findings,
                "error": error,
            }
        }
        with open(arguments.out, "w", encoding="utf-8") as handle:
            json.dump(result, handle, indent=2)
    print(json.dumps(result))
    return 0 if not findings and error is None else 1


if __name__ == "__main__":
    sys.exit(main())
