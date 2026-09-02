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

describe("the Reviewer is told what it can and cannot see", () => {
  // Two non-blocking findings on PR #10's predecessor asserted repository
  // state the Reviewer had no way to observe: that a file existed nowhere,
  // and that a file had one commit. Both were true of the one tree it was
  // given and false of the repository. It was not careless — nothing told it
  // the two differ, and no tool it holds can tell them apart.
  const prompt = reviewerPrompt({
    issueNumber: 1,
    issueBody: "ISSUE",
    riskLevel: "L2",
    branch: "b",
    diff: "d",
    checks: { summary: "ok" },
    round: 1,
    priorFindings: [],
    docs: "DOCS",
    reviewerDocs: "BRIEF",
    // Collapsed, because the prompt is wrapped prose: a phrase that straddles
    // a line break is still present, and asserting otherwise tests the
    // wrapping rather than the instruction.
  }).replace(/\s+/g, " ");

  it("states the field of view is one tree", () => {
    expect(prompt).toContain("one working tree: the branch under review");
    expect(prompt).toContain("cannot run commands");
    expect(prompt).toContain("cannot read the base branch");
  });

  it("names the three situations that look identical from there", () => {
    expect(prompt).toContain("absent from the repository");
    expect(prompt).toContain("because the branch predates it");
  });

  it("requires a claim to be scoped to what was observed", () => {
    expect(prompt).toContain("absent from this");
    expect(prompt).toContain("does not exist in this");
  });

  it("forbids claims about history, which it cannot observe at all", () => {
    expect(prompt).toContain("no commits");
    expect(prompt).toContain("what a file used to");
  });

  it("asks for the alternative it cannot rule out, not silence", () => {
    // The instruction must not suppress the finding — a stale branch and a
    // missing file are both worth reporting. Only the unobservable assertion
    // has to go.
    expect(prompt).toContain("name the alternative you cannot rule out");
  });
});
