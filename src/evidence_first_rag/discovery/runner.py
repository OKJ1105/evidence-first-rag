"""entity-discovery-v0.1 Section 4.10: one run, one artifact, no verdict.

    python3 -m evidence_first_rag.discovery.runner --artifact PATH

Runs the registered evaluation set through `Discovery` and, for a
`candidates` case that names a route, through `Selection`, records every
case with its request, its registered expectation and its observed result,
computes the Section 4.11 metrics per class and over the set, and writes one
JSON document. It never prints "adopt".

**The command exits 2 and writes nothing.** Two guards stand in front of
it. The first refuses when no set is registered: Charter Section 9 says a
metric without a pre-registered pass condition satisfies no gate, so a run
over an unregistered set must not be cited. Section 8.3 registered the set
at `0.3.0`, so that guard no longer fires, and the second one does -- the
registered set is not wired to a database. Opening that connection, driving
`perform` over `REGISTERED_SET` and judging the result against the Section
8.3 thresholds is the wiring slice, which is not this file yet. `perform`
is what that slice, and the tests, drive with cases in hand.

Section 4.9's exception -- a method under comparison re-runs under itself --
is honoured by construction: one `Discovery` and one `Selection` serve a
run, and both are built for one method. Only `M-LEX-1` exists to drive.
"""

import argparse
import datetime
import json
import pathlib
import sys
import time
import uuid

from ..status import Status
from .evaluation import REGISTERED_SET, EvaluationCase, authoring_failures
from .evidence import CONTRACT_IDENTIFIER, CONTRACT_VERSION, METHOD_IDENTIFIER, METHOD_VERSION
from .metrics import CaseOutcome, compute, per_class
from .request import DiscoveryRequest
from .selection import SelectionRequest
from .status import DiscoveryStatus

DEFAULT_ARTIFACT = pathlib.Path("milestone-3-discovery-run.json")


def _reference_json(reference) -> dict | None:
    if reference is None:
        return None
    return dict(reference.as_parameters())


def observe(case: EvaluationCase, discovery, selection, clock=time.perf_counter) -> tuple[CaseOutcome, dict]:
    """Run one case. Returns the outcome the metrics read and the record the
    artifact carries."""
    started = clock()
    result = discovery.execute(DiscoveryRequest(arguments=dict(case.arguments)))
    latency = clock() - started

    ranked = ()
    resolved_reference = None
    if result.status is DiscoveryStatus.RESOLVED:
        resolved_reference = result.resolved.reference
        ranked = ((result.resolved.reference, 1),)
    elif result.status is DiscoveryStatus.CANDIDATES:
        ranked = tuple((c.reference, c.rank) for c in result.candidates)

    # task_completion: the resolved reference, or the registered target
    # selected through Section 4.8, passed to the registered route. Which of
    # the two paths a case completes through is fixed by its *registered*
    # outcome, not by what the run observed: Section 4.11 says "a case whose
    # registered outcome is `candidates` completes through the Section 4.8
    # selection path, selecting the registered target", so an unlicensed
    # `resolved` on such a case -- already counted in false_resolution -- must
    # not be dispatched directly and credited as an end-to-end completion.
    completed = None
    completion = None
    if case.target_route is not None and case.expected_references:
        target = case.expected_references[0]
        if case.expected_outcome == "resolved":
            if result.status is DiscoveryStatus.RESOLVED:
                completed, completion = _dispatch_resolved(case, result, selection)
            else:
                completed, completion = False, {"reason": f"discovery returned {result.status.value}"}
        elif result.status is not DiscoveryStatus.CANDIDATES:
            completed, completion = False, {
                "reason": f"discovery returned {result.status.value}, not the candidate list this case"
                          " completes through (Section 4.11)"
            }
        else:
            rank = next((r for ref, r in ranked if ref == target), None)
            if rank is None:
                completed, completion = False, {"reason": "the registered target is not in the candidate list"}
            else:
                dispatched = selection.execute(SelectionRequest(arguments={
                    **dict(case.arguments),
                    "candidate_set_id": result.evidence_bundle.candidate_set_id,
                    "selected_rank": str(rank),
                    "target_route": case.target_route.value,
                }))
                completed = _carries(dispatched, target)
                completion = {"selected_rank": rank, "status": dispatched.status.value}

    outcome = CaseOutcome(
        case=case,
        observed_status=result.status.value,
        ranked=ranked,
        completed=completed,
        latency_seconds=latency,
        resolved_reference=resolved_reference,
    )
    record = {
        "identifier": case.identifier,
        "query_class": case.query_class,
        "request": dict(case.arguments),
        "expected": {
            "outcome": case.expected_outcome,
            "references": [_reference_json(r) for r in case.expected_references],
            "rank_bound": case.rank_bound,
            "target_route": None if case.target_route is None else case.target_route.value,
        },
        "observed": {
            "status": result.status.value,
            "resolved": _reference_json(resolved_reference),
            "candidates": [
                {"rank": rank, **_reference_json(reference)} for reference, rank in ranked
            ] if result.status is DiscoveryStatus.CANDIDATES else [],
            "candidate_set_id": result.evidence_bundle.candidate_set_id,
            "registry_digest": result.evidence_bundle.registry_digest,
            "completion": completion,
        },
        "latency_seconds": latency,
    }
    return outcome, record


def _dispatch_resolved(case, result, selection):
    """A resolved reference is used directly as a fully-scoped mvp-v0.1
    request (Section 4.8: "its one reference is used directly ... no
    `candidate_set_id` and needs no selection"), so the runtime is driven
    with the reference itself rather than through the selection path. Only a
    case whose *registered* outcome is `resolved` reaches here.

    It is driven over the same database the selection object holds, because
    Section 4.11's `task_completion` is "the resolved or selected reference,
    passed to that route" -- one database, one run.
    """
    from ..runtime import Request, Runtime

    runtime = Runtime(database=selection.database, fixture_provenance=selection.fixture_provenance)
    dispatched = runtime.execute(
        Request(route=case.target_route.value, arguments=dict(result.resolved.reference.as_parameters()))
    )
    return _carries(dispatched, case.expected_references[0]), {"status": dispatched.status.value}


def _carries(dispatched, target) -> bool:
    """Section 4.11 task_completion: success carrying that reference."""
    if getattr(dispatched, "status", None) is not Status.SUCCESS:
        return False
    parameters = dict(dispatched.evidence_bundle.bound_parameters)
    expected = dict(target.as_parameters())
    return all(parameters.get(name) == value for name, value in expected.items())


def perform(cases, *, discovery, selection, registry_state, started_at=None, run_id=None, clock=time.perf_counter) -> dict:
    """Run every case and build the artifact. Pure with respect to the
    database: `discovery` and `selection` arrive as arguments."""
    cases = tuple(cases)
    failures = authoring_failures(cases)
    outcomes = []
    records = []
    for case in cases:
        outcome, record = observe(case, discovery, selection, clock)
        outcomes.append(outcome)
        records.append(record)
    return {
        "run_id": run_id or str(uuid.uuid4()),
        "started_at": started_at or datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "contract_identifier": CONTRACT_IDENTIFIER,
        "contract_version": CONTRACT_VERSION,
        "method_identifier": METHOD_IDENTIFIER,
        "method_version": METHOD_VERSION,
        "registry_digest": registry_state["registry_digest"],
        "registry_built_at": registry_state["registry_built_at"],
        "authoring_failures": failures,
        "cases": records,
        "metrics": {
            "overall": compute(outcomes).as_json(),
            "per_class": {name: metrics.as_json() for name, metrics in per_class(outcomes).items()},
        },
        # Section 4.11: not a number. Recorded for the owner to weigh.
        "operational_complexity": (
            "M-LEX-1 adds no dependency, service, provisioning step, index, or"
            " egress beyond the registry tables provisioning already loads; it"
            " runs entirely in the database as the runtime identity."
        ),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--artifact", type=pathlib.Path, default=DEFAULT_ARTIFACT)
    parser.parse_args(argv)
    if not REGISTERED_SET:
        sys.stderr.write(
            "no evaluation set is registered: entity-discovery-v0.1 Section 8.3 registers"
            " none at this version, and a run over an unregistered set must not be cited"
            " (Charter Section 9)\n"
        )
        return 2
    # The wiring slice completes this: open the database, read the registry
    # state, drive perform() over REGISTERED_SET, judge the metrics against
    # the Section 8.3 thresholds, and write the artifact.
    sys.stderr.write("the registration slice has not wired the registered set to a database\n")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
