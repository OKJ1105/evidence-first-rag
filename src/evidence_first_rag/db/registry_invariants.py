"""Assert entity-discovery-v0.1 Section 4.1's constraints and Section 4.2's
rules against the loaded registry.

The registry's half of `invariants.py`, called from it so that one command
-- `python -m evidence_first_rag.db.invariants` -- is the data-level check
for both contracts. Same two kinds of assertion, for the same reason:
introspection says a constraint is declared; a probe, inside a savepoint
that is always rolled back, says the database actually refuses the row.

And one kind the mvp-v0.1 check does not need. `entity_match_term` is
derived (Section 4.2 rule 2), so the check recomputes it: every row's
`match_tokens` must equal the Section 4.5 normalization of its `match_text`,
every entity must have exactly one `lookup_key` row carrying its occurrence's
key, every other row must name exactly one alias. And `registry_digest` must
equal a recomputation from the loaded rows -- through the loader's own
serializer here, so the stored value and the code that wrote it cannot
drift; the *independent* recomputation Section 8 also asks for, written from
the contract's key table rather than from the code, is in
tests_database/test_registry.py.

Runs as the provisioning identity: probing needs INSERT.
"""

import psycopg

from ..discovery import normalize
from . import registry

SCHEMA = "mvp"

REGISTRY_TABLES = ("approved_entity", "approved_alias", "entity_match_term", "entity_registry_state")

# Section 4.1. (table, columns) for each unique constraint. The two "approved
# once" constraints are partial unique indexes and are asserted separately.
REQUIRED_UNIQUE = (
    ("approved_alias", ("approved_entity_id", "alias_text")),
    ("entity_match_term", ("approved_entity_id", "match_kind", "match_text")),
)

# Section 4.1: partial unique indexes over the non-null rows.
REQUIRED_PARTIAL_UNIQUE = (
    ("approved_entity", "message_occurrence_id"),
    ("approved_entity", "signal_occurrence_id"),
)

# Section 4.1 foreign keys, into the mvp-v0.1 tables and within the registry.
REQUIRED_FOREIGN_KEYS = (
    ("approved_entity", "message_occurrence_id", "message_occurrence"),
    ("approved_entity", "signal_occurrence_id", "signal_occurrence"),
    ("approved_alias", "approved_entity_id", "approved_entity"),
    ("approved_alias", "asserting_snapshot_id", "source_snapshot"),
    ("entity_match_term", "approved_entity_id", "approved_entity"),
    ("entity_match_term", "approved_alias_id", "approved_alias"),
)

REQUIRED_NOT_NULL = {
    "approved_entity": ("entity_kind", "approval_reference", "approved_at"),
    "approved_alias": (
        "approved_entity_id", "alias_text", "alias_kind", "asserting_snapshot_id",
        "approval_reference", "approved_at",
    ),
    "entity_match_term": ("approved_entity_id", "match_kind", "match_text", "match_tokens"),
    "entity_registry_state": ("registry_digest", "built_at"),
}

# Section 4.1 check constraints, by the name 020_registry.sql gives each. A
# probe below inserts a row each one should refuse, so a constraint that was
# renamed and quietly dropped fails twice.
REQUIRED_CHECKS = {
    "approved_entity": ("approved_entity_kind_enumerated", "approved_entity_one_occurrence"),
    "approved_alias": ("approved_alias_kind_enumerated",),
    "entity_match_term": (
        "entity_match_term_kind_enumerated",
        "entity_match_term_alias_when_not_key",
        "entity_match_term_has_a_token",
    ),
    "entity_registry_state": ("entity_registry_state_only_row_is_true",),
}


def check(cursor, failures: list[str]) -> None:
    """Append every failure to `failures`. The caller owns the transaction
    and rolls it back; nothing here commits."""
    _check_unique_constraints(cursor, failures)
    _check_partial_unique(cursor, failures)
    _check_no_unique_on_alias_text_alone(cursor, failures)
    _check_foreign_keys(cursor, failures)
    _check_not_null(cursor, failures)
    _check_check_constraints(cursor, failures)
    _check_identity_columns(cursor, failures)
    _check_runtime_grants(cursor, failures)
    _check_derived_surface(cursor, failures)
    _check_state_row_and_digest(cursor, failures)
    _probe_enforcement(cursor, failures)


def _unique_column_sets(cursor, table: str, partial: bool | None = None):
    """Unique indexes on `table` as (columns, is_partial) pairs."""
    cursor.execute(
        """
        SELECT array_agg(a.attname ORDER BY k.ordinality), i.indpred IS NOT NULL
        FROM pg_index i
        JOIN pg_class t ON t.oid = i.indrelid
        JOIN pg_namespace n ON n.oid = t.relnamespace
        CROSS JOIN LATERAL unnest(i.indkey) WITH ORDINALITY AS k(attnum, ordinality)
        JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = k.attnum
        WHERE n.nspname = %s AND t.relname = %s AND i.indisunique
        GROUP BY i.indexrelid, i.indpred
        """,
        (SCHEMA, table),
    )
    found = [(tuple(row[0]), row[1]) for row in cursor.fetchall()]
    if partial is None:
        return found
    return [columns for columns, is_partial in found if is_partial == partial]


def _check_unique_constraints(cursor, failures) -> None:
    for table, columns in REQUIRED_UNIQUE:
        found = _unique_column_sets(cursor, table, partial=False)
        if not any(set(candidate) == set(columns) for candidate in found):
            failures.append(
                f"Section 4.1: {table} has no unique constraint on {list(columns)};"
                f" found {[list(c) for c in found]}"
            )


def _check_partial_unique(cursor, failures) -> None:
    for table, column in REQUIRED_PARTIAL_UNIQUE:
        found = _unique_column_sets(cursor, table, partial=True)
        if (column,) not in found:
            failures.append(
                f"Section 4.1: {table} has no partial unique index on {column}"
                f" over its non-null rows; an occurrence could be approved twice"
            )


def _check_no_unique_on_alias_text_alone(cursor, failures) -> None:
    """Section 4.1: "There is deliberately no unique constraint on
    `alias_text` alone." One would turn DX-004's collision into a load-time
    error and tempt a later author to delete one side of it."""
    for columns, _ in _unique_column_sets(cursor, "approved_alias"):
        if "alias_text" in columns and "approved_entity_id" not in columns:
            failures.append(
                f"Section 4.1: approved_alias has a prohibited unique constraint on"
                f" {list(columns)}; a constraint over alias_text must include"
                f" approved_entity_id"
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
                f"Section 4.1: no foreign key {expected[0]}.{expected[1]} -> {expected[2]}"
            )


def _check_not_null(cursor, failures) -> None:
    cursor.execute(
        "SELECT table_name, column_name FROM information_schema.columns"
        " WHERE table_schema = %s AND is_nullable = 'NO'",
        (SCHEMA,),
    )
    found = {tuple(row) for row in cursor.fetchall()}
    for table, columns in REQUIRED_NOT_NULL.items():
        for column in columns:
            if (table, column) not in found:
                failures.append(f"Section 4.1: {table}.{column} is nullable, expected NOT NULL")


def _check_check_constraints(cursor, failures) -> None:
    cursor.execute(
        """
        SELECT t.relname, c.conname
        FROM pg_constraint c
        JOIN pg_class t ON t.oid = c.conrelid
        JOIN pg_namespace n ON n.oid = t.relnamespace
        WHERE c.contype = 'c' AND n.nspname = %s
        """,
        (SCHEMA,),
    )
    found = {tuple(row) for row in cursor.fetchall()}
    for table, names in REQUIRED_CHECKS.items():
        for name in names:
            if (table, name) not in found:
                failures.append(f"Section 4.1: {table} has no check constraint {name}")


def _check_identity_columns(cursor, failures) -> None:
    expected = {
        "approved_entity": "approved_entity_id",
        "approved_alias": "approved_alias_id",
        "entity_match_term": "entity_match_term_id",
    }
    cursor.execute(
        "SELECT table_name, column_name, is_identity, identity_generation"
        " FROM information_schema.columns WHERE table_schema = %s",
        (SCHEMA,),
    )
    found = {(row[0], row[1]): (row[2], row[3]) for row in cursor.fetchall()}
    for table, column in expected.items():
        identity, generation = found.get((table, column), (None, None))
        if identity != "YES" or generation != "ALWAYS":
            failures.append(
                f"Section 4.1: {table}.{column} is not a GENERATED ALWAYS identity column"
            )


def _check_runtime_grants(cursor, failures) -> None:
    """Section 3.3 extension 2 and Section 4.12: SELECT and nothing else."""
    for table in REGISTRY_TABLES:
        cursor.execute(
            "SELECT has_table_privilege('mvp_runtime', %s, 'SELECT')", (f"{SCHEMA}.{table}",)
        )
        if not cursor.fetchone()[0]:
            failures.append(f"Section 3.3: mvp_runtime cannot SELECT {table}")
        for privilege in ("INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER"):
            cursor.execute(
                "SELECT has_table_privilege('mvp_runtime', %s, %s)",
                (f"{SCHEMA}.{table}", privilege),
            )
            if cursor.fetchone()[0]:
                failures.append(f"Section 4.12: mvp_runtime holds {privilege} on {table}")


def _check_derived_surface(cursor, failures) -> None:
    """Section 4.2 rule 2, recomputed against the loaded rows."""
    # Every row's tokens are the normalization of its text.
    cursor.execute(
        f"SELECT entity_match_term_id, match_text, match_tokens FROM {SCHEMA}.entity_match_term"
    )
    for identifier, text, tokens in cursor.fetchall():
        expected = normalize(text)
        if list(tokens) != expected:
            failures.append(
                f"Section 4.2 rule 2: entity_match_term {identifier} carries tokens"
                f" {list(tokens)} for {text!r}; Section 4.5 gives {expected}"
            )
        if not expected:
            failures.append(
                f"Section 4.2 rule 5: entity_match_term {identifier} text {text!r}"
                f" normalizes to no token"
            )

    # Exactly one lookup_key row per entity, carrying that occurrence's key.
    cursor.execute(
        f"""
        SELECT e.approved_entity_id,
               COALESCE(m.message_key, g.signal_key) AS occurrence_key,
               array_agg(x.match_text) FILTER (WHERE x.match_kind = 'lookup_key')
        FROM {SCHEMA}.approved_entity e
        LEFT JOIN {SCHEMA}.message_occurrence m ON m.message_occurrence_id = e.message_occurrence_id
        LEFT JOIN {SCHEMA}.signal_occurrence g ON g.signal_occurrence_id = e.signal_occurrence_id
        LEFT JOIN {SCHEMA}.entity_match_term x ON x.approved_entity_id = e.approved_entity_id
        GROUP BY e.approved_entity_id, occurrence_key
        """
    )
    for identifier, key, lookup_texts in cursor.fetchall():
        texts = list(lookup_texts or [])
        if texts != [key]:
            failures.append(
                f"Section 4.2 rule 2: approved_entity {identifier} has lookup_key rows"
                f" {texts}; expected exactly one carrying {key!r}"
            )

    # Every non-lookup_key row corresponds to exactly one alias row, of the
    # same entity, text and kind; and every alias has its row.
    cursor.execute(
        f"""
        SELECT x.entity_match_term_id
        FROM {SCHEMA}.entity_match_term x
        LEFT JOIN {SCHEMA}.approved_alias a ON a.approved_alias_id = x.approved_alias_id
        WHERE x.match_kind <> 'lookup_key'
          AND (a.approved_alias_id IS NULL
               OR a.approved_entity_id <> x.approved_entity_id
               OR a.alias_text <> x.match_text
               OR a.alias_kind <> x.match_kind)
        """
    )
    for (identifier,) in cursor.fetchall():
        failures.append(
            f"Section 4.2 rule 2: entity_match_term {identifier} does not correspond"
            f" to the alias row it names"
        )
    cursor.execute(
        f"""
        SELECT a.approved_alias_id, count(x.entity_match_term_id)
        FROM {SCHEMA}.approved_alias a
        LEFT JOIN {SCHEMA}.entity_match_term x ON x.approved_alias_id = a.approved_alias_id
        GROUP BY a.approved_alias_id HAVING count(x.entity_match_term_id) <> 1
        """
    )
    for identifier, count in cursor.fetchall():
        failures.append(
            f"Section 4.2 rule 2: approved_alias {identifier} has {count} match-term rows,"
            f" expected exactly one"
        )

    # Section 4.2 rule 1, against the loaded rows: the asserting snapshot is
    # the entity's own. The loader refuses this at load; this is the database
    # being asked the same question afterwards.
    cursor.execute(
        f"""
        SELECT a.approved_alias_id
        FROM {SCHEMA}.approved_alias a
        JOIN {SCHEMA}.approved_entity e ON e.approved_entity_id = a.approved_entity_id
        LEFT JOIN {SCHEMA}.message_occurrence m ON m.message_occurrence_id = e.message_occurrence_id
        LEFT JOIN {SCHEMA}.signal_occurrence g ON g.signal_occurrence_id = e.signal_occurrence_id
        LEFT JOIN {SCHEMA}.message_occurrence pm ON pm.message_occurrence_id = g.message_occurrence_id
        WHERE a.asserting_snapshot_id <> COALESCE(m.snapshot_id, pm.snapshot_id)
        """
    )
    for (identifier,) in cursor.fetchall():
        failures.append(
            f"Section 4.2 rule 1: approved_alias {identifier} is asserted by a snapshot"
            f" other than its entity's own"
        )


def _check_state_row_and_digest(cursor, failures) -> None:
    cursor.execute(f"SELECT registry_digest FROM {SCHEMA}.entity_registry_state")
    rows = cursor.fetchall()
    if len(rows) != 1:
        failures.append(
            f"Section 4.1: entity_registry_state has {len(rows)} rows, expected exactly one"
        )
        return
    stored = rows[0][0]
    recomputed = registry.compute_digest(cursor)
    if stored != recomputed:
        failures.append(
            f"Section 4.2: stored registry_digest {stored} differs from the recomputation"
            f" {recomputed} over the loaded rows"
        )


def _probe_enforcement(cursor, failures) -> None:
    """Insert what each constraint should refuse; require the refusal."""
    probes = (
        (
            "Section 4.1 an occurrence is approved once (message)",
            psycopg.errors.UniqueViolation,
            f"""INSERT INTO {SCHEMA}.approved_entity
                    (entity_kind, message_occurrence_id, signal_occurrence_id, approval_reference, approved_at)
                SELECT 'message', message_occurrence_id, NULL, 'SAMPLE_PROBE', now()
                FROM {SCHEMA}.approved_entity WHERE entity_kind = 'message' LIMIT 1""",
        ),
        (
            "Section 4.1 an occurrence is approved once (signal)",
            psycopg.errors.UniqueViolation,
            f"""INSERT INTO {SCHEMA}.approved_entity
                    (entity_kind, message_occurrence_id, signal_occurrence_id, approval_reference, approved_at)
                SELECT 'signal', NULL, signal_occurrence_id, 'SAMPLE_PROBE', now()
                FROM {SCHEMA}.approved_entity WHERE entity_kind = 'signal' LIMIT 1""",
        ),
        (
            "Section 4.1 exactly one occurrence reference, matching entity_kind",
            psycopg.errors.CheckViolation,
            f"""INSERT INTO {SCHEMA}.approved_entity
                    (entity_kind, message_occurrence_id, signal_occurrence_id, approval_reference, approved_at)
                SELECT 'message', NULL, signal_occurrence_id, 'SAMPLE_PROBE', now()
                FROM {SCHEMA}.approved_entity WHERE entity_kind = 'signal' LIMIT 1""",
        ),
        (
            "Section 4.2 rule 3 entity_kind",
            psycopg.errors.CheckViolation,
            f"""INSERT INTO {SCHEMA}.approved_entity
                    (entity_kind, message_occurrence_id, signal_occurrence_id, approval_reference, approved_at)
                VALUES ('SAMPLE_PROBE', NULL, NULL, 'SAMPLE_PROBE', now())""",
        ),
        (
            "Section 4.1 a registry row names a loaded occurrence",
            psycopg.errors.ForeignKeyViolation,
            f"""INSERT INTO {SCHEMA}.approved_entity
                    (entity_kind, message_occurrence_id, signal_occurrence_id, approval_reference, approved_at)
                VALUES ('message', -1, NULL, 'SAMPLE_PROBE', now())""",
        ),
        (
            "Section 4.1 (approved_entity_id, alias_text)",
            psycopg.errors.UniqueViolation,
            f"""INSERT INTO {SCHEMA}.approved_alias
                    (approved_entity_id, alias_text, alias_kind, asserting_snapshot_id, approval_reference, approved_at)
                SELECT approved_entity_id, alias_text, alias_kind, asserting_snapshot_id, 'SAMPLE_PROBE', now()
                FROM {SCHEMA}.approved_alias LIMIT 1""",
        ),
        (
            "Section 4.2 rule 3 alias_kind",
            psycopg.errors.CheckViolation,
            f"""INSERT INTO {SCHEMA}.approved_alias
                    (approved_entity_id, alias_text, alias_kind, asserting_snapshot_id, approval_reference, approved_at)
                SELECT approved_entity_id, 'SAMPLE_PROBE', 'SAMPLE_PROBE', asserting_snapshot_id, 'SAMPLE_PROBE', now()
                FROM {SCHEMA}.approved_alias LIMIT 1""",
        ),
        (
            "Section 4.1 (approved_entity_id, match_kind, match_text)",
            psycopg.errors.UniqueViolation,
            f"""INSERT INTO {SCHEMA}.entity_match_term
                    (approved_entity_id, match_kind, match_text, match_tokens, approved_alias_id)
                SELECT approved_entity_id, match_kind, match_text, match_tokens, approved_alias_id
                FROM {SCHEMA}.entity_match_term LIMIT 1""",
        ),
        (
            "Section 4.2 rule 5 match_tokens is never empty",
            psycopg.errors.CheckViolation,
            f"""INSERT INTO {SCHEMA}.entity_match_term
                    (approved_entity_id, match_kind, match_text, match_tokens, approved_alias_id)
                SELECT approved_entity_id, 'lookup_key', 'SAMPLE_PROBE', ARRAY[]::text[], NULL
                FROM {SCHEMA}.approved_entity LIMIT 1""",
        ),
        (
            "Section 4.1 approved_alias_id non-null exactly when not lookup_key",
            psycopg.errors.CheckViolation,
            f"""INSERT INTO {SCHEMA}.entity_match_term
                    (approved_entity_id, match_kind, match_text, match_tokens, approved_alias_id)
                SELECT approved_entity_id, 'approved_alias', 'SAMPLE_PROBE', ARRAY['sample','probe'], NULL
                FROM {SCHEMA}.approved_entity LIMIT 1""",
        ),
        (
            "Section 4.1 entity_registry_state at most one row",
            psycopg.errors.UniqueViolation,
            f"""INSERT INTO {SCHEMA}.entity_registry_state (registry_digest, built_at)
                VALUES ('SAMPLE_PROBE', now())""",
        ),
    )
    for what, refusal, statement in probes:
        cursor.execute("SAVEPOINT registry_probe")
        try:
            cursor.execute(statement)
        except refusal:
            pass
        except psycopg.Error as error:
            failures.append(
                f"{what}: refused for another reason ({type(error).__name__}); the"
                f" constraint the contract names is not the one that fired"
            )
        else:
            failures.append(f"{what}: the database accepted a row it should refuse")
        finally:
            cursor.execute("ROLLBACK TO SAVEPOINT registry_probe")
