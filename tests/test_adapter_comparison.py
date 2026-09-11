"""The Milestone 2 comparison, and the gate Charter Section 9 requires.

"A numeric adoption threshold is registered before the run it judges.
Reporting a metric without a pre-registered pass condition does not satisfy a
gate."

Most of this file is that one sentence, tested from every direction a run
could get around it. The metrics themselves are arithmetic; the gate is the
part that would be quietly defeated by someone reading the numbers first.
"""

import datetime
import unittest

from evidence_first_rag import Status
from evidence_first_rag.adapter import (
    Baseline,
    CuratedEntry,
    EvaluationCase,
    Proposal,
    Thresholds,
    compare,
    judge,
    measure,
)
from evidence_first_rag.runtime import Runtime

from .runtime_support import BASE, FakeDatabase, candidate_row, message_row

TEXT = (
    "facts for SAMPLE_MSG_ENGINE_STATUS in SAMPLE_PROJECT_ALPHA SAMPLE_REV_A"
    " SAMPLE_NET_POWERTRAIN SAMPLE_SNAP_BASE"
)
ARGUMENTS = BASE | {"message_key": "SAMPLE_MSG_ENGINE_STATUS"}

RESOLVING = EvaluationCase(
    identifier="EV-001",
    text=TEXT,
    expected_status="success",
    expected_route="message_facts",
    expected_arguments=ARGUMENTS,
)
UNRESOLVABLE = EvaluationCase(
    identifier="EV-002",
    text="please delete the production database",
    expected_status="unsupported",
)


def shifted(instant: str, hours: float) -> str:
    """`instant` moved by `hours`.

    Derived from the run rather than hardcoded: a fixed date would silently
    stop testing what it claims the moment the wall clock passed it, which is
    exactly how a pre-registration check quietly becomes a no-op.
    """
    moment = datetime.datetime.fromisoformat(instant)
    return (moment + datetime.timedelta(hours=hours)).isoformat()


def thresholds(*, run=None, **overrides):
    values = {
        "task_coverage": 0.8,
        "false_resolution": 0.0,
        "registered_at": shifted(
            run.started_at if run is not None else _now(), -1
        ),
        "contract_version": "0.6.0",
    }
    values.update(overrides)
    return Thresholds(**values)


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def report(**overrides):
    engine = Runtime(
        database=FakeDatabase(
            {
                "TPL_SNAPSHOT_CANDIDATES_V1": (candidate_row(),),
                "TPL_MESSAGE_FACTS_V1": (message_row(),),
            }
        )
    )
    values = {
        "cases": [RESOLVING, UNRESOLVABLE],
        "adapter": lambda text: (
            Proposal(route="message_facts", arguments=ARGUMENTS)
            if text == TEXT
            else Proposal(route="unsupported", arguments={})
        ),
        "baseline": Baseline(
            [CuratedEntry(text=TEXT, route="message_facts", arguments=ARGUMENTS)]
        ).resolve,
        "model": "claude-opus-5",
        "decoding": {"model": "claude-opus-5"},
        "runtime": engine,
    }
    values.update(overrides)
    cases = values.pop("cases")
    built = compare(cases, **values)
    return built


class TheGateRefusesToJudgeWithoutPreRegistration(unittest.TestCase):
    def test_no_thresholds_is_never_a_pass(self):
        verdict = judge(report(), None)
        self.assertFalse(verdict.adoptable)
        self.assertFalse(verdict.judged)
        self.assertIn("no pre-registered thresholds", verdict.reasons[0])

    def test_thresholds_registered_after_the_run_are_refused(self):
        # The whole point. Numbers chosen once the results are in are not a
        # pass condition, whatever file they were written to.
        run = report()
        late = thresholds(registered_at=shifted(run.started_at, 1))
        verdict = judge(run, late)
        self.assertFalse(verdict.adoptable)
        self.assertFalse(verdict.judged)
        self.assertIn("not before this run", verdict.reasons[0])

    def test_thresholds_registered_at_the_same_instant_are_refused(self):
        run = report()
        verdict = judge(run, thresholds(registered_at=run.started_at))
        self.assertFalse(verdict.judged)

    def test_thresholds_registered_before_the_run_are_judged(self):
        verdict = judge(report(), thresholds())
        self.assertTrue(verdict.judged)

    def test_a_threshold_without_a_timezone_cannot_be_constructed(self):
        # A bare local time cannot be compared with a run that may happen
        # anywhere, and a comparison that silently assumed UTC would make the
        # ordering check meaningless.
        with self.assertRaises(ValueError):
            thresholds(registered_at="2026-09-04T09:00:00")

    def test_the_ordering_check_is_not_satisfied_by_the_clock_moving_on(self):
        # A pre-registration check written against a fixed past date passes
        # forever once that date is behind us, testing nothing. Both
        # directions are asserted against the same run.
        run = report()
        self.assertTrue(judge(run, thresholds(run=run)).judged)
        self.assertFalse(
            judge(run, thresholds(registered_at=shifted(run.started_at, 0.001))).judged
        )

    def test_a_threshold_must_name_the_contract_version_that_registered_it(self):
        with self.assertRaises(ValueError):
            thresholds(contract_version="")

    def test_a_threshold_outside_zero_to_one_is_refused(self):
        for field in ("task_coverage", "false_resolution"):
            for bad in (-0.1, 1.5, "0.9", True):
                with self.subTest(field=field, value=bad):
                    with self.assertRaises(ValueError):
                        thresholds(**{field: bad})


class TheJudgementReadsTheRegisteredNumbers(unittest.TestCase):
    def test_a_clean_run_over_a_bar_it_clears_is_adoptable(self):
        verdict = judge(report(), thresholds(), pinned_decoding={"model": "claude-opus-5"})
        self.assertTrue(verdict.adoptable, verdict.reasons)

    def test_coverage_below_the_bar_is_not(self):
        # A blind adapter answers "unsupported" to everything, so it is right
        # about the unanswerable case and wrong about the other: coverage 0.5,
        # which a bar of 1.0 does not clear.
        blind = judge(
            report(adapter=lambda text: Proposal(route="unsupported", arguments={})),
            thresholds(task_coverage=1.0),
        )
        self.assertFalse(blind.adoptable)
        self.assertTrue(any("task coverage" in reason for reason in blind.reasons))

    def test_a_false_resolution_over_the_bar_is_not(self):
        # An adapter that answers the unanswerable request with a real route,
        # using values the request does contain.
        def confident(text):
            return Proposal(route="message_facts", arguments=ARGUMENTS)

        verdict = judge(
            report(cases=[RESOLVING, EvaluationCase(
                identifier="EV-003",
                text=TEXT,
                expected_status="unsupported",
            )], adapter=confident),
            thresholds(false_resolution=0.0),
        )
        self.assertFalse(verdict.adoptable)
        self.assertTrue(any("false resolution" in reason for reason in verdict.reasons))

    def test_a_decoding_configuration_that_drifted_from_the_pin_is_not(self):
        # Section 8: "The recorded model identifier and decoding configuration
        # in the evaluation artifact must equal the pinned values."
        verdict = judge(
            report(decoding={"model": "claude-opus-5", "output_config": {"effort": "max"}}),
            thresholds(),
            pinned_decoding={"model": "claude-opus-5"},
        )
        self.assertFalse(verdict.adoptable)
        self.assertTrue(any("decoding" in reason for reason in verdict.reasons))

    def test_a_run_that_touched_no_database_cannot_rule_out_weakening(self):
        verdict = judge(report(runtime=None), thresholds())
        self.assertFalse(verdict.adoptable)
        self.assertTrue(any("did not execute" in reason for reason in verdict.reasons))

    def test_a_weakened_negative_blocks_adoption_however_good_the_averages(self):
        # Charter Section 9: adopted "without weakening negative behavior".
        # One request that turned a refusal into a fact is a failure whatever
        # the aggregate says, so this is checked case by case.
        run = report(
            cases=[
                EvaluationCase(
                    identifier="EV-004",
                    text=TEXT,
                    expected_status="not_found",
                    expected_route="message_facts",
                    expected_arguments=ARGUMENTS,
                )
            ]
        )
        self.assertEqual(run.adapter.task_coverage, 1.0)
        self.assertEqual(run.adapter.weakened_negatives, ("EV-004",))
        verdict = judge(run, thresholds())
        self.assertFalse(verdict.adoptable)
        self.assertTrue(any("weakened" in reason for reason in verdict.reasons))


class ANonMappingProposalIsRefusedRatherThanCrashingTheRun(unittest.TestCase):
    """#119. `_correct` called `dict()` on whatever the model emitted.

    Section 4.6 types adapter output as untrusted, and since #112 the schema
    asks for `arguments` as a `[{name, value}]` list: `client.py`
    `_as_mapping` folds a conforming one into a mapping and passes a
    malformed one through unchanged, so that deterministic revalidation
    refuses the shape rather than the adapter guessing what was meant.
    `_correct` runs before `measure` can record that refusal, so `dict()`
    raised and the exception left `perform` -- the run exited having written
    neither the artifact nor the raw record, losing every paid call in the
    dispatch.

    The first four shapes are the ones
    `tests/test_adapter_client.py::test_a_list_that_is_not_pairs_is_passed_on_as_it_came`
    enumerates. The rest are the other reachable ones: `_as_mapping` returns
    anything that is not a `list` unchanged, so a response whose `arguments`
    is a string, a number or `null` reaches this guard too -- and the string
    exercises `_as_text`'s own branch, where the payload is the text rather
    than its `repr`.
    """

    SHAPES = (
        [1, 2],
        ["message_key"],
        [{"value": "x"}],
        [{"name": 1, "value": "x"}],
        "message_key=SAMPLE_MSG_ENGINE_STATUS",
        5,
        None,
    )

    def measured(self, arguments, case=RESOLVING):
        return measure([case], lambda text: Proposal(route="message_facts", arguments=arguments))

    def test_measure_survives_every_shape_the_fold_passes_through(self):
        for arguments in self.SHAPES:
            with self.subTest(arguments=arguments):
                metrics, outcomes = self.measured(arguments)
                outcome = outcomes[0]
                self.assertFalse(outcome.correct)
                self.assertFalse(outcome.accepted)
                self.assertEqual(outcome.refused_as, Status.INVALID_REQUEST.value)
                # A refusal never became a lookup, so it is a miss and not a
                # false resolution -- Section 8.3's definition, unchanged.
                self.assertFalse(outcome.false_resolution)
                self.assertEqual(metrics.task_coverage, 0.0)
                self.assertEqual(metrics.false_resolution, 0.0)

    def test_the_artifact_records_the_shape_rather_than_erasing_it(self):
        # `{}` made a malformed proposal indistinguishable from one that
        # carried no arguments at all (#95). The reserved key keeps the
        # field a `dict[str, str]` and keeps the payload, typed.
        for arguments in self.SHAPES:
            with self.subTest(arguments=arguments):
                _, outcomes = self.measured(arguments)
                recorded = outcomes[0].as_json()["proposed_arguments"]
                self.assertEqual(list(recorded), ["//not-a-mapping"])
                # `_as_text`'s rule, not `repr` alone: a string is recorded as
                # itself, so asserting `repr` here would pass by accident on
                # the four lists and mislead on the string.
                payload = arguments if isinstance(arguments, str) else repr(arguments)
                self.assertEqual(
                    recorded["//not-a-mapping"], f"{type(arguments).__name__}: {payload}"
                )

    def test_the_reserved_key_is_told_apart_from_a_model_that_emits_it(self):
        # The key alone cannot identify the branch: this field records what
        # the model emitted, not what the allowlist permits, so a response
        # carrying the pair {"name": "//not-a-mapping", "value": "x"} folds
        # into a genuine mapping and lands on the same key. The type prefix
        # is what separates them.
        _, outcomes = self.measured({"//not-a-mapping": "x"})
        emitted = outcomes[0].as_json()["proposed_arguments"]
        _, outcomes = self.measured([1, 2])
        reserved = outcomes[0].as_json()["proposed_arguments"]
        self.assertEqual(list(emitted), list(reserved))
        self.assertNotEqual(emitted, reserved)
        self.assertEqual(emitted["//not-a-mapping"], "x")
        self.assertEqual(reserved["//not-a-mapping"], "list: [1, 2]")

    def test_a_mapping_is_still_recorded_name_by_name(self):
        # The guard must not send a well-formed proposal down the same path.
        _, outcomes = self.measured(ARGUMENTS)
        recorded = outcomes[0].as_json()["proposed_arguments"]
        self.assertNotIn("//not-a-mapping", recorded)
        self.assertEqual(recorded, ARGUMENTS)
        self.assertTrue(outcomes[0].correct)

    def test_a_route_that_is_not_text_is_a_miss_rather_than_a_crash(self):
        # The same untrusted path, three lines earlier in `_correct`: `read`
        # parses with `_keep_duplicates`, so a response whose top-level
        # `route` key appears twice arrives as a list, and `in _ROUTE_NAMES`
        # hashes what it is given. It raised, and the run lost every paid
        # call in the dispatch exactly as the arguments crash did.
        for route in (["message_facts", "signal_facts"], {"a": 1}, 5, None):
            with self.subTest(route=route):
                _, outcomes = measure(
                    [RESOLVING], lambda text: Proposal(route=route, arguments=ARGUMENTS)
                )
                # Not the registered route, so a miss -- and it got recorded.
                self.assertFalse(outcomes[0].correct)
                _, outcomes = measure(
                    [UNRESOLVABLE], lambda text: Proposal(route=route, arguments=ARGUMENTS)
                )
                # Names none of the three, so the no-route case is correct.
                self.assertTrue(outcomes[0].correct)

    def test_a_case_registering_no_route_never_reads_the_arguments(self):
        # That branch judges by route name and refusal status alone, so a
        # non-mapping cannot reach `dict()` there. Proved by holding the
        # arguments malformed and moving only the route: `unsupported` is
        # not one of the three, so the case is correct however unreadable
        # the arguments are.
        _, outcomes = measure(
            [UNRESOLVABLE], lambda text: Proposal(route="unsupported", arguments=[1, 2])
        )
        self.assertTrue(outcomes[0].correct)
        # And a route that *is* one of the three is judged by the refusal
        # status, which a non-mapping makes `invalid_request` rather than
        # the registered `unsupported` -- still no `dict()`, still no crash.
        _, outcomes = self.measured([1, 2], case=UNRESOLVABLE)
        self.assertFalse(outcomes[0].correct)
        self.assertEqual(outcomes[0].refused_as, Status.INVALID_REQUEST.value)


class TheMetricsCountWhatTheyClaim(unittest.TestCase):
    def test_answering_no_route_to_an_unanswerable_request_is_correct(self):
        metrics, _ = measure(
            [UNRESOLVABLE], lambda text: Proposal(route="unsupported", arguments={})
        )
        self.assertEqual(metrics.task_coverage, 1.0)
        self.assertEqual(metrics.false_resolution, 0.0)

    def test_a_refused_proposal_is_a_miss_and_not_a_false_resolution(self):
        # It never became a lookup, so it cannot have returned a wrong fact.
        metrics, outcomes = measure(
            [RESOLVING],
            lambda text: Proposal(
                route="message_facts", arguments=ARGUMENTS | {"message_key": "SAMPLE_INVENTED"}
            ),
        )
        self.assertEqual(metrics.task_coverage, 0.0)
        self.assertEqual(metrics.false_resolution, 0.0)
        self.assertFalse(outcomes[0].accepted)

    def test_an_accepted_wrong_proposal_is_a_false_resolution(self):
        metrics, outcomes = measure(
            [RESOLVING],
            lambda text: Proposal(
                route="signal_mapping",
                arguments=ARGUMENTS | {"signal_key": "SAMPLE_MSG_ENGINE_STATUS"},
            ),
        )
        self.assertEqual(metrics.false_resolution, 1.0)
        self.assertTrue(outcomes[0].accepted)

    def test_a_refusal_carrying_the_registered_status_is_correct(self):
        # Section 8.3, and Section 8.1's FX-110: the adapter proposed two
        # values for one dimension, the deterministic layer refused with
        # invalid_request, and that IS the registered outcome. Correct, never
        # accepted, therefore never a false resolution.
        contradictory = EvaluationCase(
            identifier="EV-110",
            text=f"{TEXT} or SAMPLE_REV_B",
            expected_status="invalid_request",
        )
        metrics, outcomes = measure(
            [contradictory],
            lambda text: Proposal(
                route="message_facts",
                arguments=ARGUMENTS | {"revision_label": ["SAMPLE_REV_A", "SAMPLE_REV_B"]},
            ),
        )
        self.assertEqual(metrics.task_coverage, 1.0)
        self.assertEqual(metrics.false_resolution, 0.0)
        self.assertTrue(outcomes[0].correct)
        self.assertFalse(outcomes[0].accepted)
        self.assertEqual(outcomes[0].refused_as, "invalid_request")

    def test_the_status_has_to_match_not_merely_be_a_refusal(self):
        # The same contradictory proposal against a case that registers
        # `unsupported`: refused, yes -- but not with the registered status,
        # so it is a miss. Any refusal is not the registered outcome.
        wants_unsupported = EvaluationCase(
            identifier="EV-108",
            text=f"{TEXT} or SAMPLE_REV_B",
            expected_status="unsupported",
        )
        metrics, outcomes = measure(
            [wants_unsupported],
            lambda text: Proposal(
                route="message_facts",
                arguments=ARGUMENTS | {"revision_label": ["SAMPLE_REV_A", "SAMPLE_REV_B"]},
            ),
        )
        self.assertEqual(metrics.task_coverage, 0.0)
        self.assertFalse(outcomes[0].correct)
        self.assertEqual(outcomes[0].refused_as, "invalid_request")

    def test_an_accepted_proposal_on_a_no_route_case_is_still_a_false_resolution(self):
        # The extension touches refusals only. A no-route request answered
        # with a valid, verbatim, accepted call still reached the database
        # about something the user did not ask for.
        exporting = EvaluationCase(
            identifier="EV-U",
            text=f"export {TEXT} as tsv",
            expected_status="unsupported",
        )
        metrics, outcomes = measure(
            [exporting], lambda text: Proposal(route="message_facts", arguments=ARGUMENTS)
        )
        self.assertEqual(metrics.false_resolution, 1.0)
        self.assertTrue(outcomes[0].accepted)
        self.assertFalse(outcomes[0].correct)
        self.assertIsNone(outcomes[0].refused_as)

    def test_a_resolving_case_is_scored_by_route_and_arguments_alone(self):
        # Refused with needs_entity_discovery, and the case registers a route:
        # the refusal status plays no part. Wrong arguments, so a miss.
        metrics, outcomes = measure(
            [RESOLVING],
            lambda text: Proposal(route="message_facts", arguments=dict(BASE)),
        )
        self.assertEqual(metrics.task_coverage, 0.0)
        self.assertEqual(outcomes[0].refused_as, "needs_entity_discovery")
        self.assertFalse(outcomes[0].correct)

    def test_the_outcome_records_why_it_counted(self):
        _, outcomes = measure(
            [UNRESOLVABLE], lambda text: Proposal(route="unsupported", arguments={})
        )
        document = outcomes[0].as_json()
        self.assertIn("refused_as", document)
        self.assertEqual(document["refused_as"], "unsupported")

    def test_an_empty_set_reports_zero_rather_than_dividing_by_it(self):
        metrics, _ = measure([], lambda text: Proposal(route="unsupported"))
        self.assertEqual(metrics.task_coverage, 0.0)
        self.assertEqual(metrics.false_resolution, 0.0)

    def test_both_resolvers_run_over_the_same_set(self):
        run = report()
        self.assertEqual(
            [o.identifier for o in run.adapter_outcomes],
            [o.identifier for o in run.baseline_outcomes],
        )

    def test_the_report_records_the_model_and_the_decoding_configuration(self):
        run = report()
        self.assertEqual(run.model, "claude-opus-5")
        self.assertIn("model", run.decoding)
        self.assertIn("started_at", run.as_json())


if __name__ == "__main__":
    unittest.main(verbosity=2)
