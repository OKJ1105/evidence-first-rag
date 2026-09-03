# MVP Runtime Contract v0.1

## 1. Identifier and version

**Identifier:** `mvp-v0.1`

**Version:** `0.4.0` — the identifier names the document; the version tracks its obligations. `0.1.0` proposed the contract. `0.2.0` filled the platform, determinism, fixture-serialization, and limit decisions that `0.1.0` listed as open in Section 9. `0.3.0` fixes the value of `bound_parameters` for the outcomes that open no connection (Section 7) and records which reading of Charter Section 9 the Section 4.7 baseline implements. `0.3.0` is the version at which this contract was accepted. `0.4.0` resolves a contradiction between Section 4.2 and Section 5 over the `ambiguous` candidate threshold in favour of Section 4.2, and registers `FX-113` for the single-candidate case that neither reading tested.

This contract combines the data, route, result, evidence, query-template-registry, runtime, and evaluation families described in [Contract Shape Framework](README.md) Section 5 into one document. Section 5 of that framework assigns responsibilities per family; it does not require one document per family.

The version changes when any observable obligation in Section 4, 5, 6, or 7 changes. Adding a fixture that exercises an existing obligation is a patch change. Adding or removing a route, template, status condition, or evidence field is a minor change. Removing or weakening an obligation is not permitted at the contract layer; see Section 10.

## 2. Status

**Status:** `Accepted 2026-09-01`

This contract is binding on implementation from that date under [Contract Shape Framework](README.md) Section 2.1. The repository owner recorded the required human review of this contract and its acceptance evidence on the pull request that set this line, and recorded merge approval by merging it.

Section 10 sets two preconditions for acceptance. Both are discharged in this document rather than only in pull request comments: the Section 3.3 decision on the Milestone 1 and Milestone 2 span is recorded in Section 3.3, and the Section 8 acceptance evidence is explicitly deferred with a named owner in Section 8.2.

An accepted contract may still be amended. Section 10 governs how, and no amendment may weaken an obligation.

## 3. Scope

### 3.1 What this contract fixes

- A PostgreSQL data model for four entities: source snapshot, message occurrence, signal occurrence, and signal mapping.
- The uniqueness and integrity rules that enforce the identity and scope invariants of [Project Charter](../PROJECT_CHARTER.md) Section 3.6 and [ADR-0002](../adr/0002-scoped-canonical-entity-identity.md).
- Separation between a provisioning database identity and a least-privilege read-only runtime identity.
- A fixed SQL template registry with four registered templates and its negative safeguards.
- Three routes: `message_facts`, `signal_facts`, and `signal_mapping`.
- The normalized result envelope, including `evidence_bundle`, `source_trace`, and `limitations`.
- All seven status families the runtime may produce.
- A Thin LLM Adapter that extracts a route and arguments from a natural-language request, and the deterministic revalidation that stands between the adapter and any database access.
- A deterministic exact-match baseline over curated requests, used only as the control group for the Milestone 2 adapter comparison.
- A conformance runner with a `pass` / `review` / `fail` outcome contract and failure-class tagging.
- A read-only invariance check.
- The structural cases every fixture set must cover.

### 3.2 What this contract does not fix

- Entity Discovery, alias provenance, and any scope-selection policy.
- Any renderer or export format.
- Deployment topology, networking, identity, or sizing.
- Vector or lexical candidate retrieval of any kind.
- Any raw source-format ingestion adapter.

Section 9 records these with their owning slice.

### 3.3 Milestone span and the decision it requires

Charter Section 5 places the deterministic backend in Milestone 1. Charter Section 6 defers the Thin LLM Adapter, and Charter Section 9 places it in Milestone 2 behind its own acceptance gate.

This contract covers both. That is a deliberate scope choice by the repository owner to shorten the path to a demonstrable portfolio artifact. Charter Section 6 states that deferred does not mean pre-approved, so this span requires a recorded human decision before the contract is accepted. Section 10 records that condition.

The Milestone 2 gate is preserved rather than skipped: Section 4.7 defines the deterministic baseline that the adapter must be compared against, and Section 8 registers the comparison as an acceptance item. No adapter output reaches the database without passing the deterministic revalidation in Section 4.6.

**Recorded decision, 2026-09-01.** The repository owner approves this contract spanning Milestone 1 and the Milestone 2 adapter, on the condition stated above: the Milestone 2 acceptance gate in Charter Section 9 is preserved in full. Accepting this contract authorizes implementation of the Milestone 1 deterministic backend and of the adapter as specified; it does not adopt the adapter. Adoption remains a separate recorded decision governed by the Section 4.7 comparison and the Section 8 acceptance evidence for Section 4.6. This satisfies the first of the two preconditions in Section 10.

### 3.4 Platform

Python and PostgreSQL, consistent with [ADR-0001](../adr/0001-postgresql-runtime-and-normalized-fixture-boundary.md).

- **PostgreSQL 17** — pinned at the major version; any patch release satisfies the contract. PostgreSQL 17 is available on the declared Azure Database for PostgreSQL Flexible Server target, which keeps the ADR-0001 compatibility boundary a subset of the deployment target.
- **No extensions.** v0.2.0 requires none. Adding one is a minor version change under Section 10.
- **Provisioning is plain SQL.** Version-controlled DDL and grant scripts, applied in lexical order by the official `postgres:17` image's init mechanism under Docker Compose. No migration framework in this contract: there is exactly one schema version, and reproducibility comes from re-provisioning, not from migration history. Adopting a migration tool later is a contract change, not an implementation detail.
- The fixture loader runs inside the same provisioning step, as the provisioning identity, before the runtime identity ever connects. Section 4.11 fixes the fixture format.

## 4. Normative requirements

### 4.1 Data model

Four tables. Column order below is normative for the schema definition; result column order is fixed per template in Section 4.4.

Within each table the columns are ordered by role, not by the order any source format happens to declare them: identity columns first, then columns that carry interpretation, then columns that describe wire encoding. The order is a choice of this contract and carries no meaning beyond readability.

**`source_snapshot`**

| Column | Type | Notes |
| --- | --- | --- |
| `snapshot_id` | surrogate key | Not exposed in any public payload. |
| `project_code` | text, not null | Scope dimension. |
| `revision_label` | text, not null | Scope dimension. |
| `network_name` | text, not null | Scope dimension. Mandatory, never inferred. |
| `snapshot_label` | text, not null | Distinguishes two snapshots that share the other three dimensions. |
| `superseded_by` | nullable reference to `snapshot_id` | Non-null means this snapshot is superseded. |
| `ingested_at` | timestamp, not null | Fixture provenance only. Never used to select a snapshot. |

Unique constraint on `(project_code, revision_label, network_name, snapshot_label)`.

**`message_occurrence`**

| Column | Type | Notes |
| --- | --- | --- |
| `message_occurrence_id` | surrogate key | Identity. Not exposed. |
| `snapshot_id` | reference, not null | Identity. Parent snapshot. |
| `message_key` | text, not null | Identity. Local lookup key within the snapshot. |
| `transmit_mode` | text, nullable | Interpretation. How the occurrence is scheduled. |
| `transmit_period_ms` | integer, nullable | Interpretation. Meaningful only for a periodic mode. |
| `payload_byte_length` | integer, nullable | Wire encoding. |
| `frame_identifier` | integer, nullable | Wire encoding. Not an identity column; two snapshots may reuse a value. |

Unique constraint on `(snapshot_id, message_key)`. This is the constraint that keeps identically named messages in different snapshots distinct.

**`signal_occurrence`**

| Column | Type | Notes |
| --- | --- | --- |
| `signal_occurrence_id` | surrogate key | Identity. Not exposed. |
| `message_occurrence_id` | reference, not null | Identity. Parent message occurrence. |
| `signal_key` | text, not null | Identity. Local lookup key within the parent message occurrence. |
| `unit_label` | text, nullable | Interpretation. |
| `scale_factor` | numeric, nullable | Interpretation. Applied with `scale_offset` to obtain a physical value. |
| `scale_offset` | numeric, nullable | Interpretation. |
| `bit_width` | integer, nullable | Wire encoding. |
| `bit_offset` | integer, nullable | Wire encoding. |

Unique constraint on `(message_occurrence_id, signal_key)`. This is the constraint that keeps identically named signals under different parent messages distinct. A snapshot-level unique constraint on `signal_key` is prohibited.

**`signal_mapping`**

| Column | Type | Notes |
| --- | --- | --- |
| `signal_mapping_id` | surrogate key | Not exposed. |
| `asserting_snapshot_id` | reference, not null | The snapshot of the artifact that asserts the relation. |
| `source_signal_occurrence_id` | reference, not null | Left endpoint. |
| `target_signal_occurrence_id` | reference, not null | Right endpoint. |
| `mapping_key` | text, not null | Local lookup key within the asserting snapshot. |
| `transform_kind` | text, nullable | |

Unique constraint on `(asserting_snapshot_id, source_signal_occurrence_id, target_signal_occurrence_id)`. Endpoints may belong to snapshots other than the asserting snapshot; that is the cross-snapshot case Charter Section 3.6 governs.

### 4.2 Identity and scope enforcement

- A canonical message reference is `(project_code, revision_label, network_name, snapshot_label, message_key)`.
- A canonical signal reference is that tuple plus `message_key` of the parent and `signal_key`.
- No surrogate key appears in any public payload. Surrogate values may differ between provisioning runs.
- The runtime never supplies a missing `project_code`, `revision_label`, `network_name`, or `snapshot_label`. It never selects the newest `ingested_at`, the highest `revision_label`, or the only loaded row.
- When a request omits or under-specifies scope and one or more candidate snapshots match, the runtime returns `ambiguous` and lists the candidate scopes. One matching candidate is still `ambiguous`. The request is under-specified whatever the database happens to hold, and resolving it would be the selection of "the only loaded row" that the rule above forbids; a candidate count is a property of what is currently loaded, so deciding on it would make the same request answerable today and ambiguous once a second snapshot lands. Scope may be narrowed to one candidate only by an explicit user selection, which Section 7 requires to be recorded in `limitations`. Zero matching candidates is not `ambiguous`; Section 5 assigns that case to `coverage_gap`.
- A `signal_mapping` row is returned only when the asserting snapshot and both endpoint snapshots resolve to exactly one snapshot each. Otherwise the request fails closed.
- A mapping asserted by a superseded snapshot is never presented as holding in a later snapshot. `superseded_by` is exposed in `limitations` when any participating snapshot is superseded.
- Continuity or equivalence between occurrences in different snapshots is never derived from equal `message_key` or `signal_key`.

**Recorded decision, 2026-09-03.** This section and Section 5 previously stated the `ambiguous` threshold differently — "more than zero" here, "more than one" there — and disagreed on one case: an under-specified request matching a single snapshot. The repository owner decided this section governs, so one matching candidate is `ambiguous`. Three obligations already required that reading and would otherwise have no work to do: the prohibition on selecting "the only loaded row" immediately above; Section 7's rule that scope narrows to one candidate only by an explicit user selection, which must be recorded in `limitations`; and Section 9's deferral of any policy that could resolve a scope dimension automatically, which states that until such a policy exists this section requires `ambiguous`. Section 5's wording was corrected to match, and `FX-113` registers the single-candidate case that no fixture had covered.

An automated data-level check asserts every constraint in Section 4.1 and every rule in this section against the loaded database. It is part of the acceptance evidence in Section 8.

### 4.3 Database identities

Two PostgreSQL roles, created by the provisioning path.

| Role | Privileges | Used by |
| --- | --- | --- |
| Provisioning identity | `CREATE`, `INSERT` on the application schema | Schema creation and fixture loading only, outside the query runtime |
| Runtime identity | `SELECT` only on the four tables; no `CREATE`, `INSERT`, `UPDATE`, `DELETE`, `TRUNCATE`, or DDL | The runtime, the adapter path, and the conformance runner |

The runtime opens every connection with the runtime identity inside a read-only transaction. The runtime never holds the provisioning credentials. A runtime attempt to write must fail at the database, not only in application code; the read-only invariance check in Section 4.10 proves this.

### 4.4 Fixed SQL template registry

Every registered template records: template name, version, the full SQL text, its allowed parameter names, its result column list in order, its ordering clause, and its declared limitations. The SQL text is committed and inspectable.

| Template | Allowed parameters | Result ordering |
| --- | --- | --- |
| `TPL_SNAPSHOT_CANDIDATES_V1` | `project_code`, `revision_label`, `network_name`, `snapshot_label` (all optional) | `project_code`, `revision_label`, `network_name`, `snapshot_label` |
| `TPL_MESSAGE_FACTS_V1` | `project_code`, `revision_label`, `network_name`, `snapshot_label`, `message_key` (all required) | `message_key` |
| `TPL_SIGNAL_FACTS_V1` | the five above plus `signal_key` (all required) | `message_key`, `signal_key` |
| `TPL_SIGNAL_MAPPING_V1` | the six above, plus optional `mapping_key` | `mapping_key`, `signal_mapping_id` |

Registry safeguards, enforced at registry construction time where possible and at execution time otherwise:

- Execution is refused for any template name not in the registry.
- Every registered SQL text must begin with `SELECT`.
- Registration is refused for SQL containing `INSERT`, `UPDATE`, `DELETE`, `MERGE`, `CREATE`, `DROP`, `ALTER`, `TRUNCATE`, `GRANT`, `REVOKE`, `COPY`, `CALL`, or `DO`.
- Every variable is bound as a named parameter. String interpolation into SQL is prohibited.
- A parameter not in the template's allowlist is refused.
- A required parameter that is missing is refused.
- No public interface accepts SQL text, a table name, or a column name from a caller.
- Ordering is part of the registered template, not applied by the caller.

`TPL_SNAPSHOT_CANDIDATES_V1` exists so that an `ambiguous` outcome can list candidate scopes without an unregistered query. It returns scope columns only; it returns no message, signal, or mapping facts.

**Limits and timeouts.** Charter Section 3.2 fixes these in this contract:

| Template | Row limit | Meaning of hitting it |
| --- | --- | --- |
| `TPL_SNAPSHOT_CANDIDATES_V1` | 100 | Candidates beyond the limit are truncated; `limitations` records the truncation (Section 7). |
| `TPL_MESSAGE_FACTS_V1` | 2 | The Section 4.1 uniqueness constraints guarantee at most one row. The limit is deliberately 2, not 1: a second row means the loaded database violates its own invariants, and the runtime reports a failure (conformance class `data`) instead of silently returning one of several. |
| `TPL_SIGNAL_FACTS_V1` | 2 | Same overflow-detection rule. |
| `TPL_SIGNAL_MAPPING_V1` | 200 | Rows beyond the limit are truncated; `limitations` records the truncation. |

There is no pagination in v0.2.0; adding it is a minor version change. The runtime identity runs with `statement_timeout = 5s`, set at the role level by provisioning. A timeout is an operational fault, not an outcome: it fails the request rather than producing a status family, and the conformance runner classes it `runtime`.

### 4.5 Routes

| Route | Required arguments | Template | Returns |
| --- | --- | --- | --- |
| `message_facts` | canonical message reference | `TPL_MESSAGE_FACTS_V1` | one message occurrence |
| `signal_facts` | canonical signal reference | `TPL_SIGNAL_FACTS_V1` | one signal occurrence |
| `signal_mapping` | canonical signal reference for the source endpoint; optional `mapping_key` | `TPL_SIGNAL_MAPPING_V1` | zero or more mapping rows, one row per mapping |

All three routes are in scope for v0.1. Route validation runs before any database access and rejects a request whose scope is missing, unknown, contradictory, or implicitly defaulted.

The shape of a `signal_mapping` response follows from an evidence obligation rather than from a formatting preference. Charter Section 3.6 and ADR-0002 require a cross-snapshot relation to carry the complete canonical reference of every endpoint together with the scope and provenance of the artifact asserting it. A response that merges several relations into one entry cannot carry that provenance per relation, so the result exposes one entry per asserting relation.

### 4.6 Thin LLM Adapter

The adapter converts a natural-language request into a candidate `{route, arguments}` object. It is the only component that sees free text.

- Model: `claude-opus-5`, pinned. The decoding configuration is recorded with the evaluation run. Changing either reopens the Milestone 2 comparison in Section 8.
- Output: a schema-constrained structured object whose `route` is one of the three names in Section 4.5 or the literal `unsupported`, and whose `arguments` contain only the parameter names that route allows.
- The adapter receives the user request and the route, argument, and scope-vocabulary metadata required to fill the schema. It receives no database rows, no fixture contents, and no evidence bundle, per Charter Section 3.3.
- The adapter may extract only values explicitly present in the request. It must not invent a `project_code`, `revision_label`, `network_name`, `snapshot_label`, `message_key`, or `signal_key`.
- Adapter output is untrusted input. Before any database access, deterministic revalidation re-checks the route name against the registry, the argument names against the route allowlist, the argument values against their declared types, and the scope completeness rule in Section 4.2. Revalidation failure produces `invalid_request` or `unsupported` and never reaches SQL.
- When the route is determined but a canonical reference cannot be formed, the adapter returns `needs_entity_discovery`. This outcome is terminal in v0.1: it never reaches database execution and never becomes a fact.
- The adapter never selects a template, writes SQL, chooses ordering, or judges conformance.

### 4.7 Deterministic baseline

A deterministic exact-match resolver over a curated request set. A request whose normalized text exactly matches a registered curated entry yields that entry's `{route, arguments}`; anything else yields `unsupported`.

This exists only as the control group for the Milestone 2 adapter comparison required by Charter Section 9. It is not a product path, it is not exposed by any public interface, and it is not a fallback when the adapter fails.

**Which reading of the Charter this implements.** Charter Section 9 requires the adapter to be compared with "the Milestone 1 deterministic baseline". Milestone 1 itself never parses free text, so that phrase does not name an existing component and admits two readings. The reading adopted here is that the baseline accepts the same input the adapter accepts — a natural-language request — and resolves it by exact match against a curated table. The rejected reading is that the baseline is the Milestone 1 runtime invoked with canonical references supplied directly.

The adopted reading is required by the Charter's own adoption criteria. Charter Section 9 admits the adapter only against pre-registered **task-coverage** and **false-resolution** thresholds. Neither quantity is defined for a baseline that is handed canonical references: its coverage is trivially total and it cannot resolve falsely, because resolution is exactly the step it skips. A control group must accept the same input as the treatment for those two numbers to mean anything. Recorded 2026-09-01 so that the Milestone 2 comparison is not later judged against a different control.

### 4.8 Answer rendering

User-facing prose is produced by rendering a fixed template over the normalized result. The renderer inserts values from the result and never adds a fact, a qualifier, or an inference. No model generates answer prose in v0.1. A rendered answer that cannot be produced from the normalized result is a defect, not a degraded success.

### 4.9 Conformance runner

The runner executes every registered fixture against the runtime with the read-only identity and writes one JSON artifact. It never uses a language model to judge correctness: Charter Section 3.3 forbids a model from judging conformance of its own output, and [Contract Shape Framework](README.md) Section 5.7 assigns that judgement to this contract.

The checks below are grouped by the obligation each one enforces, and each group names its source. A check exists because a frozen obligation requires it, not because a runner conventionally has one.

**Group A — registered expectation.** Framework Section 5.7 requires registered inputs and normalized expected outputs. Charter Section 9 requires every test registered by the Milestone 1 contract to pass.

- `A1` The normalized result for the fixture equals its registered expected result in full, field by field.

`A1` is one equality, not a set of independent field checks. On failure the runner reports the first diverging path and uses it only to assign a failure class. Divergence detail is diagnostic and never becomes a separate verdict.

**Group B — boundary assertions.** Charter Section 9 lists these as Milestone 1 gate conditions that hold independently of any expected payload.

- `B1` No SQL executed during the run originated outside the registry, and no arbitrary-SQL, arbitrary-table, or arbitrary-column path was reachable.
- `B2` No fixture whose outcome is `unsupported`, `invalid_request`, `needs_entity_discovery`, `ambiguous`, `coverage_gap`, or `not_found` reached a factual SQL success.
- `B3` The runtime identity could not write data or change the schema.
- `B4` Every table in Section 4.1 was unchanged from the start of the run to its end.

**Group C — data-level invariants.** Charter Section 9 requires an automated data-level check that the loaded database satisfies the Section 3.6 identity and scope invariants.

- `C1` Every constraint in Section 4.1 and every rule in Section 4.2 holds against the loaded database.

**Group D — determinism.** Section 6 of this contract.

- `D1` Two runs over the same fixtures and the same database produce identical artifacts.

The artifact records a run identifier and a wall-clock timestamp. Neither can be reproducible by construction, so `D1` compares the artifact with those two fields removed. The artifact does not embed its own output path, so no further exclusion is needed.

**Group E — rendering.** Charter Section 3.1 requires user-facing text to be a rendering of validated data that neither contradicts nor extends the evidence bundle.

- `E1` Every value in the rendered answer is present in the normalized result.

**Verdicts.** Framework Section 5.7 fixes the three outcomes.

| Verdict | Condition |
| --- | --- |
| `pass` | Every check in Groups A through E passes. |
| `review` | Every check passes, but the runner recorded an advisory divergence that violates no obligation. Requires an explicit recorded human disposition. |
| `fail` | Any check in Groups A through E fails. Always blocks acceptance and can never be overridden into a pass, per Charter Section 9. |

A failure in Group B or Group C forces `fail` for the whole run, not only for the fixture that surfaced it, because those groups assert properties of the runtime and the database rather than of one request.

**Failure class.** Framework Section 5.7 requires failure-class tagging. Every non-`pass` fixture carries exactly one class from the set Charter Section 9 names for observability: `data`, `retrieval`, `contract`, `runtime`, or `presentation`. Group C failures are `data`. Group B failures are `runtime`. Group E failures are `presentation`. A Group A divergence is classed by its first diverging path: a scope or row value is `data`, a route or argument is `retrieval`, a status or evidence field is `contract`.

### 4.10 Read-only invariance

Before and after every conformance run, the runner records a database state digest covering row counts per table and the highest transaction identifier visible to the runtime identity. The digests must be equal.

The runner additionally asserts that the runtime identity is refused when it attempts an `INSERT`, an `UPDATE`, a `DELETE`, and a `CREATE TABLE`. Refusal must originate from PostgreSQL privileges, not from an application guard. Both the digest comparison and the four refusals are recorded in the conformance artifact.

### 4.11 Fixture serialization and keys

- Fixtures are **JSON Lines**, one file per Section 4.1 table, under `fixtures/`, named for the table they load. One line is one row. The files are version-controlled and are the registered inputs the conformance fixtures in Section 8.1 run against.
- Fixture rows reference each other by **natural keys only** — the canonical reference tuples of Section 4.2 — never by surrogate values. The loader resolves references to surrogate keys at load time.
- Surrogate keys are PostgreSQL identity columns, assigned at load. They appear in no fixture file and no public payload (Section 4.2), so two provisioning runs may assign different values without violating determinism (Section 6).
- Identifiers in fixtures are ASCII (`A–Z a–z 0–9 _ . -`) and use the `SAMPLE_*` convention for entity-like names. Keeping fixtures ASCII makes the byte-wise collation of Section 6 also the intuitive ordering.
- A fixture file that fails to parse, or a reference that does not resolve, aborts provisioning. There is no partial load: the loader either loads every row of every file or leaves the database absent.

## 5. Outcome coverage

| Status | Condition |
| --- | --- |
| `success` | Scope resolves to exactly one snapshot, the canonical reference resolves, and the registered template returns at least one row. |
| `not_found` | Scope resolves to exactly one snapshot and that snapshot is within approved coverage, but no row matches the lookup key. |
| `coverage_gap` | The approved data scope does not contain, or cannot be established to contain, the coverage the request needs. Returned instead of `not_found` whenever coverage cannot be established. |
| `unsupported` | The request cannot be represented by an approved contract at the producing layer. The trace records whether the adapter or the runtime produced it. |
| `ambiguous` | Scope is missing or under-specified and one or more candidate snapshots match. Candidate scopes are listed. |
| `invalid_request` | Scope or arguments are malformed, contradictory, or contain a parameter outside the route allowlist. |
| `needs_entity_discovery` | The route is determined but no canonical reference can be formed. Terminal in v0.1; never reaches the database. |

Every status carries an `evidence_bundle`, a `source_trace`, and a `limitations` list, including negative outcomes. For `unsupported`, `invalid_request`, and `needs_entity_discovery`, no database connection is opened and the evidence bundle records that.

## 6. Determinism

- Every registered template carries its ordering clause; the runtime never applies caller-supplied ordering.
- Every ordering is total. Where the declared columns could tie, the template appends its surrogate key as the final tiebreaker so that row order is reproducible.
- Text comparison and ordering use the **`C` collation**: the database is created with `ENCODING UTF8`, `LC_COLLATE='C'`, `LC_CTYPE='C'`, and ordering is byte-wise. The evidence bundle records `"C"`. Rationale: byte-wise ordering is identical on every platform and PostgreSQL build, where ICU and libc collations drift between a local container and a managed service; the fixtures are ASCII (Section 4.11), so byte order is also the readable order.
- **No text normalization.** Lookup keys are compared byte-exact: no case folding, no Unicode normalization, no trimming. A lookup that differs from a stored key only by case is `not_found` — fail-closed, never fuzzy. Any future approved-alias mechanism belongs to Entity Discovery (Milestone 3), not to comparison semantics.
- Numeric values are returned with the precision stored in the schema; no rounding occurs in the runtime or the renderer.
- **Null ordering is `NULLS LAST`**, written explicitly in every registered template's ordering clause rather than left to the database default.
- Repeatable provisioning from the same schema and fixtures produces the same logical rows, constraints, contract-visible values, and query ordering. Surrogate key values need not match, and no public payload exposes them.
- The adapter is not part of the determinism guarantee. Every deterministic guarantee above applies to the path after revalidation. Adapter variability is measured, not assumed away; see Section 8.

## 7. Evidence obligations

Every result, including every negative outcome, carries these three structures.

**`evidence_bundle`**

- `contract_identifier` and `contract_version` of this contract.
- `route`.
- `template_name` and `template_version`, or an explicit empty value when no database was opened.
- `bound_parameters`, containing exactly the parameters bound, with values. Empty when no template executed. An `unsupported`, `invalid_request`, or `needs_entity_discovery` outcome binds nothing, so the arguments the adapter proposed are not bound parameters and are never reported as such; they failed revalidation or were never validated, and recording them here would present a rejected proposal as a fact the runtime acted on.
- `row_count`, the number of source rows the template returned.
- `resolved_scope`: the single `(project_code, revision_label, network_name, snapshot_label)` actually used, or an explicit empty value.
- `collation` in effect.
- `read_only_safeguards`: the runtime role name, the read-only transaction flag, and whether a connection was opened.

The key names `row_count` and `read_only_safeguards` are Charter vocabulary, not new coinage. Charter Section 3.1 requires a factual result to expose its **row count**, and requires the applicable contracts to define how conformance exposes the system-level **read-only safeguards**. This contract keeps those words so that a reader can trace each key to the frozen obligation it satisfies.

**`source_trace`**

- The resolved scope of every snapshot that contributed a row.
- For a mapping result, the scope of both endpoint snapshots and of the asserting snapshot, separately identified.
- The producing layer for an `unsupported` outcome: adapter or runtime.
- The fixture provenance that actually exists. A trace never cites a raw source-format artefact, because none exists in this repository.

**`limitations`**

Present on every result, empty list permitted. Required entries:

- when any participating snapshot has a non-null `superseded_by`;
- when a result was truncated by a limit;
- when scope was resolved to one candidate out of several by an explicit user selection;
- when the outcome is `coverage_gap`, stating what coverage could not be established;
- when the outcome is `needs_entity_discovery`, stating that Entity Discovery is not implemented in v0.1.

## 8. Acceptance evidence

Each obligation is either an automated assertion over registered inputs or a recorded human decision with named evidence, as Charter Section 9 requires.

| Obligation | Acceptance evidence |
| --- | --- |
| Section 4.1 schema and constraints | Automated. The data-level invariant check asserts every unique constraint and reference, including the prohibition on a snapshot-level unique constraint over `signal_key`. |
| Section 4.2 identity and scope | Automated. Fixtures `FX-101`, `FX-102`, `FX-105`, `FX-106`, `FX-113` below, plus the invariant check. `FX-105` and `FX-113` are both required: they are the two-candidate and one-candidate halves of the same threshold, and either alone is satisfied by a rule the section rejects. |
| Section 4.3 database identities | Automated. The four refusal assertions in Section 4.10. |
| Section 4.4 registry safeguards | Automated. Negative tests for unregistered template, write-keyword registration, unknown parameter, missing required parameter, and absence of any arbitrary-SQL entry point. |
| Section 4.4 limits and timeouts | Automated. Template-level tests assert each registered `LIMIT` value and explicit `NULLS LAST` clause; the invariance check reads the runtime role's `statement_timeout` setting; the facts-template overflow rule (limit 2 → runtime `data` failure) is asserted at unit level. |
| Section 4.11 fixture loading | Automated. Provisioning against a fixture set containing an unresolvable natural-key reference must abort with no partial load; provisioning the registered fixtures twice must satisfy the Section 6 repeatability assertions. |
| Section 4.5 routes | Automated. One success fixture per route. |
| Section 4.6 adapter | Automated for revalidation and the no-database-content rule; the latter asserts that the adapter call payload contains no row, fixture, or evidence content. Recorded human decision for adopting the adapter, based on the Milestone 2 comparison below. |
| Section 4.6 model pinning | Automated. The recorded model identifier and decoding configuration in the evaluation artifact must equal the pinned values. |
| Section 4.7 baseline comparison | Recorded human decision. The adapter and the deterministic baseline run the same frozen request set. The adapter is adopted only if it meets pre-registered task-coverage and false-resolution thresholds without weakening any negative outcome. Thresholds are registered before the run that judges them; see Section 9. |
| Section 4.8 rendering | Automated. Every rendered answer is asserted to contain only values present in the normalized result. |
| Section 4.9 runner | Automated. Check `D1`: two consecutive runs produce identical artifacts under the comparison rule Section 4.9 defines. |
| Section 4.10 invariance | Automated. Digest equality plus the four refusals. |
| Section 6 determinism | Automated. Provisioning twice from the same inputs produces equal contract-visible values and equal query ordering. |
| Section 7 evidence | Automated. Every fixture asserts the presence of all three structures and the required keys. |
| Section 3.3 milestone span | Recorded human decision. Required before this contract moves to `Accepted`. |

### 8.1 Required fixture cases

Every fixture uses `SAMPLE_*` identifiers only. Every status family in Section 5 has at least one fixture.

| ID | Structural case | Expected status |
| --- | --- | --- |
| `FX-001` | Message facts for a fully scoped reference | `success` |
| `FX-002` | Signal facts for a fully scoped reference | `success` |
| `FX-003` | Signal mapping returning more than one row | `success` |
| `FX-101` | Same `message_key` present in two snapshots, request fully scoped to one | `success`, resolved to the requested snapshot only |
| `FX-102` | Same `signal_key` under two different parent messages in one snapshot | `success`, resolved to the requested parent only |
| `FX-103` | Source signal exists, no mapping row asserted | `not_found` |
| `FX-104` | Mapping asserted by a snapshot whose `superseded_by` is non-null | `success` with a required `limitations` entry naming the superseded snapshot |
| `FX-105` | Scope omitted, two candidate snapshots match | `ambiguous` with both candidate scopes listed |
| `FX-106` | Scope names a `network_name` that no snapshot has | `coverage_gap` |
| `FX-107` | Lookup key absent from a fully resolved, covered snapshot | `not_found` |
| `FX-108` | Request outside the three approved routes | `unsupported`, producing layer recorded |
| `FX-109` | Parameter outside the route allowlist | `invalid_request`, no connection opened |
| `FX-110` | Contradictory scope, for example two different `revision_label` values | `invalid_request` |
| `FX-111` | Route determined, no canonical reference formable | `needs_entity_discovery`, terminal, no connection opened |
| `FX-112` | Adapter emits an argument value absent from the request | Revalidation rejects; `invalid_request`; forced `fail` if it reaches SQL |
| `FX-113` | Scope omitted, exactly one candidate snapshot matches | `ambiguous` with the single candidate scope listed |

`FX-113` sits outside the `1xx` data-dependent block it belongs with because a registered fixture identifier is never renumbered. It and `FX-105` are the two halves of the Section 4.2 threshold — one candidate and two — and an implementation that satisfies one while failing the other has picked a candidate count as its rule. Read them together.

`FX-104` deliberately expects `success`, not a negative status. A superseded snapshot still holds facts about itself; what is prohibited is presenting its mapping as holding in a later snapshot. The `limitations` entry carries that boundary.

### 8.2 Deferral of the acceptance evidence, recorded 2026-09-01

Section 10 permits this contract to be accepted with its acceptance evidence "explicitly deferred with a named owner". Every obligation in the Section 8 table is deferred on that basis, and this section is the record.

The deferral is structural, not a concession. Each row of Section 8 is an assertion over an implementation that does not exist on the date of acceptance: the repository holds no runtime, no schema, no fixture, and no runner. Requiring the evidence before acceptance would make acceptance unreachable, because [Contract Shape Framework](README.md) Section 2.1 forbids implementing against a contract that is not accepted. The order is therefore contract first, evidence with the implementation that the contract governs.

Named owner: the repository owner. Nothing here is delegated to an AI writer or reviewer.

Where each obligation is discharged:

| Class | Discharged |
| --- | --- |
| Every row marked **Automated** | On the pull request that introduces the behavior that row governs. Its assertions are a merge condition for that pull request. A pull request that implements a behavior without them is incomplete, not deferred again. |
| Section 4.6 adapter adoption | At the Milestone 2 gate, as a recorded human decision, after the Section 4.7 comparison has run. |
| Section 4.7 baseline comparison | At the Milestone 2 gate. Its thresholds and curated request set are the two items still open in Section 9 and are registered before the run that judges them. |
| Section 3.3 milestone span | Already discharged. Recorded in Section 3.3 on 2026-09-01. |

This deferral does not weaken any obligation, and Section 10 forbids using it to. No implementation pull request may cite this section as a reason to omit the evidence its own slice owes.

## 9. Deferred decisions

| Decision | Owner |
| --- | --- |
| Entity Discovery, approved entity registry, alias provenance, ranked candidates | Milestone 3 contract. `needs_entity_discovery` stays terminal until then. |
| Any explicit scope-selection policy that could resolve a scope dimension automatically | Later Milestone 1 contract slice. Until it exists, Section 4.2 requires `ambiguous`. |
| TSV export and any renderer beyond Section 4.8 template rendering | Milestone 4 contract |
| Azure App Service and PostgreSQL Flexible Server deployment, identity, networking, sizing | Milestone 5 contract |
| Vector search and any semantic candidate retrieval | Milestone 3 evaluation contract. Not adopted without a lexical baseline and a pre-registered acceptance metric. |
| Numeric thresholds for the Section 8 adapter-versus-baseline comparison | Open. Owned by this contract; must be filled, as a minor version change, before the evaluation run that judges the adapter. |
| The curated request set backing Section 4.7 | Open. Owned by this contract; authored alongside the Section 8.1 fixtures, before the Milestone 2 comparison. |
| The exact Docker Compose service definition (image digest, ports, volumes) | Implementation detail of the first provisioning slice, bounded by Section 3.4. Not a contract decision unless it changes an obligation. |

Version 0.1.0 also listed the PostgreSQL version and extensions, the provisioning mechanism, collation, normalization, null ordering, fixture serialization, key generation, row limits, and timeouts here. Version 0.2.0 fills them in Sections 3.4, 4.4, 4.11, and 6. The two rows that remain open above are evaluation-stage values: registering them now, before any fixture or curated request exists, would be guessing — Charter Section 9 requires thresholds to be registered before the run they judge, not before the contract is accepted.

## 10. Change control

- This contract is `Accepted`. Under [Contract Shape Framework](README.md) Section 7, a change that does not weaken a Charter or ADR invariant produces a new contract version with a recorded human decision. The looser rule that governed it while `Proposed` — amendment by an ordinary contract-only pull request — no longer applies.
- Filling an open decision from Section 9 is a minor version change with a recorded human decision.
- Adding a fixture that exercises an existing obligation is a patch version change.
- Adding or removing a route, template, status condition, or evidence field is a minor version change and requires a fresh independent design review.
- A change that would weaken a Charter or ADR invariant is not a contract-level change. It requires an architecture decision recorded in an ADR, a Charter update where the change materially changes the Charter, and a recorded human decision.
- This contract may not move to `Accepted` until the repository owner records the Section 3.3 decision on the Milestone 1 and Milestone 2 span, and the Section 8 acceptance evidence is either satisfied or explicitly deferred with a named owner. Both were discharged on 2026-09-01: the span decision in Section 3.3, and the deferral, with its named owner and the point at which each obligation is discharged, in Section 8.2. The rule is retained rather than deleted so that the acceptance record stays interpretable.
- This contract's acceptance does not depend on a separate recorded acceptance of ADR-0002. Section 3.1's citation of ADR-0002 alongside [Project Charter](../PROJECT_CHARTER.md) Section 3.6 is non-binding rationale, not coordinate authority: Charter Section 3.6 alone already carries the operative identity and scope invariants that Section 4.1 and 4.2 enforce. Should ADR-0002 later be rejected or materially revised, the invariants this contract enforces do not change unless the Charter itself changes; only then does this contract require an amendment under this section.
- A superseded version is retained with a `Superseded by` status rather than deleted.
