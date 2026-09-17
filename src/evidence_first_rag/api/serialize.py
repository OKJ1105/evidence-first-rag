"""api-v0.1 Section 4.4: the wire form of a normalized result, both ways.

Section 4.4 requires a result to become JSON and the JSON to become the result
back with nothing lost, and Section 6 requires one result to have one byte
representation. Those are two obligations and they are met by two functions
here: `as_json` and `from_json` are inverses, and `dumps` is the one way a
document becomes bytes.

**Why this is not `conformance/normalize.py`.** That function projects a
`Result` into the object Section 4.9 check `A1` compares against a registered
`FX-*` expectation, and the repository's habit is one serialization rather
than two. It cannot serve here: it predates the Milestone 3 slices and emits
neither `EvidenceBundle.selection` -- the record entity-discovery-v0.1 Section
4.8 requires on a dispatched selection, which is the whole of what that
contract adds to a fact result -- nor `SourceTrace.alias_provenance` and
`entity_approval_reference`, which its Section 7 requires on every tier-2
match. Delegating would ship a wire form that drops the evidence Section 7 of
this contract obliges it to carry, on exactly the selection path Milestone 4
exists to demonstrate. That gap is not a defect *there*, because no registered
expectation reaches the selection path; reconciling the two, and regenerating
the registered expectations, is #176 and is deliberately not done inside this
slice.

**What decides a value's wire type.** Section 4.4 fixes it by name rather than
by inspection: integers are JSON numbers, and a `numeric` column of mvp-v0.1
Section 4.1 -- `scale_factor`, `scale_offset`, and Section 4.4 names no others
-- is a JSON string of its stored decimal, because a JSON number would pass
through a binary float and mvp-v0.1 Section 6 forbids rounding anywhere. The
name is what `from_json` reads to convert back, and it can, because the
contract named the two columns instead of leaving the wire to describe itself.
A registry lookup could not have done it: a registered template records its
result column list and no types (`registry/template.py`).

**Where the dump comes from.** Section 4.4 cites entity-discovery-v0.1
Section 4.2's canonical rules, so `dumps` calls that module's writer rather
than `json.dumps`. The two differ in a way Section 6 cares about:
`json.dumps` writes a newline as `\n` where those rules require `\u000a`, so
two conforming implementations would produce different bytes for one result.
`canonical_json` itself cannot serve, because it refuses a boolean by design
-- no digest input carries one, and three of every document's values are
booleans -- which is why that module grew `json_text`, the same rules over the
wider vocabulary a response body needs. One escape set, one definition.

Nothing here opens a connection, executes a template, or validates a request.
A document reaching `from_json` is trusted to be one this module wrote; what
happens to a body that is not is Section 4.5's `malformed_request`, and
belongs to the slice that can produce one.
"""

import decimal

from ..discovery.canonical import json_text
from ..discovery.candidate import AliasProvenance, Candidate
from ..discovery.evidence import DiscoveryEvidence, DiscoveryLimitation, DiscoveryLimitationKind, DiscoveryTrace
from ..discovery.result import DiscoveryResult
from ..discovery.status import DiscoveryStatus
from ..evidence import (
    EvidenceBundle,
    Limitation,
    LimitationKind,
    MappingProvenance,
    ProducingLayer,
    ReadOnlySafeguards,
    SourceTrace,
)
from ..references import SCOPE_DIMENSIONS, MessageReference, SignalReference, SnapshotScope
from ..result import Result
from ..status import Status

#: The `numeric` columns of mvp-v0.1 Section 4.1, which Section 4.4 of this
#: contract names to fix their wire type. A column outside this tuple is
#: `text`, an integer, or a boolean, and each of those is its own JSON type.
NUMERIC_COLUMNS = ("scale_factor", "scale_offset")

__all__ = ["as_json", "from_json", "dumps", "NUMERIC_COLUMNS"]


def dumps(document: dict) -> str:
    """`document` as the one text Section 6 allows it to have.

    Keys sorted byte-wise, no insignificant whitespace, the RFC 8259 minimum
    escape set with U+0000-U+001F as four lower-case hexadecimal digits, and
    every other character as itself -- so the bytes are UTF-8 rather than
    ASCII with the text hidden inside `\\uXXXX` escapes.
    """
    return json_text(document)


def as_json(result) -> dict:
    """`result` as the Section 4.4 document.

    Dispatch is on the result type, and the key sets it produces are disjoint
    -- `rows` on one, `resolved` and `candidates` on the other -- which is the
    discriminator Section 4.3 tells a client to branch on.
    """
    if isinstance(result, Result):
        return _fact_json(result)
    if isinstance(result, DiscoveryResult):
        return _discovery_json(result)
    raise TypeError(f"{type(result).__name__} is not a normalized result")


def from_json(document: dict):
    """The result `document` was made from.

    The inverse of `as_json` over what `as_json` writes; Section 8's round-trip
    row is the assertion that it is one.
    """
    if "rows" in document:
        return _fact_result(document)
    if "candidates" in document:
        return _discovery_result(document)
    raise ValueError("a result document carries either `rows` or `candidates`")


# -- mvp-v0.1 -----------------------------------------------------------------


def _fact_json(result: Result) -> dict:
    bundle = result.evidence_bundle
    trace = result.source_trace
    return {
        "status": result.status.value,
        "rows": [_row_json(row) for row in result.rows],
        "evidence_bundle": {
            "contract_identifier": bundle.contract_identifier,
            "contract_version": bundle.contract_version,
            "route": bundle.route,
            "template_name": bundle.template_name,
            "template_version": bundle.template_version,
            "bound_parameters": _row_json(bundle.bound_parameters),
            "row_count": bundle.row_count,
            "resolved_scope": _scope_json(bundle.resolved_scope),
            "collation": bundle.collation,
            "read_only_safeguards": _safeguards_json(bundle.read_only_safeguards),
            # entity-discovery-v0.1 Section 4.8's one added key. `null` on
            # every result not reached through a selection, never absent:
            # Section 4.4 makes an omitted key indistinguishable from a
            # dropped one.
            "selection": None if bundle.selection is None else _mapping_json(bundle.selection),
        },
        "source_trace": {
            "contributing_scopes": [_scope_json(s) for s in trace.contributing_scopes],
            "mapping_provenance": [
                {
                    "asserting_scope": _scope_json(p.asserting_scope),
                    "source_endpoint_scope": _scope_json(p.source_endpoint_scope),
                    "target_endpoint_scope": _scope_json(p.target_endpoint_scope),
                }
                for p in trace.mapping_provenance
            ],
            "producing_layer": _enum_json(trace.producing_layer),
            "fixture_provenance": list(trace.fixture_provenance),
            "alias_provenance": [_mapping_json(a) for a in trace.alias_provenance],
            "entity_approval_reference": trace.entity_approval_reference,
        },
        "limitations": [_limitation_json(item) for item in result.limitations],
    }


def _fact_result(document: dict) -> Result:
    bundle = document["evidence_bundle"]
    trace = document["source_trace"]
    return Result(
        status=Status(document["status"]),
        evidence_bundle=EvidenceBundle(
            contract_identifier=bundle["contract_identifier"],
            contract_version=bundle["contract_version"],
            route=bundle["route"],
            template_name=bundle["template_name"],
            template_version=bundle["template_version"],
            bound_parameters=_row_object(bundle["bound_parameters"]),
            row_count=bundle["row_count"],
            resolved_scope=_scope_object(bundle["resolved_scope"]),
            collation=bundle["collation"],
            read_only_safeguards=_safeguards_object(bundle["read_only_safeguards"]),
            selection=None if bundle["selection"] is None else _row_object(bundle["selection"]),
        ),
        source_trace=SourceTrace(
            contributing_scopes=tuple(_scope_object(s) for s in trace["contributing_scopes"]),
            mapping_provenance=tuple(
                MappingProvenance(
                    asserting_scope=_scope_object(p["asserting_scope"]),
                    source_endpoint_scope=_scope_object(p["source_endpoint_scope"]),
                    target_endpoint_scope=_scope_object(p["target_endpoint_scope"]),
                )
                for p in trace["mapping_provenance"]
            ),
            producing_layer=_enum_object(ProducingLayer, trace["producing_layer"]),
            fixture_provenance=tuple(trace["fixture_provenance"]),
            alias_provenance=tuple(_row_object(a) for a in trace["alias_provenance"]),
            entity_approval_reference=trace["entity_approval_reference"],
        ),
        limitations=tuple(
            Limitation(kind=LimitationKind(item["kind"]), detail=item["detail"])
            for item in document["limitations"]
        ),
        rows=tuple(_row_object(row) for row in document["rows"]),
    )


# -- entity-discovery-v0.1 ----------------------------------------------------


def _discovery_json(result: DiscoveryResult) -> dict:
    bundle = result.evidence_bundle
    trace = result.source_trace
    return {
        "status": result.status.value,
        "resolved": None if result.resolved is None else _candidate_json(result.resolved),
        "candidates": [_candidate_json(c) for c in result.candidates],
        "candidate_scopes": [_scope_json(s) for s in result.candidate_scopes],
        "evidence_bundle": {
            "contract_identifier": bundle.contract_identifier,
            "contract_version": bundle.contract_version,
            "runtime_contract_identifier": bundle.runtime_contract_identifier,
            "runtime_contract_version": bundle.runtime_contract_version,
            "route": bundle.route,
            "template_name": bundle.template_name,
            "template_version": bundle.template_version,
            "bound_parameters": _row_json(bundle.bound_parameters),
            "row_count": bundle.row_count,
            "resolved_scope": _scope_json(bundle.resolved_scope),
            "collation": bundle.collation,
            "read_only_safeguards": _safeguards_json(bundle.read_only_safeguards),
            "registry_digest": bundle.registry_digest,
            "registry_built_at": bundle.registry_built_at,
            "method_identifier": bundle.method_identifier,
            "method_version": bundle.method_version,
            "match_tier": bundle.match_tier,
            "matched_text": bundle.matched_text,
            "candidate_set_id": bundle.candidate_set_id,
            "candidate_count": bundle.candidate_count,
            "selected_rank": bundle.selected_rank,
            "target_route": bundle.target_route,
        },
        "source_trace": {
            "resolved_scope": _scope_json(trace.resolved_scope),
            "contributing_scopes": [_scope_json(s) for s in trace.contributing_scopes],
            "parent_messages": [_reference_json(m) for m in trace.parent_messages],
            "alias_provenance": [_alias_json(a) for a in trace.alias_provenance],
            "entity_approval_reference": trace.entity_approval_reference,
            "producing_layer": _enum_json(trace.producing_layer),
            "fixture_provenance": list(trace.fixture_provenance),
        },
        "limitations": [_limitation_json(item) for item in result.limitations],
    }


def _discovery_result(document: dict) -> DiscoveryResult:
    bundle = document["evidence_bundle"]
    trace = document["source_trace"]
    return DiscoveryResult(
        status=DiscoveryStatus(document["status"]),
        resolved=None if document["resolved"] is None else _candidate_object(document["resolved"]),
        candidates=tuple(_candidate_object(c) for c in document["candidates"]),
        candidate_scopes=tuple(_scope_object(s) for s in document["candidate_scopes"]),
        evidence_bundle=DiscoveryEvidence(
            contract_identifier=bundle["contract_identifier"],
            contract_version=bundle["contract_version"],
            runtime_contract_identifier=bundle["runtime_contract_identifier"],
            runtime_contract_version=bundle["runtime_contract_version"],
            route=bundle["route"],
            template_name=bundle["template_name"],
            template_version=bundle["template_version"],
            bound_parameters=_row_object(bundle["bound_parameters"]),
            row_count=bundle["row_count"],
            resolved_scope=_scope_object(bundle["resolved_scope"]),
            collation=bundle["collation"],
            read_only_safeguards=_safeguards_object(bundle["read_only_safeguards"]),
            registry_digest=bundle["registry_digest"],
            registry_built_at=bundle["registry_built_at"],
            method_identifier=bundle["method_identifier"],
            method_version=bundle["method_version"],
            match_tier=bundle["match_tier"],
            matched_text=bundle["matched_text"],
            candidate_set_id=bundle["candidate_set_id"],
            candidate_count=bundle["candidate_count"],
            selected_rank=bundle["selected_rank"],
            target_route=bundle["target_route"],
        ),
        source_trace=DiscoveryTrace(
            resolved_scope=_scope_object(trace["resolved_scope"]),
            contributing_scopes=tuple(_scope_object(s) for s in trace["contributing_scopes"]),
            parent_messages=tuple(_reference_object(m) for m in trace["parent_messages"]),
            alias_provenance=tuple(_alias_object(a) for a in trace["alias_provenance"]),
            entity_approval_reference=trace["entity_approval_reference"],
            producing_layer=_enum_object(ProducingLayer, trace["producing_layer"]),
            fixture_provenance=tuple(trace["fixture_provenance"]),
        ),
        limitations=tuple(
            DiscoveryLimitation(kind=DiscoveryLimitationKind(item["kind"]), detail=item["detail"])
            for item in document["limitations"]
        ),
    )


def _candidate_json(candidate: Candidate) -> dict:
    return {
        "rank": candidate.rank,
        "entity_kind": candidate.entity_kind,
        "reference": _reference_json(candidate.reference),
        "match_tier": candidate.match_tier,
        "matched_text": candidate.matched_text,
        "match_kind": candidate.match_kind,
        "entity_approval_reference": candidate.entity_approval_reference,
        "alias": None if candidate.alias is None else _alias_json(candidate.alias),
    }


def _candidate_object(document: dict) -> Candidate:
    return Candidate(
        rank=document["rank"],
        entity_kind=document["entity_kind"],
        reference=_reference_object(document["reference"]),
        match_tier=document["match_tier"],
        matched_text=document["matched_text"],
        match_kind=document["match_kind"],
        entity_approval_reference=document["entity_approval_reference"],
        alias=None if document["alias"] is None else _alias_object(document["alias"]),
    )


def _alias_json(alias: AliasProvenance) -> dict:
    return {
        "approval_reference": alias.approval_reference,
        "approved_at": alias.approved_at,
        "asserting_scope": _scope_json(alias.asserting_scope),
    }


def _alias_object(document: dict) -> AliasProvenance:
    return AliasProvenance(
        approval_reference=document["approval_reference"],
        approved_at=document["approved_at"],
        asserting_scope=_scope_object(document["asserting_scope"]),
    )


# -- shared value forms -------------------------------------------------------


def _reference_json(reference) -> dict:
    """Section 4.4: "a canonical reference is an object of its dimensions and
    keys". `as_parameters` is that object already -- it is what the registered
    template binds -- so the wire form and the bound form cannot drift.

    **A reference's key set is its type's**, so the two shapes differ: a
    message reference carries the four dimensions and `message_key`, a signal
    reference adds `signal_key`, and the presence of that key is what
    `_reference_object` reads. That is not an exception to Section 4.4's
    never-omitted rule, which is about a field that exists and has no value: a
    `MessageReference` has no `signal_key` field to leave empty. Writing one
    as `null` would put a key in the document that the type does not have, and
    a reader would have to know that `null` there means "message" rather than
    "signal whose key is unknown" -- which is a worse thing to have to know
    than two key sets.
    """
    return dict(reference.as_parameters())


def _reference_object(document: dict):
    """A signal reference is a message reference plus `signal_key`, so the
    presence of that key is what says which was written."""
    message = MessageReference(
        scope=_scope_object({name: document[name] for name in SCOPE_DIMENSIONS}),
        message_key=document["message_key"],
    )
    if "signal_key" not in document:
        return message
    return SignalReference(message=message, signal_key=document["signal_key"])


def _scope_json(scope):
    if scope is None:
        return None
    return {name: getattr(scope, name) for name in SCOPE_DIMENSIONS}


def _scope_object(document):
    if document is None:
        return None
    return SnapshotScope(**{name: document[name] for name in SCOPE_DIMENSIONS})


def _safeguards_json(safeguards: ReadOnlySafeguards) -> dict:
    return {
        "role_name": safeguards.role_name,
        "read_only_transaction": safeguards.read_only_transaction,
        "connection_opened": safeguards.connection_opened,
    }


def _safeguards_object(document: dict) -> ReadOnlySafeguards:
    return ReadOnlySafeguards(
        role_name=document["role_name"],
        read_only_transaction=document["read_only_transaction"],
        connection_opened=document["connection_opened"],
    )


def _limitation_json(limitation) -> dict:
    return {"kind": limitation.kind.value, "detail": limitation.detail}


def _enum_json(member):
    return None if member is None else member.value


def _enum_object(enumeration, value):
    return None if value is None else enumeration(value)


def _mapping_json(mapping) -> dict:
    """A mapping whose shape another contract fixes, carried through.

    The `selection` record (entity-discovery-v0.1 Section 4.8) and an alias
    provenance entry on a dispatched selection are both this: their keys are
    that contract's, and reproducing them here would be a second place for
    them to be defined.

    **The guarantee that makes this reversible, and where it comes from.**
    Section 4.8 enumerates the record's contents exactly -- two contract
    identifiers and versions, `registry_digest`, `registry_built_at`, two
    method fields, `candidate_set_id`, `selected_rank`, `candidate_count`,
    `target_route`, the two `discovery_template_*` fields,
    `discovery_bound_parameters` and `discovery_row_count` -- and every one is
    a string, an integer, or a mapping of those. They are JSON's own types, so
    `_value_json` changes none of them and `_row_object` reads them back
    unchanged.

    It is a guarantee rather than a property of this code: a decimal added to
    that record would be written as text and read back as text, because
    `_value_object` converts by column name and no name in the record is one
    of the two Section 4.4 names. `TheSelectionRecordHoldsOnlyJsonTypes`
    asserts the guarantee against the record the runtime actually builds, so
    a change to Section 4.8 that broke it fails here rather than silently
    costing a value on the one path this module exists to protect.
    """
    return {name: _value_json(value) for name, value in mapping.items()}


def _row_json(row) -> dict:
    return {column: _value_json(value) for column, value in row.items()}


def _row_object(document: dict) -> dict:
    return {column: _value_object(column, value) for column, value in document.items()}


def _value_json(value):
    if isinstance(value, decimal.Decimal):
        return str(value)
    if isinstance(value, (str, int, bool, type(None))):
        return value
    if isinstance(value, (list, tuple)):
        # `normalized_term` is the one of these the runtime produces: the
        # Section 4.5 token list the lexical template binds.
        return [_value_json(item) for item in value]
    if hasattr(value, "items"):
        return _mapping_json(value)
    # Inventing a wire form for a type no registered column produces would put
    # a value in the document that no reader could write by hand, and would
    # make the round trip a claim about this function rather than about the
    # contract.
    raise TypeError(f"no registered column produces a {type(value).__name__}")


def _value_object(column: str, value):
    """The inverse of `_value_json`, for a value read back under `column`.

    Only the column name can say whether a JSON string was text or a decimal,
    and Section 4.4 names the two columns for which it was a decimal. A
    registry lookup could not have answered it: a registered template records
    its result column list and no types.
    """
    if column in NUMERIC_COLUMNS and isinstance(value, str):
        return decimal.Decimal(value)
    if isinstance(value, list):
        return [_value_object(column, item) for item in value]
    if isinstance(value, dict):
        return {name: _value_object(name, item) for name, item in value.items()}
    return value
