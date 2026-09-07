"""The Milestone 2 comparison, and the gate that stops it judging itself.

Charter Section 9: "A numeric adoption threshold is registered before the run
it judges. Reporting a metric without a pre-registered pass condition does not
satisfy a gate." Contract Section 8 repeats it for this comparison
specifically, and contract Section 9 lists the thresholds and the curated
request set as open decisions the owner fills as a minor version change.

That rule is easy to state and easy to defeat by accident: run the comparison,
look at the numbers, then pick a bar the numbers clear. So it is mechanical
here rather than procedural.

- `measure` and `compare` compute metrics and **never** return a verdict.
- `judge` is the only thing that can say "adopt", it requires `Thresholds`,
  and it refuses when they carry a registration timestamp that is not strictly
  earlier than the run it is judging. A number invented after the run cannot
  be laundered through this function.
- With no thresholds at all, the verdict is `not_judged` -- never `pass`.

The curated request set and the numbers themselves are not in this file, and
not in this slice. They are the owner's recorded decision; this is the machine
that consumes them.
"""

import dataclasses
import datetime
import types
from collections.abc import Mapping

from ..routes import Route
from ..runtime.request import Refusal
from ..status import Status
from .revalidation import Proposal, answer, revalidate

_ROUTE_NAMES = frozenset(route.value for route in Route)

# Section 5's negative families. "Without weakening any negative outcome"
# (Charter Section 9, contract Section 8) means none of these may become a
# `success`, and that is checked case by case rather than as an aggregate --
# one request that turned a refusal into a fact is a failure however good the
# averages look.
NEGATIVE = frozenset(status.value for status in Status if status is not Status.SUCCESS)


@dataclasses.dataclass(frozen=True, kw_only=True)
class Thresholds:
    """The pre-registered pass condition. Owner-decided, contract-recorded."""

    task_coverage: float
    false_resolution: float
    registered_at: str
    contract_version: str

    def __post_init__(self) -> None:
        for name in ("task_coverage", "false_resolution"):
            value = getattr(self, name)
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise ValueError(f"{name} must be a number")
            if not 0.0 <= float(value) <= 1.0:
                raise ValueError(f"{name} must be a fraction between 0 and 1")
        _instant(self.registered_at, "registered_at")
        if not isinstance(self.contract_version, str) or self.contract_version == "":
            raise ValueError(
                "contract_version must name the version that registered these"
                " thresholds; Section 9 makes filling them a minor version change"
            )

    def as_json(self) -> dict:
        return {
            "task_coverage": self.task_coverage,
            "false_resolution": self.false_resolution,
            "registered_at": self.registered_at,
            "contract_version": self.contract_version,
        }


@dataclasses.dataclass(frozen=True, kw_only=True)
class EvaluationCase:
    """One entry in the frozen request set both resolvers are run over."""

    identifier: str
    text: str
    expected_status: str
    expected_route: str | None = None
    expected_arguments: Mapping[str, str] = dataclasses.field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "expected_arguments", types.MappingProxyType(dict(self.expected_arguments))
        )

    def resolves(self) -> bool:
        return self.expected_route is not None


@dataclasses.dataclass(frozen=True, kw_only=True)
class Outcome:
    """What one resolver did with one case."""

    identifier: str
    proposed_route: object
    accepted: bool
    correct: bool
    false_resolution: bool
    status: str | None = None

    def as_json(self) -> dict:
        return {
            "identifier": self.identifier,
            "proposed_route": self.proposed_route
            if isinstance(self.proposed_route, str)
            else repr(self.proposed_route),
            "accepted": self.accepted,
            "correct": self.correct,
            "false_resolution": self.false_resolution,
            "status": self.status,
        }


@dataclasses.dataclass(frozen=True, kw_only=True)
class Metrics:
    """One resolver's numbers over the frozen set."""

    total: int
    correct: int
    false_resolutions: int
    weakened_negatives: tuple[str, ...] = ()

    @property
    def task_coverage(self) -> float:
        """The share of the set turned into the call the case registers.

        Counted over every case, including the ones that should *not* resolve:
        answering "no route applies" to a request that has no route is a
        correct resolution, and a metric that ignored those would reward a
        resolver for guessing.
        """
        return 0.0 if not self.total else self.correct / self.total

    @property
    def false_resolution(self) -> float:
        """The share that produced an accepted call the case did not register.

        Accepted matters: a proposal revalidation refused never became a
        lookup, so it is a miss and not a false resolution. This number counts
        the failures that would have reached the database and returned real
        facts about the wrong thing -- indistinguishable, to a reader, from a
        correct answer.
        """
        return 0.0 if not self.total else self.false_resolutions / self.total

    def as_json(self) -> dict:
        return {
            "total": self.total,
            "correct": self.correct,
            "false_resolutions": self.false_resolutions,
            "task_coverage": self.task_coverage,
            "false_resolution": self.false_resolution,
            "weakened_negatives": list(self.weakened_negatives),
        }


def measure(cases, resolve, runtime=None) -> tuple[Metrics, tuple[Outcome, ...]]:
    """Run `resolve` over `cases` and count. Returns numbers, never a verdict.

    `runtime` is optional. Without it the outcomes carry no status and the
    negative-weakening check has nothing to read, which the report records
    rather than silently treating as "none weakened".
    """
    outcomes = []
    weakened = []
    for case in cases:
        proposal = resolve(case.text)
        accepted = _accepted(proposal, case.text)
        correct = _correct(proposal, case)
        outcome_status = None
        if runtime is not None:
            outcome_status = answer(runtime, proposal, case.text).status.value
            if case.expected_status in NEGATIVE and outcome_status == Status.SUCCESS.value:
                weakened.append(case.identifier)
        outcomes.append(
            Outcome(
                identifier=case.identifier,
                proposed_route=proposal.route,
                accepted=accepted,
                correct=correct,
                false_resolution=accepted and not correct,
                status=outcome_status,
            )
        )
    return (
        Metrics(
            total=len(outcomes),
            correct=sum(1 for outcome in outcomes if outcome.correct),
            false_resolutions=sum(1 for outcome in outcomes if outcome.false_resolution),
            weakened_negatives=tuple(weakened),
        ),
        tuple(outcomes),
    )


def _accepted(proposal: Proposal, request_text: str) -> bool:
    """Whether revalidation would let this proposal reach the database."""
    try:
        revalidate(proposal, request_text)
    except Refusal:
        return False
    return True


def _correct(proposal: Proposal, case: EvaluationCase) -> bool:
    if not case.resolves():
        # The case registers no route. A proposal that names none of the
        # three is correct outright. One that does name a route is also
        # correct if revalidation refuses it with the status the case
        # registers: Section 8.3 counts that as the registered outcome
        # reached a different way, rather than scoring a miss an adapter that
        # surfaced the same contradiction the deterministic layer would have
        # refused on anyway.
        if proposal.route not in _ROUTE_NAMES:
            return True
        try:
            revalidate(proposal, case.text)
        except Refusal as refusal:
            return refusal.status.value == case.expected_status
        return False
    if proposal.route != case.expected_route:
        return False
    return dict(proposal.arguments) == dict(case.expected_arguments)


@dataclasses.dataclass(frozen=True, kw_only=True)
class Report:
    """One comparison run. Carries numbers and provenance, never a verdict."""

    started_at: str
    model: str
    decoding: dict
    adapter: Metrics
    baseline: Metrics
    adapter_outcomes: tuple[Outcome, ...]
    baseline_outcomes: tuple[Outcome, ...]
    executed: bool

    def as_json(self) -> dict:
        return {
            "started_at": self.started_at,
            "model": self.model,
            "decoding": self.decoding,
            "executed_against_a_database": self.executed,
            "adapter": self.adapter.as_json(),
            "baseline": self.baseline.as_json(),
            "adapter_outcomes": [o.as_json() for o in self.adapter_outcomes],
            "baseline_outcomes": [o.as_json() for o in self.baseline_outcomes],
        }


def compare(cases, *, adapter, baseline, model, decoding, runtime=None) -> Report:
    """Run both resolvers over the same frozen set. No verdict is produced."""
    started_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    adapter_metrics, adapter_outcomes = measure(cases, adapter, runtime)
    baseline_metrics, baseline_outcomes = measure(cases, baseline, runtime)
    return Report(
        started_at=started_at,
        model=model,
        decoding=decoding,
        adapter=adapter_metrics,
        baseline=baseline_metrics,
        adapter_outcomes=adapter_outcomes,
        baseline_outcomes=baseline_outcomes,
        executed=runtime is not None,
    )


@dataclasses.dataclass(frozen=True, kw_only=True)
class Judgement:
    """Whether the report clears a pre-registered bar, and why."""

    adoptable: bool
    judged: bool
    reasons: tuple[str, ...]
    thresholds: dict | None

    def as_json(self) -> dict:
        return {
            "adoptable": self.adoptable,
            "judged": self.judged,
            "reasons": list(self.reasons),
            "thresholds": self.thresholds,
        }


def judge(report: Report, thresholds: Thresholds | None, *, pinned_decoding=None) -> Judgement:
    """The only function here that can say "adopt", and the only gate on it.

    Refuses in three ways, and each refusal is a rule from the Charter or the
    contract rather than a safety margin invented here:

    - No thresholds: Charter Section 9 says reporting a metric without a
      pre-registered pass condition does not satisfy a gate.
    - Thresholds registered at or after the run started: they were not
      pre-registered, whatever the file says. This is the check that makes the
      rule mechanical instead of a habit.
    - A decoding configuration that differs from the pinned one: Section 8
      requires "the recorded model identifier and decoding configuration in
      the evaluation artifact must equal the pinned values", and Section 4.6
      says changing either reopens this comparison.

    Adoption itself remains a recorded human decision (Section 8). A `True`
    here means the numbers cleared a bar someone set in advance; it does not
    adopt anything.
    """
    if thresholds is None:
        return Judgement(
            adoptable=False,
            judged=False,
            reasons=(
                "no pre-registered thresholds; Charter Section 9 does not let a"
                " metric without a pass condition satisfy a gate",
            ),
            thresholds=None,
        )
    if _instant(thresholds.registered_at, "registered_at") >= _instant(
        report.started_at, "started_at"
    ):
        return Judgement(
            adoptable=False,
            judged=False,
            reasons=(
                f"the thresholds are registered at {thresholds.registered_at}, which"
                f" is not before this run at {report.started_at}; Charter Section 9"
                f" requires a threshold to be registered before the run it judges",
            ),
            thresholds=thresholds.as_json(),
        )

    reasons = []
    if pinned_decoding is not None and report.decoding != pinned_decoding:
        reasons.append(
            "the recorded decoding configuration differs from the pinned one"
            " (Sections 4.6 and 8)"
        )
    if not report.executed:
        reasons.append(
            "the run did not execute against a database, so no negative outcome"
            " was observed and weakening cannot be ruled out"
        )
    if report.adapter.task_coverage < thresholds.task_coverage:
        reasons.append(
            f"task coverage {report.adapter.task_coverage:.3f} is below the"
            f" registered {thresholds.task_coverage:.3f}"
        )
    if report.adapter.false_resolution > thresholds.false_resolution:
        reasons.append(
            f"false resolution {report.adapter.false_resolution:.3f} exceeds the"
            f" registered {thresholds.false_resolution:.3f}"
        )
    if report.adapter.weakened_negatives:
        reasons.append(
            f"negative outcomes weakened on {list(report.adapter.weakened_negatives)}"
        )
    return Judgement(
        adoptable=not reasons,
        judged=True,
        reasons=tuple(reasons),
        thresholds=thresholds.as_json(),
    )


def _instant(value: object, field: str) -> datetime.datetime:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an ISO-8601 string")
    try:
        moment = datetime.datetime.fromisoformat(value)
    except ValueError as broken:
        raise ValueError(f"{field} is not an ISO-8601 instant: {value!r}") from broken
    if moment.tzinfo is None:
        raise ValueError(
            f"{field} must carry a timezone; a bare local time cannot be compared"
            f" with a run that may happen anywhere"
        )
    return moment
