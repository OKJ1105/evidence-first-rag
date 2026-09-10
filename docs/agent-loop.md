# Agent Loop

## 1. What this is

A bounded Writer/Reviewer loop that runs inside one GitHub Actions run. The owner starts it from a pull request — a comment or a label, both reachable from a phone — and it runs Reviewer, Writer, checks, Reviewer until either nothing blocking remains or the round cap for the recorded risk level is spent. It then labels the pull request and stops.

**It does not merge and it cannot approve.** Merging is the owner's act under the [Development Workflow](DEVELOPMENT_WORKFLOW.md), and that is unchanged. The loop is the one AI-invoking GitHub Action this repository permits, and it never acts without the owner starting it; the [AI Development Workflow](ai-development-workflow.md) records that boundary.

## 2. The loop

```
owner comments /agent-loop  (or adds the agent:run label)
        |
        v
  [gate]  owner-only, pull request only, not a bot comment
        |
        v
  Reviewer  reads Issue + diff + check results  -> findings with ids
        |
   blocking findings?
        |                          no -> label agent:ready-for-human-merge, stop
       yes
        |
        v
  Writer   edits files to address the blocking findings only
        |
        v
  checks   the commands in .github/agent-checks.json
        |
        v
  Reviewer confirms  ---- round cap reached? -> label agent:needs-human, stop
        |
        +--> back to "blocking findings?"
```

One round is a Writer fix plus the Reviewer confirmation that follows it. The cap is read from the pull request's recorded risk level:

| Risk | Rounds | Behaviour |
| --- | --- | --- |
| `L0` | 0 | The loop refuses to review and says so. |
| `L1` | 1 | One fix and one confirmation. |
| `L2` | 2 | Two. |

An unrecorded or unrecognised level is treated as `L2`, because uncertainty raises the level and guessing low would spend a round the Issue never authorised.

## 3. Independence

| Property | How it holds |
| --- | --- |
| 1. No shared derivation state | Writer and Reviewer are separate `claude -p` processes. Neither inherits the other's context. |
| 2. Owner-sourced instructions | The prompts and the loop's own code run from a **second checkout of the base branch**, never from the branch under review, so a branch cannot supply the reviewer that judges it. `AGENTS.md`, `CLAUDE.md`, both workflow documents, `docs/reviewer-brief.md`, the Project Charter and the contract framework are read from that checkout and inlined into the prompts. |
| 3. Recorded order of exposure | The Reviewer prompt carries the **Issue** (resolved from the pull request's `Closes #n`, and the run aborts if there is none), the diff and the check results. The pull request body never reaches either prompt, and a test asserts it. |
| 4. No authorship | The Reviewer process is spawned with a read-only tool set. It could not edit if it tried. |
| 5. Attributable identity | Each review and each Writer response is its own comment, recording the run URL, the round, the model that turn ran on and the `claude -p` session identifier for it. Both post under one account, so the session identifier is the stated fallback, not a distinct identity. The model is the orchestrator's resolved choice, and a turn the workflow left unpinned is published as such rather than as a named default. |

## 4. Design invariants

The code comments reference these by name; they are the loop's load-bearing rules, each one established by a defect an earlier review or live run found.

| Name | Rule |
| --- | --- |
| BF1 | The Reviewer reads the Issue, never the pull request body. A loop with no linked Issue aborts rather than falling back. |
| BF2 | A verdict is never seeded from recorded state. A resumed run re-runs the checks before it will conclude anything. |
| BF3 | No credential reaches an agent process or anything an agent wrote. The checks run with a stripped environment, and a Writer turn that edits the machinery the orchestrator executes aborts the run. |
| BF4 | The machinery — orchestrator code, prompts, settings, the checks manifest — comes from the base branch or from outside both checkouts, never from the branch under review. |
| BF6 | The record is append-only. Each review and each response is its own comment; only the state marker is edited in place, and it displays no findings. |
| BF7 | A Writer turn does not amend the contract. An edit under `docs/contracts/` is discarded and the run stops at `agent:needs-human`, for its own reason: a contract is never executed and holds no credential, so BF3 does not cover it. Amending an `Accepted` contract is a recorded human decision under its Section 10, which is not a Writer's to make or to record. Unlike BF3 this is a designed terminus rather than a crash, and it is labelled as one (#82). |

## 5. Safety

**The agents hold no GitHub credential, and neither does anything they write.** `scripts/agent/claude.mjs` deletes the token from every agent process; `scripts/agent/run.mjs` strips it again before any manifest command runs, because the Writer's *output* is executed by the privileged parent moments later. A Writer turn that edits `scripts/`, `.github/`, `.githooks/` or `.claude/` **aborts the run** — those are the machinery the orchestrator executes with privileges the agents do not hold. `actions/checkout` runs with `persist-credentials: false`, so the token is not in `.git/config` either; the push step supplies its own credential through the environment of that one command. `scripts/agent/github.mjs` has no approve method and no merge method.

**A second fence, for authority rather than credentials (BF7).** A Writer turn that edits `docs/contracts/` also stops the run, and it is a separate list — `ownerDecisionPaths`, not `protectedPaths` — because the reason is different and both messages have to stay true. Nothing under `docs/contracts/` is executed and none of it carries a credential; the edit is refused because amending an `Accepted` contract is a recorded human decision under its Section 10.

**The two fences stop the run differently, and that is deliberate (#82).** BF3 throws: a Writer reaching for the machinery is a fault, and `agent:failed` is the right word for it. BF7 **concludes** `agent:needs-human` and publishes the standing findings, because a contract-only pull request reaches it by doing exactly what it is supposed to do. Both discard the edit — the commit is never reached, so nothing the Writer wrote to a fenced path is committed or pushed — and neither publishes a verdict resting on it. Labelling BF7 `agent:failed` was a real defect rather than a cosmetic one: `agent:failed` is what this repository's queue teaches the owner to restart by re-adding `agent:run`, and restarting this case aborts identically every time.

The fence is by path rather than by judgement, and that is deliberate. A code finding is resolvable from the artifacts — the diff, the contract, the tests decide it. A finding like "Section 3.4 requires Docker Compose and Issue #12 forbids it" is resolvable only by choosing between legitimate alternatives, and Section 10 assigns that choice to the repository owner. Both reach a Writer as "blocking finding, fix it", and it cannot tell them apart from the inside: on 2026-09-03 it amended a contract to authorise its own branch on one pull request, and reverted an authorised amendment on another because the decision had been recorded where it could not see it. Opposite directions, the same missing authority. No improvement in Writer quality closes that, because the input does not contain the answer.

The cost is that a correct contract fix also has to come from an out-of-loop writer. It is accepted: the precise alternative is a prompt rule asking the Writer to tell a derivable correction from a choice, which is the judgement that failed twice in one day. Revisit it if contract amendments become frequent enough that the out-of-loop fixes cost more than the mistakes did. A contract-only pull request therefore always ends at `agent:needs-human`, which is the honest outcome rather than a regression.

**A guard fails the run if anything approved, and it runs before the loop publishes its conclusion.** The workflow token *could* submit a review, so the orchestrator lists the pull request's reviews and fails if an approval appeared while it held it.

Its position is the load-bearing part. The check runs after the loop has decided its outcome and **before** the conclusion comment, the state write and the outcome label — so a run that finds an approval leaves no `agent:ready-for-human-merge` behind it, and the pull request is not left carrying a verdict the loop then disowned. A guard that ran after publication would report the problem rather than prevent it.

Both halves of that position matter. It runs **after** the agent turns because the check is bounded to what appeared while the loop held the pull request; hoisted to the top of the run it would look before the window it exists to cover. It runs **before** publication because a guard that fires afterwards reports rather than prevents.

**Two early returns come back before the guard, and neither can reach `ready`.** An `L0` pull request publishes its "nothing was reviewed" comment, its state and the `agent:needs-human` label, then returns. A re-run against a head the loop already concluded on returns earlier still: it removes the `agent:running` label and publishes nothing at all. So the guarantee is about the conclusion path — the only one that can label a pull request ready to merge — and the only early return that publishes anything is the one that cannot produce `ready`.

This document said "at the end" until #5. The guard moved ahead of publication in #4's round-1 fixes and the sentence did not follow, which is the shape of drift where a document describes a weaker guarantee than the code gives and a later change quietly restores the weaker one. A unit test now pins the ordering.

**The loop cannot refund the cap; only the owner can.** Pushing a commit invalidates the recorded review but does not reset the round count. `/agent-loop reset` is the owner's deliberate act and the only way the count returns to zero.

**A red build is never "ready", and neither is an unmeasured one.** `ready` requires a positive check verdict from this run. A clean review over failing checks concludes `agent:needs-human`; a resumed run with no verdict runs the checks before it concludes anything.

**A malformed review fails loudly.** An unparseable Reviewer reply throws rather than degrading to an empty finding list, because an empty list is indistinguishable from "nothing wrong" and would end the loop as ready.

### Stop conditions

1. No blocking findings and the checks pass → `agent:ready-for-human-merge`.
2. The round cap is spent with blocking findings outstanding → `agent:needs-human`.
3. The checks fail → `agent:needs-human`.
4. `L0` → `agent:needs-human`, with nothing reviewed.
5. A Writer turn edits `docs/contracts/` (BF7) → `agent:needs-human`, with the edit discarded and the standing findings published. Its own row rather than a case of 6 below: it is where a contract-only pull request is *supposed* to end.
6. Anything throws, BF3's fence included → `agent:failed`, with the message on the pull request.

### Concurrency, idempotency, timeouts

- One run per pull request; queued rather than cancelled, so a mid-turn cancellation cannot leave the branch edited with no status comment.
- State lives in one marker comment, edited in place. A re-run against a head the loop already concluded on does nothing. A damaged marker throws rather than silently resetting the round count.
- 60 minutes for the job, 12 minutes per agent turn, 10 minutes per check, and 10 minutes waiting for CI on a head (#21). The CI wait is taken at most once per head, because a conclusion on a commit is a fixed fact once it lands; a two-round `L2` run therefore waits on at most three heads. It is spent serially after that head's manifest checks rather than overlapped with them, which is the loosest part of the budget; dispatching before the checks and awaiting after them would recover most of it, and is **not** done here. What is done is the half that matters (#113 N3): the wait is capped by the job's own remaining time, less a reserve for the conclusion, so it is not the step that crosses the ceiling. The job's start is recorded by the loop's first step and read from `CI_AGENT_JOB_STARTED_AT`, because the orchestrator itself begins minutes later, after the checkouts and the CLI install -- budgeting from its own start would have counted that setup as spare time (#113 N8). Outside Actions there is no job and the cap falls back to process start. That matters because a job which hits `timeout-minutes` is **cancelled rather than failed**, and a `failure()`-only guard on the crash reporter would skip it — leaving the pull request carrying `agent:running` with no conclusion and no `agent:failed`. The reporter is now guarded on `failure() || cancelled()` as well.
- The workflow is not triggered by `push`: the Writer pushes inside the run, and a push trigger would restart the loop on its own output. CI (`repository-checks`) stays authoritative for merge, and the loop takes its verdict on **whichever head it is about to conclude on** — dispatching a run when none exists there yet, and reusing the pull request's own run when one does — then waits for the conclusion before labelling (#21). Keying it to the head rather than to "this run pushed something" is what closes the resumed-run hole: a job cut off during the wait leaves the marker recording the pre-fix head, and the next run re-reviews the pushed head through a path that used to take no CI verdict at all.
- **The trigger has to be on the default branch first (#113 O1).** GitHub accepts a `workflow_dispatch` API call only for a workflow whose definition **on the default branch** declares that trigger. The pull request that adds the trigger therefore cannot dispatch from its own branch — but it does not try to: the orchestrator is read from base (BF4), and the base that lacks the trigger also lacks the dispatch code, so the two arrive together on merge and there is no window in which the loop dispatches into a repository that would refuse it. What has *not* been observed, and is an assumption rather than a fact, is whether a dispatched run's check runs attach to the pull request's head commit the way a `pull_request` run's do. If they do not, the failure is `no run appeared on this head` → `agent:needs-human`, which is safe but reads like a defect; the first loop run after this merges is the one to watch. **The same reading applies to any branch cut before this merges (#113 O2).** The dispatch runs the workflow definition from the *branch's* ref, and such a branch has a `repository-checks.yml` with no `workflow_dispatch` trigger. Rebase an in-flight branch onto `main` before starting `/agent-loop` on it; until then, `no run appeared on this head` on such a branch means the branch is stale, not that its code is red.
- **Why the dispatch is needed at all.** The Writer pushes with `GITHUB_TOKEN`, and GitHub starts no workflow from an event that token raised. This document used to say CI "does run on those pushes", and it did not: on #18 the loop-pushed head `03ba0c4` had zero check runs and was labelled `agent:ready-for-human-merge` anyway. A `workflow_dispatch` raised with `GITHUB_TOKEN` is the documented exception, so the fix needs `actions: write` on the loop's job — a recorded owner decision, #68 decision 2 — and no new Secret. A red, missing, or undispatchable CI run now makes the verdict `needs-human`; the loop's own manifest checks cannot substitute, because BF4 reads them from base and they are exactly the checks that cannot cover what the branch changed about checking.

## 6. Checks

The loop runs the commands in [.github/agent-checks.json](../.github/agent-checks.json), in order, stopping at the first failure, each with a credential-stripped environment. Two tokens are bound: `{baseRef}` to the pull request's base ref, and `{baseDir}` to the base checkout's path.

The manifest is machinery under BF4: **the loop reads it from the base branch**, never from the branch under review, so a branch cannot weaken or empty the checks it is judged against — and a missing, malformed, or empty manifest fails closed rather than concluding with nothing verified. A pull request that adds checks gets them in the loop only after it merges; CI, which runs the branch's own definitions, stays authoritative for merge. The manifest is also a protected path, so a Writer turn cannot edit it mid-run.

**`{baseDir}` completes what reading the manifest from base only half-did.** The list of checks came from base, but the commands ran out of the branch's tree, so a check implemented as a repository script was whatever the branch said it was — a pull request could replace `validate_links.py` with `sys.exit(0)` and be judged by its own no-op. It also made a branch older than a check fail for the wrong reason: the base manifest named a script the head had never seen, and the loop reported a broken check rather than a stale branch, which is exactly what happened on the contract pull request. A check that names its script through `{baseDir}` runs base's code against head's files. It is per-check and opt-in: the whitespace check is a git invocation with no script, and the agent unit tests must run the branch's own tests, since verifying that a branch did not break the loop is the point. CI does not use `{baseDir}` and should not: it checks out one tree and runs the branch's own definitions, which is what makes it the authority for merge. The two runners resolve a check script differently on purpose. When the implementation grows checks that need services a runner must provide — a database, for instance — they are added to CI first, and to the manifest only if the loop's runner can support them.

## 7. Commit identity

The loop commits as the owner's public noreply identity and marks each commit with a trailer:

```
Agent-Loop-Run: https://github.com/OKJ1105/evidence-first-rag/actions/runs/...
```

The trailer is a convention, not an enforcement — the Writer and the owner share one account, which is the same limitation Property 5 records.

## 8. Files

| File | What it is |
| --- | --- |
| `.github/workflows/agent-loop.yml` | Triggers, the owner gate, and the job. |
| `.github/agent-checks.json` | The checks the loop runs between turns. |
| `scripts/agent/loop.mjs` | The state machine. Pure; decides every step. |
| `scripts/agent/run.mjs` | The orchestrator. The only file that does I/O. |
| `scripts/agent/findings.mjs` | Finding ids and the Reviewer output contract. |
| `scripts/agent/state.mjs` | The marker comment state carries. |
| `scripts/agent/prompts.mjs` | Both prompts, with the governing documents inlined from the base ref. |
| `scripts/agent/gate.mjs` | Who may start the loop, and on what. |
| `scripts/agent/claude.mjs` | Spawns agents; strips credentials; restricts tools. |
| `scripts/agent/github.mjs` | The only holder of the token. |
| `scripts/agent/test-kit.mjs` | The standard-library test kit the unit tests run on. |
| `scripts/agent/*.test.mjs` | Unit tests over the loop, ids, state, the gate, the prompts, the client, the orchestrator, and the workflow file itself. |

## 9. Owner setup, once

1. **Secret:** `CLAUDE_CODE_OAUTH_TOKEN`, from `claude setup-token`. Settings → Secrets and variables → Actions.
2. **Labels:** `agent:run`, `agent:running`, `agent:ready-for-human-merge`, `agent:needs-human`, `agent:failed`.
3. **Actions permissions:** Settings → Actions → General → Workflow permissions must allow read and write, or the Writer cannot push.

## 10. Using it from a phone

Comment on the pull request:

```
/agent-loop
```

To clear a spent round count and start over: `/agent-loop reset`. Or add the `agent:run` label. Then wait for one of the outcome labels, read the status comment, and merge if you agree with it.

One practical note: the loop's agent turns draw on the same Claude subscription quota as interactive sessions. Runs are owner-triggered and round-capped, so the spend is bounded, but starting a loop while heavily using interactive sessions shares one budget.
