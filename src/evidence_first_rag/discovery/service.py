"""The `entity_discovery` route: one request in, one discovery result out.

entity-discovery-v0.1 Sections 4.3 to 4.7, 5 and 7, in the order the
contract puts them:

1. Validate (`request.py`). Section 4.3: before any database access. Two
   statuses are decided here, and both open no connection.
2. Resolve scope, with the mvp-v0.1 candidate query unchanged (Section 4.3:
   "scope is a precondition, not a search dimension"). No candidate scope
   is `coverage_gap`. An incomplete scope is `ambiguous`; since `0.4.0`,
   within the bound of ten it is searched scope by scope with the same
   method (steps 3 and 4), and the scopes where the term matched are listed,
   or `not_found` when it matched in none.
3. Read the registry state (`TPL_REGISTRY_STATE_V1`), so the result names
   the state it was computed against.
4. Run `TPL_DISCOVERY_EXACT_V1`; if it returns nothing, run
   `TPL_DISCOVERY_LEXICAL_V1` (Section 4.9's `M-LEX-1`). Section 4.7 then
   decides `resolved`, `candidates`, or `not_found`.
5. Assemble Section 7's three structures around whichever came out.

The database is reached through the same session port mvp-v0.1's runtime
uses (`runtime/execution.py`), so this module imports no driver and the
decision path runs from a clean checkout; `tests_database/` runs the same
code against a real database loaded from `fixtures/`.
"""

import dataclasses

from ..evidence import ReadOnlySafeguards
from ..references import SCOPE_DIMENSIONS, MessageReference, SignalReference, SnapshotScope
from ..registry import get
from ..runtime.faults import DataFault
from .candidate import AliasProvenance, Candidate
from .canonical import canonical_json, sha256_hex
from .evidence import (
    CONTRACT_IDENTIFIER,
    CONTRACT_VERSION,
    METHOD_IDENTIFIER,
    METHOD_VERSION,
    DiscoveryEvidence,
    DiscoveryLimitation,
    DiscoveryLimitationKind,
    DiscoveryTrace,
    SCOPE_SEARCH_BOUND,
    ScopeSearch,
    ScopeSearchEntry,
)
from .request import (
    CANDIDATES_TEMPLATE,
    EXACT_TEMPLATE,
    LEXICAL_TEMPLATE,
    ROUTE,
    STATE_TEMPLATE,
    DiscoveryRefusal,
    DiscoveryRequest,
    ValidatedDiscovery,
    validate,
)
from .result import K, DiscoveryResult
from .status import DiscoveryStatus

# Section 7's fixed sentences, stated once. The obligation is to say these
# things, not to paraphrase them per request.
NO_REFERENCE_RESOLVED = (
    "No reference was resolved: the term matched more than one approved entity,"
    " or matched only below tier 2, and Section 4.7 permits no automatic choice"
    " among candidates. An explicit selection is required (Section 4.8)."
)
SCOPES_LISTED = (
    "The listed scopes are those in which an approved entity matched the term"
    " at some tier (Section 4.3). No scope and no entity was selected: choose a"
    " scope and discover again in it to see the candidates there."
)
NOT_IN_REGISTRY = (
    "No approved entity matched the term at any tier. Absence from the approved"
    " registry is not absence from the data: the registry is an allowlist"
    " (Section 4.2), and this result establishes nothing about what the loaded"
    " data contains."
)


@dataclasses.dataclass(frozen=True, kw_only=True)
class Discovery:
    """The `entity_discovery` route, over one database.

    `fixture_provenance` is recorded on every trace and never discovered,
    for the reason mvp-v0.1's `Runtime` gives: only whoever provisioned the
    database knows what it was loaded from.
    """

    database: object
    fixture_provenance: tuple[str, ...] = ()

    def execute(self, request: DiscoveryRequest) -> DiscoveryResult:
        try:
            validated = validate(request)
        except DiscoveryRefusal as refusal:
            return refused(refusal, ROUTE, self.fixture_provenance)
        return self._answer(validated)

    # -- the path that opens a connection -------------------------------

    def _answer(self, request: ValidatedDiscovery) -> DiscoveryResult:
        with self.database.session() as session:
            return discover(session, request, self.fixture_provenance)


def discover(session, request: ValidatedDiscovery, fixture_provenance: tuple[str, ...] = ()) -> DiscoveryResult:
    """Steps 2 to 5 of the module docstring over one open session.

    Module-level rather than a method so that Section 4.8's step 2 -- "re-
    executes the discovery request deterministically" -- is literally the
    same code the `entity_discovery` route runs, not a second implementation
    that could drift from it.
    """
    safeguards = ReadOnlySafeguards(
        role_name=session.role_name,
        read_only_transaction=session.read_only_transaction,
        connection_opened=True,
    )
    # Section 4.3: the mvp-v0.1 candidate query, "exactly as it
    # stands", on every request, complete scope included -- it is
    # what tells coverage_gap from not_found.
    candidates_template = get(CANDIDATES_TEMPLATE)
    found = session.execute(candidates_template, request.scope_arguments)
    scopes = tuple(
        SnapshotScope(**{name: row[name] for name in SCOPE_DIMENSIONS}) for row in found.rows
    )
    if not scopes:
        return _coverage_gap(request, safeguards, found, candidates_template, fixture_provenance)
    if not request.scope_is_complete:
        if len(scopes) > SCOPE_SEARCH_BOUND:
            return _ambiguous(request, safeguards, found, scopes, candidates_template, fixture_provenance)
        return _search_scopes(request, safeguards, session, found, scopes, candidates_template, fixture_provenance)
    if len(scopes) != 1:
        raise DataFault(
            f"a complete scope matched {len(scopes)} snapshots; mvp-v0.1 Section 4.1"
            f" makes the four dimensions unique"
        )
    scope = scopes[0]

    registry_digest, registry_built_at = _registry_state(session)
    template, run = _run_method(session, request, dict(request.arguments))
    return _decide(request, safeguards, scope, registry_digest, registry_built_at, template, run, fixture_provenance)


def _decide(request, safeguards, scope, registry_digest, registry_built_at, template, run, fixture_provenance) -> DiscoveryResult:
    """Section 4.7 over what the templates returned, and Section 7 around it."""
    rows = run.rows
    truncated = template.truncated(len(rows))
    listed = rows[:K]
    candidates = tuple(_candidate(rank, row) for rank, row in enumerate(listed, 1))
    limitations = list(_superseded(rows))

    common = dict(
        route=ROUTE,
        read_only_safeguards=safeguards,
        row_count=len(rows),
        template_name=template.name,
        template_version=template.version,
        bound_parameters=run.bound_parameters,
        resolved_scope=scope,
        registry_digest=registry_digest,
        registry_built_at=registry_built_at,
        method_identifier=METHOD_IDENTIFIER,
        method_version=METHOD_VERSION,
    )
    trace = dict(
        resolved_scope=scope,
        contributing_scopes=(scope,) if rows else (),
        parent_messages=tuple(
            c.reference.message for c in candidates if c.entity_kind == "signal"
        ),
        alias_provenance=tuple(c.alias for c in candidates if c.alias is not None),
        fixture_provenance=fixture_provenance,
    )

    if not rows:
        limitations.append(
            DiscoveryLimitation(kind=DiscoveryLimitationKind.NOT_IN_REGISTRY, detail=NOT_IN_REGISTRY)
        )
        return DiscoveryResult(
            status=DiscoveryStatus.NOT_FOUND,
            evidence_bundle=DiscoveryEvidence(**common),
            source_trace=DiscoveryTrace(**trace),
            limitations=tuple(limitations),
        )

    # Section 4.7: E(T) is the set of entities matching at tier 1 or 2.
    # The exact template returns exactly those, one row per entity; the
    # lexical template runs only when E(T) is empty. So a single exact
    # row is a unique tier-1-or-2 match, and everything else abstains.
    one = candidates[0]
    if len(rows) == 1 and one.match_tier in (1, 2):
        return DiscoveryResult(
            status=DiscoveryStatus.RESOLVED,
            evidence_bundle=DiscoveryEvidence(
                **common, match_tier=one.match_tier, matched_text=one.matched_text
            ),
            source_trace=DiscoveryTrace(**trace, entity_approval_reference=one.entity_approval_reference),
            limitations=tuple(limitations),
            resolved=one,
        )

    if truncated:
        limitations.append(
            DiscoveryLimitation(
                kind=DiscoveryLimitationKind.TRUNCATED_BY_LIMIT,
                detail=f"{template.name} returned more than {K} matching entities; the list"
                f" is truncated to {K} and further matches exist and were not returned"
                f" (Sections 4.4 and 4.6).",
            )
        )
    limitations.append(
        DiscoveryLimitation(kind=DiscoveryLimitationKind.NO_REFERENCE_RESOLVED, detail=NO_REFERENCE_RESOLVED)
    )
    return DiscoveryResult(
        status=DiscoveryStatus.CANDIDATES,
        evidence_bundle=DiscoveryEvidence(
            **common,
            candidate_set_id=candidate_set_id(request, registry_digest, candidates),
            candidate_count=len(candidates),
        ),
        source_trace=DiscoveryTrace(**trace),
        limitations=tuple(limitations),
        candidates=candidates,
    )

def _registry_state(session):
    state = session.execute(get(STATE_TEMPLATE), {})
    if len(state.rows) != 1:
        raise DataFault(
            f"entity_registry_state holds {len(state.rows)} rows; Section 4.1 requires"
            f" exactly one after provisioning"
        )
    return state.rows[0]["registry_digest"], _timestamp(state.rows[0]["built_at"])


def _run_method(session, request, arguments):
    """Section 4.9 M-LEX-1 over one scope: exact for tiers 1 and 2, then
    lexical for tiers 3 and 4 when E(T) is empty. `arguments` carries the
    four scope dimensions it runs in."""
    template = get(EXACT_TEMPLATE)
    run = session.execute(template, arguments)
    if not run.rows:
        template = get(LEXICAL_TEMPLATE)
        run = session.execute(
            template,
            {
                **{k: v for k, v in arguments.items() if k != "term"},
                "normalized_term": list(request.normalized_term),
            },
        )
    return template, run


def _search_scopes(request, safeguards, session, found, scopes, candidates_template, fixture_provenance):
    """Section 4.3 (`0.4.0`): an incomplete scope within the bound, searched in
    each candidate scope with the request's other arguments, exactly as a
    fully scoped request naming that scope would run. Nothing is resolved."""
    registry_digest, registry_built_at = _registry_state(session)
    entries = []
    for scope in scopes:
        arguments = {**request.arguments, **{name: getattr(scope, name) for name in SCOPE_DIMENSIONS}}
        template, run = _run_method(session, request, arguments)
        rows = run.rows
        entries.append(
            ScopeSearchEntry(
                scope=scope,
                matched=bool(rows),
                match_tier=min(int(row["match_tier"]) for row in rows) if rows else None,
                match_count=len(rows),
                template_name=template.name,
                template_version=template.version,
                bound_parameters=run.bound_parameters,
            )
        )
    search = ScopeSearch(candidate_scope_count=len(scopes), searched=True, scopes=tuple(entries), bound=SCOPE_SEARCH_BOUND)
    matched = search.matched_scopes
    evidence = DiscoveryEvidence(
        route=ROUTE,
        read_only_safeguards=safeguards,
        row_count=len(found.rows),
        template_name=candidates_template.name,
        template_version=candidates_template.version,
        bound_parameters=found.bound_parameters,
        resolved_scope=None,
        registry_digest=registry_digest,
        registry_built_at=registry_built_at,
        method_identifier=METHOD_IDENTIFIER,
        method_version=METHOD_VERSION,
        scope_search=search,
    )
    trace = DiscoveryTrace(contributing_scopes=scopes, fixture_provenance=fixture_provenance)
    if matched:
        return DiscoveryResult(
            status=DiscoveryStatus.AMBIGUOUS,
            evidence_bundle=evidence,
            source_trace=trace,
            limitations=(
                DiscoveryLimitation(kind=DiscoveryLimitationKind.SCOPES_SEARCHED, detail=SCOPES_LISTED),
            ),
            candidate_scopes=matched,
        )
    return DiscoveryResult(
        status=DiscoveryStatus.NOT_FOUND,
        evidence_bundle=evidence,
        source_trace=trace,
        limitations=(
            DiscoveryLimitation(
                kind=DiscoveryLimitationKind.SCOPES_SEARCHED,
                detail=f"The term was searched in all {len(scopes)} candidate scopes of the"
                f" incomplete scope, and matched in none (Section 4.3).",
            ),
            DiscoveryLimitation(kind=DiscoveryLimitationKind.NOT_IN_REGISTRY, detail=NOT_IN_REGISTRY),
        ),
    )


def _coverage_gap(request, safeguards, found, template, fixture_provenance) -> DiscoveryResult:
    named = ", ".join(
        f"{name}={request.arguments[name]}" for name in SCOPE_DIMENSIONS if name in request.arguments
    )
    return _scope_only(
        request, safeguards, found, template, DiscoveryStatus.COVERAGE_GAP, fixture_provenance,
        (
            DiscoveryLimitation(
                kind=DiscoveryLimitationKind.COVERAGE_NOT_ESTABLISHED,
                detail=f"no snapshot in the approved data scope matches {named}, so the"
                f" coverage this request needs could not be established (Sections 4.3 and 5).",
            ),
        ),
    )

def _ambiguous(request, safeguards, found, scopes, template, fixture_provenance) -> DiscoveryResult:
    """Above the Section 4.3 bound: every candidate scope listed, the term
    searched in none."""
    limitations = (
        DiscoveryLimitation(
            kind=DiscoveryLimitationKind.SCOPES_NOT_SEARCHED,
            detail=f"The incomplete scope has {len(scopes)} candidate scopes, more than the bound of"
            f" {SCOPE_SEARCH_BOUND}, so every candidate scope is listed and the term was searched in"
            f" none (Section 4.3).",
        ),
    )
    if template.truncated(len(found.rows)):
        limitations += (
            DiscoveryLimitation(
                kind=DiscoveryLimitationKind.TRUNCATED_BY_LIMIT,
                detail=f"{template.name} returned its registered limit of {template.row_limit}"
                f" candidate scopes; further candidates exist and are not listed.",
            ),
        )
    return _scope_only(
        request, safeguards, found, template, DiscoveryStatus.AMBIGUOUS, fixture_provenance, limitations, scopes,
        scope_search=ScopeSearch(candidate_scope_count=len(scopes), searched=False, bound=SCOPE_SEARCH_BOUND),
    )


def _scope_only(request, safeguards, found, template, status, fixture_provenance, limitations, scopes=(), scope_search=None):
    """An outcome the mvp-v0.1 candidate query decided alone: no discovery
    template executed, so no registry state is cited (Section 5)."""
    return DiscoveryResult(
        status=status,
        evidence_bundle=DiscoveryEvidence(
            route=ROUTE,
            read_only_safeguards=safeguards,
            row_count=len(found.rows),
            template_name=template.name,
            template_version=template.version,
            bound_parameters=found.bound_parameters,
            resolved_scope=None,
            scope_search=scope_search,
        ),
        source_trace=DiscoveryTrace(contributing_scopes=scopes, fixture_provenance=fixture_provenance),
        limitations=limitations,
        candidate_scopes=scopes,
    )


def refused(
    refusal: DiscoveryRefusal, route: str, fixture_provenance: tuple[str, ...], **citation: str
) -> DiscoveryResult:
    """A request refused before any connection: Section 5's two no-connection
    statuses, with every execution field the explicit empty value.

    `citation` is what a refused `entity_selection` records over and above
    that (Section 7): the values the caller cited. None of them is something
    the runtime bound or executed, so recording them does not weaken the
    empty-value rule above. `entity_discovery` has nothing to cite and passes
    none.
    """
    return DiscoveryResult(
        status=refusal.status,
        evidence_bundle=DiscoveryEvidence(
            route=route,
            read_only_safeguards=ReadOnlySafeguards(
                role_name="", read_only_transaction=False, connection_opened=False
            ),
            **citation,
        ),
        source_trace=DiscoveryTrace(
            producing_layer=refusal.producing_layer, fixture_provenance=fixture_provenance
        ),
    )


def candidate_set_id(request: ValidatedDiscovery, registry_digest: str, candidates) -> str:
    """Section 4.8's candidate-set digest: exactly these keys, canonical JSON."""
    return sha256_hex(
        canonical_json(
            {
                "contract_identifier": CONTRACT_IDENTIFIER,
                "contract_version": CONTRACT_VERSION,
                "registry_digest": registry_digest,
                **{name: request.arguments[name] for name in SCOPE_DIMENSIONS},
                "entity_kind": request.entity_kind,
                "parent_message_key": request.parent_message_key,
                "term": request.term,
                "method_identifier": METHOD_IDENTIFIER,
                "method_version": METHOD_VERSION,
                "candidates": [c.digest_fields() for c in candidates],
            }
        )
    )


def _candidate(rank: int, row) -> Candidate:
    scope = SnapshotScope(**{name: row[name] for name in SCOPE_DIMENSIONS})
    message = MessageReference(scope=scope, message_key=row["message_key"])
    kind = row["entity_kind"]
    reference = message if kind == "message" else SignalReference(message=message, signal_key=row["signal_key"])
    alias = None
    if row["match_kind"] != "lookup_key":
        alias = AliasProvenance(
            approval_reference=row["alias_approval_reference"],
            approved_at=_timestamp(row["alias_approved_at"]),
            asserting_scope=SnapshotScope(**{name: row[f"alias_{name}"] for name in SCOPE_DIMENSIONS}),
        )
    return Candidate(
        rank=rank,
        entity_kind=kind,
        reference=reference,
        match_tier=row["match_tier"],
        matched_text=row["match_text"],
        match_kind=row["match_kind"],
        entity_approval_reference=row["entity_approval_reference"],
        alias=alias,
    )


def _superseded(rows) -> tuple[DiscoveryLimitation, ...]:
    """Section 7: one entry per distinct superseded participating snapshot."""
    seen = {}
    for row in rows:
        values = {name: row[f"superseded_by_{name}"] for name in SCOPE_DIMENSIONS}
        if all(v is None for v in values.values()):
            continue
        if any(v is None for v in values.values()):
            raise DataFault("a superseding snapshot with only some dimensions set")
        scope = SnapshotScope(**{name: row[name] for name in SCOPE_DIMENSIONS})
        seen.setdefault((scope, SnapshotScope(**values)), None)
    return tuple(
        DiscoveryLimitation(
            kind=DiscoveryLimitationKind.SUPERSEDED_SNAPSHOT,
            detail=f"{_text(scope)} is superseded by {_text(successor)}. Its approved entities and"
            f" aliases hold for itself; they are not presented as holding in the later snapshot"
            f" (mvp-v0.1 Section 4.2, entity-discovery-v0.1 Section 7).",
        )
        for scope, successor in seen
    )


def _timestamp(value) -> str:
    """RFC 3339 UTC second precision Z, from the naive UTC timestamp the
    registry stores (Section 4.2)."""
    if isinstance(value, str):
        return value
    return value.replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def _text(scope: SnapshotScope) -> str:
    return " / ".join(getattr(scope, name) for name in SCOPE_DIMENSIONS)
