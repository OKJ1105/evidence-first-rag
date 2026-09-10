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

**It reads file contents and nothing else.** Commit messages, annotated tag
messages, and author and committer identities are published with the
repository and are as decidable by these rules as a file is, and none of them
is read here. That is a declared limit rather than an oversight, and it is
declared for the reason the tree scan declared its own history gap: a check
that says PASS while silently covering less than its name claims is how a
release gate comes to rest on an incomplete basis. Extending to them is its
own slice and needs a decision first — over this history those rules already
find the addresses in every commit's author metadata, which no commit can
remove.

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

# How many file versions are read and scanned before the next request.
#
# Bounded on purpose. Reading every version at once makes the peak memory the
# size of all distinct blobs in the history, and this scan deliberately does
# not skip `node_modules` or build output — so one committed binary or
# vendored tree would put that peak past a runner's budget. An OOM-killed
# security check reads as an infrastructure flake rather than as a finding,
# which is the worst way for a check like this to fail.
BATCH = 256


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


def git(*arguments):
    """One git command, in bytes, failing loudly."""
    return subprocess.run(
        ("git",) + arguments, cwd=WORK_TREE, capture_output=True, check=True
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


def batched(items, size):
    """`items` in chunks of at most `size`, preserving order."""
    for start in range(0, len(items), size):
        yield items[start : start + size]


def contents(names):
    """Read many blobs in one `git cat-file --batch`.

    The stream is `<name> <type> <size>\\n<size bytes>\\n` per request. It is
    parsed by the declared size rather than by looking for the next header,
    because a blob's own content can contain a line that looks like one.

    Every way the stream can disappoint that parse is turned into a
    `RuntimeError` here rather than left to escape as whatever the arithmetic
    happened to raise, because `main()` answers a `RuntimeError` with
    `CANNOT RUN` and that is the true answer in all of them: git exited 0 and
    what it wrote could not be read. Converting at the source rather than
    widening the handler keeps the reason attached to the object it happened
    on, and keeps `main()` from catching some unrelated `ValueError` under a
    message about git.

    The length check is the one that matters most, and it is the only one of
    the three whose absence is silent. A short final frame leaves Python's
    slice quietly returning fewer bytes than the header declared, with no
    exception anywhere: the scan would then read part of a file version,
    find nothing in the part it read, and report PASS. A security check that
    says "nothing found" when it did not look is the one failure this module
    exists to avoid, and it is the only one of these three that fails open.
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
        end = stream.find(b"\n", at)
        if end == -1:
            raise RuntimeError(
                f"git ended the batch stream mid-header for {name}: "
                f"{stream[at:at + 60]!r}"
            )
        header = stream[at:end].split()
        if len(header) < 3:
            # `<name> missing`. Cannot happen for a name git just listed, but
            # a silent mis-parse of the rest of the stream would be worse.
            raise RuntimeError(f"git could not read {name}: {stream[at:end]!r}")
        try:
            size = int(header[2])
        except ValueError:
            raise RuntimeError(
                f"git declared an unreadable size for {name}: {header[2]!r}"
            ) from None
        blob = stream[end + 1 : end + 1 + size]
        if len(blob) != size:
            raise RuntimeError(
                f"git declared {size} bytes for {name} and wrote {len(blob)}; "
                "the batch stream is truncated"
            )
        body[name] = blob
        at = end + 1 + size + 1
    return body


def cannot_run(detail) -> int:
    """One wording for every way the scan could not look.

    Distinct from a pass and from a finding on purpose: "nothing found" and
    "could not look" are the two answers a scan must never blur, and a
    traceback says the second one badly.
    """
    print(f"Sensitive strings in history: CANNOT RUN\n{detail}")
    return 1


def main() -> int:
    scan = rules()
    failures = []

    # Every git call is inside this, not only the first two: `cat-file
    # --batch` can fail on a partial clone or a corrupt object, and the
    # operator should read the sentence above rather than a traceback.
    try:
        if is_shallow():
            return cannot_run(
                "The repository is a shallow clone, so most of the history is "
                "absent and a pass here would mean nothing. Check out with "
                "fetch-depth: 0."
            )
        blobs = named_objects()
        commits = git("rev-list", "--count", REVISION).decode().strip()
        for chunk in batched(blobs, BATCH):
            # One request per object in the chunk, not one per path it
            # occupies: `cat-file --batch` returns the whole body for every
            # request line. Each chunk is scanned before the next is read, so
            # what is held at once is bounded by `BATCH` rather than by the
            # size of the history.
            body = contents(sorted({name for name, _ in chunk}))
            for name, path in chunk:
                text = body[name].decode("utf-8", errors=scan.DECODE_ERRORS)
                scan.scan_text(
                    text,
                    pathlib.PurePosixPath(path),
                    failures,
                    label=f"{name[:12]} {path}",
                )
    except subprocess.CalledProcessError as error:
        return cannot_run(
            f"git failed: {error.stderr.decode('utf-8', errors='replace').strip()}"
        )
    except RuntimeError as error:
        return cannot_run(str(error))

    if failures:
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

    print(
        f"Sensitive strings in history: PASS "
        f"({len(blobs)} file versions across {commits} commits; "
        "commit messages, tag messages and author identities are not read)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
