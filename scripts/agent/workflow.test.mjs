import { existsSync, readFileSync, statSync } from "node:fs";
import { describe, expect, it } from "./test-kit.mjs";
import { governingDocs, reviewerDocs } from "./run.mjs";
import { deniedTools } from "./claude.mjs";

// The workflow grants permissions; `github.mjs` spends them. Nothing connects
// the two, and a mismatch is invisible until a live run — the loop's first one
// died three seconds in on a 403 reading the Issue (#80). These assertions are
// the connection.

const workflow = readFileSync(".github/workflows/agent-loop.yml", "utf8");

/** The `permissions:` block of one job, as raw lines. */
function permissionsOf(job) {
  const rest = workflow.slice(workflow.indexOf(`\n  ${job}:\n`));
  const block = /\n {4}permissions:\n((?: {6}\S.*\n)+)/.exec(rest);
  if (!block) throw new Error(`the ${job} job declares no permissions`);
  return block[1];
}

describe("the loop job's permissions match what the loop actually calls", () => {
  it("grants issues: read, because the Reviewer is handed the Issue (BF1)", () => {
    // Dropping this line fails no other test and does not fail CI. It fails
    // only when someone runs the loop for real, which is what happened.
    expect(permissionsOf("loop")).toMatch(/^ {6}issues: read$/m);
  });

  it("does not grant issues: write — the loop only reads an Issue", () => {
    expect(permissionsOf("loop")).not.toMatch(/issues: write/);
  });

  it("keeps the gate read-only", () => {
    expect(permissionsOf("gate")).toMatch(/^ {6}contents: read$/m);
    expect(permissionsOf("gate")).not.toMatch(/write/);
  });

  it("grants nothing at the top level", () => {
    expect(workflow).toMatch(/^permissions: \{\}$/m);
  });
});

describe("only one client call is scoped to a real Issue", () => {
  // GitHub governs pull-request comments and labels by `pull-requests` even
  // though they are served from the issues API. The bare `/issues/${number}`
  // read is the exception, and `run.mjs` passes it the linked Issue number.
  // A second Issue-scoped call — especially a write — would need a permission
  // the job is not granted, so its arrival should fail here rather than in a run.
  it("getIssue is the only one", () => {
    const source = readFileSync("scripts/agent/github.mjs", "utf8");
    const bare = [
      ...source.matchAll(
        /"(GET|POST|PATCH|PUT|DELETE)",\s*`\$\{base\}\/issues\/\$\{number\}`/g,
      ),
    ];
    expect(bare.map((m) => m[1])).toEqual(["GET"]);
  });
});

// Emptying `reviewerDocs` left the whole suite green until this existed — the
// same shape as the defect #81 P0 fixes: a list that looks populated, is not,
// and takes a live run to notice.

describe("the documents each role is given", () => {
  it("gives the Reviewer its brief, the Charter and the contract framework", () => {
    expect(reviewerDocs).toEqual([
      "docs/reviewer-brief.md",
      "docs/PROJECT_CHARTER.md",
      "docs/contracts/README.md",
    ]);
  });

  it("gives both roles the four governing documents", () => {
    expect(governingDocs).toEqual([
      "AGENTS.md",
      "CLAUDE.md",
      "docs/DEVELOPMENT_WORKFLOW.md",
      "docs/ai-development-workflow.md",
    ]);
  });

  it("names files that exist and have content", () => {
    // A renamed or moved document would otherwise throw at `readFileSync`
    // inside a live run, after the job has spent a checkout and an install.
    for (const rel of [...governingDocs, ...reviewerDocs]) {
      expect(existsSync(rel), `${rel} is missing`).toBe(true);
      expect(statSync(rel).size, `${rel} is empty`).toBeGreaterThan(0);
    }
  });
});

describe("the two tool denylists agree", () => {
  // claude.mjs passes --disallowed-tools per process; the workflow pins a
  // settings file so a branch-supplied .claude/settings.json cannot widen
  // anything. They are two expressions of one rule, and they drifted once.
  it("every CLI-denied tool is denied in the pinned settings too", () => {
    const line = /"deny":\[([^\]]+)\]/.exec(workflow);
    expect(line).not.toBeNull();
    const pinned = [...line[1].matchAll(/"([^"]+)"/g)].map((m) => m[1]);
    for (const tool of deniedTools) {
      expect(pinned).toContain(tool);
    }
  });
});
