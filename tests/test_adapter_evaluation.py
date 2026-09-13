"""Section 8.3, rule by rule, against the registered set.

The contract registers a composition, seven authoring rules, two numbers and
an instant. `adapter/evaluation.py` claims to mirror them. Each test here is
one of those claims checked against the document, the fixtures, or the
harness -- so that a set which violates a rule does not merge, and so that
the baseline's floor is a measurement rather than a figure someone counted.
"""

import json
import pathlib
import re
import unittest
from collections import Counter

from evidence_first_rag import CONTRACT_VERSION
from evidence_first_rag.adapter import Baseline, Proposal, measure
from evidence_first_rag.adapter.baseline import normalize
from evidence_first_rag.adapter.evaluation import (
    CURATED,
    EVALUATION_SET,
    STRUCTURAL_REGISTRATIONS,
    THRESHOLDS,
    family,
)
from evidence_first_rag.adapter.revalidation import _is_verbatim_token
from evidence_first_rag.conformance.cases import REGISTERED
from evidence_first_rag.references import SCOPE_DIMENSIONS
from evidence_first_rag.runtime.request import required_lookup_keys
from evidence_first_rag.routes import Route

from .support import FIXTURES, SAMPLE, loaded_identifiers

REPOSITORY = pathlib.Path(__file__).resolve().parent.parent
CONTRACT = REPOSITORY / "docs" / "contracts" / "mvp-v0.1.md"
EXPECTED = REPOSITORY / "src" / "evidence_first_rag" / "conformance" / "expected"

# fixtures/README.md reserves these three as absent; validate_fixtures.py
# asserts the fixtures never grow one. They are legitimate in a request.
RESERVED_ABSENT = {"SAMPLE_NET_BODY", "SAMPLE_MSG_ABSENT", "SAMPLE_SIG_ABSENT"}


def _rows(name):
    return [json.loads(line) for line in (FIXTURES / name).read_text().splitlines() if line.strip()]


LOADED_IDENTIFIERS = loaded_identifiers()
LOADED_SCOPES = [
    {dimension: row[dimension] for dimension in SCOPE_DIMENSIONS}
    for row in _rows("source_snapshot.jsonl")
]
LOADED_LOOKUP_KEYS = {row["message_key"] for row in _rows("message_occurrence.jsonl")} | {
    row["signal_key"] for row in _rows("signal_occurrence.jsonl")
}


def tokens(text):
    return set(SAMPLE.findall(text))


def loaded_values_present(text, dimension):
    return {scope[dimension] for scope in LOADED_SCOPES if _is_verbatim_token(scope[dimension], text)}


def by_family():
    groups = {}
    for case in EVALUATION_SET:
        groups.setdefault(family(case), []).append(case)
    return groups


class TheComposition(unittest.TestCase):
    def test_the_four_families_have_the_registered_counts(self):
        counts = Counter(family(case) for case in EVALUATION_SET)
        self.assertEqual(counts, Counter({"P": 33, "D": 4, "X": 5, "U": 6}))
        self.assertEqual(len(EVALUATION_SET), 48)

    def test_p_is_the_eleven_structural_cases_in_three_phrasings(self):
        structural = [case for case in REGISTERED if not case.is_a_proposal]
        self.assertEqual(len(structural), 11)
        for registered in structural:
            phrasings = [c for c in EVALUATION_SET if c.identifier.startswith(f"EV-P-{registered.identifier}-")]
            self.assertEqual(len(phrasings), 3, registered.identifier)
            expected = json.loads((EXPECTED / f"{registered.identifier}.json").read_text())
            for case in phrasings:
                self.assertEqual(case.expected_route, registered.route)
                self.assertEqual(dict(case.expected_arguments), dict(registered.arguments))
                # The registered expected document is the authority on the
                # status; a P case that said `success` for FX-105 could never
                # be observed as weakened.
                self.assertEqual(case.expected_status, expected["status"], registered.identifier)

    def test_the_inlined_registrations_equal_section_8_1s(self):
        # The module writes the eleven registrations out rather than importing
        # the conformance package; this is what stops them drifting.
        for registered in REGISTERED:
            if registered.is_a_proposal:
                continue
            route, arguments = STRUCTURAL_REGISTRATIONS[registered.identifier]
            self.assertEqual(route, registered.route)
            self.assertEqual(dict(arguments), dict(registered.arguments))

    def test_d_registers_a_route_with_scope_only_arguments(self):
        for case in by_family()["D"]:
            self.assertEqual(case.expected_status, "needs_entity_discovery")
            self.assertIn(case.expected_route, {route.value for route in Route})
            self.assertEqual(set(case.expected_arguments), set(SCOPE_DIMENSIONS))

    def test_x_and_u_register_no_route(self):
        for case in by_family()["X"]:
            self.assertIsNone(case.expected_route)
            self.assertEqual(case.expected_status, "invalid_request")
        for case in by_family()["U"]:
            self.assertIsNone(case.expected_route)
            self.assertEqual(case.expected_status, "unsupported")


class TheAuthoringRules(unittest.TestCase):
    def test_rule_1_every_identifier_is_loaded_or_reserved_absent(self):
        allowed = LOADED_IDENTIFIERS | RESERVED_ABSENT
        for case in EVALUATION_SET:
            with self.subTest(case=case.identifier):
                self.assertTrue(tokens(case.text) <= allowed, tokens(case.text) - allowed)
                self.assertTrue(all(t.startswith("SAMPLE_") for t in tokens(case.text)))

    def test_rule_2_every_registered_argument_value_is_a_verbatim_token(self):
        # The same predicate the adapter is judged by. A registration whose
        # value is not a token of its own text could never be accepted.
        for case in EVALUATION_SET:
            for name, value in case.expected_arguments.items():
                with self.subTest(case=case.identifier, argument=name):
                    self.assertTrue(_is_verbatim_token(value, case.text), value)

    def test_rule_3_every_negative_case_carries_a_complete_loaded_scope(self):
        groups = by_family()
        for case in groups["D"] + groups["X"] + groups["U"]:
            with self.subTest(case=case.identifier):
                complete = any(
                    all(_is_verbatim_token(scope[d], case.text) for d in SCOPE_DIMENSIONS)
                    for scope in LOADED_SCOPES
                )
                self.assertTrue(complete, case.text)

    def test_x_doubles_exactly_one_dimension_with_loaded_values(self):
        for case in by_family()["X"]:
            with self.subTest(case=case.identifier):
                doubled = [d for d in SCOPE_DIMENSIONS if len(loaded_values_present(case.text, d)) == 2]
                single = [d for d in SCOPE_DIMENSIONS if len(loaded_values_present(case.text, d)) == 1]
                self.assertEqual(len(doubled), 1, case.text)
                self.assertEqual(len(single), 3, case.text)

    def test_d_omits_every_lookup_key_its_route_requires(self):
        for case in by_family()["D"]:
            with self.subTest(case=case.identifier):
                self.assertTrue(required_lookup_keys(Route(case.expected_route)))
                self.assertEqual(tokens(case.text) & LOADED_LOOKUP_KEYS, set(), case.text)
                self.assertEqual(tokens(case.text) & RESERVED_ABSENT, set(), case.text)

    def test_rule_4_no_two_texts_are_equal_after_normalization(self):
        normalized = [normalize(case.text) for case in EVALUATION_SET]
        self.assertEqual(len(set(normalized)), len(normalized))

    def test_rule_5_the_curated_table_is_exactly_the_eleven_canonical_phrasings(self):
        canonical = {c.text for c in EVALUATION_SET if family(c) == "P" and c.identifier.endswith("-0")}
        self.assertEqual(len(canonical), 11)
        self.assertEqual({entry.text for entry in CURATED}, canonical)
        by_text = {c.text: c for c in EVALUATION_SET}
        for entry in CURATED:
            case = by_text[entry.text]
            self.assertEqual(entry.route, case.expected_route)
            self.assertEqual(dict(entry.arguments), dict(case.expected_arguments))

    def test_canonical_phrasings_differ_where_registrations_share_arguments(self):
        # FX-002 and FX-003 carry identical arguments. Baseline refuses a table
        # with two entries normalizing alike, so the phrasing has to carry
        # the route; this asserts it for every such pair, not only that one.
        entries = list(CURATED)
        for i, left in enumerate(entries):
            for right in entries[i + 1 :]:
                if dict(left.arguments) == dict(right.arguments):
                    self.assertNotEqual(normalize(left.text), normalize(right.text))
        Baseline(CURATED)  # would raise on a collision

    def test_rule_7_every_text_is_english(self):
        for case in EVALUATION_SET:
            self.assertTrue(case.text.isascii(), case.identifier)

    def test_no_identifier_is_followed_by_a_boundary_character(self):
        # `.` and `-` are in the Section 4.6 whole-token boundary class, so an
        # identifier followed by either would not be a token of its own text.
        for case in EVALUATION_SET:
            for match in SAMPLE.finditer(case.text):
                following = case.text[match.end() : match.end() + 1]
                self.assertNotIn(following, {".", "-"}, f"{case.identifier}: {match.group()}{following}")


class TheThresholdsMirrorTheDocument(unittest.TestCase):
    def section_8_3(self):
        text = CONTRACT.read_text()
        start = text.index("### 8.3 ")
        end = text.index("## 9. ", start)
        return text[start:end]

    def test_rule_8_the_constants_equal_section_8_3(self):
        section = self.section_8_3()
        coverage = re.search(r"`task_coverage` \| ≥ `([0-9.]+)`", section)
        false_resolution = re.search(r"`false_resolution` \| ≤ `([0-9.]+)`", section)
        registered_at = re.search(r"`registered_at`: `([^`]+)`", section)
        version = re.search(r"`contract_version`: `([^`]+)`", section)
        for match in (coverage, false_resolution, registered_at, version):
            self.assertIsNotNone(match, "Section 8.3 has changed shape")
        self.assertEqual(THRESHOLDS.task_coverage, float(coverage.group(1)))
        self.assertEqual(THRESHOLDS.false_resolution, float(false_resolution.group(1)))
        self.assertEqual(THRESHOLDS.registered_at, registered_at.group(1))
        self.assertEqual(THRESHOLDS.contract_version, version.group(1))
        # And not the document's current version: Section 8.3's
        # `contract_version` records which version registered these numbers,
        # so it stays put while a later version that does not change them
        # moves past it. The line above is the whole claim.
        self.assertLessEqual(
            tuple(int(p) for p in THRESHOLDS.contract_version.split(".")),
            tuple(int(p) for p in CONTRACT_VERSION.split(".")),
            "the thresholds cannot be registered by a version later than the document's",
        )

    def test_the_composition_counts_equal_section_8_3s(self):
        section = self.section_8_3()
        for label, count in (("P", 33), ("D", 4), ("X", 5), ("U", 6)):
            self.assertIsNotNone(re.search(rf"\| `{label}` \| [a-z-]+ \| {count} \|", section), label)
        self.assertIn("`N = 48`", section)


class TheFloorIsMeasured(unittest.TestCase):
    """Rule 9: the baseline's floor as a fact about this set, by the harness."""

    def test_the_baseline_scores_22_of_48_and_never_resolves_falsely(self):
        metrics, outcomes = measure(EVALUATION_SET, Baseline(CURATED).resolve)
        self.assertEqual(metrics.correct, 22)
        self.assertEqual(metrics.false_resolutions, 0)
        split = Counter()
        for outcome in outcomes:
            if outcome.correct:
                split[outcome.identifier.split("-")[1]] += 1
        self.assertEqual(split, Counter({"P": 11, "X": 5, "U": 6}))

    def test_the_set_is_answerable_a_perfect_resolver_scores_48_of_48(self):
        # Not a claim about any adapter: a proof that every registration is
        # reachable under the rules -- a case nobody could get right would be
        # a defect of the set, not of the resolver.
        by_text = {case.text: case for case in EVALUATION_SET}

        def perfect(text):
            case = by_text[text]
            kind = family(case)
            if kind in {"P", "D"}:
                return Proposal(route=case.expected_route, arguments=dict(case.expected_arguments))
            if kind == "X":
                dimension = next(d for d in SCOPE_DIMENSIONS if len(loaded_values_present(text, d)) == 2)
                return Proposal(
                    route="message_facts",
                    arguments={dimension: sorted(loaded_values_present(text, dimension))},
                )
            return Proposal(route="unsupported", arguments={})

        metrics, outcomes = measure(EVALUATION_SET, perfect)
        self.assertEqual(metrics.correct, 48, [o.identifier for o in outcomes if not o.correct])
        self.assertEqual(metrics.false_resolutions, 0)
        self.assertEqual(metrics.task_coverage, 1.0)
