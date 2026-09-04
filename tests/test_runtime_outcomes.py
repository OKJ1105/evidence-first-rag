"""Sections 5 and 7 on the path that reaches a route's own template.

`success` and `not_found` are the two statuses decided by whether the
registered template returned a row, and everything else here is the evidence
Section 7 requires around them.
"""

import unittest

from evidence_first_rag import (
    LimitationKind,
    MappingProvenance,
    SnapshotScope,
    Status,
)
from evidence_first_rag.runtime import DataFault, Request, Runtime

from .runtime_support import (
    BASE,
    CHASSIS,
    CHASSIS_B,
    FakeDatabase,
    REVISED,
    candidate_row,
    mapping_row,
    message_row,
    signal_row,
)

CANDIDATES = "TPL_SNAPSHOT_CANDIDATES_V1"
MESSAGE_FACTS = "TPL_MESSAGE_FACTS_V1"
SIGNAL_FACTS = "TPL_SIGNAL_FACTS_V1"
SIGNAL_MAPPING = "TPL_SIGNAL_MAPPING_V1"

MESSAGE = BASE | {"message_key": "SAMPLE_MSG_ENGINE_STATUS"}
SIGNAL = MESSAGE | {"signal_key": "SAMPLE_SIG_ENGINE_SPEED"}


def answer(route, arguments, rows, scope=None, **request):
    rows = {CANDIDATES: (candidate_row(scope or BASE),), **rows}
    database = FakeDatabase(rows)
    result = Runtime(database=database, fixture_provenance=("fixtures/",)).execute(
        Request(route=route, arguments=arguments, **request)
    )
    return database, result


class ARowMakesItASuccess(unittest.TestCase):
    def test_message_facts(self):
        _, result = answer("message_facts", MESSAGE, {MESSAGE_FACTS: (message_row(),)})
        self.assertIs(result.status, Status.SUCCESS)
        self.assertEqual(result.rows[0]["transmit_period_ms"], 10)

    def test_signal_facts(self):
        _, result = answer("signal_facts", SIGNAL, {SIGNAL_FACTS: (signal_row(),)})
        self.assertIs(result.status, Status.SUCCESS)

    def test_signal_mapping_returning_more_than_one_row(self):
        _, result = answer(
            "signal_mapping",
            SIGNAL,
            {
                SIGNAL_MAPPING: (
                    mapping_row(),
                    mapping_row(mapping_key="SAMPLE_MAP_SPEED_TO_FAULT"),
                )
            },
        )
        self.assertIs(result.status, Status.SUCCESS)
        self.assertEqual(result.evidence_bundle.row_count, 2)

    def test_the_bundle_names_the_template_that_produced_the_rows(self):
        _, result = answer("message_facts", MESSAGE, {MESSAGE_FACTS: (message_row(),)})
        bundle = result.evidence_bundle
        self.assertEqual(bundle.template_name, MESSAGE_FACTS)
        self.assertEqual(bundle.template_version, "1")
        self.assertEqual(bundle.resolved_scope, SnapshotScope(**BASE))
        self.assertEqual(bundle.row_count, 1)

    def test_the_bundle_records_exactly_what_was_bound(self):
        # Section 7: "containing exactly the parameters bound, with values".
        # The optional `mapping_key` the request omitted is bound as null,
        # because the registered SQL tests it for null rather than being
        # rewritten around it.
        _, result = answer("signal_mapping", SIGNAL, {SIGNAL_MAPPING: (mapping_row(),)})
        self.assertEqual(
            dict(result.evidence_bundle.bound_parameters), SIGNAL | {"mapping_key": None}
        )

    def test_the_trace_names_every_snapshot_that_contributed_a_row(self):
        _, result = answer("message_facts", MESSAGE, {MESSAGE_FACTS: (message_row(),)})
        self.assertEqual(
            result.source_trace.contributing_scopes, (SnapshotScope(**BASE),)
        )
        self.assertEqual(result.source_trace.fixture_provenance, ("fixtures/",))

    def test_the_rows_the_caller_gets_cannot_be_edited_afterwards(self):
        _, result = answer("message_facts", MESSAGE, {MESSAGE_FACTS: (message_row(),)})
        with self.assertRaises(TypeError):
            result.rows[0]["transmit_period_ms"] = 20


class NoRowMakesItNotFound(unittest.TestCase):
    def test_a_resolved_covered_snapshot_with_no_matching_key(self):
        # `FX-107`. The scope resolved and the snapshot exists; the key does
        # not. Section 5 reserves `coverage_gap` for the case where coverage
        # itself could not be established.
        _, result = answer(
            "message_facts", BASE | {"message_key": "SAMPLE_MSG_ABSENT"}, {MESSAGE_FACTS: ()}
        )
        self.assertIs(result.status, Status.NOT_FOUND)

    def test_a_source_signal_with_no_mapping_asserted(self):
        # `FX-103`.
        _, result = answer("signal_mapping", SIGNAL, {SIGNAL_MAPPING: ()})
        self.assertIs(result.status, Status.NOT_FOUND)

    def test_it_still_records_the_scope_it_resolved(self):
        # The difference from `coverage_gap`, in the evidence rather than only
        # in the status: this one resolved a snapshot and that one did not.
        _, result = answer("message_facts", MESSAGE, {MESSAGE_FACTS: ()})
        self.assertEqual(result.evidence_bundle.resolved_scope, SnapshotScope(**BASE))
        self.assertEqual(result.evidence_bundle.row_count, 0)

    def test_no_snapshot_contributed_a_row(self):
        _, result = answer("message_facts", MESSAGE, {MESSAGE_FACTS: ()})
        self.assertEqual(result.source_trace.contributing_scopes, ())


class NotFoundAndCoverageGapAreDistinguishable(unittest.TestCase):
    """The likely defect is conflating them, so this asserts them side by side."""

    def test_the_same_route_produces_each_from_a_different_cause(self):
        _, missing_key = answer(
            "message_facts", BASE | {"message_key": "SAMPLE_MSG_ABSENT"}, {MESSAGE_FACTS: ()}
        )
        database = FakeDatabase({CANDIDATES: ()})
        missing_scope = Runtime(database=database).execute(
            Request(
                route="message_facts",
                arguments=BASE | {"network_name": "SAMPLE_NET_BODY", "message_key": "SAMPLE_MSG_ENGINE_STATUS"},
            )
        )
        self.assertIs(missing_key.status, Status.NOT_FOUND)
        self.assertIs(missing_scope.status, Status.COVERAGE_GAP)
        self.assertIsNotNone(missing_key.evidence_bundle.resolved_scope)
        self.assertIsNone(missing_scope.evidence_bundle.resolved_scope)


class ASupersededSnapshotOwesALimitationsEntry(unittest.TestCase):
    """Sections 4.2 and 7, and fixture `FX-104`."""

    def superseded_mapping(self):
        return answer(
            "signal_mapping",
            {**CHASSIS, "message_key": "SAMPLE_MSG_WHEEL_SPEED", "signal_key": "SAMPLE_SIG_WHEEL_SPEED_FL"},
            {
                SIGNAL_MAPPING: (
                    mapping_row(
                        asserting=CHASSIS,
                        source=CHASSIS,
                        target=CHASSIS_B,
                        asserting_superseded_by=CHASSIS_B,
                        source_superseded_by=CHASSIS_B,
                        source_message_key="SAMPLE_MSG_WHEEL_SPEED",
                        source_signal_key="SAMPLE_SIG_WHEEL_SPEED_FL",
                        target_message_key="SAMPLE_MSG_WHEEL_SPEED",
                        target_signal_key="SAMPLE_SIG_WHEEL_SPEED_FL",
                        mapping_key="SAMPLE_MAP_WHEEL_FL_CARRYOVER",
                    ),
                )
            },
            scope=CHASSIS,
        )

    def test_the_outcome_is_still_success(self):
        # Section 8.1: "`FX-104` deliberately expects `success`, not a negative
        # status. A superseded snapshot still holds facts about itself."
        _, result = self.superseded_mapping()
        self.assertIs(result.status, Status.SUCCESS)

    def test_the_entry_names_the_snapshot_that_superseded_it(self):
        # Section 4.2: "`superseded_by` is exposed in `limitations`". Exposing
        # it means naming what replaced the snapshot, not raising a flag.
        _, result = self.superseded_mapping()
        entries = [
            limitation
            for limitation in result.limitations
            if limitation.kind is LimitationKind.SUPERSEDED_SNAPSHOT
        ]
        self.assertEqual(len(entries), 1)
        self.assertIn("SAMPLE_NET_CHASSIS", entries[0].detail)
        self.assertIn("SAMPLE_REV_B", entries[0].detail)

    def test_one_entry_per_distinct_snapshot_not_per_row(self):
        # The asserting and source snapshots are the same superseded snapshot
        # here, and a second identical entry would say nothing the first did
        # not.
        _, result = self.superseded_mapping()
        details = [limitation.detail for limitation in result.limitations]
        self.assertEqual(len(details), len(set(details)))

    def test_each_participant_is_read_from_its_own_columns(self):
        # A mapping row carries three snapshots, and only one of them is
        # superseded here. A runtime that read one participant's supersession
        # and attributed it to the row would produce the same entry count and
        # the wrong scope, so the entry is checked for the scope it names.
        for prefix, scope in (("asserting", BASE), ("source", BASE), ("target", REVISED)):
            with self.subTest(participant=prefix):
                _, result = answer(
                    "signal_mapping",
                    SIGNAL,
                    {
                        SIGNAL_MAPPING: (
                            mapping_row(
                                asserting=BASE,
                                source=BASE,
                                target=REVISED,
                                **{f"{prefix}_superseded_by": CHASSIS_B},
                            ),
                        )
                    },
                )
                entries = [
                    limitation
                    for limitation in result.limitations
                    if limitation.kind is LimitationKind.SUPERSEDED_SNAPSHOT
                ]
                self.assertEqual(len(entries), 1)
                self.assertIn(scope["snapshot_label"], entries[0].detail)

    def test_a_current_snapshot_owes_no_entry(self):
        _, result = answer("message_facts", MESSAGE, {MESSAGE_FACTS: (message_row(),)})
        self.assertEqual(result.limitations, ())

    def test_a_facts_row_carries_its_own_supersession(self):
        _, result = answer(
            "message_facts",
            {**CHASSIS, "message_key": "SAMPLE_MSG_WHEEL_SPEED"},
            {MESSAGE_FACTS: (message_row(CHASSIS, superseded_by=CHASSIS_B, message_key="SAMPLE_MSG_WHEEL_SPEED"),)},
            scope=CHASSIS,
        )
        self.assertTrue(
            any(
                limitation.kind is LimitationKind.SUPERSEDED_SNAPSHOT
                for limitation in result.limitations
            )
        )

    def test_a_half_null_supersession_is_a_data_fault(self):
        # `superseded_by` is one nullable reference to one row, so its four
        # dereferenced dimensions are null together or present together.
        broken = message_row(CHASSIS, superseded_by=CHASSIS_B)
        broken["superseded_by_revision_label"] = None
        with self.assertRaises(DataFault):
            answer(
                "message_facts",
                {**CHASSIS, "message_key": "SAMPLE_MSG_ENGINE_STATUS"},
                {MESSAGE_FACTS: (broken,)},
                scope=CHASSIS,
            )


class AMappingCarriesProvenancePerRelation(unittest.TestCase):
    """Section 4.5: "the result exposes one entry per asserting relation"."""

    def test_each_row_gets_its_own_entry_with_all_three_scopes_separate(self):
        _, result = answer(
            "signal_mapping",
            SIGNAL,
            {
                SIGNAL_MAPPING: (
                    mapping_row(asserting=BASE, source=BASE, target=REVISED),
                    mapping_row(
                        asserting=BASE,
                        source=BASE,
                        target=BASE,
                        mapping_key="SAMPLE_MAP_SPEED_TO_FAULT",
                    ),
                )
            },
        )
        self.assertEqual(
            result.source_trace.mapping_provenance,
            (
                MappingProvenance(
                    asserting_scope=SnapshotScope(**BASE),
                    source_endpoint_scope=SnapshotScope(**BASE),
                    target_endpoint_scope=SnapshotScope(**REVISED),
                ),
                MappingProvenance(
                    asserting_scope=SnapshotScope(**BASE),
                    source_endpoint_scope=SnapshotScope(**BASE),
                    target_endpoint_scope=SnapshotScope(**BASE),
                ),
            ),
        )

    def test_the_other_two_routes_carry_none(self):
        for route, arguments, rows in (
            ("message_facts", MESSAGE, {MESSAGE_FACTS: (message_row(),)}),
            ("signal_facts", SIGNAL, {SIGNAL_FACTS: (signal_row(),)}),
        ):
            with self.subTest(route=route):
                _, result = answer(route, arguments, rows)
                self.assertEqual(result.source_trace.mapping_provenance, ())

    def test_continuity_comes_from_the_row_and_not_from_equal_keys(self):
        # Section 4.2: "Continuity or equivalence between occurrences in
        # different snapshots is never derived from equal `message_key` or
        # `signal_key`." Two occurrences with identical keys in two snapshots
        # are related here only because a mapping row says so, and the trace
        # records which snapshot asserted it.
        _, result = answer(
            "signal_mapping",
            {**CHASSIS, "message_key": "SAMPLE_MSG_WHEEL_SPEED", "signal_key": "SAMPLE_SIG_WHEEL_SPEED_FL"},
            {
                SIGNAL_MAPPING: (
                    mapping_row(
                        asserting=CHASSIS,
                        source=CHASSIS,
                        target=CHASSIS_B,
                        source_message_key="SAMPLE_MSG_WHEEL_SPEED",
                        source_signal_key="SAMPLE_SIG_WHEEL_SPEED_FL",
                        target_message_key="SAMPLE_MSG_WHEEL_SPEED",
                        target_signal_key="SAMPLE_SIG_WHEEL_SPEED_FL",
                    ),
                )
            },
            scope=CHASSIS,
        )
        provenance = result.source_trace.mapping_provenance[0]
        self.assertEqual(provenance.asserting_scope, SnapshotScope(**CHASSIS))
        self.assertEqual(provenance.target_endpoint_scope, SnapshotScope(**CHASSIS_B))
        self.assertNotEqual(
            provenance.source_endpoint_scope, provenance.target_endpoint_scope
        )

    def test_a_full_page_of_mappings_records_the_truncation(self):
        rows = tuple(
            mapping_row(mapping_key=f"SAMPLE_MAP_{index:03d}") for index in range(200)
        )
        _, result = answer("signal_mapping", SIGNAL, {SIGNAL_MAPPING: rows})
        self.assertTrue(
            any(
                limitation.kind is LimitationKind.TRUNCATED_BY_LIMIT
                for limitation in result.limitations
            )
        )


class AFactsTemplateOverflowIsAFault(unittest.TestCase):
    """Section 4.4: the limit of 2 is a detector, not a cap."""

    def test_two_rows_from_a_facts_template_raise_rather_than_answer(self):
        for route, arguments, name, row in (
            ("message_facts", MESSAGE, MESSAGE_FACTS, message_row()),
            ("signal_facts", SIGNAL, SIGNAL_FACTS, signal_row()),
        ):
            with self.subTest(route=route):
                with self.assertRaises(DataFault) as raised:
                    answer(route, arguments, {name: (row, row)})
                self.assertEqual(raised.exception.conformance_class, "data")

    def test_a_mapping_template_returning_two_rows_is_an_ordinary_success(self):
        # The same row count, the opposite meaning. Section 4.4 gives the
        # mapping template a limit of 200 that truncates; the difference is
        # registered on the template, not decided by the runtime.
        _, result = answer(
            "signal_mapping",
            SIGNAL,
            {SIGNAL_MAPPING: (mapping_row(), mapping_row(mapping_key="SAMPLE_MAP_B"))},
        )
        self.assertIs(result.status, Status.SUCCESS)


if __name__ == "__main__":
    unittest.main(verbosity=2)
