"""The `POST /chat` responses the portfolio site's page tests run against (#275).

`relay-v0.1` Section 8.2 discharges the Section 4.7 page obligations in the
portfolio site's repository, "by tests against registered `POST /chat`
responses". That repository cannot import this one, so the responses cross as a
committed JSON file -- and a hand-written copy is a second copy of the wire
shape, which goes stale the first time a key moves. This module is the same
answer `tests/test_ui_envelopes.py` gives `ui/`: it **builds every case through
the real code** and asserts the committed file equals what that code produces
today.

- Every tool result is `mcp.surface.call` over the same `FakeDatabase` services
  `tests/test_ui_envelopes.py` uses, so the `api-v0.1` envelope inside it is
  the surface's own.
- Every response is `relay.app.create_app` behind a stub Messages API client,
  so `content`, `stop_reason`, `scope_checks`, `relay` and every refusal body
  are the relay's own.

**What is assumed rather than observed** is how the Messages API connector
carries an MCP `CallToolResult` into a `mcp_tool_result` block. The builder
below uses the shape `tests/test_relay.py` stubs: the result's text blocks
under `content`, its `isError` as `is_error`, and no `structuredContent`.
`relay-v0.1` Section 4.2 records that this is not yet observed; the first
deployed `DP-012` run made no tool call. Every model `text` block is authored
stub prose, never model output. The file's `_about` says both.

Regenerate with `EFR_WRITE_RELAY_RESPONSES=1 python3 -m unittest
tests.test_relay_responses`, and read the diff before committing it.
"""

import json
import os
import pathlib
import unittest

from .discovery_support import discovery_row
from .runtime_support import BASE
from .test_ui_envelopes import (
    MESSAGE,
    OPEN_SNAPSHOT_TERM,
    PROVENANCE,
    SELECT_TERM,
    TWO_SIGNALS,
    TWO_SNAPSHOTS,
    _database,
)

try:
    from fastapi.testclient import TestClient

    from evidence_first_rag.api import app as api
    from evidence_first_rag.mcp import surface as mcp
    from evidence_first_rag.relay import app as relay
    from evidence_first_rag.runtime.faults import ConnectionUnavailable

    HAS_RELAY = True
except ImportError:  # pragma: no cover - exercised by the extra-free job
    HAS_RELAY = False

FIXTURE = pathlib.Path(__file__).resolve().parent / "relay_responses.json"

MCP_URL = "https://sample-surface.example/mcp"
ADDRESS = "192.0.2.10"
NOW = 1_790_000_000.0
TOOL_USE_ID = "SAMPLE_TOOL_USE_1"

# A person's words that name all four scope dimensions of `BASE`, so that
# `scope_checks` lists every one of them as `person_stated`.
IN_BASE = (
    "In SAMPLE_PROJECT_ALPHA SAMPLE_REV_A on SAMPLE_NET_POWERTRAIN at SAMPLE_SNAP_BASE"
)
# The same with `snapshot_label` left out: the shape that reaches `ambiguous`.
IN_BASE_OPEN = "In SAMPLE_PROJECT_ALPHA SAMPLE_REV_A on SAMPLE_NET_POWERTRAIN"

ABOUT = {
    "what": (
        "POST /chat request and response bodies for the relay-v0.1 Section 4.7"
        " page obligations, built by tests/test_relay_responses.py through the"
        " real relay and the real /mcp surface."
    ),
    "model_text_is_stub": (
        "Every content block of type text is authored stub prose standing in"
        " for the model. None is model output."
    ),
    "assumed_not_observed": (
        "The mcp_tool_result block shape (the CallToolResult's text blocks"
        " under content, isError as is_error, no structuredContent) is the"
        " shape tests/test_relay.py stubs. relay-v0.1 Section 4.2 records that"
        " the connector's wrapping is not yet observed on a deployed run."
    ),
}


class Unreachable:
    """A database no session can be opened against."""

    def session(self):
        raise ConnectionUnavailable("SAMPLE_DRIVER_MESSAGE")


def person(text):
    return {"role": "user", "content": text}


def text(words):
    return {"type": "text", "text": words}


def discover(arguments, database):
    """One `discover_entity` call and its result, the result from `/mcp`."""
    use = {
        "type": "mcp_tool_use",
        "id": TOOL_USE_ID,
        "name": "discover_entity",
        "server_name": relay.SERVER_NAME,
        "input": {"arguments": dict(arguments)},
    }
    services = api.services(database, fixture_provenance=PROVENANCE)
    result = mcp.call(services, "discover_entity", {"arguments": dict(arguments)})
    carried = {
        "type": "mcp_tool_result",
        "tool_use_id": TOOL_USE_ID,
        "is_error": bool(result.is_error),
        "content": [{"type": "text", "text": block.text} for block in result.content],
    }
    return [use, carried]


class Model:
    """The Messages API client: answers every call with one scripted `content`."""

    def __init__(self, content=None, *, raises=False):
        self.content = content
        self.raises = raises

    def __call__(self, body, headers):
        if self.raises:
            raise RuntimeError("SAMPLE_PROVIDER_FAILURE")
        return {
            "id": "SAMPLE_MESSAGE_ID",
            "type": "message",
            "role": "assistant",
            "model": relay.MODEL,
            "content": json.loads(json.dumps(self.content)),
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 100, "output_tokens": 20},
        }


def relay_client(model, *, ceiling=1000):
    app = relay.create_app(model, mcp_url=MCP_URL, ceiling=ceiling, clock=lambda: NOW)
    return TestClient(app)


def exchange(client, messages, *, method="POST"):
    """One request and what the relay answered, as a page would hold them."""
    body = {"messages": messages}
    headers = {"x-forwarded-for": ADDRESS, "content-type": "application/json"}
    if method == "POST":
        response = client.post(relay.PATH, content=json.dumps(body), headers=headers)
        request = {"method": "POST", "body": body}
    else:
        response = client.request(method, relay.PATH, headers=headers)
        request = {"method": method, "body": None}
    return {"request": request, "http_status": response.status_code, "response": response.json()}


def answered(messages, content, *, obligations, note):
    """A case whose one exchange the relay answers with `content`."""
    return {
        "obligations": obligations,
        "note": note,
        "exchanges": [exchange(relay_client(Model(content)), messages)],
    }


def _conversations():
    built = {}

    # P1, P2, P3: a discovery that resolves, every scope value the person's own,
    # so the resolved reference may be offered as a click. The closing text
    # block states a fact-shaped sentence on purpose: P2 says no `text` block
    # is ever rendered as a fact.
    words = f"{IN_BASE}, which signal is SAMPLE_SIG_GEAR_POSITION?"
    built["resolved_person_stated"] = answered(
        [person(words)],
        [text("Looking that up.")]
        + discover(SELECT_TERM, _database({}, exact=TWO_SIGNALS[:1]))
        + [text("SAMPLE_SIG_GEAR_POSITION is sent every 10 ms.")],
        obligations=["P1", "P2", "P3", "P4a"],
        note="RL-006 and RL-007 shapes; the last text block is fact-shaped stub prose.",
    )

    # P3 and P4a: a candidate list, one candidate reached through an approved
    # alias, every scope value the person's own.
    built["candidates_person_stated"] = answered(
        [person(words)],
        [text("Two entities match.")]
        + discover(SELECT_TERM, _database({}, exact=TWO_SIGNALS)),
        obligations=["P1", "P3", "P4a"],
        note="A candidate list with an approved-alias candidate.",
    )

    # P5, `RL-008`: the person named no scope value, and the call carries four.
    built["candidates_not_person_stated"] = answered(
        [person("Which signal is SAMPLE_SIG_GEAR_POSITION?")],
        [text("Two entities match.")]
        + discover(SELECT_TERM, _database({}, exact=TWO_SIGNALS)),
        obligations=["P5"],
        note="RL-008 shape: all four scope values are not_person_stated.",
    )

    # P5 across turns, `RL-010`: an `ambiguous` result in the first exchange,
    # then a re-call carrying one of its candidate scopes that no person wrote.
    first_words = person(f"{IN_BASE_OPEN}, what is SAMPLE_MSG_ENGINE_STATUS?")
    first = exchange(
        relay_client(
            Model(
                [text("That matches more than one snapshot.")]
                + discover(OPEN_SNAPSHOT_TERM, _database({}, candidates=TWO_SNAPSHOTS))
            )
        ),
        [first_words],
    )
    second_messages = [
        first_words,
        {"role": "assistant", "content": first["response"]["content"]},
        person("Use the first one."),
    ]
    second = exchange(
        relay_client(
            Model(
                [text("Using the first snapshot.")]
                + discover(MESSAGE, _database({}, exact=(discovery_row(),)))
            )
        ),
        second_messages,
    )
    built["ambiguous_then_scope_from_list"] = {
        "obligations": ["P4", "P5"],
        "note": "RL-010 shape: snapshot_label in the second call came from the first result's candidate_scopes.",
        "exchanges": [first, second],
    }

    # P4: each discovery negative, rendered from the result it arrived in.
    negatives = {
        "discovery_not_found": (MESSAGE, _database({})),
        "discovery_coverage_gap": (
            MESSAGE | {"snapshot_label": "SAMPLE_SNAP_NONE"},
            _database({}, candidates=()),
        ),
        "discovery_unsupported": (MESSAGE | {"entity_kind": "SAMPLE_KIND_OTHER"}, _database({})),
        "discovery_invalid_request": (MESSAGE | {"term": ""}, _database({})),
    }
    # The person's words name every scope value the call carries, so each of
    # these is a P4 case and nothing else: a `not_person_stated` dimension here
    # would make the case P5's as well, and a page test reading it could not
    # tell which rule it was exercising.
    for name, (arguments, database) in negatives.items():
        scope = " ".join(arguments[dimension] for dimension in relay.SCOPE_DIMENSIONS)
        built[name] = answered(
            [person(f"In {scope}, what is SAMPLE_MSG_ENGINE_STATUS?")],
            [text("Here is what the lookup returned.")] + discover(arguments, database),
            obligations=["P4", "P4a"],
            note="A negative discovery status, carried through as itself.",
        )

    # P4b, `RL-020`: a tool refusal is a refusal, never an absence.
    built["tool_refusal_database_unavailable"] = answered(
        [person(f"{IN_BASE}, what is SAMPLE_MSG_ENGINE_STATUS?")],
        [text("The lookup did not complete.")] + discover(MESSAGE, Unreachable()),
        obligations=["P4b"],
        note="RL-020 shape: is_error true, a database_unavailable refusal.",
    )

    # P1 alone: a reply with no tool call, the shape the first deployed
    # `DP-012` run observed.
    built["text_only"] = answered(
        [person("What can you look up?")],
        [text("I can find which SAMPLE entity your words refer to.")],
        obligations=["P1"],
        note="No tool call; nothing to render in the evidence region.",
    )
    return built


def _refusals():
    """P7: one body per Section 4.6 refusal kind, each reached for real."""
    reply = [text("S")]
    built = {}
    client = relay_client(Model(reply))
    built["malformed_request"] = exchange(
        client, [person("SAMPLE_A"), {"role": "assistant", "content": reply}]
    )
    built["method_not_allowed"] = exchange(client, None, method="GET")

    turns = []
    for index in range(relay.PERSON_TURN_LIMIT + 1):
        turns.append(person(f"SAMPLE_TURN_{index}"))
        if index < relay.PERSON_TURN_LIMIT:
            turns.append({"role": "assistant", "content": reply})
    built["conversation_limit"] = exchange(client, turns)

    limited = relay_client(Model(reply))
    for _ in range(relay.RATE_WINDOW_LIMIT):
        exchange(limited, [person("SAMPLE_A")])
    built["rate_limited"] = exchange(limited, [person("SAMPLE_A")])

    built["daily_ceiling_reached"] = exchange(
        relay_client(Model(reply), ceiling=0), [person("SAMPLE_A")]
    )
    built["model_unavailable"] = exchange(
        relay_client(Model(raises=True)), [person("SAMPLE_A")]
    )
    return {
        kind: {"obligations": ["P7"], "note": f"The {kind} refusal.", "exchanges": [one]}
        for kind, one in built.items()
    }


def produce():
    return {
        "_about": ABOUT
        | {
            "relay": {"identifier": relay.IDENTIFIER, "version": relay.CONTRACT_VERSION},
            "mcp": {"identifier": mcp.CONTRACT_IDENTIFIER, "version": mcp.CONTRACT_VERSION},
            "api": {"identifier": api.CONTRACT_IDENTIFIER, "version": api.CONTRACT_VERSION},
        },
        "conversations": _conversations(),
        "refusals": _refusals(),
    }


@unittest.skipUnless(HAS_RELAY, "the api extra is not installed")
class TheCommittedResponsesAreWhatTheRelayProduces(unittest.TestCase):
    def test_the_fixture_matches_the_relay(self):
        produced = json.loads(json.dumps(produce()))
        if os.environ.get("EFR_WRITE_RELAY_RESPONSES"):  # pragma: no cover - a writer's tool
            FIXTURE.write_text(json.dumps(produced, indent=2, sort_keys=True) + "\n")
        committed = json.loads(FIXTURE.read_text())
        self.assertEqual(committed["_about"], produced["_about"])
        for group in ("conversations", "refusals"):
            self.assertEqual(set(committed[group]), set(produced[group]), group)
            for name in sorted(produced[group]):
                with self.subTest(group=group, case=name):
                    self.assertEqual(committed[group][name], produced[group][name])


@unittest.skipUnless(HAS_RELAY, "the api extra is not installed")
class TheCasesReachWhatTheyAreNamedFor(unittest.TestCase):
    """A case named for an obligation that does not exercise it passes every
    test on the site's side and proves nothing there. These pin each name to
    the property it stands for."""

    @classmethod
    def setUpClass(cls):
        cls.fixture = json.loads(FIXTURE.read_text())

    def conversation(self, name):
        return self.fixture["conversations"][name]["exchanges"]

    def result_of(self, exchange):
        """The `api-v0.1` envelope inside the exchange's one tool result."""
        blocks = exchange["response"]["content"]
        (carried,) = [block for block in blocks if block["type"] == "mcp_tool_result"]
        return carried, json.loads(carried["content"][-1]["text"])

    def test_every_answered_exchange_is_a_200_with_the_four_keys(self):
        for name, case in self.fixture["conversations"].items():
            for one in case["exchanges"]:
                with self.subTest(case=name):
                    self.assertEqual(one["http_status"], 200)
                    self.assertEqual(
                        set(one["response"]), {"content", "stop_reason", "scope_checks", "relay"}
                    )

    def test_each_named_status_is_the_status_carried(self):
        expected = {
            "resolved_person_stated": "resolved",
            "candidates_person_stated": "candidates",
            "candidates_not_person_stated": "candidates",
            "discovery_not_found": "not_found",
            "discovery_coverage_gap": "coverage_gap",
            "discovery_unsupported": "unsupported",
            "discovery_invalid_request": "invalid_request",
        }
        for name, status in expected.items():
            with self.subTest(case=name):
                _, envelope = self.result_of(self.conversation(name)[0])
                self.assertEqual(envelope["result"]["status"], status)

    def test_every_negative_and_the_tool_refusal_is_wholly_person_stated(self):
        names = (
            "discovery_not_found",
            "discovery_coverage_gap",
            "discovery_unsupported",
            "discovery_invalid_request",
            "tool_refusal_database_unavailable",
        )
        for name in names:
            with self.subTest(case=name):
                (check,) = self.conversation(name)[0]["response"]["scope_checks"]
                self.assertEqual(check["not_person_stated"], [])

    def test_the_candidate_list_carries_an_approved_alias(self):
        _, envelope = self.result_of(self.conversation("candidates_person_stated")[0])
        kinds = [candidate["match_kind"] for candidate in envelope["result"]["candidates"]]
        self.assertIn("approved_alias", kinds)
        self.assertGreater(len(kinds), 1)

    def test_person_stated_and_not(self):
        (stated,) = self.conversation("resolved_person_stated")[0]["response"]["scope_checks"]
        self.assertEqual(sorted(stated["person_stated"]), sorted(relay.SCOPE_DIMENSIONS))
        self.assertEqual(stated["not_person_stated"], [])
        (unstated,) = self.conversation("candidates_not_person_stated")[0]["response"]["scope_checks"]
        self.assertEqual(sorted(unstated["not_person_stated"]), sorted(relay.SCOPE_DIMENSIONS))

    def test_the_scope_taken_from_the_list_is_not_the_persons(self):
        first, second = self.conversation("ambiguous_then_scope_from_list")
        _, envelope = self.result_of(first)
        self.assertEqual(envelope["result"]["status"], "ambiguous")
        listed = {scope["snapshot_label"] for scope in envelope["result"]["candidate_scopes"]}
        self.assertIn(BASE["snapshot_label"], listed)
        # The relay turn is sent back exactly as it was returned.
        self.assertEqual(second["request"]["body"]["messages"][1]["content"], first["response"]["content"])
        (check,) = second["response"]["scope_checks"]
        self.assertEqual(check["not_person_stated"], ["snapshot_label"])

    def test_the_tool_refusal_is_an_error_and_carries_no_status(self):
        carried, body = self.result_of(self.conversation("tool_refusal_database_unavailable")[0])
        self.assertTrue(carried["is_error"])
        self.assertEqual(set(body), {"refusal", "detail"})
        self.assertEqual(body["refusal"], "database_unavailable")

    def test_text_only_carries_no_tool_block(self):
        (one,) = self.conversation("text_only")
        self.assertEqual([block["type"] for block in one["response"]["content"]], ["text"])
        self.assertEqual(one["response"]["scope_checks"], [])

    def test_one_refusal_per_section_4_6_kind(self):
        refusals = self.fixture["refusals"]
        self.assertEqual(set(refusals), set(relay.REFUSALS))
        for kind, case in refusals.items():
            (one,) = case["exchanges"]
            with self.subTest(kind=kind):
                self.assertEqual(one["http_status"], relay.REFUSALS[kind])
                self.assertEqual(one["response"]["refusal"], kind)
                self.assertEqual(set(one["response"]), {"refusal", "detail"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
