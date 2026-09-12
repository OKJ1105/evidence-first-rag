"""entity-discovery-v0.1 Section 4.3: the discovery request, validated before
any database access.

Modelled on mvp-v0.1's `runtime/request.py`: `DiscoveryRequest` accepts
anything, `validate` returns a `ValidatedDiscovery` or raises a
`DiscoveryRefusal` carrying the Section 5 status, and the service turns the
refusal into a result with its evidence. Nothing here opens a connection.
"""

import dataclasses
import types
from collections.abc import Mapping, Sequence

from ..evidence import ProducingLayer
from ..references import SCOPE_DIMENSIONS
from ..registry import get
from .candidate import ENTITY_KINDS
from .normalize import normalize
from .status import DiscoveryStatus

ROUTE = "entity_discovery"

# Section 4.4: the two discovery templates, and the mvp-v0.1 candidate
# template every route resolves scope with first (Section 4.3).
CANDIDATES_TEMPLATE = "TPL_SNAPSHOT_CANDIDATES_V1"
STATE_TEMPLATE = "TPL_REGISTRY_STATE_V1"
EXACT_TEMPLATE = "TPL_DISCOVERY_EXACT_V1"
LEXICAL_TEMPLATE = "TPL_DISCOVERY_LEXICAL_V1"

# Section 4.3: "At most 200 bytes of UTF-8." In bytes, because everything
# else this contract compares is byte-defined.
TERM_BYTE_LIMIT = 200


class DiscoveryRefusal(Exception):
    def __init__(self, status: DiscoveryStatus, detail: str, *, producing_layer: ProducingLayer | None = None) -> None:
        super().__init__(detail)
        self.status = status
        self.detail = detail
        self.producing_layer = producing_layer


@dataclasses.dataclass(frozen=True, kw_only=True)
class DiscoveryRequest:
    """An `entity_discovery` request. Untrusted until `validate` says so."""

    arguments: object = dataclasses.field(default_factory=dict)


@dataclasses.dataclass(frozen=True, kw_only=True)
class ValidatedDiscovery:
    """A request that passed every Section 4.3 check. Values are text; the
    normalized term is the Section 4.5 token list the lexical template binds."""

    arguments: Mapping[str, str]
    normalized_term: tuple[str, ...]

    @property
    def scope_arguments(self) -> dict[str, str | None]:
        return {name: self.arguments.get(name) for name in SCOPE_DIMENSIONS}

    @property
    def scope_is_complete(self) -> bool:
        return all(name in self.arguments for name in SCOPE_DIMENSIONS)

    @property
    def entity_kind(self) -> str:
        return self.arguments["entity_kind"]

    @property
    def term(self) -> str:
        return self.arguments["term"]

    @property
    def parent_message_key(self) -> str | None:
        return self.arguments.get("parent_message_key")


def allowed_parameters() -> tuple[str, ...]:
    """The route's allowlist, read off the exact template (Section 4.3's
    table and Section 4.4's are the same set)."""
    return get(EXACT_TEMPLATE).allowed_parameters


def validate(request: DiscoveryRequest) -> ValidatedDiscovery:
    """Return the validated request, or raise `DiscoveryRefusal`.

    Order: the argument shape and allowlist (`invalid_request`); then
    `entity_kind`, whose out-of-enumeration value is `unsupported` with the
    runtime as producing layer (Section 5); then the two cross-argument rules
    and the term's limits. Scope completeness is not decided here (Section
    4.3: `ambiguous` and `coverage_gap` depend on the candidate query).
    """
    arguments = _arguments(request.arguments)
    allowed = allowed_parameters()
    unknown = sorted(set(arguments) - set(allowed))
    if unknown:
        raise DiscoveryRefusal(
            DiscoveryStatus.INVALID_REQUEST,
            f"argument(s) {unknown} are outside the allowlist {list(allowed)} for"
            f" route {ROUTE!r} (Section 4.3)",
        )
    values = {name: _value(name, arguments[name]) for name in arguments}

    missing = [name for name in ("entity_kind", "term") if name not in values]
    if missing:
        raise DiscoveryRefusal(
            DiscoveryStatus.INVALID_REQUEST,
            f"required argument(s) {missing} are missing (Section 4.3)",
        )
    if values["entity_kind"] not in ENTITY_KINDS:
        # Section 5: "an entity_kind outside message and signal" is
        # unsupported at the producing layer, which here is the runtime:
        # nothing upstream of this function has represented the request.
        raise DiscoveryRefusal(
            DiscoveryStatus.UNSUPPORTED,
            f"entity_kind {values['entity_kind']!r} is not one of {list(ENTITY_KINDS)}"
            f" (Sections 4.3 and 5, fixture DX-014)",
            producing_layer=ProducingLayer.RUNTIME,
        )
    if "parent_message_key" in values and values["entity_kind"] == "message":
        raise DiscoveryRefusal(
            DiscoveryStatus.INVALID_REQUEST,
            "parent_message_key is permitted only when entity_kind is signal"
            " (Section 4.3, fixture DX-013)",
        )

    term = values["term"]
    if len(term.encode("utf-8")) > TERM_BYTE_LIMIT:
        raise DiscoveryRefusal(
            DiscoveryStatus.INVALID_REQUEST,
            f"term is {len(term.encode('utf-8'))} bytes of UTF-8; Section 4.3 allows"
            f" at most {TERM_BYTE_LIMIT} (fixture DX-012)",
        )
    tokens = tuple(normalize(term))
    if not tokens:
        raise DiscoveryRefusal(
            DiscoveryStatus.INVALID_REQUEST,
            "term has no token after the Section 4.5 normalization (Section 4.3,"
            " fixture DX-012)",
        )
    return ValidatedDiscovery(arguments=types.MappingProxyType(values), normalized_term=tokens)


def _arguments(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise DiscoveryRefusal(
            DiscoveryStatus.INVALID_REQUEST, f"arguments must be a mapping, not {type(value).__name__}"
        )
    for name in value:
        if not isinstance(name, str) or name == "":
            raise DiscoveryRefusal(
                DiscoveryStatus.INVALID_REQUEST, f"argument name {name!r} is not a non-empty string"
            )
    return value


def _value(name: str, value: object) -> str:
    if isinstance(value, str):
        if value == "":
            raise DiscoveryRefusal(DiscoveryStatus.INVALID_REQUEST, f"argument {name!r} is the empty string")
        return value
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        raise DiscoveryRefusal(
            DiscoveryStatus.INVALID_REQUEST,
            f"argument {name!r} carries {len(value)} values; a request names one (Section 4.3)",
        )
    raise DiscoveryRefusal(
        DiscoveryStatus.INVALID_REQUEST, f"argument {name!r} must be a string, not {type(value).__name__}"
    )
