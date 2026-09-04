"""One JSON shape for a `Result`, and the comparison Section 4.9 `A1` runs.

`A1` is "The normalized result for the fixture equals its registered expected
result in full, field by field", and "On failure the runner reports the first
diverging path and uses it only to assign a failure class." Two obligations,
both structural: the result has to become something comparable to a committed
file, and a divergence has to name a path rather than a diff.

Numbers become text. A `numeric` column arrives as a `Decimal`, JSON has one
number type, and Section 6 forbids rounding anywhere in the runtime or the
renderer -- so `Decimal("0.10")` is written `"0.10"` and survives the round
trip. An integer stays an integer; nothing in the schema makes an integer
column large enough for that to lose anything.

The rendered answer is deliberately not a field here. Section 4.8 renders "a
fixed template over the normalized result", so the result is what rendering
consumes and cannot contain its own output; check `E1` judges the answer, and
`A1` judges this.
"""

import decimal

# Section 4.9's failure classes, by where the first divergence sits. "A Group A
# divergence is classed by its first diverging path: a scope or row value is
# `data`, a route or argument is `retrieval`, a status or evidence field is
# `contract`."
_DATA_PATHS = ("rows", "resolved_scope", "contributing_scopes", "mapping_provenance")
_RETRIEVAL_PATHS = ("route", "bound_parameters")


def normalize(result) -> dict:
    """`result` as the JSON object a registered expectation is written in."""
    bundle = result.evidence_bundle
    trace = result.source_trace
    return {
        "status": result.status.value,
        "rows": [_row(row) for row in result.rows],
        "evidence_bundle": {
            "contract_identifier": bundle.contract_identifier,
            "contract_version": bundle.contract_version,
            "route": bundle.route,
            "template_name": bundle.template_name,
            "template_version": bundle.template_version,
            "bound_parameters": _row(bundle.bound_parameters),
            "row_count": bundle.row_count,
            "resolved_scope": _scope(bundle.resolved_scope),
            "collation": bundle.collation,
            "read_only_safeguards": {
                "role_name": bundle.read_only_safeguards.role_name,
                "read_only_transaction": bundle.read_only_safeguards.read_only_transaction,
                "connection_opened": bundle.read_only_safeguards.connection_opened,
            },
        },
        "source_trace": {
            "contributing_scopes": [_scope(s) for s in trace.contributing_scopes],
            "mapping_provenance": [
                {
                    "asserting_scope": _scope(p.asserting_scope),
                    "source_endpoint_scope": _scope(p.source_endpoint_scope),
                    "target_endpoint_scope": _scope(p.target_endpoint_scope),
                }
                for p in trace.mapping_provenance
            ],
            "producing_layer": (
                None if trace.producing_layer is None else trace.producing_layer.value
            ),
            "fixture_provenance": list(trace.fixture_provenance),
        },
        "limitations": [
            {"kind": limitation.kind.value, "detail": limitation.detail}
            for limitation in result.limitations
        ],
    }


def _row(row) -> dict:
    return {column: _value(value) for column, value in row.items()}


def _value(value):
    if isinstance(value, decimal.Decimal):
        return str(value)
    if isinstance(value, (str, int, bool, type(None))):
        return value
    # Nothing in the Section 4.1 schema produces one, and a registered
    # expectation that carried a type this function invented would compare
    # against something no reader could write by hand.
    raise TypeError(f"no registered column produces a {type(value).__name__}")


def _scope(scope):
    if scope is None:
        return None
    return {
        "project_code": scope.project_code,
        "revision_label": scope.revision_label,
        "network_name": scope.network_name,
        "snapshot_label": scope.snapshot_label,
    }


def first_divergence(actual, expected, path=()) -> tuple[str, ...] | None:
    """The path to the first place `actual` and `expected` differ, or None.

    Depth first, and in the order the keys are written, so "first" is a
    property of the document rather than of a dict's iteration order on the
    day it ran. A path is a tuple of keys and indices: `("rows", 0,
    "transmit_period_ms")`.
    """
    if type(actual) is not type(expected) and not (
        isinstance(actual, dict) and isinstance(expected, dict)
    ):
        return path
    if isinstance(expected, dict):
        for key in expected:
            if key not in actual:
                return path + (key,)
            found = first_divergence(actual[key], expected[key], path + (key,))
            if found is not None:
                return found
        for key in actual:
            if key not in expected:
                return path + (key,)
        return None
    if isinstance(expected, list):
        if len(actual) != len(expected):
            return path
        for index, (a, e) in enumerate(zip(actual, expected)):
            found = first_divergence(a, e, path + (index,))
            if found is not None:
                return found
        return None
    return None if actual == expected else path


def failure_class(path: tuple) -> str:
    """Section 4.9's class for a Group A divergence at `path`.

    Read from the first path element that names one of the three kinds, not
    only from the root: a divergence inside `evidence_bundle` at
    `bound_parameters` is an argument (`retrieval`), and one at
    `resolved_scope` is a scope (`data`), even though both sit under an
    evidence field.
    """
    for element in path:
        if element in _DATA_PATHS:
            return "data"
        if element in _RETRIEVAL_PATHS:
            return "retrieval"
    return "contract"
