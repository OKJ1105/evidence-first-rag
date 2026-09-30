# ADR-0007: The Writer Session May Dispatch the Deploy

**Status:** Proposed. Recorded by the writer session on [#265](https://github.com/OKJ1105/evidence-first-rag/issues/265) from the repository owner's decision of 2026-09-30. The owner's disposition on the pull request is the recorded human decision.

**Date:** 2026-09-30

## Context

`deploy-v0.1` Section 4.2 makes the owner's start of a run the recorded human decision for each deploy. It forbids any writer session, agent-loop run or other automation from dispatching the deploy workflow. `0.2.0` chose that because required reviewers are not available on this repository's plan ([#205](https://github.com/OKJ1105/evidence-first-rag/issues/205#issuecomment-5844259676)).

The first deploys showed what that costs.

- **One run takes about 17 minutes.** The template apply, the image build and the provisioning take about 5. The deployed checks take about 10, of which the conformance runner and `DP-008`'s log read take most.
- **Each run surfaced one new platform fact.** Runs 36656130166, 36660167510 and 36662412772 each failed on something no local check could see. These were:
  - the federated subject's form;
  - unregistered resource providers and a CLI argument name;
  - the installed package's data files, the forwarded-for entry's port, and an `az` call that failed without a recorded cause.
- **A fix could only be verified by another full deploy.** Each one waited on the owner to start it.

The owner's review happens before a commit reaches `main`: the owner merges every pull request by hand, and the `production` environment admits `main` only. Starting the run adds no information to that decision. It adds a wait.

## Decision

1. **The Claude Code writer session may dispatch the deploy workflow**, through the owner's account, in either mode.
   - **The recorded human decision for a deploy is the owner's merge of the commit to `main`.**
   - The environment's `main`-only rule and the job's actor guard are unchanged. So a run still deploys only a commit the owner merged, and the run's triggering actor and URL are still recorded in its artifact.
2. **Creating a secret stays the owner's act.**
   - A run creates a missing database password only when the owner starts it with the `create_missing_secrets` input, and the writer session never sets that input.
   - Otherwise a missing password stops the run.
   - The three passwords exist already; the owner's start of run 36656130166 created them.
3. **No agent-loop run, schedule or event dispatches it.** The only trigger stays `workflow_dispatch`. The writer session dispatches only on the owner's standing instruction, never from a pull request's own content.
4. **The workflow gains a checks mode** (`mode: checks`). It runs the Section 4.8 deployed checks against what is already deployed.
   - It creates no secret and applies no template, pushes no image, restarts nothing, provisions nothing and rolls nothing back. Its one deployed change is the runner's firewall window, which Section 4.2 already opens for the checks.
   - `cases` may narrow it to named check groups.
   - A checks run is never a rollback target, and never the acceptance artifact.
5. **The deployed checks run fast groups first.** The fast groups are Azure resource state, HTTP, and the runtime identity's refused writes. A failure among them skips the slow groups, which are recorded as not run. `DP-003`'s scan gates the artifact upload, so it always runs.

## Consequences

- A fix to a deployed check can be verified in a few minutes by a checks run of that group, not by a full deploy.
- The writer session can take a slice from merge to a green deploy without an owner sitting. The owner's sittings then hold merges, decisions and secret-creating runs only (operating policy, item 4).
- **The writer session can now change production**, within what a merged commit contains. What bounds that is the owner's merge, the `main`-only environment rule, the guard, and the rollback to the last passing commit. The writer's judgement is not one of them.
- **A failed deploy no longer records every check.** The slow groups it skipped are named in the record, and the next run, or a checks run, covers them.
- **Reversal.** Removing the writer session from Section 4.2 restores the owner-only start without any change to the workflow's guard.
