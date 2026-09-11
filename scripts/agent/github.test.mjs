import { describe, expect, it } from "./test-kit.mjs";
import { createClient } from "./github.mjs";

// `github.mjs` had no tests: it is a thin wrapper over `fetch`, and the two
// methods #21 adds are the first whose *request* carries meaning rather than
// just a path. `dispatchWorkflow` is what makes CI run on a loop-pushed head at
// all, and `listWorkflowRuns` is how the loop finds the run it started. A
// mutation that drops the branch filter from the query string changed no
// behaviour any other test could see, which is exactly the gap #17 rule 9 says
// is not evidence.
//
// The client holds the token, so these patch `fetch` rather than reach the
// network. Nothing here asserts a response shape — `run.test.mjs` drives that
// through fakes; what is pinned here is the request that leaves the process.

/** Capture the one request a client call makes, without touching the network. */
async function capture(call) {
  const realFetch = globalThis.fetch;
  const realToken = process.env.GITHUB_TOKEN;
  const seen = [];
  globalThis.fetch = async (url, init) => {
    seen.push({ url, init });
    return { ok: true, status: 204, json: async () => null, text: async () => "" };
  };
  process.env.GITHUB_TOKEN = "t";
  try {
    await call(createClient({ owner: "o", repo: "r" }));
  } finally {
    globalThis.fetch = realFetch;
    if (realToken === undefined) delete process.env.GITHUB_TOKEN;
    else process.env.GITHUB_TOKEN = realToken;
  }
  return seen;
}

describe("the workflow calls #21 adds", () => {
  it("dispatches by POST to the workflow's dispatches endpoint, with the ref", async () => {
    const seen = await capture((gh) =>
      gh.dispatchWorkflow("repository-checks.yml", "a-branch"),
    );
    expect(seen.length).toBe(1);
    expect(seen[0].url).toContain(
      "/repos/o/r/actions/workflows/repository-checks.yml/dispatches",
    );
    expect(seen[0].init.method).toBe("POST");
    expect(JSON.parse(seen[0].init.body)).toMatchObject({ ref: "a-branch" });
  });

  it("omits `inputs` when there are none, rather than sending an empty object", async () => {
    // The dispatch endpoint rejects `inputs` that name nothing the workflow
    // declares, and `repository-checks.yml` declares none.
    const seen = await capture((gh) =>
      gh.dispatchWorkflow("repository-checks.yml", "a-branch"),
    );
    expect(Object.keys(JSON.parse(seen[0].init.body))).toEqual(["ref"]);
  });

  it("scopes the run listing to one branch", async () => {
    // Without this the listing is repository-wide. The loop then looks for its
    // head among the most recent runs of every branch, and on a repository with
    // parallel tracks the run it just dispatched can fall off the first page —
    // so the loop reports `no run appeared on this head` and refuses a head
    // whose CI actually passed.
    const seen = await capture((gh) =>
      gh.listWorkflowRuns("repository-checks.yml", "a-branch"),
    );
    expect(seen[0].url).toContain("branch=a-branch");
    expect(seen[0].init.method).toBe("GET");
  });

  it("percent-encodes a branch name that needs it", async () => {
    // Every branch this repository's loop runs on is `claude/...`.
    const seen = await capture((gh) =>
      gh.listWorkflowRuns("repository-checks.yml", "claude/track-c#1"),
    );
    expect(seen[0].url).toContain("branch=claude%2Ftrack-c%231");
  });

  it("asks for a bounded page rather than the default", async () => {
    const seen = await capture((gh) =>
      gh.listWorkflowRuns("repository-checks.yml", "a-branch", 20),
    );
    expect(seen[0].url).toContain("per_page=20");
  });
});
