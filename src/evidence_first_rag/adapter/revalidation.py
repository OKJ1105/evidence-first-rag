"""Section 4.6: adapter output is untrusted input, and this is where that bites.

"Before any database access, deterministic revalidation re-checks the route
name against the registry, the argument names against the route allowlist, the
argument values against their declared types, and the scope completeness rule
in Section 4.2. Revalidation failure produces `invalid_request` or
`unsupported` and never reaches SQL."

Four of those five checks already exist: `runtime/request.py` performs them on
every request, adapter-derived or not, because the runtime does not trust its
caller either. Re-implementing them here would create a second copy to drift,
so revalidation delegates and adds the one rule that is genuinely the
adapter's:

**Every argument value must appear verbatim in the request text.** Section
4.6: "The adapter may extract only values explicitly present in the request.
It must not invent a `project_code`, `revision_label`, `network_name`,
`snapshot_label`, `message_key`, or `signal_key`." Fixture `FX-112` registers
the case. This is the check that stands between a plausible-looking
hallucinated identifier and a database lookup that would return real facts
about the wrong thing -- the failure mode the whole contract exists to
prevent, because its output is indistinguishable from a correct answer.

Verbatim means byte-exact whole-token containment, not substring containment:
the value must appear in the request text as its own token, not merely as a
run of characters inside a longer one. A proposal that names a different real
identifier which happens to contain the hallucinated value as a prefix or
suffix (`SAMPLE_MSG_ENGINE_STATUS` inside `SAMPLE_MSG_ENGINE_STATUS_EXTENDED`)
must not pass on containment alone -- that is the same FX-112 hallucination
class, reached a different way. A request saying `sample_msg_engine_status`
and a proposal saying `SAMPLE_MSG_ENGINE_STATUS` is a rewrite, and Charter
Section 9's Milestone 2 gate requires that "explicit canonical entity
references are preserved rather than rewritten". Section 6 already fixes
byte-exact comparison with no case folding for lookup keys; applying the same
rule here keeps one comparison semantics rather than two.
"""

import dataclasses
import re
import types
from collections.abc import Mapping

from ..evidence import EvidenceBundle, Limitation, LimitationKind, ReadOnlySafeguards, SourceTrace
from ..result import Result
from ..routes import UNSUPPORTED_ROUTE, Route
from ..runtime.request import Refusal, Request, validate
from ..runtime.service import ENTITY_DISCOVERY_DETAIL
from ..status import Status


@dataclasses.dataclass(frozen=True, kw_only=True)
class Proposal:
    """What the adapter returned, before anything has checked it.

    Typed as `object` for the same reason `Request` is: Section 4.6 calls this
    untrusted input, and a type that refused a malformed proposal at
    construction would raise where the contract requires a status.
    """

    route: object
    arguments: object = dataclasses.field(default_factory=dict)

    def as_request(self) -> Request:
        return Request(route=self.route, arguments=self.arguments)


def revalidate(proposal: Proposal, request_text: str) -> Request:
    """Return the request to execute, or raise `Refusal`.

    The order is the contract's. `validate` runs first because every later
    question needs a known route and readable arguments: there is no allowlist
    to check names against until the route is known, and no value to compare
    with the request text until the value is known to be text.
    """
    request = proposal.as_request()
    validated = validate(request)
    _values_come_from_the_request(validated.arguments, request_text)
    return request


def _values_come_from_the_request(arguments: Mapping[str, str], request_text: str) -> None:
    if not isinstance(request_text, str):
        raise Refusal(
            Status.INVALID_REQUEST,
            f"the request text must be a string, not {type(request_text).__name__};"
            f" without it no argument value can be checked against what was asked",
        )
    invented = sorted(
        name for name, value in arguments.items() if not _is_verbatim_token(value, request_text)
    )
    if invented:
        raise Refusal(
            Status.INVALID_REQUEST,
            f"argument(s) {invented} carry values that do not appear in the"
            f" request text; Section 4.6 lets the adapter extract only values"
            f" explicitly present in the request",
        )


def _is_verbatim_token(value: str, request_text: str) -> bool:
    """Whole-token containment, not substring containment.

    Raw `in` lets a hallucinated value that happens to be a prefix or suffix
    of a real identifier in the request text (e.g. `SAMPLE_MSG_ENGINE_STATUS`
    inside `SAMPLE_MSG_ENGINE_STATUS_EXTENDED`) pass as if it had been
    explicitly stated, and lets an empty value pass trivially. Word-boundary
    anchoring on both sides requires the value to stand on its own. The
    boundary class covers the full Section 4.11 identifier alphabet
    (`A-Za-z0-9_.-`), not just `_`, so a hallucinated value separated from a
    longer real identifier only by `.` or `-` (e.g.
    `SAMPLE-MSG-ENGINE.STATUS` inside `SAMPLE-MSG-ENGINE.STATUS-EXTENDED`)
    is rejected the same way.
    """
    if value == "":
        return False
    pattern = rf"(?<![A-Za-z0-9_.\-]){re.escape(value)}(?![A-Za-z0-9_.\-])"
    return re.search(pattern, request_text) is not None


def refused(refusal: Refusal, proposal: Proposal, *, fixture_provenance=()) -> Result:
    """The Section 5 result for a request that revalidation stopped.

    Section 5 gives all three of these outcomes no database connection, and
    Section 7 makes every field that would describe an execution an explicit
    empty value -- `bound_parameters` above all, because the arguments the
    adapter proposed are exactly what a rejected proposal consists of.

    Deliberately built here rather than reached for inside the runtime: this
    is the adapter layer refusing, and `runtime/service.py` has no request
    text and no proposal to refuse. `tests/test_adapter_revalidation.py`
    asserts this produces the same evidence the runtime produces for a refusal
    it can see for itself, so the two cannot drift apart unnoticed.
    """
    limitations = ()
    if refusal.status is Status.NEEDS_ENTITY_DISCOVERY:
        limitations = (
            Limitation(
                kind=LimitationKind.ENTITY_DISCOVERY_NOT_IMPLEMENTED,
                detail=f"{ENTITY_DISCOVERY_DETAIL} {refusal.detail}",
            ),
        )
    return Result(
        status=refusal.status,
        evidence_bundle=EvidenceBundle(
            route=_route_name(proposal.route),
            read_only_safeguards=ReadOnlySafeguards(
                role_name="", read_only_transaction=False, connection_opened=False
            ),
        ),
        source_trace=SourceTrace(
            producing_layer=refusal.producing_layer,
            fixture_provenance=tuple(fixture_provenance),
        ),
        limitations=limitations,
    )


def _route_name(value: object) -> str:
    if isinstance(value, Route):
        return value.value
    if isinstance(value, str) and value != "":
        return value
    return UNSUPPORTED_ROUTE


def answer(runtime, proposal: Proposal, request_text: str) -> Result:
    """The whole adapter path: revalidate, then execute or refuse.

    Nothing reaches `runtime.execute` that has not passed revalidation, which
    is Section 4.6's "never reaches SQL" as control flow rather than as a
    promise. The runtime then validates again -- it does not trust its caller
    either, and that second pass is pure and cheap.
    """
    try:
        request = revalidate(proposal, request_text)
    except Refusal as refusal:
        return refused(refusal, proposal, fixture_provenance=runtime.fixture_provenance)
    return runtime.execute(request)
