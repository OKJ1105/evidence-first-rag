"""Validate the registered fixtures against the accepted MVP runtime contract.

Shared by CI (.github/workflows/repository-checks.yml) and the agent loop
(.github/agent-checks.json) so both verify the same thing with the same code,
in the same shape as validate_links.py.

This check is about the fixture FILES, not about a database. It runs with no
PostgreSQL and no loader, because neither exists yet. What it proves is that
the registered inputs every later slice is judged against are well-formed,
reference-complete, and still carry the structural cases the contract's
acceptance evidence depends on.

Sections cited below are from docs/contracts/mvp-v0.1.md at version 0.3.0.
Exits 1 and lists every failure when any assertion does not hold.
"""

import json
import pathlib
import re
import sys

FIXTURES = pathlib.Path("fixtures")

# Section 4.11: identifiers are ASCII, and entity-like names use SAMPLE_*.
ASCII_IDENTIFIER = re.compile(r"\A[A-Za-z0-9_.\-]+\Z")
SAMPLE_IDENTIFIER = re.compile(r"\ASAMPLE_[A-Za-z0-9_.\-]+\Z")

# Section 4.2 canonical reference tuples. A fixture never references a row by
# a surrogate value, so these are the only ways one row can name another.
SNAPSHOT_REF = ("project_code", "revision_label", "network_name", "snapshot_label")
MESSAGE_REF = SNAPSHOT_REF + ("message_key",)
SIGNAL_REF = MESSAGE_REF + ("signal_key",)

# Section 4.11 forbids surrogate keys in fixture files. Naming them explicitly
# beats a heuristic: a file that leaks one fails here rather than loading a
# value that Section 6 permits to differ between provisioning runs.
SURROGATE_KEYS = frozenset(
    {
        "snapshot_id",
        "message_occurrence_id",
        "signal_occurrence_id",
        "signal_mapping_id",
        "asserting_snapshot_id",
        "source_signal_occurrence_id",
        "target_signal_occurrence_id",
    }
)

# Column sets from Section 4.1, with the reference columns expressed as the
# natural keys Section 4.11 requires instead of the surrogates the schema uses.
# `True` means the value may be null; `False` means not null.
TABLES = {
    "source_snapshot": {
        "project_code": False,
        "revision_label": False,
        "network_name": False,
        "snapshot_label": False,
        "superseded_by": True,
        "ingested_at": False,
    },
    "message_occurrence": {
        "snapshot": False,
        "message_key": False,
        "transmit_mode": True,
        "transmit_period_ms": True,
        "payload_byte_length": True,
        "frame_identifier": True,
    },
    "signal_occurrence": {
        "message": False,
        "signal_key": False,
        "unit_label": True,
        "scale_factor": True,
        "scale_offset": True,
        "bit_width": True,
        "bit_offset": True,
    },
    "signal_mapping": {
        "asserting_snapshot": False,
        "source_signal": False,
        "target_signal": False,
        "mapping_key": False,
        "transform_kind": True,
    },
}

# Values the negative cases in Section 8.1 depend on being absent. A fixture
# that later adds one of these silently turns a negative case positive, so the
# absence is asserted rather than assumed.
RESERVED_ABSENT = {
    "network_name": ["SAMPLE_NET_BODY"],  # FX-106 coverage_gap
    "message_key": ["SAMPLE_MSG_ABSENT"],  # FX-107 not_found
    "signal_key": ["SAMPLE_SIG_ABSENT"],  # FX-107 not_found
}


def load(name, failures):
    """Parse one JSON Lines fixture file into a list of (line number, row)."""
    path = FIXTURES / f"{name}.jsonl"
    if not path.exists():
        failures.append(f"{path}: missing")
        return []
    rows = []
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            failures.append(f"{path}:{number}: blank line; one line is one row")
            continue
        try:
            row = json.loads(raw)
        except json.JSONDecodeError as error:
            failures.append(f"{path}:{number}: not valid JSON: {error}")
            continue
        if not isinstance(row, dict):
            failures.append(f"{path}:{number}: line is not a JSON object")
            continue
        rows.append((number, row))
    return rows


def walk(value, path=""):
    """Yield (dotted path, key, value) for every key in a nested row."""
    if isinstance(value, dict):
        for key, inner in value.items():
            here = f"{path}.{key}" if path else key
            yield here, key, inner
            yield from walk(inner, here)


def check_columns(name, rows, failures):
    """Section 4.1 column sets and nullability, and the Section 4.11 ban on
    surrogate keys anywhere in the file."""
    declared = TABLES[name]
    path = FIXTURES / f"{name}.jsonl"
    for number, row in rows:
        where = f"{path}:{number}"
        missing = sorted(set(declared) - set(row))
        extra = sorted(set(row) - set(declared))
        if missing:
            failures.append(f"{where}: missing columns {missing}")
        if extra:
            failures.append(f"{where}: columns not in Section 4.1: {extra}")
        for column, nullable in declared.items():
            if column in row and row[column] is None and not nullable:
                failures.append(f"{where}: {column} is not null in Section 4.1")
        for dotted, key, _ in walk(row):
            if key in SURROGATE_KEYS:
                failures.append(
                    f"{where}: surrogate key {dotted!r}; Section 4.11 forbids one"
                )


def check_identifiers(name, rows, failures):
    """Section 4.11: ASCII identifiers, and SAMPLE_* for entity-like names."""
    path = FIXTURES / f"{name}.jsonl"
    entity_like = {
        "project_code",
        "revision_label",
        "network_name",
        "snapshot_label",
        "message_key",
        "signal_key",
        "mapping_key",
        "transmit_mode",
        "unit_label",
        "transform_kind",
    }
    for number, row in rows:
        where = f"{path}:{number}"
        for dotted, key, value in walk(row):
            if not isinstance(value, str) or key not in entity_like:
                continue
            if not ASCII_IDENTIFIER.match(value):
                failures.append(f"{where}: {dotted}={value!r} is not ASCII")
            elif not SAMPLE_IDENTIFIER.match(value):
                failures.append(
                    f"{where}: {dotted}={value!r} does not use the SAMPLE_* convention"
                )


def key_of(value, fields, where, label, failures):
    """Read a natural-key reference, reporting a malformed one rather than
    raising. Returns None when the reference cannot be read."""
    if not isinstance(value, dict):
        failures.append(f"{where}: {label} is not a natural-key object")
        return None
    missing = sorted(set(fields) - set(value))
    extra = sorted(set(value) - set(fields))
    if missing or extra:
        failures.append(
            f"{where}: {label} is not a Section 4.2 reference; "
            f"missing {missing}, unexpected {extra}"
        )
        return None
    return tuple(value[field] for field in fields)


def check_unique(rows, key_for, constraint, failures):
    """One Section 4.1 unique constraint over the fixture rows."""
    seen = {}
    for where, key in ((w, key_for(r)) for w, r in rows):
        if key is None:
            continue
        if key in seen:
            failures.append(
                f"{where}: duplicate {constraint} {key}; first seen at {seen[key]}"
            )
        else:
            seen[key] = where


def main() -> int:
    failures = []

    snapshots = load("source_snapshot", failures)
    messages = load("message_occurrence", failures)
    signals = load("signal_occurrence", failures)
    mappings = load("signal_mapping", failures)

    for name, rows in (
        ("source_snapshot", snapshots),
        ("message_occurrence", messages),
        ("signal_occurrence", signals),
        ("signal_mapping", mappings),
    ):
        check_columns(name, rows, failures)
        check_identifiers(name, rows, failures)

    def at(name, number):
        return f"{FIXTURES / (name + '.jsonl')}:{number}"

    # --- Section 4.1 unique constraints -------------------------------------

    snapshot_keys = set()
    for number, row in snapshots:
        key = tuple(row.get(field) for field in SNAPSHOT_REF)
        snapshot_keys.add(key)
    check_unique(
        [(at("source_snapshot", n), r) for n, r in snapshots],
        lambda r: tuple(r.get(f) for f in SNAPSHOT_REF),
        "(project_code, revision_label, network_name, snapshot_label)",
        failures,
    )

    message_keys = set()
    for number, row in messages:
        where = at("message_occurrence", number)
        parent = key_of(row.get("snapshot"), SNAPSHOT_REF, where, "snapshot", failures)
        if parent is None:
            continue
        if parent not in snapshot_keys:
            failures.append(f"{where}: snapshot reference {parent} does not resolve")
        message_keys.add(parent + (row.get("message_key"),))
    check_unique(
        [(at("message_occurrence", n), r) for n, r in messages],
        lambda r: (
            tuple((r.get("snapshot") or {}).get(f) for f in SNAPSHOT_REF)
            + (r.get("message_key"),)
        ),
        "(snapshot_id, message_key)",
        failures,
    )

    signal_keys = set()
    for number, row in signals:
        where = at("signal_occurrence", number)
        parent = key_of(row.get("message"), MESSAGE_REF, where, "message", failures)
        if parent is None:
            continue
        if parent not in message_keys:
            failures.append(f"{where}: message reference {parent} does not resolve")
        signal_keys.add(parent + (row.get("signal_key"),))
    check_unique(
        [(at("signal_occurrence", n), r) for n, r in signals],
        lambda r: (
            tuple((r.get("message") or {}).get(f) for f in MESSAGE_REF)
            + (r.get("signal_key"),)
        ),
        "(message_occurrence_id, signal_key)",
        failures,
    )

    mapped_sources = set()
    for number, row in mappings:
        where = at("signal_mapping", number)
        asserting = key_of(
            row.get("asserting_snapshot"), SNAPSHOT_REF, where, "asserting_snapshot", failures
        )
        if asserting is not None and asserting not in snapshot_keys:
            failures.append(
                f"{where}: asserting_snapshot reference {asserting} does not resolve"
            )
        for side in ("source_signal", "target_signal"):
            endpoint = key_of(row.get(side), SIGNAL_REF, where, side, failures)
            if endpoint is None:
                continue
            if endpoint not in signal_keys:
                failures.append(f"{where}: {side} reference {endpoint} does not resolve")
            elif side == "source_signal":
                mapped_sources.add(endpoint)
    check_unique(
        [(at("signal_mapping", n), r) for n, r in mappings],
        lambda r: (
            tuple((r.get("asserting_snapshot") or {}).get(f) for f in SNAPSHOT_REF),
            tuple((r.get("source_signal") or {}).get(f) for f in SIGNAL_REF),
            tuple((r.get("target_signal") or {}).get(f) for f in SIGNAL_REF),
        ),
        "(asserting_snapshot_id, source_signal_occurrence_id, target_signal_occurrence_id)",
        failures,
    )

    # `superseded_by` resolves, and no snapshot supersedes itself.
    superseded = set()
    for number, row in snapshots:
        where = at("source_snapshot", number)
        value = row.get("superseded_by")
        if value is None:
            continue
        successor = key_of(value, SNAPSHOT_REF, where, "superseded_by", failures)
        if successor is None:
            continue
        if successor not in snapshot_keys:
            failures.append(f"{where}: superseded_by {successor} does not resolve")
        own = tuple(row.get(field) for field in SNAPSHOT_REF)
        if successor == own:
            failures.append(f"{where}: snapshot supersedes itself")
        superseded.add(own)

    # --- Section 8.1 structural cases ---------------------------------------
    #
    # Each assertion below keeps one acceptance-evidence case reachable. A
    # later edit that removes the structure fails here, naming the case it
    # broke, instead of turning a fixture green for the wrong reason.

    def require(condition, case, requirement):
        if not condition:
            failures.append(f"{case}: {requirement}")

    require(bool(messages), "FX-001", "no message occurrence exists to return")
    require(bool(signals), "FX-002", "no signal occurrence exists to return")

    sources = [tuple((r.get("source_signal") or {}).get(f) for f in SIGNAL_REF) for _, r in mappings]
    require(
        any(sources.count(s) > 1 for s in sources),
        "FX-003",
        "no source signal has more than one mapping row, so the multi-row case cannot arise",
    )

    per_message_key = {}
    for key in message_keys:
        per_message_key.setdefault(key[-1], set()).add(key[:-1])
    require(
        any(len(scopes) > 1 for scopes in per_message_key.values()),
        "FX-101",
        "no message_key appears in two snapshots, so cross-snapshot name collision is untested",
    )

    per_signal_key_in_snapshot = {}
    for key in signal_keys:
        snapshot, message_key, signal_key = key[:4], key[4], key[5]
        per_signal_key_in_snapshot.setdefault((snapshot, signal_key), set()).add(message_key)
    require(
        any(len(parents) > 1 for parents in per_signal_key_in_snapshot.values()),
        "FX-102",
        "no signal_key appears under two parent messages in one snapshot, so the "
        "prohibited snapshot-level unique constraint on signal_key would pass unnoticed",
    )

    require(
        bool(signal_keys - mapped_sources),
        "FX-103",
        "every signal is the source of some mapping, so the no-mapping case cannot arise",
    )

    require(
        any(
            tuple((r.get("asserting_snapshot") or {}).get(f) for f in SNAPSHOT_REF) in superseded
            for _, r in mappings
        ),
        "FX-104",
        "no mapping is asserted by a superseded snapshot",
    )

    candidates = {}
    for key in snapshot_keys:
        candidates.setdefault(key[:3], set()).add(key[3])
    ambiguous_groups = {
        scope: labels for scope, labels in candidates.items() if len(labels) > 1
    }
    require(
        bool(ambiguous_groups),
        "FX-105",
        "no (project_code, revision_label, network_name) has two snapshot_labels, "
        "so an omitted scope can never be ambiguous",
    )

    # Section 4.2 forbids selecting a snapshot by newest ingested_at. Keep at
    # least one ambiguous group where ingested_at order disagrees with
    # snapshot_label order, so an implementation that quietly picks the newest
    # returns the wrong row rather than the right one by luck.
    ingested = {
        tuple(row.get(field) for field in SNAPSHOT_REF): row.get("ingested_at")
        for _, row in snapshots
    }
    require(
        any(
            sorted(labels)
            != sorted(labels, key=lambda label: ingested.get(scope + (label,)) or "")
            for scope, labels in ambiguous_groups.items()
        ),
        "FX-105",
        "in every ambiguous group ingested_at order agrees with snapshot_label order, "
        "so a runtime that selects the newest snapshot would pass by coincidence",
    )

    present = {field: set() for field in RESERVED_ABSENT}
    for rows in (snapshots, messages, signals, mappings):
        for _, row in rows:
            for _, key, value in walk(row):
                if key in present and isinstance(value, str):
                    present[key].add(value)
    for field, reserved in RESERVED_ABSENT.items():
        for value in reserved:
            if value in present[field]:
                failures.append(
                    f"reserved-absent {field} {value!r} is present; the Section 8.1 "
                    "negative case that depends on its absence no longer holds"
                )
    require(
        bool(present["network_name"]),
        "FX-106",
        "no network_name exists, so a coverage gap cannot be distinguished from an empty database",
    )

    if failures:
        print("Fixture validation failed:")
        print("\n".join(failures))
        return 1

    print(
        "Fixtures: PASS "
        f"({len(snapshots)} snapshots, {len(messages)} messages, "
        f"{len(signals)} signals, {len(mappings)} mappings)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
