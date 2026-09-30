"""`relay-v0.1` Section 8.1: the registered cases `RL-001` to `RL-022`.

Every case runs against a stub Messages API client that returns a registered
`content` array, so no case calls a model, costs money, or varies between
runs. Every identifier is `SAMPLE_*`.

The relay's source is read from disk unconditionally, so `RL-017`'s
prohibition holds in a job without the `api` extra too; the route itself is
driven only where Starlette and its test client are installed.
"""

import copy
import json
import logging
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
RELAY_SERVE = ROOT / "src" / "evidence_first_rag" / "relay" / "serve.py"
RELAY_APP = ROOT / "src" / "evidence_first_rag" / "relay" / "app.py"
CONTRACT = ROOT / "docs" / "contracts" / "relay-v0.1.md"

try:
    from starlette.testclient import TestClient

    from evidence_first_rag.relay import app as relay
    from evidence_first_rag.relay import serve as relay_serve

    HAS_RELAY = True
except ImportError:  # pragma: no cover - exercised by the extra-free job
    HAS_RELAY = False

# The `/mcp` surface, whose served schema fixes the shape of a `discover_entity`
# call. Guarded separately from the relay: `mcp` and `fastapi` are two
# distributions of the one `api` extra, so an install that predates the surface
# can have one without the other.
try:
    from evidence_first_rag.mcp import surface as mcp_surface

    HAS_MCP_SURFACE = True
except ImportError:  # pragma: no cover - exercised by the extra-free job
    HAS_MCP_SURFACE = False

MCP_URL = "https://sample-surface.example/mcp"

# `RL-018`'s registered marker.
LOG_MARKER = "SAMPLE_LOG_MARKER_7Q2"

SCOPE = {
    "project_code": "SAMPLE_PROJECT_ALPHA",
    "revision_label": "SAMPLE_REV_A",
    "network_name": "SAMPLE_NET_POWERTRAIN",
    "snapshot_label": "SAMPLE_SNAP_BASE",
}


def person(text):
    return {"role": "user", "content": text}


def discover_use(arguments, block_id="SAMPLE_TOOL_USE_1"):
    """One `discover_entity` call, in the shape `/mcp` serves.

    `mcp-v0.1` Section 4.1 nests the tool's arguments under `arguments` and
    admits no additional property, so that is where the four scope dimensions
    of Section 4.5 sit. `TheToolCallShape` asserts this block against the
    schema `mcp/surface.py` serves, so the two cannot drift apart.
    """
    return {
        "type": "mcp_tool_use",
        "id": block_id,
        "name": "discover_entity",
        "server_name": "evidence-first-rag",
        "input": {
            "arguments": {
                "entity_kind": "signal",
                "term": "SAMPLE_ALIAS_GEARBOX_STATE",
                **arguments,
            }
        },
    }


def tool_result(document, *, is_error=False, block_id="SAMPLE_TOOL_USE_1"):
    return {
        "type": "mcp_tool_result",
        "tool_use_id": block_id,
        "is_error": is_error,
        "content": [{"type": "text", "text": json.dumps(document)}],
    }


# The envelope the MCP surface really writes (`mcp-v0.1` Section 4.2), not a
# hand-written document: its status is under `result` (#271).
# `tests/test_ui_envelopes.py` keeps this file equal to the surface's output.
AMBIGUOUS = json.loads((ROOT / "tests" / "ui_envelopes.json").read_text(encoding="utf-8"))[
    "discovery_ambiguous"
]

# `RL-006`: text, a call, and its result.
CONTENT = [
    {"type": "text", "text": "Looking that up."},
    discover_use({}),
    tool_result(AMBIGUOUS),
    {"type": "text", "text": "The term is ambiguous; choose a scope on the page."},
]


def stub_response(content=None):
    return {
        "id": "SAMPLE_MESSAGE_ID",
        "type": "message",
        "role": "assistant",
        "model": "claude-haiku-4-5",
        "content": copy.deepcopy(CONTENT if content is None else content),
        "stop_reason": "end_turn",
        "usage": {"input_tokens": 100, "output_tokens": 20},
    }


class Stub:
    """The Messages API client: records each call and answers from a script."""

    def __init__(self, response=None, raises=None):
        self.calls = []
        self.response = stub_response() if response is None else response
        self.raises = raises

    def __call__(self, body, headers):
        self.calls.append((copy.deepcopy(body), dict(headers)))
        if self.raises is not None:
            raise self.raises
        return copy.deepcopy(self.response)


class Clock:
    def __init__(self, now=1_790_000_000.0):
        self.now = now

    def __call__(self):
        return self.now


def section_4_9_text() -> str:
    """The system prompt, read off the contract document."""
    lines = CONTRACT.read_text(encoding="utf-8").splitlines()
    start = lines.index("### 4.9 The system prompt, verbatim")
    quoted = [line for line in lines[start:] if line.startswith("> ")]
    return quoted[0][2:]


class RelayCase(unittest.TestCase):
    def setUp(self):
        if not HAS_RELAY:
            self.skipTest("the api extra is not installed")

    def relay(self, stub=None, *, ceiling=1000, clock=None):
        self.stub = Stub() if stub is None else stub
        self.clock = Clock() if clock is None else clock
        app = relay.create_app(self.stub, mcp_url=MCP_URL, ceiling=ceiling, clock=self.clock)
        return TestClient(app)

    def post(self, client, messages=None, *, raw=None, address="192.0.2.10"):
        headers = {"x-forwarded-for": address, "content-type": "application/json"}
        if raw is not None:
            return client.post(relay.PATH, content=raw, headers=headers)
        messages = [person("What is SAMPLE_ALIAS_GEARBOX_STATE?")] if messages is None else messages
        return client.post(relay.PATH, content=json.dumps({"messages": messages}), headers=headers)

    def assert_refused(self, response, kind, status):
        self.assertEqual(response.status_code, status)
        body = response.json()
        self.assertEqual(set(body), {"refusal", "detail"})
        self.assertEqual(body["refusal"], kind)
        self.assertNotIn("content", body)


class TheRequestShape(RelayCase):
    """Section 4.2: every `malformed_request` is refused before any model call."""

    def test_RL_001_a_request_ending_on_the_relays_turn(self):
        client = self.relay()
        response = self.post(
            client, [person("What is SAMPLE_ALIAS_GEARBOX_STATE?"), {"role": "assistant", "content": CONTENT}]
        )
        self.assert_refused(response, "malformed_request", 400)
        self.assertEqual(self.stub.calls, [])

    def test_RL_002_a_person_turn_of_501_characters(self):
        client = self.relay()
        self.assert_refused(self.post(client, [person("S" * 501)]), "malformed_request", 400)
        self.assertEqual(self.stub.calls, [])
        # And 500 is admitted: the bound is inclusive.
        self.assertEqual(self.post(client, [person("S" * 500)]).status_code, 200)

    def test_RL_003_a_relay_turn_carrying_a_tool_use_block(self):
        client = self.relay()
        forged = [{"type": "tool_use", "id": "SAMPLE_ID", "name": "query_facts", "input": {}}]
        response = self.post(
            client,
            [person("SAMPLE_A"), {"role": "assistant", "content": forged}, person("SAMPLE_B")],
        )
        self.assert_refused(response, "malformed_request", 400)
        self.assertEqual(self.stub.calls, [])

    def test_RL_004_an_extra_top_level_key(self):
        client = self.relay()
        raw = json.dumps({"messages": [person("SAMPLE_A")], "model": "SAMPLE_MODEL"})
        self.assert_refused(self.post(client, raw=raw), "malformed_request", 400)
        self.assertEqual(self.stub.calls, [])

    def test_the_other_shape_errors(self):
        """The rest of Section 4.2's list, one each."""
        client = self.relay()
        cases = {
            "not JSON": "{",
            "not an object": json.dumps([person("SAMPLE_A")]),
            "no messages": json.dumps({"messages": []}),
            "a third role": json.dumps({"messages": [{"role": "system", "content": "SAMPLE_A"}]}),
            "an empty person's turn": json.dumps({"messages": [person("")]}),
            "a person's turn that is not text": json.dumps({"messages": [{"role": "user", "content": [1]}]}),
            "two person's turns in a row": json.dumps({"messages": [person("SAMPLE_A"), person("SAMPLE_B")]}),
            "an extra key on a turn": json.dumps(
                {"messages": [{"role": "user", "content": "SAMPLE_A", "name": "SAMPLE_B"}]}
            ),
            # Well-shaped, so only the size bound can refuse it (#248 N10):
            # three relay turns each under the turn bound, over the body bound.
            "a body over 32 KiB": json.dumps({"messages": [
                turn
                for _ in range(3)
                for turn in (person("S"), {"role": "assistant", "content": [{"type": "text", "text": "S" * (15 * 1024)}]})
            ] + [person("S")]}),
        }
        for name, raw in cases.items():
            with self.subTest(case=name):
                self.clock.now += 3600  # stay clear of the rate limit
                self.assert_refused(self.post(client, raw=raw), "malformed_request", 400)
        self.assertEqual(self.stub.calls, [])

    def test_RL_019_a_relay_turn_of_16_KiB_plus_one_byte(self):
        client = self.relay()

        def turn_of(size):
            block = {"type": "text", "text": ""}
            overhead = len(relay._serialized([block]))
            block["text"] = "S" * (size - overhead)
            content = [block]
            self.assertEqual(len(relay._serialized(content)), size)
            return [person("SAMPLE_A"), {"role": "assistant", "content": content}, person("SAMPLE_B")]

        self.assert_refused(self.post(client, turn_of(16 * 1024 + 1)), "malformed_request", 400)
        self.assertEqual(self.stub.calls, [])
        self.assertEqual(self.post(client, turn_of(16 * 1024)).status_code, 200)

    def test_RL_021_a_relay_turn_carrying_a_maximal_result_is_accepted(self):
        """The relay-turn bound admits a turn carrying one `discover_entity`
        result at `k` = 10, so a candidate can be chosen from it (#248 B1)."""
        from evidence_first_rag.deploy import cost

        text = cost.maximal_tool_result(ROOT / "tests" / "ui_envelopes.json")
        content = [
            discover_use({}),
            {
                "type": "mcp_tool_result",
                "tool_use_id": "SAMPLE_TOOL_USE_1",
                "is_error": False,
                "content": [{"type": "text", "text": text}],
            },
            {"type": "text", "text": "SAMPLE_REPLY"},
        ]
        self.assertGreater(len(relay._serialized(content)), 12 * 1024)
        self.assertLessEqual(len(relay._serialized(content)), relay.RELAY_TURN_MAX_BYTES)
        messages = [person("SAMPLE_A"), {"role": "assistant", "content": content}, person("SAMPLE_B")]
        self.assertEqual(self.post(self.relay(), messages).status_code, 200)
        self.assertEqual(len(self.stub.calls), 1)

    def test_RL_022_a_long_reply_after_a_maximal_result_ends_the_conversation(self):
        """The residual Section 4.2 states (#248 B4): a maximal result leaves
        little of the turn bound for the model's own text, and a reply that
        uses more makes the turn unreturnable."""
        from evidence_first_rag.deploy import cost

        text = cost.maximal_tool_result(ROOT / "tests" / "ui_envelopes.json")
        result = {
            "type": "mcp_tool_result",
            "tool_use_id": "SAMPLE_TOOL_USE_1",
            "is_error": False,
            "content": [{"type": "text", "text": text}],
        }
        base = [discover_use({}), result, {"type": "text", "text": ""}]
        headroom = relay.RELAY_TURN_MAX_BYTES - len(relay._serialized(base))
        # The headroom is well under what `max_tokens` of prose can occupy.
        self.assertLess(headroom, 2 * 1024)
        client = self.relay()
        for reply, expected in (("S" * headroom, 200), ("S" * (headroom + 1), 400)):
            with self.subTest(reply_bytes=len(reply)):
                self.clock.now += 3600  # stay clear of the rate limit
                content = [discover_use({}), result, {"type": "text", "text": reply}]
                messages = [person("SAMPLE_A"), {"role": "assistant", "content": content}, person("SAMPLE_B")]
                self.assertEqual(self.post(client, messages).status_code, expected)


class TheCall(RelayCase):
    """Section 4.3, `RL-005`: the Messages API call, byte for byte."""

    def test_RL_005_the_body_and_the_header(self):
        client = self.relay()
        messages = [person("What is SAMPLE_ALIAS_GEARBOX_STATE?")]
        self.assertEqual(self.post(client, messages).status_code, 200)
        [(body, headers)] = self.stub.calls
        self.assertEqual(
            set(body), {"model", "max_tokens", "system", "messages", "mcp_servers", "tools"}
        )
        self.assertEqual(body["model"], "claude-haiku-4-5")
        self.assertEqual(body["max_tokens"], 1024)
        self.assertEqual(body["messages"], messages)
        self.assertEqual(
            body["mcp_servers"], [{"type": "url", "url": MCP_URL, "name": "evidence-first-rag"}]
        )
        self.assertEqual(headers, {"anthropic-beta": "mcp-client-2025-11-20"})

    def test_RL_005_the_toolset_enables_discover_entity_alone(self):
        client = self.relay()
        self.post(client)
        [(body, _)] = self.stub.calls
        [toolset] = body["tools"]
        self.assertEqual(
            toolset,
            {
                "type": "mcp_toolset",
                "mcp_server_name": "evidence-first-rag",
                "default_config": {"enabled": False},
                "configs": {"discover_entity": {"enabled": True}},
            },
        )

    def test_RL_005_the_system_prompt_is_the_contracts_text(self):
        """Read off the document, so the two cannot drift apart."""
        client = self.relay()
        self.post(client)
        [(body, _)] = self.stub.calls
        self.assertEqual(body["system"], section_4_9_text())

    def test_the_same_request_makes_the_same_call(self):
        """Section 6: the parameters are the same bytes for the same request."""
        client = self.relay()
        self.post(client)
        self.post(client)
        first, second = (json.dumps(body, sort_keys=True) for body, _ in self.stub.calls)
        self.assertEqual(first, second)


class TheResponse(RelayCase):
    """Section 4.4: the response passes through unchanged."""

    def test_RL_006_content_unchanged(self):
        client = self.relay()
        response = self.post(client)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(set(body), {"content", "stop_reason", "scope_checks", "relay"})
        self.assertEqual(body["content"], CONTENT)
        self.assertEqual(body["stop_reason"], "end_turn")
        self.assertEqual(
            body["relay"],
            {"identifier": "relay-v0.1", "version": "0.3.0", "model": "claude-haiku-4-5"},
        )

    def test_RL_020_a_tool_refusal_passes_through(self):
        refused = {"refusal": "database_unavailable", "detail": "SAMPLE_DETAIL"}
        content = [discover_use({}), tool_result(refused, is_error=True)]
        client = self.relay(Stub(stub_response(content)))
        with self.assertLogs("evidence_first_rag.relay", level="INFO") as logs:
            response = self.post(client)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["content"], content)
        [line] = logs.records
        self.assertEqual(json.loads(line.getMessage())["tool_results"], ["database_unavailable"])

    def test_the_version_constant_is_the_one_the_contract_document_declares(self):
        text = CONTRACT.read_text(encoding="utf-8")
        declared = re.search(r"^\*\*Version:\*\* `([^`]+)`", text, re.MULTILINE).group(1)
        self.assertEqual(relay.CONTRACT_VERSION, declared)


class TheScopeCheck(RelayCase):
    """Section 4.5: which scope values the person wrote."""

    def checks_for(self, messages, arguments):
        content = [discover_use(arguments), tool_result(AMBIGUOUS)]
        client = self.relay(Stub(stub_response(content)))
        response = self.post(client, messages)
        self.assertEqual(response.status_code, 200)
        [entry] = response.json()["scope_checks"]
        self.assertEqual(entry["tool_use_id"], "SAMPLE_TOOL_USE_1")
        return entry

    def test_RL_007_the_person_wrote_all_four(self):
        text = "Find SAMPLE_ALIAS_GEARBOX_STATE in " + " ".join(SCOPE.values())
        entry = self.checks_for([person(text)], SCOPE)
        self.assertEqual(entry["person_stated"], list(SCOPE))
        self.assertEqual(entry["not_person_stated"], [])

    def test_RL_008_the_person_wrote_none(self):
        entry = self.checks_for([person("Find SAMPLE_ALIAS_GEARBOX_STATE")], SCOPE)
        self.assertEqual(entry["person_stated"], [])
        self.assertEqual(entry["not_person_stated"], list(SCOPE))

    def test_RL_009_the_boundary_alphabet(self):
        text = "Find SAMPLE_ALIAS_GEARBOX_STATE in SAMPLE_SNAP_BASE_EXTENDED"
        entry = self.checks_for([person(text)], {"snapshot_label": "SAMPLE_SNAP_BASE"})
        self.assertEqual(entry["not_person_stated"], ["snapshot_label"])

    def test_RL_010_a_scope_lifted_from_an_earlier_ambiguous_result(self):
        earlier = [discover_use({}), tool_result(AMBIGUOUS), {"type": "text", "text": "Ambiguous."}]
        messages = [
            person("Find SAMPLE_ALIAS_GEARBOX_STATE"),
            {"role": "assistant", "content": earlier},
            person("The first one, please."),
        ]
        entry = self.checks_for(messages, {"snapshot_label": SCOPE["snapshot_label"]})
        self.assertEqual(entry["not_person_stated"], ["snapshot_label"])

    def test_a_value_in_an_earlier_person_turn_is_the_persons(self):
        messages = [
            person("Find SAMPLE_ALIAS_GEARBOX_STATE in SAMPLE_SNAP_BASE"),
            {"role": "assistant", "content": [{"type": "text", "text": "Which project?"}]},
            person("SAMPLE_PROJECT_ALPHA"),
        ]
        arguments = {"snapshot_label": "SAMPLE_SNAP_BASE", "project_code": "SAMPLE_PROJECT_ALPHA"}
        entry = self.checks_for(messages, arguments)
        self.assertEqual(entry["person_stated"], ["project_code", "snapshot_label"])

    def test_no_entry_for_a_call_to_another_tool(self):
        other = dict(discover_use({}), name="query_facts")
        client = self.relay(Stub(stub_response([other])))
        self.assertEqual(self.post(client).json()["scope_checks"], [])

    def test_a_discover_call_with_no_readable_arguments_lists_no_dimension(self):
        """Section 4.5: only a dimension *present* in the call's `arguments`.

        An `mcp_tool_use` block whose `input` is not the `mcp-v0.1` Section 4.1
        shape is still one of Section 4.3's block types, so it is not
        `model_unavailable` (Section 4.6). It passes through with HTTP 200 and an
        entry whose two lists are empty; the result such a call returns is the
        served schema's `malformed_request`, which Section 5 carries through and
        P4b forbids the page any act on.
        """
        for name, input_value in {
            "the four dimensions at the top level": dict(SCOPE),
            "no input at all": {},
            "arguments that is not an object": {"arguments": "SAMPLE_NOT_AN_OBJECT"},
        }.items():
            with self.subTest(case=name):
                block = dict(discover_use({}), input=input_value)
                refused = tool_result({"refusal": "malformed_request"}, is_error=True)
                content = [block, refused]
                client = self.relay(Stub(stub_response(content)))
                response = self.post(client)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["content"], content)
                self.assertEqual(
                    response.json()["scope_checks"],
                    [
                        {
                            "tool_use_id": "SAMPLE_TOOL_USE_1",
                            "person_stated": [],
                            "not_person_stated": [],
                        }
                    ],
                )


class TheToolCallShape(unittest.TestCase):
    """The stub's `mcp_tool_use` block is the shape `/mcp` actually serves.

    Section 4.5 reads the four scope dimensions out of "the call's
    `arguments`", and `mcp-v0.1` Section 4.1 puts that object one level below
    the block's `input`. A stub that flattened it would let `RL-007` to
    `RL-010` pass over a reader that finds nothing in any real call, so the
    block this module builds is pinned to the served schema.
    """

    def test_the_stub_block_is_the_served_discover_entity_schema(self):
        if not HAS_MCP_SURFACE:
            self.skipTest("the api extra is not installed")
        schema = mcp_surface._SCHEMAS["discover_entity"]
        self.assertEqual(set(schema["properties"]), {"arguments"})
        self.assertEqual(schema["required"], ["arguments"])
        self.assertIs(schema["additionalProperties"], False)
        self.assertEqual(schema["properties"]["arguments"]["additionalProperties"]["type"], "string")
        block_input = discover_use({"snapshot_label": SCOPE["snapshot_label"]})["input"]
        self.assertEqual(set(block_input), {"arguments"})
        self.assertIsInstance(block_input["arguments"], dict)
        for value in block_input["arguments"].values():
            self.assertIsInstance(value, str)

    def test_the_relay_reads_the_dimensions_from_the_nested_object(self):
        if not HAS_RELAY:
            self.skipTest("the api extra is not installed")
        block = discover_use({"snapshot_label": SCOPE["snapshot_label"]})
        arguments = relay.discover_arguments(block)
        self.assertEqual(arguments["snapshot_label"], SCOPE["snapshot_label"])
        # The flat shape the served schema would refuse is not readable.
        flat = dict(block, input=dict(block["input"]["arguments"]))
        self.assertIsNone(relay.discover_arguments(flat))


class TheCaps(RelayCase):
    """Section 4.6: one case per kind, each asserting no model call."""

    def test_RL_011_eleven_person_turns(self):
        client = self.relay()
        messages = []
        for index in range(11):
            messages.append(person(f"SAMPLE_TURN_{index}"))
            if index < 10:
                messages.append({"role": "assistant", "content": [{"type": "text", "text": "S"}]})
        self.assert_refused(self.post(client, messages), "conversation_limit", 422)
        self.assertEqual(self.stub.calls, [])
        # Ten are admitted.
        self.assertEqual(self.post(client, messages[:-2]).status_code, 200)

    def test_RL_012_a_seventh_request_within_60_seconds(self):
        client = self.relay()
        for _ in range(6):
            self.assertEqual(self.post(client).status_code, 200)
            self.clock.now += 9
        self.assert_refused(self.post(client), "rate_limited", 429)
        self.assertEqual(len(self.stub.calls), 6)
        # Another address is not limited by this one.
        self.assertEqual(self.post(client, address="192.0.2.99").status_code, 200)
        # And the window slides: 60 seconds after the first, a request is admitted.
        self.clock.now += 60
        self.assertEqual(self.post(client).status_code, 200)

    def test_RL_013_a_61st_request_in_one_utc_day(self):
        clock = Clock(1_790_035_200.0)  # 00:00 UTC
        client = self.relay(clock=clock)
        for _ in range(60):
            self.assertEqual(self.post(client).status_code, 200)
            clock.now += 61
        self.assert_refused(self.post(client), "rate_limited", 429)
        self.assertEqual(len(self.stub.calls), 60)
        clock.now = 1_790_035_200.0 + 86_400  # the next UTC day
        self.assertEqual(self.post(client).status_code, 200)

    def test_the_client_address_is_the_last_forwarded_entry(self):
        """`deploy-v0.1` Section 4.5: an entry the caller wrote does not move
        the key."""
        client = self.relay()
        for index in range(6):
            forged = f"198.51.100.{index}, 192.0.2.10"
            self.assertEqual(self.post(client, address=forged).status_code, 200)
        self.assert_refused(self.post(client, address="203.0.113.7, 192.0.2.10"), "rate_limited", 429)

    def test_the_client_port_does_not_move_the_key(self):
        """Run 36662412772: App Service appends `address:port`, and the port
        changes per connection. Seven requests from one address on seven
        ports share one window."""
        client = self.relay()
        for port in range(6):
            forged = f"198.51.100.{port}, 192.0.2.10:{50_000 + port}"
            self.assertEqual(self.post(client, address=forged).status_code, 200)
        self.assert_refused(self.post(client, address="192.0.2.10:50999"), "rate_limited", 429)

    def test_the_forwarded_entry_is_read_as_an_address(self):
        cases = {
            "192.0.2.10:50123": "192.0.2.10",
            "192.0.2.10": "192.0.2.10",
            "[2001:db8::1]:50123": "2001:db8::1",
            "2001:db8::1": "2001:db8::1",
        }
        for entry, address in cases.items():
            with self.subTest(entry=entry):
                self.assertEqual(relay._host(entry), address)

    def test_RL_014_a_request_after_the_daily_ceiling(self):
        client = self.relay(ceiling=2)
        self.assertEqual(self.post(client, address="192.0.2.1").status_code, 200)
        self.assertEqual(self.post(client, address="192.0.2.2").status_code, 200)
        self.assert_refused(self.post(client, address="192.0.2.3"), "daily_ceiling_reached", 503)
        self.assertEqual(len(self.stub.calls), 2)

    def test_RL_014_no_ceiling_registered_refuses_everything(self):
        client = self.relay(ceiling=None)
        self.assert_refused(self.post(client), "daily_ceiling_reached", 503)
        self.assertEqual(self.stub.calls, [])

    def test_RL_015_the_stub_raises_or_times_out(self):
        for raised in (RuntimeError("SAMPLE_FAILURE"), TimeoutError()):
            with self.subTest(raised=type(raised).__name__):
                client = self.relay(Stub(raises=raised))
                response = self.post(client)
                self.assert_refused(response, "model_unavailable", 502)
                self.assertNotIn("SAMPLE_FAILURE", response.text)

    def test_RL_016_the_stub_returns_a_tool_use_block(self):
        content = [{"type": "tool_use", "id": "SAMPLE_ID", "name": "query_facts", "input": {}}]
        client = self.relay(Stub(stub_response(content)))
        self.assert_refused(self.post(client), "model_unavailable", 502)

    def test_another_method_is_refused(self):
        client = self.relay()
        for method in ("GET", "PUT", "DELETE", "OPTIONS"):
            with self.subTest(method=method):
                response = client.request(method, relay.PATH)
                self.assert_refused(response, "method_not_allowed", 405)
        self.assertEqual(self.stub.calls, [])


class TheSecretsAreSeparated(unittest.TestCase):
    """Section 4.8, `RL-017`, as far as this repository can observe it.

    The relay's half is a property of its source: `relay/` names no database
    credential or connection setting. The runtime's half -- that the surface
    process holds no Anthropic key -- is a property of the deployed settings,
    because `api-v0.1` Section 4.7 lets the surface read an optional adapter
    key for `/v1/ask`. `deploy-v0.1`'s `DP-003` asserts that half on the
    deployed `surface`.
    """

    FORBIDDEN = ("MVP_RUNTIME_PASSWORD", "MVP_PROVISIONING_PASSWORD", "PGPASSWORD", "PGHOST", "psycopg")

    def test_RL_017_the_relay_names_no_database_credential(self):
        for path in (RELAY_SERVE, RELAY_APP):
            source = path.read_text(encoding="utf-8")
            for name in self.FORBIDDEN:
                with self.subTest(module=path.name, name=name):
                    self.assertNotIn(name, source)

    def test_RL_017_the_relay_builds_from_its_own_keys_alone(self):
        if not HAS_RELAY:
            self.skipTest("the api extra is not installed")
        try:
            import anthropic  # noqa: F401
        except ImportError:
            self.skipTest("the adapter extra is not installed")
        environment = {
            "ANTHROPIC_API_KEY": "SAMPLE_KEY_NOT_A_SECRET",
            "EFR_RELAY_MCP_URL": MCP_URL,
            "EFR_RELAY_DAILY_CEILING": "100",
        }
        saved = list(relay.LOGGER.handlers)
        self.addCleanup(setattr, relay.LOGGER, "handlers", saved)
        relay_serve.build(environment)
        for missing in ("ANTHROPIC_API_KEY", "EFR_RELAY_MCP_URL"):
            with self.subTest(missing=missing):
                partial = {key: value for key, value in environment.items() if key != missing}
                with self.assertRaises(KeyError) as raised:
                    relay_serve.build(partial)
                self.assertIn(missing, str(raised.exception))

    def test_an_unregistered_ceiling_is_none(self):
        if not HAS_RELAY:
            self.skipTest("the api extra is not installed")
        for value in ("", "0", "-1", "ten", "1.5", "\u00b2"):
            with self.subTest(value=value):
                self.assertIsNone(relay_serve.daily_ceiling({"EFR_RELAY_DAILY_CEILING": value}))
        self.assertIsNone(relay_serve.daily_ceiling({}))
        self.assertEqual(relay_serve.daily_ceiling({"EFR_RELAY_DAILY_CEILING": "120"}), 120)


class TheRecords(RelayCase):
    """Section 4.10, `RL-018`."""

    def test_RL_018_no_message_text_in_any_log_line(self):
        marked = [discover_use({"snapshot_label": LOG_MARKER}), tool_result(AMBIGUOUS)]
        marked.append({"type": "text", "text": f"You asked about {LOG_MARKER}."})
        client = self.relay(Stub(stub_response(marked)))
        with self.assertLogs("evidence_first_rag.relay", level="INFO") as logs:
            self.post(client, [person(f"What is {LOG_MARKER}?")])
            self.post(client, [person(LOG_MARKER * 200)])  # malformed: over 500 characters
        self.assertEqual(len(logs.records), 2)
        for record in logs.records:
            self.assertNotIn(LOG_MARKER, record.getMessage())

    def test_the_line_carries_what_section_4_10_lists(self):
        client = self.relay()
        with self.assertLogs("evidence_first_rag.relay", level="INFO") as logs:
            self.post(client)
        [record] = logs.records
        line = json.loads(record.getMessage())
        self.assertEqual(
            set(line),
            {"timestamp", "path", "http_status", "latency_ms", "usage", "tools", "tool_results"},
        )
        self.assertEqual(line["http_status"], 200)
        self.assertEqual(line["usage"], {"input_tokens": 100, "output_tokens": 20})
        self.assertEqual(line["tools"], ["discover_entity"])
        self.assertEqual(line["tool_results"], ["ambiguous"])

    def test_a_status_is_read_under_result_only(self):
        """#271: a status at the envelope's top level is not the result's."""
        decoy = copy.deepcopy(AMBIGUOUS)
        decoy["status"] = "found"
        del decoy["result"]["status"]
        cases = {
            "the real envelope": (tool_result(AMBIGUOUS), "ambiguous"),
            "a top-level decoy only": (tool_result(decoy), "unreadable"),
            "a result that is not an object": (tool_result({"result": "ambiguous"}), "unreadable"),
        }
        for name, (block, expected) in cases.items():
            with self.subTest(name):
                self.assertEqual(relay._tool_result_kind(block), expected)

    def test_a_refusal_is_logged_by_kind(self):
        client = self.relay(ceiling=None)
        with self.assertLogs("evidence_first_rag.relay", level="INFO") as logs:
            self.post(client)
        [record] = logs.records
        line = json.loads(record.getMessage())
        self.assertEqual(line["refusal"], "daily_ceiling_reached")
        self.assertEqual(line["http_status"], 503)


class TheMemoryBounds(RelayCase):
    """Two paths a public route could grow without limit, each bounded."""

    def test_the_body_is_not_read_past_the_bound(self):
        import asyncio

        consumed = []

        class Streaming:
            headers = {}

            async def stream(self):
                for _ in range(1000):
                    consumed.append(1)
                    yield b"S" * 1024

        with self.assertRaises(relay.Refused) as raised:
            asyncio.run(relay.bounded_body(Streaming()))
        self.assertEqual(raised.exception.kind, "malformed_request")
        # 32 KiB is 32 chunks; the 33rd crosses the bound and reading stops.
        self.assertEqual(len(consumed), 33)

    def test_a_declared_length_over_the_bound_is_refused_unread(self):
        import asyncio

        read = []

        class Declared:
            headers = {"content-length": str(32 * 1024 + 1)}

            async def stream(self):
                read.append(1)
                yield b""

        with self.assertRaises(relay.Refused):
            asyncio.run(relay.bounded_body(Declared()))
        self.assertEqual(read, [])

    def test_stale_clients_are_dropped_and_live_windows_kept(self):
        caps = relay.Caps(ceiling=None)
        for index in range(relay.PRUNE_THRESHOLD + 1):
            caps.admit_request(f"198.51.100.{index}", 1000.0)
        for _ in range(6):
            caps.admit_request("192.0.2.10", 1100.0)
        caps.admit_request("192.0.2.11", 1100.0)  # triggers the sweep
        self.assertNotIn("198.51.100.0", caps._recent)
        self.assertLessEqual(len(caps._recent), 2)
        # The live window survived the sweep: a 7th request is still refused.
        with self.assertRaises(relay.Refused):
            caps.admit_request("192.0.2.10", 1100.0)


class TheRecordReachesStandardOutput(RelayCase):
    """Section 4.10 at run time: `serve` wires the record to standard output,
    since nothing else in the served process would emit an `INFO` line."""

    def setUp(self):
        super().setUp()
        self.saved = (list(relay.LOGGER.handlers), relay.LOGGER.level, relay.LOGGER.propagate)
        relay.LOGGER.handlers = [
            h for h in relay.LOGGER.handlers if not getattr(h, "_relay_record", False)
        ]

    def tearDown(self):
        relay.LOGGER.handlers, relay.LOGGER.level, relay.LOGGER.propagate = self.saved

    def test_one_json_line_per_request(self):
        import io

        stream = io.StringIO()
        relay_serve.configure_logging(stream)
        relay_serve.configure_logging(stream)  # idempotent: no second handler
        client = self.relay()
        self.post(client)
        lines = stream.getvalue().splitlines()
        self.assertEqual(len(lines), 1)
        self.assertEqual(json.loads(lines[0])["http_status"], 200)


class TheWire(unittest.TestCase):
    """`RL-005` at the SDK boundary: what the real client puts on the wire.

    The stub cases fix what the relay hands its client. This one fixes what
    the SDK then sends, over a mock transport, so that no SDK default is added
    to the body and the beta header carries exactly the one value.
    """

    def test_the_sdk_sends_the_body_and_the_header_unchanged(self):
        if not HAS_RELAY:
            self.skipTest("the api extra is not installed")
        # `httpx2`, not `httpx`: `anthropic` 1.x is built on `httpx2`, installs
        # it as its own dependency, and refuses an `httpx.Client` outright
        # ("this SDK uses `httpx2`"). So both come with the `adapter` extra,
        # and one guard naming that extra is the true statement.
        try:
            import anthropic  # noqa: F401
            import httpx2
        except ImportError:  # pragma: no cover - exercised by the extra-free job
            self.skipTest("the adapter extra is not installed")
        seen = {}
        answer = stub_response()

        def handler(request):
            seen["beta"] = request.headers.get("anthropic-beta")
            seen["body"] = json.loads(request.content)
            return httpx2.Response(200, json=answer)

        client = httpx2.Client(transport=httpx2.MockTransport(handler))
        call = relay_serve.anthropic_caller("SAMPLE_KEY_NOT_A_SECRET", http_client=client)
        body = relay.call_body([person("SAMPLE_A")], MCP_URL)
        self.assertEqual(call(body, dict(relay.CALL_HEADERS)), answer)
        self.assertEqual(seen["body"], body)
        self.assertEqual(seen["beta"], "mcp-client-2025-11-20")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
