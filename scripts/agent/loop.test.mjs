import { describe, expect, it } from "./test-kit.mjs";
import { ACTIONS, nextStep, roundCapFor } from "./loop.mjs";

const HEAD = "aaaaaaa";

/** A review with the given blocking count and nothing else. */
function review(blockingCount, extra = []) {
  return {
    findings: [
      ...Array.from({ length: blockingCount }, (_, i) => ({
        id: `B${i + 1}`,
        severity: "blocking",
        summary: `blocking ${i + 1}`,
      })),
      ...extra,
    ],
  };
}

describe("roundCapFor", () => {
  it("matches workflow section 6: L0 none, L1 one, L2 two", () => {
    expect(roundCapFor("L0")).toBe(0);
    expect(roundCapFor("L1")).toBe(1);
    expect(roundCapFor("L2")).toBe(2);
  });

  it("is case insensitive, because the level is read from prose", () => {
    expect(roundCapFor("l1")).toBe(1);
  });

  it("raises an unrecognised level to the L2 cap, per section 4", () => {
    // Guessing low would spend a round trip the Issue never authorised.
    expect(roundCapFor(undefined)).toBe(2);
    expect(roundCapFor("")).toBe(2);
    expect(roundCapFor("L7")).toBe(2);
  });
});

describe("nextStep", () => {
  it("takes no review at all on L0", () => {
    const step = nextStep({ riskLevel: "L0", headSha: HEAD });
    expect(step.action).toBe(ACTIONS.skipL0);
  });

  it("reviews first when nothing is recorded", () => {
    const step = nextStep({ riskLevel: "L2", headSha: HEAD });
    expect(step.action).toBe(ACTIONS.review);
  });

  it("concludes ready when a review found nothing blocking and checks pass", () => {
    const step = nextStep({
      riskLevel: "L2",
      lastReview: review(0, [
        { id: "N1", severity: "non-blocking", summary: "nit" },
      ]),
      checks: { ok: true },
      headSha: HEAD,
      stateHeadSha: HEAD,
    });
    expect(step.action).toBe(ACTIONS.ready);
  });

  it("refuses to call a red build ready, even with no blocking findings", () => {
    // A clean review over failing checks is not a mergeable state, and saying
    // it is would be the loop's worst possible failure.
    const step = nextStep({
      riskLevel: "L2",
      lastReview: review(0),
      checks: { ok: false },
      headSha: HEAD,
      stateHeadSha: HEAD,
    });
    expect(step.action).toBe(ACTIONS.needsHuman);
  });

  // #76 R1. `ready` needs a positive verdict, not the absence of a negative
  // one. A run that resumes on a recorded clean review at an unchanged head
  // never executes a `review` step, so nothing runs the checks — and this
  // used to fall through to `ready` reporting "the checks pass".
  it("asks for the checks rather than concluding when they have not run", () => {
    const step = nextStep({
      riskLevel: "L2",
      lastReview: review(0),
      checks: null,
      headSha: HEAD,
      stateHeadSha: HEAD,
      phase: ACTIONS.review,
    });
    expect(step.action).toBe(ACTIONS.check);
    expect(step.action).not.toBe(ACTIONS.ready);
    expect(step.reason).toMatch(/have not run/);
  });

  it("never reports that the checks pass without a verdict", () => {
    // The reason string is the thing a human reads off the pull request, so
    // it is asserted directly: no path may claim a pass that did not happen.
    for (const checks of [null, undefined]) {
      const step = nextStep({
        riskLevel: "L2",
        lastReview: review(0),
        checks,
        headSha: HEAD,
        stateHeadSha: HEAD,
      });
      expect(step.action).not.toBe(ACTIONS.ready);
      expect(step.reason).not.toMatch(/checks pass/);
    }
  });

  it("sends blocking findings to the Writer while rounds remain", () => {
    const step = nextStep({
      riskLevel: "L2",
      round: 0,
      lastReview: review(2),
      checks: { ok: true },
      headSha: HEAD,
      stateHeadSha: HEAD,
    });
    expect(step.action).toBe(ACTIONS.fix);
    expect(step.reason).toContain("round 1 of 2");
  });

  describe("the round cap is the stop condition", () => {
    it("stops L1 after one round", () => {
      const step = nextStep({
        riskLevel: "L1",
        round: 1,
        lastReview: review(1),
        checks: { ok: true },
        headSha: HEAD,
        stateHeadSha: HEAD,
      });
      expect(step.action).toBe(ACTIONS.needsHuman);
    });

    it("allows a second round on L2 and stops after it", () => {
      const base = {
        riskLevel: "L2",
        lastReview: review(1),
        checks: { ok: true },
        headSha: HEAD,
        stateHeadSha: HEAD,
      };
      expect(nextStep({ ...base, round: 1 }).action).toBe(ACTIONS.fix);
      expect(nextStep({ ...base, round: 2 }).action).toBe(ACTIONS.needsHuman);
    });

    it("never exceeds the cap however many rounds are already recorded", () => {
      for (const round of [2, 3, 99]) {
        expect(
          nextStep({
            riskLevel: "L2",
            round,
            lastReview: review(1),
            headSha: HEAD,
            stateHeadSha: HEAD,
          }).action,
        ).toBe(ACTIONS.needsHuman);
      }
    });
  });

  describe("idempotency", () => {
    it("skips a re-run against a head it already concluded", () => {
      for (const phase of [ACTIONS.ready, ACTIONS.needsHuman]) {
        const step = nextStep({
          riskLevel: "L2",
          phase,
          headSha: HEAD,
          stateHeadSha: HEAD,
          lastReview: review(0),
        });
        expect(step.action).toBe(ACTIONS.skip);
      }
    });

    it("does not skip when the head moved after concluding", () => {
      const step = nextStep({
        riskLevel: "L2",
        phase: ACTIONS.ready,
        headSha: "bbbbbbb",
        stateHeadSha: HEAD,
        lastReview: review(0),
      });
      expect(step.action).toBe(ACTIONS.review);
    });
  });

  describe("a moved head invalidates the recorded review", () => {
    it("re-reviews rather than trusting a review of different code", () => {
      const step = nextStep({
        riskLevel: "L2",
        round: 1,
        lastReview: review(0),
        headSha: "bbbbbbb",
        stateHeadSha: HEAD,
      });
      expect(step.action).toBe(ACTIONS.review);
      expect(step.reason).toContain("Head moved");
    });

    it("does not refund the round count, so a push cannot buy more rounds", () => {
      // The cap is per pull request. If pushing reset it, the loop would be
      // unbounded by construction, which is what section 6 forbids.
      const step = nextStep({
        riskLevel: "L2",
        round: 2,
        lastReview: review(1),
        headSha: "bbbbbbb",
        stateHeadSha: HEAD,
      });
      expect(step.action).toBe(ACTIONS.review);
      const after = nextStep({
        riskLevel: "L2",
        round: 2,
        lastReview: review(1),
        headSha: "bbbbbbb",
        stateHeadSha: "bbbbbbb",
      });
      expect(after.action).toBe(ACTIONS.needsHuman);
    });
  });

  it("drives a full L2 loop to ready without exceeding two rounds", () => {
    // Walks the machine the way run.mjs does, asserting the whole sequence
    // rather than one transition at a time.
    let round = 0;
    let lastReview = null;
    let stateHeadSha = null;
    const seen = [];
    const scripted = [review(2), review(1), review(0)];

    for (let guard = 0; guard < 10; guard += 1) {
      const step = nextStep({
        riskLevel: "L2",
        round,
        lastReview,
        checks: { ok: true },
        headSha: HEAD,
        stateHeadSha,
      });
      seen.push(step.action);
      if (step.action === ACTIONS.review) {
        lastReview = scripted.shift();
        stateHeadSha = HEAD;
      } else if (step.action === ACTIONS.fix) {
        round += 1;
        lastReview = scripted.shift();
      } else {
        break;
      }
    }

    expect(seen).toEqual([
      ACTIONS.review,
      ACTIONS.fix,
      ACTIONS.fix,
      ACTIONS.ready,
    ]);
    expect(round).toBe(2);
  });
});

// N1 on #92. BF7's terminus used to be synthesised by the orchestrator, which
// made this file's opening promise — "run.mjs does nothing this file did not
// decide" — false, and put the one outcome nobody can reach from here.

describe("the owner-decision fence concludes from the state machine (#82)", () => {
  const fenced = ["docs/contracts/mvp-v0.1.md"];

  it("concludes needs-human when the Writer's edit was behind the fence", () => {
    const step = nextStep({ riskLevel: "L2", headSha: "h", fencedEdits: fenced });
    expect(step.action).toBe(ACTIONS.needsHuman);
    expect(step.reason).toMatch(/docs\/contracts\/mvp-v0\.1\.md/);
    expect(step.reason).toMatch(/recorded human decision/);
    expect(step.reason).toMatch(/not a failed run/);
  });

  it("names every fenced path, not just the first", () => {
    const step = nextStep({
      riskLevel: "L2",
      headSha: "h",
      fencedEdits: ["docs/contracts/a.md", "docs/contracts/b.md"],
    });
    expect(step.reason).toContain("docs/contracts/a.md");
    expect(step.reason).toContain("docs/contracts/b.md");
  });

  it("wins over L0, which would otherwise skip the review entirely", () => {
    // A fenced edit is an observation about the run in hand. No later
    // condition can turn a discarded contract edit into a different outcome.
    expect(nextStep({ riskLevel: "L0", headSha: "h", fencedEdits: fenced }).action).toBe(
      ACTIONS.needsHuman,
    );
  });

  it("wins over the idempotency skip", () => {
    expect(
      nextStep({
        riskLevel: "L2",
        headSha: "h",
        stateHeadSha: "h",
        phase: ACTIONS.ready,
        fencedEdits: fenced,
      }).action,
    ).toBe(ACTIONS.needsHuman);
  });

  it("changes nothing when no fenced edit was seen", () => {
    // The condition it must not impose: an ordinary run is untouched.
    const step = nextStep({ riskLevel: "L2", headSha: "h", fencedEdits: [] });
    expect(step.action).toBe(ACTIONS.review);
  });
});

