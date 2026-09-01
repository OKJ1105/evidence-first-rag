// The Writer/Reviewer loop, as a pure state machine.
//
// Everything that decides *what happens next* lives here, with no GitHub calls
// and no Claude calls, so the round cap and the stop conditions can be tested
// against constructed inputs rather than by running the loop. `run.mjs` is the
// only file that performs I/O, and it does nothing this file did not decide.
//
// The cap is workflow §6's, not a new number: `L0` zero round trips, `L1` one,
// `L2` two. One round trip is Reviewer findings, Writer fix, Reviewer
// confirmation — so a round here is a fix plus the confirmation that follows.

/** Actions `nextStep` can return. `run.mjs` has one branch per value. */
export const ACTIONS = {
  /** Nothing to do — same head, already concluded. A re-run must be free. */
  skip: "skip",
  /** No AI review round trips are allowed at this risk level (§6). */
  skipL0: "skip-l0",
  /** Ask the Reviewer for findings against the current head. */
  review: "review",
  /** Run the repository checks. Nothing concludes without a verdict from them. */
  check: "check",
  /** Hand the blocking findings to the Writer. */
  fix: "fix",
  /** Concluded: no blocking findings and the checks pass. */
  ready: "ready-for-human-merge",
  /** Concluded, but a human has to look: cap reached, or checks still red. */
  needsHuman: "needs-human",
};

/**
 * Round-trip cap for a recorded risk level (workflow §6).
 *
 * An unrecognised level returns the `L2` cap deliberately: workflow §4 says
 * uncertainty raises the level, and a loop that guessed low would spend a
 * round trip the Issue never authorised.
 */
export function roundCapFor(riskLevel) {
  switch (String(riskLevel ?? "").toUpperCase()) {
    case "L0":
      return 0;
    case "L1":
      return 1;
    default:
      return 2;
  }
}

/**
 * Decide the next action. Pure.
 *
 * @param {object} input
 * @param {string} input.riskLevel        `L0` | `L1` | `L2`, from the PR.
 * @param {number} input.round            Rounds already spent on this PR.
 * @param {object|null} input.lastReview  Most recent Reviewer output, or null.
 * @param {object|null} input.checks      Most recent check run, or null.
 * @param {string} input.headSha          The PR head being acted on now.
 * @param {string|null} input.stateHeadSha Head the recorded state refers to.
 * @param {string} input.phase            Recorded phase, from state.
 */
export function nextStep({
  riskLevel,
  round = 0,
  lastReview = null,
  checks = null,
  headSha,
  stateHeadSha = null,
  phase = "idle",
}) {
  const cap = roundCapFor(riskLevel);

  // `L0` takes no AI review at all. Saying so is not the same as saying the
  // change is fine, so this concludes without a ready-to-merge claim.
  if (cap === 0) {
    return {
      action: ACTIONS.skipL0,
      reason: "L0 takes no AI review round trips (§6).",
    };
  }

  // Idempotency. A workflow re-run, a duplicate comment, or a second label
  // event must not spend a round trip or repost a review. Only an unchanged
  // head qualifies: a new commit is new work.
  const concluded = phase === ACTIONS.ready || phase === ACTIONS.needsHuman;
  if (concluded && stateHeadSha === headSha) {
    return {
      action: ACTIONS.skip,
      reason: `Already concluded at ${headSha} (${phase}).`,
    };
  }

  // A head that moved since the recorded review invalidates that review — the
  // Reviewer has not seen this code. Round count is deliberately *not* reset:
  // the cap is per pull request, so pushing a commit cannot buy more rounds.
  const reviewIsStale = lastReview !== null && stateHeadSha !== headSha;
  if (lastReview === null || reviewIsStale) {
    return {
      action: ACTIONS.review,
      reason: reviewIsStale
        ? `Head moved to ${headSha}; the recorded review was against ${stateHeadSha}.`
        : "No review recorded for this pull request yet.",
    };
  }

  const blocking = (lastReview.findings ?? []).filter(
    (f) => f.severity === "blocking",
  );

  if (blocking.length === 0) {
    // Green checks are part of "ready", and "ready" requires a *positive*
    // verdict rather than the absence of a negative one. `checks === null`
    // means they have not run on this run at all — which happens when a
    // recorded clean review is resumed at an unchanged head, so no `review`
    // step executes to run them. Treating that as a pass let the loop label a
    // red build ready while reporting "the checks pass".
    if (checks === null) {
      return {
        action: ACTIONS.check,
        reason:
          "A clean review is recorded but the checks have not run on this run.",
      };
    }
    if (checks.ok === false) {
      return {
        action: ACTIONS.needsHuman,
        reason: "No blocking findings, but the repository checks are failing.",
      };
    }
    return {
      action: ACTIONS.ready,
      reason: "No blocking findings and the checks pass.",
    };
  }

  if (round >= cap) {
    return {
      action: ACTIONS.needsHuman,
      reason:
        `${blocking.length} blocking finding(s) remain after ${round} of ${cap} ` +
        `round trip(s). §6 stops here; the owner decides.`,
    };
  }

  return {
    action: ACTIONS.fix,
    reason: `${blocking.length} blocking finding(s); round ${round + 1} of ${cap}.`,
  };
}
