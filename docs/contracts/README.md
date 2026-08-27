# Contract Shape Framework and Review Procedure

**Status:** Proposed

**Date:** 2026-08-13

[Project Charter](../PROJECT_CHARTER.md) Section 5 requires the architecture-level shapes of the data, route, result, evidence, and query-template-registry contracts, together with their review procedure, to be reviewed and committed before Milestone 1 implementation begins. This document is that framework.

It defines what a contract document must contain, what status it must carry, which obligations every contract inherits, and which decisions each contract family owns. It authors no individual contract and fixes no route, template, fixture, key, or parameter.

## 1. What a contract is

A contract is a reviewed, committed document that fixes part of the runtime's observable behaviour so that an implementation slice can be accepted against it. Contracts are normative for implementation: code conforms to a contract, not the reverse.

Authority runs Charter, then ADR, then contract. A contract must not weaken the Charter or an accepted ADR. A change that would is not a contract-level change; it is decided above this layer, as Section 7 describes.

This framework governs contract documents only. It does not govern the Charter or architecture decision records, both of which sit above it.

## 2. Status lifecycle

Every contract document carries one status.

| Status | Meaning |
| --- | --- |
| `Proposed` | Committed for review. Not binding on implementation. |
| `Accepted <date>` | Binding. The repository owner has recorded the required human review of the contract and its acceptance evidence, and has recorded merge approval. |
| `Superseded by <identifier>` | Retained for history. No longer binding. |

An implementation slice may be accepted only against a contract in `Accepted` state. A `Proposed` contract may be cited as direction but does not satisfy the pre-implementation review required by step 4 of the [Development Workflow](../DEVELOPMENT_WORKFLOW.md).

### 2.1 Contract acceptance is not a milestone gate

Contract acceptance is the event described in the `Accepted` row above: the repository owner records the required human review of the contract and its acceptance evidence on the contract's own pull request, and records merge approval. Nothing else is required, and no milestone needs to have completed.

Charter Section 9 milestone acceptance gates are a separate and later event. They judge whether an implementation satisfies its already-accepted contracts, and they are recorded under `docs/acceptance/`. A milestone gate never gates contract acceptance.

This separation is deliberate. The Milestone 1 gate requires every registered test to pass, which requires implementation to exist. If contract acceptance depended on a milestone gate, implementation would depend on a gate that itself depends on implementation. It does not.

[ADR-0001](../adr/0001-postgresql-runtime-and-normalized-fixture-boundary.md) happens to use a compatible status wording. It is cited here as precedent only. The status vocabulary of architecture decision records is not governed by this framework.

## 3. Required sections

Every contract document contains these sections. A section that does not apply says so explicitly rather than being omitted.

1. **Identifier and version.** A stable identifier and a version that changes when the contract's observable obligations change.
2. **Status.** One value from Section 2.
3. **Scope.** What this contract fixes, and what it explicitly does not fix.
4. **Normative requirements.** The obligations an implementation must satisfy, stated so that conformance can be checked.
5. **Outcome coverage.** Every status family this contract can produce, and the condition that produces each one.
6. **Determinism.** The ordering, normalization, and repeatability guarantees the contract makes.
7. **Evidence obligations.** What the contract requires to appear in `evidence_bundle`, `source_trace`, and `limitations`.
8. **Acceptance evidence.** For each obligation, either an automated assertion over registered inputs or a recorded human decision with named evidence, as Charter Section 9 requires.
9. **Deferred decisions.** Each decision left open, with the named later slice that owns it.
10. **Change control.** What kind of change requires a new version, and what must be decided above the contract layer.

## 4. Obligations every contract inherits

These are frozen in the Charter and [AGENTS.md](../../AGENTS.md). A contract restates the ones it governs and may strengthen them. No contract may weaken them.

- Authoritative facts and relations come only from registered fixed SQL templates over approved structured sources.
- No free-form SQL is generated or executed from user text or model output, and no public arbitrary-SQL, arbitrary-table, or arbitrary-column interface exists.
- User input is bound only through named, allowlisted parameters and is validated before database access.
- Database access is read-only. Write keywords, schema changes, unknown templates, and unknown parameters are rejected.
- Every registered query has deterministic result ordering.
- Missing facts, identifiers, source relations, aliases, and coverage are never inferred.
- Unsupported, ambiguous, invalid, missing, and coverage-gap cases fail closed with an explicit status and limitation.
- `not_found` means the approved data scope covers the question but has no matching row. `coverage_gap` means required coverage is absent or cannot be established.
- `unsupported` means the request is not representable by an approved contract at the producing layer, and the trace preserves that layer.
- Normalized results preserve `evidence_bundle`, `source_trace`, and `limitations`.
- Rendering and export may present validated results but may not add or alter facts.
- The identity and scope invariants in Charter Section 3.6 are preserved. Project, revision, network or CAN bus, and source snapshot are required identity dimensions for every entity occurrence, and a Signal occurrence additionally requires its parent Message occurrence. Continuity across snapshots is an evidence-backed relation, never an inference from name equality.
- Deterministic conformance is never judged by a large language model.
- Before Milestone 3, `needs_entity_discovery` is a terminal outcome and cannot reach database execution.
- A model may choose only an approved route and extract explicitly stated arguments. Model output is untrusted input to deterministic contract validation.

## 5. Contract families

Charter Section 5 names five families whose shapes must exist before implementation. Charter Section 9 additionally names runtime and evaluation contracts among the Milestone 1 deliverables; Sections 5.6 and 5.7 place them under this framework. Each entry states what that family is responsible for deciding. It does not decide it here.

### 5.1 Data contract

Owns the logical entities, relations, and attributes in the approved scope; the uniqueness and integrity rules that keep same-named occurrences distinct across source scopes and same-named signals distinct under different parent Messages; the physical PostgreSQL schema, keys, constraints, and indexes within the ADR-0001 compatibility boundary; the separation between the provisioning path and the least-privilege read-only runtime identity at the schema and privilege level; fixture serialization and fixture provenance; and the representative fixture cases required by Charter Section 5, including snapshot differences, name collisions, relations, ambiguity, and negative outcomes.

Charter Section 3.2 fixes identifier allowlists, maximum row counts, pagination, truncation, timeouts, sort keys, null ordering, normalization, and collation-sensitive behaviour in the Milestone 1 SQL and data contracts. This family owns the data-side half of those decisions.

It must also define the automated data-level check that the Milestone 1 acceptance gate requires to confirm the loaded database satisfies the Section 3.6 invariants.

### 5.2 Route contract

Owns the set of approved routes and their request shape; the named, allowlisted parameters and their validation rules; the rejection of missing, unknown, contradictory, and implicitly defaulted scope before database access; the mapping from a route to the registered fixed SQL templates it may invoke; and the status family produced by each rejection.

It must preserve the rule that no unrecorded default project, revision, bus, or source snapshot is supplied, including a latest value or the only currently loaded value, and that unresolved scope produces `ambiguous` with its candidate scopes exposed.

### 5.3 Result contract

Owns the normalized shape of fact and relation results, how each negative outcome is represented so that it cannot be mistaken for a fact, and how the ordering, limit, pagination, and truncation behaviour fixed by the data and query-template-registry contracts surfaces in the normalized result.

It does not choose those values. Charter Section 3.2 assigns them to the Milestone 1 SQL and data contracts.

### 5.4 Evidence contract

Owns the content of `evidence_bundle`, which Charter Section 3.1 requires to expose source scope, fixed-template identifier and version, bound parameters, row count, source trace, and limitations; the content of `source_trace`, including the scope actually used and the producing layer for an `unsupported` outcome; and the content of `limitations`, including unresolved coverage, selection constraints, and truncation.

It must preserve the ADR-0001 rule that a source trace describes fixture provenance that actually exists and does not cite raw artefacts absent from this repository.

### 5.5 Query-template-registry contract

Owns the registration format for a fixed SQL template, including its identifier, version, inspectable SQL, allowed parameters, result shape, and ordering; the negative safeguards that reject unregistered templates, unknown or missing parameters, write statements, and schema changes; and the demonstration that no arbitrary-SQL path exists.

Together with the data contract it owns the SQL-side half of the Charter Section 3.2 decisions listed in Section 5.1.

### 5.6 Runtime contract

Owns request validation and dispatch from a validated route to a registered template; the guarantee that only registered templates execute and that no code path reaches the database without passing contract validation first; the least-privilege read-only runtime identity and its separation from the provisioning identity at run time; transaction behaviour and the guarantee that no runtime path can write data or change the schema; which layer produces an `unsupported` outcome and how the trace preserves that layer; and the rule that before Milestone 3 a `needs_entity_discovery` outcome is terminal and cannot reach database execution.

### 5.7 Evaluation contract

Owns the conformance runner, its registered inputs, and its normalized expected outputs; the exact `pass`, `review`, and `fail` outcome contract; failure-class tagging for conformance and runtime failures; and the read-only invariance checks that ADR-0001 requires to be demonstrated through PostgreSQL roles, privileges, transaction behaviour, and database-state checks.

A conformance `fail` result always blocks acceptance and cannot be overridden into a pass. A `review` result requires an explicit recorded human disposition. Deterministic conformance is never judged by a large language model.

## 6. Review procedure

A contract follows the [Development Workflow](../DEVELOPMENT_WORKFLOW.md) with these additions.

1. A GitHub Issue records the contract slice as the canonical task.
2. The contract is proposed in a contract-only pull request. No implementation accompanies it.
3. An independent design review is performed by a model that did not author the contract. It is read-only, reports at most five P0/P1-equivalent blocking findings, and ends after one follow-up inspection.
4. The repository owner records the required human review of the contract and its acceptance evidence on that pull request. Implementation may not begin before this record exists.
5. The repository owner records merge approval.
6. On merge, the contract status moves from `Proposed` to `Accepted <date>`, citing the recorded human review from step 4. This is the contract acceptance described in Section 2.1; no milestone gate is involved.

## 7. Change control

- A contract in `Proposed` state is amended by an ordinary contract-only pull request.
- A change to an `Accepted` contract that does not weaken a Charter or ADR invariant produces a new contract version with a recorded human decision.
- A change that would weaken a Charter or ADR invariant is not a contract-level change. It requires an architecture decision recorded in an ADR, a Charter update where the change materially changes the Charter, and a recorded human decision. This framework does not decide when an ADR itself must change; that sits above the contract layer.
- A superseded contract is retained with a `Superseded by` status rather than deleted, so that a past acceptance record stays interpretable.

## 8. Deferred decisions

This framework decides nothing below. The table enumerates every open decision in Charter Section 12 and names the later slice that owns it. Where Charter text assigns a decision to more than one contract, both are named.

| Charter Section 12 open decision | Owner |
| --- | --- |
| Representative task set and normalized expected results for the first Milestone 1 contract | Evaluation contract |
| Serialized canonical-reference shape, database keys, and fixed-SQL parameter schema | Data contract; route and query-template-registry contracts for parameter schema |
| Maximum row counts, pagination, truncation, and timeout behaviour per registered query | Data and query-template-registry contracts, per Charter Section 3.2; surfaced by the result contract |
| Route and result schemas for the post-Milestone 1 API | Milestone 4 API contract |
| Approved alias provenance, registry refresh and integrity rules, confidence thresholds, and Entity Discovery selection policy | Milestone 3 Entity Discovery contract |
| Whether vector search materially outperforms lexical and BM25 baselines | Milestone 3 evaluation contract |
| Final TSV schema | Milestone 4 export contract |
| PostgreSQL version, extensions, schema-provisioning tool, serialized fixture format, key-generation strategy, ordering and collation rules | Data contract |
| Azure authentication, networking, service sizing, retention, teardown, and operating budget | Milestone 5 deployment contract |
