"""Scan the Git history for sensitive strings.

Shared by CI (.github/workflows/repository-checks.yml) and the agent loop
(.github/agent-checks.json) so both verify the same thing with the same code,
in the same shape as the other checks in this directory.

Charter Section 11 asks for a review of "the current tree, full Git history,
and public PR or issue content, not only the latest files".
`scan_sensitive_strings.py` reads the current tree and says so in its own
docstring. This reads the other half that a scanner can decide: every version
of every file the history carries, including the ones no longer in the tree.

**That difference is the whole point.** A credential committed and then deleted
is gone from the working tree and still published with the repository. The tree
scan passes on it by construction; only this one sees it.

The rules are not restated here. This imports them from
`scan_sensitive_strings.py` and applies the same seven, with the same
exemptions, the same minimum length, and the same masking, so a rule added
there is enforced here on the next run and the two can never disagree about
what a sensitive string is. Loaded by path from *this* file's directory: run
through the loop's `{baseDir}`, that is the base branch's copy, which is what
stops a branch from weakening the rules it is judged against.

Two things it does differently from the tree scan, both deliberate:

- **Nothing is skipped by directory.** The tree scan ignores `node_modules`,
  `__pycache__` and build output because they are not reviewable content in a
  working tree. Committed, they are published like anything else, so this scan
  reads whatever the history holds. Skipping them here would put the hole
  exactly where a scanner of history is supposed to look.
- **A shallow clone is a failure, not a pass.** A truncated history would make
  this check quietly meaningless, which is the one way a scan like this goes
  wrong without anyone noticing.

Scope: the commits reachable from `REVISION` (`HEAD`), which is the history
that merging this branch would publish. Other refs a checkout happens to
carry are not scanned; they are not this branch's to answer for.

Exits 1 and lists every hit when any rule matches.
"""

import importlib.util
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent

# The history reachable from here. A module constant so a test can point the
# scan at a repository it built.
REVISION = "HEAD"

# Where the git commands run. `None` means the current directory, which is the
# branch checkout under CI and under the loop.
WORK_TREE = None


def rules():
    """The tree scan's rule set, loaded by path.

    By path rather than by import because `scripts/checks/` is not a package,
    which is the same reason `test_validate_fixtures.py` loads its subject
    that way.
    """
    spec = importlib.util.spec_from_file_location(
        "scan_sensitive_strings", HERE / "scan_sensitive_strings.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def git(*arguments, stdin=b""):
    """One git command, in bytes, failing loudly."""
    return subprocess.run(
        ("git",) + arguments,
        cwd=WORK_TREE,
        input=stdin,
        capture_output=True,
        check=True,
    ).stdout


def is_shallow():
    return git("rev-parse", "--is-shallow-repository").decode().strip() == "true"


def named_objects():
    """Every (object name, path) the history carries, deduplicated.

    A blob unchanged across fifty commits is one entry: the content is
    identical and the rules read only the content and the path. The same blob
    at two different paths is two entries, because the path decides which
    rules apply to it — a literal exempt in a `.sql` file is not exempt in a
    `.yml` one.

    Read from each commit's tree rather than from `git rev-list --objects`,
    which is the obvious way and is wrong here: it names an object **once**
    even when the tree holds it at several paths, and the single path it
    reports may be the one where a rule exempts the content. That is not a
    hypothetical — the first draft of this check used it and read four fewer
    file versions than exist in this repository's own history, two expected
    results whose byte-identical content sits at two paths each. A mutation
    probe found the gap before the check was ever registered.
    """
    seen = set()
    blobs = []
    for commit in git("rev-list", REVISION).decode().split():
        # `-z` so a path is delivered raw rather than quoted, and `-r` so the
        # walk reaches every file rather than the top-level trees.
        for entry in git("ls-tree", "-r", "-z", commit).split(b"\0"):
            if not entry:
                continue
            meta, _, raw = entry.partition(b"\t")
            parts = meta.split()
            # A submodule is a `commit` entry in the tree and has no content
            # here to read.
            if len(parts) < 3 or parts[1] != b"blob":
                continue
            name = parts[2].decode()
            path = raw.decode("utf-8", errors="replace")
            if (name, path) in seen:
                continue
            seen.add((name, path))
            blobs.append((name, path))
    return sorted(blobs, key=lambda entry: (entry[1], entry[0]))


def contents(names):
    """Read many blobs in one `git cat-file --batch`.

    The stream is `<name> <type> <size>\\n<size bytes>\\n` per request. It is
    parsed by the declared size rather than by looking for the next header,
    because a blob's own content can contain a line that looks like one.
    """
    if not names:
        return {}
    stream = subprocess.run(
        ("git", "cat-file", "--batch"),
        cwd=WORK_TREE,
        input="".join(name + "\n" for name in names).encode(),
        capture_output=True,
        check=True,
    ).stdout

    body = {}
    at = 0
    for name in names:
        end = stream.index(b"\n", at)
        header = stream[at:end].split()
        if len(header) < 3:
            # `<name> missing`. Cannot happen for a name git just listed, but
            # a silent mis-parse of the rest of the stream would be worse.
            raise RuntimeError(f"git could not read {name}: {stream[at:end]!r}")
        size = int(header[2])
        body[name] = stream[end + 1 : end + 1 + size]
        at = end + 1 + size + 1
    return body


def main() -> int:
    scan = rules()
    failures = []

    try:
        if is_shallow():
            print(
                "Sensitive strings in history: CANNOT RUN\n"
                "The repository is a shallow clone, so most of the history is "
                "absent and a pass here would mean nothing. Check out with "
                "fetch-depth: 0."
            )
            return 1
        blobs = named_objects()
    except subprocess.CalledProcessError as error:
        print(
            "Sensitive strings in history: CANNOT RUN\n"
            f"git failed: {error.stderr.decode('utf-8', errors='replace').strip()}"
        )
        return 1

    body = contents([name for name, _ in blobs])
    for name, path in blobs:
        text = body[name].decode("utf-8", errors=scan.DECODE_ERRORS)
        scan.scan_text(
            text, pathlib.PurePosixPath(path), failures, label=f"{name[:12]} {path}"
        )

    if failures:
        commits = git("rev-list", "--count", REVISION).decode().strip()
        print("Sensitive strings found in the Git history:")
        print("\n".join(failures))
        print(
            f"\nEach line names an object in the history, not a file in the tree: "
            "the content may have been deleted long ago and is published all the "
            "same. `git log --oneline --find-object=<object>` names the commits "
            f"that carry one. {commits} commits were read; removing a string from "
            "the history is a rewrite and a decision for the repository owner."
        )
        return 1

    commits = git("rev-list", "--count", REVISION).decode().strip()
    print(
        f"Sensitive strings in history: PASS "
        f"({len(blobs)} file versions across {commits} commits)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
