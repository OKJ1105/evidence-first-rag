# Evidence-First RAG Runtime

Evidence-First RAG Runtime is a bounded backend for answering scoped message, signal, and mapping questions over structured engineering data.

The name is deliberate. This is a RAG architecture with the retrieval layer re-grounded: retrieval means executing registered, read-only SQL templates over structured data — never semantic search presented as fact. Augmentation means attaching an inspectable evidence bundle with a source trace and explicit limitations to every result. Generation is constrained rendering that cannot add facts.

The intended product user is an engineer who would otherwise open structured definition files and cross-check them by hand. The core rule is simple: AI may interpret intent and help locate an entity, but authoritative facts must come from approved, read-only queries over structured data.

## Status

The Project Charter is frozen and the [MVP runtime contract](docs/contracts/mvp-v0.1.md) is `Accepted`, so runtime behavior is specified by reviewed contracts before it is implemented. Implementation of that contract has started.

The table below says how much of the contract executes today, section by section. It is here because a repository that describes an architecture without saying how much of it runs is a design document, and the two are hard to tell apart from the outside. Every slice that changes what runs updates this table.

- **Contracted** — specified and reviewed. No code.
- **Types only** — the shape exists and is tested. Nothing executes it yet.
- **Implemented** — it runs, with the acceptance evidence its contract section requires.

| Contract section | Surface | State |
| --- | --- | --- |
| 3.4 Platform | PostgreSQL 17, version-controlled DDL applied in lexical order | Implemented |
| 4.1 Data model | Schema, columns, and uniqueness constraints | Implemented |
| 4.2 Identity and scope | Canonical message and signal reference types | Types only |
| 4.2 Identity and scope | Scope resolution, the candidate list, and the `ambiguous` threshold | Implemented |
| 4.2 Identity and scope | Data-level invariant check over the loaded database | Implemented |
| 4.3 Database identities | Provisioning and read-only runtime roles | Implemented |
| 4.4 Template registry | Four fixed SQL templates, safeguards, and limits | Implemented |
| 4.4 Template registry | The runtime role's five-second statement timeout | Implemented |
| 4.5 Routes | The three route names, as a closed set | Implemented |
| 4.5 Routes | Request validation, dispatch, and one entry per asserting relation | Implemented |
| 4.6 Thin LLM Adapter | Deterministic revalidation of adapter output | Implemented |
| 4.6 Thin LLM Adapter | The pinned model call and its recorded decoding configuration | Implemented |
| 4.7 Deterministic baseline | Exact-match resolver over a curated table | Implemented |
| 4.7 Deterministic baseline | The comparison harness and its pre-registration gate | Implemented |
| 4.8 Answer rendering | Fixed-template rendering over a normalized result | Implemented |
| 4.9 Conformance runner | Checks A through E, verdicts, failure classes | Implemented |
| 4.9 Conformance runner | One JSON artifact per run, and the `D1` comparison rule | Implemented |
| 4.10 Read-only invariance | State digests and the four refusal assertions | Implemented |
| 4.11 Fixture serialization | The registered JSON Lines fixture files | Implemented |
| 4.11 Fixture serialization | The loader that resolves natural keys at load time | Implemented |
| 5 Outcome coverage | The seven status families, as a closed set | Types only |
| 5 Outcome coverage | Each status produced by the condition Section 5 names | Implemented |
| 6 Determinism | `C` collation and repeatable provisioning | Implemented |
| 6 Determinism | Registered template ordering, tiebreakers, explicit `NULLS LAST` | Implemented |
| 6 Determinism | The no-normalization rules | Implemented |
| 7 Evidence obligations | `evidence_bundle`, `source_trace`, `limitations` types | Types only |
| 7 Evidence obligations | All three assembled on every outcome, negatives included | Implemented |
| 8.1 Required fixture cases | Structural fixture data for the registered cases | Implemented |
| 8.1 Required fixture cases | Registered expected results per fixture | Implemented |
| 8.3 Milestone 2 comparison | The curated request set and the adoption thresholds | Implemented |

[Milestone 3 Entity Discovery Contract v0.1](docs/contracts/entity-discovery-v0.1.md) is `Accepted 2026-09-11`. Its implementation has started, and the same table continues for it:

| Contract section | Surface | State |
| --- | --- | --- |
| 4.1 The approved entity registry | Four tables, constraints, the runtime identity's `SELECT` on them (3.3 extension 2) | Implemented |
| 4.2 Provenance, integrity, refresh | Registry fixtures under `fixtures/registry/`, loaded in the provisioning transaction; the five load-time rules; the data-level check | Implemented |
| 4.2 The registry digest | Canonical JSON and `registry_digest` over the loaded rows | Implemented |
| 4.5 Normalization | `normalize()` as the derived surface's tokenizer | Implemented |
| 4.3 The discovery request | `entity_discovery` validated before any connection; scope as a precondition via the `mvp-v0.1` candidate query | Implemented |
| 4.4 Registered templates | `TPL_REGISTRY_STATE_V1`, `TPL_DISCOVERY_EXACT_V1`, `TPL_DISCOVERY_LEXICAL_V1`, under `mvp-v0.1` Section 4.4's safeguards | Implemented |
| 4.5 Match tiers | Tiers 1–4 computed in the registered SQL; `M-LEX-1` exact-then-lexical | Implemented |
| 4.6–4.7 Candidates and auto-resolution | One entity per candidate, `k` = 10, tier-1-and-2 uniqueness; `candidate_set_id` per Section 4.8 | Implemented |
| 4.8 The verified selection path | `entity_selection`: re-derivation, the digest check, dispatch to the `mvp-v0.1` route with the `selection` record | Implemented |
| 5, 7 Outcomes and evidence (discovery) | Seven statuses, never `success`; both contracts' identities, alias provenance, the required limitations | Implemented |
| 4.9 Retrieval methods | `M-LEX-1`, exact then lexical, recorded on every result | Implemented |
| 4.10 The evaluation set | The case type, the eight classes, the authoring rules a program can check, and the run artifact | Implemented |
| 4.10 The registered cases | The set itself, and `N` | Registered — forty cases, five per class, Section 8.3 at `0.3.1` |
| 4.11 Metric definitions | `recall_at_k`, `mrr`, `false_resolution`, `correct_abstention`, `over_abstention`, `task_completion`, `latency`, per class and over the set | Implemented |
| 8.3 Adoption thresholds | The numbers each adopted method must meet | Registered — per class, Section 8.3 at `0.3.1`; the runner judges against them |

The four registered SQL templates are inspectable, the three routes execute them read-only as the runtime identity, and the conformance runner judges all sixteen registered fixture cases against a committed expected result and writes one artifact carrying its verdict. Provisioning, the data-level invariant check and the conformance run all open a database, and they run in CI against a service container rather than a local install, so a determinism claim is something anyone can re-run.

The adapter is built, its refusals are registered as fixture cases, and **the Section 4.7 comparison has been run**: the curated request set and the adoption thresholds contract Section 9 once left open were registered in Section 8.3 at `0.6.0`, and the run judged against them is committed at [`docs/acceptance/milestone-2/comparison.json`](docs/acceptance/milestone-2/comparison.json). Charter Section 9 requires a numeric threshold to be registered before the run it judges, so the harness refuses to produce a verdict without thresholds, and refuses again when the thresholds carry a registration timestamp that is not earlier than the run. Adopting the adapter remains a recorded human decision at the Milestone 2 gate: the [Milestone 2 acceptance record](docs/acceptance/milestone-2.md) collects the evidence for each gate item, and its disposition line is the repository owner's.

Discovery is built and **the Section 4.10 evaluation run has happened**: the forty labeled cases and the per-class adoption thresholds are registered in Section 8.3 at `0.3.1`, and the run judged against them is committed at [`docs/acceptance/milestone-3/discovery-run.json`](docs/acceptance/milestone-3/discovery-run.json). The runner refuses to judge a run whose thresholds are not registered before it, whose registry is not the one the cases were authored against, or whose cases are not the registered forty, and exits non-zero when a run was not judged. Adopting `M-LEX-1` remains a recorded human decision at the Milestone 3 gate: the [Milestone 3 acceptance record](docs/acceptance/milestone-3.md) collects the evidence for each gate item, states what the run does not establish, and its disposition line is the repository owner's.

The model SDK is an optional extra (`pip install evidence-first-rag[adapter]`). Charter Section 3.1 keeps the model outside the path that produces facts, so a plain install answers questions with no model library present at all.

The expected results the runner compares against are built from `fixtures/` by `src/evidence_first_rag/conformance/authoring.py`, not captured from the runtime. CI asserts the committed files are exactly what that tool produces, so the comparison is between two independently built documents rather than between the runtime and a recording of itself.

See [Project Charter](docs/PROJECT_CHARTER.md) for the product direction, architecture boundaries, success criterion, roadmap, and release conditions.

## Running it

You need a container runtime that provides `docker compose` — Docker Desktop,
Colima, Podman with the compose plugin — and nothing else. No Python
environment, no PostgreSQL, no model credential.

```
docker compose up
```

That is the whole of it. The stack starts PostgreSQL 17, provisions it with the
committed SQL and fixtures, and serves the API and the page at
<http://127.0.0.1:8000>. Only that port is published; the database is reachable
from the stack's own containers and not from your machine.

After changing anything under `src/`, `ui/`, `sql/` or `fixtures/`, start it
with `docker compose up --build`: the image is built from those directories
rather than mounting them, so without `--build` a second `up` serves the image
it built the first time. Open that address, search the approved registry for
an entity in one `SAMPLE_*` scope, choose among the candidates it offers, and
read the fact it returns with its scope, its template, its bound parameters and
its limitations beside it. Asking in your own words is what the MCP tool
surface below is for: a host's model composes the calls, and the page is where
the evidence behind a fact can be read at the source.

`api-v0.1` Section 4.7 is why this is one command rather than a list of steps,
and why the stack provisions through the same path CI uses rather than one of
its own: Charter Section 9's Milestone 5 gate forbids a second schema or
fixture meaning, so the way this starts locally is the way a deployment has to
start.

**No model credential is needed.** Neither the page nor the MCP tool surface
calls a model. `/v1/ask`, the Thin LLM Adapter's route, is still served for the
Milestone 2 evaluation path and refuses with `adapter_unavailable` until
`ANTHROPIC_API_KEY` is in your environment, but it is no longer the documented
way in: [ADR-0004](docs/adr/0004-mcp-surface-and-the-tool-result-boundary.md)
item 5, and `api-v0.1` Section 9 (#203).

**The same stack serves the MCP tool surface at `/mcp`** — `mcp-v0.1`
Section 4.5, Streamable HTTP, beside `/v1` in the same process over the same
runtime. Three tools (`query_facts`, `discover_entity`, `select_candidate`)
return the same envelope the corresponding `/v1` route returns, evidence
included. A host that runs the loop — a client that takes a remote MCP server's
URL, or an application calling the Messages API with `mcp_servers` set — is
what makes the tools conversational; this repository owns no such loop, and
[ADR-0004](docs/adr/0004-mcp-surface-and-the-tool-result-boundary.md) records
where the "no evidence, no answer" guarantee ends because of it.

The passwords in `compose.yaml` are defaults for a stack on your own loopback
holding `SAMPLE_*` fixtures. Set `POSTGRES_PASSWORD`,
`MVP_PROVISIONING_PASSWORD` and `MVP_RUNTIME_PASSWORD` to override them.

## Intended flow

1. Interpret a bounded user request.
2. Produce an approved route and validated parameters.
3. If a scoped canonical entity reference is missing, return ranked candidates from the approved entity registry and abstain when scope or identity remains ambiguous.
4. Execute only a registered fixed SQL template against a read-only structured source.
5. Return normalized facts or relations with an evidence bundle, source trace, and limitations.
6. Render or export the validated result without changing its meaning.

## Repository policy

- Use synthetic fixtures and portable placeholder identifiers only.
- Do not commit production data, real-world identifiers, credentials, or internal URLs.
- The reviewed repository contracts are the normative implementation authority.
- Do not generate or execute free-form SQL.
- Do not treat semantic retrieval results as authoritative facts.
- Implement one reviewable behavior slice per pull request, with its contract and fixtures reviewed before its code.

Detailed contributor and agent constraints are in [AGENTS.md](AGENTS.md).
