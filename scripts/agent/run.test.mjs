import { readFileSync } from "node:fs";
import { describe, expect, it } from "./test-kit.mjs";
import {
  LABELS,
  UNPINNED_MODEL,
  agentRunner,
  assertNothingApproved,
  forbiddenEdits,
  ownerDecisionEdits,
  ownerDecisionPaths,
  parseStatusPaths,
  git,
  changedPathsOf,
  pushHead,
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

  it("reads the verdict past a quoted manifest, not the manifest as the verdict", async () => {
    // A Reviewer quotes what it reviews, and this repository is full of JSON
    // it would quote. The quoted object parses; it has no `findings`. The
    // first-parseable-object rule handed it to parseReview as the review
    // (#60). The call site now selects by shape, so the loop reads the
    // verdict that follows it and concludes on that.
    const gh = fakeGitHub();
    const reply =
      "The manifest under review:\n```\n" +
      JSON.stringify({ checks: [{ name: "whitespace" }] }) +
      "\n```\n\n" +
      JSON.stringify(review([]));
    const result = await runLoop({
      gh,
      agent: fakeAgent({ reviewer: [reply] }),
      checks: passingChecks,
      commit: async () => null,
      diff: async () => "d",
      ctx: baseCtx(),
      log: () => {},
    });
    expect(result.action).toBe(LABELS.ready.replace("agent:", ""));
    expect(gh._.labels.has(LABELS.ready)).toBe(true);
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

// #5. The three cases above pin what the guard decides. None of them pins
// WHERE it runs, and the position is the guarantee: `docs/agent-loop.md` said
// "at the end" long after #4's round-1 fixes moved it ahead of publication,
// and a guard that runs after the label has gone out reports the problem
// instead of preventing it. Nothing would have failed if it drifted back.

describe("the approve guard runs before the loop publishes anything (#5)", () => {
  const approval = () => [
    {
      state: "APPROVED",
      submitted_at: "2026-01-01T01:00:00Z",
      user: { login: "someone" },
    },
  ];

  /** A fake that records the order of the calls the conclusion is made of. */
  function recordingGitHub(options) {
    const gh = fakeGitHub(options);
    const order = [];
    const wrap = (name, fn) => async (...args) => {
      order.push(name);
      return fn(...args);
    };
    return {
      ...gh,
      order,
      listReviews: wrap("listReviews", gh.listReviews),
      createComment: wrap("createComment", gh.createComment),
      updateComment: wrap("updateComment", gh.updateComment),
      addLabels: wrap("addLabels", gh.addLabels),
    };
  }

  /**
   * An agent that records each turn into the same order array.
   *
   * Anchoring "after the agent turns" on a comment is a proxy, and O1 on #86
   * showed the proxy is loose: the round-1 review comment is the FIRST
   * `createComment`, so a guard placed just after it still looks before the
   * Writer turn and the round-2 review. Recording the turns themselves makes
   * the assertion say what it means.
   */
  const recordingAgent = (order, agent) => async (call) => {
    order.push(`agent:${call.role}`);
    return agent(call);
  };

  const conclusions = /Awaiting human merge|Stopped — a human is needed/;

  const drive = (gh, agent, commit = async () => null) =>
    runLoop({
      gh,
      agent,
      checks: passingChecks,
      commit,
      diff: async () => "d",
      ctx: baseCtx(),
      log: () => {},
    });

  it("publishes no conclusion, no verdict state and no outcome label on the ready path", async () => {
    const gh = fakeGitHub({ reviews: approval() });
    const agent = fakeAgent({ reviewer: [review([])] });
    await expect(drive(gh, agent)).rejects.toThrow(/never approve/);

    const bodies = gh._.comments.map((c) => c.body).join("\n");
    expect(bodies).not.toMatch(conclusions);
    expect(gh._.labels.has(LABELS.ready)).toBe(false);
    expect(gh._.labels.has(LABELS.needsHuman)).toBe(false);
    // The marker may exist from the review step; it must not carry the verdict.
    expect(stateOf(gh).phase).not.toBe("ready-for-human-merge");
  });

  it("does the same on the needs-human path, where the outcome is not ready", async () => {
    // The guard sits above the branch that chooses the label, so an unresolved
    // blocking finding must not publish either.
    const gh = fakeGitHub({
      pr: {
        head: { sha: "sha0", ref: "agent/1-x" },
        body: "Closes #42\n\nRisk level: `L1`",
        labels: [],
      },
      reviews: approval(),
    });
    const agent = fakeAgent({
      reviewer: [review([blocking("still broken")]), review([blocking("still broken")])],
      writer: [{ responses: [{ id: "B1", action: "declined", note: "no" }], summary: "s" }],
    });
    await expect(drive(gh, agent, async () => "sha1")).rejects.toThrow(
      /never approve/,
    );
    expect(gh._.comments.map((c) => c.body).join("\n")).not.toMatch(conclusions);
    expect(gh._.labels.has(LABELS.needsHuman)).toBe(false);
  });

  it("lists the reviews before the conclusion comment, not after it", async () => {
    // The ordering itself, rather than its consequence. On a clean run the
    // guard passes, so the only evidence of its position is when it was called.
    const gh = recordingGitHub();
    const agent = fakeAgent({ reviewer: [review([])] });
    await drive(gh, agent);

    const guard = gh.order.indexOf("listReviews");
    const label = gh.order.indexOf("addLabels", 1);
    expect(guard).toBeGreaterThan(-1);
    const conclusionComment = gh._.comments.findIndex((c) =>
      conclusions.test(c.body),
    );
    expect(conclusionComment).toBeGreaterThan(-1);
    // Every publishing call after the guard: the comment, the state write and
    // the outcome label.
    const publishing = gh.order.slice(guard + 1);
    expect(publishing).toContain("createComment");
    expect(publishing).toContain("updateComment");
    expect(publishing).toContain("addLabels");
    expect(label).toBeGreaterThan(guard);
  });

  it("lists the reviews after every agent turn, not before them", async () => {
    // The other half of the position, and the half "before publication" does
    // not imply. `assertNothingApproved` filters on `submitted_at >= since`
    // with `since = startedAt`, so the guard is bounded to what appeared
    // while the loop held the pull request. Hoisted earlier it would still be
    // "before publication" and would still throw on a pre-existing approval —
    // but an approval submitted during a Reviewer or Writer turn, which is
    // the window it exists to cover, would not yet exist when it looked.
    // Raised as N2, then narrowed by O1, on #86.
    //
    // A full two-round run, so there is a Writer turn and a second Reviewer
    // turn for the guard to be late enough for. Anchoring on the first
    // comment would pass with the guard sitting between round 1 and round 2.
    const gh = recordingGitHub();
    const agent = recordingAgent(
      gh.order,
      fakeAgent({
        reviewer: [review([blocking("first")]), review([])],
        writer: [{ responses: [{ id: "B1", action: "fixed", note: "n" }], summary: "s" }],
      }),
    );
    await drive(gh, agent, async () => "sha1");

    const turns = gh.order.filter((c) => c.startsWith("agent:"));
    expect(turns).toEqual(["agent:reviewer", "agent:writer", "agent:reviewer"]);

    const guard = gh.order.indexOf("listReviews");
    const lastTurn = gh.order.findLastIndex((c) => c.startsWith("agent:"));
    expect(guard).toBeGreaterThan(lastTurn);
  });

  it("still concludes normally when nothing approved", async () => {
    // The guard must not be satisfied by refusing everything.
    const gh = fakeGitHub({
      reviews: [{ state: "COMMENTED", submitted_at: "2026-01-01T01:00:00Z" }],
    });
    const agent = fakeAgent({ reviewer: [review([])] });
    const result = await drive(gh, agent);
    expect(result.action).toBe("ready-for-human-merge");
    expect(gh._.labels.has(LABELS.ready)).toBe(true);
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

describe("a Writer turn that edits the contract stops the run at needs-human", () => {
  // #34. The loop's Writer amended an accepted contract on #23 to authorise
  // its own branch, and reverted an authorised amendment on #32 because the
  // decision was recorded where it could not see it. Both are refused here.
  //
  // #82 changed how that refusal is *reported*, not whether it happens. It
  // used to throw, and a throw is labelled `agent:failed` — a crash. Now the
  // run concludes `agent:needs-human`, which is what `docs/agent-loop.md`
  // always said a contract-only pull request ends at. The two properties #34
  // established are unchanged and are what these assert: the Writer's edit
  // does not land, and the reason given is the recorded-decision one rather
  // than BF3's credential wording.
  function driveTouching(path) {
    const gh = fakeGitHub();
    const commits = [];
    const result = runLoop({
      gh,
      agent: fakeAgent({
        reviewer: [review([blocking("one")])],
        writer: [{ responses: [], summary: "r1" }],
      }),
      checks: passingChecks,
      commit: async (message) => {
        commits.push(message);
        return "sha1";
      },
      diff: async () => "d",
      changedPaths: async () => [path],
      ctx: baseCtx(),
      log: () => {},
    });
    return { gh, commits, result };
  }

  it.each([
    ["docs/contracts/mvp-v0.1.md"],
    ["docs/contracts/README.md"],
  ])("refuses an edit to %s", async (path) => {
    const { commits, result } = driveTouching(path);
    const concluded = await result;
    // Refused: the edit is discarded rather than committed or pushed. This is
    // the assertion that carries #34's guarantee across #82's change.
    expect(commits).toEqual([]);
    expect(concluded.action).toBe("needs-human");
    expect(concluded.reason).toMatch(/recorded human decision/);
  });

  it("does not report the contract under BF3's credential wording", async () => {
    // The reason the two fences are separate lists. Reported under BF3 this
    // would tell a reader the contract is fenced to stop an agent borrowing
    // the orchestrator's privileges, which is not true of a document nothing
    // executes.
    const { gh, result } = driveTouching("docs/contracts/mvp-v0.1.md");
    const concluded = await result;
    expect(concluded.reason).toMatch(/not a review-finding fix/);
    const all = gh._.comments.map((c) => c.body).join("\n");
    expect(all).not.toContain("protected paths");
    expect(all).not.toContain("privileges the agents do not hold");
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

  // #30. The merged reviews on #18 and #24 name no model, so they cannot be
  // compared against a later one. Property 5 records the turn's identity, and
  // the model is half of it.
  it("names the model beside the session id in both published comments", async () => {
    const gh = fakeGitHub();
    const agent = async ({ role }) => ({
      role,
      text: JSON.stringify(
        role === "reviewer"
          ? review([blocking("something")])
          : { responses: [{ id: "B1", action: "fixed", note: "done" }], summary: "fixed" },
      ),
      sessionId: `session_${role}`,
      model: `model_${role}`,
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
    const all = gh._.comments.map((c) => c.body).join("\n");
    expect(all).toContain("Reviewer model: `model_reviewer` · session: `session_reviewer`");
    expect(all).toContain("Writer model: `model_writer` · session: `session_writer`");
  });

  it("says the model was not reported rather than naming an empty one", async () => {
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
    const all = gh._.comments.map((c) => c.body).join("\n");
    expect(all).toContain("Reviewer model: `not reported`");
    expect(all).not.toContain("Reviewer model: ``");
  });
});

// `main()` is the one function here that is never executed by a test: it opens
// a worktree, spawns the CLI and holds the token. #30 answered that by moving
// the model resolution into `agentRunner`, and #113 N3 moved the CI bound into
// `ciRunner` for the same reason — but a factory only helps if `main()` calls
// it, and a mutation that inlined the raw dependency again failed nothing.
//
// This is a text assertion about wiring, not a behavioural one. It cannot say
// the arguments are right; the describes below do that. It says only that the
// covered path is the one `main()` takes, which is the half no other test sees.
// `workflow.test.mjs` reads module source the same way and for the same reason.

describe("main() wires the covered factories rather than inlining them", () => {
  const source = readFileSync("scripts/agent/run.mjs", "utf8");
  const mainBody = source.slice(source.indexOf("\nasync function main("));

  it("takes its agent through agentRunner (#30)", () => {
    expect(mainBody).toMatch(/agent: agentRunner\(/);
  });

  it("takes its CI verdict through ciRunner, which carries the budget (#113 N3)", () => {
    expect(mainBody).toMatch(/ci: ciRunner\(/);
    // The bound has to reach it: `ciRunner` needs a start time to compute one.
    expect(mainBody).toMatch(/ci: ciRunner\(\{[^}]*startedAt/);
  });

  it("budgets that verdict from the job's start, not this process's (#113 N8)", () => {
    // `startedAt` is `new Date()` inside `main()`, which is minutes after the
    // job began. The ceiling the budget subtracts from is the job's, so the
    // wiring has to prefer the recorded job start and fall back only when it
    // is absent — outside Actions, where there is no job.
    expect(mainBody).toMatch(
      /ci: ciRunner\(\{[^}]*startedAt: process\.env\.CI_AGENT_JOB_STARTED_AT \|\| startedAt/,
    );
    // Only the CI budget switches. `startedAt` itself is unchanged and still
    // reaches `runLoop`, where `assertNothingApproved` uses it — that is about
    // when the loop took custody, not about the job's budget.
    expect(mainBody).toMatch(/startedAt,\s*\n?\s*(reset|runUrl|prNumber)/);
  });
});

describe("agentRunner resolves the model per role and publishes what it asked for", () => {
  // `main()` is wiring and is otherwise uncovered, which is how CI_AGENT_MODEL
  // came to be read and never set. This is the seam: the model handed to the
  // CLI and the model published beside the session id are the same value, and
  // it comes from the environment rather than from a constant.
  const spy = () => {
    const seen = [];
    const run = async (args) => {
      seen.push(args);
      return { role: args.role, text: "{}", sessionId: "s1" };
    };
    return { seen, run };
  };

  it("hands the CLI the per-role model from the environment", async () => {
    const { seen, run } = spy();
    const agent = agentRunner({
      timeoutMs: 1,
      cwd: "/w",
      settingsPath: "/s.json",
      env: {
        CI_AGENT_WRITER_MODEL: "writer-model",
        CI_AGENT_REVIEWER_MODEL: "reviewer-model",
      },
      run,
    });
    await agent({ role: "reviewer", prompt: "p" });
    await agent({ role: "writer", prompt: "p" });
    expect(seen.map((a) => a.model)).toEqual(["reviewer-model", "writer-model"]);
    // The rest of the turn's configuration still reaches the CLI.
    expect(seen[0]).toMatchObject({ timeoutMs: 1, cwd: "/w", settingsPath: "/s.json" });
  });

  it("publishes the same model it asked for", async () => {
    const { run } = spy();
    const agent = agentRunner({
      env: { CI_AGENT_MODEL: "shared-model" },
      run,
    });
    const result = await agent({ role: "reviewer", prompt: "p" });
    expect(result.model).toBe("shared-model");
  });

  it("omits the flag and publishes UNPINNED_MODEL when nothing is set", async () => {
    // `--model ""` is an argument the CLI has to interpret; undefined makes
    // `claude.mjs` leave the flag off entirely.
    const { seen, run } = spy();
    const agent = agentRunner({ env: {}, run });
    const result = await agent({ role: "writer", prompt: "p" });
    expect(seen[0].model).toBe(undefined);
    expect(result.model).toBe(UNPINNED_MODEL);
  });
});

// #82. BF7 is reached by a contract-only pull request doing exactly what it is
// supposed to do, so it is a designed terminus. It used to throw, and every
// throw is labelled `agent:failed` by `main()` — the loop's word for a crash,
// and the one #68's queue teaches the owner to restart. Restarting this case
// aborts identically every time. What must NOT change is the part of BF7 that
// matters: the fenced edit is still discarded rather than committed.

describe("BF7's terminus is a conclusion, not a crash (#82)", () => {
  const writerReply = {
    responses: [{ id: "B1", action: "fixed", note: "amended Section 4.2" }],
    summary: "amended the contract",
  };

  /** Drive a full fix round where the Writer's edits land on `paths`. */
  function driveWithWriterTouching(paths, options = {}) {
    const gh = fakeGitHub(options.gh);
    const commits = [];
    const result = runLoop({
      gh,
      agent: fakeAgent({
        reviewer: [review([blocking("Section 4.2 is ambiguous", "docs/contracts/mvp-v0.1.md")])],
        writer: [writerReply],
      }),
      checks: passingChecks,
      commit: async (message) => {
        commits.push(message);
        return "sha1";
      },
      diff: async () => "d",
      changedPaths: async () => paths,
      ctx: baseCtx(),
      log: () => {},
    });
    return { gh, commits, result };
  }

  const contractEdit = ["docs/contracts/mvp-v0.1.md"];

  it("concludes needs-human instead of throwing", async () => {
    const { gh, result } = driveWithWriterTouching(contractEdit);
    const concluded = await result;
    expect(concluded.action).toBe("needs-human");
    expect(gh._.labels.has(LABELS.needsHuman)).toBe(true);
    expect(gh._.labels.has(LABELS.ready)).toBe(false);
    // `agent:failed` is main()'s, and main() is only reached by a throw.
    expect(gh._.labels.has(LABELS.failed)).toBe(false);
  });

  it("commits nothing, so the fenced edit is discarded rather than published", async () => {
    // The half of BF7 that must survive the change. A conclusion that shipped
    // the Writer's contract edit would be worse than the crash it replaces.
    const { commits, result } = driveWithWriterTouching(contractEdit);
    await result;
    expect(commits).toEqual([]);
  });

  it("names the fence, the path, and that nothing was committed", async () => {
    const { gh, result } = driveWithWriterTouching(contractEdit);
    await result;
    const all = gh._.comments.map((c) => c.body).join("\n");
    expect(all).toContain("docs/contracts/mvp-v0.1.md");
    expect(all).toContain("owner-decision fence");
    expect(all).toMatch(/Section 10/);
    expect(all).toMatch(/nothing from that Writer turn was committed or pushed/);
    expect(all).toMatch(/not a failed run/);
  });

  it("makes no run-wide claim that nothing was committed (#92 N6)", async () => {
    // The conclusion and the proposal comment are what the owner reads. An
    // unqualified "nothing was committed or pushed" is false on a run whose
    // earlier round pushed an ordinary fix, and "contract-only" is not
    // something the loop determines — the fence fires on any Writer turn that
    // reaches `docs/contracts/`.
    const { gh, result } = driveWithWriterTouching(contractEdit);
    await result;
    const published = gh._.comments.map((c) => c.body).join("\n");
    expect(published).not.toContain("nothing was committed or pushed");
    expect(published).not.toContain("designed outcome for a contract-only change");
  });

  it("publishes the standing findings with the conclusion", async () => {
    // #82: a needs-human on a contract is exactly the moment the owner needs
    // the findings in one place rather than scrolling for them.
    const { gh, result } = driveWithWriterTouching(contractEdit);
    await result;
    const conclusion = gh._.comments
      .map((c) => c.body)
      .find((b) => b.includes("Stopped — a human is needed"));
    expect(conclusion).toContain("Section 4.2 is ambiguous");
  });

  it("records needs-human in the state marker, not a mid-run phase", async () => {
    const { gh, result } = driveWithWriterTouching(contractEdit);
    await result;
    expect(stateOf(gh).phase).toBe("needs-human");
  });

  it("runs the approve guard before concluding, like any other conclusion", async () => {
    // The conclusion path is shared, so #5's guard covers this terminus too.
    const { result } = driveWithWriterTouching(contractEdit, {
      gh: {
        reviews: [
          {
            state: "APPROVED",
            submitted_at: "2026-01-01T01:00:00Z",
            user: { login: "someone" },
          },
        ],
      },
    });
    await expect(result).rejects.toThrow(/never approve/);
  });

  it("publishes what the Writer proposed, marked as discarded", async () => {
    // N2 on #92. The proposal is the input to the decision the fence reserves
    // for the owner. Without it the record says an edit was attempted and
    // never what it was.
    const { gh, result } = driveWithWriterTouching(contractEdit);
    await result;
    const proposal = gh._.comments
      .map((c) => c.body)
      .find((b) => b.includes("Writer proposal"));
    expect(proposal).not.toBeUndefined();
    expect(proposal).toContain("discarded at the owner-decision fence");
    expect(proposal).toContain("nothing from this turn was committed or pushed");
    expect(proposal).toContain("amended the contract");
    expect(proposal).toContain("amended Section 4.2");
    expect(proposal).toContain("docs/contracts/mvp-v0.1.md");
  });

  it("does not present the discarded proposal as a change to the branch", async () => {
    // The risk in publishing it at all: a reader taking the proposal for an
    // applied edit. The heading and the body both have to say otherwise.
    const { gh, result } = driveWithWriterTouching(contractEdit);
    await result;
    const proposal = gh._.comments
      .map((c) => c.body)
      .find((b) => b.includes("Writer proposal"));
    expect(proposal).toContain("it is not a change to the branch");
    expect(proposal).not.toContain("Writer response — round");
  });

  it("still throws on a BF3 edit, so a reach for the machinery reads as a crash", async () => {
    // The other fence keeps its behaviour. A Writer editing the orchestrator
    // is not a designed terminus and must not be labelled as one.
    const { result } = driveWithWriterTouching(["scripts/agent/run.mjs"]);
    await expect(result).rejects.toThrow(/protected paths/);
  });

  it("throws on a BF3 edit even when a contract edit is present too", async () => {
    // Order matters: the credential fence is checked first and wins, because
    // the machinery reach is the more serious of the two.
    const { result } = driveWithWriterTouching([
      "docs/contracts/mvp-v0.1.md",
      "scripts/agent/run.mjs",
    ]);
    await expect(result).rejects.toThrow(/protected paths/);
  });
});

// #21. The Writer's push raises no workflow, so CI never ran on the head the
// loop labelled. These assert at the loop level what checks.test.mjs asserts
// at the helper level: a red CI on a loop-pushed head cannot reach `ready`.

describe("CI on a loop-pushed head gates the verdict (#21)", () => {
  const driveWithCi = (ci) => {
    const gh = fakeGitHub();
    const seen = [];
    const result = runLoop({
      gh,
      agent: fakeAgent({
        reviewer: [review([blocking("one")]), review([])],
        writer: [{ responses: [{ id: "B1", action: "fixed" }], summary: "r1" }],
      }),
      checks: passingChecks,
      commit: async () => "pushedsha",
      diff: async () => "d",
      changedPaths: async () => ["src/x.py"],
      ci: async (args) => {
        seen.push(args);
        return ci;
      },
      ctx: baseCtx(),
      log: () => {},
    });
    return { gh, seen, result };
  };

  const green = { ok: true, conclusion: "success", url: null, summary: "- ci: success" };
  const red = { ok: false, conclusion: "failure", url: null, summary: "- ci: **failure**" };

  it("concludes ready when the loop's checks and CI both pass", async () => {
    const { gh, result } = driveWithCi(green);
    const r = await result;
    expect(r.action).toBe("ready-for-human-merge");
    expect(gh._.labels.has(LABELS.ready)).toBe(true);
  });

  it("refuses ready when CI failed, even though every manifest check passed", async () => {
    // The defect: `passingChecks` is green throughout, and before #21 that was
    // the whole verdict. Head 03ba0c4 on #18 was labelled ready in this state.
    const { gh, result } = driveWithCi(red);
    const r = await result;
    expect(r.action).toBe("needs-human");
    expect(gh._.labels.has(LABELS.ready)).toBe(false);
    expect(gh._.labels.has(LABELS.needsHuman)).toBe(true);
  });

  it("asks for CI on the head the push created, not the head it started from", async () => {
    const { seen, result } = driveWithCi(green);
    await result;
    const heads = seen.map((s) => s.headSha);
    expect(heads).toContain("pushedsha");
    expect(seen.every((s) => s.branch === "agent/1-x")).toBe(true);
  });

  it("asks once per head, not once per verdict (#113 B2)", async () => {
    // CI's conclusion on a commit is a fixed fact once it completes, and the
    // wait is minutes. Re-asking for the same head would re-spend it for the
    // same answer.
    const { seen, result } = driveWithCi(green);
    await result;
    const heads = seen.map((s) => s.headSha);
    expect(heads.length).toBe(new Set(heads).size);
  });

  it("publishes the CI verdict where the owner reads it", async () => {
    const { gh, result } = driveWithCi(red);
    await result;
    const all = gh._.comments.map((c) => c.body).join("\n");
    expect(all).toContain("- ci: **failure**");
    expect(all).toMatch(/CI on the head this run is concluding on/);
    // N4 on #113. After B2 most verdicts are taken on heads this run did not
    // push — a fresh pull request's opening review, a resumed `check`, a Writer
    // turn that committed nothing. Claiming a push tells the owner the loop
    // created the commit CI ran on, and on a resumed run that head is theirs.
    expect(all).not.toMatch(/CI on the head this run pushed/);
  });

  it("still takes a CI verdict when the Writer pushed nothing (#113 B2)", async () => {
    // This used to be gated on there being a new head, on the reasoning that
    // an unmoved head already carries whatever CI the human's push produced.
    // The reasoning was right and the gate was still wrong: the run concludes
    // on that head either way, so the verdict has to be taken there too — and
    // asking is now cheap, because `awaitCiOnHead` looks before it dispatches
    // and starts nothing when a run already exists.
    const gh = fakeGitHub();
    const seen = [];
    const concluded = await runLoop({
      gh,
      agent: fakeAgent({
        reviewer: [review([blocking("one")]), review([])],
        writer: [{ responses: [{ id: "B1", action: "declined" }], summary: "r1" }],
      }),
      checks: passingChecks,
      commit: async () => null,
      diff: async () => "d",
      changedPaths: async () => [],
      ci: async (args) => {
        seen.push(args);
        return red;
      },
      ctx: baseCtx(),
      log: () => {},
    });
    expect(seen.length > 0).toBe(true);
    expect(concluded.action).toBe("needs-human");
  });

  it("refuses ready on a resumed run whose review path never saw CI (#113 B2)", async () => {
    // The hole B2 named. Round 1 pushes H1 and is cut off during the CI wait,
    // so the marker still records the pre-fix head and `phase: review`. The
    // next run finds the review stale, re-reviews H1 through the review path —
    // which used to take no CI verdict at all — and a clean review concluded
    // `ready` over a head no CI had ever seen. That is exactly the defect #21
    // exists to remove, reached by a different route.
    const gh = fakeGitHub();
    const seen = [];
    const concluded = await runLoop({
      gh,
      agent: fakeAgent({ reviewer: [review([])], writer: [] }),
      checks: passingChecks,
      commit: async () => null,
      diff: async () => "d",
      changedPaths: async () => [],
      ci: async (args) => {
        seen.push(args);
        return red;
      },
      ctx: baseCtx(),
      log: () => {},
    });
    // No fix round ran at all: the verdict came from the review path.
    expect(seen.length > 0).toBe(true);
    expect(concluded.action).toBe("needs-human");
    const all = gh._.comments.map((c) => c.body).join("\n");
    expect(all).toContain("- ci: **failure**");
  });

  it("folds CI into the `check` path too, so a resumed clean review is gated (#113 B2)", async () => {
    // The third route to a conclusion, and the one #76 already caught once for
    // the manifest checks: a clean review recorded at an unchanged head resumes
    // with no `review` step at all, so `nextStep` asks for a bare `check`. If
    // that path takes no CI verdict, a red CI on the head being labelled is
    // invisible — the same hole as the review path, one branch over.
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
    const seen = [];
    const concluded = await runLoop({
      gh,
      agent: fakeAgent({}),
      checks: passingChecks,
      commit: async () => null,
      diff: async () => "d",
      ci: async (args) => {
        seen.push(args);
        return red;
      },
      ctx: baseCtx(),
      log: () => {},
    });
    expect(seen.map((x) => x.headSha)).toEqual(["shaSAME"]);
    expect(concluded.action).toBe("needs-human");
    expect(gh._.labels.has(LABELS.ready)).toBe(false);
  });

  it("concludes without a verdict line when no checks ran at all (#113 N6)", async () => {
    // The guard on the new summary line is load-bearing, and the path that
    // needs it is reachable: a resumed run already at its round cap with
    // blocking findings standing at the same head concludes straight from
    // `nextStep` — `blocking.length === 0` is false, so the branch that would
    // have run the checks is never entered and `checkResult` is still null.
    // Interpolating it unguarded would crash the one comment that tells the
    // owner why the loop stopped.
    const spent = {
      round: 2,
      phase: "review",
      headSha: "shaSAME",
      riskLevel: "L2",
      issueNumber: 42,
      registry: {},
      lastReview: { summary: "one left", findings: [blocking("still broken")] },
      checksOk: true,
      runId: null,
      updatedAt: null,
    };
    const gh = fakeGitHub({
      comments: [{ id: 7, body: renderStatusComment(spent) }],
    });
    gh._.pr.head.sha = "shaSAME";
    let checksRan = 0;
    const concluded = await runLoop({
      gh,
      agent: fakeAgent({}),
      checks: async () => {
        checksRan += 1;
        return { ok: true, summary: "All checks passed." };
      },
      commit: async () => null,
      diff: async () => "d",
      ctx: baseCtx(),
      log: () => {},
    });
    expect(checksRan).toBe(0);
    expect(concluded.action).toBe("needs-human");
    const conclusion = gh._.comments
      .map((c) => c.body)
      .find((b) => b.includes("Stopped — a human is needed"));
    expect(conclusion).not.toBeUndefined();
    expect(conclusion).toContain("still broken");
  });

  it("publishes the CI verdict from the conclusion on the `check` path (#113 N6)", async () => {
    // That path posts no review and no Writer response, so the conclusion is
    // its only comment. Before this it carried `concluded.reason` alone — "the
    // repository checks are failing" — which does not say the failure was CI
    // rather than the manifest, does not distinguish a red build from a
    // timeout, and carries no run URL.
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
    await runLoop({
      gh,
      agent: fakeAgent({}),
      checks: passingChecks,
      commit: async () => null,
      diff: async () => "d",
      ci: async () => ({
        ok: false,
        conclusion: "timed_out",
        url: "https://example/run/9",
        summary: "- `repository-checks` on `shaSAME`: no run appeared on this head",
      }),
      ctx: baseCtx(),
      log: () => {},
    });
    const conclusion = gh._.comments
      .map((c) => c.body)
      .find((b) => b.includes("Stopped — a human is needed"));
    expect(conclusion).not.toBeUndefined();
    expect(conclusion).toContain("no run appeared on this head");
    // No review or Writer comment exists to carry it instead.
    // No review or Writer comment exists to carry it instead. Matched on the
    // heading, not the body: the state marker's own text mentions Writer
    // responses, and a looser filter picks it up.
    const headings = gh._.comments.map((c) => c.body.split("\n")[0]);
    expect(headings).toEqual(["## Agent loop state", "## Stopped — a human is needed"]);
  });

  it("asks CI once for a head reached by two different paths (#113 B2)", async () => {
    // The memo has to key on the head, not on the call site. A Writer turn
    // that pushes nothing leaves the head unmoved, so the fix path and the
    // review path that follows it both conclude on the same commit — and the
    // CI wait is minutes, so asking twice spends it twice for one fact.
    const gh = fakeGitHub();
    const seen = [];
    await runLoop({
      gh,
      agent: fakeAgent({
        reviewer: [review([blocking("one")]), review([])],
        writer: [{ responses: [{ id: "B1", action: "declined" }], summary: "r1" }],
      }),
      checks: passingChecks,
      commit: async () => null,
      diff: async () => "d",
      changedPaths: async () => [],
      ci: async (args) => {
        seen.push(args);
        return green;
      },
      ctx: baseCtx(),
      log: () => {},
    });
    const heads = seen.map((x) => x.headSha);
    expect(heads.length).toBe(new Set(heads).size);
  });

  it("concludes ready through the review path when CI on that head is green", async () => {
    // The other half: the new fold must not turn every clean review into
    // needs-human.
    const gh = fakeGitHub();
    const concluded = await runLoop({
      gh,
      agent: fakeAgent({ reviewer: [review([])], writer: [] }),
      checks: passingChecks,
      commit: async () => null,
      diff: async () => "d",
      changedPaths: async () => [],
      ci: async () => green,
      ctx: baseCtx(),
      log: () => {},
    });
    expect(concluded.action).toBe("ready-for-human-merge");
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

describe("parsing the paths a Writer turn changed", () => {
  // Every other test in this file stubs `changedPaths`, so until an external
  // review probed it the parsing itself had never been run by a test -- which
  // is how a fence that missed quoted paths survived three slices.
  it("returns a plain path without its status prefix", () => {
    expect(parseStatusPaths("?? src/a.py\0 M docs/b.md\0")).toEqual([
      "src/a.py",
      "docs/b.md",
    ]);
  });

  it("still sees a path that porcelain mode would have quoted", () => {
    // The finding. Without `-z`, git renders these as
    // `"docs/contracts/mvp v2.md"`, and the leading quote makes
    // startsWith("docs/contracts/") false, so the fence waved them through.
    const paths = parseStatusPaths(
      "?? docs/contracts/mvp.md\0?? docs/contracts/mvp v2.md\0?? docs/contracts/\u5951\u7d04.md\0",
    );
    expect(paths).toEqual([
      "docs/contracts/mvp.md",
      "docs/contracts/mvp v2.md",
      "docs/contracts/\u5951\u7d04.md",
    ]);
    expect(ownerDecisionEdits(paths).length).toBe(3);
  });

  it("returns both halves of a rename", () => {
    // A rename out of a fenced directory is as much an edit of it as a rename
    // in, and the source path is a separate NUL-terminated field.
    const paths = parseStatusPaths("R  src/new.py\0docs/contracts/old.md\0");
    expect(paths).toEqual(["src/new.py", "docs/contracts/old.md"]);
    expect(ownerDecisionEdits(paths)).toEqual(["docs/contracts/old.md"]);
  });

  it("treats empty output as no paths", () => {
    for (const empty of ["", "\0", null, undefined]) {
      expect(parseStatusPaths(empty)).toEqual([]);
    }
  });

  it("returns both halves of a rename git saw only in the worktree", () => {
    // ` R` -- the marker in the SECOND column. This is what an unstaged `mv`
    // reports, and it is the default: status.renames follows diff.renames.
    // Checking field[0] alone left the source field unconsumed, so the next
    // iteration sliced three bytes off it and the fence compared against
    // "s/contracts/old.md".
    const paths = parseStatusPaths(" R src/new.py\0docs/contracts/old.md\0");
    expect(paths).toEqual(["src/new.py", "docs/contracts/old.md"]);
    expect(ownerDecisionEdits(paths)).toEqual(["docs/contracts/old.md"]);
  });

  it("returns both halves of a copy in either status column", () => {
    for (const marker of ["C ", " C"]) {
      const paths = parseStatusPaths(`${marker} src/new.py\0.github/old.yml\0`);
      expect(paths).toEqual(["src/new.py", ".github/old.yml"]);
      expect(forbiddenEdits(paths)).toEqual([".github/old.yml"]);
    }
  });

  // A fake child: stdout arrives, then close. Registration order in git()
  // (data handler first) makes the queued microtasks fire in that order.
  const childWith = (stdout, code = 0, stderr = "") => ({
    stdout: { on: (ev, h) => ev === "data" && queueMicrotask(() => h(stdout)) },
    stderr: { on: (ev, h) => ev === "data" && stderr && queueMicrotask(() => h(stderr)) },
    on: (ev, h) => ev === "close" && queueMicrotask(() => h(code)),
  });

  it("git() trims by default and leaves the bytes alone with raw: true", async () => {
    const out = " M .github/workflows/ci.yml\0";
    const spawnFn = () => childWith(out);
    expect(await git(["status"], ".", { spawnFn })).toBe(out.trim());
    expect(await git(["status"], ".", { raw: true, spawnFn })).toBe(out);
  });

  it("git() rejects with stderr on a nonzero exit", async () => {
    const spawnFn = () => childWith("", 128, "fatal: not a git repository");
    await expect(git(["status"], ".", { spawnFn })).rejects.toThrow("not a git repository");
  });

  it("changedPathsOf asks for -z, raw, and hands the parser the leading space", async () => {
    // The composition the round-3 review asked to see tested. Drop either
    // half -- the -z, or raw: true -- and the first path is mangled.
    const seen = [];
    const gitFn = async (args, cwd, opts) => {
      seen.push({ args, cwd, opts });
      return " M .github/workflows/ci.yml\0?? docs/contracts/mvp.md\0";
    };
    const paths = await changedPathsOf(gitFn, "/wt");
    expect(seen).toEqual([
      { args: ["status", "--porcelain", "-z"], cwd: "/wt", opts: { raw: true } },
    ]);
    expect(paths).toEqual([".github/workflows/ci.yml", "docs/contracts/mvp.md"]);
    expect(forbiddenEdits(paths)).toEqual([".github/workflows/ci.yml"]);
    expect(ownerDecisionEdits(paths)).toEqual(["docs/contracts/mvp.md"]);
  });

  it("changedPathsOf through the real git() sees the leading space end to end", async () => {
    const out = " M .github/workflows/ci.yml\0";
    const spawnFn = () => childWith(out);
    const paths = await changedPathsOf(
      (args, cwd, opts) => git(args, cwd, { ...opts, spawnFn }),
      ".",
    );
    expect(forbiddenEdits(paths)).toEqual([".github/workflows/ci.yml"]);
  });

  it("pushHead routes the token through env, and the old positional shape lost it", async () => {
    // The round-1 review of #49: git() now takes one options object, and the
    // push call was still passing an env-shaped bag positionally. Assert the
    // token reaches the spawned process, and show the shape that dropped it.
    const seen = [];
    const spawnFn = (_cmd, args, options) => {
      seen.push({ args, env: options.env });
      return childWith("");
    };
    const wrap = (args, cwd, opts) => git(args, cwd, { ...opts, spawnFn });

    await pushHead(wrap, {
      worktree: "/wt",
      owner: "o",
      repo: "r",
      branch: "b",
      token: "tok-secret",
    });
    expect(seen.length).toBe(1);
    expect(seen[0].env.GH_PUSH_TOKEN).toBe("tok-secret");
    expect(seen[0].args.some((a) => a.includes("tok-secret"))).toBe(false);
    expect(seen[0].args).toContain("HEAD:b");
    expect(seen[0].args).toContain("https://github.com/o/r");

    // What the fixed signature does with the OLD call shape: the bag is read
    // as options, `env` is undefined, and the token is gone.
    seen.length = 0;
    await git(["push"], "/wt", { ...process.env, GH_PUSH_TOKEN: "tok-secret", spawnFn });
    expect(seen[0].env.GH_PUSH_TOKEN).toBe(undefined);
  });

  it("keeps the leading status space, which a trimmed stdout would eat", () => {
    // git() resolves out.trim() by default. A worktree-only modification is
    // ` M path\0`, so when it sorts first the whole stdout begins with a
    // space; trimming it makes slice(3) cut one byte into the path and
    // ".github/workflows/ci.yml" arrives as "github/workflows/ci.yml", which
    // under() no longer matches. The call site passes raw: true; this asserts
    // what the parser is owed.
    const raw = " M .github/workflows/ci.yml\0?? docs/contracts/mvp.md\0";
    expect(parseStatusPaths(raw)).toEqual([
      ".github/workflows/ci.yml",
      "docs/contracts/mvp.md",
    ]);
    expect(forbiddenEdits(parseStatusPaths(raw))).toEqual([
      ".github/workflows/ci.yml",
    ]);
    // And the failure the fence suffered when that space was trimmed away.
    expect(forbiddenEdits(parseStatusPaths(raw.trim()))).toEqual([]);
  });

  it("keeps a path containing a newline in one piece", () => {
    // The other reason `-z` matters: splitting on "\n" would cut this in two
    // and the fence would compare against two halves of a name.
    expect(parseStatusPaths("?? scripts/we\nird.mjs\0")).toEqual([
      "scripts/we\nird.mjs",
    ]);
  });
});
