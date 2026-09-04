"""The runtime: one request in, one normalized result out.

This is the join point Issue #14 names. Section 4.5's three routes, Section
4.2's scope enforcement, Section 5's seven statuses and Section 7's three
evidence structures all meet here, and the shape of the module follows the
order the contract puts them in:

1. Validate (`request.py`). Section 4.5: route validation runs before any
   database access. Three of the seven statuses are decided here, and all
   three are the three Section 5 says open no connection.
2. Resolve scope (`scope.py`). Section 4.2. Two more statuses are decided
   here, and neither is decided by choosing among candidates.
3. Dispatch to the route's registered template. The last two statuses,
   `success` and `not_found`, are decided by whether it returned a row.
4. Assemble evidence (Section 7) around whichever of the seven came out.

Step 4 is not a formatting step at the end. Section 5 requires all three
structures on every outcome "including negative outcomes", so every return
below goes through the same two builders, and there is no path that produces a
status without them.
"""

import dataclasses

from ..evidence import (
    EvidenceBundle,
    Limitation,
    LimitationKind,
    MappingProvenance,
    ProducingLayer,
    ReadOnlySafeguards,
    SourceTrace,
)
from ..references import SCOPE_DIMENSIONS, SnapshotScope
from ..registry import get
from ..result import Result, Row
from ..routes import UNSUPPORTED_ROUTE, Route
from ..status import Status
from .execution import Execution
from .faults import DataFault
from .request import CANDIDATES_TEMPLATE, Refusal, Request, ValidatedRequest, validate
from .scope import Candidates, candidates, resolved

# Which snapshots one result row is *about*. Section 7 requires a `limitations`
# entry "when any participating snapshot has a non-null `superseded_by`", and
# for a mapping Section 4.5 makes that three snapshots per row rather than one:
# the asserting artifact and both endpoints, "separately identified".
PARTICIPANTS = {
    Route.MESSAGE_FACTS: ("",),
    Route.SIGNAL_FACTS: ("",),
    Route.SIGNAL_MAPPING: ("asserting_", "source_", "target_"),
}

# Section 7: the entry for `needs_entity_discovery` states "that Entity
# Discovery is not implemented in v0.1". Fixed text, because the obligation is
# to say that sentence and not to paraphrase it per request.
ENTITY_DISCOVERY_DETAIL = (
    "Entity Discovery is not implemented in v0.1; this outcome is terminal and"
    " never reaches the database (Sections 4.6 and 5)."
)


@dataclasses.dataclass(frozen=True, kw_only=True)
class Runtime:
    """The Section 4.5 routes, over one database.

    `fixture_provenance` is recorded on every trace and is never discovered.
    Section 7 asks for "the fixture provenance that actually exists", and only
    whoever provisioned the database knows what it was loaded from; a runtime
    that named `fixtures/` by itself would be asserting provenance for a
    database it did not load. A runtime told nothing records nothing, which is
    an empty tuple and not a guess.
    """

    database: object
    fixture_provenance: tuple[str, ...] = ()

    def execute(self, request: Request) -> Result:
        """Answer `request`. Returns one of the seven Section 5 statuses.

        Raises rather than returns for the two conditions Section 4.4 puts
        outside the seven; see `faults.py`.
        """
        try:
            validated = validate(request)
        except Refusal as refusal:
            return self._refused(request, refusal)
        return self._answer(validated)

    # -- the path that opens a connection -------------------------------

    def _answer(self, request: ValidatedRequest) -> Result:
        with self.database.session() as session:
            safeguards = ReadOnlySafeguards(
                role_name=session.role_name,
                read_only_transaction=session.read_only_transaction,
                connection_opened=True,
            )
            found = candidates(session, request)
            if not found.scopes:
                return self._coverage_gap(request, safeguards, found)
            if not request.scope_is_complete:
                return self._ambiguous(request, safeguards, found)

            scope = resolved(request, found)
            template = get(request.template_name)
            run = session.execute(template, request.arguments)

        if template.rows_are_overflow(len(run.rows)):
            # Section 4.4: "a second row means the loaded database violates its
            # own invariants, and the runtime reports a failure (conformance
            # class `data`) instead of silently returning one of several."
            raise DataFault(
                f"{template.name} returned {len(run.rows)} rows for a canonical"
                f" reference; Section 4.1 makes it at most one, so the loaded"
                f" database contradicts its own uniqueness constraints"
            )

        participants = _participants(request.route, run.rows)
        limitations = list(_superseded(participants))
        if template.truncated(len(run.rows)):
            limitations.append(
                Limitation(
                    kind=LimitationKind.TRUNCATED_BY_LIMIT,
                    detail=f"{template.name} returned its registered limit of"
                    f" {template.row_limit} rows; further rows exist and are"
                    f" not in this result (Section 4.4).",
                )
            )
        limitations.extend(_user_selection(request, scope))

        return Result(
            status=Status.SUCCESS if run.rows else Status.NOT_FOUND,
            evidence_bundle=EvidenceBundle(
                route=request.route.value,
                read_only_safeguards=safeguards,
                row_count=len(run.rows),
                template_name=template.name,
                template_version=template.version,
                bound_parameters=run.bound_parameters,
                resolved_scope=scope,
            ),
            source_trace=SourceTrace(
                contributing_scopes=_contributing(participants),
                mapping_provenance=_mapping_provenance(request.route, participants),
                fixture_provenance=self.fixture_provenance,
            ),
            limitations=tuple(limitations),
            rows=run.rows,
        )

    def _coverage_gap(
        self, request: ValidatedRequest, safeguards, found: Candidates
    ) -> Result:
        """Section 5: coverage "cannot be established to contain" the request.

        Returned instead of `not_found` whenever coverage cannot be
        established, which is exactly the case where the scope named no
        snapshot at all. `not_found` is reserved for a scope that resolved:
        the route's own template ran against a real snapshot and matched no
        key. Conflating the two is the defect this branch exists to prevent,
        and it is why the candidate query runs even for a complete scope.
        """
        named = ", ".join(
            f"{name}={request.arguments[name]}"
            for name in SCOPE_DIMENSIONS
            if name in request.arguments
        )
        return self._opened_without_facts(
            request,
            safeguards,
            found,
            Status.COVERAGE_GAP,
            (
                Limitation(
                    kind=LimitationKind.COVERAGE_NOT_ESTABLISHED,
                    detail=f"no snapshot in the approved data scope matches"
                    f" {named}, so the coverage this request needs could not be"
                    f" established (Sections 4.2 and 5).",
                ),
            ),
        )

    def _ambiguous(
        self, request: ValidatedRequest, safeguards, found: Candidates
    ) -> Result:
        """Section 4.2: an under-specified scope, with the candidates listed.

        No narrowing happens here, and none is attempted. Section 4.2 makes one
        matching candidate `ambiguous` as surely as two, so this branch never
        reads `len(found.scopes)`: it is reached whenever the scope is
        incomplete and the candidate query returned anything.
        """
        limitations = []
        if found.truncated:
            limitations.append(
                Limitation(
                    kind=LimitationKind.TRUNCATED_BY_LIMIT,
                    detail=f"{CANDIDATES_TEMPLATE} returned its registered limit"
                    f" of {get(CANDIDATES_TEMPLATE).row_limit} candidate scopes;"
                    f" further candidates exist and are not listed"
                    f" (Section 4.4).",
                )
            )
        return self._opened_without_facts(
            request, safeguards, found, Status.AMBIGUOUS, tuple(limitations)
        )

    def _opened_without_facts(
        self,
        request: ValidatedRequest,
        safeguards,
        found: Candidates,
        status: Status,
        limitations: tuple[Limitation, ...],
    ) -> Result:
        """The evidence for an outcome decided by the candidate query alone.

        `resolved_scope` is None: nothing was resolved, and Section 7's
        "explicit empty value" is the honest record of that. `template_name`
        names the candidate template, because that is the template that ran --
        the route's own template was never reached.
        """
        template = get(CANDIDATES_TEMPLATE)
        return Result(
            status=status,
            evidence_bundle=EvidenceBundle(
                route=request.route.value,
                read_only_safeguards=safeguards,
                row_count=found.row_count,
                template_name=template.name,
                template_version=template.version,
                bound_parameters=found.execution.bound_parameters,
                resolved_scope=None,
            ),
            source_trace=SourceTrace(
                contributing_scopes=found.scopes,
                fixture_provenance=self.fixture_provenance,
            ),
            limitations=limitations,
            rows=found.execution.rows,
        )

    # -- the path that opens nothing ------------------------------------

    def _refused(self, request: Request, refusal: Refusal) -> Result:
        """Section 5's three no-connection statuses, with their evidence.

        Every field the bundle would carry about an execution is the explicit
        empty value Section 7 requires, and `bound_parameters` in particular is
        empty rather than echoing what the caller proposed: Section 7 says the
        arguments of a rejected request "are never reported as such", because
        recording them "would present a rejected proposal as a fact the
        runtime acted on".
        """
        limitations = ()
        if refusal.status is Status.NEEDS_ENTITY_DISCOVERY:
            limitations = (
                Limitation(
                    kind=LimitationKind.ENTITY_DISCOVERY_NOT_IMPLEMENTED,
                    detail=f"{ENTITY_DISCOVERY_DETAIL} {refusal.detail}",
                ),
            )
        return Result(
            status=refusal.status,
            evidence_bundle=EvidenceBundle(
                route=_route_name(request.route),
                read_only_safeguards=ReadOnlySafeguards(
                    role_name="", read_only_transaction=False, connection_opened=False
                ),
            ),
            source_trace=SourceTrace(
                producing_layer=refusal.producing_layer,
                fixture_provenance=self.fixture_provenance,
            ),
            limitations=limitations,
        )


def _route_name(value: object) -> str:
    """What the bundle records as `route` for a request that never ran.

    Section 7 requires a `route` on every result and `EvidenceBundle` refuses
    an empty one, so a request whose route is unusable still needs a name.
    Recording what was asked for is the honest answer when it is text; when it
    is not, the fallback is Section 4.6's own literal for "no route applies"
    rather than a token this module invented.
    """
    if isinstance(value, Route):
        return value.value
    if isinstance(value, str) and value != "":
        return value
    return UNSUPPORTED_ROUTE


@dataclasses.dataclass(frozen=True, kw_only=True)
class _Participant:
    """One snapshot a result row is about, and the snapshot superseding it."""

    prefix: str
    scope: SnapshotScope
    superseded_by: SnapshotScope | None


def _participants(route: Route, rows: tuple[Row, ...]) -> tuple[tuple[_Participant, ...], ...]:
    """The participating snapshots of each row, in the row's own order."""
    return tuple(
        tuple(_participant(row, prefix) for prefix in PARTICIPANTS[route])
        for row in rows
    )


def _participant(row: Row, prefix: str) -> _Participant:
    scope = SnapshotScope(**{name: row[prefix + name] for name in SCOPE_DIMENSIONS})
    values = {
        name: row[f"{prefix}superseded_by_{name}"] for name in SCOPE_DIMENSIONS
    }
    present = [name for name, value in values.items() if value is not None]
    if not present:
        return _Participant(prefix=prefix, scope=scope, superseded_by=None)
    if len(present) != len(SCOPE_DIMENSIONS):
        # `superseded_by` is one nullable reference to one row, so its four
        # dereferenced dimensions are null together or present together.
        raise DataFault(
            f"{scope} names a superseding snapshot with only {present} set;"
            f" Section 4.1 makes all four scope dimensions not null"
        )
    return _Participant(
        prefix=prefix, scope=scope, superseded_by=SnapshotScope(**values)
    )


def _superseded(participants) -> tuple[Limitation, ...]:
    """One entry per distinct superseded snapshot (Sections 4.2 and 7).

    Section 4.2: "`superseded_by` is exposed in `limitations` when any
    participating snapshot is superseded." Exposed means the superseding
    snapshot is named, not merely that a flag is raised -- a reader has to be
    able to go and look at what replaced it.

    Distinct rather than one per row: a mapping result can carry the same
    superseded asserting snapshot on two hundred rows, and two hundred
    identical entries would say nothing the first one did not.
    """
    seen = {}
    for row in participants:
        for participant in row:
            if participant.superseded_by is None:
                continue
            seen.setdefault(
                (participant.scope, participant.superseded_by), participant
            )
    return tuple(
        Limitation(
            kind=LimitationKind.SUPERSEDED_SNAPSHOT,
            detail=f"{_text(participant.scope)} is superseded by"
            f" {_text(participant.superseded_by)}. Its facts hold for itself;"
            f" they are not presented as holding in the later snapshot"
            f" (Section 4.2).",
        )
        for participant in seen.values()
    )


def _user_selection(
    request: ValidatedRequest, scope: SnapshotScope
) -> tuple[Limitation, ...]:
    """Section 7's entry for a scope narrowed by an explicit user selection."""
    if not request.scope_selected_by_user:
        return ()
    return (
        Limitation(
            kind=LimitationKind.SCOPE_SELECTED_BY_USER,
            detail=f"scope was narrowed to {_text(scope)} by an explicit user"
            f" selection, not by the runtime (Sections 4.2 and 7).",
        ),
    )


def _contributing(participants) -> tuple[SnapshotScope, ...]:
    """Every snapshot that contributed a row, first appearance first.

    Section 7 asks for "the resolved scope of every snapshot that contributed
    a row", so a result with no rows contributes nothing and the tuple is
    empty. That is not the same as having no resolved scope: `not_found`
    resolved one, and the bundle's `resolved_scope` records it.
    """
    ordered = {}
    for row in participants:
        for participant in row:
            ordered.setdefault(participant.scope, None)
    return tuple(ordered)


def _mapping_provenance(route: Route, participants) -> tuple[MappingProvenance, ...]:
    """Section 4.5: one entry per asserting relation, never merged.

    Charter Section 3.6 requires the asserting artifact's scope to travel with
    each relation, so this is per row rather than per result, and the three
    scopes stay in separate fields rather than being collapsed into a set.
    """
    if route is not Route.SIGNAL_MAPPING:
        return ()
    return tuple(
        MappingProvenance(
            asserting_scope=_at(row, "asserting_"),
            source_endpoint_scope=_at(row, "source_"),
            target_endpoint_scope=_at(row, "target_"),
        )
        for row in participants
    )


def _at(row: tuple[_Participant, ...], prefix: str) -> SnapshotScope:
    for participant in row:
        if participant.prefix == prefix:
            return participant.scope
    raise DataFault(f"no participating snapshot carries the {prefix!r} prefix")


def _text(scope: SnapshotScope) -> str:
    """A scope as the four dimensions, in Section 4.2's order."""
    return " / ".join(getattr(scope, name) for name in SCOPE_DIMENSIONS)
