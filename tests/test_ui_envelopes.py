"""The envelopes `ui/view.test.mjs` runs against, and the check that they are real.

The UI's tests are JavaScript and the surface is Python, so the fixture between
them is a committed JSON file. That file is the hazard this module exists for:
a hand-written envelope is a second copy of the wire shape, and a generated one
goes stale the first time a key moves.

So `ENVELOPES` below **builds each case through the real surface**, and the
test asserts the committed file equals what the surface produces today. A key
added to either contract, a renamed field, a changed serialization — any of
them fails here rather than leaving `ui/` asserting things about a shape the
system stopped producing.

Regenerate with `EFR_WRITE_UI_ENVELOPES=1 python3 -m unittest
tests.test_ui_envelopes`, and read the diff before committing it.
"""

import json
import os
import pathlib
import re
import unittest

from .discovery_support import BASE, MESSAGE, SIGNAL, database, discovery_row
from .runtime_support import (
    CHASSIS,
    REVISED,
    FakeDatabase,
    candidate_row,
    message_row,
    signal_row,
)

try:
    from fastapi.testclient import TestClient

    from evidence_first_rag.adapter.revalidation import Proposal
    from evidence_first_rag.api.app import Services, create_app, services

    HAS_API = True
except ImportError:  # pragma: no cover - exercised by the extra-free job
    HAS_API = False

# Beside the tests rather than in `ui/`, because everything under `ui/` is
# served to a browser. Nothing here is secret -- every identifier is
# `SAMPLE_*` -- but a test fixture on the public page is a thing a reader
# has to work out the meaning of, and it has no meaning there.
FIXTURE = pathlib.Path(__file__).resolve().parent / "ui_envelopes.json"

PROVENANCE = ("fixtures/registry/approved_entity.jsonl",)
FACT_MESSAGE = BASE | {"message_key": "SAMPLE_MSG_ENGINE_STATUS"}
FACT_SIGNAL = FACT_MESSAGE | {"signal_key": "SAMPLE_SIG_ENGINE_SPEED"}
SELECT_TERM = SIGNAL | {"term": "SAMPLE_SIG_GEAR_POSITION"}

# The two `ambiguous` shapes, which differ by contract and which a screen has to
# read both of. Each names three of the four scope dimensions, so the fourth is
# what `TPL_SNAPSHOT_CANDIDATES_V1` answers with more than one row.
#
# `snapshot_label` is the one left open because `BASE` and `REVISED` differ in
# that dimension and no other: the view model computes which dimension
# distinguishes the scopes, and a pair differing in two would not show that the
# computation found the right one.
OPEN_SNAPSHOT = {name: value for name, value in FACT_MESSAGE.items() if name != "snapshot_label"}
OPEN_SNAPSHOT_TERM = {name: value for name, value in MESSAGE.items() if name != "snapshot_label"}
TWO_SNAPSHOTS = (candidate_row(BASE), candidate_row(REVISED))

# The text `/v1/ask` cases are evaluated against: its four scope values appear
# in it and its message key does not, which is what makes one proposal's
# `verbatim` name all four and the other's name none.
ASK_TEXT = (
    "In SAMPLE_PROJECT_ALPHA SAMPLE_REV_A on SAMPLE_NET_POWERTRAIN"
    " at SAMPLE_SNAP_BASE, what is there?"
)

TWO_SIGNALS = (
    discovery_row(
        entity_kind="signal",
        message_key="SAMPLE_MSG_TRANSMISSION_STATE",
        signal_key="SAMPLE_SIG_GEAR_POSITION",
    ),
    discovery_row(
        entity_kind="signal",
        message_key="SAMPLE_MSG_DIAGNOSTIC_EVENT",
        signal_key="SAMPLE_SIG_FAULT_CODE",
        match_tier=2,
        match_kind="approved_alias",
        match_text="SAMPLE_SIG_GEAR_POSITION",
    ),
)


class Injected:
    """What the adapter returned, supplied by the fixture (Section 8.1)."""

    def __init__(self, proposal):
        self.proposal = proposal

    def propose_with_call(self, request_text):
        return self.proposal, None

    def propose(self, request_text):
        return self.proposal


def _database(rows=None, *, candidates=None, **discovery_rows):
    found = (candidate_row(BASE),) if candidates is None else tuple(candidates)
    db = database(candidates=found, **discovery_rows)
    db.rows.update(rows or {})
    return db


def _client(db, *, proposer=None):
    return TestClient(create_app(services(db, fixture_provenance=PROVENANCE, proposer=proposer)))


def _envelopes():
    """One envelope per obligation the UI has to satisfy, keyed by its name."""
    built = {}

    # Obligations 1, 2 and 7: a fact, its rendered answer, and its rows.
    client = _client(_database({"TPL_SIGNAL_FACTS_V1": (signal_row(),)}))
    built["fact_success"] = client.post(
        "/v1/query", json={"route": "signal_facts", "arguments": FACT_SIGNAL}
    ).text

    # Obligation 5: a negative status, carried through as itself.
    client = _client(_database({"TPL_MESSAGE_FACTS_V1": ()}))
    built["fact_not_found"] = client.post(
        "/v1/query", json={"route": "message_facts", "arguments": FACT_MESSAGE}
    ).text

    # Obligation 5 again, and the step the whole path turns on.
    client = _client(_database({}))
    built["needs_entity_discovery"] = client.post(
        "/v1/query", json={"route": "signal_facts", "arguments": BASE}
    ).text

    # Obligations 1, 3 and 4: the candidate list, and `rendered` null.
    client = _client(_database({}, exact=TWO_SIGNALS))
    built["candidates"] = client.post("/v1/discover", json={"arguments": SELECT_TERM}).text

    # Obligation 3's other discovery outcome: one match resolves, and the tier
    # and matched text that resolved it are what a screen has to show. Without
    # this case `result.resolved` is null in every envelope and the view
    # model's `resolved` branch is asserted by nothing.
    client = _client(_database({}, exact=TWO_SIGNALS[:1]))
    built["discovery_resolved"] = client.post(
        "/v1/discover", json={"arguments": SELECT_TERM}
    ).text

    # A discovery negative: nothing resolved, and no prose about it.
    client = _client(_database({}))
    built["discovery_not_found"] = client.post("/v1/discover", json={"arguments": MESSAGE}).text

    # Obligations 4 and 6: a proposal whose scope values are the person's own
    # words, so a UI may prefill them.
    proposal = Proposal(route="signal_facts", arguments=dict(BASE))
    client = _client(_database({}), proposer=Injected(proposal))
    built["ask_verbatim_scope"] = client.post(
        "/v1/ask", json={"request_text": ASK_TEXT}
    ).text

    # The prohibition: a proposal whose scope values are **not** in the request
    # text. A UI may show them, labelled, and may not put them in the fields.
    invented = {name: f"SAMPLE_INVENTED_{name.upper()}" for name in BASE}
    proposal = Proposal(
        route="message_facts", arguments=invented | {"message_key": "SAMPLE_MSG_ENGINE_STATUS"}
    )
    client = _client(_database({}), proposer=Injected(proposal))
    built["ask_invented_scope"] = client.post(
        "/v1/ask", json={"request_text": ASK_TEXT}
    ).text

    # Obligation 1's "may not omit", over a result carrying **more than one**
    # limitations entry. Without it, a screen that showed the first and dropped
    # the rest would satisfy every other case in this set: the superseded
    # snapshot and the explicit selection are two separate obligations of
    # `mvp-v0.1` Section 7, and a reader shown one of them is told the other
    # did not happen.
    db = _database(
        {
            "TPL_SIGNAL_FACTS_V1": (
                signal_row(
                    message_key="SAMPLE_MSG_TRANSMISSION_STATE",
                    signal_key="SAMPLE_SIG_GEAR_POSITION",
                    superseded_by=CHASSIS,
                ),
            )
        },
        exact=TWO_SIGNALS,
    )
    client = _client(db)
    digest = json.loads(
        client.post("/v1/discover", json={"arguments": SELECT_TERM}).text
    )["result"]["evidence_bundle"]["candidate_set_id"]
    built["selection_two_limitations"] = client.post(
        "/v1/select",
        json={
            "arguments": SELECT_TERM
            | {
                "candidate_set_id": digest,
                "selected_rank": "1",
                "target_route": "signal_facts",
            }
        },
    ).text

    # Obligation 5 over `ambiguous`, in **both** shapes, because the two
    # contracts carry the scopes in different places and a screen that read one
    # of them would print the bare status word for the other.
    #
    # `mvp-v0.1` has no top-level `candidate_scopes`: the scopes are the rows of
    # `TPL_SNAPSHOT_CANDIDATES_V1`, and `source_trace.contributing_scopes`
    # repeats them (`WF-002`).
    client = _client(_database({}, candidates=TWO_SNAPSHOTS))
    built["fact_ambiguous"] = client.post(
        "/v1/query", json={"route": "message_facts", "arguments": OPEN_SNAPSHOT}
    ).text

    # `entity-discovery-v0.1` carries them in a top-level `candidate_scopes` and
    # executes no discovery template (`WF-020`).
    client = _client(_database({}, candidates=TWO_SNAPSHOTS))
    built["discovery_ambiguous"] = client.post(
        "/v1/discover", json={"arguments": OPEN_SNAPSHOT_TERM}
    ).text

    # `mvp-v0.1` Section 5: "One matching candidate is still `ambiguous`."
    # Without this case every `ambiguous` envelope carries two scopes, and a
    # screen saying "this does not resolve to a single snapshot" while listing
    # exactly one passes every other assertion in the set (`FX-113`, `DX-011`).
    client = _client(_database({}, candidates=(candidate_row(BASE),)))
    built["fact_ambiguous_one_scope"] = client.post(
        "/v1/query", json={"route": "message_facts", "arguments": OPEN_SNAPSHOT}
    ).text

    # Section 5 again: zero matching candidates is `coverage_gap`, not
    # `ambiguous`. No envelope reached this status before, so the sentence the
    # page shows for it was asserted by nothing.
    client = _client(_database({}, candidates=()))
    built["fact_coverage_gap"] = client.post(
        "/v1/query", json={"route": "message_facts", "arguments": OPEN_SNAPSHOT}
    ).text

    # `entity-discovery-v0.1` Section 5 `unsupported`: an `entity_kind`
    # outside `message` and `signal` (`DX-014`). The only negative discovery
    # outcome that is **not** `not_found` and still binds a `snapshot_label`,
    # which is what makes the assertion "no widening is offered on any other
    # status" run at all. Without it that test is green whether or not the
    # rule holds -- the failure shape #101 and #182 are about.
    client = _client(_database({}))
    built["discovery_unsupported"] = client.post(
        "/v1/discover", json={"arguments": MESSAGE | {"entity_kind": "SAMPLE_KIND_OTHER"}}
    ).text

    # `entity-discovery-v0.1` Section 5 `coverage_gap`, which N1 on #196 showed
    # this set could not reach. It matters for two separate reasons, and both
    # were asserted by nothing before: the sentence the page shows for it is
    # only ever shown for *this* vocabulary (an `mvp-v0.1` result carries a
    # Section 4.8 render, so the page writes none), and it is the one negative
    # outcome besides `not_found` that binds a **non-empty** `snapshot_label` --
    # the request named a snapshot, and no snapshot has it.
    client = _client(_database({}, candidates=()))
    built["discovery_coverage_gap"] = client.post(
        "/v1/discover", json={"arguments": MESSAGE | {"snapshot_label": "SAMPLE_SNAP_NONE"}}
    ).text

    # `entity-discovery-v0.1` Section 5 `invalid_request`: an empty term. The
    # other sentence N1 found unexercised, and the other side of the widening
    # rule -- refused before anything binds, so its `snapshot_label` is null.
    client = _client(_database({}))
    built["discovery_invalid_request"] = client.post(
        "/v1/discover", json={"arguments": MESSAGE | {"term": ""}}
    ).text

    # Section 4.5: a refusal, which obligation 5 forbids showing as a result.
    client = _client(_database({}))
    built["refusal"] = client.post("/v1/query", json={"route": "x", "arguments": {}, "y": "z"}).text

    return {name: json.loads(text) for name, text in built.items()}


@unittest.skipUnless(HAS_API, "the api extra is not installed")
class TheCommittedEnvelopesAreWhatTheSurfaceProduces(unittest.TestCase):
    """The one assertion that keeps `ui/`'s tests honest."""

    def test_the_fixture_matches_the_surface(self):
        produced = _envelopes()
        if os.environ.get("EFR_WRITE_UI_ENVELOPES"):  # pragma: no cover - a writer's tool
            FIXTURE.write_text(json.dumps(produced, indent=2, sort_keys=True) + "\n")
        committed = json.loads(FIXTURE.read_text())
        self.assertEqual(
            set(committed),
            set(produced),
            "ui/envelopes.json names a case the surface no longer builds, or the reverse",
        )
        for name in sorted(produced):
            with self.subTest(case=name):
                self.assertEqual(committed[name], produced[name])

    def test_every_case_the_ui_tests_name_is_present(self):
        """`ui/view.test.mjs` reads these by name.

        A rename here and not there leaves a JavaScript test asserting things
        about `undefined`, which passes for several of them. Nothing else
        connects the two files, so this is the join.
        """
        source = (pathlib.Path(__file__).resolve().parents[1] / "ui" / "view.test.mjs").read_text()
        # The lookbehind keeps `./envelopes.json` and `test_ui_envelopes.py`
        # out: a path or an identifier is not a reference to a case.
        named = set(re.findall(r"(?<![\w/])envelopes(?:\.(\w+)|\[\"(\w+)\"\])", source))
        cases = {first or second for first, second in named}
        committed = set(json.loads(FIXTURE.read_text()))
        self.assertTrue(cases, "no envelope is referenced by the UI tests")
        self.assertEqual(
            cases - committed,
            set(),
            "ui/view.test.mjs names an envelope this module does not build",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
