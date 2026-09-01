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
