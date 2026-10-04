"""entity-discovery-v0.1 Section 4.8: the `entity_selection` route and the
verified selection path.

A `candidates` outcome is completed by an explicit selection, and the runtime
knows a selection is real because it **re-derives** the list the caller says
it chose from (step 2), recomputes the digest (step 3), and refuses unless it
matches (step 4). #17 rule 8 forbids a field that asserts provenance the
runtime cannot verify; this path is how a selection becomes provenance the
runtime did verify.

The seven steps, in the contract's order and numbering:

1. `target_route` is one of the three mvp-v0.1 routes, and `mapping_key`
   accompanies only `signal_mapping`. Before any connection.
2. The discovery request is re-executed -- through `service.discover`, the
   same code `entity_discovery` runs, so it cannot drift from it.
3. `candidate_set_id` is recomputed from the result.
4. Refused unless the re-run produced a candidate list whose digest equals
   the supplied one; a re-run that produced anything else is named in
   `limitations` (DX-023).
5. Refused unless `selected_rank` names a candidate in that list.
6. Refused unless the resolved candidate's `entity_kind` permits
   `target_route`.
7. The candidate's canonical reference -- and `mapping_key` when supplied --
   goes to `target_route` as an ordinary fully-scoped mvp-v0.1 request,
   through `Runtime.execute`, "which then runs entirely under that contract".

What comes back from step 7 is that contract's `Result`, plus exactly what
Section 4.8 adds: the `selection` record on the bundle, the selected
candidate's alias provenance and the entity's `approval_reference` on the
trace, and the explicit-selection entry in `limitations`.
"""

import dataclasses
import types
from collections.abc import Mapping, Sequence

from ..evidence import Limitation, LimitationKind
from ..references import SCOPE_DIMENSIONS
from ..result import Result
from ..routes import Route
from ..runtime import Request, Runtime
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
from .request import DiscoveryRefusal, DiscoveryRequest, ValidatedDiscovery
from .request import allowed_parameters as discovery_parameters
from .request import validate as validate_discovery
from .result import SELECTION_ROUTE, DiscoveryResult
from .service import candidate_set_id, discover, refused
from .status import DiscoveryStatus

# Section 4.8: which mvp-v0.1 routes a resolved candidate's kind permits.
PERMITTED_TARGETS = types.MappingProxyType(
    {
        "message": (Route.MESSAGE_FACTS,),
        "signal": (Route.SIGNAL_FACTS, Route.SIGNAL_MAPPING),
    }
)

SELECTION_ARGUMENTS = ("candidate_set_id", "selected_rank", "target_route", "mapping_key")


@dataclasses.dataclass(frozen=True, kw_only=True)
class SelectionRequest:
    """An `entity_selection` request. Untrusted until validated."""

    arguments: object = dataclasses.field(default_factory=dict)


@dataclasses.dataclass(frozen=True, kw_only=True)
class ValidatedSelection:
    """A request that passed step 1. The discovery half is a validated
    discovery request; the rest is what step 4 onwards reads."""

    discovery: ValidatedDiscovery
    candidate_set_id: str
    selected_rank: int
    target_route: Route
    mapping_key: str | None


def allowed_parameters() -> tuple[str, ...]:
    """Section 4.8's table: every discovery argument, plus the four."""
    return discovery_parameters() + SELECTION_ARGUMENTS


def validate(request: SelectionRequest) -> ValidatedSelection:
    """Step 1, and the discovery request's own Section 4.3 validation.

    Order: the allowlist; then the discovery half, exactly as
    `entity_discovery` validates it (an unsupported `entity_kind` is
    `unsupported` here too); then the selection arguments.
    """
    arguments = request.arguments
    if not isinstance(arguments, Mapping):
        raise DiscoveryRefusal(
            DiscoveryStatus.INVALID_REQUEST, f"arguments must be a mapping, not {type(arguments).__name__}"
        )
    for name in arguments:
        if not isinstance(name, str) or name == "":
            raise DiscoveryRefusal(DiscoveryStatus.INVALID_REQUEST, f"argument name {name!r} is not a non-empty string")
    allowed = allowed_parameters()
    unknown = sorted(set(arguments) - set(allowed))
    if unknown:
        raise DiscoveryRefusal(
            DiscoveryStatus.INVALID_REQUEST,
            f"argument(s) {unknown} are outside the allowlist {list(allowed)} for route"
            f" {SELECTION_ROUTE!r} (Section 4.8)",
        )
    discovery = validate_discovery(
        DiscoveryRequest(arguments={k: v for k, v in arguments.items() if k not in SELECTION_ARGUMENTS})
    )
    # #318: Section 4.8's argument table requires every scope dimension, and
    # a candidate set can only come from a complete scope. Refused here, so an
    # incomplete scope never reaches the step-2 re-run or a connection.
    if not discovery.scope_is_complete:
        missing_scope = [name for name in SCOPE_DIMENSIONS if name not in discovery.arguments]
        raise DiscoveryRefusal(
            DiscoveryStatus.INVALID_REQUEST,
            f"scope dimension(s) {missing_scope} are missing; {SELECTION_ROUTE!r} requires a complete"
            f" scope (Section 4.8)",
        )
    values = {name: _text(name, arguments[name]) for name in SELECTION_ARGUMENTS if name in arguments}
    missing = [name for name in ("candidate_set_id", "selected_rank", "target_route") if name not in values]
    if missing:
        raise DiscoveryRefusal(DiscoveryStatus.INVALID_REQUEST, f"required argument(s) {missing} are missing (Section 4.8)")

    target = Route.__members__.get(values["target_route"].upper()) if values["target_route"] in {r.value for r in Route} else None
    if target is None:
        raise DiscoveryRefusal(
            DiscoveryStatus.INVALID_REQUEST,
            f"target_route {values['target_route']!r} is not one of {[r.value for r in Route]}"
            f" (Section 4.8 step 1, fixture DX-022)",
        )
    if "mapping_key" in values and target is not Route.SIGNAL_MAPPING:
        raise DiscoveryRefusal(
            DiscoveryStatus.INVALID_REQUEST,
            "mapping_key is permitted only with target_route = signal_mapping"
            " (Section 4.8 step 1, fixture DX-022)",
        )
    rank_text = values["selected_rank"]
    # ASCII digits only. `str.isdigit` is true of superscripts and of every
    # other decimal script, so it alone would let "²" through to an
    # `int()` that raises, and would accept "٣" as a rank in a runtime
    # whose comparisons are byte-defined throughout (Section 4.5's
    # normalization, Section 7's `collation` = C).
    if not (rank_text.isascii() and rank_text.isdigit()) or int(rank_text) < 1:
        raise DiscoveryRefusal(
            DiscoveryStatus.INVALID_REQUEST, f"selected_rank {rank_text!r} is not a 1-based rank (Section 4.8)"
        )
    return ValidatedSelection(
        discovery=discovery,
        candidate_set_id=values["candidate_set_id"],
        selected_rank=int(rank_text),
        target_route=target,
        mapping_key=values.get("mapping_key"),
    )


def _cited(request: SelectionRequest) -> dict[str, str]:
    """What the caller cited, read off a request that never passed step 1.

    Section 7 requires a refused selection to name the `candidate_set_id`
    cited -- in that key, which is why the bundle's `candidate_set_id` is
    the caller's value on this route and not one the runtime derived -- the
    `selected_rank`, and the `target_route`. A step-1 refusal has
    only the untrusted request to read them from, so this reads exactly those
    three, only when each is non-empty text, and asserts nothing about them:
    a rank of "one" is recorded as "one", because that is what was cited.
    """
    arguments = request.arguments
    if not isinstance(arguments, Mapping):
        return {}
    cited = {}
    for name, field in (
        ("candidate_set_id", "candidate_set_id"),
        ("selected_rank", "selected_rank"),
        ("target_route", "target_route"),
    ):
        value = arguments.get(name)
        if isinstance(value, str) and value != "":
            cited[field] = value
    return cited


def _text(name: str, value: object) -> str:
    if isinstance(value, str):
        if value == "":
            raise DiscoveryRefusal(DiscoveryStatus.INVALID_REQUEST, f"argument {name!r} is the empty string")
        return value
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        raise DiscoveryRefusal(DiscoveryStatus.INVALID_REQUEST, f"argument {name!r} carries {len(value)} values")
    raise DiscoveryRefusal(DiscoveryStatus.INVALID_REQUEST, f"argument {name!r} must be a string, not {type(value).__name__}")


@dataclasses.dataclass(frozen=True, kw_only=True)
class Selection:
    """The `entity_selection` route, over one database."""

    database: object
    fixture_provenance: tuple[str, ...] = ()

    def execute(self, request: SelectionRequest) -> DiscoveryResult | Result:
        """Steps 1 to 7. A refusal is this contract's `invalid_request`; a
        dispatch is the mvp-v0.1 result of `target_route`."""
        try:
            validated = validate(request)
        except DiscoveryRefusal as refusal:
            # Step 1 opened no connection, but Section 7 still wants the
            # selection named.
            return refused(refusal, SELECTION_ROUTE, self.fixture_provenance, **_cited(request))

        # Step 2: the re-run, through the discovery route's own code.
        with self.database.session() as session:
            rerun = discover(session, validated.discovery, self.fixture_provenance)

        # Step 4, first half: a re-run that produced no list has nothing to
        # match against. Refused, naming what it produced (Section 7,
        # fixture DX-023).
        if rerun.status is not DiscoveryStatus.CANDIDATES:
            return self._refuse(
                validated,
                rerun,
                extra=DiscoveryLimitation(
                    kind=DiscoveryLimitationKind.RERUN_PRODUCED_NO_LIST,
                    detail=f"The re-run produced {rerun.status.value!r}. A candidate set computed"
                    f" against one registry state cannot be selected from against another"
                    f" (Section 4.8).",
                ),
            )
        # Step 3 is the digest the re-run's bundle already carries -- computed
        # by the same function over the recomputed list. Step 4, second half:
        # the registry state or the request differs from the one the list was
        # computed against (fixture DX-018).
        if rerun.evidence_bundle.candidate_set_id != validated.candidate_set_id:
            return self._refuse(validated, rerun)
        # Step 5: the rank names no candidate in the re-derived list
        # (fixture DX-019).
        if validated.selected_rank > len(rerun.candidates):
            return self._refuse(validated, rerun)
        chosen = rerun.candidates[validated.selected_rank - 1]
        # Step 6: against the candidate, which is not known until step 5
        # (fixture DX-021).
        if validated.target_route not in PERMITTED_TARGETS[chosen.entity_kind]:
            return self._refuse(validated, rerun)

        # Step 7: an ordinary fully-scoped mvp-v0.1 request.
        arguments = dict(chosen.reference.as_parameters())
        if validated.mapping_key is not None:
            arguments["mapping_key"] = validated.mapping_key
        result = Runtime(database=self.database, fixture_provenance=self.fixture_provenance).execute(
            Request(route=validated.target_route.value, arguments=arguments)
        )
        return _dispatched(result, rerun, validated, chosen)

    def _refuse(
        self,
        validated: ValidatedSelection,
        rerun: DiscoveryResult,
        extra: DiscoveryLimitation | None = None,
    ) -> DiscoveryResult:
        """This contract's `invalid_request`, reporting the re-run it made.

        Section 7 (as #88 amended it): a selection refused at step 4, 5 or 6
        still reports the re-run's template and bound parameters, so the
        bundle is the re-run's with the route renamed -- and carries, over
        that, the selection Section 7 requires a refusal to name. Its
        `candidate_set_id` becomes the digest the caller cited, which is what
        Section 7 assigns that key on a refusal; the digest the re-run derived
        is not a Section 7 key and is not recorded under another name. The re-run's
        own `limitations` travel with it, and they describe the re-run rather
        than this outcome. Which step refused is not itself an evidence field:
        Section 7's key list for a refused selection does not contain one, and
        `mvp-v0.1` records no reason on its own `invalid_request` either.
        """
        bundle = rerun.evidence_bundle
        limitations = list(rerun.limitations)
        if extra is not None:
            limitations.append(extra)
        return DiscoveryResult(
            status=DiscoveryStatus.INVALID_REQUEST,
            evidence_bundle=dataclasses.replace(
                bundle,
                route=SELECTION_ROUTE,
                candidate_set_id=validated.candidate_set_id,
                selected_rank=str(validated.selected_rank),
                target_route=validated.target_route.value,
            ),
            source_trace=rerun.source_trace,
            limitations=tuple(limitations),
        )


def _dispatched(result: Result, rerun: DiscoveryResult, validated: ValidatedSelection, chosen) -> Result:
    """Section 4.8: the mvp-v0.1 result plus exactly its enumerated additions."""
    bundle = rerun.evidence_bundle
    selection = {
        "contract_identifier": CONTRACT_IDENTIFIER,
        "contract_version": CONTRACT_VERSION,
        "registry_digest": bundle.registry_digest,
        "registry_built_at": bundle.registry_built_at,
        "method_identifier": METHOD_IDENTIFIER,
        "method_version": METHOD_VERSION,
        "candidate_set_id": bundle.candidate_set_id,
        "selected_rank": validated.selected_rank,
        "candidate_count": bundle.candidate_count,
        "target_route": validated.target_route.value,
        "discovery_template_name": bundle.template_name,
        "discovery_template_version": bundle.template_version,
        "discovery_bound_parameters": dict(bundle.bound_parameters),
        "discovery_row_count": bundle.row_count,
    }
    alias_provenance = ()
    if chosen.alias is not None:
        alias_provenance = (
            {
                "approval_reference": chosen.alias.approval_reference,
                "approved_at": chosen.alias.approved_at,
                **{name: getattr(chosen.alias.asserting_scope, name) for name in SCOPE_DIMENSIONS},
            },
        )
    entry = Limitation(
        kind=LimitationKind.SCOPE_SELECTED_BY_USER,
        detail=f"This reference was selected explicitly, at rank {validated.selected_rank} of"
        f" {bundle.candidate_count} candidates in candidate set {bundle.candidate_set_id},"
        f" and dispatched to {validated.target_route.value}. The selection was verified by"
        f" re-deriving the candidate set (entity-discovery-v0.1 Section 4.8).",
    )
    return dataclasses.replace(
        result,
        evidence_bundle=dataclasses.replace(result.evidence_bundle, selection=selection),
        source_trace=dataclasses.replace(
            result.source_trace,
            alias_provenance=alias_provenance,
            entity_approval_reference=chosen.entity_approval_reference,
        ),
        limitations=result.limitations + (entry,),
    )
