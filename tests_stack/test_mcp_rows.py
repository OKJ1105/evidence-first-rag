"""`mcp-v0.1` Section 8.1: the `MC-*` rows that need no model and no fault,
against the stack's `/mcp`, over HTTP.

`deploy-v0.1` Section 4.8 item 2 runs "the `api-v0.1` `WF-*` and `mcp-v0.1`
`MC-*` equality cases, over HTTPS against `surface`, for every case that needs
no model". `test_workflows.py` is the `WF-*` half, and this module is the
`MC-*` half. It runs wherever that one runs: the `local-stack` CI job and the
deploy job, with `EFR_STACK_URL` naming the surface.

**Equality is checked against the same surface.** Each row issues its
`WF-*` body twice: as a tool call on `/mcp` and as the `/v1` request. It then
asserts that `structuredContent` equals the `/v1` envelope and that `isError`
is false. That comparison is what Section 4.2 registers, and it holds whatever
data is provisioned.

**Not here:**

- `MC-016` and `MC-017` inject a database fault, and a stack has none to
  inject.
- `MC-025` compares the served descriptions byte for byte with the contract
  text, and `tests/test_mcp_surface.py` does that over the same server code.

**Standard library only**, for the reason `test_workflows.py` gives.
"""

import json
import unittest
import urllib.error
import urllib.request

from . import test_workflows as stack

PROTOCOL_VERSION = "2025-06-18"
TOOL_FOR = {"/v1/query": "query_facts", "/v1/discover": "discover_entity", "/v1/select": "select_candidate"}

POWERTRAIN = stack.POWERTRAIN
UNDER_SPECIFIED = stack.UNDER_SPECIFIED
FACT = {"route": "message_facts", "arguments": POWERTRAIN | {"message_key": "SAMPLE_MSG_ENGINE_STATUS"}}
GEAR = POWERTRAIN | {"entity_kind": "signal", "term": "SAMPLE_SIG_GEAR_POSITION"}


def setUpModule():
    stack.setUpModule()


def _post(url, payload, headers):
    request = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request) as response:
            return response.status, dict(response.headers), response.read()
    except urllib.error.HTTPError as refused:
        return refused.code, dict(refused.headers), refused.read()


def _message(raw: bytes):
    """The one JSON-RPC message of a JSON or a single-event SSE answer."""
    text = raw.decode("utf-8")
    if text.lstrip().startswith("{"):
        return json.loads(text)
    data = [line[len("data:"):].strip() for line in text.splitlines() if line.startswith("data:")]
    return json.loads("".join(data))


class Session:
    """A Streamable HTTP client over `urllib`: `initialize`, the initialized
    notification, then requests, echoing a session identifier if one is set."""

    def __init__(self):
        self.url = stack.BASE_URL + "/mcp"
        self.headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
        self.next_id = 1
        self.initialization = self.request("initialize", {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "tests_stack", "version": "0"},
        })
        self.headers["MCP-Protocol-Version"] = self.initialization.get("protocolVersion", PROTOCOL_VERSION)
        status, _, raw = _post(self.url, {"jsonrpc": "2.0", "method": "notifications/initialized"}, self.headers)
        # A notification is accepted with 202 or 200 and no JSON-RPC answer (#258 O1).
        if status not in (200, 202):
            raise AssertionError(f"the initialized notification answered HTTP {status}: {raw[:200]!r}")

    def request(self, method, params):
        payload = {"jsonrpc": "2.0", "id": self.next_id, "method": method, "params": params}
        self.next_id += 1
        status, headers, raw = _post(self.url, payload, self.headers)
        if status != 200:
            raise AssertionError(f"{method} answered HTTP {status}: {raw[:200]!r}")
        session = {name.lower(): value for name, value in headers.items()}.get("mcp-session-id")
        if session:
            self.headers["Mcp-Session-Id"] = session
        message = _message(raw)
        if "error" in message:
            raise AssertionError(f"{method} answered a JSON-RPC error: {message['error']}")
        return message["result"]

    def call(self, tool, arguments):
        return self.request("tools/call", {"name": tool, "arguments": arguments})


class McpCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.session = Session()

    def equal_to_v1(self, path, body):
        """`MC-*` Section 4.2: the tool's `structuredContent` equals `/v1`."""
        code, expected, _ = stack.call(path, body)
        self.assertEqual(code, 200, expected)
        outcome = self.session.call(TOOL_FOR[path], body)
        self.assertFalse(outcome.get("isError"), outcome)
        self.assertEqual(outcome.get("structuredContent"), expected)
        # The last block is the canonical JSON of the same document.
        self.assertEqual(json.loads(outcome["content"][-1]["text"]), expected)
        return outcome


class TheEqualityRows(McpCase):
    """`MC-001`, `MC-002`, `MC-004` to `MC-006`, `MC-014`, `MC-015`, `MC-019` to
    `MC-021` and `MC-024`."""

    def test_mc_001(self):
        outcome = self.equal_to_v1("/v1/query", FACT)
        self.assertEqual(outcome["structuredContent"]["result"]["status"], "success")

    def test_mc_002(self):
        body = {"route": "message_facts", "arguments": UNDER_SPECIFIED | {"message_key": "SAMPLE_MSG_ENGINE_STATUS"}}
        self.assertEqual(self.equal_to_v1("/v1/query", body)["structuredContent"]["result"]["status"], "ambiguous")

    def test_mc_004(self):
        found = self.equal_to_v1(
            "/v1/discover", {"arguments": POWERTRAIN | {"entity_kind": "message", "term": "SAMPLE_MSG_ENGINE_STATUS"}}
        )
        self.assertEqual(found["structuredContent"]["result"]["status"], "resolved")
        # The resolved reference is what answers, as `WF-004` threads it (#258 N1).
        key = found["structuredContent"]["result"]["resolved"]["reference"]["message_key"]
        answered = self.equal_to_v1("/v1/query", {"route": "message_facts", "arguments": POWERTRAIN | {"message_key": key}})
        self.assertEqual(answered["structuredContent"]["result"]["status"], "success")

    def test_mc_005(self):
        """Both of `WF-005`'s bodies (#258 N4)."""
        for kind, term, scope in (
            ("message", "SAMPLE_MSG_DIAGNOSTIC_EVENT", POWERTRAIN),
            ("signal", "SAMPLE_SIG_WHEEL_SPEED_FR", stack.CHASSIS_A),
        ):
            with self.subTest(kind=kind):
                body = {"arguments": scope | {"entity_kind": kind, "term": term}}
                self.assertEqual(
                    self.equal_to_v1("/v1/discover", body)["structuredContent"]["result"]["status"], "not_found"
                )

    def test_mc_006(self):
        body = {"arguments": GEAR | {"candidate_set_id": "b" * 64, "selected_rank": "1", "target_route": "signal_facts"}}
        self.assertEqual(
            self.equal_to_v1("/v1/select", body)["structuredContent"]["result"]["status"], "invalid_request"
        )

    def test_mc_014(self):
        for route in ("entity_discovery", "entity_selection", "SAMPLE_NOT_A_ROUTE"):
            with self.subTest(route=route):
                body = {"route": route, "arguments": FACT["arguments"]}
                self.assertEqual(
                    self.equal_to_v1("/v1/query", body)["structuredContent"]["result"]["status"], "unsupported"
                )

    def test_mc_015(self):
        outside = POWERTRAIN | {"network_name": "SAMPLE_NET_BODY"}
        for path, body in (
            ("/v1/query", {"route": "message_facts", "arguments": outside | {"message_key": "SAMPLE_MSG_ENGINE_STATUS"}}),
            ("/v1/discover", {"arguments": outside | {"entity_kind": "message", "term": "SAMPLE_MSG_ENGINE_STATUS"}}),
        ):
            with self.subTest(path=path):
                self.assertEqual(
                    self.equal_to_v1(path, body)["structuredContent"]["result"]["status"], "coverage_gap"
                )

    def test_mc_019(self):
        body = {"route": "message_facts", "arguments": POWERTRAIN | {"message_key": "SAMPLE_MSG_ABSENT"}}
        self.assertEqual(self.equal_to_v1("/v1/query", body)["structuredContent"]["result"]["status"], "not_found")

    def test_mc_020(self):
        body = {"arguments": UNDER_SPECIFIED | {"entity_kind": "message", "term": "SAMPLE_MSG_TRANSMISSION_STATE"}}
        self.assertEqual(self.equal_to_v1("/v1/discover", body)["structuredContent"]["result"]["status"], "ambiguous")

    def test_mc_021(self):
        body = {"arguments": POWERTRAIN | {"entity_kind": "SAMPLE_NOT_A_KIND", "term": "SAMPLE_MSG_ENGINE_STATUS"}}
        self.assertEqual(
            self.equal_to_v1("/v1/discover", body)["structuredContent"]["result"]["status"], "unsupported"
        )

    def test_mc_024(self):
        body = {"route": "message_facts", "arguments": FACT["arguments"] | {"nonsense": "SAMPLE_X"}}
        self.assertEqual(
            self.equal_to_v1("/v1/query", body)["structuredContent"]["result"]["status"], "invalid_request"
        )


class TheTargetPath(McpCase):
    def test_mc_003_the_three_steps(self):
        """`WF-003` as three tool calls, each equal to `/v1` at its step."""
        first = self.equal_to_v1("/v1/query", {"route": "signal_facts", "arguments": dict(POWERTRAIN)})
        self.assertEqual(first["structuredContent"]["result"]["status"], "needs_entity_discovery")
        second = self.equal_to_v1("/v1/discover", {"arguments": GEAR})
        result = second["structuredContent"]["result"]
        self.assertEqual(result["status"], "candidates")
        selection = GEAR | {
            "candidate_set_id": result["evidence_bundle"]["candidate_set_id"],
            "selected_rank": str(result["candidates"][0]["rank"]),
            "target_route": "signal_facts",
        }
        third = self.equal_to_v1("/v1/select", {"arguments": selection})
        self.assertEqual(third["structuredContent"]["result"]["status"], "success")


class TheSurfaceRows(McpCase):
    def test_mc_011_malformed_arguments_are_refused(self):
        for name, (tool, arguments) in {
            "no arguments key": ("query_facts", {"route": "message_facts"}),
            "an extra key": ("query_facts", {"route": "message_facts", "arguments": {}, "extra": "SAMPLE_X"}),
            "a non-object arguments": ("query_facts", {"route": "message_facts", "arguments": "SAMPLE_X"}),
            # The one non-string value inside `arguments`, on `select_candidate` (#258 N3).
            "a numeric selected_rank": (
                "select_candidate",
                {"arguments": GEAR | {"candidate_set_id": "b" * 64, "selected_rank": 1, "target_route": "signal_facts"}},
            ),
        }.items():
            with self.subTest(case=name):
                outcome = self.session.call(tool, arguments)
                self.assertTrue(outcome.get("isError"), outcome)
                self.assertNotIn("structuredContent", outcome)
                self.assertEqual(json.loads(outcome["content"][0]["text"])["refusal"], "malformed_request")

    def test_mc_012_two_identical_calls_are_identical(self):
        first = self.session.call("query_facts", FACT)
        second = self.session.call("query_facts", FACT)
        self.assertEqual(first, second)

    def test_mc_023_tools_and_no_other_capability(self):
        initialization = self.session.initialization
        self.assertEqual(initialization["serverInfo"]["name"], "mcp-v0.1")
        # A literal, as `test_workflows.py` pins the health contracts (#258 N2).
        self.assertEqual(initialization["serverInfo"]["version"], "0.2.0")
        self.assertEqual(set(initialization["capabilities"]) - {"experimental"}, {"tools"})


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
