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
import {
  checksManifestPath,
  loadChecksManifest,
  modelFor,
  runChecks,
} from "./run.mjs";

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
