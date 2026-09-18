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
  FACT_ROUTES,
  answerOf,
  candidatesOf,
  chooseRank,
  discoveryForm,
  evidenceOf,
  maySend,
  proposalOf,
  selectionForm,
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
