"""What makes `A1` a comparison rather than a tautology.

Section 4.9's `A1` compares the runtime's result against a registered expected
result. That is only evidence if the two sides were built independently, so
this file pins the independence rather than describing it:

- the committed `expected/` files are exactly what `authoring.py` produces
  from `fixtures/`, so the provenance is re-runnable and not a claim;
- `authoring.py` imports nothing from `runtime/`, so the expected side cannot
  be the runtime's own output wearing a different name;
- every `SAMPLE_*` identifier in an expectation appears in `fixtures/`, so an
  expectation cannot name data the registered inputs do not contain.
"""

import ast
import json
import pathlib
import re
import unittest

from evidence_first_rag.conformance import authoring, expected
from evidence_first_rag.conformance.cases import REGISTERED

FIXTURES = pathlib.Path(authoring.FIXTURES)
SAMPLE = re.compile(r"SAMPLE_[A-Z0-9_]+")


class TheCommittedFilesAreWhatTheToolProduces(unittest.TestCase):
    def test_every_case_has_a_registered_expectation(self):
        self.assertEqual(
            sorted(case.identifier for case in REGISTERED), list(expected.identifiers())
        )

    def test_each_committed_file_equals_the_freshly_built_document(self):
        # The provenance claim, checkable. If someone edits an expectation by
        # hand to make a failing run pass, this fails and names the file.
        built = authoring.build()
        for identifier, document in built.items():
            with self.subTest(identifier=identifier):
                committed = json.loads(
                    (authoring.DIRECTORY / f"{identifier}.json").read_text()
                )
                self.assertEqual(committed, document)


class TheExpectedSideNeverSeesTheRuntime(unittest.TestCase):
    def test_authoring_imports_nothing_from_the_runtime_that_produces_results(self):
        """`authoring.py` may reach the registry for a template's allowlist --
        Section 4.4 fixes it and it is an input, not an output -- but never
        the runtime's result path. An expectation built from `service.py`
        would make `A1` compare the runtime with itself.
        """
        tree = ast.parse(pathlib.Path(authoring.__file__).read_text())
        forbidden = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                if any(part in node.module for part in ("service", "render", "normalize")):
                    forbidden.append(node.module)
            if isinstance(node, ast.Import):
                forbidden += [
                    alias.name
                    for alias in node.names
                    if "service" in alias.name or "render" in alias.name
                ]
        self.assertEqual(forbidden, [])

    def test_it_does_not_import_the_conformance_runner(self):
        source = pathlib.Path(authoring.__file__).read_text()
        self.assertNotIn("from .runner", source)
        self.assertNotIn("import runner", source)


class AnExpectationCannotNameDataTheFixturesLack(unittest.TestCase):
    def fixture_identifiers(self):
        found = set()
        for path in FIXTURES.glob("*.jsonl"):
            found.update(SAMPLE.findall(path.read_text()))
        return found

    def test_every_sample_identifier_comes_from_the_fixtures(self):
        available = self.fixture_identifiers()
        # The three names `fixtures/README.md` reserves as absent. A case that
        # looks one of them up expects `not_found`, so the identifier appears
        # in the request and, through `bound_parameters`, in the expectation.
        absent_on_purpose = {"SAMPLE_MSG_ABSENT", "SAMPLE_SIG_ABSENT", "SAMPLE_NET_BODY"}
        for identifier in expected.identifiers():
            with self.subTest(identifier=identifier):
                document = json.dumps(expected.registered(identifier))
                unknown = set(SAMPLE.findall(document)) - available - absent_on_purpose
                self.assertEqual(unknown, set())

    def test_the_reserved_absent_names_really_are_absent_from_the_fixtures(self):
        # Otherwise the carve-out above would be hiding real data.
        available = self.fixture_identifiers()
        for name in ("SAMPLE_MSG_ABSENT", "SAMPLE_SIG_ABSENT", "SAMPLE_NET_BODY"):
            with self.subTest(name=name):
                self.assertNotIn(name, available)


class TheExpectationsSayWhatSection81Registers(unittest.TestCase):
    """A last reading of the documents against the contract's own table, so
    that a wrong-but-self-consistent set of expectations is still caught."""

    EXPECTED_STATUS = {
        "FX-001": "success", "FX-002": "success", "FX-003": "success",
        "FX-101": "success", "FX-102": "success", "FX-103": "not_found",
        "FX-104": "success", "FX-105": "ambiguous", "FX-106": "coverage_gap",
        "FX-107": "not_found", "FX-113": "ambiguous",
    }

    def test_each_expectation_carries_the_status_section_8_1_registers(self):
        for identifier, status in self.EXPECTED_STATUS.items():
            with self.subTest(identifier=identifier):
                self.assertEqual(expected.registered(identifier)["status"], status)

    def test_fx_003_expects_more_than_one_row(self):
        self.assertGreater(len(expected.registered("FX-003")["rows"]), 1)

    def test_fx_104_expects_a_limitations_entry_naming_the_superseded_snapshot(self):
        entries = expected.registered("FX-104")["limitations"]
        self.assertEqual([entry["kind"] for entry in entries], ["superseded_snapshot"])
        self.assertIn("SAMPLE_REV_B", entries[0]["detail"])

    def test_fx_105_lists_both_candidates_and_fx_113_lists_one(self):
        self.assertEqual(len(expected.registered("FX-105")["rows"]), 2)
        self.assertEqual(len(expected.registered("FX-113")["rows"]), 1)
        for identifier in ("FX-105", "FX-113"):
            with self.subTest(identifier=identifier):
                bundle = expected.registered(identifier)["evidence_bundle"]
                self.assertIsNone(bundle["resolved_scope"])

    def test_fx_101_expects_the_requested_snapshots_differing_value(self):
        # The whole point of the case: SNAP_REVISED carries 20 and SNAP_BASE
        # carries 10, so an expectation of 20 is what catches a runtime that
        # resolved to the wrong snapshot.
        row = expected.registered("FX-101")["rows"][0]
        self.assertEqual(row["snapshot_label"], "SAMPLE_SNAP_REVISED")
        self.assertEqual(row["transmit_period_ms"], 20)

    def test_fx_102_expects_the_requested_parents_differing_value(self):
        row = expected.registered("FX-102")["rows"][0]
        self.assertEqual(row["message_key"], "SAMPLE_MSG_TRANSMISSION_STATE")
        self.assertEqual(row["scale_factor"], "0.5")

    def test_not_found_resolves_a_scope_and_coverage_gap_does_not(self):
        # Section 5's line between the two, in the registered expectations
        # rather than only in the runtime.
        self.assertIsNotNone(
            expected.registered("FX-107")["evidence_bundle"]["resolved_scope"]
        )
        self.assertIsNone(
            expected.registered("FX-106")["evidence_bundle"]["resolved_scope"]
        )

    def test_no_expectation_carries_a_surrogate_key(self):
        # Section 4.2: "No surrogate key appears in any public payload."
        for identifier in expected.identifiers():
            with self.subTest(identifier=identifier):
                for row in expected.registered(identifier)["rows"]:
                    for column in row:
                        self.assertFalse(column.endswith("_id"), column)


if __name__ == "__main__":
    unittest.main(verbosity=2)
