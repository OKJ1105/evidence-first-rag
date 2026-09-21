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
  wideningOf,
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

/**
 * The single-scope `ambiguous` shape, derived from the committed two-scope one.
 *
 * `mvp-v0.1` `FX-113` and `entity-discovery-v0.1` `DX-011` register it: a scope
 * dimension the request left open is `ambiguous` even where exactly one
 * snapshot matches, because Section 4.2 forbids the runtime to default a
 * dimension it did not receive. No committed envelope reaches that outcome and
 * this slice may not add one — #195's scope fence is `ui/` only, and
 * `tests/ui_envelopes.json` is built by `tests/test_ui_envelopes.py` from the
 * real surface. Truncating the real list is the nearest honest substitute: it
 * is a shape the surface produced, one row shorter, rather than a second copy
 * of the wire format written here.
 */
function oneScopeAmbiguous(name) {
  const result = envelopes[name].result;
  return "candidate_scopes" in result
    ? { ...result, candidate_scopes: result.candidate_scopes.slice(0, 1) }
    : { ...result, rows: result.rows.slice(0, 1) };
}

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

  it("offers to fill only the dimensions that differ", () => {
    // The owner's reading on #195: a person's act may fill a value the runtime
    // returned. Filling a dimension that does not differ would rewrite what
    // they typed; filling a `null` would put the word null in a field.
    for (const name of ["fact_ambiguous", "discovery_ambiguous"]) {
      for (const scope of scopeChoicesOf(envelopes[name].result).scopes) {
        assert.deepEqual(scope.fill.map((entry) => entry.name), ["snapshot_label"], name);
        for (const entry of scope.fill) assert.equal(typeof entry.value, "string");
      }
    }
  });

  it("lists the one scope an `FX-113` / `DX-011` ambiguity resolves to", () => {
    // The case the two-scope fixtures cannot reach. A list of one has no
    // dimension with more than one value, so nothing differs and nothing is
    // badged — and the row is still listed, because the scope is still the
    // one thing the person has to name.
    for (const name of ["fact_ambiguous", "discovery_ambiguous"]) {
      const choices = scopeChoicesOf(oneScopeAmbiguous(name));
      assert.ok(choices, `${name}: a single-scope ambiguity lists nothing at all`);
      assert.equal(choices.scopes.length, 1, name);
      assert.deepEqual(choices.differing, [], name);
      for (const field of choices.scopes[0].fields) {
        assert.equal(field.differs, false, `${name} ${field.key}`);
      }
    }
  });

  it("offers a single listed scope's own dimensions to fill", () => {
    // Filling only what differs would leave this row with nothing to offer —
    // the affordance disappearing in the one case where every value on it is
    // unambiguous and runtime-returned, which is the condition the owner's
    // reading on #195 turns on.
    for (const name of ["fact_ambiguous", "discovery_ambiguous"]) {
      const scope = scopeChoicesOf(oneScopeAmbiguous(name)).scopes[0];
      assert.deepEqual(
        scope.fill.map((entry) => entry.name).sort(),
        [...SCOPE_DIMENSIONS].sort(),
        name,
      );
      // Each filled value is the row's own, never a value from elsewhere.
      for (const entry of scope.fill) {
        assert.equal(entry.value, scope.fields.find((f) => f.key === entry.name).value, name);
      }
    }
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

describe("#195 item 2 — a status carries the fixed sentence that says what it means", () => {
  it("gives every negative status a sentence, and none to the three that have one", () => {
    // `success` and `resolved` carry `rendered`, which obligation 2 makes the
    // answer verbatim. `candidates` carries the `no_reference_resolved`
    // limitation, which obligation 3 makes the sentence the list is shown
    // under. All three already have their text, and it is the response's.
    const answered = new Set(["success", "resolved", "candidates"]);
    for (const [name, envelope] of Object.entries(envelopes)) {
      if (!("result" in envelope)) continue;
      const notice = statusNotice(envelope.result);
      if (answered.has(envelope.result.status)) {
        assert.equal(notice, null, name);
      } else {
        assert.ok(notice, `${name} (${envelope.result.status}) has no sentence`);
        assert.equal(notice.status, envelope.result.status);
        assert.ok(notice.sentence.length > 0);
      }
    }
  });

  it("states nothing the response carries — the sentence interpolates no value", () => {
    // The hazard obligation 7 names. A sentence that named the term or the
    // scope would read as a claim about them, and the one sentence that must
    // never gain a clause is `not_found`: a match elsewhere is exactly what a
    // `not_found` response does not establish.
    for (const [name, envelope] of Object.entries(envelopes)) {
      if (!("result" in envelope)) continue;
      const notice = statusNotice(envelope.result);
      if (notice === null) continue;
      for (const value of scalars(envelope.result)) {
        if (typeof value !== "string" || value.length < 3) continue;
        assert.equal(notice.sentence.includes(value), false, `${name}: ${value}`);
      }
    }
  });

  it("names no source the result's own contract does not implicate", () => {
    // A sentence that said "the approved registry" for a `mvp-v0.1` fact route
    // would name something that route never consulted, and would invite the
    // inference the committed `not_in_registry` limitation exists to refuse:
    // "Absence from the approved registry is not absence from the data."
    // Obligation 7 makes that a value the response does not contain.
    const SOURCE_WORDS = new Map([
      ["registry", "entity-discovery-v0.1"],
      ["lookup key", "mvp-v0.1"],
    ]);
    for (const [name, envelope] of Object.entries(envelopes)) {
      if (!("result" in envelope)) continue;
      const notice = statusNotice(envelope.result);
      if (notice === null) continue;
      const contract = envelope.result.evidence_bundle.contract_identifier;
      for (const [word, owner] of SOURCE_WORDS) {
        if (!notice.sentence.includes(word)) continue;
        assert.equal(contract, owner, `${name}: the sentence names the ${word}; ${contract} produced it`);
      }
    }
  });

  it("gives the two `not_found` meanings their own sentence", () => {
    // `mvp-v0.1` Section 5: a resolved, covered snapshot in which no row
    // matched the lookup key. `entity-discovery-v0.1` Section 5: one in which
    // no approved entity matched the term at any tier. One sentence covering
    // both is wrong for one of them.
    const fact = statusNotice(envelopes.fact_not_found.result);
    const discovery = statusNotice(envelopes.discovery_not_found.result);
    assert.notEqual(fact.sentence, discovery.sentence);
    assert.ok(fact.sentence.includes("lookup key"), fact.sentence);
    assert.equal(fact.sentence.includes("registry"), false, fact.sentence);
    assert.ok(discovery.sentence.includes("registry"), discovery.sentence);
    // And the page does not contradict the runtime's own prose for the same
    // result: `fact_not_found` carries `rendered`, printed on the same screen.
    assert.match(envelopes.fact_not_found.rendered, /lookup key/);
  });

  it("asserts no cause for `coverage_gap`", () => {
    // Both Section 5s define it as coverage the approved data scope does not
    // contain **or cannot be established to contain**, so a sentence naming
    // the first branch states what the response does not carry. No committed
    // envelope reaches the status and this slice may not add one (#195's scope
    // fence), so the map's own input is supplied here instead.
    for (const contract of ["mvp-v0.1", "entity-discovery-v0.1"]) {
      const notice = statusNotice({
        status: "coverage_gap",
        evidence_bundle: { contract_identifier: contract, bound_parameters: {} },
      });
      assert.ok(notice, `${contract}: coverage_gap has no sentence`);
      assert.match(notice.sentence, /could not be established/);
      assert.equal(notice.sentence.includes("outside"), false, notice.sentence);
    }
  });

  it("claims no count and no dimension for `ambiguous`", () => {
    // `FX-113` lists exactly one scope. A sentence saying the scope "does not
    // resolve to a single snapshot" above a list of one states the opposite of
    // what the screen shows, which is the Milestone 4 `G2` item.
    for (const name of ["fact_ambiguous", "discovery_ambiguous"]) {
      for (const result of [envelopes[name].result, oneScopeAmbiguous(name)]) {
        const sentence = statusNotice(result).sentence;
        for (const word of ["single", "two", "both", "one of", "the ones"]) {
          assert.equal(sentence.includes(word), false, `${name}: "${word}" in ${sentence}`);
        }
        for (const dimension of SCOPE_DIMENSIONS) {
          assert.equal(sentence.includes(dimension), false, `${name}: ${dimension}`);
        }
      }
    }
  });

  it("points below only where there is a list below", () => {
    // `scopeChoicesOf` returns null for an `ambiguous` result carrying neither
    // `candidate_scopes` nor `rows`, and a sentence pointing at a list the page
    // did not draw is a false statement about the page itself.
    assert.match(statusNotice(envelopes.discovery_ambiguous.result).sentence, /listed below/);
    const empty = { ...envelopes.discovery_ambiguous.result, candidate_scopes: [] };
    assert.equal(scopeChoicesOf(empty), null);
    assert.equal(statusNotice(empty).sentence.includes("listed below"), false);
  });

  it("carries the bound parameters beside the sentence, unchanged", () => {
    // Duplication on purpose: for a negative result the first question is what
    // was searched for, and obligation 4 puts the person's whole request text
    // in the discovery `term`.
    const result = envelopes.discovery_not_found.result;
    const notice = statusNotice(result);
    assert.deepEqual(
      Object.fromEntries(notice.searched.map((field) => [field.key, field.value])),
      result.evidence_bundle.bound_parameters,
    );
  });
});

describe("#195 item 2 — a `not_found` offers the widening, and no dead end", () => {
  it("names the snapshot field to clear, where the search was bound to one", () => {
    // Item 2 registers two things: the sentence, and "one affordance — clear
    // `snapshot_label` and search again". This is the second, as a value.
    const widening = wideningOf(envelopes.discovery_not_found.result);
    assert.ok(widening, "a not_found screen offers no next step at all");
    assert.deepEqual(widening.clear, ["snapshot_label"]);
    assert.equal(
      widening.value,
      envelopes.discovery_not_found.result.evidence_bundle.bound_parameters.snapshot_label,
    );
    // Both `not_found` vocabularies reach it, not only the discovery one.
    assert.deepEqual(wideningOf(envelopes.fact_not_found.result).clear, ["snapshot_label"]);
  });

  it("offers nothing where the bound parameters name no snapshot", () => {
    // There is then no scope value to drop, and a button that changed nothing
    // would be an offer of a next step that is not one.
    const result = envelopes.discovery_not_found.result;
    const withBound = (bound) => ({
      ...result,
      evidence_bundle: { ...result.evidence_bundle, bound_parameters: bound },
    });
    const absent = { ...result.evidence_bundle.bound_parameters };
    delete absent.snapshot_label;
    assert.equal(wideningOf(withBound(absent)), null, "a widening with nothing to clear");
    assert.equal(wideningOf(withBound({ ...absent, snapshot_label: null })), null, "null is not a value");
    assert.equal(wideningOf(withBound({ ...absent, snapshot_label: "" })), null, "empty is not a value");
  });

  it("offers nothing on any status but `not_found`", () => {
    // Obligation 5: it is what `not_found` means as a next step, not a control
    // the page shows wherever a snapshot happens to be bound. An `ambiguous`
    // has its scope rows and a `success` has an answer.
    for (const [name, envelope] of Object.entries(envelopes)) {
      if (!("result" in envelope) || envelope.result.status === "not_found") continue;
      assert.equal(wideningOf(envelope.result), null, name);
    }
  });

  it("says nothing about what another snapshot holds", () => {
    // The sentence beside it may not gain a clause either: a match elsewhere
    // is exactly what a `not_found` response does not establish.
    const widening = wideningOf(envelopes.discovery_not_found.result);
    assert.deepEqual(Object.keys(widening).sort(), ["clear", "value"]);
    // And it reaches the page through the view model, not by the page
    // deciding for itself when a next step exists.
    assert.deepEqual(view(envelopes.discovery_not_found).widening, widening);
    assert.equal(view(envelopes.fact_success).widening, null);
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
