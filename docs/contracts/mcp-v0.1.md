# MCP Surface Contract v0.1

## 1. Identifier and version

**Identifier:** `mcp-v0.1`

**Version:** `0.2.0` — the identifier names the document; the version tracks its obligations. `0.1.0` is the version at which it was accepted. `0.2.0` changes the fixed `discover_entity` description (Section 4.4) and `MC-020` to match `entity-discovery-v0.1` `0.4.0`, under which a discovery request with a missing scope value searches each candidate snapshot, up to ten, and lists only those in which the term was found ([#314](https://github.com/OKJ1105/evidence-first-rag/issues/314)). It removes no obligation: every instruction in the description stands, and two are added: the scope of the search, and what the host does with an `ambiguous` result. `0.1.1` closes the Section 9 row on retiring `/v1/ask` and corrects Section 3.2 to match, on the repository owner's decisions on [#203](https://github.com/OKJ1105/evidence-first-rag/issues/203#issuecomment-5827589592) and [#204's review](https://github.com/OKJ1105/evidence-first-rag/issues/203#issuecomment-5827797082); **no obligation in Section 4, 5, 6 or 7 changed.** The version changes when any observable obligation in Section 4, 5, 6, or 7 changes. Adding or removing a tool, a content block, a result key, or a fixed description is a minor change. Adding a registered case that exercises an existing obligation is a patch change. Removing or weakening an obligation is not permitted at the contract layer; see Section 10.

This contract is the one [ADR-0004](../adr/0004-mcp-surface-and-the-tool-result-boundary.md) names as its next slice: the tool surface that is "the single new entry point". In [Contract Shape Framework](README.md) Section 5 terms it belongs to the route and result families for a surface *above* the runtime, beside [api-v0.1](api-v0.1.md). It registers no entity, no fixed SQL template, no status family, and no route *on* the runtime: every tool below dispatches to an entry point that [mvp-v0.1](mvp-v0.1.md) or [entity-discovery-v0.1](entity-discovery-v0.1.md) already fixes, through the same objects `api-v0.1` Section 4.1 dispatches to.

It is a **separate document from all three, not an amendment to any.** `mvp-v0.1`, `entity-discovery-v0.1` and `api-v0.1` are `Accepted`, and each makes a change to itself a recorded human decision under its own Section 10. Nothing here changes a word of any of them. Where ADR-0004 assigns a wording patch to one of them, Section 9 carries it as that contract's owner-recorded decision.

## 2. Status

**Status:** `Accepted 2026-09-22`

This contract is binding on implementation from that date under [Contract Shape Framework](README.md) Section 2.1. The repository owner recorded the required human review of this contract and its acceptance evidence on [#200](https://github.com/OKJ1105/evidence-first-rag/pull/200#issuecomment-5775823750), and merge approval is the owner's act on that pull request. No milestone gate is involved (Framework Section 2.1).

**How this document reached here.** `0.1.0` was drafted on [#199](https://github.com/OKJ1105/evidence-first-rag/issues/199). The loop's two rounds found three blocking findings — the Section 3.3 row restated the ADR-0004 permission without Charter Section 3.3's synthetic-scope condition, and the `mvp-v0.1` `invalid_request` family had no registered case and Section 5 had no pass-through row — and six non-blocking ones; the loop's Writer could edit nothing under `docs/contracts/` (BF7) and recorded the amendments instead. Every one was verified and applied by the writer session out of loop, on the same pull request, before the status line moved.

The direction it is drafted against is the owner's, recorded on [#169](https://github.com/OKJ1105/evidence-first-rag/issues/169) (2026-09-22) and in ADR-0004 — whose own Status line names the owner's disposition on [#198](https://github.com/OKJ1105/evidence-first-rag/pull/198) as its acceptance, given by that pull request's merge, while the line's word stays `Proposed` in the shape ADR-0003 set: an MCP server as the single new entry point; no repository-owned conversational loop; the invariant guaranteed at the tool boundary and not beyond it; three residual risks named and accepted. The slice is [#199](https://github.com/OKJ1105/evidence-first-rag/issues/199).

## 3. Scope

### 3.1 What this contract fixes

- **The tool set** (Section 4.1): three tools, their names, their argument schemas, and the entry point each dispatches to. No other tool.
- **The tool result** (Section 4.2): what `structuredContent` and `content` carry for every result, so that the tool's result and the `/v1` response for the same request are one document.
- **Refusals** (Section 4.3): how an `api-v0.1` Section 4.5 refusal reaches a host, and that it is never a result.
- **The tool descriptions, verbatim** (Section 4.4): the instructions ADR-0004 items 2 and 4 pass to the host, fixed as strings the served tool list must equal.
- **Transport and process** (Section 4.5): where the server listens, what it shares with `/v1`, and what protocol features it offers.
- **What the surface never does** (Section 4.6).

### 3.2 What this contract does not fix

- **Any route, template, parameter or status on the runtime.** The surface refuses nothing the runtime does not refuse again, beyond the argument shape in Section 4.3.
- **What a host model does with a result.** ADR-0004 item 3: the guarantee ends at the tool boundary. This contract fixes what crosses it and what the host is told; it fixes nothing about what the host then writes, chooses, or omits, and it claims nothing about it.
- **The `/v1` surface**, which `api-v0.1` fixes and which stays as it is. `/v1/ask` and `proposal` were retired from the documented path and kept in that contract's route table, by the repository owner's decision on [#203](https://github.com/OKJ1105/evidence-first-rag/issues/203#issuecomment-5827589592) and `api-v0.1` `0.1.2` (ADR-0004 item 5); that was `api-v0.1`'s amendment, not this document's.
- **A renderer for an `entity-discovery-v0.1` result.** `api-v0.1` Section 4.2 fixes `rendered` as `null` for one, and ADR-0004 item 3 records why no renderer is invented at the tool boundary: it would be a second representation of a result whose contract has none, and Section 8's equality cases forbid it.
- **Authentication, authorization, rate limiting, TLS termination, logging, metrics, and the deployment topology.** Milestone 5, exactly as `api-v0.1` Section 3.2 defers them for `/v1`.
- **MCP resources, prompts, sampling, elicitation, and notifications.** Not offered (Section 4.5). Nothing in this repository is a resource a host should read whole, and every capability beyond tool calls would be a second path to the same data.
- **The MCP specification revision.** Fixed by the implementation slice, at or after the revision that introduced `structuredContent` on a tool result, which is the one feature Section 4.2 depends on. This contract uses three fields of a tool result — `content`, `structuredContent`, `isError` — and three of a tool definition — `name`, `description`, `inputSchema`. Every other field of either is absent (Sections 4.1 and 4.2).
- **A non-synthetic approved data scope.** This contract is written against the synthetic `SAMPLE_*` fixtures Charter Section 11 requires, which is the condition Charter Section 3.3 attaches to the boundary ADR-0004 moved. Serving this surface over any other approved data scope is not admitted here: it reopens ADR-0004 (its item 2), and is not inherited from it.

### 3.3 What this contract inherits, and the three readings it builds against

These obligations apply unchanged to every path this contract defines, and it may not weaken them ([Contract Shape Framework](README.md) Section 4).

| Inherited | From |
| --- | --- |
| Every `api-v0.1` Section 3.3 row: fixed SQL only, two database identities, the fourteen status families with their meanings, the three evidence structures on every result, the baseline off every public interface, no rounding, no surrogate key in a public payload, route-name validation against the union | `api-v0.1` Section 3.3 and the contracts it cites |
| `needs_entity_discovery` is terminal inside the runtime path and opens no connection; the next request is a new request from the caller | `mvp-v0.1` Sections 4.6 and 5, `entity-discovery-v0.1` Section 4.12 |
| One entry-point call per tool call; the surface never joins, retries, rephrases, or falls back on a negative result | `api-v0.1` Sections 4.1 and 4.3, Charter Section 3.4 |
| The response envelope and its serialization: one byte representation per result, `null` never omitted, numeric column values as strings | `api-v0.1` Sections 4.2 and 4.4 |
| While the approved data scope is the synthetic `SAMPLE_*` fixtures Charter Section 11 requires, a tool result, evidence bundle included, is returned to the host model that called the tool; the "no evidence, no answer" guarantee ends at that tool boundary | Charter Section 3.3 as amended by ADR-0004, with the condition that sentence carries; ADR-0004 items 2 and 3 |

**Three readings, recorded here because ADR-0004 records them as accepted residual risks and this contract is where they meet an implementation.** None edits an `Accepted` contract; each is stated so that a reader of this document alone knows what the surface does and does not verify.

**1. The selection tool's provenance.** `entity-discovery-v0.1` Section 4.8 says a selection "is never made by a model" and comes "from a person, or from an API caller relaying a person's choice". Its trust mechanism, step 4, verifies the candidate list by re-derivation and verifies nothing about who chose from it — for every caller, `/v1/select` included. ADR-0004 item 4 reads "never made by a model" as binding this system's own models, and passes the obligation to relay a person's choice to the host as an instruction (Section 4.4). The selection tool is `/v1/select`'s equal: the same arguments, the same seven steps, the same result. **This surface verifies the list and not the chooser, and says so in the tool's description.** The `limitations` entry the runtime writes on a dispatched selection currently reads as an explicit user selection; its re-wording is a Section 9 row.

**2. No verbatim gate on host-composed arguments.** `api-v0.1` Section 4.3 lets a scope value become a default only where it is verbatim in the person's request, because a scope the person never named yields true facts about the wrong snapshot. At the tool boundary the host composes every argument, and no equivalent check exists: the tool receives values, not the person's words. The runtime still refuses a scope that does not exist and still records the scope it used in `resolved_scope` and `bound_parameters`, so the error is visible in the evidence. ADR-0004 item 2 accepts this; Section 4.4 carries the instruction; **this surface adds no check**, because a check it could add would compare against text it does not have.

**3. The fact tool bypasses the selection record.** A candidate in a `candidates` result carries its four scope dimensions and its lookup key, and `entity-discovery-v0.1` Section 4.8 calls that "an ordinary fully-scoped argument to a `mvp-v0.1` route". A host that reads a candidate out of the list and calls the fact tool with it gets true facts with no `selection` record, no `candidate_set_id`, and no explicit-selection `limitations` entry. The runtime cannot tell that reference from one a person typed. ADR-0004 item 4 accepts this and names the deterministic alternative — no fact tool, every fact through selection — which Section 9 carries for the owner. **This contract exposes the fact tool**, because a `resolved` discovery outcome needs no selection and would otherwise have no tool to complete it.

## 4. Normative requirements

### 4.1 Tools

Exactly three tools. Each is a fixed dispatch to one entry point — the same object `api-v0.1` Section 4.1 dispatches the corresponding route to — with one entry-point call per tool call.

| Tool name | Arguments | Dispatches to | Result |
| --- | --- | --- | --- |
| `query_facts` | `{"route", "arguments"}` | the `mvp-v0.1` Section 4.5 fact-route entry point, as a `Request`, with no adapter — what `POST /v1/query` dispatches to | an `mvp-v0.1` result |
| `discover_entity` | `{"arguments"}` | `entity_discovery`, `entity-discovery-v0.1` Section 4.3 — what `POST /v1/discover` dispatches to | an `entity-discovery-v0.1` result |
| `select_candidate` | `{"arguments"}` | `entity_selection`, `entity-discovery-v0.1` Section 4.8 — what `POST /v1/select` dispatches to | a dispatched selection (an `mvp-v0.1` result) or a refused one (an `entity-discovery-v0.1` result) |

`route` is a string, and `arguments` is a JSON object whose values are **strings**, on every tool without exception — `api-v0.1` Section 4.1's rule, including its `selected_rank` asymmetry: a discovery result serializes `rank` as a number, and the caller sends its decimal text back. The input schema of each tool states exactly these keys and types and no others, and admits no additional property. **A tool definition declares no `outputSchema`**, and carries no title, annotation, icon or metadata: `structuredContent` is fixed by Section 4.2 as the `api-v0.1` envelope, whose shape that contract's Section 4.4 already fixes, and a second statement of it on the tool would be a second place for the rule to live. `MC-025` asserts the absence. **The surface has no allowlist of its own**: no route name, scope dimension or argument name is checked here, for the reason `api-v0.1` Section 4.1 gives — duplicating the runtime's would be a second place for the rule to live.

**There is no tool over `/v1/ask`** (ADR-0004 item 5). A host model choosing a tool and composing its arguments does the work the Thin LLM Adapter did, and a tool over the adapter would put a second model in the chain and carry the `proposal` key — an adapter's unverified output — across the boundary as if it were a result. There is no tool that lists entities, snapshots, templates or registry contents, no tool that accepts SQL, a table or a column name, no tool that writes, and no tool over `GET /v1/health`: the protocol's own initialization identifies the server (Section 4.5).

### 4.2 The tool result

Every tool call that produces a result returns a tool result with `isError` false, whatever the result's status; a call that produces no result — because its arguments failed Section 4.1's shape, or because the entry point was reached and raised instead of returning — is a refusal (Section 4.3). A `not_found`, an `ambiguous`, an `unsupported` are results — Charter Section 3.4 — and marking one as an error would be a second status vocabulary over the first, which `api-v0.1` Section 4.2 forbids of an HTTP code and this section forbids of `isError`.

| Field | Value |
| --- | --- |
| `structuredContent` | **the `api-v0.1` Section 4.2 envelope for the same request**: `result`, `rendered`, and `contract`, exactly as `POST /v1/query`, `/v1/discover` or `/v1/select` would return them for the same body, serialized under `api-v0.1` Section 4.4 — `proposal` never present, because no tool calls the adapter. `contract` is `api-v0.1`'s identifier and version, because the envelope is that contract's; this contract's identity is carried by the server (Section 4.5), not inside a result. |
| `content` | an ordered list of text blocks. **For an `mvp-v0.1` result**: first, the `rendered` string verbatim as one block; then the canonical JSON of `structuredContent` as one block. **For an `entity-discovery-v0.1` result**: the canonical JSON of `structuredContent` as one block, and nothing else. **Which it is, is decided by the key set `api-v0.1` Section 4.4 fixes and by nothing else**: a `structuredContent.result` carrying `rows` is an `mvp-v0.1` result — a dispatched selection included — and one carrying `resolved`, `candidates` and `candidate_scopes` is an `entity-discovery-v0.1` result. Not by the tool, because the selection tool returns either; and not by a contract identifier inside the bundle, because `api-v0.1` Section 4.3 records that a discovery bundle carries both contracts' identities and cannot be branched on. |
| `isError` | `false` |

The first block for an `mvp-v0.1` result is ADR-0004 item 3's mitigation, stated with its boundary: a host that quotes the block keeps the sentence the runtime rendered, and the `resolved_scope` the sentence is about sits in the second block beside it. It is `rendered` **verbatim** — not prefixed, not suffixed, not joined with the scope into a new sentence — because anything else would be a rendering `mvp-v0.1` Section 4.8 does not define. For an `entity-discovery-v0.1` result no sentence exists to quote, and none is written here (Section 3.2).

The canonical-JSON block exists because the protocol requires `content` on every tool result and a host may read only `content`; it is the same bytes `/v1` would send, so a host that reads either field reads one document. **`structuredContent` is the result and `content` is its carriage**: Section 8's equality cases are asserted on `structuredContent`, and the JSON block is asserted equal to it.

Nothing else. No request identifier, no timestamp, no server identity, no annotation, no resource link, no image: Section 6 requires two identical calls to produce identical results, and every key beyond this table would be either state or a second representation.

### 4.3 Refusals

A **refusal** is a tool result that carries no result. It is `api-v0.1` Section 4.5's vocabulary, carried the one way the protocol offers:

| Field | Value |
| --- | --- |
| `isError` | `true` |
| `content` | one text block: the canonical JSON of `{"refusal", "detail"}`, `refusal` one of the kinds below, `detail` text that names no credential, host, path, or row |
| `structuredContent` | absent |

| Kind | Condition |
| --- | --- |
| `malformed_request` | the arguments fail Section 4.1's shape — a missing top-level key, an extra **top-level** key, a non-object `arguments`, a non-string value inside it. Refused before anything is dispatched, and structural: it never reads a value's meaning. A key *inside* `arguments` that a route does not allow is never checked here: it reaches the entry point, which refuses it as the `mvp-v0.1` or `entity-discovery-v0.1` `invalid_request` **result**, with its evidence structures (`MC-024`). |
| `database_unavailable` | a tool that opens a connection could not |
| `runtime_fault` | the runtime raised one of the `mvp-v0.1` Section 4.4 faults outside the seven statuses |

`unknown_route`, `method_not_allowed` and `adapter_unavailable` do not occur: a tool name outside Section 4.1 is refused by the protocol layer before this surface sees it, tools have no method, and no tool calls the adapter. A refusal never carries `structuredContent`, so a host reading either field tells a refusal from a result by the presence of `result` — the same rule `api-v0.1` Section 4.5 gives an HTTP client. **A refusal is never a result, and a result is never marked `isError`**: the dangerous direction `api-v0.1` `WF-016` to `WF-018` close — a dropped connection reported as a `coverage_gap`, or a registered negative status hidden behind an error flag — is closed here by the same two rows.

A host that validates arguments against the input schema before calling may refuse a malformed call itself, in which case this surface never sees it; the outcome is the same refusal either way, and `MC-011` registers the case at this surface so that a host that does not validate meets the same answer. **The boundary between a shape failure and an argument the runtime rejects is `MC-011` beside `MC-024`**: the first never reaches an entry point and carries no evidence; the second does, and does.

### 4.4 The tool descriptions, verbatim

Each tool's `description` in the served tool list is **exactly** the string below. These are the instructions ADR-0004 items 2 and 4 pass to the host; an instruction that can drift is not one the ADR can cite, so they are fixed here and `MC-020` asserts them byte for byte. A description is text the host reads and this surface cannot enforce (Section 3.3); it is stated as an obligation on the host, in the host's terms, and it is not a check.

**`query_facts`:**

> Returns registered facts about one message, signal, or signal mapping in one source snapshot, from fixed SQL, with the evidence that produced them. `route` is one of message_facts, signal_facts, signal_mapping. `arguments` is a canonical entity reference: the four scope values (project_code, revision_label, network_name, snapshot_label) and the lookup key — message_key for message_facts; message_key and signal_key for signal_facts and signal_mapping, which also accepts an optional mapping_key. Every scope value must be a value the person stated; never supply one the person did not name, and never guess a snapshot. If a scope value is missing, the result is `ambiguous` with the candidate scopes listed, or `coverage_gap` when no snapshot matches — show what the result carries to the person and ask; do not pick one. If the entity is not known, use discover_entity first. The `rendered` sentence is the answer; the evidence beside it is where it came from. A negative status (not_found, ambiguous, coverage_gap, unsupported, invalid_request, needs_entity_discovery) is a result: report it as such and do not answer from anything but the result.

**`discover_entity`:**

> Finds which approved entity a term may refer to, in one source snapshot, or, when a scope value is missing, in each snapshot matching the values given, up to ten. `arguments` carries the four scope values (project_code, revision_label, network_name, snapshot_label), entity_kind (`message` or `signal`), term (the person's words for the entity, at most 200 bytes), and optionally parent_message_key when entity_kind is signal and the parent message is known. Every scope value must be a value the person stated; never supply one the person did not name. An `ambiguous` result lists the snapshots in which the term was found, or every matching snapshot when there are more than ten: show them to the person, let the person choose one, and call again with it. A `candidates` result is a ranked list and is not an answer: show the candidates to the person and let the person choose; do not choose for them, and do not call query_facts with a candidate the person has not chosen. Use select_candidate with the person's choice. A `resolved` result names exactly one entity and may be used with query_facts directly. A `not_found` result means no approved entity matched the term; it does not mean the entity does not exist in the data. A negative status is a result: report it as such.

**`select_candidate`:**

> Completes a `candidates` result from discover_entity with the person's explicit choice. Call it only after the person has chosen a candidate by its rank; never select on the person's behalf, and never call it to try candidates in turn. Pass the same arguments discover_entity was called with, the candidate_set_id from that result, the chosen selected_rank as its decimal text, and the target_route the person's question needs (message_facts for a message; signal_facts or signal_mapping for a signal). The runtime verifies that the candidate list still exists and that the rank names a candidate in it; it does not verify who chose. The result is the fact result for the chosen entity, with a selection record naming the candidate set it was chosen from.

The four sentences these descriptions have in common with `api-v0.1` Section 4.6 are the same obligations for a different reader: a candidate list is not an answer; a scope the person never named is not a default; a negative status is rendered as itself; the surface never chooses, retries, or discovers on the person's behalf. `api-v0.1` binds a page under a person's hand; this section tells a host the same thing and can only tell it.

### 4.5 Transport and process

- **Streamable HTTP**, at one path fixed by the implementation slice and stated in its README, beside `/v1`, **in the same process over the same `Services`** the `api-v0.1` surface dispatches through. One process, one database identity, one registry state: the equality in Section 8 is a statement about two surfaces over one runtime, and a second process would make it a statement about two deployments.
- **Stateless.** No session is held between calls, and no call's outcome depends on an earlier one. A `candidate_set_id` is the whole of what connects a discovery to a selection, and `entity-discovery-v0.1` Section 4.8 makes the runtime re-derive it rather than remember it.
- **Tools only.** The server declares the tools capability and no other. `resources/list` and `prompts/list`, if a host sends them, are answered as the protocol answers an undeclared capability. The remote MCP connectors this surface exists for support tool calls only (ADR-0004, Context), and every further capability would be a second path to the same data.
- **Server identity.** The protocol's initialization carries this contract's identifier as the server name and its version as the server version. That is the one place this contract's identity appears; a tool result carries `api-v0.1`'s (Section 4.2).
- **Blocking work off the event loop.** Every entry-point call opens a connection and runs statements; it runs where `api-v0.1`'s handlers run theirs, so that one slow call does not delay every other call in the process.
- No authentication, authorization, or TLS at this surface. Milestone 5 owns them for `/v1` and owns them here identically (Section 9).

### 4.6 What the surface never does

Each is a prohibition `api-v0.1` states for `/v1`, restated because a tool surface is the place a reader would expect it relaxed:

- It never issues a second entry-point call inside one tool call: no discovery after `needs_entity_discovery`, no second `entity_kind`, no fact call after `resolved`. Chaining is the host's, and each link is its own tool call with its own result.
- It never chooses among candidates, among candidate scopes, or among target routes.
- It never rewrites, summarizes, reorders, filters, or annotates a result. `structuredContent` is the envelope and `content` is fixed by Section 4.2.
- It never marks a result as an error or a refusal as a result.
- It never calls the adapter, and never exposes the `mvp-v0.1` Section 4.7 baseline.

## 5. Outcome coverage

**This contract produces no status family of its own.** A tool result carries through, unchanged, one of the seven `mvp-v0.1` Section 5 statuses or the seven `entity-discovery-v0.1` Section 5 statuses, under the condition that contract fixes — `api-v0.1` Section 5's table, tool for route:

| Tool | Status vocabulary of `result` |
| --- | --- |
| `query_facts` | `mvp-v0.1` Section 5, all seven |
| `discover_entity` | `entity-discovery-v0.1` Section 5, all seven |
| `select_candidate` | `entity-discovery-v0.1` Section 5 for a refused selection; `mvp-v0.1` Section 5 for a dispatched one |

The three refusal kinds of Section 4.3 are a property of the tool exchange, not of a request's outcome, and never appear in a `result`.

## 6. Determinism

- Two tool calls with identical arguments to the same tool, against the same provisioned database and the same registry, produce identical `structuredContent` and identical `content` — Section 4.2 admits no timestamp or identifier, and `api-v0.1` Section 4.4 fixes one serialization.
- **A tool call and a `/v1` request with the same body produce the same envelope**, byte for byte after serialization. This is the property Section 8 registers, and it is what makes the tool surface a surface and not a second runtime.
- The surface reorders nothing and holds no state (Sections 4.5 and 4.6).
- The host model is outside every guarantee here, as the adapter is outside `mvp-v0.1` Section 6's: which tool it calls, with what, and in what order is not this contract's, and the guarantee applies from the tool call onward.

## 7. Evidence obligations

This contract adds no evidence key and requires none. Its obligation is `api-v0.1` Section 7's, in both directions:

- **Every key** `mvp-v0.1` Section 7 and `entity-discovery-v0.1` Section 7 require on a result — the `selection` record and the `discovery_*` keys of a dispatched selection included — is present in `structuredContent.result` with the value the runtime produced.
- **Nothing in `result` is the surface's.** `rendered` and `contract` sit beside it in the envelope, and the `content` blocks are carriage, not evidence: the first block on an `mvp-v0.1` result is `rendered` copied, and the JSON block is `structuredContent` copied. Neither is in `evidence_bundle`, `source_trace` or `limitations`, and a host is told (Section 4.4) that the evidence is where the answer came from.

A tool result names no credential, host, local path, or environment variable. The one role name it carries is the `read_only_safeguards.role_name` that `mvp-v0.1` Section 7 already requires in every evidence bundle.

## 8. Acceptance evidence

Each obligation is either an automated assertion over registered inputs or a recorded human decision with named evidence, as Charter Section 9 requires. No Charter gate item is this contract's: Milestone 4's `G2` and `G3` are `api-v0.1`'s, and this surface is judged by equality with that one.

| Obligation | Acceptance evidence |
| --- | --- |
| Section 4.1 tools and dispatch | Automated. `MC-025`: `tools/list` returns exactly three tools with the fixed names, the fixed input schemas, no `outputSchema`, and no fourth; a test that no tool accepts a key Section 4.1 does not name; `MC-014`. |
| Section 4.1 no tool over `/v1/ask` | Automated. `MC-025` asserts the absence; a test that the adapter is never called by any tool, with a proposer injected and its call count asserted zero across every registered case. |
| Section 4.2 equality with `/v1` | Automated, **the reason this contract exists**. `MC-001` to `MC-006`, `MC-014`, `MC-015`, `MC-019` to `MC-021`, `MC-024`: for each, `structuredContent` equals the `/v1` response envelope for the same body, compared as canonical JSON. |
| Section 4.2 `content` | Automated. `MC-022`: on every `mvp-v0.1` result the first block equals `rendered` and the last equals the canonical JSON of `structuredContent`; on every `entity-discovery-v0.1` result there is exactly one block and it is that JSON; on a dispatched selection there are two blocks because the result is `mvp-v0.1`'s. |
| Section 4.2 a negative status is not an error | Automated. `MC-002`, `MC-019`, `MC-020`, `MC-021`, `MC-024`: `isError` false with an `ambiguous`, a `not_found`, a discovery `ambiguous`, an `unsupported`, an `invalid_request` in `result`. |
| Section 4.3 refusals | Automated. `MC-011`, `MC-016`, `MC-017`: `isError` true, exactly one block, body exactly `{"refusal", "detail"}`, no `structuredContent`, no status family produced, and no entry point called on `MC-011`. |
| Section 4.4 descriptions | Automated. `MC-025`: each served description equals its Section 4.4 string byte for byte. |
| Section 5 status pass-through | Automated. The registered cases between them reach each of the fourteen status families, and a test enumerating both vocabularies asserts that every member is named by at least one registered case, each equal to `/v1` and none marked an error — so this row cannot silently stop being true. |
| Section 7 evidence | Automated. For every registered case, the key set of `structuredContent.result.evidence_bundle`, of `structuredContent.result.source_trace` and of each `limitations` entry equals the key set of the runtime's own result, on negative outcomes as well as successes; the equality rows above are what make "the surface adds no key to, removes none from, and renames none in `result`" a checked property rather than an argument. |
| Section 4.5 one process, one `Services` | Automated. A test that the MCP server and the `/v1` app are built over the same `Services` object, and that a fault injected into it is observed identically by both surfaces (`MC-016`, `MC-017` run against both). |
| Section 4.5 tools only | Automated. `MC-023`: the initialization result declares tools and no other capability; the server name and version are this contract's. |
| Section 4.6 one entry-point call per tool call | Automated. A test over every tool that exactly one entry-point call occurs per tool call, `MC-003` included, where the whole path is three tool calls and three entry-point calls. |
| Section 6 determinism | Automated. `MC-012`: `MC-001`'s call twice yields identical `structuredContent` and `content`. |
| Section 3.3 readings 1 to 3 | **Recorded human decision**: ADR-0004, accepted on #198, and this contract's Framework Section 6 step-4 review. Nothing automated can assert who chose or what the host does, and this row says so rather than registering a test that would pass whether or not the risk is realised. |

### 8.1 Registered cases

Each case names an `api-v0.1` Section 8.1 workflow fixture and is that fixture's steps issued as tool calls instead of HTTP requests, with the expected `structuredContent` at each step equal to that fixture's expected response envelope. A case names a fixture rather than restating it, so that one registration cannot drift from the other. Every identifier is `SAMPLE_*`.

| ID | Tool calls | Expected |
| --- | --- | --- |
| `MC-001` | `query_facts` with `WF-001`'s body | `structuredContent` equals `WF-001`'s envelope; `content` is `rendered` then the JSON |
| `MC-002` | `query_facts` with `WF-002`'s body | equals `WF-002`: `ambiguous`, candidate scopes in `result.source_trace.contributing_scopes`; `isError` false |
| `MC-003` | `WF-003`'s three steps as `query_facts`, `discover_entity`, `select_candidate`, the third citing the second's `candidate_set_id` | each step equals `WF-003`'s expected envelope at that step; `needs_entity_discovery` with no discovery executed; `candidates`; `success` with the `selection` record; three entry-point calls in all |
| `MC-004` | `WF-004`'s two steps as `discover_entity`, `query_facts` | equals `WF-004`: `resolved`; `success` |
| `MC-005` | `discover_entity` with `WF-005`'s body | equals `WF-005`: `not_found` with the not-in-registry entry; one block; nothing else executed |
| `MC-006` | `select_candidate` with `WF-006`'s body | equals `WF-006`: `invalid_request` from `entity-discovery-v0.1`; no fact template executed; one block |
| `MC-011` | `query_facts` with no `arguments` key; with an extra key; with a non-object `arguments`; with a numeric `selected_rank` on `select_candidate` | `malformed_request` in all, per Section 4.3; no entry point called |
| `MC-012` | `MC-001` twice | identical `structuredContent` and `content` |
| `MC-014` | `query_facts` with `WF-014`'s three bodies | equals `WF-014`: `unsupported`, producing layer `runtime`, in all three |
| `MC-015` | `WF-015`'s two steps as `query_facts`, `discover_entity` | equals `WF-015`: `coverage_gap` in both with the required entry |
| `MC-016` | a tool that opens a connection, against an unreachable database | `database_unavailable` per Section 4.3; **no `structuredContent` and no status family produced** |
| `MC-017` | an injected `mvp-v0.1` Section 4.4 fault on a tool that opens a connection | `runtime_fault` per Section 4.3; no `structuredContent` and no status family produced |
| `MC-019` | `query_facts` with `WF-019`'s body | equals `WF-019`: the `mvp-v0.1` `not_found` with its evidence structures; `isError` false; asserted **not** to serialize as an empty `success` |
| `MC-020` | `discover_entity` with `WF-020`'s body | equals `WF-020`: the `entity-discovery-v0.1` `ambiguous`, carrying the candidate scopes in which the term was found and `evidence_bundle.scope_search` (`0.2.0`); `isError` false |
| `MC-021` | `discover_entity` with `WF-021`'s body | equals `WF-021`: the `entity-discovery-v0.1` `unsupported` with its producing layer; `isError` false — never an error, for the reason `WF-021` gives: an unknown enumeration value looks structural and is not |
| `MC-022` | every case above whose result carries `rows`, and every one whose result carries `resolved`, `candidates` and `candidate_scopes` | the Section 4.2 `content` rule holds for each, decided by that key set — not by tool, and not by a contract identifier inside the bundle; `MC-006`, a refused selection, is the case that separates the three readings, and it carries one block |
| `MC-023` | initialization | the tools capability and no other; server name `mcp-v0.1`, server version this document's |
| `MC-024` | `query_facts` with a fact route and an argument name outside that route's allowlist — `mvp-v0.1` `FX-109`'s shape, string-valued and with exactly the top-level keys, so that Section 4.3 passes it | equals `POST /v1/query` for the same body: the `mvp-v0.1` `invalid_request` with its `evidence_bundle`, `source_trace` and `limitations`, `bound_parameters` empty, no connection opened; `isError` false. Refused by the runtime, never by Section 4.3, which never reads an argument's meaning. **`FX-110`'s contradictory scope has no case here**: two values for one dimension can only be sent as a non-string value, which is `malformed_request` on this surface exactly as it is on `/v1` (`MC-011`). |
| `MC-025` | `tools/list` | exactly `query_facts`, `discover_entity`, `select_candidate`, in that order, with Section 4.1's input schemas and Section 4.4's descriptions byte for byte; no `outputSchema` on any; no fourth tool |

The numbering is deliberate: for `MC-001` to `MC-021`, an identifier's suffix is the `WF-*` fixture it issues as tool calls, so that `MC-014` is read beside `WF-014` without a lookup. `WF-007` to `WF-010`, `WF-013`, `WF-018` and `WF-022` have no counterpart because they exercise `/v1/ask` or `GET /v1/health`, which have no tool. `MC-011`, `MC-012`, `MC-016` and `MC-017` keep their `WF-*` numbers because they are the same cases at this surface. `MC-022` to `MC-025` are this surface's own and mirror no fixture; `MC-024` exists because the `mvp-v0.1` `invalid_request` family was reached in `api-v0.1` only through `/v1/ask`, so a tool surface without it would leave one family of Section 5's table with no case.

**`MC-003` is the whole target path** — a vague request, a candidate list, a person's choice, a fact with its evidence — as three tool calls, and it is the reason this contract exists. `MC-025` is the one that binds the host's instructions to a string a test can read.

### 8.2 Deferral of the acceptance evidence

Section 10 permits this contract to be accepted with its acceptance evidence explicitly deferred with a named owner, as `api-v0.1` Section 8.2 was. Every automated row above is an assertion over an implementation that does not exist on the date of acceptance; requiring it first would make acceptance unreachable, because [Contract Shape Framework](README.md) Section 2.1 forbids implementing against a contract that is not accepted. **The owner is the named owner of the deferral**, and each automated row is discharged by the implementation slice's pull request, which cites this section and shows every registered case passing — with each assertion shown failing under a named mutation, per [#17](https://github.com/OKJ1105/evidence-first-rag/issues/17) rule 9.

**No numeric threshold is registered and no `registered_at` is recorded.** Every row is an equality or a structural assertion; there is nothing for Charter Section 9's before-the-run rule to order.

## 9. Deferred decisions

| Decision | Owner |
| --- | --- |
| **The explicit-selection `limitations` wording.** `mvp-v0.1` Section 7 requires an entry "when scope was resolved to one candidate out of several by an explicit user selection", and `entity-discovery-v0.1` Section 7 supplies the analogous entry on a dispatched selection. On this surface the chooser is unverified (Section 3.3, reading 1), and ADR-0004 item 4 assigns a re-wording to what the runtime does verify — the candidate set, its digest and count, and that a caller selected from it — never to who chose. | The repository owner, as a patch version of `entity-discovery-v0.1` under its Section 10, on that contract's own slice. **Implementation of this contract does not depend on the answer**: Section 8's equality holds whatever the entry says, because both surfaces carry the runtime's entry unchanged. Until it is recorded, the entry reads as it does today and Section 4.4's `select_candidate` description says what is and is not verified. |
| **No fact tool: every fact through selection.** The deterministic alternative ADR-0004 item 4 names for reading 3: withdraw `query_facts`, so that every fact the MCP surface returns carries a `selection` record. Cost: a `resolved` discovery outcome needs no selection and would have no tool to complete it without an `entity-discovery-v0.1` change admitting a `resolved` reference to the selection path. | The repository owner. **Not adopted at `0.1.0`**, for the cost stated; adopting it is a minor version here and a minor version of `entity-discovery-v0.1`. |
| **Closed at `0.1.1`**: retiring `/v1/ask` and `proposal` (ADR-0004 item 5) | **Decided by the repository owner on [#203](https://github.com/OKJ1105/evidence-first-rag/issues/203#issuecomment-5827589592)**: retired from the documented path, kept in the route table, recorded as `api-v0.1` `0.1.2`. Implementation of this contract did not depend on it: no tool calls the adapter either way. |
| **The transport path**, and whether the README's connector instructions name it. | The implementation slice. Bounded: it is not under `/v1`, which `api-v0.1` Section 4.1 fixes exhaustively. |
| **The MCP specification revision** the server declares. | The implementation slice, at or after the revision that introduced `structuredContent` (Section 3.2). |
| Authentication, authorization, rate limiting, TLS termination, structured logs and metrics at this surface. | Milestone 5 deployment contract, together with `/v1`'s. A remote connector needs a public HTTPS URL, which is that milestone's. |
| Whether `api-v0.1` Section 8.1's fixture table is patched to note that its `WF-*` cases are also issued as `MC-*` tool calls. | The repository owner, under `api-v0.1` Section 10. Implementation does not depend on the answer: Section 8.1 here names the fixtures either way. |
| Resources, prompts, sampling, elicitation, notifications, and a tool that returns a widget or UI resource. | **Not opened.** Section 4.5 declares tools only. A later minor version may add a capability after the surface has been used and a need is measured (Charter Section 3.5). |

No row above is open in the sense that this contract needs it to be implementable. Sections 4.1 through 4.6 are complete as they stand.

## 10. Change control

- This contract is `Proposed` and is amended by an ordinary contract-only pull request under [Contract Shape Framework](README.md) Section 7 until it is `Accepted`.
- After acceptance, a change that does not weaken a Charter or ADR invariant produces a new version with a recorded human decision. Adding or removing a tool, a `content` block, a result field, a refusal kind, or a fixed description is a minor version and requires a fresh independent design review. Adding a registered case that exercises an existing obligation is a patch version.
- **Removing or weakening an obligation is not permitted at this layer.** A change that would let the surface issue a second entry-point call inside one tool call, choose among candidates or scopes, rewrite a result, mark a negative status as an error, call the adapter, send to a host anything a result does not carry, or serve a non-synthetic approved data scope (Section 3.2) is not a contract-level change: it would weaken Charter Sections 3.1, 3.3 or 3.4, or ADR-0004, and requires an ADR, a Charter update where material, and a recorded human decision.
- This contract may not move to `Accepted` until the repository owner records the Framework Section 6 step-4 review on its pull request, **and** the Section 8 acceptance evidence is either satisfied or explicitly deferred with a named owner. Section 8.2 is that deferral.
- A superseded version is retained with a `Superseded by` status rather than deleted, so that a past acceptance record stays interpretable.
