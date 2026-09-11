// Loop state, carried in a marker comment on the pull request.
//
// Workflow section 2 makes GitHub the only canonical record, so the loop's
// state lives where a human can read it rather than in workflow artifacts that
// expire.
//
// This comment carries STATE ONLY, and is edited in place. Round artifacts -
// each review, each Writer response - are posted as separate comments and are
// never rewritten, because BF6 found that overwriting one comment destroyed
// round 1's findings and the response that answered them, which workflow
// section 2 makes canonical and section 7 makes the basis of the owner's
// decision.
//
// The marker is an HTML comment: invisible in the rendered pull request, plain
// text in the source, and greppable.

export const stateMarker = "agent-loop-state";
export const stateVersion = 2;

const OPEN = `<!-- ${stateMarker}`;
const CLOSE = "-->";

/** The state a pull request the loop has never touched is treated as having. */
export function emptyState() {
  return {
    v: stateVersion,
    round: 0,
    phase: "idle",
    headSha: null,
    riskLevel: null,
    issueNumber: null,
    registry: {},
    lastReview: null,
    // Display only. Never an input to `nextStep`: a verdict recorded on a
    // previous run belongs to a different commit (BF2).
    checksOk: null,
    // The CI verdict at the last run that CONCLUDED, and whether a completed
    // CI run produced it (#116, #137 N3).
    //
    // "Concluded" is exact, not loose: both fields are written only where the
    // phase is set to `ready` or `needs-human`. The review and fix steps
    // advance `headSha` without touching them, so an interrupted marker can
    // pair a new `headSha` with an older run's verdict. That is safe only
    // because `nextStep` reads `ciObserved` in one branch, and that branch
    // requires a concluded phase — which only the write that sets these fields
    // produces. Display only otherwise, like `checksOk`, and never a verdict
    // carried across commits (BF2).
    ciConclusion: null,
    // `false` means the loop never saw a completed run: its wait expired, the
    // dispatch was refused, or the job had no time left. `true` means a
    // completed run judged the head, whatever it concluded — `cancelled` and
    // `timed_out` included, which is why this is a flag and not a list of
    // conclusion strings (#137 B1). `null` is "not recorded", which is every
    // marker written before this field existed.
    ciObserved: null,
    runId: null,
    updatedAt: null,
  };
}

/**
 * Read state out of a comment body.
 *
 * Returns null when the body carries no marker, and throws only when a marker
 * is present but unreadable - a corrupted marker is a state the loop must not
 * silently treat as "never run", because that would reset the round count.
 */
export function parseState(body) {
  if (typeof body !== "string") return null;
  const start = body.indexOf(OPEN);
  if (start === -1) return null;
  const end = body.indexOf(CLOSE, start);
  if (end === -1) {
    throw new Error("Loop state marker is not closed.");
  }
  const json = body.slice(start + OPEN.length, end).trim();
  let parsed;
  try {
    parsed = JSON.parse(json);
  } catch (cause) {
    throw new Error(`Loop state marker is not valid JSON: ${cause.message}`, {
      cause,
    });
  }
  if (parsed?.v !== stateVersion) {
    throw new Error(
      `Loop state marker is version ${parsed?.v}; this build writes ${stateVersion}.`,
    );
  }
  return { ...emptyState(), ...parsed };
}

/** Serialise state into the marker a comment body carries. */
export function renderState(state) {
  return [
    OPEN,
    JSON.stringify({ ...state, v: stateVersion }, null, 0),
    CLOSE,
  ].join("\n");
}

/**
 * The state comment: a short human-readable summary, then the marker.
 *
 * It carries no findings and no responses. Those are in their own comments,
 * where they survive the next round.
 */
export function renderStatusComment(state) {
  return [
    "## Agent loop state",
    "",
    `- Issue: ${state.issueNumber ? `#${state.issueNumber}` : "unresolved"}`,
    `- Risk: \`${state.riskLevel ?? "unknown"}\``,
    `- Rounds spent: **${state.round}**`,
    `- Phase: \`${state.phase}\``,
    `- Head: \`${state.headSha ?? "unknown"}\``,
    `- Checks at last run: ${state.checksOk === null ? "not run" : state.checksOk ? "pass" : "**FAIL**"}`,
    ...(state.ciConclusion
      ? [
          `- CI on that head: \`${state.ciConclusion}\`` +
            (state.ciObserved === false
              ? " — **the loop never saw a completed run**, so a re-run takes the verdict again"
              : ""),
        ]
      : []),
    ...(state.runId ? [`- Latest run: ${state.runId}`] : []),
    ...(state.updatedAt ? [`- Updated: ${state.updatedAt}`] : []),
    "",
    "Findings and Writer responses are separate comments on this pull request and are not rewritten.",
    "",
    renderState(state),
  ].join("\n");
}
