/**
 * `api-v0.1` Section 4.6: an envelope in, a description of the screen out.
 *
 * Every function here is pure. No DOM, no `fetch`, no globals, no clock — so
 * the obligations Section 4.6 states about what a person sees are assertions
 * over a value, and `ui/view.test.mjs` runs them under `node --test` with no
 * browser. `ui/index.html` applies what these return and decides nothing.
 *
 * **The UI holds no vocabulary of its own**, which is Section 4.1's rule about
 * the surface applied one layer out. One consequence of that and the single
 * exception to it, both worth stating: the first looks like an omission and
 * the second looks like a violation.
 *
 * - The evidence sections are built by walking the keys the result carries,
 *   not from a list written here. A key added to `mvp-v0.1` Section 7 or
 *   `entity-discovery-v0.1` Section 7 appears on screen without this file
 *   changing, and obligation 1's "may not omit" holds structurally rather
 *   than by maintenance.
 * - The one map that does appear is `entity_kind` to the `target_route` values
 *   that kind permits, and it is not a second copy of a decision: `api-v0.1`
 *   Section 4.3 states it for this surface in as many words — "offering a
 *   target the selected candidate does not permit would be offering an option
 *   this contract's own selection path refuses" — and obligation 4 requires
 *   the route sent to be "one the person chose **from the permitted values**".
 *   Prefilling is still declined for both kinds, including the `message` kind
 *   where only one value is permitted: obligation 4 permits that prefill and
 *   never requires it. What is enforced here is the **offer**, and what is
 *   refused remains `entity-discovery-v0.1` Section 4.8 step 6's to refuse —
 *   a value typed past this page is still judged there, as a result with its
 *   evidence.
 */

/** `mvp-v0.1` Section 4.5. The three fact routes, as their union. */
export const FACT_ROUTES = ["message_facts", "signal_facts", "signal_mapping"];

/**
 * `entity-discovery-v0.1` Section 4.8's table, which `api-v0.1` Section 4.3
 * restates for this surface. A `Map` rather than an object literal so that a
 * kind read off a response cannot reach a prototype property and be answered
 * with something that is not a route list.
 */
const TARGET_ROUTES = new Map([
  ["message", ["message_facts"]],
  ["signal", ["signal_facts", "signal_mapping"]],
]);

/**
 * The routes a candidate of `entityKind` permits, and no others.
 *
 * A kind outside the two is not one this table covers, so it offers nothing:
 * `entity-discovery-v0.1` Section 5 makes such a request `unsupported` and no
 * candidate carries such a kind, and offering the union on a kind nobody
 * recognises would be guessing on the one field this function exists to stop
 * guessing on.
 */
export function targetRoutesFor(entityKind) {
  return [...(TARGET_ROUTES.get(entityKind) ?? [])];
}

/** The three top-level result keys every outcome carries (Section 4.4). */
const EVIDENCE_KEYS = ["evidence_bundle", "source_trace", "limitations"];

/** Obligation 1: shown, in a stable order, never omitted. */
function entries(mapping) {
  if (mapping === null || mapping === undefined) return [];
  return Object.keys(mapping)
    .sort()
    .map((key) => ({ key, value: mapping[key] }));
}

/**
 * The evidence of one result, as sections a screen can collapse but not drop.
 *
 * Read off the result rather than enumerated, so the two contracts' differing
 * key sets are both covered and neither can drift from this file.
 */
export function evidenceOf(result) {
  const sections = [];
  for (const key of EVIDENCE_KEYS) {
    if (!(key in (result ?? {}))) continue;
    const value = result[key];
    sections.push({
      key,
      // `limitations` is a list of `{kind, detail}`; the other two are
      // mappings. Both are shown whole.
      items: Array.isArray(value) ? value.map((entry) => entries(entry)) : [entries(value)],
    });
  }
  return sections;
}

/**
 * Obligation 2. The answer is `rendered`, verbatim, or there is no answer.
 *
 * `kind: "none"` is not an empty string with a different name: it tells the
 * page to show no prose at all, which is what the obligation requires where
 * `rendered` is null. A heading or a field label is not prose that states a
 * fact, so the page may still print those.
 */
export function answerOf(envelope) {
  const rendered = envelope?.rendered;
  if (typeof rendered !== "string") return { kind: "none" };
  return { kind: "prose", text: rendered };
}

/**
 * Obligation 3. A candidate list is not an answer.
 *
 * Rank order as the response carried it — `sort` is deliberately absent, since
 * re-sorting is the reordering obligation 7 forbids. Every field of every
 * candidate, none hidden. `selected` is false on every row: a list arriving
 * from the surface has no selection state, and obligation 4 says only a
 * person's act creates one.
 */
export function candidatesOf(result) {
  const candidates = result?.candidates;
  if (!Array.isArray(candidates)) return [];
  return candidates.map((candidate) => ({
    rank: candidate.rank,
    // Carried out of `fields` as well as in it, because the selection form
    // below decides the routes it may offer from this one value. It is shown
    // by `fields` like every other; naming it twice hides nothing.
    entityKind: candidate.entity_kind ?? null,
    fields: entries(candidate),
    selected: false,
    highlighted: false,
  }));
}

/**
 * Obligation 6. The adapter's output, labelled as a proposal or not shown.
 *
 * `verbatim` travels with it because obligation 4 reads it, and because a
 * reader deciding whether to trust a proposed value needs to see which of them
 * the system could find in their own words.
 */
export function proposalOf(envelope) {
  if (!envelope || !("proposal" in envelope)) return null;
  const proposal = envelope.proposal ?? {};
  const verbatim = Array.isArray(proposal.verbatim) ? proposal.verbatim : [];
  const argumentsGiven = proposal.arguments;
  const isMapping =
    argumentsGiven !== null && typeof argumentsGiven === "object" && !Array.isArray(argumentsGiven);
  return {
    label: "the adapter's proposal, before revalidation",
    route: proposal.route,
    verbatim,
    arguments: isMapping
      ? Object.keys(argumentsGiven)
          .sort()
          .map((name) => ({
            name,
            value: argumentsGiven[name],
            // The distinction obligation 4 turns on, carried to the screen so
            // a person can see which values came from what they typed.
            verbatim: verbatim.includes(name),
          }))
      : [],
  };
}

/**
 * Obligation 4, the prefill rules, as the state of a discovery form.
 *
 * Section 4.6 decides each field by **what a wrong value would do**, not by
 * who produced it:
 *
 * - `term` carries the person's own `request_text`: they see their own words
 *   and accept or edit them, so what is sent is what they approved.
 * - a scope dimension is prefilled **only** from a `proposal.arguments` value
 *   named in `proposal.verbatim`. A value outside it is `offered` — displayed,
 *   labelled as the adapter's unverified proposal — and is **not** the field's
 *   value, because a wrong scope returns true facts about the wrong snapshot
 *   and nothing in the result says so.
 * - `entity_kind` may be prefilled: a wrong kind fails closed.
 *
 * Every field is `editable`, and nothing here submits: `submitted` is false on
 * every return, and only `ui/index.html` acting on a person's act changes it.
 */
export function discoveryForm({ requestText = "", proposal = null, scopeDimensions = [], entityKind = null } = {}) {
  const verbatim = new Set(proposal?.verbatim ?? []);
  const proposed = new Map((proposal?.arguments ?? []).map((argument) => [argument.name, argument]));

  const fields = [
    { name: "term", value: requestText, source: "the person's own request text", editable: true, offered: null },
    {
      name: "entity_kind",
      value: entityKind ?? "",
      source: entityKind ? "the Section 4.3 table; a wrong kind fails closed" : null,
      editable: true,
      offered: null,
    },
  ];

  for (const dimension of scopeDimensions) {
    const argument = proposed.get(dimension);
    const isVerbatim = argument !== undefined && verbatim.has(dimension);
    fields.push({
      name: dimension,
      // Empty unless the person's own words carried it.
      value: isVerbatim ? argument.value : "",
      source: isVerbatim ? "present in the request text" : null,
      editable: true,
      // Shown beside the field, never in it.
      offered:
        argument !== undefined && !isVerbatim
          ? { value: argument.value, label: "the adapter proposed this; it is not in your request" }
          : null,
    });
  }

  return { fields, submitted: false };
}

/**
 * Obligation 4, the selection half.
 *
 * No default on `target_route`, ever — see this module's docstring. `rank` has
 * no default either: obligation 3 forbids a pre-selected candidate, and a
 * prefilled rank is one.
 *
 * `targetRoutes` is **empty until a rank is chosen**, which is not the same
 * omission as having no default: which routes are permitted is a property of
 * the selected candidate, and before an act there is no selected candidate to
 * read it off. `choices` carries each candidate's permitted set so that
 * `chooseRank` can answer the question without a second pass over the result.
 */
export function selectionForm({ candidates = [] } = {}) {
  const choices = candidates.map((candidate) => ({
    rank: candidate.rank,
    entityKind: candidate.entityKind ?? null,
    targetRoutes: targetRoutesFor(candidate.entityKind),
  }));
  return {
    ranks: choices.map((choice) => choice.rank),
    choices,
    chosenRank: null,
    targetRoutes: [],
    chosenTargetRoute: null,
    // `ui/index.html` may send only when both are set by an act.
    sendable: false,
    submitted: false,
  };
}

/**
 * One person's act: this rank, and therefore these routes.
 *
 * A route chosen for a different candidate is dropped rather than carried
 * across, because a value that was permitted for the previous rank may not be
 * permitted for this one — and a choice the person made about another
 * candidate was never a choice about this one.
 *
 * A rank that names no listed candidate chooses nothing. Obligation 4 admits a
 * selection only on "one listed rank", so an unlisted one is not a narrower
 * selection; it is none.
 */
export function chooseRank(form, rank) {
  const choice = (form?.choices ?? []).find((entry) => entry.rank === rank) ?? null;
  return {
    ...form,
    chosenRank: choice === null ? null : choice.rank,
    targetRoutes: choice === null ? [] : [...choice.targetRoutes],
    chosenTargetRoute: null,
  };
}

/**
 * Whether a `/v1/select` may be sent. Both choices, both from an act, and the
 * route among the ones the chosen candidate permits.
 *
 * The last clause is the guard, not a restatement: without it a page could
 * offer the permitted set and still send a value from outside it, which is the
 * option `entity-discovery-v0.1` Section 4.8 step 6 refuses.
 */
export function maySend(form) {
  return (
    form?.chosenRank !== null &&
    form?.chosenRank !== undefined &&
    typeof form?.chosenTargetRoute === "string" &&
    form.chosenTargetRoute.length > 0 &&
    (form?.targetRoutes ?? []).includes(form.chosenTargetRoute)
  );
}

/**
 * The whole screen for one envelope.
 *
 * Obligation 5 is why there is no `error` branch: a status is carried through
 * as itself, and a surface refusal is a different shape entirely — see
 * `refusalView`. Nothing here retries, rephrases, or discovers.
 */
export function view(envelope, { requestText = "" } = {}) {
  const result = envelope?.result ?? null;
  const proposal = proposalOf(envelope);
  const candidates = candidatesOf(result);
  return {
    kind: "result",
    status: result?.status ?? null,
    answer: answerOf(envelope),
    // Order untouched (obligation 7).
    rows: Array.isArray(result?.rows) ? result.rows.map((row) => entries(row)) : [],
    resolved: result?.resolved ? entries(result.resolved) : null,
    candidates,
    evidence: evidenceOf(result),
    proposal,
    contract: envelope?.contract ?? null,
    selection: candidates.length > 0 ? selectionForm({ candidates }) : null,
    requestText,
  };
}

/**
 * A Section 4.5 refusal: `{refusal, detail}` and no result.
 *
 * A separate shape so the page cannot render one as an outcome — obligation 5
 * forbids presenting a surface refusal as a result, and the two being the same
 * type is how that happens by accident.
 */
export function refusalView(body) {
  return { kind: "refusal", refusal: body?.refusal ?? null, detail: body?.detail ?? null };
}

/**
 * A request that never reached the surface, which is neither of the two above.
 *
 * Obligation 5 forbids showing a surface refusal as a result. A `fetch` that
 * rejects is a third thing again -- no response exists at all -- and the
 * failure it invites is quieter: the previous request's result and evidence
 * stay on screen, and are read as the answer to the question just asked. So it
 * has its own `kind`, and `ui/index.html` clears the screen before showing it.
 *
 * The cause is carried as text for a reader, never parsed: nothing downstream
 * branches on why the request failed.
 */
export function unreachedView(cause) {
  return {
    kind: "unreached",
    detail: "the request did not reach the surface; nothing was answered",
    cause: cause === null || cause === undefined ? "" : String(cause?.message ?? cause),
  };
}

/** Which of the two a response body is, by the key that distinguishes them. */
export function viewFor(body, options) {
  if (body && "refusal" in body) return refusalView(body);
  return view(body, options);
}
