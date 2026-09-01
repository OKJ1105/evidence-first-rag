// Spawning the Writer and the Reviewer.
//
// Each call is a separate `claude -p` process, which is what makes them
// separate sessions: no shared context, no inherited transcript, nothing the
// Writer said reaching the Reviewer except the artifacts on disk. That is
// workflow section 3 property 1, satisfied by construction rather than by
// asking a model to forget.
//
// Three safety properties are enforced here rather than in a prompt:
//
//   1. The child process has no GitHub credential. GITHUB_TOKEN and friends are
//      deleted from its environment. Note this is necessary and not sufficient:
//      `run.mjs` must also strip the token before running any repository script,
//      because the Writer's *output* is executed by the privileged parent (BF3).
//   2. The child gets an explicit tool allowlist, and a denylist as well. The
//      denylist matters because `claude -p` reads project settings from its cwd,
//      and a branch under review could otherwise supply a settings file with
//      hooks that run shell commands irrespective of the allowlist (BF4).
//   3. Settings are pinned to a file the orchestrator controls, so nothing in
//      the worktree can widen what the agent may do.

import { spawn } from "node:child_process";

/** Env names stripped from every agent process, whatever the runner set. */
const credentialEnv = [
  "GITHUB_TOKEN",
  "GH_TOKEN",
  "GH_PUSH_TOKEN",
  "GITHUB_API_URL",
  "ACTIONS_RUNTIME_TOKEN",
  "ACTIONS_ID_TOKEN_REQUEST_TOKEN",
  "ACTIONS_ID_TOKEN_REQUEST_URL",
];

/**
 * Tools each role may use.
 *
 * Neither role gets `Bash`. The Writer therefore cannot run the checks itself
 * and cannot push; `run.mjs` runs the checks and feeds the result back. That
 * costs the Writer some local iteration and buys a Writer with no route to the
 * network or to git, which is the safer side of the trade.
 */
export const TOOLS = {
  writer: ["Read", "Edit", "Write", "Glob", "Grep"],
  // Property 4: the Reviewer did not write any part of the change, and here it
  // could not have.
  reviewer: ["Read", "Glob", "Grep"],
};

/** Denied outright, so a branch-supplied settings file cannot restore them. */
export const deniedTools = [
  "Bash",
  "WebFetch",
  "WebSearch",
  "Task",
  "NotebookEdit",
];

export class AgentError extends Error {}

/**
 * Run one agent turn.
 *
 * @param {object} opts
 * @param {"writer"|"reviewer"} opts.role
 * @param {string} opts.prompt
 * @param {number} opts.timeoutMs
 * @param {string} opts.cwd          The worktree the agent operates on.
 * @param {string} [opts.settingsPath] Settings file the orchestrator controls.
 * @param {string} [opts.model]
 * @returns {Promise<{text: string, role: string, sessionId: string|null}>}
 */
export function runAgent({
  role,
  prompt,
  timeoutMs,
  cwd,
  settingsPath,
  model,
  // Injected so a test can assert what reaches argv without spawning a CLI.
  // Everything else in the loop is injected the same way.
  spawnFn = spawn,
}) {
  const allowed = TOOLS[role];
  if (!allowed)
    throw new AgentError(`Unknown agent role ${JSON.stringify(role)}.`);

  const env = { ...process.env };
  for (const name of credentialEnv) delete env[name];
  if (!env.CLAUDE_CODE_OAUTH_TOKEN) {
    throw new AgentError(
      "CLAUDE_CODE_OAUTH_TOKEN is not set; cannot start the agent.",
    );
  }

  // The prompt goes on stdin, not argv. Linux caps a single argument at
  // 32 pages - 131072 bytes - and the Reviewer's prompt inlines the Charter
  // and the contract framework on top of the diff, which can exceed that on
  // its own. As an argument that fails the exec with E2BIG; on stdin there is
  // no such ceiling.
  const args = [
    "-p",
    // JSON so the session identifier is recoverable. Property 5 needs a stated
    // session identifier when the Writer and the Reviewer post under one
    // account, and text output gives nothing to state (BF6).
    "--output-format",
    "json",
    "--allowed-tools",
    allowed.join(","),
    "--disallowed-tools",
    deniedTools.join(","),
    "--permission-mode",
    // No prompts: nothing is watching. Anything outside the allowlist fails
    // rather than waiting for an answer that will never come.
    "acceptEdits",
  ];
  if (settingsPath) args.push("--settings", settingsPath);
  if (model) args.push("--model", model);

  return new Promise((resolve, reject) => {
    const child = spawnFn("claude", args, {
      cwd,
      env,
      stdio: ["pipe", "pipe", "pipe"],
    });
    child.stdin.on("error", () => {
      // The child can exit before the prompt is written - a bad flag, a
      // missing binary. The close handler reports why; an unhandled EPIPE here
      // would crash the run first and hide it.
    });
    child.stdin.end(prompt);

    let stdout = "";
    let stderr = "";
    let timedOut = false;

    const timer = setTimeout(() => {
      timedOut = true;
      child.kill("SIGKILL");
    }, timeoutMs);

    child.stdout.on("data", (d) => (stdout += d));
    child.stderr.on("data", (d) => (stderr += d));

    child.on("error", (err) => {
      clearTimeout(timer);
      reject(new AgentError(`Could not start the ${role}: ${err.message}`));
    });

    child.on("close", (code) => {
      clearTimeout(timer);
      if (timedOut) {
        reject(
          new AgentError(
            `The ${role} exceeded its ${Math.round(timeoutMs / 1000)}s timeout.`,
          ),
        );
        return;
      }
      if (code !== 0) {
        reject(
          new AgentError(
            `The ${role} exited ${code}: ${detail(stdout, stderr)}`,
          ),
        );
        return;
      }
      const parsed = parseAgentOutput(role, stdout);
      // A zero exit is not success on its own: the envelope carries its own
      // error flag, and a run that hit its turn limit reports it that way.
      // Passing that text on as a review would hand `parseReview` prose to
      // fail on, blaming the wrong thing.
      if (parsed.isError) {
        reject(
          new AgentError(
            `The ${role} reported an error: ${detail(stdout, stderr)}`,
          ),
        );
        return;
      }
      resolve(parsed);
    });
  });
}

/**
 * Read `claude -p --output-format json`.
 *
 * Falls back to treating the whole of stdout as the reply when it is not the
 * envelope, so a CLI change degrades to the previous behaviour rather than
 * failing the run — but the session identifier is then null, and the caller
 * says so in the record rather than inventing one.
 */
export function parseAgentOutput(role, stdout) {
  const text = stdout.trim();
  try {
    const doc = JSON.parse(text);
    if (doc && typeof doc === "object" && typeof doc.result === "string") {
      return {
        role,
        text: doc.result,
        sessionId: typeof doc.session_id === "string" ? doc.session_id : null,
        isError: doc.is_error === true,
      };
    }
  } catch {
    // Not the envelope; fall through.
  }
  return { role, text, sessionId: null, isError: false };
}

/**
 * What actually went wrong, for a message a human will read off a pull request.
 *
 * `claude -p --output-format json` writes its result — including its errors —
 * to **stdout**, and exits non-zero with stderr empty. Reporting stderr alone
 * produced "(no stderr)" and threw the only evidence away, which is how the
 * loop's second live run became undiagnosable. Both streams are reported, and
 * the envelope's own `result` is preferred when it is there.
 */
export function detail(stdout, stderr) {
  const out = String(stdout ?? "").trim();
  const err = String(stderr ?? "").trim();
  try {
    const doc = JSON.parse(out);
    if (doc && typeof doc === "object") {
      const message =
        typeof doc.result === "string"
          ? doc.result
          : typeof doc.error === "string"
            ? doc.error
            : null;
      if (message) return truncate(message);
    }
  } catch {
    // Not the envelope; report the raw streams instead.
  }
  const parts = [];
  if (out) parts.push(`stdout: ${truncate(out)}`);
  if (err) parts.push(`stderr: ${truncate(err)}`);
  return parts.join("\n") || "(no output on either stream)";
}

/** Enough to diagnose, short enough for a comment. */
function truncate(s, limit = 1500) {
  return s.length <= limit ? s : `${s.slice(0, limit)}… (${s.length} chars)`;
}

/**
 * Pull the first top-level JSON object out of an agent's reply.
 *
 * Models wrap JSON in prose or a fence even when told not to. Extracting is
 * tolerant; validating what was extracted is not - that is `findings.mjs`.
 */
export function extractJson(text) {
  const fenced = /```(?:json)?\s*([\s\S]*?)```/.exec(text);
  const candidate = fenced ? fenced[1] : text;
  const start = candidate.indexOf("{");
  if (start === -1) throw new AgentError("The agent returned no JSON object.");

  let depth = 0;
  let inString = false;
  let escaped = false;
  for (let i = start; i < candidate.length; i += 1) {
    const ch = candidate[i];
    if (escaped) {
      escaped = false;
    } else if (ch === "\\") {
      escaped = true;
    } else if (ch === '"') {
      inString = !inString;
    } else if (!inString && ch === "{") {
      depth += 1;
    } else if (!inString && ch === "}") {
      depth -= 1;
      if (depth === 0) return candidate.slice(start, i + 1);
    }
  }
  throw new AgentError("The agent's JSON object is not closed.");
}
