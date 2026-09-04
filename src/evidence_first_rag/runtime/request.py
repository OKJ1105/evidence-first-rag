"""Route validation: everything Section 4.5 requires before any database access.

Section 4.5: "Route validation runs before any database access and rejects a
request whose scope is missing, unknown, contradictory, or implicitly
defaulted." Section 4.6 adds that adapter output is untrusted input, and that
revalidation "never reaches SQL" when it fails. Both rules make the same
structural demand: nothing in this module opens a connection, and the runtime
calls it before it opens one.

`Request` therefore accepts anything. Typing its fields as `object` is the
point rather than an omission -- a `Request` that refused a malformed route at
construction would raise where Section 5 requires a status, and the caller
would have to catch the exception to produce that status anyway.

The refusals here are raised as `Refusal` and turned into a `Result` by
`service.py`, which is the only module that can build one: a refusal knows its
status and its reason, and the evidence bundle around it is the runtime's.
"""

import dataclasses
import types
from collections.abc import Mapping, Sequence

from ..evidence import ProducingLayer
from ..references import SCOPE_DIMENSIONS
from ..registry import get
from ..routes import UNSUPPORTED_ROUTE, Route, route_or_none
from ..status import Status

# Section 4.5's table, as the route-to-template binding it fixes.
ROUTE_TEMPLATE = types.MappingProxyType(
    {
        Route.MESSAGE_FACTS: "TPL_MESSAGE_FACTS_V1",
        Route.SIGNAL_FACTS: "TPL_SIGNAL_FACTS_V1",
        Route.SIGNAL_MAPPING: "TPL_SIGNAL_MAPPING_V1",
    }
)

# Section 4.4: the template every route resolves scope with, before it
# dispatches. Not a route of its own -- Section 4.5 registers three.
CANDIDATES_TEMPLATE = "TPL_SNAPSHOT_CANDIDATES_V1"


class Refusal(Exception):
    """A request refused before any database access.

    Carries the Section 5 status the refusal produces and the detail that
    explains it. `producing_layer` is set only for `unsupported`, which is the
    one status Section 7 requires the trace to attribute to a layer.
    """

    def __init__(
        self,
        status: Status,
        detail: str,
        *,
        producing_layer: ProducingLayer | None = None,
    ) -> None:
        super().__init__(detail)
        self.status = status
        self.detail = detail
        self.producing_layer = producing_layer


@dataclasses.dataclass(frozen=True, kw_only=True)
class Request:
    """What the runtime is asked to do. Untrusted until `validate` says so.

    `scope_selected_by_user` is Section 4.2's one permitted way to narrow an
    under-specified scope: "Scope may be narrowed to one candidate only by an
    explicit user selection, which Section 7 requires to be recorded in
    `limitations`." The flag is the caller's assertion that the complete scope
    in `arguments` came from such a selection; the runtime cannot verify it
    after the fact, and records it rather than inferring it. Without a way to
    say this, Section 7's third required `limitations` entry has no path to
    exist.
    """

    route: object
    arguments: object = dataclasses.field(default_factory=dict)
    scope_selected_by_user: object = False


@dataclasses.dataclass(frozen=True, kw_only=True)
class ValidatedRequest:
    """A request that passed every Section 4.5 check. Values are text."""

    route: Route
    arguments: Mapping[str, str]
    scope_selected_by_user: bool

    @property
    def template_name(self) -> str:
        return ROUTE_TEMPLATE[self.route]

    @property
    def scope_arguments(self) -> dict[str, str | None]:
        """The four dimensions as `TPL_SNAPSHOT_CANDIDATES_V1` takes them.

        An omitted dimension binds as None, which the registered SQL tests for
        null. Section 4.2 forbids the runtime from supplying it, and None is
        how the query says "not narrowed by this dimension" without the
        runtime choosing a value for it.
        """
        return {name: self.arguments.get(name) for name in SCOPE_DIMENSIONS}

    @property
    def scope_is_complete(self) -> bool:
        return all(name in self.arguments for name in SCOPE_DIMENSIONS)


def allowed_parameters(route: Route) -> tuple[str, ...]:
    """The route's argument allowlist.

    Read off the registered template rather than restated here. Section 4.5's
    "Required arguments" column and Section 4.4's "Allowed parameters" column
    describe the same set for all three routes, and two copies of one list
    drift; `tests/test_runtime_requests.py` pins the derived value against
    Section 4.5's own wording so that a template change cannot widen a route
    unnoticed.
    """
    return get(ROUTE_TEMPLATE[route]).allowed_parameters


def required_lookup_keys(route: Route) -> tuple[str, ...]:
    """The route's required arguments that are not scope dimensions.

    Section 4.2 governs a missing scope dimension and assigns it to
    `ambiguous` or `coverage_gap`; Section 5 assigns a reference that cannot
    be formed at all to `needs_entity_discovery`. The split is which of the
    two rules applies, so it is drawn on the same list Section 4.2 fixes.
    """
    template = get(ROUTE_TEMPLATE[route])
    return tuple(
        name for name in template.required_parameters if name not in SCOPE_DIMENSIONS
    )


def validate(request: Request) -> ValidatedRequest:
    """Return the validated request, or raise `Refusal`.

    The order of the checks is the order their statuses are decided in, and it
    is deliberate:

    1. An unknown route is `unsupported`; there is no allowlist to check
       arguments against until a route is known.
    2. Malformed or out-of-allowlist arguments are `invalid_request`. A
       malformed request is answered as malformed even when it also fails a
       later check, because the later checks read values this one has not
       established are readable.
    3. A missing lookup key is `needs_entity_discovery`, which Section 4.6
       makes terminal, so it is decided before anything that would open a
       connection.
    4. Scope completeness is *not* decided here. Section 4.2 sends an
       under-specified scope to `ambiguous` or `coverage_gap`, and both
       depend on what the candidate query returns.
    """
    route = route_or_none(request.route)
    if route is None:
        # Section 5: "The trace records whether the adapter or the runtime
        # produced it." The adapter emitting its own `unsupported` literal
        # (Section 4.6) is the adapter's refusal; anything else is this
        # layer refusing to recognise what the adapter sent.
        produced_by_adapter = request.route == UNSUPPORTED_ROUTE
        raise Refusal(
            Status.UNSUPPORTED,
            f"{request.route!r} is not one of the three routes Section 4.5"
            f" approves: {[member.value for member in Route]}",
            producing_layer=(
                ProducingLayer.ADAPTER if produced_by_adapter else ProducingLayer.RUNTIME
            ),
        )

    arguments = _arguments(request.arguments)
    allowed = allowed_parameters(route)
    unknown = sorted(set(arguments) - set(allowed))
    if unknown:
        raise Refusal(
            Status.INVALID_REQUEST,
            f"argument(s) {unknown} are outside the allowlist {list(allowed)}"
            f" for route {route.value!r} (Section 4.5)",
        )
    values = {name: _value(name, arguments[name]) for name in arguments}

    selected = request.scope_selected_by_user
    if not isinstance(selected, bool):
        raise Refusal(
            Status.INVALID_REQUEST,
            f"scope_selected_by_user must be a bool, not"
            f" {type(selected).__name__}",
        )
    complete = all(name in values for name in SCOPE_DIMENSIONS)
    if selected and not complete:
        # Section 4.2 permits an explicit user selection to narrow scope to
        # one candidate. A request that claims the selection while still
        # omitting a dimension contradicts itself, and answering it would
        # record a `limitations` entry for a narrowing that did not happen.
        raise Refusal(
            Status.INVALID_REQUEST,
            "scope_selected_by_user claims an explicit selection, but the"
            f" scope omits {sorted(set(SCOPE_DIMENSIONS) - set(values))}"
            f" (Section 4.2)",
        )

    missing = [name for name in required_lookup_keys(route) if name not in values]
    if missing:
        raise Refusal(
            Status.NEEDS_ENTITY_DISCOVERY,
            f"route {route.value!r} is determined, but {missing} is missing, so"
            f" no canonical reference can be formed (Sections 4.2 and 5)",
        )

    return ValidatedRequest(
        route=route,
        arguments=types.MappingProxyType(values),
        scope_selected_by_user=selected,
    )


def _arguments(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise Refusal(
            Status.INVALID_REQUEST,
            f"arguments must be a mapping, not {type(value).__name__}",
        )
    for name in value:
        if not isinstance(name, str) or name == "":
            raise Refusal(
                Status.INVALID_REQUEST,
                f"argument name {name!r} is not a non-empty string",
            )
    return value


def _value(name: str, value: object) -> str:
    """One argument value, as the text it has to be.

    Section 5 lumps "malformed, contradictory, or ... outside the route
    allowlist" into one status, so the distinction below changes the detail
    and not the outcome. It is drawn anyway because Section 8.1 registers a
    contradictory scope as its own case (`FX-110`, "two different
    `revision_label` values"), and a request that carries two values for one
    dimension is the only shape a contradiction can take: a mapping holds one
    value per name, so the second value has to arrive inside the first.
    """
    if isinstance(value, str):
        if value == "":
            raise Refusal(
                Status.INVALID_REQUEST, f"argument {name!r} is the empty string"
            )
        return value
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        offered = list(value)
        raise Refusal(
            Status.INVALID_REQUEST,
            f"argument {name!r} carries {len(offered)} values {offered!r};"
            f" a canonical reference names one (Section 4.2)",
        )
    raise Refusal(
        Status.INVALID_REQUEST,
        f"argument {name!r} must be a string, not {type(value).__name__}",
    )
