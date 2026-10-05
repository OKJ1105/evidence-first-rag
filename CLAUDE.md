# Claude Code Instructions

Claude Code is the default writer for this repository. These instructions supplement [AGENTS.md](AGENTS.md), the [Development Workflow](docs/DEVELOPMENT_WORKFLOW.md), and the [AI Development Workflow](docs/ai-development-workflow.md). Those documents and the frozen Project Charter remain authoritative. The [Operating Policy](docs/operating-policy.md) governs cadence — pipelined slices, batched owner sittings, parallel tracks — and names the tracking Issue (#68) that holds the live queue; read both before starting.

## Writer workflow

1. Start from a canonical GitHub Issue and a clean branch based on the latest `main`.
2. Record the intended L0, L1, or L2 review level in the Issue and pull request before implementation.
3. Keep one independently reviewable behavior and its tests or acceptance evidence in one pull request.
4. Follow every contract-first and human-review stop condition in `AGENTS.md`. Do not implement behavior that lacks the required reviewed contract and fixtures.
5. Run all repository-defined checks and report exact commands and results. Never report a skipped check as passing.
6. Open a Draft pull request and identify Claude Code as writer. Do not claim to be the independent reviewer.
7. Address at most one review follow-up. If a blocker remains after the second AI review round, stop and request the repository owner's recorded disposition.

## Boundaries

- Do not merge or approve a pull request.
- Do not review a change you authored, in whole or in part. The independent review comes from a separate, non-authoring process — normally the Agent Loop — never from the writer session.
- Do not treat Nimbalyst-local state as the task record. Copy adopted decisions and evidence into GitHub and the applicable repository artifact.
- Record a decision the owner gives in chat as a neutral English statement: its date, what was decided, and where it applies. Do not quote the chat message itself. This repository is published, and its record should read as a record.
- Do not install GitHub Apps, enable automated review, change OAuth grants, create or rotate Secrets, or alter Rulesets without explicit repository-owner approval.
