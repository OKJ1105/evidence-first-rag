"""Row builders for the discovery tests that run over `runtime_support`'s
fake database.

The fake runs the registered template's real `bind`, so Section 4.4's
allowlist and required-parameter refusals are exercised; rows come back
because a test supplied them. What these tests prove is the route's
decisions -- which template it reaches for, what it binds, which status it
assigns and what evidence it assembles -- and `tests_database/
test_discovery_fixtures.py` proves the rows against a real database.
"""

import datetime

from evidence_first_rag import SCOPE_DIMENSIONS
from evidence_first_rag.registry import get

from .runtime_support import BASE, CHASSIS, CHASSIS_B, REVISED, FakeDatabase, candidate_row  # noqa: F401

STATE_ROW = {
    "registry_digest": "a" * 64,
    "built_at": datetime.datetime(2026, 9, 12, 0, 0, 0),
}


def discovery_row(
    scope=None,
    *,
    entity_kind="message",
    message_key="SAMPLE_MSG_ENGINE_STATUS",
    signal_key=None,
    match_tier=1,
    match_kind="lookup_key",
    match_text=None,
    superseded_by=None,
    template="TPL_DISCOVERY_EXACT_V1",
    **overrides,
):
    """One row as either discovery template returns it. An alias row carries
    the provenance columns; a lookup-key row carries nulls there."""
    scope = scope or BASE
    values = {
        **scope,
        "entity_kind": entity_kind,
        "message_key": message_key,
        "signal_key": signal_key,
        "match_tier": match_tier,
        "match_kind": match_kind,
        "match_text": match_text if match_text is not None else (signal_key or message_key),
        "entity_approval_reference": "SAMPLE_APPROVAL_M3_001",
        "alias_approval_reference": None if match_kind == "lookup_key" else "SAMPLE_APPROVAL_M3_101",
        "alias_approved_at": None if match_kind == "lookup_key" else datetime.datetime(2026, 3, 5),
        **{f"alias_{name}": (None if match_kind == "lookup_key" else scope[name]) for name in SCOPE_DIMENSIONS},
        **{f"superseded_by_{name}": (None if superseded_by is None else superseded_by[name]) for name in SCOPE_DIMENSIONS},
        **overrides,
    }
    columns = get(template).result_columns
    unknown = sorted(set(values) - set(columns))
    assert not unknown, f"{template} has no column(s) {unknown}"
    return {column: values.get(column) for column in columns}


def database(*, candidates=(candidate_row(),), state=(STATE_ROW,), exact=(), lexical=(), **kwargs):
    return FakeDatabase(
        {
            "TPL_SNAPSHOT_CANDIDATES_V1": tuple(candidates),
            "TPL_REGISTRY_STATE_V1": tuple(state),
            "TPL_DISCOVERY_EXACT_V1": tuple(exact),
            "TPL_DISCOVERY_LEXICAL_V1": tuple(lexical),
        },
        **kwargs,
    )


MESSAGE = BASE | {"entity_kind": "message", "term": "SAMPLE_MSG_ENGINE_STATUS"}
SIGNAL = BASE | {"entity_kind": "signal", "term": "SAMPLE_SIG_TEMPERATURE"}
