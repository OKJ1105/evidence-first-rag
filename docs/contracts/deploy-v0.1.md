# Deployment Contract v0.1

## 1. Identifier and version

**Identifier:** `deploy-v0.1`

**Version:** `0.6.0` — the identifier names the document; the version tracks its obligations. The version changes when any observable obligation in Section 4, 5, 6, or 7 changes. Adding or removing a deployed process, a resource, an identity, a secret, a network path or a configuration key, or changing a registered limit, is a minor change. Adding a registered case that exercises an existing obligation is a patch change. Removing or weakening an obligation is not permitted at the contract layer; see Section 10.

This is the Milestone 5 contract that [Project Charter](../PROJECT_CHARTER.md) Section 9 asks for — "deployment, configuration, database-identity, secret-handling, and networking contracts" — and the one Charter Section 12 leaves to answer "the Azure authentication, networking, service sizing, retention, teardown, and operating budget within the fixed App Service and PostgreSQL Flexible Server topology". [api-v0.1](api-v0.1.md) Section 9 and [mcp-v0.1](mcp-v0.1.md) Section 9 defer authentication, rate limiting, TLS, logs and metrics to it. [relay-v0.1](relay-v0.1.md) defers its hosting, CORS origin and client address to it.

It registers no route, template, status, tool or fixture. It deploys the ones the four accepted contracts and `relay-v0.1` already fix, **unchanged**.

## 2. Status

**Status:** `Accepted 2026-09-25`

This contract is binding on implementation from that date under [Contract Shape Framework](README.md) Section 2.1. The repository owner reviewed it with [ADR-0005](../adr/0005-the-chat-relay-is-a-host-this-project-operates.md) and `relay-v0.1` in one sitting, recorded the open decisions on [#210](https://github.com/OKJ1105/evidence-first-rag/issues/210#issuecomment-5828675894) (database access: "allow Azure services"; the `/v1` preflight: option (a), implemented in `api-v0.1` `0.2.0`), and merged it in [#211](https://github.com/OKJ1105/evidence-first-rag/pull/211). The acceptance is the owner's merge of the pull request that moves this line ([#218](https://github.com/OKJ1105/evidence-first-rag/issues/218)). The owner-side Azure setup this contract builds on is recorded on [#205](https://github.com/OKJ1105/evidence-first-rag/issues/205).

**How this document reached here.** Drafted on [#210](https://github.com/OKJ1105/evidence-first-rag/issues/210). The budget figure was amended to 8,000 JPY in [#217](https://github.com/OKJ1105/evidence-first-rag/pull/217) while still `Proposed`. **`0.2.0`** replaces the deploy gate: GitHub's required reviewers are not available for this repository's plan and visibility, so the owner decided on [#205](https://github.com/OKJ1105/evidence-first-rag/issues/205#issuecomment-5844259676) that a deploy starts only when the owner starts it (Sections 4.2 and 4.3, `DP-013`), with no approval step and no automatic deploy. **It removes no obligation.** The obligation is a recorded human act by the owner before every deploy and before the database passwords are created; `0.2.0` changes that act from approving a queued run to starting it, and the `main`-only environment rule and the actor guard keep it the only path to the deploy identity. Recorded with a fresh design review on [#222](https://github.com/OKJ1105/evidence-first-rag/issues/222). **`0.3.0`** adds the resource Section 4.1 left out: both apps run "the image built from this repository's `Dockerfile`", and no resource held that image. The owner chose an Azure Container Registry on [#205](https://github.com/OKJ1105/evidence-first-rag/issues/205#issuecomment-5844641601). Recorded with a fresh design review on [#225](https://github.com/OKJ1105/evidence-first-rag/issues/225). **`0.4.0`** gives the deploy identity the Key Vault role Section 4.3 already needed: the workflow writes the generated database passwords and reads them back, and neither of its resource-group roles reads or writes a secret value. The owner decided on [#205](https://github.com/OKJ1105/evidence-first-rag/issues/205#issuecomment-5852648358) to grant it by hand. Recorded with a fresh design review on [#232](https://github.com/OKJ1105/evidence-first-rag/issues/232). **`0.4.1`** restates `DP-009` as the procedure that can observe it: two requests cannot show a shared key under a six-per-window limit, and seven malformed ones can, at no model cost ([#239](https://github.com/OKJ1105/evidence-first-rag/pull/239)). The obligation is unchanged. **`0.5.0`** carries `relay-v0.1` `0.3.0` ([ADR-0006](../adr/0006-relay-spend-is-bounded-by-the-provider-workspace.md), [#249](https://github.com/OKJ1105/evidence-first-rag/issues/249)): the Anthropic key comes from a Console workspace dedicated to the relay, whose monthly spend limit bounds spend, and `EFR_RELAY_DAILY_CEILING` is the registered 67. It removes no obligation. It adds no process, resource, identity, secret, network path or configuration key, so Section 10's design-review trigger does not apply; the design was reviewed with ADR-0006 on [#250](https://github.com/OKJ1105/evidence-first-rag/pull/250). **`0.6.0`** carries [ADR-0007](../adr/0007-the-writer-session-may-dispatch-the-deploy.md), decided by the owner on [#265](https://github.com/OKJ1105/evidence-first-rag/issues/265).
- **Who starts a run.** The Claude Code writer session may start the deploy as well as the owner. The recorded human decision for a deploy becomes the owner's merge of the commit to `main` (Section 4.2).
- **The checks mode.** The workflow gains a mode that runs the Section 4.8 checks against what is deployed and changes nothing (Section 4.8, `DP-017`).
- **The order.** The deployed checks run their fast groups first, and a failure there skips the slow ones.

It removes no check and no identity bound. The environment rule and the guard are unchanged.

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
| Azure Container Registry | **Basic** tier, the admin user **disabled**, holding the one image both apps run ([#205](https://github.com/OKJ1105/evidence-first-rag/issues/205#issuecomment-5844641601)) | The image Section 4.1 names has to live somewhere the apps can pull from without a secret |

**The image in the registry.** Each deploy pushes the image under an **immutable tag equal to the commit it was built from**, and configures both apps to pull that tag; no mutable tag such as `latest` is used. The deploy workflow **deletes no image and no tag**, so the last passing commit's image is always present for Section 4.8's rollback, which redeploys it by that tag. Each app pulls under its own system-assigned identity (the site setting that makes App Service use the managed identity for the registry, rather than a registry credential). Nothing in Section 4.6 changes: that setting is the platform's, not a key the process reads. **The registry and the apps' `AcrPull` assignments are created by the deploy workflow's provisioning definitions**, under the deploy identity's `Contributor` and Role Based Access Control Administrator roles on the resource group (#205); no one creates them by hand. **That App Service pulls from the registry under a system-assigned identity with the admin user disabled is expected and unverified here**; the first deploy and `DP-014` settle it. If it does not hold, the fix is an amendment to this contract, never enabling the admin user or storing a registry credential. The images the workflow keeps are small against the Basic tier's included storage; the Section 4.9 computation states that storage.


**Two apps, one image.** `relay-v0.1` Section 4.8 separates the Anthropic key from the database credential by process. Two apps on one plan give that separation at no extra plan cost, and one image keeps a second build from becoming a second runtime. **No other compute** — no Container Apps, no Functions, no VM — runs any part of this system.

### 4.2 Provisioning

The deployed database is built by **`evidence_first_rag.db.provision`, unchanged**: the same `sql/cluster` and `sql/database` files, the same lexical order, the same abort, and the same fixture loader in one transaction. That is the module CI's `database-checks` job runs and the local stack runs. Charter Section 9's Milestone 5 gate forbids "a second schema, fixture meaning, SQL-template behavior, or fallback runtime". A deployment that provisioned any other way would be that second path.

- It runs **from the deploy workflow**, in the GitHub Actions job that uses the `production` environment (#205).
  - **Who starts a run.** It runs only when **the owner or the Claude Code writer session** starts that run ([ADR-0007](../adr/0007-the-writer-session-may-dispatch-the-deploy.md), [#265](https://github.com/OKJ1105/evidence-first-rag/issues/265)).
  - **The guard.** The workflow's only trigger is `workflow_dispatch`. Its job ends before any step that logs in to Azure unless the actor and the triggering actor are both `OKJ1105` and the ref is `refs/heads/main`, so a re-run started by anyone else ends too.
  - **No automatic deploy.** Nothing deploys on push, merge, schedule or any other event, and no step waits on an approval: the environment has no required reviewers on this repository's plan.
  - **The recorded human decision** for a deploy is **the owner's merge of the commit to `main`**. The environment admits `main` only, and only the owner merges, so a run deploys nothing the owner did not merge. The run's triggering actor and URL are its evidence (Section 4.8).
  - **The account.** The actor check bounds the run to the owner's GitHub account, not to the owner in person, and the writer session dispatches through that account. So **no agent-loop run and no scheduled or event-driven automation dispatches the deploy workflow**. The writer session dispatches only on the owner's standing instruction.
- The server's administrator login plays the role the local stack's superuser plays: it runs `sql/cluster`. It is used by that job only, and never by an app.
- The job opens the server's firewall to its own runner address for **the provisioning step and the Section 4.8 deployed checks**, which also connect from the runner, and **closes it in a final step that runs whatever the result of either**.
- **Every deploy re-provisions**, with `--recreate`, from the commit being deployed, so the database and the image always come from one commit. Provisioning is re-runnable: `--recreate` rebuilds the application database from the committed files. There is no migration, and no state to preserve: `mvp-v0.1` Section 3.4 says "reproducibility comes from re-provisioning".

**What the first deployed run must show, because this contract cannot assume it.** Flexible Server's administrator is not a PostgreSQL superuser. `sql/cluster` creates two `NOSUPERUSER` roles, creates a database with `LC_COLLATE 'C'` from `template0`, and sets `statement_timeout` on a role. **That these succeed under the managed administrator is expected and unverified.** The data-level invariant check and the conformance runner already assert the collation and the timeout they got. So a managed service that silently substituted either fails the deployed run (Section 8) rather than passing it. If one fails, the fix is an amendment to this contract or to `mvp-v0.1` Section 3.4. It is never a deployment-only SQL file.

### 4.3 Identities and secrets

| Identity | Holds | Used by | Never |
| --- | --- | --- | --- |
| Deploy identity (#205) | nothing; federated, no secret | the deploy workflow in the `production` environment, started by the owner (Section 4.2) | an app |
| Deploy identity, on Key Vault | `Key Vault Secrets Officer`, scoped to the vault, granted by the owner in the portal ([#205](https://github.com/OKJ1105/evidence-first-rag/issues/205#issuecomment-5852648358)) | the deploy job only: writing the three database passwords on the first run, and reading them on every run | an app; reading, writing or naming `anthropic-api-key`; listing the vault's secrets; deleting or purging any secret (`DP-015`) |
| Server administrator | its password, in Key Vault | the provisioning step of the deploy job only | an app, a log |
| `mvp_provisioning` | its password, in Key Vault | the provisioning step and the deployed checks of the deploy job (the conformance runner's Group C data-level invariants connect as it) | an app |
| `mvp_runtime` | its password, in Key Vault | **`surface` only** | `relay` |
| Anthropic key | in Key Vault (#205, entered by the owner). **Issued from an Anthropic Console workspace that holds no other key, whose monthly spend limit is set as `relay-v0.1` Section 8.3 fixes** ([ADR-0006](../adr/0006-relay-spend-is-bounded-by-the-provider-workspace.md)); replacing the key repeats the owner's statement on [#249](https://github.com/OKJ1105/evidence-first-rag/issues/249) | **`relay` only** | `surface`; a key from any other workspace |
| `surface`, `relay` | a system-assigned managed identity each | reading **only** their own Key Vault secrets, and pulling the image (`AcrPull` on the registry) | any other secret; pushing an image |
| Deploy identity, on the registry | `AcrPush`, scoped to the registry | the deploy job's image push only. The apps' `AcrPull` assignments are created by the deploy identity's Role Based Access Control Administrator role on the resource group (#205), in the provisioning definitions, and by nothing else | an app |

- **The deploy workflow's secrets are exactly three**, named in the vault `postgres-admin-password` (the server administrator), `mvp-provisioning-password` and `mvp-runtime-password`. **The Secrets Officer role is vault-wide, so the Anthropic key is readable under it; the workflow never reads it**, and `DP-015` asserts it over every secret operation in the workflow file: each one names one of the three literally, none lists the vault, and none deletes or purges a secret. The role is bounded as the deploy identity itself is: the `main`-only environment rule and the actor guard (Section 4.2).
- **The database passwords are generated by the deploy workflow** on the first run, as random values, and written to Key Vault. They are never printed, and never stored in GitHub. The owner starts that run (Section 4.2), and starting it is the recorded human decision CLAUDE.md requires for creating a secret. A later run reads them and never regenerates them.
- **Each app reads its secrets through a Key Vault reference** in its settings, under its own identity. Its role on the vault is scoped to the secrets it needs, and no other. So `surface` cannot read the Anthropic key, and `relay` cannot read `mvp_runtime`'s password. `relay-v0.1` Section 4.8 is enforced by the vault, not by convention.
- **No password or token exists for the container registry**: its admin user is disabled, and every pull and push is by role (`DP-014`).
- **No secret is in the repository, in a workflow file, in a GitHub Secret, in a log, or in an image.** The GitHub environment holds only the non-secret identifiers #205 lists.
- **The `production` environment admits `main` only.** The federated credential trusts any job that names the `production` environment, and the Section 4.2 guard lives in the deploy workflow's own file. So the environment's deployment-branch rule is restricted to `main` ([#205](https://github.com/OKJ1105/evidence-first-rag/issues/205#issuecomment-5844343236)): a job on any other branch that names the environment is rejected by GitHub before it can request a token, and code reaches `main` only by the owner's merge. No other file under `.github/workflows/` names the environment (`DP-013`). The rule is a repository setting that nothing in this repository can read; its evidence is the owner's recorded statement on #205 (Section 8). No text in CLAUDE.md or AGENTS.md forbids a writer session from editing `.github/`, so the bound is this rule and the owner's merge, not a writing convention.
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
| The container registry | the two apps' identities (pull) and the deploy identity (push), by role; no admin user, no password, no token | Azure RBAC |

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
| `EFR_RELAY_DAILY_CEILING` | — | `67`, the number `relay-v0.1` Section 8.3 registers, passed by the deploy workflow as the `relayDailyCeiling` parameter |

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
3. **`DP-001` to `DP-010`, and `DP-014`** (Section 8.1); `DP-011` runs only on the failure path.
4. **`DP-012`, one `POST /chat` call**, which costs one model call. It asserts what the relay controls and not what the model writes: HTTP 200, a `content` array of only the Section 4.3 block types of `relay-v0.1`, a `scope_checks` entry per `discover_entity` call, and a `relay` key naming the registered model.

**Order.** The checks run in two tiers ([#265](https://github.com/OKJ1105/evidence-first-rag/issues/265)).
- **The fast tier runs first:** Azure resource state (`DP-014`, `DP-003`'s settings half), HTTP (`DP-005`, `DP-009`, `DP-010`, `DP-012`), and `DP-004`.
- **The slow tier follows:** the conformance runner (`DP-007`), the `WF-*` and `MC-*` rows, `DP-008`, and `DP-006`'s local comparison.
- **A failure in the fast tier skips the slow tier.** The run has already failed, so it is rolled back as below, and its artifact names the groups that did not run.
- **`DP-003`'s image, workflow and artifact scan always runs**, because it gates the artifact's upload.

**Checks mode** (`DP-017`). The workflow has a second mode that runs these checks against what is already deployed.
- **It changes no deployed resource:** no secret, template deployment, image, restart, provisioning, or rollback.
- **What it checks.** It reads the resource names from the newest succeeded template deployment. The commit under check is the image tag `surface` is running.
- **Narrowing.** It may be narrowed to named check groups.
- **Its artifact** records `mode: checks`. It is **never a rollback target and never the artifact this section commits**.
- **Its local comparison.** `DP-006` provisions locally from the checkout, which may be newer than the deployed commit. A difference that makes is reported, not hidden.

The run writes **one JSON artifact**, and the artifact is committed under `docs/acceptance/milestone-5/`, with the commit, the image digest, the date, **the run's triggering actor and its Actions run URL**. The last two are the named evidence of the owner's start of that deploy (Section 4.2). **A deploy whose run does not pass is rolled back in both halves.** The Section 4.1 tier has no deployment slots, and one database serves both apps, so there is no second environment to test in first. On a failed run the workflow **re-provisions the database from the last passing commit** with the Section 4.2 path, **and redeploys that commit's image**, and then re-runs `DP-006` against the restored state. `DP-011` asserts that the restored state digest's stable part (`DP-006`) equals the last passing run's. The failure is recorded in the artifact either way. **During a deploy, and during a rollback, the demo may answer `database_unavailable` or serve a mismatched pair for the minutes the steps take**; that is accepted for a demonstration deployment, and removing it needs a second database or a slotted tier, which is a later minor version.

### 4.9 Cost and teardown

- **Budget**: the owner's alert of **8,000 JPY per month** ([#205](https://github.com/OKJ1105/evidence-first-rag/issues/205#issuecomment-5829415863); raised from 3,000 JPY so that the base charges alone do not trip it). The topology in Section 4.1 is the smallest the Charter's fixed topology admits. **Whether it fits under that budget is not known to the writer and must be computed from live prices before the first deploy.** An App Service plan, a Flexible Server and the container registry all bill while they exist, whether or not anyone calls them, and the relay's model calls add to that. The computation is committed with its date beside the `relay-v0.1` Section 8.3 ceiling, and Section 9 carries the owner's decision if it does not fit. **API spend** is bounded by the Anthropic key's workspace spend limit (`relay-v0.1` Section 8.3, [ADR-0006](../adr/0006-relay-spend-is-bounded-by-the-provider-workspace.md)); the committed cost computations are under `docs/acceptance/milestone-5/`.
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
| Section 4.2 provisioning path | Automated: `DP-013`, the deploy starts only by hand, from `main`, through the owner's account. Recorded: the owner's merge of each deployed commit; the owner's decision on [#265](https://github.com/OKJ1105/evidence-first-rag/issues/265) that the writer session may start it (ADR-0007); for each deploy, the committed artifact's triggering actor and run URL (Section 4.8); for the environment's `main`-only rule, the owner's statement on [#205](https://github.com/OKJ1105/evidence-first-rag/issues/205#issuecomment-5844359363); `DP-001`, the deploy workflow invokes `evidence_first_rag.db.provision` and no other SQL; `DP-002`, the firewall rule opened for the runner is closed after the final step, whatever the result of provisioning or the deployed checks |
| Section 4.3 secrets | Recorded: the owner's statement on [#205](https://github.com/OKJ1105/evidence-first-rag/issues/205) (the comment is linked here when the owner records it) that the deploy identity holds `Key Vault Secrets Officer` on the vault. Automated: `DP-015`, the deploy workflow names only its three secrets; `DP-003`, a scan of the built image, the workflow files and the committed artifact for every secret pattern the sensitive-string scan defines, plus a check that `surface`'s settings name no `ANTHROPIC_API_KEY` and `relay`'s name no `MVP_RUNTIME_PASSWORD`; `RL-017` carries the same statement per process |
| Section 4.1, 4.3 and 4.5 registry | Automated, deployed: `DP-014` |
| Section 4.4 the runtime cannot write | Automated, deployed: `DP-004` |
| Section 4.6 the relay's daily ceiling | Automated: `DP-016` |
| Section 4.8 checks mode and order | Automated: `DP-017` |
| Section 4.5 networking | Automated, deployed: `DP-009` and `DP-010` for the rate-limit key and `/mcp` origins; `DP-005`, HTTP redirects to HTTPS on both apps, a cross-origin request from an origin other than the registered one is refused, and the database refuses a connection without TLS |
| Section 4.8 deployed conformance | Automated, deployed: the run itself; `DP-006` for the digests; `DP-011` for the rollback; `DP-007`, the conformance runner's verdict equals the local run's for every case |
| Section 4.7 logs | Automated: `DP-008`, a deployed request carrying a registered `SAMPLE_*` term, after which that term appears in no log line |
| Section 4.9 cost | Recorded human decision: the owner's acceptance of the committed cost computation ([#249](https://github.com/OKJ1105/evidence-first-rag/issues/249#issuecomment-5886519603)) |
| Section 4.3 Anthropic key workspace | Recorded: the owner's statement on [#249](https://github.com/OKJ1105/evidence-first-rag/issues/249) that the relay's key is issued from its dedicated workspace with the spend limit set, before the first deployed run (`relay-v0.1` Section 8.3) |
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
| `DP-009` | seven deployed `POST /chat` requests from one runner inside one rate-limit window, alternating a forged forwarded-for header and none, each with a body `relay-v0.1` refuses as malformed after counting it, so no model is called | the seventh is refused `rate_limited`: all seven were counted against the same rate-limit key |
| `DP-010` | deployed `/mcp`, called with no `Origin` and with a foreign `Origin` | the first is served; the second is refused |
| `DP-012` | one deployed `POST /chat` with the registered text `What is SAMPLE_ALIAS_GEARBOX_STATE?` | 200; only `relay-v0.1` Section 4.3 block types; `scope_checks` present; `relay.model` equals the registered model. The model's words are not asserted |
| `DP-013` | every file under `.github/workflows/` | the deploy workflow's only trigger is `workflow_dispatch`; **every** job that logs in to Azure names the `production` environment and has as its first condition `github.actor == 'OKJ1105'`, `github.triggering_actor == 'OKJ1105'` and `github.ref == 'refs/heads/main'`; no other workflow file names the `production` environment. That no approval is waited on is a property of the environment's settings (Section 4.2) and not of the file |
| `DP-014` | the deployed registry and its role assignments | the admin user is disabled; anonymous pull is disabled; the registry has no credential; no app setting carries a registry user name, password or token; the only role assignments scoped to it are `AcrPull` for each app's system-assigned identity and `AcrPush` for the deploy identity; neither app identity holds a push-capable role on it; both apps' configured image names a commit tag and not a mutable tag |
| `DP-015` | the deploy workflow definition | every `keyvault secret` operation carries an explicit `--name` whose value is one of `postgres-admin-password`, `mvp-provisioning-password` and `mvp-runtime-password`, or a variable bound only to those three; no operation lists the vault's secrets or selects one without naming it; no operation deletes, purges or backs up a secret; `anthropic-api-key` is named nowhere; the one `secret set` is reached only after a `secret show` of the same name has found nothing; a value is passed to `secret set` by file, never on a command line, and every value read into the job is masked before use |
| `DP-016` | the deploy workflow definition | the provisioning parameters pass `relayDailyCeiling` equal to the number `relay-v0.1` Section 8.3 registers, and Section 4.6 names the same number |
| `DP-017` | the deploy workflow definition | under `mode: checks`, every step that creates a secret, applies the template, builds or pushes an image, restarts an app, provisions the database or rolls back is skipped, and the template step exits before it applies anything; the fast tier runs before the slow tier, and a failure in the fast tier skips the slow tier; `DP-003`'s scan is outside the tiers and always runs; the artifact records the mode and the groups run and skipped; and a checks-mode record is never a rollback target |
| `DP-011` | a deploy whose conformance run is forced to fail | the database and image are the last passing commit's, and the `DP-006` comparison against the last passing run is equal |

### 8.2 Deferral of the acceptance evidence

Every `DP-*` case but `DP-001`, `DP-013`, `DP-015`, `DP-016` and `DP-017` needs the deployed resources, and the resources need #205's setup. They are therefore run by the first deploy after this contract's acceptance, not by this contract's pull request. `DP-001`, `DP-013`, `DP-015`, `DP-016` and `DP-017` read the workflow files or the committed records, so they run in the implementation slice's own checks. The implementation slice commits the workflow and the tests. The first deployed run commits the artifact. The Milestone 5 acceptance record cites both.

## 9. Deferred decisions

| Decision | Owner |
| --- | --- |
| **The `/v1` preflight (Section 4.5) — decided (a)** on [#210](https://github.com/OKJ1105/evidence-first-rag/issues/210#issuecomment-5828675894): an `api-v0.1` minor version, on its own slice with a fresh design review, admitting an `OPTIONS` preflight from the one registered origin on `/v1/select`, `/v1/query` and `/v1/discover`, answered before routing and with no result. ADR-0005 item 1 stands. | Done: `api-v0.1` `0.2.0`, contract in [#213](https://github.com/OKJ1105/evidence-first-rag/pull/213), implementation in [#215](https://github.com/OKJ1105/evidence-first-rag/pull/215). |
| **Database network access — decided**: "allow Azure services" (Section 4.5), with its cross-tenant residual accepted, over a private network, by the repository owner on [#210](https://github.com/OKJ1105/evidence-first-rag/issues/210#issuecomment-5828675894). | Decided. A private network later is a minor version. |
| **The deploy gate — decided**: the owner starts each deploy with `workflow_dispatch` ([#205](https://github.com/OKJ1105/evidence-first-rag/issues/205#issuecomment-5844259676)), and the `production` environment admits `main` only ([#205](https://github.com/OKJ1105/evidence-first-rag/issues/205#issuecomment-5844343236)), because GitHub's required reviewers are not available for this repository's plan and visibility | Decided. The branch rule's evidence is the owner's statement on #205 |
| **If the computed cost exceeds 8,000 JPY per month** (Section 4.9): raise the budget, stop the demo outside review periods, or accept a lower relay ceiling | The repository owner, when the computation is committed |
| The portfolio site's origin (Section 4.6) | A patch version, when the site's production URL exists |
| A custom domain | A later minor version |
| Structured metrics beyond the platform's built-in set, and an evaluation hook that samples deployed traffic | A later minor version, when observed use gives a reason. Charter Section 9's "evaluation-driven improvement loop" starts from the committed deployed runs |
| A privacy-safe feedback workflow | Charter Section 9, when real users exist |

## 10. Change control

- This contract is `Accepted`. Under [Contract Shape Framework](README.md) Section 7, a change that does not weaken a Charter or ADR invariant produces a new contract version with a recorded human decision. The looser rule that governed it while `Proposed` — amendment by an ordinary contract-only pull request — no longer applies.
- After acceptance, a change that does not weaken a Charter or ADR invariant produces a new version with a recorded human decision. Replacing how an obligation is discharged, when the platform cannot provide the original means and the obligation itself stands, is such a change (`0.2.0`, Section 2). Adding a process, a resource, an identity, a secret, a network path or a configuration key is a minor version and requires a fresh independent design review.
- **A deployment-only schema, SQL file, fixture, template or fallback runtime is not a contract-level change**: Charter Section 9 forbids it. **Giving `relay` a database credential or `surface` the Anthropic key** reverses ADR-0005 and `relay-v0.1` Section 4.8, and requires an ADR and a recorded human decision.
- A superseded version is retained with a `Superseded by` status rather than deleted.
