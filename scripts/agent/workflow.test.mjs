import { existsSync, readFileSync, statSync } from "node:fs";
import { describe, expect, it } from "./test-kit.mjs";
import { governingDocs, reviewerDocs } from "./run.mjs";
import { deniedTools } from "./claude.mjs";

// The workflow grants permissions; `github.mjs` spends them. Nothing connects
// the two, and a mismatch is invisible until a live run — the loop's first one
// died three seconds in on a 403 reading the Issue (#80). These assertions are
// the connection.

// Normalized to LF. A CRLF checkout is a property of the machine reading
// the file, not of the workflow, and letting it reach the line patterns
// below made every assertion here fail on Windows while passing in CI —
// a check that fails only on the maintainer's platform teaches people to
// ignore it.
const workflow = normalize(
  readFileSync(".github/workflows/agent-loop.yml", "utf8"),
);

/** CI's own definition. #21 makes the loop dispatch it, so it must be dispatchable. */
const ci = normalize(
  readFileSync(".github/workflows/repository-checks.yml", "utf8"),
);

/** Strip carriage returns so the line patterns below see LF either way. */
export function normalize(text) {
  return text.replaceAll("\r\n", "\n");
}

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

describe("the workflow pins the model each loop role runs on", () => {
  // Unset is the failure mode this exists for. The CLI version above it is
  // pinned so the toolchain moves only by a deliberate commit; an unpinned
  // model undoes that silently, and nothing else in the repository would
  // notice. `modelFor` resolves whatever is set — these assert that
  // something is.
  const values = () =>
    [...workflow.matchAll(/\n\s+CI_AGENT_\w*MODEL:[ \t]*(.+)/g)].map((m) =>
      m[1].trim(),
    );

  it.each([["CI_AGENT_WRITER_MODEL"], ["CI_AGENT_REVIEWER_MODEL"]])(
    "sets %s in the loop job",
    (name) => {
      expect(workflow).toMatch(new RegExp("\\n\\s+" + name + ":[ \\t]*\\S+"));
    },
  );

  it("sets exactly those two and no third model variable", () => {
    expect(values()).toHaveLength(2);
  });

  it("names a concrete model, not a passthrough expression", () => {
    // `${{ ... }}` here would move the pin into repository settings, where a
    // change leaves no commit. Leaving one is the whole point.
    for (const v of values()) expect(v.startsWith("${{")).toBe(false);
  });
});

describe("the loop can dispatch CI, and CI can be dispatched (#21)", () => {
  // Two halves of one mechanism, in two files. Either alone is useless and
  // fails only on a live run — the exact shape of defect this file exists for.

  it("grants the loop job actions: write, which dispatching needs", () => {
    expect(permissionsOf("loop")).toMatch(/^ {6}actions: write$/m);
  });

  it("still grants nothing else administrative", () => {
    // The permission was widened by one line on a recorded owner decision.
    // This pins that it was one line.
    const granted = permissionsOf("loop");
    expect(granted).not.toMatch(/^ {6}id-token:/m);
    expect(granted).not.toMatch(/^ {6}packages:/m);
    expect(granted).not.toMatch(/^ {6}administration:/m);
  });

  it("does not tell its reader that CI runs on the Writer's push (#113 B1)", () => {
    // The loop's own header comment asserted the falsehood #21 was opened
    // about — "`ci.yml` still runs on those pushes" — and after the rest of
    // this slice it also contradicted `docs/agent-loop.md`, which now says the
    // opposite. The file that *is* the loop is the worst place to leave it: a
    // reader, or a future agent turn, opens it and is told the thing that
    // caused the defect.
    expect(workflow).not.toMatch(/still\s+runs on those pushes/);
    expect(workflow).toMatch(/raises no CI of its own/);
  });

  it("does not name a workflow file this repository does not have (#113 B1)", () => {
    // The same sentence named `ci.yml`. There is no such file; CI is
    // `repository-checks.yml`, which is what the dispatch actually targets.
    expect(existsSync(".github/workflows/ci.yml")).toBe(false);
    expect(workflow).not.toMatch(/`ci\.yml`/);
    expect(workflow).toMatch(/dispatches `repository-checks\.yml`/);
  });

  it("gives repository-checks a workflow_dispatch trigger", () => {
    expect(ci).toMatch(/\n {2}workflow_dispatch:/);
  });

  it("keeps repository-checks' pull_request trigger, so the normal path is unchanged", () => {
    // Additive, per #17 rule 2's carve-out. Replacing the trigger rather than
    // adding to it would stop CI on every ordinary pull request.
    expect(ci).toMatch(/\n {2}pull_request:/);
  });

  it("resolves the whitespace range without the pull request event", () => {
    // On a dispatched run there is no pull request, so the two shas are empty
    // and `git diff --check "..."` would fail for a reason that has nothing to
    // do with whitespace.
    expect(ci).toContain('base="${BASE_SHA:-$(git rev-parse "origin/$BASE_REF")}"');
    expect(ci).toContain('head="${HEAD_SHA:-$(git rev-parse HEAD)}"');
  });
});

describe("CRLF tolerance", () => {
  it("normalizes a CRLF checkout before matching", () => {
    // Fed CRLF directly, the line patterns above match nothing. This asserts
    // the normalizer rather than the checkout, so the guard survives on a
    // machine that happens to check out LF.
    const crlf = "\n    permissions:\r\n      contents: read\r\n";
    expect(normalize(crlf)).toBe("\n    permissions:\n      contents: read\n");
  });
});
