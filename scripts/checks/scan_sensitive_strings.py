"""Scan the repository tree for sensitive strings.

Shared by CI (.github/workflows/repository-checks.yml) and the agent loop
(.github/agent-checks.json) so both verify the same thing with the same code,
in the same shape as validate_links.py and validate_fixtures.py.

Charter Section 11 lists "run secret and sensitive-string scans" among the
conditions for a public release, and AGENTS.md already forbids production
data, real records, credentials, secrets, internal URLs, local machine paths
and personal information anywhere in this repository. Both were prose. This
check is the mechanical half: every category in that list that a scanner can
decide is decided here, on every pull request, rather than once at the release
gate when the history is already long.

What it cannot decide is stated rather than implied. "Production data" and
"real records" are not recognizable from their shape; for the registered
fixtures the SAMPLE_* convention that stands in for them is enforced by
validate_fixtures.py, and nothing enforces it for prose. This scan reads the
working tree only, not the Git history that Charter Section 11 also requires.

Placeholder conventions are how a string that has the shape of a secret stays
in the tree legitimately: a value that names a variable rather than carrying
one, or that is marked as an example. Both are matched explicitly below, so
the exemption is auditable and each is probed by a negative test.

Exits 1 and lists every hit when any rule matches.
"""

import pathlib
import re
import sys

ROOT = pathlib.Path(".")

# Directories that hold no reviewable repository content: version control
# metadata, dependency trees, and build or cache output.
SKIP_DIRECTORIES = frozenset(
    {
        ".git",
        ".mypy_cache",
        ".nimbalyst",
        ".pytest_cache",
        ".venv",
        "__pycache__",
        "build",
        "dist",
        "node_modules",
        "venv",
    }
)

# A binary file is decoded rather than skipped. A credential pasted into one is
# still ASCII, and a scanner that skips what it cannot parse has a hole exactly
# where something would be hidden.
DECODE_ERRORS = "replace"

# A value shorter than this is not credential material any service in this
# repository's stack issues; every literal under it in the tree today is a test
# token. The threshold is named so the negative tests can probe both sides.
MINIMUM_SECRET_LENGTH = 12

# A value that names a variable instead of carrying one: shell and GitHub
# Actions expansion, an environment lookup in either language used here, and
# psql's :'name' interpolation, which is handled in the assignment pattern
# because its colon would otherwise read as the assignment operator.
REFERENCE_VALUE = re.compile(
    r"""(?x)
    \A(?:
        [$] | \{\{ | os\.environ | process\.env | getenv | secrets\. | <[^>]*>
    )
    """
)

# A value marked as an example. Deliberately a small closed list: every entry
# is a word that no issued credential contains, and each one widens what may
# sit in the tree, so the list is short and is probed.
PLACEHOLDER_VALUE = re.compile(
    r"(?i)(sample|example|placeholder|dummy|fake|redacted|changeme"
    r"|not[-_]?a[-_]?(real|secret)|\Ax{4,}\Z)"
)

# Domains reserved for documentation and non-delivery. RFC 2606 reserves the
# first group; the GitHub no-reply forms exist so a commit can carry an author
# without publishing an address, which is what makes them not personal
# information.
NON_PERSONAL_EMAIL_DOMAINS = frozenset(
    {
        "example.com",
        "example.net",
        "example.org",
        "invalid",
        "localhost",
        "noreply.github.com",
        "users.noreply.github.com",
    }
)

# Home directory segments that name no particular machine: a documentation
# stand-in, or the fixed account GitHub-hosted runners use.
PORTABLE_HOME_SEGMENTS = frozenset({"runner", "user", "you", "youruser"})

# Languages in which an unquoted value is an expression rather than a literal:
# `password=provisioning_password` passes a name, and the name is the point.
# Everywhere else — YAML, shell, configuration, prose — a bare value is the
# value, so it is read as one. A literal in these files still has to be
# quoted, which is what keeps the rule from being weakened by the exemption.
EXPRESSION_SOURCES = frozenset(
    {".cjs", ".js", ".jsx", ".mjs", ".py", ".sql", ".ts", ".tsx"}
)

_SECRET_NAME = (
    r"[A-Za-z0-9_]*"
    r"(?:password|passwd|secret|token|api[-_]?key|apikey|credential)s?"
)

# The assignment operator is `=`, or `:` when it is not immediately followed by
# a quote: `PASSWORD :'name'` is psql interpolation, not a literal.
_ASSIGNMENT = re.compile(
    r"(?i)\b" + _SECRET_NAME + r"\s*(?:=|:(?!'))\s*"
    r"(?P<quote>[\"'])?(?P<value>(?(quote)[^\"'\n]*|[^\s#,;)\]}]+))"
)

# The last label has to be alphabetic, so a package specifier that carries a
# version after an at-sign is not read as an address.
_EMAIL = re.compile(
    r"(?i)\b[A-Za-z0-9._%+-]+@"
    r"(?P<domain>[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,})\b"
)

_HOME_PATH = re.compile(
    r"(?i)(?:\A|[\s\"'(=:])(?:/(?:home|Users)/|[A-Z]:\\\\?Users\\\\?)"
    r"(?P<segment>[A-Za-z0-9._-]+)"
)

_PRIVATE_ADDRESS = (
    r"(?:10(?:\.\d{1,3}){3}"
    r"|192\.168(?:\.\d{1,3}){2}"
    r"|172\.(?:1[6-9]|2\d|3[01])(?:\.\d{1,3}){2})"
)
_INTERNAL_TLD = r"[A-Za-z0-9-]+\.(?:internal|intranet|corp|lan|local)"
_INTERNAL_HOST = re.compile(
    r"(?i)\b[a-z][a-z0-9+.-]*://(?:[^\s/@\"'<>]*@)?"
    r"(?P<host>" + _PRIVATE_ADDRESS + r"|" + _INTERNAL_TLD + r")\b"
)

_URL_CREDENTIALS = re.compile(
    r"(?i)\b[a-z][a-z0-9+.-]*://[^\s:/@\"'<>]+:(?P<value>[^\s:/@\"'<>]+)@"
)

# Issued-credential shapes, by the prefix each issuer puts on them. A prefix is
# how a scanner recognizes a live credential without guessing at entropy.
_ISSUED_CREDENTIAL = re.compile(
    r"(?x)"
    r"\b(?:"
    r"sk-ant-[A-Za-z0-9_-]{16,}"
    r"|sk-[A-Za-z0-9]{20,}"
    r"|AKIA[0-9A-Z]{16}"
    r"|ASIA[0-9A-Z]{16}"
    r"|gh[pousr]_[A-Za-z0-9]{20,}"
    r"|github_pat_[A-Za-z0-9_]{20,}"
    r"|AIza[0-9A-Za-z_-]{35}"
    r"|xox[abprs]-[A-Za-z0-9-]{10,}"
    r")"
)

_PRIVATE_KEY = re.compile(r"-----BEGIN (?:[A-Z0-9]+ )?PRIVATE KEY-----")


def _exempt_value(value):
    """A value that names a variable or is marked as an example."""
    return bool(REFERENCE_VALUE.match(value) or PLACEHOLDER_VALUE.search(value))


def _assigned_secret(line, path):
    for match in _ASSIGNMENT.finditer(line):
        value = match.group("value")
        if match.group("quote") is None and path.suffix in EXPRESSION_SOURCES:
            continue
        if len(value) < MINIMUM_SECRET_LENGTH or _exempt_value(value):
            continue
        yield value


def _personal_email(line, path):
    for match in _EMAIL.finditer(line):
        if match.group("domain").lower() not in NON_PERSONAL_EMAIL_DOMAINS:
            yield match.group(0)


def _home_path(line, path):
    for match in _HOME_PATH.finditer(line):
        segment = match.group("segment")
        if segment.lower() in PORTABLE_HOME_SEGMENTS or _exempt_value(segment):
            continue
        yield match.group(0).lstrip("\"'(=: \t")


def _matches(pattern, group=0):
    def find(line, path):
        for match in pattern.finditer(line):
            yield match.group(group)

    return find


# Every rule names the clause it enforces, so a hit says which rule of the
# repository it broke rather than only which regex fired. `mask` is set on the
# rules whose match may be a live credential: printing one into a CI log widens
# the exposure the scan exists to stop.
RULES = (
    (
        "private-key",
        "AGENTS.md: never add credentials or secrets",
        _matches(_PRIVATE_KEY),
        True,
    ),
    (
        "issued-credential",
        "AGENTS.md: never add credentials or secrets",
        _matches(_ISSUED_CREDENTIAL),
        True,
    ),
    (
        "assigned-secret",
        "AGENTS.md: never add credentials or secrets",
        _assigned_secret,
        True,
    ),
    (
        "url-credentials",
        "AGENTS.md: never add credentials or secrets",
        _matches(_URL_CREDENTIALS, "value"),
        True,
    ),
    (
        "internal-host",
        "AGENTS.md: never add internal URLs",
        _matches(_INTERNAL_HOST),
        False,
    ),
    (
        "local-machine-path",
        "AGENTS.md: never add local machine paths",
        _home_path,
        False,
    ),
    (
        "personal-email",
        "AGENTS.md: never add personal information",
        _personal_email,
        False,
    ),
)


def mask(text):
    """Report enough of a match to recognize it, not enough to use it."""
    keep = 4
    if len(text) <= keep:
        return "*" * len(text)
    return f"{text[:keep]}... ({len(text)} characters)"


def scan_text(text, where, failures):
    for number, line in enumerate(text.splitlines(), 1):
        for name, clause, find, secret in RULES:
            for hit in find(line, where):
                shown = mask(hit) if secret else hit
                failures.append(f"{where}:{number}: {name}: {shown} — {clause}")


def files(root):
    """Every file under root, skipping directories that hold no reviewable
    repository content."""
    for path in sorted(root.rglob("*")):
        if any(part in SKIP_DIRECTORIES for part in path.parts):
            continue
        if path.is_file() and not path.is_symlink():
            yield path


def main() -> int:
    failures = []
    scanned = 0
    for path in files(ROOT):
        scanned += 1
        text = path.read_bytes().decode("utf-8", errors=DECODE_ERRORS)
        scan_text(text, path, failures)

    if failures:
        print("Sensitive strings found:")
        print("\n".join(failures))
        print(
            "\nEach line names the repository rule it breaks. A value that has "
            "the shape of a secret but is not one belongs in the tree as a "
            "variable reference or under a placeholder convention; see "
            "scripts/checks/scan_sensitive_strings.py."
        )
        return 1

    print(f"Sensitive strings: PASS ({scanned} files scanned)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
