# Milestone 5 Acceptance Record

**Milestone:** 5 — Azure deployment and learning loop

**Disposition:** *Pending — the repository owner's to record.*

**Date:** *set when the owner records the disposition*

**Recorded by:** *the repository owner*

This record collects the evidence for the Milestone 5 acceptance gate in [Project Charter](../PROJECT_CHARTER.md) Section 9. For each gate item it names the evidence that exists: a deployed check registered in [`deploy-v0.1`](../contracts/deploy-v0.1.md) Section 8.1, a field of a committed deploy record, or contract text. Where the only evidence is contract text, the record says so. Claude Code, the writer session, drafted this record from that evidence. **The disposition is the owner's alone.**

## The run this record rests on

The latest passing deploy, which `deploy-v0.1` Section 4.8's rollback reads as its target:

| | |
| --- | --- |
| Committed record | [`milestone-5/deploy-f8b82e6cc96a993d596e3a7a98372f293db5dd03.json`](milestone-5/deploy-f8b82e6cc96a993d596e3a7a98372f293db5dd03.json) |
| Its files | [`milestone-5/run-37308165456/`](milestone-5/run-37308165456/) |
| Actions run | [37308165456](https://github.com/OKJ1105/evidence-first-rag/actions/runs/37308165456), `mode: deploy`, commit `f8b82e6`, 2026-10-05 |
| Outcome | `success`; `deployed_checks: pass`; all seven groups ran (`AZURE HTTP DP-004 DP-007 WF/MC DP-008 DP-006`); no rollback |

[`milestone-5/README.md`](milestone-5/README.md) lists every earlier deploy record. Each is committed unedited, as Section 4.8 requires.

## Gate item 1 — The deployed environment passes the same representative conformance and end-to-end contracts as the local PostgreSQL environment

- **`DP-007`:** the conformance runner reaches equal verdicts on every registered case, deployed and local. `conformance.json` and `local-conformance.json` both read `verdict: pass`. `compare.json` records `DP-007` passed.
- **WF/MC group:** the deployed run executes the `api-v0.1` `WF-*` and `mcp-v0.1` `MC-*` rows that need no model. The group ran and passed.
- **`DP-012`:** one `POST /chat` with the registered text reached `discover_entity` and was answered by a tool result. `http-checks.json` shows 200, three blocks, and one call answered.

Code: `src/evidence_first_rag/deploy/digests.py` and `deploy/http_checks.py`. Tests: `tests/test_deploy_digests.py` and `tests/test_deploy_http_checks.py`.

## Gate item 2 — Reproducible provisioning definitions and a recorded deployed conformance run remain available even if the demo environment is later stopped

- **Provisioning is in the repository:** `infra/main.bicep` and `.github/workflows/deploy.yml`. `DP-001`, `DP-013`, and `DP-015` to `DP-018` are asserted statically over the workflow definition in `tests/test_deploy_workflow.py`, on every pull request.
- **The recorded runs are committed files,** not live resources. They are the deploy records and run directories under `docs/acceptance/milestone-5/`. Stopping or deleting the Azure resources removes none of them.

## Gate item 3 — Deployment does not introduce a second schema, fixture meaning, SQL-template behavior, or fallback runtime

- **`DP-001`:** provisioning is exactly `python -m evidence_first_rag.db.provision`, run with the committed `sql/` and `fixtures/`.
- **`DP-006`:** deployed and local provisioning of one commit have equal row counts per table, an equal `registry_digest`, and equal template digests. `compare.json` records `DP-006` passed. `stable-digest.json` equals `local-stable-digest.json`.
- **One image:** both apps run the image built from the repository's `Dockerfile`, pulled by its commit tag (Section 4.1). The `DP-014 surface image` and `DP-014 relay image` rows pass in this run's `azure-checks.json`.

## Gate item 4 — The deployed runtime identity cannot write data or change the schema

`DP-004` connects to the deployed database as `mvp_runtime`. In this run's `writes.json`, `INSERT`, `UPDATE`, `DELETE`, `CREATE` and `DROP` are each `refused`. The refusal comes from PostgreSQL privileges, not from an application guard. Code: `deploy/deployed.py`. Test: `tests/test_deploy_deployed.py`.

## Gate item 5 — Secrets and environment-specific configuration stay outside the repository

- **`DP-003`:** no secret in the image, the workflows, the artifact or the app settings, and neither app holds the other's credential. See `secret-scan.json`, `secret-scan-record.json`, and the settings row of `azure-checks.json`.
- **`DP-014` and `DP-015`:** the registry holds no credential, and Key Vault operations name only the three registered secrets.
- **Environment-specific identifiers** are read from the `production` environment's variables (`vars.AZURE_*`). No value appears in the repository. The pre-release content review on [#311](https://github.com/OKJ1105/evidence-first-rag/issues/311#issuecomment-5996203716) read the whole history and found none.
- **Recorded owner statements** cover what a check cannot see: the Key Vault role ([#205](https://github.com/OKJ1105/evidence-first-rag/issues/205)) and the Anthropic workspace ([#249](https://github.com/OKJ1105/evidence-first-rag/issues/249)).

## Gate item 6 — Observed failures can be classified as data, retrieval, contract, runtime, or presentation problems

**Contract text only.** `deploy-v0.1` Section 4.7 fixes the classification and reads it off fields already logged:

- a refusal kind or an HTTP status is **runtime**;
- a registered negative status is **data** or **retrieval**, as its contract assigns it;
- a deployed-run mismatch is **contract**;
- a page defect is **presentation**.

Each app writes one JSON line per request carrying those fields. No deployed check asserts the classification, and no committed artifact shows an observed failure being classified. The owner has to decide whether a classification that is defined but not yet exercised meets this item.

## The deliverables

| Charter deliverable | Where it stands |
| --- | --- |
| Deployment of the same runtime to App Service and PostgreSQL Flexible Server | Done; gate items 1 and 3. |
| Deployment, configuration, identity, secret and networking contracts | `deploy-v0.1` and `relay-v0.1`, with ADR-0005 to ADR-0007. |
| Least-privilege read-only database access | `DP-004`; gate item 4. |
| Structured logs | One JSON line per request (Section 4.7). `DP-008` and `DP-020` assert what the lines must not contain. No check asserts the line's schema. |
| Latency/error metrics | The platform's built-in request count, latency and status per app only. No metrics artifact is committed. |
| Evaluation hooks and an evaluation-driven improvement loop | **Deferred** by `deploy-v0.1` Section 9 to a later minor version, "when observed use gives a reason". The loop starts from the committed deployed runs. |
| A privacy-safe user-feedback workflow, when real users exist | **Deferred** by `deploy-v0.1` Section 9 until real users exist. |

## What this record does not claim

- **Two deployed cases have never run.** `DP-011`, the rollback after a forced conformance failure, has `dp_011: null` in every committed record; only the workflow-definition test covers it. `DP-002`, the firewall rule's removal after a forced failure, has no committed evidence. Both need a deliberately failed deploy.
- **What is still unobserved in production** is listed in [`docs/limitations.md`](../limitations.md): the daily ceiling, the conversation limit, `model_unavailable`, and cold-start latency. The per-address daily limit and the chat-to-`/v1/select` path were observed by the owner on 2026-10-05; the screenshots are not committed.
- **Model prose is not checked,** and whether the model calls `discover_entity` is outside this repository's control.
- **There is no monitoring** beyond the platform's built-in metrics, and no on-call.

## Effect

- Once the owner records a disposition here, Milestone 5 closes. The deferred deliverables stay deferred under `deploy-v0.1` Section 9, and none is claimed here.
- A later deploy that fails its checks rolls back to the record above, by Section 4.8. A committed passing record replaces it as the rollback target, and does not reopen this gate.
