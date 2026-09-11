import { existsSync, readFileSync, statSync } from "node:fs";
import { describe, expect, it } from "./test-kit.mjs";
import { governingDocs, jobBudgetMs, reviewerDocs } from "./run.mjs";
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

  it("does not list a permission as absent that the same block grants (#113 B3)", () => {
    // B1's defect, one block lower and inside the security-relevant surface:
    // the "notably absent" list named `actions` nineteen lines above
    // `actions: write`. Someone auditing what the loop holds reads that list.
    // Scoped to the "notably absent" SENTENCE, not the whole comment block:
    // prose around it may name a permission precisely to say it IS granted,
    // and forbidding that would push the explanation out of the file.
    const loopBlock = workflow.slice(workflow.indexOf("\n  loop:"));
    const absent = loopBlock.match(/# Notably absent:[^.]*\./);
    expect(absent).not.toBe(null);
    for (const granted of permissionsOf("loop").matchAll(/^ {6}([a-z-]+):/gm)) {
      expect(absent[0].includes(`\`${granted[1]}\``)).toBe(false);
    }
  });

  it("reports a crashed run on cancellation as well as failure (#113 N3)", () => {
    // A job that hits `timeout-minutes` is CANCELLED, not failed. Guarded on
    // `failure()` alone, the reporter is skipped and the pull request is left
    // carrying `agent:running` with no conclusion — the one label state this
    // loop otherwise never leaves behind.
    const reporter = workflow.slice(workflow.indexOf("- name: Report a crashed run"));
    expect(reporter).toMatch(/if: failure\(\) \|\| cancelled\(\)/);
  });

  it("keeps the two whitespace-range mechanisms in separate paragraphs (#113 O7)", () => {
    // My own O3 edit ran them together, so "Without this" read as attributing
    // the fallback's purpose to `fetch-depth: 0`. That is the same
    // misleading-comment defect B1 and B3 raised as blocking against the loop
    // workflow, left behind in the file this slice had just edited.
    const step = ci.slice(ci.indexOf("- name: Check changed lines for whitespace"));
    const comment = step.slice(0, step.indexOf("\n        env:"));
    expect(comment).not.toMatch(/true\. `fetch-depth: 0`/);
    expect(comment).toMatch(/`:-` fallbacks are what keep the step/);
  });

  it("records the job's start before anything else runs (#113 N8)", () => {
    // The budget subtracts from the job's ceiling, so it has to measure from
    // the job's start. This must be the FIRST step: every step before it is
    // setup time the orchestrator would otherwise count as spare.
    const loopBlock = workflow.slice(workflow.indexOf("\n  loop:"));
    const firstStep = loopBlock.slice(loopBlock.indexOf("\n    steps:"));
    expect(firstStep).toMatch(/steps:\n {6}- name: Record when this job started/);
    expect(firstStep).toMatch(/CI_AGENT_JOB_STARTED_AT=/);
    expect(firstStep).toMatch(/>> "\$GITHUB_ENV"/);
  });

  it("mirrors the loop job's timeout into the code that bounds the CI wait", () => {
    // `ciBudgetMs` caps the wait by what is left of this budget. A constant
    // that drifted from the workflow would make the cap wrong in the one
    // direction that matters — too generous, so the wait crosses the ceiling.
    const loopBlock = workflow.slice(workflow.indexOf("\n  loop:"));
    const declared = loopBlock.match(/\n {4}timeout-minutes: (\d+)/);
    expect(declared).not.toBe(null);
    expect(Number(declared[1]) * 60_000).toBe(jobBudgetMs);
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

// #126 round 1, finding N2. The independence table and the loop diagram are
// what an owner answers "what does the Reviewer see, and where could a Writer's
// own narrative reach it" from. They enumerated Issue + diff + check results
// and went on saying that after the Issue's comments started reaching both
// prompts. The document names this drift shape as a real defect itself.

describe("the loop document enumerates what each role actually sees", () => {
  const doc = readFileSync("docs/agent-loop.md", "utf8");
  const property3 = /\| 3\. Recorded order of exposure \|[^|]*\|/.exec(doc);

  it("has the property-3 row", () => {
    expect(property3).not.toBeNull();
  });

  it("names the Issue's comments as an input, in that row", () => {
    expect(property3[0]).toContain("the Issue's own comments");
  });

  it("says the Writer gets them too, not the Reviewer alone", () => {
    expect(property3[0]).toContain("Writer prompt carries the Issue and its comments");
  });

  it("still says the pull request's own body and comments reach neither", () => {
    // BF2. Widening the row must not quietly drop what it already guaranteed.
    expect(property3[0]).toContain("reach neither prompt");
    expect(property3[0]).toContain("BF2");
  });

  it("names the round-2 exception rather than overstating the rule", () => {
    expect(property3[0]).toContain("earlier findings");
  });

  it("says what a failed read renders as", () => {
    expect(property3[0]).toContain("could not read them");
  });

  it("puts the comments in the diagram too", () => {
    const diagram = doc.slice(doc.indexOf("owner comments /agent-loop"));
    expect(diagram.slice(0, diagram.indexOf("```"))).toContain(
      "Issue + its comments + diff",
    );
  });
});

// #116. The document is where the owner learns what `/agent-loop reset` means,
// and the reason this change exists is that `reset` silently meant two things.
// A document that still describes it as the only way to re-take a verdict
// would keep teaching the workaround this removes.

describe("the loop document records the transient-CI carve-out (#116)", () => {
  const doc = readFileSync("docs/agent-loop.md", "utf8");

  it("names every conclusion that counts as unseen", () => {
    for (const c of ["timed_out", "not_dispatched", "budget_exhausted", "cancelled"]) {
      expect(doc, `${c} is not named`).toContain(c);
    }
  });

  it("says the re-examination spends no round", () => {
    expect(doc).toContain("no round is spent");
  });

  it("says a red build stays terminal", () => {
    expect(doc).toContain("`failure` is about the branch");
  });

  it("stops presenting reset as the way to re-take a verdict", () => {
    expect(doc).toContain("Re-examination now happens on a plain re-run");
  });
});
