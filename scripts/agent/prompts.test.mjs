import { describe, expect, it } from "./test-kit.mjs";
import { issueDiscussion, reviewerPrompt, writerPrompt } from "./prompts.mjs";

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

  it("says the second fence stops the run differently from the first (#82)", () => {
    // N3 on #92. The two fences now terminate differently — BF3 aborts, BF7
    // concludes and hands over — and a Writer told they do the same thing is
    // reading the description that was true before #82.
    expect(prompt).toContain("it stops the run differently");
    expect(prompt).toContain("stops and hands the pull request to the owner");
    expect(prompt).toContain("nothing from your turn is committed or pushed");
    // The first fence keeps its own word.
    expect(prompt).toContain("the run is **aborted** if your edits touch");
  });

  it("does not commend the second fence's outcome to the Writer (#92 N9)", () => {
    // N9 on #92. The BF7 path exits `run.mjs`'s fix step by `continue`, above
    // the `state.round + 1` increment, so tripping the fence costs the Writer
    // no round and ends the run at once. A prompt that also calls that outcome
    // correct — "where a contract-only change is supposed to end", "not a
    // failed run" — describes a free exit from any finding the Writer cannot
    // resolve, and the honest conclusion ("blocking finding(s) remain after N
    // of 2 round trip(s)") is never reached. The owner is the reader who needs
    // the designed-terminus framing, and `docs/agent-loop.md` Section 5 gives
    // it to them; the Writer needs the prohibition.
    expect(prompt).toContain("without your fix");
    expect(prompt).toContain("the route you must take instead");
    expect(prompt).toContain("is the worse of the two");
    expect(prompt).not.toContain("is supposed to end");
    expect(prompt).not.toContain("That is not a failed run");
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

// #33's first defect. The loop read `issue.body` and nothing else, so a
// decision recorded as an Issue comment reached neither role. On #32 that made
// the Writer revert a contract amendment because "no such decision is present
// in this session's context" — correct on its inputs, and the inputs were
// missing it.

describe("the Issue's comments reach both roles, as discussion (#33)", () => {
  const comments = [
    {
      user: { login: "OKJ1105" },
      created_at: "2026-09-01T00:00:00Z",
      body: "DECISION: alias resolution stays opt-in.",
    },
    {
      user: { login: "github-actions[bot]" },
      created_at: "2026-09-02T00:00:00Z",
      body: "SECOND: and the fixture ids are frozen.",
    },
  ];
  const base = {
    issueNumber: 42,
    issueBody: "ISSUE BODY",
    issueComments: comments,
    riskLevel: "L2",
    branch: "b",
    checks: { summary: "All checks passed." },
    docs: [],
  };
  const reviewer = reviewerPrompt({ ...base, diff: "d", round: 1, priorFindings: [] });
  const writer = writerPrompt({
    ...base,
    findings: [],
    round: 1,
    cap: 2,
    protectedPaths: ["scripts/"],
    ownerDecisionPaths: ["docs/contracts/"],
  });

  it("puts every comment in the Reviewer's prompt", () => {
    expect(reviewer).toContain("DECISION: alias resolution stays opt-in.");
    expect(reviewer).toContain("SECOND: and the fixture ids are frozen.");
  });

  it("puts every comment in the Writer's prompt", () => {
    // Option 1 on the Issue: both roles, not the Reviewer alone. A Writer that
    // cannot see the decision is the role that reverted the amendment.
    expect(writer).toContain("DECISION: alias resolution stays opt-in.");
    expect(writer).toContain("SECOND: and the fixture ids are frozen.");
  });

  it("keeps them out of the Issue's own section", () => {
    // The body is what the slice is measured against; a comment is someone
    // talking about it, including talk the next comment superseded. Merged into
    // one text, a passing remark reads as a requirement.
    const issueSection = reviewer.slice(
      reviewer.indexOf("## Issue #42"),
      reviewer.indexOf("## Discussion on the Issue"),
    );
    expect(issueSection).toContain("ISSUE BODY");
    expect(issueSection).not.toContain("DECISION: alias resolution");
  });

  it("labels them as discussion rather than specification", () => {
    expect(reviewer).toContain("comments on the Issue, not the Issue's specification");
    expect(writer).toContain("comments on the Issue, not the Issue's specification");
  });

  it("says a login is not provenance, without claiming what is (#33 defect 2)", () => {
    // Writer, Reviewer and owner post under one account. Defect 2 — what a
    // "recorded decision" claim is worth, and what does carry provenance — is
    // not settled by this slice, so the prompt states the limit and stops.
    expect(reviewer).toContain("not provenance");
    expect(reviewer).toContain("post under one account");
  });

  it("names the authors anyway, so two voices can be told apart", () => {
    expect(reviewer).toContain("OKJ1105");
    expect(reviewer).toContain("github-actions[bot]");
  });

  it("keeps the comments in the order they were said", () => {
    expect(reviewer.indexOf("DECISION: alias") < reviewer.indexOf("SECOND: and the")).toBe(true);
  });

  it("tells the Reviewer the comments are now in its field of view (#29's gap)", () => {
    // The Issue names this as the same class as #29: the Reviewer had no way to
    // know comments existed at all.
    expect(reviewer).toContain("The Issue's comments are in your view");
  });

  it("still names what is outside the view, so the fix does not read as total", () => {
    expect(reviewer).toContain("the Issue's labels");
    expect(reviewer).toContain("every pull request comment");
  });
});

describe("issueDiscussion on an Issue with no comments", () => {
  it("says so, rather than rendering an empty heading", () => {
    // A blank section reads as "nothing was recorded anywhere"; an explicit
    // "None" reads as "this was looked at and there was nothing".
    expect(issueDiscussion([])).toContain("The Issue has no comments");
  });

  it("does not claim there is discussion to read", () => {
    expect(issueDiscussion([])).not.toContain("not the Issue's specification");
  });

  it("survives a malformed comment without dropping its body", () => {
    // The API shape is not this repository's to guarantee.
    const out = issueDiscussion([{ body: "orphaned" }]);
    expect(out).toContain("orphaned");
    expect(out).toContain("unknown");
    expect(out).toContain("undated");
  });

  it("treats a non-array as no comments at all", () => {
    expect(issueDiscussion(undefined)).toContain("The Issue has no comments");
    expect(issueDiscussion(null)).toContain("The Issue has no comments");
  });
});
