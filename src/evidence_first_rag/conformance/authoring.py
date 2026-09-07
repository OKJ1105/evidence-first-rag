"""Builds `expected/` from `fixtures/`, so that `A1` is not circular.

Framework Section 5.7 requires registered inputs and normalized expected
outputs, and Section 4.9's `A1` compares one against the other. That
comparison is worth nothing if the expected side came out of the runtime: a
generated expectation makes `A1` the claim that the runtime equals itself,
which is true of every runtime including a broken one.

So the expected side is built here, from the registered fixture files and the
contract Sections that fix each field. `cases.py` says which fixture row each
case asks for; this module reads that row's stored values out of
`fixtures/*.jsonl` and assembles the Section 5 and Section 7 structure around
it.

**What it may and may not import, precisely.** Nothing that computes a result:
not `service`, not `render`, not `normalize`. It does read two pieces of static
contract metadata from `runtime.request` -- Section 4.5's route-to-template map
and the name of the candidate template -- and one template's allowlist from the
registry. Those are things the contract fixes, the same class of input as the
fixture files, and copying them here would create a second list to drift
rather than an independence the comparison needs.
`tests/test_conformance_expected.py` enforces exactly that line: any import
from `runtime` outside a named allowlist fails, so the docstring's claim and
the test's claim are the same claim.

**The prose is deliberately a second copy.** The two `limitations` details
below restate the sentences `runtime/service.py` composes rather than
importing them. Importing would make the expectation agree with the code by
construction; a registered expectation exists precisely to fail when the text
a user reads changes, so it has to be written down twice and kept equal by the
check rather than by a shared constant.

Re-run with `python -m evidence_first_rag.conformance.authoring`. CI asserts
the committed files are exactly what it produces.
"""

import decimal
import json
import pathlib

from ..contract import COLLATION, CONTRACT_IDENTIFIER, CONTRACT_VERSION
from .cases import REGISTERED, Case

REPOSITORY = pathlib.Path(__file__).resolve().parents[3]
FIXTURES = REPOSITORY / "fixtures"
DIRECTORY = pathlib.Path(__file__).resolve().parent / "expected"

SCOPE = ("project_code", "revision_label", "network_name", "snapshot_label")
RUNTIME_ROLE = "mvp_runtime"
FIXTURE_PROVENANCE = [
    "fixtures/source_snapshot.jsonl",
    "fixtures/message_occurrence.jsonl",
    "fixtures/signal_occurrence.jsonl",
    "fixtures/signal_mapping.jsonl",
]


def _load(name):
    return [json.loads(line) for line in (FIXTURES / f"{name}.jsonl").read_text().splitlines() if line.strip()]


def _key(scope) -> tuple:
    return tuple(scope[dimension] for dimension in SCOPE)


def _number(value):
    """A fixture's numeric literal as the text the normalized result carries.

    Section 6 keeps the stored precision, and `normalize.py` writes a
    `Decimal` as its own string, so this is the same round trip the database
    performs: the JSON literal, exactly as written, never a float.
    """
    return None if value is None else str(decimal.Decimal(str(value)))


class Fixtures:
    """The registered inputs, indexed by the natural keys Section 4.2 fixes."""

    def __init__(self):
        self.snapshots = {_key(row): row for row in _load("source_snapshot")}
        self.messages = {
            _key(row["snapshot"]) + (row["message_key"],): row
            for row in _load("message_occurrence")
        }
        self.signals = {
            _key(row["message"]) + (row["message"]["message_key"], row["signal_key"]): row
            for row in _load("signal_occurrence")
        }
        self.mappings = {row["mapping_key"]: row for row in _load("signal_mapping")}

    def scope(self, scope) -> dict:
        return {dimension: scope[dimension] for dimension in SCOPE}

    def superseded_by(self, scope, prefix="") -> dict:
        """The four dereferenced columns the templates return for `scope`.

        `superseded_by` is a reference in the fixture and a surrogate key in
        the database; Section 4.2 keeps surrogate keys out of every payload,
        so what the result carries is the superseding snapshot's own scope, or
        four nulls when the snapshot is current.
        """
        superseding = self.snapshots[_key(scope)]["superseded_by"]
        return {
            f"{prefix}superseded_by_{dimension}": (
                None if superseding is None else superseding[dimension]
            )
            for dimension in SCOPE
        }

    def message(self, scope, message_key) -> dict:
        row = self.messages[_key(scope) + (message_key,)]
        return {
            **self.scope(scope),
            "message_key": message_key,
            "transmit_mode": row["transmit_mode"],
            "transmit_period_ms": row["transmit_period_ms"],
            "payload_byte_length": row["payload_byte_length"],
            "frame_identifier": row["frame_identifier"],
            **self.superseded_by(scope),
        }

    def signal(self, scope, message_key, signal_key) -> dict:
        row = self.signals[_key(scope) + (message_key, signal_key)]
        return {
            **self.scope(scope),
            "message_key": message_key,
            "signal_key": signal_key,
            "unit_label": row["unit_label"],
            "scale_factor": _number(row["scale_factor"]),
            "scale_offset": _number(row["scale_offset"]),
            "bit_width": row["bit_width"],
            "bit_offset": row["bit_offset"],
            **self.superseded_by(scope),
        }

    def mapping(self, mapping_key) -> dict:
        row = self.mappings[mapping_key]
        asserting, source, target = (
            row["asserting_snapshot"],
            row["source_signal"],
            row["target_signal"],
        )
        return {
            **{f"asserting_{d}": asserting[d] for d in SCOPE},
            **{f"source_{d}": source[d] for d in SCOPE},
            "source_message_key": source["message_key"],
            "source_signal_key": source["signal_key"],
            **{f"target_{d}": target[d] for d in SCOPE},
            "target_message_key": target["message_key"],
            "target_signal_key": target["signal_key"],
            "mapping_key": mapping_key,
            "transform_kind": row["transform_kind"],
            **self.superseded_by(asserting, "asserting_"),
            **self.superseded_by(source, "source_"),
            **self.superseded_by(target, "target_"),
        }


def _text(scope) -> str:
    return " / ".join(scope[dimension] for dimension in SCOPE)


def superseded_detail(scope, superseding) -> str:
    # A deliberate second copy of `runtime/service.py`'s sentence; see the
    # module docstring for why it is not imported.
    return (
        f"{_text(scope)} is superseded by {_text(superseding)}. Its facts hold"
        f" for itself; they are not presented as holding in the later snapshot"
        f" (Section 4.2)."
    )


def coverage_detail(named: dict) -> str:
    # The same, for Section 5's `coverage_gap`.
    listed = ", ".join(f"{d}={named[d]}" for d in SCOPE if d in named)
    return (
        f"no snapshot in the approved data scope matches {listed}, so the"
        f" coverage this request needs could not be established (Sections 4.2"
        f" and 5)."
    )


def _document(
    case: Case,
    *,
    status,
    rows,
    template,
    version,
    resolved_scope=None,
    contributing=(),
    mapping_provenance=(),
    limitations=(),
    producing_layer=None,
    connection_opened=True,
) -> dict:
    """The Section 5 and Section 7 envelope around a case's rows.

    `connection_opened=False` is Section 5's three no-connection families, and
    every field that would describe an execution becomes the explicit empty
    value Section 7 requires -- `bound_parameters` above all, because those
    outcomes bound nothing and the arguments the adapter proposed are exactly
    what a rejected proposal consists of.
    """
    allowed = _bound(case) if connection_opened else {}
    return {
        "status": status,
        "rows": list(rows),
        "evidence_bundle": {
            "contract_identifier": CONTRACT_IDENTIFIER,
            "contract_version": CONTRACT_VERSION,
            "route": case.route,
            "template_name": template,
            "template_version": version,
            "bound_parameters": allowed,
            "row_count": len(rows),
            "resolved_scope": resolved_scope,
            "collation": COLLATION,
            "read_only_safeguards": {
                "role_name": RUNTIME_ROLE if connection_opened else "",
                "read_only_transaction": connection_opened,
                "connection_opened": connection_opened,
            },
        },
        "source_trace": {
            "contributing_scopes": list(contributing),
            "mapping_provenance": list(mapping_provenance),
            "producing_layer": producing_layer,
            "fixture_provenance": list(FIXTURE_PROVENANCE),
        },
        "limitations": list(limitations),
    }


def _bound(case: Case) -> dict:
    """What Section 7 says the bundle records: exactly the parameters bound.

    Section 4.4 binds a template's whole allowlist, an omitted optional as
    null, because the registered SQL tests it for null rather than being
    rewritten around it. So this is the template's allowlist filled from the
    case's arguments, which is the one place authoring has to know a rule
    rather than a value.
    """
    from ..registry import get
    from ..runtime.request import CANDIDATES_TEMPLATE, ROUTE_TEMPLATE
    from ..routes import Route

    name = CANDIDATES_TEMPLATE if _stops_at_candidates(case) else ROUTE_TEMPLATE[Route(case.route)]
    return {parameter: case.arguments.get(parameter) for parameter in get(name).allowed_parameters}


def _stops_at_candidates(case: Case) -> bool:
    """Whether Section 4.2 answers this case before the route's template runs."""
    return case.identifier in {"FX-105", "FX-106", "FX-113"}


# Two more deliberate second copies of prose the runtime composes, for the
# same reason as `superseded_detail` above: importing the wording would make
# the expectation agree by construction, and a registered expectation exists
# to fail when the text a user reads changes.
ENTITY_DISCOVERY_DETAIL = (
    "Entity Discovery is not implemented in v0.1; this outcome is terminal and"
    " never reaches the database (Sections 4.6 and 5)."
)


def no_reference_detail(route: str, missing: list[str]) -> str:
    return (
        f"route {route!r} is determined, but {missing} is missing, so"
        f" no canonical reference can be formed (Sections 4.2 and 5)"
    )


def _refused(case: Case, status: str, *, producing_layer=None, limitations=()) -> dict:
    """The expected document for a case Section 5 gives no connection."""
    return _document(
        case,
        status=status,
        rows=[],
        template="",
        version="",
        producing_layer=producing_layer,
        connection_opened=False,
        limitations=limitations,
    )


def build() -> dict[str, dict]:
    """Every registered expectation, by identifier."""
    f = Fixtures()
    by_identifier = {case.identifier: case for case in REGISTERED}

    powertrain_base = f.scope(f.snapshots[("SAMPLE_PROJECT_ALPHA", "SAMPLE_REV_A", "SAMPLE_NET_POWERTRAIN", "SAMPLE_SNAP_BASE")])
    powertrain_revised = f.scope(f.snapshots[("SAMPLE_PROJECT_ALPHA", "SAMPLE_REV_A", "SAMPLE_NET_POWERTRAIN", "SAMPLE_SNAP_REVISED")])
    chassis_a = f.scope(f.snapshots[("SAMPLE_PROJECT_ALPHA", "SAMPLE_REV_A", "SAMPLE_NET_CHASSIS", "SAMPLE_SNAP_BASE")])
    chassis_b = f.scope(f.snapshots[("SAMPLE_PROJECT_ALPHA", "SAMPLE_REV_B", "SAMPLE_NET_CHASSIS", "SAMPLE_SNAP_BASE")])

    def facts(identifier, scope, row, template, contributing=None):
        case = by_identifier[identifier]
        return _document(
            case,
            status="success" if row else "not_found",
            rows=[row] if row else [],
            template=template,
            version="2",
            resolved_scope=scope,
            contributing=[scope] if row else [],
        )

    documents = {}

    documents["FX-001"] = facts(
        "FX-001", powertrain_base,
        f.message(powertrain_base, "SAMPLE_MSG_ENGINE_STATUS"), "TPL_MESSAGE_FACTS_V1",
    )
    documents["FX-002"] = facts(
        "FX-002", powertrain_base,
        f.signal(powertrain_base, "SAMPLE_MSG_ENGINE_STATUS", "SAMPLE_SIG_ENGINE_SPEED"),
        "TPL_SIGNAL_FACTS_V1",
    )
    # Section 4.4 orders the mapping template by `mapping_key`, and Section 6's
    # `C` collation makes that byte order.
    fault, gear = f.mapping("SAMPLE_MAP_SPEED_TO_FAULT"), f.mapping("SAMPLE_MAP_SPEED_TO_GEAR")
    documents["FX-003"] = _document(
        by_identifier["FX-003"],
        status="success",
        rows=[fault, gear],
        template="TPL_SIGNAL_MAPPING_V1",
        version="2",
        resolved_scope=powertrain_base,
        contributing=[powertrain_base],
        mapping_provenance=[_provenance(row) for row in (fault, gear)],
    )
    documents["FX-101"] = facts(
        "FX-101", powertrain_revised,
        f.message(powertrain_revised, "SAMPLE_MSG_ENGINE_STATUS"), "TPL_MESSAGE_FACTS_V1",
    )
    documents["FX-102"] = facts(
        "FX-102", powertrain_base,
        f.signal(powertrain_base, "SAMPLE_MSG_TRANSMISSION_STATE", "SAMPLE_SIG_TEMPERATURE"),
        "TPL_SIGNAL_FACTS_V1",
    )
    documents["FX-103"] = facts("FX-103", powertrain_base, None, "TPL_SIGNAL_MAPPING_V1")
    carryover = f.mapping("SAMPLE_MAP_WHEEL_FL_CARRYOVER")
    documents["FX-104"] = _document(
        by_identifier["FX-104"],
        status="success",
        rows=[carryover],
        template="TPL_SIGNAL_MAPPING_V1",
        version="2",
        resolved_scope=chassis_a,
        # First appearance order: the asserting snapshot, then the target's.
        # The source is the asserting snapshot again and contributes no second
        # entry.
        contributing=[chassis_a, chassis_b],
        mapping_provenance=[_provenance(carryover)],
        limitations=[
            {
                "kind": "superseded_snapshot",
                "detail": superseded_detail(chassis_a, chassis_b),
            }
        ],
    )
    documents["FX-105"] = _document(
        by_identifier["FX-105"],
        status="ambiguous",
        rows=[powertrain_base, powertrain_revised],
        template="TPL_SNAPSHOT_CANDIDATES_V1",
        version="1",
        contributing=[powertrain_base, powertrain_revised],
    )
    documents["FX-106"] = _document(
        by_identifier["FX-106"],
        status="coverage_gap",
        rows=[],
        template="TPL_SNAPSHOT_CANDIDATES_V1",
        version="1",
        limitations=[
            {
                "kind": "coverage_not_established",
                "detail": coverage_detail(dict(by_identifier["FX-106"].arguments)),
            }
        ],
    )
    documents["FX-107"] = facts("FX-107", powertrain_base, None, "TPL_MESSAGE_FACTS_V1")

    # The adapter-level half. All five open no connection, so their evidence
    # is Section 7's explicit empty values throughout.
    documents["FX-108"] = _refused(
        by_identifier["FX-108"], "unsupported", producing_layer="runtime"
    )
    documents["FX-109"] = _refused(by_identifier["FX-109"], "invalid_request")
    documents["FX-110"] = _refused(by_identifier["FX-110"], "invalid_request")
    documents["FX-111"] = _refused(
        by_identifier["FX-111"],
        "needs_entity_discovery",
        limitations=[
            {
                "kind": "entity_discovery_not_implemented",
                "detail": f"{ENTITY_DISCOVERY_DETAIL} "
                + no_reference_detail("message_facts", ["message_key"]),
            }
        ],
    )
    documents["FX-112"] = _refused(by_identifier["FX-112"], "invalid_request")
    documents["FX-113"] = _document(
        by_identifier["FX-113"],
        status="ambiguous",
        rows=[chassis_b],
        template="TPL_SNAPSHOT_CANDIDATES_V1",
        version="1",
        contributing=[chassis_b],
    )
    return documents


def _provenance(row) -> dict:
    return {
        "asserting_scope": {d: row[f"asserting_{d}"] for d in SCOPE},
        "source_endpoint_scope": {d: row[f"source_{d}"] for d in SCOPE},
        "target_endpoint_scope": {d: row[f"target_{d}"] for d in SCOPE},
    }


def write() -> list[pathlib.Path]:
    DIRECTORY.mkdir(exist_ok=True)
    written = []
    for identifier, document in build().items():
        path = DIRECTORY / f"{identifier}.json"
        path.write_text(json.dumps(document, indent=2) + "\n")
        written.append(path)
    return written


if __name__ == "__main__":
    for path in write():
        print(path.relative_to(REPOSITORY))
