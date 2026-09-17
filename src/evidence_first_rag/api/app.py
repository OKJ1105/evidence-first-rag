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

import dataclasses
import json

import fastapi
import fastapi.exceptions
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
CONTRACT_VERSION = "0.1.0"

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
    raw text off the call record it kept to decide which side of the line the
    call fell on. There is no second parser producing a proposal.
    """

    adapter: object

    def propose(self, request_text: str) -> Proposal:
        try:
            proposal = self.adapter.propose(request_text)
        except Exception as unreachable:
            raise AdapterUnavailable(
                "the adapter could not be reached"
            ) from unreachable
        calls = getattr(self.adapter, "calls", ())
        if not calls:
            raise AdapterUnavailable("the adapter returned nothing")
        call = calls[-1]
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


def create_app(services: Services) -> fastapi.FastAPI:
    """The Section 4.1 surface over `services`."""
    app = fastapi.FastAPI(
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
    return app


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
    """

    @app.post("/v1/query")
    async def query(body: QueryBody):
        result = services.runtime.execute(
            RuntimeRequest(route=body.route, arguments=body.arguments)
        )
        return _json(envelope(result))

    @app.post("/v1/discover")
    async def discover(body: DiscoverBody):
        result = services.discovery.execute(DiscoveryRequest(arguments=body.arguments))
        return _json(envelope(result))

    @app.post("/v1/select")
    async def select(body: SelectBody):
        result = services.selection.execute(SelectionRequest(arguments=body.arguments))
        return _json(envelope(result))

    @app.post("/v1/ask")
    async def ask(body: AskBody):
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
    async def health():
        # Section 4.5: neither a result nor a refusal, and identified by
        # carrying neither key. It opens no connection, so it says nothing
        # about the database; a readiness probe that does is Milestone 5's.
        return _json(
            {
                "contracts": dict(CONTRACTS),
                "adapter_configured": services.proposer is not None,
            }
        )
