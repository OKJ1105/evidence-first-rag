"""The one JSON artifact a run writes, and the verdict it carries.

Section 4.9 fixes three verdicts and one rule about them that this module
exists to make structural: a `fail` "always blocks acceptance and can never be
overridden into a pass, per Charter Section 9". So `verdict` is computed from
the recorded checks every time it is read. There is no field to set, no
argument to pass, and no code path from a failing check to `pass` --
`tests/test_conformance_artifact.py` enumerates the ways one might try.
"""

import dataclasses
import enum

from .checks import CheckResult

# Section 4.9: "The artifact records a run identifier and a wall-clock
# timestamp. Neither can be reproducible by construction, so `D1` compares the
# artifact with those two fields removed." Exactly these two, named here so
# that a third exclusion has to be a deliberate edit rather than a quiet one.
IRREPRODUCIBLE = ("run_identifier", "started_at")


class Verdict(enum.Enum):
    """Framework Section 5.7's three outcomes, as Section 4.9 conditions them."""

    PASS = "pass"
    REVIEW = "review"
    FAIL = "fail"


@dataclasses.dataclass(frozen=True, kw_only=True)
class FixtureOutcome:
    """One registered fixture's result and the checks that judged it."""

    identifier: str
    structural_case: str
    checks: tuple[CheckResult, ...]
    result: dict

    @property
    def verdict(self) -> Verdict:
        return Verdict.FAIL if self.failed else Verdict.PASS

    @property
    def failed(self) -> tuple[CheckResult, ...]:
        return tuple(check for check in self.checks if not check.passed)

    @property
    def failure_class(self) -> str | None:
        """Section 4.9: "Every non-`pass` fixture carries exactly one class."

        The first failing check's class, in the order the checks ran, so a
        fixture that failed both `A1` and `E1` is classed by the divergence
        rather than by whichever check happened to be listed last.
        """
        for check in self.checks:
            if not check.passed:
                return check.failure_class
        return None

    def as_json(self) -> dict:
        return {
            "identifier": self.identifier,
            "structural_case": self.structural_case,
            "verdict": self.verdict.value,
            "failure_class": self.failure_class,
            "checks": [check.as_json() for check in self.checks],
            "result": self.result,
        }


@dataclasses.dataclass(frozen=True, kw_only=True)
class Artifact:
    """Everything one run recorded."""

    run_identifier: str
    started_at: str
    contract_identifier: str
    contract_version: str
    environment: dict
    state_digest: dict
    refusals: dict
    run_checks: tuple[CheckResult, ...]
    fixtures: tuple[FixtureOutcome, ...]
    # Section 4.9's `review` requires "an advisory divergence that violates no
    # obligation". Nothing in this slice produces one -- every divergence it
    # can observe violates a check -- so this is always empty today. It is a
    # field rather than a missing concept because the verdict rule is the
    # contract's, and a runner that could not represent `review` would be
    # implementing two of the three verdicts while claiming all three.
    advisories: tuple[str, ...] = ()

    @property
    def failed(self) -> tuple[CheckResult, ...]:
        """Every failing check, run-level first.

        Section 4.9: "A failure in Group B or Group C forces `fail` for the
        whole run, not only for the fixture that surfaced it." That is what
        run-level checks being in the same list as the fixtures' does: the
        run's verdict reads all of them.
        """
        failed = [check for check in self.run_checks if not check.passed]
        for fixture in self.fixtures:
            failed.extend(fixture.failed)
        return tuple(failed)

    @property
    def verdict(self) -> Verdict:
        if self.failed:
            return Verdict.FAIL
        if self.advisories:
            return Verdict.REVIEW
        return Verdict.PASS

    def as_json(self) -> dict:
        return {
            "run_identifier": self.run_identifier,
            "started_at": self.started_at,
            "contract_identifier": self.contract_identifier,
            "contract_version": self.contract_version,
            "verdict": self.verdict.value,
            "environment": self.environment,
            "state_digest": self.state_digest,
            "refusals": self.refusals,
            "checks": [check.as_json() for check in self.run_checks],
            "advisories": list(self.advisories),
            "fixtures": [fixture.as_json() for fixture in self.fixtures],
        }


def comparable(document: dict) -> dict:
    """`document` with the two fields Section 4.9 excludes from `D1` removed.

    Removed from the comparison, not from the artifact: Section 4.10 wants the
    run identifier and the timestamp recorded, and a runner that dropped them
    to make two runs match would be making `D1` pass by writing less down.
    """
    return {key: value for key, value in document.items() if key not in IRREPRODUCIBLE}
