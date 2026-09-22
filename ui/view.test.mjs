/**
 * `api-v0.1` Section 8's row for Section 4.6, and one assertion per obligation.
 *
 * The envelopes are `ui/envelopes.json`, built by the real surface and kept
 * honest by `tests/test_ui_envelopes.py`, which fails if the committed file
 * stops matching what the surface produces. Nothing here writes an envelope by
 * hand: a hand-written one is a second copy of the wire shape, and it agrees
 * with the tests long after it has stopped agreeing with the system.
 *
 * What this cannot reach is `ui/index.html` applying a view model to a page.
 * That gap is why the thin layer is kept small enough to read and why the
 * pull request carries a browser-driven run of the real page.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { describe, it } from "node:test";

import {
  EXAMPLE_REQUESTS,
  FACT_ROUTES,
  SCOPE_DIMENSIONS as EXPORTED_SCOPE_DIMENSIONS,
  answerOf,
  candidatesOf,
  chooseRank,
  discoveryForm,
  evidenceOf,
  maySend,
  proposalOf,
  headlineOf,
  scopeChoicesOf,
  selectionForm,
  statusNotice,
  targetRoutesFor,
  view,
  unreachedView,
  viewFor,
} from "./view.mjs";

// Outside `ui/`, because everything in here is served to a browser and a test
// fixture has no meaning on the page. `tests/test_ui_envelopes.py` builds it
// from the real surface and fails if it stops matching.
const envelopes = JSON.parse(
  readFileSync(new URL("../tests/ui_envelopes.json", import.meta.url), "utf8"),
);

const SCOPE_DIMENSIONS = ["project_code", "revision_label", "network_name", "snapshot_label"];

// The `message` kind, read off an envelope the surface really produced rather
// than typed here. No fixture carries a message-kind **candidate list** — the
// discovery cases that return one return signals — so the list below is built
// locally, which is sound because what it exercises is the map from a kind to
// the routes that kind permits and not the shape of a candidate on the wire.
const MESSAGE_KIND =
  envelopes.discovery_not_found.result.evidence_bundle.bound_parameters.entity_kind;

function messageCandidates() {
  return candidatesOf({ candidates: [{ rank: 1, entity_kind: MESSAGE_KIND }] });
}

/** Every scalar a value contains, flattened, so containment can be asserted. */
function scalars(value, into = []) {
  if (value === null || value === undefined) return into;
  if (Array.isArray(value)) {
    for (const item of value) scalars(item, into);
    return into;
  }
  if (typeof value === "object") {
    for (const key of Object.keys(value)) scalars(value[key], into);
    return into;
  }
  into.push(value);
  return into;
}

/** Every value the view model tells the page to show as a fact. */
function displayed(model) {
  const values = [];
  for (const row of model.rows) for (const field of row) values.push(field.value);
  for (const candidate of model.candidates) {
    for (const field of candidate.fields) scalars(field.value, values);
  }
  for (const section of model.evidence) {
    for (const item of section.items) for (const field of item) scalars(field.value, values);
  }
  if (model.resolved) for (const field of model.resolved) scalars(field.value, values);
  // The three surfaces this slice added, which `ui/index.html` paints and
  // which this helper did not walk until N7 on #196. `api-v0.1` Section 8
  // names the test below as `G2`'s automated evidence, so a value shown on
  // one of them and absent from the result was a fact on screen that the
  // containment check never read.
  //
  // `statusNotice.sentence` is deliberately left out: it is a fixed label,
  // and "the sentence interpolates no value" is where it is governed.
  if (model.headline) {
    for (const fact of model.headline.facts) scalars(fact.value, values);
    for (const entry of model.headline.limitations) {
      for (const field of entry) scalars(field.value, values);
    }
  }
  if (model.statusNotice) {
    for (const field of model.statusNotice.searched) scalars(field.value, values);
  }
  if (model.scopeChoices) {
    for (const scope of model.scopeChoices.scopes) {
      for (const field of scope.fields) scalars(field.value, values);
      for (const entry of scope.fill) scalars(entry.value, values);
    }
  }
  return values.filter((value) => value !== null && value !== undefined && value !== "");
}

describe("obligation 1 — it shows the evidence, and may not omit it", () => {
  it("carries every key of every evidence structure, on every outcome", () => {
    for (const [name, envelope] of Object.entries(envelopes)) {
      if (!("result" in envelope)) continue;
      const sections = evidenceOf(envelope.result);
      const shown = Object.fromEntries(sections.map((section) => [section.key, section]));
      for (const key of ["evidence_bundle", "source_trace", "limitations"]) {
        assert.ok(key in shown, `${name}: ${key} is not shown at all`);
      }
      // Read off the result, so a key added to either contract appears here
      // without this file changing.
      assert.deepEqual(
        shown.evidence_bundle.items[0].map((field) => field.key).sort(),
        Object.keys(envelope.result.evidence_bundle).sort(),
        `${name}: the bundle on screen is not the bundle in the result`,
      );
      assert.deepEqual(
        shown.source_trace.items[0].map((field) => field.key).sort(),
        Object.keys(envelope.result.source_trace).sort(),
        `${name}: the trace on screen is not the trace in the result`,
      );
      assert.equal(
        shown.limitations.items.length,
        envelope.result.limitations.length,
        `${name}: a limitations entry is missing`,
      );
      for (const [index, entry] of envelope.result.limitations.entries()) {
        assert.deepEqual(
          shown.limitations.items[index].map((field) => field.key).sort(),
          Object.keys(entry).sort(),
          `${name}: limitation ${index} lost a key`,
        );
      }
    }
  });

  it("shows every limitations entry, not only the first", () => {
    // The assertion the rest of this suite could not make: every other fixture
    // carries at most one entry, so a screen showing the first and dropping the
    // rest would satisfy all of them. Two obligations of `mvp-v0.1` Section 7
    // land here at once, and a reader shown one is told the other did not
    // happen.
    const envelope = envelopes.selection_two_limitations;
    const entries = envelope.result.limitations;
    assert.ok(entries.length >= 2, "the fixture no longer carries two limitations");
    const shown = evidenceOf(envelope.result).find((section) => section.key === "limitations");
    assert.equal(shown.items.length, entries.length);
    assert.deepEqual(
      shown.items.map((item) => item.find((field) => field.key === "kind").value),
      entries.map((entry) => entry.kind),
    );
  });

  it("shows a discovery result's registry digest, method and per-candidate provenance", () => {
    // The keys Section 4.6 names for a discovery result specifically.
    const model = view(envelopes.candidates);
    const bundle = model.evidence.find((section) => section.key === "evidence_bundle").items[0];
    const keys = bundle.map((field) => field.key);
    for (const key of ["registry_digest", "method_identifier", "candidate_set_id"]) {
      assert.ok(keys.includes(key), `${key} is not on screen`);
    }
    for (const candidate of model.candidates) {
      const fields = candidate.fields.map((field) => field.key);
      for (const key of ["match_tier", "matched_text", "match_kind"]) {
        assert.ok(fields.includes(key), `a candidate does not show ${key}`);
      }
    }
    // The tier-2 candidate's alias provenance reaches the screen.
    const second = model.candidates[1].fields.find((field) => field.key === "alias");
    assert.notEqual(second.value, null, "the alias match shows no alias provenance");
  });
});

describe("obligation 2 — the answer text is `rendered`, verbatim", () => {
  it("is the string the response carried, unaltered", () => {
    const answer = answerOf(envelopes.fact_success);
    assert.equal(answer.kind, "prose");
    assert.equal(answer.text, envelopes.fact_success.rendered);
  });

  it("is no prose at all where `rendered` is null", () => {
    for (const name of ["candidates", "discovery_not_found"]) {
      assert.equal(envelopes[name].rendered, null, `${name} unexpectedly carries prose`);
      assert.deepEqual(answerOf(envelopes[name]), { kind: "none" }, name);
    }
  });

  it("never invents prose for a negative status", () => {
    // `not_found` has a rendered answer because `mvp-v0.1` Section 4.8 renders
    // one; what the UI may not do is write its own.
    const answer = answerOf(envelopes.fact_not_found);
    assert.equal(answer.text, envelopes.fact_not_found.rendered);
  });
});

describe("obligation 3 — a candidate list is not an answer", () => {
  const model = view(envelopes.candidates);

  it("shows every candidate the response carried", () => {
    assert.equal(model.candidates.length, envelopes.candidates.result.candidates.length);
    assert.ok(model.candidates.length >= 2, "the fixture no longer exercises a list");
  });

  it("keeps the response's rank order", () => {
    assert.deepEqual(
      model.candidates.map((candidate) => candidate.rank),
      envelopes.candidates.result.candidates.map((candidate) => candidate.rank),
    );
  });

  it("hides no field of any candidate", () => {
    for (const [index, candidate] of envelopes.candidates.result.candidates.entries()) {
      assert.deepEqual(
        model.candidates[index].fields.map((field) => field.key).sort(),
        Object.keys(candidate).sort(),
      );
    }
  });

  it("carries no selection state before an act, and highlights none as likely", () => {
    for (const candidate of model.candidates) {
      assert.equal(candidate.selected, false);
      assert.equal(candidate.highlighted, false);
    }
    assert.equal(model.selection.chosenRank, null);
  });

  it("shows a resolved outcome whole, with the tier and text that resolved it", () => {
    const resolved = view(envelopes.discovery_resolved);
    assert.equal(resolved.status, "resolved");
    assert.equal(resolved.candidates.length, 0, "a resolved outcome lists no candidates");
    assert.notEqual(resolved.resolved, null);
    // Every key, not a chosen few: obligation 1 applies to this outcome too.
    assert.deepEqual(
      resolved.resolved.map((field) => field.key).sort(),
      Object.keys(envelopes.discovery_resolved.result.resolved).sort(),
    );
    const shown = new Map(resolved.resolved.map((field) => [field.key, field.value]));
    assert.equal(shown.get("match_tier"), envelopes.discovery_resolved.result.resolved.match_tier);
    assert.equal(
      shown.get("matched_text"),
      envelopes.discovery_resolved.result.resolved.matched_text,
    );
    // And nothing is offered to select against an outcome with no list.
    assert.equal(resolved.selection, null);
  });

  it("introduces the list in the result's words, and never in its own", () => {
    // Obligation 3 names what a candidate list is shown under, and obligations
    // 2 and 7 forbid the page adding a sentence of its own about the data. The
    // notice is therefore an equality with the result, not a string here.
    const entry = envelopes.candidates.result.limitations.find(
      (item) => item.kind === "no_reference_resolved",
    );
    assert.ok(entry, "the fixture no longer carries the entry obligation 3 names");
    assert.deepEqual(model.candidatesNotice, { kind: entry.kind, detail: entry.detail });
    // And an outcome without that entry gets no notice rather than an invented
    // one: a page with nothing to quote says nothing.
    assert.equal(view(envelopes.fact_success).candidatesNotice, null);
  });

  it("shows the limitation that says nothing was resolved", () => {
    assert.ok(envelopes.candidates.result.limitations.length > 0);
    const section = model.evidence.find((s) => s.key === "limitations");
    assert.equal(section.items.length, envelopes.candidates.result.limitations.length);
  });
});

describe("obligation 4 — a selection is a person's act, and a prefilled field is not", () => {
  it("sends no selection until a rank and a route are both chosen", () => {
    const form = selectionForm({ candidates: view(envelopes.candidates).candidates });
    assert.equal(maySend(form), false, "sendable with nothing chosen");
    assert.equal(maySend(chooseRank(form, 1)), false, "sendable with no route");
    // The rank withdrawn from a form that had one, so the route on it is a
    // permitted value and the missing rank is the only defect left.
    assert.equal(
      maySend({ ...chooseRank(form, 1), chosenRank: null, chosenTargetRoute: "signal_facts" }),
      false,
      "sendable with no rank",
    );
    assert.equal(
      maySend({ ...chooseRank(form, 1), chosenTargetRoute: "signal_facts" }),
      true,
    );
  });

  it("offers `target_route` with no default, for a signal candidate or any other", () => {
    const form = selectionForm({ candidates: view(envelopes.candidates).candidates });
    assert.equal(form.chosenTargetRoute, null);
    // Empty before an act: which routes are permitted is the chosen
    // candidate's property, and nothing is chosen.
    assert.deepEqual(form.targetRoutes, []);
    for (const rank of form.ranks) {
      assert.equal(chooseRank(form, rank).chosenTargetRoute, null, `rank ${rank} carries a default`);
    }
  });

  it("offers a signal candidate exactly the two routes its kind permits", () => {
    // The fixture's candidates are signals, where two routes are permitted and
    // `entity-discovery-v0.1` Section 4.8 makes the choice the caller's.
    for (const candidate of envelopes.candidates.result.candidates) {
      assert.equal(candidate.entity_kind, "signal");
    }
    const form = selectionForm({ candidates: view(envelopes.candidates).candidates });
    for (const rank of form.ranks) {
      assert.deepEqual(chooseRank(form, rank).targetRoutes, ["signal_facts", "signal_mapping"]);
    }
  });

  it("offers a message candidate exactly `message_facts`", () => {
    // `entity-discovery-v0.1` Section 4.8 step 6 refuses a `message` candidate
    // dispatched to a signal route (`DX-021`), so offering one would be
    // offering an option the selection path refuses.
    const form = selectionForm({ candidates: messageCandidates() });
    assert.deepEqual(chooseRank(form, 1).targetRoutes, ["message_facts"]);
    assert.equal(chooseRank(form, 1).chosenTargetRoute, null);
  });

  it("never offers a route outside the three, and none at all for a kind it does not know", () => {
    // The map adds no route name of its own: its union is `mvp-v0.1`'s three.
    const offered = [...targetRoutesFor(MESSAGE_KIND), ...targetRoutesFor("signal")];
    assert.deepEqual([...new Set(offered)].sort(), [...FACT_ROUTES].sort());
    assert.deepEqual(targetRoutesFor("SAMPLE_NOT_A_KIND"), []);
    assert.deepEqual(targetRoutesFor(null), []);
  });

  it("will not send a route the chosen candidate does not permit", () => {
    // The guard behind the offer: a value that reached the form some other way
    // is still not sendable.
    const message = selectionForm({ candidates: messageCandidates() });
    assert.equal(
      maySend({ ...chooseRank(message, 1), chosenTargetRoute: "signal_facts" }),
      false,
      "a message candidate was sendable to a signal route",
    );
    const signal = selectionForm({ candidates: view(envelopes.candidates).candidates });
    assert.equal(
      maySend({ ...chooseRank(signal, 1), chosenTargetRoute: "message_facts" }),
      false,
      "a signal candidate was sendable to the message route",
    );
  });

  it("drops a route chosen for another candidate when the rank changes", () => {
    const form = selectionForm({ candidates: view(envelopes.candidates).candidates });
    const chosen = { ...chooseRank(form, 1), chosenTargetRoute: "signal_mapping" };
    assert.equal(maySend(chosen), true);
    assert.equal(chooseRank(chosen, 2).chosenTargetRoute, null);
    assert.equal(maySend(chooseRank(chosen, 2)), false);
  });

  it("puts the person's own request text in the term field", () => {
    const form = discoveryForm({ requestText: "SAMPLE_WHAT_I_TYPED", scopeDimensions: SCOPE_DIMENSIONS });
    const term = form.fields.find((field) => field.name === "term");
    assert.equal(term.value, "SAMPLE_WHAT_I_TYPED");
    assert.equal(term.editable, true);
  });

  it("prefills a scope dimension only from a value named in `proposal.verbatim`", () => {
    const proposal = proposalOf(envelopes.ask_verbatim_scope);
    assert.ok(proposal.verbatim.length > 0, "the fixture no longer has a verbatim value");
    const form = discoveryForm({
      requestText: "SAMPLE_TEXT",
      proposal,
      scopeDimensions: SCOPE_DIMENSIONS,
    });
    for (const dimension of SCOPE_DIMENSIONS) {
      const field = form.fields.find((f) => f.name === dimension);
      if (proposal.verbatim.includes(dimension)) {
        const argument = proposal.arguments.find((a) => a.name === dimension);
        assert.equal(field.value, argument.value, `${dimension} was not prefilled`);
      }
    }
  });

  it("never prefills a scope dimension from a value outside it", () => {
    const proposal = proposalOf(envelopes.ask_invented_scope);
    assert.deepEqual(proposal.verbatim, [], "the fixture no longer has invented values");
    const form = discoveryForm({
      requestText: "SAMPLE_TEXT",
      proposal,
      scopeDimensions: SCOPE_DIMENSIONS,
    });
    for (const dimension of SCOPE_DIMENSIONS) {
      const field = form.fields.find((f) => f.name === dimension);
      assert.equal(field.value, "", `${dimension} carries an unverified value`);
      // Shown beside the field, labelled, never in it.
      assert.notEqual(field.offered, null, `${dimension} hides the adapter's proposal entirely`);
      assert.match(field.offered.label, /not in your request/);
    }
  });

  it("leaves every field editable and submits nothing by itself", () => {
    const form = discoveryForm({ requestText: "x", scopeDimensions: SCOPE_DIMENSIONS });
    assert.equal(form.submitted, false);
    for (const field of form.fields) assert.equal(field.editable, true);
    assert.equal(selectionForm({ candidates: [] }).submitted, false);
  });
});

describe("obligation 5 — a negative status is rendered as itself", () => {
  it("carries the status the response produced, for every fixture", () => {
    for (const [name, envelope] of Object.entries(envelopes)) {
      if (!("result" in envelope)) continue;
      assert.equal(view(envelope).status, envelope.result.status, name);
    }
  });

  it("reaches every negative family in the fixture set", () => {
    const statuses = new Set(
      Object.values(envelopes)
        .filter((envelope) => "result" in envelope)
        .map((envelope) => envelope.result.status),
    );
    for (const status of ["not_found", "needs_entity_discovery", "invalid_request"]) {
      assert.ok(statuses.has(status), `no fixture reaches ${status}`);
    }
  });

  it("does not present a surface refusal as a result", () => {
    const model = viewFor(envelopes.refusal);
    assert.equal(model.kind, "refusal");
    assert.equal(model.status, undefined, "a refusal was given a status family");
    assert.equal(model.refusal, envelopes.refusal.refusal);
    assert.equal(viewFor(envelopes.fact_success).kind, "result");
  });

  it("is a third kind again when the request never reached the surface", () => {
    const unreached = unreachedView(new TypeError("Failed to fetch"));
    // Not a result and not a Section 4.5 refusal: no status family, no refusal
    // kind, and nothing a reader could mistake for either.
    assert.equal(unreached.kind, "unreached");
    assert.equal(unreached.status, undefined);
    assert.equal(unreached.refusal, undefined);
    assert.equal(unreached.result, undefined);
    assert.match(unreached.detail, /nothing was answered/);
    // The cause is text for a reader, never a value anything branches on.
    assert.equal(unreached.cause, "Failed to fetch");
    assert.equal(unreachedView(undefined).cause, "");
    // And the three kinds are distinct, which is what lets the page tell them
    // apart without reading a status.
    assert.deepEqual(
      new Set([unreached.kind, viewFor(envelopes.refusal).kind, viewFor(envelopes.fact_success).kind]),
      new Set(["unreached", "refusal", "result"]),
    );
  });
});

describe("obligation 6 — `proposal` is shown as a proposal", () => {
  it("is labelled as the adapter's output and absent where the route carries none", () => {
    const proposal = proposalOf(envelopes.ask_verbatim_scope);
    assert.match(proposal.label, /adapter/);
    assert.equal(proposalOf(envelopes.fact_success), null);
    assert.equal(view(envelopes.candidates).proposal, null);
  });

  it("marks which of its values the person's own words carried", () => {
    const verified = proposalOf(envelopes.ask_verbatim_scope);
    const invented = proposalOf(envelopes.ask_invented_scope);
    assert.ok(verified.arguments.some((argument) => argument.verbatim));
    assert.ok(invented.arguments.every((argument) => !argument.verbatim));
  });
});

describe("obligation 7 — it adds no value the response does not contain", () => {
  it("every value shown as a fact is present in the result (check E1, applied)", () => {
    for (const [name, envelope] of Object.entries(envelopes)) {
      if (!("result" in envelope)) continue;
      const present = new Set(scalars(envelope.result).map(String));
      for (const value of displayed(view(envelope))) {
        assert.ok(
          present.has(String(value)),
          `${name}: the screen shows ${JSON.stringify(value)}, which the result does not contain`,
        );
      }
    }
  });

  it("reorders no row and no candidate", () => {
    const model = view(envelopes.fact_success);
    assert.deepEqual(
      model.rows.map((row) => row.map((field) => field.value)),
      envelopes.fact_success.result.rows.map((row) =>
        Object.keys(row).sort().map((key) => row[key]),
      ),
    );
  });

  it("converts no unit and rounds no number", () => {
    // A `numeric` column travels as its stored decimal text (Section 4.4), and
    // what reaches the screen is that text rather than a parsed number.
    const row = envelopes.fact_success.result.rows[0];
    const shown = view(envelopes.fact_success).rows[0];
    for (const key of ["scale_factor", "scale_offset"]) {
      if (!(key in row)) continue;
      const field = shown.find((f) => f.key === key);
      assert.equal(field.value, row[key]);
      assert.equal(typeof field.value, typeof row[key]);
    }
  });
});

/** Every status word the two vocabularies use, as the fixture carries them. */
function statusesInFixture() {
  return Object.values(envelopes)
    .filter((envelope) => "result" in envelope)
    .map((envelope) => envelope.result.status);
}

describe("#195 item 1 — an `ambiguous` result lists the scopes it resolved to", () => {
  it("reads both shapes, because the two contracts carry the scopes elsewhere", () => {
    // `mvp-v0.1` has no top-level `candidate_scopes`; the scopes are the rows
    // of `TPL_SNAPSHOT_CANDIDATES_V1` (`WF-002`). `entity-discovery-v0.1` has
    // the key and no rows (`WF-020`). A reader of one shape alone prints the
    // bare status word for the other, which is the defect #195 is about.
    const fromRows = envelopes.fact_ambiguous.result;
    const fromKey = envelopes.discovery_ambiguous.result;
    assert.equal("candidate_scopes" in fromRows, false);
    assert.equal("rows" in fromKey, false);
    for (const result of [fromRows, fromKey]) {
      const choices = scopeChoicesOf(result);
      assert.ok(choices, "an ambiguous result lists no scopes");
      assert.equal(choices.scopes.length, 2);
    }
  });

  it("marks the dimension that differs, and no dimension that does not", () => {
    // Computed, never assumed: the open dimension is whichever one the request
    // left out, and on this registry a term can be ambiguous across
    // `revision_label` too.
    for (const name of ["fact_ambiguous", "discovery_ambiguous"]) {
      const choices = scopeChoicesOf(envelopes[name].result);
      assert.deepEqual(choices.differing, ["snapshot_label"], name);
      for (const scope of choices.scopes) {
        for (const field of scope.fields) {
          assert.equal(field.differs, field.key === "snapshot_label", `${name} ${field.key}`);
        }
      }
    }
  });

  it("lists every dimension of every scope, not only the differing one", () => {
    // Obligation 1. A list showing only what differs would tell a reader the
    // scopes are two snapshots and never say of which project or revision.
    for (const name of ["fact_ambiguous", "discovery_ambiguous"]) {
      for (const scope of scopeChoicesOf(envelopes[name].result).scopes) {
        assert.deepEqual(
          scope.fields.map((field) => field.key).sort(),
          [...SCOPE_DIMENSIONS].sort(),
          name,
        );
      }
    }
  });

  it("keeps the order the response carried", () => {
    // Obligation 7 forbids reordering. Asserted against the response's own
    // list rather than an expected order written here.
    const result = envelopes.discovery_ambiguous.result;
    const choices = scopeChoicesOf(result);
    assert.deepEqual(
      choices.scopes.map((scope) => scope.fields.find((f) => f.key === "snapshot_label").value),
      result.candidate_scopes.map((scope) => scope.snapshot_label),
    );
  });

  it("offers to fill the dimensions this request left unbound", () => {
    // The owner's reading on #195: a person's act may fill a value the runtime
    // returned. The unbound ones, not the differing ones -- a single-scope
    // `ambiguous` has nothing differing and is still ambiguous, and offering
    // nothing there would leave that screen with no act at all (B2 on #196).
    // Filling a bound dimension would rewrite what the person typed.
    for (const name of ["fact_ambiguous", "discovery_ambiguous", "fact_ambiguous_one_scope"]) {
      const result = envelopes[name].result;
      const choices = scopeChoicesOf(result);
      assert.deepEqual(choices.unbound, ["snapshot_label"], name);
      for (const scope of choices.scopes) {
        assert.deepEqual(scope.fill.map((entry) => entry.name), ["snapshot_label"], name);
        for (const entry of scope.fill) assert.equal(typeof entry.value, "string");
      }
    }
  });

  it("lists the one scope of a single-scope `ambiguous`, with nothing marked", () => {
    // `mvp-v0.1` Section 5: "One matching candidate is still `ambiguous`."
    const choices = scopeChoicesOf(envelopes.fact_ambiguous_one_scope.result);
    assert.equal(choices.scopes.length, 1);
    assert.deepEqual(choices.differing, []);
    for (const field of choices.scopes[0].fields) assert.equal(field.differs, false);
  });

  it("lists the same rows a result carries, so suppressing the rows table hides nothing", () => {
    // `ui/index.html` draws the scope list **instead of** the rows table
    // whenever `scopeChoices` is non-null. That is safe only while the listed
    // scopes are those rows. `scopeChoicesOf` prefers `candidate_scopes` and
    // falls back to `rows`, so a result carrying both would show its rows
    // nowhere outside the disclosure -- and what forbids that combination is
    // `src/evidence_first_rag/runtime/service.py`, a file this suite does not
    // read. N2 on #196: stated here, over the envelopes, in both parts.
    let withRows = 0;
    for (const [name, envelope] of Object.entries(envelopes)) {
      if (!("result" in envelope)) continue;
      const result = envelope.result;
      const carriesScopes = Array.isArray(result.candidate_scopes) && result.candidate_scopes.length > 0;
      const carriesRows = Array.isArray(result.rows) && result.rows.length > 0;
      assert.equal(carriesScopes && carriesRows, false, `${name} carries both`);
      if (result.status !== "ambiguous" || !carriesRows) continue;
      withRows += 1;
      const listed = scopeChoicesOf(result).scopes;
      assert.equal(listed.length, result.rows.length, name);
      for (const [index, scope] of listed.entries()) {
        assert.deepEqual(
          Object.fromEntries(scope.fields.map((field) => [field.key, field.value])),
          result.rows[index],
          `${name} scope ${index}`,
        );
      }
    }
    assert.ok(withRows > 0, "no ambiguous envelope carries rows");
  });

  it("lists nothing for a status that is not `ambiguous`", () => {
    // Without the guard, `fact_success`'s rows become a scope chooser on an
    // answered request -- a screen inviting a choice about a result that
    // already resolved.
    for (const [name, envelope] of Object.entries(envelopes)) {
      if (!("result" in envelope) || envelope.result.status === "ambiguous") continue;
      assert.equal(scopeChoicesOf(envelope.result), null, name);
    }
  });
});

describe("#195 item 2 — a sentence only where the runtime wrote none", () => {
  it("writes nothing where `rendered` carries the answer", () => {
    // Obligation 2. The first version of this slice printed a sentence of the
    // page's own directly above the runtime's Section 4.8 render, and the two
    // disagreed (B1 on #196). Every `mvp-v0.1` result carries a render.
    for (const [name, envelope] of Object.entries(envelopes)) {
      if (!("result" in envelope)) continue;
      if (typeof envelope.rendered !== "string") continue;
      assert.equal(statusNotice(envelope), null, name);
    }
  });

  it("writes one for every status that arrives with no prose at all", () => {
    // The screen the owner met: `/v1/discover` returns `rendered: null`, so
    // without this the page shows a status word and nothing else.
    const carriesItsOwnText = new Set(["candidates", "resolved"]);
    for (const [name, envelope] of Object.entries(envelopes)) {
      if (!("result" in envelope) || typeof envelope.rendered === "string") continue;
      const notice = statusNotice(envelope);
      if (carriesItsOwnText.has(envelope.result.status)) {
        assert.equal(notice, null, name);
      } else {
        assert.ok(notice, `${name} (${envelope.result.status}) has no sentence`);
        assert.equal(notice.status, envelope.result.status);
      }
    }
  });

  it("writes for one vocabulary only, which is what keeps B1 from recurring", () => {
    // **This test asserted nothing until N6 on #196.** It looked for a
    // sentence naming another contract's provenance, and skipped every
    // envelope `statusNotice` returned null for -- which is every `mvp-v0.1`
    // one, since they all carry `rendered`. What survived was all
    // `entity-discovery-v0.1`, and the inner loop then skipped its only
    // entry. Zero assertions ran, and removing the `rendered` guard left it
    // green: the exact recurrence of B1 it was written to catch.
    //
    // Stated directly instead. The sentences are `entity-discovery-v0.1`'s
    // Section 5 conditions, and its `not_found` really is about the registry;
    // the same word on an `mvp-v0.1` fact route would name a source no
    // request consulted. So the rule is which vocabulary may be spoken for at
    // all, and it is asserted over every envelope, in both directions, with
    // the count that makes each side real.
    const DISCOVERY = "entity-discovery-v0.1";
    let spokenFor = 0;
    let silent = 0;
    for (const [name, envelope] of Object.entries(envelopes)) {
      if (!("result" in envelope)) continue;
      const contract = envelope.result.evidence_bundle.contract_identifier;
      const notice = statusNotice(envelope);
      if (contract === DISCOVERY) {
        if (notice !== null) spokenFor += 1;
      } else {
        assert.equal(notice, null, `${name} (${contract}) was given a sentence`);
        silent += 1;
      }
    }
    // The #101 guard: green either way if no envelope reached either side.
    assert.ok(spokenFor > 0, "no discovery envelope is given a sentence");
    assert.ok(silent > 0, "no envelope of another contract is withheld one");

    // And the half that gives the rule its point: this contract's `not_found`
    // is about an approved entity matching a term at a tier, which is true
    // here and false on an `mvp-v0.1` fact route, where `not_found` means no
    // row matched the lookup key and nothing was searched for by term at all.
    // Naming that provenance on the wrong vocabulary is what B1 did, so the
    // two assertions together say why the split matters and not only that it
    // holds.
    const sentence = statusNotice(envelopes.discovery_not_found).sentence;
    for (const word of ["approved entity", "term", "tier"]) {
      assert.ok(sentence.includes(word), `the discovery not_found sentence drops "${word}"`);
    }
    assert.equal(sentence.includes("lookup key"), false);
  });

  it("does not claim an `ambiguous` result lists more than one scope", () => {
    // `mvp-v0.1` Section 5: "One matching candidate is still `ambiguous`."
    // `FX-113` and `DX-011` register that shape (B2 on #196).
    const one = envelopes.fact_ambiguous_one_scope.result;
    assert.equal(one.status, "ambiguous");
    assert.equal(scopeChoicesOf(one).scopes.length, 1);
    for (const [name, envelope] of Object.entries(envelopes)) {
      if (!("result" in envelope) || envelope.result.status !== "ambiguous") continue;
      const notice = statusNotice(envelope);
      if (notice === null) continue;
      for (const word of ["single", "more than one", "two", "several"]) {
        assert.equal(notice.sentence.includes(word), false, `${name}: ${word}`);
      }
    }
  });

  it("names a list below only when one is below", () => {
    // The defect the loop Writer's round-1 fix found: the clause was
    // unconditional, and `scopeChoicesOf` returns null for an `ambiguous`
    // result that lists no scope -- so the sentence pointed at a list that
    // was not on the screen. Asserted in both directions.
    const listing = envelopes.discovery_ambiguous;
    assert.ok(scopeChoicesOf(listing.result));
    assert.ok(statusNotice(listing).sentence.includes("listed below"));

    // The same envelope with its list removed, which is the one input no
    // committed envelope carries. Derived from a real one rather than written,
    // and used only to assert the guard, never as a wire shape.
    const empty = { ...listing, result: { ...listing.result, candidate_scopes: [] } };
    assert.equal(scopeChoicesOf(empty.result), null);
    assert.equal(statusNotice(empty).sentence.includes("listed below"), false);
  });

  it("asserts no cause for `coverage_gap`, which has two", () => {
    // Section 5: coverage the scope "does not contain, or cannot be
    // established to contain". Naming one states what the response does not.
    //
    // Asserted against `discovery_coverage_gap`, the envelope that really
    // reaches this sentence. It was `fact_coverage_gap` with its `rendered`
    // dropped -- an `mvp-v0.1` result, a vocabulary this sentence is never
    // shown for, so the assertion ran on an input the surface never produces
    // (N1 on #196).
    const envelope = envelopes.discovery_coverage_gap;
    assert.equal(envelope.result.status, "coverage_gap");
    assert.equal(envelope.rendered, null);
    assert.ok(statusNotice(envelope).sentence.includes("or cannot be established"));
  });

  it("shows every sentence it holds on some envelope the surface produced", () => {
    // The #101 guard over the map itself. Two entries were reachable in a
    // browser and unreachable in this suite, so their wording was asserted by
    // nothing (N1 on #196). This fails when an entry is added without a case.
    const shown = new Set();
    for (const envelope of Object.values(envelopes)) {
      if (!("result" in envelope)) continue;
      const notice = statusNotice(envelope);
      if (notice !== null) shown.add(notice.status);
    }
    assert.deepEqual(
      [...shown].sort(),
      ["ambiguous", "coverage_gap", "invalid_request", "not_found", "unsupported"],
    );
  });

  it("states nothing the response carries — the sentence interpolates no value", () => {
    for (const [name, envelope] of Object.entries(envelopes)) {
      if (!("result" in envelope)) continue;
      const notice = statusNotice(envelope);
      if (notice === null) continue;
      for (const value of scalars(envelope.result)) {
        if (typeof value !== "string" || value.length < 3) continue;
        assert.equal(notice.sentence.includes(value), false, `${name}: ${value}`);
      }
    }
  });

  it("carries the bound parameters beside the sentence, unchanged", () => {
    const envelope = envelopes.discovery_not_found;
    const notice = statusNotice(envelope);
    assert.deepEqual(
      Object.fromEntries(notice.searched.map((field) => [field.key, field.value])),
      envelope.result.evidence_bundle.bound_parameters,
    );
  });

  it("offers to clear `snapshot_label` on a `not_found` that bound one", () => {
    // #195 item 2's other half, absent from the first version (B3 on #196).
    const envelope = envelopes.discovery_not_found;
    const bound = envelope.result.evidence_bundle.bound_parameters;
    assert.equal(typeof bound.snapshot_label, "string");
    assert.deepEqual(statusNotice(envelope).widen, [
      { name: "snapshot_label", value: bound.snapshot_label },
    ]);
  });

  it("offers a widening exactly where a non-empty `snapshot_label` was bound", () => {
    // Stated over the bound value rather than the status, because the status
    // is not the rule: `ambiguous` and `coverage_gap` bind `snapshot_label` as
    // null -- it is the dimension the request left open -- and
    // `invalid_request` and `unsupported` are refused before anything binds.
    // Asserted in both directions, so neither dropping the offer nor offering
    // it where nothing was bound survives.
    let offered = 0;
    let withheld = 0;
    for (const [name, envelope] of Object.entries(envelopes)) {
      if (!("result" in envelope)) continue;
      const notice = statusNotice(envelope);
      if (notice === null) continue;
      const bound = envelope.result.evidence_bundle.bound_parameters.snapshot_label;
      const expected = typeof bound === "string" && bound !== "";
      assert.equal(notice.widen.length === 1, expected, name);
      if (expected) {
        assert.deepEqual(notice.widen, [{ name: "snapshot_label", value: bound }], name);
        offered += 1;
      } else {
        withheld += 1;
      }
    }
    // The #101 guard: green either way if no envelope reached either side.
    assert.ok(offered > 0, "no envelope offers a widening");
    assert.ok(withheld > 0, "no envelope withholds one");
  });
});

describe("#195 item 3 — some evidence is outside the disclosure", () => {
  it("puts every limitations entry outside, whole", () => {
    // `selection_two_limitations` carries two, and a screen showing one tells
    // a reader the other did not happen.
    const result = envelopes.selection_two_limitations.result;
    const headline = headlineOf(result);
    assert.equal(headline.limitations.length, result.limitations.length);
    assert.ok(headline.limitations.length > 1);
    for (const [index, entry] of headline.limitations.entries()) {
      assert.deepEqual(
        Object.fromEntries(entry.map((field) => [field.key, field.value])),
        result.limitations[index],
      );
    }
  });

  it("puts the row count and the resolved scope outside, where the bundle has them", () => {
    const result = envelopes.fact_success.result;
    const facts = Object.fromEntries(headlineOf(result).facts.map((f) => [f.key, f.value]));
    assert.equal(facts.row_count, result.evidence_bundle.row_count);
    assert.deepEqual(facts.resolved_scope, result.evidence_bundle.resolved_scope);
  });

  it("omits nothing: the disclosure still carries every value the headline shows", () => {
    // Obligation 1 forbids omitting, and this is the assertion that makes the
    // headline a second view rather than a place a value could live alone.
    for (const [name, envelope] of Object.entries(envelopes)) {
      if (!("result" in envelope)) continue;
      const headline = headlineOf(envelope.result);
      const inside = [];
      for (const section of evidenceOf(envelope.result)) {
        for (const item of section.items) for (const field of item) scalars(field.value, inside);
      }
      for (const fact of headline.facts) {
        for (const value of scalars(fact.value)) {
          assert.ok(inside.includes(value), `${name}: ${fact.key} is only outside`);
        }
      }
    }
  });
});

describe("#195 item 4 — the example requests claim nothing", () => {
  it("names no identifier that is not a SAMPLE_ one", () => {
    // Charter Section 11: this repository carries synthetic identifiers only,
    // and the page is served to whoever opens it.
    for (const request of EXAMPLE_REQUESTS) {
      for (const token of request.split(/[^A-Za-z0-9_]+/)) {
        // An identifier, as this repository writes them: it carries an
        // underscore, or it is all upper case. A capital that merely begins an
        // English sentence is neither, and flagging it would make this test
        // about prose rather than about identifiers.
        const isIdentifier =
          token.includes("_") || (token.length > 1 && token === token.toUpperCase());
        if (!isIdentifier) continue;
        assert.ok(token.startsWith("SAMPLE_"), `${request} names ${token}`);
      }
    }
  });

  it("says nothing about what it returns", () => {
    // The page cannot know before a response exists: the same string reaches a
    // different status as the registry changes, so a label promising one would
    // be a fact no response has produced (obligations 2 and 7).
    const statuses = new Set(statusesInFixture());
    assert.ok(statuses.size > 1);
    for (const request of EXAMPLE_REQUESTS) {
      for (const status of statuses) {
        assert.equal(request.includes(status), false, `${request} names ${status}`);
      }
    }
  });

  it("is a list of non-empty strings, and the page holds no other scope list", () => {
    assert.ok(EXAMPLE_REQUESTS.length > 0);
    for (const request of EXAMPLE_REQUESTS) {
      assert.equal(typeof request, "string");
      assert.ok(request.trim().length > 0);
    }
    // The exported dimensions are what `ui/index.html` now imports instead of
    // keeping its own copy; this is the independent statement of what a scope
    // is that keeps the exported one honest.
    assert.deepEqual([...EXPORTED_SCOPE_DIMENSIONS].sort(), [...SCOPE_DIMENSIONS].sort());
  });
});
