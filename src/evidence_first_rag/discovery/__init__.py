"""Contract `entity-discovery-v0.1`: the discovery route and what it shares
with the provisioning path.

Two pure modules are what `db/` and the route both need and neither may
define twice: the Section 4.5 normalization and the Section 4.2 canonical
JSON. Both are byte-defined, use no locale and no library default, so the
tokens the loader stores and the tokens the runtime binds come from one
function, and the digest provisioning writes and the digest a selection
re-derives come from one serializer.

The rest is the `entity_discovery` route (Sections 4.3 to 4.7, 5 and 7):
its request and validation, its candidate and evidence types, its seven
statuses, and `Discovery`, the object that answers a request over one
database through the same session port mvp-v0.1's runtime uses.

Nothing here imports a driver. `db/` imports the two pure modules, never the
other way round; `runtime/` is imported for the session port and the fault
types, and `registry/` for the templates.

Every function cites the Section of docs/contracts/entity-discovery-v0.1.md
it implements.
"""

from .candidate import AliasProvenance, Candidate
from .canonical import CanonicalError, canonical_json, sha256_hex
from .evaluation import CLASSES, REGISTERED_SET, EvaluationCase, authoring_failures
from .evidence import (
    CONTRACT_IDENTIFIER,
    CONTRACT_VERSION,
    METHOD_IDENTIFIER,
    METHOD_VERSION,
    DiscoveryEvidence,
    DiscoveryLimitation,
    DiscoveryLimitationKind,
    DiscoveryTrace,
)
from .judgement import Judgement, judge
from .metrics import CaseOutcome, Metrics, compute, per_class
from .normalize import normalize
from .request import DiscoveryRefusal, DiscoveryRequest, ValidatedDiscovery, validate
from .result import DISCOVERY_ROUTE, K, SELECTION_ROUTE, DiscoveryResult
from .selection import Selection, SelectionRequest, ValidatedSelection
from .service import Discovery, candidate_set_id
from .status import DiscoveryStatus

__all__ = [
    "AliasProvenance",
    "CLASSES",
    "CONTRACT_IDENTIFIER",
    "CONTRACT_VERSION",
    "Candidate",
    "CanonicalError",
    "CaseOutcome",
    "DISCOVERY_ROUTE",
    "Discovery",
    "DiscoveryEvidence",
    "DiscoveryLimitation",
    "DiscoveryLimitationKind",
    "DiscoveryRefusal",
    "DiscoveryRequest",
    "DiscoveryResult",
    "DiscoveryStatus",
    "DiscoveryTrace",
    "EvaluationCase",
    "Judgement",
    "K",
    "METHOD_IDENTIFIER",
    "METHOD_VERSION",
    "Metrics",
    "REGISTERED_SET",
    "SELECTION_ROUTE",
    "Selection",
    "SelectionRequest",
    "ValidatedDiscovery",
    "ValidatedSelection",
    "authoring_failures",
    "candidate_set_id",
    "canonical_json",
    "compute",
    "judge",
    "normalize",
    "per_class",
    "sha256_hex",
    "validate",
]
