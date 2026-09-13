"""entity-discovery-v0.1 Sections 4.10 and 8.3: the registered case's shape,
the authoring rules a program can check, and the registration they govern.

Section 4.10's half asserts the type and the rules against sets built here
to break one rule each. Section 8.3's half asserts the registration: that
the constants equal the contract text, and that the bars the section calls
derived are recomputed from the registered cases rather than copied from
the document -- `mvp-v0.1` Section 8.3 is pinned to `adapter/evaluation.py`
the same way, because a number nobody compares against the document is a
number nobody checks.
"""

import pathlib
import re
import unittest

from evidence_first_rag import MessageReference, Route, SignalReference, SnapshotScope
from evidence_first_rag.discovery import REGISTERED_SET, EvaluationCase, authoring_failures
from evidence_first_rag.discovery import K
from evidence_first_rag.discovery.normalize import normalize
from evidence_first_rag.discovery.evaluation import (
    CEILINGS,
    CLASSES,
    EXPECTED_OUTCOME,
    MINIMUM_PER_CLASS,
    NAMES_A_TARGET,
    NO_DENOMINATOR,
    REGISTERED_AGAINST_DIGEST,
    REGISTERED_AT,
    REGISTRATION_CONTRACT_VERSION,
    REPORTED,
    TERM_IS_AN_IDENTIFIER,
    THRESHOLDS,
    multi_recall_ceilings,
    semantic_recall_bars,
)
from evidence_first_rag.discovery.evidence import CONTRACT_VERSION

CONTRACT = pathlib.Path(__file__).resolve().parents[1] / "docs" / "contracts" / "entity-discovery-v0.1.md"


def section_8_3() -> str:
    text = CONTRACT.read_text()
    start = text.index("### 8.3 ")
    return text[start:text.index("## 9. Deferred decisions", start)]

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
        cases[0] = case("Q-EXACT-0", "Q-EXACT", arguments=SCOPE | {"entity_kind": "message", "term": "SAMPLE_MSG_X", "parent_message_key": "MSG_REAL_NAME"})
        failures = authoring_failures(cases)
        self.assertTrue(any("rule 1" in failure for failure in failures), failures)

    def test_rule_1_governs_the_term_where_the_class_makes_it_an_identifier(self):
        # Section 4.10's table fixes the term of these four as a name: a
        # lookup key byte for byte (Q-EXACT), a registered alias byte for
        # byte (Q-ALIAS), "a fully scoped request for a key" (Q-COLLIDE),
        # and a name the fixtures reserve as absent (Q-NOMATCH). A
        # real-world name in that position is what rule 1 forbids.
        for name in TERM_IS_AN_IDENTIFIER:
            with self.subTest(query_class=name):
                cases = self.full_set()
                index = next(i for i, registered in enumerate(cases) if registered.query_class == name)
                cases[index] = case(f"{name}-0", name, term="EngineStatus_HS")
                failures = authoring_failures(cases)
                self.assertTrue(
                    any("rule 1" in failure and "term=" in failure for failure in failures),
                    failures,
                )

    def test_rule_1_exempts_the_term_where_the_class_makes_it_free_text(self):
        # A Q-SEMANTIC term "describes the entity without equalling any
        # match_text", so it could not satisfy SAMPLE_* and rule 1 does not
        # ask it to. The same holds for Q-OUT and Q-SCOPE, whose registered
        # request never reaches a key.
        for name, term in (
            ("Q-SEMANTIC", "the engine speed signal"),
            ("Q-SCOPE", "the gearbox state message"),
            ("Q-OUT", "the colour of the wiring harness"),
        ):
            with self.subTest(query_class=name):
                cases = self.full_set()
                index = next(i for i, registered in enumerate(cases) if registered.query_class == name)
                cases[index] = case(f"{name}-0", name, term=term)
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
        cases[1] = case("Q-EXACT-1", "Q-EXACT", term="SAMPLE_TERM.Q-EXACT.0")
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


class TheRegisteredSet(unittest.TestCase):
    """Section 8.3, registered. The constants and the section text are one
    registration written twice, and these assertions are what keeps them one:
    `mvp-v0.1` Section 8.3 is pinned to `adapter/evaluation.py` the same way,
    for the same reason -- a number nobody compares against the document is a
    number nobody checks."""

    def test_forty_cases_are_registered_five_in_each_class(self):
        self.assertEqual(len(REGISTERED_SET), 40)
        for name in CLASSES:
            with self.subTest(query_class=name):
                members = [c for c in REGISTERED_SET if c.query_class == name]
                self.assertEqual(len(members), 5)

    def test_the_registered_set_breaks_no_authoring_rule(self):
        self.assertEqual(authoring_failures(REGISTERED_SET), [])

    def test_every_identifier_is_registered_once(self):
        identifiers = [case.identifier for case in REGISTERED_SET]
        self.assertEqual(len(set(identifiers)), len(identifiers))

    def test_the_registration_record_equals_section_8_3(self):
        section = section_8_3()
        registered_at = re.search(r"`registered_at`: `([^`]+)`", section)
        version = re.search(r"`contract_version`: `([^`]+)`", section)
        digest = re.search(r"`registry_digest`: `([0-9a-f]{64})`", section)
        for match in (registered_at, version, digest):
            self.assertIsNotNone(match, "Section 8.3 has changed shape")
        self.assertEqual(REGISTERED_AT, registered_at.group(1))
        self.assertEqual(REGISTRATION_CONTRACT_VERSION, version.group(1))
        self.assertEqual(REGISTERED_AGAINST_DIGEST, digest.group(1))
        # The registration landed at this version and the document is still
        # there: unlike mvp-v0.1's thresholds, which record a past version,
        # nothing has moved past this one yet.
        self.assertEqual(REGISTRATION_CONTRACT_VERSION, CONTRACT_VERSION)

    def test_the_section_8_3_heading_carries_the_registered_instant(self):
        self.assertIn(f"registered {REGISTERED_AT}", section_8_3().splitlines()[0])

    def test_every_threshold_equals_the_section_8_3_table(self):
        # One row of the table per quantity, one column per class, read back
        # out of the document and compared with the constant.
        rows = {}
        columns = None
        for line in section_8_3().splitlines():
            cells = [c.strip().strip("`") for c in line.strip().strip("|").split("|")]
            if len(cells) != 9:
                continue
            if cells[0] == "Quantity":
                # The column order is the document's, not CLASSES's. Reading
                # it rather than assuming it is the difference between this
                # test checking the table and checking a coincidence.
                columns = cells[1:]
            elif cells[0] in (
                "false_resolution", "correct_abstention", "over_abstention",
                "recall_at_1", "recall_at_5", "recall_at_10", "task_completion", "mrr",
            ):
                rows[cells[0]] = cells[1:]
        self.assertEqual(len(rows), 8, "Section 8.3's threshold table has changed shape")
        self.assertEqual(sorted(columns or []), sorted(CLASSES), "the table names other classes")
        for quantity, cells in rows.items():
            for name, cell in zip(columns, cells):
                with self.subTest(quantity=quantity, query_class=name):
                    registered = getattr(THRESHOLDS[name], quantity)
                    if cell == "—":
                        self.assertIs(registered, NO_DENOMINATOR)
                    elif cell == "reported":
                        self.assertIs(registered, REPORTED)
                    else:
                        number = float(re.sub(r"[^0-9.]", "", cell))
                        self.assertEqual(registered, number)
                        self.assertEqual(cell.startswith("≤"), quantity in CEILINGS)

    def test_the_semantic_recall_bars_are_derived_from_the_registered_bounds(self):
        # Not copied. Section 8.3 derives the class bar from the rank bounds
        # rule 3 makes each case register, so editing a bound without editing
        # the bar -- or the reverse -- fails here.
        bars = semantic_recall_bars(REGISTERED_SET)
        for k, expected in bars.items():
            with self.subTest(k=k):
                self.assertEqual(getattr(THRESHOLDS["Q-SEMANTIC"], f"recall_at_{k}"), expected)

    def test_the_multi_recall_bars_are_the_ceilings_the_registered_lists_entail(self):
        # Section 4.11 counts a Q-MULTI case only when every registered
        # reference appears, so a case registering n references cannot count
        # for k < n. The bars are those ceilings; recall_at_1's ceiling is
        # zero, which is why it is `reported` rather than a bar.
        ceilings = multi_recall_ceilings(REGISTERED_SET)
        self.assertEqual(ceilings[1], 0.0)
        self.assertIs(THRESHOLDS["Q-MULTI"].recall_at_1, REPORTED)
        for k in (5, 10):
            with self.subTest(k=k):
                self.assertEqual(getattr(THRESHOLDS["Q-MULTI"], f"recall_at_{k}"), ceilings[k])

    def test_no_registered_candidate_list_exceeds_k(self):
        # Section 8.3 states it, and a list beyond k would make a recall bar
        # unreachable for a reason the section does not record.
        for case in REGISTERED_SET:
            with self.subTest(case=case.identifier):
                self.assertLessEqual(len(case.expected_references), K)

    def test_the_set_holds_no_difficult_semantic_case(self):
        # Section 8.3 registers the definition and records that the count is
        # zero, so that a vector registration cannot choose it afterwards.
        # A term sharing no token with any match text of its target cannot be
        # reached at tier 4, which is the whole of what the baseline does.
        self.assertIn("holds zero of them", section_8_3())
        for case in REGISTERED_SET:
            if case.query_class != "Q-SEMANTIC":
                continue
            target = case.expected_references[0]
            key = getattr(target, "signal_key", None) or target.message_key
            with self.subTest(case=case.identifier):
                self.assertTrue(set(normalize(case.term)) & set(normalize(key)))

    def test_the_registration_precedes_any_run_it_could_judge(self):
        # Charter Section 9. The artifact a run writes is not committed, and
        # the runner still refuses to open a database, so there is nothing to
        # compare against yet; what is asserted here is that the recorded
        # instant is a well-formed UTC instant the runner can compare with.
        self.assertRegex(REGISTERED_AT, r"\A\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z")


if __name__ == "__main__":
    unittest.main(verbosity=2)
