"""The Milestone 2 comparison: one command, one artifact, no verdict of its own.

    python3 -m evidence_first_rag.adapter.run --artifact PATH

This is the only entry point that calls a model, and the last piece of code
the Section 8 gate needs. It runs `compare` over the registered set with the
registered curated table, hands the report to `judge` with the registered
thresholds, and writes one JSON document. It never prints "adopt": a
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
the tree when it is committed to `docs/acceptance/`; the pull request that
commits it is gated by `scripts/checks/scan_sensitive_strings.py`, which is
registered in `.github/agent-checks.json` and in CI and scans the whole
working tree.

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


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def prompt_digest() -> dict:
    """Section 4.6: the instructions and the payload, recorded by digest."""
    return {
        "instructions_sha256": _sha256(vocabulary.instructions()),
        "payload_sha256": _sha256(vocabulary.as_text(vocabulary.payload())),
    }


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
) -> dict:
    """Run the comparison once and return the artifact document.

    `propose` is the adapter's resolver (text -> Proposal); `runtime` is the
    `Runtime` the accepted proposals execute against, and it must be a real
    one for the run to be judged -- `judge` refuses a run that touched no
    database, because weakening cannot be ruled out without observing the
    statuses. `pinned_decoding` defaults to `decoding`: `main` passes the
    client's own configuration for both, and the artifact recording it is
    the Section 8 "equals the pinned values" evidence.
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
    return {
        "contract_identifier": CONTRACT_IDENTIFIER,
        "contract_version": CONTRACT_VERSION,
        "run_identifier": str(uuid.uuid4()),
        "started_at": report.started_at,
        "model": model,
        "decoding": decoding,
        "prompt_digest": prompt_digest(),
        "thresholds": thresholds.as_json() if thresholds is not None else None,
        "report": report.as_json(),
        "judgement": judgement.as_json(),
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
    )
    write(arguments.artifact, document)
    print(f"{summary(document)}\n  -> {arguments.artifact}")
    return exit_code(document)


if __name__ == "__main__":
    sys.exit(main())
