# Limitations

What this repository and its deployed demo do not do, or do not establish. Project Charter Section 11 requires this page before a public release. Each item names where the detail lives. It is a summary written on 2026-10-03, and the linked contract or record is authoritative where they differ.

## The data

- **Every fact comes from synthetic fixtures.** Every identifier is `SAMPLE_*`. There is no real DBC, ARXML or production data, and no ingestion path for one: the initial implementation starts from normalized synthetic fixtures, and Section 11 keeps every fixture synthetic ([Charter](PROJECT_CHARTER.md); [`fixtures/`](../fixtures/)).
- **The data is small and hand-curated.** The fixtures (`fixtures/*.jsonl`) hold four snapshots, seven messages, thirteen signals and three mappings, and the approved registry (`fixtures/registry/`) holds seventeen entities and six aliases. What the runtime and discovery show at this scale says nothing about their behaviour on a real network database.

## What the evaluations establish

- **The discovery evaluation's forty cases were authored by an AI session that had read the tier table the method implements.** No method was run over a case before it was registered. But that is a construct-validity limitation, and it is why forty of forty cases land on their registered outcome ([Milestone 3 acceptance](acceptance/milestone-3.md)).
- **Adopting the adapter (Milestone 2) and `M-LEX-1` (Milestone 3) are the owner's recorded decisions,** made against registered thresholds. A threshold met on this data is not a claim about other data ([Milestone 2](acceptance/milestone-2.md), [Milestone 3](acceptance/milestone-3.md)).

## The chat relay

- **The model's prose is not checked.** Facts reach the page only from the `/v1` routes, never from the model's text ([`relay-v0.1`](contracts/relay-v0.1.md), Section 4.7). What the model writes can still be unhelpful or wrong about anything that is not a fact.
- **Whether the model calls `discover_entity` is not in this repository's control.** Before `relay-v0.1` `0.5.0`, three deployed runs answered an ordinary question without calling it (#286). Since `0.5.0` the deployed check (`DP-012`) has seen the call on every run, which is evidence, not a guarantee.
- **The committed worst-case cost record predates the `0.5.0` system prompt.** Spend is bounded by the Anthropic workspace's monthly limit, not by that record (`relay-v0.1` Section 2 and Section 8.3; [ADR-0006](adr/0006-relay-spend-is-bounded-by-the-provider-workspace.md)).

## The deployed demo

- **It is a demo, with no availability commitment.** It runs as one instance per app in one region (Japan East), with the platform's built-in metrics and no other monitoring. There is no on-call rota and no runbook. Recovery is a run of the deploy workflow, which restarts both apps and rolls back on a failed check ([`deploy-v0.1`](contracts/deploy-v0.1.md), Sections 4.7 to 4.9).
- **The caps can stop it for a day.**
  - Relay limits: 6 requests a minute and 60 a UTC day per client address, 10 person's turns per conversation, and 67 model calls a UTC day for everyone ([`relay-v0.1`](contracts/relay-v0.1.md), Sections 4.6 and 8.3).
  - Once the daily ceiling is reached, every chat request is refused until the UTC day ends or the relay restarts.
  - The caps are held in memory, so a restart resets them.
  - When the workspace's monthly spend limit is reached, every model call fails and the relay answers `model_unavailable`.
- **There is no authentication.** Anyone may call the public routes. CORS admits one browser origin, but it decides only which page a browser lets read the reply. It is not access control ([`relay-v0.1`](contracts/relay-v0.1.md), Section 4.1).
- **What is recorded about a request.**
  - The apps' own logs carry no person's words and no client address. That is asserted on each deploy by `DP-008` and `DP-020`.
  - The platform's management-site traces do hold the address of the deploy job that read them.
  - That the apps saw the deploy job under the address `DP-020` searched for is expected, not verified.
  - What Azure records outside the app's log store cannot be asserted by this repository ([`deploy-v0.1`](contracts/deploy-v0.1.md), Section 4.7).
- **Observed on the deployed demo, by the owner on 2026-10-05** (relay `0.7.0`, deploy of `0f79e2e`; the owner's screenshots, not committed here): a chat turn whose `discover_entity` call carried no scope value returned `ambiguous`, listing the two snapshots in which the term was found (`scope_search` searched, four candidate scopes). The owner chose one on the page; the page's `/v1/discover` returned `resolved`, and the owner's click sent `/v1/query`, which returned `success` from `TPL_MESSAGE_FACTS_V1`. That path never passes through `/v1/select`.
- **Observed on the deployed demo, by the owner on 2026-10-05** (same deploy; the owner's screenshots, not committed here): a chat turn's `candidates` list carried into `/v1/select`. A chat question naming the scope (`SAMPLE_PROJECT_ALPHA`, `SAMPLE_REV_A`, `SAMPLE_NET_POWERTRAIN`, `SAMPLE_SNAP_BASE`) and the term `SAMPLE_SIG_GEAR_POSITION` returned two candidates, at match tiers 1 and 2, with nothing preselected. The owner's click on rank 1's facts sent a CORS preflight, answered `204`, and a `POST` to `/v1/select`, answered `200`. The browser's network panel showed both. The result was `success` on `signal_facts`, with the `scope_selected_by_user` limitation naming rank 1 of 2 in the cited candidate set.
- **Not yet observed on the deployed demo:**
  - the per-address daily limit, the daily ceiling and the conversation limit; each is unit-tested (`RL-011`, `RL-013`, `RL-014`).
  - `model_unavailable`, for a failed or timed-out model call (`RL-015`) and for an unregistered block type (`RL-016`);
  - cold-start latency.

## Reproducibility

- **Dependencies are ranges, not locks.** `pyproject.toml` sets floors, and the deployed image resolves them when it is built, so two builds of one commit can carry different third-party versions ([third-party licenses](third-party-licenses.md)). The database, fixtures and expected results are pinned by commit and checked by digest (`DP-006`).

## How it was built

- **Most of the code and documents were written by AI sessions, and reviewed by an independent AI review loop.** Every decision that the [AI Development Workflow](ai-development-workflow.md) reserves for a person is recorded as the repository owner's, on the Issue or pull request named beside it.
