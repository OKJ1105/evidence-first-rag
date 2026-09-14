"""entity-discovery-v0.1 Section 8.3: whether a run cleared the registered bars.

The only code here that can say a threshold was met, and the only gate on
it. It follows `adapter/comparison.py`, which answers the same question for
Milestone 2 and is already the repository's shape for it: a `Judgement`
carrying `judged`, `adoptable` and the reasons, refusing in ways the Charter
and the contract fix rather than by any margin invented here.

**`adoptable` does not adopt.** Section 8's row keeps adoption a recorded
human decision taken after the run, in the Milestone 3 acceptance record; a
true here means the numbers cleared a bar someone set in advance.
"""

import dataclasses
import datetime

from .evaluation import (
    CEILINGS,
    NotABar,
    REGISTERED_AGAINST_DIGEST,
    REGISTERED_AT,
    REGISTERED_SET,
    THRESHOLDS,
    NO_DENOMINATOR,
    rank_bound_violations,
)
from .evaluation import authoring_failures as _failures_of


#: "the caller said nothing", distinct from a caller who passed None or an
#: empty mapping on purpose. The registration is then read at call time
#: rather than bound when this module is imported, so a test -- and a later
#: re-registration -- sees the constant that is in force rather than the one
#: that happened to exist first.
_REGISTERED = object()


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


@dataclasses.dataclass(frozen=True, kw_only=True)
class Judgement:
    """Whether the run clears the Section 8.3 registration, and why not."""

    adoptable: bool
    judged: bool
    reasons: tuple[str, ...]
    registered_at: str | None
    registry_digest: str | None
    #: The registered bars this run was judged against, per class, so the
    #: artifact says what it was measured by without anyone opening the
    #: contract. `adapter/comparison.py` records its thresholds for the same
    #: reason. None when there were none to judge by.
    thresholds: dict | None

    def as_json(self) -> dict:
        return {
            "adoptable": self.adoptable,
            "judged": self.judged,
            "reasons": list(self.reasons),
            "registered_at": self.registered_at,
            "registry_digest": self.registry_digest,
            "thresholds": self.thresholds,
        }


def _unjudged(reason: str, *, registered_at=None, registry_digest=None, thresholds=None) -> Judgement:
    return Judgement(
        adoptable=False, judged=False, reasons=(reason,),
        registered_at=registered_at, registry_digest=registry_digest,
        thresholds=thresholds,
    )


def _set_difference(cases, registered) -> str:
    """How the judged cases differ from the registered ones, or "" when they
    do not. Named per case rather than counted, so a refusal says which case
    is not the registered one."""
    cases = tuple(cases)
    registered_by_identifier = {case.identifier: case for case in registered}
    judged_by_identifier = {case.identifier: case for case in cases}
    differences = []
    absent = sorted(set(registered_by_identifier) - set(judged_by_identifier))
    unregistered = sorted(set(judged_by_identifier) - set(registered_by_identifier))
    altered = sorted(
        identifier for identifier, case in judged_by_identifier.items()
        if identifier in registered_by_identifier and case != registered_by_identifier[identifier]
    )
    if len(judged_by_identifier) != len(cases):
        differences.append("an identifier was judged twice")
    if absent:
        differences.append(f"registered but not judged: {', '.join(absent)}")
    if unregistered:
        differences.append(f"judged but not registered: {', '.join(unregistered)}")
    if altered:
        differences.append(f"judged with arguments or expectations the registration does not"
                           f" carry: {', '.join(altered)}")
    return "; ".join(differences)


def judge(
    outcomes,
    per_class,
    *,
    started_at: str,
    observed_digest: str,
    authoring_failures=_REGISTERED,
    thresholds=_REGISTERED,
    registered_at: str | None = _REGISTERED,
    registered_digest: str | None = _REGISTERED,
    registered_set=_REGISTERED,
) -> Judgement:
    """Judge one run against the Section 8.3 registration.

    `per_class` is what `metrics.per_class` returned for this run, and
    `authoring_failures` what `evaluation.authoring_failures` returned over
    the cases it ran; the run computes both, and passing them in keeps the
    judgement about the run that happened rather than about a recomputation
    of it. Five refusals come before any number is compared, and each is a
    rule rather than a safety margin:

    - **No registered thresholds.** Charter Section 9: reporting a metric
      without a pre-registered pass condition does not satisfy a gate.
    - **`registered_at` not strictly before the run.** They were not
      pre-registered, whatever the document says. This is the check that
      makes Section 8.3's own sentence mechanical instead of a habit.
    - **A registry the set was not authored against.** Section 4.10 rule 8
      makes the recorded digest how a registry change that alters a
      registered case's outcome is detected; a run against another registry
      is not a run over this set, and its numbers are about something else.
    - **Cases that are not the registered ones.** Section 8.3 sets its
      conditions "over the set above", and Charter Section 9 registers the
      task definitions before the run and not only the numbers. A set the
      registration does not carry can be built to clear any bar, so its
      numbers are judged by nothing.
    - **A set that breaks a Section 4.10 authoring rule.** The set the run
      ran is then not a registrable one, and `perform` already records the
      violations in the same artifact; a judgement that ignored them would
      report numbers as if the set were sound.

    Then every condition Section 8.3 registers, per class: the numeric bars,
    with the `CEILINGS` compared as upper bounds and the rest as floors; and
    the per-case rank bound `0.3.1` registered, which no class fraction can
    express.
    """
    if thresholds is _REGISTERED:
        thresholds = THRESHOLDS
    if registered_at is _REGISTERED:
        registered_at = REGISTERED_AT
    if registered_digest is _REGISTERED:
        registered_digest = REGISTERED_AGAINST_DIGEST
    if registered_set is _REGISTERED:
        registered_set = REGISTERED_SET

    outcomes = tuple(outcomes)
    registered_bars = (
        {name: bars.as_json() for name, bars in thresholds.items()} if thresholds else None
    )

    def refuse(reason: str) -> Judgement:
        """A refusal that records what it did observe.

        Every refusal below goes through this rather than calling
        `_unjudged` with its own subset, because two of them used to record
        neither the registry they ran against nor the registration they were
        measured by, although both were in hand -- so a reader of a failed
        run learned nothing about either, and the artifact answered the same
        question differently depending on which refusal fired. Passing the
        three here rather than at each site means a refusal added later
        cannot forget them.
        """
        return _unjudged(
            reason,
            registered_at=registered_at,
            registry_digest=observed_digest,
            thresholds=registered_bars,
        )

    if not thresholds:
        return refuse(
            "no registered thresholds; Charter Section 9 does not let a metric"
            " without a pass condition satisfy a gate"
        )
    if not outcomes:
        return refuse(
            "the run observed no case; there is nothing for the Section 8.3"
            " thresholds to judge"
        )
    if registered_at is None:
        return refuse("the registration records no `registered_at`")
    if _instant(registered_at, "registered_at") >= _instant(started_at, "started_at"):
        return refuse(
            f"the registration is recorded at {registered_at}, which is not before"
            f" this run at {started_at}; Charter Section 9 requires a threshold to"
            f" be registered before the run it judges"
        )
    if registered_digest and observed_digest != registered_digest:
        return refuse(
            f"the run executed against registry {observed_digest}, and the set was"
            f" authored against {registered_digest}; Section 4.10 rule 8 makes a"
            f" registry change a re-registration, not a run over this set"
        )
    judged_cases = tuple(outcome.case for outcome in outcomes)
    difference = _set_difference(judged_cases, registered_set)
    if difference:
        return refuse(
            f"the run judged a set that is not the one Section 8.3 registers"
            f" ({difference}); Charter Section 9 registers the task definitions"
            f" before the run, so numbers over another set are measured by"
            f" nothing"
        )
    if authoring_failures is _REGISTERED:
        authoring_failures = _failures_of(judged_cases)
    if authoring_failures:
        return refuse(
            f"the set the run ran breaks Section 4.10's authoring rules, so it is"
            f" not a registrable set: {'; '.join(authoring_failures)}"
        )

    reasons = []
    for name, registered in sorted(thresholds.items()):
        measured = per_class.get(name)
        if measured is None:
            reasons.append(f"{name}: the run reports no metrics for a registered class")
            continue
        # `Metrics.as_json` nests the three recall values under `recall_at_k`
        # and the two latencies under `latency`; the registered bars are flat,
        # one field per quantity. Flattened here rather than read from the
        # nested document, so a lookup that misses reports a missing value
        # instead of silently judging nothing -- which is what a first
        # version of this function did, passing a run in which every recall
        # bar was unevaluated.
        values = measured.as_json()
        values = {k: v for k, v in values.items() if k != "recall_at_k"} | dict(values["recall_at_k"])
        for field in dataclasses.fields(registered):
            bar = getattr(registered, field.name)
            value = values.get(field.name)
            if isinstance(bar, NotABar):
                # Section 8.3: a run that reports a number where the
                # registration says there is no denominator has a defect, and
                # is said so rather than quietly ignored.
                if bar is NO_DENOMINATOR and value is not None:
                    reasons.append(
                        f"{name}.{field.name}: reported {value} where Section 8.3"
                        f" registers no denominator"
                    )
                continue
            if value is None:
                reasons.append(
                    f"{name}.{field.name}: no value where Section 8.3 registers {bar}"
                )
            elif field.name in CEILINGS:
                if value > bar:
                    reasons.append(f"{name}.{field.name}: {value} exceeds the registered {bar}")
            elif value < bar:
                reasons.append(f"{name}.{field.name}: {value} is below the registered {bar}")

    # The condition that is not a per-class fraction (Section 8.3 at 0.3.1).
    observed_ranks = {
        outcome.case.identifier: (
            outcome.rank_of(outcome.case.expected_references[0])
            if outcome.case.expected_references else None
        )
        for outcome in outcomes
    }
    reasons.extend(
        f"rank bound: {line}"
        for line in rank_bound_violations([o.case for o in outcomes], observed_ranks)
    )

    return Judgement(
        adoptable=not reasons,
        judged=True,
        reasons=tuple(reasons),
        registered_at=registered_at,
        registry_digest=observed_digest,
        thresholds=registered_bars,
    )
