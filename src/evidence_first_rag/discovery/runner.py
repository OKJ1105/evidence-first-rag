"""entity-discovery-v0.1 Section 4.10: one run, one artifact, no verdict.

    python3 -m evidence_first_rag.discovery.runner --artifact PATH

Runs the registered evaluation set through `Discovery` and, for a
`candidates` case that names a route, through `Selection`, records every
case with its request, its registered expectation and its observed result,
computes the Section 4.11 metrics per class and over the set, and writes one
JSON document. It never prints "adopt".

The artifact carries a **judgement** (`judgement.py`) and no verdict: whether
the run cleared the conditions Section 8.3 registered, and the reasons it did
not. `adoptable` there does not adopt -- Section 8's row keeps adoption a
recorded human decision taken after the run.

**The command still refuses when no set is registered**, which Section 4.10
rule 8 keeps reachable: Charter Section 9 says a metric without a
pre-registered pass condition satisfies no gate, so a run over an
unregistered set must not be cited. **Exit 0 when the run was judged**,
adoptable or not, **and 2 when it was not** -- an unjudged run must not be
cited, and a red job is how that is said. `adapter/run.py` uses the same two
codes for the same rule.

`perform` is pure with respect to the database: `discovery` and `selection`
arrive as arguments, so the tests drive it with cases in hand and `main`
drives it with a connection.

Section 4.9's exception -- a method under comparison re-runs under itself --
is honoured by construction: one `Discovery` and one `Selection` serve a
run, and both are built for one method. Only `M-LEX-1` exists to drive.
"""

import argparse
import datetime
import json
import os
import pathlib
import sys
import time
import uuid

from ..conformance.runner import FIXTURE_PROVENANCE as FACT_FIXTURE_PROVENANCE
from ..status import Status
from .evaluation import REGISTERED_SET, EvaluationCase, authoring_failures
from .evidence import CONTRACT_IDENTIFIER, CONTRACT_VERSION, METHOD_IDENTIFIER, METHOD_VERSION
from .judgement import judge
from .metrics import CaseOutcome, compute, per_class
from .request import DiscoveryRequest
from .selection import SelectionRequest
from .status import DiscoveryStatus

DEFAULT_ARTIFACT = pathlib.Path("milestone-3-discovery-run.json")

# Section 7 asks for "the fixture provenance that actually exists", and
# `conformance/runner.py` states why the runner is the layer that can supply
# it: only what provisioned the database knows what it was loaded from. A
# discovery run reads both trees -- the registry the discovery templates
# resolve against, and the fact fixtures the dispatched `mvp-v0.1` routes
# read -- so it names both. The fact half is imported rather than retyped,
# so a change there cannot leave this list describing a tree that has moved.
FIXTURE_PROVENANCE = FACT_FIXTURE_PROVENANCE + (
    "fixtures/registry/approved_entity.jsonl",
    "fixtures/registry/approved_alias.jsonl",
)


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
    # Read before the cases run, not after: Section 4.10 records "the run's
    # start instant", and `judge` compares Section 8.3's `registered_at`
    # against it. A clock read after the loop would record the finish
    # instant, so a run that began before the thresholds were registered and
    # ended after them -- reachable, because Section 4.10 rule 8
    # re-registers `registered_at` whenever a case or a threshold changes --
    # would be judged as though it had begun after them.
    started = started_at or datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    outcomes = []
    records = []
    for case in cases:
        outcome, record = observe(case, discovery, selection, clock)
        outcomes.append(outcome)
        records.append(record)
    classes = per_class(outcomes)
    judgement = judge(
        outcomes, classes,
        started_at=started,
        observed_digest=registry_state["registry_digest"],
        # The violations this run recorded, not a second computation of
        # them: the artifact's `authoring_failures` and its judgement are
        # then the same statement about the same set.
        authoring_failures=failures,
    )
    return {
        "run_id": run_id or str(uuid.uuid4()),
        "started_at": started,
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
            "per_class": {name: metrics.as_json() for name, metrics in classes.items()},
        },
        # Section 8.3: whether the run cleared the registered conditions, and
        # why not. Never a verdict -- `adoptable` is a statement about
        # numbers, and Section 8 keeps adoption a person's.
        "judgement": judgement.as_json(),
        # Section 4.11: not a number. Recorded for the owner to weigh.
        "operational_complexity": (
            "M-LEX-1 adds no dependency, service, provisioning step, index, or"
            " egress beyond the registry tables provisioning already loads; it"
            " runs entirely in the database as the runtime identity."
        ),
    }


def artifact_text(document: dict) -> str:
    """The one serialisation of a document: what `main` writes and prints.

    One function rather than two call sites, so the bytes in the artifact and
    the bytes in the job log cannot drift apart -- an acceptance record taken
    from the log has to be the file. `adapter/run.py` carries the same helper
    for the same reason.
    """
    return json.dumps(document, indent=2) + "\n"


def main(argv=None) -> int:
    """Open a database, run the registered set, judge it, write the artifact.

    The connection is opened as `conformance/runner.py` opens one: the
    runtime identity from the environment, so the run is performed by the
    read-only role the contract fixes and not by whoever invoked it. The
    registry state comes from `TPL_REGISTRY_STATE_V1` through the same
    session -- a registered template, per Section 4.4, rather than ad-hoc
    SQL -- so the digest the artifact records is one a registered template
    returned.
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--artifact", type=pathlib.Path, default=DEFAULT_ARTIFACT)
    parser.add_argument("--database", default=os.environ.get("MVP_DATABASE", "mvp"))
    arguments = parser.parse_args(argv)

    if not REGISTERED_SET:
        sys.stderr.write(
            "no evaluation set is registered: entity-discovery-v0.1 Section 8.3 registers"
            " none at this version, and a run over an unregistered set must not be cited"
            " (Charter Section 9)\n"
        )
        return 2

    # Deferred until after the refusal above, and not merely for tidiness:
    # `runtime/connection.py` imports the psycopg driver at module scope and
    # is deliberately not reachable from `runtime/__init__.py`, so that
    # `tests/` runs from a clean checkout with neither the driver nor a
    # database. Importing it before the guard would report "no evaluation set
    # is registered" as a missing driver wherever one is absent, turning a
    # Charter Section 9 refusal into an environment problem.
    from ..runtime.connection import PsycopgDatabase
    from ..registry import get
    from .request import STATE_TEMPLATE
    from .service import Discovery, _timestamp
    from .selection import Selection

    database = PsycopgDatabase(connection_parameters={
        "dbname": arguments.database,
        "user": os.environ.get("MVP_RUNTIME_USER", "mvp_runtime"),
        "password": os.environ.get("MVP_RUNTIME_PASSWORD"),
        "host": os.environ.get("PGHOST"),
        "port": os.environ.get("PGPORT"),
    })

    with database.session() as session:
        state = session.execute(get(STATE_TEMPLATE), {})
    if len(state.rows) != 1:
        sys.stderr.write(
            f"entity_registry_state holds {len(state.rows)} rows; Section 4.1 requires"
            f" exactly one after provisioning\n"
        )
        return 2
    registry_state = {
        "registry_digest": state.rows[0]["registry_digest"],
        "registry_built_at": _timestamp(state.rows[0]["built_at"]),
    }

    document = perform(
        REGISTERED_SET,
        discovery=Discovery(database=database, fixture_provenance=FIXTURE_PROVENANCE),
        selection=Selection(database=database, fixture_provenance=FIXTURE_PROVENANCE),
        registry_state=registry_state,
    )
    arguments.artifact.write_text(artifact_text(document))

    judgement = document["judgement"]
    print(
        f"Discovery run: judged={judgement['judged']}"
        f" adoptable={judgement['adoptable']}  ->  {arguments.artifact}"
    )
    for reason in judgement["reasons"]:
        print(f"  {reason}")
    # #117, for the same reason `adapter/run.py` does it: the document
    # follows the summary on stdout, so a run can be read from its job log by
    # a reader who cannot download the artifact. The Milestone 3 artifact
    # expires with the Actions run that produced it, and the acceptance
    # record is drafted from these bytes.
    #
    # Printed on the unjudged path too. The exit code says a run must not be
    # cited; it does not say nobody may read it, which is why
    # `milestone-3-run.yml` uploads with `if: always()`.
    #
    # There is nothing to hold back. `adapter/run.py` prints the main
    # document only, because its raw record carries model text the SAMPLE_*
    # convention cannot vouch for; this run invokes no model and writes no
    # second document.
    print(artifact_text(document), end="")
    # 0 when the run was judged, adoptable or not; 2 when it was not, because
    # an unjudged run must not be cited and a red job is how that is said.
    return 0 if judgement["judged"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
