"""Section 7 evidence obligations: the three structures every result carries.

Section 5 requires all three on every outcome, including every negative one,
and Section 7 fixes their fields. The empty-value rules are the delicate part
and are enforced here rather than described: Section 7 says `bound_parameters`
is empty when no template executed, and says so with a reason — the arguments
an adapter proposed and revalidation rejected are not parameters the runtime
bound, and reporting them as such would present a rejected proposal as a fact
the runtime acted on.

The key names `row_count` and `read_only_safeguards` are Charter vocabulary
kept verbatim, per the note under Section 7's `evidence_bundle` list.
"""

import dataclasses
import enum
import types
from collections.abc import Mapping

from ._validation import optional_text, required_flag, required_text, text_tuple
from .contract import COLLATION, CONTRACT_IDENTIFIER, CONTRACT_VERSION
from .references import SnapshotScope
from .routes import Route, route_field


class ProducingLayer(enum.Enum):
    """Which layer produced an `unsupported` outcome (Sections 5 and 7).

    Section 5 requires the trace to record it, and the two layers are the only
    two that can refuse a request as unrepresentable: the adapter, which sees
    free text, and the runtime, which sees a revalidated route.
    """

    ADAPTER = "adapter"
    RUNTIME = "runtime"


class LimitationKind(enum.Enum):
    """The five conditions Section 7 requires a `limitations` entry for.

    Section 7 names the conditions but not identifiers for them; these five
    are one-to-one with its list, in its order. The set is closed because
    Section 7's list is closed — adding a sixth is a contract change under
    Section 10, not a new enum member.
    """

    # "when any participating snapshot has a non-null `superseded_by`"
    SUPERSEDED_SNAPSHOT = "superseded_snapshot"
    # "when a result was truncated by a limit"
    TRUNCATED_BY_LIMIT = "truncated_by_limit"
    # "when scope was resolved to one candidate out of several by an explicit
    # user selection"
    SCOPE_SELECTED_BY_USER = "scope_selected_by_user"
    # "when the outcome is `coverage_gap`, stating what coverage could not be
    # established"
    COVERAGE_NOT_ESTABLISHED = "coverage_not_established"
    # "when the outcome is `needs_entity_discovery`, stating that Entity
    # Discovery is not implemented in v0.1"
    ENTITY_DISCOVERY_NOT_IMPLEMENTED = "entity_discovery_not_implemented"


@dataclasses.dataclass(frozen=True, kw_only=True)
class Limitation:
    """One entry in the `limitations` list.

    `detail` is required because every entry Section 7 requires has something
    to say: which snapshot is superseded, what was truncated, what coverage
    could not be established. An entry that names a kind and says nothing
    satisfies the letter of the list and none of its purpose.
    """

    kind: LimitationKind
    detail: str

    def __post_init__(self) -> None:
        if not isinstance(self.kind, LimitationKind):
            raise ValueError("kind must be a LimitationKind")
        required_text("detail", self.detail)


@dataclasses.dataclass(frozen=True, kw_only=True)
class ReadOnlySafeguards:
    """Section 7's `read_only_safeguards`: role name, transaction flag, and
    whether a connection was opened.

    Section 4.3 requires the runtime to open every connection with the runtime
    identity inside a read-only transaction, so these three values are what a
    reader checks to see that it did.
    """

    role_name: str
    read_only_transaction: bool
    connection_opened: bool

    def __post_init__(self) -> None:
        optional_text("role_name", self.role_name)
        required_flag("read_only_transaction", self.read_only_transaction)
        required_flag("connection_opened", self.connection_opened)
        # A connection that was never opened was never opened read-only, and
        # under no role. Recording either would claim a safeguard the runtime
        # did not take.
        if not self.connection_opened:
            if self.read_only_transaction:
                raise ValueError(
                    "read_only_transaction must be False when no connection was opened"
                )
            if self.role_name != "":
                raise ValueError(
                    "role_name must be empty when no connection was opened"
                )


@dataclasses.dataclass(frozen=True, kw_only=True)
class EvidenceBundle:
    """Section 7's `evidence_bundle`.

    `template_name`, `template_version`, and `resolved_scope` carry the
    "explicit empty value" Section 7 permits when no database was opened: the
    empty string for the two text fields, None for the scope. Both are values
    of a field that is always present, never an absent field.
    """

    route: Route | str
    read_only_safeguards: ReadOnlySafeguards
    row_count: int = 0
    template_name: str = ""
    template_version: str = ""
    bound_parameters: Mapping[str, object] = dataclasses.field(default_factory=dict)
    resolved_scope: SnapshotScope | None = None
    contract_identifier: str = CONTRACT_IDENTIFIER
    contract_version: str = CONTRACT_VERSION
    collation: str = COLLATION

    def __post_init__(self) -> None:
        object.__setattr__(self, "route", route_field(self.route))
        if not isinstance(self.read_only_safeguards, ReadOnlySafeguards):
            raise ValueError("read_only_safeguards must be a ReadOnlySafeguards")
        # bool is an int; a row_count of True would pass a bare int check.
        if not isinstance(self.row_count, int) or isinstance(self.row_count, bool):
            raise ValueError("row_count must be an int")
        if self.row_count < 0:
            raise ValueError("row_count must not be negative")
        optional_text("template_name", self.template_name)
        optional_text("template_version", self.template_version)
        if self.resolved_scope is not None and not isinstance(
            self.resolved_scope, SnapshotScope
        ):
            raise ValueError("resolved_scope must be a SnapshotScope or None")
        object.__setattr__(
            self, "bound_parameters", _frozen_parameters(self.bound_parameters)
        )
        required_text("contract_identifier", self.contract_identifier)
        required_text("contract_version", self.contract_version)
        required_text("collation", self.collation)

        # Section 7's empty-value rules, read together with Section 5's
        # closing paragraph. Nothing was executed, so nothing may be reported
        # as executed.
        if not self.read_only_safeguards.connection_opened:
            for field, value in (
                ("template_name", self.template_name),
                ("template_version", self.template_version),
            ):
                if value != "":
                    raise ValueError(
                        f"{field} must be empty when no database was opened"
                    )
            if self.resolved_scope is not None:
                raise ValueError(
                    "resolved_scope must be empty when no database was opened"
                )
            if self.bound_parameters:
                raise ValueError(
                    "bound_parameters must be empty when no template executed"
                )
            if self.row_count != 0:
                raise ValueError("row_count must be 0 when no database was opened")


def _frozen_parameters(value: object) -> Mapping[str, object]:
    """Copy a parameter mapping into one the bundle's holder cannot mutate.

    Section 7 requires `bound_parameters` to contain exactly the parameters
    bound. A bundle that shares a caller's dict can be edited after the fact,
    which would make the record of what was bound depend on who still holds a
    reference to it.
    """
    if not isinstance(value, Mapping):
        raise ValueError("bound_parameters must be a mapping")
    for name in value:
        required_text("bound_parameters key", name)
    return types.MappingProxyType(dict(value))


@dataclasses.dataclass(frozen=True, kw_only=True)
class MappingProvenance:
    """The three scopes one mapping row carries (Section 7, `source_trace`).

    Section 4.5 fixes one entry per asserting relation rather than one merged
    entry, because Charter Section 3.6 requires the asserting artifact's scope
    to travel with each relation. Separately named fields are what "separately
    identified" means here: a reader can tell which snapshot asserted the
    relation from which snapshots hold its endpoints.
    """

    asserting_scope: SnapshotScope
    source_endpoint_scope: SnapshotScope
    target_endpoint_scope: SnapshotScope

    def __post_init__(self) -> None:
        for field in (
            "asserting_scope",
            "source_endpoint_scope",
            "target_endpoint_scope",
        ):
            if not isinstance(getattr(self, field), SnapshotScope):
                raise ValueError(f"{field} must be a SnapshotScope")


@dataclasses.dataclass(frozen=True, kw_only=True)
class SourceTrace:
    """Section 7's `source_trace`.

    `fixture_provenance` names provenance that actually exists in this
    repository. Section 7 is explicit that a trace never cites a raw
    source-format artefact, because none exists here, so the field holds the
    registered fixture inputs of Section 4.11 and nothing else.
    """

    contributing_scopes: tuple[SnapshotScope, ...] = ()
    mapping_provenance: tuple[MappingProvenance, ...] = ()
    producing_layer: ProducingLayer | None = None
    fixture_provenance: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "contributing_scopes",
            _typed_tuple("contributing_scopes", self.contributing_scopes, SnapshotScope),
        )
        object.__setattr__(
            self,
            "mapping_provenance",
            _typed_tuple("mapping_provenance", self.mapping_provenance, MappingProvenance),
        )
        if self.producing_layer is not None and not isinstance(
            self.producing_layer, ProducingLayer
        ):
            raise ValueError("producing_layer must be a ProducingLayer or None")
        object.__setattr__(
            self, "fixture_provenance", text_tuple("fixture_provenance", self.fixture_provenance)
        )


def _typed_tuple(field: str, value: object, expected: type) -> tuple:
    if isinstance(value, str) or not hasattr(value, "__iter__"):
        raise ValueError(f"{field} must be an iterable of {expected.__name__}")
    items = tuple(value)
    for index, item in enumerate(items):
        if not isinstance(item, expected):
            raise ValueError(f"{field}[{index}] must be a {expected.__name__}")
    return items
