# AI Development Workflow

This document adds lightweight AI role and risk routing to the repository [Development Workflow](DEVELOPMENT_WORKFLOW.md). It does not replace the Project Charter, `AGENTS.md`, contract-first sequencing, human acceptance, or CI.

## Canonical record

The canonical development record lives in GitHub:

- the Issue defines scope, acceptance evidence, review level, and deferred work;
- the branch and commits contain the writer's proposed change;
- the pull request contains the complete diff, validation results, review record, and human dispositions;
- required status checks provide deterministic verification.

Nimbalyst may be used as a local UI for sessions, diffs, and GitHub-backed work. Nimbalyst-local Issues, plans, session metadata, or chat history are not authoritative. Copy any adopted decision into the GitHub Issue or pull request and, when durable, into the applicable contract, ADR, or test.

## Roles

### Claude Code: default writer

Claude Code owns the implementation branch and proposed patch. It reads the canonical Issue, follows `CLAUDE.md` and `AGENTS.md`, runs checks, records evidence, and opens a Draft pull request. The writer does not provide its own independent approval.

### Codex: independent reviewer

Codex reviews the Issue, applicable contracts, branch diff, tests, and validation evidence without editing files. It reports only consequential P0/P1-equivalent blockers. A Codex review is requested manually; automatic Codex reviews remain disabled.

### ChatGPT: exceptional arbiter

ChatGPT is not a routine writer or reviewer. Use it only when an L2 design decision has material architecture, security, provenance, or irreversible-cost risk, or when writer and reviewer remain in substantive disagreement after the two-round limit. Record the question, options, evidence, and adopted human decision in GitHub and the applicable durable artifact.

### Repository owner: decision and merge authority

The repository owner classifies risk, approves any escalation, records required human decisions, resolves review conversations, confirms CI, and initiates merge. AI-generated approval or automatic merge is prohibited.

## Execution environment selection

- Use a cloud-first default. Implement an Issue in Claude Code Cloud when it can run from a fresh clone using a repository-defined setup script.
- Use the desktop environment only when the Issue requires local files, uncommitted changes, a GUI, a local database, or authentication or network access that the cloud environment cannot provide.
- "Remote" means the smartphone Remote connection described in the [Manual Setup Checklist](manual-setup-checklist.md#optional-smartphone-remote-connection): the ChatGPT desktop and mobile apps operating the local desktop host. Use Remote only for an urgent task while away from the desktop when that task requires the local environment; urgency does not waive any other gate in this document. Remote is a transport for operating the local desktop environment only — it does not change writer or reviewer assignment, review level, the bounded review cycle, CI, or the human-merge requirement, and it does not make ChatGPT the writer for that task. Keeping the desktop computer continuously running or available is not a workflow assumption.
- Never edit the same branch in cloud and local environments at the same time.
- Before handing work from local to cloud, commit and push the local work.
- Before moving work from cloud to local, end the cloud task and pull the branch locally.
- Use the GitHub Issue, commits, and pull request as handoff context. Session history is not an authoritative handoff record.

## Review levels

Choose the highest applicable level and record it in both the Issue and pull request.

| Level | Use when | Required AI review |
| --- | --- | --- |
| L0 | A mechanical or non-normative change cannot alter product behavior, contracts, security, CI, deployment, data meaning, or public interfaces. Examples: typo fixes and link corrections. | None. Human scope check and CI still apply. |
| L1 | A contained implementation or test change follows an already accepted contract and has no architecture, security, provenance, schema, migration, CI, deployment, or public-interface impact. | One read-only Codex code review after implementation and validation. |
| L2 | A change affects contracts, ADRs, architecture, schema or migrations, security or permissions, Secrets handling, CI, Rulesets, deployment, public interfaces, failure behavior, provenance, or multiple components. Use L2 whenever classification is uncertain. | Read-only Codex design review before implementation, then read-only Codex code/configuration review after implementation and validation. ChatGPT arbitration only when the exceptional conditions above apply. |

An L2 contract-only pull request may satisfy the design-review stage, but it does not authorize implementation until the repository's required human contract review is recorded.

## Bounded review cycle

An AI review cycle has at most two rounds:

1. initial review with at most five P0/P1-equivalent blockers;
2. one final inspection of the fix diff.

After round 2, stop AI review. Any unresolved blocker is recorded for human disposition. ChatGPT may arbitrate only for an L2 issue that meets its exceptional role; it does not create a third writer/reviewer loop.

L2 design review and L2 code/configuration review are separate stages. Each stage follows the same two-round ceiling, and the pull request records which stage each review covers.

## Pull request flow

1. Create or refine the GitHub Issue and select L0, L1, or L2.
2. Create one branch from the latest `main` and keep commits traceable to the Issue.
3. For L2, complete the required design or contract review and human gate before implementation.
4. Claude Code writes the scoped change and its tests or acceptance evidence.
5. Run all deterministic checks locally and record results in the Draft pull request.
6. Request the required Codex review manually. Do not enable an automatic review trigger.
7. Apply accepted fixes once and request the final inspection when needed.
8. Record unresolved findings, ChatGPT arbitration when applicable, and the repository owner's disposition.
9. The repository owner confirms required CI success and conversation resolution, then manually merges.

## Automation boundary

- Deterministic repository checks may run in GitHub Actions.
- AI GitHub Actions and automatic AI reviews are not enabled.
- AI accounts and GitHub Apps receive no Ruleset bypass and no merge authority.
- OAuth grants, GitHub App installation, cloud Secrets, environment variables, and Rulesets are configured only by the repository owner using the [Manual Setup Checklist](manual-setup-checklist.md).
