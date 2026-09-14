# Milestone 3 Entity Discovery Contract v0.1

## 1. Identifier and version

**Identifier:** `entity-discovery-v0.1`

**Version:** `0.3.1` — the identifier names the document; the version tracks its obligations. `0.1.0` proposed the contract. `0.2.0` fixes what a re-read of the merged `0.1.0` text found under-specified or untrue under its own rules: the exact inputs of both digests (Sections 4.2 and 4.8), the comparison rule behind the determinism claim (Section 6), which registered method serves a request (Section 4.9), the shape of a dispatched selection's result and the standing of a `resolved` outcome (Sections 4.8 and 7), a byte-defined term limit (Section 4.3), a load rule for an alias that normalizes to nothing (Section 4.2), the intent of `false_resolution` (Section 4.11), the canonical JSON both digests are computed over (Section 4.2), the refusal of a selection whose re-run yields no candidate list (Section 4.8), the evaluation runner's standing outside the one-adopted-method rule (Section 4.9), the three places this contract extends `mvp-v0.1` and the union registry that route-name validation runs against (Sections 3.3 and 5), the evaluation runner's matching exception in the selection path, without which no method under comparison could be scored on a `candidates` case (Section 4.8), the fences that exception does not move (Section 4.9), and the step-2 re-run's own execution evidence on a dispatched selection, without which the one path that executes two templates would evidence only one (Sections 4.8 and 7). It adds no route, template, tier, status, or caller-visible capability, and weakens nothing. It takes a minor version because Sections 4, 6, and 7 change, on the precedent of `mvp-v0.1` moving `0.1.0` to `0.2.0` while still `Proposed`. `0.2.1` adds five `approved_entity` rows and one `approved_alias` row to the Section 4.2 registry fixtures, so that a set satisfying Section 4.10's authoring rules can be drawn from them: three of the entities approve the occurrences `mvp-v0.1` `0.6.1` adds, and two approve existing `SNAP_REVISED` occurrences, which makes their keys present in two snapshots. It registers no case and no number — Section 8.3 stays reserved — and every Section 8.1 case is unchanged, so it is a patch version under Section 10. `0.3.0` fills Section 8.3: forty evaluation cases, five in each of the eight Section 4.10 classes, and the per-class adoption thresholds, on the repository owner's recorded decision. It is a minor version because Section 1 names filling Section 8.3 one, and it changes no obligation in Sections 4, 5, 6 or 7 — no route, template, retrieval method, match tier, status condition, or evidence field. Charter Section 9 requires the registration to precede the run it judges, and no run over the set had happened when it landed. `0.3.1` corrects three things in that registration before any run is recorded against it, and re-registers `registered_at` under Section 4.10 rule 8: a `Q-SEMANTIC` case's registered rank bound is now a pass condition in its own right rather than only an input to the class bar, which is the reading rule 3 supports and which the owner recorded; a sentence that counted ten refusals as deciding before any template runs now says *discovery* template and names the three cases that open no connection; and the section cites the pull request the owner decided on rather than an Issue body, which Section 2 says is not the operative record. No case, threshold, bound or digest changes.

This contract covers the Entity Discovery half of the Milestone 3 deliverables in [Project Charter](../PROJECT_CHARTER.md) Section 9, and the evaluation family that judges it. In [Contract Shape Framework](README.md) Section 5 terms it combines the data, route, result, evidence, query-template-registry, runtime, and evaluation families for one layer, as [MVP Runtime Contract v0.1](mvp-v0.1.md) does for its own. Framework Section 5 assigns responsibilities per family; it does not require one document per family.

It is a **separate document from `mvp-v0.1`, not an amendment to it.** `mvp-v0.1` is `Accepted`, its Section 9 names "Milestone 3 contract" as the owner of the deferred Entity Discovery row, and its Section 10 makes any change to it a recorded human decision. Nothing here changes a word of it. Section 3.3 below lists what this contract inherits from it, and the three places where the two meet in a way the repository owner should confirm.

The version changes when any observable obligation in Section 4, 5, 6, or 7 changes. Adding a fixture case that exercises an existing obligation is a patch change. Adding or removing a route, template, retrieval method, match tier, status condition, or evidence field is a minor change. Registering the evaluation set and the adoption thresholds in Section 8.3 is a minor change; `0.3.0` is where that happened, and a later change to a registered case or number is the Section 4.10 rule 8 patch version. Removing or weakening an obligation is not permitted at the contract layer; see Section 10. `0.2.0` is the version at which this contract was accepted. Moving the Section 2 status line is **not** a version change: Section 4.7's rule is already written, and Section 2 already fixed that it becomes binding when this contract is accepted. Acceptance changes what the document binds, not what it obliges.

## 2. Status

**Status:** `Accepted 2026-09-11`

This contract is binding on implementation from that date under [Contract Shape Framework](README.md) Section 2.1. The repository owner recorded the required human review of this contract and its acceptance evidence on the pull request that set this line, and recorded merge approval by merging it. [#138](https://github.com/OKJ1105/evidence-first-rag/issues/138) is the task record that carries the decision and its reasoning; the operative record is the owner's on that pull request, because an Issue body written by a writer session is not one. Milestone 3 code, schema, and fixtures may be written against this document from that date; before it, Section 2 forbade them.

Section 10 sets two preconditions for acceptance. Both are discharged in this document rather than only in pull request comments: the Section 4.7 alias policy [Project Charter](../PROJECT_CHARTER.md) Section 4.2 requires is adopted and recorded in Section 4.7, and the Section 8 acceptance evidence is explicitly deferred with a named owner in Section 8.2.

**How this document reached here.** `0.1.0` was merged to `main` as `Proposed` on 2026-09-08 by [#79](https://github.com/OKJ1105/evidence-first-rag/pull/79), after two loop reviews. `0.2.0` closed what a re-read and three further loop rounds found, and merged as `Proposed` as well. This line moved only after that, on its own pull request, because acceptance is a separate decision from any amendment that precedes it.

An accepted contract may still be amended. Section 10 governs how, and no amendment may weaken an obligation.

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

- **A pre-registered budget for a vector variant.** Charter Section 8 admits vector search only on a material improvement on the difficult semantic cases within such a budget, and Section 8.3 registers none: it registers what a difficult semantic case *is*, and that the set holds none, so that a later registration cannot choose the definition after the fact. The budget itself arrives with the variant, as a version of Section 8.3. **The evaluation cases and the numeric adoption thresholds are no longer here:** Section 8.3 registered them at `0.3.0`, and the Section 9 row is struck through as decided. Charter Section 9 requires a threshold to be registered before the run it judges, not before the contract is accepted, which is why they arrived in a later version rather than at acceptance; a later change to any of them is a Section 4.10 rule 8 patch version that re-registers `registered_at` before the run it judges.
- **BM25, vector search, or any other retrieval method beyond `M-LEX-1`.** Section 4.9 fixes how one is registered; registering one is a later minor version.
- **Any scope-selection policy that resolves a scope dimension automatically.** That row belongs to `mvp-v0.1` Section 9 and stays there. This contract requires a resolved scope and resolves no scope dimension.
- **Which Section governs a request whose scope is incomplete *and* whose entity reference cannot be formed.** That is the open `mvp-v0.1` question in [#43](https://github.com/OKJ1105/evidence-first-rag/issues/43). Section 4.3 requires a complete scope as a precondition, which neither answers that question nor prejudices it.
- **Any API, renderer, or export surface.** Milestone 4 owns those. Discovery here is a route on the existing runtime, not an HTTP interface.
- **Ingestion of any raw source format.** The registry is loaded from the version-controlled fixtures, as `mvp-v0.1` Section 4.11 loads its own.
- **The alias approval process outside this repository.** `approval_reference` is an opaque citation of a recorded decision; this contract fixes that one is required and what it must accompany, not how it is obtained.

Section 9 records each of these with its owning slice.

### 3.3 What this contract inherits from `mvp-v0.1`, and the three places it extends it

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

**Three extensions, each recorded rather than assumed.** This contract is additive, but it meets `mvp-v0.1` in three places. None of them edits that contract's text, none removes, renames, or reinterprets anything it defines, and none weakens an obligation. Each is recorded here, and Section 9 carries the repository owner's decision on whether `mvp-v0.1` is patched to name it — a change to an `Accepted` contract, which its Section 10 assigns to the owner. **Implementation depends on none of the three answers**: what this contract fixes is the same either way.

**1. The route registry.** This contract registers two routes, `entity_discovery` and `entity_selection`. `mvp-v0.1` Section 4.5's table holds three, and does not contain them. **Route-name validation therefore runs against the union of the registered routes** — those three plus these two — and never against either contract's list alone. A name outside the union is refused as an unregistered route, with the producing layer recorded (Section 5). This has to be stated rather than inferred: an implementer validating every route name against Section 4.5's table alone would refuse `entity_discovery` itself, and no fixture in Section 8.1 could pass.

**2. The runtime identity's privileges.** `mvp-v0.1` Section 4.3 enumerates them as `SELECT` only *on the four tables* of its Section 4.1. The registry tables in Section 4.1 of this contract are additional tables the same identity must read. This contract grants that identity `SELECT` on its own tables and no other privilege on them; no write, DDL, or escalation is added anywhere, the read-only invariance obligations of `mvp-v0.1` Section 4.10 are extended to the new tables by Section 8 below, and the four `mvp-v0.1` tables are unaffected.

**Until and unless `mvp-v0.1` is patched, its Section 4.3 enumeration is read as enumerating that contract's own tables, not as exhausting the role's grants.** This has to be said, because from the moment this contract is `Accepted` both documents bind at once: a runtime role holding `SELECT` on `mvp-v0.1` Section 4.1's four tables *and* on this contract's four registry tables, and no other privilege on either set, **conforms to both**. Without this sentence an implementer of the first Milestone 3 provisioning slice would read `mvp-v0.1` Section 4.3's "only on the four tables" as a ceiling and be unable to grant the registry reads this contract requires, so two `Accepted` contracts would state incompatible privilege sets with nothing reconciling them. The reading adds no privilege that this contract does not already grant, weakens nothing in `mvp-v0.1`, and is exactly the kind of statement Section 3.3 exists to make: this contract extends that one rather than amending it. Whether the enumeration is patched to name these tables outright remains the owner's, in Section 9.

**3. One `evidence_bundle` key on a dispatched selection.** Section 4.8 requires a dispatched selection to return the `mvp-v0.1` result of its `target_route` with one `selection` record added to the `evidence_bundle`. `mvp-v0.1` Section 7 enumerates that bundle's keys and does not include it. The record adds one key and removes, renames, or reinterprets none, so every obligation of that section still holds of the result; what changes is that a fact result reached through a selection carries one key more than the same result reached with a canonical reference supplied directly.

**What this contract deliberately does not touch in `mvp-v0.1`.** The adapter's fixed instructions and vocabulary payload are unchanged, so the Section 4.6 digests are unchanged and the Milestone 2 comparison is not reopened. The adapter's route vocabulary stays the three routes of `mvp-v0.1` Section 4.5 plus the literal `unsupported`. **That vocabulary and the route registry above are different things**, and only the registry gains two rows: the routes this contract registers are not adapter-selectable, and Section 4.12 forbids the automatic chaining that would make them so. Keeping the vocabulary fixed is what leaves the Section 4.6 digests unchanged.

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
5. An `entity_match_term` row whose `match_text` normalizes to no token under Section 4.5 is refused at load, whatever its `match_kind`. Section 4.1 says `match_tokens` is never empty; this is the rule that makes that true rather than assumed, and it is a rule because a guard that lives only in a column note cannot be seen to fail. In practice only an alias can trip it: a lookup key under `mvp-v0.1` Section 4.11's `SAMPLE_*` convention always carries a letter, though the character set alone (`_ . -` are all permitted) would not guarantee that, which is why the rule is stated over the derived surface and not over aliases.

**Refresh.** The registry is loaded in the same provisioning phase as the `mvp-v0.1` Section 4.11 fixtures, by the provisioning identity, from version-controlled JSON Lines files under `fixtures/`, before the runtime identity ever connects. There is no incremental update path and no runtime write path: the runtime identity holds `SELECT` and nothing else on all four tables of Section 4.1. **A refresh is a re-provision.** A partial load aborts, as `mvp-v0.1` Section 4.11 requires of its own files.

**The registry digest.** `registry_digest` is the SHA-256, lower-case hexadecimal, of the concatenation of one line per registry row, each line a UTF-8 JSON object with keys sorted byte-wise and no insignificant whitespace, terminated by `\n`, in this order: every `approved_entity` row, then every `approved_alias` row, then every `entity_match_term` row; within each group, sorted byte-wise by the serialized line. A row is serialized by **natural keys only**, never by a surrogate value, which `mvp-v0.1` Section 6 permits to differ between provisioning runs. The keys per table are fixed here so that two implementations compute one digest:

| Table | Keys in its line |
| --- | --- |
| `approved_entity` | `entity_kind`; `project_code`, `revision_label`, `network_name`, `snapshot_label`, `message_key`; `signal_key` (`null` for a message); `approval_reference`; `approved_at` |
| `approved_alias` | the seven entity keys above, identifying the entity; `alias_text`; `alias_kind`; `asserting_project_code`, `asserting_revision_label`, `asserting_network_name`, `asserting_snapshot_label`; `approval_reference`; `approved_at` |
| `entity_match_term` | the seven entity keys above; `match_kind`; `match_text`; `match_tokens` as a JSON array of strings; `alias_text` (`null` for a `lookup_key` row), which with the entity keys names the alias row without its surrogate |

The three tables are serialized after the load completes, from the loaded rows and not from the fixture files, so the digest covers what the runtime will read.

**Canonical JSON.** Every digest in this contract — this one and the candidate-set digest of Section 4.8 — is computed over JSON produced by these rules and no others, so that two independent implementations produce one byte sequence:

- UTF-8 output. A character that JSON does not require escaping is written as itself, never as a `\u` escape; a non-ASCII byte in an `alias_text`, a `match_text`, an `approval_reference`, or a `term` therefore reaches the digest as the bytes the runtime holds.
- The escape set is exactly RFC 8259's minimum: `"` as `\"`, `\` as `\\`, and the C0 control characters U+0000–U+001F as `\u` followed by four lower-case hexadecimal digits. Nothing else is escaped; `/` is written as `/`.
- Object keys are sorted by their UTF-8 bytes. No whitespace appears outside string values.
- An absent or inapplicable value is `null`. An integer — `rank`, `match_tier` — is written as its shortest decimal form with no sign, fraction, or exponent. No other number appears in any digest input.
- A timestamp is a string in RFC 3339 form, UTC, second precision, trailing `Z`. A JSON array keeps its order.

These rules are stated inline rather than by reference so that the digest does not depend on any library's defaults; a JSON writer that ASCII-escapes non-ASCII characters, or that emits a space after a colon, produces a different digest and is non-conforming.

The digest is what makes a discovery result reproducible and a selection verifiable. It appears in every discovery `evidence_bundle` (Section 7), in every candidate-set digest (Section 4.8), and in every evaluation artifact (Section 4.10). A registry change changes it, which is the intended signal: a candidate set computed against one registry state cannot be selected from against another.

### 4.3 The discovery request and its preconditions

One route, `entity_discovery`. Its arguments are named, allowlisted, and validated before any database access, as `mvp-v0.1` Section 4.5 requires of every route.

| Argument | Required | Notes |
| --- | --- | --- |
| `project_code`, `revision_label`, `network_name`, `snapshot_label` | all four required | The resolved source scope. |
| `entity_kind` | required | `message` or `signal`. Any other value is `unsupported` (Section 5, fixture `DX-014`). |
| `parent_message_key` | optional, and permitted only when `entity_kind` is `signal` | Narrows the search to one parent Message occurrence. Supplying it with `entity_kind` = `message` is `invalid_request`. |
| `term` | required | The user's free text naming or describing the entity. At most 200 bytes of UTF-8, and at least one token after the Section 4.5 normalization; otherwise `invalid_request`. The limit is in bytes because everything else this contract compares — normalization, collation, the digests — is byte-defined, and a character count would make the same term valid or invalid depending on an implementation's string type. |

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

**The row limit is 11 because `k` is 10.** An eleventh row means the candidate list was truncated, which Section 7 requires `limitations` to record. This is the **truncation** pattern `mvp-v0.1` Section 4.4 uses for `TPL_SNAPSHOT_CANDIDATES_V1` — "candidates beyond the limit are truncated; `limitations` records the truncation" — applied to a list that can legitimately exceed `k`. It is deliberately **not** the facts-template pattern in that same section, where a limit of 2 makes a second row a violation of the database's own invariants and a `data` failure. A discovery term matching many entities is ordinary and safe; a message key matching two rows is not.

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

**The alternative, retained because it was declined rather than deleted.** The conservative reading of Charter Section 4.2 is that *no* alias may auto-resolve, so only tier 1 — the entity's own lookup key — would be eligible and every alias match would require an explicit selection. This contract does not adopt it, because Charter Section 9's gate item is worded "**unapproved** aliases do not auto-resolve to a single candidate", which distinguishes approved from unapproved, and because an approved alias with a recorded approval reference and a byte-exact unique match is exactly the evidence an approval is for. The cost of the adopted reading is that one wrong approval turns into one silent resolution, bounded by the four consequences above; the cost of the alternative is that the approved-alias registry buys nothing a person would notice. **The adopted reading is the one above**, recorded by the repository owner at contract review on 2026-09-11, on the pull request that moved the Section 2 status line ([#138](https://github.com/OKJ1105/evidence-first-rag/issues/138)). The alternative is retained here rather than deleted, so that what was chosen and what was declined both remain legible. Changing the adopted reading afterwards is a minor version under Section 10.

### 4.8 The verified selection path

A `candidates` outcome is completed by an explicit selection. This section fixes how the runtime knows a selection is real, because [#17](https://github.com/OKJ1105/evidence-first-rag/issues/17) rule 8 forbids any field that asserts provenance the runtime cannot verify, and a caller saying "the user picked this one" is exactly such a field.

**The candidate-set digest.** A discovery result that carries candidates also carries `candidate_set_id`: the SHA-256, lower-case hexadecimal, of a UTF-8 JSON object with keys sorted byte-wise and no insignificant whitespace, containing exactly these keys and nothing else: `contract_identifier`, `contract_version`, `registry_digest`, `project_code`, `revision_label`, `network_name`, `snapshot_label`, `entity_kind`, `parent_message_key` (`null` when not supplied), `term` byte-exact, `method_identifier`, `method_version`, and `candidates` — a JSON array in rank order in which each element is an object with exactly the Section 4.6 fields: `rank`, `entity_kind`, `project_code`, `revision_label`, `network_name`, `snapshot_label`, `message_key`, `signal_key` (`null` for a message), `match_tier`, `matched_text`, `match_kind`. The alias provenance a candidate carries is not in the digest input: it is derivable from the registry the digest already names, and repeating it would make the digest depend on how provenance is rendered. The object is serialized under Section 4.2's canonical JSON rules. It is a **digest, not a token**: it holds no session state, no randomness, and no clock, and any process with the same registry and the same request recomputes it.

**A `resolved` outcome carries no `candidate_set_id` and needs no selection.** Its one reference is used directly, as an ordinary fully-scoped argument to a `mvp-v0.1` route. A selection request whose re-run produces anything other than a `candidates` outcome — `resolved` because the registry changed, `not_found` because the entity was removed, `coverage_gap` because the snapshot is gone — has no list to match against and is refused at step 4 below with `invalid_request`, and the `limitations` entry names what the re-run produced (Section 7). It is refused rather than answered with the re-run's own status because the caller asked for a selection from a list, and the list no longer exists; the caller learns that and discovers again. Fixture `DX-023` registers the case.

**The selection request.** One route, `entity_selection`. Its arguments are named and allowlisted like every other route's:

| Argument | Required | Notes |
| --- | --- | --- |
| every argument of the discovery request that produced the list | all | The four scope dimensions, `entity_kind`, `parent_message_key` where it was supplied, and the byte-exact `term`. The selection re-runs that request; it does not re-describe it. |
| `candidate_set_id` | required | The digest the discovery result carried. |
| `selected_rank` | required | The 1-based `rank` of the chosen candidate. |
| `target_route` | required | The `mvp-v0.1` Section 4.5 route the selected reference is dispatched to. Allowed values are exactly `message_facts`, `signal_facts`, and `signal_mapping`. |
| `mapping_key` | optional, and permitted only when `target_route` is `signal_mapping` | Passed through to `TPL_SIGNAL_MAPPING_V1`, which `mvp-v0.1` Section 4.5 declares it optional for. Supplying it with any other `target_route` is `invalid_request`. |

`target_route` is required rather than derived, because it cannot be derived: a signal candidate is valid input to **two** `mvp-v0.1` routes, `signal_facts` and `signal_mapping`, which answer different questions and take different argument shapes. Deriving one from `entity_kind` would pick for the caller, and the pick would be silent.

| Resolved `entity_kind` | Permitted `target_route` |
| --- | --- |
| `message` | `message_facts` |
| `signal` | `signal_facts`, `signal_mapping` — the selected signal is the mapping's source endpoint |

The runtime then:

1. refuses with `invalid_request` unless `target_route` is one of the three names above, and unless `mapping_key`, when present, accompanies `target_route` = `signal_mapping`;
2. re-executes the discovery request deterministically, against the registry state it finds now;
3. recomputes `candidate_set_id` from the result;
4. refuses with `invalid_request` unless the recomputed digest equals the supplied one;
5. refuses with `invalid_request` unless `selected_rank` names a candidate in the recomputed list;
6. refuses with `invalid_request` unless the **resolved candidate's** `entity_kind` permits `target_route`, by the table above;
7. emits that candidate's canonical entity reference — and `mapping_key` when supplied — to `target_route`, as an ordinary fully-scoped `mvp-v0.1` request, which then runs entirely under that contract.

Steps 1 and 6 are both needed and are not the same check: step 1 validates an argument, and step 6 validates it against a candidate that is not known until step 5. No fact template executes if any of them refuses.

**What a selection returns.** A selection refused at step 1, 4, 5, or 6 returns this contract's `invalid_request`, with `route` = `entity_selection` and the Section 7 structures. A selection that reaches step 7 returns **the `mvp-v0.1` result of `target_route`**, exactly as that contract defines it — its `route`, its status, every `evidence_bundle` key and `source_trace` entry that contract requires — **plus** the following, which are this contract's and are the whole of what it adds:

- in the `evidence_bundle`, one `selection` record, and inside it exactly: this contract's `contract_identifier` and `contract_version`; `registry_digest` and `registry_built_at`; `method_identifier` and `method_version`; `candidate_set_id`, `selected_rank`, `candidate_count`; `target_route`; and the step-2 re-run's own execution evidence — `discovery_template_name` and `discovery_template_version` (an explicit empty value when no discovery template executed), `discovery_bound_parameters` including `normalized_term` where the lexical template ran, and `discovery_row_count` before truncation to `k`. This contract's identity lives inside the record rather than beside `mvp-v0.1`'s at the top level, because the top-level `contract_identifier` is `mvp-v0.1`'s and a bundle cannot carry two values under one key; the re-run's execution evidence lives there for the same reason — two templates execute on this path and `template_name` is one key;
- in the `source_trace`, the selected candidate's alias provenance as Section 7 defines it — `approval_reference`, `approved_at`, and the asserting snapshot's four scope dimensions — whenever its `match_kind` is not `lookup_key`, and the approved entity's own `approval_reference` in every case;
- in `limitations`, the Section 7 entry for a selected reference.

Nothing else is added, and nothing of `mvp-v0.1`'s is removed or renamed. **This list is the authoritative key set for a dispatched selection**; Section 7 cites it rather than restating it, so that the Section 8 row for Sections 5 and 7 has one reading to assert against. That is why fixture `DX-017` expects `success`: the status is the fact route's, not a status of this contract, and Section 5 lists no `success` for that reason. Step 2's re-run uses the method the runtime currently has adopted under Section 4.9; a change of adopted method changes `method_identifier` or `method_version` in the digest input and so refuses every earlier candidate set, which is the intended outcome rather than a nuisance.

**Two templates execute on this path, and both are evidenced.** A dispatched selection runs `TPL_DISCOVERY_EXACT_V1` — and `TPL_DISCOVERY_LEXICAL_V1` where `E(T)` was empty — at step 2, and the `target_route`'s fact template at step 7. The top-level `template_name`, `template_version`, `bound_parameters` and `row_count` of the returned result are the **fact route's alone**, exactly as `mvp-v0.1` Section 7 defines them for that route; the discovery re-run's are the four `discovery_*` keys of the `selection` record above. `mvp-v0.1` Section 7's "exactly the parameters bound" is therefore read **per template** on this one path rather than per request, and neither set is a union of the other: an auditor reads the fact template's execution at the top level and the discovery execution beside it, and every template that ran is named. Without this, a selection that reached step 7 would be the one outcome in this contract that records less than a selection refused at step 4, which still reports the re-run under Section 7 — and less than `0.1.0`, whose Section 7 required these keys of every discovery and selection result. This is not a fourth extension of `mvp-v0.1`: the keys are inside the `selection` record, which Section 3.3 extension 3 already records as the one `evidence_bundle` key a dispatched selection adds.

**The Section 4.10 evaluation runner is the one exception to that sentence.** When the runner executes a method that is not the adopted one — which Section 4.9 permits, and its point 5 requires before any adoption — step 2's re-run uses **that same method** for the duration of the run, and the artifact records which method both halves used. Without the exception the digest would carry the challenger on the way out and the adopted method on the way back, step 4 would refuse, and **every `candidates`-registered case would score zero on `task_completion` (Section 4.11) for every method under comparison while the adopted method scored normally** — a number that reads as a verdict on the challenger when it is an artefact of the re-run, on exactly the class Charter Section 8's end-to-end axis exists to measure. A candidate set produced under this exception is never citable by a caller's selection; the runner's output does not leave the artifact.

`target_route` is **not** part of the `candidate_set_id` digest. The digest is over the discovery request and what discovery produced, and discovery does not know what the caller will ask next; folding the target route into it would make a list undiscoverable by the process that has to re-derive it.

Step 4 is the whole trust mechanism. The selection is trusted because the runtime **re-derived** the list the caller says it chose from, not because the caller asserted it. A registry that changed between the two requests changes the digest and the selection is refused — the fail-closed outcome, and the one a caller can act on by discovering again. Fixtures `DX-018`, `DX-019`, and `DX-021` through `DX-023` register the five refusals. `DX-020` sits inside that range but is not one of them: Section 8.1 registers it as a `limitations` case on the discovery path, and it takes whatever outcome its term earns.

**What a selection is not.** It resolves no scope dimension: every scope dimension was already resolved before discovery ran (Section 4.3). It creates no continuity: selecting an occurrence in one snapshot says nothing about an occurrence in another. And it is **never made by a model.** Charter Section 3.3 forbids an adapter to silently resolve an ambiguous entity, and choosing among candidates is that act; the selection comes from a person, or from an API caller relaying a person's choice, and Milestone 4 owns that surface.

**What it records.** `mvp-v0.1` Section 7 requires a `limitations` entry "when scope was resolved to one candidate out of several by an explicit user selection". This contract supplies the analogous entry for an entity selection, naming the candidate-set digest and the candidate count (Section 7). That is the entry [#17](https://github.com/OKJ1105/evidence-first-rag/issues/17) rule 8 says waits for a slice with a trusted selection path.

### 4.9 Retrieval methods and their registration

**`M-LEX-1`, version 1, registered by this contract.** The deterministic lexical baseline: `TPL_DISCOVERY_EXACT_V1` for tiers 1 and 2, then `TPL_DISCOVERY_LEXICAL_V1` for tiers 3 and 4 when `E(T)` is empty, ranked and truncated by Section 4.6. It runs entirely in the database as the read-only identity, uses no model, has no configuration, and sends nothing anywhere. It is the lexical baseline Charter Section 8 requires a candidate method to be compared against, and the initial implementation Charter Section 4.2 calls for — "exact identifiers, approved aliases, and lexical matching".

**Exactly one registered method serves a discovery request.** Which one is fixed by an adoption record — a recorded human decision taken as a minor version of this contract, after the Section 8.3 comparison — and never by a caller: a method is not an argument. Until another method is adopted, `M-LEX-1` is that method, and its identifier and version are the ones every result and every `candidate_set_id` carry (Sections 4.8 and 7). Charter Section 9's "each adopted method" is therefore read as each method that has been adopted for this role over time, judged at its own adoption, not as several methods answering one request. The Section 4.10 evaluation runner is the one exception, and it lies outside the caller request path: it may execute a candidate or registered-but-unadopted method over the registered cases, because point 5 below requires that comparison before any adoption. Its output is recorded only in the run artifact; it is never returned to a caller and never carried into a `candidate_set_id` a selection may cite. **The exception moves nothing else.** A method under comparison executes only templates already registered under `mvp-v0.1` Section 4.4, only as the read-only runtime identity in a read-only transaction, contributes candidates only and never auto-resolves whatever it computes, and sends nothing outside the process — the last of which is the boundary the closing paragraph of this section reserves to a separately reviewed ADR. Points 2, 3, 4 and that paragraph bind a method under comparison exactly as they bind a registered one; what point 5 defers until the comparison has run is the adoption, not the fence. Section 4.8's step 2 carries the matching exception, without which a `candidates` case could not be scored for any method under comparison.

**Registering another method** — BM25, a vector variant, or anything else — is a minor version of this contract under Section 10, and the registration must state:

1. its identifier and version, both recorded in every result and every evaluation artifact;
2. its inputs, which may be the registry and the term and nothing else — no fact table, no evidence bundle;
3. its determinism: given the same `registry_digest` and the same request, the same ordered candidate list, byte for byte. A method that cannot promise this cannot be registered, because Section 4.8's selection path re-derives the list;
4. how its output maps into the Section 4.5 tier vocabulary. **No method may auto-resolve.** Auto-resolution is Section 4.7's tier-1-or-2 uniqueness rule and nothing else; an added method contributes candidates only, whatever it computes;
5. its comparison against `M-LEX-1` on the registered evaluation set, by the Section 4.11 definitions, judged against thresholds registered before the run (Section 8.3);
6. its operational cost, as Charter Section 8 requires: any new dependency, service, provisioning step, index, or egress.

**The boundary that is not this contract's to move.** A method that sends registry content, fixture content, an entity name, or any database row to an external service — an embedding API included — is outside [Project Charter](../PROJECT_CHARTER.md) Section 3.3, which permits an external model to receive "only the user request and the approved route, argument, and schema metadata required by the adapter contract". Such a method requires a **separately reviewed ADR** before it may be registered. This contract does not grant it, and a registration under point 1–6 above does not either. Charter Section 8 additionally admits vector search only on a material improvement on the difficult semantic cases within a pre-registered budget for false resolution, latency, and complexity; Section 8.3 is where such a budget would be registered.

### 4.10 The labeled discovery evaluation set

[Project Charter](../PROJECT_CHARTER.md) Section 8 requires an approved entity registry **and** a labeled evaluation set to exist before Entity Discovery is added, and lists what the set must include. This section fixes the classes, the authoring rules, and what an evaluation run records. It authors no case and registers no number itself; Section 8.3 registers the forty cases and the per-class thresholds, and each authoring rule below is an assertion over them.

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
- **`false_resolution`** — over every case in the class: the fraction that returned `resolved` with a reference other than the one registered, or returned `resolved` at all where the registered outcome is not `resolved`. This is the quantity Charter Section 3.3 is about: an answer a reader cannot distinguish from a correct one, because it is a true fact about the wrong entity. A `resolved` returned for a case registered as `candidates` counts here **even when the reference is the registered target**: the resolution was not licensed by Section 4.7, and a method that resolves where the rule says abstain is the defect this metric exists to count, whichever entity it happened to land on.
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
| `invalid_request` | A malformed or empty term, a term over the length limit, a parameter outside the route allowlist, `parent_message_key` with `entity_kind` = `message`, or a contradictory scope. On a selection (Section 4.8): a `target_route` outside the three `mvp-v0.1` routes, a `mapping_key` without `target_route` = `signal_mapping`, a candidate-set digest that does not re-derive — including a re-run that yields no candidate list at all — a `selected_rank` naming no candidate, or a `target_route` the resolved candidate's `entity_kind` does not permit. No fact template executes in any of these. |
| `unsupported` | The request is not representable by this contract at the producing layer: an `entity_kind` outside `message` and `signal`. A route name outside the **union registry** of Section 3.3 — neither this contract's two routes nor `mvp-v0.1` Section 4.5's three — never reaches this contract's validation at all: it is refused as an unregistered route before dispatch, with the producing layer recorded. The trace records the producing layer. |

**`success` is not in this table, and its absence is the point.** `success` in `mvp-v0.1` Section 5 means a registered template returned facts. Discovery returns no facts, so a discovery result can never carry that status, and no reader can mistake a candidate list for an answer. The `success` that ends a discovery flow is the `mvp-v0.1` result of the fact route the selected reference is passed to.

Every status carries an `evidence_bundle`, a `source_trace`, and a `limitations` list, including every negative outcome (Section 7). For `invalid_request`, `unsupported`, and the `ambiguous` case that is refused before dispatch, no discovery template executes and the evidence bundle records that no connection was opened for discovery.

## 6. Determinism

- Every registered template carries its ordering clause with explicit `NULLS LAST`; the runtime never applies caller-supplied ordering, and `k` is fixed by Section 4.6 rather than supplied by a caller.
- The candidate ordering in Section 4.6 is **total**: no two candidates share a canonical reference, so no tie can survive to the last key.
- Text comparison and ordering use the `C` collation of `mvp-v0.1` Section 6. Discovery normalization (Section 4.5) is ASCII and locale-free, and applies only to candidate generation.
- **No score.** A candidate carries a discrete tier, so ranking cannot drift with a floating-point detail of an implementation or a platform.
- Two discovery requests with the same arguments against the same `registry_digest` return results that are byte-identical **with `registry_built_at` removed**, `candidate_set_id` included. `registry_built_at` is provisioning provenance (Section 4.1) and differs between two provisionings that share a digest, so it is excluded from the comparison the way `mvp-v0.1` Section 4.9 `D1` excludes its run identifier and timestamp; nothing else in a result may differ. `candidate_set_id` is a digest of the request and the result (Section 4.8) — it contains no clock, no counter, and no randomness.
- A latency measurement is recorded by the evaluation runner and never appears in a result payload, which is what keeps the previous rule true (Section 4.11).
- Repeatable provisioning from the same fixture files produces the same registry rows, the same `entity_match_term` derivation, and the same `registry_digest`. Surrogate keys may differ between runs and appear in no public payload, exactly as `mvp-v0.1` Section 6 permits.
- Determinism is a property of this whole layer, not only of the baseline: Section 4.9 point 3 refuses to register a method that cannot promise it, because Section 4.8's selection path re-derives the candidate list.

## 7. Evidence obligations

Every discovery result, and every selection refused before dispatch, carries the three structures `mvp-v0.1` Section 7 requires with the keys below. A **dispatched** selection is the `mvp-v0.1` result of its `target_route` and carries that contract's keys at the top level; what this contract adds to it is fixed by Section 4.8's list and nothing here. Where a bullet below names a key a dispatched selection also carries — this contract's identity, `registry_digest`, `registry_built_at`, `method_identifier`, `method_version` — that key is carried **inside the `selection` record** for a dispatched selection and at the top level for every other result. The three execution keys below — `template_name` and `template_version`, `bound_parameters`, `row_count` — are the same in kind but not in name: on a dispatched selection the top-level three are the fact route's, and the discovery re-run's are the `selection` record's `discovery_*` keys (Section 4.8). The keys below are `mvp-v0.1` Section 7's keys; the additions are named and each one exists because an obligation above needs to be checkable from the result.

**`evidence_bundle`**

- `contract_identifier` and `contract_version` of this contract, and of `mvp-v0.1`, whose registry safeguards the templates run under.
- `route`: `entity_discovery`, or `entity_selection` for a refused selection. A dispatched selection returns the `mvp-v0.1` result of its `target_route`, whose `route` is that route's, with the `selection` record Section 4.8 adds.
- `template_name` and `template_version`, or an explicit empty value when no template executed. On a dispatched selection this pair is the `target_route`'s; the discovery template the step-2 re-run executed is `discovery_template_name` and `discovery_template_version` in the `selection` record (Section 4.8).
- `bound_parameters`: exactly the parameters bound, with values — including `normalized_term` where the lexical template ran. An outcome that opens no connection binds nothing and reports an empty value, never the arguments it rejected. This is `mvp-v0.1` Section 7's rule, and its reason holds here unchanged: a rejected proposal must not be recorded as something the runtime acted on. On a dispatched selection this key is the `target_route`'s parameters alone and the re-run's are `discovery_bound_parameters` (Section 4.8); nothing the runtime bound goes unrecorded either way.
- `row_count`: the number of registry match rows the template returned, before truncation to `k`. On a dispatched selection this is the `target_route`'s own row count and the re-run's is `discovery_row_count` (Section 4.8).
- `resolved_scope`: the single `(project_code, revision_label, network_name, snapshot_label)` used, or an explicit empty value.
- `collation` in effect.
- `read_only_safeguards`: the runtime role name, the read-only transaction flag, and whether a connection was opened.
- `registry_digest` and `registry_built_at` — **the addition that makes a discovery result reproducible.** A result without them names no registry state, and Section 4.8's re-derivation would have nothing to compare against.
- `method_identifier` and `method_version` — which retrieval method produced the list.
- `match_tier` and `matched_text` for a `resolved` outcome; per candidate for `candidates`.
- `candidate_set_id` and `candidate_count` for a `candidates` outcome. For a **refused** selection, the `candidate_set_id` cited, the `selected_rank`, and the `target_route` named; for a **dispatched** selection, the `selection` record fixed by Section 4.8, which carries all three. `target_route` is recorded because it is the caller's choice among the routes the candidate permits, and a result that did not name it could not be traced back to the request that produced it.

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
- when a reference reached a fact route through the Section 4.8 selection path, naming the `candidate_set_id`, the candidate count it was selected from, and the `target_route` it was dispatched to. This is the explicit-selection entry `mvp-v0.1` Section 7 requires, now backed by a path that verifies it;
- when a selection is refused because its re-run produced no candidate list (Section 4.8), naming the outcome the re-run produced — `resolved`, `not_found`, or `coverage_gap` — so that the caller knows whether to discover again or that the entity is no longer discoverable;
- when the outcome is `coverage_gap`, stating what coverage could not be established.

## 8. Acceptance evidence

Each obligation is either an automated assertion over registered inputs or a recorded human decision with named evidence, as [Project Charter](../PROJECT_CHARTER.md) Section 9 requires.

| Obligation | Acceptance evidence |
| --- | --- |
| Section 4.1 registry schema and constraints | Automated. A data-level check asserts every constraint, including the exactly-one-occurrence-reference check, both partial unique constraints, the foreign keys into the `mvp-v0.1` tables, and the **absence** of a unique constraint on `alias_text` alone. |
| Section 4.2 integrity | Automated. The same check asserts the three derivation rules for `entity_match_term`, the same-snapshot rule for an alias's asserting snapshot, the enumerated values of `entity_kind` and `alias_kind`, and that loading a match text whose normalization has no token aborts. Each must be shown to fail against a database from which the rule has been removed. |
| Section 4.2 refresh and digest | Automated. Provisioning twice from the same fixture files produces the same `registry_digest`; provisioning from a registry file with an unresolvable natural key aborts with no partial load; the stored digest equals a recomputation from the loaded rows. |
| Section 4.3 request validation | Automated. Fixtures `DX-011` through `DX-014` below, each asserting that no discovery template executed. |
| Section 4.4 templates | Automated. Negative tests for an unregistered template, a write keyword at registration, an unknown parameter, and a missing required parameter, under `mvp-v0.1` Section 4.4's safeguards; template-level tests assert each registered `LIMIT`, each `NULLS LAST`, and that the registered result column list contains no attribute column. |
| Section 4.5 normalization and tiers | Automated. A unit-level table of terms and expected tiers, including the case-only difference that must reach tier 3 and never tier 1. |
| Section 4.6 candidate contract | Automated. `DX-016` for truncation at `k`; a test asserting one candidate per entity where several match texts match; a test asserting no attribute column appears in a candidate. |
| Section 4.7 auto-resolution | Automated. `DX-001` through `DX-007`. `DX-004` and `DX-005` are the two collisions that must **not** resolve, and either alone is satisfied by a rule this section rejects. |
| Section 4.7 alias policy | **Recorded human decision — discharged.** Whether an approved alias may auto-resolve is the Charter Section 4.2 question this section answers. The repository owner adopted the tier-1-and-2 reading at contract review on 2026-09-11 ([#138](https://github.com/OKJ1105/evidence-first-rag/issues/138)); the declined alternative is recorded beside it. The adopted rule's own behaviour is asserted by the Section 4.7 row above, `DX-001` through `DX-007`. |
| Section 4.8 selection path | Automated. `DX-017` for a verified selection reaching a fact route, `DX-018`, `DX-019` and `DX-021` through `DX-023` for the five refusals, and **not** `DX-020`, which Section 8.1 registers as a `limitations` case rather than a refusal; a test asserting that a changed registry changes `candidate_set_id`, one asserting that `target_route` is **not** an input to that digest, and one computing the digest from the Section 4.8 key list independently of the runtime and matching it. `DX-017` additionally asserts that the `selection` record names the discovery template the step-2 re-run executed, its bound parameters and its row count, and that the top-level `template_name` and `bound_parameters` are the fact route's — so that both templates that executed are evidenced and neither reading of `mvp-v0.1` Section 7 is left to an implementer. A discovery or selection request carrying any parameter that names a retrieval method is refused as a parameter outside the route allowlist with no template executed, and a `candidate_set_id` produced by the Section 4.10 runner under a registered-but-unadopted method is refused by `entity_selection`. |
| Section 4.9 `M-LEX-1` | Automated. The method's results over the registered evaluation set, recorded in the run artifact with its identifier and version. |
| Section 4.9 registering another method | **Recorded human decision**, per registration, as a minor version of this contract. A method that would send registry content outside the process additionally requires a separately reviewed ADR. |
| Section 4.10 evaluation set | Automated: each authoring rule is an assertion over the cases Section 8.3 registers at `0.3.0`, and `authoring_failures(REGISTERED_SET)` is empty. |
| Section 4.11 metrics | Automated. The runner computes every metric from the recorded per-case results, and no model participates. |
| Section 4.12 boundaries | Automated. One assertion per line: no attribute column in any discovery payload; no code path from a fact-route failure to discovery; a `needs_entity_discovery` result opens no connection and triggers no discovery; the runtime identity is refused `INSERT`, `UPDATE`, `DELETE`, and `CREATE TABLE` on the registry tables, from PostgreSQL privileges rather than an application guard. |
| Sections 5 and 7 | Automated. Every fixture in Section 8.1 asserts its status family and the presence of all three evidence structures with the required keys, including `registry_digest`. |
| Section 6 determinism | Automated. Two runs over the same registry and request compare byte-identical with `registry_built_at` removed, `candidate_set_id` included; a second provisioning from the same fixture files yields the same `registry_digest` and the same `candidate_set_id` for the same request; the read-only state digest of `mvp-v0.1` Section 4.10 is extended to the four registry tables and must be unchanged across a discovery run. |
| Section 3.3 extension 1, the route registry | Automated. A route name in neither this contract's two routes nor `mvp-v0.1` Section 4.5's three is refused before dispatch as an unregistered route, with the producing layer recorded and no template executed. Whether `mvp-v0.1` is patched to name the two routes is the separate **recorded human decision** in Section 9; the union-validation obligation holds either way. |
| Section 3.3 extension 2, the runtime identity's privileges | **Recorded human decision**, recorded in Section 9. The privileges themselves are asserted by the Section 4.12 row. |
| Section 3.3 extension 3, the dispatched-selection `evidence_bundle` key | **Recorded human decision**, recorded in Section 9. The key set itself is asserted by the Section 4.8 row. |
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
| `DX-012` | Empty or whitespace-only term, and a term over the 200-byte limit | `invalid_request`, no connection opened |
| `DX-013` | `parent_message_key` supplied with `entity_kind` = `message` | `invalid_request` |
| `DX-014` | `entity_kind` outside `message` and `signal` | `unsupported`, producing layer recorded |
| `DX-015` | Occurrence present in the loaded data but absent from `approved_entity` | `not_found`, limitation stating that absence from the registry is not absence from the data |
| `DX-016` | More than `k` entities match at one tier | `candidates`, exactly ten, truncation recorded in `limitations` |
| `DX-017` | Selection citing a candidate set that re-derives, with a `target_route` the candidate permits | `success` from that route, with the selection entry in `limitations` naming the digest, the count and the route, and the `selection` record carrying the fact route's identity alongside the step-2 re-run's `discovery_template_name`, `discovery_bound_parameters` and `discovery_row_count` while the top-level `template_name` and `bound_parameters` are the fact route's |
| `DX-018` | Selection citing a `candidate_set_id` that does not re-derive | `invalid_request`, no fact template executed |
| `DX-019` | Selection whose `selected_rank` names no candidate in the re-derived list | `invalid_request`, no fact template executed |
| `DX-020` | Alias asserted by a snapshot whose `superseded_by` is non-null | The outcome the term earns, with the required `superseded_by` entry in `limitations` |
| `DX-021` | Selection of a `message`-kind candidate with `target_route` = `signal_facts`, and of a `signal`-kind candidate with `target_route` = `message_facts` | `invalid_request` in both, no fact template executed |
| `DX-022` | Selection carrying `mapping_key` with `target_route` = `signal_facts`, and one naming a `target_route` outside the three `mvp-v0.1` routes | `invalid_request` in both, no fact template executed |
| `DX-023` | Selection citing a candidate set whose re-run, against a registry re-provisioned without the selected entity, yields `not_found` | `invalid_request`, no fact template executed, `limitations` naming `not_found` as the re-run's outcome |

`DX-004` and `DX-005` are the two halves of Section 4.7's uniqueness rule — a collision between kinds of match text, and a collision between parents — and an implementation that passes one while failing the other has made something other than tier-1-and-2 uniqueness its rule. Read them together, as `mvp-v0.1` Section 8.1 says of `FX-105` and `FX-113`.

`DX-015` is the fixture that proves the registry is an allowlist rather than a mirror of the loaded data. Without it, an implementation that discovered straight from `message_occurrence` and `signal_occurrence` would pass every other case here.

`DX-021` and `DX-022` are the two halves of the Section 4.8 route check, and they fail at different steps: `DX-022` is refused at step 1, on the argument alone, and `DX-021` at step 6, against a candidate the runtime does not have until step 5. A single fixture would leave whichever step it did not reach untested, and an implementation with only one of the two checks would still pass it.

`DX-020` deliberately does not fix its own status: whether the term earns `resolved` or `candidates` is decided by Section 4.7 as for any other term, and what the supersession changes is the `limitations` entry, not the outcome. A superseded snapshot still holds facts about itself; what is prohibited is presenting them as holding in a later snapshot.

### 8.2 Deferral of the acceptance evidence

Section 10 permits this contract to be accepted with its acceptance evidence explicitly deferred with a named owner. This section is that record.

The deferral is structural, not a concession. Every row of the Section 8 table is an assertion over an implementation that does not exist on the date this contract is proposed: the repository holds no registry table, no registry fixture, no discovery template, and no discovery runner. Requiring the evidence before acceptance would make acceptance unreachable, because [Contract Shape Framework](README.md) Section 2.1 forbids implementing against a contract that is not accepted. The order is contract first, then the evidence with the implementation the contract governs — the same order `mvp-v0.1` Section 8.2 records for itself.

**Named owner: the repository owner.** Nothing here is delegated to an AI writer or reviewer.

| Class | Discharged |
| --- | --- |
| Every row marked **Automated** | On the pull request that introduces the behaviour that row governs. Its assertions are a merge condition for that pull request. A pull request that implements a behaviour without them is incomplete, not deferred again. |
| Section 4.7's alias policy | **Discharged** at contract review on 2026-09-11 ([#138](https://github.com/OKJ1105/evidence-first-rag/issues/138)), by the owner's record on the pull request that moved the status line. |
| Section 3.3's three extensions | **Not at contract review.** What each row asks is whether `mvp-v0.1` is *patched* to name this contract's routes, registry tables, and `selection` record — an amendment to an `Accepted` contract, which its Section 10 reserves to the repository owner and which no acceptance of *this* document can take on the owner's behalf. Each is discharged on the `mvp-v0.1` amendment it leads to, or, if the owner leaves the enumerations as they are, on the implementation pull request that first relies on the extension, by that pull request recording which reading it built against. Section 3.3 states the reading that holds in the interval for each of the three, so that no implementer is blocked and no two `Accepted` documents contradict each other while a row stays open. Extension 1's union-validation obligation is Automated and discharged with the behaviour, per the row above. |
| Section 4.9's per-method registration | At the registration of each later method, as a minor version of this contract. |
| The adoption thresholds | At the Milestone 3 gate, after Section 8.3 registers them and the run they judge has happened. |

This deferral does not weaken any obligation, and Section 10 forbids using it to. No implementation pull request may cite this section as a reason to omit the evidence its own slice owes.

### 8.3 The evaluation set and the adoption thresholds, registered 2026-09-13T15:55:00Z

This section fills the row Section 9 left open at `0.2.0`. [Project Charter](../PROJECT_CHARTER.md) Section 9 requires a numeric adoption threshold to be registered *before the run it judges*, and states that reporting a metric without a pre-registered pass condition does not satisfy a gate. This section is that registration. It was taken as a minor version under Section 10 and a recorded human decision: the operative record is the repository owner's on [#153](https://github.com/OKJ1105/evidence-first-rag/pull/153), where the owner adopted the draft and merged it, as Section 2 requires of this document's own acceptance — an Issue body written by a writer session is not one. [#152](https://github.com/OKJ1105/evidence-first-rag/issues/152) is the task record that carries the registration and its reasoning, and [#154](https://github.com/OKJ1105/evidence-first-rag/issues/154) the three corrections `0.3.1` makes, recorded the same way on the pull request that closes it.

`registered_at`: `2026-09-13T15:55:00Z`. `contract_version`: `0.3.1`. A run whose start instant is not strictly later than `registered_at` is not judged by these thresholds. **`0.3.1` re-registers the instant under Section 4.10 rule 8**, which requires it of a change to this section: the conditions below changed — the `Q-SEMANTIC` rank bound became a pass condition in its own right — so the `0.3.0` instant no longer names the text a run would be judged under. No case, threshold, bound or digest moved, and no run over this set has happened.

`registry_digest`: `1b81429adae7a373bf434b6a7e1e912991808c94376df849fdfd5c230c608ddb` — the Section 4.2 digest of the registry loaded from the fixture files at `mvp-v0.1` `0.6.1` and this contract `0.2.1`. Every case below was authored against that state. Section 4.10 rule 8 makes a registry change that alters any registered case's outcome a patch version of this section that re-registers `registered_at`, and this digest is how such a change is detected rather than remembered.

#### The evaluation set

`N` = 40, five cases in each of the eight Section 4.10 classes. The cases are registered in `src/evidence_first_rag/discovery/evaluation.py` as `REGISTERED_SET`; every case's class, request arguments, registered outcome, canonical reference or rank bound is fixed there, and each authoring rule of Section 4.10 is an assertion over them.

| Class | Cases | Registered outcome | Names a target |
| --- | --- | --- | --- |
| `Q-EXACT` | `EV-EXACT-1`–`5` | `resolved` | yes |
| `Q-ALIAS` | `EV-ALIAS-1`–`5` | `resolved` | yes |
| `Q-COLLIDE` | `EV-COLLIDE-1`–`5` | `resolved` | yes |
| `Q-SEMANTIC` | `EV-SEMANTIC-1`–`5` | `candidates`, rank bounds `1, 1, 1, 2, 1` | yes |
| `Q-MULTI` | `EV-MULTI-1`–`5` | `candidates`, with `2, 2, 2, 3, 7` references | yes |
| `Q-SCOPE` | `EV-SCOPE-1`–`5` | `ambiguous` | no |
| `Q-NOMATCH` | `EV-NOMATCH-1`–`5` | `not_found` | no |
| `Q-OUT` | `EV-OUT-1`–`5` | `unsupported` (3), `coverage_gap` (2) | no |

Twenty-five cases name a target and a `mvp-v0.1` route; fifteen register a refusal. Every request text is English (rule 7). Every case was authored **without running any retrieval method over it** (rule 5): each outcome was read off the registry rows and Section 4.5's tier table, and then checked against a second derivation written independently from the same table.

#### Thresholds

A method is adoptable for the Section 4.9 role only if every condition below holds **in every class in which the quantity has a denominator**, by the Section 4.11 definitions, over the set above. Whole-set values are reported beside the per-class ones and carry no bar of their own: Charter Section 9's gate is per class, and a whole-set bar can be met while a class fails.

| Quantity | `Q-EXACT` | `Q-ALIAS` | `Q-COLLIDE` | `Q-SEMANTIC` | `Q-MULTI` | `Q-SCOPE` | `Q-NOMATCH` | `Q-OUT` |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `false_resolution` | ≤ `0.00` | ≤ `0.00` | ≤ `0.00` | ≤ `0.00` | ≤ `0.00` | ≤ `0.00` | ≤ `0.00` | ≤ `0.00` |
| `correct_abstention` | — | — | — | ≥ `1.00` | ≥ `1.00` | ≥ `1.00` | ≥ `1.00` | ≥ `1.00` |
| `over_abstention` | ≤ `0.00` | ≤ `0.00` | ≤ `0.00` | — | — | — | — | — |
| `recall_at_1` | ≥ `1.00` | ≥ `1.00` | ≥ `1.00` | ≥ `0.80` | reported | — | — | — |
| `recall_at_5` | ≥ `1.00` | ≥ `1.00` | ≥ `1.00` | ≥ `1.00` | ≥ `0.80` | — | — | — |
| `recall_at_10` | ≥ `1.00` | ≥ `1.00` | ≥ `1.00` | ≥ `1.00` | ≥ `1.00` | — | — | — |
| `task_completion` | ≥ `1.00` | ≥ `1.00` | ≥ `1.00` | ≥ `1.00` | ≥ `1.00` | — | — | — |
| `mrr` | reported | reported | reported | reported | reported | — | — | — |
| `latency` | reported | reported | reported | reported | reported | reported | reported | reported |

**A ninth condition is not in the table, because it is not a per-class fraction.** Every `Q-SEMANTIC` case's registered target must appear at a rank at or above that case's own registered `rank_bound`. Rule 3 registers a bound per case precisely because "the target is somewhere in ten candidates" and "the target is first" are different claims, and a class fraction cannot distinguish them: over the registered bounds `1, 1, 1, 2, 1`, a method that returns `EV-SEMANTIC-1`'s target at rank 2 and `EV-SEMANTIC-4`'s at rank 1 scores `recall_at_1` = `0.80` and clears the class bar, having violated one bound and cleared a bar it was never set — the two errors cancel in the aggregate. The class bar is derived *from* the bounds, so a reading on which the derived condition is weaker than what it was derived from would register less than the bounds say. Both are conditions: the aggregate, and each case's own bound. A judge that checks only the fraction has not judged this registration.

Two cells carry no bar for different reasons, and the difference is part of the registration. **`—`** marks a pair whose Section 4.11 denominator is empty by the class's registered outcome — `recall_at_k` over a class that names no target, `correct_abstention` over a class registered `resolved`, `over_abstention` over a class registered otherwise. The runner reports `null` there, and a run that reports a number in such a cell has a defect. **`reported`** marks a pair whose denominator exists and on which no bar would say anything: `recall_at_1` over `Q-MULTI`, where every case registers at least two references that Section 4.11 requires all of, so no method can score above zero. Neither is a waiver.

#### The reasoning behind each number

A bar is a judgement unless it is derived. Almost every bar below is **derived** — entailed by this contract's own rules applied to the registered cases — and the derivation is given so a reader can check the entailment rather than weigh an opinion. With five cases per class, every achievable value is a multiple of `0.20`, so a bar is stated only at that granularity, and "≥ `0.80`" means exactly "at most one miss".

**`false_resolution` ≤ `0.00`, every class — derived, on two independent grounds.** First, Charter Section 3.3, as `mvp-v0.1` Section 8.3 reasons for its own zero: a false resolution is a true fact about the wrong entity, an outcome a reader cannot distinguish from a correct answer, and the failure this milestone exists to prevent. Second, this contract's structure. Section 4.9 point 4 fixes that **no method may auto-resolve** — auto-resolution is Section 4.7's tier-1-or-2 uniqueness rule and nothing else, and tiers 1 and 2 are byte-exact facts about the registry rather than a method's judgement. Every case registered `resolved` was authored by reading that rule against the registry at the digest above, and every case registered otherwise so that the rule does not license a resolution. A conforming method therefore scores zero by construction, and a positive value is not a weaker method but one that resolved where Section 4.7 does not permit it. A bar above zero would register permission for exactly that.

**`correct_abstention` ≥ `1.00` — entailed by the bar above.** In each of the five classes where it has a denominator, every case is registered not-`resolved`, so a miss here is exactly a false resolution counted above and `correct_abstention` = 1 − `false_resolution` within those classes. It is registered separately because Section 8.3 names it and because the two denominators differ over the whole set; the value is not a second decision.

**`over_abstention` ≤ `0.00` and `recall_at_k` ≥ `1.00` in the three `resolved` classes — derived.** Section 4.11 fixes the observed list for a case registered `resolved` as the single resolved reference at rank 1, so the three recall values coincide and each equals 1 − `over_abstention` once false resolutions are excluded. Whether such a case resolves is decided by Section 4.7 over tiers 1 and 2, which are registry facts a method does not compute. Anything below `1.00` would admit a method that refuses a byte-exact identifier, an approved alias, or a fully scoped key — the three things Charter Section 4.2 names as what discovery should prefer, and the floor of usefulness for an allowlist that exists to make those requests answerable. For the baseline this is a conformance check rather than a performance bar: a miss reveals a defect in the implementation of the contract's own rule — normalization, scope handling, or `parent_message_key`, which `EV-COLLIDE-5` is the case that turns on — which is what a run before adoption is for.

**`recall_at_k` in `Q-SEMANTIC` — derived from the registered rank bounds.** Rule 3 makes each case register the rank its target must meet, because "somewhere in ten" and "first" are different claims. The class bar is the aggregate those bounds entail: the fraction of cases whose bound is at or below `k`. The registered bounds are `1, 1, 1, 2, 1`, giving `recall_at_1` ≥ `0.80` and `recall_at_5` = `recall_at_10` ≥ `1.00`. The judgement was taken when the bounds were authored, and each bound was itself derived: four terms reach one entity by Section 4.5's tier-4 containment, and `EV-SEMANTIC-4`'s bound is `2` because its term reaches two entities and Section 4.6's ordering places the other first — a bound of `1` there would register a bar the contract's own ordering forbids any conforming method from clearing. No tolerance is added above the bounds, in either direction: the class bar is how the bounds aggregate, and the condition above is each bound holding on its own case. `rank_bound` is recorded in the run artifact; the judge step reads it.

**`recall_at_k` in `Q-MULTI` — derived from the registered lists.** Section 4.11 counts a `Q-MULTI` case only when **every** registered reference appears, so the set fixes ceilings no method can exceed: every case registers at least two references, so `recall_at_1` is `0.00` for every method; `EV-MULTI-5` registers seven, so `recall_at_5` cannot exceed `0.80`. The bars are those ceilings, for a safety reason rather than a usefulness one: a candidate list that omits a plausible candidate presents part of an ambiguity as the whole of it, and the person selecting from that list cannot know. Every registered list is within `k` = 10, so no case here is affected by Section 4.6 truncation.

**`task_completion` ≥ `1.00` in every targeted class — derived from Section 4.1.** This quantity is the numeric form of Charter Section 9's gate item that selected candidates "are canonical entity references that are present in the approved entity registry and resolvable in the approved data scope". Section 4.1 makes every approved entity a foreign key into a loaded occurrence, so every reference this set names is resolvable by its fact route by construction, and a completion miss is a broken invariant — of the registry, the selection path, or a fact route — and not a retrieval shortfall.

**`mrr` — reported, with the floors the recall bars entail** so a reader can check a run against them: `1.00` in the three `resolved` classes, `0.90` in `Q-SEMANTIC` (four targets at rank 1 and one at rank 2), and `83/210` ≈ `0.395` in `Q-MULTI` (worst-ranked references at `2, 2, 2, 3, 7`). No separate bar: a run meeting the recall bars meets these, and a bar on a derived quantity would be a second copy of the first.

**`latency` — reported, with no bar in any class.** Charter Section 8 asks that methods be compared on it and Section 4.9 point 6 that a later method record its cost; the pre-registered budget Charter Section 8 requires is a vector variant's and is registered with that variant. `M-LEX-1` is two fixed SQL templates executed as the read-only identity and adds no dependency, service, provisioning step, index, or egress; its `operational_complexity` record says so, and Section 4.11 keeps that a description the owner weighs rather than a number.

#### What this registration states plainly

**The baseline is expected to clear every bar, and that prediction may not be cited.** Reading the rules against the registered cases predicts `1.00` on every gated quantity for `M-LEX-1`, because the cases were derived from the rules `M-LEX-1` implements. Charter Section 9 admits only the run. It also means these bars do not measure how good the baseline is: they check that an implementation conforms, and they fix the floor a later method may not fall below.

**No case in this set is a difficult semantic case.** Every `Q-SEMANTIC` term reaches its target by Section 4.5 tier-4 token containment, which is what a lexical method does; a vector variant could show no improvement here even if it were better. Charter Section 8 admits vector search only on a "material improvement on the difficult semantic cases" within a pre-registered budget. This version registers **no vector variant and no budget**, and registers instead — so that a later registration cannot choose after the fact — what such a case is: a `Q-SEMANTIC` case whose term shares **no token** with any `match_text` of its target under Section 4.5, so that tier 4 cannot reach it. A synonym, an abbreviation, or a description in other words. **This set holds zero of them.** A registration under Section 4.9 of a vector variant must first add such cases as a patch version of this section, re-registering `registered_at` before the run it judges (rule 8), and register its budget beside them. Until then no vector comparison over this set may be cited.

**Ten of the forty cases are refusals decided before any *discovery* template runs.** `Q-SCOPE` and `Q-OUT` measure validation rather than retrieval, so `recall_at_k` and `mrr` have a denominator of twenty-five, not forty. *Discovery* is the operative word, and matches Section 4.10's `Q-SCOPE` row: seven of the ten — the five `Q-SCOPE` cases and `EV-OUT-4`/`EV-OUT-5` — open a connection and execute the `mvp-v0.1` candidate query, which Section 4.3 runs on every request because it is what tells `coverage_gap` from `not_found`. Only `EV-OUT-1` to `EV-OUT-3`, refused on an `entity_kind` outside the two Section 4.1 enumerates, open no connection at all. A reader checking a run against this sentence should expect an empty `template_name` on three records, not ten. That is what Charter Section 8's eight bullets ask for; it is stated here so that a whole-set number is not read as a retrieval score.

**Two `Q-MULTI` cases are degenerate requests.** `sample msg` and `sample sig` match on the fixture naming convention rather than on anything a person would type. They are registered because the loaded occurrences offer few genuinely ambiguous descriptions, and because a broad term is the request a method is most tempted to resolve. Replacing them takes more fixture rows and a patch version.

**What this section does not decide.** Adoption. The Section 8 row for the thresholds stays a recorded human decision taken after the run, in the Milestone 3 acceptance record under `docs/acceptance/`. A judgement that these bars were cleared is an input to that decision, not a substitute for it.

## 9. Deferred decisions

| Decision | Owner |
| --- | --- |
| ~~The evaluation set's cases and `N`, and the per-class adoption thresholds~~ **Decided 2026-09-13**: forty cases, five per class, and the per-class thresholds are registered in Section 8.3, at `0.3.0` and corrected at `0.3.1`. The operative record is the owner's on [#153](https://github.com/OKJ1105/evidence-first-rag/pull/153) and on the pull request closing [#154](https://github.com/OKJ1105/evidence-first-rag/issues/154); [#152](https://github.com/OKJ1105/evidence-first-rag/issues/152) is the task record. | Retained as a row rather than deleted, so that a reader of this table can see the decision was taken rather than dropped. Changing a registered number is a version under Section 10, and re-registers `registered_at` before the run it judges. |
| ~~Whether an approved alias may auto-resolve (Section 4.7), against the conservative alternative recorded there~~ **Decided 2026-09-11**: the tier-1-and-2 reading is adopted ([#138](https://github.com/OKJ1105/evidence-first-rag/issues/138)). | Retained as a row rather than deleted, so a reader of this table can see the decision was taken rather than dropped. Changing it is a minor version under Section 10. |
| Whether `mvp-v0.1` Section 4.5's route table is patched to name `entity_discovery` and `entity_selection` (Section 3.3, extension 1) | The repository owner, under `mvp-v0.1` Section 10. Implementation does not depend on the answer: Section 3.3 fixes that route-name validation runs against the union either way. |
| Whether `mvp-v0.1` Section 4.3's privilege enumeration is patched to name this contract's registry tables (Section 3.3, extension 2) | The repository owner, under `mvp-v0.1` Section 10. Implementation of this contract does not depend on the answer. |
| Whether `mvp-v0.1` Section 7's `evidence_bundle` key list is patched to name the `selection` record (Section 3.3, extension 3) | The repository owner, under `mvp-v0.1` Section 10. Implementation does not depend on the answer: Section 4.8 fixes the record's contents either way. |
| BM25 as a registered method | A later minor version of this contract, under Section 4.9. |
| Vector or embedding-based candidate retrieval | A later minor version of this contract **and** a separately reviewed ADR, if any registry or database content would leave the process ([Project Charter](../PROJECT_CHARTER.md) Section 3.3). Charter Section 12's "whether vector search materially outperforms lexical and BM25 baselines" is answered by the comparison, not by a contract. |
| Any scope-selection policy that resolves a scope dimension automatically | `mvp-v0.1` Section 9's row, unchanged. Not this contract's, and not prejudiced by it. |
| Which Section governs a request whose scope is incomplete and whose entity reference cannot be formed | [#43](https://github.com/OKJ1105/evidence-first-rag/issues/43), against `mvp-v0.1`. Section 4.3 requires a complete scope and neither answers nor forecloses it. |
| The API and rendering surface for discovery and selection, and any export of a candidate list | Milestone 4 contracts. This contract fixes routes on the existing runtime, not an interface. |
| Alias approval outside this repository | Out of scope. `approval_reference` is an opaque citation; this contract fixes that one is required, not how it is obtained. |

No row above is open in the sense that this contract needs it to be implementable. Sections 4.1 through 4.12 are complete as they stand; every row either registers numbers that Charter Section 9 requires to come later, or belongs to another document.

## 10. Change control

- This contract is `Accepted`. Under [Contract Shape Framework](README.md) Section 7, a change that does not weaken a Charter or ADR invariant produces a new contract version with a recorded human decision. The looser rule that governed it while `Proposed` — amendment by an ordinary contract-only pull request — no longer applies.
- This contract may not move to `Accepted` until the repository owner records the review required by Framework Section 6 step 4, **and** the Section 8 acceptance evidence is either satisfied or explicitly deferred with a named owner. Both were discharged on 2026-09-11: the review in Section 2, and the deferral, with its named owner and the point at which each obligation is discharged, in Section 8.2. The rule is retained rather than deleted so that the acceptance record stays interpretable, as `mvp-v0.1` Section 10 retains its own. Framework Section 2.1: no milestone gate was involved.
- After acceptance, a change that does not weaken a Charter or ADR invariant produces a new version with a recorded human decision. Adding or removing a route, template, retrieval method, match tier, status condition, or evidence field is a minor version and requires a fresh independent design review. Filling Section 8.3 is a minor version. Adding a fixture case that exercises an existing obligation is a patch version.
- **Removing or weakening an obligation is not permitted at this layer.** A change that would weaken a Charter or ADR invariant requires an architecture decision recorded in an ADR, a Charter update where the change materially changes the Charter, and a recorded human decision.
- Two changes are named here because they are the ones an implementer will reach for: sending any registry or database content to an external service requires a separately reviewed ADR under [Project Charter](../PROJECT_CHARTER.md) Section 3.3 (Section 4.9), and permitting a method other than Section 4.7's tier-1-and-2 rule to auto-resolve would weaken the Charter Section 9 gate item on unapproved aliases and is therefore not a contract-level change at all.
- **This contract amends nothing in `mvp-v0.1`.** It *extends* it in the three places Section 3.3 records — the route registry, the runtime identity's privileges, and one `evidence_bundle` key on a dispatched selection — each additive, each weakening nothing, and each carried to Section 9 as the owner's decision on whether that contract is patched to name it. Where the two meet, `mvp-v0.1` governs the fact path and this contract governs discovery. A change here that would require a change there is an `mvp-v0.1` amendment under its Section 10, and is the repository owner's to record.
- This contract's acceptance does not depend on a separate recorded acceptance of [ADR-0002](../adr/0002-scoped-canonical-entity-identity.md). Its citations of that ADR are rationale; the operative identity and scope invariants this contract preserves are carried by [Project Charter](../PROJECT_CHARTER.md) Section 3.6 itself, and by `mvp-v0.1` Section 4.2, which is `Accepted`.
- A superseded version is retained with a `Superseded by` status rather than deleted, so that a past acceptance record stays interpretable.
