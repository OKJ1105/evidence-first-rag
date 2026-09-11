// The orchestrator: the only file that performs I/O, and the only one that
// holds a GitHub credential.
//
// `runLoop` takes its dependencies as arguments so the whole loop - the round
// cap, the stop conditions, idempotency, the approve guard - can be driven
// against fakes in `run.test.mjs` without a token, a network, or a model.
// `main()` wires the real ones.

import { spawn } from "node:child_process";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { ACTIONS, nextStep, roundCapFor } from "./loop.mjs";
import {
  assignIds,
  blockingOf,
  parseReview,
  renderFindings,
} from "./findings.mjs";
import { emptyState, parseState, renderStatusComment } from "./state.mjs";
import { runAgent, selectJson } from "./claude.mjs";
import { createClient } from "./github.mjs";
import { reviewerPrompt, writerPrompt } from "./prompts.mjs";

export const LABELS = {
  running: "agent:running",
  ready: "agent:ready-for-human-merge",
  needsHuman: "agent:needs-human",
  failed: "agent:failed",
};

/** Every label the loop owns, so a new phase can clear the previous one. */
const outcomeLabels = [LABELS.ready, LABELS.needsHuman, LABELS.failed];

/**
 * Paths a Writer turn may never touch (BF3).
 *
 * The orchestrator runs these files with a token the agents do not have, in
 * the same run and moments after the Writer edits. Refusing the edit is
 * cheaper than reasoning about what a given edit could do, and a review-finding
 * fix has no business in any of them.
 */
export const protectedPaths = ["scripts/", ".github/", ".githooks/", ".claude/"];

/**
 * The model each role runs on, pinned per role rather than shared.
 *
 * `CI_AGENT_MODEL` was read here and set nowhere, so every Writer and every
 * Reviewer turn ran on whatever the CLI defaulted to. The CLI version is
 * pinned in the workflow precisely so the toolchain moves only by a
 * deliberate commit; leaving the model it drives unpinned undid that. A
 * provider-side default change would silently alter what writes and what
 * judges this repository, with nothing in the history to show it — and the
 * reviews already merged (#18, #24) name no model, so they cannot be compared
 * against a later one.
 *
 * **Two variables, both currently the same value.** Model difference is not
 * an independence property and is not required — the repository owner dropped
 * that requirement on 2026-09-03 (#30), and `docs/DEVELOPMENT_WORKFLOW.md`
 * records the decision and what it gives up. The pair is kept anyway so that
 * assigning the Reviewer a different model on one slice is a one-line change
 * with a commit behind it, rather than a mechanism that has to be built first.
 * Nothing here requires the two to differ, and nothing requires them to match.
 *
 * Falls back to the shared `CI_AGENT_MODEL`, then to the CLI's own default. An
 * unset or blank model resolves to `undefined` rather than to `""`: the caller
 * omits the flag entirely, because `--model ""` is an argument the CLI has to
 * interpret, and the published comment reports the turn as unpinned rather
 * than naming a model that was never chosen.
 *
 * @param {"writer"|"reviewer"} role
 * @param {Record<string,string|undefined>} [env]
 * @returns {string|undefined} A model identifier, or undefined to let the CLI choose.
 */
export function modelFor(role, env = process.env) {
  const perRole =
    role === "reviewer" ? env.CI_AGENT_REVIEWER_MODEL : env.CI_AGENT_WRITER_MODEL;
  const chosen = perRole ?? env.CI_AGENT_MODEL;
  const trimmed = typeof chosen === "string" ? chosen.trim() : "";
  return trimmed === "" ? undefined : trimmed;
}

/** What the published comment says for a turn the workflow left unpinned. */
export const UNPINNED_MODEL = "CLI default (unpinned)";

/**
 * The `agent` dependency `runLoop` calls, with the per-role model resolved.
 *
 * A factory rather than an inline closure in `main()` so that the one thing
 * worth asserting is assertable: that the model reaching the CLI is
 * `modelFor(role)` and not a constant, and that the value published beside the
 * session id is the same one. `main()` is wiring and is not otherwise covered;
 * a pin nothing checks is how `CI_AGENT_MODEL` came to be read and never set.
 *
 * The model stamped on the result is the model the orchestrator *asked for*,
 * which is the fact worth recording: an unset one is published as
 * `UNPINNED_MODEL` rather than as a default name nobody chose.
 */
export function agentRunner({
  timeoutMs,
  cwd,
  settingsPath,
  env = process.env,
  run = runAgent,
}) {
  return async ({ role, prompt }) => {
    const model = modelFor(role, env);
    const result = await run({ role, prompt, timeoutMs, cwd, settingsPath, model });
    return { ...result, model: model ?? UNPINNED_MODEL };
  };
}

/**
 * Paths whose changes require a recorded human decision.
 *
 * A second fence, and deliberately not part of `protectedPaths`. BF3 is about
 * credentials: those files are executed by the orchestrator with a token the
 * agents do not hold, so editing them is a way to borrow privilege. A contract
 * is never executed and carries no credential. It is refused because the change
 * needs an authority a Writer does not have — Section 10 of the contract makes
 * an amendment to an `Accepted` document a recorded human decision.
 *
 * Keeping the two lists apart keeps both abort messages true. Merged, a reader
 * asking why the contract is fenced would get the credential answer, and
 * relaxing BF3 on credential grounds would quietly relax this as well.
 *
 * The rule is by path rather than by judgement because a contract finding does
 * not carry its own answer. A code finding is resolvable from the artifacts; a
 * finding like "Section 3.4 and Issue #12 cannot both hold" is resolvable only
 * by choosing between legitimate alternatives. Both reach a Writer as "blocking
 * finding, fix it", and it cannot tell them apart from the inside — on
 * 2026-09-03 it picked "amend the contract" on #23 and "revert the amendment"
 * on #32, opposite directions, neither its to decide. See #34.
 */
export const ownerDecisionPaths = ["docs/contracts/"];

/** Governing documents injected into both prompts, read from the base ref. */
export const governingDocs = [
  "AGENTS.md",
  "CLAUDE.md",
  "docs/DEVELOPMENT_WORKFLOW.md",
  "docs/ai-development-workflow.md",
];

/**
 * Documents the Reviewer gets on top of those, also from the base ref.
 *
 * `reviewer-brief.md` is the Reviewer's owner-sourced instructions under the
 * independence properties in `docs/ai-development-workflow.md`. The Project
 * Charter and the contract framework are there because the brief makes the
 * hard architecture boundaries and the contract-first gate **blocking**
 * priorities: a Reviewer never shown them cannot apply them, which is a guard
 * that looks present and does not apply.
 *
 * The Writer does not get these. It is the Reviewer that the brief binds, and
 * the Writer's prompt is already the larger of the two.
 */
export const reviewerDocs = [
  "docs/reviewer-brief.md",
  "docs/PROJECT_CHARTER.md",
  "docs/contracts/README.md",
];

/**
 * Where the checks are defined.
 *
 * The manifest is machinery (BF4): the orchestrator reads it from the BASE
 * checkout, never from the branch under review, so a branch cannot weaken or
 * empty the checks it is judged against. A pull request that adds checks gets
 * them in the loop only after it merges; CI, which runs the branch's own
 * definitions, stays authoritative for merge. `.github/` is additionally a
 * protected path, so a Writer turn cannot edit the manifest mid-run either.
 */
export const checksManifestPath = ".github/agent-checks.json";

/**
 * Load the manifest. A missing or malformed manifest is reported as a failing
 * check rather than thrown: the Reviewer should see it, and the loop should
 * conclude `needs-human` instead of crashing.
 */
export function loadChecksManifest(cwd) {
  let raw;
  try {
    raw = readFileSync(join(cwd, checksManifestPath), "utf8");
  } catch {
    return {
      error: `${checksManifestPath} is missing; the loop cannot know which checks to run.`,
    };
  }
  let doc;
  try {
    doc = JSON.parse(raw);
  } catch (err) {
    return { error: `${checksManifestPath} is not valid JSON: ${err.message}` };
  }
  if (!Array.isArray(doc.checks)) {
    return { error: `${checksManifestPath} has no "checks" array.` };
  }
  if (doc.checks.length === 0) {
    return {
      error:
        `${checksManifestPath} defines no checks. An empty manifest would ` +
        "conclude a run with nothing verified, so it fails closed instead.",
    };
  }
  for (const c of doc.checks) {
    if (
      typeof c?.name !== "string" ||
      !Array.isArray(c?.command) ||
      c.command.length === 0 ||
      c.command.some((a) => typeof a !== "string")
    ) {
      return {
        error:
          `${checksManifestPath} has an invalid entry; every check needs a ` +
          `"name" and a non-empty "command" array of strings.`,
      };
    }
  }
  return { checks: doc.checks };
}

/** Read the risk level a pull request records. Uncertainty raises it (S4). */
export function riskLevelOf({ labels = [], body = "" }) {
  const fromLabel = labels
    .map((l) => (typeof l === "string" ? l : l.name))
    .find((n) => /^L[012]$/i.test(n ?? ""));
  if (fromLabel) return fromLabel.toUpperCase();
  const fromBody = /(?:^|\s)risk(?:\s+level)?\s*[:=]?\s*`?(L[012])`?/i.exec(
    body ?? "",
  );
  return fromBody ? fromBody[1].toUpperCase() : "L2";
}

/**
 * The Issue a pull request closes.
 *
 * Fails loudly rather than falling back to the pull request. Falling back is
 * exactly the defect BF1 found: the Reviewer would then read the Writer's
 * narrative as though it were the requirement.
 */
export function linkedIssueNumber(prBody) {
  const m = /\b(?:closes|fixes|resolves)\s+#(\d+)/i.exec(prBody ?? "");
  if (!m) {
    throw new Error(
      "The pull request body names no Issue (`Closes #<n>`). The Reviewer must " +
        "read the Issue, never the pull request body, so the loop cannot proceed.",
    );
  }
  return Number(m[1]);
}

/** Whether `path` falls under any prefix in `fence`. */
function under(path, fence) {
  return fence.some((prefix) =>
    prefix.endsWith("/") ? path.startsWith(prefix) : path === prefix,
  );
}

/**
 * The paths in `git status --porcelain -z` output.
 *
 * `-z` is the whole point. Without it git quotes any path containing a space,
 * a tab, or a non-ASCII byte (`core.quotePath` is on by default), and a
 * quoted string does not match `startsWith("docs/contracts/")` -- so BF3 and
 * BF7 waved through a *new* file whose name happened to need quoting. An
 * external review demonstrated it: three of four paths under
 * `docs/contracts/` slipped the fence. `-z` emits raw bytes with NUL
 * separators and no quoting at all, which removes the class rather than
 * matching more patterns.
 *
 * A rename or copy entry carries two paths: the destination in the entry
 * itself, then the source as its own NUL-terminated field. Both are returned.
 * A rename *out of* a fenced directory is as much an edit of that directory
 * as a rename into one, and taking only the destination would miss it.
 */
export function parseStatusPaths(output) {
  const fields = String(output ?? "").split("\0");
  const paths = [];
  for (let index = 0; index < fields.length; index += 1) {
    const field = fields[index];
    if (field === "") continue;
    // `XY<space>PATH`: two status characters, a separator, then raw bytes.
    paths.push(field.slice(3));
    // The marker can sit in EITHER column. `R ` is a rename staged in the
    // index; ` R` is one git detected in the worktree only, which is what an
    // unstaged `mv` reports and what `status.renames` makes the default. A
    // check on `field[0]` alone leaves the source field unconsumed, and the
    // next iteration then slices three bytes off a bare path.
    const marker = field.slice(0, 2);
    if (marker.includes("R") || marker.includes("C")) {
      index += 1;
      if (fields[index]) paths.push(fields[index]);
    }
  }
  return paths.filter(Boolean);
}

/** Paths in `changed` that a Writer turn was not allowed to touch (BF3). */
export function forbiddenEdits(changed) {
  return changed.filter((p) => under(p, protectedPaths));
}

/**
 * Paths in `changed` whose change requires a recorded human decision.
 *
 * Separate from `forbiddenEdits` so each abort states its own reason. A caller
 * that reported both under BF3's credential wording would be telling a reader
 * something untrue about why the contract is fenced.
 */
export function ownerDecisionEdits(changed) {
  return changed.filter((p) => under(p, ownerDecisionPaths));
}

/** Run one manifest check, capturing enough output to be useful in a prompt. */
function runCommand({ name, command }, { cwd, timeoutMs, env }) {
  return new Promise((resolve) => {
    const child = spawn(command[0], command.slice(1), {
      cwd,
      env,
      stdio: ["ignore", "pipe", "pipe"],
    });
    let out = "";
    let timedOut = false;
    const timer = setTimeout(() => {
      timedOut = true;
      child.kill("SIGKILL");
    }, timeoutMs);
    child.stdout.on("data", (d) => (out += d));
    child.stderr.on("data", (d) => (out += d));
    child.on("error", (err) => {
      clearTimeout(timer);
      resolve({ name, ok: false, output: `could not start: ${err.message}` });
    });
    child.on("close", (code) => {
      clearTimeout(timer);
      resolve({
        name,
        ok: !timedOut && code === 0,
        output: timedOut ? "timed out" : out.slice(-1500),
      });
    });
  });
}

/**
 * The environment repository scripts run in.
 *
 * Stripped of every credential (BF3). The manifest's commands execute test
 * files and scripts the Writer can author. Inheriting the orchestrator's
 * environment would hand the Writer's output the token the Writer itself was
 * denied.
 */
export function checkEnv(base = process.env) {
  const env = { ...base };
  for (const name of [
    "GITHUB_TOKEN",
    "GH_TOKEN",
    "GH_PUSH_TOKEN",
    "CLAUDE_CODE_OAUTH_TOKEN",
    "ACTIONS_RUNTIME_TOKEN",
    "ACTIONS_ID_TOKEN_REQUEST_TOKEN",
    "ACTIONS_ID_TOKEN_REQUEST_URL",
  ]) {
    delete env[name];
  }
  return env;
}

/**
 * Run the manifest's checks and render a summary the agents can read.
 *
 * The commands execute in `cwd` (the branch under review); the manifest is
 * read from `manifestDir` (the base checkout, per BF4). `{baseRef}` in a
 * command argument is replaced with the pull request's base ref, so the
 * manifest does not hardcode a branch name.
 *
 * `{baseDir}` is replaced with the base checkout's path, and it completes what
 * BF4 only half-did. Reading the manifest from base stops a branch weakening
 * the *list* of checks, but the commands still ran out of the branch's own
 * tree, so a check implemented as a repository script was whatever the branch
 * said it was — a pull request could replace `validate_links.py` with
 * `sys.exit(0)` and be judged by its own no-op. It also made a branch older
 * than a check fail for the wrong reason: the base manifest named a script the
 * head had never seen, and the loop reported a broken check rather than a
 * stale branch. Naming a script through `{baseDir}` runs base's code against
 * head's files, which is the split that was intended.
 *
 * Per-check and opt-in, because not every check wants it: the whitespace check
 * is a git invocation with no script, and the unit tests must run the branch's
 * own tests — verifying that a branch did not break the loop is the point.
 */
export async function runChecks({
  cwd,
  manifestDir = cwd,
  baseRef = "main",
  baseDir = manifestDir,
  manifest = loadChecksManifest(manifestDir),
  timeoutMs = 10 * 60_000,
  env = checkEnv(),
}) {
  if (manifest.error) {
    return {
      ok: false,
      results: [],
      summary: `A check failed.\n\n- \`${checksManifestPath}\`: **FAIL**\n\n${manifest.error}`,
    };
  }
  const results = [];
  for (const check of manifest.checks) {
    const bound = {
      name: check.name,
      command: check.command.map((a) =>
        a.replaceAll("{baseRef}", baseRef).replaceAll("{baseDir}", baseDir),
      ),
    };
    const r = await runCommand(bound, { cwd, timeoutMs, env });
    results.push(r);
    if (!r.ok) break; // Cheapest-first, like CI: stop at the first failure.
  }
  const ok = results.every((r) => r.ok);
  const summary = [
    ok ? "All checks passed." : "A check failed.",
    "",
    ...results.map((r) => `- \`${r.name}\`: ${r.ok ? "pass" : "**FAIL**"}`),
    ...(ok
      ? []
      : [
          "",
          "Output of the failing check:",
          "",
          "```",
          results.at(-1).output,
          "```",
        ]),
  ].join("\n");
  return { ok, results, summary };
}

/** Locate the loop's state comment, or report that there is not one yet. */
async function loadState(gh, prNumber) {
  const comments = await gh.listComments(prNumber);
  for (const c of comments) {
    const state = parseState(c.body);
    if (state) return { state, commentId: c.id };
  }
  return { state: emptyState(), commentId: null };
}

/**
 * The state marker lives in one comment, edited in place.
 *
 * Round artifacts do not: each review and each Writer response is posted as a
 * new comment, so round 1's findings survive round 2 (BF6). Workflow section 2
 * makes the pull request canonical for review findings and decisions, and a
 * record that overwrites itself cannot be that.
 */
async function writeState(gh, prNumber, commentId, state) {
  const body = renderStatusComment(state);
  if (commentId === null) {
    const created = await gh.createComment(prNumber, body);
    return created.id;
  }
  await gh.updateComment(commentId, body);
  return commentId;
}

async function setOutcomeLabel(gh, prNumber, label) {
  for (const l of outcomeLabels) {
    if (l !== label) await gh.removeLabel(prNumber, l);
  }
  await gh.removeLabel(prNumber, LABELS.running);
  if (label) await gh.addLabels(prNumber, [label]);
}

/** The CI workflow the loop dispatches after a Writer push (#21). */
export const ciWorkflowFile = "repository-checks.yml";

/**
 * The `timeout-minutes` on the loop job, mirrored here so the CI wait can be
 * bounded by it. `workflow.test.mjs` asserts the two agree; a value that drifts
 * from the workflow would make the bound below meaningless in the one direction
 * that matters.
 */
export const jobBudgetMs = 60 * 60_000;

/**
 * How long the CI wait may take without being the thing that crosses the
 * ceiling (#113 N3).
 *
 * A job that hits `timeout-minutes` is cancelled rather than failed, and a
 * cancelled job publishes no conclusion. The wait is the one step long enough
 * to cause that on its own, so it is capped at the time actually left, minus a
 * reserve for the conclusion the run still has to write. Never negative: a run
 * already past its budget asks for no wait at all and takes whatever verdict is
 * already on the head.
 *
 * @returns {number} milliseconds, never below zero
 */
/**
 * The `ci` dependency `runLoop` calls, with the wait already bounded.
 *
 * A factory rather than an inline closure in `main()`, for the reason #30 gave
 * for `agentRunner`: `main()` is wiring and is not otherwise covered, and a
 * bound nothing checks is how a cap comes to be computed and never passed. A
 * mutation that dropped `timeoutMs` from an inline closure failed no test.
 *
 * @param {{gh: object, startedAt: string, log?: Function, awaitCi?: Function}} deps
 */
export function ciRunner({ gh, startedAt, log = () => {}, awaitCi = awaitCiOnHead }) {
  return ({ branch, headSha }) =>
    awaitCi({
      gh,
      branch,
      headSha,
      // #113 N3: never let the wait be what crosses the job ceiling.
      timeoutMs: ciBudgetMs({ startedAt }),
      log,
    });
}

export function ciBudgetMs({
  startedAt,
  now = Date.now(),
  ceilingMs = jobBudgetMs,
  reserveMs = 2 * 60_000,
  requestedMs = 10 * 60_000,
}) {
  const spent = now - Date.parse(startedAt);
  const left = ceilingMs - spent - reserveMs;
  if (!Number.isFinite(left)) return requestedMs;
  return Math.max(0, Math.min(requestedMs, left));
}

/**
 * Resolve CI's verdict on one head, dispatching a run only if none exists yet.
 *
 * #21: the Writer pushes with `GITHUB_TOKEN`, and GitHub starts no workflow
 * from an event that token raised. So `repository-checks` — which
 * `docs/agent-loop.md` calls authoritative for merge — never ran on a
 * loop-fixed head, and the loop labelled that head
 * `agent:ready-for-human-merge` anyway. Observed on #18: head `03ba0c4` had
 * zero check runs and was labelled ready.
 *
 * The loop's own manifest checks are not a substitute. They are read from the
 * base branch by design (BF4), so they are exactly the checks that cannot
 * cover what the branch changed about checking.
 *
 * **It looks before it dispatches (B2 on #113).** The question this answers is
 * "did CI pass on this commit", and a `pull_request` run already on the head
 * answers it — which is why `listWorkflowRuns` is deliberately unfiltered by
 * event. Dispatching anyway would burn a second runner on every human-pushed
 * head for no new information. The caller is therefore free to ask about any
 * head it is about to conclude on, not only one this run pushed, and that is
 * what makes the verdict a property of the head rather than of the push.
 *
 * A listing that throws is not read as "no run": it falls through to the
 * dispatch, because not knowing is not a reason to skip the check.
 *
 * Everything is injected so the whole wait is testable without a network: a
 * fake client, a fake clock and a fake sleep drive every branch below.
 *
 * @returns {Promise<{ok: boolean, conclusion: string, url: string|null, summary: string}>}
 */
export async function awaitCiOnHead({
  gh,
  branch,
  headSha,
  workflowFile = ciWorkflowFile,
  timeoutMs = 10 * 60_000,
  pollMs = 15_000,
  sleep = (ms) => new Promise((r) => setTimeout(r, ms)),
  now = () => Date.now(),
  log = () => {},
}) {
  const say = (conclusion, ok, detail, url = null) => ({
    ok,
    conclusion,
    url,
    summary: `- \`${workflowFile}\` on \`${headSha}\`: ${detail}`,
  });
  const runOnHead = async () => {
    const runs = await gh.listWorkflowRuns(workflowFile, branch);
    return (runs?.workflow_runs ?? []).find((r) => r.head_sha === headSha) ?? null;
  };
  const verdictOf = (run) =>
    say(
      run.conclusion ?? "unknown",
      run.conclusion === "success",
      `**${run.conclusion}**`,
      run.html_url ?? null,
    );

  // Look first. An existing run on this head — dispatched or raised by the
  // pull request — is the answer, and a second one would add nothing.
  let seen = null;
  let existed = false;
  try {
    seen = await runOnHead();
    existed = seen !== null;
    if (seen?.status === "completed") return verdictOf(seen);
  } catch (err) {
    log(`CI listing failed before dispatch, dispatching anyway: ${err.message}`);
  }

  if (!existed) {
    try {
      await gh.dispatchWorkflow(workflowFile, branch);
    } catch (err) {
      return say("not_dispatched", false, `could not be dispatched — ${err.message}`);
    }
  }

  // #113 N9: out of job time is a different answer from "nothing ever
  // appeared", and the owner acts on them differently. With no budget left the
  // poll below never runs, and falling through to the timeout message would
  // publish `no run appeared on this head within 0 minutes` -- the exact
  // sentence `docs/agent-loop.md` teaches the owner to read as "this branch
  // predates the trigger, rebase it". The dispatch above has already happened,
  // so CI is running and will post its own status; what ran out was the loop.
  if (timeoutMs < pollMs) {
    return say(
      "budget_exhausted",
      false,
      "was dispatched, but this run had no job time left to wait for it",
      seen?.html_url ?? null,
    );
  }

  const deadline = now() + timeoutMs;
  while (now() < deadline) {
    await sleep(pollMs);
    try {
      seen = await runOnHead();
    } catch (err) {
      log(`CI poll failed, retrying: ${err.message}`);
      continue;
    }
    if (seen?.status === "completed") return verdictOf(seen);
  }
  return say(
    "timed_out",
    false,
    seen
      ? `started but did not finish within ${Math.round(timeoutMs / 60_000)} minutes`
      : `no run appeared on this head within ${Math.round(timeoutMs / 60_000)} minutes`,
    seen?.html_url ?? null,
  );
}

export function withCiVerdict(checkResult, ci) {
  if (!ci) return checkResult;
  return {
    ...checkResult,
    ok: checkResult.ok && ci.ok,
    ci,
    summary: [
      checkResult.summary,
      "",
      "CI on the head this run is concluding on (#21):",
      "",
      ci.summary,
      ci.url ? `\n${ci.url}` : "",
    ].join("\n"),
  };
}

/**
 * Fail the run if anything approved the pull request while the loop held it.
 *
 * The workflow token can submit reviews, so "the AI never approves" needs a
 * check and not only an absent code path. The agents have no credential, so a
 * hit here means something else did it - which the owner should see.
 */
export async function assertNothingApproved(gh, prNumber, since) {
  const reviews = await gh.listReviews(prNumber);
  const offending = reviews.filter(
    (r) =>
      r.state === "APPROVED" &&
      (!since || new Date(r.submitted_at) >= new Date(since)),
  );
  if (offending.length > 0) {
    throw new Error(
      `An approving review appeared during this run (${offending.map((r) => r.user?.login).join(", ")}). ` +
        "The loop must never approve; failing the run so this is visible.",
    );
  }
}

/**
 * Drive the loop to a conclusion.
 *
 * @param {object} deps
 * @param {object} deps.gh        GitHub client (see github.mjs).
 * @param {Function} deps.agent   ({role, prompt}) => Promise<{text, sessionId}>.
 * @param {Function} deps.checks  () => Promise<{ok, summary}>.
 * @param {Function} deps.commit  (message) => Promise<string|null> new head sha.
 * @param {Function} deps.diff    () => Promise<string>.
 * @param {Function} deps.changedPaths () => Promise<string[]>.
 * @param {string} deps.docs      Governing documents, read from the base ref.
 * @param {object} deps.ctx       { prNumber, runUrl, startedAt, reset }.
 */
/**
 * A truthy, printable reason for any thrown value.
 *
 * The catch that reads the Issue's comments is deliberately non-fatal, and the
 * flag it sets decides whether both agents are told the discussion is unknown
 * or told there is none. So the flag must be armed for every throw shape:
 * `new Error("").message` is `""`, a non-Error throw has no `.message`, and
 * `throw undefined` makes an unguarded `err.message` throw again.
 *
 * **The coercion is guarded too (#135 O1).** `String(Object.create(null))`
 * throws `TypeError: Cannot convert object to primitive value`, and a throw
 * there would escape `runLoop` — taking out the run over a failure whose whole
 * point was that it must not. The rationale for `?.` applies verbatim to the
 * second operand, so it gets the same treatment.
 *
 * A real message is preferred over the stringified form: the notice has one
 * job, which is to name the cause, and `Error: ` in front of every reason is
 * noise.
 */
export function failureReason(err) {
  try {
    return err?.message || String(err) || "unknown error";
  } catch {
    return "unknown error";
  }
}

export async function runLoop({
  gh,
  agent,
  checks,
  commit,
  diff,
  // #21. Null means "do not dispatch CI", which is what every test that is
  // not about CI wants and what a local run has no credential for. `main()`
  // wires the real one.
  ci = null,
  changedPaths = async () => [],
  docs = "",
  reviewerOnlyDocs = "",
  ctx,
  log = console.log,
}) {
  const { prNumber, runUrl, startedAt, reset = false } = ctx;

  const pr = await gh.getPull(prNumber);
  const branch = pr.head.ref;
  const riskLevel = riskLevelOf(pr);
  const cap = roundCapFor(riskLevel);

  // BF1: the Reviewer reads the Issue. `pr.body` is the Writer's narrative and
  // never reaches either prompt.
  const issueNumber = linkedIssueNumber(pr.body);
  const issue = await gh.getIssue(issueNumber);
  const issueBody = issue.body ?? "";

  // #33: the body was all either role ever saw, so a decision recorded as an
  // Issue comment was structurally invisible. On #32 that made the Writer
  // revert a contract amendment because "no such decision is present in this
  // session's context" — correct on its inputs, and the inputs were missing it.
  //
  // `listComments` is the same paginated read the state marker relies on, and
  // GitHub serves an Issue's comments from the same path as a pull request's.
  // A failure here is not fatal: the Issue's body is still the specification,
  // and losing the discussion is worse than losing the run.
  //
  // But the failure is CARRIED, not swallowed (#126 B1). The first version left
  // `issueComments = []`, and an empty list renders as "None. The Issue has no
  // comments." — so a 502 reached both agents as an affirmative claim that
  // nothing was recorded, on exactly the case this read exists for. Unread and
  // empty are different states and both prompts now say which one they got.
  let issueComments = [];
  let issueCommentsUnread = null;
  try {
    issueComments = await gh.listComments(issueNumber);
  } catch (err) {
    // #134: the flag is what `issueDiscussion` branches on, so it has to be
    // truthy on every path that reaches here. Keying it on `err.message` made
    // it depend on a property of the thrown value that nothing guarantees:
    // `new Error("").message` is `""` and a non-Error throw has no `.message`
    // at all, and either one collapses back to the empty branch — publishing
    // "None. The Issue has no comments." on a run where the read failed, which
    // is the #126 B1 claim verbatim. A guard must not be disarmed by the shape
    // of the failure it exists to report.
    issueCommentsUnread = failureReason(err);
    log(
      `Could not read Issue #${issueNumber}'s comments: ${issueCommentsUnread}`,
    );
  }

  // The owner reads the pull request, not the Actions log. A run whose agents
  // reasoned without the discussion has to say so where the merge decision is
  // made, or the gap is invisible at exactly the moment it matters.
  const unreadNotice = issueCommentsUnread
    ? `> **The Issue's comments could not be read** (${issueCommentsUnread}). ` +
      "Both agents were told the discussion is unknown rather than empty, so " +
      "anything recorded only in an Issue comment was not in front of either " +
      "of them on this run."
    : null;

  let { state, commentId } = await loadState(gh, prNumber);
  if (reset) {
    log("Reset requested: clearing the recorded round count.");
    state = { ...emptyState(), riskLevel };
  }
  state = { ...state, riskLevel, runId: runUrl, issueNumber };

  await gh.addLabels(prNumber, [LABELS.running]);

  // BF2: never seeded from state. A verdict recorded on a previous run belongs
  // to a different commit, and reusing it let the loop call a red head ready.
  let checkResult = null;

  // B2 on #113: the CI verdict is a property of the head the loop is about to
  // conclude on, not of "this run pushed something". Folding it in only on the
  // fix path left a hole: if the job is cut off during the CI wait, the marker
  // still records the pre-fix head, and the next run re-reviews the pushed head
  // through the review path — which took no CI verdict — and can conclude
  // `ready` over a head no CI has ever seen. That is the defect #21 exists to
  // remove, so every path that produces a verdict folds CI in.
  //
  // Memoised per head, because CI's conclusion on a given commit is a fixed
  // fact once it completes. Re-asking would re-spend the wait for the same
  // answer; `awaitCiOnHead` looks before dispatching, so the second ask would
  // not even start a run.
  const ciByHead = new Map();
  const withCi = async (result, head) => {
    if (!ci) return result;
    if (!ciByHead.has(head)) ciByHead.set(head, await ci({ branch, headSha: head }));
    const verdict = ciByHead.get(head);
    log(`CI on ${head}: ${verdict.conclusion}`);
    return withCiVerdict(result, verdict);
  };
  let concluded = null;
  let currentHead = pr.head.sha;
  // #82 / N1 on #92: what the Writer touched behind the owner-decision fence,
  // observed during the fix step and handed to `nextStep` on the iteration
  // after, so the terminal decision stays in the state machine.
  let fencedEdits = [];

  // Two steps per round (fix, review), plus the opening review, plus the
  // conclusion — and one more for the `check` step a resumed run inserts
  // before it will conclude.
  const guardLimit = 2 * cap + 3;
  for (let guard = 0; guard <= guardLimit; guard += 1) {
    const step = nextStep({
      riskLevel,
      round: state.round,
      lastReview: state.lastReview,
      checks: checkResult,
      headSha: currentHead,
      stateHeadSha: state.headSha,
      phase: state.phase,
      fencedEdits,
    });
    log(`step: ${step.action} - ${step.reason}`);

    if (step.action === ACTIONS.skip) {
      await gh.removeLabel(prNumber, LABELS.running);
      return { action: step.action, reason: step.reason, round: state.round };
    }

    if (step.action === ACTIONS.skipL0) {
      state = {
        ...state,
        headSha: currentHead,
        phase: ACTIONS.needsHuman,
        updatedAt: new Date(startedAt).toISOString(),
      };
      await gh.createComment(
        prNumber,
        `## Agent loop: no AI review at this risk level\n\n${step.reason}\n\nNothing was reviewed. The owner decides.`,
      );
      await writeState(gh, prNumber, commentId, state);
      await setOutcomeLabel(gh, prNumber, LABELS.needsHuman);
      return { action: step.action, reason: step.reason, round: state.round };
    }

    // The state machine asked for a verdict before it will conclude. Running
    // the checks is the whole step; the next iteration decides on the result.
    if (step.action === ACTIONS.check) {
      checkResult = await withCi(await checks(), currentHead);
      log(`checks: ${checkResult.ok ? "pass" : "FAIL"}`);
      continue;
    }

    if (step.action === ACTIONS.review) {
      if (checkResult === null) {
        checkResult = await withCi(await checks(), currentHead);
        // Whether the checks ran, and what they said, is otherwise invisible
        // in the run log — `runChecks` captures output rather than streaming
        // it, so a failure after this point gives no way to tell.
        log(`checks: ${checkResult.ok ? "pass" : "FAIL"}`);
      }
      const raw = await agent({
        role: "reviewer",
        prompt: reviewerPrompt({
          issueNumber,
          issueBody,
          issueComments,
          issueCommentsUnread,
          riskLevel,
          branch,
          diff: await diff(),
          checks: checkResult,
          round: state.round + 1,
          priorFindings: state.lastReview?.findings ?? [],
          docs,
          reviewerDocs: reviewerOnlyDocs,
        }),
      });
      // parseReview is the validator: a quoted manifest in the reply parses
      // as JSON but has no `findings` array, and is passed over (#60).
      const parsed = selectJson(raw.text, parseReview);
      const { findings, registry } = assignIds(parsed.findings, state.registry);
      state = {
        ...state,
        headSha: currentHead,
        phase: ACTIONS.review,
        registry,
        lastReview: { summary: parsed.summary, findings },
        checksOk: checkResult.ok,
        updatedAt: new Date().toISOString(),
      };
      await gh.createComment(
        prNumber,
        [
          `## Independent review — round ${state.round + 1} of ${cap}`,
          "",
          `Head \`${currentHead}\` · Issue #${issueNumber} · risk \`${riskLevel}\``,
          `Reviewer model: \`${raw.model ?? "not reported"}\` · session: \`${raw.sessionId ?? "not reported by the CLI"}\``,
          "",
          ...(unreadNotice ? [unreadNotice, ""] : []),
          parsed.summary,
          "",
          renderFindings(findings),
          "",
          checkResult.summary,
        ].join("\n"),
      );
      commentId = await writeState(gh, prNumber, commentId, state);
      continue;
    }

    if (step.action === ACTIONS.fix) {
      const blocking = blockingOf(state.lastReview.findings);
      const raw = await agent({
        role: "writer",
        prompt: writerPrompt({
          issueNumber,
          issueBody,
          issueComments,
          issueCommentsUnread,
          riskLevel,
          branch,
          findings: blocking,
          checks: checkResult,
          round: state.round + 1,
          cap,
          docs,
          protectedPaths,
          ownerDecisionPaths,
        }),
      });

      // BF3: refuse a Writer turn that edited the machinery the orchestrator
      // runs with privileges the Writer does not have.
      const changedNow = await changedPaths();
      const forbidden = forbiddenEdits(changedNow);
      if (forbidden.length > 0) {
        throw new Error(
          `The Writer edited protected paths: ${forbidden.join(", ")}. ` +
            "Those are run by the orchestrator with credentials the agents do not hold, " +
            "so the run is aborted rather than executing them.",
        );
      }
      // The reply is read before the second fence, so a Writer turn that
      // trips that fence can still have its proposal published (N2 on #92).
      // Parsing is pure; nothing here acts on the reply.
      let responses = [];
      let summary;
      try {
        // The shape prompts.mjs asks for. A quoted object in the reply that
        // is neither a response table nor carries a summary is passed over
        // rather than read as an empty one (#60).
        const doc = selectJson(raw.text, (candidate) => {
          const parsed = JSON.parse(candidate);
          if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed))
            throw new Error("Writer output is not a JSON object.");
          if (!Array.isArray(parsed.responses) && typeof parsed.summary !== "string")
            throw new Error("Writer output has neither `responses` nor `summary`.");
          return parsed;
        });
        responses = Array.isArray(doc.responses) ? doc.responses : [];
        summary = typeof doc.summary === "string" ? doc.summary : "";
      } catch {
        summary =
          "The Writer's reply could not be parsed; its edits are in the diff.";
      }

      // A separate fence with a separate reason: nothing under it is executed
      // and nothing carries a credential. The edit is refused because amending
      // an `Accepted` contract is a recorded human decision under its Section
      // 10, which is not a Writer's to make.
      //
      // It records rather than throws (#82). BF7 is reached by a contract-only
      // pull request doing exactly what it is supposed to do, so it is a
      // designed terminus, not a crash — and every throw is labelled
      // `agent:failed` by `main()`, which is this repository's word for a
      // crash and the one its queue teaches the owner to restart. Restarting
      // this case aborts identically every time.
      //
      // BF7 still holds where it matters: `commit()` is below this point and
      // is never reached, so the Writer's edit to a fenced path is discarded
      // with the runner rather than committed or pushed. The BF3 fence above
      // keeps throwing, because a Writer reaching for the machinery is a fault
      // and should read as one.
      const needsOwner = ownerDecisionEdits(changedNow);
      if (needsOwner.length > 0) {
        // N2 on #92: publish what the Writer proposed. That proposal is the
        // input to the decision the fence reserves for the owner, and without
        // it the record says an edit was attempted but never what it was.
        await gh.createComment(
          prNumber,
          [
            `## Writer proposal — discarded at the owner-decision fence`,
            "",
            `Head \`${currentHead}\` · nothing from this turn was committed or pushed`,
            `Writer model: \`${raw.model ?? "not reported"}\` · session: \`${raw.sessionId ?? "not reported by the CLI"}\``,
            "",
            `The Writer's fix reached ${needsOwner.map((p) => `\`${p}\``).join(", ")}, which is behind the owner-decision fence. ` +
              "Its edit was **discarded**. What it proposed is recorded here because that proposal is the input to the decision the fence reserves for you — it is not a change to the branch.",
            "",
            summary,
            "",
            ...(responses.length
              ? [
                  "| Finding | Proposed action | Note |",
                  "| --- | --- | --- |",
                  ...responses.map(
                    (r) =>
                      `| ${r.id} | ${r.action} | ${(r.note ?? "").replace(/\|/g, "/")} |`,
                  ),
                ]
              : ["_No structured response._"]),
          ].join("\n"),
        );
        fencedEdits = needsOwner;
        continue;
      }

      const newHead = await commit(
        `Address review findings (round ${state.round + 1})\n\n` +
          responses
            .map((r) => `${r.id}: ${r.action}${r.note ? ` - ${r.note}` : ""}`)
            .join("\n"),
      );
      if (newHead) currentHead = newHead;
      // #21: the push above raised no workflow run, because GitHub starts none
      // from an event `GITHUB_TOKEN` raised. `withCi` dispatches on the pushed
      // head and waits, so `ready` is never published over a head no CI has
      // seen. It is no longer gated on there being a new head: a Writer turn
      // that changed nothing still concludes on this head, and asking about a
      // head CI already ran on costs one listing and starts nothing.
      checkResult = await withCi(await checks(), currentHead);

      state = {
        ...state,
        round: state.round + 1,
        headSha: currentHead,
        phase: ACTIONS.fix,
        checksOk: checkResult.ok,
        lastReview: null,
        updatedAt: new Date().toISOString(),
      };
      await gh.createComment(
        prNumber,
        [
          `## Writer response — round ${state.round} of ${cap}`,
          "",
          `Head \`${currentHead}\``,
          `Writer model: \`${raw.model ?? "not reported"}\` · session: \`${raw.sessionId ?? "not reported by the CLI"}\``,
          "",
          ...(unreadNotice ? [unreadNotice, ""] : []),
          summary,
          "",
          ...(responses.length
            ? [
                "| Finding | Action | Note |",
                "| --- | --- | --- |",
                ...responses.map(
                  (r) =>
                    `| ${r.id} | ${r.action} | ${(r.note ?? "").replace(/\|/g, "/")} |`,
                ),
              ]
            : ["_No structured response._"]),
          "",
          checkResult.summary,
        ].join("\n"),
      );
      commentId = await writeState(gh, prNumber, commentId, state);
      continue;
    }

    concluded = step;
    break;
  }

  if (concluded === null) {
    throw new Error(
      "The loop did not conclude within its guard; refusing to continue.",
    );
  }

  const ready = concluded.action === ACTIONS.ready;

  // Before publishing any conclusion: if something approved the pull request
  // while the loop held it, fail now rather than after a "ready" label and
  // comment have already gone out.
  await assertNothingApproved(gh, prNumber, startedAt);

  state = {
    ...state,
    phase: concluded.action,
    updatedAt: new Date().toISOString(),
  };
  await gh.createComment(
    prNumber,
    [
      `## ${ready ? "Awaiting human merge" : "Stopped — a human is needed"}`,
      "",
      concluded.reason,
      "",
      // A run that concludes through `check` posts neither a review nor a
      // Writer response, so this can be the only comment it writes. The notice
      // has to be here too or a whole run can go by with the gap recorded
      // nowhere the owner looks.
      ...(unreadNotice ? [unreadNotice, ""] : []),
      ready
        ? "No blocking findings remain and the checks pass. **Merging is the owner's act; nothing here approves or merges.**"
        : "The loop stopped without clearing every blocking finding. The comments above are the record the owner decides from.",
      "",
      // #113 N6: the verdict has to reach the owner from here too. A run that
      // concludes through the `check` action posts no review and no Writer
      // response, so this is its only comment — and since #21 the verdict it
      // carries includes CI, whose run URL and whose distinction between a red
      // build and a timeout are exactly what the owner needs to act. Without
      // this they are told only that "the checks are failing".
      ...(checkResult ? [checkResult.summary, ""] : []),
      ...(state.lastReview ? [renderFindings(state.lastReview.findings)] : []),
    ].join("\n"),
  );
  await writeState(gh, prNumber, commentId, state);
  await setOutcomeLabel(gh, prNumber, ready ? LABELS.ready : LABELS.needsHuman);

  return {
    action: concluded.action,
    reason: concluded.reason,
    round: state.round,
  };
}

/**
 * Run git and resolve its stdout, trimmed.
 *
 * `raw: true` resolves the bytes untouched, and `git status --porcelain -z`
 * is why the option exists. A worktree-only modification is reported as
 * ` M path\0` -- a LEADING SPACE. Trimming the whole stdout eats that space
 * when the entry sorts first, `parseStatusPaths` then slices one byte too
 * far, and `.github/workflows/ci.yml` arrives as `github/workflows/ci.yml`,
 * which `under()` no longer matches. That is the same fence bypass the `-z`
 * change closed, reached through whitespace instead of quoting.
 */
export function git(args, cwd, { raw = false, env, spawnFn = spawn } = {}) {
  return new Promise((resolve, reject) => {
    const child = spawnFn("git", args, {
      cwd,
      env: env ?? process.env,
      stdio: ["ignore", "pipe", "pipe"],
    });
    let out = "";
    let err = "";
    child.stdout.on("data", (d) => (out += d));
    child.stderr.on("data", (d) => (err += d));
    child.on("close", (code) =>
      code === 0
        ? resolve(raw ? out : out.trim())
        : reject(new Error(`git ${args.join(" ")} failed: ${err.trim()}`)),
    );
  });
}

/**
 * The paths a Writer turn changed, as BF3 and BF7 read them.
 *
 * Exported so the composition is a tested unit: `-z` AND `raw: true`, or the
 * fence is bypassable. `parseStatusPaths` alone proves what the parser does
 * with a leading space; only this proves the parser is handed one.
 */
export async function changedPathsOf(gitFn, worktree) {
  return parseStatusPaths(
    await gitFn(["status", "--porcelain", "-z"], worktree, { raw: true }),
  );
}

/**
 * Push the worktree's HEAD to the pull request branch.
 *
 * BF3: the credential travels in the environment of this one command and is
 * never written into .git/config, where the agents' Read could reach it.
 *
 * Exported so the credential's route is a tested unit. `git()` takes its
 * options as one object, and the round-1 review of #49 found this call still
 * handing it an env-shaped bag positionally. Destructured as options that bag
 * has no `env` key, the spawn falls back to `process.env`, and the token never
 * reaches the helper -- so the first real fix-round push fails auth and the
 * run dies. The test asserts the token arrives under `env` and nowhere else.
 */
export function pushHead(gitFn, { worktree, owner, repo, branch, token }) {
  return gitFn(
    [
      "-c",
      "credential.helper=!f() { echo username=x-access-token; echo password=$GH_PUSH_TOKEN; }; f",
      "push",
      `https://github.com/${owner}/${repo}`,
      `HEAD:${branch}`,
    ],
    worktree,
    { env: { ...process.env, GH_PUSH_TOKEN: token } },
  );
}

/* c8 ignore start - wiring, exercised by the workflow rather than by tests */

async function main() {
  const worktree = process.env.CI_AGENT_WORKTREE ?? process.cwd();
  // BF4: the governing documents come from the base ref, never from the branch
  // under review.
  const baseDir = process.env.CI_AGENT_BASE_DIR ?? worktree;
  const [owner, repo] = (process.env.GITHUB_REPOSITORY ?? "").split("/");
  const prNumber = Number(process.env.CI_AGENT_PR_NUMBER);
  const runUrl = process.env.CI_AGENT_RUN_URL ?? null;
  const reset = process.env.CI_AGENT_RESET === "true";
  const branch = process.env.CI_AGENT_BRANCH;
  const baseRef = process.env.CI_AGENT_BASE_REF ?? "main";

  if (!owner || !repo || !Number.isInteger(prNumber)) {
    throw new Error("GITHUB_REPOSITORY and CI_AGENT_PR_NUMBER must be set.");
  }

  const gh = createClient({ owner, repo });
  const startedAt = new Date().toISOString();

  const inline = (list) =>
    list
      .map((rel) => {
        const text = readFileSync(join(baseDir, rel), "utf8");
        return `### ${rel} (from ${baseRef})\n\n${text}`;
      })
      .join("\n\n");

  const docs = inline(governingDocs);
  const reviewerOnlyDocs = inline(reviewerDocs);

  // Commit under the owner's public noreply identity, marked with the
  // Agent-Loop-Run trailer. See docs/agent-loop.md.
  await git(
    ["config", "user.name", process.env.CI_AGENT_GIT_NAME ?? "OKJ1105"],
    worktree,
  );
  await git(
    [
      "config",
      "user.email",
      process.env.CI_AGENT_GIT_EMAIL ??
        "206027169+OKJ1105@users.noreply.github.com",
    ],
    worktree,
  );

  const agentTimeoutMs = Number(
    process.env.CI_AGENT_TURN_TIMEOUT_MS ?? 12 * 60_000,
  );
  const settingsPath = process.env.CI_AGENT_SETTINGS ?? undefined;

  try {
    const result = await runLoop({
      gh,
      docs,
      reviewerOnlyDocs,
      ctx: { prNumber, runUrl, startedAt, reset },
      agent: agentRunner({
        timeoutMs: agentTimeoutMs,
        cwd: worktree,
        settingsPath,
      }),
      checks: () =>
        runChecks({ cwd: worktree, manifestDir: baseDir, baseDir, baseRef }),
      diff: () => git(["diff", `origin/${baseRef}...HEAD`], worktree),
      changedPaths: () => changedPathsOf(git, worktree),
      // #21. Thin by design: everything worth asserting is in
      // `awaitCiOnHead`, which is driven by fakes in the tests. `main()` is
      // wiring and is not otherwise covered.
      // #113 N8: budget from the JOB's start, not this process's. The ceiling
      // `ciBudgetMs` subtracts from is the job's `timeout-minutes`, and this
      // process begins after the job's checkouts, setup and CLI install.
      // `startedAt` stays as it is for `assertNothingApproved`, which is about
      // when the loop took custody rather than about the job's budget.
      ci: ciRunner({
        gh,
        startedAt: process.env.CI_AGENT_JOB_STARTED_AT || startedAt,
        log: console.log,
      }),
      commit: async (message) => {
        const dirty = await git(["status", "--porcelain"], worktree);
        if (dirty === "") return null;
        await git(["add", "-A"], worktree);
        await git(
          [
            "commit",
            "-m",
            `${message}\n\nAgent-Loop-Run: ${runUrl ?? "local"}`,
          ],
          worktree,
        );
        await pushHead(git, {
          worktree,
          owner,
          repo,
          branch,
          token: process.env.GITHUB_TOKEN,
        });
        return git(["rev-parse", "HEAD"], worktree);
      },
    });
    console.log(
      `Loop finished: ${result.action} after ${result.round} round(s).`,
    );
  } catch (err) {
    console.error(`Loop failed: ${err.message}`);
    try {
      await gh.createComment(
        prNumber,
        [
          "## Agent loop failed",
          "",
          "```",
          String(err.message).slice(0, 1500),
          "```",
          "",
          runUrl ? `Run: ${runUrl}` : "",
          "",
          "Nothing was approved or merged.",
        ].join("\n"),
      );
      await setOutcomeLabel(gh, prNumber, LABELS.failed);
    } catch (reportErr) {
      console.error(`Could not report the failure: ${reportErr.message}`);
    }
    process.exitCode = 1;
  }
}

if (process.argv[1] && import.meta.url === `file://${process.argv[1]}`) {
  await main();
}

/* c8 ignore stop */
