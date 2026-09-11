"""What more than one test module needs, defined once.

**Builders.** Every test needs a complete, valid result before it can break
one field, and spelling out a full evidence bundle in each one hides the
assertion inside its setup. These builders produce the contract-conforming
default; a test passes only the field it is about.

**The fixture-identifier enumeration.** `tests/test_adapter_vocabulary.py`
and `tests/test_adapter_evaluation.py` each carried their own copy of the
glob, the pattern and the set comprehension (#69). Two tests that both mean
"every identifier the fixtures load" must read one definition, or a change to
the convention -- the pattern, the glob, a field to exclude -- updates one
copy and leaves the other passing on a stale assumption.
"""

import pathlib
import re

from evidence_first_rag import (
    EvidenceBundle,
    ReadOnlySafeguards,
    Result,
    SnapshotScope,
    SourceTrace,
    Status,
)

RUNTIME_ROLE = "SAMPLE_RUNTIME_ROLE"

FIXTURES = pathlib.Path(__file__).resolve().parent.parent / "fixtures"
SAMPLE = re.compile(r"SAMPLE_[A-Za-z0-9_]+")


def loaded_identifiers() -> set[str]:
    """Every `SAMPLE_*` identifier the registered fixture files contain.

    Read rather than imported from the loader: the question is what a reader
    of `fixtures/` would find, and a test that asked the code instead would
    agree with it by construction.
    """
    return {
        token for path in FIXTURES.glob("*.jsonl") for token in SAMPLE.findall(path.read_text())
    }


def scope(**overrides):
    values = {
        "project_code": "SAMPLE_PROJECT_ALPHA",
        "revision_label": "SAMPLE_REV_A",
        "network_name": "SAMPLE_NET_POWERTRAIN",
        "snapshot_label": "SAMPLE_SNAP_BASE",
    }
    values.update(overrides)
    return SnapshotScope(**values)


def opened_safeguards():
    """Section 4.3: the runtime identity, inside a read-only transaction."""
    return ReadOnlySafeguards(
        role_name=RUNTIME_ROLE, read_only_transaction=True, connection_opened=True
    )


def closed_safeguards():
    """Section 5: the record that no connection was opened."""
    return ReadOnlySafeguards(
        role_name="", read_only_transaction=False, connection_opened=False
    )


def executed_bundle(**overrides):
    values = {
        "route": "message_facts",
        "read_only_safeguards": opened_safeguards(),
        "row_count": 1,
        "template_name": "TPL_MESSAGE_FACTS_V1",
        "template_version": "1",
        "bound_parameters": scope().as_parameters() | {"message_key": "SAMPLE_MSG_A"},
        "resolved_scope": scope(),
    }
    values.update(overrides)
    return EvidenceBundle(**values)


def unexecuted_bundle(**overrides):
    values = {"route": "message_facts", "read_only_safeguards": closed_safeguards()}
    values.update(overrides)
    return EvidenceBundle(**values)


def success_result(**overrides):
    values = {
        "status": Status.SUCCESS,
        "evidence_bundle": executed_bundle(),
        "source_trace": SourceTrace(contributing_scopes=(scope(),)),
        "rows": ({"message_key": "SAMPLE_MSG_A", "transmit_mode": "SAMPLE_MODE_CYCLIC"},),
    }
    values.update(overrides)
    return Result(**values)
