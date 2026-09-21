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

/** `entity-discovery-v0.1`'s entry for "nothing was resolved" (obligation 3). */
const NO_REFERENCE_RESOLVED = "no_reference_resolved";

/**
 * Obligation 3: the sentence a candidate list is shown **under**.
 *
 * Taken verbatim from the result's `limitations`, never written here. A page
 * that introduced a list in its own words would be stating something about
 * the candidates that the response does not say -- obligation 2 forbids prose
 * stating a fact where `rendered` is null, and obligation 7 forbids a summary
 * the response does not contain. The page's own text about a list is limited
 * to what is true of the page itself ("None is chosen").
 *
 * `null` when the result carries no such entry, so the page shows nothing
 * rather than a sentence of its own.
 */
export function candidatesNotice(result) {
  const limitations = Array.isArray(result?.limitations) ? result.limitations : [];
  const entry = limitations.find((item) => item?.kind === NO_REFERENCE_RESOLVED);
  return entry ? { kind: entry.kind, detail: entry.detail } : null;
}

/**
 * The four dimensions of a source scope, in `mvp-v0.1` Section 3.6's order.
 *
 * Written here rather than read off a response because the **order** is what
 * this constant supplies, and no response carries one: a JSON object's keys are
 * a set. The names are still checked against what arrives -- every reader below
 * uses `in` or a type test, so a dimension named here and absent from a
 * response is skipped rather than printed as `undefined`.
 *
 * `ui/index.html` imports it instead of keeping its own copy, so the discovery
 * form and the scope list below cannot disagree about what a scope is.
 */
export const SCOPE_DIMENSIONS = ["project_code", "revision_label", "network_name", "snapshot_label"];

/**
 * The scopes an `ambiguous` result resolved to, and which dimension tells them
 * apart (#195 item 1).
 *
 * **`ambiguous` arrives in two shapes and this reads both.**
 * `entity-discovery-v0.1` puts the scopes in a top-level `candidate_scopes`;
 * `mvp-v0.1` has no such key and puts them in `rows`, because there they are
 * the rows of `TPL_SNAPSHOT_CANDIDATES_V1`. `WF-002` and `WF-020` register that
 * difference. A page that read only one of the two would print the bare status
 * word for the other, which is the defect this function exists to remove.
 *
 * `differing` is **computed, never assumed to be `snapshot_label`**: the
 * dimension that fails to resolve is whichever one the request left open, and
 * on this registry a term is ambiguous across `revision_label` too
 * (`SAMPLE_MSG_WHEEL_SPEED` exists in `SAMPLE_REV_A` and `SAMPLE_REV_B`).
 *
 * Nothing is sorted and nothing is dropped. Obligation 7 forbids reordering, so
 * the scopes keep the order they arrived in; obligation 1 forbids omitting, so
 * every dimension of every scope is listed and `differs` marks one rather than
 * hiding the rest. Obligation 3's rule for candidates -- none pre-selected,
 * none highlighted as likely -- is the reason there is no `selected` here and
 * no ordering by anything: these are scopes the runtime reported, and the
 * screen must not prefer one.
 */
export function scopeChoicesOf(result) {
  if (result?.status !== "ambiguous") return null;
  const listed =
    Array.isArray(result?.candidate_scopes) && result.candidate_scopes.length > 0
      ? result.candidate_scopes
      : Array.isArray(result?.rows)
        ? result.rows
        : [];
  if (listed.length === 0) return null;

  const differing = SCOPE_DIMENSIONS.filter((name) => {
    const values = new Set(listed.map((scope) => JSON.stringify(scope?.[name] ?? null)));
    return values.size > 1;
  });

  return {
    differing,
    scopes: listed.map((scope) => ({
      fields: entries(scope).map((field) => ({ ...field, differs: differing.includes(field.key) })),
      // What a person's act on this row writes into the discovery form.
      //
      // With more than one scope listed it is the dimensions that differ, and
      // only those. The rest are what the person already typed, and rewriting
      // those would be the page editing a field nobody asked it to touch.
      //
      // With **exactly one** scope listed it is the scope's own dimensions.
      // `mvp-v0.1` `FX-113` and `entity-discovery-v0.1` `DX-011` register that
      // shape -- a scope the request left open that exactly one snapshot
      // matches is still `ambiguous`, because Section 4.2 forbids the runtime
      // to default a dimension it did not receive -- and there no dimension
      // differs, so the rule above would leave the row with nothing to offer
      // in the one case where every value on it is unambiguous. Every value on
      // a single listed scope is one the runtime returned, which is the
      // condition the owner's reading on #195 turns on.
      //
      // A non-string or empty value fills nothing either way: that reading
      // permits filling a value the runtime returned, and `null` is not one.
      fill: (listed.length > 1 ? differing : SCOPE_DIMENSIONS)
        .filter((name) => typeof scope?.[name] === "string" && scope[name] !== "")
        .map((name) => ({ name, value: scope[name] })),
    })),
  };
}

/**
 * What a status means, as a fixed sentence (#195 item 2).
 *
 * Obligation 5 renders a negative status "as itself" and Charter Section 3.4
 * makes it a result rather than an error. The page printed the status word
 * alone, which reads as an error and says nothing a person can act on.
 *
 * These are **fixed labels**, which obligation 2 admits beside "a field name, a
 * heading, 'no reference was resolved'". Each says what the contract that
 * produced the result means by that status, and nothing else; none states
 * anything about the data. In particular `not_found` does **not** say a match
 * exists in some other scope: a `not_found` response does not carry that, and
 * obligation 7 forbids the page adding what the response does not contain.
 *
 * **One status means a different thing in each vocabulary, so the map is keyed
 * by the contract first.** `mvp-v0.1` Section 5 defines `not_found` as a
 * resolved, covered snapshot in which no row matched the **lookup key**;
 * `entity-discovery-v0.1` Section 5 defines it as one in which no approved
 * entity matched the **term** at any tier. A single sentence covering both has
 * to name a source for one of them that the other never consulted -- and
 * naming the registry on a fact route is exactly the inference the committed
 * `not_in_registry` limitation warns against ("Absence from the approved
 * registry is not absence from the data"). `STATUS_SENTENCE` is the fallback
 * for a contract identifier this page does not recognise, and it names no
 * source at all.
 *
 * **`coverage_gap` asserts no cause.** Both Section 5s define it as coverage
 * the approved data scope does not contain *or cannot be established to
 * contain*, and a sentence naming the first branch states something the
 * response does not carry.
 *
 * **Three statuses are deliberately absent from the map.** `success` and
 * `resolved` carry `rendered`, which obligation 2 makes the answer verbatim;
 * a sentence of the page's own beside it would be prose stating a fact. And
 * `candidates` already has a sentence this contract supplies -- obligation 3
 * shows the list "under the `limitations` entry that says no reference was
 * resolved", which `candidatesNotice` returns from the result's own words. A
 * second sentence written here would sit beside that one, saying the same
 * thing in the page's voice, which is the substitution obligation 3 exists to
 * prevent. The test below found this; it was not reasoned out first.
 */
const STATUS_SENTENCE = new Map([
  ["needs_entity_discovery", "The request named no canonical entity reference, so nothing was looked up."],
  ["ambiguous", "The request did not name one source scope, so nothing was looked up."],
  ["not_found", "The scope resolved to a single snapshot within approved coverage, and nothing in it matched what was looked up."],
  ["coverage_gap", "The coverage this request needs is absent from the approved data scope, or could not be established there, so nothing was looked up."],
  ["unsupported", "No approved contract can express this request, so nothing was looked up."],
  ["invalid_request", "The request did not satisfy the contract it named, so nothing was looked up."],
]);

/**
 * Where the two vocabularies differ, keyed by the contract that produced the
 * result. A contract absent here falls back to `STATUS_SENTENCE`.
 */
const CONTRACT_STATUS_SENTENCE = new Map([
  [
    "mvp-v0.1",
    new Map([
      ["not_found", "The scope resolved to a single snapshot within approved coverage, and no row in it matched the lookup key."],
    ]),
  ],
  [
    "entity-discovery-v0.1",
    new Map([
      ["not_found", "The scope resolved to a single snapshot within approved coverage, and no entry in the approved registry matched the term at any tier."],
    ]),
  ],
]);

/**
 * The clause `ambiguous` gains **only when there is something below to read**.
 *
 * A sentence pointing at a list the page did not draw is a false statement
 * about the page, and `scopeChoicesOf` returns null for an `ambiguous` result
 * that carries neither `candidate_scopes` nor `rows`.
 */
const SCOPES_BELOW = "The scopes it could name are listed below.";

/**
 * The sentence for this result's status, and what the request was bound with.
 *
 * `searched` is the result's own `bound_parameters`, surfaced beside the
 * sentence rather than left inside the disclosure with the rest of the bundle.
 * That is deliberate duplication: for a negative result the first question is
 * what was actually searched for, and obligation 4's rule that the discovery
 * `term` carries the person's **whole request text** makes the answer
 * surprising the first time it is seen. Nothing is added here -- it is the
 * bundle's own mapping, shown twice.
 */
export function statusNotice(result) {
  const status = result?.status ?? null;
  const contract = result?.evidence_bundle?.contract_identifier ?? null;
  const base = CONTRACT_STATUS_SENTENCE.get(contract)?.get(status) ?? STATUS_SENTENCE.get(status);
  if (base === undefined) return null;
  const listsScopes = status === "ambiguous" && scopeChoicesOf(result) !== null;
  return {
    status,
    sentence: listsScopes ? `${base} ${SCOPES_BELOW}` : base,
    searched: entries(result?.evidence_bundle?.bound_parameters),
  };
}

/**
 * The one next action a `not_found` carries (#195 item 2).
 *
 * Item 2 registers two things and the sentence above is only the first of
 * them: a `not_found` screen also offers "one affordance -- clear
 * `snapshot_label` and search again". This is that affordance as a value, so
 * `ui/index.html` draws it and decides nothing about when it exists.
 *
 * **It is an offer to widen the search, and never a claim that widening will
 * find anything.** A `not_found` response establishes nothing about any scope
 * other than the one it resolved, so the returned value names the field to
 * clear and the value being cleared -- both of which the response carries --
 * and says nothing about what another snapshot holds. Obligation 5's "does not
 * retry, rephrase, or discover on the person's behalf" is why it clears a
 * field and stops: the person presses Search.
 *
 * `null` where the bound parameters name no snapshot, because there is then no
 * scope value to drop and a button that changed nothing would be an offer of a
 * next step that is not one.
 */
export function wideningOf(result) {
  if (result?.status !== "not_found") return null;
  const bound = result?.evidence_bundle?.bound_parameters;
  const value = bound === null || typeof bound !== "object" ? undefined : bound.snapshot_label;
  if (typeof value !== "string" || value === "") return null;
  return { clear: ["snapshot_label"], value };
}

/**
 * The evidence that is not behind a disclosure (#195 item 3).
 *
 * Obligation 1 permits collapsing and forbids omitting. `evidenceOf` is
 * unchanged and the disclosure still carries **every** section, so this is a
 * second view of some of those values and never a subset that replaces them:
 * getting this list wrong can show too little here, and cannot omit anything
 * from the screen.
 *
 * Why anything is outside at all: Pew Research measured a click on a source
 * inside an AI summary at about 1% of visits (2025-07-22), so what sits behind
 * a disclosure is in practice not read. The three values chosen are the ones
 * whose absence changes what a reader concludes from the screen alone -- how
 * many rows there are, which snapshot they came from, and what the result says
 * it does not establish. The template identifier and the bound parameters stay
 * inside: they are what a reader checks an answer with, not what they read it
 * with, and `statusNotice` already surfaces the parameters where a negative
 * status makes them the point.
 */
const HEADLINE_KEYS = ["row_count", "candidate_count", "resolved_scope"];

export function headlineOf(result) {
  if (result === null || result === undefined) return null;
  const bundle = result.evidence_bundle ?? null;
  const hasBundle = bundle !== null && typeof bundle === "object";
  const limitations = Array.isArray(result.limitations) ? result.limitations : [];
  return {
    facts: HEADLINE_KEYS.filter((key) => hasBundle && key in bundle).map((key) => ({ key, value: bundle[key] })),
    // Obligation 1 names every `limitations` entry's kind and detail. Outside
    // the disclosure because a limitation is the result telling a reader what
    // it does not establish, which is the one thing a confident-looking answer
    // hides best.
    limitations: limitations.map((entry) => entries(entry)),
  };
}

/**
 * Three requests, as fixed strings (#195 item 4).
 *
 * Not from the survey behind #195 -- the writer's proposal, kept on the owner's
 * record of 2026-09-21. It is the cheapest answer to "the page requires prior
 * understanding": a person who has read no contract has no way to know that
 * this database holds `SAMPLE_*` identifiers and nothing else, and a request
 * naming anything real returns `not_found` correctly and teaches nothing.
 *
 * **Each is a question and nothing more.** None is labelled with what it
 * returns, because the page cannot know: the same string reaches a different
 * status as the registry changes, and a label promising a result would be the
 * page stating a fact no response has produced (obligations 2 and 7). Clicking
 * one fills the Ask field; the person presses Ask.
 */
export const EXAMPLE_REQUESTS = [
  "What is the temperature signal in SAMPLE_PROJECT_ALPHA SAMPLE_REV_A SAMPLE_NET_POWERTRAIN SAMPLE_SNAP_BASE?",
  "Tell me about engine speed in SAMPLE_PROJECT_ALPHA SAMPLE_REV_A SAMPLE_NET_POWERTRAIN",
  "Summarize the overall health of the powertrain network",
];

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
    candidatesNotice: candidatesNotice(result),
    statusNotice: statusNotice(result),
    widening: wideningOf(result),
    headline: headlineOf(result),
    scopeChoices: scopeChoicesOf(result),
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
