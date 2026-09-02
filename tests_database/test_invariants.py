"""The data-level invariant check: Section 8's acceptance evidence for
Sections 4.1 and 4.2, and Section 4.9's check `C1`.

Issue #12 requires this check to pass on the loaded fixtures **and to fail
when given a schema missing any one constraint**. A check nobody has seen fail
is a check nobody knows works, so each test below removes exactly one thing
the contract requires and asserts the check notices — then puts it back.

Every mutation runs inside a savepoint on one connection and is rolled back,
so no test leaves the database different from how it found it.
"""

import unittest

from evidence_first_rag.db import invariants

from . import support

DATABASE = "mvp_test_invariants"

# Section 4.1. Each entry is the DDL that removes one required constraint and
# the DDL that restores it, plus the text the failure must name.
DROPPABLE = {
    "source_snapshot scope": (
        "ALTER TABLE mvp.source_snapshot DROP CONSTRAINT source_snapshot_scope_key",
        "ALTER TABLE mvp.source_snapshot ADD CONSTRAINT source_snapshot_scope_key"
        " UNIQUE (project_code, revision_label, network_name, snapshot_label)",
        "source_snapshot has no unique constraint",
    ),
    "message_occurrence key": (
        "ALTER TABLE mvp.message_occurrence DROP CONSTRAINT message_occurrence_key",
        "ALTER TABLE mvp.message_occurrence ADD CONSTRAINT message_occurrence_key"
        " UNIQUE (snapshot_id, message_key)",
        "message_occurrence has no unique constraint",
    ),
    "signal_occurrence key": (
        "ALTER TABLE mvp.signal_occurrence DROP CONSTRAINT signal_occurrence_key",
        "ALTER TABLE mvp.signal_occurrence ADD CONSTRAINT signal_occurrence_key"
        " UNIQUE (message_occurrence_id, signal_key)",
        "signal_occurrence has no unique constraint",
    ),
    "signal_mapping relation": (
        "ALTER TABLE mvp.signal_mapping DROP CONSTRAINT signal_mapping_relation_key",
        "ALTER TABLE mvp.signal_mapping ADD CONSTRAINT signal_mapping_relation_key"
        " UNIQUE (asserting_snapshot_id, source_signal_occurrence_id,"
        " target_signal_occurrence_id)",
        "signal_mapping has no unique constraint",
    ),
}


class TheCheckPassesOnTheRegisteredFixtures(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        support.build(DATABASE)

    @classmethod
    def tearDownClass(cls):
        support.drop(DATABASE)

    def test_it_reports_no_failures(self):
        with support.connect(DATABASE) as connection:
            self.assertEqual(invariants.check(connection), [])
            connection.rollback()


class TheCheckFailsOnAMissingConstraint(unittest.TestCase):
    """The half that matters. `validate_fixtures.py` already proves the files
    satisfy the contract; this check exists to catch a schema that fails to
    enforce what those files happen to satisfy, and that claim is only worth
    anything if removing a constraint makes it fail."""

    @classmethod
    def setUpClass(cls):
        support.build(DATABASE)

    @classmethod
    def tearDownClass(cls):
        support.drop(DATABASE)

    def setUp(self):
        self.connection = support.connect(DATABASE)
        self.addCleanup(self.connection.close)
        self.addCleanup(self.connection.rollback)
        self.cursor = self.connection.cursor()
        self.addCleanup(self.cursor.close)

    def mutate(self, statement):
        self.cursor.execute("SAVEPOINT mutation")
        self.cursor.execute(statement)

    def restore(self):
        self.cursor.execute("ROLLBACK TO SAVEPOINT mutation")

    def failures(self):
        return invariants.check(self.connection)

    def test_dropping_any_required_unique_constraint_fails_the_check(self):
        for name, (drop, _restore_ddl, expected) in DROPPABLE.items():
            with self.subTest(constraint=name):
                self.mutate(drop)
                try:
                    reported = self.failures()
                    self.assertTrue(
                        any(expected in failure for failure in reported),
                        f"expected a failure naming {expected!r}, got {reported}",
                    )
                finally:
                    self.restore()

    def test_a_dropped_constraint_also_fails_the_enforcement_probe(self):
        # Introspection and probing are different claims. Dropping the
        # constraint must fail both: the catalog no longer declares it, and
        # the database now accepts the duplicate row the probe inserts.
        self.mutate(DROPPABLE["message_occurrence key"][0])
        try:
            reported = self.failures()
            self.assertTrue(
                any("declared but not enforced" in failure for failure in reported),
                f"the probe did not notice the missing constraint: {reported}",
            )
        finally:
            self.restore()

    def test_the_registered_fixtures_make_the_prohibited_constraint_uncreatable(self):
        # Section 4.1 prohibits a snapshot-level unique constraint on
        # `signal_key`, and FX-102 is the fixture that gives the prohibition
        # teeth: two signals share a key under different parent messages, so
        # the constraint cannot even be created against the loaded data.
        import psycopg

        self.mutate("SELECT 1")
        try:
            with self.assertRaises(psycopg.errors.UniqueViolation):
                self.cursor.execute(
                    "CREATE UNIQUE INDEX signal_key_globally_unique"
                    " ON mvp.signal_occurrence (signal_key)"
                )
        finally:
            self.restore()

    def test_the_check_reports_the_prohibited_constraint_where_data_permits_it(self):
        # The fixtures block the constraint today, but a fixture set without
        # the FX-102 case would not, and the schema would acquire a
        # prohibition nobody noticed. Removing the duplicate first is what
        # lets this test reach the check rather than the database.
        self.mutate("DELETE FROM mvp.signal_mapping")
        try:
            self.cursor.execute(
                "DELETE FROM mvp.signal_occurrence a USING mvp.signal_occurrence b"
                " WHERE a.signal_key = b.signal_key"
                "   AND a.signal_occurrence_id > b.signal_occurrence_id"
            )
            self.cursor.execute(
                "CREATE UNIQUE INDEX signal_key_globally_unique"
                " ON mvp.signal_occurrence (signal_key)"
            )
            reported = self.failures()
            self.assertTrue(
                any("prohibited unique constraint" in failure for failure in reported),
                f"expected the prohibition to be reported, got {reported}",
            )
        finally:
            self.restore()

    def test_dropping_a_foreign_key_fails_the_check(self):
        self.cursor.execute(
            """
            SELECT c.conname FROM pg_constraint c
            JOIN pg_class t ON t.oid = c.conrelid
            JOIN pg_namespace n ON n.oid = t.relnamespace
            WHERE c.contype = 'f' AND n.nspname = 'mvp'
              AND t.relname = 'message_occurrence'
            """
        )
        (name,) = self.cursor.fetchone()
        self.mutate(f"ALTER TABLE mvp.message_occurrence DROP CONSTRAINT {name}")
        try:
            reported = self.failures()
            self.assertTrue(
                any("no foreign key message_occurrence.snapshot_id" in f for f in reported),
                f"expected the missing foreign key to be reported, got {reported}",
            )
        finally:
            self.restore()

    def test_dropping_a_not_null_fails_the_check(self):
        self.mutate("ALTER TABLE mvp.message_occurrence ALTER COLUMN message_key DROP NOT NULL")
        try:
            reported = self.failures()
            self.assertTrue(
                any("message_occurrence.message_key is nullable" in f for f in reported),
                f"expected the nullable column to be reported, got {reported}",
            )
        finally:
            self.restore()

    def test_a_relaxed_identity_column_fails_the_check(self):
        # Section 4.11 keeps surrogate keys out of fixture files. GENERATED
        # BY DEFAULT would let a loader supply one, which is the rule this
        # column is here to make unrepresentable.
        self.mutate(
            "ALTER TABLE mvp.source_snapshot ALTER COLUMN snapshot_id"
            " SET GENERATED BY DEFAULT"
        )
        try:
            reported = self.failures()
            self.assertTrue(
                any("not a GENERATED ALWAYS identity" in f for f in reported),
                f"expected the relaxed identity column to be reported, got {reported}",
            )
        finally:
            self.restore()

    def test_a_self_superseding_snapshot_fails_the_check(self):
        # The schema already refuses this through a CHECK constraint, which is
        # where it should be refused. Dropping that constraint first is what
        # makes the data-level assertion reachable at all -- and shows it is a
        # real second line rather than dead code behind a constraint that can
        # never fail.
        self.mutate(
            "ALTER TABLE mvp.source_snapshot"
            " DROP CONSTRAINT source_snapshot_not_self_superseding"
        )
        try:
            self.cursor.execute(
                "UPDATE mvp.source_snapshot SET superseded_by = snapshot_id"
                " WHERE snapshot_id = (SELECT min(snapshot_id) FROM mvp.source_snapshot)"
            )
            reported = self.failures()
            self.assertTrue(
                any("supersede themselves" in f for f in reported),
                f"expected the self-reference to be reported, got {reported}",
            )
        finally:
            self.restore()

    def test_the_provisioning_identity_cannot_alter_either_role(self):
        # Not a mutation test: the attempt to write one found this. Section
        # 4.3 gives the provisioning identity CREATE and INSERT on the
        # application schema and nothing else, so it cannot relax the runtime
        # identity's own settings. The role configuration the check reads is
        # therefore outside what a compromised provisioning step could change,
        # and the positive assertions live in test_roles.py.
        import psycopg

        self.mutate("SELECT 1")
        try:
            with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                self.cursor.execute("ALTER ROLE mvp_runtime RESET statement_timeout")
        finally:
            self.restore()


if __name__ == "__main__":
    unittest.main(verbosity=2)
