"""entity-discovery-v0.1 Section 7: the three structures every discovery
result carries.

Modelled on mvp-v0.1's `evidence.py` and kept separate from it for the same
reason `DiscoveryStatus` is separate from `Status`: this contract's list of
required limitation conditions is its own closed list, and its bundle carries
keys -- `registry_digest`, `method_identifier`, `candidate_set_id` -- that no
mvp-v0.1 result has.

Two contracts' identities are on the bundle. Section 7 requires
`contract_identifier` and `contract_version` "of this contract, and of
`mvp-v0.1`, whose registry safeguards the templates run under", and does not
fix the second pair's key names (#88 N3). This slice records them as
`runtime_contract_identifier` / `runtime_contract_version`; a registration
choice, stated on #143.
"""

import dataclasses
import enum
import types
from collections.abc import Mapping

from .._validation import optional_text, required_text, text_tuple
from ..contract import COLLATION
from ..contract import CONTRACT_IDENTIFIER as RUNTIME_CONTRACT_IDENTIFIER
from ..contract import CONTRACT_VERSION as RUNTIME_CONTRACT_VERSION
from ..evidence import ProducingLayer, ReadOnlySafeguards
from ..references import MessageReference, SnapshotScope
from .candidate import AliasProvenance

# Section 4.3 and Section 4.8: the two route names this contract registers.
# Defined here rather than in `result.py` because the bundle's own rules
# below depend on which of the two it belongs to.
DISCOVERY_ROUTE = "entity_discovery"
SELECTION_ROUTE = "entity_selection"

# entity-discovery-v0.1 Section 1.
CONTRACT_IDENTIFIER = "entity-discovery-v0.1"
CONTRACT_VERSION = "0.2.1"

# Section 4.9: the one registered method, and the version every result and
# every candidate-set digest carries.
METHOD_IDENTIFIER = "M-LEX-1"
METHOD_VERSION = "1"


class DiscoveryLimitationKind(enum.Enum):
    """Section 7's required `limitations` entries for discovery, in its order.

    The two selection-path entries (a reference reached a fact route through
    Section 4.8; a selection refused because its re-run produced no list) are
    here so the list is the contract's, and are produced by the selection
    slice.
    """

    TRUNCATED_BY_LIMIT = "truncated_by_limit"
    NO_REFERENCE_RESOLVED = "no_reference_resolved"
    NOT_IN_REGISTRY = "not_in_registry"
    SUPERSEDED_SNAPSHOT = "superseded_snapshot"
    SELECTED_VIA_CANDIDATES = "selected_via_candidates"
    RERUN_PRODUCED_NO_LIST = "rerun_produced_no_list"
    COVERAGE_NOT_ESTABLISHED = "coverage_not_established"


@dataclasses.dataclass(frozen=True, kw_only=True)
class DiscoveryLimitation:
    kind: DiscoveryLimitationKind
    detail: str

    def __post_init__(self) -> None:
        if not isinstance(self.kind, DiscoveryLimitationKind):
            raise ValueError("kind must be a DiscoveryLimitationKind")
        required_text("detail", self.detail)


@dataclasses.dataclass(frozen=True, kw_only=True)
class DiscoveryEvidence:
    """Section 7's `evidence_bundle` for a discovery result.

    The empty-value rules are mvp-v0.1 Section 7's, inherited: when no
    connection was opened nothing may be recorded as executed. One rule is
    this contract's own: `registry_digest` names the registry state a result
    was computed against, so it is present whenever a discovery template ran
    and absent (empty) whenever none did -- a result that cited a digest for
    a query it never made would be asserting a comparison nobody performed.
    """

    route: str
    read_only_safeguards: ReadOnlySafeguards
    row_count: int = 0
    template_name: str = ""
    template_version: str = ""
    bound_parameters: Mapping[str, object] = dataclasses.field(default_factory=dict)
    resolved_scope: SnapshotScope | None = None
    registry_digest: str = ""
    registry_built_at: str = ""
    method_identifier: str = ""
    method_version: str = ""
    match_tier: int | None = None
    matched_text: str = ""
    candidate_set_id: str = ""
    candidate_count: int = 0
    # Section 7, for a refused `entity_selection` (Section 4.8): "the
    # `candidate_set_id` cited, the `selected_rank`, and the `target_route`
    # named", so the refusal can be traced back to the request that produced
    # it. The cited digest goes in `candidate_set_id` itself, which is the
    # key Section 7 assigns it; a second key for it would be an evidence
    # field no contract text names, and Section 10 makes adding one a minor
    # version of this contract. These are the caller's own values -- nothing
    # the runtime bound or executed -- so a step-1 refusal that opened no
    # connection still records them.
    selected_rank: str = ""
    target_route: str = ""
    contract_identifier: str = CONTRACT_IDENTIFIER
    contract_version: str = CONTRACT_VERSION
    runtime_contract_identifier: str = RUNTIME_CONTRACT_IDENTIFIER
    runtime_contract_version: str = RUNTIME_CONTRACT_VERSION
    collation: str = COLLATION

    def __post_init__(self) -> None:
        required_text("route", self.route)
        if not isinstance(self.read_only_safeguards, ReadOnlySafeguards):
            raise ValueError("read_only_safeguards must be a ReadOnlySafeguards")
        _count("row_count", self.row_count)
        _count("candidate_count", self.candidate_count)
        for field in ("template_name", "template_version", "registry_digest", "registry_built_at",
                      "method_identifier", "method_version", "matched_text", "candidate_set_id",
                      "selected_rank", "target_route"):
            optional_text(field, getattr(self, field))
        if self.resolved_scope is not None and not isinstance(self.resolved_scope, SnapshotScope):
            raise ValueError("resolved_scope must be a SnapshotScope or None")
        if self.match_tier is not None and (
            not isinstance(self.match_tier, int) or isinstance(self.match_tier, bool)
            or not 1 <= self.match_tier <= 4
        ):
            raise ValueError("match_tier is 1, 2, 3 or 4, or None")
        object.__setattr__(self, "bound_parameters", _frozen(self.bound_parameters))
        for field in ("contract_identifier", "contract_version", "runtime_contract_identifier",
                      "runtime_contract_version", "collation"):
            required_text(field, getattr(self, field))

        # On `entity_selection`, `candidate_set_id` is the digest the caller
        # cited, not one this runtime derived, so it survives both rules
        # below: a step-1 refusal opens no connection and still records it
        # (Section 7), and it is paired with no candidate_count because the
        # list it names was not returned by this result.
        cites_rather_than_derives = self.route == SELECTION_ROUTE
        empty_when_closed = ["template_name", "template_version", "registry_digest",
                             "registry_built_at", "matched_text"]
        if not cites_rather_than_derives:
            empty_when_closed.append("candidate_set_id")
        if not self.read_only_safeguards.connection_opened:
            for field in empty_when_closed:
                if getattr(self, field) != "":
                    raise ValueError(f"{field} must be empty when no database was opened")
            if self.resolved_scope is not None or self.bound_parameters or self.row_count:
                raise ValueError("nothing may be recorded as executed when no database was opened")
        # The digest and the method travel together: both name what the
        # registry-backed comparison ran against, and neither means anything
        # without the other.
        if (self.registry_digest == "") != (self.method_identifier == ""):
            raise ValueError("registry_digest and method_identifier are recorded together")
        if (self.method_identifier == "") != (self.method_version == ""):
            raise ValueError("method_identifier and method_version are recorded together")
        if not cites_rather_than_derives and (self.candidate_set_id == "") != (self.candidate_count == 0):
            raise ValueError("candidate_set_id and candidate_count are recorded together")
        if (self.match_tier is None) != (self.matched_text == ""):
            raise ValueError("match_tier and matched_text are recorded together")


def _count(field: str, value: object) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{field} must be a non-negative int")


def _frozen(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError("bound_parameters must be a mapping")
    for name in value:
        required_text("bound_parameters key", name)
    return types.MappingProxyType(dict(value))


@dataclasses.dataclass(frozen=True, kw_only=True)
class DiscoveryTrace:
    """Section 7's `source_trace` for a discovery result.

    - `resolved_scope`: the snapshot every returned reference belongs to.
    - `parent_messages`: for each signal reference returned, the parent
      Message occurrence, "separately identified".
    - `alias_provenance`: for every tier-2 match and every candidate whose
      `match_kind` is not `lookup_key`.
    - `entity_approval_reference`: the entity's own, for a `resolved` outcome.
    - `producing_layer`: for `unsupported`.
    - `fixture_provenance`: what actually exists; never a raw source artefact.
    """

    resolved_scope: SnapshotScope | None = None
    contributing_scopes: tuple[SnapshotScope, ...] = ()
    parent_messages: tuple[MessageReference, ...] = ()
    alias_provenance: tuple[AliasProvenance, ...] = ()
    entity_approval_reference: str = ""
    producing_layer: ProducingLayer | None = None
    fixture_provenance: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.resolved_scope is not None and not isinstance(self.resolved_scope, SnapshotScope):
            raise ValueError("resolved_scope must be a SnapshotScope or None")
        object.__setattr__(self, "contributing_scopes", _typed("contributing_scopes", self.contributing_scopes, SnapshotScope))
        object.__setattr__(self, "parent_messages", _typed("parent_messages", self.parent_messages, MessageReference))
        object.__setattr__(self, "alias_provenance", _typed("alias_provenance", self.alias_provenance, AliasProvenance))
        optional_text("entity_approval_reference", self.entity_approval_reference)
        if self.producing_layer is not None and not isinstance(self.producing_layer, ProducingLayer):
            raise ValueError("producing_layer must be a ProducingLayer or None")
        object.__setattr__(self, "fixture_provenance", text_tuple("fixture_provenance", self.fixture_provenance))


def _typed(field: str, value: object, expected: type) -> tuple:
    if isinstance(value, str) or not hasattr(value, "__iter__"):
        raise ValueError(f"{field} must be an iterable of {expected.__name__}")
    items = tuple(value)
    for index, item in enumerate(items):
        if not isinstance(item, expected):
            raise ValueError(f"{field}[{index}] must be a {expected.__name__}")
    return items
