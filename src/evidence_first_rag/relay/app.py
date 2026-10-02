"""`relay-v0.1`: `POST /chat`, over an injected Messages API client.

Everything here takes its collaborators as arguments -- the client that makes
the Messages API call, the daily ceiling, the `/mcp` URL and the clock -- so
that `tests/test_relay.py` drives every registered case over a stub and no
test calls a model. `serve.py` is the one module that reads an environment.

What the relay does, in the order it does it:

1. **Caps before anything costs** (Section 4.6). The rate limit counts every
   `POST` to the route, the shape and the conversation limit are checked
   next, and the daily ceiling last, all before the model call. A refused
   request makes no call.
2. **Exactly one Messages API call** (Section 4.3), whose body is a pure
   function of the request: the same bytes for the same request (Section 6).
3. **The response passes through unchanged** (Section 4.4), with
   `scope_checks` computed beside it (Section 4.5) and never inside it.
4. **One log line per request, with no message text** (Section 4.10), written
   by `RequestLog` outermost so that a request this route never answers --
   an unserved path, a trailing slash, a handler that raised -- leaves its
   line too (`deploy-v0.1` Section 4.7, #280).

Between the two sits `Cors` (Section 4.1, `0.4.0`): it answers an admitted
preflight before step 1 is reached, and adds the CORS headers to every
`POST /chat` response, whichever step wrote it.

The relay holds no conversation. Every check reads the request and the
response and nothing else, which is what lets a stateless Messages API sit
behind a stateless relay.
"""

import collections
import datetime
import json
import logging
import threading
import time
from collections.abc import Callable, Mapping

import starlette.applications
import starlette.concurrency
import starlette.exceptions
import starlette.requests
import starlette.responses
import starlette.routing

from ..adapter.revalidation import is_verbatim

IDENTIFIER = "relay-v0.1"
CONTRACT_VERSION = "0.5.0"

PATH = "/chat"

# Section 4.3: the call, exactly.
MODEL = "claude-haiku-4-5"
MAX_TOKENS = 1024
BETA = "mcp-client-2025-11-20"
SERVER_NAME = "evidence-first-rag"
ENABLED_TOOL = "discover_entity"

# Section 4.9, byte for byte. `RL-005` reads the contract document and asserts
# this constant equals the text there, so the two cannot drift apart.
SYSTEM_PROMPT = (
    "You help a person find engineering facts in a demonstration database that holds only "
    "synthetic SAMPLE_* identifiers. You have one tool, discover_entity. Use it only to find "
    "which approved entity the person's words refer to. Whenever the person's words name or "
    "describe something that could be an entity in this database, call discover_entity with "
    "those words before you reply, whatever form the question takes: \"What is X?\", \"Tell me "
    "about X\" and a bare \"X\" all start with that call. You cannot fetch facts and you cannot "
    "select a candidate: the person does both on the page, by clicking. A question asking for"
    " a fact is still answered by finding the entity first, so call discover_entity and then "
    "tell the person to choose a candidate on the page to see its facts. The discover_entity "
    "description also mentions query_facts and select_candidate; those tools are not "
    "available to you here, so never call them and never say you did. Put only values the "
    "person wrote into the four scope arguments. If the person did not name a snapshot, call "
    "discover_entity without inventing one, and stop at the `ambiguous` result so the person "
    "can choose a scope on the page. Do not choose a scope, a candidate, or a route for the "
    "person. Report each result's status as it is: a candidate list is not an answer, and "
    "not_found, ambiguous, coverage_gap, unsupported and invalid_request are results. Never "
    "state an engineering fact yourself — no values, units, signal names, message names, or "
    "meanings — because every fact comes from the page's evidence, not from you. If you found"
    " nothing, say so. Keep replies short. Decline anything unrelated to finding entities in "
    "this database."
)

# Section 4.3: the block types the relay passes through. A relay turn in a
# request, and a response, may carry these and no others.
BLOCK_TYPES = frozenset({"text", "mcp_tool_use", "mcp_tool_result"})

# Section 4.2.
PERSON_TURN_MAX_CHARACTERS = 500
BODY_MAX_BYTES = 32 * 1024
RELAY_TURN_MAX_BYTES = 16 * 1024

# Section 4.6.
PERSON_TURN_LIMIT = 10
RATE_WINDOW_SECONDS = 60
RATE_WINDOW_LIMIT = 6
RATE_DAY_LIMIT = 60

# How many clients the rate-limit window holds before stale ones are dropped.
PRUNE_THRESHOLD = 1024

# Section 4.5: the four scope dimensions of a `discover_entity` call.
SCOPE_DIMENSIONS = ("project_code", "revision_label", "network_name", "snapshot_label")

REFUSALS = {
    "malformed_request": 400,
    "method_not_allowed": 405,
    "conversation_limit": 422,
    "rate_limited": 429,
    "model_unavailable": 502,
    "daily_ceiling_reached": 503,
}

# The relay's own sentences. Section 4.6: a `detail` names no credential,
# host, path, key or message text, so none is derived from an exception or
# from the request.
DETAILS = {
    "malformed_request": "The request does not have the shape relay-v0.1 Section 4.2 fixes.",
    "method_not_allowed": "This route accepts POST only.",
    "conversation_limit": "The conversation has more than 10 of the person's turns.",
    "rate_limited": "Too many requests from this client; try again later.",
    "daily_ceiling_reached": "The relay has reached its daily limit of model calls.",
    "model_unavailable": "The model call did not return a usable response.",
}

LOGGER = logging.getLogger("evidence_first_rag.relay")


class Refused(Exception):
    """A Section 4.6 refusal, raised where it is decided and answered once."""

    def __init__(self, kind: str):
        super().__init__(kind)
        self.kind = kind


# --------------------------------------------------------------------------
# Section 4.2: the request.
# --------------------------------------------------------------------------


def _serialized(value) -> bytes:
    """The serialization the Section 4.2 size bound is measured on."""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _is_person_turn(turn) -> bool:
    content = turn.get("content")
    return (
        turn.get("role") == "user"
        and isinstance(content, str)
        and 1 <= len(content) <= PERSON_TURN_MAX_CHARACTERS
    )


def _is_relay_turn(turn) -> bool:
    content = turn.get("content")
    if turn.get("role") != "assistant" or not isinstance(content, list):
        return False
    if len(_serialized(content)) > RELAY_TURN_MAX_BYTES:
        return False
    return all(isinstance(block, dict) and block.get("type") in BLOCK_TYPES for block in content)


def parse_request(body: bytes) -> list:
    """The request's `messages`, or `Refused` with the Section 4.2 or 4.6 kind.

    Every `malformed_request` condition Section 4.2 lists is checked here, and
    no other. The number of person's turns is not a shape error: more than
    ten is `conversation_limit`, decided only once the shape is known good.
    """
    if len(body) > BODY_MAX_BYTES:
        raise Refused("malformed_request")
    try:
        document = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        raise Refused("malformed_request") from None
    if not isinstance(document, dict) or set(document) != {"messages"}:
        raise Refused("malformed_request")
    messages = document["messages"]
    if not isinstance(messages, list) or not messages:
        raise Refused("malformed_request")
    for index, turn in enumerate(messages):
        if not isinstance(turn, dict) or set(turn) != {"role", "content"}:
            raise Refused("malformed_request")
        # Alternation, starting with a person's turn: even indexes are the
        # person's, odd are the relay's, and the last must be the person's.
        if index % 2 == 0:
            if not _is_person_turn(turn):
                raise Refused("malformed_request")
        elif not _is_relay_turn(turn):
            raise Refused("malformed_request")
    if len(messages) % 2 == 0:
        raise Refused("malformed_request")
    if (len(messages) + 1) // 2 > PERSON_TURN_LIMIT:
        raise Refused("conversation_limit")
    return messages


# --------------------------------------------------------------------------
# Section 4.3: the call.
# --------------------------------------------------------------------------


def call_body(messages: list, mcp_url: str) -> dict:
    """The Messages API body for one accepted request, and nothing else."""
    return {
        "model": MODEL,
        "max_tokens": MAX_TOKENS,
        "system": SYSTEM_PROMPT,
        "messages": messages,
        "mcp_servers": [{"type": "url", "url": mcp_url, "name": SERVER_NAME}],
        "tools": [
            {
                "type": "mcp_toolset",
                "mcp_server_name": SERVER_NAME,
                "default_config": {"enabled": False},
                "configs": {ENABLED_TOOL: {"enabled": True}},
            }
        ],
    }


CALL_HEADERS = {"anthropic-beta": BETA}


# --------------------------------------------------------------------------
# Section 4.5: the scope check.
# --------------------------------------------------------------------------


def discover_arguments(block: Mapping):
    """A `discover_entity` call's `arguments` object, or `None` where the block
    carries none this relay can read.

    **The four dimensions sit one level below the block's `input`.**
    `mcp-v0.1` Section 4.1 gives `discover_entity` the input schema
    `{"arguments": {<string>: <string>}}`, required and admitting no additional
    property, which is what `mcp/surface.py` serves and therefore what a call
    to this deployment's `/mcp` carries: `input == {"arguments": {...}}`.
    Section 4.5's "present in the call's `arguments`" is that inner object.
    Reading the dimensions off the outer one would find none in any real call
    and report every call as carrying no scope at all.
    """
    arguments = block.get("input")
    if not isinstance(arguments, Mapping):
        return None
    arguments = arguments.get("arguments")
    return arguments if isinstance(arguments, Mapping) else None


def scope_checks(messages: list, content: list) -> list:
    """One entry per `discover_entity` call in `content`, in block order.

    A value is the person's when it is verbatim, by the `api-v0.1` Section 4.3
    rule, in the text of any one person's turn. Each turn is checked on its
    own: joining them would put two turns' words next to each other and let a
    value straddle the join. Relay turns are never read, so a scope the model
    lifted from an earlier `ambiguous` result is not the person's (`RL-010`).

    A block carrying no readable `arguments` object gets an entry whose two
    lists are empty: no dimension is present in the call's `arguments`, which
    is what Section 4.5 says of it. The relay refuses nothing on this ground
    (Section 4.6 lists only a block type outside Section 4.3's list), and the
    result that call returns is the `mcp-v0.1` Section 4.3 refusal the served
    schema produces, on which P4b already forbids the page any act.
    """
    person_texts = [turn["content"] for turn in messages if turn["role"] == "user"]
    checks = []
    for block in content:
        if block.get("type") != "mcp_tool_use" or block.get("name") != ENABLED_TOOL:
            continue
        arguments = discover_arguments(block) or {}
        stated, not_stated = [], []
        for dimension in SCOPE_DIMENSIONS:
            if dimension not in arguments:
                continue
            value = arguments[dimension]
            is_persons = isinstance(value, str) and any(
                is_verbatim(value, text) for text in person_texts
            )
            (stated if is_persons else not_stated).append(dimension)
        checks.append(
            {
                "tool_use_id": block.get("id"),
                "person_stated": stated,
                "not_person_stated": not_stated,
            }
        )
    return checks


# --------------------------------------------------------------------------
# Section 4.6: the caps.
# --------------------------------------------------------------------------


def _utc_day(now: float) -> datetime.date:
    return datetime.datetime.fromtimestamp(now, tz=datetime.timezone.utc).date()


class Caps:
    """The per-client rate limit and the per-day ceiling on model calls.

    In memory, so both reset when the process restarts: `deploy-v0.1` runs one
    `relay` instance, and what a restart forgets is still bounded in money by
    the API key's workspace spend limit (Section 8.3, ADR-0006), with the
    Azure budget alert as the backstop. `ceiling` of `None` means none is registered, and then every
    request is refused: the relay fails closed and never runs uncapped.
    """

    def __init__(self, ceiling: int | None):
        self.ceiling = ceiling
        self._lock = threading.Lock()
        self._recent = collections.defaultdict(collections.deque)
        self._day = None
        self._per_client_today = collections.Counter()
        self._calls_today = 0

    def _roll(self, now: float) -> None:
        day = _utc_day(now)
        if day != self._day:
            self._day = day
            self._per_client_today.clear()
            self._calls_today = 0

    def admit_request(self, client: str, now: float) -> None:
        """Count one request from `client`, refusing the 7th in 60 seconds or
        the 61st in a UTC day. Every request counts, refused or not."""
        with self._lock:
            self._roll(now)
            if len(self._recent) > PRUNE_THRESHOLD:
                self._prune(now)
            recent = self._recent[client]
            while recent and recent[0] <= now - RATE_WINDOW_SECONDS:
                recent.popleft()
            recent.append(now)
            self._per_client_today[client] += 1
            if len(recent) > RATE_WINDOW_LIMIT or self._per_client_today[client] > RATE_DAY_LIMIT:
                raise Refused("rate_limited")

    def _prune(self, now: float) -> None:
        """Drop the clients with no request in the current window.

        Without this the map grows by one key per address ever seen, on a
        public route. A key is dropped only once its window is empty, so no
        count a live window needs is lost -- including across midnight, which
        is why the window is not simply cleared when the day rolls.
        """
        stale = [
            client
            for client, recent in self._recent.items()
            if not recent or recent[-1] <= now - RATE_WINDOW_SECONDS
        ]
        for client in stale:
            del self._recent[client]

    def admit_call(self, now: float) -> None:
        """Take one model call from today's ceiling, or refuse."""
        with self._lock:
            self._roll(now)
            if self.ceiling is None or self._calls_today >= self.ceiling:
                raise Refused("daily_ceiling_reached")
            self._calls_today += 1


async def bounded_body(request: starlette.requests.Request) -> bytes:
    """The body, read no further than one byte past the Section 4.2 bound.

    `request.body()` would read the whole stream into memory before the bound
    could be applied, so a client could make the relay hold any amount. Past
    the bound the request is `malformed_request` and the rest is never read.
    """
    declared = request.headers.get("content-length", "")
    if declared.isascii() and declared.isdigit() and int(declared) > BODY_MAX_BYTES:
        raise Refused("malformed_request")
    received = bytearray()
    async for chunk in request.stream():
        received.extend(chunk)
        if len(received) > BODY_MAX_BYTES:
            raise Refused("malformed_request")
    return bytes(received)


def client_address(request: starlette.requests.Request) -> str:
    """`deploy-v0.1` Section 4.5: the entry the platform's front end appends to
    the forwarded-for header, which is its last, never one the caller wrote.
    Without the header -- a local run -- the connection's own address."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return _host(forwarded.split(",")[-1].strip())
    return request.client.host if request.client else "unknown"


def _host(entry: str) -> str:
    """The address alone. App Service writes its entry as `address:port`, and
    the port is the caller's ephemeral one, new on every connection, so a key
    that kept it would give each request its own window (run 36662412772,
    `DP-009`). `[v6]:port` loses the brackets and port; a bare IPv6 address,
    which has more than one colon, is already an address."""
    if entry.startswith("["):
        return entry[1:].split("]", 1)[0]
    if entry.count(":") == 1:
        return entry.split(":", 1)[0]
    return entry


# --------------------------------------------------------------------------
# Section 4.10: what the relay records.
# --------------------------------------------------------------------------


def _tool_result_kind(block: Mapping) -> str:
    """A `mcp_tool_result`'s status, or its refusal kind when it is an error.

    Read off the last text block, which `mcp-v0.1` Section 4.2 makes the
    canonical JSON on every result and Section 4.3 the refusal body. The two
    are not nested alike: a refusal body is flat (`{"refusal", "detail"}`),
    while a result is the `api-v0.1` envelope, whose status is under
    `result` (#271). A value that cannot be read is logged as that, and never
    as a status.
    """
    texts = [
        item.get("text")
        for item in block.get("content") or []
        if isinstance(item, dict) and item.get("type") == "text"
    ]
    try:
        document = json.loads(texts[-1])
    except (IndexError, TypeError, ValueError):
        return "unreadable"
    # The Messages API names the flag `is_error`; `relay-v0.1` Section 4.10
    # writes the MCP spelling `isError`. Either marks a refusal.
    if not isinstance(document, dict):
        return "unreadable"
    if block.get("is_error") or block.get("isError"):
        value = document.get("refusal")
    else:
        result = document.get("result")
        value = result.get("status") if isinstance(result, dict) else None
    return value if isinstance(value, str) else "unreadable"


# A path the relay does not serve is caller-chosen and may carry a person's
# words, so its record names it as this rather than as itself (#280).
OTHER_PATH = "(other)"


def log_line(
    *, http_status: int, latency_ms: float, refusal=None, response=None, path: str = PATH
) -> str:
    """The Section 4.10 record: no message text, no argument value, no key.

    Only integers are taken from `usage`, only tool names from `mcp_tool_use`
    blocks, and only a status or refusal kind from `mcp_tool_result` blocks.
    """
    record = {
        "timestamp": datetime.datetime.now(tz=datetime.timezone.utc).isoformat(),
        "path": path,
        "http_status": http_status,
        "latency_ms": round(latency_ms, 1),
    }
    if refusal is not None:
        record["refusal"] = refusal
    if response is not None:
        usage = response.get("usage")
        usage = usage if isinstance(usage, dict) else {}
        record["usage"] = {
            key: value
            for key, value in usage.items()
            if isinstance(key, str) and isinstance(value, int) and not isinstance(value, bool)
        }
        content = response.get("content") or []
        record["tools"] = [
            block.get("name")
            for block in content
            if block.get("type") == "mcp_tool_use" and isinstance(block.get("name"), str)
        ]
        record["tool_results"] = [
            _tool_result_kind(block) for block in content if block.get("type") == "mcp_tool_result"
        ]
    return json.dumps(record, separators=(",", ":"))


# The key the route leaves the Section 4.10 fields only it can know under, in
# the ASGI scope it shares with `RequestLog`.
RECORD = "efr_relay_record"


class RequestLog:
    """`deploy-v0.1` Section 4.7: one line per request, and exactly one (#280).

    A pure ASGI wrapper, outermost, as `api/request_log.RequestLog` is for the
    surface, so it sees every response: the ones this app's route and its
    refusal handlers write, the 404 for a path `relay-v0.1` names nowhere, the
    307 the router answers a trailing slash with, and the 500 left by a handler
    that raised past every layer. Writing the line here rather than inside the
    handlers is what makes "every request" structural rather than a property of
    each handler remembering: a request that reaches no handler of ours, or
    leaves one by exception, still leaves its line.

    What only the route can know it hands over in the scope. Section 4.10's
    `usage` counts, tool names and result kinds are read off the *upstream*
    Messages API response, which this wrapper never sees, and the refusal kind
    is decided in the route; the status, the latency and the path are read here.
    """

    def __init__(self, app, *, logger=LOGGER, clock=time.perf_counter) -> None:
        self.app = app
        self.logger = logger
        self.clock = clock

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = self.clock()
        scope[RECORD] = {}
        state = {"status": 500, "logged": False}

        async def recording(message):
            if message["type"] == "http.response.start":
                state["status"] = message["status"]
            elif message["type"] == "http.response.body" and not message.get("more_body", False):
                self._write(state, scope, started)
            await send(message)

        try:
            await self.app(scope, receive, recording)
        finally:
            # A handler that raised past every layer still leaves a line.
            self._write(state, scope, started)

    def _write(self, state, scope, started) -> None:
        if state["logged"]:
            return
        state["logged"] = True
        fields = scope[RECORD]
        self.logger.info(
            log_line(
                http_status=state["status"],
                latency_ms=(self.clock() - started) * 1000,
                refusal=fields.get("refusal"),
                response=fields.get("response"),
                # A path this relay does not serve is caller-chosen; its query
                # string is never written at all.
                path=PATH if scope["path"] == PATH else OTHER_PATH,
            )
        )


# --------------------------------------------------------------------------
# Section 4.1 (`0.4.0`): the CORS preflight and the response header.
# --------------------------------------------------------------------------


class Cors:
    """Section 4.1's one exception to `method_not_allowed`, and the header a
    browser needs to hand the page a `POST /chat` response.

    A pure ASGI wrapper, as `api/app._Preflight` is for `/v1`, placed inside
    `RequestLog` and outside the framework:

    - **Inside `RequestLog`**, so an admitted preflight leaves exactly one
      Section 4.10 line, with HTTP 204 and nothing a `POST` adds: it reaches no
      route, so nothing is left in the scope for the line but what `RequestLog`
      reads itself.
    - **Before routing and before the caps**, so an admitted preflight reaches
      no cap, consumes none, and makes no model call (`RL-023`).
    - **Outside the framework**, so every `POST /chat` response passes through
      `with_headers`: the 200, each Section 4.6 refusal, and the 500 a handler
      that raised past every layer leaves, which `_Preflight` learned in #215
      B2. A browser withholds a response without `Access-Control-Allow-Origin`
      from the page, and P7 forbids a refusal reaching the person as a network
      failure.

    An `OPTIONS /chat` is admitted only with all three of Section 4.1's
    conditions: a registered origin, an `Origin` equal to it, and
    `Access-Control-Request-Method: POST`. Anything short of that is passed
    through untouched and refused `method_not_allowed`, exactly as at `0.3.x`
    (`RL-024`). The origin is compared, never reflected.

    `Vary: Origin` goes on **every** `POST /chat`, whatever its `Origin` and
    whether or not an origin is registered, because the response differs by
    `Origin`; `Access-Control-Allow-Origin` only on one from the registered
    origin (`RL-025`). The body is never touched.
    """

    def __init__(self, app, *, origin: str | None) -> None:
        self.app = app
        self.origin = origin.encode("latin-1") if origin else None

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["path"] != PATH:
            await self.app(scope, receive, send)
            return
        headers = dict(scope["headers"])
        from_origin = self.origin is not None and headers.get(b"origin") == self.origin
        if scope["method"] == "OPTIONS":
            if from_origin and headers.get(b"access-control-request-method") == b"POST":
                await send(
                    {
                        "type": "http.response.start",
                        "status": 204,
                        "headers": [
                            (b"access-control-allow-origin", self.origin),
                            (b"access-control-allow-methods", b"POST"),
                            (b"access-control-allow-headers", b"content-type"),
                            (b"vary", b"Origin"),
                        ],
                    }
                )
                await send({"type": "http.response.body", "body": b""})
                return
            await self.app(scope, receive, send)
            return
        if scope["method"] != "POST":
            await self.app(scope, receive, send)
            return
        added = [(b"vary", b"Origin")]
        if from_origin:
            added.insert(0, (b"access-control-allow-origin", self.origin))

        async def with_headers(message):
            if message["type"] == "http.response.start":
                message = dict(message)
                message["headers"] = list(message.get("headers", [])) + added
            await send(message)

        await self.app(scope, receive, with_headers)


# --------------------------------------------------------------------------
# The route.
# --------------------------------------------------------------------------


def _json(document: dict, status_code: int) -> starlette.responses.Response:
    return starlette.responses.Response(
        content=_serialized(document), status_code=status_code, media_type="application/json"
    )


def refusal(kind: str) -> starlette.responses.Response:
    """Section 4.6: `{"refusal", "detail"}`, and never `content`."""
    return _json({"refusal": kind, "detail": DETAILS[kind]}, REFUSALS[kind])


def _vouchable(block) -> bool:
    """One block the relay can vouch for (Section 4.3): its type, and nothing
    else.

    Section 4.6 makes `model_unavailable` exactly "the call failed, timed out
    after 60 seconds, or returned a block type outside Section 4.3's list", so
    the *type* is the whole of this test. A `discover_entity` call whose `input`
    is not the `mcp-v0.1` Section 4.1 shape is still an `mcp_tool_use` block:
    it passes through, its `mcp_tool_result` carries the `mcp-v0.1` Section 4.3
    `malformed_request` the served schema produces, and Section 5 requires that
    refusal to cross this boundary with HTTP 200. Its `scope_checks` entry lists
    no dimension in either list, because none is present in the call's
    `arguments` (Section 4.5), and the page offers no act on a tool refusal
    (Section 4.7, P4b).
    """
    return isinstance(block, dict) and block.get("type") in BLOCK_TYPES


def _usable(response) -> bool:
    """Section 4.3: a response the relay can vouch for, block by block."""
    if not isinstance(response, dict):
        return False
    content = response.get("content")
    return isinstance(content, list) and all(_vouchable(block) for block in content)


# The Messages API client: called with the body and the headers, returning the
# response's JSON document as received. Anything it raises is `model_unavailable`.
Caller = Callable[[dict, dict], dict]


def create_app(
    caller: Caller,
    *,
    mcp_url: str,
    ceiling: int | None,
    cors_origin: str | None = None,
    clock: Callable[[], float] = time.time,
) -> RequestLog:
    """The `relay-v0.1` route, over `caller`, under its Section 4.7 request log.

    `ceiling` is the Section 8.3 count of model calls per UTC day, or `None`
    while none is registered. `cors_origin` is Section 4.1's one registered
    origin (`0.4.0`), or `None`, in which case no preflight is admitted and no
    response carries `Access-Control-Allow-Origin`.

    Returned **wrapped** rather than as the `Starlette` application itself, so
    that one line is written for every request and not only for the ones a
    handler here answers (#280). Both are ASGI applications, which is all
    `serve.build`'s uvicorn and the tests' `TestClient` ask of it.
    """
    caps = Caps(ceiling)

    def refused_with(request: starlette.requests.Request, kind: str):
        """Section 4.6's answer, with the kind left for `RequestLog` to write."""
        request.scope.setdefault(RECORD, {})["refusal"] = kind
        return refusal(kind)

    async def chat(request: starlette.requests.Request):
        try:
            caps.admit_request(client_address(request), clock())
            messages = parse_request(await bounded_body(request))
            caps.admit_call(clock())
        except Refused as refused:
            return refused_with(request, refused.kind)
        try:
            response = await starlette.concurrency.run_in_threadpool(
                caller, call_body(messages, mcp_url), dict(CALL_HEADERS)
            )
        except Exception:  # noqa: BLE001 - Section 4.6: any failure is this refusal
            return refused_with(request, "model_unavailable")
        if not _usable(response):
            return refused_with(request, "model_unavailable")
        content = response["content"]
        document = {
            "content": content,
            "stop_reason": response.get("stop_reason"),
            "scope_checks": scope_checks(messages, content),
            "relay": {"identifier": IDENTIFIER, "version": CONTRACT_VERSION, "model": MODEL},
        }
        # Section 4.10's `usage` counts, tool names and result kinds are read
        # off the upstream response, which `RequestLog` never sees, so it is
        # handed over here. Only those values reach the line (`RL-018`).
        request.scope.setdefault(RECORD, {})["response"] = response
        return _json(document, 200)

    async def not_allowed(request, exc):
        # Section 4.1: any other method on the path. The framework's own 405
        # would be plain text and carry an `Allow` header this contract does
        # not name.
        return refused_with(request, "method_not_allowed")

    async def not_found(request, exc):
        # `relay-v0.1` names no path but this one, so an unserved path keeps
        # the plain answer the framework's own default handler gives it. It
        # leaves no Section 4.6 refusal kind in the record, and `RequestLog`
        # writes the line for it as it does for every other request.
        return starlette.responses.PlainTextResponse("Not Found", status_code=404)

    return RequestLog(
        Cors(
            starlette.applications.Starlette(
                routes=[starlette.routing.Route(PATH, chat, methods=["POST"])],
                exception_handlers={404: not_found, 405: not_allowed},
            ),
            origin=cors_origin,
        )
    )
