"""The verdict rules of Section 4.9, and the one that has to be structural.

"A `fail` ... always blocks acceptance and can never be overridden into a
pass, per Charter Section 9." Issue #15 asks for that "asserted, not
documented", so this file enumerates the ways one might try.
"""

import dataclasses
import unittest

from evidence_first_rag.conformance.artifact import (
    IRREPRODUCIBLE,
    Artifact,
    FixtureOutcome,
    Verdict,
    comparable,
)
from evidence_first_rag.conformance.checks import CheckResult


def check(identifier="B1", passed=True, group="B", failure_class=None):
    return CheckResult(
        identifier=identifier,
        group=group,
        passed=passed,
        detail="",
        failure_class=failure_class if not passed else None,
    )


def fixture(identifier="FX-001", checks=()):
    return FixtureOutcome(
        identifier=identifier, structural_case="", checks=tuple(checks), result={}
    )


def artifact(**overrides):
    values = {
        "run_identifier": "00000000-0000-0000-0000-000000000000",
        "started_at": "2026-09-04T00:00:00+00:00",
        "contract_identifier": "mvp-v0.1",
        "contract_version": "0.5.0",
        "environment": {},
        "state_digest": {},
        "refusals": {},
        "run_checks": (check(),),
        "fixtures": (fixture(checks=(check("A1", True, "A"),)),),
    }
    values.update(overrides)
    return Artifact(**values)


class AFailCannotBecomeAPass(unittest.TestCase):
    def test_a_failing_run_check_fails_the_run(self):
        self.assertIs(artifact(run_checks=(check(passed=False),)).verdict, Verdict.FAIL)

    def test_a_failing_fixture_check_fails_the_run(self):
        failing = fixture(checks=(check("A1", False, "A", "data"),))
        self.assertIs(artifact(fixtures=(failing,)).verdict, Verdict.FAIL)

    def test_verdict_has_no_setter_to_override(self):
        # It is a property computed from the checks on every read, so there is
        # no stored value to assign and no argument to pass.
        with self.assertRaises((AttributeError, dataclasses.FrozenInstanceError)):
            artifact().verdict = Verdict.PASS
        with self.assertRaises(TypeError):
            artifact(verdict=Verdict.PASS)

    def test_advisories_cannot_lift_a_failure_to_review(self):
        # `review` is "every check passes, but ... an advisory divergence".
        # A failing check with an advisory beside it is still a fail.
        both = artifact(run_checks=(check(passed=False),), advisories=("noted",))
        self.assertIs(both.verdict, Verdict.FAIL)

    def test_no_combination_of_failures_yields_pass(self):
        for run_failed in (True, False):
            for fixture_failed in (True, False):
                with self.subTest(run=run_failed, fixture=fixture_failed):
                    document = artifact(
                        run_checks=(check(passed=not run_failed),),
                        fixtures=(
                            fixture(checks=(check("A1", not fixture_failed, "A", "data"),)),
                        ),
                    )
                    expected = (
                        Verdict.FAIL if run_failed or fixture_failed else Verdict.PASS
                    )
                    self.assertIs(document.verdict, expected)


class TheVerdictsAreSection49s(unittest.TestCase):
    def test_all_passing_is_a_pass(self):
        self.assertIs(artifact().verdict, Verdict.PASS)

    def test_an_advisory_over_passing_checks_is_a_review(self):
        self.assertIs(artifact(advisories=("noted",)).verdict, Verdict.REVIEW)

    def test_the_three_verdicts_are_the_closed_set(self):
        self.assertEqual(
            sorted(verdict.value for verdict in Verdict), ["fail", "pass", "review"]
        )

    def test_a_run_level_failure_fails_the_run_even_with_every_fixture_passing(self):
        # Section 4.9: "A failure in Group B or Group C forces `fail` for the
        # whole run, not only for the fixture that surfaced it."
        document = artifact(run_checks=(check("C1", False, "C", "data"),))
        self.assertIs(document.verdict, Verdict.FAIL)
        self.assertTrue(all(f.verdict is Verdict.PASS for f in document.fixtures))


class AFixtureCarriesExactlyOneFailureClass(unittest.TestCase):
    def test_the_first_failing_check_decides(self):
        outcome = fixture(
            checks=(
                check("A1", False, "A", "data"),
                check("E1", False, "E", "presentation"),
            )
        )
        self.assertEqual(outcome.failure_class, "data")

    def test_a_passing_fixture_carries_none(self):
        self.assertIsNone(fixture(checks=(check("A1", True, "A"),)).failure_class)


class TheComparisonRuleRemovesOnlyWhatSection49Names(unittest.TestCase):
    def test_it_removes_the_two_irreproducible_fields(self):
        document = artifact().as_json()
        reduced = comparable(document)
        for field in IRREPRODUCIBLE:
            self.assertIn(field, document)
            self.assertNotIn(field, reduced)

    def test_it_is_exactly_those_two(self):
        # Section 4.9 names the run identifier and the timestamp. A third
        # exclusion would be a rule change, so it has to be a deliberate edit
        # to this list rather than a quiet one inside `comparable`.
        self.assertEqual(IRREPRODUCIBLE, ("run_identifier", "started_at"))
        document = artifact().as_json()
        self.assertEqual(
            set(document) - set(comparable(document)), set(IRREPRODUCIBLE)
        )

    def test_the_artifact_still_records_them(self):
        # Removed from the comparison, not from the artifact: Section 4.10
        # wants both recorded, and making `D1` pass by writing less down would
        # be the wrong repair.
        document = artifact().as_json()
        self.assertTrue(document["run_identifier"])
        self.assertTrue(document["started_at"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
