import { describe, expect, it } from "./test-kit.mjs";
import { startLabel, decide } from "./gate.mjs";

// The 15 cases the review (NB3) found had been checked but left no artefact.
// They are committed here because the gate is the single control BF4's
// mitigation rests on.

const base = {
  name: "issue_comment",
  actor: "OKJ1105",
  owner: "OKJ1105",
  commentUserType: "User",
  isPullRequest: true,
  issueNumber: 7,
};

const at = (over) => decide({ ...base, ...over });

describe("who may start the loop", () => {
  it("refuses a non-owner actor", () => {
    expect(at({ actor: "someone", commentBody: "/agent-loop" }).run).toBe(
      false,
    );
  });

  it("refuses when the owner is unknown rather than defaulting to allow", () => {
    expect(at({ owner: "", actor: "", commentBody: "/agent-loop" }).run).toBe(
      false,
    );
  });
});

describe("comment trigger", () => {
  it("starts on /agent-loop", () => {
    expect(at({ commentBody: "/agent-loop" })).toMatchObject({
      run: true,
      pr: "7",
      reset: false,
    });
  });

  it("tolerates leading whitespace", () => {
    expect(at({ commentBody: "  \t/agent-loop" }).run).toBe(true);
  });

  it("is case insensitive", () => {
    expect(at({ commentBody: "/Agent-Loop" }).run).toBe(true);
  });

  it("allows trailing prose", () => {
    expect(at({ commentBody: "/agent-loop please have a look" }).run).toBe(
      true,
    );
  });

  it("sets reset only on /agent-loop reset", () => {
    expect(at({ commentBody: "/agent-loop reset" }).reset).toBe(true);
    expect(at({ commentBody: "/agent-loop" }).reset).toBe(false);
  });

  // The command must be the start of the comment, or quoting a previous
  // comment would restart the loop.
  it("does not start on a mid-comment mention", () => {
    expect(at({ commentBody: "I ran /agent-loop earlier" }).run).toBe(false);
  });

  it("does not start on a similar command", () => {
    expect(at({ commentBody: "/agent-looper" }).run).toBe(false);
  });

  it("ignores an unrelated comment", () => {
    expect(at({ commentBody: "looks good to me" }).run).toBe(false);
  });

  // The loop posts its own status comments; reacting to them would be
  // self-recursive.
  it("ignores a bot comment even when it carries the command", () => {
    expect(at({ commentBody: "/agent-loop", commentUserType: "Bot" }).run).toBe(
      false,
    );
  });

  it("ignores a comment on an issue rather than a pull request", () => {
    expect(at({ commentBody: "/agent-loop", isPullRequest: false }).run).toBe(
      false,
    );
  });
});

describe("label trigger", () => {
  it("starts on the start label", () => {
    expect(
      decide({
        ...base,
        name: "pull_request_target",
        labelName: startLabel,
        pullNumber: 12,
      }),
    ).toMatchObject({
      run: true,
      pr: "12",
    });
  });

  it("ignores an unrelated label", () => {
    expect(
      decide({
        ...base,
        name: "pull_request_target",
        labelName: "bug",
        pullNumber: 12,
      }).run,
    ).toBe(false);
  });

  // A status label the loop applies itself must never start another run.
  it.each([
    "agent:running",
    "agent:ready-for-human-merge",
    "agent:needs-human",
    "agent:failed",
  ])("ignores the status label %s", (labelName) => {
    expect(
      decide({
        ...base,
        name: "pull_request_target",
        labelName,
        pullNumber: 12,
      }).run,
    ).toBe(false);
  });
});

describe("manual dispatch", () => {
  it("starts and honours reset", () => {
    expect(
      decide({
        ...base,
        name: "workflow_dispatch",
        inputPull: 5,
        inputReset: true,
      }),
    ).toMatchObject({
      run: true,
      pr: "5",
      reset: true,
    });
  });

  it("refuses without a pull request number", () => {
    expect(
      decide({ ...base, name: "workflow_dispatch", inputPull: "" }).run,
    ).toBe(false);
  });
});

describe("unknown events", () => {
  // push in particular: a push trigger would restart the loop on its own
  // output, which is the recursion the design refuses.
  it.each(["push", "pull_request", "schedule"])("refuses %s", (name) => {
    expect(decide({ ...base, name, commentBody: "/agent-loop" }).run).toBe(
      false,
    );
  });
});
