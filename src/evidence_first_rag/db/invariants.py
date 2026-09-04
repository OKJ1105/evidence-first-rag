"""Assert the Section 4.1 constraints and the Section 4.2 rules against the
loaded database.

Section 8 names this as the acceptance evidence for both sections, and Section
4.9 calls it check `C1`. It deliberately does not read the fixture files:
`scripts/checks/validate_fixtures.py` already covers those, and a check that
only re-read them would pass against a schema that enforces nothing. What this
one catches is a schema that fails to enforce what the fixtures happen to
satisfy — a missing unique constraint stays invisible until the day someone
loads data that needs it.

Two kinds of assertion, because introspection and enforcement are different
claims. Introspection reads the catalog and says a constraint is declared.
Probing inserts a row the constraint should reject, inside a savepoint that is
always rolled back, and says the database actually refuses it. A constraint
declared but not enforced would pass the first and fail the second.

Runs as the provisioning identity: probing needs INSERT, which Section 4.3
gives that identity and denies the runtime one.

Sections cited are from docs/contracts/mvp-v0.1.md at version 0.3.0.
"""

import os
import sys

import psycopg

SCHEMA = "mvp"

# Section 4.1. Each entry is (table, columns) for a constraint the contract
# names. Written out rather than derived, so that a constraint dropped from
# the schema fails here instead of shrinking what this check covers.
REQUIRED_UNIQUE = (
    ("source_snapshot", ("project_code", "revision_label", "network_name", "snapshot_label")),
    ("message_occurrence", ("snapshot_id", "message_key")),
    ("signal_occurrence", ("message_occurrence_id", "signal_key")),
    (
        "signal_mapping",
        ("asserting_snapshot_id", "source_signal_occurrence_id", "target_signal_occurrence_id"),
    ),
)

# Section 4.1. Every reference the contract declares not null, as
# (table, column, referenced table).
REQUIRED_FOREIGN_KEYS = (
    ("source_snapshot", "superseded_by", "source_snapshot"),
    ("message_occurrence", "snapshot_id", "source_snapshot"),
    ("signal_occurrence", "message_occurrence_id", "message_occurrence"),
    ("signal_mapping", "asserting_snapshot_id", "source_snapshot"),
    ("signal_mapping", "source_signal_occurrence_id", "signal_occurrence"),
    ("signal_mapping", "target_signal_occurrence_id", "signal_occurrence"),
)

# Section 4.1 nullability. Only the not-null columns are listed; a column the
# contract allows to be null is not asserted either way.
REQUIRED_NOT_NULL = {
    "source_snapshot": ("project_code", "revision_label", "network_name", "snapshot_label", "ingested_at"),
    "message_occurrence": ("snapshot_id", "message_key"),
    "signal_occurrence": ("message_occurrence_id", "signal_key"),
    "signal_mapping": (
        "asserting_snapshot_id",
        "source_signal_occurrence_id",
        "target_signal_occurrence_id",
        "mapping_key",
    ),
}


def check(connection) -> list[str]:
    """Return every failure. An empty list means the database satisfies the
    contract; the caller decides what to do about a non-empty one."""
    failures: list[str] = []
    with connection.cursor() as cursor:
        _check_collation(cursor, failures)
        _check_unique_constraints(cursor, failures)
        _check_prohibited_signal_key_constraint(cursor, failures)
        _check_foreign_keys(cursor, failures)
        _check_not_null(cursor, failures)
        _check_identity_columns(cursor, failures)
        _check_superseded_by_resolves(cursor, failures)
        _check_runtime_role_settings(cursor, failures)
        _probe_unique_enforcement(cursor, failures)
    return failures


def _check_collation(cursor, failures) -> None:
    """Section 6: the database is created with `LC_COLLATE='C'` and the
    evidence bundle records "C". A database that took the cluster default
    would order text by whatever locale the host initialised with."""
    cursor.execute(
        "SELECT datcollate, datctype, pg_encoding_to_char(encoding)"
        " FROM pg_database WHERE datname = current_database()"
    )
    collate, ctype, encoding = cursor.fetchone()
    if collate != "C":
        failures.append(f"Section 6: LC_COLLATE is {collate!r}, expected 'C'")
    if ctype != "C":
        failures.append(f"Section 6: LC_CTYPE is {ctype!r}, expected 'C'")
    if encoding != "UTF8":
        failures.append(f"Section 6: encoding is {encoding!r}, expected 'UTF8'")


def _unique_column_sets(cursor, table: str) -> list[tuple[str, ...]]:
    """Every unique constraint or unique index on one table, as column tuples."""
    cursor.execute(
        """
        SELECT array_agg(a.attname ORDER BY k.ordinality)
        FROM pg_index i
        JOIN pg_class t ON t.oid = i.indrelid
        JOIN pg_namespace n ON n.oid = t.relnamespace
        CROSS JOIN LATERAL unnest(i.indkey) WITH ORDINALITY AS k(attnum, ordinality)
        JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = k.attnum
        WHERE n.nspname = %s AND t.relname = %s AND i.indisunique
        GROUP BY i.indexrelid
        """,
        (SCHEMA, table),
    )
    return [tuple(row[0]) for row in cursor.fetchall()]


def _check_unique_constraints(cursor, failures) -> None:
    for table, columns in REQUIRED_UNIQUE:
        found = _unique_column_sets(cursor, table)
        if not any(set(candidate) == set(columns) for candidate in found):
            failures.append(
                f"Section 4.1: {table} has no unique constraint on {list(columns)};"
                f" found {[list(c) for c in found]}"
            )


def _check_prohibited_signal_key_constraint(cursor, failures) -> None:
    """Section 4.1: "A snapshot-level unique constraint on `signal_key` is
    prohibited."

    Section 4.2 explains why: continuity between occurrences in different
    snapshots is never derived from equal keys, and `FX-102` loads two signals
    that share a key under different parents. Any unique constraint that
    includes `signal_key` without also including the parent message would make
    that fixture unloadable, so the absence is asserted rather than assumed.
    """
    for candidate in _unique_column_sets(cursor, "signal_occurrence"):
        if "signal_key" in candidate and "message_occurrence_id" not in candidate:
            failures.append(
                f"Section 4.1: signal_occurrence has a prohibited unique constraint on"
                f" {list(candidate)}; a constraint over signal_key must include"
                f" message_occurrence_id"
            )
    # The same prohibition, one level up: a message key is unique within its
    # snapshot and nowhere else.
    for candidate in _unique_column_sets(cursor, "message_occurrence"):
        if "message_key" in candidate and "snapshot_id" not in candidate:
            failures.append(
                f"Section 4.1: message_occurrence has a prohibited unique constraint on"
                f" {list(candidate)}; a constraint over message_key must include"
                f" snapshot_id"
            )


def _check_foreign_keys(cursor, failures) -> None:
    cursor.execute(
        """
        SELECT t.relname, a.attname, f.relname
        FROM pg_constraint c
        JOIN pg_class t ON t.oid = c.conrelid
        JOIN pg_class f ON f.oid = c.confrelid
        JOIN pg_namespace n ON n.oid = t.relnamespace
        CROSS JOIN LATERAL unnest(c.conkey) AS k(attnum)
        JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = k.attnum
        WHERE c.contype = 'f' AND n.nspname = %s
        """,
        (SCHEMA,),
    )
    found = {tuple(row) for row in cursor.fetchall()}
    for expected in REQUIRED_FOREIGN_KEYS:
        if expected not in found:
            failures.append(
                f"Section 4.1: no foreign key {expected[0]}.{expected[1]}"
                f" -> {expected[2]}"
            )


def _check_not_null(cursor, failures) -> None:
    cursor.execute(
        """
        SELECT table_name, column_name
        FROM information_schema.columns
        WHERE table_schema = %s AND is_nullable = 'NO'
        """,
        (SCHEMA,),
    )
    found = {tuple(row) for row in cursor.fetchall()}
    for table, columns in REQUIRED_NOT_NULL.items():
        for column in columns:
            if (table, column) not in found:
                failures.append(f"Section 4.1: {table}.{column} is nullable, expected NOT NULL")


def _check_identity_columns(cursor, failures) -> None:
    """Section 4.11: surrogate keys are PostgreSQL identity columns, assigned
    at load, and appear in no fixture file. GENERATED ALWAYS is what refuses a
    loader that tried to supply one."""
    expected = {
        "source_snapshot": "snapshot_id",
        "message_occurrence": "message_occurrence_id",
        "signal_occurrence": "signal_occurrence_id",
        "signal_mapping": "signal_mapping_id",
    }
    cursor.execute(
        """
        SELECT table_name, column_name, is_identity, identity_generation
        FROM information_schema.columns
        WHERE table_schema = %s
        """,
        (SCHEMA,),
    )
    found = {(row[0], row[1]): (row[2], row[3]) for row in cursor.fetchall()}
    for table, column in expected.items():
        identity, generation = found.get((table, column), (None, None))
        if identity != "YES" or generation != "ALWAYS":
            failures.append(
                f"Section 4.11: {table}.{column} is not a GENERATED ALWAYS identity"
                f" column (is_identity={identity!r}, generation={generation!r})"
            )


def _check_superseded_by_resolves(cursor, failures) -> None:
    """Section 4.2 exposes `superseded_by` in `limitations`, so a dangling or
    self-referential value would put a meaningless entry on a real result.
    The foreign key covers the dangling case; this covers the self-reference
    and reports the row rather than only the constraint."""
    cursor.execute(
        f"SELECT count(*) FROM {SCHEMA}.source_snapshot WHERE superseded_by = snapshot_id"
    )
    (self_superseding,) = cursor.fetchone()
    if self_superseding:
        failures.append(
            f"Section 4.2: {self_superseding} snapshot(s) supersede themselves"
        )


def _check_runtime_role_settings(cursor, failures) -> None:
    """Section 4.4: "The runtime identity runs with `statement_timeout = 5s`,
    set at the role level by provisioning." Set on the role rather than per
    session, so a runtime that forgets it still gets it."""
    cursor.execute(
        "SELECT rolconfig FROM pg_roles WHERE rolname = %s", ("mvp_runtime",)
    )
    row = cursor.fetchone()
    if row is None:
        failures.append("Section 4.3: role mvp_runtime does not exist")
        return
    settings = dict(
        item.split("=", 1) for item in (row[0] or []) if "=" in item
    )
    if settings.get("statement_timeout") != "5s":
        failures.append(
            f"Section 4.4: mvp_runtime statement_timeout is"
            f" {settings.get('statement_timeout')!r}, expected '5s'"
        )
    if settings.get("default_transaction_read_only") != "on":
        failures.append(
            f"Section 4.3: mvp_runtime default_transaction_read_only is"
            f" {settings.get('default_transaction_read_only')!r}, expected 'on'"
        )


def _probe_unique_enforcement(cursor, failures) -> None:
    """Insert a duplicate of a row that already exists and require the database
    to refuse it.

    A constraint can be declared and not enforced — NOT VALID, disabled, or
    declared on the wrong columns in a way the catalog check above happens to
    accept. Introspection cannot tell the difference; an insert can. Every
    probe runs inside a savepoint that is rolled back whether it fails or not,
    so this check leaves the database exactly as it found it.
    """
    probes = (
        (
            "source_snapshot",
            "Section 4.1 (project_code, revision_label, network_name, snapshot_label)",
            f"""INSERT INTO {SCHEMA}.source_snapshot
                    (project_code, revision_label, network_name, snapshot_label,
                     superseded_by, ingested_at)
                SELECT project_code, revision_label, network_name, snapshot_label,
                       NULL, ingested_at
                FROM {SCHEMA}.source_snapshot LIMIT 1""",
        ),
        (
            "message_occurrence",
            "Section 4.1 (snapshot_id, message_key)",
            f"""INSERT INTO {SCHEMA}.message_occurrence (snapshot_id, message_key)
                SELECT snapshot_id, message_key
                FROM {SCHEMA}.message_occurrence LIMIT 1""",
        ),
        (
            "signal_occurrence",
            "Section 4.1 (message_occurrence_id, signal_key)",
            f"""INSERT INTO {SCHEMA}.signal_occurrence (message_occurrence_id, signal_key)
                SELECT message_occurrence_id, signal_key
                FROM {SCHEMA}.signal_occurrence LIMIT 1""",
        ),
        (
            "signal_mapping",
            "Section 4.1 (asserting_snapshot_id, source_signal_occurrence_id,"
            " target_signal_occurrence_id)",
            f"""INSERT INTO {SCHEMA}.signal_mapping
                    (asserting_snapshot_id, source_signal_occurrence_id,
                     target_signal_occurrence_id, mapping_key)
                SELECT asserting_snapshot_id, source_signal_occurrence_id,
                       target_signal_occurrence_id, mapping_key
                FROM {SCHEMA}.signal_mapping LIMIT 1""",
        ),
    )
    for table, what, statement in probes:
        cursor.execute("SAVEPOINT probe")
        try:
            cursor.execute(statement)
        except psycopg.errors.UniqueViolation:
            pass
        else:
            failures.append(
                f"{what}: {table} accepted a duplicate row; the constraint is"
                f" declared but not enforced"
            )
        finally:
            cursor.execute("ROLLBACK TO SAVEPOINT probe")


def main() -> int:
    with psycopg.connect(
        dbname=os.environ.get("MVP_DATABASE", "mvp"),
        user=os.environ.get("MVP_PROVISIONING_USER", "mvp_provisioning"),
        password=os.environ.get("MVP_PROVISIONING_PASSWORD"),
        host=os.environ.get("PGHOST"),
        port=os.environ.get("PGPORT"),
    ) as connection:
        failures = check(connection)
        # Nothing this check does may outlive it. The probes roll back to
        # their savepoints, and the transaction is discarded rather than
        # committed, so Section 4.10's "unchanged from the start of the run to
        # its end" is not something the invariant check itself can break.
        connection.rollback()

    if failures:
        print("Data-level invariants: FAIL")
        for failure in failures:
            print(f"  {failure}")
        return 1
    print("Data-level invariants: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
