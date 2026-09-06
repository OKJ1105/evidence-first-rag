"""Run every registered fixture, judge it, and write one artifact.

Section 4.9's shape, in order: execute each fixture against the runtime with
the read-only identity, run Groups A through E, assign verdicts and failure
classes, write one JSON artifact.

**No language model is invoked here, or anywhere in this package.** Charter
Section 3.3 forbids a model from judging conformance of its own output and
Framework Section 5.7 assigns that judgement to the contract, so every check
in this package is an equality, a set difference, or a SQLSTATE comparison.
`tests/test_conformance_surface.py` asserts the absence rather than trusting
this paragraph.

`D1` needs two runs, so the runner performs two and emits the second. The two
documents it compares do not themselves contain `D1`, which is appended to the
emitted artifact afterwards -- a comparison that included its own result would
never be equal.
"""

import argparse
import dataclasses
import datetime
import hashlib
import json
import pathlib
import sys
import uuid

from ..contract import CONTRACT_IDENTIFIER, CONTRACT_VERSION
from ..registry import REGISTERED as REGISTERED_TEMPLATES
from ..runtime import Request, Runtime
from . import checks, expected, probes
from .artifact import Artifact, FixtureOutcome, Verdict, comparable
from .cases import REGISTERED
from .normalize import normalize
from .recording import RecordingDatabase, recording_cursor

# Section 7 asks for "the fixture provenance that actually exists". The runner
# knows what the database was provisioned from, so it is the layer that can
# tell the runtime; see `Runtime.fixture_provenance`.
FIXTURE_PROVENANCE = (
    "fixtures/source_snapshot.jsonl",
    "fixtures/message_occurrence.jsonl",
    "fixtures/signal_occurrence.jsonl",
    "fixtures/signal_mapping.jsonl",
)


def run(open_runtime_database, *, probe_connection, invariant_failures) -> Artifact:
    """One pass over every registered fixture.

    `open_runtime_database` is called with a psycopg cursor class and must
    return the runtime's session source built to use it. That indirection is
    what lets `B1` watch at the driver rather than at the session port: see
    `recording.py`, and Issue #28 for why the depth decides whether the check
    means anything. `probe_connection` yields a fresh connection as the
    runtime identity for the Section 4.10 instrumentation in `probes.py`.
    `invariant_failures` is what `db.invariants.check` returned, a parameter
    rather than something computed here because it needs the provisioning
    identity, which Section 4.3 keeps out of the runtime and which this
    package never holds. Its enforcement probes insert rows inside savepoints
    and roll them back; nothing survives, and Section 4.10's digest -- built
    on `max(xmin)` over the four tables rather than on the cluster's
    transaction counter, see `probes.py` -- does not move for them.
    """
    statements: list[str] = []
    recording = RecordingDatabase(open_runtime_database(recording_cursor(statements)))
    runtime = Runtime(database=recording, fixture_provenance=FIXTURE_PROVENANCE)

    with probe_connection() as connection:
        before = probes.state_digest(connection)
        timeout = probes.statement_timeout(connection)
        connection.rollback()

    outcomes = []
    fixtures = []
    for case in REGISTERED:
        mark = len(recording.executions)
        result = runtime.execute(Request(route=case.route, arguments=case.arguments))
        executions = recording.since(mark)
        document = normalize(result)
        outcomes.append((case.identifier, result.status.value, executions))
        fixtures.append(
            FixtureOutcome(
                identifier=case.identifier,
                structural_case=case.structural_case,
                checks=(
                    checks.a1(case, document, expected.registered(case.identifier)),
                    checks.e1(case, result),
                ),
                result=document,
            )
        )

    opened = sum(
        1
        for outcome in fixtures
        if outcome.result["evidence_bundle"]["read_only_safeguards"]["connection_opened"]
    )
    recorded_refusals = probes.refusals(probe_connection)
    with probe_connection() as connection:
        after = probes.state_digest(connection)
        connection.rollback()

    return Artifact(
        run_identifier=str(uuid.uuid4()),
        started_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        contract_identifier=CONTRACT_IDENTIFIER,
        contract_version=CONTRACT_VERSION,
        environment={
            "statement_timeout": timeout,
            # Section 7 requires the role name on every bundle; recorded once
            # here too, read back off the results rather than off the
            # connection parameters, so that the artifact says which identity
            # actually connected and not which one was configured.
            # The committed template texts, by digest. Section 4.4 makes the
            # SQL "committed and inspectable"; recording the digests lets a
            # reader confirm that the texts `B1` compared against are the ones
            # in `registry.py` today, without the artifact carrying four
            # copies of the SQL.
            "registered_templates": [
                {
                    "name": template.name,
                    "version": template.version,
                    "sha256": hashlib.sha256(template.sql.encode("utf-8")).hexdigest(),
                }
                for template in REGISTERED_TEMPLATES
            ],
            "runtime_roles": sorted(
                {
                    safeguards["role_name"]
                    for safeguards in (
                        outcome.result["evidence_bundle"]["read_only_safeguards"]
                        for outcome in fixtures
                    )
                    if safeguards["connection_opened"]
                }
            ),
        },
        state_digest={"before": before, "after": after},
        refusals=recorded_refusals,
        run_checks=(
            checks.b1(statements, recording.executions, opened),
            checks.b2(outcomes),
            checks.b3(recorded_refusals),
            checks.b4(before, after),
            checks.c1(invariant_failures, statement_timeout=timeout),
        ),
        fixtures=tuple(fixtures),
    )


def run_twice(open_runtime_database, *, probe_connection, invariant_failures) -> Artifact:
    """Two passes, and the `D1` comparison between them.

    Emits the second run's artifact with `D1` appended. Section 4.9: "Two runs
    over the same fixtures and the same database produce identical artifacts."
    """
    first = run(
        open_runtime_database,
        probe_connection=probe_connection,
        invariant_failures=invariant_failures,
    )
    second = run(
        open_runtime_database,
        probe_connection=probe_connection,
        invariant_failures=invariant_failures,
    )
    determinism = checks.d1(comparable(first.as_json()), comparable(second.as_json()))
    return dataclasses.replace(second, run_checks=second.run_checks + (determinism,))


def main(argv=None) -> int:
    """Provision-independent entry point. Writes the artifact and returns 0/1."""
    import os

    import psycopg

    from ..db import invariants
    from ..runtime.connection import PsycopgDatabase

    parser = argparse.ArgumentParser(description="Run the Section 4.9 conformance suite.")
    parser.add_argument("--database", default=os.environ.get("MVP_DATABASE", "mvp"))
    parser.add_argument("--artifact", type=pathlib.Path, default=pathlib.Path("conformance.json"))
    arguments = parser.parse_args(argv)

    runtime_parameters = {
        "dbname": arguments.database,
        "user": os.environ.get("MVP_RUNTIME_USER", "mvp_runtime"),
        "password": os.environ.get("MVP_RUNTIME_PASSWORD"),
        "host": os.environ.get("PGHOST"),
        "port": os.environ.get("PGPORT"),
    }

    with psycopg.connect(
        dbname=arguments.database,
        user=os.environ.get("MVP_PROVISIONING_USER", "mvp_provisioning"),
        password=os.environ.get("MVP_PROVISIONING_PASSWORD"),
        host=os.environ.get("PGHOST"),
        port=os.environ.get("PGPORT"),
    ) as connection:
        invariant_failures = invariants.check(connection)
        connection.rollback()

    artifact = run_twice(
        lambda cursor_factory: PsycopgDatabase(
            connection_parameters=runtime_parameters | {"cursor_factory": cursor_factory}
        ),
        probe_connection=lambda: psycopg.connect(**runtime_parameters),
        invariant_failures=invariant_failures,
    )
    arguments.artifact.write_text(json.dumps(artifact.as_json(), indent=2, sort_keys=False) + "\n")

    print(f"Conformance: {artifact.verdict.value.upper()}  ->  {arguments.artifact}")
    for check in artifact.failed:
        print(f"  {check.identifier} [{check.failure_class}] {check.detail}")
    return 0 if artifact.verdict is not Verdict.FAIL else 1


if __name__ == "__main__":
    sys.exit(main())
