"""The Milestone 2 comparison: one command, one artifact, no verdict of its own.

    python3 -m evidence_first_rag.adapter.run --artifact PATH

This is the only entry point that calls a model, and the last piece of code
the Section 8 gate needs. It runs `compare` over the registered set with the
registered curated table, hands the report to `judge` with the registered
thresholds, and writes **two** JSON documents. It never prints "adopt": a
`Judgement.adoptable` of true means the numbers cleared a bar set in advance,
and adoption is the owner's recorded decision at the gate (Section 8.2).

**Exit codes.** `0` when the run was judged -- whether or not it cleared the
bar, because a measurement against a pre-registered condition is the
deliverable either way. `2` when `not_judged`: the thresholds were missing or
not earlier than the run, so the run happened out of order and must not be
cited. `1` on any error.

**What the artifact carries beyond the report.** The model and decoding
configuration Section 4.6 pins, taken from `Adapter.configuration()` so the
artifact records what the client actually sends; and the SHA-256 of the
fixed instructions and of the vocabulary payload, which Section 4.6 (0.6.0)
requires recorded by digest -- a change to either reopens the comparison.

**Model-emitted text in a committed artifact.** Each outcome now records the
arguments the adapter proposed and the detail of the refusal that stopped
them, so this document is the one place non-`SAMPLE_*` content could enter
the tree when it is committed to `docs/acceptance/`. The pull request that
commits it is gated by `scripts/checks/scan_sensitive_strings.py`, which is
registered in `.github/agent-checks.json` and in CI and scans the whole
working tree -- but only for what a scanner can decide: credentials,
internal URLs, local machine paths and personal information. It says so
itself, and the exception matters here: a real-world identifier is not
recognisable from its shape, so a model that emits one into
`proposed_arguments` passes that scan. `validate_fixtures.py` enforces the
`SAMPLE_*` convention on `fixtures/` and does not read `docs/`. On this
artifact the AGENTS.md "portable placeholder identifiers only" obligation
is therefore discharged by the human review of the pull request that
commits it, and by nothing mechanical.

**The second document, and why it is never committed.** `PATH.raw.json`
beside the main artifact carries, per model call, the text the adapter
parsed, the `stop_reason`, and the token usage. It exists because #58's first
run could report that all forty-eight proposals were refused without showing
one thing the model wrote: the parsed arguments say *what was proposed*, this
says *what it was parsed from*.

**It is uploaded as an Actions artifact for its ninety-day life and that is
all.** Raw model text is unbounded and is the one thing in this repository
that the `SAMPLE_*` convention cannot vouch for -- the paragraph above
explains why no scanner decides that question either, and there the content
is at least forty-eight parsed argument mappings a reader can check, while
this is whatever the model emitted. So the main artifact is what `docs/acceptance/`
records and this one stays off the tree. The workflow uploads both; nothing
commits this one.

The main artifact gains only `usage_totals` from all of this, and gains it
**absent rather than zero** when no call exposed usage: a run that could not
observe its own cost must not report having cost nothing, the same rule
`Report.executed` applies to a run that touched no database.

`perform` is pure with respect to the model and the database: both arrive as
arguments. `main` is the wiring that supplies the real ones, and it imports
the SDK and the driver only there, so this module is importable -- and
testable -- with neither installed.
"""

import argparse
import hashlib
import json
import pathlib
import sys
import uuid

from ..contract import CONTRACT_IDENTIFIER, CONTRACT_VERSION
from . import vocabulary
from .baseline import Baseline
from .comparison import compare, judge
from .evaluation import CURATED, EVALUATION_SET, THRESHOLDS

DEFAULT_ARTIFACT = pathlib.Path("milestone-2-comparison.json")


def raw_path(artifact: pathlib.Path) -> pathlib.Path:
    """Where the never-committed record sits, derived from the main artifact.

    Derived rather than configured so the two cannot be pointed at unrelated
    places, and so the workflow's two `path:` lines are predictable from the
    one `--artifact` it passes.
    """
    return artifact.with_name(artifact.stem + ".raw" + artifact.suffix)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def prompt_digest() -> dict:
    """Section 4.6: the instructions and the payload, recorded by digest."""
    return {
        "instructions_sha256": _sha256(vocabulary.instructions()),
        "payload_sha256": _sha256(vocabulary.as_text(vocabulary.payload())),
    }


def schema_digest() -> str:
    """The output schema, recorded beside the prompt it is sent with.

    Not required by Section 4.6, which names the model and the decoding
    configuration; the schema is in neither, and the owner's disposition on
    #91 records that reading. It is pinned anyway because this incident is
    the demonstration of what an unpinned input costs: the schema travels
    inside `output_config`, the same object whose `effort` the contract does
    pin, and a change to it decided a whole comparison while leaving every
    recorded digest identical. Two runs with the same `prompt_digest` were
    not the same experiment.

    A digest rather than the schema itself, for the reason Section 4.6 gives
    for the prompt: what matters is that a reader can tell two runs apart,
    not that the artifact carries a copy.
    """
    return _sha256(vocabulary.as_text(vocabulary.schema()))


def perform(
    *,
    propose,
    runtime,
    model: str,
    decoding: dict,
    pinned_decoding: dict | None = None,
    thresholds=THRESHOLDS,
    cases=EVALUATION_SET,
    curated=CURATED,
    recorder=None,
) -> dict:
    """Run the comparison once and return the artifact document.

    `propose` is the adapter's resolver (text -> Proposal); `runtime` is the
    `Runtime` the accepted proposals execute against, and it must be a real
    one for the run to be judged -- `judge` refuses a run that touched no
    database, because weakening cannot be ruled out without observing the
    statuses. `pinned_decoding` defaults to `decoding`: `main` passes the
    client's own configuration for both, and the artifact recording it is
    the Section 8 "equals the pinned values" evidence.

    `recorder` is anything carrying a `calls` sequence -- in a dispatched run
    it is the `Adapter` itself, which is the only object that ever saw a
    response. It is read *after* `compare`, because that is when the calls
    have happened. Omit it and the document is exactly what it was before:
    `usage_totals` is a key that appears when there is something to put in
    it, never a zero standing in for an unobserved cost.
    """
    baseline = Baseline(curated)
    report = compare(
        cases,
        adapter=propose,
        baseline=baseline.resolve,
        model=model,
        decoding=decoding,
        runtime=runtime,
    )
    judgement = judge(
        report,
        thresholds,
        pinned_decoding=decoding if pinned_decoding is None else pinned_decoding,
    )
    document = {
        "contract_identifier": CONTRACT_IDENTIFIER,
        "contract_version": CONTRACT_VERSION,
        "run_identifier": str(uuid.uuid4()),
        "started_at": report.started_at,
        "model": model,
        "decoding": decoding,
        "prompt_digest": prompt_digest(),
        "schema_digest": schema_digest(),
        "thresholds": thresholds.as_json() if thresholds is not None else None,
        "report": report.as_json(),
        "judgement": judgement.as_json(),
    }
    totals = usage_totals(_calls(recorder))
    if totals is not None:
        document["usage_totals"] = totals
    return document


def _calls(recorder) -> tuple:
    return () if recorder is None else tuple(recorder.calls)


def usage_totals(calls) -> dict | None:
    """The token counts summed over every call, or `None` if none reported.

    Only integer values are summed. A usage payload may carry nested
    breakdowns as well as counts, and a total is only meaningful for
    something that adds up; the per-call records in the raw document keep
    whatever the SDK returned, in full, so nothing is lost by this being
    narrow.

    `None` rather than `{}` for the same reason `Call.usage` is: a run that
    observed no cost has not observed a cost of zero.
    """
    totals: dict[str, int] = {}
    for call in calls:
        usage = getattr(call, "usage", None)
        if not usage:
            continue
        for name, value in usage.items():
            if isinstance(value, int) and not isinstance(value, bool):
                totals[name] = totals.get(name, 0) + value
    return totals or None


def raw_document(document: dict, calls) -> dict:
    """The never-committed record for one run.

    `run_identifier` is the main artifact's, not a fresh one: the two files
    are halves of one run, and a reader who has the artifact needs to know
    which raw file belongs to it. That is what ties the two halves together.

    `usage_totals` appears in both on purpose rather than by oversight. The
    raw file outlives nothing -- it is deleted with the Actions artifact --
    but while it exists it has to be readable on its own, and a per-call
    record with no total is a question rather than an answer. The main
    artifact omits the key when nothing reported; this one carries `None`,
    because a file whose whole subject is the calls should say that the
    calls reported no usage rather than stay silent about it.
    """
    calls = tuple(calls)
    return {
        "run_identifier": document["run_identifier"],
        "calls": [call.as_json() for call in calls],
        "usage_totals": usage_totals(calls),
    }


def exit_code(document: dict) -> int:
    """`0` if judged, `2` if not. Adoptable or not is not the runner's to say."""
    return 0 if document["judgement"]["judged"] else 2


def write(path: pathlib.Path, document: dict) -> pathlib.Path:
    path.write_text(json.dumps(document, indent=2, sort_keys=False) + "\n")
    return path


def summary(document: dict) -> str:
    adapter = document["report"]["adapter"]
    judgement = document["judgement"]
    line = (
        f"Comparison: judged={judgement['judged']} adoptable={judgement['adoptable']}"
        f" task_coverage={adapter['task_coverage']:.4f}"
        f" false_resolution={adapter['false_resolution']:.4f}"
        f" weakened={adapter['weakened_negatives']}"
    )
    return line + "".join(f"\n  - {reason}" for reason in judgement["reasons"])


def main(argv=None) -> int:
    """Wire the real model and the real database in, and run once."""
    import os

    from ..conformance.runner import FIXTURE_PROVENANCE
    from ..runtime import Runtime
    from ..runtime.connection import PsycopgDatabase
    from .client import MODEL, Adapter

    parser = argparse.ArgumentParser(description="Run the Section 4.7 adapter comparison once.")
    parser.add_argument("--database", default=os.environ.get("MVP_DATABASE", "mvp"))
    parser.add_argument("--artifact", type=pathlib.Path, default=DEFAULT_ARTIFACT)
    arguments = parser.parse_args(argv)

    runtime = Runtime(
        database=PsycopgDatabase(
            connection_parameters={
                "dbname": arguments.database,
                "user": os.environ.get("MVP_RUNTIME_USER", "mvp_runtime"),
                "password": os.environ.get("MVP_RUNTIME_PASSWORD"),
                "host": os.environ.get("PGHOST"),
                "port": os.environ.get("PGPORT"),
            }
        ),
        fixture_provenance=FIXTURE_PROVENANCE,
    )
    adapter = Adapter.from_environment()
    document = perform(
        propose=adapter.propose,
        runtime=runtime,
        model=MODEL,
        decoding=Adapter.configuration(),
        pinned_decoding=Adapter.configuration(),
        recorder=adapter,
    )
    write(arguments.artifact, document)
    raw = raw_path(arguments.artifact)
    write(raw, raw_document(document, adapter.calls))
    print(f"{summary(document)}\n  -> {arguments.artifact}\n  -> {raw} (not committed)")
    return exit_code(document)


if __name__ == "__main__":
    sys.exit(main())
