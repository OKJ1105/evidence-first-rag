# Milestone 4 Export Contract v0.1

## 1. Identifier and version

**Identifier:** `export-v0.1`

**Version:** `0.1.0` — the identifier names the document; the version tracks its obligations. `0.1.0` proposes the contract.

The version changes when any observable obligation in Section 4, 5, 6, or 7 changes. Adding or removing a column, a document, an entry group, or a refusal condition is a minor change. Adding a fixture case that exercises an existing obligation is a patch change. Removing or weakening an obligation is not permitted at the contract layer; see Section 10.

This contract covers the **export** half of the Milestone 4 deliverables in [Project Charter](../PROJECT_CHARTER.md) Section 9: "TSV export with a frozen column contract". In [Contract Shape Framework](README.md) Section 5 terms it belongs to the result and evidence families for a presentation surface. That framework assigns responsibilities per family; it does not require one document per family, and it does not require a contract to own every family. This one registers no entity, no route, no fixed SQL template, and no status family, because an export executes none of those.

It is a **separate document from [mvp-v0.1](mvp-v0.1.md) and [entity-discovery-v0.1](entity-discovery-v0.1.md), not an amendment to either.** Both are `Accepted`, and each makes a change to itself a recorded human decision under its own Section 10. Nothing here changes a word of either. `mvp-v0.1` Section 9 names "TSV export and any renderer beyond Section 4.8 template rendering" as this contract's row, and Charter Section 12 names "the final TSV schema" as the Milestone 4 export contract's; this document is those two rows and nothing more.

## 2. Status

**Status:** `Proposed`

Committed for review. Not binding on implementation: under [Contract Shape Framework](README.md) Section 2.1 an implementation slice may be accepted only against a contract in `Accepted` state, so **no Milestone 4 export code may be written against this document while this line reads `Proposed`.** It may be cited as direction; it does not satisfy the pre-implementation review required by step 4 of the [Development Workflow](../DEVELOPMENT_WORKFLOW.md).

The line moves under [Contract Shape Framework](README.md) Section 6: an independent design review by a model that did not author this document, then the repository owner's recorded human review of the contract and its acceptance evidence on its own pull request, then merge approval, then `Proposed` → `Accepted <date>` citing that review. **The writer session that authored this document may take none of those steps** — [#17](https://github.com/OKJ1105/evidence-first-rag/issues/17) rule 6 forbids a writer turn from moving it, and [CLAUDE.md](../../CLAUDE.md) forbids the writer from reviewing what it wrote.

Section 10 sets the preconditions that must be discharged before this line may move. Both are discharged in this document rather than only in pull request comments: the granularity decision Section 4.6 owns is recorded there, and the Section 8 acceptance evidence is explicitly deferred with a named owner in Section 8.2.

## 3. Scope

### 3.1 What this contract fixes

- **What an export is**: a function from one `mvp-v0.1` normalized runtime result, and the committed template registry read for one column list, to one *export document set*. It opens no connection and executes nothing.
- **The document set**: which documents it holds, that both are always present, and that a document with nothing to say carries its header row and no records.
- **The frozen column list** of the fact document, in order — the evidence block this contract names, the per-row provenance block, then the executing template's registered result column list in its registered order.
- **The row granularity of evidence**: which evidence travels on every exported row, which travels on the row it describes, and how a per-row correspondence is established rather than assumed.
- **The byte-level format**: field and record delimiters, character encoding, line ending, the escape set, and the representation that distinguishes a null from an empty string.
- **The derivation of every exported value** from the normalized result, field by field.
- **How the variable-length evidence structures are represented** — `limitations`, `bound_parameters`, contributing scopes, fixture provenance, alias provenance, and the `selection` record — since a rectangle holds none of them as a column and dropping any of them would weaken `mvp-v0.1` Section 7.
- **The closed list of refusal conditions**, and that a refusal produces no document at all rather than a partial one.
- **Determinism**: that exporting the same normalized result twice is byte-identical.
- **The complete list of values the export contributes that the result does not contain**, and that the list is closed.

### 3.2 What this contract does not fix

- **Any HTTP, route, or API surface that serves an export.** Charter Section 9's other Milestone 4 deliverable — "stable API flow from request or candidate selection to evidence-backed result" — is the separate **Milestone 4 API contract** that [Contract Shape Framework](README.md) Section 8 names for "route and result schemas for the post-Milestone 1 API". This contract fixes a document, not an interface that hands one over.
- **`mvp-v0.1` Section 4.8 answer rendering.** That section governs user-facing prose and is untouched. The export is a second presentation surface under the same Charter Section 3.1 rule, not a replacement for the first, and this contract relaxes nothing in it.
- **Where an export is written, how long it is kept, whether it is archived or compressed, and what a file is called outside a document set.** Placement and retention are deployment and interface questions.
- **Export of any discovery-layer result of [entity-discovery-v0.1](entity-discovery-v0.1.md)** — every outcome of its Section 5, a refused selection included, not only `candidates` and `resolved`. Such a result is a different shape with its own status vocabulary and its own required evidence keys, none of which has a column or an entry group here, so Section 4.9 `R6` refuses it rather than exporting it with those keys dropped. A fact result *reached through* the Section 4.8 selection path **is** in scope, because that result is an `mvp-v0.1` result of a fact route.
- **Multi-result export.** One export document set describes exactly one normalized result.
- **Any format other than TSV.** Charter Section 9 names TSV; nothing here opens CSV, JSON, or a spreadsheet format.
- **The minimal UI** of Charter Section 9's fourth Milestone 4 deliverable.

Section 9 records each of these with its owning slice.

### 3.3 What this contract inherits, and the three places it reads an accepted contract closely

These obligations apply unchanged to every path this contract defines. They are restated as inherited, not re-decided, and this contract may not weaken them ([Contract Shape Framework](README.md) Section 4).

| Inherited | From |
| --- | --- |
| Rendering and export may present validated results but may not add or alter facts | [Project Charter](../PROJECT_CHARTER.md) Section 3.1, [AGENTS.md](../../AGENTS.md), [Contract Shape Framework](README.md) Section 4 |
| Every result, including every negative outcome, carries an `evidence_bundle`, a `source_trace`, and a `limitations` list with the required keys | `mvp-v0.1` Sections 5 and 7 |
| The seven status families and their meanings; `unsupported` preserves its producing layer | `mvp-v0.1` Section 5, Charter Section 3.4 |
| `C` collation, byte-wise ordering, total orderings, no rounding, numeric values at their stored precision | `mvp-v0.1` Section 6 |
| Surrogate keys appear in no public payload | `mvp-v0.1` Sections 4.2 and 4.11 |
| A source trace describes fixture provenance that actually exists in this repository and never cites a raw source-format artefact | `mvp-v0.1` Section 7, [ADR-0001](../adr/0001-postgresql-runtime-and-normalized-fixture-boundary.md) |
| Identity and scope: project, revision, network, and source snapshot are required identity dimensions, and a signal occurrence additionally requires its parent message occurrence | Charter Section 3.6, `mvp-v0.1` Section 4.2 |
| The `selection` record and the alias provenance a dispatched selection adds, and their key sets | `entity-discovery-v0.1` Sections 4.8 and 7 |

**Three places where this contract reads an `Accepted` contract closely.** None edits that contract's text, none removes, renames, or reinterprets anything it defines, and none weakens an obligation. Each is recorded here, and Section 9 carries the repository owner's decision on whether that contract is patched to state it — a change to an `Accepted` contract, which its Section 10 assigns to the owner. **Implementation depends on none of the three answers**, because in each case this contract refuses rather than assumes.

**1. The row-to-mapping-provenance correspondence.** `mvp-v0.1` Section 4.5 fixes that a mapping result "exposes one entry per asserting relation", and Section 7 fixes that the trace carries the asserting and both endpoint scopes "separately identified". Neither sentence says that the *n*-th entry of `source_trace.mapping_provenance` describes the *n*-th row of the result. Section 4.6 below needs that correspondence to put a relation's provenance on the relation's own exported row, which is what Charter Section 3.6 requires — the asserting artifact's scope travels with each relation. **This contract does not assume the correspondence and does not ask `mvp-v0.1` to promise it.** It requires the exporter to check the one consequence it can check — that the two lengths are equal — and to refuse the export when they are not (Section 4.9, `R3`). A result that fails that check is not exported at all, so no reader is ever handed a row carrying another row's provenance.

**2. The names inside `source_trace`, and the shape of a `limitations` entry.** `mvp-v0.1` Section 7 describes `source_trace` in four prose bullets and names no members, and it describes `limitations` as a list of conditions without fixing an entry's shape. Sections 4.5, 4.7 and 4.9 of this contract read those bullets as four named members — `mapping_provenance`, one entry per asserting relation; `contributing_scopes`; `fixture_provenance`; and `producing_layer` — and read a `limitations` entry as carrying a **kind** and a **detail**, which is what puts the kind in `evidence_entry_key` and the detail in the value. **That reading is this contract's, not a quotation.** It matches what the repository's committed runtime types hold today, and Section 9 carries the owner's decision on whether `mvp-v0.1` is patched to name them. Where the reading could fail silently it does not: `R3` refuses a relation result whose per-relation provenance is absent or the wrong length, and `R6` refuses a result that is not an `mvp-v0.1` normalized result at all. Where it cannot fail silently — a `limitations` entry that carried no kind — `evidence_entry_key` is `\N` under Section 4.7's own rule for an entry with no name, and no implementer is ever asked to invent a kind string, which would be a string in the document that Section 7's closed vocabulary does not admit.

**3. The reserved `evidence_` column prefix.** Section 4.5 gives every column this contract contributes the prefix `evidence_`, so that it cannot collide with a fact column. `mvp-v0.1` Section 4.4 fixes each registered template's allowed parameters, ordering, and row limit, and requires each to record its result column list; it does not fix what those column names may be. A template could therefore register a column named `evidence_route`, and a reader of the export could not tell the two apart. **This contract does not ask `mvp-v0.1` to reserve the prefix.** It requires the exporter to check the executing template's registered column list and to refuse the export when any name begins with `evidence_` (Section 4.9, `R2`). No ambiguous document is ever produced.

## 4. Normative requirements

### 4.1 What an export is

An export is a function of **two inputs and nothing else**: one `mvp-v0.1` normalized runtime result, and the **committed fixed SQL template registry**, read for one thing only — the registered result column list, in its registered order, of the template the result names. Given the same result against the same registry state it produces the same document set; given a result it refuses under Section 4.9 it produces nothing.

The registry is named as an input rather than smuggled in, because Section 4.5's fact block **is** that column list and three of the Section 4.9 refusals are predicates over it, while `mvp-v0.1` Section 7 puts no column list in the result. A contract that called the export a function of the result alone while requiring the column list would state two obligations no implementation could satisfy at once. The registry is a reviewed, committed, version-controlled artefact that `mvp-v0.1` Section 4.4 fixes, and it is read for column names only: never for SQL text, never to choose or execute a template, and never for a value that reaches a field.

Everything else stays out. The export opens no database connection, executes no SQL, and registers no template. It receives no request text, no adapter output, no fixture file, and no model output: every **value** it may put in a document is already in the result it was handed, plus the closed vocabulary Section 7 enumerates. This is not a convenience. It is what makes Charter Section 9's first Milestone 4 gate item — "exported values are derived from the normalized runtime result" — a property of the export's *inputs* rather than a claim about its behaviour, and it is the reason no export path can reach a fact the result does not carry.

An export takes no option, no profile, and no column selection. A caller who could choose which columns to export could choose to omit the evidence, and Charter Section 3.1 does not admit a factual result without its source scope, template identity, bound parameters, row count, source trace, and limitations.

### 4.2 The export document set

One export is **two TSV documents**:

| Document | One record per |
| --- | --- |
| `rows.tsv` | one row of the normalized result, or exactly one record when the result carries no rows |
| `evidence_entries.tsv` | one evidence item that is not representable as a column of `rows.tsv` |

**Both documents are always present**, and every document carries its header record first. A document with nothing to say carries its header record and no data records; it is never omitted and never empty. An absent document and a document with no records would be indistinguishable to a reader who received only one of them, and the second is the one that says "there were no limitations" rather than "the limitations were not exported".

The two file names are fixed. Where the set is written, how the two files travel together, and whether they are archived are not fixed here (Section 3.2).

### 4.3 The byte-level format

Both documents obey the same rules.

- **Encoding** is UTF-8 with no byte-order mark.
- A **field delimiter** is one U+0009 CHARACTER TABULATION. A **record delimiter** is one U+000A LINE FEED. There is no CR anywhere in either document, and the last record is followed by one LF.
- Every record carries **exactly the number of fields the header declares**, including trailing empty fields. A short record is not permitted.
- Within a field, exactly four escape sequences exist, and no others: `\\` for one U+005C REVERSE SOLIDUS, `\t` for one U+0009, `\n` for one U+000A, and `\r` for one U+000D. Decoding is their inverse. Because a literal backslash is always doubled, the encoding is unambiguous and **lossless**: decoding an exported field returns the original text byte for byte. Section 8 asserts that round trip rather than trusting it.
- An **absent value** is the two-character field `\N`. An **empty string** is a field of zero length. The two are different values and the format keeps them different: `\N` cannot arise from encoding any string, because a literal backslash would have been doubled.

An escape is an encoding, not a rendering: it changes how a value is written down and not what the value is, which is why it does not collide with the Charter's "may not add or alter facts". These conventions are those of PostgreSQL's `COPY … TEXT` format, cited as prior art rather than as authority; nothing here defers to that tool's behaviour, and the four sequences above are the whole set.

### 4.4 The text form of a value

| Value in the normalized result | Field |
| --- | --- |
| absent — a `None`, an unset optional structure, a fact column with a SQL null | `\N` |
| a text value, including the empty string | the text, escaped per Section 4.3 |
| a boolean | `true` or `false`, lower case |
| a number | the text the normalized result carries, at the precision stored in the schema |
| anything else the result carries in a row | its text form, escaped per Section 4.3 |

`mvp-v0.1` Section 6 forbids rounding in the runtime and the renderer; this contract forbids it in the export too, and forbids in addition any locale-dependent formatting — no grouping separator, no alternative decimal mark, no date or time reformatting, no unit suffix. A number that reaches the export as `0.10` is exported as `0.10`, not as `0.1`, because the trailing digit is stored precision and dropping it would alter a fact.

### 4.5 `rows.tsv`: the frozen column list

The columns are, in this order: the **evidence block**, then the **per-row provenance block**, then the **fact block**. Every column this contract contributes carries the prefix `evidence_`; no fact column may (Section 4.9, `R2`).

**The evidence block.** Twenty-two columns. **Columns 1 to 21 are identical on every record of one export**, because each describes the result rather than a row. **Column 22, `evidence_row_ordinal`, is the one per-record column of this block**; it sits here rather than in the provenance block because it is about the record itself rather than about a relation, and Section 4.6 says why it exists.

| # | Column | Derived from |
| --- | --- | --- |
| 1 | `evidence_export_contract_identifier` | this contract's identifier |
| 2 | `evidence_export_contract_version` | this contract's version |
| 3 | `evidence_result_contract_identifier` | `evidence_bundle.contract_identifier` |
| 4 | `evidence_result_contract_version` | `evidence_bundle.contract_version` |
| 5 | `evidence_status` | the result's status value |
| 6 | `evidence_route` | `evidence_bundle.route` |
| 7 | `evidence_template_name` | `evidence_bundle.template_name` |
| 8 | `evidence_template_version` | `evidence_bundle.template_version` |
| 9 | `evidence_row_count` | `evidence_bundle.row_count` |
| 10 | `evidence_resolved_project_code` | `evidence_bundle.resolved_scope`, or `\N` when it is empty |
| 11 | `evidence_resolved_revision_label` | as above |
| 12 | `evidence_resolved_network_name` | as above |
| 13 | `evidence_resolved_snapshot_label` | as above |
| 14 | `evidence_collation` | `evidence_bundle.collation` |
| 15 | `evidence_read_only_role_name` | `evidence_bundle.read_only_safeguards`, role name |
| 16 | `evidence_read_only_transaction` | as above, the read-only transaction flag |
| 17 | `evidence_connection_opened` | as above, whether a connection was opened |
| 18 | `evidence_producing_layer` | `source_trace.producing_layer`, or `\N` when it is empty |
| 19 | `evidence_entity_approval_reference` | the approved entity's approval reference that `entity-discovery-v0.1` Section 7 requires, or `\N` when the result carries none — which is every result that did not reach a fact route through that contract's Section 4.8 selection path |
| 20 | `evidence_limitation_count` | the number of entries in `limitations` |
| 21 | `evidence_entry_count` | the number of data records in `evidence_entries.tsv` |
| 22 | `evidence_row_ordinal` | see below |

Columns 7, 8, and 10 to 13 carry the **explicit empty value** `mvp-v0.1` Section 7 permits when no database was opened: the two text fields are the empty string, so they export as empty fields, and the four scope columns export as `\N`. That contract distinguishes the two; so does this one. **Those six are the only carve-outs from Section 4.4**, and they are carve-outs only because an accepted contract fixes the empty string as a value there. Column 19 is deliberately not one: an approval reference is an opaque citation that may itself be the empty string, so encoding "no selection path was taken" as an empty field would make it indistinguishable from an approving decision whose reference is empty — exactly the collapse Section 4.3 exists to prevent.

Columns 20 and 21 are counts, and they exist so that a reader who has `rows.tsv` and not its companion cannot conclude there was nothing to say. A non-zero `evidence_limitation_count` beside an unread `evidence_entries.tsv` is a visible gap; a silent omission is not. Section 4.9 requires both counts to agree with the companion document, and Section 8 asserts it.

`evidence_row_ordinal` is the **1-based position of this record's row in the normalized result's row order**, and it is `\N` on the single record of a result that carries no rows. It is the column that tells a reader whether a record is a row at all, and it preserves `mvp-v0.1` Section 6's ordering in a document that a consumer may sort.

**The per-row provenance block.** Twelve columns, from `source_trace.mapping_provenance` under the rule in Section 4.6.

| Columns | Derived from |
| --- | --- |
| `evidence_mapping_asserting_project_code`, `…_revision_label`, `…_network_name`, `…_snapshot_label` | the entry's asserting scope |
| `evidence_mapping_source_endpoint_project_code`, `…_revision_label`, `…_network_name`, `…_snapshot_label` | the entry's source endpoint scope |
| `evidence_mapping_target_endpoint_project_code`, `…_revision_label`, `…_network_name`, `…_snapshot_label` | the entry's target endpoint scope |

All twelve are `\N` on every record of a result whose `mapping_provenance` is empty — which, by `R3`, is never a result on the `signal_mapping` route that carries rows. The three scopes stay in three separate column groups rather than being merged, because `mvp-v0.1` Section 7 requires them "separately identified" and Charter Section 3.6 requires the asserting artifact's scope to travel with the relation rather than beside it.

**The fact block.** The **registered result column list of the template the result names, in its registered order**, with each field carrying that row's value for that column under Section 4.4. When no template executed — the outcomes `mvp-v0.1` Section 5 says open no connection — the block is empty and `rows.tsv` has exactly the thirty-four columns above.

**On the single record of a result that carries no rows, every fact-block field is `\N`**, which Section 4.3 keeps distinct from a zero-length field. Without that sentence two conforming implementations could differ on every rowless outcome, and Section 6's byte-identical promise would be weaker than it reads.

The fact block is frozen without being enumerated here, and that is deliberate: `mvp-v0.1` Section 4.4 requires every registered template to record its result column list in order, so the list is already fixed by a registration this contract must not duplicate. A second copy here would be a second place to change, and the copy that drifted would be the one a conformance check compared against. What this contract fixes is that the block **is** that list, in that order, in full, with nothing added, nothing dropped, and nothing reordered.

### 4.6 The row granularity of evidence

**Every record of `rows.tsv` carries the evidence block.** The repetition is the point: the exported artefact is a rectangle that a reader may filter, sort, or split, and a row that travelled without its source scope, its template identity, and its status would be a fact with no evidence attached — the one thing Charter Section 3.1 forbids. Repetition costs bytes and buys the property that no single row of an export is ever evidence-free.

**A record's per-row provenance block is the provenance of that record's own row.** Where `source_trace.mapping_provenance` is non-empty, the record whose `evidence_row_ordinal` is *n* carries the *n*-th entry of that tuple. That correspondence is not promised by `mvp-v0.1` (Section 3.3, extension 1), so the export establishes what it can and refuses what it cannot: `R3` requires the length of `mapping_provenance` to equal the number of rows — on the `signal_mapping` route including the case where it is zero and rows are present — and refuses the whole export otherwise. A relation's provenance is never attached to a row by guess, and a relation never travels without one.

**Recorded decision.** The repository owner decided on 2026-09-14, on [#68](https://github.com/OKJ1105/evidence-first-rag/issues/68), that the Milestone 4 TSV export carries evidence columns rather than facts alone; the queue put the question as evidence columns with "`source_trace` per row". That decision is the premise of this section and is not reopened by it. What the decision leaves to this contract is what "per row" means for each field, and this section answers it in three parts: the result-level evidence repeats on every record, the mapping provenance goes on the row it describes, and the evidence that is neither — a list or a mapping of its own — goes to Section 4.7 rather than being packed into a field.

The declined alternative is recorded beside it. **A single evidence record per export, joined to the rows by a key**, is smaller and would have been defensible for a machine consumer. It was not adopted because it makes an evidence-free row representable: a reader who opens, filters, or copies `rows.tsv` alone holds facts with no scope and no template, and the failure is silent. The owner's decision is for evidence columns, and a join key is not a column of evidence.

### 4.7 `evidence_entries.tsv`: the evidence a rectangle cannot hold as columns

`bound_parameters` is a mapping whose keys vary per route. `limitations` is a list whose length varies per result. The contributing scopes, the fixture provenance, the alias provenance, and the `selection` record are lists or mappings too. None of them is a fixed set of columns, and the two ways of forcing them into one — packing several values into one field, or adding a column per possible key — each break something. Packing puts a second format inside a field, so a reader needs a parser for it and a mis-parse silently changes what a limitation says. A column per possible key is not a frozen column list at all.

So they are exported **long** instead of wide: one record per item, four columns.

| Column | Meaning |
| --- | --- |
| `evidence_entry_group` | which structure this entry came from, from the closed set below |
| `evidence_entry_ordinal` | the 0-based position of the entry within its group |
| `evidence_entry_key` | the name within the entry, or `\N` when the entry has no name |
| `evidence_entry_value` | the value, under Section 4.4 |

The groups are closed. A structure not in this table is not exported here, and adding a row to it is a minor version under Section 10.

| `evidence_entry_group` | Source | One entry is | `evidence_entry_key` | Record order |
| --- | --- | --- | --- | --- |
| `bound_parameters` | `evidence_bundle.bound_parameters` | one bound parameter | the parameter name | by parameter name, byte-wise ascending |
| `limitations` | `limitations` | one limitation | the limitation's kind | the list's own order |
| `contributing_scopes` | `source_trace.contributing_scopes` | one scope dimension of one scope | the dimension name | the tuple's order, then `project_code`, `revision_label`, `network_name`, `snapshot_label` |
| `fixture_provenance` | `source_trace.fixture_provenance` | one provenance string | `\N` | the tuple's order |
| `alias_provenance` | `source_trace.alias_provenance` | one key of one alias record | that record's key | the tuple's order, then key byte-wise ascending |
| `selection` | `evidence_bundle.selection` | one key of the record | that record's key | key byte-wise ascending |

`evidence_entry_ordinal` counts **entries**, not records: for `contributing_scopes` it is the position of the scope, so four records share an ordinal and are told apart by their dimension name; for `alias_provenance` it is the position of the alias record; for `selection`, which is at most one record, it is always `0`.

Two details follow from the contracts rather than from taste. The `limitations` group puts the **kind** in the key and the **detail** in the value, because `mvp-v0.1` Section 7's list is a list of conditions each with something to say, and splitting a limitation across two records would let one of them be read without the other. The `selection` group flattens the one nested mapping `entity-discovery-v0.1` Section 4.8 puts inside the record — the step-2 re-run's bound parameters — as the key `discovery_bound_parameters.<name>`, one record per parameter; the dot is unambiguous because those names are allowlisted parameter names, which carry none.

This contract does **not** restate the key set of the `selection` record or of an alias provenance entry. `entity-discovery-v0.1` Section 4.8 calls its list "the authoritative key set for a dispatched selection", and a second copy here would be a second thing to change. The export carries whatever keys the record carries, in the order this table fixes.

Byte-wise ascending order is `mvp-v0.1` Section 6's `C` collation, named so that no locale can reorder an export.

### 4.8 What the export never does

Each line below is a consequence of an obligation above or of an inherited one, stated as a boundary so that a conformance check has one assertion per line.

- It opens no database connection, executes no SQL, and reaches no fixture file or model. Its one registry read is the registered result column list of the template the result names (Section 4.1), for column names only.
- It adds no fact, no qualifier, and no inference. Every field is a value from the normalized result or a member of the closed vocabulary Section 7 enumerates.
- It drops nothing. Every key `mvp-v0.1` Section 7 requires, and every key `entity-discovery-v0.1` Section 7 adds, appears in the column or entry group Section 7 below names for it.
- It reorders nothing. Row order is the result's; column order and record order are this contract's.
- It does not round, reformat, localize, or truncate a value.
- It exports no surrogate key. It exports what the result carries, and `mvp-v0.1` Section 4.2 keeps surrogate keys out of every public payload, so this follows rather than being a new rule.
- It carries no clock, no counter, no randomness, and no run identifier, which is what Section 6 rests on.
- It does not replace `mvp-v0.1` Section 4.8 rendering, does not consume its output, and does not put rendered prose in a document.
- It produces no partial document set (Section 4.9).

### 4.9 Refusals

An export **refuses** when any condition below holds. A refusal produces **no document at all** — not a partial `rows.tsv`, not a header-only pair, and not a document with a note in it. This is the export's fail-closed behaviour and it mirrors `mvp-v0.1` Section 4.11's loader, which either loads every row of every file or leaves the database absent.

| | Condition | Why it cannot be exported |
| --- | --- | --- |
| `R1` | `template_name` is non-empty and the pair (`template_name`, `template_version`) names no registered template; **or** `template_name` is non-empty while `read_only_safeguards` reports that no connection was opened | The fact block is that template's registered result column list. With no registered template there is no column list, and inventing one would put a column name in the document that no registration fixed. The second half is a result that contradicts itself — `mvp-v0.1` Section 7 makes `template_name` empty whenever no database was opened — and the two halves of Section 4.5 would give an exporter incompatible instructions about whether the fact block exists. |
| `R2` | Any name in that template's registered result column list begins with `evidence_` | The two blocks would collide and a reader could not tell a fact column from an evidence column (Section 3.3, extension 3). |
| `R3` | `evidence_bundle.route` is `signal_mapping` and the length of `source_trace.mapping_provenance` differs from the number of rows — **including a length of zero while rows are present**; or, on any other route, `mapping_provenance` is non-empty and its length differs from the number of rows | The per-row correspondence Section 4.6 needs cannot be established, and attaching a relation's provenance to another relation's row would be a false statement about where a fact came from (Section 3.3, extension 1). Stated over the route rather than only over a non-empty tuple, because a relation route that carried rows and no provenance at all would otherwise export relation records whose asserting scope is absent — the scope Charter Section 3.6 requires to travel with each relation — and it would do so silently, while a length of 1 against 2 rows refused the whole export. |
| `R4` | That column list contains the same name twice | A reader cannot address either column, and a consumer that reads by name would silently take one of the two. |
| `R5a` | `evidence_limitation_count` would not equal the number of **`limitations`-group** data records in `evidence_entries.tsv` | The count exists to make a missing companion visible (Section 4.5). A count that does not count is worse than no count. |
| `R5b` | `evidence_entry_count` would not equal the **total** number of data records in `evidence_entries.tsv` | As above, for the companion as a whole. |
| `R6` | The result is not an `mvp-v0.1` normalized result, or its `route` is not one of the three `mvp-v0.1` Section 4.5 fact routes | See below. |

`R5a` and `R5b` are two comparisons, not one, and separating them matters: on a conforming export of a result that binds parameters and records no limitation, the limitation count is zero while the companion holds records, and a single condition over "the number of records the companion document holds" would refuse almost every export this contract exists to produce.

**`R6` is the boundary of Section 3.2 made enforceable.** A discovery-layer result of [entity-discovery-v0.1](entity-discovery-v0.1.md) Section 5 is a different shape: its own status vocabulary — which has `resolved` and `candidates` and has no `success` — its own evidence keys (`registry_digest`, `registry_built_at`, `method_identifier`, `method_version`, and on a refused selection the cited `candidate_set_id`, `selected_rank` and `target_route`), and candidates where an `mvp-v0.1` result has rows. **None of those keys has a column or an entry group here**, so exporting such a result under this contract would silently drop evidence that contract requires on every result — which Section 4.8's "It drops nothing" forbids. Refusing is the fail-closed answer, and Section 9 names the later slice that owns the discovery-layer export. A **dispatched** selection is unaffected and exports normally: `entity-discovery-v0.1` Section 4.8 makes it the `mvp-v0.1` result of its `target_route`, whose `route` is one of the three fact routes and whose one added key, the `selection` record, has an entry group here.

A refusal is not a status family, and it is not a result: see Section 5. `R5a` and `R5b` are self-checks on the export's own output rather than properties of the result, and they are listed with the others because the consequence is the same — nothing is written.

## 5. Outcome coverage

**This contract produces no status family, and that is not an omitted section.**

[Contract Shape Framework](README.md) Section 3 requires every contract to state every status family it can produce and the condition that produces each. The status families of `mvp-v0.1` Section 5 and of `entity-discovery-v0.1` Section 5 are produced by a *runtime that validates a request and may reach a database*. An export validates no request and reaches no database (Section 4.1); its one registry read is a column list, not a judgement. It is handed a result that already carries its status, and it carries that status through to `evidence_status` without judging, changing, or adding to it.

| The export is handed | It produces |
| --- | --- |
| an `mvp-v0.1` normalized result of any of the seven `mvp-v0.1` Section 5 statuses, on one of the three Section 4.5 fact routes — including a `success` reached through the `entity-discovery-v0.1` Section 4.8 selection path, which is an `mvp-v0.1` result of its `target_route` | a document set whose `evidence_status` is that status, whose rows are that result's rows, and whose evidence is that result's evidence |
| a discovery-layer result of `entity-discovery-v0.1` Section 5, or any result on a route outside those three | nothing at all — `R6`, for the reason Section 4.9 gives |
| a result that meets a Section 4.9 refusal condition | nothing at all |

**An `ambiguous` outcome's records are candidate scopes, not facts.** `mvp-v0.1` Section 4.4 makes `TPL_SNAPSHOT_CANDIDATES_V1` the template that runs, and it "returns scope columns only", so the fact block of such an export is that template's registered scope columns and each record is a candidate scope the runtime declined to choose between. What keeps a reader from taking one for a returned fact is `evidence_status`, which carries `ambiguous` on **every** record, together with the `limitations` entries the outcome requires — the same distinction Section 3.2 relies on when it declines candidate-list export, made explicit here because this is the one place where a non-fact record does appear in the fact block.

**Every negative outcome exports.** A `not_found`, a `coverage_gap`, an `ambiguous`, an `invalid_request`, an `unsupported`, and a `needs_entity_discovery` each produce a full document set: the evidence block, the single record whose `evidence_row_ordinal` is `\N` where the result carries no rows, and the `limitations` entries that `mvp-v0.1` Section 7 requires of that outcome. A negative outcome that exported as an empty file, or did not export at all, would let a reader take an absent document for an absent answer. Charter Section 9's third Milestone 4 gate item asks for workflows that complete "with traceable failures", and a failure is traceable here because it exports exactly as fully as a success does.

**A refusal is not a status.** It is the absence of an artefact, and it is reported to whatever invoked the export rather than written into a document — a document that described its own refusal would be an export of something that is not a normalized result. How a refusal is surfaced to a caller belongs to the Milestone 4 API contract (Section 3.2).

## 6. Determinism

- **Exporting the same normalized result twice, against the same registry state, produces byte-identical documents.** There is nothing to exclude from the comparison: no run identifier, no timestamp, no path, no counter, and no randomness enters either document. `mvp-v0.1` Section 4.9 has to exclude two fields from its artifact comparison because a conformance run records when it ran; an export records nothing about itself, so its comparison is total.
- **Column order** is fixed by Section 4.5 and, for the fact block, by the template's registered result column list. No implementation chooses it and no caller influences it.
- **Record order in `rows.tsv`** is the normalized result's row order, which `mvp-v0.1` Section 6 already makes total and reproducible. `evidence_row_ordinal` is 1-based and strictly increasing, so the order survives a consumer that sorts the file.
- **Record order in `evidence_entries.tsv`** is the group order of Section 4.7's table, then within each group the order that table fixes. Every ordering there is total: a list's own order, or byte-wise ascending over keys that are unique within their mapping.
- **Byte-wise ordering** is `mvp-v0.1` Section 6's `C` collation. It is named rather than left to a default so that an export produced on one machine is byte-identical to one produced on another.
- **No value is reformatted** (Section 4.4), so two exports of one result cannot differ by a locale, a floating-point printer, or a rounding mode.
- Determinism is a property of the export alone. The export makes no claim about whether two *runtime executions* produce the same result; that is `mvp-v0.1` Section 6's, and this contract inherits it without extending it.

## 7. Evidence obligations

The export produces no `evidence_bundle`, `source_trace`, or `limitations` of its own: it is a projection of the three structures the result already carries. Its obligation is therefore stated in both directions — **nothing is dropped, and nothing is added** — and both directions are checkable.

**Nothing is dropped.** Every key below appears in the named column or entry group of every export.

| Structure and key | Where it lands |
| --- | --- |
| `evidence_bundle.contract_identifier`, `contract_version` | columns 3 and 4 |
| `evidence_bundle.route` | column 6 |
| `evidence_bundle.template_name`, `template_version` | columns 7 and 8 |
| `evidence_bundle.bound_parameters` | entry group `bound_parameters` |
| `evidence_bundle.row_count` | column 9 |
| `evidence_bundle.resolved_scope` | columns 10 to 13 |
| `evidence_bundle.collation` | column 14 |
| `evidence_bundle.read_only_safeguards` | columns 15 to 17 |
| `evidence_bundle.selection` (`entity-discovery-v0.1` Section 3.3, extension 3) | entry group `selection` |
| `source_trace`, the scope of every snapshot that contributed a row | entry group `contributing_scopes` |
| `source_trace`, the asserting and both endpoint scopes of a mapping result | the twelve per-row provenance columns |
| `source_trace.producing_layer` | column 18 |
| `source_trace.fixture_provenance` | entry group `fixture_provenance` |
| `source_trace`, alias provenance (`entity-discovery-v0.1` Section 7) | entry group `alias_provenance` |
| `source_trace`, the approved entity's approval reference (`entity-discovery-v0.1` Section 7) | column 19 |
| `limitations`, every entry, with its kind and its detail | entry group `limitations` |
| the result's status (`mvp-v0.1` Section 5) | column 5 |
| the result's rows | the fact block, and `evidence_row_ordinal` |

**Nothing is added.** Every byte of both documents is either a value from the normalized result, encoded under Sections 4.3 and 4.4, or a member of this closed vocabulary:

1. the column names of Section 4.5 and Section 4.7, in the header records;
2. the field and record delimiters, and the four escape sequences of Section 4.3;
3. the absent-value field `\N`;
4. the boolean tokens `true` and `false`;
5. the six `evidence_entry_group` names of Section 4.7;
6. the four scope dimension names `project_code`, `revision_label`, `network_name`, `snapshot_label`, as `evidence_entry_key` values in the `contributing_scopes` group — registered vocabulary from `mvp-v0.1` Section 4.2, not new coinage here;
7. the key prefix `discovery_bound_parameters.` of Section 4.7;
8. the decimal digits of the four values this contract derives rather than copies: `evidence_row_ordinal`, `evidence_entry_ordinal`, `evidence_limitation_count`, and `evidence_entry_count`;
9. the two values that identify this contract: `export-v0.1` and this document's version, in columns 1 and 2;
10. the registered result column names of the executing template, in the header record of `rows.tsv` — read from the committed registry named as an input in Section 4.1, and fixed there by `mvp-v0.1` Section 4.4 rather than chosen here.

Items 8, 9 and 10 are the whole of what an export contributes that the normalized result does not contain. The counts and the two ordinals are **derived** from the result and add no fact — an ordinal restates an order the result or this contract already fixes, and a count restates a length. The two contract-identity values name the document format a reader is holding, which is what lets a reader check the rest of this list. Item 10 is a reviewed registration, not a choice made at export time. None of the three is a fact about the data. Enumerating them exhaustively is the checkable form of Charter Section 9's second Milestone 4 gate item, "rendering does not add or alter facts": an export containing an eleventh kind of string fails the check.

**Information safety.** Nothing in an export names a credential, a connection string, a host, a local path, or a person. `evidence_read_only_role_name` is the runtime role name, which `mvp-v0.1` Section 7 already requires in every evidence bundle, so exporting it exposes nothing the result did not already carry; the export adds no field of its own that could. Fixture provenance names the registered fixture inputs of `mvp-v0.1` Section 4.11 and never a raw source-format artefact, because [ADR-0001](../adr/0001-postgresql-runtime-and-normalized-fixture-boundary.md) says none exists in this repository.

## 8. Acceptance evidence

Each obligation is either an automated assertion over registered inputs or a recorded human decision with named evidence, as [Project Charter](../PROJECT_CHARTER.md) Section 9 requires.

**The three rows marked `G1`, `G2`, and `G3` are the three Milestone 4 acceptance gate items of Charter Section 9, one to one.** They are marked so that a reader can see which evidence discharges the gate and which discharges an obligation of this contract alone. All three gate items are non-numeric, so **this contract registers no threshold and records no `registered_at`.** Charter Section 9's rule that a threshold is registered before the run it judges has nothing to order here, and a number introduced into this contract would be scope the Charter does not ask for.

| Obligation | Acceptance evidence |
| --- | --- |
| **`G1`** — "exported values are derived from the normalized runtime result" | **Automated.** Over every fixture in Section 8.1, in both directions: every field of both documents, decoded under Section 4.3, is either the value Section 7's table derives it from or a member of Section 7's closed vocabulary; **and** every key in Section 7's first table is present in the column or entry group named for it. The second direction is not optional — a one-sided check is satisfied by an export that drops every limitation. |
| **`G2`** — "rendering does not add or alter facts" | **Automated**, as two assertions rather than one. **Per export:** every string in both documents that is not derived from the result is a member of Section 7's closed vocabulary — a containment, because no single export exercises every member (a result that reached no selection path emits no `selection` group name). **Across the Section 8.1 set as a whole:** every member of the closed vocabulary appears in at least one export, so a vocabulary item that nothing produces is caught rather than carried. Additionally, over the Section 8.1 fixtures, changing one value in the normalized result changes the export, and changing nothing changes nothing; and the Section 4.8 boundary lines are asserted one per line, including that no export path opens a connection or reads a fixture file. |
| **`G3`** — "representative workflows complete end to end with traceable failures" | **Automated**, for the export half. Every status family of `mvp-v0.1` Section 5 has a fixture in Section 8.1, and each asserts a full document set: the evidence block present, `evidence_status` carrying that status, the `limitations` entries that outcome requires present in `evidence_entries.tsv`, and the producing layer present for `unsupported`. The workflow half of this gate item — that a request reaches a result end to end — is the Milestone 4 API contract's and is recorded in Section 9. |
| Section 4.1 the export's inputs | Automated. An export path is asserted to reach no database connection, no fixture file and no model, to take no caller option that could omit a column, and to read the committed template registry for a registered result column list only — never for SQL text, never to execute a template, and never for a value that reaches a field. |
| Section 4.2 the document set | Automated. Both documents are produced for every Section 8.1 fixture, each with its header record, including the fixtures whose companion holds no data record. |
| Section 4.3 the byte-level format | Automated. `EX-013` asserts the lossless round trip for a value containing a tab, a line feed, a carriage return, and a backslash; `EX-014` asserts that `\N` and a zero-length field are distinguishable; every fixture asserts the field count per record, the absence of CR outside an escape, and the trailing LF. |
| Section 4.4 the text form of a value | Automated. A value table at unit level covering absent, empty string, text, both booleans, and a number whose stored precision carries a trailing zero, which must not be dropped. |
| Section 4.5 the frozen column list | Automated. The header of `rows.tsv` equals the thirty-four names in their fixed order followed by the executing template's registered result column list in its registered order, compared against the registry rather than against a copy. |
| Section 4.6 row granularity | Automated. `EX-003` asserts that two rows of one mapping result carry different per-row provenance, columns 1 to 21 identical, and `evidence_row_ordinal` `1` and `2`; `EX-005` asserts the single `\N`-ordinal record of a rowless outcome. |
| Section 4.6 the granularity decision | **Recorded human decision — discharged.** The repository owner decided on 2026-09-14 that the export carries evidence columns; the declined alternative is recorded beside it in Section 4.6. The operative record is the owner's on this contract's own pull request, per [Contract Shape Framework](README.md) Section 6 step 4. |
| Section 4.7 the long form | Automated. Each group's record order, key, and ordinal rule is asserted; `EX-012` asserts the `selection` group including a flattened `discovery_bound_parameters.<name>` key; a test asserts that no group outside the closed set appears. |
| Section 4.8 boundaries | Automated, with `G2`. |
| Section 4.9 refusals | Automated. `EX-015` registers all seven conditions — `R1` in both its halves, `R2`, `R3` in both its halves, `R4`, `R5a`, `R5b`, `R6` — each asserting that **no document is written at all**. Each must be shown to fail against an export from which that refusal has been removed, per [#17](https://github.com/OKJ1105/evidence-first-rag/issues/17) rule 9 — a refusal never seen to fire is not evidence. |
| Section 5 outcome coverage | Automated, with `G3`. |
| Section 6 determinism | Automated. Two exports of the same normalized result compare byte-identical with nothing excluded; a second export in a different process and locale environment compares equal to the first. |
| Section 7 evidence obligations | Automated, with `G1` and `G2`. The two directions of Section 7 are exactly those two rows. |
| Section 7 information safety | Automated. The repository's sensitive-string scan covers any committed export; every identifier in every Section 8.1 fixture is `SAMPLE_*`. |
| Section 3.3 extension 1, the row-to-provenance correspondence | **Recorded human decision**, recorded in Section 9: whether `mvp-v0.1` is patched to state it. The refusal that makes implementation independent of the answer is asserted by the Section 4.9 row (`R3`). |
| Section 3.3 extension 2, the `source_trace` member names and the `limitations` entry shape | **Recorded human decision**, recorded in Section 9: whether `mvp-v0.1` Section 7 is patched to name them. Automated for the part that can fail silently — the Section 4.9 rows (`R3`, `R6`) — and for the `\N` key of a limitation entry carrying no kind. |
| Section 3.3 extension 3, the reserved `evidence_` prefix | **Recorded human decision**, recorded in Section 9: whether `mvp-v0.1` Section 4.4 is patched to reserve it. The refusal is asserted by the Section 4.9 row (`R2`). |

### 8.1 Required export fixture cases

Every fixture uses `SAMPLE_*` identifiers only. Every status family of `mvp-v0.1` Section 5 has at least one case. A case that names a registered `FX-*` or `DX-*` result exports that result, so that this contract registers no new runtime fixture and reaches no file outside its own tree; the four that name none are constructed results, for the reason stated under the table.

| ID | Case | What the export must show |
| --- | --- | --- |
| `EX-001` | `message_facts` success (`FX-001`) | one row record, ordinal `1`, the fact block equal to the registered column list, the twelve provenance columns `\N`, column 19 `\N`, and `evidence_limitation_count` `0` beside a companion that holds records |
| `EX-002` | `signal_facts` success (`FX-002`) | as above for the signal template, and the parent message key present in the fact block |
| `EX-003` | `signal_mapping` success returning more than one row (`FX-003`) | one record per relation, per-row provenance differing between records, columns 1 to 21 identical on both, `evidence_row_ordinal` `1` and `2` |
| `EX-004` | mapping asserted by a superseded snapshot (`FX-104`) | `evidence_status` `success`, a `limitations` entry of kind `superseded_snapshot` naming the superseding snapshot, `evidence_limitation_count` `1` |
| `EX-005` | lookup key absent from a resolved, covered snapshot (`FX-107`) | `evidence_row_count` `0`, exactly one record, `evidence_row_ordinal` `\N`, the fact block present and every fact field `\N` |
| `EX-006` | scope names a network no snapshot has (`FX-106`) | `evidence_status` `coverage_gap` and a `coverage_not_established` limitation entry stating what could not be established |
| `EX-007` | scope omitted, two candidate snapshots match (`FX-105`) | the candidate scopes exported as rows of the candidate template's registered columns, one record each |
| `EX-008` | parameter outside the route allowlist (`FX-109`) | no connection opened, `evidence_template_name` and `evidence_template_version` empty fields, the four resolved-scope columns `\N`, the fact block absent so that `rows.tsv` has exactly thirty-four columns, and the `bound_parameters` group empty |
| `EX-009` | request outside the approved routes (`FX-108`) | `evidence_producing_layer` carrying the producing layer |
| `EX-010` | route determined, no canonical reference formable (`FX-111`) | `evidence_status` `needs_entity_discovery` and its required limitation entry, no connection opened |
| `EX-011` | a constructed normalized result truncated by a registered row limit | a `truncated_by_limit` limitation entry, and `evidence_row_count` beside the number of exported records |
| `EX-012` | a fact result reached through the `entity-discovery-v0.1` Section 4.8 selection path (`DX-017`) | the `selection` group present with a flattened `discovery_bound_parameters.<name>` key, the alias provenance group present, `evidence_entity_approval_reference` non-empty, and the selection `limitations` entry present |
| `EX-013` | a constructed normalized result carrying a tab, a line feed, a carriage return, and a backslash in one text value | every record has the declared field count, and decoding the field returns the original text byte for byte |
| `EX-014` | a constructed normalized result carrying an empty-string value beside a null value in the same row | the first exports as a zero-length field and the second as `\N`, and the two are distinguishable |
| `EX-015` | the seven Section 4.9 refusal conditions, one constructed input each — including a `signal_mapping` result carrying rows and an empty `mapping_provenance` (`R3`), a result naming a template while reporting no connection (`R1`), and a discovery-layer result and a refused selection (`R6`) | no document is written at all, in each of the seven |

`EX-011`, `EX-013`, `EX-014`, and `EX-015` are constructed inputs rather than database fixtures, and are named as such. `EX-015`'s `R6` cases are the exception within the exception: a discovery-layer result and a refused selection are ordinary outputs of the `entity-discovery-v0.1` runtime, so those two are taken from its registered `DX-*` cases rather than constructed. The registered fixtures are ASCII `SAMPLE_*` identifiers by `mvp-v0.1` Section 4.11, so no loaded row can carry a tab or a backslash; `mvp-v0.1` Section 8.1 registers no case that reaches a registered row limit, and its two fact templates treat their limit as an overflow detector rather than a truncation (Section 4.4), so no registered fixture truncates; and none of the seven refusal conditions is reachable from a conforming runtime and registry. Registering them as database fixtures would mean adding fixture rows whose only purpose is to be malformed or to overflow a limit, or registering a template that violates `mvp-v0.1` Section 4.4 — none of which this contract may do. Constructing the result is the honest way to reach the path; the alternative is a refusal that is never seen to fire, which [#17](https://github.com/OKJ1105/evidence-first-rag/issues/17) rule 9 says is not evidence.

### 8.2 Deferral of the acceptance evidence

Section 10 permits this contract to be accepted with its acceptance evidence explicitly deferred with a named owner. Every **Automated** row of the Section 8 table is deferred on that basis, and this section is the record.

The deferral is structural, not a concession. Each of those rows is an assertion over an export that does not exist: on the date this contract is accepted the repository holds no exporter, no export fixture, and no export document. Requiring the evidence before acceptance would make acceptance unreachable, because [Contract Shape Framework](README.md) Section 2.1 forbids implementing against a contract that is not accepted. The order is therefore contract first, evidence with the implementation the contract governs — the order `mvp-v0.1` Section 8.2 and `entity-discovery-v0.1` Section 8.2 both record.

Named owner: the repository owner. Nothing here is delegated to an AI writer or reviewer.

| Class | Discharged |
| --- | --- |
| Every row marked **Automated**, including `G1`, `G2`, and `G3` | On the implementation pull request that introduces the behaviour that row governs. Its assertions are a merge condition for that pull request. A pull request that implements a behaviour without them is incomplete, not deferred again. |
| Section 4.6, the granularity decision | Already discharged. Recorded by the repository owner on 2026-09-14 and restated in Section 4.6. |
| Section 3.3 extensions 1 and 2 | At the owner's convenience, under `mvp-v0.1` Section 10. Implementation of this contract depends on neither; each is a refusal here either way. |

This deferral does not weaken any obligation, and Section 10 forbids using it to. No implementation pull request may cite this section as a reason to omit the evidence its own slice owes.

**There is no Section 8.3 in this contract, and its absence is deliberate.** `mvp-v0.1` and `entity-discovery-v0.1` each carry one because Charter Section 9 gives their milestones numeric adoption thresholds that must be registered before the run that judges them. Charter Section 9's Milestone 4 gate has three items and no number in any of them. A registration section here would have to invent a quantity the Charter does not ask for, and pre-registering an invented bar is worse than not registering one: it would look like a gate.

## 9. Deferred decisions

Each decision this contract leaves open, with the named later slice that owns it.

| Decision | Owner |
| --- | --- |
| The route, request, and response shape of the surface that *serves* an export, and how a Section 4.9 refusal reaches a caller | **Milestone 4 API contract**, the other half of Charter Section 9's Milestone 4 deliverables. [Contract Shape Framework](README.md) Section 8 already names it for "route and result schemas for the post-Milestone 1 API". |
| The workflow half of Charter Section 9's third Milestone 4 gate item — that a request or a candidate selection reaches a result end to end | **Milestone 4 API contract**, with the end-to-end task fixtures Charter Section 9 lists beside it. Section 8's `G3` row covers the export half only, and says so. |
| Export of a **discovery-layer result** of `entity-discovery-v0.1` — every outcome of its Section 5, including a refused selection, not only `candidates` and `resolved` | A **later minor version of this contract**, as the Milestone 4 discovery-export slice. Refused here rather than partly supported: `R6` produces no document at all, because none of the evidence keys that contract requires on every discovery result has a column or an entry group in this one, and exporting such a result would drop them silently. Deferred rather than guessed: a candidate is not a row a fact template returned, its columns are the Section 4.6 candidate fields of that contract, and putting candidate records beside fact records in one rectangle would let a reader take a candidate list for an answer — which `entity-discovery-v0.1` Section 5 exists to prevent. `entity-discovery-v0.1` Section 9 already names "any export of a candidate list" as a Milestone 4 contract's. |
| Multi-result export: one document set describing a whole workflow rather than one result | A **later minor version of this contract**. It needs a per-result key in every record and a rule for a set whose results executed different templates, and neither follows from anything decided here. |
| A stable identifier or digest for one export | **Not opened.** Deliberately not introduced at `0.1.0`: an identifier would be a value in the document that the normalized result does not contain, and Section 7's closed vocabulary is the check that would have to be widened to admit it. The later slice that needs to name one export among many owns it, and multi-result export is the first candidate. |
| Where an export is written, how it is named outside a document set, retention, and archiving or compression | **Milestone 4 API contract** for the served path; **Milestone 5 deployment contract** for anything an environment decides. Not a property of the document. |
| Any export format other than TSV | **Not opened.** Charter Section 9 names TSV. Opening another format is new scope under Charter Section 10 and is not a contract-level change this document may make. |
| The minimal UI of Charter Section 9's fourth Milestone 4 deliverable — and whether it is built at all, which that deliverable makes conditional | **Not this contract's.** Charter Section 9 admits it "only if it materially supports evaluation or use", which is a judgement about use rather than a contract decision. |
| Whether `mvp-v0.1` Section 7 is patched to state that the *n*-th `mapping_provenance` entry describes the *n*-th row (Section 3.3, extension 1) | The **repository owner**, under `mvp-v0.1` Section 10. Implementation does not depend on the answer: Section 4.9 `R3` refuses rather than assumes, either way. |
| Whether `mvp-v0.1` Section 7 is patched to name the `source_trace` members and the `kind`/`detail` shape of a `limitations` entry that this contract reads from its prose bullets (Section 3.3, extension 2) | The **repository owner**, under `mvp-v0.1` Section 10. Implementation does not depend on the answer: `R3` and `R6` refuse where the reading could fail silently, and Section 4.7's `\N` rule covers the rest. |
| Whether `mvp-v0.1` Section 4.4 is patched to reserve the `evidence_` prefix in a registered result column list (Section 3.3, extension 3) | The **repository owner**, under `mvp-v0.1` Section 10. Implementation does not depend on the answer: Section 4.9 `R2` refuses rather than assumes, either way. |

No row above is open in the sense that this contract needs it to be implementable. Sections 4.1 through 4.9 are complete as they stand: every row either belongs to another document, is new scope the Charter has not opened, or is a question whose two answers this contract already behaves identically under.

## 10. Change control

- This contract is `Proposed`. Under [Contract Shape Framework](README.md) Section 7 it is amended by an ordinary contract-only pull request while it stays in that state. That looser rule stops applying the moment it is `Accepted`.
- **This contract may not move to `Accepted`** until the repository owner records the review required by [Contract Shape Framework](README.md) Section 6 step 4, **and** the Section 8 acceptance evidence is either satisfied or explicitly deferred with a named owner. The deferral, with its named owner and the point at which each obligation is discharged, is in Section 8.2; the review is the owner's and has not happened. The rule is written here rather than assumed so that the acceptance record stays interpretable afterwards, as `mvp-v0.1` Section 10 and `entity-discovery-v0.1` Section 10 each retain their own.
- After acceptance, a change that does not weaken a Charter or ADR invariant produces a new version with a recorded human decision. **Adding or removing a column, a document, an `evidence_entry_group`, or a refusal condition is a minor version and requires a fresh independent design review.** Adding a fixture case that exercises an existing obligation is a patch version.
- **Removing or weakening an obligation is not permitted at this layer.** A change that would weaken a Charter or ADR invariant requires an architecture decision recorded in an ADR, a Charter update where the change materially changes the Charter, and a recorded human decision.
- Two changes are named because they are the ones an implementer will reach for. **Making any column optional, or admitting a caller-chosen column set, weakens Charter Section 3.1** — a factual result exported without its source scope, template identity, bound parameters, row count, source trace, or limitations is a fact without evidence — and is therefore not a contract-level change at all. **Packing a list into one field**, rather than exporting it long under Section 4.7, would put a second format inside a field and is a minor version at best, never an implementation detail.
- **This contract amends nothing in `mvp-v0.1` or in `entity-discovery-v0.1`.** Where it reads either closely, Section 3.3 records it and Section 9 carries the owner's decision on whether that contract is patched to state it. A change here that would require a change there is an amendment to that contract under its own Section 10, and is the repository owner's to record.
- A superseded version is retained with a `Superseded by` status rather than deleted, so that a past acceptance record stays interpretable.
