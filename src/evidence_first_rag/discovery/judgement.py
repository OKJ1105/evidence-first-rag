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
    THRESHOLDS,
    NO_DENOMINATOR,
    rank_bound_violations,
)


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


def judge(
    outcomes,
    per_class,
    *,
    started_at: str,
    observed_digest: str,
    thresholds=_REGISTERED,
    registered_at: str | None = _REGISTERED,
    registered_digest: str | None = _REGISTERED,
) -> Judgement:
    """Judge one run against the Section 8.3 registration.

    `per_class` is what `metrics.per_class` returned for this run. Three
    refusals come before any number is compared, and each is a rule rather
    than a safety margin:

    - **No registered thresholds.** Charter Section 9: reporting a metric
      without a pre-registered pass condition does not satisfy a gate.
    - **`registered_at` not strictly before the run.** They were not
      pre-registered, whatever the document says. This is the check that
      makes Section 8.3's own sentence mechanical instead of a habit.
    - **A registry the set was not authored against.** Section 4.10 rule 8
      makes the recorded digest how a registry change that alters a
      registered case's outcome is detected; a run against another registry
      is not a run over this set, and its numbers are about something else.

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

    outcomes = tuple(outcomes)
    if not thresholds:
        return _unjudged(
            "no registered thresholds; Charter Section 9 does not let a metric"
            " without a pass condition satisfy a gate"
        )
    registered_bars = {name: bars.as_json() for name, bars in thresholds.items()}
    if not outcomes:
        return _unjudged(
            "the run observed no case; there is nothing for the Section 8.3"
            " thresholds to judge",
            registered_at=registered_at, thresholds=registered_bars,
        )
    if registered_at is None:
        return _unjudged("the registration records no `registered_at`")
    if _instant(registered_at, "registered_at") >= _instant(started_at, "started_at"):
        return _unjudged(
            f"the registration is recorded at {registered_at}, which is not before"
            f" this run at {started_at}; Charter Section 9 requires a threshold to"
            f" be registered before the run it judges",
            registered_at=registered_at, thresholds=registered_bars,
        )
    if registered_digest and observed_digest != registered_digest:
        return _unjudged(
            f"the run executed against registry {observed_digest}, and the set was"
            f" authored against {registered_digest}; Section 4.10 rule 8 makes a"
            f" registry change a re-registration, not a run over this set",
            registered_at=registered_at, registry_digest=observed_digest,
            thresholds=registered_bars,
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
