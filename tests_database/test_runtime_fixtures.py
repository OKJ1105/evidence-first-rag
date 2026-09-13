"""The Section 8.1 fixture cases, run against a real PostgreSQL database.

Issue #14 registers `FX-001` to `FX-107` and `FX-113` as this slice's
acceptance evidence, and they belong here rather than in `tests/` because most
of them are claims about what the registered SQL returns. `tests/` proves the
runtime's decisions given rows; this file proves the rows.

Two examples of why the split matters. `FX-101` asserts the result carries
`transmit_period_ms` 20 rather than 10 -- an implementation whose WHERE clause
ignored `snapshot_label` returns the other snapshot's row, and only a real
query can catch that. `FX-105` asserts that a request omitting
`snapshot_label` resolves nothing, against a fixture set where the newest
`ingested_at` and the highest `snapshot_label` deliberately disagree, so a
runtime that quietly ordered by either returns a snapshot here and fails.

Every case additionally asserts the three Section 7 structures and runs
Section 4.9's check `E1` over the rendered answer.
"""

import decimal
import os
import unittest

from evidence_first_rag import LimitationKind, Status
from evidence_first_rag.runtime import Request, Runtime, render, values_of
from evidence_first_rag.runtime.connection import PsycopgDatabase

from . import support

DATABASE = "mvp_test_runtime"

POWERTRAIN = {
    "project_code": "SAMPLE_PROJECT_ALPHA",
    "revision_label": "SAMPLE_REV_A",
    "network_name": "SAMPLE_NET_POWERTRAIN",
    "snapshot_label": "SAMPLE_SNAP_BASE",
}
REVISED = POWERTRAIN | {"snapshot_label": "SAMPLE_SNAP_REVISED"}
CHASSIS_A = POWERTRAIN | {"network_name": "SAMPLE_NET_CHASSIS"}
CHASSIS_B = CHASSIS_A | {"revision_label": "SAMPLE_REV_B"}

# Section 7: "the fixture provenance that actually exists."
PROVENANCE = (
    "fixtures/source_snapshot.jsonl",
    "fixtures/message_occurrence.jsonl",
    "fixtures/signal_occurrence.jsonl",
    "fixtures/signal_mapping.jsonl",
)


def setUpModule():
    support.build(DATABASE)


def tearDownModule():
    support.drop(DATABASE)


def runtime():
    return Runtime(
        database=PsycopgDatabase(
            connection_parameters={
                "dbname": DATABASE,
                "user": "mvp_runtime",
                "password": os.environ["MVP_RUNTIME_PASSWORD"],
                "host": os.environ.get("PGHOST"),
                "port": os.environ.get("PGPORT"),
            }
        ),
        fixture_provenance=PROVENANCE,
    )


def without(mapping, *names):
    return {key: value for key, value in mapping.items() if key not in names}


class FixtureCase(unittest.TestCase):
    """One registered case, with the assertions every case owes."""

    def answer(self, route, arguments, **request):
        result = runtime().execute(Request(route=route, arguments=arguments, **request))
        self.assert_evidence(result)
        self.assert_rendering(result)
        return result

    def assert_evidence(self, result):
        """Section 7: all three structures, with their required keys.

        Section 8's acceptance evidence for Section 7 is "every fixture
        asserts the presence of all three structures and the required keys",
        so this runs on every case rather than on one of them.
        """
        bundle = result.evidence_bundle
        self.assertEqual(bundle.contract_identifier, "mvp-v0.1")
        self.assertEqual(bundle.contract_version, "0.6.1")
        self.assertEqual(bundle.collation, "C")
        self.assertNotEqual(bundle.route, "")
        self.assertIsNotNone(result.source_trace)
        self.assertIsInstance(result.limitations, tuple)
        opened = bundle.read_only_safeguards
        if opened.connection_opened:
            # Section 4.3: every connection is opened with the runtime
            # identity, inside a read-only transaction.
            self.assertEqual(opened.role_name, "mvp_runtime")
            self.assertTrue(opened.read_only_transaction)
        self.assertEqual(result.source_trace.fixture_provenance, PROVENANCE)

    def assert_rendering(self, result):
        """Section 4.9 check `E1`, on every case."""
        from evidence_first_rag.runtime import compose

        answer = compose(result)
        self.assertEqual(set(answer.values()) - values_of(result), set())
        self.assertIn(result.status.value, answer.render())
        self.assertEqual(answer.render(), render(result))

    def assert_no_surrogate_key(self, result):
        # Section 4.2: "No surrogate key appears in any public payload."
        for row in result.rows:
            for column in row:
                self.assertFalse(column.endswith("_id"), column)


class TheSuccessCasePerRoute(FixtureCase):
    def test_fx_001_message_facts_for_a_fully_scoped_reference(self):
        result = self.answer(
            "message_facts", POWERTRAIN | {"message_key": "SAMPLE_MSG_ENGINE_STATUS"}
        )
        self.assertIs(result.status, Status.SUCCESS)
        self.assertEqual(len(result.rows), 1)
        self.assertEqual(result.rows[0]["frame_identifier"], 256)
        self.assert_no_surrogate_key(result)

    def test_fx_002_signal_facts_for_a_fully_scoped_reference(self):
        result = self.answer(
            "signal_facts",
            POWERTRAIN
            | {
                "message_key": "SAMPLE_MSG_ENGINE_STATUS",
                "signal_key": "SAMPLE_SIG_ENGINE_SPEED",
            },
        )
        self.assertIs(result.status, Status.SUCCESS)
        self.assertEqual(result.rows[0]["unit_label"], "SAMPLE_UNIT_RPM")
        # Section 6: the stored precision, unrounded.
        self.assertEqual(result.rows[0]["scale_factor"], decimal.Decimal("0.25"))
        self.assert_no_surrogate_key(result)

    def test_fx_003_signal_mapping_returning_more_than_one_row(self):
        result = self.answer(
            "signal_mapping",
            POWERTRAIN
            | {
                "message_key": "SAMPLE_MSG_ENGINE_STATUS",
                "signal_key": "SAMPLE_SIG_ENGINE_SPEED",
            },
        )
        self.assertIs(result.status, Status.SUCCESS)
        self.assertEqual(len(result.rows), 2)
        # Section 4.4 registers the ordering as `mapping_key`; Section 6
        # forbids the caller from applying its own.
        self.assertEqual(
            [row["mapping_key"] for row in result.rows],
            ["SAMPLE_MAP_SPEED_TO_FAULT", "SAMPLE_MAP_SPEED_TO_GEAR"],
        )
        # Section 4.5: one entry per asserting relation, never merged.
        self.assertEqual(len(result.source_trace.mapping_provenance), 2)
        self.assert_no_surrogate_key(result)


class ScopeResolvesToTheRequestedSnapshotOnly(FixtureCase):
    def test_fx_101_the_same_message_key_in_two_snapshots(self):
        # Asserted on the differing `transmit_period_ms`, not on a row merely
        # coming back: both snapshots hold a row for this key, so "the right
        # one" is only observable in a value that differs between them.
        periods = {}
        for scope in (POWERTRAIN, REVISED):
            result = self.answer(
                "message_facts", scope | {"message_key": "SAMPLE_MSG_ENGINE_STATUS"}
            )
            self.assertIs(result.status, Status.SUCCESS)
            self.assertEqual(
                result.rows[0]["snapshot_label"], scope["snapshot_label"]
            )
            periods[scope["snapshot_label"]] = result.rows[0]["transmit_period_ms"]
        self.assertEqual(
            periods, {"SAMPLE_SNAP_BASE": 10, "SAMPLE_SNAP_REVISED": 20}
        )

    def test_fx_102_the_same_signal_key_under_two_parent_messages(self):
        # Asserted on the differing `scale_factor`. Section 4.1 prohibits a
        # snapshot-level unique constraint on `signal_key` precisely so this
        # case can exist.
        factors = {}
        for parent in ("SAMPLE_MSG_ENGINE_STATUS", "SAMPLE_MSG_TRANSMISSION_STATE"):
            result = self.answer(
                "signal_facts",
                POWERTRAIN
                | {"message_key": parent, "signal_key": "SAMPLE_SIG_TEMPERATURE"},
            )
            self.assertIs(result.status, Status.SUCCESS)
            self.assertEqual(result.rows[0]["message_key"], parent)
            factors[parent] = result.rows[0]["scale_factor"]
        self.assertEqual(
            factors,
            {
                "SAMPLE_MSG_ENGINE_STATUS": decimal.Decimal("0.1"),
                "SAMPLE_MSG_TRANSMISSION_STATE": decimal.Decimal("0.5"),
            },
        )


class TheTwoWaysToReturnNothing(FixtureCase):
    """`not_found` and `coverage_gap`, side by side. Section 5 draws the line
    at whether coverage could be established, and conflating them is the
    likely defect."""

    def test_fx_103_a_source_signal_with_no_mapping_asserted(self):
        result = self.answer(
            "signal_mapping",
            POWERTRAIN
            | {
                "message_key": "SAMPLE_MSG_ENGINE_STATUS",
                "signal_key": "SAMPLE_SIG_TEMPERATURE",
            },
        )
        self.assertIs(result.status, Status.NOT_FOUND)
        self.assertEqual(result.rows, ())

    def test_fx_107_a_lookup_key_absent_from_a_resolved_covered_snapshot(self):
        for route, arguments in (
            ("message_facts", POWERTRAIN | {"message_key": "SAMPLE_MSG_ABSENT"}),
            (
                "signal_facts",
                POWERTRAIN
                | {
                    "message_key": "SAMPLE_MSG_ENGINE_STATUS",
                    "signal_key": "SAMPLE_SIG_ABSENT",
                },
            ),
        ):
            with self.subTest(route=route):
                result = self.answer(route, arguments)
                self.assertIs(result.status, Status.NOT_FOUND)
                # The snapshot exists and was resolved; only the key is
                # missing. This is the field that tells it from `FX-106`.
                self.assertIsNotNone(result.evidence_bundle.resolved_scope)

    def test_fx_106_a_network_name_no_snapshot_has(self):
        result = self.answer(
            "message_facts",
            POWERTRAIN
            | {"network_name": "SAMPLE_NET_BODY", "message_key": "SAMPLE_MSG_ENGINE_STATUS"},
        )
        self.assertIs(result.status, Status.COVERAGE_GAP)
        self.assertIsNone(result.evidence_bundle.resolved_scope)
        self.assertTrue(
            any(
                limitation.kind is LimitationKind.COVERAGE_NOT_ESTABLISHED
                for limitation in result.limitations
            )
        )

    def test_the_two_are_distinguishable_by_status_and_by_evidence(self):
        absent_key = self.answer(
            "message_facts", POWERTRAIN | {"message_key": "SAMPLE_MSG_ABSENT"}
        )
        absent_scope = self.answer(
            "message_facts",
            POWERTRAIN
            | {"network_name": "SAMPLE_NET_BODY", "message_key": "SAMPLE_MSG_ABSENT"},
        )
        self.assertIs(absent_key.status, Status.NOT_FOUND)
        self.assertIs(absent_scope.status, Status.COVERAGE_GAP)
        self.assertNotEqual(
            absent_key.evidence_bundle.template_name,
            absent_scope.evidence_bundle.template_name,
        )


class ASupersededSnapshotStillHoldsItsOwnFacts(FixtureCase):
    def test_fx_104_a_mapping_asserted_by_a_superseded_snapshot(self):
        result = self.answer(
            "signal_mapping",
            CHASSIS_A
            | {
                "message_key": "SAMPLE_MSG_WHEEL_SPEED",
                "signal_key": "SAMPLE_SIG_WHEEL_SPEED_FL",
            },
        )
        # Section 8.1: "`FX-104` deliberately expects `success`, not a negative
        # status."
        self.assertIs(result.status, Status.SUCCESS)
        self.assertEqual(len(result.rows), 1)
        self.assertEqual(result.rows[0]["mapping_key"], "SAMPLE_MAP_WHEEL_FL_CARRYOVER")

        entries = [
            limitation
            for limitation in result.limitations
            if limitation.kind is LimitationKind.SUPERSEDED_SNAPSHOT
        ]
        self.assertEqual(len(entries), 1)
        self.assertIn("SAMPLE_REV_B", entries[0].detail)

        # Each participant's supersession is read from its own dereference,
        # asserted separately because the asserting and source snapshots are
        # the same row here: an entry produced from one of them alone would
        # look identical in `limitations`, and only these three columns say
        # which joins actually resolved.
        row = result.rows[0]
        self.assertEqual(row["asserting_superseded_by_revision_label"], "SAMPLE_REV_B")
        self.assertEqual(row["source_superseded_by_revision_label"], "SAMPLE_REV_B")
        self.assertIsNone(row["target_superseded_by_revision_label"])

    def test_the_relation_carries_both_endpoints_and_its_asserting_scope(self):
        # Section 4.2: continuity between the two `SAMPLE_SIG_WHEEL_SPEED_FL`
        # occurrences comes from this row, never from their equal keys.
        result = self.answer(
            "signal_mapping",
            CHASSIS_A
            | {
                "message_key": "SAMPLE_MSG_WHEEL_SPEED",
                "signal_key": "SAMPLE_SIG_WHEEL_SPEED_FL",
            },
        )
        provenance = result.source_trace.mapping_provenance[0]
        self.assertEqual(provenance.asserting_scope.revision_label, "SAMPLE_REV_A")
        self.assertEqual(provenance.source_endpoint_scope.revision_label, "SAMPLE_REV_A")
        self.assertEqual(provenance.target_endpoint_scope.revision_label, "SAMPLE_REV_B")
        self.assertEqual(
            result.rows[0]["source_signal_key"], result.rows[0]["target_signal_key"]
        )

    def test_the_later_snapshot_is_not_presented_as_asserting_it(self):
        # Section 4.2: "A mapping asserted by a superseded snapshot is never
        # presented as holding in a later snapshot." Asking the later snapshot
        # for the same relation returns nothing; the row belongs to the
        # snapshot that asserted it.
        result = self.answer(
            "signal_mapping",
            CHASSIS_B
            | {
                "message_key": "SAMPLE_MSG_WHEEL_SPEED",
                "signal_key": "SAMPLE_SIG_WHEEL_SPEED_FL",
            },
        )
        self.assertIs(result.status, Status.NOT_FOUND)


class AnUnderSpecifiedScopeIsNeverResolved(FixtureCase):
    def test_fx_105_two_candidate_snapshots(self):
        result = self.answer(
            "message_facts",
            without(POWERTRAIN, "snapshot_label")
            | {"message_key": "SAMPLE_MSG_ENGINE_STATUS"},
        )
        self.assertIs(result.status, Status.AMBIGUOUS)
        self.assertEqual(
            [row["snapshot_label"] for row in result.rows],
            ["SAMPLE_SNAP_BASE", "SAMPLE_SNAP_REVISED"],
        )
        self.assertEqual(len(result.source_trace.contributing_scopes), 2)

    def test_fx_105_the_newest_ingested_snapshot_is_not_the_one_returned(self):
        # `SAMPLE_SNAP_BASE` is the newest by `ingested_at` (2026-02-01) and
        # `SAMPLE_SNAP_REVISED` is the highest by `snapshot_label`. A runtime
        # that resolved by either would return facts here. None are returned,
        # and nothing is resolved.
        result = self.answer(
            "message_facts",
            without(POWERTRAIN, "snapshot_label")
            | {"message_key": "SAMPLE_MSG_ENGINE_STATUS"},
        )
        self.assertIsNone(result.evidence_bundle.resolved_scope)
        for row in result.rows:
            self.assertNotIn("transmit_period_ms", row)

    def test_fx_113_exactly_one_candidate_snapshot(self):
        # Contract version 0.4.0's recorded decision: "One matching candidate
        # is still `ambiguous`." `ALPHA / REV_B / CHASSIS` holds exactly one
        # snapshot, and it is not superseded, so this case can fail for one
        # reason only.
        result = self.answer(
            "message_facts",
            without(CHASSIS_B, "snapshot_label")
            | {"message_key": "SAMPLE_MSG_WHEEL_SPEED"},
        )
        self.assertIs(result.status, Status.AMBIGUOUS)
        self.assertEqual(len(result.rows), 1)
        self.assertEqual(result.rows[0]["snapshot_label"], "SAMPLE_SNAP_BASE")
        self.assertIsNone(result.evidence_bundle.resolved_scope)
        self.assertEqual(result.limitations, ())

    def test_the_two_halves_of_the_threshold_agree(self):
        # `FX-105` and `FX-113` are the two-candidate and one-candidate halves
        # of one Section 4.2 rule. An implementation that answered one and not
        # the other has made the candidate count its threshold, which is the
        # reading Section 4.2 rejects.
        for arguments in (
            without(POWERTRAIN, "snapshot_label")
            | {"message_key": "SAMPLE_MSG_ENGINE_STATUS"},
            without(CHASSIS_B, "snapshot_label")
            | {"message_key": "SAMPLE_MSG_WHEEL_SPEED"},
        ):
            with self.subTest(arguments=sorted(arguments)):
                self.assertIs(self.answer("message_facts", arguments).status, Status.AMBIGUOUS)


class LookupKeysAreComparedByteExact(FixtureCase):
    """Section 6: "Lookup keys are compared byte-exact: no case folding, no
    Unicode normalization, no trimming. A lookup that differs from a stored key
    only by case is `not_found` -- fail-closed, never fuzzy."

    An absence again, and one a runtime acquires by accident rather than on
    purpose: a helper that upper-cased an identifier on the way in would make
    all four of these succeed.
    """

    def test_a_message_key_differing_only_by_case(self):
        for key in (
            "sample_msg_engine_status",
            "Sample_Msg_Engine_Status",
            " SAMPLE_MSG_ENGINE_STATUS",
            "SAMPLE_MSG_ENGINE_STATUS ",
        ):
            with self.subTest(message_key=key):
                result = self.answer("message_facts", POWERTRAIN | {"message_key": key})
                self.assertIs(result.status, Status.NOT_FOUND)

    def test_a_scope_dimension_differing_only_by_case_is_a_coverage_gap(self):
        # The same rule one level up: an unmatched scope value is not a
        # near-miss to be corrected, it is coverage that could not be
        # established.
        result = self.answer(
            "message_facts",
            POWERTRAIN
            | {
                "network_name": "sample_net_powertrain",
                "message_key": "SAMPLE_MSG_ENGINE_STATUS",
            },
        )
        self.assertIs(result.status, Status.COVERAGE_GAP)


class TheRuntimeIdentityIsTheOneThatConnects(FixtureCase):
    def test_every_opened_connection_is_read_only_and_named(self):
        # Section 4.3 and Section 7. Asserted here rather than only in
        # `assert_evidence` so that it is a test with a name, and not a
        # condition inside a helper.
        result = self.answer(
            "message_facts", POWERTRAIN | {"message_key": "SAMPLE_MSG_ENGINE_STATUS"}
        )
        safeguards = result.evidence_bundle.read_only_safeguards
        self.assertTrue(safeguards.connection_opened)
        self.assertTrue(safeguards.read_only_transaction)
        self.assertEqual(safeguards.role_name, "mvp_runtime")

    def test_the_same_request_twice_produces_the_same_result(self):
        # Section 6 repeatability, at the level a caller sees. The evidence
        # bundle carries no timestamp and no run identifier, so two results
        # for one request are comparable in full.
        arguments = POWERTRAIN | {"message_key": "SAMPLE_MSG_ENGINE_STATUS"}
        first = self.answer("message_facts", arguments)
        second = self.answer("message_facts", arguments)
        self.assertEqual(first, second)
        self.assertEqual(render(first), render(second))


if __name__ == "__main__":
    unittest.main(verbosity=2)
