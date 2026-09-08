# Milestone 3 Entity Discovery Contract v0.1

## 1. Identifier and version

**Identifier:** `entity-discovery-v0.1`

**Version:** `0.1.0` — the identifier names the document; the version tracks its obligations. `0.1.0` proposes the contract.

This contract covers the Entity Discovery half of the Milestone 3 deliverables in [Project Charter](../PROJECT_CHARTER.md) Section 9, and the evaluation family that judges it. In [Contract Shape Framework](README.md) Section 5 terms it combines the data, route, result, evidence, query-template-registry, runtime, and evaluation families for one layer, as [MVP Runtime Contract v0.1](mvp-v0.1.md) does for its own. Framework Section 5 assigns responsibilities per family; it does not require one document per family.

It is a **separate document from `mvp-v0.1`, not an amendment to it.** `mvp-v0.1` is `Accepted`, its Section 9 names "Milestone 3 contract" as the owner of the deferred Entity Discovery row, and its Section 10 makes any change to it a recorded human decision. Nothing here changes a word of it. Section 3.3 below lists what this contract inherits from it, and the one place where the two meet in a way the repository owner should confirm.

The version changes when any observable obligation in Section 4, 5, 6, or 7 changes. Adding a fixture case that exercises an existing obligation is a patch change. Adding or removing a route, template, retrieval method, match tier, status condition, or evidence field is a minor change. Registering the evaluation set and the adoption thresholds reserved in Section 8.3 is a minor change. Removing or weakening an obligation is not permitted at the contract layer; see Section 10.

## 2. Status

**Status:** `Proposed`

Not binding on implementation. Under [Contract Shape Framework](README.md) Section 2, an implementation slice may be accepted only against a contract in `Accepted` state, and a `Proposed` contract may be cited as direction but does not satisfy the pre-implementation review the [Development Workflow](../DEVELOPMENT_WORKFLOW.md) requires. **No Milestone 3 code, schema, or fixture may be written against this document while this line reads `Proposed`.**

Acceptance is the event in Framework Section 2.1: the repository owner records the required human review of this contract and its acceptance evidence on this contract's own pull request, and records merge approval. No milestone gate is involved, and Framework Section 2.1 states that acceptance never waits for one.

Section 10 sets the preconditions for acceptance and Section 8.2 discharges the second of them.

## 3. Scope

### 3.1 What this contract fixes

- The **approved entity registry**: an allowlist of entity occurrences that discovery may return, the approved aliases attached to them, the provenance every registry row carries, its integrity rules, and its refresh rule.
- The **discovery request**: its route, its parameters, and the precondition that its source scope is already resolved to exactly one snapshot.
- **Discovery normalization** and the discrete **match tiers** that replace a confidence score.
- The **ranked candidate contract**: what a candidate is, what it may carry, how the list is ordered, how long it is, and how truncation is reported.
- **Auto-resolution and abstention**: the single condition under which discovery may return one canonical entity reference without an explicit selection, and the requirement that everything else abstains into candidates or a negative outcome.
- The **verified selection path** that connects a selected candidate to the `mvp-v0.1` fixed-SQL runtime, and what makes a selection's provenance verifiable rather than asserted.
- The **lexical baseline method** `M-LEX-1`, and the registration rule every later candidate-retrieval method must satisfy.
- The **labeled discovery evaluation set**: its query classes, its authoring rules, and the definitions of every metric [Project Charter](../PROJECT_CHARTER.md) Section 8 requires a method comparison to report.
- The **evidence obligations** of a discovery result, including alias provenance and the registry digest it was computed against.
- The **outcome families** discovery can produce, and the fact that `success` is not among them.

### 3.2 What this contract does not fix

- **The numeric adoption thresholds, and the evaluation cases themselves.** Section 8.3 is reserved for their registration; Section 9 carries the row. Charter Section 9 requires a threshold to be registered before the run it judges, not before the contract is accepted.
- **BM25, vector search, or any other retrieval method beyond `M-LEX-1`.** Section 4.9 fixes how one is registered; registering one is a later minor version.
- **Any scope-selection policy that resolves a scope dimension automatically.** That row belongs to `mvp-v0.1` Section 9 and stays there. This contract requires a resolved scope and resolves no scope dimension.
- **Which Section governs a request whose scope is incomplete *and* whose entity reference cannot be formed.** That is the open `mvp-v0.1` question in [#43](https://github.com/OKJ1105/evidence-first-rag/issues/43). Section 4.3 requires a complete scope as a precondition, which neither answers that question nor prejudices it.
- **Any API, renderer, or export surface.** Milestone 4 owns those. Discovery here is a route on the existing runtime, not an HTTP interface.
- **Ingestion of any raw source format.** The registry is loaded from the version-controlled fixtures, as `mvp-v0.1` Section 4.11 loads its own.
- **The alias approval process outside this repository.** `approval_reference` is an opaque citation of a recorded decision; this contract fixes that one is required and what it must accompany, not how it is obtained.

Section 9 records each of these with its owning slice.

### 3.3 What this contract inherits from `mvp-v0.1`, and the one place it extends it

These obligations of [MVP Runtime Contract v0.1](mvp-v0.1.md) apply unchanged to every path this contract defines. They are restated here as inherited, not re-decided, and this contract may not weaken them ([Contract Shape Framework](README.md) Section 4).

| Inherited | From |
| --- | --- |
| Registry safeguards: no unregistered template executes, every registered SQL text begins with `SELECT`, write and DDL keywords are refused at registration, every variable is a named allowlisted parameter, no string interpolation, no caller-supplied SQL, table, or column, ordering belongs to the template | `mvp-v0.1` Section 4.4 |
| Two database identities; the runtime opens every connection as the read-only identity inside a read-only transaction and never holds the provisioning credentials | `mvp-v0.1` Section 4.3 |
| `C` collation, byte-wise ordering, total orderings with explicit `NULLS LAST`, no rounding, repeatable provisioning, surrogate keys in no public payload | `mvp-v0.1` Sections 4.2 and 6 |
| The canonical message and signal reference tuples, and every Section 4.2 identity and scope rule — including that the runtime never supplies a missing scope dimension and never selects the newest, highest, or only loaded row | `mvp-v0.1` Section 4.2, [Project Charter](../PROJECT_CHARTER.md) Section 3.6, [ADR-0002](../adr/0002-scoped-canonical-entity-identity.md) |
| `evidence_bundle`, `source_trace`, and `limitations` on every result including every negative outcome, with the required keys | `mvp-v0.1` Section 7 |
| Fixture serialization: JSON Lines under `fixtures/`, natural keys only, `SAMPLE_*` ASCII identifiers, abort with no partial load | `mvp-v0.1` Section 4.11 |
| Fact lookup is byte-exact. No case folding, no Unicode normalization, no trimming on a lookup key | `mvp-v0.1` Section 6 |
| The `unsupported`, `invalid_request`, `coverage_gap`, `not_found`, and `ambiguous` meanings | `mvp-v0.1` Section 5, Charter Section 3.4 |

**The one extension, and why it is recorded rather than assumed.** `mvp-v0.1` Section 4.3 enumerates the runtime identity's privileges as `SELECT` only *on the four tables* of its Section 4.1. The registry tables in Section 4.1 of this contract are additional tables the same identity must read. This contract grants that identity `SELECT` on its own tables and no other privilege on them; no write, DDL, or escalation is added anywhere, the read-only invariance obligations of `mvp-v0.1` Section 4.10 are extended to the new tables by Section 8 below, and the four `mvp-v0.1` tables are unaffected. Nothing is weakened.

Whether `mvp-v0.1` Section 4.3's enumeration should be patched to say so is nevertheless a change to an `Accepted` contract, and its Section 10 assigns that to the repository owner. It is recorded as a decision in Section 9 rather than taken here. Implementation of this contract does not depend on the answer: the grants this contract fixes are the same either way.

**What this contract deliberately does not touch in `mvp-v0.1`.** The adapter's fixed instructions and vocabulary payload are unchanged, so the Section 4.6 digests are unchanged and the Milestone 2 comparison is not reopened. The adapter's route vocabulary stays the three routes of `mvp-v0.1` Section 4.5 plus the literal `unsupported`; the routes this contract registers are not adapter-selectable, and Section 4.12 forbids the automatic chaining that would make them so.

## 4. Normative requirements

### 4.1 The approved entity registry

Four tables, additional to the four in `mvp-v0.1` Section 4.1 and referencing them. Column order is normative for the schema definition; result column order is fixed per template in Section 4.4.

**`approved_entity`** — the allowlist. One row per entity occurrence that discovery may return.

| Column | Type | Notes |
| --- | --- | --- |
| `approved_entity_id` | surrogate key | Not exposed in any public payload. |
| `entity_kind` | text, not null | `message` or `signal`. No other value is loadable. |
| `message_occurrence_id` | nullable reference to `message_occurrence` | Non-null exactly when `entity_kind` is `message`. |
| `signal_occurrence_id` | nullable reference to `signal_occurrence` | Non-null exactly when `entity_kind` is `signal`. |
| `approval_reference` | text, not null | The recorded human decision that admitted this occurrence to the registry. Opaque to the runtime; never parsed. |
| `approved_at` | timestamp, not null | Registry provenance only. Never used to rank or to select. |

A check constraint enforces that exactly one of the two occurrence references is non-null and that it matches `entity_kind`. Unique constraints on `message_occurrence_id` and on `signal_occurrence_id`, each over its non-null rows: an occurrence is approved once or not at all.

Both references are **foreign keys into the `mvp-v0.1` tables**, which is what makes Charter Section 9's gate item "selected candidates … resolvable in the approved data scope" a database constraint rather than a check that could be forgotten. A registry row naming an occurrence that is not loaded cannot exist.

**`approved_alias`** — lookup metadata for an approved entity.

| Column | Type | Notes |
| --- | --- | --- |
| `approved_alias_id` | surrogate key | Not exposed. |
| `approved_entity_id` | reference, not null | The entity this alias names. |
| `alias_text` | text, not null | The alias exactly as approved. Byte-exact; not normalized at rest. |
| `alias_kind` | text, not null | `approved_alias` or `spelling_variant`. |
| `asserting_snapshot_id` | reference to `source_snapshot`, not null | The snapshot of the artifact that asserts the alias. |
| `approval_reference` | text, not null | The recorded human decision that approved this alias. |
| `approved_at` | timestamp, not null | Provenance only. |

Unique constraint on `(approved_entity_id, alias_text)`.

**There is deliberately no unique constraint on `alias_text` alone.** Two entities may carry the same approved alias, and an alias may equal another entity's lookup key. That is a collision to be surfaced, not a corruption to be rejected: Section 4.7 makes such a term abstain into candidates. A uniqueness constraint here would move a fail-closed outcome into a load-time error and would tempt a later author to delete one side of the collision.

**`entity_match_term`** — the derived matching surface, built during provisioning from the two tables above. It stores no fact and adds no name; it is the normalization of Section 4.5 applied once, at load, so that the runtime binds one parameter instead of assembling a query.

| Column | Type | Notes |
| --- | --- | --- |
| `entity_match_term_id` | surrogate key | Not exposed. |
| `approved_entity_id` | reference, not null | |
| `match_kind` | text, not null | `lookup_key`, `approved_alias`, or `spelling_variant`. |
| `match_text` | text, not null | The lookup key of the occurrence, or the `alias_text`. Byte-exact. |
| `match_tokens` | text array, not null | `match_text` under the Section 4.5 normalization. Never empty. |
| `approved_alias_id` | nullable reference | Non-null exactly when `match_kind` is not `lookup_key`. Carries the provenance Section 7 requires in the trace. |

Unique constraint on `(approved_entity_id, match_kind, match_text)`. Exactly one `lookup_key` row exists per approved entity, and its `match_text` is that occurrence's `message_key` or `signal_key`.

**`entity_registry_state`** — exactly one row, written by the provisioning identity after the three tables above are loaded.

| Column | Type | Notes |
| --- | --- | --- |
| `registry_digest` | text, not null | The Section 4.2 digest of the loaded registry. |
| `built_at` | timestamp, not null | Provisioning provenance. Never used to select or to rank. |

A check constraint permits at most one row.

### 4.2 Registry provenance, integrity, and refresh

These are the "approved alias provenance, registry refresh and integrity rules" that [Project Charter](../PROJECT_CHARTER.md) Section 12 and Section 4.2 assign to this contract.

**Provenance.** Every `approved_entity` and every `approved_alias` row carries an `approval_reference` and an `approved_at`. An alias additionally carries the snapshot of the artifact that asserts it. A row missing any of them cannot be loaded — they are `not null` columns, not a convention. `approval_reference` is opaque: the runtime never parses it, never ranks by it, and never presents it as a fact. It is carried into `source_trace` (Section 7) so that a reader can trace an alias back to the decision that approved it.

**Integrity, enforced at load:**

1. An alias's `asserting_snapshot_id` is the snapshot of its entity's own occurrence. An alias asserted by another snapshot would carry a cross-snapshot claim, and Charter Section 3.6 makes continuity across snapshots an evidence-backed *relation*, never a naming fact. An alias that needs to say "this is the same signal as the one in the earlier snapshot" is a `signal_mapping` row under `mvp-v0.1` Section 4.1, not an alias.
2. `entity_match_term` is derived, not authored. Every row's `match_tokens` equals the Section 4.5 normalization of its `match_text`, every approved entity has exactly one `lookup_key` row whose `match_text` is that occurrence's key, and every non-`lookup_key` row corresponds to exactly one `approved_alias` row. A data-level check asserts all three against the loaded database and is part of the acceptance evidence in Section 8.
3. `entity_kind` and `alias_kind` accept only the values listed in Section 4.1.
4. The registry may be a strict subset of the loaded occurrences. **Absence from the registry is not absence from the data**, and Section 7 requires a `not_found` result to say so.

**Refresh.** The registry is loaded in the same provisioning phase as the `mvp-v0.1` Section 4.11 fixtures, by the provisioning identity, from version-controlled JSON Lines files under `fixtures/`, before the runtime identity ever connects. There is no incremental update path and no runtime write path: the runtime identity holds `SELECT` and nothing else on all four tables of Section 4.1. **A refresh is a re-provision.** A partial load aborts, as `mvp-v0.1` Section 4.11 requires of its own files.

**The registry digest.** `registry_digest` is the SHA-256, lower-case hexadecimal, of the concatenation of one line per registry row, each line a UTF-8 JSON object with keys sorted byte-wise and no insignificant whitespace, terminated by `\n`, in this order: every `approved_entity` row, then every `approved_alias` row, then every `entity_match_term` row; within each group, sorted byte-wise by the serialized line. Every row is serialized by its **natural keys only** — the canonical reference of its occurrence, `entity_kind`, `alias_text`, `alias_kind`, the asserting snapshot's four scope dimensions, `approval_reference`, `approved_at`, `match_kind`, `match_text`, `match_tokens` — and never by a surrogate value, which `mvp-v0.1` Section 6 permits to differ between provisioning runs.

The digest is what makes a discovery result reproducible and a selection verifiable. It appears in every discovery `evidence_bundle` (Section 7), in every candidate-set digest (Section 4.8), and in every evaluation artifact (Section 4.10). A registry change changes it, which is the intended signal: a candidate set computed against one registry state cannot be selected from against another.

### 4.3 The discovery request and its preconditions

One route, `entity_discovery`. Its arguments are named, allowlisted, and validated before any database access, as `mvp-v0.1` Section 4.5 requires of every route.

| Argument | Required | Notes |
| --- | --- | --- |
| `project_code`, `revision_label`, `network_name`, `snapshot_label` | all four required | The resolved source scope. |
| `entity_kind` | required | `message` or `signal`. |
| `parent_message_key` | optional, and permitted only when `entity_kind` is `signal` | Narrows the search to one parent Message occurrence. Supplying it with `entity_kind` = `message` is `invalid_request`. |
| `term` | required | The user's free text naming or describing the entity. At most 200 characters, and at least one token after the Section 4.5 normalization; otherwise `invalid_request`. |

**Scope is a precondition, not a search dimension.**

- A request that omits or under-specifies any of the four scope dimensions is governed by `mvp-v0.1` Section 4.2 exactly as it stands: the runtime returns `ambiguous` and lists the candidate scopes from `TPL_SNAPSHOT_CANDIDATES_V1`. **No discovery template executes.** This contract adds nothing to that rule, narrows nothing in it, and does not decide the ordering question in [#43](https://github.com/OKJ1105/evidence-first-rag/issues/43).
- A fully specified scope that matches no snapshot is `coverage_gap`, per `mvp-v0.1` Section 5.
- Discovery therefore never resolves a scope dimension, and Charter Section 4.2's rule that an alias "cannot … bypass explicit scope resolution" holds by construction: an alias is only ever consulted inside one already-resolved snapshot.

**`parent_message_key` is optional on purpose.** A signal's identity requires its parent Message (Charter Section 3.6), and discovery is the step that finds it: a user who knew the parent would not be discovering. Every candidate therefore carries the **complete** canonical signal reference, its parent included, and a term matching one signal key under two different parent messages in one snapshot produces two candidates and no auto-resolution (Section 4.7, fixture `DX-005`).

### 4.4 Registered templates

Registered under `mvp-v0.1` Section 4.4's safeguards, which apply unchanged. Each records its name, version, full inspectable SQL text, allowed parameter names, result column list in order, ordering clause, and declared limitations.

| Template | Allowed parameters | Result ordering | Row limit |
| --- | --- | --- | --- |
| `TPL_REGISTRY_STATE_V1` | none | none — at most one row | 1 |
| `TPL_DISCOVERY_EXACT_V1` | the four scope dimensions, `entity_kind`, `term`, optional `parent_message_key` (all scope dimensions and `entity_kind` required) | `match_tier`, `message_key`, `signal_key` `NULLS LAST`, `match_text` | 11 |
| `TPL_DISCOVERY_LEXICAL_V1` | the same, with `normalized_term` in place of `term` | `match_tier`, `message_key`, `signal_key` `NULLS LAST`, `match_text` | 11 |

`TPL_DISCOVERY_EXACT_V1` returns tier 1 and tier 2 rows only: rows whose `match_text` equals the bound `term` byte for byte. `TPL_DISCOVERY_LEXICAL_V1` returns tier 3 and tier 4 rows, matching on `match_tokens` against the bound normalized term as an array, so a variable number of tokens is one bound parameter and not an assembled query. Neither returns any column of `message_occurrence` or `signal_occurrence` other than the canonical reference columns; Section 4.12 forbids an attribute in a discovery result, and the registered result column list is where that is enforced.

**The row limit is 11 because `k` is 10.** An eleventh row means the candidate list was truncated, which Section 7 requires `limitations` to record. This is the overflow-detection pattern `mvp-v0.1` Section 4.4 uses for its facts templates, applied to a list that legitimately has many rows.

Both discovery templates bind `parent_message_key` as an optional parameter that, when null, imposes no restriction, and when non-null restricts to that one parent Message occurrence within the resolved snapshot. `mvp-v0.1` Section 4.4's rule that a parameter outside the allowlist is refused, and that a missing required parameter is refused, applies to both.

The runtime identity's `statement_timeout` of 5 s (`mvp-v0.1` Section 4.4) applies. A timeout is an operational fault, not an outcome.

### 4.5 Discovery normalization and the match tiers

**Normalization.** For a text `t`, `normalize(t)` is: map each ASCII upper-case letter to its lower-case form; replace every character that is not `a-z` or `0-9` with a single space; split on spaces; drop empty tokens. The result is an ordered list of tokens. It is defined on bytes, uses no locale, and is identical on every platform — the same reason `mvp-v0.1` Section 6 chose the `C` collation. Fixture identifiers are ASCII by `mvp-v0.1` Section 4.11, so nothing in the registered inputs depends on the treatment of a non-ASCII byte, which this normalization maps to a separator.

**This normalization applies to candidate generation only.** It never applies to a fact lookup. `mvp-v0.1` Section 6 is unchanged: a fact lookup whose key differs from a stored key by case is `not_found`, and the reference this contract hands to a fact route is a byte-exact key taken from the registry, never a normalized string. `mvp-v0.1` Section 6 anticipated exactly this split when it recorded that "any future approved-alias mechanism belongs to Entity Discovery (Milestone 3), not to comparison semantics".

**The match tiers.** A discovery request with term `T` produces, for each approved entity in the resolved scope of the requested kind (and under `parent_message_key` when supplied), the lowest-numbered tier any of its `entity_match_term` rows satisfies:

| Tier | Condition | Auto-resolution eligible |
| --- | --- | --- |
| 1 | `match_kind` is `lookup_key` and `match_text` equals `T` byte for byte | yes |
| 2 | `match_kind` is `approved_alias` or `spelling_variant` and `match_text` equals `T` byte for byte | yes |
| 3 | `normalize(match_text)` equals `normalize(T)` as an ordered token list | no |
| 4 | every token of `normalize(T)` occurs in `match_tokens` | no |
| — | none of the above | not a candidate |

A tier is a discrete, inspectable statement about *how* a term matched. It is the confidence vocabulary this contract fixes, in place of the numeric confidence threshold [Project Charter](../PROJECT_CHARTER.md) Section 12 leaves open. The reason is that a float invites a threshold nobody can interpret and that drifts with an implementation detail, while a tier is checkable by reading the two strings. Section 4.9 requires any later method that computes a score to map it into this vocabulary, and permits no method to auto-resolve above tier 2.

Tier 3 exists and does not auto-resolve on purpose: a term differing from a stored key only by case is precisely what `mvp-v0.1` Section 6 makes fail closed on the fact path, and discovery answers it with a candidate a person must select, not with a resolution.

### 4.6 The candidate contract

A **candidate** is one approved entity, with the complete canonical entity reference of its occurrence and the evidence of how it matched. One entity appears at most once in a candidate list: where several of its `entity_match_term` rows match, the candidate carries the best one — lowest tier, then lowest `match_text` in byte order — and the others are not separate candidates.

Each candidate carries exactly:

- `entity_kind`;
- the canonical entity reference: the four scope dimensions, `message_key`, and for a signal the parent's `message_key` and the `signal_key`;
- `match_tier` and `matched_text`, the `match_text` that produced the tier;
- `match_kind`, and for an alias match the `approval_reference` and the asserting snapshot's scope, which Section 7 also carries into `source_trace`;
- `rank`, its 1-based position in the ordering below.

It carries **no attribute of the entity** — no `transmit_period_ms`, `frame_identifier`, `unit_label`, `scale_factor`, or any other column of the `mvp-v0.1` Section 4.1 fact tables — and no score. Section 4.12 states the rule; this is where the payload enforces it.

**Ordering.** Ascending `match_tier`; then the canonical reference in byte order (`message_key`, then `signal_key` with `NULLS LAST`); then `matched_text` in byte order; then `match_kind` in the order `lookup_key`, `approved_alias`, `spelling_variant`. The first three are total on their own — no two distinct candidates share a canonical reference — so the ordering is total and reproducible, as `mvp-v0.1` Section 6 requires of every registered ordering.

**Length.** `k` = 10. A discovery result carries at most ten candidates. When an eleventh row is returned by a Section 4.4 template, the list is truncated to ten and `limitations` records the truncation (Section 7). `k` is fixed by this contract and not a caller argument: a caller-supplied `k` would let a caller change the meaning of the recall metrics in Section 4.11 after they were registered.

### 4.7 Auto-resolution, and the alias policy Charter Section 4.2 requires

[Project Charter](../PROJECT_CHARTER.md) Section 4.2 states that "until an alias policy is reviewed and recorded, an alias may contribute candidates but cannot by itself select one candidate". **This section is that policy**, and it is binding only when this contract reaches `Accepted` (Section 2).

Let `E(T)` be the set of approved entities that match the term `T` at **tier 1 or tier 2** within the resolved scope, of the requested kind, and under `parent_message_key` when supplied.

| `E(T)` | Outcome |
| --- | --- |
| exactly one entity | `resolved`: that one canonical entity reference, with its tier and matched text |
| more than one entity | `candidates`: the full ranked list, **no** resolution |
| empty | the registered retrieval method runs; a non-empty result is `candidates`, an empty one is `not_found` |

Four consequences, each of which is a Charter Section 9 Milestone 3 gate item discharged by construction:

1. **An unapproved alias never auto-resolves.** Only a registered approved alias reaches tier 2; every other term is at best tier 3, which is candidates-only. A term nobody approved cannot become a resolution however good its lexical match.
2. **Ambiguity never resolves silently.** Uniqueness is required over tiers 1 and 2 *combined*, so a term that is one entity's lookup key and another's approved alias produces two candidates rather than a silent preference for the key. Fixture `DX-004` is that case, and it is the reason Section 4.1 refuses to make `alias_text` unique.
3. **A resolution is inspectable.** `resolved` carries the tier and the matched text, so a reader can see that it came from a byte-exact match on an approved name and not from a similarity judgement.
4. **A resolution is not a fact.** It is one canonical entity reference. Facts still come only from a `mvp-v0.1` fixed-SQL route invoked with that reference.

**The alternative, recorded because the owner may prefer it.** The conservative reading of Charter Section 4.2 is that *no* alias may auto-resolve, so only tier 1 — the entity's own lookup key — would be eligible and every alias match would require an explicit selection. This contract does not adopt it, because Charter Section 9's gate item is worded "**unapproved** aliases do not auto-resolve to a single candidate", which distinguishes approved from unapproved, and because an approved alias with a recorded approval reference and a byte-exact unique match is exactly the evidence an approval is for. The cost of the adopted reading is that one wrong approval turns into one silent resolution; the cost of the alternative is that the approved-alias registry buys nothing a person would notice. Adopting either is the owner's, at contract review; changing it afterwards is a minor version under Section 10.

### 4.8 The verified selection path

A `candidates` outcome is completed by an explicit selection. This section fixes how the runtime knows a selection is real, because [#17](https://github.com/OKJ1105/evidence-first-rag/issues/17) rule 8 forbids any field that asserts provenance the runtime cannot verify, and a caller saying "the user picked this one" is exactly such a field.

**The candidate-set digest.** A discovery result that carries candidates also carries `candidate_set_id`: the SHA-256, lower-case hexadecimal, of a UTF-8 JSON object with keys sorted byte-wise and no insignificant whitespace, containing exactly the contract identifier and version, the `registry_digest`, the resolved scope's four dimensions, `entity_kind`, `parent_message_key` or null, the byte-exact `term`, the method identifier and version, and the ordered candidate list as serialized in the result. It is a **digest, not a token**: it holds no session state, no randomness, and no clock, and any process with the same registry and the same request recomputes it.

**The selection request.** One route, `entity_selection`. Its arguments are every argument of the discovery request that produced the list, plus `candidate_set_id` and `selected_rank`. The runtime then:

1. re-executes the discovery request deterministically, against the registry state it finds now;
2. recomputes `candidate_set_id` from the result;
3. refuses with `invalid_request` unless the recomputed digest equals the supplied one;
4. refuses with `invalid_request` unless `selected_rank` names a candidate in the recomputed list;
5. emits that candidate's canonical entity reference to the `mvp-v0.1` route the caller names, as an ordinary fully-scoped request.

Step 3 is the whole mechanism. The selection is trusted because the runtime **re-derived** the list the caller says it chose from, not because the caller asserted it. A registry that changed between the two requests changes the digest and the selection is refused — the fail-closed outcome, and the one a caller can act on by discovering again. Fixtures `DX-018` and `DX-019` register the two refusals.

**What a selection is not.** It resolves no scope dimension: every scope dimension was already resolved before discovery ran (Section 4.3). It creates no continuity: selecting an occurrence in one snapshot says nothing about an occurrence in another. And it is **never made by a model.** Charter Section 3.3 forbids an adapter to silently resolve an ambiguous entity, and choosing among candidates is that act; the selection comes from a person, or from an API caller relaying a person's choice, and Milestone 4 owns that surface.

**What it records.** `mvp-v0.1` Section 7 requires a `limitations` entry "when scope was resolved to one candidate out of several by an explicit user selection". This contract supplies the analogous entry for an entity selection, naming the candidate-set digest and the candidate count (Section 7). That is the entry [#17](https://github.com/OKJ1105/evidence-first-rag/issues/17) rule 8 says waits for a slice with a trusted selection path.

### 4.9 Retrieval methods and their registration

**`M-LEX-1`, version 1, registered by this contract.** The deterministic lexical baseline: `TPL_DISCOVERY_EXACT_V1` for tiers 1 and 2, then `TPL_DISCOVERY_LEXICAL_V1` for tiers 3 and 4 when `E(T)` is empty, ranked and truncated by Section 4.6. It runs entirely in the database as the read-only identity, uses no model, has no configuration, and sends nothing anywhere. It is the lexical baseline Charter Section 8 requires a candidate method to be compared against, and the initial implementation Charter Section 4.2 calls for — "exact identifiers, approved aliases, and lexical matching".

**Registering another method** — BM25, a vector variant, or anything else — is a minor version of this contract under Section 10, and the registration must state:

1. its identifier and version, both recorded in every result and every evaluation artifact;
2. its inputs, which may be the registry and the term and nothing else — no fact table, no evidence bundle;
3. its determinism: given the same `registry_digest` and the same request, the same ordered candidate list, byte for byte. A method that cannot promise this cannot be registered, because Section 4.8's selection path re-derives the list;
4. how its output maps into the Section 4.5 tier vocabulary. **No method may auto-resolve.** Auto-resolution is Section 4.7's tier-1-or-2 uniqueness rule and nothing else; an added method contributes candidates only, whatever it computes;
5. its comparison against `M-LEX-1` on the registered evaluation set, by the Section 4.11 definitions, judged against thresholds registered before the run (Section 8.3);
6. its operational cost, as Charter Section 8 requires: any new dependency, service, provisioning step, index, or egress.

**The boundary that is not this contract's to move.** A method that sends registry content, fixture content, an entity name, or any database row to an external service — an embedding API included — is outside [Project Charter](../PROJECT_CHARTER.md) Section 3.3, which permits an external model to receive "only the user request and the approved route, argument, and schema metadata required by the adapter contract". Such a method requires a **separately reviewed ADR** before it may be registered. This contract does not grant it, and a registration under point 1–6 above does not either. Charter Section 8 additionally admits vector search only on a material improvement on the difficult semantic cases within a pre-registered budget for false resolution, latency, and complexity; Section 8.3 is where such a budget would be registered.

### 4.10 The labeled discovery evaluation set

[Project Charter](../PROJECT_CHARTER.md) Section 8 requires an approved entity registry **and** a labeled evaluation set to exist before Entity Discovery is added, and lists what the set must include. This section fixes the classes, the authoring rules, and what an evaluation run records. It authors no case and registers no number; Section 8.3 is reserved for that, and Section 9 carries the row.

**Query classes.** Charter Section 8's eight bullets, one class each. Charter Section 9's gate requires each adopted method to meet its thresholds "for every governed query class", so the class is the unit a threshold is registered against.

| Class | Charter bullet | Each case registers | Registered outcome |
| --- | --- | --- | --- |
| `Q-EXACT` | exact identifier requests | a term equal to an approved entity's lookup key, byte for byte | `resolved`, with that canonical reference |
| `Q-ALIAS` | approved aliases and spelling variations | a term equal to a registered `approved_alias` or `spelling_variant`, byte for byte | `resolved`, with that canonical reference |
| `Q-SEMANTIC` | descriptive semantic requests | a term describing the entity without equalling any `match_text` | `candidates`, with the target's reference and the rank bound it must meet |
| `Q-SCOPE` | entity name present, source scope missing or partial | a term that would match, with at least one scope dimension absent | `ambiguous`, with the candidate scopes; **no discovery template executes** |
| `Q-COLLIDE` | the same name in more than one source snapshot | a fully scoped request for a key that exists in two snapshots | `resolved`, in the named snapshot only; the other snapshot's occurrence must be absent from the result |
| `Q-MULTI` | multiple plausible candidates | a term matching two or more approved entities in the resolved scope | `candidates`, with every expected reference; **never** `resolved` |
| `Q-NOMATCH` | no-match requests | a term matching nothing at any tier in a resolved, covered snapshot | `not_found` |
| `Q-OUT` | out-of-scope requests | a request discovery does not represent — an `entity_kind` outside the two values, or a scope naming an uncovered dimension | `unsupported` or `coverage_gap`, as the case registers |

**Authoring rules.** Each becomes an assertion in the slice that registers the set.

1. Every identifier is `SAMPLE_*` and is either loaded by the `mvp-v0.1` Section 4.11 fixture files or reserved there as absent. No case invents a name.
2. Every case registers its class, its exact request arguments, its expected outcome family, and — where the outcome names an entity — the complete canonical entity reference expected, including the parent Message for a signal.
3. A `Q-SEMANTIC` case registers the rank bound its target must meet, because "the target is somewhere in ten candidates" and "the target is first" are different claims and the metrics in Section 4.11 distinguish them.
4. **At least five cases in each of the eight classes.** Thresholds are per class (Charter Section 9), so a class is the denominator of its own fraction; below five, the only achievable values are so coarse that one case moves a rate by more than twenty points. This is a judgement about what a per-class threshold can mean, not a derivation.
5. Every case is authored **without running any retrieval method over it**, and without an entity's attributes: a case describes a request, never an expected fact.
6. No two case texts are equal after the Section 4.5 normalization.
7. All case texts are English, as `mvp-v0.1` Section 8.3 rule 7 fixes for the Milestone 2 set and for the same reason: a set in another language measures a different capability and is a different registration.
8. Adding, removing, or editing a case after registration is a patch version that re-registers `registered_at`. The denominators are part of the registration. A change to the registry files that changes any registered case's outcome does the same, and the `registry_digest` recorded with the registration is how that is detected rather than remembered.

**What a run records.** One artifact per run, per method: the method identifier and version, this contract's identifier and version, the `registry_digest` and `built_at` the run executed against, the run's start instant, every case with its request, its registered expectation and its observed result, and the Section 4.11 metrics per class and over the set. Every metric is computed deterministically from the recorded per-case results. **No language model judges any of it** — Charter Section 3.3 and [Contract Shape Framework](README.md) Section 5.7 both forbid it, and `mvp-v0.1` Section 4.9 says so of its own runner.

### 4.11 Metric definitions

The quantities [Project Charter](../PROJECT_CHARTER.md) Section 8 requires a candidate-method comparison to report, defined here so that a later change to how one is computed is visibly a change to the bar rather than an implementation detail. Each is computed per class and over the whole set. For a case whose registered outcome is `resolved`, the observed candidate list is the single resolved reference at rank 1.

- **`recall_at_k`**, for `k` in 1, 5, 10 — over the cases whose registration names a target reference (`Q-EXACT`, `Q-ALIAS`, `Q-SEMANTIC`, `Q-COLLIDE`, `Q-MULTI`): the fraction whose registered target appears at rank ≤ `k`. A `Q-MULTI` case counts only when **every** registered reference appears. `k` never exceeds the Section 4.6 list length.
- **`mrr`** — over the same cases: the mean of 1 divided by the rank of the registered target, and 0 when it is absent. For `Q-MULTI`, the rank of its worst-ranked registered reference.
- **`false_resolution`** — over every case in the class: the fraction that returned `resolved` with a reference other than the one registered, or returned `resolved` at all where the registered outcome is not `resolved`. This is the quantity Charter Section 3.3 is about: an answer a reader cannot distinguish from a correct one, because it is a true fact about the wrong entity.
- **`correct_abstention`** — over the cases whose registered outcome is not `resolved`: the fraction that did not return `resolved`. Charter Section 8's "abstention quality on ambiguous and no-match inputs".
- **`over_abstention`** — over the cases whose registered outcome is `resolved`: the fraction that returned anything else. Recorded alongside `correct_abstention` because a method that abstains on everything scores perfectly on that one, and this is the number that says so.
- **`task_completion`** — over the cases whose registration names a target and a `mvp-v0.1` route: the fraction where the resolved or selected reference, passed to that route, returns `success` carrying that reference. Charter Section 8's "end-to-end task completion after candidate selection". A case whose registered outcome is `candidates` completes through the Section 4.8 selection path, selecting the registered target.
- **`latency`** — the wall-clock duration of each discovery call, reported as median and 95th percentile per method. **Recorded, never returned:** a duration in a result payload would break the byte-identity Section 6 requires of two runs.
- **`operational_complexity`** — not a number. A recorded description of every dependency, service, provisioning step, index, and external egress the method adds, which the repository owner weighs at adoption. Charter Section 8 lists it beside the numbers; this contract does not pretend it is one.

`M-LEX-1` is measured by these same definitions over the same set and recorded alongside any method compared with it. It sets no bar; it is the baseline Charter Section 8 requires the comparison to have.

### 4.12 What discovery never does

Each line is an obligation, and Section 8 names the assertion that discharges it.

- **It returns no fact.** A discovery result carries canonical entity references and match evidence only, never an attribute of an entity. Authoritative facts come only from the `mvp-v0.1` registered fixed-SQL routes, which is Charter Section 9's Milestone 3 gate item "final facts still come only from the fixed-SQL runtime".
- **It is never a fallback.** No failed fact lookup falls back to discovery, and no discovery result is presented as the answer to a fact request. Charter Section 3.4: a negative case must not silently fall back to retrieval and present retrieved text as factual evidence.
- **It is never chained automatically.** A `needs_entity_discovery` outcome stays terminal inside the `mvp-v0.1` runtime path: that request opens no connection and returns that status, exactly as `mvp-v0.1` Sections 4.6 and 5 require. A discovery request is a **new** request from the caller. `mvp-v0.1` Section 9's row — "`needs_entity_discovery` stays terminal until then" — is satisfied by this reading rather than overridden, and the adapter's vocabulary is untouched (Section 3.3).
- **It writes nothing.** The runtime identity holds `SELECT` on the registry tables and no other privilege.
- **It creates no entity, no alias, and no continuity.** Every reference it returns already exists in the registry, and every alias was approved before the request. Name equality across snapshots remains a `signal_mapping` relation, never an inference (Charter Section 3.6).
- **It resolves no scope dimension.** Section 4.3.
- **No model ranks, selects, or judges.** Not the candidate order, not the selection, not a metric.

## 5. Outcome coverage

Every status family this contract can produce, and the condition that produces it.

| Status | Condition |
| --- | --- |
| `resolved` | Scope resolves to exactly one snapshot and exactly one approved entity matches the term at tier 1 or tier 2 (Section 4.7). One canonical entity reference, with its tier and matched text. |
| `candidates` | Scope resolves to exactly one snapshot and at least one approved entity matches at any tier, but Section 4.7's uniqueness condition does not hold. A ranked list of at most ten candidates; **no reference is resolved**, and explicit selection is required. |
| `not_found` | Scope resolves to exactly one snapshot that is within approved coverage, and no approved entity matches the term at any tier. |
| `coverage_gap` | The approved data scope does not contain, or cannot be established to contain, the coverage the request needs — a scope dimension no snapshot has. Returned instead of `not_found` whenever coverage cannot be established. |
| `ambiguous` | Source scope is missing or under-specified. Governed by `mvp-v0.1` Section 4.2 unchanged: the candidate scopes are listed and **no discovery template executes**. |
| `invalid_request` | A malformed or empty term, a term over the length limit, a parameter outside the route allowlist, `parent_message_key` with `entity_kind` = `message`, a contradictory scope, or a selection whose candidate-set digest does not re-derive or whose rank names no candidate (Section 4.8). |
| `unsupported` | The request is not representable by this contract at the producing layer — an `entity_kind` outside `message` and `signal`, or an operation discovery does not perform. The trace records the producing layer. |

**`success` is not in this table, and its absence is the point.** `success` in `mvp-v0.1` Section 5 means a registered template returned facts. Discovery returns no facts, so a discovery result can never carry that status, and no reader can mistake a candidate list for an answer. The `success` that ends a discovery flow is the `mvp-v0.1` result of the fact route the selected reference is passed to.

Every status carries an `evidence_bundle`, a `source_trace`, and a `limitations` list, including every negative outcome (Section 7). For `invalid_request`, `unsupported`, and the `ambiguous` case that is refused before dispatch, no discovery template executes and the evidence bundle records that no connection was opened for discovery.

## 6. Determinism

- Every registered template carries its ordering clause with explicit `NULLS LAST`; the runtime never applies caller-supplied ordering, and `k` is fixed by Section 4.6 rather than supplied by a caller.
- The candidate ordering in Section 4.6 is **total**: no two candidates share a canonical reference, so no tie can survive to the last key.
- Text comparison and ordering use the `C` collation of `mvp-v0.1` Section 6. Discovery normalization (Section 4.5) is ASCII and locale-free, and applies only to candidate generation.
- **No score.** A candidate carries a discrete tier, so ranking cannot drift with a floating-point detail of an implementation or a platform.
- Two discovery requests with the same arguments against the same `registry_digest` return byte-identical results, `candidate_set_id` included. `candidate_set_id` is a digest of the request and the result (Section 4.8) — it contains no clock, no counter, and no randomness.
- A latency measurement is recorded by the evaluation runner and never appears in a result payload, which is what keeps the previous rule true (Section 4.11).
- Repeatable provisioning from the same fixture files produces the same registry rows, the same `entity_match_term` derivation, and the same `registry_digest`. Surrogate keys may differ between runs and appear in no public payload, exactly as `mvp-v0.1` Section 6 permits.
- Determinism is a property of this whole layer, not only of the baseline: Section 4.9 point 3 refuses to register a method that cannot promise it, because Section 4.8's selection path re-derives the candidate list.

## 7. Evidence obligations

Every discovery and selection result, including every negative outcome, carries the three structures `mvp-v0.1` Section 7 requires. The keys below are that section's keys; the additions are named and each one exists because an obligation above needs to be checkable from the result.

**`evidence_bundle`**

- `contract_identifier` and `contract_version` of this contract, and of `mvp-v0.1`, whose registry safeguards the templates run under.
- `route`: `entity_discovery` or `entity_selection`.
- `template_name` and `template_version`, or an explicit empty value when no template executed.
- `bound_parameters`: exactly the parameters bound, with values — including `normalized_term` where the lexical template ran. An outcome that opens no connection binds nothing and reports an empty value, never the arguments it rejected. This is `mvp-v0.1` Section 7's rule, and its reason holds here unchanged: a rejected proposal must not be recorded as something the runtime acted on.
- `row_count`: the number of registry match rows the template returned, before truncation to `k`.
- `resolved_scope`: the single `(project_code, revision_label, network_name, snapshot_label)` used, or an explicit empty value.
- `collation` in effect.
- `read_only_safeguards`: the runtime role name, the read-only transaction flag, and whether a connection was opened.
- `registry_digest` and `registry_built_at` — **the addition that makes a discovery result reproducible.** A result without them names no registry state, and Section 4.8's re-derivation would have nothing to compare against.
- `method_identifier` and `method_version` — which retrieval method produced the list.
- `match_tier` and `matched_text` for a `resolved` outcome; per candidate for `candidates`.
- `candidate_set_id` and `candidate_count` for a `candidates` outcome; the `candidate_set_id` cited and the `selected_rank` for an `entity_selection` result.

**`source_trace`**

- The resolved scope of the snapshot every returned reference belongs to.
- For a signal reference, the parent Message occurrence, separately identified.
- **Alias provenance**, for every match at tier 2 and for every candidate whose `match_kind` is not `lookup_key`: the `approval_reference` of the alias, its `approved_at`, and the four scope dimensions of its asserting snapshot. This is the "approved alias provenance" [Project Charter](../PROJECT_CHARTER.md) Section 12 assigns to this contract, surfaced where a reader meets it rather than only in the table it was loaded from.
- The `approval_reference` of the approved entity itself, for a `resolved` outcome.
- The producing layer for an `unsupported` outcome.
- The fixture provenance that actually exists. A trace never cites a raw source-format artefact, because none exists in this repository ([ADR-0001](../adr/0001-postgresql-runtime-and-normalized-fixture-boundary.md)).

**`limitations`** — present on every result, empty list permitted. Required entries:

- when the candidate list was truncated at `k`, stating that further matches exist and were not returned;
- when the outcome is `candidates`, stating that **no reference was resolved** and that an explicit selection is required — so that a candidate list is never read as an answer;
- when the outcome is `not_found`, stating that no approved entity matched **and that absence from the approved registry is not absence from the data**. The registry is an allowlist (Section 4.2), and a result that let a reader infer the entity does not exist would be inferring coverage the runtime never established;
- when any participating snapshot has a non-null `superseded_by`, naming it — inherited from `mvp-v0.1` Section 7 and required of an alias asserted by a superseded snapshot;
- when a reference reached a fact route through the Section 4.8 selection path, naming the `candidate_set_id` and the candidate count it was selected from. This is the explicit-selection entry `mvp-v0.1` Section 7 requires, now backed by a path that verifies it;
- when the outcome is `coverage_gap`, stating what coverage could not be established.

## 8. Acceptance evidence

Each obligation is either an automated assertion over registered inputs or a recorded human decision with named evidence, as [Project Charter](../PROJECT_CHARTER.md) Section 9 requires.

| Obligation | Acceptance evidence |
| --- | --- |
| Section 4.1 registry schema and constraints | Automated. A data-level check asserts every constraint, including the exactly-one-occurrence-reference check, both partial unique constraints, the foreign keys into the `mvp-v0.1` tables, and the **absence** of a unique constraint on `alias_text` alone. |
| Section 4.2 integrity | Automated. The same check asserts the three derivation rules for `entity_match_term`, the same-snapshot rule for an alias's asserting snapshot, and the enumerated values of `entity_kind` and `alias_kind`. Each must be shown to fail against a database from which the rule has been removed. |
| Section 4.2 refresh and digest | Automated. Provisioning twice from the same fixture files produces the same `registry_digest`; provisioning from a registry file with an unresolvable natural key aborts with no partial load; the stored digest equals a recomputation from the loaded rows. |
| Section 4.3 request validation | Automated. Fixtures `DX-011` through `DX-014` below, each asserting that no discovery template executed. |
| Section 4.4 templates | Automated. Negative tests for an unregistered template, a write keyword at registration, an unknown parameter, and a missing required parameter, under `mvp-v0.1` Section 4.4's safeguards; template-level tests assert each registered `LIMIT`, each `NULLS LAST`, and that the registered result column list contains no attribute column. |
| Section 4.5 normalization and tiers | Automated. A unit-level table of terms and expected tiers, including the case-only difference that must reach tier 3 and never tier 1. |
| Section 4.6 candidate contract | Automated. `DX-016` for truncation at `k`; a test asserting one candidate per entity where several match texts match; a test asserting no attribute column appears in a candidate. |
| Section 4.7 auto-resolution | Automated. `DX-001` through `DX-007`. `DX-004` and `DX-005` are the two collisions that must **not** resolve, and either alone is satisfied by a rule this section rejects. |
| Section 4.7 alias policy | **Recorded human decision.** Whether an approved alias may auto-resolve is the Charter Section 4.2 question this section answers; the alternative is recorded beside the adopted rule, and the owner's contract review is what adopts one. |
| Section 4.8 selection path | Automated. `DX-017` for a verified selection reaching a fact route, `DX-018` and `DX-019` for the two refusals; a test asserting that a changed registry changes `candidate_set_id`. |
| Section 4.9 `M-LEX-1` | Automated. The method's results over the registered evaluation set, recorded in the run artifact with its identifier and version. |
| Section 4.9 registering another method | **Recorded human decision**, per registration, as a minor version of this contract. A method that would send registry content outside the process additionally requires a separately reviewed ADR. |
| Section 4.10 evaluation set | Automated once registered: each authoring rule becomes an assertion over the registered cases. The set itself is registered by Section 8.3, which is reserved. |
| Section 4.11 metrics | Automated. The runner computes every metric from the recorded per-case results, and no model participates. |
| Section 4.12 boundaries | Automated. One assertion per line: no attribute column in any discovery payload; no code path from a fact-route failure to discovery; a `needs_entity_discovery` result opens no connection and triggers no discovery; the runtime identity is refused `INSERT`, `UPDATE`, `DELETE`, and `CREATE TABLE` on the registry tables, from PostgreSQL privileges rather than an application guard. |
| Sections 5 and 7 | Automated. Every fixture in Section 8.1 asserts its status family and the presence of all three evidence structures with the required keys, including `registry_digest`. |
| Section 6 determinism | Automated. Two runs over the same registry and request compare byte-identical, `candidate_set_id` included; the read-only state digest of `mvp-v0.1` Section 4.10 is extended to the four registry tables and must be unchanged across a discovery run. |
| Section 3.3's grant extension | **Recorded human decision**, recorded in Section 9. |
| The adoption thresholds | **Recorded human decision**, at the Milestone 3 gate, after the Section 8.3 registration and the run it judges. |

### 8.1 Required fixture cases

Every fixture uses `SAMPLE_*` identifiers only. Every status family in Section 5 has at least one fixture. These are the registered inputs the implementation slices are accepted against; they are not the Section 4.10 evaluation set, which measures a method's behaviour over requests rather than a runtime's behaviour over cases.

| ID | Structural case | Expected status |
| --- | --- | --- |
| `DX-001` | Term equals an approved entity's `message_key` byte for byte, unique in the resolved scope | `resolved`, `match_tier` 1 |
| `DX-002` | Term equals an approved alias byte for byte, unique in the resolved scope | `resolved`, `match_tier` 2, alias provenance in the trace |
| `DX-003` | Term equals a registered spelling variant byte for byte | `resolved`, `match_tier` 2 |
| `DX-004` | Term is one entity's lookup key **and** another entity's approved alias in the same snapshot and kind | `candidates`, both entities listed, no resolution |
| `DX-005` | Term equals a `signal_key` that occurs under two parent Message occurrences in one snapshot, `parent_message_key` not supplied | `candidates`, both parents listed, no resolution |
| `DX-006` | Term equals a `message_key` present in two snapshots; the request is fully scoped to one | `resolved`, in the requested snapshot only |
| `DX-007` | Term differs from a lookup key only by case | `candidates` at `match_tier` 3, never `resolved` |
| `DX-008` | Descriptive term whose tokens are all contained in an entity's match tokens | `candidates` at `match_tier` 4, target present, ranked |
| `DX-009` | Term matching nothing at any tier, in a resolved and covered snapshot | `not_found`, with the allowlist limitation |
| `DX-010` | Scope names a `network_name` no snapshot has | `coverage_gap` |
| `DX-011` | `snapshot_label` omitted | `ambiguous` with candidate scopes; no discovery template executed |
| `DX-012` | Empty or whitespace-only term, and a term over the length limit | `invalid_request`, no connection opened |
| `DX-013` | `parent_message_key` supplied with `entity_kind` = `message` | `invalid_request` |
| `DX-014` | `entity_kind` outside `message` and `signal` | `unsupported`, producing layer recorded |
| `DX-015` | Occurrence present in the loaded data but absent from `approved_entity` | `not_found`, limitation stating that absence from the registry is not absence from the data |
| `DX-016` | More than `k` entities match at one tier | `candidates`, exactly ten, truncation recorded in `limitations` |
| `DX-017` | Selection citing a candidate set that re-derives, then the `mvp-v0.1` route | `success` from that route, with the selection entry in `limitations` |
| `DX-018` | Selection citing a `candidate_set_id` that does not re-derive | `invalid_request`, no fact template executed |
| `DX-019` | Selection whose `selected_rank` names no candidate in the re-derived list | `invalid_request`, no fact template executed |
| `DX-020` | Alias asserted by a snapshot whose `superseded_by` is non-null | The outcome the term earns, with the required `superseded_by` entry in `limitations` |

`DX-004` and `DX-005` are the two halves of Section 4.7's uniqueness rule — a collision between kinds of match text, and a collision between parents — and an implementation that passes one while failing the other has made something other than tier-1-and-2 uniqueness its rule. Read them together, as `mvp-v0.1` Section 8.1 says of `FX-105` and `FX-113`.

`DX-015` is the fixture that proves the registry is an allowlist rather than a mirror of the loaded data. Without it, an implementation that discovered straight from `message_occurrence` and `signal_occurrence` would pass every other case here.

`DX-020` deliberately does not fix its own status: whether the term earns `resolved` or `candidates` is decided by Section 4.7 as for any other term, and what the supersession changes is the `limitations` entry, not the outcome. A superseded snapshot still holds facts about itself; what is prohibited is presenting them as holding in a later snapshot.

### 8.2 Deferral of the acceptance evidence

Section 10 permits this contract to be accepted with its acceptance evidence explicitly deferred with a named owner. This section is that record.

The deferral is structural, not a concession. Every row of the Section 8 table is an assertion over an implementation that does not exist on the date this contract is proposed: the repository holds no registry table, no registry fixture, no discovery template, and no discovery runner. Requiring the evidence before acceptance would make acceptance unreachable, because [Contract Shape Framework](README.md) Section 2.1 forbids implementing against a contract that is not accepted. The order is contract first, then the evidence with the implementation the contract governs — the same order `mvp-v0.1` Section 8.2 records for itself.

**Named owner: the repository owner.** Nothing here is delegated to an AI writer or reviewer.

| Class | Discharged |
| --- | --- |
| Every row marked **Automated** | On the pull request that introduces the behaviour that row governs. Its assertions are a merge condition for that pull request. A pull request that implements a behaviour without them is incomplete, not deferred again. |
| Section 4.7's alias policy | At contract review, by the owner's record on this contract's own pull request. |
| Section 3.3's grant extension | At contract review, recorded on this contract's pull request or on the `mvp-v0.1` amendment it may lead to. |
| Section 4.9's per-method registration | At the registration of each later method, as a minor version of this contract. |
| The adoption thresholds | At the Milestone 3 gate, after Section 8.3 registers them and the run they judge has happened. |

This deferral does not weaken any obligation, and Section 10 forbids using it to. No implementation pull request may cite this section as a reason to omit the evidence its own slice owes.

### 8.3 Reserved: the evaluation set and the adoption thresholds

**Nothing is registered here yet, and that is deliberate.** [Project Charter](../PROJECT_CHARTER.md) Section 9 requires a numeric adoption threshold to be registered *before the run it judges*, and states that reporting a metric without a pre-registered pass condition does not satisfy a gate. It does not require registration before the contract is accepted, and `mvp-v0.1` Section 9 records why doing so would be guessing: at acceptance no case exists to be a denominator of, and no registry exists for a case to name.

A registration filling this section is a minor version under Section 10, taken as a recorded human decision, and must contain all of:

1. `registered_at`, the instant the repository owner recorded the decision, and the `contract_version` it landed at. A run whose start instant is not strictly later is not judged by these thresholds.
2. The `registry_digest` the set was authored against.
3. The evaluation set: every case, its class, its request arguments, its registered outcome, and its target reference or rank bound, satisfying every authoring rule in Section 4.10.
4. Per class, the numeric thresholds each adopted method must meet — at minimum for `recall_at_k`, `false_resolution`, and `correct_abstention`, which are the three Charter Section 9's gate names as "retrieval, false-resolution, and abstention thresholds".
5. For a vector variant, the pre-registered budget Charter Section 8 requires for false resolution, latency, and complexity, and what "material improvement on the difficult semantic cases" is measured as.
6. The reasoning behind each number, stated so that a reader can disagree with a step. A bar is a judgement unless it is derived, and a derivation should say what it derives from.

**What this section will not decide, whenever it is filled.** Adoption. The Section 8 row for the thresholds stays a recorded human decision taken after the run, in the Milestone 3 acceptance record under `docs/acceptance/`. A judgement that the thresholds were cleared is an input to that decision, not a substitute for it.

## 9. Deferred decisions

| Decision | Owner |
| --- | --- |
| The evaluation set's cases and `N`, and the per-class adoption thresholds | This contract, Section 8.3, as a later minor version registered before the run it judges. Recorded human decision. |
| Whether an approved alias may auto-resolve (Section 4.7), against the conservative alternative recorded there | The repository owner, at contract review. Changing it afterwards is a minor version. |
| Whether `mvp-v0.1` Section 4.3's privilege enumeration is patched to name this contract's registry tables (Section 3.3) | The repository owner, under `mvp-v0.1` Section 10. Implementation of this contract does not depend on the answer. |
| BM25 as a registered method | A later minor version of this contract, under Section 4.9. |
| Vector or embedding-based candidate retrieval | A later minor version of this contract **and** a separately reviewed ADR, if any registry or database content would leave the process ([Project Charter](../PROJECT_CHARTER.md) Section 3.3). Charter Section 12's "whether vector search materially outperforms lexical and BM25 baselines" is answered by the comparison, not by a contract. |
| Any scope-selection policy that resolves a scope dimension automatically | `mvp-v0.1` Section 9's row, unchanged. Not this contract's, and not prejudiced by it. |
| Which Section governs a request whose scope is incomplete and whose entity reference cannot be formed | [#43](https://github.com/OKJ1105/evidence-first-rag/issues/43), against `mvp-v0.1`. Section 4.3 requires a complete scope and neither answers nor forecloses it. |
| The API and rendering surface for discovery and selection, and any export of a candidate list | Milestone 4 contracts. This contract fixes routes on the existing runtime, not an interface. |
| Alias approval outside this repository | Out of scope. `approval_reference` is an opaque citation; this contract fixes that one is required, not how it is obtained. |

No row above is open in the sense that this contract needs it to be implementable. Sections 4.1 through 4.12 are complete as they stand; every row either registers numbers that Charter Section 9 requires to come later, or belongs to another document.

## 10. Change control

- This contract is `Proposed`. Under [Contract Shape Framework](README.md) Section 7 it is amended by an ordinary contract-only pull request while it stays in that state.
- It may not move to `Accepted` until the repository owner records the review required by Framework Section 6 step 4, **and** the Section 8 acceptance evidence is either satisfied or explicitly deferred with a named owner. The second is discharged in Section 8.2; the first is the review this contract's own pull request asks for.
- On acceptance the status line moves to `Accepted <date>`, citing that recorded review, and this contract becomes binding on implementation. Framework Section 2.1: no milestone gate is involved.
- After acceptance, a change that does not weaken a Charter or ADR invariant produces a new version with a recorded human decision. Adding or removing a route, template, retrieval method, match tier, status condition, or evidence field is a minor version and requires a fresh independent design review. Filling Section 8.3 is a minor version. Adding a fixture case that exercises an existing obligation is a patch version.
- **Removing or weakening an obligation is not permitted at this layer.** A change that would weaken a Charter or ADR invariant requires an architecture decision recorded in an ADR, a Charter update where the change materially changes the Charter, and a recorded human decision.
- Two changes are named here because they are the ones an implementer will reach for: sending any registry or database content to an external service requires a separately reviewed ADR under [Project Charter](../PROJECT_CHARTER.md) Section 3.3 (Section 4.9), and permitting a method other than Section 4.7's tier-1-and-2 rule to auto-resolve would weaken the Charter Section 9 gate item on unapproved aliases and is therefore not a contract-level change at all.
- **This contract amends nothing in `mvp-v0.1`.** Where the two meet, `mvp-v0.1` governs the fact path and this contract governs discovery. A change here that would require a change there is an `mvp-v0.1` amendment under its Section 10, and is the repository owner's to record.
- This contract's acceptance does not depend on a separate recorded acceptance of [ADR-0002](../adr/0002-scoped-canonical-entity-identity.md). Its citations of that ADR are rationale; the operative identity and scope invariants this contract preserves are carried by [Project Charter](../PROJECT_CHARTER.md) Section 3.6 itself, and by `mvp-v0.1` Section 4.2, which is `Accepted`.
- A superseded version is retained with a `Superseded by` status rather than deleted, so that a past acceptance record stays interpretable.
