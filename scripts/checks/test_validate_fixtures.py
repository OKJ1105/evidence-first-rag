"""Negative tests for validate_fixtures.py.

A validator nobody has seen fail is a validator nobody knows works. Each test
here takes the real fixtures, breaks exactly one thing, and asserts that the
check fails and says which thing. The positive case is asserted too, so a test
that starts passing for the wrong reason is visible.

Run directly (`python scripts/checks/test_validate_fixtures.py`) or through
`python -m unittest`. Standard library only, like everything else in
scripts/checks.
"""

import contextlib
import importlib.util
import io
import json
import pathlib
import shutil
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
REPOSITORY = HERE.parent.parent
SOURCE = REPOSITORY / "fixtures"

TABLES = (
    "source_snapshot",
    "message_occurrence",
    "signal_occurrence",
    "signal_mapping",
)


def load_module():
    """Import validate_fixtures.py by path, so this file does not depend on
    the checks directory being an importable package."""
    spec = importlib.util.spec_from_file_location(
        "validate_fixtures", HERE / "validate_fixtures.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FixtureCheck(unittest.TestCase):
    """Runs the checker over a mutable copy of the real fixtures."""

    def setUp(self):
        self.module = load_module()
        self.directory = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.directory, ignore_errors=True)
        self.fixtures = self.directory / "fixtures"
        shutil.copytree(SOURCE, self.fixtures)
        self.module.FIXTURES = self.fixtures

    def rows(self, table):
        path = self.fixtures / f"{table}.jsonl"
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

    def write(self, table, rows):
        path = self.fixtures / f"{table}.jsonl"
        path.write_text(
            "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
        )

    def run_check(self):
        """Return (exit code, printed output)."""
        captured = io.StringIO()
        with contextlib.redirect_stdout(captured):
            code = self.module.main()
        return code, captured.getvalue()

    def assert_fails(self, fragment):
        code, output = self.run_check()
        self.assertEqual(code, 1, f"expected failure, got pass:\n{output}")
        self.assertIn(fragment, output)
        return output


class TestPositive(FixtureCheck):
    def test_the_registered_fixtures_pass(self):
        code, output = self.run_check()
        self.assertEqual(code, 0, output)
        self.assertIn("Fixtures: PASS", output)


class TestFileShape(FixtureCheck):
    def test_a_malformed_line_fails(self):
        path = self.fixtures / "source_snapshot.jsonl"
        path.write_text(path.read_text(encoding="utf-8") + "{not json\n", encoding="utf-8")
        self.assert_fails("not valid JSON")

    def test_a_blank_line_fails(self):
        path = self.fixtures / "message_occurrence.jsonl"
        path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        self.assert_fails("blank line")

    def test_a_missing_file_fails(self):
        (self.fixtures / "signal_mapping.jsonl").unlink()
        self.assert_fails("missing")

    def test_a_line_that_is_not_an_object_fails(self):
        path = self.fixtures / "source_snapshot.jsonl"
        path.write_text(path.read_text(encoding="utf-8") + "[1, 2]\n", encoding="utf-8")
        self.assert_fails("not a JSON object")


class TestColumns(FixtureCheck):
    def test_a_missing_column_fails(self):
        rows = self.rows("message_occurrence")
        del rows[0]["frame_identifier"]
        self.write("message_occurrence", rows)
        self.assert_fails("missing columns ['frame_identifier']")

    def test_a_column_outside_the_contract_fails(self):
        rows = self.rows("signal_occurrence")
        rows[0]["comment"] = "SAMPLE_NOTE"
        self.write("signal_occurrence", rows)
        self.assert_fails("columns not in Section 4.1: ['comment']")

    def test_a_null_in_a_not_null_column_fails(self):
        rows = self.rows("source_snapshot")
        rows[0]["network_name"] = None
        self.write("source_snapshot", rows)
        self.assert_fails("network_name is not null in Section 4.1")

    def test_a_surrogate_key_in_a_fixture_fails(self):
        rows = self.rows("source_snapshot")
        rows[0]["snapshot_id"] = 1
        self.write("source_snapshot", rows)
        self.assert_fails("Section 4.11 forbids one")

    def test_a_surrogate_key_nested_in_a_reference_fails(self):
        rows = self.rows("message_occurrence")
        rows[0]["snapshot"]["snapshot_id"] = 1
        self.write("message_occurrence", rows)
        self.assert_fails("Section 4.11 forbids one")


class TestIdentifiers(FixtureCheck):
    def test_an_identifier_without_the_sample_prefix_fails(self):
        rows = self.rows("source_snapshot")
        rows[0]["project_code"] = "ACME_PROJECT"
        self.write("source_snapshot", rows)
        self.assert_fails("does not use the SAMPLE_* convention")

    def test_a_non_ascii_identifier_fails(self):
        rows = self.rows("signal_occurrence")
        rows[0]["signal_key"] = "SAMPLE_SIG_温度"
        self.write("signal_occurrence", rows)
        self.assert_fails("is not ASCII")


class TestReferences(FixtureCheck):
    def test_an_unresolvable_snapshot_reference_fails(self):
        rows = self.rows("message_occurrence")
        rows[0]["snapshot"]["snapshot_label"] = "SAMPLE_SNAP_NOWHERE"
        self.write("message_occurrence", rows)
        self.assert_fails("snapshot reference")

    def test_an_unresolvable_message_reference_fails(self):
        rows = self.rows("signal_occurrence")
        rows[0]["message"]["message_key"] = "SAMPLE_MSG_NOWHERE"
        self.write("signal_occurrence", rows)
        self.assert_fails("message reference")

    def test_an_unresolvable_mapping_endpoint_fails(self):
        rows = self.rows("signal_mapping")
        rows[0]["target_signal"]["signal_key"] = "SAMPLE_SIG_NOWHERE"
        self.write("signal_mapping", rows)
        self.assert_fails("target_signal reference")

    def test_a_reference_missing_a_scope_dimension_fails(self):
        rows = self.rows("message_occurrence")
        del rows[0]["snapshot"]["network_name"]
        self.write("message_occurrence", rows)
        self.assert_fails("is not a Section 4.2 reference")

    def test_an_unresolvable_superseded_by_fails(self):
        rows = self.rows("source_snapshot")
        for row in rows:
            if row["superseded_by"]:
                row["superseded_by"]["revision_label"] = "SAMPLE_REV_NOWHERE"
                break
        self.write("source_snapshot", rows)
        self.assert_fails("superseded_by")

    def test_a_snapshot_that_supersedes_itself_fails(self):
        rows = self.rows("source_snapshot")
        rows[0]["superseded_by"] = {
            field: rows[0][field] for field in self.module.SNAPSHOT_REF
        }
        self.write("source_snapshot", rows)
        self.assert_fails("supersedes itself")


class TestUniqueConstraints(FixtureCheck):
    def test_a_duplicate_snapshot_fails(self):
        rows = self.rows("source_snapshot")
        rows.append(dict(rows[0]))
        self.write("source_snapshot", rows)
        self.assert_fails("duplicate (project_code, revision_label, network_name, snapshot_label)")

    def test_a_duplicate_message_in_one_snapshot_fails(self):
        rows = self.rows("message_occurrence")
        rows.append(dict(rows[0]))
        self.write("message_occurrence", rows)
        self.assert_fails("duplicate (snapshot_id, message_key)")

    def test_a_duplicate_signal_under_one_parent_fails(self):
        rows = self.rows("signal_occurrence")
        rows.append(dict(rows[0]))
        self.write("signal_occurrence", rows)
        self.assert_fails("duplicate (message_occurrence_id, signal_key)")

    def test_a_duplicate_mapping_triple_fails(self):
        rows = self.rows("signal_mapping")
        duplicate = dict(rows[0])
        duplicate["mapping_key"] = "SAMPLE_MAP_OTHER_NAME"
        rows.append(duplicate)
        self.write("signal_mapping", rows)
        self.assert_fails("duplicate (asserting_snapshot_id,")


class TestStructuralCases(FixtureCheck):
    """Each Section 8.1 case the data has to keep reachable."""

    def rename_message_key(self, scope, old, new):
        """Rename one message_key within one snapshot, everywhere it is
        referenced. The fixtures carry two cross-snapshot collisions on
        purpose, so a test for FX-101 has to remove both."""

        def matches(reference):
            return (
                all(reference[field] == value for field, value in scope.items())
                and reference["message_key"] == old
            )

        messages = self.rows("message_occurrence")
        for row in messages:
            if all(row["snapshot"][f] == v for f, v in scope.items()) and row["message_key"] == old:
                row["message_key"] = new
        self.write("message_occurrence", messages)

        signals = self.rows("signal_occurrence")
        for row in signals:
            if matches(row["message"]):
                row["message"]["message_key"] = new
        self.write("signal_occurrence", signals)

        mappings = self.rows("signal_mapping")
        for row in mappings:
            for side in ("source_signal", "target_signal"):
                if matches(row[side]):
                    row[side]["message_key"] = new
        self.write("signal_mapping", mappings)

    def test_removing_every_cross_snapshot_name_collision_fails_fx_101(self):
        self.rename_message_key(
            {"snapshot_label": "SAMPLE_SNAP_REVISED"},
            "SAMPLE_MSG_ENGINE_STATUS",
            "SAMPLE_MSG_ENGINE_STATUS_V2",
        )
        self.rename_message_key(
            {"revision_label": "SAMPLE_REV_B"},
            "SAMPLE_MSG_WHEEL_SPEED",
            "SAMPLE_MSG_WHEEL_SPEED_V2",
        )
        self.assert_fails("FX-101")

    def test_removing_the_shared_signal_key_fails_fx_102(self):
        rows = self.rows("signal_occurrence")
        for row in rows:
            if (
                row["message"]["message_key"] == "SAMPLE_MSG_TRANSMISSION_STATE"
                and row["signal_key"] == "SAMPLE_SIG_TEMPERATURE"
            ):
                row["signal_key"] = "SAMPLE_SIG_OIL_TEMPERATURE"
        self.write("signal_occurrence", rows)
        self.assert_fails("FX-102")

    def test_mapping_every_signal_fails_fx_103(self):
        signals = self.rows("signal_occurrence")
        mappings = self.rows("signal_mapping")
        # Two targets, so the signal used as a target is still a source of
        # something. With one target it stays unmapped and FX-103 holds.
        target_a = mappings[0]["target_signal"]
        target_b = mappings[0]["source_signal"]
        existing = {
            (
                tuple(sorted(row["asserting_snapshot"].items())),
                tuple(sorted(row["source_signal"].items())),
                tuple(sorted(row["target_signal"].items())),
            )
            for row in mappings
        }
        for index, signal in enumerate(signals):
            source = dict(signal["message"])
            source["signal_key"] = signal["signal_key"]
            target = target_b if source == target_a else target_a
            if source == target:
                continue
            asserting = {
                field: signal["message"][field] for field in self.module.SNAPSHOT_REF
            }
            triple = (
                tuple(sorted(asserting.items())),
                tuple(sorted(source.items())),
                tuple(sorted(target.items())),
            )
            if triple in existing:
                continue
            existing.add(triple)
            mappings.append(
                {
                    "asserting_snapshot": {
                        field: signal["message"][field]
                        for field in self.module.SNAPSHOT_REF
                    },
                    "source_signal": source,
                    "target_signal": target,
                    "mapping_key": f"SAMPLE_MAP_SATURATE_{index}",
                    "transform_kind": "SAMPLE_TRANSFORM_DIRECT",
                }
            )
        self.write("signal_mapping", mappings)
        self.assert_fails("FX-103")

    def test_unsuperseding_the_asserting_snapshot_fails_fx_104(self):
        rows = self.rows("source_snapshot")
        for row in rows:
            row["superseded_by"] = None
        self.write("source_snapshot", rows)
        self.assert_fails("FX-104")

    def test_removing_the_second_candidate_snapshot_fails_fx_105(self):
        self.write(
            "message_occurrence",
            [
                row
                for row in self.rows("message_occurrence")
                if row["snapshot"]["snapshot_label"] != "SAMPLE_SNAP_REVISED"
            ],
        )
        self.write(
            "signal_occurrence",
            [
                row
                for row in self.rows("signal_occurrence")
                if row["message"]["snapshot_label"] != "SAMPLE_SNAP_REVISED"
            ],
        )
        self.write(
            "source_snapshot",
            [
                row
                for row in self.rows("source_snapshot")
                if row["snapshot_label"] != "SAMPLE_SNAP_REVISED"
            ],
        )
        self.assert_fails("FX-105")

    def test_ingested_at_agreeing_with_label_order_fails_fx_105(self):
        """The Section 4.2 trap: if the newest snapshot is also the one a
        correct runtime would pick, a runtime that picks the newest passes by
        luck. The fixtures must keep the two orders disagreeing."""
        rows = self.rows("source_snapshot")
        for row in rows:
            if row["snapshot_label"] == "SAMPLE_SNAP_REVISED":
                row["ingested_at"] = "2026-12-31T00:00:00Z"
        self.write("source_snapshot", rows)
        self.assert_fails("would pass by coincidence")

    def test_adding_a_reserved_absent_value_fails(self):
        rows = self.rows("source_snapshot")
        rows.append(
            {
                "project_code": "SAMPLE_PROJECT_ALPHA",
                "revision_label": "SAMPLE_REV_A",
                "network_name": "SAMPLE_NET_BODY",
                "snapshot_label": "SAMPLE_SNAP_BASE",
                "superseded_by": None,
                "ingested_at": "2026-04-01T00:00:00Z",
            }
        )
        self.write("source_snapshot", rows)
        self.assert_fails("reserved-absent network_name")

    def test_removing_every_mapping_fails_fx_003(self):
        self.write("signal_mapping", [])
        self.assert_fails("FX-003")


class TestFixtureFilesAreRegistered(unittest.TestCase):
    def test_one_file_exists_per_contract_table(self):
        for table in TABLES:
            with self.subTest(table=table):
                self.assertTrue((SOURCE / f"{table}.jsonl").is_file())

    def test_no_unexpected_fixture_files(self):
        found = {path.stem for path in SOURCE.glob("*.jsonl")}
        self.assertEqual(found, set(TABLES))


if __name__ == "__main__":
    unittest.main(verbosity=2)
