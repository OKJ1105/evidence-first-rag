"""Sections 5 and 7: what a normalized result must carry to exist at all."""

import unittest

from evidence_first_rag import (
    OPENS_NO_CONNECTION,
    Limitation,
    LimitationKind,
    ProducingLayer,
    Result,
    Route,
    SourceTrace,
    Status,
    UNSUPPORTED_ROUTE,
)

from .support import executed_bundle, scope, success_result, unexecuted_bundle


def negative_result(status, **overrides):
    """A minimal valid result for one of the no-connection families."""
    limitations = ()
    if status is Status.NEEDS_ENTITY_DISCOVERY:
        limitations = (
            Limitation(
                kind=LimitationKind.ENTITY_DISCOVERY_NOT_IMPLEMENTED,
                detail="Entity Discovery is not implemented in v0.1.",
            ),
        )
    trace = SourceTrace()
    if status is Status.UNSUPPORTED:
        trace = SourceTrace(producing_layer=ProducingLayer.ADAPTER)
    values = {
        "status": status,
        "evidence_bundle": unexecuted_bundle(
            route=UNSUPPORTED_ROUTE if status is Status.UNSUPPORTED else Route.MESSAGE_FACTS
        ),
        "source_trace": trace,
        "limitations": limitations,
    }
    values.update(overrides)
    return Result(**values)


class EveryResultCarriesAllThreeStructures(unittest.TestCase):
    """Section 5: including every negative outcome."""

    def test_a_result_without_an_evidence_bundle_does_not_construct(self):
        with self.assertRaises(TypeError):
            Result(status=Status.SUCCESS, source_trace=SourceTrace())

    def test_a_result_without_a_source_trace_does_not_construct(self):
        with self.assertRaises(TypeError):
            Result(status=Status.SUCCESS, evidence_bundle=executed_bundle())

    def test_limitations_is_present_and_may_be_empty(self):
        self.assertEqual(success_result().limitations, ())

    def test_every_status_family_can_carry_all_three(self):
        for status in Status:
            with self.subTest(status=status):
                result = (
                    success_result()
                    if status is Status.SUCCESS
                    else _minimal(status)
                )
                self.assertIsNotNone(result.evidence_bundle)
                self.assertIsNotNone(result.source_trace)
                self.assertIsInstance(result.limitations, tuple)


def _minimal(status):
    if status in OPENS_NO_CONNECTION:
        return negative_result(status)
    limitations = ()
    if status is Status.COVERAGE_GAP:
        limitations = (
            Limitation(
                kind=LimitationKind.COVERAGE_NOT_ESTABLISHED,
                detail="No snapshot covers network_name SAMPLE_NET_BODY.",
            ),
        )
    rows = ()
    row_count = 0
    if status is Status.AMBIGUOUS:
        rows = (scope().as_parameters(), scope(revision_label="SAMPLE_REV_B").as_parameters())
        row_count = 2
    return Result(
        status=status,
        evidence_bundle=executed_bundle(
            row_count=row_count,
            template_name="TPL_SNAPSHOT_CANDIDATES_V1",
            template_version="1",
            resolved_scope=None if status is not Status.NOT_FOUND else scope(),
        ),
        source_trace=SourceTrace(),
        limitations=limitations,
        rows=rows,
    )


class TheThreeFamiliesThatOpenNoConnection(unittest.TestCase):
    """Section 5's closing paragraph, asserted on the result rather than only
    on the bundle: the status may not claim what the family forbids."""

    def test_their_evidence_is_empty_on_all_four_fields(self):
        for status in OPENS_NO_CONNECTION:
            with self.subTest(status=status):
                bundle = negative_result(status).evidence_bundle
                self.assertEqual(bundle.template_name, "")
                self.assertEqual(bundle.template_version, "")
                self.assertEqual(dict(bundle.bound_parameters), {})
                self.assertIsNone(bundle.resolved_scope)

    def test_they_record_that_no_connection_was_opened(self):
        for status in OPENS_NO_CONNECTION:
            with self.subTest(status=status):
                safeguards = negative_result(status).evidence_bundle.read_only_safeguards
                self.assertFalse(safeguards.connection_opened)

    def test_a_bundle_that_opened_one_is_refused(self):
        for status in OPENS_NO_CONNECTION:
            with self.subTest(status=status):
                with self.assertRaises(ValueError) as raised:
                    negative_result(status, evidence_bundle=executed_bundle())
                self.assertIn("Section 5", str(raised.exception))

    def test_they_return_no_rows(self):
        for status in OPENS_NO_CONNECTION:
            with self.subTest(status=status):
                with self.assertRaises(ValueError):
                    negative_result(status, rows=({"message_key": "SAMPLE_MSG_A"},))


class SuccessMeansAtLeastOneRow(unittest.TestCase):
    def test_a_success_with_no_rows_is_refused(self):
        with self.assertRaises(ValueError):
            success_result(rows=())

    def test_a_success_with_a_zero_row_count_is_refused(self):
        with self.assertRaises(ValueError):
            success_result(evidence_bundle=executed_bundle(row_count=0))


class NotFoundMeansNoRowMatched(unittest.TestCase):
    def test_a_not_found_carrying_rows_is_refused(self):
        with self.assertRaises(ValueError):
            Result(
                status=Status.NOT_FOUND,
                evidence_bundle=executed_bundle(row_count=0),
                source_trace=SourceTrace(),
                rows=({"message_key": "SAMPLE_MSG_A"},),
            )

    def test_a_not_found_with_a_non_zero_row_count_is_refused(self):
        with self.assertRaises(ValueError):
            Result(
                status=Status.NOT_FOUND,
                evidence_bundle=executed_bundle(row_count=1),
                source_trace=SourceTrace(),
            )


class TheEntriesSection7RequiresUnconditionally(unittest.TestCase):
    def test_coverage_gap_states_what_coverage_could_not_be_established(self):
        with self.assertRaises(ValueError) as raised:
            Result(
                status=Status.COVERAGE_GAP,
                evidence_bundle=executed_bundle(row_count=0),
                source_trace=SourceTrace(),
            )
        self.assertIn("coverage_not_established", str(raised.exception))

    def test_needs_entity_discovery_states_that_discovery_is_not_implemented(self):
        with self.assertRaises(ValueError) as raised:
            negative_result(Status.NEEDS_ENTITY_DISCOVERY, limitations=())
        self.assertIn("entity_discovery_not_implemented", str(raised.exception))

    def test_unsupported_records_its_producing_layer(self):
        with self.assertRaises(ValueError) as raised:
            negative_result(Status.UNSUPPORTED, source_trace=SourceTrace())
        self.assertIn("producing layer", str(raised.exception))

    def test_either_producing_layer_is_accepted(self):
        for layer in ProducingLayer:
            with self.subTest(layer=layer):
                result = negative_result(
                    Status.UNSUPPORTED, source_trace=SourceTrace(producing_layer=layer)
                )
                self.assertIs(result.source_trace.producing_layer, layer)


class TheRowsAreNotEditableAfterTheFact(unittest.TestCase):
    def test_a_caller_cannot_change_a_row_it_handed_over(self):
        row = {"message_key": "SAMPLE_MSG_A"}
        result = success_result(rows=(row,))
        row["message_key"] = "SAMPLE_MSG_B"
        self.assertEqual(result.rows[0]["message_key"], "SAMPLE_MSG_A")

    def test_a_row_that_is_not_a_mapping_is_refused(self):
        with self.assertRaises(ValueError):
            success_result(rows=(("message_key", "SAMPLE_MSG_A"),))

    def test_a_single_mapping_is_not_a_row_sequence(self):
        with self.assertRaises(ValueError):
            success_result(rows={"message_key": "SAMPLE_MSG_A"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
