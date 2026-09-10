"""Exactly what the adapter is allowed to see, and nothing else.

Section 4.6: "The adapter receives the user request and the route, argument,
and scope-vocabulary metadata required to fill the schema. It receives no
database rows, no fixture contents, and no evidence bundle, per Charter
Section 3.3."

That is a rule about a payload, so the payload is built here, from the
registry and the route table, and there is no parameter on any function below
through which a row could arrive. `tests/test_adapter_vocabulary.py` asserts
the absence directly: it builds the payload, then searches it for every
identifier the fixtures contain, and fails if one appears.

**Scope vocabulary is the delicate word.** Naming the loaded `project_code`
values would be database content -- the adapter would learn which projects
exist and could then produce one the user never typed. So the scope vocabulary
here is the *names* of Section 4.2's four dimensions and what each means, not
their values. An adapter that needs to know a value must read it in the
request, which is Section 4.6's rule anyway: "may extract only values
explicitly present in the request".
"""

import json

from ..references import SCOPE_DIMENSIONS
from ..routes import UNSUPPORTED_ROUTE, Route

__all__ = [
    "DIMENSION_MEANINGS",
    "ROUTE_MEANINGS",
    "UNSUPPORTED_ROUTE",
    "as_text",
    "instructions",
    "payload",
    "schema",
]
from ..runtime.request import allowed_parameters, required_lookup_keys

# What each of Section 4.2's dimensions is, in words rather than values. The
# adapter needs enough to recognise one in a sentence and nothing more.
DIMENSION_MEANINGS = {
    "project_code": "the project the request is about",
    "revision_label": "the revision of that project",
    "network_name": "the communication network within the revision",
    "snapshot_label": "the particular source snapshot within that network",
}

ROUTE_MEANINGS = {
    Route.MESSAGE_FACTS: "facts about one message occurrence",
    Route.SIGNAL_FACTS: "facts about one signal occurrence inside a message",
    Route.SIGNAL_MAPPING: "the asserted mappings whose source is one signal",
}


def payload() -> dict:
    """The metadata half of the adapter call. Contains no database content.

    Built rather than written out, so that a route added to Section 4.5 or an
    argument added to a template reaches the adapter without a second list
    being edited -- and so that nothing here can drift into naming a value.
    """
    return {
        "routes": [
            {
                "name": route.value,
                "means": ROUTE_MEANINGS[route],
                "arguments": list(allowed_parameters(route)),
                "required_lookup_keys": list(required_lookup_keys(route)),
            }
            for route in Route
        ],
        "unsupported_route": UNSUPPORTED_ROUTE,
        "scope_dimensions": [
            {"name": name, "means": DIMENSION_MEANINGS[name]}
            for name in SCOPE_DIMENSIONS
        ],
    }


# The schema the adapter's output is constrained to. Section 4.6: "a
# schema-constrained structured object whose `route` is one of the three names
# in Section 4.5 or the literal `unsupported`, and whose `arguments` contain
# only the parameter names that route allows."
#
# The route enum is closed here, so an unknown route cannot be returned at all.
# That is the one constraint this schema is asked to carry.
#
# **The argument names are deliberately open.** They were enumerated as
# `properties` with `additionalProperties: false` until #111, and the
# enumeration cost a whole Milestone 2 comparison run. `properties` is an
# ordered mapping, and the second run (`d2f08cb8`) shows all 41
# argument-bearing calls emitting keys in ascending property order, starting
# at `project_code`. The three names sorted before it -- `mapping_key`,
# `message_key`, `network_name` -- were therefore unreachable once the object
# had opened, and were emitted on 0 of 33 positive cases. Two of them are
# required lookup keys, so every positive case refused.
#
# **Where to check that.** Not from this tree today: the run's artifact is
# not committed yet and the per-call raw record never is, by design (see
# `run.py`). The reading and an independent adjudication that recomputed
# every figure from the primary data are on #91 -- the finding at
# `issues/91#issuecomment-5611514697`, the adjudication at
# `#issuecomment-5611662689`. The artifact itself lands under
# `docs/acceptance/` when #58 commits it; until then #91 is the record, and
# a reader deciding whether to re-close this enumeration should start there
# rather than from the run identifier alone.
#
# Closing the names here was never the trust boundary and could not be one:
# JSON Schema cannot express "the allowlist of whichever route you chose"
# without a oneOf per route, so the flat enumeration accepted `signal_key` on
# `message_facts` anyway. Section 4.6 puts the check where it belongs --
# adapter output is untrusted, and `runtime/request.py` `validate()` refuses
# an unknown argument name as `invalid_request` before any SQL.
# `tests/test_adapter_revalidation.py` asserts that refusal. This schema
# narrows the route and nothing else; read it that way.
def schema() -> dict:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["route", "arguments"],
        "properties": {
            "route": {
                "type": "string",
                "enum": [route.value for route in Route] + [UNSUPPORTED_ROUTE],
            },
            "arguments": {"type": "object", "additionalProperties": {"type": "string"}},
        },
    }


def instructions() -> str:
    """The system prompt. Fixed text; it carries no request and no data.

    Written as prohibitions because Section 4.6's rules are prohibitions, and
    because the deterministic revalidation behind this will refuse anyway --
    the prompt exists to make the refusals rare, not to be the enforcement.
    """
    return (
        "You convert one engineering data request into a route and arguments.\n"
        "\n"
        "Rules you must follow:\n"
        "- Choose exactly one route from the list you are given, or the"
        f" literal {UNSUPPORTED_ROUTE!r} when no route fits the request.\n"
        "- Use only argument names that the chosen route lists.\n"
        "- Copy argument values verbatim from the request text. Do not"
        " translate, expand, correct, case-fold, or complete them. If a value"
        " is not written in the request, leave the argument out.\n"
        "- Never invent a project, revision, network, snapshot, message or"
        " signal identifier. An omitted argument is always better than a"
        " guessed one; a later step turns a missing one into a safe outcome"
        " and a wrong one into a wrong answer.\n"
        "- You are not deciding whether the request can be answered. Something"
        " deterministic checks your output and refuses it if it is wrong.\n"
    )


def as_text(document: dict) -> str:
    """Stable JSON for the metadata block, so the prompt prefix can cache."""
    return json.dumps(document, indent=2, sort_keys=True)
