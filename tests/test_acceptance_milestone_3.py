"""The committed Milestone 3 run is what `docs/acceptance/milestone-3.md` says.

The record states of itself that "no item rests on a claim made only here",
and every gate item honours that by naming a test or an artifact field. Its
*verification* section did not: that the committed document reproduces was
the writer's assertion and nothing in the tree would have noticed if the
file's `metrics` or `judgement` block were edited after commit. This is that
claim made re-runnable, and standing rather than one-off -- `package-unit-tests`
runs it, so an edit to the committed artifact fails a check.

The Milestone 2 record supplies a one-liner for the equivalent claim
(`docs/acceptance/milestone-2.md`); `M-LEX-1` is deterministic, so the check
here can be stronger than a comparison of two runs -- the artifact is
recomputed from its own case records and compared with what it reports.

What this cannot check, and says so rather than implying otherwise: the
per-case `completed` flag Section 4.11's `task_completion` counts is not
serialised. The artifact records the dispatched `completion` instead, so the
`task_completion` assertion below is against that, and `_carries` -- whether
the dispatched bundle's bound parameters matched the target -- is taken on
the run's own word. A `completion` edited on a case that names no route is
therefore invisible here, because Section 4.11 does not count such a case;
one edited on a routed case is not.
"""

import json
import math
import pathlib
import re
import unittest

from evidence_first_rag.discovery import METHOD_IDENTIFIER, CaseOutcome, compute, per_class
from evidence_first_rag.discovery.evaluation import (
    REGISTERED_AGAINST_DIGEST,
    REGISTERED_SET,
    SAMPLE,
    THRESHOLDS,
    rank_bound_violations,
)

ARTIFACT = (
    pathlib.Path(__file__).resolve().parent.parent
    / "docs" / "acceptance" / "milestone-3" / "discovery-run.json"
)

#: A name in the artifact text: a run of identifier characters that starts
#: where a word starts. The leading `\b` keeps the `T` and `Z` of an ISO
#: timestamp out -- each is preceded by a digit, so neither begins a word --
#: and a lower-case digest is matched but carries no upper-case letter, so
#: the check below passes over it.
#: The run of record judged the `0.3.1` registration. `0.4.0` re-registered
#: it under Section 4.10 rule 8 (#314): a later instant, and EV-SCOPE-5's
#: term. The run is read against what it was judged by, so these two record
#: the `0.3.1` registration where it differs from the current one.
REGISTERED_AT_0_3_1 = "2026-09-13T15:55:00Z"
ARGUMENTS_AT_0_3_1 = {"EV-SCOPE-5": {"term": "temperature reading"}}

NAME = re.compile(r"\b[A-Za-z][A-Za-z0-9_.\-]*")

#: How far a recomputed mean may sit from the reported one, in units in the
#: last place. `mrr` is the one reported quantity that is a mean of floats,
#: and Python changed how `sum()` adds floats at 3.12: 3.11 and earlier fold
#: left, 3.12 and later use Neumaier compensated summation (gh-100425). Over
#: `Q-MULTI`'s reciprocal worst ranks -- 1/2, 1/2, 1/2, 1/3, 1/7 -- the left
#: fold discards half a unit in the last place that the compensated sum keeps,
#: which lands the compensated total exactly on a tie and rounds it to even:
#: one unit above. So the committed run, produced on the pinned 3.11, and a
#: recomputation on a later interpreter cannot be compared for bit equality,
#: and a test that demanded it would be asserting the interpreter rather than
#: the run. Four units covers that difference with margin and is still some
#: fourteen orders of magnitude below the smallest edit to a reported figure
#: that would change what a reader concludes. Every other quantity the
#: artifact reports is a single division of counts or a measurement that was
#: taken, so those are compared exactly.
MEAN_TOLERANCE_ULPS = 4


def _document() -> dict:
    return json.loads(ARTIFACT.read_text(encoding="utf-8"))


class _Absent:
    """Stands in for a resolved reference that is not the registered one.

    Equal to nothing, so `compute` counts it as a false resolution exactly
    where the run did. A `None` would be indistinguishable from "no reference
    was resolved", which is a different outcome.
    """

    def __eq__(self, other):
        return False

    def __hash__(self):
        return id(self)


def _outcomes(document: dict) -> tuple[CaseOutcome, ...]:
    """Rebuild what the metrics read, from the artifact's own case records.

    The registered case supplies the reference objects, matched to the
    record's candidate list by the parameters `runner._reference_json` wrote.
    Only the registered references need to appear in `ranked`: Section 4.11
    reads ranks of registered references and nothing else.
    """
    registered = {case.identifier: case for case in REGISTERED_SET}
    outcomes = []
    for record in document["cases"]:
        case = registered[record["identifier"]]
        observed = record["observed"]
        ranked = []
        for reference in case.expected_references:
            wanted = dict(reference.as_parameters())
            if observed["status"] == "resolved":
                if observed["resolved"] == wanted:
                    ranked.append((reference, 1))
                continue
            for candidate in observed["candidates"]:
                if {k: v for k, v in candidate.items() if k != "rank"} == wanted:
                    ranked.append((reference, candidate["rank"]))
                    break
        resolved = None
        if observed["status"] == "resolved":
            first = case.expected_references[0] if case.expected_references else None
            resolved = (
                first
                if first is not None and observed["resolved"] == dict(first.as_parameters())
                else _Absent()
            )
        completion = observed["completion"]
        outcomes.append(CaseOutcome(
            case=case,
            observed_status=observed["status"],
            ranked=tuple(ranked),
            completed=None if completion is None else completion.get("status") == "success",
            latency_seconds=record["latency_seconds"],
            resolved_reference=resolved,
        ))
    return tuple(outcomes)


class TheCommittedRunIsTheRegisteredSet(unittest.TestCase):
    def setUp(self):
        self.document = _document()

    def test_it_judges_the_forty_registered_cases_and_no_others(self):
        self.assertEqual(
            [record["identifier"] for record in self.document["cases"]],
            [case.identifier for case in REGISTERED_SET],
        )

    def test_every_expectation_is_the_registered_one(self):
        # Not the identifiers alone: an identifier reused for an easier
        # request would pass a name comparison. This compares the question.
        for record, case in zip(self.document["cases"], REGISTERED_SET):
            with self.subTest(case=case.identifier):
                registered = dict(case.arguments) | ARGUMENTS_AT_0_3_1.get(case.identifier, {})
                self.assertEqual(record["request"], registered)
                self.assertEqual(record["query_class"], case.query_class)
                self.assertEqual(record["expected"], {
                    "outcome": case.expected_outcome,
                    "references": [dict(r.as_parameters()) for r in case.expected_references],
                    "rank_bound": case.rank_bound,
                    "target_route": None if case.target_route is None else case.target_route.value,
                })

    def test_it_ran_against_the_registry_the_set_was_authored_against(self):
        # Section 4.10 rule 8: a registry change is a re-registration, not a
        # run over this set.
        self.assertEqual(self.document["registry_digest"], REGISTERED_AGAINST_DIGEST)

    def test_the_registration_precedes_the_run(self):
        # Charter Section 9, and the reason the artifact carries both.
        self.assertEqual(self.document["judgement"]["registered_at"], REGISTERED_AT_0_3_1)
        self.assertLess(REGISTERED_AT_0_3_1, self.document["started_at"])

    def test_it_was_judged_by_the_registered_bars(self):
        self.assertEqual(
            self.document["judgement"]["thresholds"],
            {name: bars.as_json() for name, bars in THRESHOLDS.items()},
        )

    def test_the_record_may_cite_it(self):
        judgement = self.document["judgement"]
        self.assertEqual(judgement["reasons"], [])
        self.assertTrue(judgement["judged"])
        self.assertTrue(judgement["adoptable"])
        self.assertEqual(self.document["authoring_failures"], [])


class TheCommittedMetricsRecomputeFromItsOwnCases(unittest.TestCase):
    """The numbers the acceptance record quotes are the artifact's own case
    records, run back through Section 4.11. An edited `metrics` block fails
    here -- exactly, except for the two reported means, which are held to
    `MEAN_TOLERANCE_ULPS` because the interpreter and not the run decides
    their last bit."""

    def setUp(self):
        self.document = _document()
        self.outcomes = _outcomes(self.document)

    def _compare(self, recomputed, reported, where):
        # Latency included. It is derived -- median and nearest-rank p95 over
        # the per-case measurements -- so recomputing it catches an edited
        # `latency_seconds`, which excluding it would not. `mrr` is compared
        # separately and not for bit equality, for the reason
        # `MEAN_TOLERANCE_ULPS` states; every other field here is exact.
        computed = recomputed.as_json()
        self.assertIn("mrr", reported, where)
        self.assertEqual(
            {name: value for name, value in computed.items() if name != "mrr"},
            {name: value for name, value in reported.items() if name != "mrr"},
            where,
        )
        self._compare_mean(computed["mrr"], reported["mrr"], f"{where} mrr")

    def _compare_mean(self, recomputed, reported, where):
        """A reported mean, to within `MEAN_TOLERANCE_ULPS`.

        A `None` is not a number and is compared as itself: a class with no
        denominator reports `null`, and a float standing where that `null`
        belongs is an edit, not a rounding difference.
        """
        if recomputed is None or reported is None:
            self.assertEqual(recomputed, reported, where)
            return
        self.assertLessEqual(
            abs(recomputed - reported), MEAN_TOLERANCE_ULPS * math.ulp(reported), where
        )

    def test_the_overall_numbers_recompute(self):
        self._compare(compute(self.outcomes), self.document["metrics"]["overall"], "overall")

    def test_every_class_recomputes(self):
        classes = per_class(self.outcomes)
        reported = self.document["metrics"]["per_class"]
        self.assertEqual(sorted(classes), sorted(reported))
        for name, metrics in classes.items():
            self._compare(metrics, reported[name], name)

    def test_the_denominator_for_recall_is_twenty_five_not_forty(self):
        # Section 8.3 states this plainly so that a whole-set number is not
        # read as a retrieval score, and the acceptance record repeats it.
        # Asserted here so the record's sentence cannot drift from the set.
        targeted = [o for o in self.outcomes if o.case.expected_references]
        self.assertEqual(len(self.outcomes), 40)
        self.assertEqual(len(targeted), 25)
        self.assertEqual(self.document["metrics"]["overall"]["recall_at_k"]["recall_at_1"], 0.76)
        self.assertEqual(round(19 / 25, 10), 0.76)

    def test_no_registered_rank_bound_is_violated(self):
        # Section 4.10 rule 3, as `0.3.1` makes it a pass condition: a class
        # fraction cannot express it, so it is checked over the cases.
        observed = {
            outcome.case.identifier: outcome.rank_of(outcome.case.expected_references[0])
            for outcome in self.outcomes
            if outcome.case.query_class == "Q-SEMANTIC"
        }
        self.assertEqual(rank_bound_violations(REGISTERED_SET, observed), [])


class TheCommittedArtifactNamesNothingButSampleIdentifiers(unittest.TestCase):
    """Charter Section 11, over a run document committed under `docs/`.

    No standing check covers it there: `scripts/checks/validate_fixtures.py`
    applies the `SAMPLE_*` convention under `fixtures/` only, and
    `scripts/checks/scan_sensitive_strings.py` says in its own docstring that
    the convention "is enforced by validate_fixtures.py, and nothing enforces
    it for prose". The acceptance record states that the convention was
    checked over this file; this is the mechanical half of that statement,
    standing rather than the writer's word.

    The artifact is machine output over the registered set, so it can carry a
    name only where the set or the registry does -- which is exactly where a
    real-world name would enter if one were ever loaded.
    """

    def test_every_name_it_carries_is_sample_or_a_registered_label(self):
        allowed = (
            {case.identifier for case in REGISTERED_SET}
            | {case.query_class for case in REGISTERED_SET}
            | {METHOD_IDENTIFIER}
        )
        offenders = sorted({
            name
            for name in NAME.findall(ARTIFACT.read_text(encoding="utf-8"))
            if any(character.isupper() for character in name)
            and name not in allowed
            and not SAMPLE.match(name)
        })
        # A capitalised word -- the shape a person, product or company name
        # takes -- is an offender by this rule, because it is neither
        # `SAMPLE_*` nor a label the registration fixes.
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
