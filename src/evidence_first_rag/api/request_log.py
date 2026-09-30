"""`deploy-v0.1` Section 4.7: `surface`'s one JSON line per request (#259).

The record is timestamp, path, HTTP status, latency, and for a `/v1` result
its `status` or for a refusal its kind -- the same keys `relay`'s Section 4.10
record uses for the fields they share, so one reader serves both apps.

What never reaches the line (Section 4.7):

- **No body, argument value or row.** A `/v1` response body is read only to
  take two values out of it, the result's `status` and the refusal's kind, and
  each is written only if it is a bare lowercase token. Anything else is
  dropped, not quoted.
- **No path a caller chose.** A path outside the routes this app registers
  could carry a person's words (`GET /what-is-the-signal`), so it is written
  as `(other)`. A query string is never written.

A pure ASGI wrapper, outermost, so it sees every response -- the refusals the
framework writes, the preflights `_Preflight` answers before routing, and
`/mcp` -- and so its latency covers all of them.
"""

import datetime
import json
import logging
import re
import sys
import time

LOGGER = logging.getLogger("evidence_first_rag.surface.requests")

# The paths `create_app` registers, written as themselves. `api-v0.1`
# Section 4.1's five routes, `mcp-v0.1`'s endpoint, and the page's root.
KNOWN_PATHS = frozenset(
    {"/", "/mcp", "/v1/health", "/v1/select", "/v1/query", "/v1/discover", "/v1/ask"}
)
OTHER_PATH = "(other)"
# Only a `/v1` JSON body is read, and only up to this many bytes: every
# Section 4.2 envelope fits, and a larger one is logged without its status
# rather than held in memory.
BODY_LIMIT = 1 << 20
TOKEN = re.compile(r"^[a-z][a-z_]{0,63}$")


def _token(value):
    return value if isinstance(value, str) and TOKEN.match(value) else None


def outcome(body: bytes) -> dict:
    """The result's `status` or the refusal's kind, and nothing else."""
    try:
        document = json.loads(body)
    except ValueError:
        return {}
    if not isinstance(document, dict):
        return {}
    kind = _token(document.get("refusal"))
    if kind is not None:
        return {"refusal": kind}
    result = document.get("result")
    status = _token(result.get("status")) if isinstance(result, dict) else None
    return {"status": status} if status is not None else {}


def log_line(*, path: str, http_status: int, latency_ms: float, body: bytes | None) -> str:
    record = {
        "timestamp": datetime.datetime.now(tz=datetime.timezone.utc).isoformat(),
        "path": path if path in KNOWN_PATHS else OTHER_PATH,
        "http_status": http_status,
        "latency_ms": round(latency_ms, 1),
    }
    if body is not None:
        record.update(outcome(body))
    return json.dumps(record, separators=(",", ":"))


class RequestLog:
    """Writes `log_line` once per HTTP request, after its last body chunk."""

    def __init__(self, app, *, logger=LOGGER, clock=time.perf_counter) -> None:
        self.app = app
        self.logger = logger
        self.clock = clock

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = self.clock()
        path = scope["path"]
        read = path.startswith("/v1/")
        state = {"status": 500, "chunks": [], "size": 0, "logged": False}

        async def recording(message):
            if message["type"] == "http.response.start":
                state["status"] = message["status"]
            elif message["type"] == "http.response.body":
                chunk = message.get("body", b"")
                if read and state["size"] + len(chunk) <= BODY_LIMIT:
                    state["chunks"].append(chunk)
                state["size"] += len(chunk)
                if not message.get("more_body", False):
                    self._write(state, path, started, read)
            await send(message)

        try:
            await self.app(scope, receive, recording)
        finally:
            # A handler that raised past every layer still leaves a line.
            self._write(state, path, started, read)

    def _write(self, state, path, started, read):
        if state["logged"]:
            return
        state["logged"] = True
        body = b"".join(state["chunks"]) if read and state["size"] <= BODY_LIMIT else None
        self.logger.info(
            log_line(path=path, http_status=state["status"], latency_ms=(self.clock() - started) * 1000, body=body)
        )


def configure_logging(stream=None) -> None:
    """Send the record to standard output, one JSON line each, as
    `relay.serve.configure_logging` does for the relay's. Idempotent."""
    if any(getattr(handler, "_surface_record", False) for handler in LOGGER.handlers):
        return
    handler = logging.StreamHandler(sys.stdout if stream is None else stream)
    handler.setFormatter(logging.Formatter("%(message)s"))
    handler._surface_record = True
    LOGGER.addHandler(handler)
    LOGGER.setLevel(logging.INFO)
    LOGGER.propagate = False
