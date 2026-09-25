# Deployment Contract v0.1

## 1. Identifier and version

**Identifier:** `deploy-v0.1`

**Version:** `0.1.0` — the identifier names the document; the version tracks its obligations. The version changes when any observable obligation in Section 4, 5, 6, or 7 changes. Adding or removing a deployed process, an identity, a secret, a network path or a configuration key, or changing a registered limit, is a minor change. Adding a registered case that exercises an existing obligation is a patch change. Removing or weakening an obligation is not permitted at the contract layer; see Section 10.

This is the Milestone 5 contract that [Project Charter](../PROJECT_CHARTER.md) Section 9 asks for — "deployment, configuration, database-identity, secret-handling, and networking contracts" — and the one Charter Section 12 leaves to answer "the Azure authentication, networking, service sizing, retention, teardown, and operating budget within the fixed App Service and PostgreSQL Flexible Server topology". [api-v0.1](api-v0.1.md) Section 9 and [mcp-v0.1](mcp-v0.1.md) Section 9 defer authentication, rate limiting, TLS, logs and metrics to it. [relay-v0.1](relay-v0.1.md) defers its hosting, CORS origin and client address to it.

It registers no route, template, status, tool or fixture. It deploys the ones the four accepted contracts and `relay-v0.1` already fix, **unchanged**.

## 2. Status

**Status:** `Accepted 2026-09-25`

This contract is binding on implementation from that date under [Contract Shape Framework](README.md) Section 2.1. The repository owner reviewed it with [ADR-0005](../adr/0005-the-chat-relay-is-a-host-this-project-operates.md) and `relay-v0.1` in one sitting, recorded the open decisions on [#210](https://github.com/OKJ1105/evidence-first-rag/issues/210#issuecomment-5828675894) (database access: "allow Azure services"; the `/v1` preflight: option (a), implemented in `api-v0.1` `0.2.0`), and merged it in [#211](https://github.com/OKJ1105/evidence-first-rag/pull/211). The acceptance is the owner's merge of the pull request that moves this line ([#218](https://github.com/OKJ1105/evidence-first-rag/issues/218)). The owner-side Azure setup this contract builds on is recorded on [#205](https://github.com/OKJ1105/evidence-first-rag/issues/205).

**How this document reached here.** Drafted on [#210](https://github.com/OKJ1105/evidence-first-rag/issues/210). The budget figure was amended to 8,000 JPY in [#217](https://github.com/OKJ1105/evidence-first-rag/pull/217) while still `Proposed`.

**ADR-0005's status line still reads `Proposed`.** The owner adopted it as drafted on [#210](https://github.com/OKJ1105/evidence-first-rag/issues/210#issuecomment-5828675894) and merged it in [#207](https://github.com/OKJ1105/evidence-first-rag/pull/207). This is the same standing ADR-0004 has under the accepted `mcp-v0.1`: this repository's ADR status lines have not been moved on merge. A change to ADR-0005 that removes an item this contract implements is a change to this contract's authority, and it reopens this contract.

## 3. Scope

### 3.1 What this contract fixes

- **Topology**: the Azure resources, the processes, and which process holds which credential.
- **Provisioning**: how the deployed database is built, and that it is built by the path CI and the local stack already use.
- **Identities and secrets**: every credential, where it lives, and who reads it.
- **Networking**: what is reachable from where, TLS, CORS and host allowlists.
- **Configuration**: every environment key a deployed process reads.
- **Observability**: logs, metrics and retention, and what they never contain.
- **The deployed conformance run**, and what is committed from it.
- **Cost and teardown**: the budget the topology is sized against, and how the demo is stopped without losing the evidence.

### 3.2 What this contract does not fix

- **The portfolio site's hosting.** It stays on Cloudflare Pages under that repository's Blueprint. This contract fixes only the origin it may call from (Section 4.5).
- **A custom domain.** The deployment uses the platform's own `*.azurewebsites.net` host names. A custom domain is a later minor version.
- **User authentication.** None. ADR-0005 item 5: the goal is a link a reader opens. Section 4.5 states what bounds each public path instead.
- **A privacy-safe feedback workflow.** Charter Section 9 opens it "when real users exist". Not started.

### 3.3 What this contract inherits

| Inherited | From |
| --- | --- |
| PostgreSQL 17, no extensions, plain-SQL provisioning in lexical order with abort, `C` collation | `mvp-v0.1` Sections 3.4 and 6 |
| The two database identities, and the runtime identity's `SELECT`-only grants and `statement_timeout` | `mvp-v0.1` Sections 4.3 and 4.4, `entity-discovery-v0.1` Section 3.3 extension 2 |
| The single-command stack as the path a deployment reuses | `api-v0.1` Section 4.7, decision D on #169 |
| `/v1`, the page, `/mcp` and its host allowlist, served from one process | `api-v0.1` Section 4.1, `mcp-v0.1` Section 4.5 |
| `POST /chat`, its caps, and its process separation | `relay-v0.1` Sections 4.6 and 4.8 |

## 4. Normative requirements

### 4.1 Topology

| Resource | Setting | Why |
| --- | --- | --- |
| Resource group | the one created in #205, and **every** resource below inside it | One scope for the deploy identity's roles, the budget and teardown |
| Azure Database for PostgreSQL Flexible Server | PostgreSQL **17**, the lowest Burstable compute, the smallest storage, no high availability, backup retention at the minimum | `mvp-v0.1` Section 3.4; the data is synthetic and re-provisionable, so HA and long backups buy nothing (Section 4.2) |
| App Service plan | one Linux plan, the lowest tier that runs two always-available apps | Section 4.9 |
| App **`surface`** | the image built from this repository's `Dockerfile`, entry point `evidence_first_rag.api.serve:build` — `/v1`, `/mcp`, the page | The same image `api-v0.1` Section 4.7's stack builds, unchanged |
| App **`relay`** | the same image, entry point the relay's | `relay-v0.1` Section 4.8 needs a second process, not a second image |
| Key Vault | the one created in #205 | Section 4.3 |

**Two apps, one image.** `relay-v0.1` Section 4.8 separates the Anthropic key from the database credential by process. Two apps on one plan give that separation at no extra plan cost, and one image keeps a second build from becoming a second runtime. **No other compute** — no Container Apps, no Functions, no VM — runs any part of this system.

### 4.2 Provisioning

The deployed database is built by **`evidence_first_rag.db.provision`, unchanged**: the same `sql/cluster` and `sql/database` files, the same lexical order, the same abort, and the same fixture loader in one transaction. That is the module CI's `database-checks` job runs and the local stack runs. Charter Section 9's Milestone 5 gate forbids "a second schema, fixture meaning, SQL-template behavior, or fallback runtime". A deployment that provisioned any other way would be that second path.

- It runs **from the deploy workflow**, in the GitHub Actions job gated by the `production` environment (#205), which means **after the owner's approval of that run**.
- The server's administrator login plays the role the local stack's superuser plays: it runs `sql/cluster`. It is used by that job only, and never by an app.
- The job opens the server's firewall to its own runner address for **the provisioning step and the Section 4.8 deployed checks**, which also connect from the runner, and **closes it in a final step that runs whatever the result of either**.
- **Every deploy re-provisions**, with `--recreate`, from the commit being deployed, so the database and the image always come from one commit. Provisioning is re-runnable: `--recreate` rebuilds the application database from the committed files. There is no migration, and no state to preserve: `mvp-v0.1` Section 3.4 says "reproducibility comes from re-provisioning".

**What the first deployed run must show, because this contract cannot assume it.** Flexible Server's administrator is not a PostgreSQL superuser. `sql/cluster` creates two `NOSUPERUSER` roles, creates a database with `LC_COLLATE 'C'` from `template0`, and sets `statement_timeout` on a role. **That these succeed under the managed administrator is expected and unverified.** The data-level invariant check and the conformance runner already assert the collation and the timeout they got. So a managed service that silently substituted either fails the deployed run (Section 8) rather than passing it. If one fails, the fix is an amendment to this contract or to `mvp-v0.1` Section 3.4. It is never a deployment-only SQL file.

### 4.3 Identities and secrets

| Identity | Holds | Used by | Never |
| --- | --- | --- | --- |
| Deploy identity (#205) | nothing; federated, no secret | the deploy workflow in the `production` environment | an app |
| Server administrator | its password, in Key Vault | the provisioning step of the deploy job only | an app, a log |
| `mvp_provisioning` | its password, in Key Vault | the provisioning step and the deployed checks of the deploy job (the conformance runner's Group C data-level invariants connect as it) | an app |
| `mvp_runtime` | its password, in Key Vault | **`surface` only** | `relay` |
| Anthropic key | in Key Vault (#205, entered by the owner) | **`relay` only** | `surface` |
| `surface`, `relay` | a system-assigned managed identity each | reading **only** their own Key Vault secrets | any other secret |

- **The database passwords are generated by the deploy workflow** on the first run, as random values, and written to Key Vault. They are never printed, and never stored in GitHub. The owner approves that run in the `production` environment, and that approval is the recorded human decision CLAUDE.md requires for creating a secret. A later run reads them and never regenerates them.
- **Each app reads its secrets through a Key Vault reference** in its settings, under its own identity. Its role on the vault is scoped to the secrets it needs, and no other. So `surface` cannot read the Anthropic key, and `relay` cannot read `mvp_runtime`'s password. `relay-v0.1` Section 4.8 is enforced by the vault, not by convention.
- **No secret is in the repository, in a workflow file, in a GitHub Secret, in a log, or in an image.** The GitHub environment holds only the non-secret identifiers #205 lists.
- The deployed `surface` holds **no** `ANTHROPIC_API_KEY`, so `/v1/ask` answers `adapter_unavailable` in the deployment. That is `api-v0.1` Section 4.5's arrangement, and it matches #203: the route stays served and is not the documented path.

### 4.4 The runtime identity cannot write

Charter Section 9's gate: "the deployed runtime identity cannot write data or change the schema". It holds by the same grants `mvp-v0.1` Section 4.3 fixes and `tests_database/test_roles.py` pins locally. The deployed run re-asserts it **against the deployed server**: an `INSERT`, `UPDATE`, `DELETE`, `CREATE` and `DROP` as `mvp_runtime` each fail with a privilege error (`DP-004`).

### 4.5 Networking

| Path | Reachable from | Bounded by |
| --- | --- | --- |
| `surface` `/v1`, the page, `/mcp` | the public internet, HTTPS only | read-only grants over synthetic fixtures; `statement_timeout`; per-template row limits (`mvp-v0.1` Section 4.4); the plan's fixed cost. **No per-call spend exists on this path.** |
| `relay` `POST /chat` | the public internet, HTTPS only | `relay-v0.1` Section 4.6's caps, checked before any model call |
| The database | **only** from Azure services, by the server's "allow Azure services" rule; and from the deploy job's runner, during the provisioning step and the deployed checks only | the server firewall; TLS required |
| Key Vault | the two apps' identities and the deploy identity, by role | Azure RBAC |

- **HTTPS only** on both apps, with HTTP redirected. TLS terminates at the platform, and the database connection requires TLS (`PGSSLMODE=require`).
- **CORS**: `relay` allows exactly one origin, the portfolio site's production origin, recorded in Section 4.6 once it is known. `surface` allows the same origin on `/v1/select`, `/v1/query` and `/v1/discover`, which the page calls (`relay-v0.1` P3). Nothing else is allowed from a browser. **This collides with an `Accepted` contract, and the owner decided how it is resolved (Section 9, option (a)).** A browser sends an `OPTIONS` preflight before a cross-origin JSON `POST`, and `api-v0.1` Section 4.5 answers every method but `POST` on a `/v1` route with `method_not_allowed`. Under `api-v0.1` `0.1.2`, then, the page's calls to `/v1` would have been blocked by the browser. This contract does not answer that by changing `api-v0.1` itself: option (a) did, as `api-v0.1` `0.2.0` (Section 4.5, the preflight from the one origin named by `EFR_CORS_ORIGIN`), implemented in [#215](https://github.com/OKJ1105/evidence-first-rag/pull/215).
- **`/mcp`'s host allowlist** (`mcp-v0.1` Section 4.5) is widened to `surface`'s host name with `EFR_MCP_ALLOWED_HOSTS`. The Messages API connector reaches `/mcp` from Anthropic's side over public HTTPS (ADR-0005, Context).
- **The client address** that `relay-v0.1` Section 4.6 rate-limits is the address **the platform's front end appends** to the forwarded-for header, which is its last entry, and never an entry the request already carried. A caller can write any value into that header; only the entry the platform adds is the caller's connection. `DP-009` asserts, against the deployed relay, that a request carrying its own forwarded-for header is rate-limited on the same key as one carrying none. **That the platform appends rather than replaces is expected and unverified here**; `DP-009` settles it, and a different platform behaviour is a patch to this bullet, not a relaxed check.

**No rate limit on `surface`, decided rather than left open.** `api-v0.1` Section 9 and `mcp-v0.1` Section 9 defer rate limiting to this contract. This contract registers **none** for `/v1`, the page and `/mcp`, on the ground in the table above: those paths carry no per-call spend, the plan's cost is fixed whatever the request volume, and each request is bounded by the read-only grants, the statement timeout and the template row limits. The cost of a flood is degraded service for the demo, not money. The two deferral rows close here. Adding a limit later is a minor version.

**The residual this accepts.** "Allow Azure services" admits connections from any Azure tenant's services, not only this subscription's. The database still requires a password that only `surface` and the deploy job hold, and it holds only synthetic data. A private network (VNet integration and a private endpoint) closes that gap at additional cost, and the owner decides it in Section 9.

### 4.6 Configuration

Every key a deployed process reads. Nothing else is read, and nothing here is a secret unless marked as a Key Vault reference.

| Key | `surface` | `relay` |
| --- | --- | --- |
| `PGHOST`, `PGPORT`, `MVP_DATABASE` | the server, 5432, the application database | — |
| `PGSSLMODE` | `require` | — |
| `MVP_RUNTIME_PASSWORD` | Key Vault reference | — |
| `EFR_MCP_ALLOWED_HOSTS` | `surface`'s host name | — |
| `EFR_MCP_ALLOWED_ORIGINS` | **unset**, so loopback origins only: the Messages API connector calls `/mcp` server to server and is expected to send no `Origin`, and a browser has no reason to call `/mcp`. `DP-010` asserts both halves on the deployed `/mcp` | — |
| `EFR_CORS_ORIGIN` | the portfolio site's origin | the portfolio site's origin |
| `ANTHROPIC_API_KEY` | — | Key Vault reference |
| `EFR_RELAY_MCP_URL` | — | `https://<surface host>/mcp` |
| `EFR_RELAY_DAILY_CEILING` | — | the number `relay-v0.1` Section 8.3 registers |

**The portfolio site's origin** is recorded in this table as a patch version once the site's production URL exists. Until then `EFR_CORS_ORIGIN` is unset, and an unset value allows **no** cross-origin call. It is never a wildcard.

### 4.7 Observability

- Both apps write **one JSON line per request** to standard output: timestamp, path, HTTP status, latency, and for a result its `status`, or for a refusal its kind. `relay` adds what `relay-v0.1` Section 4.10 lists, and no more.
- **No log line carries a request body, a message text, a bound parameter value, a row, or a credential.** A request identifier may be logged, and a person's words may not.
- Logs go to the platform's built-in log store, retained **7 days**. Metrics are the platform's built-in request count, latency and HTTP status per app. **No additional monitoring service**: whether one fits under the Section 4.9 budget is not known until that section's cost computation is committed, and adding one is a later minor version (Section 9).
- **Failure classification** (Charter Section 9: data, retrieval, contract, runtime, presentation) is read off what is already logged. A refusal kind or an HTTP status is **runtime**. A registered negative status is **data** or **retrieval**, as its contract assigns it. A deployed-run mismatch is **contract**. A page defect is **presentation**, reported by the site's slice. No new field is invented for it.

### 4.8 The deployed conformance run

Charter Section 9's first gate item: "the deployed environment passes the same representative conformance and end-to-end contracts as the local PostgreSQL environment". After every deploy, the workflow runs, **against the deployed resources**:

1. **The `mvp-v0.1` Section 4.9 conformance runner** against the deployed database, over every registered fixture case: **as the runtime identity for every request**, and as `mvp_provisioning` for its Group C data-level invariants only, exactly as it connects in CI. It runs from the deploy job's runner, inside the firewall window Section 4.2 opens. It uses the same committed expected results CI compares against.
2. **The `api-v0.1` `WF-*` and `mcp-v0.1` `MC-*` equality cases**, over HTTPS against `surface`, for every case that needs no model.
3. **`DP-001` to `DP-010`** (Section 8.1); `DP-011` runs only on the failure path.
4. **`DP-012`, one `POST /chat` call**, which costs one model call. It asserts what the relay controls and not what the model writes: HTTP 200, a `content` array of only the Section 4.3 block types of `relay-v0.1`, a `scope_checks` entry per `discover_entity` call, and a `relay` key naming the registered model.

The run writes **one JSON artifact**, and the artifact is committed under `docs/acceptance/milestone-5/`, with the commit, the image digest and the date. **A deploy whose run does not pass is rolled back in both halves.** The Section 4.1 tier has no deployment slots, and one database serves both apps, so there is no second environment to test in first. On a failed run the workflow **re-provisions the database from the last passing commit** with the Section 4.2 path, **and redeploys that commit's image**, and then re-runs `DP-006` against the restored state. `DP-011` asserts that the restored state digest's stable part (`DP-006`) equals the last passing run's. The failure is recorded in the artifact either way. **During a deploy, and during a rollback, the demo may answer `database_unavailable` or serve a mismatched pair for the minutes the steps take**; that is accepted for a demonstration deployment, and removing it needs a second database or a slotted tier, which is a later minor version.

### 4.9 Cost and teardown

- **Budget**: the owner's alert of **8,000 JPY per month** ([#205](https://github.com/OKJ1105/evidence-first-rag/issues/205#issuecomment-5829415863); raised from 3,000 JPY so that the base charges alone do not trip it). The topology in Section 4.1 is the smallest the Charter's fixed topology admits. **Whether it fits under that budget is not known to the writer and must be computed from live prices before the first deploy.** An App Service plan and a Flexible Server both bill while they exist, whether or not anyone calls them, and the relay's model calls add to that. The computation is committed with its date beside the `relay-v0.1` Section 8.3 ceiling, and Section 9 carries the owner's decision if it does not fit.
- **Stopping the demo** stops the Flexible Server and the apps. It does not delete the resource group. Charter Section 9 requires that "reproducible provisioning definitions and a recorded deployed conformance run remain available even if the demo environment is later stopped". The definitions are in this repository, and the run is committed (Section 4.8). **Neither lives only in Azure.**
- **Teardown** deletes the resource group. Everything in it is re-creatable from this repository and #205, except the Anthropic key, which the owner re-enters.

## 5. Outcome coverage

This contract produces **no result status**. Every status a person sees is one the four contracts and `relay-v0.1` already fix, unchanged. The deployment adds exactly one new way to fail, **a deploy whose conformance run does not pass**, and Section 4.8 fixes its outcome: the previous deployment stays, and the failure is recorded.

## 6. Determinism

The deployed runtime carries `mvp-v0.1` Section 6 and `entity-discovery-v0.1` Section 6 unchanged: `C` collation, registered ordering, and repeatable provisioning. **Repeatability across environments is asserted, not assumed**: `DP-006` compares, between the deployed provisioning and the local provisioning of the same commit, **the row count of every table, the `registry_digest`, and the committed template digests** the conformance artifact records. They are equal, or the deploy fails. **The `mvp-v0.1` Section 4.10 state digest's highest transaction identifier is excluded**: it is a property of one database instance, compared by that section before and after a single run, and two instances number their transactions independently.

## 7. Evidence obligations

Unchanged. The deployment adds nothing to `evidence_bundle`, `source_trace` or `limitations`, and removes nothing. **Source traces name only artifacts in this repository** (Charter Section 11): a deployed result's trace names the same committed fixture files as a local one, never an Azure resource, host name or connection string.

## 8. Acceptance evidence

| Obligation | Evidence |
| --- | --- |
| Section 4.2 provisioning path | Automated: `DP-001`, the deploy workflow invokes `evidence_first_rag.db.provision` and no other SQL; `DP-002`, the firewall rule opened for the runner is closed after the final step, whatever the result of provisioning or the deployed checks |
| Section 4.3 secrets | Automated: `DP-003`, a scan of the built image, the workflow files and the committed artifact for every secret pattern the sensitive-string scan defines, plus a check that `surface`'s settings name no `ANTHROPIC_API_KEY` and `relay`'s name no `MVP_RUNTIME_PASSWORD`; `RL-017` carries the same statement per process |
| Section 4.4 the runtime cannot write | Automated, deployed: `DP-004` |
| Section 4.5 networking | Automated, deployed: `DP-009` and `DP-010` for the rate-limit key and `/mcp` origins; `DP-005`, HTTP redirects to HTTPS on both apps, a cross-origin request from an origin other than the registered one is refused, and the database refuses a connection without TLS |
| Section 4.8 deployed conformance | Automated, deployed: the run itself; `DP-006` for the digests; `DP-011` for the rollback; `DP-007`, the conformance runner's verdict equals the local run's for every case |
| Section 4.7 logs | Automated: `DP-008`, a deployed request carrying a registered `SAMPLE_*` term, after which that term appears in no log line |
| Section 4.9 cost | Recorded human decision: the owner's acceptance of the committed cost computation |
| The Milestone 5 gate as a whole | The Milestone 5 acceptance record, citing the committed deployed run and this table |

### 8.1 Registered cases

| Case | Where | Expected |
| --- | --- | --- |
| `DP-001` | the deploy workflow definition | provisioning is exactly `python -m evidence_first_rag.db.provision` with the committed `sql/` and `fixtures/` |
| `DP-002` | the deploy workflow, with the provisioning step forced to fail and, separately, a deployed check forced to fail | the runner's firewall rule is absent after the final step in both |
| `DP-003` | image, workflows, artifact, app settings | no secret; neither app holds the other's credential |
| `DP-004` | deployed database, as `mvp_runtime` | `INSERT`, `UPDATE`, `DELETE`, `CREATE`, `DROP` each refused with a privilege error |
| `DP-005` | both apps and the database | HTTP → HTTPS redirect; foreign origin refused; non-TLS connection refused |
| `DP-006` | deployed and local provisioning of one commit | equal row count per table, `registry_digest` and template digests; the highest transaction identifier is not compared |
| `DP-007` | the conformance runner, deployed and local | equal verdicts on every registered case |
| `DP-008` | one deployed request with a `SAMPLE_*` term, then the log store | the term is in no log line |
| `DP-009` | two deployed `POST /chat` requests from one runner, one carrying a forged forwarded-for header | both counted against the same rate-limit key |
| `DP-010` | deployed `/mcp`, called with no `Origin` and with a foreign `Origin` | the first is served; the second is refused |
| `DP-012` | one deployed `POST /chat` with the registered text `What is SAMPLE_ALIAS_GEARBOX_STATE?` | 200; only `relay-v0.1` Section 4.3 block types; `scope_checks` present; `relay.model` equals the registered model. The model's words are not asserted |
| `DP-011` | a deploy whose conformance run is forced to fail | the database and image are the last passing commit's, and the `DP-006` comparison against the last passing run is equal |

### 8.2 Deferral of the acceptance evidence

Every `DP-*` case needs the deployed resources, and the resources need #205's setup. They are therefore run by the first deploy after this contract's acceptance, not by this contract's pull request. The implementation slice commits the workflow and the tests. The first deployed run commits the artifact. The Milestone 5 acceptance record cites both.

## 9. Deferred decisions

| Decision | Owner |
| --- | --- |
| **The `/v1` preflight (Section 4.5) — decided (a)** on [#210](https://github.com/OKJ1105/evidence-first-rag/issues/210#issuecomment-5828675894): an `api-v0.1` minor version, on its own slice with a fresh design review, admitting an `OPTIONS` preflight from the one registered origin on `/v1/select`, `/v1/query` and `/v1/discover`, answered before routing and with no result. ADR-0005 item 1 stands. | That `api-v0.1` slice. This contract's `/v1` CORS takes effect only once it is accepted. |
| **Database network access — decided**: "allow Azure services" (Section 4.5), with its cross-tenant residual accepted, over a private network, by the repository owner on [#210](https://github.com/OKJ1105/evidence-first-rag/issues/210#issuecomment-5828675894). | Decided. A private network later is a minor version. |
| **If the computed cost exceeds 8,000 JPY per month** (Section 4.9): raise the budget, stop the demo outside review periods, or accept a lower relay ceiling | The repository owner, when the computation is committed |
| The portfolio site's origin (Section 4.6) | A patch version, when the site's production URL exists |
| A custom domain | A later minor version |
| Structured metrics beyond the platform's built-in set, and an evaluation hook that samples deployed traffic | A later minor version, when observed use gives a reason. Charter Section 9's "evaluation-driven improvement loop" starts from the committed deployed runs |
| A privacy-safe feedback workflow | Charter Section 9, when real users exist |

## 10. Change control

- This contract is `Accepted`. Under [Contract Shape Framework](README.md) Section 7, a change that does not weaken a Charter or ADR invariant produces a new contract version with a recorded human decision. The looser rule that governed it while `Proposed` — amendment by an ordinary contract-only pull request — no longer applies.
- After acceptance, a change that does not weaken a Charter or ADR invariant produces a new version with a recorded human decision. Adding a process, an identity, a secret, a network path or a configuration key is a minor version and requires a fresh independent design review.
- **A deployment-only schema, SQL file, fixture, template or fallback runtime is not a contract-level change**: Charter Section 9 forbids it. **Giving `relay` a database credential or `surface` the Anthropic key** reverses ADR-0005 and `relay-v0.1` Section 4.8, and requires an ADR and a recorded human decision.
- A superseded version is retained with a `Superseded by` status rather than deleted.
