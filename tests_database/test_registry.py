"""entity-discovery-v0.1 Sections 4.1 and 4.2, and Section 3.3 extension 2,
against a real PostgreSQL database.

Section 8's rows for the registry schema, its integrity rules, and its
refresh-and-digest obligation; and #17 rule 9 for every one of them: a check
nobody has seen fail is a check nobody knows works, so each test that says
"the invariant check passes" has a sibling that removes one thing and asserts
the check names it.
"""

import datetime
import hashlib
import json
import pathlib
import shutil
import tempfile
import unittest

import psycopg

from evidence_first_rag.db import fixtures, invariants, loader, registry, registry_fixtures
from evidence_first_rag.discovery import normalize

from . import support

DATABASE = "mvp_test_registry"

REGISTRY_TABLES = ("approved_entity", "approved_alias", "entity_match_term", "entity_registry_state")


def setUpModule():
    support.build(DATABASE)


def tearDownModule():
    support.drop(DATABASE)


class TheRegistryIsLoaded(unittest.TestCase):
    def test_every_registered_row_is_loaded_and_the_surface_is_derived(self):
        parsed = registry_fixtures.read(support.FIXTURES)
        with support.connect(DATABASE) as connection, connection.cursor() as cursor:
            counts = {}
            for table in REGISTRY_TABLES:
                cursor.execute(f"SELECT count(*) FROM mvp.{table}")
                counts[table] = cursor.fetchone()[0]
        self.assertEqual(counts["approved_entity"], len(parsed.entities))
        self.assertEqual(counts["approved_alias"], len(parsed.aliases))
        # Section 4.2 rule 2: one lookup_key row per entity plus one per alias.
        self.assertEqual(counts["entity_match_term"], len(parsed.entities) + len(parsed.aliases))
        self.assertEqual(counts["entity_registry_state"], 1)

    def test_the_invariant_check_passes(self):
        with support.connect(DATABASE) as connection:
            self.assertEqual(invariants.check(connection), [])
            connection.rollback()


# --- Section 4.1: the constraints, seen to fail -----------------------------

# Each entry removes one thing Section 4.1 requires and names the text the
# invariant check must produce. The restore DDL puts it back so the module's
# one database is unchanged for the next test.
DROPPABLE = {
    "approved once (message)": (
        "DROP INDEX mvp.approved_entity_message_once",
        "CREATE UNIQUE INDEX approved_entity_message_once ON mvp.approved_entity (message_occurrence_id)"
        " WHERE message_occurrence_id IS NOT NULL",
        "no partial unique index on message_occurrence_id",
    ),
    "approved once (signal)": (
        "DROP INDEX mvp.approved_entity_signal_once",
        "CREATE UNIQUE INDEX approved_entity_signal_once ON mvp.approved_entity (signal_occurrence_id)"
        " WHERE signal_occurrence_id IS NOT NULL",
        "no partial unique index on signal_occurrence_id",
    ),
    "one occurrence reference": (
        "ALTER TABLE mvp.approved_entity DROP CONSTRAINT approved_entity_one_occurrence",
        "ALTER TABLE mvp.approved_entity ADD CONSTRAINT approved_entity_one_occurrence CHECK ("
        "(entity_kind = 'message' AND message_occurrence_id IS NOT NULL AND signal_occurrence_id IS NULL)"
        " OR (entity_kind = 'signal' AND signal_occurrence_id IS NOT NULL AND message_occurrence_id IS NULL))",
        "approved_entity_one_occurrence",
    ),
    "entity_kind enumerated": (
        "ALTER TABLE mvp.approved_entity DROP CONSTRAINT approved_entity_kind_enumerated",
        "ALTER TABLE mvp.approved_entity ADD CONSTRAINT approved_entity_kind_enumerated"
        " CHECK (entity_kind IN ('message', 'signal'))",
        "approved_entity_kind_enumerated",
    ),
    "(approved_entity_id, alias_text)": (
        "ALTER TABLE mvp.approved_alias DROP CONSTRAINT approved_alias_text_per_entity",
        "ALTER TABLE mvp.approved_alias ADD CONSTRAINT approved_alias_text_per_entity"
        " UNIQUE (approved_entity_id, alias_text)",
        "approved_alias has no unique constraint",
    ),
    "(approved_entity_id, match_kind, match_text)": (
        "ALTER TABLE mvp.entity_match_term DROP CONSTRAINT entity_match_term_per_entity",
        "ALTER TABLE mvp.entity_match_term ADD CONSTRAINT entity_match_term_per_entity"
        " UNIQUE (approved_entity_id, match_kind, match_text)",
        "entity_match_term has no unique constraint",
    ),
    "match_tokens never empty": (
        "ALTER TABLE mvp.entity_match_term DROP CONSTRAINT entity_match_term_has_a_token",
        "ALTER TABLE mvp.entity_match_term ADD CONSTRAINT entity_match_term_has_a_token"
        " CHECK (cardinality(match_tokens) > 0)",
        "entity_match_term_has_a_token",
    ),
    "state at most one row": (
        "ALTER TABLE mvp.entity_registry_state DROP CONSTRAINT entity_registry_state_at_most_one_row",
        "ALTER TABLE mvp.entity_registry_state ADD CONSTRAINT entity_registry_state_at_most_one_row"
        " UNIQUE (only_row)",
        "at most one row",
    ),
    "foreign key into message_occurrence": (
        "ALTER TABLE mvp.approved_entity DROP CONSTRAINT approved_entity_message_occurrence_id_fkey",
        "ALTER TABLE mvp.approved_entity ADD CONSTRAINT approved_entity_message_occurrence_id_fkey"
        " FOREIGN KEY (message_occurrence_id) REFERENCES mvp.message_occurrence (message_occurrence_id)",
        "no foreign key approved_entity.message_occurrence_id",
    ),
}


class TheCheckFailsOnAMissingConstraint(unittest.TestCase):
    def test_each_removed_constraint_is_named(self):
        with support.connect(DATABASE) as connection, connection.cursor() as cursor:
            for name, (drop, restore, expected) in DROPPABLE.items():
                with self.subTest(constraint=name):
                    cursor.execute(drop)
                    try:
                        failures = invariants.check(connection)
                    finally:
                        cursor.execute(restore)
                    self.assertTrue(
                        any(expected in failure for failure in failures),
                        f"{name}: expected a failure naming {expected!r}, got {failures}",
                    )
            connection.rollback()

    def test_a_unique_constraint_on_alias_text_alone_is_reported_as_prohibited(self):
        # Section 4.1: deliberately absent, so its presence is the defect.
        # The registered rows carry two aliases with the same text? No --
        # DX-004's collision is between an alias and a lookup key, so the
        # constraint can be added; the check must still refuse it.
        with support.connect(DATABASE) as connection, connection.cursor() as cursor:
            cursor.execute("ALTER TABLE mvp.approved_alias ADD CONSTRAINT probe_alias_text UNIQUE (alias_text)")
            try:
                failures = invariants.check(connection)
            finally:
                cursor.execute("ALTER TABLE mvp.approved_alias DROP CONSTRAINT probe_alias_text")
            self.assertTrue(any("prohibited unique constraint" in f for f in failures), failures)
            connection.rollback()


# --- Section 4.2: the integrity rules, seen to fail -------------------------

class TheCheckFailsWhenTheDerivedSurfaceIsWrong(unittest.TestCase):
    """Rule 2 says entity_match_term is derived, not authored. Each test
    below authors it -- by a direct UPDATE as the provisioning identity, the
    one thing the loader would never do -- and asserts the check notices.
    Each runs inside a transaction that is rolled back."""

    def mutated(self, statement, expected):
        with support.connect(DATABASE) as connection, connection.cursor() as cursor:
            cursor.execute(statement)
            failures = invariants.check(connection)
            connection.rollback()
        self.assertTrue(any(expected in f for f in failures), f"expected {expected!r} in {failures}")

    def test_tokens_that_are_not_the_normalization_of_the_text(self):
        self.mutated(
            "UPDATE mvp.entity_match_term SET match_tokens = ARRAY['wrong'] WHERE match_kind = 'lookup_key'",
            "Section 4.2 rule 2",
        )

    def test_a_lookup_key_row_carrying_the_wrong_key(self):
        self.mutated(
            "UPDATE mvp.entity_match_term SET match_text = 'SAMPLE_OTHER', match_tokens = ARRAY['sample','other']"
            " WHERE entity_match_term_id = (SELECT min(entity_match_term_id) FROM mvp.entity_match_term"
            " WHERE match_kind = 'lookup_key')",
            "expected exactly one carrying",
        )

    def test_an_entity_with_no_lookup_key_row(self):
        self.mutated(
            "DELETE FROM mvp.entity_match_term WHERE entity_match_term_id = (SELECT min(entity_match_term_id)"
            " FROM mvp.entity_match_term WHERE match_kind = 'lookup_key')",
            "expected exactly one carrying",
        )

    def test_an_alias_row_whose_text_differs_from_its_alias(self):
        self.mutated(
            "UPDATE mvp.entity_match_term SET match_text = 'SAMPLE_DRIFTED', match_tokens = ARRAY['sample','drifted']"
            " WHERE match_kind <> 'lookup_key'",
            "does not correspond to the alias row",
        )

    def test_an_alias_with_no_match_term_row(self):
        self.mutated(
            "DELETE FROM mvp.entity_match_term WHERE approved_alias_id = (SELECT min(approved_alias_id) FROM mvp.approved_alias)",
            "expected exactly one",
        )

    def test_an_alias_asserted_by_another_snapshot(self):
        # Rule 1, against loaded rows: move one alias's asserting snapshot to
        # a snapshot that is not its entity's.
        self.mutated(
            "UPDATE mvp.approved_alias SET asserting_snapshot_id = (SELECT snapshot_id FROM mvp.source_snapshot s"
            " WHERE s.snapshot_id <> approved_alias.asserting_snapshot_id LIMIT 1)"
            " WHERE approved_alias_id = (SELECT min(approved_alias_id) FROM mvp.approved_alias)",
            "Section 4.2 rule 1",
        )

    def test_a_stored_digest_that_does_not_match_the_rows(self):
        self.mutated(
            "UPDATE mvp.entity_registry_state SET registry_digest = repeat('0', 64)",
            "differs from the recomputation",
        )

    def test_a_registry_change_after_the_digest_was_written(self):
        # The digest's purpose: a changed registry changes it. Here the rows
        # change and the stored digest does not, which is the same mismatch
        # seen from the other side.
        self.mutated(
            "UPDATE mvp.approved_entity SET approval_reference = 'SAMPLE_APPROVAL_CHANGED'"
            " WHERE approved_entity_id = (SELECT min(approved_entity_id) FROM mvp.approved_entity)",
            "differs from the recomputation",
        )

    def test_a_runtime_write_grant_is_reported(self):
        self.mutated(
            "GRANT INSERT ON mvp.approved_alias TO mvp_runtime",
            "mvp_runtime holds INSERT on approved_alias",
        )


# --- Section 4.2: refresh, no partial load ----------------------------------

class ARegistryThatCannotLoadLeavesNothingLoaded(unittest.TestCase):
    """Section 4.2: "A refresh is a re-provision. A partial load aborts."
    And because the registry loads in the same transaction as the mvp-v0.1
    tables, a failure in it leaves those empty too: there is no state in
    which the occurrences are loaded and the registry that names them is
    not."""

    DATABASE = "mvp_test_registry_partial"

    def setUp(self):
        self.directory = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.directory, ignore_errors=True)
        self.addCleanup(support.drop, self.DATABASE)
        self.fixtures = self.directory / "fixtures"
        shutil.copytree(support.FIXTURES, self.fixtures)

    def rows(self, table):
        path = self.fixtures / "registry" / f"{table}.jsonl"
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

    def write(self, table, rows):
        (self.fixtures / "registry" / f"{table}.jsonl").write_text(
            "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
        )

    def assert_every_table_is_empty(self):
        with support.connect(self.DATABASE) as connection, connection.cursor() as cursor:
            for table in fixtures.TABLES + REGISTRY_TABLES:
                cursor.execute(f"SELECT count(*) FROM mvp.{table}")
                self.assertEqual(cursor.fetchone()[0], 0, f"{table} is not empty")

    def test_an_entity_naming_an_unloaded_occurrence(self):
        rows = self.rows("approved_entity")
        rows[0]["reference"]["message_key"] = "SAMPLE_MSG_NOT_LOADED"
        self.write("approved_entity", rows)
        with self.assertRaises(loader.UnresolvedReference):
            support.build(self.DATABASE, self.fixtures)
        self.assert_every_table_is_empty()

    def test_an_alias_naming_an_entity_the_registry_does_not_approve(self):
        rows = self.rows("approved_alias")
        rows[0]["reference"]["message_key"] = "SAMPLE_MSG_DIAGNOSTIC_EVENT"  # loaded, not approved
        self.write("approved_alias", rows)
        with self.assertRaises(loader.UnresolvedReference):
            support.build(self.DATABASE, self.fixtures)
        self.assert_every_table_is_empty()

    def test_an_alias_asserted_by_another_snapshot_is_refused(self):
        # Section 4.2 rule 1.
        rows = self.rows("approved_alias")
        rows[0]["asserting_snapshot"]["snapshot_label"] = "SAMPLE_SNAP_REVISED"
        self.write("approved_alias", rows)
        with self.assertRaises(registry.IntegrityError) as caught:
            support.build(self.DATABASE, self.fixtures)
        self.assertIn("rule 1", str(caught.exception))
        self.assert_every_table_is_empty()

    def test_an_alias_that_normalizes_to_no_token_is_refused(self):
        # Section 4.2 rule 5. The text passes the parser (non-empty) and
        # every column check; only the derived surface can see it is empty.
        rows = self.rows("approved_alias")
        rows[0]["alias_text"] = "___"
        self.write("approved_alias", rows)
        with self.assertRaises(registry.IntegrityError) as caught:
            support.build(self.DATABASE, self.fixtures)
        self.assertIn("rule 5", str(caught.exception))
        self.assert_every_table_is_empty()

    def test_a_registry_file_that_fails_to_parse_never_reaches_the_database(self):
        (self.fixtures / "registry" / "approved_entity.jsonl").write_text('{"open\n', encoding="utf-8")
        with self.assertRaises(fixtures.FixtureError):
            support.build(self.DATABASE, self.fixtures)
        with support.connect("postgres") as connection, connection.cursor() as cursor:
            cursor.execute("SELECT count(*) FROM pg_database WHERE datname = %s", (self.DATABASE,))
            self.assertEqual(cursor.fetchone()[0], 0)


# --- Section 4.2: the digest ------------------------------------------------

def independent_digest(database: str) -> str:
    """The Section 4.2 digest computed from the contract's key table, not
    from `registry.py`.

    Deliberately its own code: a second serializer written from the text.
    It reads the natural keys with its own queries, builds each line with its
    own dict, serializes with `json.dumps` under settings that happen to
    match the canonical rules for these inputs (ASCII-only identifiers, no
    control characters, no floats), sorts and hashes. If `registry.py` and
    this disagree, one of them has misread Section 4.2, and that is the
    disagreement the Section 8 row exists to surface.
    """
    def line(obj):
        return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8") + b"\n"

    def stamp(value: datetime.datetime) -> str:
        return value.strftime("%Y-%m-%dT%H:%M:%SZ")

    with support.connect(database, "runtime") as connection, connection.cursor() as cursor:
        cursor.execute("""
            SELECT e.approved_entity_id, e.entity_kind, e.approval_reference, e.approved_at,
                   e.message_occurrence_id, e.signal_occurrence_id
            FROM mvp.approved_entity e
        """)
        entities = {}
        for entity_id, kind, approval, approved_at, message_id, signal_id in cursor.fetchall():
            if kind == "message":
                cursor.execute("""
                    SELECT s.project_code, s.revision_label, s.network_name, s.snapshot_label, m.message_key
                    FROM mvp.message_occurrence m JOIN mvp.source_snapshot s ON s.snapshot_id = m.snapshot_id
                    WHERE m.message_occurrence_id = %s
                """, (message_id,))
                project, revision, network, snapshot, message_key = cursor.fetchone()
                signal_key = None
            else:
                cursor.execute("""
                    SELECT s.project_code, s.revision_label, s.network_name, s.snapshot_label,
                           m.message_key, g.signal_key
                    FROM mvp.signal_occurrence g
                    JOIN mvp.message_occurrence m ON m.message_occurrence_id = g.message_occurrence_id
                    JOIN mvp.source_snapshot s ON s.snapshot_id = m.snapshot_id
                    WHERE g.signal_occurrence_id = %s
                """, (signal_id,))
                project, revision, network, snapshot, message_key, signal_key = cursor.fetchone()
            keys = {
                "project_code": project, "revision_label": revision, "network_name": network,
                "snapshot_label": snapshot, "message_key": message_key, "signal_key": signal_key,
            }
            entities[entity_id] = (kind, keys, approval, approved_at)

        entity_lines = sorted(
            line({"entity_kind": kind, **keys, "approval_reference": approval, "approved_at": stamp(at)})
            for kind, keys, approval, at in entities.values()
        )

        cursor.execute("""
            SELECT a.approved_alias_id, a.approved_entity_id, a.alias_text, a.alias_kind,
                   t.project_code, t.revision_label, t.network_name, t.snapshot_label,
                   a.approval_reference, a.approved_at
            FROM mvp.approved_alias a JOIN mvp.source_snapshot t ON t.snapshot_id = a.asserting_snapshot_id
        """)
        aliases = {}
        alias_lines = []
        for alias_id, entity_id, text, kind, ap, ar, an, asn, approval, approved_at in cursor.fetchall():
            aliases[alias_id] = text
            _, keys, _, _ = entities[entity_id]
            alias_lines.append(line({
                **keys, "alias_text": text, "alias_kind": kind,
                "asserting_project_code": ap, "asserting_revision_label": ar,
                "asserting_network_name": an, "asserting_snapshot_label": asn,
                "approval_reference": approval, "approved_at": stamp(approved_at),
            }))
        alias_lines.sort()

        cursor.execute("""
            SELECT approved_entity_id, match_kind, match_text, match_tokens, approved_alias_id
            FROM mvp.entity_match_term
        """)
        term_lines = sorted(
            line({
                **entities[entity_id][1], "match_kind": kind, "match_text": text,
                "match_tokens": list(tokens), "alias_text": aliases.get(alias_id),
            })
            for entity_id, kind, text, tokens, alias_id in cursor.fetchall()
        )

    return hashlib.sha256(b"".join(entity_lines + alias_lines + term_lines)).hexdigest()


class TheDigest(unittest.TestCase):
    def stored(self, database=DATABASE):
        with support.connect(database, "runtime") as connection, connection.cursor() as cursor:
            cursor.execute("SELECT registry_digest FROM mvp.entity_registry_state")
            return cursor.fetchone()[0]

    def test_it_is_lower_case_hex_sha256(self):
        digest = self.stored()
        self.assertEqual(len(digest), 64)
        self.assertEqual(digest, digest.lower())
        int(digest, 16)

    def test_the_stored_digest_equals_an_independent_computation_from_the_contracts_key_table(self):
        # The Section 8 row: "one computing the digest from the Section 4.2
        # key list independently of the runtime and matching it."
        self.assertEqual(self.stored(), independent_digest(DATABASE))

    def test_the_stored_digest_equals_the_loaders_own_recomputation(self):
        with support.connect(DATABASE, "runtime") as connection, connection.cursor() as cursor:
            self.assertEqual(self.stored(), registry.compute_digest(cursor))

    def test_the_lines_use_natural_keys_only(self):
        # Section 4.2: "never by a surrogate value". No line may carry a key
        # that names one.
        with support.connect(DATABASE, "runtime") as connection, connection.cursor() as cursor:
            lines = registry.digest_lines(cursor)
        self.assertEqual(len(lines), 12 + 5 + 17)
        for raw in lines:
            obj = json.loads(raw)
            for key in obj:
                self.assertFalse(key.endswith("_id"), key)

    def test_a_changed_registry_changes_the_digest(self):
        # The intended signal: a candidate set computed against one registry
        # state cannot be selected from against another.
        with support.connect(DATABASE) as connection, connection.cursor() as cursor:
            before = registry.compute_digest(cursor)
            cursor.execute(
                "UPDATE mvp.approved_alias SET approval_reference = 'SAMPLE_APPROVAL_OTHER'"
                " WHERE approved_alias_id = (SELECT min(approved_alias_id) FROM mvp.approved_alias)"
            )
            after = registry.compute_digest(cursor)
            connection.rollback()
        self.assertNotEqual(before, after)

    def test_a_timestamp_is_rfc_3339_utc_second_precision(self):
        self.assertEqual(registry.timestamp(datetime.datetime(2026, 3, 5, 1, 2, 3, 999999)), "2026-03-05T01:02:03Z")
        aware = datetime.datetime(2026, 3, 5, 10, 0, 0, tzinfo=datetime.timezone(datetime.timedelta(hours=9)))
        self.assertEqual(registry.timestamp(aware), "2026-03-05T01:00:00Z")


class ProvisioningTwiceIsRepeatable(unittest.TestCase):
    """Section 6 of entity-discovery-v0.1: "Repeatable provisioning from the
    same fixture files produces the same registry rows, the same
    entity_match_term derivation, and the same registry_digest." Surrogates
    may differ and are projected away; built_at differs and is not
    compared."""

    DATABASES = ("mvp_test_registry_repeat_a", "mvp_test_registry_repeat_b")

    @classmethod
    def setUpClass(cls):
        for database in cls.DATABASES:
            support.build(database)

    @classmethod
    def tearDownClass(cls):
        for database in cls.DATABASES:
            support.drop(database)

    def test_registry_rows_and_digest_are_equal(self):
        first, second = (support.contract_visible(d) for d in self.DATABASES)
        for table in REGISTRY_TABLES:
            with self.subTest(table=table):
                self.assertGreater(len(first[table]), 0)
                self.assertEqual(first[table], second[table])


# --- Section 3.3 extension 2, Section 4.12: the runtime reads and never writes

class TheRuntimeIdentityOnTheRegistry(unittest.TestCase):
    WRITES = {
        "INSERT": "INSERT INTO mvp.entity_registry_state (registry_digest, built_at) VALUES ('X', now())",
        "UPDATE": "UPDATE mvp.approved_entity SET approval_reference = 'X'",
        "DELETE": "DELETE FROM mvp.approved_alias",
        "CREATE TABLE": "CREATE TABLE mvp.registry_intruder (id integer)",
    }

    def test_it_can_read_all_four_tables(self):
        with support.connect(DATABASE, "runtime") as connection, connection.cursor() as cursor:
            for table in REGISTRY_TABLES:
                cursor.execute(f"SELECT count(*) FROM mvp.{table}")
                self.assertGreater(cursor.fetchone()[0], 0, table)

    def test_it_holds_select_and_nothing_else(self):
        with support.connect(DATABASE) as connection, connection.cursor() as cursor:
            for table in REGISTRY_TABLES:
                for privilege in ("INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER"):
                    with self.subTest(table=table, privilege=privilege):
                        cursor.execute("SELECT has_table_privilege('mvp_runtime', %s, %s)", (f"mvp.{table}", privilege))
                        self.assertFalse(cursor.fetchone()[0])
                cursor.execute("SELECT has_table_privilege('mvp_runtime', %s, 'SELECT')", (f"mvp.{table}",))
                self.assertTrue(cursor.fetchone()[0])

    def test_the_mvp_tables_are_unaffected(self):
        # Extension 2 adds a grant on the registry and changes nothing on
        # the four mvp-v0.1 tables.
        with support.connect(DATABASE) as connection, connection.cursor() as cursor:
            for table in fixtures.TABLES:
                for privilege in ("INSERT", "UPDATE", "DELETE", "TRUNCATE"):
                    cursor.execute("SELECT has_table_privilege('mvp_runtime', %s, %s)", (f"mvp.{table}", privilege))
                    self.assertFalse(cursor.fetchone()[0], (table, privilege))

    def test_each_write_is_refused_by_privilege_not_by_transaction_mode(self):
        # As tests_database/test_roles.py does for the mvp-v0.1 tables: turn
        # the read-only default off so the refusal can only be the grant's.
        for name, statement in self.WRITES.items():
            with self.subTest(statement=name):
                with support.connect(DATABASE, "runtime") as connection:
                    connection.autocommit = True
                    with connection.cursor() as cursor:
                        cursor.execute("SET default_transaction_read_only = off")
                        with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                            cursor.execute(statement)


class TheDerivedSurfaceMatchesTheDefinition(unittest.TestCase):
    """Section 4.2 rule 2 from the positive side, on the registered rows."""

    def test_every_row_carries_the_normalization_of_its_text(self):
        with support.connect(DATABASE, "runtime") as connection, connection.cursor() as cursor:
            cursor.execute("SELECT match_text, match_tokens FROM mvp.entity_match_term")
            rows = cursor.fetchall()
        self.assertTrue(rows)
        for text, tokens in rows:
            with self.subTest(text=text):
                self.assertEqual(list(tokens), normalize(text))

    def test_dx_004s_collision_is_loaded(self):
        # The row Section 4.1's missing constraint exists to allow: one
        # entity's lookup key is another's alias, same snapshot, same kind.
        with support.connect(DATABASE, "runtime") as connection, connection.cursor() as cursor:
            cursor.execute("""
                SELECT count(DISTINCT x.approved_entity_id)
                FROM mvp.entity_match_term x
                JOIN mvp.approved_entity e ON e.approved_entity_id = x.approved_entity_id
                WHERE x.match_text = 'SAMPLE_SIG_GEAR_POSITION' AND e.entity_kind = 'signal'
            """)
            self.assertEqual(cursor.fetchone()[0], 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
