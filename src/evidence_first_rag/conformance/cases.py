"""The registered fixture cases of Section 8.1, as requests.

Section 4.9: "The runner executes every registered fixture against the
runtime." A fixture is a registered *input* — Contract Shape Framework Section
5.7 requires registered inputs and normalized expected outputs — so a case
here is the request, and `expected/` holds the output it is judged against.

`structural_case` is Section 8.1's own wording for the row, copied rather than
paraphrased, so that a reader comparing this table with the contract's is
comparing the same sentence. `FX-108` to `FX-112` are absent: Section 8.1
registers them as properties of a request or of the adapter, and Issue #14
placed them with the slices that produce them.
"""

import dataclasses
import types
from collections.abc import Mapping

# The scopes the fixtures load, named once. `fixtures/README.md` is the table
# these come from; `scripts/checks/validate_fixtures.py` is what keeps that
# table true.
_POWERTRAIN_BASE = {
    "project_code": "SAMPLE_PROJECT_ALPHA",
    "revision_label": "SAMPLE_REV_A",
    "network_name": "SAMPLE_NET_POWERTRAIN",
    "snapshot_label": "SAMPLE_SNAP_BASE",
}
_POWERTRAIN_REVISED = _POWERTRAIN_BASE | {"snapshot_label": "SAMPLE_SNAP_REVISED"}
_CHASSIS_A = _POWERTRAIN_BASE | {"network_name": "SAMPLE_NET_CHASSIS"}
_CHASSIS_B = _CHASSIS_A | {"revision_label": "SAMPLE_REV_B"}


@dataclasses.dataclass(frozen=True, kw_only=True)
class Case:
    """One registered fixture: an identifier and the request it stands for."""

    identifier: str
    structural_case: str
    route: str
    arguments: Mapping[str, str]

    def __post_init__(self) -> None:
        object.__setattr__(self, "arguments", types.MappingProxyType(dict(self.arguments)))


def _without(mapping, *names):
    return {key: value for key, value in mapping.items() if key not in names}


REGISTERED = (
    Case(
        identifier="FX-001",
        structural_case="Message facts for a fully scoped reference",
        route="message_facts",
        arguments=_POWERTRAIN_BASE | {"message_key": "SAMPLE_MSG_ENGINE_STATUS"},
    ),
    Case(
        identifier="FX-002",
        structural_case="Signal facts for a fully scoped reference",
        route="signal_facts",
        arguments=_POWERTRAIN_BASE
        | {
            "message_key": "SAMPLE_MSG_ENGINE_STATUS",
            "signal_key": "SAMPLE_SIG_ENGINE_SPEED",
        },
    ),
    Case(
        identifier="FX-003",
        structural_case="Signal mapping returning more than one row",
        route="signal_mapping",
        arguments=_POWERTRAIN_BASE
        | {
            "message_key": "SAMPLE_MSG_ENGINE_STATUS",
            "signal_key": "SAMPLE_SIG_ENGINE_SPEED",
        },
    ),
    Case(
        identifier="FX-101",
        structural_case=(
            "Same `message_key` present in two snapshots, request fully scoped to one"
        ),
        # Scoped to SNAP_REVISED deliberately. It is the older snapshot by
        # `ingested_at` and the higher one by `snapshot_label`, so a runtime
        # that resolved by either of the two orders Section 4.2 forbids would
        # return SNAP_BASE's row and diverge on `transmit_period_ms`.
        route="message_facts",
        arguments=_POWERTRAIN_REVISED | {"message_key": "SAMPLE_MSG_ENGINE_STATUS"},
    ),
    Case(
        identifier="FX-102",
        structural_case=(
            "Same `signal_key` under two different parent messages in one snapshot"
        ),
        route="signal_facts",
        arguments=_POWERTRAIN_BASE
        | {
            "message_key": "SAMPLE_MSG_TRANSMISSION_STATE",
            "signal_key": "SAMPLE_SIG_TEMPERATURE",
        },
    ),
    Case(
        identifier="FX-103",
        structural_case="Source signal exists, no mapping row asserted",
        route="signal_mapping",
        arguments=_POWERTRAIN_BASE
        | {
            "message_key": "SAMPLE_MSG_ENGINE_STATUS",
            "signal_key": "SAMPLE_SIG_TEMPERATURE",
        },
    ),
    Case(
        identifier="FX-104",
        structural_case=(
            "Mapping asserted by a snapshot whose `superseded_by` is non-null"
        ),
        route="signal_mapping",
        arguments=_CHASSIS_A
        | {
            "message_key": "SAMPLE_MSG_WHEEL_SPEED",
            "signal_key": "SAMPLE_SIG_WHEEL_SPEED_FL",
        },
    ),
    Case(
        identifier="FX-105",
        structural_case="Scope omitted, two candidate snapshots match",
        route="message_facts",
        arguments=_without(_POWERTRAIN_BASE, "snapshot_label")
        | {"message_key": "SAMPLE_MSG_ENGINE_STATUS"},
    ),
    Case(
        identifier="FX-106",
        structural_case="Scope names a `network_name` that no snapshot has",
        route="message_facts",
        arguments=_POWERTRAIN_BASE
        | {
            "network_name": "SAMPLE_NET_BODY",
            "message_key": "SAMPLE_MSG_ENGINE_STATUS",
        },
    ),
    Case(
        identifier="FX-107",
        structural_case="Lookup key absent from a fully resolved, covered snapshot",
        route="message_facts",
        arguments=_POWERTRAIN_BASE | {"message_key": "SAMPLE_MSG_ABSENT"},
    ),
    Case(
        identifier="FX-113",
        structural_case="Scope omitted, exactly one candidate snapshot matches",
        route="message_facts",
        arguments=_without(_CHASSIS_B, "snapshot_label")
        | {"message_key": "SAMPLE_MSG_WHEEL_SPEED"},
    ),
)

BY_IDENTIFIER = types.MappingProxyType({case.identifier: case for case in REGISTERED})
