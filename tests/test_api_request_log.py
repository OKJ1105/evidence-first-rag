"""`deploy-v0.1` Section 4.7: `surface`'s one JSON line per request (#259).

Driven with a stand-in ASGI app, so no web framework is needed: what is under
test is the wrapper's record, and the record is Section 4.7's.
"""

import asyncio
import json
import logging
import unittest

from evidence_first_rag.api import request_log

MARKER = "SAMPLE_PERSON_WORDS_7Q2"


def respond(status, body, *, chunks=1, raises=None):
    """A stand-in app answering with `body`, split into `chunks` parts."""

    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": status, "headers": []})
        if raises is not None:
            raise raises
        size = max(1, len(body) // chunks)
        parts = [body[i:i + size] for i in range(0, len(body), size)] or [b""]
        for index, part in enumerate(parts):
            await send({"type": "http.response.body", "body": part, "more_body": index < len(parts) - 1})

    return app


def jsonrpc(canonical, *, error_key=None):
    """The `/mcp` answer to a tool call: one JSON-RPC document whose result
    carries `mcp-v0.1` Section 4.2's canonical JSON in its last text block."""
    result = {"content": [{"type": "text", "text": json.dumps(canonical)}]}
    if error_key is not None:
        result[error_key] = True
    return json.dumps({"jsonrpc": "2.0", "id": 1, "result": result}).encode()


class Captured(logging.Handler):
    def __init__(self):
        super().__init__()
        self.lines = []

    def emit(self, record):
        self.lines.append(record.getMessage())


def run(app, path, *, method="POST", query=b""):
    logger = logging.getLogger(f"test.request_log.{id(app)}")
    logger.propagate = False
    logger.setLevel(logging.INFO)
    handler = Captured()
    logger.addHandler(handler)
    wrapped = request_log.RequestLog(app, logger=logger)
    sent = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    scope = {"type": "http", "method": method, "path": path, "query_string": query, "headers": []}
    error = None
    try:
        asyncio.run(wrapped(scope, receive, send))
    except Exception as raised:  # noqa: BLE001 - the test inspects what was logged anyway
        error = raised
    return [json.loads(line) for line in handler.lines], sent, error


class TheRecord(unittest.TestCase):
    def test_a_result_is_logged_with_its_status_and_nothing_from_the_body(self):
        body = json.dumps({
            "contract": {"identifier": "api-v0.1"},
            "result": {"status": "found", "rows": [{"value": MARKER}]},
        }).encode()
        lines, sent, _ = run(respond(200, body, chunks=3), "/v1/discover")
        self.assertEqual(len(lines), 1)
        line = lines[0]
        self.assertEqual(set(line), {"timestamp", "path", "http_status", "latency_ms", "status"})
        self.assertEqual((line["path"], line["http_status"], line["status"]), ("/v1/discover", 200, "found"))
        self.assertNotIn(MARKER, json.dumps(line))
        # The response itself passes through untouched.
        self.assertEqual(b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body"), body)

    def test_a_refusal_is_logged_with_its_kind(self):
        body = json.dumps({"refusal": "invalid_request", "detail": f"SAMPLE {MARKER}"}).encode()
        lines, _, _ = run(respond(400, body), "/v1/query")
        self.assertEqual(lines[0]["refusal"], "invalid_request")
        self.assertNotIn(MARKER, json.dumps(lines[0]))
        self.assertNotIn("detail", lines[0])

    def test_a_value_that_is_not_a_bare_token_is_dropped(self):
        body = json.dumps({"result": {"status": f"found {MARKER}"}}).encode()
        lines, _, _ = run(respond(200, body), "/v1/select")
        self.assertNotIn("status", lines[0])
        self.assertNotIn(MARKER, json.dumps(lines[0]))

    def test_a_path_the_app_does_not_register_is_not_written(self):
        """A caller-chosen path could carry a person's words."""
        lines, _, _ = run(respond(404, b"{}"), f"/{MARKER}", method="GET", query=b"q=" + MARKER.encode())
        self.assertEqual(lines[0]["path"], request_log.OTHER_PATH)
        self.assertNotIn(MARKER, json.dumps(lines[0]))

    def test_the_page_is_logged_without_reading_the_body(self):
        lines, _, _ = run(respond(200, json.dumps({"result": {"status": "found"}}).encode()), "/")
        self.assertEqual(lines[0]["path"], "/")
        self.assertNotIn("status", lines[0])

    def test_a_mcp_tool_result_is_logged_with_its_status(self):
        """Without this, a `coverage_gap`, a `not_found` and a lookup over
        `/mcp` leave byte-identical lines apart from latency (#259 B1)."""
        lines, _, _ = run(respond(200, jsonrpc({
            "contract": {"identifier": "mcp-v0.1"},
            "status": "coverage_gap",
            "limitations": [MARKER],
        })), request_log.MCP_PATH)
        self.assertEqual(lines[0]["path"], request_log.MCP_PATH)
        self.assertEqual(lines[0]["status"], "coverage_gap")
        self.assertNotIn(MARKER, json.dumps(lines[0]))

    def test_a_mcp_tool_refusal_is_logged_with_its_kind(self):
        """Either spelling of the error flag marks a refusal."""
        for key in ("isError", "is_error"):
            with self.subTest(key=key):
                lines, _, _ = run(respond(200, jsonrpc(
                    {"refusal": "malformed_request", "detail": f"SAMPLE {MARKER}"}, error_key=key
                )), request_log.MCP_PATH)
                self.assertEqual(lines[0]["refusal"], "malformed_request")
                self.assertNotIn("status", lines[0])
                self.assertNotIn(MARKER, json.dumps(lines[0]))

    def test_a_mcp_value_that_is_not_a_bare_token_is_dropped(self):
        lines, _, _ = run(respond(200, jsonrpc({"status": f"found {MARKER}"})), request_log.MCP_PATH)
        self.assertNotIn("status", lines[0])
        self.assertNotIn(MARKER, json.dumps(lines[0]))

    def test_a_mcp_response_carrying_no_tool_result_is_logged_without_one(self):
        """`initialize` and `tools/list` answer with no content blocks, and a
        stream or a protocol error is not a Section 4.2 document either."""
        bodies = (
            json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"tools": [{"name": "discover_entity"}]}}).encode(),
            json.dumps({"jsonrpc": "2.0", "id": 1, "error": {"code": -32600, "message": MARKER}}).encode(),
            b"event: message\ndata: " + jsonrpc({"status": "found"}) + b"\n\n",
        )
        for body in bodies:
            with self.subTest(body=body[:24]):
                lines, _, _ = run(respond(200, body), request_log.MCP_PATH)
                self.assertEqual(set(lines[0]), {"timestamp", "path", "http_status", "latency_ms"})
                self.assertNotIn(MARKER, json.dumps(lines[0]))

    def test_a_body_over_the_limit_is_logged_without_its_status(self):
        body = json.dumps({"result": {"status": "found"}, "pad": "x" * (request_log.BODY_LIMIT + 1)}).encode()
        lines, _, _ = run(respond(200, body, chunks=4), "/v1/query")
        self.assertEqual(len(lines), 1)
        self.assertNotIn("status", lines[0])

    def test_a_handler_that_raises_still_leaves_one_line(self):
        lines, _, error = run(respond(500, b"", raises=RuntimeError("SAMPLE")), "/v1/query")
        self.assertIsInstance(error, RuntimeError)
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0]["http_status"], 500)


class TheRegisteredPaths(unittest.TestCase):
    def test_every_route_the_surface_serves_is_written_as_itself(self):
        """`KNOWN_PATHS` must track `create_app`, or a real route would be
        logged as `(other)`."""
        try:
            from evidence_first_rag.api import serve
        except ImportError:
            self.skipTest("the api extra is not installed")
        base = {"PGHOST": "SAMPLE_HOST", "MVP_RUNTIME_PASSWORD": "SAMPLE_PASSWORD"}
        try:
            app = serve.build(base)
        except KeyError:
            self.skipTest("serve.build needs more of the environment here")
        self.assertIsInstance(app, request_log.RequestLog)
        # A templated route (the `/v1/{rest:path}` catch-all that refuses
        # unknown paths) takes a caller's path, so it is rightly `(other)`.
        served = {
            route.path for route in app.app.routes if route.path.startswith("/v1/") and "{" not in route.path
        }
        self.assertTrue(served)
        self.assertLessEqual(served, request_log.KNOWN_PATHS)

    def test_the_mcp_path_is_the_one_the_surface_serves(self):
        """`MCP_PATH` is written out rather than imported, so drift in either
        would silently stop the body being read there (#259 B1)."""
        try:
            from evidence_first_rag.mcp import surface
        except ImportError:
            self.skipTest("the mcp extra is not installed")
        self.assertEqual(request_log.MCP_PATH, surface.PATH)
        self.assertIn(surface.PATH, request_log.KNOWN_PATHS)


if __name__ == "__main__":
    unittest.main()
