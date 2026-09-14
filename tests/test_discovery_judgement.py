"""entity-discovery-v0.1 Section 8.3: what the judge refuses, and why.

Every refusal below is a rule from the Charter or the contract, so each test
names the rule rather than the behaviour. The set judged is the registered
one: a fabricated set could be made to clear anything, and the point of
these assertions is that the registered conditions bite on the registered
cases.
"""

import unittest

from evidence_first_rag import MessageReference, SnapshotScope
from evidence_first_rag.discovery import REGISTERED_SET, CaseOutcome, judge, per_class
from evidence_first_rag.discovery.evaluation import (
    NO_DENOMINATOR,
    REGISTERED_AGAINST_DIGEST,
    REGISTERED_AT,
    THRESHOLDS,
    ClassThresholds,
)

DIGEST = REGISTERED_AGAINST_DIGEST
AFTER = "2026-09-14T00:00:00Z"
BEFORE = "2026-09-13T00:00:00Z"

OTHER = MessageReference(
    scope=SnapshotScope(
        project_code="SAMPLE_PROJECT_ALPHA", revision_label="SAMPLE_REV_A",
        network_name="SAMPLE_NET_POWERTRAIN", snapshot_label="SAMPLE_SNAP_BASE",
    ),
    message_key="SAMPLE_MSG_FILLER",
)


def perfect(cases=REGISTERED_SET, *, ranks=None):
    """Outcomes for a run that does exactly what the registration expects.

    Each registered target lands at its registered rank: rank 1 for a
    `resolved` case, ranks 1..n for a `Q-MULTI` case's references, and
    exactly its `rank_bound` for a `Q-SEMANTIC` case, with fillers above it
    where the bound is not 1. `ranks` overrides one case's target rank.
    """
    ranks = ranks or {}
    outcomes = []
    for case in cases:
        ranked = ()
        resolved = None
        if case.expected_outcome == "resolved":
            resolved = case.expected_references[0]
            ranked = ((resolved, 1),)
        elif case.expected_outcome == "candidates":
            if case.query_class == "Q-SEMANTIC":
                rank = ranks.get(case.identifier, case.rank_bound)
                ranked = tuple((OTHER, position) for position in range(1, rank)) + (
                    (case.expected_references[0], rank),
                )
            else:
                ranked = tuple(
                    (reference, position)
                    for position, reference in enumerate(case.expected_references, start=1)
                )
        outcomes.append(CaseOutcome(
            case=case,
            observed_status=case.expected_outcome,
            ranked=ranked,
            completed=True if case.target_route is not None else None,
            latency_seconds=0.01,
            resolved_reference=resolved,
        ))
    return tuple(outcomes)


def judged(outcomes, **overrides):
    return judge(
        outcomes, per_class(outcomes),
        started_at=overrides.pop("started_at", AFTER),
        observed_digest=overrides.pop("observed_digest", DIGEST),
        **overrides,
    )


class ARunThatDoesWhatTheRegistrationExpects(unittest.TestCase):
    def test_it_is_judged_and_clears_every_condition(self):
        judgement = judged(perfect())
        self.assertEqual(judgement.reasons, ())
        self.assertTrue(judgement.judged)
        self.assertTrue(judgement.adoptable)

    def test_the_judgement_records_what_it_judged_by(self):
        # The artifact says what the run was measured against without anyone
        # opening the contract, as the Milestone 2 artifact does.
        judgement = judged(perfect())
        self.assertEqual(judgement.registered_at, REGISTERED_AT)
        self.assertEqual(judgement.registry_digest, DIGEST)
        self.assertEqual(sorted(judgement.thresholds), sorted(THRESHOLDS))

    def test_the_nested_recall_values_are_the_ones_judged(self):
        # Metrics.as_json nests the three recall values under `recall_at_k`
        # while the registered bars are flat. A judge that reads the flat
        # key off the nested document finds nothing and judges nothing --
        # the first version of this code did exactly that, and passed a run
        # in which no recall bar had been evaluated. A bar that is not
        # evaluated must read as a missing value, not as a cleared one.
        judgement = judged(perfect())
        self.assertNotIn("no value", " ".join(judgement.reasons))
        below = judged(perfect(ranks={"EV-SEMANTIC-2": 3}))
        self.assertIn("Q-SEMANTIC.recall_at_1", " ".join(below.reasons))


class TheThreeRefusalsThatComeBeforeAnyNumber(unittest.TestCase):
    def test_no_registered_thresholds_is_not_a_pass(self):
        judgement = judged(perfect(), thresholds={})
        self.assertFalse(judgement.judged)
        self.assertFalse(judgement.adoptable)
        self.assertIn("Charter Section 9", judgement.reasons[0])

    def test_a_registration_not_before_the_run_is_not_a_pre_registration(self):
        judgement = judged(perfect(), started_at=BEFORE)
        self.assertFalse(judgement.judged)
        self.assertIn("is not before this run", judgement.reasons[0])

    def test_a_run_against_another_registry_is_not_a_run_over_this_set(self):
        judgement = judged(perfect(), observed_digest="0" * 64)
        self.assertFalse(judgement.judged)
        self.assertIn("Section 4.10 rule 8", judgement.reasons[0])

    def test_an_unjudged_run_is_never_adoptable(self):
        for judgement in (
            judged(perfect(), thresholds={}),
            judged(perfect(), started_at=BEFORE),
            judged(perfect(), observed_digest="0" * 64),
            judged(()),
        ):
            with self.subTest(reason=judgement.reasons[0][:40]):
                self.assertFalse(judgement.adoptable)


class TheConditionsSection83Registers(unittest.TestCase):
    def test_a_floor_that_is_missed_is_named(self):
        # A Q-EXACT case that did not resolve: recall and task_completion
        # fall, over_abstention rises.
        outcomes = list(perfect())
        outcomes[0] = CaseOutcome(
            case=outcomes[0].case, observed_status="not_found", ranked=(),
            completed=False, latency_seconds=0.01,
        )
        judgement = judged(tuple(outcomes))
        self.assertTrue(judgement.judged)
        self.assertFalse(judgement.adoptable)
        self.assertIn("Q-EXACT.recall_at_1: 0.8 is below the registered 1.0", judgement.reasons)

    def test_a_ceiling_that_is_exceeded_is_named(self):
        # A Q-MULTI case that resolved is a false resolution however it
        # landed, and Section 8.3 registers zero.
        outcomes = list(perfect())
        multi = next(i for i, o in enumerate(outcomes) if o.case.query_class == "Q-MULTI")
        case = outcomes[multi].case
        outcomes[multi] = CaseOutcome(
            case=case, observed_status="resolved",
            ranked=((case.expected_references[0], 1),),
            completed=False, latency_seconds=0.01,
            resolved_reference=case.expected_references[0],
        )
        judgement = judged(tuple(outcomes))
        self.assertFalse(judgement.adoptable)
        self.assertTrue(any("false_resolution" in reason for reason in judgement.reasons))

    def test_a_number_where_the_registration_says_there_is_none_is_a_defect(self):
        # Section 8.3: "a run that reports a number in such a cell has a
        # defect", so the judge says so rather than ignoring the cell.
        loosened = dict(THRESHOLDS)
        loosened["Q-EXACT"] = ClassThresholds(
            **{
                **{f.name: getattr(THRESHOLDS["Q-EXACT"], f.name)
                   for f in ClassThresholds.__dataclass_fields__.values()},
                "correct_abstention": NO_DENOMINATOR,
                "false_resolution": NO_DENOMINATOR,
            }
        )
        judgement = judged(perfect(), thresholds=loosened)
        self.assertFalse(judgement.adoptable)
        self.assertIn(
            "Q-EXACT.false_resolution: reported 0.0 where Section 8.3 registers no denominator",
            judgement.reasons,
        )

    def test_a_bar_registered_where_the_run_reports_nothing_is_not_cleared(self):
        # The mirror of the test above: there, a number where the
        # registration says there is no denominator; here, no number where
        # the registration sets a bar. Treating a null as a cleared bar
        # would let a class with an empty denominator pass a condition it
        # never evaluated, which is the same defect in the other direction.
        demanding = dict(THRESHOLDS)
        demanding["Q-SCOPE"] = ClassThresholds(
            **{
                **{f.name: getattr(THRESHOLDS["Q-SCOPE"], f.name)
                   for f in ClassThresholds.__dataclass_fields__.values()},
                "recall_at_1": 1.0,
            }
        )
        judgement = judged(perfect(), thresholds=demanding)
        self.assertTrue(judgement.judged)
        self.assertFalse(judgement.adoptable)
        self.assertIn(
            "Q-SCOPE.recall_at_1: no value where Section 8.3 registers 1.0",
            judgement.reasons,
        )

    def test_a_class_the_run_never_reported_is_not_silently_cleared(self):
        outcomes = tuple(o for o in perfect() if o.case.query_class != "Q-NOMATCH")
        judgement = judged(outcomes)
        self.assertIn("Q-NOMATCH: the run reports no metrics for a registered class", judgement.reasons)
        self.assertFalse(judgement.adoptable)


class TheRankBoundConditionTheClassBarCannotExpress(unittest.TestCase):
    def test_the_cancelling_run_clears_the_class_bar_and_fails_the_judgement(self):
        # Section 8.3's own scenario, end to end: EV-SEMANTIC-1's target at
        # rank 2 against a bound of 1, and EV-SEMANTIC-4's at rank 1 against
        # a bound of 2. recall_at_1 is still 0.80 -- the registered bar --
        # and the registration is still not met.
        outcomes = perfect(ranks={"EV-SEMANTIC-1": 2, "EV-SEMANTIC-4": 1})
        classes = per_class(outcomes)
        self.assertEqual(
            classes["Q-SEMANTIC"].recall_at_k["recall_at_1"],
            THRESHOLDS["Q-SEMANTIC"].recall_at_1,
        )
        judgement = judged(outcomes)
        self.assertTrue(judgement.judged)
        self.assertFalse(judgement.adoptable)
        self.assertEqual(
            [reason for reason in judgement.reasons if reason.startswith("rank bound")],
            ["rank bound: EV-SEMANTIC-1: the registered target came back at rank 2,"
             " below the registered bound of 1"],
        )

    def test_a_target_that_never_came_back_fails_its_bound(self):
        outcomes = list(perfect())
        index = next(i for i, o in enumerate(outcomes) if o.case.identifier == "EV-SEMANTIC-3")
        outcomes[index] = CaseOutcome(
            case=outcomes[index].case, observed_status="candidates",
            ranked=((OTHER, 1),), completed=False, latency_seconds=0.01,
        )
        judgement = judged(tuple(outcomes))
        self.assertFalse(judgement.adoptable)
        self.assertTrue(any("did not appear" in reason for reason in judgement.reasons))


if __name__ == "__main__":
    unittest.main(verbosity=2)
