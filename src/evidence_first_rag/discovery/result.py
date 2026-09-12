"""entity-discovery-v0.1 Sections 5 and 7: the normalized discovery result.

The cross-field rules here are the ones Sections 5 and 7 state
unconditionally. `resolved` carries exactly one reference and no list;
`candidates` carries a non-empty list of at most `k`, a `candidate_set_id`,
and the "no reference was resolved" entry; `not_found` carries the "absence
from the registry is not absence from the data" entry; `coverage_gap` says
what could not be established; `unsupported` names its producing layer; and
the two statuses that open no connection have opened none.
"""

import dataclasses
import types

from ..evidence import ProducingLayer
from .candidate import AUTO_RESOLVABLE_TIERS, Candidate
from .evidence import DiscoveryEvidence, DiscoveryLimitation, DiscoveryLimitationKind, DiscoveryTrace
from .status import EXECUTES_NO_DISCOVERY_TEMPLATE, OPENS_NO_CONNECTION, DiscoveryStatus

DISCOVERY_ROUTE = "entity_discovery"
SELECTION_ROUTE = "entity_selection"

# Section 4.6: k = 10, fixed by the contract and not a caller argument.
K = 10

REQUIRED_LIMITATION = types.MappingProxyType(
    {
        DiscoveryStatus.CANDIDATES: DiscoveryLimitationKind.NO_REFERENCE_RESOLVED,
        DiscoveryStatus.NOT_FOUND: DiscoveryLimitationKind.NOT_IN_REGISTRY,
        DiscoveryStatus.COVERAGE_GAP: DiscoveryLimitationKind.COVERAGE_NOT_ESTABLISHED,
    }
)


@dataclasses.dataclass(frozen=True, kw_only=True)
class DiscoveryResult:
    status: DiscoveryStatus
    evidence_bundle: DiscoveryEvidence
    source_trace: DiscoveryTrace
    limitations: tuple[DiscoveryLimitation, ...] = ()
    resolved: Candidate | None = None
    candidates: tuple[Candidate, ...] = ()
    # Section 5 `ambiguous`: the candidate scopes, listed as mvp-v0.1 lists
    # them. Empty for every other status.
    candidate_scopes: tuple = ()

    def __post_init__(self) -> None:
        if not isinstance(self.status, DiscoveryStatus):
            raise ValueError("status must be a DiscoveryStatus")
        if not isinstance(self.evidence_bundle, DiscoveryEvidence):
            raise ValueError("evidence_bundle must be a DiscoveryEvidence")
        if not isinstance(self.source_trace, DiscoveryTrace):
            raise ValueError("source_trace must be a DiscoveryTrace")
        object.__setattr__(self, "limitations", _limitations(self.limitations))
        object.__setattr__(self, "candidates", _candidates(self.candidates))
        object.__setattr__(self, "candidate_scopes", tuple(self.candidate_scopes))
        bundle = self.evidence_bundle

        # Section 5's closing paragraph is about a discovery request. A
        # selection refused at step 4, 5 or 6 (Section 4.8) is also this
        # contract's `invalid_request`, and Section 7 requires it to report
        # the re-run it made, so for `route` = `entity_selection` an opened
        # connection and a cited registry state are what the contract asks
        # for rather than what it forbids.
        if bundle.route == DISCOVERY_ROUTE:
            if self.status in OPENS_NO_CONNECTION and bundle.read_only_safeguards.connection_opened:
                raise ValueError(f"{self.status.value} opens no database connection (Section 5)")
            if self.status in EXECUTES_NO_DISCOVERY_TEMPLATE and bundle.registry_digest != "":
                raise ValueError(f"{self.status.value} executes no discovery template, so it cites no registry state")

        if self.status is DiscoveryStatus.RESOLVED:
            if self.resolved is None or self.candidates:
                raise ValueError("resolved carries exactly one reference and no list (Section 5)")
            if self.resolved.match_tier not in AUTO_RESOLVABLE_TIERS:
                raise ValueError("only tier 1 or tier 2 may resolve (Section 4.7)")
            if bundle.match_tier != self.resolved.match_tier or bundle.matched_text != self.resolved.matched_text:
                raise ValueError("the bundle records the resolved match's tier and text (Section 7)")
            if bundle.candidate_set_id != "":
                raise ValueError("a resolved outcome carries no candidate_set_id (Section 4.8)")
            if self.source_trace.entity_approval_reference == "":
                raise ValueError("a resolved outcome traces the entity's approval_reference (Section 7)")
        else:
            if self.resolved is not None:
                raise ValueError(f"{self.status.value} resolves no reference")

        if self.status is DiscoveryStatus.CANDIDATES:
            if not self.candidates:
                raise ValueError("candidates carries at least one candidate (Section 5)")
            if len(self.candidates) > K:
                raise ValueError(f"a discovery result carries at most {K} candidates (Section 4.6)")
            if [c.rank for c in self.candidates] != list(range(1, len(self.candidates) + 1)):
                raise ValueError("ranks are 1-based positions in the list (Section 4.6)")
            if bundle.candidate_set_id == "" or bundle.candidate_count != len(self.candidates):
                raise ValueError("candidates carries candidate_set_id and its count (Sections 4.8 and 7)")
        elif self.candidates:
            raise ValueError(f"{self.status.value} carries no candidate list")

        if self.status is not DiscoveryStatus.AMBIGUOUS and self.candidate_scopes:
            raise ValueError("only ambiguous lists candidate scopes")

        if self.status is DiscoveryStatus.UNSUPPORTED and self.source_trace.producing_layer is None:
            raise ValueError("unsupported must record its producing layer (Section 7)")
        if self.status is not DiscoveryStatus.UNSUPPORTED and isinstance(self.source_trace.producing_layer, ProducingLayer):
            raise ValueError("only unsupported records a producing layer")

        required = REQUIRED_LIMITATION.get(self.status)
        if required is not None and not self.has_limitation(required):
            raise ValueError(f"{self.status.value} requires a {required.value} limitation (Section 7)")

    def has_limitation(self, kind: DiscoveryLimitationKind) -> bool:
        return any(limitation.kind is kind for limitation in self.limitations)


def _limitations(value: object) -> tuple[DiscoveryLimitation, ...]:
    if isinstance(value, str) or not hasattr(value, "__iter__"):
        raise ValueError("limitations must be an iterable of DiscoveryLimitation")
    items = tuple(value)
    for index, item in enumerate(items):
        if not isinstance(item, DiscoveryLimitation):
            raise ValueError(f"limitations[{index}] must be a DiscoveryLimitation")
    return items


def _candidates(value: object) -> tuple[Candidate, ...]:
    if isinstance(value, str) or not hasattr(value, "__iter__"):
        raise ValueError("candidates must be an iterable of Candidate")
    items = tuple(value)
    for index, item in enumerate(items):
        if not isinstance(item, Candidate):
            raise ValueError(f"candidates[{index}] must be a Candidate")
    return items
