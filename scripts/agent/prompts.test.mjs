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
      ownerDecisionPaths: ["docs/contracts/"],
    });
    expect(p).toContain("SHARED-DOCS");
    expect(p).not.toContain("BRIEF-AND-CHARTER");
  });
});

describe("the Writer is told about both fences, with the reason for each", () => {
  // Two lists, two reasons. A prompt that named the paths without the reason
  // would leave the Writer to infer one, and on 2026-09-03 it inferred that a
  // contract amendment was a review-finding fix — twice, in opposite
  // directions. See #34.
  const prompt = writerPrompt({
    issueNumber: 1,
    issueBody: "ISSUE",
    riskLevel: "L2",
    branch: "b",
    findings: [],
    checks: { summary: "ok" },
    round: 1,
    cap: 2,
    docs: "DOCS",
    protectedPaths: ["scripts/", ".github/"],
    ownerDecisionPaths: ["docs/contracts/"],
  }).replace(/\s+/g, " ");

  it("lists the paths from both fences", () => {
    expect(prompt).toContain("`scripts/`");
    expect(prompt).toContain("`.github/`");
    expect(prompt).toContain("`docs/contracts/`");
  });

  it("gives BF3 the credential reason", () => {
    expect(prompt).toContain("privileges you do not have");
  });

  it("gives the second fence the recorded-decision reason, not the credential one", () => {
    // The distinction the two lists exist to preserve: a contract is not
    // executed and holds no credential, so borrowing privilege is not why it
    // is fenced.
    expect(prompt).toContain("recorded human");
    expect(prompt).toContain("Section 10");
    expect(prompt).toContain("nothing carries a credential");
  });

  it("forbids the revert direction as well as the amend direction", () => {
    // #23 amended a contract to authorise its own branch; #32 reverted an
    // authorised amendment because the decision was recorded where it could
    // not see it. Naming only the first would leave the second open.
    expect(prompt).toContain("do not revert an amendment");
    expect(prompt).toContain("recorded outside your inputs still exists");
  });

  it("says declining is the expected outcome, not a failed turn", () => {
    expect(prompt).toContain("not a failure of your turn");
  });
});

// #29. The Reviewer holds `Read`, `Glob` and `Grep` over one working tree and
// no history, and nothing in its prompt said so. Three findings asserted
// repository state it could not observe, one of them grading a real gap
// `optional` on a mitigation that does not exist. The fix is context, and the
// tests that matter are the ones pinning that it stays context rather than
// becoming an instruction to keep quiet.

describe("the Reviewer is told its field of view (#29)", () => {
  const prompt = reviewerPrompt({
    issueNumber: 29,
    issueBody: "ISSUE",
    riskLevel: "L1",
    branch: "b",
    diff: "d",
    checks: { summary: "ok" },
    round: 1,
    priorFindings: [],
    docs: "SHARED-DOCS",
    reviewerDocs: "BRIEF-AND-CHARTER",
  });
  const flat = prompt.replace(/\s+/g, " ");

  it("states the boundary: one tree, no shell, no history, no base branch", () => {
    expect(flat).toMatch(/one working tree/);
    expect(flat).toMatch(/`Read`, `Glob` and `Grep`/);
    expect(flat).toMatch(/No shell, no network, no GitHub API, and \*\*no history\*\*/);
    expect(flat).toMatch(/no base branch/);
  });

  it("names the three situations it cannot tell apart, and which one it sees", () => {
    expect(flat).toMatch(/indistinguishable/);
    expect(flat).toContain("A file that exists nowhere in the repository.");
    expect(flat).toContain("A file that exists on the base branch but not in this tree");
    expect(flat).toContain("A file this diff deletes.");
    expect(flat).toMatch(/only the third is visible/);
  });

  it("asks for the unruled-out alternative, and does not ask for silence", () => {
    // The load-bearing half of #29. An instruction that reads "do not raise
    // what you cannot verify" would suppress the finding instead of scoping
    // it, and a suppressed gap is worse than a loosely worded one.
    expect(flat).toContain("This is not a request for silence");
    expect(flat).toMatch(/still a finding/);
    expect(flat).toContain("Name the alternative you could not rule out");
    expect(flat).toMatch(/which observation would settle it/);
  });

  it("requires the claim to be scoped to the tree it was read from", () => {
    expect(flat).toMatch(/no file matching `X` in this tree/);
    expect(flat).toMatch(/rather than "`X` does not exist in the repository"/);
  });

  it("forbids grading a finding on an unopened mitigation", () => {
    // The #24 `O1` shape: `optional` awarded for a source scan that never
    // looks for what the finding said it looks for.
    expect(flat).toMatch(/Grade the finding on what you verified/);
    expect(flat).toMatch(/never on a mitigation you are assuming/);
    expect(flat).toMatch(/an unchecked mitigation reported as one is worse/);
  });

  it("says the manifest checks are not the whole of CI", () => {
    // Raised as the same finding on three consecutive pull requests, because
    // the answer lived only in the pull request body, which BF1 withholds.
    expect(flat).toMatch(/not the whole of CI/);
    expect(flat).toContain("`.github/agent-checks.json`");
    expect(flat).toContain("`database-checks`");
    expect(flat).toMatch(/CI stays authoritative for merge/);
  });

  it("scopes an unseen check as a limit of its view, still reportable", () => {
    expect(flat).toMatch(
      /a fact about your field of view, not evidence that the change is unverified/,
    );
    expect(flat).toMatch(/Report that you could not see it/);
  });
});

describe("the field of view is the Reviewer's alone", () => {
  it("is not in the Writer prompt, which edits the tree rather than judging it", () => {
    const p = writerPrompt({
      issueNumber: 29,
      issueBody: "ISSUE",
      riskLevel: "L1",
      branch: "b",
      findings: [],
      checks: { summary: "ok" },
      round: 1,
      cap: 2,
      docs: "SHARED-DOCS",
      protectedPaths: ["scripts/"],
      ownerDecisionPaths: ["docs/contracts/"],
    });
    expect(p).not.toContain("What you can and cannot see");
  });
});
