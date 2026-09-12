"""entity-discovery-v0.1 Section 4.10: the registered case's shape, and the
authoring rules a program can check.

No case is registered -- Section 8.3 is reserved, and the registration is a
recorded human decision Charter Section 9 requires before the run it judges.
What these tests hold is the type a registration will be written in and the
assertions Section 4.10 says "each becomes an assertion in the slice that
registers the set", so the registration slice inherits them rather than
writing them beside the numbers they govern.
"""

import unittest

from evidence_first_rag import MessageReference, Route, SignalReference, SnapshotScope
from evidence_first_rag.discovery import REGISTERED_SET, EvaluationCase, authoring_failures
from evidence_first_rag.discovery.evaluation import (
    CLASSES,
    EXPECTED_OUTCOME,
    MINIMUM_PER_CLASS,
    NAMES_A_TARGET,
)

SCOPE = {
    "project_code": "SAMPLE_PROJECT_ALPHA",
    "revision_label": "SAMPLE_REV_A",
    "network_name": "SAMPLE_NET_POWERTRAIN",
    "snapshot_label": "SAMPLE_SNAP_BASE",
}
REFERENCE = MessageReference(scope=SnapshotScope(**SCOPE), message_key="SAMPLE_MSG_ENGINE_STATUS")
OTHER = MessageReference(scope=SnapshotScope(**SCOPE), message_key="SAMPLE_MSG_TRANSMISSION_STATE")
SIGNAL = SignalReference(message=REFERENCE, signal_key="SAMPLE_SIG_ENGINE_SPEED")


def case(identifier="Q-1", query_class="Q-EXACT", term="SAMPLE_MSG_ENGINE_STATUS", **overrides):
    values = {
        "identifier": identifier,
        "query_class": query_class,
        "arguments": SCOPE | {"entity_kind": "message", "term": term},
        "expected_outcome": EXPECTED_OUTCOME[query_class][0],
    }
    if query_class in NAMES_A_TARGET:
        values["expected_references"] = (REFERENCE,)
        values["target_route"] = Route.MESSAGE_FACTS
    if query_class == "Q-SEMANTIC":
        values["rank_bound"] = 1
    values.update(overrides)
    return EvaluationCase(**values)


class TheEightClasses(unittest.TestCase):
    def test_they_are_charter_section_8s_eight_bullets(self):
        self.assertEqual(
            CLASSES,
            ("Q-EXACT", "Q-ALIAS", "Q-SEMANTIC", "Q-SCOPE", "Q-COLLIDE", "Q-MULTI", "Q-NOMATCH", "Q-OUT"),
        )

    def test_each_registers_the_outcome_section_4_10_names(self):
        self.assertEqual(
            {name: EXPECTED_OUTCOME[name] for name in CLASSES},
            {
                "Q-EXACT": ("resolved",),
                "Q-ALIAS": ("resolved",),
                "Q-SEMANTIC": ("candidates",),
                "Q-SCOPE": ("ambiguous",),
                "Q-COLLIDE": ("resolved",),
                "Q-MULTI": ("candidates",),
                "Q-NOMATCH": ("not_found",),
                "Q-OUT": ("unsupported", "coverage_gap"),
            },
        )

    def test_the_classes_that_name_a_target_are_section_4_11s(self):
        # recall_at_k and mrr are computed "over the cases whose registration
        # names a target reference".
        self.assertEqual(NAMES_A_TARGET, {"Q-EXACT", "Q-ALIAS", "Q-SEMANTIC", "Q-COLLIDE", "Q-MULTI"})

    def test_an_unknown_class_has_no_representation(self):
        with self.assertRaises(ValueError):
            EvaluationCase(
                identifier="Q-1",
                query_class="Q-GUESS",
                arguments=SCOPE | {"entity_kind": "message", "term": "x"},
                expected_outcome="resolved",
            )

    def test_a_class_cannot_register_another_classs_outcome(self):
        with self.assertRaises(ValueError):
            case(query_class="Q-EXACT", expected_outcome="candidates")
        # Q-OUT is the one class with two, and both are accepted.
        case("Q-o1", "Q-OUT", expected_outcome="unsupported")
        case("Q-o2", "Q-OUT", expected_outcome="coverage_gap")


class TheRegistration(unittest.TestCase):
    """Section 4.10 rule 2, as far as the type can hold it."""

    def test_a_target_class_registers_a_reference_and_others_do_not(self):
        for name in NAMES_A_TARGET:
            with self.subTest(query_class=name), self.assertRaises(ValueError):
                case(query_class=name, expected_references=())
        for name in set(CLASSES) - NAMES_A_TARGET:
            with self.subTest(query_class=name), self.assertRaises(ValueError):
                case(query_class=name, expected_references=(REFERENCE,))

    def test_only_q_multi_registers_more_than_one_reference(self):
        case("Q-m", "Q-MULTI", expected_references=(REFERENCE, OTHER))
        with self.assertRaises(ValueError):
            case(query_class="Q-EXACT", expected_references=(REFERENCE, OTHER))

    def test_only_q_semantic_registers_a_rank_bound_and_it_must(self):
        # Rule 3: "'the target is somewhere in ten candidates' and 'the
        # target is first' are different claims."
        with self.assertRaises(ValueError):
            case(query_class="Q-SEMANTIC", rank_bound=None)
        with self.assertRaises(ValueError):
            case(query_class="Q-EXACT", rank_bound=1)

    def test_a_rank_bound_is_within_the_list_length(self):
        for bound in (0, 11, True):
            with self.subTest(bound=bound), self.assertRaises(ValueError):
                case(query_class="Q-SEMANTIC", rank_bound=bound)

    def test_a_case_with_no_target_names_no_route(self):
        with self.assertRaises(ValueError):
            case(query_class="Q-NOMATCH", target_route=Route.MESSAGE_FACTS)

    def test_a_reference_is_a_canonical_reference(self):
        with self.assertRaises(ValueError):
            case(expected_references=("SAMPLE_MSG_ENGINE_STATUS",))

    def test_a_signal_reference_carries_its_parent(self):
        # Rule 2: "including the parent Message for a signal." The reference
        # type enforces it; this is the case that shows it reaches here.
        registered = case(expected_references=(SIGNAL,))
        self.assertEqual(registered.expected_references[0].message_key, "SAMPLE_MSG_ENGINE_STATUS")

    def test_the_arguments_are_copied_not_shared(self):
        arguments = SCOPE | {"entity_kind": "message", "term": "x"}
        registered = case(arguments=arguments)
        arguments["term"] = "y"
        self.assertEqual(registered.term, "x")


class TheAuthoringRules(unittest.TestCase):
    """Section 4.10's rules, each shown to fail on a set that breaks it."""

    def full_set(self):
        """Five cases per class: the minimum rule 4 requires, with distinct
        normalized texts."""
        cases = []
        for name in CLASSES:
            for index in range(MINIMUM_PER_CLASS):
                cases.append(case(f"{name}-{index}", name, term=f"SAMPLE_TERM_{name}_{index}"))
        return cases

    def test_a_conforming_set_reports_nothing(self):
        self.assertEqual(authoring_failures(self.full_set()), [])

    def test_rule_1_every_identifier_is_sample(self):
        cases = self.full_set()
        cases[0] = case("Q-EXACT-0", "Q-EXACT", arguments=SCOPE | {"entity_kind": "message", "term": "x", "parent_message_key": "MSG_REAL_NAME"})
        failures = authoring_failures(cases)
        self.assertTrue(any("rule 1" in failure for failure in failures), failures)

    def test_rule_1_exempts_the_term_which_is_free_text(self):
        # The term is the user's words, not an identifier; a Q-SEMANTIC case
        # is a description and could not satisfy SAMPLE_*.
        cases = self.full_set()
        cases[10] = case("Q-SEMANTIC-0", "Q-SEMANTIC", term="the engine speed signal")
        self.assertEqual(authoring_failures(cases), [])

    def test_rule_4_at_least_five_per_class(self):
        cases = [c for c in self.full_set() if c.identifier != "Q-MULTI-0"]
        failures = authoring_failures(cases)
        self.assertTrue(any("Q-MULTI" in f and "rule 4" in f for f in failures), failures)

    def test_rule_4_names_every_short_class(self):
        failures = authoring_failures([case("Q-EXACT-0", "Q-EXACT")])
        self.assertEqual(sum(1 for f in failures if "rule 4" in f), len(CLASSES))

    def test_rule_6_no_two_texts_are_equal_after_normalization(self):
        cases = self.full_set()
        # Different bytes, same tokens: exactly what rule 6 forbids.
        cases[1] = case("Q-EXACT-1", "Q-EXACT", term="sample-term-Q-EXACT-0")
        failures = authoring_failures(cases)
        self.assertTrue(any("rule 6" in f for f in failures), failures)

    def test_a_duplicate_identifier_is_reported(self):
        cases = self.full_set()
        cases[1] = case("Q-EXACT-0", "Q-EXACT", term="SAMPLE_OTHER_TEXT")
        failures = authoring_failures(cases)
        self.assertTrue(any("registered twice" in f for f in failures), failures)

    def test_a_term_with_no_token_is_reported_except_where_the_class_has_none(self):
        cases = self.full_set()
        cases[0] = case("Q-EXACT-0", "Q-EXACT", term="___")
        self.assertTrue(any("no token" in f for f in authoring_failures(cases)), "Q-EXACT")
        # Q-OUT and Q-SCOPE may register a request the runtime refuses before
        # it ever normalizes a term.
        cases = self.full_set()
        cases[-1] = case(f"Q-OUT-{MINIMUM_PER_CLASS - 1}", "Q-OUT", term="___")
        self.assertEqual(authoring_failures(cases), [])


class TheReservedRegistration(unittest.TestCase):
    def test_no_set_is_registered(self):
        # Section 8.3 is reserved. The registration slice replaces this, and
        # the runner refuses to run over nothing until it does.
        self.assertEqual(REGISTERED_SET, ())


if __name__ == "__main__":
    unittest.main(verbosity=2)
