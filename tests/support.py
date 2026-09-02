"""Builders that keep the assertions in each test about one thing.

Every test needs a complete, valid result before it can break one field, and
spelling out a full evidence bundle in each one hides the assertion inside its
setup. These builders produce the contract-conforming default; a test passes
only the field it is about.
"""

from evidence_first_rag import (
    EvidenceBundle,
    ReadOnlySafeguards,
    Result,
    Route,
    SnapshotScope,
    SourceTrace,
    Status,
)

RUNTIME_ROLE = "SAMPLE_RUNTIME_ROLE"


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
        "route": Route.MESSAGE_FACTS,
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
    values = {"route": Route.MESSAGE_FACTS, "read_only_safeguards": closed_safeguards()}
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
