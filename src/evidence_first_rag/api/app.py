"""Contract `api-v0.1` Sections 4.1 to 4.3 and 4.5: the HTTP surface.

Five routes, one envelope, six refusals. Everything this module does is
dispatch and shape; every decision about an answer is made below it, by
`mvp-v0.1` or `entity-discovery-v0.1`, and arrives here already normalized.

Three properties are structural rather than promised, because each is a
prohibition the contract states and a reader should be able to check by
reading this file:

1. **The surface has no allowlist of its own** (Section 4.1). No route name,
   scope dimension or argument name is checked here. `arguments` reaches the
   entry point as it arrived, and that contract's validation decides every
   question about it. The one thing this module refuses is the body's shape.
2. **The surface never joins** (Section 4.3). There is no code path from a
   `needs_entity_discovery` result to a discovery request. Each handler calls
   one entry point and returns what it gave back. The caller issues the next
   request.
3. **Nothing about a response varies with when it was made** (Section 6). No
   clock, no counter, no identifier is read anywhere below, and Section 4.2's
   key table admits none, so two identical requests produce identical bytes.

**On FastAPI.** The framework is used as a router and a body parser and as
nothing else. Its defaults are the wrong shape for this contract -- a
validation failure is HTTP 422 with a list-valued `detail`, where Section 4.5
fixes 400 with `{"refusal", "detail"}` -- so both of its exception handlers are
replaced below and no response anywhere is built by it. Bodies are written by
`serialize.dumps`, because Section 6's byte-identity is a claim about an
escape set and a key order that no library default supplies.

What Pydantic *is* used for is Section 4.4's request-body rule, which is
exactly a model with `extra="forbid"` over string-valued fields. That is the
surface's only refusal, so expressing it declaratively is not the framework
adding validation the contract forbids; it is the framework expressing the one
check the contract requires.
"""

import contextlib
import dataclasses
import json
import mimetypes

import pathlib

import fastapi
import fastapi.exceptions
import fastapi.staticfiles
import pydantic
import starlette.exceptions
import starlette.responses

from ..adapter.revalidation import Proposal, answer, is_verbatim
from ..contract import CONTRACT_IDENTIFIER as RUNTIME_CONTRACT
from ..contract import CONTRACT_VERSION as RUNTIME_VERSION
from ..discovery import Discovery, DiscoveryRequest, Selection, SelectionRequest
from ..discovery.evidence import CONTRACT_IDENTIFIER as DISCOVERY_CONTRACT
from ..discovery.evidence import CONTRACT_VERSION as DISCOVERY_VERSION
from ..result import Result
from ..runtime import Request as RuntimeRequest
from ..runtime import Runtime, render
from ..runtime.faults import ConnectionUnavailable, Fault
from .serialize import as_json, dumps

# Section 1 of docs/contracts/api-v0.1.md. Carried on every result-bearing
# response by Section 4.2's `contract` key, and reported by `GET /v1/health`.
CONTRACT_IDENTIFIER = "api-v0.1"
CONTRACT_VERSION = "0.2.0"

# Section 4.5's six kinds, with the HTTP code each is fixed to. A dict rather
# than six constants so that the refusal writer cannot pair a kind with a code
# the table does not give it, and so a test can assert the table's width.
REFUSALS = {
    "malformed_request": 400,
    "unknown_route": 404,
    "method_not_allowed": 405,
    "adapter_unavailable": 503,
    "database_unavailable": 503,
    "runtime_fault": 500,
}

# Section 4.5: the health probe reports exactly three contracts. `export-v0.1`
# is not among them -- it is not in this tree and no route here serves one.
CONTRACTS = {
    CONTRACT_IDENTIFIER: CONTRACT_VERSION,
    RUNTIME_CONTRACT: RUNTIME_VERSION,
    DISCOVERY_CONTRACT: DISCOVERY_VERSION,
}

# Section 4.1 fixes the API under `/v1`, and Section 4.5 bounds `unknown_route`
# to that namespace and "nothing else". A path outside it is not a path this
# contract says anything about, so it is neither a route nor a refusal; the
# presentation surface (Section 4.6) is served from outside `/v1` and must not
# be turned into a 404 by a rule written for the API.
NAMESPACE = "/v1"

JSON_MEDIA_TYPE = "application/json"

# Section 4.5's sentence for `runtime_fault`, written once because two handlers
# below give it: the `Fault` the runtime raises on purpose, and the exception
# nothing named. What a caller can do about either is the same, and a second
# sentence would only say which of the two happened -- which is exactly the
# thing Section 4.5 keeps out of a refusal body.
RUNTIME_FAULT_DETAIL = (
    "the request failed for a reason the seven status families do not cover"
    " (mvp-v0.1 Section 4.4)"
)


class AdapterUnavailable(Exception):
    """The adapter could not be reached, timed out, or said nothing usable.

    Section 4.5 confines `adapter_unavailable` to transport conditions, and
    Section 4.3 step 1 puts everything the adapter actually *proposed* on the
    other side of that line -- including a proposal naming a route that does
    not exist, which is a result at HTTP 200 and never a 503. So this is raised
    by the proposer and by nothing else: no handler below infers it from the
    shape of a proposal it received.
    """


# --------------------------------------------------------------------------
# Section 4.4, request side: the one check by which the surface refuses.
# --------------------------------------------------------------------------


class Body(pydantic.BaseModel):
    """Section 4.4: exactly the keys Section 4.1 names, each of its type.

    `extra="forbid"` is the "carrying an extra key" clause. The
    "carrying a non-string where a string is required" clause is the `str`
    annotation itself: Pydantic 2 refuses an `int`, a `bool`, a `float` and a
    `null` for a `str` field **in either mode**, which is what makes a caller
    who echoes a `rank` as a JSON number `malformed_request` by name
    (Section 4.1).

    `strict=True` is therefore not what produces that refusal today, and
    saying so would be a claim this module cannot support -- a mutation run
    turning it off changed no test, because it changes no behavior. It is kept
    as a pin: coercion for these types is a library policy, and a future
    Pydantic that relaxed it would silently turn a `malformed_request` into an
    accepted `"3"`. What the tests assert is the behavior, not the setting.
    """

    model_config = pydantic.ConfigDict(extra="forbid", strict=True)


class QueryBody(Body):
    route: str
    arguments: dict[str, str]


class AskBody(Body):
    request_text: str


class DiscoverBody(Body):
    arguments: dict[str, str]


class SelectBody(Body):
    arguments: dict[str, str]


# --------------------------------------------------------------------------
# Section 4.2: the envelope.
# --------------------------------------------------------------------------


def envelope(result, *, proposal: dict | None = None) -> dict:
    """Section 4.2's key table over one result. Nothing else goes in it.

    `rendered` is the `mvp-v0.1` Section 4.8 answer for a fact result and
    `null` for a discovery one, because `entity-discovery-v0.1` defines no
    renderer and this contract does not invent one. The `result` is whatever
    `as_json` wrote: the surface adds no key to it, removes none, renames none,
    and reorders no list.
    """
    document = {
        "result": as_json(result),
        "rendered": render(result) if isinstance(result, Result) else None,
        "contract": {"identifier": CONTRACT_IDENTIFIER, "version": CONTRACT_VERSION},
    }
    # Section 4.2: present on `/v1/ask` only, and absent -- not null -- on
    # every other route. The `null`-never-omitted rule is Section 4.4's and
    # governs the result, not this table.
    if proposal is not None:
        document["proposal"] = proposal
    return document


def _json(document: dict, status_code: int = 200) -> starlette.responses.Response:
    """One document, one text (Section 6).

    `Response` rather than any of FastAPI's JSON responses: the body is written
    by `serialize.dumps`, which is the Section 4.4 escape set and key order.
    Handing the document to a framework serializer would put a second
    representation of every response in the system, and Section 6's byte
    identity would then depend on which one ran.
    """
    return starlette.responses.Response(
        content=dumps(document), status_code=status_code, media_type=JSON_MEDIA_TYPE
    )


def refusal(kind: str, detail: str) -> starlette.responses.Response:
    """Section 4.5: a response carrying no result. Two keys, and no others.

    `detail` is the surface's own text on every path below. Nothing derived
    from an exception's message reaches it: a driver's message names a host and
    a port, and Section 4.5 forbids a refusal to name either.
    """
    return _json({"refusal": kind, "detail": detail}, status_code=REFUSALS[kind])


# --------------------------------------------------------------------------
# Section 4.3: what `/v1/ask` reports about the proposal it received.
# --------------------------------------------------------------------------


def verbatim_arguments(proposal: Proposal, request_text: str) -> list[str]:
    """The `arguments` names whose value occurs verbatim in `request_text`.

    Section 4.2 makes this the surface's own computation rather than something
    read off revalidation, and Section 4.3 says why: on the path where
    revalidation *passed* there is nothing to read it off, and that is exactly
    the path where a UI is about to offer these values as form defaults
    (Section 4.6, obligation 4). Sorted, because Section 6 admits one body per
    request and a set has no order.

    A proposal whose `arguments` are not a mapping of strings names nothing.
    That is not a refusal: Section 4.6 makes adapter output untrusted, this is
    a report on it, and a report on a malformed proposal is the empty list.
    """
    arguments = proposal.arguments
    if not isinstance(arguments, dict):
        return []
    return sorted(
        name
        for name, value in arguments.items()
        if isinstance(name, str) and isinstance(value, str) and is_verbatim(value, request_text)
    )


def proposal_document(proposal: Proposal, request_text: str) -> dict:
    """Section 4.2's `proposal` value: `{route, arguments, verbatim}`.

    `route` and `arguments` are the adapter's output exactly as returned and
    before revalidation, which is the contract's wording and is the point: a
    reader comparing the proposal with the result can see what was proposed and
    what happened to it. Presenting the revalidated request here instead would
    hide every case where the two differ, which is every case revalidation
    exists for.

    **Both go through `_wire`, because this is the one key of Section 4.2 that
    carries untrusted output.** `Adapter.read` passes `document.get("route")`
    and a non-conforming `arguments` through unchanged -- deliberately, so that
    revalidation is what judges a proposal -- so either can be any JSON value a
    model emitted, and a float or a negative integer is outside the vocabulary
    the Section 4.4 canonical rules write. Serializing one raw raises inside
    the handler, and what a caller then receives is the framework's plain-text
    500: a non-200 carrying neither a result nor one of Section 4.5's six
    refusals. `_wire` keeps the envelope in the vocabulary without dropping the
    proposal, which is what Section 4.3's report is for.
    """
    return {
        "route": _wire(proposal.route),
        "arguments": _wire(proposal.arguments),
        "verbatim": verbatim_arguments(proposal, request_text),
    }


def _wire(value):
    """`value` as something the Section 4.4 canonical rules can write.

    That vocabulary is `null`, a boolean, an integer of either sign, a string,
    an array and an object (`discovery/canonical.py`). A value inside it is
    returned unchanged, so a conforming proposal reaches the wire exactly as
    the adapter returned it. A value outside it becomes its text form rather
    than an exception, because the alternative on this path is not a better
    body -- it is a response outside Section 4.5's table.

    **What is left outside is a float, and deliberately.** `json_text` was
    widened to write a negative integer because a result row can carry one;
    it was not widened to write a float, because a float has no canonical text
    to agree on -- two conforming implementations would have to pick the same
    one for Section 6's byte identity to hold -- and because `mvp-v0.1`
    Section 6 forbids rounding anywhere, which is why a `numeric` column
    travels as its stored decimal text rather than as a JSON number at all.
    Choosing a float form here would be deciding that question in a helper.
    A model that proposed `1.5` still has its value shown, as `"1.5"`.

    Text rather than omission: a reader comparing the proposal with the
    `invalid_request` that followed needs to see the value that caused it, and
    a dropped key would make an off-schema proposal look like one that carried
    nothing.
    """
    if isinstance(value, (str, bool, int, type(None))):
        return value
    if isinstance(value, (list, tuple)):
        return [_wire(item) for item in value]
    if isinstance(value, dict):
        return {_wire_name(name): _wire(item) for name, item in value.items()}
    return str(value)


def _wire_name(name):
    """An object key as the string those rules require one to be.

    JSON gives no other kind of key, so this is reachable only from a proposal
    injected in-process; it exists so that `_wire` has no path that raises."""
    return name if isinstance(name, str) else str(name)


# --------------------------------------------------------------------------
# The services a surface dispatches to.
# --------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True, kw_only=True)
class Services:
    """The four entry points of Section 4.1, as objects the app calls.

    Handed in rather than constructed per request so that a test can count
    dispatches and inject a fault without a database, and so that the "at most
    one entry point per request" property of Section 4.3 is observable from
    outside. `proposer` is `None` when no adapter is configured, which
    Section 4.5 makes `/v1/ask`'s `adapter_unavailable` and Section 4.7 makes
    an ordinary way to run the stack.
    """

    runtime: object
    discovery: object
    selection: object
    proposer: object | None = None


def services(database, *, fixture_provenance=(), proposer=None) -> Services:
    """The three routes' entry points over one database."""
    return Services(
        runtime=Runtime(database=database, fixture_provenance=fixture_provenance),
        discovery=Discovery(database=database, fixture_provenance=fixture_provenance),
        selection=Selection(database=database, fixture_provenance=fixture_provenance),
        proposer=proposer,
    )


@dataclasses.dataclass(frozen=True, kw_only=True)
class SurfaceProposer:
    """An `adapter.Adapter`, with Section 4.5's transport boundary drawn on it.

    `Adapter.read` answers a different question from the one this contract
    asks. It turns unparseable output into an `unsupported` proposal, which is
    right for the `mvp-v0.1` Section 8.3 comparison -- a model that produced
    nothing usable scored a miss, and losing the case to an exception would
    lose the measurement. Section 4.5 draws the line elsewhere: bytes that are
    not a JSON object are a **transport** condition, 503, and never a result,
    because a 200 carrying a fabricated empty proposal would present a model
    failure as a runtime outcome (`WF-022`).

    So this wraps rather than replaces: the adapter parses, and this reads the
    raw text off the record of **its own** call to decide which side of the
    line that call fell on. There is no second parser producing a proposal.

    `propose_with_call` rather than `propose` plus `calls[-1]`: the handlers
    are `def` and therefore run in Starlette's threadpool, so two requests can
    be inside this method at once and the shared list's last element is not
    reliably the one this call appended.
    """

    adapter: object

    def propose(self, request_text: str) -> Proposal:
        try:
            proposal, call = self.adapter.propose_with_call(request_text)
        except Exception as unreachable:
            raise AdapterUnavailable(
                "the adapter could not be reached"
            ) from unreachable
        if getattr(call, "stop_reason", None) == "refusal":
            # A model that declined has said "no route applies", which
            # Section 4.6 of `mvp-v0.1` gives it a vocabulary for. That is a
            # proposal, and it becomes an `unsupported` result.
            return proposal
        if not _is_json_object(getattr(call, "text", None)):
            raise AdapterUnavailable(
                "the adapter returned bytes that are not a JSON object"
            )
        return proposal


def _is_json_object(text: object) -> bool:
    """Whether `text` parses as a JSON object. A predicate, not a parser --
    it builds no proposal and nothing downstream reads its result."""
    if not isinstance(text, str):
        return False
    try:
        return isinstance(json.loads(text), dict)
    except json.JSONDecodeError:
        return False


# --------------------------------------------------------------------------
# The application.
# --------------------------------------------------------------------------


def _mcp(services: Services):
    """The `mcp-v0.1` surface over the same `services`, or `None`.

    `mcp-v0.1` Section 4.5 serves its tools from this process, over the same
    `Services`, beside `/v1` -- one runtime, two surfaces, which is what makes
    that contract's equality cases a statement about one system. The import
    is inside the function because `mcp/surface.py` imports this module.

    **Only a missing package is tolerated, and that is deliberate.** `mcp`
    arrives with the `api` extra, and a checkout that installed the framework
    before this surface landed has fastapi without it; there, `/v1` keeps
    serving and this returns `None`. The guard is on the **package**, not on
    the import of this repository's module over it: an SDK that is installed
    but incompatible raises from that second import, and it propagates. A
    surface that half-built itself and served `/v1` anyway would be a fallback
    runtime with no signal -- Charter Section 9's Milestone 5 gate forbids one,
    and nothing in CI would see it, because a deployment that quietly lost its
    tools looks exactly like one that never had them.
    """
    try:
        import mcp  # noqa: F401
    except ImportError:  # pragma: no cover - the api extra carries mcp
        return None
    # Outside the guard on purpose. Once the package is there, any failure
    # importing this repository's module over it -- a symbol that moved in a
    # later SDK, a defect in the module -- propagates and the process does not
    # start. Catching it here would serve `/v1` with the tool surface silently
    # absent, which is a fallback runtime with no signal (#101 at run time).
    from ..mcp import surface

    return surface.mount(services)


def create_app(
    services: Services, *, cors_origin: str | None = None
) -> "fastapi.FastAPI | _Preflight":
    """The Section 4.1 surface over `services`, with `mcp-v0.1`'s beside it.

    `cors_origin` is Section 4.5's one registered origin (`0.2.0`), or `None`,
    in which case no preflight is admitted and nothing changes from `0.1.x`.
    Registered, the app is returned **wrapped** rather than as the `FastAPI`
    itself; `_Preflight` says why. Both are ASGI applications, which is all
    `serve.build`'s uvicorn and the tests' `TestClient` ask of it.
    """
    mounted = _mcp(services)

    @contextlib.asynccontextmanager
    async def lifespan(app):
        # The MCP session manager answers nothing until it is running, and it
        # runs for the life of the process; entering it here is what makes
        # `PATH` answer under uvicorn and under a `with TestClient(app)`.
        if mounted is None:
            yield
            return
        async with mounted.lifespan():
            yield

    app = fastapi.FastAPI(
        lifespan=lifespan,
        title="Evidence-First RAG Runtime",
        version=CONTRACT_VERSION,
        description=(
            "Contract api-v0.1. Every route dispatches to mvp-v0.1 or"
            " entity-discovery-v0.1; this surface decides nothing about an"
            " answer."
        ),
        # Starlette's default retries an unmatched path with its trailing
        # slash added or removed and answers HTTP 307. Section 4.5 admits a
        # 200 result and six refusal codes and nothing else -- "a client has
        # three branches, not two" -- so a redirect is a fourth, and it would
        # also serve a route at `/v1/query/`, a path Section 4.1 does not
        # name. Off, an unmatched path under `/v1` reaches the 404 handler and
        # leaves as `unknown_route`, which is what that namespace is for.
        redirect_slashes=False,
    )
    _install_refusal_handlers(app)
    _install_routes(app, services)
    if mounted is not None:
        # Before the presentation mount, which takes every path not yet
        # claimed; and not under `/v1`, which Section 4.1 fixes exhaustively.
        # A route at the exact path, not a mount: the protocol posts to `PATH`
        # itself, and with `redirect_slashes` off a mount would not match it.
        from ..mcp.surface import PATH

        app.router.add_route(PATH, mounted, include_in_schema=False, name="mcp")
    _install_presentation(app)
    if cors_origin:
        return _Preflight(app, origin=cors_origin)
    return app


# Section 4.5 at `0.2.0`: the three routes a person's choice is sent to from
# another origin's page. Not `/v1/ask`, not `/v1/health`.
CORS_PATHS = frozenset({NAMESPACE + "/select", NAMESPACE + "/query", NAMESPACE + "/discover"})


class _Preflight:
    """Section 4.5's one exception to `method_not_allowed` (`0.2.0`).

    A pure ASGI wrapper, so it answers **before routing**: an admitted
    preflight reaches no route and opens no connection. It needs all four
    conditions -- `OPTIONS`, one of `CORS_PATHS`, the registered origin, and
    `Access-Control-Request-Method: POST` -- and anything short of all four is
    passed through untouched, to be refused exactly as at `0.1.x`.

    A `POST` from the registered origin to one of the same paths gets the
    response it would have had, plus `Access-Control-Allow-Origin` and
    `Vary: Origin`. Nothing is added for any other origin: the origin is
    compared, never reflected.

    **It wraps the app from outside rather than being added to it, and the
    difference is the catch-all 500.** Starlette builds its stack as
    `[ServerErrorMiddleware] + user_middleware + [ExceptionMiddleware]` and
    routes the handler keyed on `Exception` to the outermost layer, not to the
    inner one every other handler in `_install_refusal_handlers` runs in. An
    `add_middleware` wrapper would therefore sit *inside* the layer that writes
    the `runtime_fault` 500 for an exception nothing named -- a third driver
    condition `runtime/connection.py` does not wrap, or a defect here -- and
    that response would leave carrying neither header. Section 4.5's sentence
    about a `POST` from the registered origin admits no exception, and a
    browser handed a 500 without `Access-Control-Allow-Origin` blocks it: the
    page would show an opaque network error in place of the refusal, which is
    the one response a caller most needs to read. Outside the framework, every
    response passes through `with_origin`.
    """

    def __init__(self, app, *, origin: str) -> None:
        self.app = app
        self.origin = origin.encode("latin-1")

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["path"] not in CORS_PATHS:
            await self.app(scope, receive, send)
            return
        headers = dict(scope["headers"])
        from_origin = headers.get(b"origin") == self.origin
        if (
            scope["method"] == "OPTIONS"
            and from_origin
            and headers.get(b"access-control-request-method") == b"POST"
        ):
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
        if not (scope["method"] == "POST" and from_origin):
            await self.app(scope, receive, send)
            return

        async def with_origin(message):
            if message["type"] == "http.response.start":
                message = dict(message)
                message["headers"] = list(message.get("headers", [])) + [
                    (b"access-control-allow-origin", self.origin),
                    (b"vary", b"Origin"),
                ]
            await send(message)

        await self.app(scope, receive, with_origin)


# Section 4.6's page, and Section 3.2's reason it is not fixed by the contract.
PRESENTATION = pathlib.Path(__file__).resolve().parents[3] / "ui"


def _install_presentation(app: fastapi.FastAPI) -> None:
    """Serve the Section 4.6 page, from outside `/v1`.

    Section 4.5 bounds `unknown_route` to the `/v1` namespace "and nothing
    else", and says why in as many words: without that bound, Section 4.6 would
    oblige a UI a person opens while Section 4.5 turned `GET /` into a 404. So
    this mount is what that sentence was written to permit.

    **It adds no route under `/v1`**, which Section 4.1 fixes exhaustively, and
    Section 9 puts that bound on this slice explicitly. Mounted last, after the
    five routes are registered, so a path under `/v1` reaches one of them or the
    Section 4.5 handler and never this.

    Absent — a checkout that installed the package without the tree beside it —
    the surface still serves the API. The page is a client of it, not a part of
    it, and a missing page is not a reason for `/v1/query` to stop answering.
    """
    if not PRESENTATION.is_dir():  # pragma: no cover - a package without the tree
        return

    # A pin, not a fix -- and the difference is worth stating, because the
    # finding that prompted it (N10 on #187) reasoned from a premise that does
    # not hold here.
    #
    # `StaticFiles` takes a file's media type from `mimetypes.guess_type`, and
    # a module script served as anything but JavaScript is refused by the
    # browser: `GET /` would return the whole page and render nothing, while
    # the suite stayed green, because a status and a byte comparison are
    # identical under either type. The claim was that `.mjs` resolves here only
    # from the system's `/etc/mime.types` and would fall back to `text/plain`
    # in a slim image. **It does not**: `.mjs` is in CPython's own built-in
    # table on the version this repository pins, so `mimetypes.init(files=[])`
    # -- the system table removed -- still answers `text/javascript`.
    #
    # The line stays because what it costs is one call and what it removes is
    # a dependency on an interpreter's built-in table for something a person
    # sees. The test below asserts the served type, which is the part that has
    # force either way.
    mimetypes.add_type("text/javascript", ".mjs")

    # The Section 4.1 paths, **read off the routes already registered** rather
    # than listed again here. A second list is a second place for the five to
    # be wrong, and this one would only be consulted on the failure path, where
    # nobody would notice it had drifted.
    registered = {
        route.path
        for route in app.routes
        if getattr(route, "path", "").startswith(NAMESPACE + "/")
    }

    class _NothingElseUnderTheNamespace:
        """Every `/v1` request the five routes do not answer, **before** the mount.

        Without this, mounting at `/` makes the static files the catch-all for
        the whole tree, and `POST /v1/nowhere` is answered by them: they serve
        GET and HEAD, so it would leave as `method_not_allowed` where Section
        4.5 fixes `unknown_route` — "the path is under `/v1` and is none of
        Section 4.1's". A caller debugging a typo would be told its method was
        the problem.

        Catching everything also swallows the 405 the router would have raised
        for a **known** path with the wrong method, so the two are told apart
        here by the same set the five routes registered. Both refusals stay the
        ones Section 4.5 names.

        Registered here rather than beside the five, because order decides it:
        the router tries routes in registration order, so this comes after them
        and before the mount.

        **It matches every method, and is an ASGI endpoint in order to.** A
        route registered for a list of methods makes `TRACE /v1/nowhere` a
        partial match — the path matches, the method does not — which Starlette
        answers with 405, so a path Section 4.5 calls `unknown_route` would be
        reported as a method problem, for exactly the methods nobody thought to
        list. `starlette.routing.Route` leaves the method set as "any" only for
        an endpoint it treats as ASGI, and a plain function is not one, so this
        is a class with `__call__`. It reads the path and raises: no body is
        read, nothing blocks, and being the one thing under `/v1` that runs on
        the event loop rather than the threadpool costs nothing.
        """

        def __init__(self, registered: frozenset[str]) -> None:
            self._registered = registered

        async def __call__(self, scope, receive, send):
            kind = "method_not_allowed" if scope["path"] in self._registered else "unknown_route"
            raise starlette.exceptions.HTTPException(status_code=REFUSALS[kind])

    nothing_else = _NothingElseUnderTheNamespace(frozenset(registered))

    app.router.add_route(
        "/v1/{rest:path}",
        nothing_else,
        include_in_schema=False,
        name="nothing_else_under_the_namespace",
    )

    # **The bare path, separately, because the pattern above cannot reach it.**
    # `/v1/{rest:path}` compiles to `^/v1/(?P<rest>.*)$`, which wants the
    # slash, so `/v1` matches no registered route and falls through to the
    # mount -- where `StaticFiles` raises 405 on any method but GET and HEAD
    # before it looks for a file, and `POST /v1` would leave as
    # `method_not_allowed`. Section 4.5 fixes `unknown_route` there: `/v1` is
    # under the namespace and is none of Section 4.1's five. The same endpoint
    # answers it, and `/v1` is not in `registered`, so it already yields the
    # right one.
    #
    # Registered for the exact path rather than by widening the pattern to
    # `/v1{rest:path}`: that form would also match `/v1x/query`, pulling a path
    # the contract says nothing about into this rule.
    app.router.add_route(
        NAMESPACE,
        nothing_else,
        include_in_schema=False,
        name="the_bare_namespace",
    )

    app.mount(
        "/",
        fastapi.staticfiles.StaticFiles(directory=PRESENTATION, html=True),
        name="presentation",
    )


def _install_refusal_handlers(app: fastapi.FastAPI) -> None:
    """Every non-200 response the surface produces, in one place (Section 4.5).

    Two of these replace a FastAPI default. Without them a body failing
    Section 4.4 leaves as HTTP 422 with a list-valued `detail` naming the field
    that failed, and an unknown path leaves as 404 with a string one; neither
    is this contract's vocabulary, and the first would also put a value read
    off the request into a refusal body.

    The next two catch the repository's own exception types. Registering them
    on the app rather than wrapping each dispatch keeps the five handlers free
    of error handling, and costs nothing in precision: `ConnectionUnavailable`
    and `Fault` are raised by the session provider and the runtime and by
    nothing else, so neither can be produced by building an envelope.

    The last catches what none of the others names, which is what makes "every
    non-200 response is written by `refusal`" a property of this module rather
    than of the list of exceptions someone thought of. `runtime/connection.py`
    wraps two driver conditions; a third would otherwise leave as a plain-text
    500, and so would any defect here.
    """

    @app.exception_handler(fastapi.exceptions.RequestValidationError)
    async def _malformed(request, error):
        # Deliberately not `str(error)`: Pydantic's message quotes the input,
        # and Section 4.5 keeps a refusal's `detail` free of anything read off
        # the request. The condition is structural, so the sentence is fixed.
        return refusal(
            "malformed_request",
            "the request body must be a JSON object carrying exactly the keys"
            " this route names, each of the stated type (Section 4.4)",
        )

    @app.exception_handler(ConnectionUnavailable)
    async def _database(request, error):
        return refusal(
            "database_unavailable",
            "the database could not be reached, so the request was never"
            " attempted (Section 4.5)",
        )

    @app.exception_handler(Fault)
    async def _fault(request, error):
        return refusal("runtime_fault", RUNTIME_FAULT_DETAIL)

    @app.exception_handler(Exception)
    async def _unexpected(request, error):
        # Nothing is read off `error`, for the reason `refusal` states: a
        # driver's message names a host and a port, and a traceback names a
        # path. The sentence is `Fault`'s, because the condition a caller sees
        # is the same one -- the request failed, and no status family covers it.
        #
        # Registered for `Exception` rather than for a list of types, so a
        # driver condition `runtime/connection.py` does not wrap, and a defect
        # in this module, both land inside Section 4.5's table. The framework
        # re-raises after this response is sent, so a test still sees the
        # exception and a server still logs it; what changes is only what
        # reaches the wire.
        return refusal("runtime_fault", RUNTIME_FAULT_DETAIL)

    @app.exception_handler(starlette.exceptions.HTTPException)
    async def _http(request, error):
        # **The namespace decides before the status code does.** Outside `/v1`
        # this contract says nothing (Section 4.5), so no response there may
        # carry a refusal -- including a 405. Testing the code first made
        # `POST /docs` answer `method_not_allowed`, which told a client that a
        # vocabulary applies to a path the contract disclaims.
        if not _under_namespace(request.url.path):
            # Neither a `result` nor a `refusal`, and not JSON at all, so a
            # client reading the body cannot mistake it for either.
            return starlette.responses.PlainTextResponse(
                "Not Found", status_code=error.status_code
            )
        if error.status_code == REFUSALS["method_not_allowed"]:
            # A fixed sentence. The method is read off the request, and every
            # other detail in this module deliberately carries nothing that was
            # sent to it (Section 4.5).
            return refusal(
                "method_not_allowed",
                "this route does not accept the request method (Section 4.1)",
            )
        if error.status_code == REFUSALS["unknown_route"]:
            return refusal(
                "unknown_route",
                f"no route of Section 4.1 is served at this path under {NAMESPACE}",
            )
        # A status code under `/v1` that is neither of the two above is not a
        # path this table covers; the catch-all below owns it.
        return refusal("runtime_fault", RUNTIME_FAULT_DETAIL)


def _under_namespace(path: str) -> bool:
    return path == NAMESPACE or path.startswith(NAMESPACE + "/")


def _install_routes(app: fastapi.FastAPI, services: Services) -> None:
    """Section 4.1's five routes, each a fixed dispatch to one entry point.

    Each handler makes **one** entry-point call and returns what it gave back.
    There is no branch here on a result's status, and in particular no path
    from `needs_entity_discovery` to a discovery request: Section 4.3 stops the
    surface there and the caller issues the next request.

    **`def`, not `async def`, and that is the whole point.** Every call below
    is blocking -- psycopg opens a connection and runs statements, and
    `/v1/ask` waits on a model. An `async def` handler runs those on the event
    loop, so under the Section 4.7 stack, which is one worker, a ten-second
    `/v1/ask` delays every other request in the process -- including
    `GET /v1/health`, which opens no connection and would then report the
    process dead for a reason that has nothing to do with liveness. Declared
    `def`, Starlette runs each in its threadpool and the loop stays free.

    That is why `SurfaceProposer` takes the record of its own call rather than
    the adapter's last one: concurrency here is real, so shared mutable state
    on the request path is a race rather than a style question.
    """

    @app.post("/v1/query")
    def query(body: QueryBody):
        result = services.runtime.execute(
            RuntimeRequest(route=body.route, arguments=body.arguments)
        )
        return _json(envelope(result))

    @app.post("/v1/discover")
    def discover(body: DiscoverBody):
        result = services.discovery.execute(DiscoveryRequest(arguments=body.arguments))
        return _json(envelope(result))

    @app.post("/v1/select")
    def select(body: SelectBody):
        result = services.selection.execute(SelectionRequest(arguments=body.arguments))
        return _json(envelope(result))

    @app.post("/v1/ask")
    def ask(body: AskBody):
        if services.proposer is None:
            # Section 4.3: the adapter is the only proposer, and nothing runs
            # in its place. Not the Section 4.7 baseline, which mvp-v0.1 keeps
            # off every public interface; not the runtime, which has no request
            # to execute. The runtime is never called.
            return refusal(
                "adapter_unavailable",
                "no adapter is configured, and Section 4.3 admits no other"
                " proposer",
            )
        try:
            proposal = services.proposer.propose(body.request_text)
        except AdapterUnavailable:
            return refusal(
                "adapter_unavailable",
                "the adapter could not be reached, timed out, or returned"
                " nothing parseable as a JSON object (Section 4.5)",
            )
        # Revalidation and execution, in that order, by the module that owns
        # them. Every parseable proposal reaches it, including one outside the
        # mvp-v0.1 Section 4.6 vocabulary: that is a result carrying its
        # evidence, at 200, with the producing layer recorded -- never a 503.
        result = answer(services.runtime, proposal, body.request_text)
        return _json(envelope(result, proposal=proposal_document(proposal, body.request_text)))

    @app.get("/v1/health")
    def health():
        # Section 4.5: neither a result nor a refusal, and identified by
        # carrying neither key. It opens no connection, so it says nothing
        # about the database; a readiness probe that does is Milestone 5's.
        return _json(
            {
                "contracts": dict(CONTRACTS),
                "adapter_configured": services.proposer is not None,
            }
        )
