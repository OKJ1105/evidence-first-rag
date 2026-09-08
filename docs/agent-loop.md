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
| BF7 | A Writer turn does not amend the contract. An edit under `docs/contracts/` aborts the run, and for its own reason: a contract is never executed and holds no credential, so BF3 does not cover it. Amending an `Accepted` contract is a recorded human decision under its Section 10, which is not a Writer's to make or to record. |

## 5. Safety

**The agents hold no GitHub credential, and neither does anything they write.** `scripts/agent/claude.mjs` deletes the token from every agent process; `scripts/agent/run.mjs` strips it again before any manifest command runs, because the Writer's *output* is executed by the privileged parent moments later. A Writer turn that edits `scripts/`, `.github/`, `.githooks/` or `.claude/` **aborts the run** — those are the machinery the orchestrator executes with privileges the agents do not hold. `actions/checkout` runs with `persist-credentials: false`, so the token is not in `.git/config` either; the push step supplies its own credential through the environment of that one command. `scripts/agent/github.mjs` has no approve method and no merge method.

**A second fence, for authority rather than credentials (BF7).** A Writer turn that edits `docs/contracts/` also aborts the run, and it is a separate list — `ownerDecisionPaths`, not `protectedPaths` — because the reason is different and both abort messages have to stay true. Nothing under `docs/contracts/` is executed and none of it carries a credential; the edit is refused because amending an `Accepted` contract is a recorded human decision under its Section 10.

The fence is by path rather than by judgement, and that is deliberate. A code finding is resolvable from the artifacts — the diff, the contract, the tests decide it. A finding like "Section 3.4 requires Docker Compose and Issue #12 forbids it" is resolvable only by choosing between legitimate alternatives, and Section 10 assigns that choice to the repository owner. Both reach a Writer as "blocking finding, fix it", and it cannot tell them apart from the inside: on 2026-09-03 it amended a contract to authorise its own branch on one pull request, and reverted an authorised amendment on another because the decision had been recorded where it could not see it. Opposite directions, the same missing authority. No improvement in Writer quality closes that, because the input does not contain the answer.

The cost is that a correct contract fix also has to come from an out-of-loop writer. It is accepted: the precise alternative is a prompt rule asking the Writer to tell a derivable correction from a choice, which is the judgement that failed twice in one day. Revisit it if contract amendments become frequent enough that the out-of-loop fixes cost more than the mistakes did. A contract-only pull request therefore always ends at `agent:needs-human`, which is the honest outcome rather than a regression.

**A guard fails the run if anything approved.** The workflow token *could* submit a review, so the orchestrator lists reviews at the end and fails if an approval appeared while it held the pull request.

**The loop cannot refund the cap; only the owner can.** Pushing a commit invalidates the recorded review but does not reset the round count. `/agent-loop reset` is the owner's deliberate act and the only way the count returns to zero.

**A red build is never "ready", and neither is an unmeasured one.** `ready` requires a positive check verdict from this run. A clean review over failing checks concludes `agent:needs-human`; a resumed run with no verdict runs the checks before it concludes anything.

**A malformed review fails loudly.** An unparseable Reviewer reply throws rather than degrading to an empty finding list, because an empty list is indistinguishable from "nothing wrong" and would end the loop as ready.

### Stop conditions

1. No blocking findings and the checks pass → `agent:ready-for-human-merge`.
2. The round cap is spent with blocking findings outstanding → `agent:needs-human`.
3. The checks fail → `agent:needs-human`.
4. `L0` → `agent:needs-human`, with nothing reviewed.
5. Anything throws → `agent:failed`, with the message on the pull request.

### Concurrency, idempotency, timeouts

- One run per pull request; queued rather than cancelled, so a mid-turn cancellation cannot leave the branch edited with no status comment.
- State lives in one marker comment, edited in place. A re-run against a head the loop already concluded on does nothing. A damaged marker throws rather than silently resetting the round count.
- 60 minutes for the job, 12 minutes per agent turn, 10 minutes per check.
- The workflow is not triggered by `push`: the Writer pushes inside the run, and a push trigger would restart the loop on its own output. CI (`repository-checks`) does run on those pushes and stays authoritative for merge.

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
