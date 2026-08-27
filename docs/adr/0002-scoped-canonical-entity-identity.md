# ADR-0002: Scoped Canonical Entity Identity

**Status:** Proposed

**Date:** 2026-08-13

## Context

The [Project Charter](../PROJECT_CHARTER.md) defines a canonical entity reference as the identity of an entity occurrence within an explicit source snapshot. For the initial requirements source, a source snapshot belongs to one project, one revision, and one network or CAN bus scope. A message name is local to that snapshot, and a signal name is local to its parent Message and snapshot.

These rules prevent a result from silently combining entities that happen to share a name but come from different projects, revisions, buses, snapshots, or parent Messages. They also prevent a runtime from treating the only loaded scope or a presumed latest revision as user intent.

Milestone 1 must translate these frozen invariants into data, route, fixed-SQL, result, evidence, and fixture contracts. Before those contracts choose serialized shapes or database keys, the identity model needs a durable public rationale.

## Decision

### Entity occurrence identity is explicitly scoped

The conceptual identity of a source snapshot includes its project, revision, network or CAN bus, and snapshot scope. These are required identity dimensions, not optional filters.

A Message occurrence is identified by that complete source scope plus its local message lookup key. A Signal occurrence is identified by the same complete source scope, its parent Message occurrence, and its local signal lookup key.

This is a conceptual identity composition. It does not yet choose a public serialized payload, a PostgreSQL primary key, a table layout, or exact fixed-SQL parameter names.

### Scope is never supplied implicitly

The runtime does not default a missing project, revision, bus, or source snapshot to a latest value, the only loaded value, or a process-local default. If the required scope cannot be resolved by an explicitly reviewed selection policy, the request fails closed as `ambiguous` and exposes the applicable candidate scopes for explicit selection or abstention.

Malformed or contradictory scope remains subject to the later route contract's `invalid_request` rules. `not_found` is available only after the approved data scope is explicit and known to cover the request; absent or unestablished coverage produces `coverage_gap` instead.

### Cross-snapshot continuity is a relation, not identity

Name equality does not prove that two occurrences in different snapshots represent one continuing entity. Continuity or equivalence across projects, revisions, buses, or snapshots is a separate relation that requires an approved evidence source.

A cross-snapshot relation carries the complete canonical reference of every endpoint and the scope and provenance of the artifact asserting the relation. If any endpoint scope or asserting-artifact scope is unresolved, authoritative retrieval rejects the relation request. A superseded snapshot does not imply that its relations continue into another snapshot.

### Downstream contracts preserve the identity dimensions

Later Milestone 1 contracts must preserve this decision in the following ways:

- data uniqueness and integrity rules distinguish same-named occurrences across source scopes and same-named Signals under different parent Messages;
- fixed SQL binds all required identity dimensions through named, allowlisted parameters and applies deterministic ordering;
- route validation rejects missing, unknown, contradictory, or implicitly defaulted scope before database access;
- normalized results and `source_trace` expose the scope actually used, while `limitations` describe unresolved coverage or selection constraints;
- synthetic fixtures include name collisions across snapshots, parent-Message collisions, explicit ambiguity, coverage gaps, and evidence-backed cross-snapshot relations;
- Entity Discovery, when added later, may return scoped canonical references but cannot create identity or continuity from name similarity.

The existing requirements for registered fixed SQL, read-only database access, fail-closed outcomes, `evidence_bundle`, `source_trace`, and `limitations` remain unchanged.

## Alternatives considered

### Treat an entity name as globally unique

Rejected. Names are local lookup keys. A global name would collapse distinct occurrences and make results depend on whichever snapshot happened to be loaded or searched first.

### Use a global surrogate identifier as the complete public identity

Rejected as the contract-level identity model. An internal surrogate key may later support storage, but it cannot remove or conceal the source scope needed for validation, evidence, and reproducibility. Whether a surrogate key is exposed is deferred to the Milestone 1 data contract.

### Default missing scope to latest or only loaded data

Rejected. The answer would change when data is added or refreshed, and the selected scope would not reflect explicit user intent or an approved policy.

### Infer continuity from equal names

Rejected. Equal names do not establish that an entity or relation survives across projects, revisions, buses, or snapshots. Continuity requires its own approved evidence and provenance.

### Collapse all revisions into one mutable entity record

Rejected. Mutation would erase the historical source scope that makes a result reproducible and would obscure which snapshot supported the evidence.

## Consequences

- Canonical references and query parameters are more explicit, but a result remains reproducible when multiple snapshots contain the same names.
- Database constraints and fixtures must model collisions intentionally rather than relying on global name uniqueness.
- Requests with incomplete scope return explicit negative outcomes instead of plausible facts.
- Cross-snapshot mappings require additional evidence and provenance; they cannot be synthesized from entity names.
- Source traces can identify the exact occurrence used by a fixed SQL template without citing raw artifacts that are absent from the public repository.
- This decision constrains future schema and API choices but does not freeze them prematurely.

## Deferred decisions

Separate reviewed Milestone 1 contract slices will choose:

- the serialized canonical-reference shape and versioning rules;
- physical PostgreSQL keys, uniqueness constraints, tables, columns, and indexes;
- exact route and fixed-SQL parameter names and validation rules;
- approved alias provenance and any explicit scope-selection policy;
- fixture serialization and representative fixture identifiers;
- normalization, collation, null ordering, pagination, and result limits.

Those decisions must preserve this ADR and the Project Charter. A proposal that changes the frozen architecture or identity invariants requires a new ADR, a Charter update, and a recorded human decision.

