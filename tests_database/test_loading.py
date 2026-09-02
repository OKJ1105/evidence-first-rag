"""Section 4.11 loading rules and the Section 6 repeatability assertion."""

import json
import pathlib
import shutil
import tempfile
import unittest

from evidence_first_rag.db import fixtures, loader

from . import support


class ProvisioningTwiceIsRepeatable(unittest.TestCase):
    """Section 6: "Repeatable provisioning from the same schema and fixtures
    produces the same logical rows, constraints, contract-visible values, and
    query ordering." Section 4.11 permits the surrogate keys to differ, so the
    comparison projects every one of them back to the natural key it stands
    for."""

    DATABASES = ("mvp_test_repeat_a", "mvp_test_repeat_b")

    @classmethod
    def setUpClass(cls):
        for database in cls.DATABASES:
            support.build(database)

    @classmethod
    def tearDownClass(cls):
        for database in cls.DATABASES:
            support.drop(database)

    def test_contract_visible_values_and_ordering_are_equal(self):
        first, second = (support.contract_visible(d) for d in self.DATABASES)
        self.assertEqual(set(first), set(second))
        for table in first:
            with self.subTest(table=table):
                # Compared as lists, not sets: Section 6 requires equal query
                # ordering, so two runs that returned the same rows in a
                # different order would not satisfy it.
                self.assertEqual(first[table], second[table])

    def test_every_table_was_actually_loaded(self):
        # A repeatability assertion over two empty databases would pass and
        # prove nothing.
        contents = support.contract_visible(self.DATABASES[0])
        for table, rows in contents.items():
            with self.subTest(table=table):
                self.assertGreater(len(rows), 0)


class ThereIsNoPartialLoad(unittest.TestCase):
    """Section 4.11: "A fixture file that fails to parse, or a reference that
    does not resolve, aborts provisioning. There is no partial load: the loader
    either loads every row of every file or leaves the database absent."
    """

    DATABASE = "mvp_test_partial"

    def setUp(self):
        self.directory = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.directory, ignore_errors=True)
        self.addCleanup(support.drop, self.DATABASE)
        self.fixtures = self.directory / "fixtures"
        shutil.copytree(support.FIXTURES, self.fixtures)

    def rows(self, table):
        path = self.fixtures / f"{table}.jsonl"
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

    def write(self, table, rows):
        path = self.fixtures / f"{table}.jsonl"
        path.write_text(
            "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
        )

    def assert_database_is_empty(self):
        """Every table present and empty. The transaction rolled back, so the
        schema the SQL scripts built is still there and carries no rows."""
        with support.connect(self.DATABASE) as connection, connection.cursor() as cursor:
            for table in fixtures.TABLES:
                cursor.execute(f"SELECT count(*) FROM mvp.{table}")
                self.assertEqual(cursor.fetchone()[0], 0, f"{table} is not empty")

    def test_an_unresolvable_message_reference_leaves_nothing_loaded(self):
        rows = self.rows("message_occurrence")
        rows[0]["snapshot"]["snapshot_label"] = "SAMPLE_SNAP_NOT_CREATED"
        self.write("message_occurrence", rows)

        with self.assertRaises(loader.UnresolvedReference):
            support.build(self.DATABASE, self.fixtures)
        self.assert_database_is_empty()

    def test_an_unresolvable_superseded_by_leaves_nothing_loaded(self):
        rows = self.rows("source_snapshot")
        rows[0]["superseded_by"] = {
            "project_code": "SAMPLE_PROJECT_ALPHA",
            "revision_label": "SAMPLE_REV_NOT_CREATED",
            "network_name": "SAMPLE_NET_POWERTRAIN",
            "snapshot_label": "SAMPLE_SNAP_BASE",
        }
        self.write("source_snapshot", rows)

        with self.assertRaises(loader.UnresolvedReference):
            support.build(self.DATABASE, self.fixtures)
        self.assert_database_is_empty()

    def test_an_unresolvable_mapping_endpoint_leaves_nothing_loaded(self):
        rows = self.rows("signal_mapping")
        rows[0]["target_signal"]["signal_key"] = "SAMPLE_SIG_NOT_CREATED"
        self.write("signal_mapping", rows)

        with self.assertRaises(loader.UnresolvedReference):
            support.build(self.DATABASE, self.fixtures)
        self.assert_database_is_empty()

    def test_a_file_that_fails_to_parse_never_reaches_the_database(self):
        # Parsing happens before any SQL runs, so this case does not even get
        # as far as creating the database. Section 4.11's "leaves the database
        # absent" is literal here.
        (self.fixtures / "signal_occurrence.jsonl").write_text(
            '{"not closed"\n', encoding="utf-8"
        )
        with self.assertRaises(fixtures.FixtureError):
            support.build(self.DATABASE, self.fixtures)

        with support.connect("postgres") as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT count(*) FROM pg_database WHERE datname = %s", (self.DATABASE,)
            )
            self.assertEqual(cursor.fetchone()[0], 0)


class TheLoaderPreservesNumericPrecision(unittest.TestCase):
    """Section 6: "Numeric values are returned with the precision stored in
    the schema; no rounding occurs in the runtime or the renderer." A loader
    that routed 0.1 through a binary float would store the nearest double, and
    the value would differ from the one the fixture wrote."""

    DATABASE = "mvp_test_numeric"

    @classmethod
    def setUpClass(cls):
        support.build(cls.DATABASE)

    @classmethod
    def tearDownClass(cls):
        support.drop(cls.DATABASE)

    def test_a_scale_factor_round_trips_exactly(self):
        parsed = fixtures.read(support.FIXTURES)
        expected = {
            (row.reference.signal_key, row.scale_factor)
            for row in parsed.signals
            if row.scale_factor is not None
        }
        with support.connect(self.DATABASE) as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT signal_key, scale_factor FROM mvp.signal_occurrence"
                " WHERE scale_factor IS NOT NULL"
            )
            stored = set(cursor.fetchall())
        self.assertEqual(stored, expected)


if __name__ == "__main__":
    unittest.main(verbosity=2)
