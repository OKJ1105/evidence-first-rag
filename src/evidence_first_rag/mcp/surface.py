"""Contract `mcp-v0.1` Sections 4.1 to 4.6: the MCP tool surface.

Three tools, one result shape, three refusals. Everything this module does is
dispatch and carriage; every decision about an answer is made below it, by
`mvp-v0.1` or `entity-discovery-v0.1`, and arrives here already normalized --
through the same `Services` the `api-v0.1` surface dispatches through, which
is what makes Section 8's equality a statement about one runtime.

Four properties are structural rather than promised:

1. **The tool set is the allowlist** (Section 4.1). `TOOLS` is the whole of
   what `tools/list` returns and `on_call_tool` dispatches on; a name outside
   it is refused by name before anything is read. No route name, scope
   dimension or argument name is checked here -- `arguments` reaches the entry
   point as it arrived, and that contract's validation decides every question
   about it.
2. **One entry-point call per tool call** (Section 4.6). Each branch of
   `_dispatch` makes one call and returns what it gave back. There is no
   branch on a result's status, and no path from `needs_entity_discovery` or
   `candidates` to a second call.
3. **The result is the envelope** (Section 4.2). `structuredContent` is what
   `api.app.envelope` wrote, and `content` is that document's carriage: the
   `rendered` sentence copied, where the contract supplies one, then the
   canonical JSON of the same document. Nothing is composed here.
4. **A refusal is never a result, and a result is never marked an error**
   (Section 4.3). `is_error` is set in exactly one function, `refusal`, and
   that function never carries `structuredContent`.

The SDK's low-level `Server` is used rather than its decorator front end,
because the front end derives a tool's schema and result from a Python
signature and wraps what a handler returns. Section 4.4 fixes the descriptions
byte for byte and Section 4.2 fixes the blocks one by one, so both have to be
written out rather than derived.
"""

from __future__ import annotations

import contextlib
import dataclasses
import os

import anyio
import mcp.types as types
import pydantic
from mcp.server.lowlevel import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.server.transport_security import TransportSecuritySettings
from mcp.shared.exceptions import MCPError

from ..api.app import (
    RUNTIME_FAULT_DETAIL,
    DiscoverBody,
    QueryBody,
    SelectBody,
    Services,
    envelope,
)
from ..api.serialize import dumps
from ..discovery import DiscoveryRequest, SelectionRequest
from ..result import Result
from ..runtime import Request as RuntimeRequest
from ..runtime.faults import ConnectionUnavailable, Fault

# Section 1 of docs/contracts/mcp-v0.1.md. Carried by the server's identity in
# the protocol's initialization (Section 4.5), and nowhere inside a result: a
# tool result's `contract` key is `api-v0.1`'s, because the envelope is that
# contract's (Section 4.2).
CONTRACT_IDENTIFIER = "mcp-v0.1"
CONTRACT_VERSION = "0.1.1"

# Section 4.5: one path beside `/v1`, fixed by this slice. Not under `/v1`,
# which `api-v0.1` Section 4.1 fixes exhaustively.
PATH = "/mcp"

# Section 4.3's three kinds. The other three of `api-v0.1` Section 4.5 do not
# occur here, and the contract says why: a tool name outside Section 4.1 is a
# protocol error before this surface sees a result, tools have no method, and
# no tool calls the adapter.
REFUSALS = ("malformed_request", "database_unavailable", "runtime_fault")

# --------------------------------------------------------------------------
# Section 4.4: the descriptions, verbatim.
# --------------------------------------------------------------------------

# These are the instructions ADR-0004 items 2 and 4 pass to the host, and the
# contract fixes them byte for byte so that `MC-025` can read them. They are
# text the host reads and this surface cannot enforce (Section 3.3): an
# obligation on the host, in the host's terms, and not a check.
DESCRIPTIONS = {
    "query_facts": (
        "Returns registered facts about one message, signal, or signal mapping"
        " in one source snapshot, from fixed SQL, with the evidence that"
        " produced them. `route` is one of message_facts, signal_facts,"
        " signal_mapping. `arguments` is a canonical entity reference: the four"
        " scope values (project_code, revision_label, network_name,"
        " snapshot_label) and the lookup key — message_key for message_facts;"
        " message_key and signal_key for signal_facts and signal_mapping, which"
        " also accepts an optional mapping_key. Every scope value must be a"
        " value the person stated; never supply one the person did not name,"
        " and never guess a"
        " snapshot. If a scope value is missing, the result is `ambiguous` with"
        " the candidate scopes listed, or `coverage_gap` when no snapshot"
        " matches — show what the result carries to the person and ask; do not"
        " pick one. If the entity is not known, use discover_entity first. The"
        " `rendered` sentence is the answer; the evidence beside it is where it"
        " came from. A negative status (not_found, ambiguous, coverage_gap,"
        " unsupported, invalid_request, needs_entity_discovery) is a result:"
        " report it as such and do not answer from anything but the result."
    ),
    "discover_entity": (
        "Finds which approved entity a term may refer to, inside one"
        " fully-specified source snapshot. `arguments` carries the four scope"
        " values (project_code, revision_label, network_name, snapshot_label),"
        " entity_kind (`message` or `signal`), term (the person's words for the"
        " entity, at most 200 bytes), and optionally parent_message_key when"
        " entity_kind is signal and the parent message is known. Every scope"
        " value must be a value the person stated; never supply one the person"
        " did not name. A `candidates` result is a ranked list and"
        " is not an answer: show the candidates to the person and let the"
        " person choose; do not choose for them, and do not call query_facts"
        " with a candidate the person has not chosen. Use select_candidate with"
        " the person's choice. A `resolved` result names exactly one entity and"
        " may be used with query_facts directly. A `not_found` result means no"
        " approved entity matched the term; it does not mean the entity does"
        " not exist in the data. A negative status is a result: report it as"
        " such."
    ),
    "select_candidate": (
        "Completes a `candidates` result from discover_entity with the person's"
        " explicit choice. Call it only after the person has chosen a candidate"
        " by its rank; never select on the person's behalf, and never call it"
        " to try candidates in turn. Pass the same arguments discover_entity"
        " was called with, the candidate_set_id from that result, the chosen"
        " selected_rank as its decimal text, and the target_route the person's"
        " question needs (message_facts for a message; signal_facts or"
        " signal_mapping for a signal). The runtime verifies that the candidate"
        " list still exists and that the rank names a candidate in it; it does"
        " not verify who chose. The result is the fact result for the chosen"
        " entity, with a selection record naming the candidate set it was"
        " chosen from."
    ),
}

# --------------------------------------------------------------------------
# Section 4.1: the three tools and their argument shapes.
# --------------------------------------------------------------------------

# `arguments` is a JSON object whose values are strings, on every tool without
# exception (Section 4.1) -- `selected_rank` included, whose value is the
# decimal text of the `rank` a discovery result carried as a number.
_ARGUMENTS = {"type": "object", "additionalProperties": {"type": "string"}}

# The served schemas state exactly the keys Section 4.1 names, each of its
# type, and admit no additional property. They are the same shape the
# `api-v0.1` body models express, which is why those models are what
# `_shape` validates against: one rule, two statements of it, and a test that
# the two agree.
_SCHEMAS = {
    "query_facts": {
        "type": "object",
        "properties": {"route": {"type": "string"}, "arguments": _ARGUMENTS},
        "required": ["route", "arguments"],
        "additionalProperties": False,
    },
    "discover_entity": {
        "type": "object",
        "properties": {"arguments": _ARGUMENTS},
        "required": ["arguments"],
        "additionalProperties": False,
    },
    "select_candidate": {
        "type": "object",
        "properties": {"arguments": _ARGUMENTS},
        "required": ["arguments"],
        "additionalProperties": False,
    },
}

_BODIES = {"query_facts": QueryBody, "discover_entity": DiscoverBody, "select_candidate": SelectBody}

# In Section 4.1's order, which `MC-025` asserts `tools/list` returns.
TOOLS = tuple(
    types.Tool(name=name, description=DESCRIPTIONS[name], input_schema=_SCHEMAS[name])
    for name in ("query_facts", "discover_entity", "select_candidate")
)

TOOL_NAMES = tuple(tool.name for tool in TOOLS)


# --------------------------------------------------------------------------
# Sections 4.2 and 4.3: a result, and a refusal.
# --------------------------------------------------------------------------


def _text(text: str) -> types.TextContent:
    return types.TextContent(type="text", text=text)


def tool_result(result) -> types.CallToolResult:
    """Section 4.2's table over one result. Nothing else goes in it.

    `structuredContent` is the `api-v0.1` Section 4.2 envelope, exactly as
    `/v1` would return it for the same body -- `proposal` never present,
    because no tool calls the adapter. `content` is its carriage: on an
    `mvp-v0.1` result the `rendered` string verbatim, then the canonical JSON;
    on an `entity-discovery-v0.1` result the JSON alone, because that contract
    defines no renderer and this surface does not invent one.

    **The branch is the key set Section 4.2 names**, and a Python type is how
    this module reads it: `as_json` dispatches on the same type, emitting
    `rows` for one and `resolved`/`candidates`/`candidate_scopes` for the
    other, so `isinstance(result, Result)` and "carries `rows`" are the same
    question asked twice. Not the tool, because a dispatched selection is an
    `mvp-v0.1` result reached through the selection tool; and not a contract
    identifier inside the bundle, which Section 4.2 forbids branching on
    because a discovery bundle carries two. `MC-022` asserts it by the key
    set, over `MC-006` among others.
    """
    document = envelope(result)
    blocks = []
    if isinstance(result, Result):
        blocks.append(_text(document["rendered"]))
    blocks.append(_text(dumps(document)))
    return types.CallToolResult(content=blocks, structured_content=document, is_error=False)


def refusal(kind: str, detail: str) -> types.CallToolResult:
    """Section 4.3: one block, the fixed body, no `structuredContent`.

    The only place `is_error` is set. `detail` is a fixed sentence: nothing
    read off the arguments or off what was raised reaches it, for the reason
    `api-v0.1` Section 4.5 gives -- a driver's message names a host and a
    port, and a traceback names a path.
    """
    if kind not in REFUSALS:
        raise ValueError(f"{kind!r} is not a Section 4.3 refusal kind")
    return types.CallToolResult(
        content=[_text(dumps({"refusal": kind, "detail": detail}))], is_error=True
    )


MALFORMED_DETAIL = (
    "the arguments must be a JSON object carrying exactly the keys this tool"
    " names, each of the stated type (Section 4.1)"
)
DATABASE_DETAIL = (
    "the database could not be reached, so the request was never attempted"
    " (Section 4.3)"
)


# --------------------------------------------------------------------------
# Section 4.1: dispatch.
# --------------------------------------------------------------------------


def _shape(name: str, arguments):
    """Section 4.3's `malformed_request`: structural, and it never reads a
    value's meaning. The `api-v0.1` body model is the rule; a `ValidationError`
    is the refusal."""
    return _BODIES[name].model_validate(arguments if arguments is not None else {})


def _dispatch(services: Services, name: str, body):
    """One entry-point call, and the one branch in this module -- on the tool,
    never on a result."""
    if name == "query_facts":
        return services.runtime.execute(RuntimeRequest(route=body.route, arguments=body.arguments))
    if name == "discover_entity":
        return services.discovery.execute(DiscoveryRequest(arguments=body.arguments))
    return services.selection.execute(SelectionRequest(arguments=body.arguments))


def call(services: Services, name: str, arguments) -> types.CallToolResult:
    """One tool call, synchronously: what `on_call_tool` does once it is off
    the event loop. Separated so a test can call it without a session and so
    the blocking part is one function."""
    if name not in _BODIES:
        # Section 4.3: a name outside Section 4.1 is a protocol error, not a
        # refusal -- the protocol's own vocabulary for a tool that does not
        # exist, raised before anything is read.
        raise MCPError(code=types.INVALID_PARAMS, message="unknown tool")
    try:
        body = _shape(name, arguments)
    except pydantic.ValidationError:
        return refusal("malformed_request", MALFORMED_DETAIL)
    try:
        # `tool_result` is **inside** the try, not after it. Building the
        # envelope and serializing it can fail -- a result shape `as_json` does
        # not know, a value `dumps` cannot write -- and Section 4.3 admits no
        # outcome outside its table. Left outside, such a failure would leave
        # the surface as a bare protocol error carrying neither a result nor a
        # refusal, which is the one response shape this contract has no row for.
        return tool_result(_dispatch(services, name, body))
    except ConnectionUnavailable:
        return refusal("database_unavailable", DATABASE_DETAIL)
    except Fault:
        return refusal("runtime_fault", RUNTIME_FAULT_DETAIL)
    except Exception:  # noqa: BLE001 - Section 4.3: nothing leaves as a bare error
        # What no handler names lands inside Section 4.3's table, as the
        # `api-v0.1` surface's catch-all does: a driver condition
        # `runtime/connection.py` does not wrap, or a defect here, is still a
        # refusal with a fixed sentence and never a result.
        return refusal("runtime_fault", RUNTIME_FAULT_DETAIL)


def create_server(services: Services) -> Server:
    """The Section 4.1 surface over `services`, as a protocol server.

    Tools only (Section 4.5): the two handlers below are the whole of what is
    registered, so the capabilities the SDK derives declare tools and nothing
    else.
    """

    async def on_list_tools(ctx, params):
        return types.ListToolsResult(tools=list(TOOLS))

    async def on_call_tool(ctx, params):
        # Every entry-point call opens a connection and runs statements. It
        # runs where `api-v0.1`'s handlers run theirs -- off the event loop --
        # so that one slow call does not delay every other call in the
        # process (Section 4.5).
        return await anyio.to_thread.run_sync(call, services, params.name, params.arguments)

    return Server(
        CONTRACT_IDENTIFIER,
        version=CONTRACT_VERSION,
        on_list_tools=on_list_tools,
        on_call_tool=on_call_tool,
    )


# --------------------------------------------------------------------------
# Section 4.5: transport.
# --------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class Mounted:
    """What `api.app.create_app` registers at `PATH`: an ASGI endpoint, and
    the lifespan that must be entered before it answers.

    An instance is the endpoint -- a class with `__call__` rather than a
    function -- for the reason `api.app` gives for its namespace guard:
    Starlette treats a plain function as a request handler with a method
    list, and only an ASGI callable is routed for every method at the exact
    path. Registered as a route rather than a mount because a mount matches
    `PATH/…` and the protocol posts to `PATH` itself.
    """

    server: Server
    manager: StreamableHTTPSessionManager

    async def __call__(self, scope, receive, send):
        await self.manager.handle_request(scope, receive, send)

    @contextlib.asynccontextmanager
    async def lifespan(self):
        async with self.manager.run():
            yield


def mount(services: Services, environment=None) -> Mounted:
    """Streamable HTTP, stateless, JSON responses (Section 4.5).

    Stateless because the surface holds nothing between calls: a
    `candidate_set_id` is the whole of what connects a discovery to a
    selection, and the runtime re-derives it rather than remembering it. JSON
    rather than an event stream because every tool call is one request and one
    result, and a stream would carry nothing a response does not.

    **`Origin` and `Host` are validated, and that is not one of the things
    Section 9 defers.** Section 9 defers authentication, authorization, rate
    limiting, TLS and metrics to Milestone 5; DNS-rebinding protection is none
    of those, and without it any web page a person visits could POST to this
    path on their own loopback and read whatever the tools return. The SDK
    turns the same protection on by default for a server it binds to
    loopback; this manager is constructed directly, so it has to be passed,
    and the allowlist is the loopback the Section 4.7 stack publishes.

    `EFR_MCP_ALLOWED_HOSTS` and `EFR_MCP_ALLOWED_ORIGINS` widen it, as
    comma-separated lists, because a deployment answers for a name this
    module cannot know. Reading them is not deployment configuration this
    contract fixes -- Section 9 leaves that to Milestone 5 -- it is the one
    hook that keeps the safe default from being the reason a deployment turns
    the protection off wholesale.
    """
    server = create_server(services)
    manager = StreamableHTTPSessionManager(
        app=server,
        stateless=True,
        json_response=True,
        security_settings=transport_security(environment),
    )
    return Mounted(server=server, manager=manager)


# The loopback the `api-v0.1` Section 4.7 stack publishes, with the ports a
# browser may leave off or vary.
LOOPBACK_HOSTS = ("127.0.0.1:*", "localhost:*", "[::1]:*", "127.0.0.1", "localhost")
LOOPBACK_ORIGINS = (
    "http://127.0.0.1:*",
    "http://localhost:*",
    "http://[::1]:*",
    "http://127.0.0.1",
    "http://localhost",
)


def transport_security(environment=None) -> TransportSecuritySettings:
    """Section 4.5's `Origin` and `Host` allowlist, loopback plus the
    environment's additions."""
    environment = os.environ if environment is None else environment

    def extra(name):
        return tuple(part.strip() for part in environment.get(name, "").split(",") if part.strip())

    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=list(LOOPBACK_HOSTS + extra("EFR_MCP_ALLOWED_HOSTS")),
        allowed_origins=list(LOOPBACK_ORIGINS + extra("EFR_MCP_ALLOWED_ORIGINS")),
    )
