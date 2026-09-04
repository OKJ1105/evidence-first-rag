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
import { extractJson, runAgent } from "./claude.mjs";
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

/** Paths in `changed` that a Writer turn was not allowed to touch. */
export function forbiddenEdits(changed) {
  return changed.filter((p) =>
    protectedPaths.some((prefix) =>
      prefix.endsWith("/") ? p.startsWith(prefix) : p === prefix,
    ),
  );
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
export async function runLoop({
  gh,
  agent,
  checks,
  commit,
  diff,
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
  let concluded = null;
  let currentHead = pr.head.sha;

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
      checkResult = await checks();
      log(`checks: ${checkResult.ok ? "pass" : "FAIL"}`);
      continue;
    }

    if (step.action === ACTIONS.review) {
      if (checkResult === null) {
        checkResult = await checks();
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
      const parsed = parseReview(extractJson(raw.text));
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
          `Reviewer session: \`${raw.sessionId ?? "not reported by the CLI"}\``,
          "",
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
          riskLevel,
          branch,
          findings: blocking,
          checks: checkResult,
          round: state.round + 1,
          cap,
          docs,
          protectedPaths,
        }),
      });

      // BF3: refuse a Writer turn that edited the machinery the orchestrator
      // runs with privileges the Writer does not have.
      const forbidden = forbiddenEdits(await changedPaths());
      if (forbidden.length > 0) {
        throw new Error(
          `The Writer edited protected paths: ${forbidden.join(", ")}. ` +
            "Those are run by the orchestrator with credentials the agents do not hold, " +
            "so the run is aborted rather than executing them.",
        );
      }

      let responses = [];
      let summary;
      try {
        const doc = JSON.parse(extractJson(raw.text));
        responses = Array.isArray(doc.responses) ? doc.responses : [];
        summary = typeof doc.summary === "string" ? doc.summary : "";
      } catch {
        summary =
          "The Writer's reply could not be parsed; its edits are in the diff.";
      }

      const newHead = await commit(
        `Address review findings (round ${state.round + 1})\n\n` +
          responses
            .map((r) => `${r.id}: ${r.action}${r.note ? ` - ${r.note}` : ""}`)
            .join("\n"),
      );
      if (newHead) currentHead = newHead;
      checkResult = await checks();

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
          `Writer session: \`${raw.sessionId ?? "not reported by the CLI"}\``,
          "",
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
      ready
        ? "No blocking findings remain and the checks pass. **Merging is the owner's act; nothing here approves or merges.**"
        : "The loop stopped without clearing every blocking finding. The comments above are the record the owner decides from.",
      "",
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

/* c8 ignore start - wiring, exercised by the workflow rather than by tests */

function git(args, cwd, env) {
  return new Promise((resolve, reject) => {
    const child = spawn("git", args, {
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
        ? resolve(out.trim())
        : reject(new Error(`git ${args.join(" ")} failed: ${err.trim()}`)),
    );
  });
}

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
      agent: ({ role, prompt }) =>
        runAgent({
          role,
          prompt,
          timeoutMs: agentTimeoutMs,
          cwd: worktree,
          settingsPath,
          model: process.env.CI_AGENT_MODEL,
        }),
      checks: () =>
        runChecks({ cwd: worktree, manifestDir: baseDir, baseDir, baseRef }),
      diff: () => git(["diff", `origin/${baseRef}...HEAD`], worktree),
      changedPaths: async () =>
        (await git(["status", "--porcelain"], worktree))
          .split("\n")
          .map((l) => l.slice(3).trim())
          .filter(Boolean),
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
        // BF3: the push credential is passed through the environment of this
        // one command, never written into .git/config where the agents' Read
        // could reach it.
        await git(
          [
            "-c",
            "credential.helper=!f() { echo username=x-access-token; echo password=$GH_PUSH_TOKEN; }; f",
            "push",
            `https://github.com/${owner}/${repo}`,
            `HEAD:${branch}`,
          ],
          worktree,
          { ...process.env, GH_PUSH_TOKEN: process.env.GITHUB_TOKEN },
        );
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
