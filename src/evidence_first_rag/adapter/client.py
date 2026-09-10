"""The one place a language model is called, and the only file that imports the SDK.

Section 4.6 pins the model and requires the decoding configuration to be
recorded with the evaluation run: "Model: `claude-opus-5`, pinned. The decoding
configuration is recorded with the evaluation run. Changing either reopens the
Milestone 2 comparison in Section 8."

So `DECODING` below is a frozen mapping, it is what the request is built from,
and `Adapter.configuration()` returns it for the artifact. Editing it is a
Section 8 event, not a tuning knob.

Not imported by `adapter/__init__.py`: the revalidation path, the baseline and
the comparison harness are all testable without the SDK and without a network,
which is what lets the pure suite run this slice from a clean checkout.

Output is constrained by `output_config.format` rather than parsed out of
prose. That is Section 4.6's "schema-constrained structured object" as a
request parameter: the route enum is closed in the schema, so `route` comes
back as one of the four permitted strings or the call fails, rather than as
something revalidation has to recognise as wrong.

**What each call leaves behind.** `propose` used to return `self.read(response)`
and drop the response, so the first Milestone 2 comparison could report that
forty-eight proposals were refused without being able to show a single thing
the model wrote. Every call now appends a `Call` to the adapter: the text
block `read` parsed, the `stop_reason`, and `usage` when the SDK exposes it.
That is a record of what came *back*; **nothing new is sent**, so Charter
Section 3.3 and Section 4.6's list of what the adapter may be told are
untouched, and `tests/test_adapter_vocabulary.py` still holds the request
side.

The records are the adapter's, not the artifact's, and `run.py` decides where
they go -- into a second file that is never committed, because raw model text
is unbounded and is exactly what the `SAMPLE_*` convention cannot vouch for.
"""

import dataclasses
import json
import types
from collections.abc import Mapping

import anthropic

from . import vocabulary
from .revalidation import Proposal

# Section 4.6, pinned. The identifier is the contract's, not a default.
MODEL = "claude-opus-5"


def _keep_duplicates(pairs):
    """Turn a repeated JSON key into a multi-valued argument, not a last-win.

    Section 8.1 registers `FX-110` as "contradictory scope, for example two
    different `revision_label` values", and a model that emitted the key twice
    is exactly that. Plain `json.loads` keeps the last occurrence and drops
    the first, so the contradiction disappears before revalidation can see it
    and `FX-110` becomes unreachable through the adapter -- found by an
    external review, and reproduced.

    Collecting them into a list is what makes the conflict representable: a
    Python mapping cannot hold one key twice, and `runtime/request.py` already
    refuses a multi-valued argument as contradictory. So the adapter reports
    what the model said, and the deterministic layer decides what it means,
    which is the division Section 4.6 draws.
    """
    document = {}
    for key, value in pairs:
        if key not in document:
            document[key] = value
            continue
        existing = document[key]
        document[key] = (
            [*existing, value] if isinstance(existing, list) else [existing, value]
        )
    return document

# The decoding configuration Section 4.6 requires recorded. Frozen so that the
# artifact records what ran and a change is visible in the diff.
#
# `effort: low` because the task is extraction from one sentence against a
# closed vocabulary, not reasoning; the guidance for Claude Opus 5 is that low
# effort suits simple extraction, and a higher setting would spend tokens on a
# decision the schema has already narrowed to four routes. `max_tokens` is
# generous relative to an output of a few dozen tokens so that a long argument
# list cannot truncate mid-JSON.
DECODING = types.MappingProxyType(
    {
        "model": MODEL,
        "max_tokens": 4096,
        "output_config": {"effort": "low"},
        "thinking": {"type": "adaptive"},
    }
)


@dataclasses.dataclass(frozen=True, kw_only=True)
class Call:
    """What one model call returned, before anything parsed it.

    Three fields, and each answers a question the first comparison could not.
    `text` is what `read` parsed, so a proposal that came back `unsupported`
    can be told apart from a model that wrote nothing and one that wrote
    something unparseable. `stop_reason` separates a refusal from a length
    cut. `usage` is what the call cost.

    `usage` is `None` rather than an empty mapping when the SDK exposed
    nothing: a run that could not observe its own cost must not report zero,
    the way `Report.executed` refuses to treat "no database" as "nothing
    weakened".
    """

    text: str
    stop_reason: str | None
    usage: dict | None

    def as_json(self) -> dict:
        return {
            "text": self.text,
            "stop_reason": self.stop_reason,
            "usage": self.usage,
        }


def _first_text(response) -> str:
    """The first `text` block, or `""`. The one place this is decided.

    `read` parses it and `Call` records it, and they must be the same string
    or the raw file would explain a proposal that was never parsed from it.
    """
    return next((block.text for block in response.content if block.type == "text"), "")


def _usage_as_json(response) -> dict | None:
    """`response.usage` as a plain mapping, or `None` when there is none.

    The SDK returns a model object; `model_dump()` gives plain Python types
    that survive `json.dumps`. A stub in a test may hand back a mapping, or an
    object with neither -- and this must not raise on any of them, because a
    run that failed to record its own token count is still a run whose
    proposals are the point.
    """
    usage = getattr(response, "usage", None)
    if usage is None:
        return None
    if isinstance(usage, Mapping):
        return dict(usage)
    for name in ("model_dump", "to_dict"):
        method = getattr(usage, name, None)
        if not callable(method):
            continue
        try:
            dumped = method()
        except Exception:  # noqa: BLE001 -- see the docstring
            return None
        if isinstance(dumped, Mapping):
            return dict(dumped)
        # A `model_dump` that returned something else is not usage. Falling
        # through rather than raising is the docstring's promise: the token
        # count is the least important thing this run produces.
        return None
    attributes = getattr(usage, "__dict__", None)
    return dict(attributes) if isinstance(attributes, Mapping) else None


@dataclasses.dataclass(frozen=True, kw_only=True)
class Adapter:
    """Section 4.6's Thin LLM Adapter. Proposes; never decides."""

    client: object
    # Per-call records, in call order. A list inside a frozen dataclass: the
    # frozen-ness is about the client and the pinned configuration, and
    # appending here rebinds nothing. Excluded from comparison so that adding
    # a record does not change what an `Adapter` equals.
    _records: list = dataclasses.field(
        default_factory=list, repr=False, compare=False
    )

    @property
    def calls(self) -> tuple[Call, ...]:
        """What every call so far returned, in the order they were made."""
        return tuple(self._records)

    @classmethod
    def from_environment(cls) -> "Adapter":
        """Build a client from whatever credential the environment carries.

        No key is read, stored, or logged here -- the SDK resolves it, and
        AGENTS.md keeps secret material out of this repository entirely.
        """
        return cls(client=anthropic.Anthropic())

    def propose(self, request_text: str) -> Proposal:
        """One request in, one `{route, arguments}` proposal out.

        The call carries the fixed instructions, the route and scope
        vocabulary, and the request. It carries no row, no fixture and no
        evidence bundle; `vocabulary.payload()` is built from the contract's
        own metadata and `tests/test_adapter_vocabulary.py` searches the
        assembled payload for every fixture identifier and fails on a hit.
        """
        parameters = dict(DECODING)
        # The schema joins the pinned `output_config` rather than replacing
        # it. Splatting `DECODING` and then passing `output_config` again
        # would send the key twice; `tests/test_adapter_client.py` caught that
        # before any call was made, which is what the recording stub is for.
        output_config = dict(parameters.pop("output_config"))
        output_config["format"] = {
            "type": "json_schema",
            "schema": vocabulary.schema(),
        }
        response = self.client.messages.create(
            **parameters,
            output_config=output_config,
            system=[
                {"type": "text", "text": vocabulary.instructions()},
                {
                    "type": "text",
                    "text": vocabulary.as_text(vocabulary.payload()),
                    # The metadata block is identical on every call, so it is
                    # the cacheable prefix; the request text follows it and is
                    # the only thing that varies.
                    "cache_control": {"type": "ephemeral"},
                },
            ],
            messages=[{"role": "user", "content": request_text}],
        )
        self._records.append(
            Call(
                text=_first_text(response),
                stop_reason=getattr(response, "stop_reason", None),
                usage=_usage_as_json(response),
            )
        )
        return self.read(response)

    @staticmethod
    def read(response) -> Proposal:
        """The proposal a response carries, or an `unsupported` one.

        A refusal or an empty response is not an error to raise: Section 4.6
        gives the adapter one way to say "no route applies", and a model that
        declined to answer has said exactly that. Turning it into an exception
        would make the comparison harness lose a case it should count.
        """
        if getattr(response, "stop_reason", None) == "refusal":
            return Proposal(route=vocabulary.UNSUPPORTED_ROUTE, arguments={})
        text = _first_text(response)
        try:
            document = json.loads(text, object_pairs_hook=_keep_duplicates)
        except json.JSONDecodeError:
            return Proposal(route=vocabulary.UNSUPPORTED_ROUTE, arguments={})
        if not isinstance(document, dict):
            return Proposal(route=vocabulary.UNSUPPORTED_ROUTE, arguments={})
        # Deliberately unvalidated beyond shape: revalidation is what judges a
        # proposal, and an adapter that pre-filtered its own output would hide
        # the failures the Milestone 2 comparison exists to measure.
        return Proposal(
            route=document.get("route"), arguments=document.get("arguments", {})
        )

    @staticmethod
    def configuration() -> dict:
        """What Section 4.6 requires recorded with the evaluation run."""
        return json.loads(json.dumps(dict(DECODING)))
