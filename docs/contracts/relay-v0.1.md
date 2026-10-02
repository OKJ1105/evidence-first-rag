# Chat Relay Contract v0.1

## 1. Identifier and version

**Identifier:** `relay-v0.1`

**Version:** `0.4.0` — the identifier names the document; the version tracks its obligations. The line moved to `0.4.0` with the implementation slice that serves it ([#293](https://github.com/OKJ1105/evidence-first-rag/issues/293)), not with the text, as `api-v0.1` `0.2.0` did ([#212](https://github.com/OKJ1105/evidence-first-rag/issues/212)): the served version must be one the relay conforms to, and `tests/test_relay.py` holds the two in step. The version changes when any observable obligation in Section 4, 5, 6, or 7 changes. Adding or removing a route, a request or response key, a refusal kind, or a page obligation, or changing a registered text or cap, is a minor change. **Enabling a tool is never a minor change**: Section 10. Adding a registered case that exercises an existing obligation is a patch change. Removing or weakening an obligation is not permitted at the contract layer; see Section 10.

This contract is the one [ADR-0005](../adr/0005-the-chat-relay-is-a-host-this-project-operates.md) names as its next slice: the **relay**, the endpoint the portfolio site's chat calls and the only component that holds the Anthropic key. In [Contract Shape Framework](README.md) Section 5 terms it is a route contract for a surface *above* [mcp-v0.1](mcp-v0.1.md). It registers no entity, no template, no status family, no tool, and no route on the runtime.

It is a **separate document, not an amendment** to `mcp-v0.1`, `api-v0.1`, `entity-discovery-v0.1` or `mvp-v0.1`, each of which is `Accepted`. Nothing here changes a word of any of them.

## 2. Status

**Status:** `Accepted 2026-09-25`

This contract is binding on implementation from that date under [Contract Shape Framework](README.md) Section 2.1. The repository owner reviewed it with ADR-0005 and `deploy-v0.1` in one sitting, recorded the open decisions on [#210](https://github.com/OKJ1105/evidence-first-rag/issues/210#issuecomment-5828675894) (the model is `claude-haiku-4-5`), and merged it in [#209](https://github.com/OKJ1105/evidence-first-rag/pull/209). The acceptance is the owner's merge of the pull request that moves this line ([#218](https://github.com/OKJ1105/evidence-first-rag/issues/218)). No milestone gate is involved (Framework Section 2.1).

**`0.2.0`** is binding from the owner's merge of [#248](https://github.com/OKJ1105/evidence-first-rag/pull/248), which carries the fresh independent design review Section 10 requires for a cap change and the owner's figures recorded on [#247](https://github.com/OKJ1105/evidence-first-rag/issues/247#issuecomment-5884648135).

**`0.3.0`** is binding from the owner's merge of the pull request that closes [#249](https://github.com/OKJ1105/evidence-first-rag/issues/249). That pull request carries the fresh independent design review Section 10 requires for a cap change, and the owner's decision recorded on #249.

**`0.4.0`**'s text is accepted by the owner's merge of the pull request that closes [#224](https://github.com/OKJ1105/evidence-first-rag/issues/224). That pull request carries the fresh independent design review Section 10 requires for a minor version. The version line moved, and the text became binding on what is served, with the implementation slice ([#293](https://github.com/OKJ1105/evidence-first-rag/issues/293)). It adds **one obligation**: the CORS preflight and response header for the one registered origin (Section 4.1). It follows the shape `api-v0.1` `0.2.0` took for `/v1` on the owner's decision (a) on [#210](https://github.com/OKJ1105/evidence-first-rag/issues/210#issuecomment-5828675894). Without it no browser can call `POST /chat`, because `deploy-v0.1` Section 4.5 allows the page's origin and Section 4.1 at `0.3.0` refused the preflight that a cross-origin JSON `POST` requires. **It removes no obligation.** Every refusal, cap and check is unchanged. An `OPTIONS` request that is not an admitted preflight is still `method_not_allowed`, and a `POST` receives the same body with or without an `Origin`.

**How this document reached here.** Drafted on [#208](https://github.com/OKJ1105/evidence-first-rag/issues/208) against ADR-0005 ([#207](https://github.com/OKJ1105/evidence-first-rag/pull/207)). The budget figure was amended to 8,000 JPY in [#217](https://github.com/OKJ1105/evidence-first-rag/pull/217) while still `Proposed`. **`0.2.0`** lowers the Section 4.2 size bounds, the body from 128 KiB to **32 KiB** and a relay turn from 32 KiB to **16 KiB**, so that Section 8.3's ceiling can be positive under the budget. The committed 2026-09-29 computation ([#244](https://github.com/OKJ1105/evidence-first-rag/issues/244)) put the fixed cost at 6,733.50 JPY a month and the per-call bound at 128 KiB above one day's share of what is left, so every ceiling was zero. The owner chose this option on 2026-09-29, over cutting the fixed cost, raising the budget, or capping tool rounds, and fixed the figures on [#247](https://github.com/OKJ1105/evidence-first-rag/issues/247#issuecomment-5884648135) once the review of [#248](https://github.com/OKJ1105/evidence-first-rag/pull/248) showed that a relay turn carrying a maximal `discover_entity` result is 14,918 bytes, so a 12 KiB turn bound would have made it impossible to send back. **It removes no obligation**: every refusal and check is unchanged, and a smaller bound refuses more requests, never fewer. **`0.3.0`** changes what bounds spend (Section 8.3). At the 32 KiB body, the per-call worst case is 13.91 JPY at one tool call and 61.11 at five ([cost record](../acceptance/milestone-5/cost-2026-09-29-body-32k.json)). A count derived from it leaves one to three calls a day, so the owner chose on 2026-09-29 ([#249](https://github.com/OKJ1105/evidence-first-rag/issues/249), [ADR-0006](../adr/0006-relay-spend-is-bounded-by-the-provider-workspace.md)) to bound spend with the Anthropic workspace's monthly spend limit instead. The daily ceiling becomes a guard against exhaustion. **It removes no obligation**: the relay still fails closed without a registered ceiling, and spend still has a registered bound.

**ADR-0005's status line still reads `Proposed`.** The owner adopted it as drafted on [#210](https://github.com/OKJ1105/evidence-first-rag/issues/210#issuecomment-5828675894) and merged it in [#207](https://github.com/OKJ1105/evidence-first-rag/pull/207). This is the same standing ADR-0004 has under the accepted `mcp-v0.1`: this repository's ADR status lines have not been moved on merge. A change to ADR-0005 that removes an item this contract implements is a change to this contract's authority, and it reopens this contract.

## 3. Scope

### 3.1 What this contract fixes

- **One route**, `POST /chat`: its request body, the Messages API call the relay makes, and its response body; and **the CORS preflight** that lets a browser on the one registered origin call it (Section 4.1, `0.4.0`).
- **The host configuration**: the model, the system prompt as a registered text, `max_tokens`, and the toolset that enables `discover_entity` alone (ADR-0005 item 2).
- **The scope check** (ADR-0005 item 4): which scope values in a `discover_entity` call are the person's own, computed by the relay on every response.
- **The caps and refusals** (ADR-0005 item 5), and **what the relay records** (item 6).
- **The page obligations** (ADR-0005 item 3): what a client of this route must and must not render.

### 3.2 What this contract does not fix

- **The page itself.** It lives in the portfolio site's repository. This contract fixes the obligations that page must meet, as `api-v0.1` Section 4.6 fixes them for the Milestone 4 page, and that repository's slice carries their acceptance evidence (Section 8.2).
- **Hosting, identities, secrets, networking, TLS, CORS origins, and logs retention.** The deployment contract fixes them. This contract fixes only the two identity facts ADR-0005 depends on (Section 4.8).
- **What the model writes.** ADR-0005 item 3: an instruction, not a check. This contract fixes where the prose may appear, not what it says.
- **Streaming.** A response is returned whole. A later minor version may add streaming.

### 3.3 What this contract inherits

| Inherited | From |
| --- | --- |
| The three tools, their results, their descriptions and their refusals | `mcp-v0.1` Sections 4.1 to 4.4 |
| Which routes a page calls for a person's choice, and their envelopes | `api-v0.1` Sections 4.1, 4.2 |
| The verbatim rule, byte-exact over the identifier alphabet `A-Za-z0-9_.-` | `api-v0.1` Section 4.3 |
| The page obligations Section 4.7 restates for this surface | `api-v0.1` Section 4.6 obligations 1, 3, 4, 5 and 7 (the evidence region), and obligation 2's "`rendered`, verbatim" for a fact. Obligation 2's "no prose" and obligation 7's "no summary" are displaced for the prose region by the Charter Section 3.1 carve-out (ADR-0005 item 3). Obligation 6 does not arise: no `proposal` reaches this page. |
| The candidate list, the candidate-set digest, and what a selection re-runs | `entity-discovery-v0.1` Sections 4.6 to 4.8 |

## 4. Normative requirements

### 4.1 The route

| Method and path | Request body | Response |
| --- | --- | --- |
| `POST /chat` | `{"messages"}` | Section 4.4 |

The path is outside `/v1`, which `api-v0.1` Section 4.1 fixes exhaustively, and outside `/mcp`. Any other method on the path is refused as `method_not_allowed`, with one exception.

**The exception: a CORS preflight** (`0.4.0`). An `OPTIONS` request to `/chat` is admitted only when all three of these hold:

- it carries an `Origin` header equal to the **registered origin**;
- it carries `Access-Control-Request-Method: POST`;
- a registered origin is configured.

An admitted preflight is answered **before any cap is checked**, with HTTP 204 and no body, and with these headers:

- `Access-Control-Allow-Origin` equal to that origin;
- `Access-Control-Allow-Methods: POST`;
- `Access-Control-Allow-Headers: content-type`;
- `Vary: Origin`.

The registered origin is a single value read from the process environment as `EFR_CORS_ORIGIN`, never a wildcard. The deployment contract sets it (`deploy-v0.1` Section 4.6), and while it is unset no preflight is admitted. An `OPTIONS` request to `/chat` that fails any of the conditions is `method_not_allowed`, exactly as at `0.3.x`: no origin configured, another origin, or the request-method header absent or naming another method.

**On a `POST` from the registered origin**, every response carries `Access-Control-Allow-Origin` equal to that origin and `Vary: Origin`, **refusals included**, and is otherwise the same response it would be without an `Origin`. The refusals must be included, because a browser withholds a response that lacks the header from the page. A `daily_ceiling_reached` the page could not read would reach the person as a network failure, which P7 forbids. A `POST` from any other origin, or with no `Origin`, carries `Vary: Origin` and **no** `Access-Control-Allow-Origin`. `Vary` is sent on every `POST`, because the response differs by `Origin`. A shared cache that ignored it could hand the registered origin a copy without the header, and the browser would withhold that copy from the page.

**A preflight is not a request in Section 4.6's sense.** It reaches no cap, consumes none, and makes no model call. Its cost is the deployment's fixed cost, as for `surface`'s unauthenticated routes (`deploy-v0.1` Section 4.5). It is not a refusal kind and not a response: it carries no body, so a client reading bodies meets only Section 4.4's response and Section 4.6's refusals, as before.

**CORS is not access control.** It decides which page a *browser* lets read the reply. A client that is not a browser sends no preflight and reads every reply, as at `0.3.x`. What bounds such a client is Section 4.6's caps, which this version does not change.

### 4.2 The request

`messages` is the whole conversation as the page holds it, oldest first. **The relay holds no conversation**: the Messages API is stateless, and every check in Section 4.5 is computed from the request and the response alone (ADR-0005 item 6).

| Element | Shape |
| --- | --- |
| a person's turn | `{"role": "user", "content": "<text>"}` — a string, 1 to 500 characters |
| a relay turn | `{"role": "assistant", "content": [...]}` — **exactly** the `content` array a previous `POST /chat` response returned, unchanged |

The list alternates, starts with a person's turn and ends with one.

**Size.** The serialized request body is at most **32 KiB**, and each relay turn's serialized `content` at most **16 KiB**. These bound what one model call can be sent, which is what makes Section 8.3's per-call bound a bound: without them a client could return relay turns of any size, and a ceiling that counts calls would bound nothing. The relay-turn bound sits below the body bound so that `RL-019` observes it on its own, and above a relay turn carrying one maximal `discover_entity` result (Section 4.6 of `entity-discovery-v0.1`, k = 10), so that such a turn can be sent back and a candidate chosen from it (`RL-010`, P5), **provided the model's own `text` in that turn fits the about 1.4 KiB that remain**. That headroom is shared with the reply, and `max_tokens` (Section 4.3) can produce more. That size counts the result's `content` text once; whether the connector also carries its `structuredContent` into the turn is not yet observed, and if the first deploy shows that it does, the bounds are raised by a further minor version.

**What the 32 KiB bound costs a conversation.** The whole conversation, tool results included, is sent on every request, and the relay never truncates it (Section 4.3). A conversation that has grown past 32 KiB is refused as `malformed_request`, and the person starts a new one. A relay turn can exceed 16 KiB on its own in two ways: the model called the tool more than once with large results, or it wrote a long reply after one maximal result (`RL-022`). Either way that conversation cannot continue past that turn. The owner kept these bounds with this residual stated, over raising them, on [#247](https://github.com/OKJ1105/evidence-first-rag/issues/247#issuecomment-5884948455). Both are the accepted price of a smaller per-call worst case, which is what the spend limit of Section 8.3 is measured against.

**The relay cannot verify that a relay turn is one it returned**, because it holds no conversation. A client may forge one. The size bound limits what that costs. The scope check reads only person's turns (Section 4.5). And a fact never comes from a relay turn on the page (Section 4.7, P2). So a forged relay turn can change what the model writes, which is prose, and nothing the page renders as a fact.

**`malformed_request`**, refused before any model call, is exactly: a body that is not a JSON object with the one key `messages`; a role outside the two; a person's turn that is not a string of 1 to 500 characters; a relay turn containing a block type outside Section 4.3's list; turns that do not alternate or do not start and end with a person's turn; or a body or relay turn over the size bound. **The number of person's turns is not a shape error**: more than 10 is `conversation_limit` (Section 4.6).

**The page sends no `/v1` result to the model.** A fact the person obtains by clicking (Section 4.7, P3) is not appended to the conversation. The model sees only what its own tool returned.

### 4.3 The call the relay makes

For every accepted request, exactly one Messages API call, with **exactly** these parameters and no others:

| Parameter | Value |
| --- | --- |
| `model` | `claude-haiku-4-5` (the owner's decision, Section 9) |
| `max_tokens` | `1024` |
| `system` | the registered text in Section 4.9, byte for byte |
| `messages` | the request's `messages`, unchanged |
| `mcp_servers` | one entry: `{"type": "url", "url": "<this deployment's public /mcp URL>", "name": "evidence-first-rag"}` |
| `tools` | one entry: `{"type": "mcp_toolset", "mcp_server_name": "evidence-first-rag", "default_config": {"enabled": false}, "configs": {"discover_entity": {"enabled": true}}}` |

The beta is not a body parameter. It is sent as the `anthropic-beta` request header, with the value `mcp-client-2025-11-20` and nothing else.

**The toolset enables `discover_entity` alone** (ADR-0005 item 2). `query_facts` and `select_candidate` stay disabled, and no other tool of any kind is sent. The relay adds no retry. A failed call is refused as `model_unavailable` (Section 4.6). The relay never retries with a different model, never truncates the conversation to fit, and never writes a reply of its own.

Content blocks the relay passes through are `text`, `mcp_tool_use` and `mcp_tool_result`. A response containing any other block type is `model_unavailable`, because the relay cannot vouch for what it did not configure.

### 4.4 The response

HTTP 200, a JSON object with exactly these keys:

| Key | Value |
| --- | --- |
| `content` | the Messages API response's `content` array, **unchanged**: text blocks, and `mcp_tool_use` / `mcp_tool_result` blocks with the `mcp-v0.1` results inside them verbatim |
| `stop_reason` | the Messages API `stop_reason`, unchanged |
| `scope_checks` | Section 4.5 |
| `relay` | `{"identifier": "relay-v0.1", "version": "<version>", "model": "<the model string of Section 4.3>"}` |

The relay rewrites, filters, summarizes and reorders nothing in `content`. It adds no key to a block and removes none.

### 4.5 The scope check

For every `mcp_tool_use` block in `content` that calls `discover_entity`, `scope_checks` carries one entry, in block order:

`{"tool_use_id", "person_stated": [...], "not_person_stated": [...]}`

Each of the four scope dimensions (`project_code`, `revision_label`, `network_name`, `snapshot_label`) present in the call's `arguments` is listed in exactly one of the two lists. A value is in `person_stated` when it is **verbatim**, by the `api-v0.1` Section 4.3 rule, in the text of **any person's turn** in the request. Otherwise it is in `not_person_stated`. The relay computes this from the request and the response and nothing else.

**This is the check ADR-0005 item 4 names, and it is stricter than that item's minimum.** It flags any scope value the person did not write, whether the model took it from an `ambiguous` candidate list or invented it. The page acts on it (Section 4.7, P5). The relay itself refuses nothing on this ground: the result is the runtime's and is passed through, and the gate is what the page may offer a person to click.

### 4.6 Caps and refusals

A refusal carries no `content`. It is HTTP JSON `{"refusal", "detail"}`, with `detail` naming no credential, host, path, key or message text.

| Kind | HTTP | Condition |
| --- | --- | --- |
| `malformed_request` | 400 | Section 4.2 |
| `method_not_allowed` | 405 | Section 4.1, including an `OPTIONS` request that is not an admitted preflight |
| `conversation_limit` | 422 | the request carries more than 10 person's turns |
| `rate_limited` | 429 | more than **6** requests in any 60 seconds, or more than **60** in a UTC day, from one client address |
| `daily_ceiling_reached` | 503 | the relay has already made the registered number of model calls in the current UTC day (Section 8.3) |
| `model_unavailable` | 502 | the Messages API call failed, timed out after 60 seconds, or returned a block type outside Section 4.3's list |

**Every cap is checked before the model call**, so a refused request costs nothing. **A numeric daily ceiling is registered before the relay serves any request**, as a configuration value the deployment contract carries. While none is registered, the relay refuses every request with `daily_ceiling_reached`: it fails closed, and it never runs uncapped. The daily ceiling is a count of model calls, not an estimate of spend. Spend is bounded by the API key's workspace spend limit, and Section 8.3 registers both ([ADR-0006](../adr/0006-relay-spend-is-bounded-by-the-provider-workspace.md), which supersedes ADR-0005 item 5's "backstop" for the Console limit). The Azure budget alert (8,000 JPY per month, [#205](https://github.com/OKJ1105/evidence-first-rag/issues/205#issuecomment-5829415863)) remains a backstop. **The relay's API key belongs to an Anthropic Console workspace that holds no other key, with a monthly spend limit set as Section 8.3 fixes**; this is an obligation on the deployment, and Section 8.3 names its evidence.

### 4.7 The page obligations

A page that renders a `POST /chat` response is the relay's client, and these obligations are on it. They carry `api-v0.1` Section 4.6 onto a surface that section does not reach (ADR-0005 item 3).

- **P1. Two regions.** The model's `text` blocks are rendered only in a region labelled as the assistant's words. A fact, a candidate, a scope or a status is rendered only in a separate evidence region, and never in the prose region.
- **P2. A fact comes only from a route result.** A fact is rendered only from a `/v1/select` or `/v1/query` response the page itself received, with its `rendered` string verbatim and its evidence under `api-v0.1` Section 4.6 obligations 1, 2 and 7. Nothing in a `text` block is rendered as a fact, and no fact is written into the prose region.
- **P3. A choice is a person's act.** A request to `/v1/select`, `/v1/query` or `/v1/discover` is sent only on an explicit act naming one listed candidate, one resolved reference, or one listed scope. A candidate list is rendered under obligation 3, and a selection is made under obligation 4. The page never sends one itself, and none is preselected or highlighted.
- **P4. A negative status is rendered as itself** (obligation 5), from the `mcp_tool_result` it arrived in: `not_found`, `ambiguous`, `coverage_gap`, `unsupported` and `invalid_request` are results.
- **P4a. Every result rendered out of a `mcp_tool_result` shows its evidence** (obligation 1): the status, every `limitations` entry's kind and detail, the `evidence_bundle` and `source_trace` keys Charter Section 3.1 names, and for a discovery result the `registry_digest`, `method_identifier`, and per-candidate `match_tier`, `matched_text`, `match_kind` and alias provenance. It may collapse them and may not omit them. Obligation 7 holds on the evidence region: no value the result does not contain, and no reordering of rows or candidates.
- **P4b. A tool refusal is rendered as a refusal.** A `mcp_tool_result` with `isError` true carries an `mcp-v0.1` Section 4.3 refusal (`malformed_request`, `database_unavailable` or `runtime_fault`) and no result. The page renders it in the evidence region **as a refusal**, never as an absence, never as a negative status, and never as a `not_found`. It offers no act on it.
- **P5. A scope the person did not write is not offered as clickable.** For a `discover_entity` result whose `scope_checks` entry lists any dimension in `not_person_stated`, the page renders the result under P4 but offers **no** act on its candidates or its resolved reference. Instead it offers the person a scope to choose. For an `ambiguous` result, that is the candidate scopes it lists, none defaulted and none preselected. The person's chosen scope is sent to `/v1/discover` **by the page**, with the same `entity_kind` and `term`. That result's scope is the person's by construction.
- **P6. Before the first message**, the page states that messages are sent to Anthropic and that the relay stores none.
- **P7. A refusal is shown as a refusal**, not as a reply and not as a result.

### 4.8 Identity and process

- The relay runs **in a process that holds no database credential**. The runtime, `/v1` and `/mcp` run in a process that **holds no Anthropic key**. The relay reaches facts only through `/mcp` over HTTPS, as any host does. How the two processes are hosted is the deployment contract's.
- The relay reads the Anthropic key from the deployment's secret store at start, and it never logs, returns or echoes the key.

### 4.9 The system prompt, verbatim

The `system` parameter is **exactly** this text:

> You help a person find engineering facts in a demonstration database that holds only synthetic SAMPLE_* identifiers. You have one tool, discover_entity. Use it only to find which approved entity the person's words refer to. You cannot fetch facts and you cannot select a candidate: the person does both on the page, by clicking. The discover_entity description also mentions query_facts and select_candidate; those tools are not available to you here, so never call them and never say you did. Put only values the person wrote into the four scope arguments. If the person did not name a snapshot, call discover_entity without inventing one, and stop at the `ambiguous` result so the person can choose a scope on the page. Do not choose a scope, a candidate, or a route for the person. Report each result's status as it is: a candidate list is not an answer, and not_found, ambiguous, coverage_gap, unsupported and invalid_request are results. Never state an engineering fact yourself — no values, units, signal names, message names, or meanings — because every fact comes from the page's evidence, not from you. If you found nothing, say so. Keep replies short. Decline anything unrelated to finding entities in this database.

It supersedes, for this host only, the two sentences of `mcp-v0.1` Section 4.4's `discover_entity` description that name the disabled tools (ADR-0005 item 2). The rest of that description still binds. It is an instruction to the model and not a check: the check is Section 4.3's toolset, Section 4.5's scope check, and Section 4.7's page obligations.

### 4.10 What the relay records

The relay stores no message text and **logs no message text**, neither a person's turn nor a model block. Per request it logs exactly the timestamp, the refusal kind or HTTP 200, the latency, the Messages API usage counts, the names of the tools called, and for each `mcp_tool_result` its result `status`, or its refusal kind when it carries `isError` true. An admitted preflight (Section 4.1) logs **exactly one line**, carrying the per-request fields `deploy-v0.1` Section 4.7 fixes, with HTTP 204. It carries nothing this section adds for a `POST`: no usage counts, no tool names and no tool-result kinds. It also carries no `Origin` value and no other request-header value. What that feeds, and how long it is kept, is the deployment contract's.

## 5. Outcome coverage

The relay produces **no result status of its own**. Every status a person sees comes from an `mcp-v0.1` tool result, passed through inside `content` (Section 4.4), or from a `/v1` response the page receives. The relay's own outcomes are HTTP 200 with a response, or one of the six refusal kinds in Section 4.6. **An admitted Section 4.1 preflight is a third shape** (`0.4.0`): HTTP 204 with no body, answering an `OPTIONS` request and never a `POST`. It is not a status, not a result and not a refusal, and only a browser meets it. A registered negative status inside a tool result is never a refusal, and a refusal never carries `content`. **An `mcp-v0.1` Section 4.3 refusal also crosses this boundary**, inside `content` as a `mcp_tool_result` with `isError` true: `malformed_request`, `database_unavailable` or `runtime_fault`. It is not a status and not a relay refusal. The relay passes it through unchanged with HTTP 200, and the page renders it under P4b.

## 6. Determinism

**The model is not deterministic, and this contract does not claim that it is.** What is deterministic, and asserted: the parameters of the Messages API call are the same bytes for the same request (Section 4.3), `scope_checks` is a pure function of the request and the response (Section 4.5), and a refusal for a given request and cap state is the same refusal. The tool results inside `content` carry `mcp-v0.1` Section 6's guarantee unchanged.

## 7. Evidence obligations

The relay adds nothing to `evidence_bundle`, `source_trace` or `limitations`, removes nothing, and adds no evidence structure of its own. Every tool result it returns is `mcp-v0.1`'s, byte for byte. `relay` and `scope_checks` sit beside `content`, not inside any result, and are not evidence.

## 8. Acceptance evidence

| Obligation | Evidence |
| --- | --- |
| Section 4.2 request shape and size | Automated: `RL-001` to `RL-004`, `RL-019`, `RL-021`, `RL-022` |
| Section 4.3 the call, toolset and system prompt | Automated, against a stub Messages API client: `RL-005` asserts the exact body parameter set and, separately, the header, that `configs` enables `discover_entity` alone and `default_config` disables the rest, and that `system` equals the Section 4.9 text read off this document byte for byte |
| Section 4.4 pass-through | Automated: `RL-006`, the response's `content` equals the stub's byte for byte |
| Section 4.5 scope check | Automated: `RL-007` to `RL-010` |
| Section 4.1 the CORS preflight (`0.4.0`) | Automated: `RL-023` to `RL-025` |
| Section 4.6 caps and refusals | Automated: `RL-011` to `RL-016`, one per kind, each asserting that **no model call was made** when a cap refuses |
| Section 4.8 identity | Automated where observable: `RL-017`, the relay's settings expose no database credential and the runtime's no Anthropic key. The deployment contract carries the deployed check. |
| Section 4.10 records | Automated: `RL-018`, as registered below; `RL-023` for the preflight's line (`0.4.0`) |
| Section 4.7 page obligations | The portfolio site's slice, automated there (Section 8.2), and the owner's recorded decision that the page materially supports use |
| End to end, deployed | The deployment contract's `DP-012`: one deployed `POST /chat`, asserting only what the relay controls — HTTP 200, the Section 4.3 block types, `scope_checks`, and the `relay` key — never the model's words |

### 8.1 Registered cases

Every case runs against a stub Messages API client that returns a registered `content` array, so that no case calls a model, costs money, or varies between runs. Every identifier is `SAMPLE_*`.

| Case | Input | Expected |
| --- | --- | --- |
| `RL-001` | a request whose last turn is the relay's | `malformed_request`; no model call |
| `RL-002` | a person's turn of 501 characters | `malformed_request` |
| `RL-003` | a relay turn carrying a `tool_use` block | `malformed_request` |
| `RL-004` | an extra top-level key | `malformed_request` |
| `RL-005` | any valid request | the Messages API call of Section 4.3, byte for byte |
| `RL-006` | a stub response with text, `mcp_tool_use` and `mcp_tool_result` blocks | 200; `content` unchanged |
| `RL-007` | the person wrote all four scope values; the call uses them | all four in `person_stated` |
| `RL-008` | the person wrote none; the call carries four | all four in `not_person_stated` |
| `RL-009` | the person wrote `SAMPLE_SNAP_BASE_EXTENDED`; the call carries `SAMPLE_SNAP_BASE` | `snapshot_label` in `not_person_stated`, which is the boundary-alphabet case of `api-v0.1` Section 4.3 |
| `RL-010` | **across turns**: a relay turn in the request carrying an `ambiguous` result, then, in this response, a call carrying one of its listed scopes that no person's turn contains | that dimension in `not_person_stated`, which is ADR-0005 item 4's case, and the multi-turn case ADR-0005's Consequences require |
| `RL-019` | a relay turn whose serialized `content` is 16 KiB plus one byte, in a body under 32 KiB | `malformed_request`; no model call |
| `RL-020` | a stub response whose `mcp_tool_result` has `isError` true with a `database_unavailable` refusal | 200; `content` unchanged; the log line names the refusal kind |
| `RL-021` | a relay turn carrying one `discover_entity` result at `k` = 10 (the result Section 8.3 counts as maximal), in a body under 32 KiB | accepted; one model call |
| `RL-022` | a relay turn carrying one maximal `discover_entity` result and a `text` block that fills the rest of the turn bound, then one byte more | accepted at the bound; `malformed_request` one byte over |
| `RL-011` | 11 person's turns | `conversation_limit`; no model call |
| `RL-012` | a 7th request within 60 seconds from one address | `rate_limited`; no model call |
| `RL-013` | a 61st request in one UTC day from one address | `rate_limited`; no model call |
| `RL-014` | a request after the daily ceiling | `daily_ceiling_reached`; no model call |
| `RL-015` | the stub raises, or times out | `model_unavailable`; no `content` |
| `RL-016` | the stub returns a `tool_use` block | `model_unavailable` |
| `RL-017` | the relay's and the runtime's settings | neither holds the other's secret |
| `RL-018` | a person's turn containing a registered marker `SAMPLE_LOG_MARKER_7Q2`, with logs captured | the marker appears in no log line |
| `RL-023` | with the registered origin `https://sample-origin.example` configured, an `OPTIONS /chat` from that origin with `Access-Control-Request-Method: POST`: once from an address whose per-minute limit is exhausted, with the daily ceiling also reached; then seven times from a fresh address, followed by one `POST` from that address under a ceiling not yet reached | every preflight HTTP 204, no body, the four headers of Section 4.1 exactly, and no model call; the `POST` is answered 200, because no preflight consumed the address's limit. With the relay's logs captured, each admitted preflight writes **exactly one** line, carrying HTTP 204 and the `deploy-v0.1` Section 4.7 per-request fields, and none of the usage counts, tool names, tool-result kinds, `Origin` value or other request-header value (Section 4.10) |
| `RL-024` | an `OPTIONS /chat` from another origin; from the registered origin with no origin configured; from the registered origin with `Access-Control-Request-Method: DELETE`; and from the registered origin with that header absent | `method_not_allowed` in all four, as at `0.3.x`; no `Access-Control-Allow-Origin` on any |
| `RL-025` | a `POST /chat` from the registered origin answered 200; the same origin refused as `malformed_request`; the same origin refused as `daily_ceiling_reached`; and the 200 request from another origin and with no `Origin` | the first three carry `Access-Control-Allow-Origin` equal to the origin and `Vary: Origin`, with bodies byte-equal to the same request without an `Origin`; the last two carry `Vary: Origin` and no `Access-Control-Allow-Origin` |

### 8.2 Deferral of the acceptance evidence

The Section 4.7 page obligations are discharged in the portfolio site's repository, by tests against registered `POST /chat` responses — the `RL-006`, `RL-008`, `RL-010` and `RL-020` shapes at minimum, and a discovery result's full evidence under P4a — and by the owner's recorded decision on that repository's slice. This repository cannot run them, and this contract names them so that the site's slice has a fixed target.

### 8.3 The spend bound and the daily ceiling

**Spend is bounded by the API key's workspace, not by a count.** The relay's Anthropic API key belongs to an Anthropic Console workspace that holds no other key. The workspace's monthly spend limit is set to at most `(monthly_budget − monthly_fixed) / jpy_per_usd`:

- `monthly_budget` is the owner's (8,000 JPY, [#205](https://github.com/OKJ1105/evidence-first-rag/issues/205#issuecomment-5829415863)).
- `monthly_fixed` and `jpy_per_usd` are taken from the committed cost record.

On [the 2026-09-29 record](../acceptance/milestone-5/cost-2026-09-29-body-32k.json) that is (8,000 − 6,733.50) / 157.77 = 8.03, so **USD 8**. The owner sets the limit. The owner's statement that it is set, with the workspace's name and the date, is recorded before the first deployed run. That statement is this section's acceptance evidence, because no check this repository runs can read a Console setting.

When the limit is reached, the Messages API refuses the call. The relay then answers `model_unavailable` (Section 4.6), and serves no reply until the next month or a raised limit. This is the accepted cost of a hard bound.

**The daily ceiling is a brake, not the bound.** It is a count of model calls per UTC day, registered before the first deployed run as the configuration value the deployment contract carries: **67**, about 2,000 calls over a 30-day month. It limits how many calls one UTC day can make, and the per-address limits of Section 4.6 limit what one client can make. **It does not keep one day from exhausting the month**: at the committed worst case, 67 calls cost about 932 JPY at one tool call per model call (67 × 13.9081), most of the month's allowance, and about 1,560 JPY at two (67 × 23.2859), more than all of it. The relay's counters are in memory, so a restart re-arms the day (Section 4.6). What bounds the month is the spend limit. A month exhausted early is the accepted residual: every later request is answered `model_unavailable`, and nothing is spent past the limit.

**The worst case stays recorded.** `cost_per_call_upper_bound` is still computed as before. It uses the live published price of the Section 4.3 model and the maximum request this contract admits: a **32 KiB** body (Section 4.2), plus the Section 4.9 text and the tool definitions. The input tokens are **counted by the API's token-counting endpoint** on a registered maximal request, not estimated. `max_tokens` is added as output, and the tool results the connector adds within the call are bounded by counting a registered maximal `discover_entity` result.

**The price, the exchange rate used, the token counts and the result are committed with the date they were read, before deployment.** They are the evidence for what the spend limit buys at worst: USD 8 is about 91 worst-case calls at one tool call per model call. The ceiling of 67 a day therefore binds only traffic well short of the worst case; closer to it, the spend limit is reached first. Prices change, and a number written here now would be a remembered one.

## 9. Deferred decisions

| Decision | Owner |
| --- | --- |
| **The model — decided**: `claude-haiku-4-5`, the lowest-cost current model that makes tool calls, chosen by the repository owner over `claude-sonnet-5` on [#210](https://github.com/OKJ1105/evidence-first-rag/issues/210#issuecomment-5828675894). | Decided. Changing it later is a minor version. |
| The numeric daily ceiling | **Registered**: 67 (Section 8.3). The deployment contract carries it as configuration. |
| The workspace spend limit | The owner sets it in the Anthropic Console, and records the statement before the first deployed run (Section 8.3) |
| The CORS origin allowed to call `POST /chat`, and the client address used by the rate limit behind the hosting's proxy | The deployment contract |
| Streaming responses | Not opened. A later minor version. |
| `Access-Control-Max-Age` on the preflight | Not set at `0.4.0`, as `api-v0.1` `0.2.0` sets none. A browser therefore preflights each `POST`, which costs a round trip but no model call. Caching it is a later minor version if observed latency asks for it. |
| A positive deployed check of the preflight | `deploy-v0.1`'s. `DP-005` asserts the foreign-origin refusal today. A check that the registered origin is admitted belongs with the patch that records the site's origin in its Section 4.6. |
| Whether the page offers a person's scope choice for a non-`ambiguous` result with a `not_person_stated` dimension (P5 offers the candidate scopes only where an `ambiguous` result listed them) | The portfolio site's slice may propose it; adding it here is a minor version |

## 10. Change control

- This contract is `Accepted`. Under [Contract Shape Framework](README.md) Section 7, a change that does not weaken a Charter or ADR invariant produces a new contract version with a recorded human decision. The looser rule that governed it while `Proposed` — amendment by an ordinary contract-only pull request — no longer applies.
- After acceptance, a change that does not weaken a Charter or ADR invariant produces a new version with a recorded human decision. Changing the model, the system prompt, a cap or a page obligation, or adding a route or refusal kind is a minor version and requires a fresh independent design review.
- **Enabling `query_facts` or `select_candidate`** in Section 4.3, or letting the relay or the page select, fetch a fact, or choose a scope on a person's behalf, is not a contract-level change: it reverses ADR-0005 item 2 or item 4 and requires an ADR and a recorded human decision.
- A superseded version is retained with a `Superseded by` status rather than deleted.
