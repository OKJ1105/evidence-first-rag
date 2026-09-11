// The checks layer is the one module whose input used to be reachable from
// the branch under review, and the bootstrap review found exactly the defect
// class this file exists to pin: an empty manifest concluded "the checks
// pass" while nothing ran. Every error path here must fail closed, and the
// manifest must be readable from a directory other than the one the commands
// run in, because the orchestrator reads it from the base checkout (BF4).

import { mkdtempSync, mkdirSync, writeFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "./test-kit.mjs";
import { awaitCiOnHead, checksManifestPath, ciBudgetMs, ciRunner, ciWorkflowFile, loadChecksManifest, modelFor, runChecks, withCiVerdict } from "./run.mjs";

function tempRepo(manifestBody) {
  const dir = mkdtempSync(join(tmpdir(), "agent-checks-"));
  if (manifestBody !== undefined) {
    mkdirSync(join(dir, ".github"), { recursive: true });
    writeFileSync(join(dir, checksManifestPath), manifestBody);
  }
  return dir;
}

describe("loadChecksManifest fails closed on every bad input", () => {
  it.each([
    ["a missing manifest", undefined, /missing/],
    ["malformed JSON", "{nope", /not valid JSON/],
    ["no checks array", '{"checks": "yes"}', /no "checks" array/],
    ["an empty checks array", '{"checks": []}', /fails closed/],
    [
      "an entry without a command",
      '{"checks": [{"name": "x"}]}',
      /invalid entry/,
    ],
    [
      "a command with a non-string argument",
      '{"checks": [{"name": "x", "command": ["git", 1]}]}',
      /invalid entry/,
    ],
  ])("rejects %s", (_label, body, message) => {
    const dir = tempRepo(body);
    try {
      const manifest = loadChecksManifest(dir);
      expect(manifest.error).toMatch(message);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  it("accepts a valid manifest", () => {
    const dir = tempRepo('{"checks": [{"name": "ok", "command": ["node", "-v"]}]}');
    try {
      const manifest = loadChecksManifest(dir);
      expect(manifest.error).toBeUndefined();
      expect(manifest.checks).toHaveLength(1);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });
});

describe("runChecks", () => {
  it("reports a manifest error as a failing check, never a pass", async () => {
    const dir = tempRepo('{"checks": []}');
    try {
      const r = await runChecks({ cwd: dir, manifestDir: dir });
      expect(r.ok).toBe(false);
      expect(r.summary).toContain("FAIL");
      expect(r.summary).toContain("fails closed");
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  it("reads the manifest from manifestDir and runs commands in cwd", async () => {
    const base = tempRepo(
      JSON.stringify({
        checks: [
          {
            name: "cwd-marker",
            command: [
              "node",
              "-e",
              "process.exit(require('node:fs').existsSync('marker.txt') ? 0 : 1)",
            ],
          },
        ],
      }),
    );
    const head = tempRepo(undefined);
    writeFileSync(join(head, "marker.txt"), "x");
    try {
      // Manifest exists only in base; marker exists only in head. Passing
      // proves the split: definition from base, execution in head.
      const r = await runChecks({ cwd: head, manifestDir: base });
      expect(r.ok).toBe(true);
    } finally {
      rmSync(base, { recursive: true, force: true });
      rmSync(head, { recursive: true, force: true });
    }
  });

  it("binds {baseDir} to the base checkout, not to the branch", async () => {
    // The tamper case. Both trees hold a script at the same path; only base's
    // is the real one. A check that names it through {baseDir} must run base's
    // copy, or a branch is judged by a script it wrote itself.
    const base = tempRepo(
      JSON.stringify({
        checks: [{ name: "scripted", command: ["node", "{baseDir}/check.js"] }],
      }),
    );
    const head = mkdtempSync(join(tmpdir(), "agent-checks-head-"));
    try {
      // Each script announces itself before exiting. Asserting only that the
      // run failed would pass for the wrong reason: with the substitution
      // broken, `{baseDir}/check.js` stays literal, node cannot find it, and
      // the run fails too — the same verdict for the opposite cause. The
      // marker is what separates "base's script ran" from "no script ran".
      writeFileSync(join(base, "check.js"), "console.log('BASE-RAN');process.exit(1);\n");
      writeFileSync(join(head, "check.js"), "console.log('HEAD-RAN');process.exit(0);\n");
      const result = await runChecks({ cwd: head, manifestDir: base, baseDir: base });
      // base's script fails; head's would have passed. Failing is correct.
      expect(result.ok).toBe(false);
      const output = result.results.map((r) => r.output).join("\n");
      expect(output).toContain("BASE-RAN");
      expect(output).not.toContain("HEAD-RAN");
    } finally {
      rmSync(base, { recursive: true, force: true });
      rmSync(head, { recursive: true, force: true });
    }
  });

  it("runs a {baseDir} script the branch has never seen", async () => {
    // The stale-branch case. A branch older than a check does not have the
    // script; naming it through {baseDir} must still run it, instead of
    // reporting a broken check when the real fact is an out-of-date branch.
    const base = tempRepo(
      JSON.stringify({
        checks: [{ name: "new-check", command: ["node", "{baseDir}/added.js"] }],
      }),
    );
    const head = mkdtempSync(join(tmpdir(), "agent-checks-stale-"));
    try {
      writeFileSync(join(base, "added.js"), "process.exit(0);\n");
      const result = await runChecks({ cwd: head, manifestDir: base, baseDir: base });
      expect(result.ok).toBe(true);
    } finally {
      rmSync(base, { recursive: true, force: true });
      rmSync(head, { recursive: true, force: true });
    }
  });

  it("leaves a command without {baseDir} running in the branch", async () => {
    // The condition the binding must NOT impose. Checks that verify the
    // branch's own code — the agent unit tests — still run from head.
    const base = tempRepo(
      JSON.stringify({
        checks: [{ name: "branch-own", command: ["node", "own.js"] }],
      }),
    );
    const head = mkdtempSync(join(tmpdir(), "agent-checks-own-"));
    try {
      writeFileSync(join(base, "own.js"), "process.exit(1);\n");
      writeFileSync(join(head, "own.js"), "process.exit(0);\n");
      const result = await runChecks({ cwd: head, manifestDir: base, baseDir: base });
      expect(result.ok).toBe(true);
    } finally {
      rmSync(base, { recursive: true, force: true });
      rmSync(head, { recursive: true, force: true });
    }
  });

  it("binds {baseRef} in command arguments", async () => {
    const dir = tempRepo(
      JSON.stringify({
        checks: [
          {
            name: "baseref",
            command: [
              "node",
              "-e",
              "process.exit(process.argv[1] === 'origin/dev' ? 0 : 1)",
              "origin/{baseRef}",
            ],
          },
        ],
      }),
    );
    try {
      const bound = await runChecks({ cwd: dir, manifestDir: dir, baseRef: "dev" });
      expect(bound.ok).toBe(true);
      const unbound = await runChecks({ cwd: dir, manifestDir: dir, baseRef: "main" });
      expect(unbound.ok).toBe(false);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  it("stops at the first failing check", async () => {
    const dir = tempRepo(
      JSON.stringify({
        checks: [
          { name: "fails", command: ["node", "-e", "process.exit(1)"] },
          { name: "never-runs", command: ["node", "-e", "process.exit(0)"] },
        ],
      }),
    );
    try {
      const r = await runChecks({ cwd: dir, manifestDir: dir });
      expect(r.ok).toBe(false);
      expect(r.results).toHaveLength(1);
      expect(r.summary).not.toContain("never-runs");
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });
});

// #30. `CI_AGENT_MODEL` was read and set nowhere, so every turn ran on
// whatever the CLI defaulted to and no merged review names what produced it.
// These pin the resolution order and, more importantly, the unset case: an
// empty variable must not reach the CLI as `--model ""`.
//
// Deliberately absent: any assertion that the two configured models differ.
// The different-model requirement was dropped by the repository owner on
// 2026-09-03 (#30), and a test asserting it would re-impose through the test
// suite what the governing document no longer asks for.

describe("modelFor pins the model per role", () => {
  it("resolves each role from its own variable", () => {
    const env = {
      CI_AGENT_WRITER_MODEL: "claude-opus-5",
      CI_AGENT_REVIEWER_MODEL: "claude-fable-5-1",
    };
    expect(modelFor("writer", env)).toBe("claude-opus-5");
    expect(modelFor("reviewer", env)).toBe("claude-fable-5-1");
  });

  it("falls back to the shared variable when a role is unset", () => {
    const env = { CI_AGENT_MODEL: "claude-opus-5" };
    expect(modelFor("writer", env)).toBe("claude-opus-5");
    expect(modelFor("reviewer", env)).toBe("claude-opus-5");
  });

  it("prefers the per-role variable over the shared one", () => {
    const env = {
      CI_AGENT_MODEL: "claude-opus-5",
      CI_AGENT_REVIEWER_MODEL: "claude-fable-5-1",
    };
    expect(modelFor("reviewer", env)).toBe("claude-fable-5-1");
    expect(modelFor("writer", env)).toBe("claude-opus-5");
  });

  it("accepts two roles configured to the same model", () => {
    // The shipped configuration. Nothing may refuse it: model difference is
    // not an independence property and is not required.
    const env = {
      CI_AGENT_WRITER_MODEL: "claude-opus-5",
      CI_AGENT_REVIEWER_MODEL: "claude-opus-5",
    };
    expect(modelFor("writer", env)).toBe("claude-opus-5");
    expect(modelFor("reviewer", env)).toBe("claude-opus-5");
  });

  it("reports nothing pinned rather than an empty model", () => {
    // An empty string would reach the CLI as `--model ""`. `undefined` makes
    // `claude.mjs` omit the flag, and the published comment says "unpinned".
    expect(modelFor("writer", {})).toBe(undefined);
    expect(modelFor("reviewer", { CI_AGENT_REVIEWER_MODEL: "  " })).toBe(undefined);
    expect(modelFor("writer", { CI_AGENT_MODEL: "" })).toBe(undefined);
  });

  it("trims a padded value rather than passing the padding through", () => {
    expect(modelFor("writer", { CI_AGENT_WRITER_MODEL: " claude-opus-5 " })).toBe(
      "claude-opus-5",
    );
  });

  it("treats an unknown role as the writer's variable rather than throwing", () => {
    // `runAgent` already rejects an unknown role with a named error, and this
    // resolver runs before it. Returning a value keeps the failure there,
    // where the message says which role was wrong.
    expect(modelFor("auditor", { CI_AGENT_MODEL: "claude-opus-5" })).toBe(
      "claude-opus-5",
    );
  });
});

// #21. The loop's Writer pushes with GITHUB_TOKEN, and GitHub starts no
// workflow from an event that token raised. So `repository-checks` never ran
// on a loop-fixed head and the loop labelled it ready anyway — observed on
// #18, head `03ba0c4`, zero check runs. These drive the dispatch-and-wait
// with a fake client, a fake clock and a fake sleep, so every branch is
// exercised without a network.

function fakeActions({ runs = [], dispatchError = null, listError = null } = {}) {
  const calls = { dispatched: [], listed: 0 };
  const pages = Array.isArray(runs[0]) ? [...runs] : [runs];
  return {
    calls,
    dispatchWorkflow: async (file, ref) => {
      calls.dispatched.push({ file, ref });
      if (dispatchError) throw new Error(dispatchError);
      return null;
    },
    listWorkflowRuns: async () => {
      calls.listed += 1;
      if (listError && calls.listed === 1) throw new Error(listError);
      const page = pages.length > 1 ? pages.shift() : pages[0];
      return { workflow_runs: page };
    },
  };
}

const fastClock = () => {
  let t = 0;
  return { now: () => t, sleep: async (ms) => { t += ms; } };
};

const completed = (sha, conclusion) => ({
  head_sha: sha,
  status: "completed",
  conclusion,
  html_url: `https://example/run/${conclusion}`,
});

describe("awaitCiOnHead dispatches CI and waits for its verdict", () => {
  it("dispatches the CI workflow on the branch that was pushed to", async () => {
    // No run exists on this head yet, which is the loop-pushed case: the push
    // used `GITHUB_TOKEN` and raised nothing.
    const gh = fakeActions({ runs: [] });
    await awaitCiOnHead({ gh, branch: "agent/1-x", headSha: "headsha", ...fastClock() });
    expect(gh.calls.dispatched).toEqual([
      { file: ciWorkflowFile, ref: "agent/1-x" },
    ]);
  });

  it("does not dispatch when a run already exists on that head (#113 B2)", async () => {
    // A `pull_request` run on the head answers the same question, which is why
    // `listWorkflowRuns` is unfiltered by event. Dispatching anyway would burn
    // a second runner on every human-pushed head for no new information — and
    // looking first is what lets the caller ask about any head it concludes on,
    // not only one this run pushed.
    const gh = fakeActions({ runs: [completed("headsha", "success")] });
    const r = await awaitCiOnHead({ gh, branch: "b", headSha: "headsha", ...fastClock() });
    expect(gh.calls.dispatched).toEqual([]);
    expect(r.ok).toBe(true);
  });

  it("does not dispatch when a run is already in progress on that head (#113 B2)", async () => {
    // The case the completed-run test cannot reach: a run exists but has not
    // finished. Dispatching a second one would race it and prove nothing.
    const gh = fakeActions({
      runs: [{ head_sha: "headsha", status: "in_progress", conclusion: null }],
    });
    await awaitCiOnHead({ gh, branch: "b", headSha: "headsha", ...fastClock() });
    expect(gh.calls.dispatched).toEqual([]);
  });

  it("says the budget ran out rather than that no run appeared (#113 N9)", async () => {
    // Two different things for the owner to do. "No run appeared" is the
    // stale-branch diagnosis `docs/agent-loop.md` teaches; an exhausted budget
    // means CI was dispatched and is running normally, and the pull request's
    // own checks will say so a minute later. Reporting the second as the first
    // sends the owner to rebase a branch that is fine.
    const gh = fakeActions({ runs: [] });
    const r = await awaitCiOnHead({
      gh,
      branch: "b",
      headSha: "headsha",
      timeoutMs: 0,
      pollMs: 15_000,
      sleep: async () => {},
      now: () => 0,
    });
    expect(r.ok).toBe(false);
    expect(r.conclusion).toBe("budget_exhausted");
    expect(r.summary).toContain("no job time left");
    expect(r.summary).not.toContain("no run appeared");
    // The dispatch still happened, so CI posts its own status to the head.
    expect(gh.calls.dispatched.length).toBe(1);
  });

  it("still waits when the budget is merely small, not gone (#113 N9)", async () => {
    // The boundary matters: a budget shorter than one poll cannot observe
    // anything, but anything longer should still be spent looking.
    const gh = fakeActions({ runs: [completed("headsha", "success")] });
    const r = await awaitCiOnHead({
      gh,
      branch: "b",
      headSha: "headsha",
      timeoutMs: 60_000,
      pollMs: 15_000,
      sleep: async () => {},
      now: () => 0,
    });
    expect(r.conclusion).toBe("success");
  });

  it("retries a listing that throws DURING the wait, not only before it (#113 O6)", async () => {
    // The gap this closes was mine twice over: the retry branch inside the poll
    // loop had no test, and my own mutation pass never mutated it either — both
    // existing listing-failure cases throw on the first call, which is the
    // pre-dispatch look, so the `catch { log; continue }` in the wait was never
    // entered. A transient 502 mid-wait would then have turned a head whose CI
    // passed into `timed_out` → `needs-human`.
    let n = 0;
    const gh = {
      calls: { dispatched: [] },
      dispatchWorkflow: async (file, ref) => {
        gh.calls.dispatched.push({ file, ref });
      },
      listWorkflowRuns: async () => {
        n += 1;
        if (n === 1) return { workflow_runs: [] };
        if (n === 2) throw new Error("502 Bad Gateway");
        return { workflow_runs: [completed("headsha", "success")] };
      },
    };
    const r = await awaitCiOnHead({ gh, branch: "b", headSha: "headsha", ...fastClock() });
    expect(n).toBe(3);
    expect(r.ok).toBe(true);
    expect(r.conclusion).toBe("success");
  });

  it("answers from an existing completed run without waiting at all (#113 B2)", async () => {
    // The look-first path has to be a shortcut, not just a different route to
    // the same poll loop: the wait is minutes, and re-entering it for a run
    // that has already concluded spends them for an answer already in hand.
    let slept = 0;
    const gh = fakeActions({ runs: [completed("headsha", "success")] });
    const r = await awaitCiOnHead({
      gh,
      branch: "b",
      headSha: "headsha",
      timeoutMs: 60_000,
      pollMs: 1_000,
      sleep: async () => {
        slept += 1;
      },
      now: () => 0,
    });
    expect(slept).toBe(0);
    expect(r.ok).toBe(true);
  });

  it("dispatches anyway when the listing throws, rather than reading it as no run", async () => {
    // Not knowing is not a reason to skip the check.
    let first = true;
    const inner = fakeActions({ runs: [completed("headsha", "success")] });
    const gh = {
      calls: inner.calls,
      dispatchWorkflow: inner.dispatchWorkflow,
      listWorkflowRuns: async (...args) => {
        if (first) {
          first = false;
          throw new Error("502");
        }
        return inner.listWorkflowRuns(...args);
      },
    };
    const r = await awaitCiOnHead({ gh, branch: "b", headSha: "headsha", ...fastClock() });
    expect(gh.calls.dispatched.length).toBe(1);
    expect(r.ok).toBe(true);
  });

  it("passes when the run on that exact head concludes success", async () => {
    const gh = fakeActions({ runs: [completed("headsha", "success")] });
    const r = await awaitCiOnHead({ gh, branch: "b", headSha: "headsha", ...fastClock() });
    expect(r.ok).toBe(true);
    expect(r.conclusion).toBe("success");
    expect(r.url).toBe("https://example/run/success");
  });

  it("fails when that run concludes anything else", async () => {
    const gh = fakeActions({ runs: [completed("headsha", "failure")] });
    const r = await awaitCiOnHead({ gh, branch: "b", headSha: "headsha", ...fastClock() });
    expect(r.ok).toBe(false);
    expect(r.conclusion).toBe("failure");
  });

  it("ignores a completed run on a different head", async () => {
    // The stale-evidence mistake BF2 exists to stop. A green run on the
    // previous commit says nothing about the one about to be labelled.
    const gh = fakeActions({ runs: [completed("an-older-head", "success")] });
    const r = await awaitCiOnHead({
      gh, branch: "b", headSha: "headsha", timeoutMs: 60_000, pollMs: 15_000, ...fastClock(),
    });
    expect(r.ok).toBe(false);
    expect(r.conclusion).toBe("timed_out");
    expect(r.summary).toMatch(/no run appeared on this head/);
  });

  it("keeps waiting while the run is still in progress, then takes its verdict", async () => {
    const gh = fakeActions({
      runs: [
        [{ head_sha: "headsha", status: "in_progress", conclusion: null }],
        [completed("headsha", "success")],
      ],
    });
    const r = await awaitCiOnHead({ gh, branch: "b", headSha: "headsha", ...fastClock() });
    expect(r.ok).toBe(true);
    expect(gh.calls.listed).toBe(2);
  });

  it("reports a run that starts but never finishes as a timeout, not a pass", async () => {
    const gh = fakeActions({
      runs: [{ head_sha: "headsha", status: "in_progress", conclusion: null, html_url: "u" }],
    });
    const r = await awaitCiOnHead({
      gh, branch: "b", headSha: "headsha", timeoutMs: 60_000, pollMs: 15_000, ...fastClock(),
    });
    expect(r.ok).toBe(false);
    expect(r.conclusion).toBe("timed_out");
    expect(r.summary).toMatch(/did not finish/);
  });

  it("reports a dispatch it could not raise, rather than passing silently", async () => {
    // The failure mode the Issue is about: an unchecked head reaching a ready
    // label. A swallowed dispatch error would recreate it exactly.
    const gh = fakeActions({ dispatchError: "403 Resource not accessible" });
    const r = await awaitCiOnHead({ gh, branch: "b", headSha: "headsha", ...fastClock() });
    expect(r.ok).toBe(false);
    expect(r.conclusion).toBe("not_dispatched");
    expect(r.summary).toMatch(/403 Resource not accessible/);
  });

  it("retries a failed poll rather than giving up on the run", async () => {
    const gh = fakeActions({
      listError: "502 Bad Gateway",
      runs: [completed("headsha", "success")],
    });
    const r = await awaitCiOnHead({ gh, branch: "b", headSha: "headsha", ...fastClock() });
    expect(r.ok).toBe(true);
    expect(gh.calls.listed).toBe(2);
  });
});

describe("withCiVerdict folds CI into the verdict the state machine reads", () => {
  const passing = { ok: true, summary: "All checks passed." };

  it("keeps a pass a pass when CI passed", () => {
    const r = withCiVerdict(passing, { ok: true, conclusion: "success", url: null, summary: "- ci: pass" });
    expect(r.ok).toBe(true);
  });

  it("turns a pass into a failure when CI failed", () => {
    // The whole point: `nextStep` concludes needs-human on `checks.ok === false`,
    // so a red CI can no longer be labelled ready.
    const r = withCiVerdict(passing, { ok: false, conclusion: "failure", url: null, summary: "- ci: FAIL" });
    expect(r.ok).toBe(false);
  });

  it("keeps the two summaries apart", () => {
    // "the loop's checks passed and CI failed" and "a check failed" are
    // different facts and the owner acts differently on them.
    const r = withCiVerdict(passing, { ok: false, conclusion: "failure", url: "https://example/run/1", summary: "- ci: FAIL" });
    expect(r.summary).toContain("All checks passed.");
    expect(r.summary).toContain("- ci: FAIL");
    expect(r.summary).toContain("https://example/run/1");
  });

  it("leaves the verdict untouched when no CI verdict was taken", () => {
    expect(withCiVerdict(passing, null)).toBe(passing);
  });
});

// N3 on #113. The CI wait is the one step long enough to cross the job's
// ceiling on its own, and a job that hits `timeout-minutes` is cancelled rather
// than failed — so it publishes nothing at all. Capping the wait by what is
// actually left is what stops the wait from being the cause.

describe("the CI wait is bounded by the job's remaining time (#113 N3)", () => {
  const t0 = "2026-01-01T00:00:00Z";
  const at = (min) => Date.parse(t0) + min * 60_000;

  it("asks for the full wait early in the job", () => {
    expect(ciBudgetMs({ startedAt: t0, now: at(1) })).toBe(10 * 60_000);
  });

  it("shortens the wait once the ceiling is close", () => {
    // 60 minute ceiling, 53 spent, 2 reserved for the conclusion -> 5 left.
    expect(ciBudgetMs({ startedAt: t0, now: at(53) })).toBe(5 * 60_000);
  });

  it("never returns a negative wait", () => {
    // A run already past its budget asks for no wait and takes whatever
    // verdict is already on the head.
    expect(ciBudgetMs({ startedAt: t0, now: at(75) })).toBe(0);
  });

  it("keeps a reserve, so the wait is never the whole of what is left", () => {
    // Without it the wait could end exactly at the ceiling, leaving no time to
    // write the conclusion the run exists to publish.
    const left = 60 * 60_000 - 58 * 60_000;
    expect(ciBudgetMs({ startedAt: t0, now: at(58) })).toBe(0);
    expect(left > 0).toBe(true);
  });

  it("is computed from the job's start, so setup time is not counted as spare", () => {
    // #113 N8. The ceiling is the job's `timeout-minutes`, measured from job
    // start; the orchestrator only learns the time once it begins, after the
    // checkouts, toolchain setup and CLI install. Budgeting from process start
    // is optimistic by exactly that setup, and the guarantee this cap exists to
    // give — that the wait is never what crosses the ceiling — does not hold.
    const jobStart = "2026-01-01T00:00:00Z";
    const processStart = "2026-01-01T00:04:00Z";
    const now = Date.parse(jobStart) + 53 * 60_000;
    // From the job's start there are 5 minutes left after the reserve.
    expect(ciBudgetMs({ startedAt: jobStart, now })).toBe(5 * 60_000);
    // From the process's start it looks like 9, which would run 4 minutes past.
    expect(ciBudgetMs({ startedAt: processStart, now })).toBe(9 * 60_000);
  });

  it("falls back to the requested wait when the start time is unreadable", () => {
    // A malformed marker should not silently mean "do not wait for CI".
    expect(ciBudgetMs({ startedAt: "not a date" })).toBe(10 * 60_000);
  });
});

describe("the ci dependency main() wires in carries the bound (#113 N3)", () => {
  // `main()` is wiring and is not otherwise covered. #30 made `agentRunner` a
  // factory for exactly this reason, after an unpinned model was read and never
  // set; a bound computed and never passed is the same defect one slice over.

  it("passes the budgeted timeout, not the raw default", () => {
    let got = null;
    const run = ciRunner({
      gh: {},
      startedAt: new Date(Date.now() - 53 * 60_000).toISOString(),
      awaitCi: async (args) => {
        got = args;
        return { ok: true };
      },
    });
    return run({ branch: "b", headSha: "h" }).then(() => {
      expect(got.timeoutMs <= 5 * 60_000).toBe(true);
      expect(got.timeoutMs > 0).toBe(true);
    });
  });

  it("passes the branch and head it was asked about", () => {
    let got = null;
    const run = ciRunner({
      gh: {},
      startedAt: new Date().toISOString(),
      awaitCi: async (args) => {
        got = args;
        return { ok: true };
      },
    });
    return run({ branch: "agent/1-x", headSha: "sha" }).then(() => {
      expect(got.branch).toBe("agent/1-x");
      expect(got.headSha).toBe("sha");
    });
  });
});

// #137 B1. The carve-out that lets a re-run re-take a verdict (#116) must key
// on whether a COMPLETED run judged the head, never on the conclusion string:
// `cancelled` is only ever GitHub's own verdict, and `timed_out` is both
// GitHub's and this function's wait-expiry sentinel. Since `awaitCiOnHead`
// looks for an existing run before dispatching, a completed run on the head
// means a re-run gets the same answer for ever — so a head mistaken for
// "unseen" could never conclude again, and `reset` would not end it.

describe("a CI verdict says whether a completed run produced it (#137)", () => {
  for (const conclusion of ["success", "failure", "cancelled", "timed_out"]) {
    it(`marks a completed \`${conclusion}\` run as observed`, async () => {
      const gh = fakeActions({ runs: [completed("headsha", conclusion)] });
      const r = await awaitCiOnHead({
        gh,
        branch: "b",
        headSha: "headsha",
        ...fastClock(),
      });
      expect(r.conclusion).toBe(conclusion);
      expect(r.observed).toBe(true);
    });
  }

  it("marks a completed run with no conclusion as observed", async () => {
    // `unknown` is this function's word for a run GitHub reports as completed
    // with a null conclusion. Completed is completed: re-asking cannot help.
    const gh = fakeActions({
      runs: [{ head_sha: "headsha", status: "completed", conclusion: null }],
    });
    const r = await awaitCiOnHead({
      gh,
      branch: "b",
      headSha: "headsha",
      ...fastClock(),
    });
    expect(r.conclusion).toBe("unknown");
    expect(r.observed).toBe(true);
  });

  it("marks a refused dispatch as not observed", async () => {
    const gh = {
      listWorkflowRuns: async () => ({ workflow_runs: [] }),
      dispatchWorkflow: async () => {
        throw new Error("403");
      },
    };
    const r = await awaitCiOnHead({
      gh,
      branch: "b",
      headSha: "headsha",
      ...fastClock(),
    });
    expect(r.conclusion).toBe("not_dispatched");
    expect(r.observed).toBe(false);
  });

  it("marks an exhausted job budget as not observed", async () => {
    const gh = fakeActions({ runs: [] });
    const r = await awaitCiOnHead({
      gh,
      branch: "b",
      headSha: "headsha",
      timeoutMs: 0,
      ...fastClock(),
    });
    expect(r.conclusion).toBe("budget_exhausted");
    expect(r.observed).toBe(false);
  });

  it("marks its own expired wait as not observed", async () => {
    // The collision that makes the string unusable: this is `timed_out` and so
    // is the first table's fourth row, and they must decide oppositely.
    const gh = fakeActions({ runs: [] });
    const r = await awaitCiOnHead({
      gh,
      branch: "b",
      headSha: "headsha",
      ...fastClock(),
    });
    expect(r.conclusion).toBe("timed_out");
    expect(r.observed).toBe(false);
  });

  it("keeps the flag through `withCiVerdict`, which is how the loop reads it", () => {
    const folded = withCiVerdict(
      { ok: true, summary: "checks" },
      { ok: false, conclusion: "timed_out", url: null, observed: false, summary: "s" },
    );
    expect(folded.ci.observed).toBe(false);
  });
});
