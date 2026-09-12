"""entity-discovery-v0.1 Section 4.11: the metric definitions, on hand-built
outcomes.

Each metric is asserted against the sentence that defines it, and the two
clauses that are easy to implement the obvious wrong way get a test of their
own: `false_resolution` counts a `resolved` returned for a case registered
`candidates` **even when the reference is the registered target**, and a
`Q-MULTI` case counts for recall only when **every** registered reference
appears.
"""

import unittest

from evidence_first_rag import MessageReference, Route, SnapshotScope
from evidence_first_rag.discovery import EvaluationCase
from evidence_first_rag.discovery.metrics import RECALL_KS, CaseOutcome, compute, per_class

SCOPE = SnapshotScope(
    project_code="SAMPLE_PROJECT_ALPHA", revision_label="SAMPLE_REV_A",
    network_name="SAMPLE_NET_POWERTRAIN", snapshot_label="SAMPLE_SNAP_BASE",
)
ARGUMENTS = {**SCOPE.as_parameters(), "entity_kind": "message", "term": "SAMPLE_TERM"}


def reference(key):
    return MessageReference(scope=SCOPE, message_key=key)


A, B, C = reference("SAMPLE_MSG_A"), reference("SAMPLE_MSG_B"), reference("SAMPLE_MSG_C")


def case(identifier="Q-1", query_class="Q-EXACT", references=(A,), outcome=None, route=Route.MESSAGE_FACTS, rank_bound=None):
    from evidence_first_rag.discovery.evaluation import EXPECTED_OUTCOME, NAMES_A_TARGET

    names_target = query_class in NAMES_A_TARGET
    return EvaluationCase(
        identifier=identifier,
        query_class=query_class,
        arguments=ARGUMENTS,
        expected_outcome=outcome or EXPECTED_OUTCOME[query_class][0],
        expected_references=references if names_target else (),
        rank_bound=1 if query_class == "Q-SEMANTIC" else rank_bound,
        target_route=route if names_target else None,
    )


def outcome(registered, status, ranked=(), completed=None, latency=0.0, resolved=None):
    return CaseOutcome(
        case=registered, observed_status=status, ranked=ranked,
        completed=completed, latency_seconds=latency, resolved_reference=resolved,
    )


def resolved(registered, reference_, **kwargs):
    """Section 4.11: "For a case whose registered outcome is `resolved`, the
    observed candidate list is the single resolved reference at rank 1."""
    return outcome(registered, "resolved", ranked=((reference_, 1),), resolved=reference_, **kwargs)


def candidates(registered, *references, **kwargs):
    return outcome(registered, "candidates", ranked=tuple((r, i) for i, r in enumerate(references, 1)), **kwargs)


class RecallAtK(unittest.TestCase):
    def test_the_ks_are_section_4_11s(self):
        self.assertEqual(RECALL_KS, (1, 5, 10))

    def test_it_counts_only_the_cases_that_name_a_target(self):
        # Q-NOMATCH names none, so it is not in the denominator.
        metrics = compute([
            resolved(case("Q-1"), A),
            outcome(case("Q-2", "Q-NOMATCH"), "not_found"),
        ])
        self.assertEqual(metrics.recall_at_k["recall_at_1"], 1.0)
        self.assertEqual(metrics.total, 2)

    def test_a_target_below_k_does_not_count_at_k(self):
        registered = case("Q-1", "Q-SEMANTIC")
        metrics = compute([candidates(registered, B, C, A)])  # A at rank 3
        self.assertEqual(metrics.recall_at_k["recall_at_1"], 0.0)
        self.assertEqual(metrics.recall_at_k["recall_at_5"], 1.0)

    def test_an_absent_target_counts_at_no_k(self):
        metrics = compute([candidates(case("Q-1", "Q-SEMANTIC"), B, C)])
        self.assertEqual(set(metrics.recall_at_k.values()), {0.0})

    def test_q_multi_counts_only_when_every_reference_appears(self):
        # Section 4.11: "A Q-MULTI case counts only when every registered
        # reference appears."
        registered = case("Q-1", "Q-MULTI", references=(A, B))
        self.assertEqual(compute([candidates(registered, A, B)]).recall_at_k["recall_at_5"], 1.0)
        # One of the two present is not a hit.
        self.assertEqual(compute([candidates(registered, A, C)]).recall_at_k["recall_at_5"], 0.0)

    def test_q_multi_is_judged_at_its_worst_ranked_reference(self):
        registered = case("Q-1", "Q-MULTI", references=(A, B))
        metrics = compute([candidates(registered, A, C, B)])  # A at 1, B at 3
        self.assertEqual(metrics.recall_at_k["recall_at_1"], 0.0)
        self.assertEqual(metrics.recall_at_k["recall_at_5"], 1.0)

    def test_with_no_targeted_case_there_is_no_rate(self):
        # None rather than 0.0: a class with no case of that kind has no
        # rate, and a zero would read as a failing score.
        metrics = compute([outcome(case("Q-1", "Q-NOMATCH"), "not_found")])
        self.assertIsNone(metrics.recall_at_k["recall_at_1"])
        self.assertIsNone(metrics.mrr)


class Mrr(unittest.TestCase):
    def test_it_is_the_mean_reciprocal_rank(self):
        metrics = compute([
            resolved(case("Q-1"), A),
            candidates(case("Q-2", "Q-SEMANTIC"), B, A),
        ])
        self.assertAlmostEqual(metrics.mrr, (1.0 + 0.5) / 2)

    def test_an_absent_target_contributes_zero(self):
        metrics = compute([candidates(case("Q-1", "Q-SEMANTIC"), B)])
        self.assertEqual(metrics.mrr, 0.0)

    def test_q_multi_uses_its_worst_ranked_reference(self):
        registered = case("Q-1", "Q-MULTI", references=(A, B))
        self.assertAlmostEqual(compute([candidates(registered, A, B)]).mrr, 0.5)


class FalseResolution(unittest.TestCase):
    """Section 4.11: "the fraction that returned `resolved` with a reference
    other than the one registered, or returned `resolved` at all where the
    registered outcome is not `resolved`.\""""

    def test_a_resolution_on_the_wrong_reference_counts(self):
        metrics = compute([resolved(case("Q-1"), B)])
        self.assertEqual(metrics.false_resolution, 1.0)

    def test_a_resolution_on_the_registered_reference_does_not(self):
        self.assertEqual(compute([resolved(case("Q-1"), A)]).false_resolution, 0.0)

    def test_a_resolution_on_a_candidates_case_counts_even_on_the_target(self):
        # The clause the metric exists for: "a `resolved` returned for a case
        # registered as `candidates` counts here even when the reference is
        # the registered target ... a method that resolves where the rule says
        # abstain is the defect this metric exists to count."
        registered = case("Q-1", "Q-MULTI", references=(A, B))
        self.assertEqual(compute([resolved(registered, A)]).false_resolution, 1.0)

    def test_abstaining_never_counts(self):
        metrics = compute([
            candidates(case("Q-1", "Q-MULTI", references=(A, B)), A, B),
            outcome(case("Q-2", "Q-NOMATCH"), "not_found"),
            outcome(case("Q-3", "Q-OUT", outcome="unsupported"), "unsupported"),
        ])
        self.assertEqual(metrics.false_resolution, 0.0)

    def test_it_is_computed_over_every_case(self):
        metrics = compute([resolved(case("Q-1"), B), outcome(case("Q-2", "Q-NOMATCH"), "not_found")])
        self.assertEqual(metrics.false_resolution, 0.5)


class Abstention(unittest.TestCase):
    def test_correct_abstention_is_over_the_cases_registered_not_resolved(self):
        metrics = compute([
            outcome(case("Q-1", "Q-NOMATCH"), "not_found"),
            resolved(case("Q-2", "Q-MULTI", references=(A, B)), A),
            resolved(case("Q-3"), A),  # registered resolved: not in this denominator
        ])
        self.assertEqual(metrics.correct_abstention, 0.5)

    def test_over_abstention_is_its_mirror(self):
        # "a method that abstains on everything scores perfectly on that one,
        # and this is the number that says so."
        registered = [case(f"Q-{i}") for i in range(4)]
        metrics = compute([outcome(r, "not_found") for r in registered])
        self.assertEqual(metrics.correct_abstention, None)
        self.assertEqual(metrics.over_abstention, 1.0)

    def test_a_perfect_resolver_over_abstains_on_nothing(self):
        self.assertEqual(compute([resolved(case("Q-1"), A)]).over_abstention, 0.0)


class TaskCompletion(unittest.TestCase):
    def test_it_is_over_the_cases_naming_a_target_and_a_route(self):
        metrics = compute([
            resolved(case("Q-1"), A, completed=True),
            candidates(case("Q-2", "Q-MULTI", references=(A,)), A, completed=False),
            outcome(case("Q-3", "Q-NOMATCH"), "not_found"),
        ])
        self.assertEqual(metrics.task_completion, 0.5)

    def test_an_unreached_route_is_not_a_completion(self):
        self.assertEqual(compute([outcome(case("Q-1"), "not_found", completed=False)]).task_completion, 0.0)

    def test_with_no_routed_case_there_is_no_rate(self):
        self.assertIsNone(compute([outcome(case("Q-1", "Q-NOMATCH"), "not_found")]).task_completion)

    def test_a_case_naming_a_target_but_no_route_leaves_the_denominator(self):
        # Section 4.11 names two conditions, not one: the case must name a
        # target *and* a registered route. A target named without a route is
        # in recall's denominator and out of this one.
        metrics = compute([
            resolved(case("Q-1"), A, completed=True),
            resolved(case("Q-2", references=(B,), route=None), B, completed=None),
        ])
        self.assertEqual(metrics.task_completion, 1.0)
        self.assertEqual(metrics.recall_at_k["recall_at_1"], 1.0)


class Latency(unittest.TestCase):
    def test_the_median_and_the_95th_percentile_are_reported(self):
        metrics = compute([outcome(case(f"Q-{i}"), "resolved", resolved=A, latency=float(i)) for i in range(20)])
        self.assertEqual(metrics.latency_median_seconds, 9.5)
        # Nearest-rank: ceil(0.95 * 20) - 1 = 18.
        self.assertEqual(metrics.latency_p95_seconds, 18.0)

    def test_the_percentile_is_a_measurement_that_was_taken(self):
        for n in (1, 3, 4, 7, 30):
            with self.subTest(n=n):
                latencies = [float(i) for i in range(n)]
                metrics = compute([outcome(case(f"Q-{i}"), "not_found", latency=value) for i, value in enumerate(latencies)])
                self.assertIn(metrics.latency_p95_seconds, latencies)

    def test_it_never_reaches_a_result_payload(self):
        # Section 4.11: "Recorded, never returned." The metric is on the run
        # artifact; nothing here is part of a DiscoveryResult, and
        # tests/test_discovery_evidence.py pins the bundle's fields.
        from evidence_first_rag.discovery import DiscoveryEvidence

        self.assertNotIn("latency", {f for f in DiscoveryEvidence.__dataclass_fields__})


class PerClass(unittest.TestCase):
    def test_each_class_present_gets_its_own_numbers(self):
        outcomes = [
            resolved(case("Q-1", "Q-EXACT"), A),
            resolved(case("Q-2", "Q-ALIAS"), B),  # wrong reference
            outcome(case("Q-3", "Q-NOMATCH"), "not_found"),
        ]
        by_class = per_class(outcomes)
        self.assertEqual(set(by_class), {"Q-EXACT", "Q-ALIAS", "Q-NOMATCH"})
        self.assertEqual(by_class["Q-EXACT"].false_resolution, 0.0)
        self.assertEqual(by_class["Q-ALIAS"].false_resolution, 1.0)

    def test_an_absent_class_has_no_row_rather_than_a_zero(self):
        by_class = per_class([outcome(case("Q-1", "Q-NOMATCH"), "not_found")])
        self.assertNotIn("Q-SEMANTIC", by_class)

    def test_the_classes_come_out_in_the_contracts_order(self):
        outcomes = [outcome(case("Q-1", "Q-NOMATCH"), "not_found"), resolved(case("Q-2", "Q-EXACT"), A)]
        self.assertEqual(list(per_class(outcomes)), ["Q-EXACT", "Q-NOMATCH"])


class TheJsonShape(unittest.TestCase):
    def test_it_carries_every_section_4_11_quantity(self):
        document = compute([resolved(case("Q-1"), A, completed=True, latency=0.5)]).as_json()
        self.assertEqual(
            set(document),
            {"total", "recall_at_k", "mrr", "false_resolution", "correct_abstention",
             "over_abstention", "task_completion", "latency"},
        )
        self.assertEqual(set(document["latency"]), {"median_seconds", "p95_seconds"})
        self.assertEqual(set(document["recall_at_k"]), {"recall_at_1", "recall_at_5", "recall_at_10"})

    def test_the_recall_mapping_cannot_be_edited_through_the_metrics(self):
        metrics = compute([resolved(case("Q-1"), A)])
        with self.assertRaises(TypeError):
            metrics.recall_at_k["recall_at_1"] = 0.0


if __name__ == "__main__":
    unittest.main(verbosity=2)
