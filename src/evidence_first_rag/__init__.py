"""Evidence-First RAG Runtime: the type surface of contract `mvp-v0.1`.

This module is the shape every slice is written against: the reference,
evidence, result, status, and route types, and the constants that name the
contract. The subpackages hold what executes -- `registry` the four fixed SQL
templates of Section 4.4, `runtime` the three routes and their outcomes, `db`
the provisioning path -- and none of them is imported from here, so importing
the type surface pulls in no driver and opens no connection.

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
from .routes import UNSUPPORTED_ROUTE, Route
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
]
