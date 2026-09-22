# Project Charter

**Project:** Evidence-First RAG Runtime

**Status:** Frozen at Milestone 0, 2026-08-12. See [Milestone 0 Acceptance Record](acceptance/milestone-0.md). Changes require an ADR and a recorded human decision.

**Current phase:** Milestone 1 contract shaping

## 1. Purpose

Build a bounded engineering assistant that turns natural-language requests into traceable, reproducible results over structured engineering data.

The project is not intended to be a general chatbot. It targets a limited engineering domain in which several related workflows can share the same entity model, query contracts, evidence model, and runtime.

The system should support a complete improvement loop:

1. observe a real user task;
2. identify the required entities and relations;
3. retrieve authoritative facts through approved queries;
4. expose evidence and limitations;
5. record failures and unsupported requests;
6. improve the data, contracts, retrieval, and user flow from evaluation results.

### 1.1 Target user and success criterion

The product user is an engineer who currently answers scoped message, signal, and mapping questions by opening structured engineering definition files and cross-checking them by hand. That workflow is slow to repeat, and its conclusions are difficult for another engineer to verify later. The product user is distinct from the technical hiring reviewer who may evaluate this repository as portfolio evidence.

The project succeeds when the representative tasks registered in the applicable milestone contract produce the expected normalized result and inspectable evidence bundle, and when every task that cannot be answered within the approved data scope returns the expected explicit negative outcome instead of a plausible unsupported answer. Milestone acceptance requires the registered conformance checks to pass and the database to remain read-only; task definitions and thresholds are registered before the run that judges them.

## 2. Problem statement

Vector retrieval can find relevant text, but relevance alone does not establish that a statement is correct. A production-oriented engineering assistant also needs stable identifiers, explicit source scope, reproducible queries, negative behavior, and traceable output.

This project therefore separates two responsibilities:

- **Discovery:** determine which approved entity the user may mean.
- **Authoritative retrieval:** obtain facts and relations for a canonical entity reference from structured data through registered fixed SQL.

Discovery may rank candidates. It must not invent an identifier or supply final engineering facts. Authoritative retrieval may answer only after its input contract is valid.

## 3. Product principles

### 3.1 Evidence before prose

User-facing text is a rendering of validated data. It must not contradict or extend the evidence bundle.

Every factual result must expose its source scope, fixed-template identifier and version, bound parameters, row count, source trace, and limitations. The committed public query-template registry contains the inspectable SQL. The applicable contracts define how conformance exposes the system-level read-only safeguards.

### 3.2 Fixed queries for authoritative facts

Production fact retrieval uses a registry of reviewed SQL templates. User input is passed only through named, allowlisted parameters. Every registered query has deterministic result ordering.

The runtime must reject:

- unregistered templates;
- unknown or missing parameters;
- arbitrary table or column requests;
- write statements and schema changes;
- inferred facts or relations that are absent from the approved data scope.

No public arbitrary-SQL interface is permitted. Exact identifier allowlists, maximum row counts, pagination, truncation, timeouts, sort keys, null ordering, normalization, and collation-sensitive behavior are fixed in the Milestone 1 SQL and data contracts.

### 3.3 Bounded AI responsibility

An LLM may later be used as a thin adapter to:

- choose one approved route;
- extract explicitly stated arguments;
- normalize a discovery query when a canonical entity reference is missing;
- return `unsupported` when the request is outside the approved boundary.

It must not:

- write SQL;
- select arbitrary tables or columns;
- infer missing engineering facts;
- silently resolve ambiguous entities;
- create a new route or contract at runtime;
- judge conformance of its own output.

An external model receives only the user request and the approved route, argument, and schema metadata required by the adapter contract. Database rows, fixture contents, and evidence bundles are not sent to an external model unless a separately reviewed ADR changes this boundary. [ADR-0004](adr/0004-mcp-surface-and-the-tool-result-boundary.md) changes it for the MCP surface: a tool result, evidence bundle included, is returned to the host model that called the tool, and the "no evidence, no answer" guarantee ends at that tool boundary.

### 3.4 Fail closed

Missing, ambiguous, unsupported, and out-of-scope cases are expected results, not exceptional cases to hide.

The runtime must preserve explicit status families such as `not_found`, `ambiguous`, `invalid_request`, `unsupported`, and `coverage_gap`. `not_found` means the approved data scope covers the question but contains no matching row. `coverage_gap` means the approved data scope does not contain the coverage needed to answer the question; when the runtime cannot establish coverage, it returns `coverage_gap` rather than `not_found`.

`unsupported` has the same layer-neutral meaning in the adapter and runtime: the request cannot be represented by an approved contract at the layer that produced the outcome. The trace identifies that layer. A negative case must not silently fall back to semantic RAG and present retrieved text as factual evidence.

### 3.5 Evaluation drives complexity

Start with the simplest method that meets a measured need. Add an LLM, BM25, vector search, or another component only when a representative evaluation set shows a useful improvement without weakening the safety boundary.

### 3.6 Scoped canonical entity references

A canonical entity reference identifies an entity occurrence within an explicit source snapshot. A message or signal name alone is not canonical.

For the initial requirements source:

- each source snapshot belongs to exactly one project, one revision, and one network or CAN bus scope;
- the network or CAN bus scope is mandatory and must be preserved through entity resolution, authoritative retrieval, and source trace;
- identical message or signal names in different source snapshots identify distinct entity occurrences;
- a message name is a local lookup key within its source snapshot;
- a signal name is a local lookup key within its parent Message and source snapshot.

Continuity or equivalence across projects, revisions, or buses is a separate relation. It requires evidence from an approved source and must not be inferred from name equality.

A relation whose endpoints belong to different source snapshots carries every endpoint's scoped canonical entity reference plus the source scope and provenance of the artifact that asserts the relation. The runtime must reject the relation request if any participating endpoint or asserting-artifact scope is unresolved, and it must not infer that a relation survives a superseded snapshot.

The runtime never supplies an unrecorded default project, revision, bus, or source snapshot, including a "latest" value or the only currently loaded value. An explicitly reviewed selection policy may resolve a scope dimension; until such a policy exists, unresolved scope produces `ambiguous`, exposes the candidate scopes, and requires explicit selection or abstention. An unapproved alias cannot by itself auto-resolve a request to one candidate.

The exact serialized reference shape, physical database key, uniqueness constraints, approved alias provenance, and fixed-SQL parameters are frozen in the applicable Milestone 1 or Milestone 3 contracts. Those contracts must preserve these identity and scope invariants.

### 3.7 PostgreSQL runtime and normalized fixture boundary

PostgreSQL is the runtime database for both local development and the deployed system. The initial implementation uses a reproducible local PostgreSQL environment. The public deployment target is Azure App Service with Azure Database for PostgreSQL Flexible Server.

The initial public implementation begins from version-controlled, normalized synthetic fixtures. Raw DBC or ARXML ingestion is not a prerequisite for building the database or completing the core runtime.

Database provisioning and runtime access are separate responsibilities:

- a setup identity may create the approved schema and load synthetic fixtures through a controlled provisioning path;
- the application runtime uses a distinct least-privilege, read-only database identity;
- runtime requests must not create, alter, or load data;
- source traces must describe the fixture provenance that actually exists and must not cite fictional DBC or ARXML artifacts.

The Milestone 1 PostgreSQL compatibility boundary must be a subset of the capabilities available on the declared Azure Database for PostgreSQL Flexible Server target. Repeatable provisioning means that the same versioned schema and fixtures produce the same logical rows, constraints, and contract-visible values, and that registered queries produce the same normalized ordering. Identical surrogate keys are required only when a public contract exposes them.

A future raw-source adapter may map an approved format into the current normalized data contract only after its own fixtures, provenance rules, and tests are reviewed. If a real format cannot be represented without changing the normalized contract, that change requires an ADR and updated contracts; parity is not assumed in advance.

The exact PostgreSQL version, required extensions, schema-provisioning mechanism, serialized fixture format, key-generation strategy, collation and ordering strategy, and Azure identity and networking configuration are frozen in the applicable Milestone 1 or Milestone 5 contracts. The architecture decision is recorded in [ADR-0001](adr/0001-postgresql-runtime-and-normalized-fixture-boundary.md).

## 4. Target user flow

### 4.1 Explicit canonical reference

When the validated request contract contains a canonical entity reference, the expected core-runtime flow is:

```text
bounded request with explicit source scope
-> approved route and explicit arguments
-> contract validation
-> registered fixed SQL template
-> normalized facts or relation rows
-> evidence bundle and limitations
```

The canonical entity reference may be supplied directly or constructed deterministically from an explicitly selected source scope and local lookup keys. The initial runtime implements this path with deterministic routing. A later Thin LLM Adapter may produce the same approved route contract, but it does not replace scope selection, validation, or fixed SQL. API and rendering surfaces are added in Milestone 4 and must not change the normalized result.

### 4.2 Missing or ambiguous canonical reference

When the user describes an entity without providing enough information to form a canonical entity reference, the expected flow after Milestone 3 is:

```text
natural-language request
-> Thin LLM Adapter identifies route but reports missing entity
-> Entity Discovery searches an approved entity registry
-> ranked candidates with canonical entity references
-> explicit selection, or abstention when ambiguous
-> existing route contract with canonical entity reference
-> registered fixed SQL template
-> evidence-backed result
```

The approved entity registry is the allowlisted set of entities that discovery may return. It contains canonical entity references and lookup metadata such as names and aliases, but it is not an authoritative fact source. Discovery may return only references that are resolvable within the approved data scope. Registry refresh, integrity, and approved alias-provenance rules are defined in the Milestone 3 contract.

An alias is lookup metadata, not authority. Until an alias policy is reviewed and recorded, an alias may contribute candidates but cannot by itself select one candidate or bypass explicit scope resolution.

The initial discovery implementation should prefer exact identifiers, approved aliases, and lexical matching. BM25 and vector search are optional candidate-retrieval methods, not fact sources.

### 4.3 Adapter outcome contract

The future adapter returns one of three outcome families:

- `executable`: an approved route and all required explicit parameters are present;
- `needs_entity_discovery`: the route is known but a canonical entity reference is missing;
- `unsupported`: the request cannot be represented by an approved contract.

The adapter outcome is validated deterministically before any database access. Before Milestone 3, `needs_entity_discovery` is a terminal, non-executable outcome. Milestone 2 freezes a versioned minimum outcome contract that Milestone 3 may consume or extend only compatibly; a breaking payload change reopens the applicable acceptance gate.

## 5. Initial product scope

The first executable milestone is a deterministic backend runtime over newly authored, normalized synthetic data in a reproducible local PostgreSQL environment. Its bounded behavior includes:

- controlled schema provisioning and fixture loading outside the query runtime;
- a dedicated read-only runtime database identity;
- message facts;
- signal facts;
- one approved source-to-target signal mapping relation;
- a small set of representative fixed-rule routes;
- evidence bundles, source traces, and explicit limitations;
- deterministic negative behavior;
- a conformance runner and read-only database invariance checks.

Before implementation begins, the architecture-level shapes of the data, route, result, evidence, and query-template-registry contracts, together with their review procedure, must be reviewed and committed. Individual routes, SQL templates, and fixtures are then added incrementally under Section 10; the contract and applicable fixtures for a behavior slice must be reviewed before that slice's code.

Raw DBC or ARXML ingestion is not required for this milestone. The normalized fixtures must nevertheless preserve representative structural cases such as source-snapshot differences, entity-name collisions, relations, ambiguity, and negative outcomes. They must not imitate real project, revision, bus, or artifact names.

## 6. Deferred scope

The following are deliberately deferred until the deterministic backend is stable:

- Thin LLM Adapter;
- Entity Discovery;
- vector search;
- broad retrieval over document chunks;
- TSV export and other renderers;
- conversational and streaming adapters;
- UI;
- raw DBC, ARXML, and other source-format ingestion adapters;
- Azure App Service and Azure Database for PostgreSQL Flexible Server deployment until Milestone 5;
- production observability and user-feedback collection.

Deferred does not mean pre-approved. Each item requires a contract, evaluation fixtures, and a separate reviewable slice.

## 7. Non-goals

This project does not aim to provide:

- free-form natural-language-to-SQL generation;
- arbitrary database exploration;
- a general-purpose chat assistant;
- generic report generation without a concrete user workflow;
- semantic-search passages presented as authoritative facts;
- automatic resolution of ambiguous entities without an approved policy;
- hidden expansion to new data sources, entities, relations, or business rules;
- production data, credentials, or content copied from private sources.

Report generation may be reconsidered only after a real use case and a stable underlying evidence contract exist.

## 8. Entity Discovery evaluation policy

Entity Discovery will be added only after an approved entity registry and a labeled evaluation set exist. The evaluation set must include:

- exact identifier requests;
- approved aliases and spelling variations;
- descriptive semantic requests;
- requests where the entity name is present but source scope is missing or partial;
- requests where the same name occurs in more than one source snapshot;
- multiple plausible candidates;
- no-match requests;
- out-of-scope requests.

Candidate methods should be compared using, at minimum:

- Recall@k for the canonical entity reference;
- ranking quality such as MRR;
- false-resolution rate;
- abstention quality on ambiguous and no-match inputs;
- latency and operational complexity;
- end-to-end task completion after candidate selection.

Vector search is adopted only if it provides a material improvement on the difficult semantic cases while keeping false resolution, latency, and complexity within a pre-registered and explicitly accepted budget.

## 9. Milestones and acceptance gates

Every acceptance-gate item is either an automated assertion over registered inputs or a recorded human decision with named evidence. A numeric adoption threshold is registered before the run it judges. Reporting a metric without a pre-registered pass condition does not satisfy a gate.

### Milestone 0: Charter freeze

**Deliverables**

- project charter;
- repository-level agent rules;
- minimal README.

**Acceptance gate**

- product boundary, architecture responsibilities, milestone order, and public-safety rules receive a recorded human review;
- no runtime code is added.

### Milestone 1: Deterministic PostgreSQL runtime

**Deliverables**

- reviewed architecture-level contract shapes and slice-specific runtime, data, routing, result, evidence, and evaluation contracts;
- source-snapshot and canonical-entity-reference contracts that preserve project, revision, bus, and parent-Message scope;
- a declared PostgreSQL compatibility boundary, including required version and extensions;
- reproducible local PostgreSQL provisioning from version-controlled schema definitions and normalized synthetic fixtures;
- separate setup and fixture-loading access from a dedicated least-privilege, read-only runtime identity;
- fixed SQL template registry and negative safeguards;
- facts and relation result contracts;
- deterministic router;
- conformance runner with normalized expected outputs and an exact `pass`, `review`, and `fail` outcome contract;
- failure-class tagging for conformance and runtime failures.

**Acceptance gate**

- every test registered by the Milestone 1 contract passes;
- the conformance run is deterministic, has no `fail` result, and has a recorded disposition for every `review` result;
- a `fail` result cannot be accepted as a pass by human override;
- unsupported and contract-defined No-Go requests never reach factual SQL success;
- an automated data-level check confirms that the loaded database satisfies the identity and scope invariants in Section 3.6;
- the runtime identity cannot write data or change the schema;
- representative source tables remain unchanged throughout conformance execution;
- no arbitrary SQL path exists.

### Milestone 2: Thin LLM Adapter

**Deliverables**

- schema-constrained route and argument extraction;
- versioned minimum adapter outcome contract;
- evaluation cases for executable, missing-entity, invalid, and unsupported requests;
- traces that separate adapter output from deterministic runtime execution.

**Acceptance gate**

- adapter output can invoke only approved contracts;
- explicit canonical entity references are preserved rather than rewritten;
- missing identifiers or scope do not become fabricated values;
- before Milestone 3, every `needs_entity_discovery` result remains terminal and cannot reach database execution;
- at least one scope-complete `executable` case runs end to end through the deterministic runtime;
- the adapter is compared with the Milestone 1 deterministic baseline on the same frozen evaluation set and is adopted only when it meets pre-registered task-coverage and false-resolution thresholds without weakening negative behavior;
- the model or reproducible provider version and decoding configuration are pinned by the Milestone 2 evaluation contract, and a material change reopens this gate.

### Milestone 3: Entity Discovery

**Deliverables**

- approved entity registry with canonical entity references and approved aliases;
- labeled discovery evaluation set;
- lexical baseline and optional BM25/vector variants;
- ranked candidate contract and abstention behavior;
- candidate selection connected to the existing fixed-SQL runtime.

**Acceptance gate**

- each adopted method meets the pre-registered retrieval, false-resolution, and abstention thresholds for every governed query class;
- ambiguous requests do not silently resolve;
- selected candidates are canonical entity references that are present in the approved entity registry and resolvable in the approved data scope;
- unapproved aliases do not auto-resolve to a single candidate;
- final facts still come only from the fixed-SQL runtime.

### Milestone 4: End-to-end workflow and export

**Deliverables**

- stable API flow from request or candidate selection to evidence-backed result;
- TSV export with a frozen column contract (moved out of scope by [ADR-0004](adr/0004-mcp-surface-and-the-tool-result-boundary.md) until a measured need exists);
- end-to-end task fixtures;
- minimal UI only if it materially supports evaluation or use.

**Acceptance gate**

- exported values are derived from the normalized runtime result;
- rendering does not add or alter facts;
- representative workflows complete end to end with traceable failures.

### Milestone 5: Azure deployment and learning loop

This milestone begins from the working Milestone 1 through Milestone 4 system. Contract, conformance, failure classification, and end-to-end evaluation begin in earlier milestones; Milestone 5 adds deployment evidence and improvement from observed use.

**Deliverables**

- deployment of the same PostgreSQL-backed runtime to Azure App Service and Azure Database for PostgreSQL Flexible Server;
- deployment, configuration, database-identity, secret-handling, and networking contracts;
- least-privilege read-only database access for the deployed application;
- structured logs, latency/error metrics, and evaluation hooks;
- an evaluation-driven improvement loop and, when real users exist, a privacy-safe user-feedback workflow.

**Acceptance gate**

- the deployed environment passes the same representative conformance and end-to-end contracts as the local PostgreSQL environment;
- reproducible provisioning definitions and a recorded deployed conformance run remain available even if the demo environment is later stopped;
- deployment does not introduce a second schema, fixture meaning, SQL-template behavior, or fallback runtime;
- the deployed runtime identity cannot write data or change the schema;
- secrets and environment-specific configuration stay outside the repository;
- observed failures can be classified as data, retrieval, contract, runtime, or presentation problems.

## 10. Change policy

Implementation proceeds in small vertical slices. One pull request should add one independently reviewable behavior and its tests.

Before adding a route, entity, relation, data source, SQL template, or status behavior:

1. update the relevant contract;
2. add fixtures for every outcome the behavior can produce, including applicable positive, negative, ambiguity, abstention, `not_found`, `invalid_request`, `unsupported`, and `coverage_gap` cases;
3. record source meaning and limitations;
4. define the automated assertion or recorded human decision that accepts the slice;
5. obtain human review;
6. then implement.

Architecture decisions that materially change this charter should be recorded in an ADR rather than hidden inside implementation code.

## 11. Public release conditions

The repository remains private until the owner records an explicit release decision. Fixtures and examples are synthetic throughout; they must not contain production records or real-world identifiers.

Before any public release:

- use synthetic fixtures and portable placeholder identifiers only;
- ensure source traces describe only artifacts that actually exist in this repository;
- exclude production records, credentials, secrets, and internal references;
- review the current tree, full Git history, and public PR or issue content, not only the latest files;
- run secret and sensitive-string scans;
- confirm dependency licenses and add an explicit repository license;
- document limitations;
- record the owner's release decision.

## 12. Open decisions

These questions are intentionally not answered by this charter:

- the exact representative task set and normalized expected results for the first Milestone 1 contract;
- the exact serialized canonical-entity-reference shape, database keys, and fixed-SQL parameter schema;
- maximum row counts, pagination, truncation, and timeout behavior for each registered query;
- the exact route and result schemas for the post-Milestone 1 API;
- approved alias provenance, registry refresh and integrity rules, confidence thresholds, and selection policy for Entity Discovery;
- whether vector search materially outperforms lexical and BM25 baselines;
- the final TSV schema;
- the exact PostgreSQL version, extensions, schema-provisioning tool, serialized fixture format, key-generation strategy, and ordering/collation rules;
- the Azure authentication, networking, service sizing, retention, teardown, and operating budget within the fixed App Service and PostgreSQL Flexible Server topology.

They should be resolved in the named milestone contract with evidence from the preceding milestone, not by adding speculative implementation.
