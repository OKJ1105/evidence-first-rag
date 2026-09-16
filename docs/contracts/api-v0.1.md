# Milestone 4 API Contract v0.1

## 1. Identifier and version

**Identifier:** `api-v0.1`

**Version:** `0.1.0` — the identifier names the document; the version tracks its obligations. `0.1.0` proposes the contract.

The version changes when any observable obligation in Section 4, 5, 6, or 7 changes. Adding or removing a route, a response key, a refusal kind, or a presentation obligation is a minor change. Adding a workflow fixture that exercises an existing obligation is a patch change. Removing or weakening an obligation is not permitted at the contract layer; see Section 10.

This contract is the **Milestone 4 API contract** that [Contract Shape Framework](README.md) Section 8 names for "route and result schemas for the post-Milestone 1 API", and covers the first Milestone 4 deliverable in [Project Charter](../PROJECT_CHARTER.md) Section 9: "stable API flow from request or candidate selection to evidence-backed result". In Framework Section 5 terms it belongs to the route and result families for a surface *above* the runtime. It registers no entity, no fixed SQL template, no status family, and no route *on* the runtime: every route below dispatches to one that [mvp-v0.1](mvp-v0.1.md) or [entity-discovery-v0.1](entity-discovery-v0.1.md) already fixes.

It is a **separate document from both, not an amendment to either.** Both are `Accepted`, and each makes a change to itself a recorded human decision under its own Section 10. Nothing here changes a word of either, and nothing here touches `export-v0.1`, which is `Proposed` on its own pull request ([#159](https://github.com/OKJ1105/evidence-first-rag/pull/159)) and is not yet in the tree.

## 2. Status

**Status:** `Proposed`

Not binding on implementation ([Contract Shape Framework](README.md) Section 2). It may be cited as direction. The repository owner's Framework Section 6 step-4 review on this contract's pull request is the record acceptance cites; the status line moves only on that record, and the writer does not move it.

The direction it is drafted against is the owner's, recorded on [#169](https://github.com/OKJ1105/evidence-first-rag/issues/169): decision A (the caller joins), B (one contract, with a size budget), C (the minimal UI is built) and D (a single-command local stack now, the Charter Section 3.7 Azure target in Milestone 5), and the reordering that defers the export implementation and the surface that serves one. Each is a relay by a writer session; the operative record is the review above.

## 3. Scope

### 3.1 What this contract fixes

- **Five routes** on an HTTP surface: a structured query, a natural-language ask, a discovery request, a selection, and a health probe — their methods, paths, request bodies and response bodies.
- **The orchestration** behind the natural-language route: adapter, revalidation, runtime, in that order and no other, and what a `needs_entity_discovery` response carries so that a caller can make its next request itself.
- **Statelessness.** Every request carries everything it needs. A candidate set is named by the `candidate_set_id` digest of `entity-discovery-v0.1` Section 4.8, never by a session, a cookie, or a server-side record.
- **Surface refusals**: the closed list of conditions under which no result is produced, their HTTP status, their body, and that none of them is a status family.
- **Serialization** of a normalized result as JSON, lossless in both directions against `mvp-v0.1` Section 7 and `entity-discovery-v0.1` Section 7.
- **The response envelope**: the keys a response carries beside the result, and that none of them is inside `evidence_bundle`, `source_trace` or `limitations`.
- **The presentation surface's obligations** — what the minimal UI of Charter Section 9 may and may not do with a result.
- **The local stack**: that it provisions through the `mvp-v0.1` Section 3.4 path and nothing else.
- **End-to-end workflow fixtures** `WF-*`, built from the `FX-*` and `DX-*` cases the two accepted contracts register.

### 3.2 What this contract does not fix

- **Serving an export.** Deferred with the export implementation to the decision point recorded on #169. Section 9 carries the row and the two paths.
- **The TSV document** (`export-v0.1`), **answer prose** (`mvp-v0.1` Section 4.8), and **any route, template, parameter or status on the runtime**. The surface validates nothing the runtime does not validate again, and adds no validation of its own beyond the body shape in Section 4.4.
- **The adapter's vocabulary and instructions.** `mvp-v0.1` Section 4.6 pins both by digest and makes a change reopen the Milestone 2 comparison. This contract sends the adapter exactly what that section fixes, and nothing more.
- **Authentication, authorization, rate limiting, logging, metrics, TLS, and the deployment topology.** Milestone 5 (Charter Section 9), with the Section 9 rows below.
- **The copy button** and any presentation convenience beyond Section 4.6. Deferred on #169 until the surface has been used.

### 3.3 What this contract inherits, and the four places it reads an accepted contract closely

These obligations apply unchanged to every path this contract defines. They are restated as inherited, not re-decided, and this contract may not weaken them ([Contract Shape Framework](README.md) Section 4).

| Inherited | From |
| --- | --- |
| Authoritative facts come only from registered fixed SQL templates; no free-form SQL from user text or model output; input bound only through named allowlisted parameters | Charter Section 3.2, `mvp-v0.1` Section 4.4 |
| Two database identities; every runtime connection is the read-only identity in a read-only transaction; the runtime never holds the provisioning credentials | `mvp-v0.1` Section 4.3 |
| The seven `mvp-v0.1` status families and the seven `entity-discovery-v0.1` families, with their meanings; `success` is not a discovery outcome; `unsupported` preserves its producing layer | `mvp-v0.1` Section 5, `entity-discovery-v0.1` Section 5, Charter Section 3.4 |
| `evidence_bundle`, `source_trace` and `limitations` on every result including every negative outcome, with the required keys | `mvp-v0.1` Section 7, `entity-discovery-v0.1` Section 7 |
| The adapter receives the request text and the route, argument and scope-vocabulary metadata of `mvp-v0.1` Section 4.6, and no row, fixture or evidence content; its output is untrusted input to deterministic revalidation | Charter Section 3.3, `mvp-v0.1` Section 4.6 |
| The deterministic baseline is not a product path, is exposed by no public interface, and is not a fallback | `mvp-v0.1` Section 4.7 |
| A selection is never made by a model; it comes from a person, or from an API caller relaying a person's choice | `entity-discovery-v0.1` Section 4.8 |
| `needs_entity_discovery` is terminal inside the runtime path, opens no connection, and a discovery request is a new request from the caller | `mvp-v0.1` Sections 4.6 and 5, `entity-discovery-v0.1` Section 4.12 |
| Rendering may present validated results but may not add or alter facts; no rounding anywhere | Charter Sections 3.1 and 9, `mvp-v0.1` Sections 4.8 and 6 |
| Surrogate keys appear in no public payload | `mvp-v0.1` Section 4.2 |
| Route-name validation runs against the **union** of the five registered routes — the three fact routes and the two discovery routes — never against either contract's list alone | `entity-discovery-v0.1` Section 3.3 extension 1 |

**Four places where this contract reads an `Accepted` contract closely.** None edits that contract's text, and none weakens an obligation. Each is recorded here with a Section 9 row for the owner's decision on whether that contract is patched to state it. **Implementation depends on none of the answers**, because in each case this contract takes the conservative side of the reading.

**1. Whom `entity-discovery-v0.1` Section 4.12 binds.** Its acceptance evidence asserts that a `needs_entity_discovery` result "opens no connection and triggers no discovery", and Section 4.12 says the outcome "stays terminal inside the `mvp-v0.1` runtime path" and that a discovery request "is a **new** request from the caller". This contract reads both as binding **the runtime**, not a caller above it: the surface's natural-language route returns that result unchanged, and the caller's next request is a new request the caller makes (Section 4.3). The surface itself never issues a discovery request on a caller's behalf, so the assertion stays true under either reading. This is decision A on #169.

**2. What `mvp-v0.1` Section 7 forbids of a rejected proposal.** For an outcome that opens no connection, that section fixes `bound_parameters` as empty and says the adapter's arguments "are never reported as such" — as bound parameters — because that "would present a rejected proposal as a fact the runtime acted on". Section 4.3 places the adapter's proposal in a response key **outside** the result, labelled as a proposal. This contract reads Section 7 as governing the evidence bundle, not the envelope around it; the obligation's reason is honoured because the key is named for what it is and the bundle it sits beside still says nothing was bound. Where the reading could mislead it does not: the key is never present on a route that does not call the adapter, and Section 4.6 forbids a presentation surface to render it as a fact.

**3. What `mvp-v0.1` Section 4.6's verbatim-token rule reaches, given the order revalidation checks in.** That section forbids the adapter to invent a scope value and installs revalidation as the deterministic check against it. **On the one path this contract cares about, that check does not run.** `validate` refuses a missing lookup key as `needs_entity_discovery` before `_values_come_from_the_request` is reached, so the scope values in a `needs_entity_discovery` proposal have passed the route, allowlist and type checks and **never the verbatim-token check**. `mvp-v0.1` Section 4.6 does not say which order the checks run in, so the ordering is an implementation fact this contract must not build on. It therefore builds on the *obligation* instead: Section 4.3 requires the surface to apply the verbatim-token rule itself to every proposed value it lets a person act on, whether or not revalidation reached it. The conservative behaviour that holds in the interval is stated there and in Section 4.6 obligation 4, and it is the same under either ordering.

**4. Whether a union-registered non-fact route reaching a fact-route endpoint is "unregistered".** `entity-discovery-v0.1` Section 3.3 extension 1 makes route-name validation run against the five-route union, and its Section 5 reserves the unregistered-route refusal for a name outside that union. `entity_discovery` and `entity_selection` are inside it, so neither is an unregistered route. This contract reads that rule as fixing **which names are registered**, not as obliging every endpoint to dispatch every registered name: `/v1/query` is a fixed dispatch to the `mvp-v0.1` Section 4.5 fact routes (Section 4.1), and a registered non-fact route arriving there is not representable by the contract that endpoint serves, which is what `unsupported` means (Charter Section 3.4). The alternative reading — that the union makes discovery reachable through `/v1/query` — is declined: it would put a `candidates` result on a route whose Section 5 row admits only the `mvp-v0.1` seven, which is the confusion `entity-discovery-v0.1` Section 5 exists to prevent.

## 4. Normative requirements

### 4.1 Routes

| Method and path | Body | Dispatches to | Response |
| --- | --- | --- | --- |
| `POST /v1/query` | `{"route", "arguments"}` | `mvp-v0.1` Section 4.5, as a `Request`, with no adapter | an `mvp-v0.1` result |
| `POST /v1/ask` | `{"request_text"}` | the Section 4.3 orchestration | an `mvp-v0.1` result, with `proposal` |
| `POST /v1/discover` | `{"arguments"}` | `entity_discovery`, `entity-discovery-v0.1` Section 4.3 | an `entity-discovery-v0.1` result |
| `POST /v1/select` | `{"arguments"}` | `entity_selection`, `entity-discovery-v0.1` Section 4.8 | a dispatched selection (an `mvp-v0.1` result) or a refused one (an `entity-discovery-v0.1` result) |
| `GET /v1/health` | none | nothing; opens no connection | Section 4.5 |

**`/v1/query` is a fixed dispatch to the `mvp-v0.1` fact-route entry point**, not a general route-name endpoint. Its `route` is one of the three Section 4.5 names; any other value — including `entity_discovery` and `entity_selection`, which Section 3.3 reading 4 records as *registered* in the union and still not fact routes — reaches that entry point and is refused there as `unsupported`, with the producing layer recorded. This is not the unregistered-route refusal `entity-discovery-v0.1` Section 5 defines; it is a registered name that the contract this endpoint serves cannot represent. The two discovery routes are reached through `/v1/discover` and `/v1/select`, which dispatch to them the same fixed way.

`arguments` on every route is a JSON object whose values are strings; the surface passes it to its route's entry point as-is and that contract's own validation decides every other question. **The surface has no allowlist of its own.** Duplicating the runtime's would be a second place for the rule to live; fixing which entry point a path dispatches to is not an allowlist, because no request is refused by it.

There is no route that lists entities, snapshots, templates or registry contents, no route that accepts SQL, a table or a column name, and no route that writes. Charter Section 3.2 forbids the first three; `mvp-v0.1` Section 4.3 makes the fourth impossible at the database.

### 4.2 The response envelope

Every response that carries a result is HTTP **200**, whatever the result's status. A `not_found`, an `ambiguous`, an `unsupported` are results — Charter Section 3.4 calls them "expected results, not exceptional cases to hide" — and an HTTP error code would be a second status vocabulary over the first. The body is one JSON object:

| Key | Present | Value |
| --- | --- | --- |
| `result` | always | the normalized result, serialized under Section 4.4 |
| `rendered` | always | **a JSON string or `null`.** For an `mvp-v0.1` result, the string is the `mvp-v0.1` Section 4.8 rendered answer: the ordered concatenation of its segments, verbatim. For an `entity-discovery-v0.1` result it is `null` — that contract defines no renderer, and this contract does not invent one. The type is fixed here because the answer exists as an ordered sequence of prose and value segments inside the runtime, so that `mvp-v0.1` Section 4.9's `E1` can compare segments; carrying that structure on the wire would put a second representation of the answer in the envelope and would make two conforming implementations produce different bodies. |
| `proposal` | on `/v1/ask` only | `{"route", "arguments", "verbatim"}`. `route` and `arguments` are the adapter's output exactly as returned and before revalidation; `verbatim` is the list of `arguments` names whose value is a verbatim whole token of `request_text` by the `mvp-v0.1` Section 4.6 rule, which Section 4.3 requires the surface to evaluate because revalidation did not reach it. On any other route the key is absent. |
| `contract` | always | this contract's identifier and version, as `{"identifier", "version"}` |

Nothing else. In particular no request identifier, no timestamp, and no server identity: Section 6 requires two identical requests to produce identical bodies, and Milestone 5 owns observability. A key not in this table is a defect.

`result` is the whole of what the runtime returned. The surface adds no key to it, removes none, renames none, and reorders no list. The keys beside it are the surface's and are not evidence (Section 7).

### 4.3 The natural-language route and the join

`POST /v1/ask` runs, in this order and no other:

1. The request text goes to the `mvp-v0.1` Section 4.6 adapter, which returns a proposal `{route, arguments}`.
2. The proposal goes through `mvp-v0.1` Section 4.6 revalidation. A refusal there is the response's result, with the producing layer that section fixes.
3. A proposal that passes is executed by the runtime, and the runtime's result is the response's result.

The adapter is the **only** proposer. When none is configured the route refuses with `adapter_unavailable` (Section 4.5) and calls nothing: not the baseline, which `mvp-v0.1` Section 4.7 keeps off every public interface, and not any other resolver. Charter Section 3.4's "must not silently fall back" applies to a missing model as much as to a negative result.

**There is therefore nothing for a response to record about *which* proposer ran.** Issue [#170](https://github.com/OKJ1105/evidence-first-rag/issues/170) admitted the Section 4.7 baseline as a second proposer and asked the response to name the one that ran; that is declined, not dropped, and `mvp-v0.1` Section 4.7 is the reason — the baseline "is not exposed by any public interface", so admitting it here would put it on one. With exactly one permitted proposer, the presence of `proposal` is itself the record. Admitting a second would be a minor version that adds the key, under Section 10.

**The join.** When step 2 or 3 produces `needs_entity_discovery`, the response is that result, unchanged, with `proposal` beside it. **That is where the surface stops.** The caller's next request is `POST /v1/discover`, and the caller makes it. Three things follow, and together they are what decision A on #169 required this contract to state, because Charter Section 3.3's prohibitions are written of an LLM and the orchestrator is not one:

| The surface never | Because |
| --- | --- |
| issues a discovery request or a selection without a person's act — and never lets a value the person did not supply stand as one, which Section 4.6 obligation 4 fixes for every field a form can carry | Charter Section 3.3, "silently resolve ambiguous entities"; `entity-discovery-v0.1` Section 4.8, a selection comes from a person |
| returns a candidate list where a fact result is expected, or the reverse. The two are different result contracts and `result.evidence_bundle.contract_identifier` names which | Charter Section 3.1, a rendering "must not contradict or extend the evidence bundle"; `entity-discovery-v0.1` Section 5 |
| reaches for another path when a result is negative: no retry with a different proposer, no discovery after `not_found`, no second lookup after `ambiguous` | Charter Section 3.4 |

**What the caller can take from the response, and the check that is not skipped.** `proposal` is the adapter's output as returned. `proposal.route` is the route it determined; the table below fixes the `entity_kind` a discovery request for that route would name, so that no client has to guess it.

`proposal.arguments` are the adapter's scope values, and **revalidation never checked them against the request text**: it refused at the missing lookup key first (Section 3.3, reading 3). A model-invented `project_code`, `revision_label`, `network_name` or `snapshot_label` therefore sits in that key having passed no check that `mvp-v0.1` Section 4.6 installs against exactly that failure. **The surface applies the check revalidation did not reach.** For every value in `proposal.arguments`, the surface evaluates `mvp-v0.1` Section 4.6's rule — the value is a verbatim whole token of `request_text`, in the sense that section fixes — and the envelope carries the outcome per argument as `proposal.verbatim`, a list of the argument names that passed.

The values themselves are not filtered out: `proposal` is a record of what the model returned, and editing it would make it a worse record. What the check governs is **what may become a default in front of a person** — Section 4.6 obligation 4 — because a scope the person never named is the one error this system exists to prevent: it yields *true facts about the wrong snapshot*, with `resolved_scope` recording the scope as used and no `limitations` entry saying where it came from. Charter Section 3.6 forbids the runtime to supply an unrecorded project, revision, bus or snapshot; arriving at one through a model and a prefilled form is the same outcome by a longer road.

The **term** is the caller's — the surface derives none, and Section 9 records why. A presentation surface may put the person's own request text into the term field for them to edit (Section 4.6): showing someone their own words back is transcription, not derivation.

| `proposal.route` | `entity_kind` | Permitted `target_route` on selection (`entity-discovery-v0.1` Section 4.8) |
| --- | --- | --- |
| `message_facts` | `message` | `message_facts` |
| `signal_facts` | `signal` | `signal_facts`, `signal_mapping` |
| `signal_mapping` | `signal` | `signal_facts`, `signal_mapping` |

`POST /v1/discover` and `POST /v1/select` pass `arguments` to their route unchanged. A selection's `candidate_set_id` is the digest the discovery response carried, so the surface holds nothing between the two requests and a selection made against a registry that has since changed is refused by `entity-discovery-v0.1` Section 4.8 step 4, not by anything here.

### 4.4 Body shape and serialization

**Request bodies** are UTF-8 JSON objects with exactly the keys Section 4.1 names for the route, no others, each of the stated type. Anything else — a body that is not JSON, not an object, missing a key, carrying an extra key, or carrying a non-string where a string is required — is the surface refusal `malformed_request` (Section 4.5), before anything is dispatched. This is the one validation the surface performs, and it is structural: it never reads a value's meaning.

**Response bodies** serialize a normalized result under these rules, so that the result can be read back with no loss:

- **The top-level result keys are fixed by this contract**, because neither accepted contract names them: `status`, `evidence_bundle`, `source_trace` and `limitations` on both; `rows` on an `mvp-v0.1` result; `resolved`, `candidates` and `candidate_scopes` on an `entity-discovery-v0.1` result. `evidence_bundle`, `source_trace` and `limitations` are the names `mvp-v0.1` Section 7 and `entity-discovery-v0.1` Section 7 use, and the keys *inside* those three are theirs entirely. The other four are this contract's naming for a payload those documents describe without naming — `mvp-v0.1` Section 5 for the status values and its Section 4.5 for what a route returns, `entity-discovery-v0.1` Section 5 for `resolved` and `candidates` as *statuses* and its Sections 4.6 and 4.3 for the lists those statuses carry. Section 9 carries the owner's decision on whether either contract is patched to name them. A field with no value is `null`, never omitted; an empty list is `[]`.
- An enumeration value is its string value. A scope is an object of its four dimensions. A canonical reference is an object of its dimensions and keys. A limitation is `{"kind", "detail"}`.
- Integers are JSON numbers. **A numeric column value of `mvp-v0.1` Section 4.1 — `scale_factor`, `scale_offset` — is a JSON string** of its stored decimal representation, because a JSON number would pass through a binary float and `mvp-v0.1` Section 6 forbids rounding anywhere.
- Serialization uses the canonical JSON rules of `entity-discovery-v0.1` Section 4.2 — keys sorted byte-wise, no insignificant whitespace, UTF-8 — so that one result has one byte representation.

### 4.5 Surface refusals and the health probe

A **surface refusal** is a response that carries no result. It is not a status family: no request reached a route, or a fault outside the seven statuses occurred. The body is `{"refusal", "detail"}` and nothing else; `refusal` is one of the kinds below, and `detail` is text that names no credential, host, path, or row.

| Kind | HTTP | Condition |
| --- | --- | --- |
| `malformed_request` | 400 | the body fails Section 4.4 |
| `unknown_route` | 404 | the path is none of Section 4.1's |
| `method_not_allowed` | 405 | the path is known and the method is not |
| `adapter_unavailable` | 503 | `/v1/ask` and no adapter is configured, or the adapter call fails |
| `database_unavailable` | 503 | a route that opens a connection could not |
| `runtime_fault` | 500 | the runtime raised one of the `mvp-v0.1` Section 4.4 faults outside the seven statuses |

A refusal is never HTTP 200, and a result is never anything else. The two cannot be confused by a client reading the status code alone, and a client reading the body alone tells them apart by the presence of `result`.

`GET /v1/health` returns HTTP 200 and `{"contracts": {identifier: version, …}, "adapter_configured": boolean}` for exactly three: `api-v0.1`, `mvp-v0.1` and `entity-discovery-v0.1`. `export-v0.1` is not among them — it is not in this tree and no route here serves one; a later route that does adds it to the map, as part of the Section 9 path-A minor version. It opens no connection, so it says nothing about the database; a readiness probe that does is a Milestone 5 row in Section 9.

### 4.6 The presentation surface

Charter Section 9 admits a minimal UI "only if it materially supports evaluation or use"; the owner's record that it does is decision C on #169, and Section 8 carries its row. The UI is a **client of Section 4.1** and nothing more: it sends the five routes, receives the envelope, and has no other path to the runtime or the database. Its obligations are Charter Section 3.1 and Section 9's "rendering does not add or alter facts", applied to a screen:

1. **It shows the evidence.** For every result it displays the status, every `limitations` entry's kind and detail, and the `evidence_bundle` and `source_trace` keys Charter Section 3.1 names — source scope, template identifier and version, bound parameters, row count, source trace, limitations — and for a discovery result the `registry_digest`, `method_identifier`, and per-candidate `match_tier`, `matched_text`, `match_kind` and alias provenance. It may collapse them; it may not omit them.
2. **The answer text is `rendered`, verbatim.** Where `rendered` is `null` the UI shows no prose that states a fact. Fixed labels — a field name, a heading, "no reference was resolved" — are not prose that states a fact.
3. **A candidate list is not an answer.** It is shown in rank order with every candidate's fields, none hidden, none pre-selected, none highlighted as likely, and under the `limitations` entry that says no reference was resolved. A `resolved` outcome is shown with its tier and matched text.
4. **A selection is a person's act, and a prefilled field is not.** A `/v1/select` request is sent only on an explicit act that names one listed rank and one `target_route` the person chose from the permitted values. A UI never submits a form itself, and every prefilled value is visible and editable before submission.

   **What may be prefilled is decided by what a wrong value would do, not by who produced it.** A UI may prefill:

   | Field | Prefill | Why |
   | --- | --- | --- |
   | the discovery `term` | from the person's own `request_text` | Transcription: they see their own words and accept or edit them, so the term sent is one they approved. Leaving it empty would ask them to retype what they already typed. |
   | a scope dimension | **only** from a `proposal.arguments` value named in `proposal.verbatim` | The person put that text in the request. A value **not** in `proposal.verbatim` may be displayed, labelled as the adapter's unverified proposal, but **may not be a default in the field** — see below. |
   | `entity_kind` | from the Section 4.3 table | A wrong kind fails closed: discovery searches the other kind and returns `not_found`, or returns candidates whose names the person reads and rejects. It cannot produce a fact about the wrong thing. |
   | `target_route` | **only** where the selected candidate's `entity_kind` permits exactly one — that is, a `message` candidate | Never from `proposal.route`. For a `signal` candidate two routes are permitted, and `entity-discovery-v0.1` Section 4.8 makes `target_route` required rather than derived precisely there, because deriving it "would pick for the caller, and the pick would be silent". Both are offered with no default. |

   **An unverified scope value may not be a default because a wrong scope is the one error this system exists to prevent.** It returns true facts about the wrong snapshot, and nothing in the result says so: the scope was complete, so no candidate list appeared and `mvp-v0.1` Section 7's explicit-selection entry never fires. A person who never named a snapshot, shown four plausible pre-filled boxes, submits them. That is the runtime supplying an unrecorded scope (Charter Section 3.6, `mvp-v0.1` Section 4.2) with a model and a form in between. The other three rows above fail closed or are the person's own text, which is why they are permitted.
5. **A negative status is rendered as itself.** `not_found`, `ambiguous`, `coverage_gap`, `unsupported`, `invalid_request`, `needs_entity_discovery` are results. The UI does not retry, rephrase, or discover on the person's behalf, and does not present a surface refusal as a result.
6. **It shows `proposal` as a proposal**, if at all: labelled as the adapter's output, never as a bound parameter or a fact.
7. **It adds no value that the response does not contain**: no unit conversion, no rounding, no summary, no reordering of rows or candidates.

### 4.7 The local stack

One command starts a PostgreSQL 17 instance, provisions it through the `mvp-v0.1` Section 3.4 path — the same scripts, the same lexical order, the same abort, the same fixture loader, as the provisioning identity — and starts the surface as the runtime identity. The surface process never holds the provisioning credentials. The adapter credential is read from the environment and is optional; absent, `/v1/ask` refuses per Section 4.5 and every other route works. No credential, host or password appears in the repository beyond the job-scoped non-secret values the CI workflows already carry.

Decision D on #169 fixes why this is a contract obligation and not an implementation note: Charter Section 9's Milestone 5 gate forbids "a second schema, fixture meaning, SQL-template behavior, or fallback runtime", so the local stack must be the path the deployment later reuses. The mechanism — Docker Compose or another — is bounded by `mvp-v0.1` Section 3.4 and is not fixed here.

## 5. Outcome coverage

**This contract produces no status family of its own.** A response carries through, unchanged, one of the seven `mvp-v0.1` Section 5 statuses or the seven `entity-discovery-v0.1` Section 5 statuses, under the condition that contract fixes. The one thing the surface adds is the six-kind refusal vocabulary of Section 4.5, which is a property of the HTTP exchange, not of a request's outcome, and which never appears in a `result`.

| Route | Status vocabulary of `result` |
| --- | --- |
| `/v1/query`, `/v1/ask` | `mvp-v0.1` Section 5, all seven |
| `/v1/discover` | `entity-discovery-v0.1` Section 5, all seven |
| `/v1/select` | `entity-discovery-v0.1` Section 5 for a refused selection; `mvp-v0.1` Section 5 for a dispatched one — `entity-discovery-v0.1` Section 4.8 |

## 6. Determinism

- Two requests with byte-identical bodies to the same route, against the same provisioned database and the same registry, produce byte-identical response bodies — Section 4.2 admits no timestamp or identifier, and Section 4.4 fixes one serialization.
- `/v1/ask` is excluded from that guarantee **at step 1 only**: `mvp-v0.1` Section 6 keeps the adapter outside the determinism guarantee, and the guarantee here applies from the proposal onward. Two identical proposals produce identical results.
- The surface reorders nothing: rows in template order, candidates in rank order, `limitations` in the order the runtime produced them, candidate scopes in `TPL_SNAPSHOT_CANDIDATES_V1` order.
- The surface holds no state between requests, so no request's outcome depends on an earlier one.

## 7. Evidence obligations

This contract adds no evidence key and requires none. Its obligation is in both directions:

- **Every key** `mvp-v0.1` Section 7 and `entity-discovery-v0.1` Section 7 require on a result — the `selection` record and the `discovery_*` keys of a dispatched selection included — is present in `result` with the value the runtime produced. Section 4.4's `null`-never-omitted rule is what makes absence visible rather than ambiguous.
- **Nothing in `result` is the surface's.** `rendered`, `proposal` and `contract` sit beside it in the envelope. They are not evidence, they are not in `evidence_bundle`, `source_trace` or `limitations`, and Section 4.6 forbids a presentation surface to treat `proposal` as one.

A response names no credential, host, local path, or environment variable. The one role name it carries is the `read_only_safeguards.role_name` that `mvp-v0.1` Section 7 already requires in every evidence bundle.

## 8. Acceptance evidence

Each obligation is either an automated assertion over registered inputs or a recorded human decision with named evidence, as Charter Section 9 requires. Two Milestone 4 gate items are this contract's and are marked: **`G2`** "rendering does not add or alter facts" and **`G3`** "representative workflows complete end to end with traceable failures". `G1`, exported values, is `export-v0.1`'s.

| Obligation | Acceptance evidence |
| --- | --- |
| Section 4.1 routes and dispatch | Automated. `WF-001` to `WF-006`; `WF-014`, which asserts that `entity_discovery` and `entity_selection` on `/v1/query` are `unsupported` from the fact-route entry point and that a name outside the five-route union is too; a test that no route accepts a key Section 4.1 does not name. |
| Section 4.2 envelope | Automated. Every `WF-*` asserts the exact key set of its response; `WF-007` asserts `proposal` present on `/v1/ask` and `WF-001` asserts it absent elsewhere. |
| Section 4.3 orchestration order | Automated. `WF-007` to `WF-009` with an injected proposal; a test that the runtime is not called when revalidation refuses; `WF-010` that nothing is called when no adapter is configured. |
| Section 4.3 the verbatim check the surface applies | Automated. `WF-008`: an injected proposal whose scope values are absent from the request text yields a `proposal.verbatim` that names none of them, and one whose values are present names them; a test that `proposal.verbatim` is computed by the `mvp-v0.1` Section 4.6 rule and not by revalidation's return. |
| Section 4.3 the surface never joins | Automated, **`G3`**. `WF-003` and `WF-008` assert that the response to a `needs_entity_discovery` contains exactly that result and that no discovery template executed in producing it; a test over every route that at most one runtime call occurs per request. |
| Section 4.4 serialization | Automated. A round-trip test: every `FX-*` and `DX-*` result serialized and read back equals the original; a test that a numeric column value survives as its stored decimal text. |
| Section 4.5 refusals | Automated. `WF-010`, `WF-011`; a test that a refusal body carries exactly two keys and that `detail` matches no host, path or credential pattern the sensitive-string scan defines. |
| Section 4.6 presentation, **`G2`** | Automated where a screen can be asserted: a test that every value the UI displays as a fact is present in `result` or `rendered` (`mvp-v0.1` Section 4.9 Group E, check `E1`, applied to the UI); a test that the candidate list is rendered in rank order with no candidate omitted and no selection state before an act; a test that a `/v1/select` request is not issued without an act naming a rank; **and the obligation-4 prefill tests — that no scope field is prefilled from a value outside `proposal.verbatim`, that `target_route` carries no default for a `signal` candidate, and that the term field carries the person's own request text.** **Recorded human decision** for decision C on #169 — that the UI materially supports use — cited in the Milestone 4 acceptance record with the owner's stated reason. |
| Section 4.7 local stack | Automated. The stack provisions from a clean state and `WF-001` to `WF-013` pass against it; a test that the surface process holds no provisioning credential. **Recorded human decision** for decision D on #169, cited in the Milestone 4 acceptance record. |
| Section 6 determinism | Automated. `WF-012`. |
| Section 7 evidence | Automated. For every `WF-*` step, the key set of `result.evidence_bundle`, `result.source_trace` and each `result.limitations` entry equals the key set of the runtime's own result. |
| The #169 decision point on export | **Recorded human decision**, after the UI has been used: path A implements `export-v0.1` and Section 9's serving row; path B is an ADR under Charter Section 10. Milestone 4 does not close before one of the two is recorded. |

### 8.1 Required workflow fixtures

A workflow fixture is a sequence of surface requests with the expected response at each step, and a later step may cite a value from an earlier response — `candidate_set_id`, a resolved reference. Every identifier is `SAMPLE_*`. Where a step's inputs are those of a registered `FX-*` or `DX-*` case, the fixture names it rather than restating it; the expected `result` at that step is that case's registered result, serialized. `/v1/ask` steps **inject the proposal**: the fixture supplies what the adapter returned, so the step is deterministic and costs nothing, and what it tests is steps 2 and 3 of Section 4.3. That is the same division `tests/test_adapter_revalidation.py` already makes. The adapter itself is measured by `mvp-v0.1` Section 8.3, not here.

| ID | Steps | Expected |
| --- | --- | --- |
| `WF-001` | `/v1/query` with `FX-001` | 200, `success`; `rendered` equals the runtime's Section 4.8 render; no `proposal` |
| `WF-002` | `/v1/query` with `FX-105` | 200, `ambiguous`, both candidate scopes in `result`; the workflow ends |
| `WF-003` | `/v1/query` with `FX-111`; then `/v1/discover` with `DX-017`'s discovery arguments; then `/v1/select` citing the returned `candidate_set_id`, `DX-017`'s rank and `target_route` | `needs_entity_discovery` with no discovery executed; `candidates` with `candidate_set_id`; `success` with the `selection` record and the `selected_via_candidates` entry |
| `WF-004` | `/v1/discover` with `DX-001`; then `/v1/query` naming the resolved reference on `message_facts` | `resolved`, tier 1; `success` |
| `WF-005` | `/v1/discover` with `DX-015` | `not_found` with the not-in-registry entry; the workflow ends and nothing else was executed |
| `WF-006` | `/v1/select` with `DX-018` | `invalid_request` from `entity-discovery-v0.1`; no fact template executed |
| `WF-007` | `/v1/ask` with the injected proposal of `FX-001`'s canonical phrasing | 200, `success`; `proposal` present and equal to the injected one |
| `WF-008` | `/v1/ask` twice with an injected proposal naming a route, a complete scope and no lookup key (an `mvp-v0.1` Section 8.3 family `D` case): once where the request text contains the four scope values, once where it contains none of them | `needs_entity_discovery` both times, no discovery executed; `proposal.verbatim` names all four scope arguments in the first and none in the second |
| `WF-009` | `/v1/ask` with an injected `unsupported` proposal | `unsupported`, producing layer `adapter` |
| `WF-010` | `/v1/ask` with no adapter configured | 503 `adapter_unavailable`; no result; the runtime was not called |
| `WF-011` | a body that is not an object; a body with an extra key; an unknown path; `GET /v1/query` | 400, 400, 404, 405; each body exactly `{"refusal", "detail"}` |
| `WF-012` | `WF-001`'s request twice | byte-identical bodies |
| `WF-013` | `GET /v1/health` | 200; the versions of `api-v0.1`, `mvp-v0.1` and `entity-discovery-v0.1`, and no fourth entry; no connection opened |
| `WF-014` | `/v1/query` with `route` = `entity_discovery`, with `entity_selection`, and with a name outside the five-route union | `unsupported` in all three, producing layer `runtime`, no discovery template executed and no fact template executed |

`WF-003` is the whole target path — the one that has never run end to end — and is the reason this contract exists. `WF-008` is its natural-language start, tested separately because the `mvp-v0.1` Section 4.7 baseline can produce no `needs_entity_discovery` and a deterministic fixture therefore cannot reach it through a real proposer.

### 8.2 Deferral of the acceptance evidence

Section 10 permits this contract to be accepted with its acceptance evidence explicitly deferred with a named owner. Every automated row above is an assertion over an implementation that does not exist on the date of acceptance; requiring it first would make acceptance unreachable, because [Contract Shape Framework](README.md) Section 2.1 forbids implementing against a contract that is not accepted. Named owner: the repository owner. Each automated row is discharged on the pull request that introduces the behavior it governs, as a merge condition of that pull request; each recorded decision is discharged in the Milestone 4 acceptance record. No implementation pull request may cite this section as a reason to omit the evidence its slice owes.

**No numeric threshold is registered and no `registered_at` is recorded.** `G2` and `G3` are non-numeric, so there is nothing for Charter Section 9's before-the-run rule to order, and a number here would be scope the Charter does not ask for.

## 9. Deferred decisions

| Decision | Owner |
| --- | --- |
| **Serving an export**: the route, request and response shape that hands over an `export-v0.1` document set, and how a Section 4.9 refusal of that contract reaches a caller | The #169 decision point, after the UI has been used. **Path A**: a minor version of this contract adds the route, against an accepted `export-v0.1`. **Path B**: an ADR under Charter Section 10 moves TSV export out of Milestone 4, and this row closes with it. |
| **Where the discovery term comes from** when `/v1/ask` reports a missing entity | Fixed at `0.1.0`: the caller supplies it (Section 4.3). Two alternatives were declined, and are recorded so the choice is legible. *Extending the adapter to return a normalized term* — which Charter Section 3.3 permits an LLM to do — changes the Section 4.6 vocabulary and reopens the Milestone 2 comparison; a later minor version may take it, with that comparison re-run first. *The surface using the request text as the term* — a retrieval-quality question `entity-discovery-v0.1` Section 4.10's registered set does not measure; Charter Section 3.5 says to measure before adopting. **What Section 4.6 permits is neither of these**: a UI showing the person their own request text in an editable term field takes no view on whether that text is a good term, and the term that is sent is the one the person approved. |
| Whether `entity-discovery-v0.1` Section 4.12 is patched to say its "triggers no discovery" binds the runtime and not a caller (Section 3.3, reading 1) | The repository owner, under that contract's Section 10. Implementation does not depend on the answer. |
| Whether `mvp-v0.1` Section 7 is patched to say a rejected proposal may be reported outside the evidence bundle, labelled as such (Section 3.3, reading 2) | The repository owner, under `mvp-v0.1` Section 10. Implementation does not depend on the answer: `proposal` is outside the bundle either way. |
| Whether `mvp-v0.1` Section 4.6 is patched to fix the order revalidation checks in, so that the verbatim-token rule is reached on a `needs_entity_discovery` proposal (Section 3.3, reading 3) | The repository owner, under `mvp-v0.1` Section 10. Implementation does not depend on the answer: Section 4.3 has the surface apply the rule itself, and `proposal.verbatim` reports the same thing under either ordering. Patching the order would make the key redundant, not wrong. |
| Whether `mvp-v0.1` Section 7 and `entity-discovery-v0.1` Section 7 are patched to name their result payload fields — `status`, `rows`, `resolved`, `candidates`, `candidate_scopes` (Section 4.4) | The repository owner, under each contract's Section 10. Implementation does not depend on the answer: Section 4.4 fixes the wire names for this surface either way, and it claims no provenance it does not have. |
| Whether `entity-discovery-v0.1` Section 3.3 extension 1 is patched to say the union fixes which names are registered rather than which endpoint dispatches them (Section 3.3, reading 4) | The repository owner, under that contract's Section 10. Implementation does not depend on the answer: `/v1/query` is a fixed dispatch either way, and `WF-014` registers the outcome. |
| Authentication, authorization, rate limiting, TLS termination, a database-readiness probe, structured logs and metrics | Milestone 5 deployment contract. Section 4.2 keeps the body free of anything those would add. |
| Whether the Milestone 5 deployment reuses the Section 4.7 stack's images and definitions | Milestone 5 deployment contract, bounded by Charter Section 9's "no second schema, fixture meaning, SQL-template behavior, or fallback runtime". |
| A copy action, a history of the person's requests, and any presentation convenience beyond Section 4.6 | A later patch or minor version, after the surface has been used (#169). |
| Streaming, pagination, or batching of responses | **Not opened.** Every registered template carries its own row limit (`mvp-v0.1` Section 4.4) and a candidate list is at most `k`, so no response is unbounded. |

No row above is open in the sense that this contract needs it to be implementable. Sections 4.1 through 4.7 are complete as they stand.

## 10. Change control

- This contract is `Proposed`. Under [Contract Shape Framework](README.md) Section 7 it is amended by an ordinary contract-only pull request until accepted; after acceptance, a change that does not weaken a Charter or ADR invariant produces a new version with a recorded human decision.
- Adding a workflow fixture that exercises an existing obligation is a patch version change. Adding or removing a route, an envelope key, a refusal kind, or a presentation obligation is a minor version change and requires a fresh independent design review.
- Filling the serving-an-export row of Section 9 is a minor version change and may not precede `export-v0.1`'s acceptance.
- A change that would let the surface construct a discovery request or a selection on a caller's behalf, fall back to another proposer, or add or alter a value in a rendering is not a contract-level change: it would weaken Charter Sections 3.1, 3.3 or 3.4 and requires an ADR, a Charter update where material, and a recorded human decision.
- This contract may not move to `Accepted` until the repository owner records the Framework Section 6 step-4 review on its pull request. The Section 8 acceptance evidence is deferred with a named owner in Section 8.2.
- A superseded version is retained with a `Superseded by` status rather than deleted.
