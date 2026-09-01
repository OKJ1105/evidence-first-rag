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

### Independent Reviewer: a separate, non-authoring Claude process

The Independent Reviewer inspects the Issue, applicable contracts, branch diff, and check results without editing files, and reports only consequential blocking findings with named fixes. It is normally run by the [Agent Loop](agent-loop.md), which the owner starts from the pull request; its standing instructions are [docs/reviewer-brief.md](reviewer-brief.md). The Reviewer must not have authored any part of the change it reviews.

### Repository owner: decision and merge authority

The repository owner classifies risk, approves any escalation, records required human decisions, resolves review conversations, confirms CI, and initiates merge. AI-generated approval or automatic merge is prohibited. A disagreement the bounded cycle does not resolve goes to the owner; no third model arbitrates.

## Independence properties

Every review, however it is produced, satisfies five properties. Inside the agent loop the first four hold structurally rather than by instruction; [agent-loop.md](agent-loop.md) records how.

1. **No shared derivation state.** The Reviewer is a separate process from the Writer and inherits none of its context.
2. **Owner-sourced instructions.** The Reviewer's instructions come from the base branch, never from the branch under review.
3. **Recorded order of exposure.** The Reviewer receives the Issue, the diff, and the check results. The pull request body — the Writer's narrative — is withheld.
4. **No authorship.** The Reviewer holds a read-only tool set and reviews nothing it wrote.
5. **Attributable identity.** Each review records its session identifier and run URL. Writer and Reviewer post under one account, so the session identifier is the stated fallback rather than a distinct identity.

## Execution environment selection

- Use a cloud-first default. Implement an Issue in Claude Code Cloud when it can run from a fresh clone using a repository-defined setup script.
- Use the desktop environment only when the Issue requires local files, uncommitted changes, a GUI, a local database, or authentication or network access that the cloud environment cannot provide.
- Away from the desktop, the [Agent Loop](agent-loop.md) is the phone-reachable path: starting `/agent-loop` on a pull request needs only the GitHub app. Keeping the desktop computer continuously running or available is not a workflow assumption.
- Never edit the same branch in cloud and local environments at the same time.
- Before handing work from local to cloud, commit and push the local work.
- Before moving work from cloud to local, end the cloud task and pull the branch locally.
- Use the GitHub Issue, commits, and pull request as handoff context. Session history is not an authoritative handoff record.

## Review levels

Choose the highest applicable level and record it in both the Issue and pull request.

| Level | Use when | Required AI review |
| --- | --- | --- |
| L0 | A mechanical or non-normative change cannot alter product behavior, contracts, security, CI, deployment, data meaning, or public interfaces. Examples: typo fixes and link corrections. | None. Human scope check and CI still apply. |
| L1 | A contained implementation or test change follows an already accepted contract and has no architecture, security, provenance, schema, migration, CI, deployment, or public-interface impact. | One independent code review after implementation and validation — one agent-loop round. |
| L2 | A change affects contracts, ADRs, architecture, schema or migrations, security or permissions, Secrets handling, CI, Rulesets, deployment, public interfaces, failure behavior, provenance, or multiple components. Use L2 whenever classification is uncertain. | An independent design review before implementation, then an independent code/configuration review after implementation and validation — up to two agent-loop rounds per stage. |

An L2 contract-only pull request may satisfy the design-review stage, but it does not authorize implementation until the repository's required human contract review is recorded.

## Bounded review cycle

An AI review cycle has at most two rounds:

1. initial review with at most five P0/P1-equivalent blockers;
2. one final inspection of the fix diff.

After round 2, stop AI review. Any unresolved blocker is recorded for human disposition; no third model arbitrates. The [Agent Loop](agent-loop.md) enforces this cap mechanically — `L0` gets no review, `L1` one round, `L2` two — and only the owner's explicit `/agent-loop reset` refunds it.

L2 design review and L2 code/configuration review are separate stages. Each stage follows the same two-round ceiling, and the pull request records which stage each review covers.

## Pull request flow

1. Create or refine the GitHub Issue and select L0, L1, or L2.
2. Create one branch from the latest `main` and keep commits traceable to the Issue.
3. For L2, complete the required design or contract review and human gate before implementation.
4. Claude Code writes the scoped change and its tests or acceptance evidence.
5. Run all deterministic checks locally and record results in the Draft pull request.
6. Start the required review by commenting `/agent-loop` on the pull request (or adding the `agent:run` label). The loop runs the review, the fixes, and the final inspection within the round cap, then labels the pull request.
7. Record any unresolved findings and the repository owner's disposition.
8. The repository owner confirms required CI success and conversation resolution, then manually merges.

## Automation boundary

- Deterministic repository checks may run in GitHub Actions.
- The [Agent Loop](agent-loop.md) is the one AI-invoking GitHub Action. It runs only when the owner starts it on a pull request, it cannot approve or merge, and it is not triggered by pushes or schedules. No other AI Action and no automatic AI review is enabled.
- AI accounts and GitHub Apps receive no Ruleset bypass and no merge authority.
- OAuth grants, GitHub App installation, cloud Secrets, environment variables, and Rulesets are configured only by the repository owner using the [Manual Setup Checklist](manual-setup-checklist.md).
