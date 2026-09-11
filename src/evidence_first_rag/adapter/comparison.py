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

from ..evidence import Limitation
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
    """What one resolver did with one case, and enough of why to diagnose it.

    The first Milestone 2 comparison refused all forty-eight proposals and the
    artifact could not say what any of them had proposed or which check
    stopped it. `proposed_route`, `accepted` and `refused_as` name the shape
    of the failure; the four fields below carry its content, which is what
    turns "the adapter scored 0.1667" into a finding someone can act on.

    `proposed_route` and `proposed_arguments` are both typed `object` for the
    reason `Proposal` is: Section 4.6 makes adapter output untrusted input,
    and a field that refused a malformed proposal here would raise where the
    artifact needs to record what arrived. Serialisation, not construction, is
    where they become text.

    Recording the proposed arguments is not the thing Section 7 forbids. That
    rule is about `bound_parameters` on a `Result` -- the arguments of a
    rejected request "are never reported as such", because a result echoing
    them would present a rejected proposal as a fact the runtime acted on.
    This is not a `Result` and claims nothing about the runtime: it is the
    measurement of what a model proposed, recorded beside the deterministic
    layer's refusal of it, which is the separation Charter Section 9 asks the
    Milestone 2 trace to show.
    """

    identifier: str
    proposed_route: object
    accepted: bool
    correct: bool
    false_resolution: bool
    status: str | None = None
    # The status revalidation refused with, or None when it accepted. Recorded
    # so the artifact shows *why* a no-route case counted, not only that it did.
    refused_as: str | None = None
    # What the proposal actually carried, untouched. `{}` when it carried no
    # mapping at all -- and that is a blind spot rather than a record: a
    # proposal whose `arguments` were a list and one that genuinely carried
    # none both serialise to `{}` and both refuse as `invalid_request`, a
    # status several unrelated causes share. `refusal_detail` recovers the
    # *type* ("arguments must be a mapping, not list"); nothing recovers the
    # content. Carrying it would mean widening this field beyond the
    # `dict[str, str]` #89 registers, or widening the refusal detail in
    # `runtime/request.py`, and both are outside this slice.
    proposed_arguments: object = dataclasses.field(default_factory=dict)
    # The refusal's own explanation -- the missing lookup key, or the argument
    # whose value is not in the request text. `None` when nothing refused.
    #
    # Only revalidation can fill this, and that is not a gap. `answer`
    # revalidates with the runtime's own `validate` and then hands the *same*
    # `Request` to the runtime, which validates it again with the same pure
    # function: a proposal that passed revalidation cannot be refused by the
    # runtime's validation, so there is no second detail to lose.
    # `TheRuntimeNeverRefusesWhatRevalidationAccepted` in
    # `tests/test_adapter_run.py` holds that invariant rather than leaving it
    # as a claim in a comment.
    refusal_detail: str | None = None
    # The `Result`'s own `limitations`, which is where a terminal
    # `needs_entity_discovery` says so. Empty when the run had no runtime.
    limitations: tuple[Limitation, ...] = ()
    # `source_trace.producing_layer`: Section 5's "the trace records whether
    # the adapter or the runtime produced it", carried through to the artifact.
    producing_layer: str | None = None

    def as_json(self) -> dict:
        return {
            "identifier": self.identifier,
            "proposed_route": _as_text(self.proposed_route),
            "proposed_arguments": _arguments_as_json(self.proposed_arguments),
            "accepted": self.accepted,
            "correct": self.correct,
            "false_resolution": self.false_resolution,
            "refused_as": self.refused_as,
            "refusal_detail": self.refusal_detail,
            "status": self.status,
            "producing_layer": self.producing_layer,
            # The shape `conformance/normalize.py` already writes a
            # `Limitation` in, not a second one invented here.
            # `TheLimitationShapeIsTheOneAlreadyRegistered` compares the two
            # so they cannot drift.
            "limitations": [
                {"kind": limitation.kind.value, "detail": limitation.detail}
                for limitation in self.limitations
            ],
        }


def _as_text(value: object) -> str:
    """A proposal's field as the text the artifact records it in.

    `repr` rather than `str` for anything that is not already text: the
    artifact is read to find out what the model emitted, and `repr` keeps the
    difference between the string `"None"` and `None`, and between one value
    and a list of two.
    """
    return value if isinstance(value, str) else repr(value)


def _arguments_as_json(value: object) -> dict[str, str]:
    """The proposal's arguments as a plain `dict[str, str]`.

    A proposal that carried no mapping is recorded under one reserved key
    rather than as `{}`. Until #112 the schema constrained `arguments` to an
    object and a non-mapping was an aberration that had never occurred, so
    `{}` cost nothing (#95). Since #112 the schema carries `arguments` as a
    `[{name, value}]` list and `client.py` `_as_mapping` passes a
    non-conforming list through unchanged, so `{}` would now make the normal
    shape's failure mode indistinguishable from a proposal that carried no
    arguments at all -- the exact absence #89 exists to close.

    The reserved key keeps the field a `dict[str, str]`, which is the shape
    #89 registered and every reader of `docs/acceptance/` relies on, while
    `_as_text`'s `repr` keeps the payload. `//` cannot collide with an
    argument name, and on that branch there is no other key to collide with.

    Otherwise every name and value goes through
    `_as_text`, which is what keeps the diagnostic that matters: Section
    8.1's `FX-110` is "the adapter proposed two `revision_label` values", and
    those two values arrive as a list inside one name. A serialisation that
    dropped anything that was not already a string would erase exactly the
    case the artifact is being read to find.
    """
    if not isinstance(value, Mapping):
        return {"//not-a-mapping": _as_text(value)}
    return {_as_text(name): _as_text(item) for name, item in value.items()}


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

        A no-route case is also correct when revalidation refused the proposal
        **with the status the case registers** (Section 8.3). Section 8.1's
        `FX-110` registers "the adapter proposed two `revision_label` values"
        as the input whose correct outcome is `invalid_request` from the
        deterministic layer; an adapter that does exactly that is producing
        the registered outcome, and scoring it a miss put a perfect adapter at
        43/48 = 0.896 under a 0.90 bar for doing what the contract asks.
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
        accepted, refused_as, refusal_detail = _revalidated(proposal, case.text)
        correct = _correct(proposal, case, refused_as)
        outcome_status = None
        limitations: tuple[Limitation, ...] = ()
        producing_layer = None
        if runtime is not None:
            # The whole `Result`, not only its status. `limitations` and
            # `source_trace` were built to explain an outcome, and discarding
            # them here is what left the first run's artifact unable to say
            # why forty-eight proposals came to nothing.
            result = answer(runtime, proposal, case.text)
            outcome_status = result.status.value
            limitations = result.limitations
            if result.source_trace.producing_layer is not None:
                producing_layer = result.source_trace.producing_layer.value
            if case.expected_status in NEGATIVE and outcome_status == Status.SUCCESS.value:
                weakened.append(case.identifier)
        outcomes.append(
            Outcome(
                identifier=case.identifier,
                proposed_route=proposal.route,
                proposed_arguments=proposal.arguments,
                accepted=accepted,
                correct=correct,
                false_resolution=accepted and not correct,
                status=outcome_status,
                refused_as=refused_as,
                refusal_detail=refusal_detail,
                limitations=limitations,
                producing_layer=producing_layer,
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


def _revalidated(
    proposal: Proposal, request_text: str
) -> tuple[bool, str | None, str | None]:
    """Whether revalidation lets this proposal reach the database, and if not,
    the status it refused with and the detail that explains it.

    One call answers all three, so `accepted`, `_correct` and the recorded
    explanation can never disagree about the same proposal.

    The detail is the part the artifact was missing. Every refusal here names
    the specific thing that was wrong -- which lookup key is absent, which
    argument carries a value the request text does not contain -- and the
    first Milestone 2 run threw all forty-eight of them away, leaving twenty-
    one `needs_entity_discovery` and twelve `invalid_request` refusals with no
    way to tell which key or which value.
    """
    try:
        revalidate(proposal, request_text)
    except Refusal as refusal:
        return False, refusal.status.value, refusal.detail
    return True, None, None


def _correct(proposal: Proposal, case: EvaluationCase, refused_as: str | None) -> bool:
    if not case.resolves():
        # The case registers no route. Correct is a proposal that names none
        # of the three either -- or one the deterministic layer refused with
        # exactly the status the case registers, which is the registered
        # outcome reached the way Section 8.1 describes it (Section 8.3).
        return proposal.route not in _ROUTE_NAMES or refused_as == case.expected_status
    if proposal.route != case.expected_route:
        return False
    if not isinstance(proposal.arguments, Mapping):
        # Section 4.6 types adapter output as untrusted, so `arguments` can be
        # anything the model emitted, and since #112 a list is what the schema
        # asks for -- `client.py` `_as_mapping` folds a conforming one and
        # passes a malformed one through so that revalidation refuses the
        # shape. `dict()` on that raises, and `_correct` runs before `measure`
        # can record the refusal, so the exception left `perform` and the run
        # exited having written neither document: every paid call in that
        # dispatch lost (#119). A non-mapping cannot equal a registered
        # argument mapping, so `False` is the answer the definition already
        # gives; what changes is that the harness survives to record it.
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
