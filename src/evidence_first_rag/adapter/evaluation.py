"""Section 8.3: the Milestone 2 evaluation set, the curated table, the thresholds.

Contract version 0.6.0 registers three things this module mirrors, and
`tests/test_adapter_evaluation.py` asserts the mirror against the document
rule by rule:

- `EVALUATION_SET` -- forty-eight cases in the four families Charter Section
  9 names for Milestone 2 (executable, missing-entity, invalid, unsupported),
  built from the eleven data-dependent Section 8.1 cases.
- `CURATED` -- the eleven canonical `P` phrasings, and nothing else. This is
  the Section 4.7 table `baseline.py` refused to author for itself.
- `THRESHOLDS` -- the two numbers, `registered_at`, and the contract version,
  copied from Section 8.3.

**Authored without running the adapter over it** (Section 8.3 rule 6). The
session that wrote these texts held no model credential.

**Every identifier is `SAMPLE_*`** and is either loaded by `fixtures/` or one
of the three names `fixtures/README.md` reserves as absent. No text ends an
identifier with `.` or `-`: both are in the Section 4.6 whole-token boundary
class, so `SAMPLE_SNAP_BASE.` would not contain `SAMPLE_SNAP_BASE` as a token
and a correct proposal would be refused for a full stop.

**The canonical phrasing names the route.** `FX-002` and `FX-003` carry
identical arguments -- same scope, message and signal -- and differ only in
whether the request is for the signal's facts or its mappings. A phrasing
built from the arguments alone collides, and `Baseline` refuses to hold two
entries that normalize to the same text.

Deliberately not imported by `adapter/__init__.py`: the public surface is
pinned by `tests/test_adapter_surface.py`, and the runner that consumes these
imports them from here by name.
"""

import types

from ..contract import CONTRACT_VERSION
from .baseline import CuratedEntry
from .comparison import EvaluationCase, Thresholds

# Section 8.3, "Thresholds". `registered_at` is the instant the owner recorded
# the decision on #52; a run that started before it is not judged.
THRESHOLDS = Thresholds(
    task_coverage=0.90,
    false_resolution=0.00,
    registered_at="2026-09-07T09:32:37Z",
    contract_version=CONTRACT_VERSION,
)

# The four loaded scopes, from fixtures/source_snapshot.jsonl.
_POWERTRAIN_BASE = {
    "project_code": "SAMPLE_PROJECT_ALPHA",
    "revision_label": "SAMPLE_REV_A",
    "network_name": "SAMPLE_NET_POWERTRAIN",
    "snapshot_label": "SAMPLE_SNAP_BASE",
}
_POWERTRAIN_REVISED = _POWERTRAIN_BASE | {"snapshot_label": "SAMPLE_SNAP_REVISED"}
_CHASSIS_A = _POWERTRAIN_BASE | {"network_name": "SAMPLE_NET_CHASSIS"}
_CHASSIS_B = _CHASSIS_A | {"revision_label": "SAMPLE_REV_B"}


def _without(mapping, *names):
    return {key: value for key, value in mapping.items() if key not in names}


# Section 8.1's expected status per structural case. `weakened` in
# `comparison.measure` is a case registering a non-success status observed as
# `success`; a P case registered as `success` across the board could never be
# weakened, so FX-105's `ambiguous` or FX-106's `coverage_gap` turning into a
# fact would go unnoticed. The test asserts these against `expected/`.
_STRUCTURAL_STATUS = {
    "FX-001": "success",
    "FX-002": "success",
    "FX-003": "success",
    "FX-101": "success",
    "FX-102": "success",
    "FX-103": "not_found",
    "FX-104": "success",
    "FX-105": "ambiguous",
    "FX-106": "coverage_gap",
    "FX-107": "not_found",
    "FX-113": "ambiguous",
}


# --- P: executable. Eleven structural cases, three phrasings each. --------
#
# The registrations are the eleven data-dependent Section 8.1 cases, written
# out rather than imported from the conformance package so that this module
# depends on nothing that judges conformance; the test asserts they equal
# `conformance.cases.REGISTERED` so they cannot drift. Phrasing 0 is canonical
# and is the curated entry; 1 and 2 are paraphrases the baseline cannot match.
_STRUCTURAL = (
    (
        "FX-001",
        "message_facts",
        _POWERTRAIN_BASE | {"message_key": "SAMPLE_MSG_ENGINE_STATUS"},
        (
            "Show the message facts for SAMPLE_MSG_ENGINE_STATUS in SAMPLE_PROJECT_ALPHA"
            " SAMPLE_REV_A SAMPLE_NET_POWERTRAIN SAMPLE_SNAP_BASE",
            "What are the message facts of SAMPLE_MSG_ENGINE_STATUS on network"
            " SAMPLE_NET_POWERTRAIN, project SAMPLE_PROJECT_ALPHA, revision SAMPLE_REV_A,"
            " snapshot SAMPLE_SNAP_BASE?",
            "In SAMPLE_PROJECT_ALPHA at SAMPLE_REV_A, on SAMPLE_NET_POWERTRAIN snapshot"
            " SAMPLE_SNAP_BASE, give me the message SAMPLE_MSG_ENGINE_STATUS and its facts",
        ),
    ),
    (
        "FX-002",
        "signal_facts",
        _POWERTRAIN_BASE
        | {"message_key": "SAMPLE_MSG_ENGINE_STATUS", "signal_key": "SAMPLE_SIG_ENGINE_SPEED"},
        (
            "Show the signal facts for SAMPLE_SIG_ENGINE_SPEED in message"
            " SAMPLE_MSG_ENGINE_STATUS in SAMPLE_PROJECT_ALPHA SAMPLE_REV_A"
            " SAMPLE_NET_POWERTRAIN SAMPLE_SNAP_BASE",
            "What are the facts about signal SAMPLE_SIG_ENGINE_SPEED inside"
            " SAMPLE_MSG_ENGINE_STATUS, network SAMPLE_NET_POWERTRAIN, project"
            " SAMPLE_PROJECT_ALPHA, revision SAMPLE_REV_A, snapshot SAMPLE_SNAP_BASE?",
            "Signal SAMPLE_SIG_ENGINE_SPEED of message SAMPLE_MSG_ENGINE_STATUS: scale,"
            " offset and unit, for SAMPLE_PROJECT_ALPHA SAMPLE_REV_A SAMPLE_NET_POWERTRAIN"
            " SAMPLE_SNAP_BASE",
        ),
    ),
    (
        "FX-003",
        "signal_mapping",
        _POWERTRAIN_BASE
        | {"message_key": "SAMPLE_MSG_ENGINE_STATUS", "signal_key": "SAMPLE_SIG_ENGINE_SPEED"},
        (
            "Show the signal mappings whose source is SAMPLE_SIG_ENGINE_SPEED in message"
            " SAMPLE_MSG_ENGINE_STATUS in SAMPLE_PROJECT_ALPHA SAMPLE_REV_A"
            " SAMPLE_NET_POWERTRAIN SAMPLE_SNAP_BASE",
            "Where does signal SAMPLE_SIG_ENGINE_SPEED from SAMPLE_MSG_ENGINE_STATUS map"
            " to, in SAMPLE_PROJECT_ALPHA revision SAMPLE_REV_A on SAMPLE_NET_POWERTRAIN"
            " snapshot SAMPLE_SNAP_BASE?",
            "List every mapping that starts at SAMPLE_SIG_ENGINE_SPEED of"
            " SAMPLE_MSG_ENGINE_STATUS for SAMPLE_PROJECT_ALPHA SAMPLE_REV_A"
            " SAMPLE_NET_POWERTRAIN SAMPLE_SNAP_BASE",
        ),
    ),
    (
        "FX-101",
        "message_facts",
        _POWERTRAIN_REVISED | {"message_key": "SAMPLE_MSG_ENGINE_STATUS"},
        (
            "Show the message facts for SAMPLE_MSG_ENGINE_STATUS in SAMPLE_PROJECT_ALPHA"
            " SAMPLE_REV_A SAMPLE_NET_POWERTRAIN SAMPLE_SNAP_REVISED",
            "What does the SAMPLE_SNAP_REVISED snapshot say about message"
            " SAMPLE_MSG_ENGINE_STATUS on SAMPLE_NET_POWERTRAIN, project SAMPLE_PROJECT_ALPHA"
            " revision SAMPLE_REV_A?",
            "Message facts, SAMPLE_MSG_ENGINE_STATUS, scope SAMPLE_PROJECT_ALPHA SAMPLE_REV_A"
            " SAMPLE_NET_POWERTRAIN, snapshot SAMPLE_SNAP_REVISED specifically",
        ),
    ),
    (
        "FX-102",
        "signal_facts",
        _POWERTRAIN_BASE
        | {"message_key": "SAMPLE_MSG_TRANSMISSION_STATE", "signal_key": "SAMPLE_SIG_TEMPERATURE"},
        (
            "Show the signal facts for SAMPLE_SIG_TEMPERATURE in message"
            " SAMPLE_MSG_TRANSMISSION_STATE in SAMPLE_PROJECT_ALPHA SAMPLE_REV_A"
            " SAMPLE_NET_POWERTRAIN SAMPLE_SNAP_BASE",
            "I need the facts on SAMPLE_SIG_TEMPERATURE as carried by"
            " SAMPLE_MSG_TRANSMISSION_STATE, project SAMPLE_PROJECT_ALPHA, revision"
            " SAMPLE_REV_A, network SAMPLE_NET_POWERTRAIN, snapshot SAMPLE_SNAP_BASE",
            "Under SAMPLE_MSG_TRANSMISSION_STATE, what is signal SAMPLE_SIG_TEMPERATURE in"
            " SAMPLE_PROJECT_ALPHA SAMPLE_REV_A SAMPLE_NET_POWERTRAIN SAMPLE_SNAP_BASE?",
        ),
    ),
    (
        "FX-103",
        "signal_mapping",
        _POWERTRAIN_BASE
        | {"message_key": "SAMPLE_MSG_ENGINE_STATUS", "signal_key": "SAMPLE_SIG_TEMPERATURE"},
        (
            "Show the signal mappings whose source is SAMPLE_SIG_TEMPERATURE in message"
            " SAMPLE_MSG_ENGINE_STATUS in SAMPLE_PROJECT_ALPHA SAMPLE_REV_A"
            " SAMPLE_NET_POWERTRAIN SAMPLE_SNAP_BASE",
            "Is SAMPLE_SIG_TEMPERATURE of SAMPLE_MSG_ENGINE_STATUS mapped anywhere in"
            " SAMPLE_PROJECT_ALPHA SAMPLE_REV_A SAMPLE_NET_POWERTRAIN SAMPLE_SNAP_BASE?",
            "Mappings from signal SAMPLE_SIG_TEMPERATURE, message SAMPLE_MSG_ENGINE_STATUS,"
            " for project SAMPLE_PROJECT_ALPHA revision SAMPLE_REV_A network"
            " SAMPLE_NET_POWERTRAIN snapshot SAMPLE_SNAP_BASE",
        ),
    ),
    (
        "FX-104",
        "signal_mapping",
        _CHASSIS_A
        | {"message_key": "SAMPLE_MSG_WHEEL_SPEED", "signal_key": "SAMPLE_SIG_WHEEL_SPEED_FL"},
        (
            "Show the signal mappings whose source is SAMPLE_SIG_WHEEL_SPEED_FL in message"
            " SAMPLE_MSG_WHEEL_SPEED in SAMPLE_PROJECT_ALPHA SAMPLE_REV_A SAMPLE_NET_CHASSIS"
            " SAMPLE_SNAP_BASE",
            "Where is SAMPLE_SIG_WHEEL_SPEED_FL from SAMPLE_MSG_WHEEL_SPEED mapped to, on"
            " SAMPLE_NET_CHASSIS in SAMPLE_PROJECT_ALPHA at SAMPLE_REV_A, snapshot"
            " SAMPLE_SNAP_BASE?",
            "List the mappings starting at signal SAMPLE_SIG_WHEEL_SPEED_FL of"
            " SAMPLE_MSG_WHEEL_SPEED for SAMPLE_PROJECT_ALPHA SAMPLE_REV_A SAMPLE_NET_CHASSIS"
            " SAMPLE_SNAP_BASE",
        ),
    ),
    (
        "FX-105",
        "message_facts",
        _without(_POWERTRAIN_BASE, "snapshot_label") | {"message_key": "SAMPLE_MSG_ENGINE_STATUS"},
        (
            "Show the message facts for SAMPLE_MSG_ENGINE_STATUS in SAMPLE_PROJECT_ALPHA"
            " SAMPLE_REV_A SAMPLE_NET_POWERTRAIN",
            "What are the message facts of SAMPLE_MSG_ENGINE_STATUS on network"
            " SAMPLE_NET_POWERTRAIN, project SAMPLE_PROJECT_ALPHA, revision SAMPLE_REV_A?",
            "Message SAMPLE_MSG_ENGINE_STATUS, project SAMPLE_PROJECT_ALPHA, revision"
            " SAMPLE_REV_A, network SAMPLE_NET_POWERTRAIN: the facts please",
        ),
    ),
    (
        "FX-106",
        "message_facts",
        _POWERTRAIN_BASE
        | {"network_name": "SAMPLE_NET_BODY", "message_key": "SAMPLE_MSG_ENGINE_STATUS"},
        (
            "Show the message facts for SAMPLE_MSG_ENGINE_STATUS in SAMPLE_PROJECT_ALPHA"
            " SAMPLE_REV_A SAMPLE_NET_BODY SAMPLE_SNAP_BASE",
            "What are the message facts of SAMPLE_MSG_ENGINE_STATUS on network"
            " SAMPLE_NET_BODY, project SAMPLE_PROJECT_ALPHA, revision SAMPLE_REV_A, snapshot"
            " SAMPLE_SNAP_BASE?",
            "On the SAMPLE_NET_BODY network of SAMPLE_PROJECT_ALPHA SAMPLE_REV_A, snapshot"
            " SAMPLE_SNAP_BASE, give me message SAMPLE_MSG_ENGINE_STATUS",
        ),
    ),
    (
        "FX-107",
        "message_facts",
        _POWERTRAIN_BASE | {"message_key": "SAMPLE_MSG_ABSENT"},
        (
            "Show the message facts for SAMPLE_MSG_ABSENT in SAMPLE_PROJECT_ALPHA SAMPLE_REV_A"
            " SAMPLE_NET_POWERTRAIN SAMPLE_SNAP_BASE",
            "What are the message facts of SAMPLE_MSG_ABSENT on network SAMPLE_NET_POWERTRAIN,"
            " project SAMPLE_PROJECT_ALPHA, revision SAMPLE_REV_A, snapshot SAMPLE_SNAP_BASE?",
            "Look up message SAMPLE_MSG_ABSENT in SAMPLE_PROJECT_ALPHA SAMPLE_REV_A"
            " SAMPLE_NET_POWERTRAIN SAMPLE_SNAP_BASE and tell me its facts",
        ),
    ),
    (
        "FX-113",
        "message_facts",
        _without(_CHASSIS_B, "snapshot_label") | {"message_key": "SAMPLE_MSG_WHEEL_SPEED"},
        (
            "Show the message facts for SAMPLE_MSG_WHEEL_SPEED in SAMPLE_PROJECT_ALPHA"
            " SAMPLE_REV_B SAMPLE_NET_CHASSIS",
            "What are the message facts of SAMPLE_MSG_WHEEL_SPEED on network"
            " SAMPLE_NET_CHASSIS, project SAMPLE_PROJECT_ALPHA, revision SAMPLE_REV_B?",
            "Message SAMPLE_MSG_WHEEL_SPEED for SAMPLE_PROJECT_ALPHA at SAMPLE_REV_B on"
            " SAMPLE_NET_CHASSIS: the facts",
        ),
    ),
)

# --- D: missing-entity. A route and a complete scope; the lookup key absent.
# Registers the route with scope-only arguments; the deterministic layer then
# refuses with needs_entity_discovery, which is the expected status.
_MISSING_ENTITY = (
    (
        "message_facts",
        _POWERTRAIN_BASE,
        "What messages are defined in SAMPLE_PROJECT_ALPHA SAMPLE_REV_A"
        " SAMPLE_NET_POWERTRAIN SAMPLE_SNAP_BASE?",
    ),
    (
        "signal_facts",
        _POWERTRAIN_REVISED,
        "Give me the signal facts for the engine speed signal in SAMPLE_PROJECT_ALPHA"
        " SAMPLE_REV_A SAMPLE_NET_POWERTRAIN SAMPLE_SNAP_REVISED",
    ),
    (
        "signal_mapping",
        _CHASSIS_B,
        "Which signal mappings are asserted in SAMPLE_PROJECT_ALPHA SAMPLE_REV_B"
        " SAMPLE_NET_CHASSIS SAMPLE_SNAP_BASE?",
    ),
    (
        "message_facts",
        _CHASSIS_A,
        "Show the message facts for the wheel speed message on SAMPLE_NET_CHASSIS in"
        " SAMPLE_PROJECT_ALPHA at SAMPLE_REV_A, snapshot SAMPLE_SNAP_BASE",
    ),
)

# --- X: invalid. Two loaded values for exactly one scope dimension; no route.
_CONTRADICTORY = (
    "Show the message facts for SAMPLE_MSG_ENGINE_STATUS in SAMPLE_PROJECT_ALPHA SAMPLE_REV_A"
    " or SAMPLE_REV_B on SAMPLE_NET_POWERTRAIN snapshot SAMPLE_SNAP_BASE",
    "Message facts for SAMPLE_MSG_ENGINE_STATUS in SAMPLE_PROJECT_ALPHA SAMPLE_REV_A"
    " SAMPLE_NET_POWERTRAIN, snapshot SAMPLE_SNAP_BASE and also SAMPLE_SNAP_REVISED",
    "Signal facts for SAMPLE_SIG_ENGINE_SPEED in SAMPLE_MSG_ENGINE_STATUS, project"
    " SAMPLE_PROJECT_ALPHA revision SAMPLE_REV_A, network SAMPLE_NET_POWERTRAIN or"
    " SAMPLE_NET_CHASSIS, snapshot SAMPLE_SNAP_BASE",
    "Where does SAMPLE_SIG_WHEEL_SPEED_FL of SAMPLE_MSG_WHEEL_SPEED map to in"
    " SAMPLE_PROJECT_ALPHA SAMPLE_NET_CHASSIS SAMPLE_SNAP_BASE, revision SAMPLE_REV_A or"
    " SAMPLE_REV_B?",
    "Facts for signal SAMPLE_SIG_TEMPERATURE in SAMPLE_MSG_TRANSMISSION_STATE,"
    " SAMPLE_PROJECT_ALPHA SAMPLE_REV_A SAMPLE_NET_POWERTRAIN, either SAMPLE_SNAP_BASE or"
    " SAMPLE_SNAP_REVISED",
)

# --- U: unsupported. An operation none of the three routes performs, naming
# valid identifiers under a complete scope; no route.
_UNSUPPORTED = (
    "Export the message facts for SAMPLE_MSG_ENGINE_STATUS in SAMPLE_PROJECT_ALPHA"
    " SAMPLE_REV_A SAMPLE_NET_POWERTRAIN SAMPLE_SNAP_BASE as a TSV file",
    "Compare SAMPLE_MSG_ENGINE_STATUS in SAMPLE_PROJECT_ALPHA SAMPLE_REV_A"
    " SAMPLE_NET_POWERTRAIN SAMPLE_SNAP_BASE against its previous definition and show"
    " the differences",
    "What changed in SAMPLE_PROJECT_ALPHA SAMPLE_REV_A SAMPLE_NET_POWERTRAIN"
    " SAMPLE_SNAP_BASE since it was last ingested?",
    "Dump every message, signal and mapping in SAMPLE_PROJECT_ALPHA SAMPLE_REV_A"
    " SAMPLE_NET_CHASSIS SAMPLE_SNAP_BASE",
    "Find signals similar to SAMPLE_SIG_ENGINE_SPEED in SAMPLE_PROJECT_ALPHA SAMPLE_REV_A"
    " SAMPLE_NET_POWERTRAIN SAMPLE_SNAP_BASE",
    "Delete message SAMPLE_MSG_DIAGNOSTIC_EVENT from SAMPLE_PROJECT_ALPHA SAMPLE_REV_A"
    " SAMPLE_NET_POWERTRAIN SAMPLE_SNAP_BASE",
)


def _build():
    cases, curated = [], []
    for identifier, route, arguments, phrasings in _STRUCTURAL:
        curated.append(CuratedEntry(text=phrasings[0], route=route, arguments=arguments))
        for index, text in enumerate(phrasings):
            cases.append(
                EvaluationCase(
                    identifier=f"EV-P-{identifier}-{index}",
                    text=text,
                    expected_status=_STRUCTURAL_STATUS[identifier],
                    expected_route=route,
                    expected_arguments=arguments,
                )
            )
    for index, (route, scope, text) in enumerate(_MISSING_ENTITY, start=1):
        cases.append(
            EvaluationCase(
                identifier=f"EV-D-{index}",
                text=text,
                expected_status="needs_entity_discovery",
                expected_route=route,
                expected_arguments=scope,
            )
        )
    for index, text in enumerate(_CONTRADICTORY, start=1):
        cases.append(
            EvaluationCase(identifier=f"EV-X-{index}", text=text, expected_status="invalid_request")
        )
    for index, text in enumerate(_UNSUPPORTED, start=1):
        cases.append(
            EvaluationCase(identifier=f"EV-U-{index}", text=text, expected_status="unsupported")
        )
    return tuple(cases), tuple(curated)


EVALUATION_SET, CURATED = _build()

STRUCTURAL_REGISTRATIONS = types.MappingProxyType(
    {identifier: (route, arguments) for identifier, route, arguments, _ in _STRUCTURAL}
)


def family(case: EvaluationCase) -> str:
    """`P`, `D`, `X` or `U`, from the identifier."""
    return case.identifier.split("-")[1]
