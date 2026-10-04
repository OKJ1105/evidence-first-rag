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
from .evidence import (
    DISCOVERY_ROUTE,
    SELECTION_ROUTE,
    DiscoveryEvidence,
    DiscoveryLimitation,
    DiscoveryLimitationKind,
    DiscoveryTrace,
)
from .status import EXECUTES_NO_DISCOVERY_TEMPLATE, OPENS_NO_CONNECTION, DiscoveryStatus

__all__ = ["DISCOVERY_ROUTE", "SELECTION_ROUTE", "K", "DiscoveryResult"]

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
    # Section 5 `ambiguous`: since `0.4.0`, the candidate scopes in which the
    # term matched, or every candidate scope above the Section 4.3 bound.
    # Empty for every other status.
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
        #
        # Stated as "anything that is not the selection route", not as "the
        # discovery route": a rule that named only `entity_discovery` would
        # let an unknown route string skip all three checks, and these are
        # construction errors precisely so that no path can forget them.
        if bundle.route != SELECTION_ROUTE:
            if self.status in OPENS_NO_CONNECTION and bundle.read_only_safeguards.connection_opened:
                raise ValueError(f"{self.status.value} opens no database connection (Section 5)")
            if self.status in EXECUTES_NO_DISCOVERY_TEMPLATE and bundle.registry_digest != "":
                raise ValueError(f"{self.status.value} executes no discovery template, so it cites no registry state")
            # Section 7 records the cited selection on a refused selection.
            # A discovery result has no selection to cite, so carrying one
            # would be a claim about a request nobody made.
            for field in ("selected_rank", "target_route"):
                if getattr(bundle, field) != "":
                    raise ValueError(f"{field} belongs to a refused {SELECTION_ROUTE} (Section 7)")
        else:
            # The selection route's own Section 5 and 4.8 rules, which the
            # branch above cannot state because they are about a different
            # shape of outcome.
            #
            # `unsupported` on this route can come only from `validate()`,
            # which runs before any session (Section 4.8 step 1).
            if self.status is DiscoveryStatus.UNSUPPORTED and bundle.read_only_safeguards.connection_opened:
                raise ValueError(f"{SELECTION_ROUTE} refuses an unsupported request before any connection (Section 4.8 step 1)")
            # And a refusal is internally consistent: either it opened
            # nothing and executed nothing, or it opened a connection and
            # reports the re-run it made (Section 7, as #88 amended it).
            # A re-run that executed no discovery template -- a coverage
            # gap, or an incomplete scope above the Section 4.3 bound --
            # read no registry state, so it reports its template and an
            # empty digest (#318); one that did reports both.
            executed = (bundle.template_name != "", bundle.registry_digest != "")
            if bundle.read_only_safeguards.connection_opened:
                if not executed[0]:
                    raise ValueError(
                        f"a {SELECTION_ROUTE} outcome that opened a connection reports the re-run's"
                        f" template (Section 7)"
                    )
            elif any(executed):
                raise ValueError("nothing may be recorded as executed when no database was opened")

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

        # `0.4.0`, Sections 4.3 and 7: the incomplete-scope search.
        search = bundle.scope_search
        if self.status is DiscoveryStatus.AMBIGUOUS and search is None:
            raise ValueError("ambiguous records its scope_search (Section 7)")
        if search is not None:
            if self.status not in (DiscoveryStatus.AMBIGUOUS, DiscoveryStatus.NOT_FOUND):
                raise ValueError(f"{self.status.value} is not reached through an incomplete scope")
            if search.searched != (bundle.registry_digest != ""):
                raise ValueError("an incomplete scope cites the registry state exactly when the term was searched")
            if self.status is DiscoveryStatus.NOT_FOUND:
                if not search.searched or search.matched_scopes:
                    raise ValueError("not_found through an incomplete scope searched every candidate scope and matched in none")
            elif search.searched:
                if not search.matched_scopes or self.candidate_scopes != search.matched_scopes:
                    raise ValueError("a searched ambiguous lists exactly the scopes where the term matched (Section 4.3)")
            elif len(self.candidate_scopes) != search.candidate_scope_count:
                raise ValueError("an unsearched ambiguous lists every candidate scope (Section 4.3)")
            needed = (
                DiscoveryLimitationKind.SCOPES_SEARCHED if search.searched
                else DiscoveryLimitationKind.SCOPES_NOT_SEARCHED
            )
            if not self.has_limitation(needed):
                raise ValueError(f"an incomplete scope requires a {needed.value} limitation (Section 7)")

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
