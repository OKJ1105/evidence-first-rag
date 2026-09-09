// The only file that talks to GitHub.
//
// It is deliberately small, and deliberately the only holder of the token in
// the orchestrator's own code. The agents in `claude.mjs` are spawned with the
// credential stripped, and `run.mjs` strips it again before running any
// repository script (BF3).
//
// There is no method here that approves a review, merges, or closes anything.
// Adding one would be the change to argue about.

const API = process.env.GITHUB_API_URL ?? "https://api.github.com";

function tokenOrThrow() {
  const token = process.env.GITHUB_TOKEN;
  if (!token) {
    throw new Error(
      "GITHUB_TOKEN is not set; refusing to call the API unauthenticated.",
    );
  }
  return token;
}

async function request(method, path, body) {
  const res = await fetch(`${API}${path}`, {
    method,
    headers: {
      Authorization: `Bearer ${tokenOrThrow()}`,
      Accept: "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
      ...(body ? { "Content-Type": "application/json" } : {}),
    },
    ...(body ? { body: JSON.stringify(body) } : {}),
  });
  if (!res.ok) {
    throw new Error(
      `${method} ${path} returned ${res.status}: ${(await res.text()).slice(0, 400)}`,
    );
  }
  return res.status === 204 ? null : res.json();
}

export function createClient({ owner, repo }) {
  const base = `/repos/${owner}/${repo}`;

  return {
    getPull: (number) => request("GET", `${base}/pulls/${number}`),

    /**
     * The Issue, which is what the Reviewer must read (BF1). This is a
     * different resource from `getPull`: `pulls/{n}` returns the pull request
     * body, which is the Writer's narrative and the thing property 3 exists to
     * keep out of the Reviewer's search space.
     */
    getIssue: (number) => request("GET", `${base}/issues/${number}`),

    /**
     * Every comment, not the first hundred.
     *
     * Comments come back oldest-first, so on a busy pull request an unpaginated
     * read drops the loop's state marker off the end, `loadState` falls back to
     * empty, and the round count silently resets to zero (NB2) — the one thing
     * the state parser is careful never to do on a damaged marker.
     */
    listComments: async (number) => {
      const all = [];
      for (let page = 1; page <= 20; page += 1) {
        const batch = await request(
          "GET",
          `${base}/issues/${number}/comments?per_page=100&page=${page}`,
        );
        all.push(...batch);
        if (batch.length < 100) return all;
      }
      throw new Error(
        `More than 2000 comments on #${number}; refusing to guess whether the state marker was reached.`,
      );
    },

    createComment: (number, body) =>
      request("POST", `${base}/issues/${number}/comments`, { body }),

    updateComment: (commentId, body) =>
      request("PATCH", `${base}/issues/comments/${commentId}`, { body }),

    addLabels: (number, labels) =>
      request("POST", `${base}/issues/${number}/labels`, { labels }),

    /** Missing labels are not an error: the caller wants the label gone. */
    removeLabel: async (number, label) => {
      try {
        await request(
          "DELETE",
          `${base}/issues/${number}/labels/${encodeURIComponent(label)}`,
        );
      } catch (err) {
        if (!/returned 404/.test(String(err.message))) throw err;
      }
    },

    /**
     * Reviews on the pull request. Read-only, and used by the guard in
     * `run.mjs` that fails the run if anything approved on its watch.
     */
    /**
     * Start a workflow run on `ref` (#21).
     *
     * The loop's Writer pushes with `GITHUB_TOKEN`, and GitHub starts no
     * workflow from an event that token raised — so the `pull_request:
     * synchronize` the push would otherwise fire never happens and CI never
     * runs on the head the loop is about to label. `workflow_dispatch` raised
     * with `GITHUB_TOKEN` is GitHub's documented exception to that rule, which
     * is why this needs no new Secret and no PAT. It does need `actions: write`
     * on the loop's job, which is a permission change and was the repository
     * owner's to approve; recorded on #68 decision 2, answered 2026-09-09.
     *
     * 204 on success, so `request` resolves null.
     */
    dispatchWorkflow: (workflowFile, ref, inputs = {}) =>
      request("POST", `${base}/actions/workflows/${workflowFile}/dispatches`, {
        ref,
        ...(Object.keys(inputs).length > 0 ? { inputs } : {}),
      }),

    /**
     * Recent runs of one workflow on one branch, newest first.
     *
     * Deliberately not filtered by `event`: the run this looks for is the
     * dispatched one, but a `pull_request` run on the same head is just as
     * good an answer to "did CI pass on this commit", and refusing it would
     * make the loop wait for a second run it did not need.
     */
    listWorkflowRuns: (workflowFile, branch, perPage = 20) =>
      request(
        "GET",
        `${base}/actions/workflows/${workflowFile}/runs` +
          `?branch=${encodeURIComponent(branch)}&per_page=${perPage}`,
      ),

    listReviews: (number) =>
      request("GET", `${base}/pulls/${number}/reviews?per_page=100`),
  };
}
