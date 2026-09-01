// Whether an event is a real request from the owner to start the loop.
//
// This lived as embedded shell inside the workflow until the review found that
// it was the single control BF4's mitigation rests on and the one guard that
// could not be mutation-checked (NB3). It is a pure function here so the cases
// live in `gate.test.mjs` as committed tests rather than in a transcript.

/** Commands the loop answers to, anchored so a mention cannot start it. */
const COMMAND = /^[ \t]*\/agent-loop\b/i;
const RESET = /^[ \t]*\/agent-loop[ \t]+reset\b/i;

/** The one label that starts the loop. Status labels must never do. */
export const startLabel = "agent:run";

/**
 * @param {object} event
 * @param {string} event.name      GitHub event name.
 * @param {string} event.actor     Who triggered it.
 * @param {string} event.owner     Repository owner.
 * @param {string} [event.commentBody]
 * @param {string} [event.commentUserType]  "User" or "Bot".
 * @param {boolean} [event.isPullRequest]
 * @param {string|number} [event.issueNumber]
 * @param {string} [event.labelName]
 * @param {string|number} [event.pullNumber]
 * @param {string|number} [event.inputPull]
 * @param {boolean} [event.inputReset]
 * @returns {{run: boolean, pr: string, reset: boolean, reason: string}}
 */
export function decide(event) {
  const no = (reason) => ({ run: false, pr: "", reset: false, reason });
  const yes = (pr, reset, reason) => ({
    run: true,
    pr: String(pr ?? ""),
    reset: Boolean(reset),
    reason,
  });

  // The loop pushes commits and spends model budget, so it is not something a
  // commenter should be able to trigger.
  if (!event.owner || event.actor !== event.owner) {
    return no(`actor ${event.actor} is not the owner`);
  }

  switch (event.name) {
    case "issue_comment": {
      // The loop posts its own comments; reacting to them would be
      // self-recursive.
      if (event.commentUserType === "Bot") return no("bot comment");
      if (!event.isPullRequest) return no("comment is on an issue");
      const body = event.commentBody ?? "";
      if (!COMMAND.test(body)) return no("no /agent-loop command");
      return yes(
        event.issueNumber,
        RESET.test(body),
        "/agent-loop on a pull request",
      );
    }
    case "pull_request_target":
      if (event.labelName !== startLabel)
        return no(`label ${event.labelName} does not start the loop`);
      return yes(event.pullNumber, false, `${startLabel} label added`);
    case "workflow_dispatch":
      if (!event.inputPull) return no("no pull request number given");
      return yes(event.inputPull, event.inputReset, "manual dispatch");
    default:
      return no(`event ${event.name} does not start the loop`);
  }
}

/* c8 ignore start - CLI shim, exercised by the workflow */
if (process.argv[1] && import.meta.url === `file://${process.argv[1]}`) {
  const env = process.env;
  const result = decide({
    name: env.CI_EVENT_NAME,
    actor: env.CI_EVENT_ACTOR,
    owner: env.CI_REPO_OWNER,
    commentBody: env.CI_COMMENT_BODY,
    commentUserType: env.CI_COMMENT_USER_TYPE,
    isPullRequest: env.CI_IS_PULL_REQUEST === "true",
    issueNumber: env.CI_ISSUE_NUMBER,
    labelName: env.CI_LABEL_NAME,
    pullNumber: env.CI_PULL_NUMBER,
    inputPull: env.CI_INPUT_PR,
    inputReset: env.CI_INPUT_RESET === "true",
  });
  const { appendFileSync } = await import("node:fs");
  const out = env.GITHUB_OUTPUT;
  const lines = `run=${result.run}\npr=${result.pr}\nreset=${result.reset}\n`;
  if (out) appendFileSync(out, lines);
  console.log(
    `Decision: run=${result.run} pr=${result.pr} reset=${result.reset} (${result.reason})`,
  );
}
/* c8 ignore stop */
