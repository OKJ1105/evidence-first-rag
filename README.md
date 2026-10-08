# Evidence-First RAG Runtime

A bounded retrieval backend that answers scoped questions about message, signal and mapping definitions in structured engineering data. **Facts come only from registered, read-only SQL over PostgreSQL**, and each one carries its evidence: the scope, the query template, the bound parameters and its limitations. A language model may help find *which* entry a person means. It never supplies the fact.

- **Live demo:** <https://junokaniwa.com/demo/>, a chat page on the author's site. It calls this repository's deployment on Azure.
- **Case study:** <https://junokaniwa.com/case-study/> covers the problem, the design decisions and how they changed, and the evaluation.

All data in this repository is synthetic (`SAMPLE_*`).

- [What it does](#what-it-does)
- [Features](#features)
- [How it works](#how-it-works)
- [Architecture](#architecture)
- [Getting started](#getting-started)
- [Deployment](#deployment)
- [Evaluation and evidence](#evaluation-and-evidence)
- [Costs](#costs)
- [Security](#security)
- [Limitations](#limitations)
- [Project documents](#project-documents)
- [License](#license)

## What it does

An engineer checking a signal or message definition often opens several structured files and compares them by hand. The same name can appear in two versions of the data with different values. In the synthetic data, `SAMPLE_MSG_ENGINE_STATUS` has a 10 ms cycle time in one snapshot and 20 ms in another. A search that matches the name can return a true value from the wrong version, and nothing in the answer shows it.

This runtime treats the **scope** as part of an entry's identity: project, revision, network and snapshot. It never fills in a "latest" or default scope. When the scope or the entry is unclear, it lists the possibilities and lets the person choose.

![How a question becomes a fact: you ask; the LLM, through one MCP tool, finds candidates but cannot fetch facts or choose; you choose; fixed read-only SQL on PostgreSQL returns the fact with its source. When nothing matches, the result is "not found", with no guess.](docs/images/request-flow.svg)

**In the demo,** a person asks in their own words. The model can only search for candidates. Here it found the name in two snapshots, and the page lists both and chooses neither:

![Screenshot of the demo. The question asks the cycle time of SAMPLE_MSG_ENGINE_STATUS. The model's reply sits under "The model's words", marked as not evidence. A Lookups panel shows "Lookup: scope not specified" and two candidate scopes, SAMPLE_SNAP_BASE and SAMPLE_SNAP_REVISED, each with a "Use this scope" button and neither selected.](docs/images/demo-model-words-and-scopes.png)

After the person chooses a scope and then the message, the fact comes from the database. It appears under its own heading, with the route, template, bound parameters and read-only safeguards beside it:

![Screenshot of the answer. Answered, with its returned values: frame_identifier 256, message_key SAMPLE_MSG_ENGINE_STATUS, payload_byte_length 8, transmit_mode SAMPLE_MODE_CYCLIC and transmit_period_ms 10. The open Evidence panel lists the result contract api-v0.1 0.2.0, the bound parameters, contract mvp-v0.1 0.6.1, the read-only safeguards, the resolved scope SAMPLE_SNAP_BASE, the route message_facts, one row returned, and the template TPL_MESSAGE_FACTS_V1 version 2.](docs/images/demo-fact-from-database.png)

*Screenshots recorded from the deployed demo on 2026-10-08, at commit `f8b82e6`. The step between them, choosing the scope and then the message, is not pictured.*

## Features

- **Fixed, read-only SQL.** A closed set of registered query templates runs under a read-only database role. There is no free-form SQL and no text-to-SQL. The role is refused `INSERT`, `UPDATE`, `DELETE`, `CREATE` and `DROP` by PostgreSQL privileges.
- **Evidence on every result, negatives included.** Each result carries an `evidence_bundle`: scope, template name and version, bound parameters and row count. It also carries a `source_trace` and explicit `limitations`.
- **Explicit negative outcomes.** When the system cannot answer, it returns a named status instead of a plausible guess. The statuses cover no match in covered data, data that does not cover the question, more than one candidate or scope, a request outside what it is built for, and malformed or contradictory arguments.
- **Entity discovery without silent resolution.** A term is matched against an approved registry by exact name, approved alias, then word match. A match is settled automatically only when exactly one entry matches its exact name or an approved alias. Anything else is a candidate list for the person to pick from.
- **Two interfaces, one result.** An HTTP API (`/v1/query`, `/v1/discover`, `/v1/select`) and an MCP server at `/mcp` (`query_facts`, `discover_entity`, `select_candidate`) return the same envelope.
- **A chat relay that holds one tool.** The demo's relay gives the model `discover_entity` only, so the model can search but cannot choose or fetch a fact. It enforces per-address and daily limits.
- **The same build everywhere.** CI, the local stack and the Azure deploy use one container image and one provisioning module. Every deploy compares the deployed database and test verdicts with a local build of the same commit.

## How it works

Finding candidates is the one MCP tool the demo's model can call:

![Flowchart of the MCP tool "find candidates". Your term, then "Which version?": if the scope is missing, each version is searched and the person picks a version, offered only where the term was found. Given a version: exact name or approved alias, identified if exactly one. If none: word match, all words found, and the person picks a candidate, never automatically. If none: no match, "not found", no guess. Each match shows how it was found; facts come only after the person's click.](docs/images/finding-candidates.svg)

The person's choice is sent to `/v1/select`. The selection path re-derives the candidate list and checks the cited `candidate_set_id` before dispatching the chosen reference to a fact route. A selection made against a list that has since changed is refused rather than answered.

## Architecture

![Architecture diagram. The visitor loads a static site from Cloudflare. Chat goes to the chat relay on Azure App Service, which holds the API key and sends the question to Claude (the LLM). Claude calls the MCP tool "find candidates" on the RAG backend. The visitor's click goes to the RAG backend, a FastAPI and MCP server, which runs fixed SQL on Azure Database for PostgreSQL 17 under a read-only role. Both apps run one image from Azure Container Registry, deployed by GitHub Actions with OIDC login, and each reads only its own secret from Azure Key Vault through its managed identity.](docs/images/architecture.svg)

| Component | Role |
| --- | --- |
| `surface` app (Azure App Service, Linux) | FastAPI: the `/v1` HTTP API and the `/mcp` server, over the runtime. It connects to PostgreSQL with the read-only role. |
| `relay` app (same plan, same image) | `POST /chat`: calls the Claude Messages API with the `surface` MCP server and one tool enabled. It holds no database credential. |
| Azure Database for PostgreSQL Flexible Server 17 | The structured data and the approved entity registry, provisioned from the committed `sql/` and `fixtures/`. |
| Azure Key Vault | The model key, readable by `relay` only, and the database passwords. Each app reads only its own secret through its managed identity. |
| Azure Container Registry | One image per commit, tagged with the commit. No registry credential is stored. |
| GitHub Actions | A manual `workflow_dispatch` from `main` only, signing in with OIDC. No cloud secret is stored in GitHub. |

The chat page itself lives in the author's site repository and is not part of this one.

## Getting started

You need a container runtime that provides `docker compose`, such as Docker Desktop, Colima, or Podman with the compose plugin. You need nothing else: no Python environment, no PostgreSQL, no model credential.

```
docker compose up
```

The stack starts PostgreSQL 17, provisions it with the committed SQL and fixtures, and serves the API, the MCP server and a page at <http://127.0.0.1:8000>. Only that port is published; the database is reachable from the stack's own containers only.

- **The page** searches the approved registry in one `SAMPLE_*` scope, lists the candidates, and shows the fact you pick with its evidence beside it.
- **The MCP server** is at <http://127.0.0.1:8000/mcp> (Streamable HTTP). A client that takes a remote MCP server's URL lets its model compose the calls in your own words. That host model is outside this repository, and [ADR-0004](docs/adr/0004-mcp-surface-and-the-tool-result-boundary.md) records where the "no evidence, no answer" guarantee ends because of it.
- **No model credential is needed.** Neither the page nor the MCP server calls a model. The chat relay is not part of the local stack.

After changing anything under `src/`, `ui/`, `sql/` or `fixtures/`, run `docker compose up --build`. The image is built from those directories rather than mounted from them.

The passwords in `compose.yaml` are defaults for a loopback-only stack holding `SAMPLE_*` fixtures. Set `POSTGRES_PASSWORD`, `MVP_PROVISIONING_PASSWORD` and `MVP_RUNTIME_PASSWORD` to override them.

<details>
<summary>Running the checks without the stack</summary>

The package is plain Python, and the model SDK is an optional extra (`pip install evidence-first-rag[adapter]`). A plain install answers questions with no model library present. CI runs the following on every pull request; see `.github/workflows/repository-checks.yml`:

```
python3 -m unittest discover --start-directory tests --top-level-directory .
python3 scripts/checks/validate_fixtures.py
python3 scripts/checks/validate_links.py
python3 scripts/checks/scan_sensitive_strings.py
node --test "scripts/agent/*.test.mjs" "ui/*.test.mjs"
```

The database tests (`tests_database/`) and the stack tests (`tests_stack/`) need PostgreSQL and the running stack respectively, as in CI.

</details>

## Deployment

The deployment is defined by [`deploy-v0.1`](docs/contracts/deploy-v0.1.md), with `infra/main.bicep` and `.github/workflows/deploy.yml`. A deploy is started by hand, from `main` only, under the repository owner's account. It is not something a fork can run as it is: it reads the owner's Azure identifiers from a protected GitHub environment.

Each deploy rebuilds the database from the commit being deployed and then runs the deployed checks (`DP-*`):

- the deployed database's row counts, registry digest and template digests equal a local build's;
- the conformance verdicts are equal;
- the runtime role cannot write;
- no secret is in the image, the workflows or the artifact;
- HTTPS and CORS are enforced;
- no client address or message text is in the logs;
- the model calls the search tool through the relay.

A failed check rolls back the database and the image to the last passing commit. Every deploy's record is committed unedited under [`docs/acceptance/milestone-5/`](docs/acceptance/milestone-5/README.md).

## Evaluation and evidence

Every pass mark was registered before the run it judges, and each milestone closes on a recorded decision by the repository owner. Milestones 1–4 are accepted; Milestone 5's disposition is pending.

| Milestone | What it established | Record |
| --- | --- | --- |
| 1 Query runtime | Fixed templates, read-only role, evidence on every outcome; sixteen registered fixture cases judged against expected results built separately from the data | [milestone-1](docs/acceptance/milestone-1.md) |
| 2 Thin LLM adapter | The model adapter judged against a deterministic baseline on a pre-registered request set | [milestone-2](docs/acceptance/milestone-2.md), [run](docs/acceptance/milestone-2/comparison.json) |
| 3 Entity discovery | Forty labelled cases in eight classes judged against per-class thresholds; no false resolution | [milestone-3](docs/acceptance/milestone-3.md), [run](docs/acceptance/milestone-3/discovery-run.json) |
| 4 End-to-end workflow | The HTTP and MCP workflows end to end; rendering adds no facts | [milestone-4](docs/acceptance/milestone-4.md) |
| 5 Azure deployment | Evidence collected; the owner's disposition is pending. The deployed checks compare the deployed environment with the local build and test that the runtime identity cannot write | [milestone-5](docs/acceptance/milestone-5.md) |

Each record states what it does not establish. For example, the adapter was tuned on the cases it was judged on, the search cases were written from the rules the search implements, and neither says anything about unseen questions. The adapter from Milestone 2 is not on the demo's path.

[Implementation status](docs/implementation-status.md) maps each contract section to what runs.

## Costs

The deployment is sized as the smallest topology the project allows: one Linux App Service plan running two apps, the lowest Burstable PostgreSQL Flexible Server tier, Basic Container Registry, and Key Vault. The owner's budget alert is 8,000 JPY a month ([`deploy-v0.1`](docs/contracts/deploy-v0.1.md) Section 4.9). The committed cost computation puts the fixed charges at 6,733.50 JPY a month at the prices it records; see [Cost computations](docs/acceptance/milestone-5/README.md#cost-computations). Model spend is bounded by the relay's daily ceiling of 67 model calls and by the provider workspace's spend limit ([ADR-0006](docs/adr/0006-relay-spend-is-bounded-by-the-provider-workspace.md)). Prices change; recompute before relying on these numbers.

## Security

- **No secrets in the repository.** The model key and the database passwords are in Key Vault, read through each app's managed identity, and the deploy signs in to Azure with OIDC. Every deploy scans the image, the workflows and its own record (`DP-003`), and CI scans the tree and its whole history for sensitive strings.
- **Credentials split by process.** Only `relay` can read the model key; only `surface` can read the database password.
- **Least privilege in the database.** The runtime role has `SELECT` only, under a five-second statement timeout.
- **No authentication.** The public routes are open. CORS admits one browser origin, which decides only which page a browser lets read the reply; it is not access control. The relay limits each address to 6 requests a minute and 60 a day, and all callers to 67 model calls a day.

## Limitations

This is a personal project on small synthetic data: four snapshots, seven messages, thirteen signals and three mappings. It does not show:

- a comparison with vector search;
- accuracy on unseen questions;
- operation with real users;
- availability: one instance per app, one region, and the platform's built-in metrics only.

The model's own sentences are not checked. Matching is by words, not meaning, so a synonym is found only when it is registered as an approved alias. The full list, including what has and has not been observed on the deployed demo, is in [Limitations](docs/limitations.md).

## Project documents

- [Project Charter](docs/PROJECT_CHARTER.md): product direction, architecture boundaries, roadmap and release conditions.
- [Contracts](docs/contracts/README.md): the reviewed contracts that specify behavior before it is implemented.
  - [`mvp-v0.1`](docs/contracts/mvp-v0.1.md): the runtime;
  - [`entity-discovery-v0.1`](docs/contracts/entity-discovery-v0.1.md): discovery;
  - [`api-v0.1`](docs/contracts/api-v0.1.md): the HTTP API;
  - [`mcp-v0.1`](docs/contracts/mcp-v0.1.md): the MCP server;
  - [`relay-v0.1`](docs/contracts/relay-v0.1.md): the chat relay;
  - [`deploy-v0.1`](docs/contracts/deploy-v0.1.md): the deployment.
- [Architecture decision records](docs/adr/).
- [Development workflow](docs/DEVELOPMENT_WORKFLOW.md) and [AGENTS.md](AGENTS.md).
  - Most code and documents were written by AI coding sessions (Claude Code) and reviewed by a separate AI review loop ([Agent Loop](docs/agent-loop.md)).
  - Every decision the workflow reserves for a person was the repository owner's: accepting contracts and ADRs, setting pass marks, accepting milestones, and merging.

### Repository policy

- Use synthetic fixtures and portable placeholder identifiers only.
- Do not commit production data, real-world identifiers, credentials, or internal URLs.
- The reviewed repository contracts are the normative implementation authority.
- Do not generate or execute free-form SQL.
- Do not treat semantic retrieval results as authoritative facts.
- Implement one reviewable behavior slice per pull request, with its contract and fixtures reviewed before its code.

## License

All rights reserved: the repository is published to be read, and no license to use it is granted. See [LICENSE](LICENSE). Third-party licenses are recorded in [docs/third-party-licenses.md](docs/third-party-licenses.md).

The figures under `docs/images/` are the author's, from the case study. The architecture diagrams use Microsoft's Azure service icons unmodified, as Microsoft permits in architecture diagrams.
