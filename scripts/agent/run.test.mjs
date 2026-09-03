import { describe, expect, it } from "./test-kit.mjs";
import {
  LABELS,
  assertNothingApproved,
  forbiddenEdits,
  ownerDecisionEdits,
  ownerDecisionPaths,
  protectedPaths,
  riskLevelOf,
  runLoop,
} from "./run.mjs";
import { parseState, renderStatusComment } from "./state.mjs";

/**
 * A fake GitHub that records what the loop did to the pull request.
 *
 * It has no approve method and no merge method, for the same reason the real
 * client does not: the loop must have no route to either.
 */
function fakeGitHub({ pr, issue, comments = [], reviews = [] } = {}) {
  const state = {
    pr: pr ?? {
      head: { sha: "sha0", ref: "agent/1-x" },
      body: "Closes #42\n\nRisk: `L2`",
      labels: [],
    },
    issue: issue ?? { number: 42, body: "ISSUE BODY: the requirement." },
    comments: [...comments],
    reviews: [...reviews],
    labels: new Set(),
    nextId: 100,
  };
  return {
    _: state,
    getPull: async () => state.pr,
    getIssue: async () => state.issue,
    listComments: async () => state.comments,
    createComment: async (_n, body) => {
      const c = { id: (state.nextId += 1), body };
      state.comments.push(c);
      return c;
    },
    updateComment: async (id, body) => {
      const c = state.comments.find((x) => x.id === id);
      c.body = body;
      return c;
    },
    addLabels: async (_n, labels) => labels.forEach((l) => state.labels.add(l)),
    removeLabel: async (_n, label) => state.labels.delete(label),
    listReviews: async () => state.reviews,
  };
}

/** Scripted agent: each call shifts the next canned reply for that role. */
function fakeAgent(script) {
  const queues = {
    reviewer: [...(script.reviewer ?? [])],
    writer: [...(script.writer ?? [])],
  };
  const calls = [];
  const fn = async ({ role, prompt }) => {
    calls.push({ role, prompt });
    const next = queues[role].shift();
    if (next === undefined)
      throw new Error(`fakeAgent ran out of ${role} replies`);
    return {
      role,
      text: typeof next === "string" ? next : JSON.stringify(next),
    };
  };
  fn.calls = calls;
  return fn;
}

const review = (findings, summary = "reviewed") => ({ summary, findings });
const blocking = (summary, file = "a.mjs") => ({
  severity: "blocking",
  file,
  summary,
  failure: "it breaks",
  fix: "fix it",
});

function baseCtx(overrides = {}) {
  return {
    prNumber: 7,
    runUrl: "https://example/run/1",
    startedAt: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

const passingChecks = async () => ({ ok: true, summary: "All checks passed." });

/** The state marker is its own comment now, not the last one (BF6). */
function stateOf(gh) {
  for (const c of gh._.comments) {
    const parsed = parseState(c.body);
    if (parsed) return parsed;
  }
  throw new Error("no state marker comment found");
}

describe("riskLevelOf", () => {
  it("prefers an explicit label", () => {
    expect(
      riskLevelOf({
        labels: [{ name: "L1" }],
        body: "Closes #42\n\nRisk: `L2`",
      }),
    ).toBe("L1");
  });

  it("falls back to the body", () => {
    expect(
      riskLevelOf({ labels: [], body: "Risk level: `L1` because ..." }),
    ).toBe("L1");
  });

  it("defaults to L2 when nothing says otherwise, per section 4", () => {
    expect(riskLevelOf({ labels: [], body: "no level here" })).toBe("L2");
  });
});

describe("runLoop", () => {
  it("concludes ready when the first review finds nothing blocking", async () => {
    const gh = fakeGitHub();
    const agent = fakeAgent({ reviewer: [review([])] });
    const result = await runLoop({
      gh,
      agent,
      checks: passingChecks,
      commit: async () => null,
      diff: async () => "diff",
      ctx: baseCtx(),
      log: () => {},
    });

    expect(result.action).toBe(LABELS.ready.replace("agent:", ""));
    expect(gh._.labels.has(LABELS.ready)).toBe(true);
    expect(gh._.labels.has(LABELS.running)).toBe(false);
    expect(gh._.comments.at(-1).body).toContain("Awaiting human merge");
    expect(gh._.comments.at(-1).body).toContain("Merging is the owner's act");
  });

  it("runs Reviewer, Writer, Reviewer and stops at the L2 cap", async () => {
    const gh = fakeGitHub();
    const agent = fakeAgent({
      reviewer: [review([blocking("one")]), review([])],
      writer: [
        {
          responses: [{ id: "B1", action: "fixed", note: "done" }],
          summary: "fixed B1",
        },
      ],
    });
    let head = 0;
    const result = await runLoop({
      gh,
      agent,
      checks: passingChecks,
      commit: async () => `sha${(head += 1)}`,
      diff: async () => "diff",
      ctx: baseCtx(),
      log: () => {},
    });

    expect(agent.calls.map((c) => c.role)).toEqual([
      "reviewer",
      "writer",
      "reviewer",
    ]);
    expect(result.round).toBe(1);
    expect(gh._.labels.has(LABELS.ready)).toBe(true);
  });

  it("stops after two rounds on L2 and asks for a human", async () => {
    const gh = fakeGitHub();
    const agent = fakeAgent({
      reviewer: [
        review([blocking("one")]),
        review([blocking("still")]),
        review([blocking("still")]),
      ],
      writer: [
        { responses: [{ id: "B1", action: "fixed" }], summary: "r1" },
        {
          responses: [{ id: "B1", action: "declined", note: "disagree" }],
          summary: "r2",
        },
      ],
    });
    let head = 0;
    const result = await runLoop({
      gh,
      agent,
      checks: passingChecks,
      commit: async () => `sha${(head += 1)}`,
      diff: async () => "diff",
      ctx: baseCtx(),
      log: () => {},
    });

    expect(result.round).toBe(2);
    expect(agent.calls.filter((c) => c.role === "writer")).toHaveLength(2);
    expect(gh._.labels.has(LABELS.needsHuman)).toBe(true);
    expect(gh._.labels.has(LABELS.ready)).toBe(false);
    expect(gh._.comments.at(-1).body).toContain("Stopped");
  });

  it("stops after one round on L1", async () => {
    const gh = fakeGitHub({
      pr: {
        head: { sha: "sha0", ref: "b" },
        body: "Closes #42\n\nRisk: `L1`",
        labels: [],
      },
    });
    const agent = fakeAgent({
      reviewer: [review([blocking("one")]), review([blocking("one")])],
      writer: [{ responses: [{ id: "B1", action: "fixed" }], summary: "r1" }],
    });
    const result = await runLoop({
      gh,
      agent,
      checks: passingChecks,
      commit: async () => "sha1",
      diff: async () => "diff",
      ctx: baseCtx(),
      log: () => {},
    });
    expect(result.round).toBe(1);
    expect(gh._.labels.has(LABELS.needsHuman)).toBe(true);
  });

  it("takes no review at all on L0", async () => {
    const gh = fakeGitHub({
      pr: {
        head: { sha: "s", ref: "b" },
        body: "Closes #42\n\nRisk: `L0`",
        labels: [],
      },
    });
    const agent = fakeAgent({});
    await runLoop({
      gh,
      agent,
      checks: passingChecks,
      commit: async () => null,
      diff: async () => "",
      ctx: baseCtx(),
      log: () => {},
    });
    expect(agent.calls).toHaveLength(0);
    expect(gh._.labels.has(LABELS.needsHuman)).toBe(true);
  });

  it("refuses to call a red build ready", async () => {
    const gh = fakeGitHub();
    const agent = fakeAgent({ reviewer: [review([])] });
    await runLoop({
      gh,
      agent,
      checks: async () => ({ ok: false, summary: "A check failed." }),
      commit: async () => null,
      diff: async () => "diff",
      ctx: baseCtx(),
      log: () => {},
    });
    expect(gh._.labels.has(LABELS.needsHuman)).toBe(true);
    expect(gh._.labels.has(LABELS.ready)).toBe(false);
  });

  it("is idempotent: a second run on the same head does nothing", async () => {
    const gh = fakeGitHub();
    const first = fakeAgent({ reviewer: [review([])] });
    await runLoop({
      gh,
      agent: first,
      checks: passingChecks,
      commit: async () => null,
      diff: async () => "d",
      ctx: baseCtx(),
      log: () => {},
    });
    const commentsAfterFirst = gh._.comments.length;

    const second = fakeAgent({}); // no replies queued: calling it would throw
    const result = await runLoop({
      gh,
      agent: second,
      checks: passingChecks,
      commit: async () => null,
      diff: async () => "d",
      ctx: baseCtx(),
      log: () => {},
    });

    expect(result.action).toBe("skip");
    expect(second.calls).toHaveLength(0);
    expect(gh._.comments).toHaveLength(commentsAfterFirst);
  });

  it("re-reviews when the head moved, without refunding the round count", async () => {
    const gh = fakeGitHub();
    await runLoop({
      gh,
      agent: fakeAgent({
        reviewer: [
          review([blocking("one")]),
          review([blocking("one")]),
          review([blocking("one")]),
        ],
        writer: [
          { responses: [], summary: "r1" },
          { responses: [], summary: "r2" },
        ],
      }),
      checks: passingChecks,
      commit: async () => "shaX",
      diff: async () => "d",
      ctx: baseCtx(),
      log: () => {},
    });
    const spent = stateOf(gh).round;
    expect(spent).toBe(2);

    // The owner pushes a commit. A new run must not get two more rounds.
    gh._.pr.head.sha = "shaNEW";
    const agent2 = fakeAgent({ reviewer: [review([blocking("one")])] });
    const result = await runLoop({
      gh,
      agent: agent2,
      checks: passingChecks,
      commit: async () => "shaNEW",
      diff: async () => "d",
      ctx: baseCtx(),
      log: () => {},
    });
    expect(agent2.calls.filter((c) => c.role === "writer")).toHaveLength(0);
    expect(result.round).toBe(2);
    expect(gh._.labels.has(LABELS.needsHuman)).toBe(true);
  });

  it("reset clears the round count when the owner asks", async () => {
    const gh = fakeGitHub();
    await runLoop({
      gh,
      agent: fakeAgent({
        reviewer: [
          review([blocking("one")]),
          review([blocking("one")]),
          review([blocking("one")]),
        ],
        writer: [
          { responses: [], summary: "r1" },
          { responses: [], summary: "r2" },
        ],
      }),
      checks: passingChecks,
      commit: async () => "shaX",
      diff: async () => "d",
      ctx: baseCtx(),
      log: () => {},
    });
    expect(stateOf(gh).round).toBe(2);

    const agent2 = fakeAgent({ reviewer: [review([])] });
    const result = await runLoop({
      gh,
      agent: agent2,
      checks: passingChecks,
      commit: async () => null,
      diff: async () => "d",
      ctx: baseCtx({ reset: true }),
      log: () => {},
    });
    expect(result.round).toBe(0);
    expect(gh._.labels.has(LABELS.ready)).toBe(true);
  });

  it("keeps a finding's id across rounds", async () => {
    const gh = fakeGitHub({
      pr: {
        head: { sha: "sha0", ref: "b" },
        body: "Closes #42\n\nRisk: `L1`",
        labels: [],
      },
    });
    await runLoop({
      gh,
      agent: fakeAgent({
        reviewer: [
          review([blocking("same defect")]),
          review([blocking("same defect"), blocking("new one", "b.mjs")]),
        ],
        writer: [
          {
            responses: [{ id: "B1", action: "declined", note: "no" }],
            summary: "r1",
          },
        ],
      }),
      checks: passingChecks,
      commit: async () => "shaX",
      diff: async () => "d",
      ctx: baseCtx(),
      log: () => {},
    });
    const body = gh._.comments.at(-1).body;
    expect(body).toContain("**B1**");
    expect(body).toContain("**B2**");
  });

  it("surfaces a malformed review as a failure instead of treating it as clean", async () => {
    const gh = fakeGitHub();
    await expect(
      runLoop({
        gh,
        agent: fakeAgent({ reviewer: ["I had a look and it seems fine!"] }),
        checks: passingChecks,
        commit: async () => null,
        diff: async () => "d",
        ctx: baseCtx(),
        log: () => {},
      }),
    ).rejects.toThrow();
    expect(gh._.labels.has(LABELS.ready)).toBe(false);
  });
});

describe("assertNothingApproved", () => {
  it("passes when no review approved", async () => {
    const gh = fakeGitHub({
      reviews: [{ state: "COMMENTED", submitted_at: "2026-01-01T01:00:00Z" }],
    });
    await expect(
      assertNothingApproved(gh, 7, "2026-01-01T00:00:00Z"),
    ).resolves.toBeUndefined();
  });

  it("fails the run if an approval appeared while the loop held the pull request", async () => {
    const gh = fakeGitHub({
      reviews: [
        {
          state: "APPROVED",
          submitted_at: "2026-01-01T01:00:00Z",
          user: { login: "someone" },
        },
      ],
    });
    await expect(
      assertNothingApproved(gh, 7, "2026-01-01T00:00:00Z"),
    ).rejects.toThrow(/never approve/);
  });

  it("ignores an approval that predates the run", async () => {
    const gh = fakeGitHub({
      reviews: [
        {
          state: "APPROVED",
          submitted_at: "2025-12-01T00:00:00Z",
          user: { login: "someone" },
        },
      ],
    });
    await expect(
      assertNothingApproved(gh, 7, "2026-01-01T00:00:00Z"),
    ).resolves.toBeUndefined();
  });
});

// ---------------------------------------------------------------------------
// Regression tests for the review's blocking findings. Each is written to fail
// against the code as it was, not merely to pass against the code as it is.
// ---------------------------------------------------------------------------

describe("BF1 - the Reviewer reads the Issue, never the pull request body", () => {
  it("puts the Issue body in the prompt and keeps the pull request body out", async () => {
    const gh = fakeGitHub({
      pr: {
        head: { sha: "sha0", ref: "b" },
        body: "Closes #42\n\nRisk: `L2`\n\nPRBODYMARKER: worth a reviewer's attention - look only at X.",
        labels: [],
      },
      issue: {
        number: 42,
        body: "ISSUEBODYMARKER: what this change must achieve.",
      },
    });
    const agent = fakeAgent({ reviewer: [review([])] });
    await runLoop({
      gh,
      agent,
      checks: passingChecks,
      commit: async () => null,
      diff: async () => "diff",
      ctx: baseCtx(),
      log: () => {},
    });

    const prompt = agent.calls.find((c) => c.role === "reviewer").prompt;
    expect(prompt).toContain("ISSUEBODYMARKER");
    // The inversion BF1 found: the Writer's framing was the only statement of
    // requirement the Reviewer received.
    expect(prompt).not.toContain("PRBODYMARKER");
  });

  it("keeps the pull request body out of the Writer prompt too", async () => {
    const gh = fakeGitHub({
      pr: {
        head: { sha: "sha0", ref: "b" },
        body: "Closes #42\n\nRisk: `L1`\n\nPRBODYMARKER",
        labels: [],
      },
      issue: { number: 42, body: "ISSUEBODYMARKER" },
    });
    const agent = fakeAgent({
      reviewer: [review([blocking("one")]), review([blocking("one")])],
      writer: [{ responses: [], summary: "r1" }],
    });
    await runLoop({
      gh,
      agent,
      checks: passingChecks,
      commit: async () => "sha1",
      diff: async () => "d",
      ctx: baseCtx(),
      log: () => {},
    });
    const prompt = agent.calls.find((c) => c.role === "writer").prompt;
    expect(prompt).toContain("ISSUEBODYMARKER");
    expect(prompt).not.toContain("PRBODYMARKER");
  });

  it("refuses to run when the pull request names no Issue, rather than falling back", async () => {
    const gh = fakeGitHub({
      pr: {
        head: { sha: "s", ref: "b" },
        body: "Risk: `L2`  (no Closes line)",
        labels: [],
      },
    });
    await expect(
      runLoop({
        gh,
        agent: fakeAgent({}),
        checks: passingChecks,
        commit: async () => null,
        diff: async () => "d",
        ctx: baseCtx(),
        log: () => {},
      }),
    ).rejects.toThrow(/names no Issue/);
  });
});

describe("R1 - a resumed clean review still runs the checks (#76)", () => {
  it("runs them, and refuses ready when they fail", async () => {
    // Run 1 posted a clean review at HEAD and was then cancelled - the job hit
    // its ceiling before the concluding comment - so the marker is left in
    // phase `review` at the same head. Run 2 resumes: no `review` step
    // executes, because the recorded review is neither absent nor stale.
    //
    // Against the code R1 describes, run 2 labelled the pull request ready and
    // reported "the checks pass" without ever having run them.
    const interrupted = {
      round: 1,
      phase: "review",
      headSha: "shaSAME",
      riskLevel: "L2",
      issueNumber: 42,
      registry: {},
      lastReview: { summary: "clean", findings: [] },
      checksOk: true,
      runId: null,
      updatedAt: null,
    };
    const gh = fakeGitHub({
      comments: [{ id: 7, body: renderStatusComment(interrupted) }],
    });
    gh._.pr.head.sha = "shaSAME";

    let calls = 0;
    const failing = async () => {
      calls += 1;
      return { ok: false, summary: "A check failed." };
    };

    await runLoop({
      gh,
      agent: fakeAgent({}),
      checks: failing,
      commit: async () => null,
      diff: async () => "d",
      ctx: baseCtx(),
      log: () => {},
    });

    expect(calls).toBe(1);
    expect(gh._.labels.has(LABELS.ready)).toBe(false);
    expect(gh._.labels.has(LABELS.needsHuman)).toBe(true);
  });

  it("concludes ready once the checks have actually passed", async () => {
    const interrupted = {
      round: 1,
      phase: "review",
      headSha: "shaSAME",
      riskLevel: "L2",
      issueNumber: 42,
      registry: {},
      lastReview: { summary: "clean", findings: [] },
      checksOk: null,
      runId: null,
      updatedAt: null,
    };
    const gh = fakeGitHub({
      comments: [{ id: 7, body: renderStatusComment(interrupted) }],
    });
    gh._.pr.head.sha = "shaSAME";

    let calls = 0;
    const passing = async () => {
      calls += 1;
      return { ok: true, summary: "All checks passed." };
    };

    await runLoop({
      gh,
      agent: fakeAgent({}),
      checks: passing,
      commit: async () => null,
      diff: async () => "d",
      ctx: baseCtx(),
      log: () => {},
    });

    // The verdict is earned on this run, not inherited from the marker.
    expect(calls).toBe(1);
    expect(gh._.labels.has(LABELS.ready)).toBe(true);
  });
});

describe("BF2 - a resuming run re-runs the checks", () => {
  it("does not carry a previous run's verdict, and refuses a red head", async () => {
    const gh = fakeGitHub();
    // Round 1 concludes needs-human with the checks passing.
    await runLoop({
      gh,
      agent: fakeAgent({
        reviewer: [
          review([blocking("one")]),
          review([blocking("one")]),
          review([blocking("one")]),
        ],
        writer: [
          { responses: [], summary: "r1" },
          { responses: [], summary: "r2" },
        ],
      }),
      checks: passingChecks,
      commit: async () => "shaOLD",
      diff: async () => "d",
      ctx: baseCtx(),
      log: () => {},
    });

    // The owner pushes. The checks now fail. The loop must notice.
    gh._.pr.head.sha = "shaNEW";
    let calls = 0;
    const failing = async () => {
      calls += 1;
      return { ok: false, summary: "A check failed." };
    };
    await runLoop({
      gh,
      agent: fakeAgent({ reviewer: [review([])] }),
      checks: failing,
      commit: async () => null,
      diff: async () => "d",
      ctx: baseCtx(),
      log: () => {},
    });

    // Against the code BF2 describes: calls === 0, and the label was `ready`.
    expect(calls).toBeGreaterThan(0);
    expect(gh._.labels.has(LABELS.needsHuman)).toBe(true);
    expect(gh._.labels.has(LABELS.ready)).toBe(false);
  });

  it("never puts undefined where the check results belong", async () => {
    const gh = fakeGitHub();
    const agent = fakeAgent({ reviewer: [review([])] });
    await runLoop({
      gh,
      agent,
      checks: passingChecks,
      commit: async () => null,
      diff: async () => "d",
      ctx: baseCtx(),
      log: () => {},
    });
    expect(agent.calls[0].prompt).not.toContain("undefined");
  });
});

describe("BF3 - a Writer turn that edits the machinery aborts the run", () => {
  it.each([
    ["scripts/agent/loop.test.mjs"],
    ["scripts/checks/validate_links.py"],
    [".github/workflows/agent-loop.yml"],
    [".github/agent-checks.json"],
    [".githooks/pre-commit"],
    [".claude/settings.json"],
  ])("refuses an edit to %s", async (path) => {
    const gh = fakeGitHub();
    await expect(
      runLoop({
        gh,
        agent: fakeAgent({
          reviewer: [review([blocking("one")])],
          writer: [{ responses: [], summary: "r1" }],
        }),
        checks: passingChecks,
        commit: async () => "sha1",
        diff: async () => "d",
        // Only the machinery path. `docs/contracts/` used to sit here too,
        // which stopped mattering the moment it grew a fence of its own (#34):
        // the run would abort either way and the test could no longer say
        // which fence did it.
        changedPaths: async () => ["src/evidence_first_rag/runtime/routes.py", path],
        ctx: baseCtx(),
        log: () => {},
      }),
    ).rejects.toThrow(/protected paths/);
  });

  it("allows an ordinary source edit", async () => {
    const gh = fakeGitHub();
    const result = await runLoop({
      gh,
      agent: fakeAgent({
        reviewer: [review([blocking("one")]), review([])],
        writer: [{ responses: [{ id: "B1", action: "fixed" }], summary: "r1" }],
      }),
      checks: passingChecks,
      commit: async () => "sha1",
      diff: async () => "d",
      changedPaths: async () => ["src/lib/rag/contract.ts"],
      ctx: baseCtx(),
      log: () => {},
    });
    expect(result.round).toBe(1);
  });
});

describe("a Writer turn that edits the contract aborts the run", () => {
  // #34. The loop's Writer amended an accepted contract on #23 to authorise
  // its own branch, and reverted an authorised amendment on #32 because the
  // decision was recorded where it could not see it. Both are refused here,
  // and the message must give the recorded-decision reason rather than BF3's
  // credential one — a contract is never executed and holds no credential.
  it.each([
    ["docs/contracts/mvp-v0.1.md"],
    ["docs/contracts/README.md"],
  ])("refuses an edit to %s", async (path) => {
    const gh = fakeGitHub();
    await expect(
      runLoop({
        gh,
        agent: fakeAgent({
          reviewer: [review([blocking("one")])],
          writer: [{ responses: [], summary: "r1" }],
        }),
        checks: passingChecks,
        commit: async () => "sha1",
        diff: async () => "d",
        changedPaths: async () => [path],
        ctx: baseCtx(),
        log: () => {},
      }),
    ).rejects.toThrow(/recorded human decision/);
  });

  it("does not report the contract under BF3's credential wording", async () => {
    // The reason the two fences are separate lists. Reported under BF3 this
    // would tell a reader the contract is fenced to stop an agent borrowing
    // the orchestrator's privileges, which is not true of a document nothing
    // executes.
    const gh = fakeGitHub();
    await expect(
      runLoop({
        gh,
        agent: fakeAgent({
          reviewer: [review([blocking("one")])],
          writer: [{ responses: [], summary: "r1" }],
        }),
        checks: passingChecks,
        commit: async () => "sha1",
        diff: async () => "d",
        changedPaths: async () => ["docs/contracts/mvp-v0.1.md"],
        ctx: baseCtx(),
        log: () => {},
      }),
    ).rejects.toThrow(/not a review-finding fix/);
  });

  it("leaves a document outside docs/contracts/ alone", async () => {
    // The condition this fence must NOT impose. `docs/agent-loop.md` and the
    // workflow documents are ordinary prose a finding may legitimately need.
    const gh = fakeGitHub();
    const result = await runLoop({
      gh,
      agent: fakeAgent({
        reviewer: [review([blocking("one")]), review([])],
        writer: [{ responses: [{ id: "B1", action: "fixed" }], summary: "r1" }],
      }),
      checks: passingChecks,
      commit: async () => "sha1",
      diff: async () => "d",
      changedPaths: async () => ["docs/DEVELOPMENT_WORKFLOW.md"],
      ctx: baseCtx(),
      log: () => {},
    });
    expect(result.round).toBe(1);
  });
});

describe("BF6 - the record is not overwritten", () => {
  it("keeps round 1's findings and response after round 2", async () => {
    const gh = fakeGitHub();
    await runLoop({
      gh,
      agent: fakeAgent({
        reviewer: [
          review([blocking("first round defect")]),
          review([blocking("second round defect", "b.mjs")]),
          review([blocking("second round defect", "b.mjs")]),
        ],
        writer: [
          {
            responses: [{ id: "B1", action: "fixed", note: "round one note" }],
            summary: "r1",
          },
          {
            responses: [
              { id: "B2", action: "declined", note: "round two note" },
            ],
            summary: "r2",
          },
        ],
      }),
      checks: passingChecks,
      commit: async () => "shaX",
      diff: async () => "d",
      ctx: baseCtx(),
      log: () => {},
    });

    const all = gh._.comments.map((c) => c.body).join("\n");
    expect(all).toContain("first round defect");
    expect(all).toContain("round one note");
    expect(all).toContain("second round defect");
    expect(all).toContain("round two note");
    // Exactly one comment carries the state marker; the rest are the record.
    const markers = gh._.comments.filter((c) =>
      c.body.includes("agent-loop-state"),
    );
    expect(markers).toHaveLength(1);
  });

  it("records a session identifier for each turn, for property 5", async () => {
    const gh = fakeGitHub();
    const agent = async ({ role }) => ({
      role,
      text: JSON.stringify(
        role === "reviewer" ? review([]) : { responses: [], summary: "" },
      ),
      sessionId: `session_${role}`,
    });
    await runLoop({
      gh,
      agent,
      checks: passingChecks,
      commit: async () => null,
      diff: async () => "d",
      ctx: baseCtx(),
      log: () => {},
    });
    expect(gh._.comments.map((c) => c.body).join("\n")).toContain(
      "session_reviewer",
    );
  });
});

describe("the two fences on a Writer turn", () => {
  // Neither fence had a test before #34, which is how the contract came to be
  // editable by a Writer turn at all. They are asserted separately on purpose:
  // a later change that merged the two lists would make one abort message
  // state the wrong reason, and a single combined test would not notice.

  it("BF3 catches an edit to the machinery the orchestrator runs", () => {
    expect(forbiddenEdits(["scripts/agent/run.mjs"])).toEqual([
      "scripts/agent/run.mjs",
    ]);
    expect(forbiddenEdits([".github/workflows/agent-loop.yml"])).toEqual([
      ".github/workflows/agent-loop.yml",
    ]);
  });

  it("the owner-decision fence catches an edit to the contract", () => {
    expect(ownerDecisionEdits(["docs/contracts/mvp-v0.1.md"])).toEqual([
      "docs/contracts/mvp-v0.1.md",
    ]);
  });

  it("neither fence catches what the other one guards", () => {
    // The distinction the separation exists to keep. A contract is not BF3's
    // business (nothing executes it, no credential) and the loop's machinery
    // is not the owner-decision fence's (editing it is not an amendment).
    expect(forbiddenEdits(["docs/contracts/mvp-v0.1.md"])).toEqual([]);
    expect(ownerDecisionEdits(["scripts/agent/run.mjs"])).toEqual([]);
  });

  it("leaves an ordinary source or test edit alone", () => {
    // The condition the fences must NOT impose: fixing a finding in the code
    // under review is the Writer's whole job.
    const ordinary = [
      "src/evidence_first_rag/runtime/routes.py",
      "tests/test_routes.py",
      "README.md",
      "fixtures/source_snapshot.jsonl",
    ];
    expect(forbiddenEdits(ordinary)).toEqual([]);
    expect(ownerDecisionEdits(ordinary)).toEqual([]);
  });

  it("matches on a path prefix, not a substring", () => {
    // `docs/contracts-notes.md` is not under `docs/contracts/`. A substring
    // test would fence it, and the usual repair for that is to weaken the
    // fence.
    expect(ownerDecisionEdits(["docs/contracts-notes.md"])).toEqual([]);
    expect(forbiddenEdits(["scriptsomething/x.mjs"])).toEqual([]);
  });

  it("names the contract fence in its own list", () => {
    // If someone folds `docs/contracts/` into protectedPaths, this fails and
    // says why: the abort message would then give the credential reason for a
    // file that holds no credential.
    expect(ownerDecisionPaths).toContain("docs/contracts/");
    expect(protectedPaths).not.toContain("docs/contracts/");
  });
});
