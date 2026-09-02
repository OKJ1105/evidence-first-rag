"""Evidence-First RAG Runtime: the type surface of contract `mvp-v0.1`.

This package holds types and constants only. It opens no database, registers
no SQL template, routes no request, and renders no answer; each of those is a
later slice with its own Issue. What it fixes is the shape those slices are
written against, so that they agree by construction instead of informally.

Every type cites the Section of docs/contracts/mvp-v0.1.md it implements.
"""

from .contract import COLLATION, CONTRACT_IDENTIFIER, CONTRACT_VERSION
from .evidence import (
    EvidenceBundle,
    Limitation,
    LimitationKind,
    MappingProvenance,
    ProducingLayer,
    ReadOnlySafeguards,
    SourceTrace,
)
from .references import (
    SCOPE_DIMENSIONS,
    MessageReference,
    SignalReference,
    SnapshotScope,
)
from .result import REQUIRED_LIMITATION, Result, Row
from .routes import UNSUPPORTED_ROUTE, Route, route_field, route_name
from .status import OPENS_NO_CONNECTION, Status

__all__ = [
    "COLLATION",
    "CONTRACT_IDENTIFIER",
    "CONTRACT_VERSION",
    "EvidenceBundle",
    "Limitation",
    "LimitationKind",
    "MappingProvenance",
    "MessageReference",
    "OPENS_NO_CONNECTION",
    "ProducingLayer",
    "REQUIRED_LIMITATION",
    "ReadOnlySafeguards",
    "Result",
    "Route",
    "Row",
    "SCOPE_DIMENSIONS",
    "SignalReference",
    "SnapshotScope",
    "SourceTrace",
    "Status",
    "UNSUPPORTED_ROUTE",
    "route_field",
    "route_name",
]
