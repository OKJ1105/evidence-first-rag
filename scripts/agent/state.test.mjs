import { describe, expect, it } from "./test-kit.mjs";
import {
  stateVersion,
  emptyState,
  parseState,
  renderState,
  renderStatusComment,
} from "./state.mjs";

describe("state round trip", () => {
  it("reads back what it wrote", () => {
    const state = {
      ...emptyState(),
      round: 1,
      phase: "review",
      headSha: "abc1234",
      riskLevel: "L2",
    };
    const parsed = parseState(`some prose\n\n${renderState(state)}\n`);
    expect(parsed).toMatchObject({
      round: 1,
      phase: "review",
      headSha: "abc1234",
      riskLevel: "L2",
    });
  });

  it("survives being embedded in a full status comment", () => {
    const state = {
      ...emptyState(),
      round: 2,
      headSha: "deadbee",
      riskLevel: "L1",
    };
    const body = renderStatusComment(state, {
      title: "Agent loop",
      lines: ["- something"],
    });
    expect(parseState(body)).toMatchObject({ round: 2, headSha: "deadbee" });
  });

  it("returns null for a comment that carries no marker", () => {
    expect(parseState("an ordinary review comment")).toBeNull();
    expect(parseState(undefined)).toBeNull();
  });
});

describe("a damaged marker is never treated as 'never run'", () => {
  // Silently falling back to empty state would reset the round count, which is
  // the one way the loop could exceed its cap without any code being wrong.
  it("throws on an unclosed marker", () => {
    expect(() => parseState("<!-- agent-loop-state {}")).toThrow(/not closed/);
  });

  it("throws on unparseable JSON", () => {
    expect(() => parseState("<!-- agent-loop-state {oops} -->")).toThrow(
      /not valid JSON/,
    );
  });

  it("throws on a version this build does not write", () => {
    expect(() =>
      parseState(`<!-- agent-loop-state {"v":${stateVersion + 1}} -->`),
    ).toThrow(/version/);
  });
});

describe("renderStatusComment", () => {
  it("puts the human-readable status before the machine marker", () => {
    const body = renderStatusComment({
      ...emptyState(),
      round: 1,
      headSha: "abc",
      riskLevel: "L2",
      issueNumber: 42,
    });
    expect(body.indexOf("Agent loop state")).toBeLessThan(
      body.indexOf("agent-loop-state"),
    );
    expect(body).toContain("Rounds spent: **1**");
    expect(body).toContain("`L2`");
    expect(body).toContain("#42");
  });

  it("renders no findings, so rewriting it destroys no record (BF6)", () => {
    const body = renderStatusComment({
      ...emptyState(),
      lastReview: {
        summary: "x",
        findings: [{ id: "B1", summary: "SHOULDNOTAPPEAR" }],
      },
    });
    // The marker legitimately carries `lastReview` — the loop needs it across
    // runs. What must not happen is a finding being *displayed* only here,
    // because this comment is the one that gets overwritten.
    const rendered = body.slice(0, body.indexOf("<!-- agent-loop-state"));
    expect(rendered).not.toContain("SHOULDNOTAPPEAR");
    expect(rendered).toContain("separate comments");
  });
});

// #116. The marker is the only place the next run can learn WHY the last CI
// verdict said what it said, and `nextStep` reads it to decide whether a
// concluded head may be looked at again. A missing default or a missing line
// costs nothing at runtime and everything to the reader.

describe("the marker carries why CI said what it said (#116)", () => {
  it("defaults both fields rather than leaving the keys absent", () => {
    // `parseState` spreads `emptyState()` under the parsed marker, so this is
    // what a marker written before #116 resolves to. `null` is a stated
    // "not recorded"; an absent key is an accident that reads the same.
    for (const key of ["ciConclusion", "ciObserved"]) {
      expect(Object.keys(emptyState())).toContain(key);
      expect(emptyState()[key]).toBe(null);
    }
  });

  it("tells the owner when the loop never saw a completed run (#137)", () => {
    // The conclusion string alone does not say it: `timed_out` is both the
    // loop's expired wait and one of GitHub's own run conclusions.
    const unseen = renderStatusComment({
      ...emptyState(),
      headSha: "abc",
      ciConclusion: "timed_out",
      ciObserved: false,
    });
    expect(unseen).toContain("the loop never saw a completed run");

    const judged = renderStatusComment({
      ...emptyState(),
      headSha: "abc",
      ciConclusion: "timed_out",
      ciObserved: true,
    });
    expect(judged).toContain("CI on that head: `timed_out`");
    expect(judged).not.toContain("never saw a completed run");
  });

  it("shows the conclusion to the owner when there is one", () => {
    const body = renderStatusComment({
      ...emptyState(),
      headSha: "abc",
      checksOk: false,
      ciConclusion: "timed_out",
    });
    expect(body).toContain("CI on that head: `timed_out`");
  });

  it("says nothing about CI when none was taken", () => {
    // An empty line here would read as a verdict of its own.
    const body = renderStatusComment({ ...emptyState(), headSha: "abc" });
    expect(body).not.toContain("CI on that head");
  });

  it("survives a round trip through the marker", () => {
    const state = {
      ...emptyState(),
      headSha: "abc",
      ciConclusion: "cancelled",
      ciObserved: true,
    };
    const back = parseState(renderStatusComment(state));
    expect(back.ciConclusion).toBe("cancelled");
    expect(back.ciObserved).toBe(true);
  });
});
