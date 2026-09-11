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
  fencedEdits = [],
  ciObserved = null,
}) {
  const cap = roundCapFor(riskLevel);

  // BF7's terminus (#82), decided here rather than in the orchestrator.
  //
  // A Writer turn that edited a path behind the owner-decision fence has its
  // edit discarded and hands the pull request to the owner. This lives in
  // `nextStep` because the header above promises `run.mjs` "does nothing this
  // file did not decide", and an orchestrator that synthesised its own
  // terminal action would make that false — raised as N1 on #92.
  //
  // It is checked before the `L0` and idempotency branches on purpose: the
  // observation is about the run in hand, and no later condition can make a
  // discarded contract edit into a different outcome.
  if (fencedEdits.length > 0) {
    return {
      action: ACTIONS.needsHuman,
      reason:
        `The Writer's fix required editing ${fencedEdits.join(", ")}, which is behind the ` +
        "owner-decision fence. Amending an accepted contract is a recorded human decision " +
        "under its Section 10, not a review-finding fix, so that edit was discarded and " +
        "nothing from that Writer turn was committed or pushed. Whether the amendment was " +
        "warranted is yours to judge, and earlier rounds of this run may already have moved " +
        "the branch head. Reaching this fence is a designed outcome, not a failed run. The " +
        "findings below stand and are the owner's to resolve.",
    };
  }

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
  //
  // #116 carves out one case, and only one. Since #21 the verdict folded into
  // `checks` can be a statement about the RUN rather than about the branch:
  // the loop's wait expired, the dispatch was refused, or the job ran out of
  // time before it could wait. All three set `ok: false` — correctly, an
  // unmeasured build is not ready — and the head then concluded `needs-human`
  // and became untouchable. CI going green two minutes later changed nothing,
  // and the only way to make the loop look again was `/agent-loop reset`,
  // which is implemented as `emptyState()` and therefore puts `round` back to
  // 0. Recovering from a slow build and refunding two AI review rounds were
  // the same keystroke, and nothing in the record said which one was meant.
  //
  // "the build is red" is about the branch and stays terminal until the branch
  // changes. "I did not see the build" is about the run, and a later run at
  // the same head has strictly better information.
  //
  // **Keyed on `ciObserved`, never on the conclusion string (#137 B1).** The
  // first version listed the conclusions it considered transient, and two of
  // them can be written by GitHub as a COMPLETED run's own terminal verdict:
  // `cancelled` always is, and `timed_out` is both that and the loop's own
  // wait-expiry sentinel. Since `awaitCiOnHead` looks before it dispatches, a
  // completed run on the head means a re-run gets the same answer for ever —
  // so such a head could never conclude again, and `/agent-loop reset` did not
  // end it either. `observed` is set by the one place that reads a completed
  // run, so the two producers cannot collide.
  //
  // Deliberately narrow. Re-examination needs a recorded review at this head
  // with nothing blocking left in it, so the unseen verdict is the only thing
  // between this head and `ready`. A head carrying blocking findings stays
  // skipped: resuming the fix loop would spend a round the owner did not ask
  // for, and that is not what this is for.
  const recordedBlocking = (lastReview?.findings ?? []).filter(
    (f) => f.severity === "blocking",
  );
  const ciWasNeverAVerdict =
    ciObserved === false && lastReview !== null && recordedBlocking.length === 0;

  const concluded = phase === ACTIONS.ready || phase === ACTIONS.needsHuman;
  if (concluded && stateHeadSha === headSha && !ciWasNeverAVerdict) {
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
