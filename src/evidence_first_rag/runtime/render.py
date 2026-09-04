"""Section 4.8: user-facing prose, rendered from a fixed template.

"The renderer inserts values from the result and never adds a fact, a
qualifier, or an inference. No model generates answer prose in v0.1."

That is a claim about where every character of the answer came from, and a
renderer that returned a finished string would leave it unverifiable: given
"transmit_period_ms: 10", nothing downstream can tell the 10 that came from a
row from a 10 the renderer chose. So an answer is built as a sequence of
segments that remember which they are. `Prose` is fixed text, and the fixed
text a renderer may use is closed: the `FRAGMENTS` table below, plus the
result-column names the registry already fixes. `Value` is text taken from the
result and from nowhere else.

Section 4.9's check `E1` -- "Every value in the rendered answer is present in
the normalized result" -- is then a comparison over `Answer.values()` rather
than a search through a string, and its mirror, that every `Prose` came from
the registered fixed text, is a comparison over `Answer.prose()`.
"""

import dataclasses

from ..references import SCOPE_DIMENSIONS
from ..registry import REGISTERED
from ..result import Result
from ..status import Status

# Every piece of fixed text the renderer may emit. Closed on purpose: a
# sentence that is not here cannot reach an answer, which is how "no model
# generates answer prose" is enforced rather than described.
FRAGMENTS = {
    "route": "Route: ",
    "status": "Status: ",
    "scope": "Resolved scope: ",
    "scope_separator": " / ",
    "field_separator": ", ",
    "label_separator": ": ",
    "null": "null",
    "row_marker": "- ",
    "limitation": "Limitation ",
    "limitation_open": " (",
    "limitation_close": "): ",
    "line": "\n",
    "stop": ".",
}

# One opening sentence per Section 5 status, restating the condition Section 5
# assigns to it. Restating the contract adds no fact: every one of these is
# true of the result by construction, because the status is what put it here.
OPENING = {
    Status.SUCCESS: "The registered template returned these rows.",
    Status.NOT_FOUND: (
        "Scope resolved to one snapshot within approved coverage, and no row"
        " matched the lookup key."
    ),
    Status.COVERAGE_GAP: (
        "The approved data scope does not contain, or could not be established"
        " to contain, the coverage this request needs."
    ),
    Status.UNSUPPORTED: (
        "This request cannot be represented by an approved contract at the"
        " producing layer."
    ),
    Status.AMBIGUOUS: (
        "Scope is missing or under-specified. These candidate snapshots match;"
        " the runtime does not choose between them."
    ),
    Status.INVALID_REQUEST: (
        "Scope or arguments are malformed, contradictory, or name a parameter"
        " outside the route allowlist."
    ),
    Status.NEEDS_ENTITY_DISCOVERY: (
        "The route is determined, but no canonical reference could be formed."
    ),
}

# The labels a row may carry. Section 4.4 records each template's "result
# column list in order", so a column name is registered vocabulary rather than
# prose the renderer chose, and reusing it keeps the answer readable against
# the same names the evidence bundle uses.
COLUMN_LABELS = frozenset(
    column for template in REGISTERED for column in template.result_columns
)


@dataclasses.dataclass(frozen=True)
class Prose:
    """Fixed text. Comes from `FRAGMENTS`, `OPENING`, or a column label."""

    text: str


@dataclasses.dataclass(frozen=True)
class Value:
    """Text taken from the normalized result."""

    text: str


@dataclasses.dataclass(frozen=True)
class Answer:
    """A rendered answer, kept as the segments it was assembled from."""

    segments: tuple[Prose | Value, ...]

    def render(self) -> str:
        return "".join(segment.text for segment in self.segments)

    def values(self) -> tuple[str, ...]:
        return tuple(s.text for s in self.segments if isinstance(s, Value))

    def prose(self) -> tuple[str, ...]:
        return tuple(s.text for s in self.segments if isinstance(s, Prose))


def render(result: Result) -> str:
    """The answer for `result`, as text."""
    return compose(result).render()


def values_of(result: Result) -> frozenset[str]:
    """Every string the normalized result contains.

    This is the right-hand side of Section 4.9's check `E1`, "Every value in
    the rendered answer is present in the normalized result". It lives here
    rather than in a test because two suites and, later, the conformance
    runner all have to compare against the same set; three copies of it would
    make `E1` mean three things, and the one that drifted would be the one
    that passed.

    Values are compared as text, because that is what an answer is made of. A
    numeric value contributes `str(value)` at its stored precision, which is
    the form Section 6 requires the renderer to keep.
    """
    bundle = result.evidence_bundle
    trace = result.source_trace
    values = {
        result.status.value,
        bundle.route,
        bundle.template_name,
        bundle.template_version,
        bundle.contract_identifier,
        bundle.contract_version,
        bundle.collation,
        bundle.read_only_safeguards.role_name,
        str(bundle.row_count),
    }
    scopes = list(trace.contributing_scopes)
    if bundle.resolved_scope is not None:
        scopes.append(bundle.resolved_scope)
    for provenance in trace.mapping_provenance:
        scopes += [
            provenance.asserting_scope,
            provenance.source_endpoint_scope,
            provenance.target_endpoint_scope,
        ]
    for scope in scopes:
        values.update(getattr(scope, dimension) for dimension in SCOPE_DIMENSIONS)
    for row in result.rows:
        values.update(str(value) for value in row.values() if value is not None)
    for parameter in bundle.bound_parameters.values():
        if parameter is not None:
            values.add(str(parameter))
    for limitation in result.limitations:
        values.add(limitation.kind.value)
        values.add(limitation.detail)
    if trace.producing_layer is not None:
        values.add(trace.producing_layer.value)
    values.update(trace.fixture_provenance)
    return frozenset(values)


def compose(result: Result) -> Answer:
    """Assemble the answer for `result`.

    Every branch reads the result and the tables above, and nothing else.
    There is no argument for a tone, a length, or a locale, because each would
    be a decision about the answer that the result does not contain.
    """
    bundle = result.evidence_bundle
    segments: list[Prose | Value] = [
        Prose(OPENING[result.status]),
        Prose(FRAGMENTS["line"]),
        Prose(FRAGMENTS["route"]),
        Value(bundle.route),
        Prose(FRAGMENTS["field_separator"]),
        Prose(FRAGMENTS["status"]),
        Value(result.status.value),
        Prose(FRAGMENTS["stop"]),
        Prose(FRAGMENTS["line"]),
    ]

    if bundle.resolved_scope is not None:
        segments.append(Prose(FRAGMENTS["scope"]))
        segments.extend(_scope(bundle.resolved_scope))
        segments.append(Prose(FRAGMENTS["stop"]))
        segments.append(Prose(FRAGMENTS["line"]))

    for row in result.rows:
        segments.append(Prose(FRAGMENTS["row_marker"]))
        segments.extend(_row(row))
        segments.append(Prose(FRAGMENTS["line"]))

    for limitation in result.limitations:
        segments.append(Prose(FRAGMENTS["limitation"]))
        segments.append(Prose(FRAGMENTS["limitation_open"]))
        segments.append(Value(limitation.kind.value))
        segments.append(Prose(FRAGMENTS["limitation_close"]))
        segments.append(Value(limitation.detail))
        segments.append(Prose(FRAGMENTS["line"]))

    return Answer(segments=tuple(segments))


def _scope(scope):
    for position, dimension in enumerate(SCOPE_DIMENSIONS):
        if position:
            yield Prose(FRAGMENTS["scope_separator"])
        yield Value(getattr(scope, dimension))


def _row(row):
    """One row, as its registered columns.

    A null renders as the fixed `null` token, not as an empty gap and not as a
    phrase about absence. Section 6 keeps numeric values at their stored
    precision, which is why `str` is applied to the stored value rather than
    to a formatted one: `0.10` stays `0.10`.
    """
    first = True
    for column, value in row.items():
        if not first:
            yield Prose(FRAGMENTS["field_separator"])
        first = False
        yield Prose(column)
        yield Prose(FRAGMENTS["label_separator"])
        yield Prose(FRAGMENTS["null"]) if value is None else Value(str(value))
