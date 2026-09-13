"""Section 4.11 parsing, with no database.

`scripts/checks/validate_fixtures.py` already asserts the registered files are
well-formed. What these cover is the parser's own behaviour on files that are
not: Section 4.11 makes a parse failure fatal to provisioning, so the failure
has to happen here, before the loader opens a transaction, and it has to say
which line.
"""

import decimal
import json
import pathlib
import shutil
import tempfile
import unittest

from evidence_first_rag.db import fixtures

REPOSITORY = pathlib.Path(__file__).resolve().parent.parent
REGISTERED = REPOSITORY / "fixtures"


class TheRegisteredFixturesParse(unittest.TestCase):
    def test_every_table_has_rows(self):
        parsed = fixtures.read(REGISTERED)
        self.assertEqual(len(parsed.snapshots), 4)
        self.assertEqual(len(parsed.messages), 7)
        self.assertEqual(len(parsed.signals), 13)
        self.assertEqual(len(parsed.mappings), 3)

    def test_the_four_table_names_are_section_4_11s(self):
        self.assertEqual(
            fixtures.TABLES,
            (
                "source_snapshot",
                "message_occurrence",
                "signal_occurrence",
                "signal_mapping",
            ),
        )

    def test_a_numeric_column_keeps_the_precision_the_fixture_wrote(self):
        # Section 6: values are returned with the precision stored in the
        # schema. 0.1 has no exact binary float, so parsing through float
        # would store the nearest double instead of the number in the file.
        parsed = fixtures.read(REGISTERED)
        factors = [row.scale_factor for row in parsed.signals if row.scale_factor is not None]
        self.assertTrue(factors)
        for factor in factors:
            with self.subTest(factor=factor):
                self.assertIsInstance(factor, decimal.Decimal)
        self.assertIn(decimal.Decimal("0.1"), factors)

    def test_references_come_out_as_the_section_4_2_types(self):
        parsed = fixtures.read(REGISTERED)
        signal = parsed.signals[0]
        # A signal reference carries its parent message, which carries the
        # complete scope. Section 4.2 forbids a partial tuple, and these types
        # refuse to hold one.
        self.assertEqual(signal.reference.scope, signal.reference.message.scope)
        self.assertTrue(signal.reference.message_key)


class AMalformedFixtureIsAParseFailure(unittest.TestCase):
    def setUp(self):
        self.directory = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.directory, ignore_errors=True)
        self.fixtures = self.directory / "fixtures"
        shutil.copytree(REGISTERED, self.fixtures)

    def rows(self, table):
        path = self.fixtures / f"{table}.jsonl"
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

    def write(self, table, rows):
        (self.fixtures / f"{table}.jsonl").write_text(
            "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
        )

    def assert_fails(self, fragment):
        with self.assertRaises(fixtures.FixtureError) as raised:
            fixtures.read(self.fixtures)
        self.assertIn(fragment, str(raised.exception))

    def test_a_missing_file_fails(self):
        (self.fixtures / "signal_mapping.jsonl").unlink()
        self.assert_fails("missing")

    def test_invalid_json_names_the_line(self):
        # A real first row, so the failure reported is the invalid JSON on
        # line 2 and not a column complaint about a placeholder on line 1.
        path = self.fixtures / "source_snapshot.jsonl"
        first = path.read_text(encoding="utf-8").splitlines()[0]
        path.write_text(f"{first}\n{{not json\n", encoding="utf-8")
        self.assert_fails("source_snapshot.jsonl:2")

    def test_a_blank_line_fails(self):
        path = self.fixtures / "message_occurrence.jsonl"
        path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        self.assert_fails("blank line")

    def test_a_missing_column_fails(self):
        rows = self.rows("message_occurrence")
        del rows[0]["frame_identifier"]
        self.write("message_occurrence", rows)
        self.assert_fails("missing columns")

    def test_an_unexpected_column_fails(self):
        rows = self.rows("message_occurrence")
        rows[0]["invented_column"] = 1
        self.write("message_occurrence", rows)
        self.assert_fails("unexpected columns")

    def test_a_scope_hole_fails_at_the_reference_type(self):
        # Section 4.2: the runtime never supplies a missing scope dimension,
        # and the reference type refuses to be built with one. A fixture with
        # a hole is therefore a parse failure, not a row to check later.
        rows = self.rows("message_occurrence")
        rows[0]["snapshot"]["network_name"] = ""
        self.write("message_occurrence", rows)
        self.assert_fails("network_name")

    def test_a_wrongly_typed_integer_column_fails(self):
        rows = self.rows("message_occurrence")
        rows[0]["transmit_period_ms"] = "10"
        self.write("message_occurrence", rows)
        self.assert_fails("transmit_period_ms")

    def test_a_bool_is_not_an_integer(self):
        rows = self.rows("message_occurrence")
        rows[0]["payload_byte_length"] = True
        self.write("message_occurrence", rows)
        self.assert_fails("must be an integer, not a bool")

    def test_an_empty_lookup_key_fails(self):
        rows = self.rows("signal_occurrence")
        rows[0]["signal_key"] = ""
        self.write("signal_occurrence", rows)
        self.assert_fails("signal_key")


if __name__ == "__main__":
    unittest.main(verbosity=2)
