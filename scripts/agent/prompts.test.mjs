import { describe, expect, it } from "./test-kit.mjs";
import { reviewerPrompt, writerPrompt } from "./prompts.mjs";

// The loop's Reviewer once ran without `docs/reviewer-brief.md`, the Charter
// or the contract framework, so the brief's blocking priorities could not be
// applied. A Reviewer never shown its priorities cannot enforce them, so the
// prompt names them and this test pins that.

describe("the Reviewer's own documents", () => {
  const call = (over = {}) =>
    reviewerPrompt({
      issueNumber: 78,
      issueBody: "ISSUE",
      riskLevel: "L2",
      branch: "b",
      diff: "d",
      checks: { summary: "ok" },
      round: 1,
      priorFindings: [],
      docs: "SHARED-DOCS",
      reviewerDocs: "BRIEF-AND-CHARTER",
      ...over,
    });

  it("reaches the Reviewer", () => {
    expect(call()).toContain("BRIEF-AND-CHARTER");
  });

  it("names the blocking priorities, so they are not left to be inferred", () => {
    const p = call();
    expect(p).toMatch(/hard architecture boundaries/i);
    expect(p).toMatch(/registered fixed SQL templates/);
    expect(p).toMatch(/fail closed/);
    expect(p).toMatch(/evidence_bundle/);
    expect(p).toMatch(/source_trace/);
    expect(p).toMatch(/limitations/);
    expect(p).toMatch(/contract-first/i);
    expect(p).toMatch(/`Accepted` state/);
  });

  it("says the brief loses to AGENTS.md and the workflow", () => {
    // The brief says so itself; a Reviewer that only sees the brief would not
    // know which document wins.
    expect(call()).toMatch(/those win and the brief is wrong/);
  });

  it("still withholds the pull request body (BF1 is not undone)", () => {
    const p = call({ issueBody: "ISSUEBODYMARKER" });
    expect(p).toContain("ISSUEBODYMARKER");
    expect(p).not.toContain("PRBODYMARKER");
  });
});

describe("the Writer does not get the Reviewer's documents", () => {
  it("keeps the Writer prompt to the shared governing documents", () => {
    const p = writerPrompt({
      issueNumber: 78,
      issueBody: "ISSUE",
      riskLevel: "L2",
      branch: "b",
      findings: [],
      checks: { summary: "ok" },
      round: 1,
      cap: 2,
      docs: "SHARED-DOCS",
      protectedPaths: ["scripts/"],
    });
    expect(p).toContain("SHARED-DOCS");
    expect(p).not.toContain("BRIEF-AND-CHARTER");
  });
});
