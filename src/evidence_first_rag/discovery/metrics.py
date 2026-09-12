"""entity-discovery-v0.1 Section 4.11: the metric definitions.

Each quantity is defined here so that a later change to how one is computed
is visibly a change to the bar rather than an implementation detail. Every
metric is computed deterministically from recorded per-case outcomes; no
model participates, and latency is recorded and never returned in a result.
"""

import dataclasses
import statistics

from .evaluation import NAMES_A_TARGET, CLASSES, EvaluationCase

RECALL_KS = (1, 5, 10)


@dataclasses.dataclass(frozen=True, kw_only=True)
class CaseOutcome:
    """What one case produced, reduced to what the metrics read.

    `observed_status` is the Section 5 status; `ranked` is the observed
    candidate list as (reference, rank) pairs -- for a `resolved` outcome,
    the single resolved reference at rank 1 (Section 4.11). `completed` is
    whether the reference, passed to the registered mvp-v0.1 route,
    returned success carrying it; None when the case names no route.
    `latency_seconds` is the wall-clock duration of the discovery call.
    """

    case: EvaluationCase
    observed_status: str
    ranked: tuple[tuple[object, int], ...] = ()
    completed: bool | None = None
    latency_seconds: float = 0.0
    resolved_reference: object = None

    def rank_of(self, reference) -> int | None:
        for candidate, rank in self.ranked:
            if candidate == reference:
                return rank
        return None


def _fraction(numerator: int, denominator: int) -> float | None:
    """None when the denominator is zero: a class with no case of that kind
    has no rate, and 0.0 would read as a perfect or a failing score."""
    return None if denominator == 0 else numerator / denominator


@dataclasses.dataclass(frozen=True, kw_only=True)
class Metrics:
    """Section 4.11's numbers over one set of outcomes."""

    total: int
    recall_at_k: dict
    mrr: float | None
    false_resolution: float | None
    correct_abstention: float | None
    over_abstention: float | None
    task_completion: float | None
    latency_median_seconds: float | None
    latency_p95_seconds: float | None

    def as_json(self) -> dict:
        return {
            "total": self.total,
            "recall_at_k": dict(self.recall_at_k),
            "mrr": self.mrr,
            "false_resolution": self.false_resolution,
            "correct_abstention": self.correct_abstention,
            "over_abstention": self.over_abstention,
            "task_completion": self.task_completion,
            "latency": {"median_seconds": self.latency_median_seconds, "p95_seconds": self.latency_p95_seconds},
        }


def _worst_rank(outcome: CaseOutcome) -> int | None:
    """The rank of the registered target, or for Q-MULTI of its worst-ranked
    registered reference; None when any registered reference is absent."""
    ranks = []
    for reference in outcome.case.expected_references:
        rank = outcome.rank_of(reference)
        if rank is None:
            return None
        ranks.append(rank)
    return max(ranks) if ranks else None


def compute(outcomes) -> Metrics:
    outcomes = tuple(outcomes)
    targeted = [o for o in outcomes if o.case.query_class in NAMES_A_TARGET]

    # recall_at_k and mrr, over the cases that name a target. A Q-MULTI case
    # counts only when every registered reference appears within k.
    recall = {}
    for k in RECALL_KS:
        hits = sum(1 for o in targeted if (r := _worst_rank(o)) is not None and r <= k)
        recall[f"recall_at_{k}"] = _fraction(hits, len(targeted))
    reciprocal = [0.0 if (r := _worst_rank(o)) is None else 1.0 / r for o in targeted]
    mrr = None if not targeted else sum(reciprocal) / len(reciprocal)

    # false_resolution, over every case: resolved with a reference other than
    # the registered one, or resolved at all where the registration is not
    # resolved -- even when it landed on the registered target.
    false = 0
    for o in outcomes:
        if o.observed_status != "resolved":
            continue
        if o.case.expected_outcome != "resolved":
            false += 1
        elif o.case.expected_references and o.resolved_reference != o.case.expected_references[0]:
            false += 1
    false_resolution = _fraction(false, len(outcomes))

    # correct_abstention, over the cases registered as not resolved; and its
    # mirror, over_abstention, over the cases registered as resolved.
    should_abstain = [o for o in outcomes if o.case.expected_outcome != "resolved"]
    correct_abstention = _fraction(sum(1 for o in should_abstain if o.observed_status != "resolved"), len(should_abstain))
    should_resolve = [o for o in outcomes if o.case.expected_outcome == "resolved"]
    over_abstention = _fraction(sum(1 for o in should_resolve if o.observed_status != "resolved"), len(should_resolve))

    # task_completion, over the cases that name a target and a route.
    routed = [o for o in targeted if o.case.target_route is not None]
    task_completion = _fraction(sum(1 for o in routed if o.completed is True), len(routed))

    latencies = sorted(o.latency_seconds for o in outcomes)
    median = statistics.median(latencies) if latencies else None
    p95 = None
    if latencies:
        index = max(0, int(round(0.95 * len(latencies) + 0.5)) - 1)
        p95 = latencies[min(index, len(latencies) - 1)]

    return Metrics(
        total=len(outcomes),
        recall_at_k=recall,
        mrr=mrr,
        false_resolution=false_resolution,
        correct_abstention=correct_abstention,
        over_abstention=over_abstention,
        task_completion=task_completion,
        latency_median_seconds=median,
        latency_p95_seconds=p95,
    )


def per_class(outcomes) -> dict[str, Metrics]:
    """Section 4.11: each metric per class and over the whole set. Only the
    classes present in the outcomes are reported; an absent class has no
    number to report rather than a zero."""
    outcomes = tuple(outcomes)
    result = {}
    for name in CLASSES:
        members = [o for o in outcomes if o.case.query_class == name]
        if members:
            result[name] = compute(members)
    return result
