"""A database the runtime tests can hand rows to, and builders for those rows.

**What this fake proves and what it does not.** It runs the registered
template's real `bind` -- so Section 4.4's allowlist, its required-parameter
refusal and its null-scope refusal are exercised for real -- and it records
every `(template, bound parameters)` pair, so a test can assert what the
runtime asked the database for. It does not evaluate SQL. Rows come back
because a test supplied them, whatever the parameters were.

So the claim these tests make is about the runtime's decisions: which template
it reaches for, what it binds, which of the seven statuses it assigns, and
what evidence it assembles. The claim that the registered SQL returns those
rows for the registered fixtures is a different claim about PostgreSQL, and it
is asserted in `tests_database/test_runtime_fixtures.py` against a real
database loaded from `fixtures/`. Neither file is sufficient alone, and
neither one is where the other's failure would surface.
"""

import contextlib
import decimal

from evidence_first_rag import SCOPE_DIMENSIONS
from evidence_first_rag.registry import get
from evidence_first_rag.runtime.execution import Execution

RUNTIME_ROLE = "SAMPLE_RUNTIME_ROLE"

BASE = {
    "project_code": "SAMPLE_PROJECT_ALPHA",
    "revision_label": "SAMPLE_REV_A",
    "network_name": "SAMPLE_NET_POWERTRAIN",
    "snapshot_label": "SAMPLE_SNAP_BASE",
}
REVISED = BASE | {"snapshot_label": "SAMPLE_SNAP_REVISED"}
CHASSIS = BASE | {"network_name": "SAMPLE_NET_CHASSIS"}
CHASSIS_B = CHASSIS | {"revision_label": "SAMPLE_REV_B"}


class FakeDatabase:
    """Hands out sessions that return the rows a test registered."""

    def __init__(
        self,
        rows=None,
        *,
        role_name=RUNTIME_ROLE,
        read_only_transaction=True,
    ):
        self.rows = dict(rows or {})
        self.role_name = role_name
        self.read_only_transaction = read_only_transaction
        self.sessions = 0
        self.calls = []

    @contextlib.contextmanager
    def session(self):
        self.sessions += 1
        yield FakeSession(self)

    def bound(self, template_name):
        """The parameters bound the first time `template_name` ran."""
        for name, parameters in self.calls:
            if name == template_name:
                return parameters
        raise AssertionError(f"{template_name} never ran; calls were {self.calls}")

    def ran(self, template_name):
        return any(name == template_name for name, _ in self.calls)


class FakeSession:
    def __init__(self, database):
        self._database = database
        self.role_name = database.role_name
        self.read_only_transaction = database.read_only_transaction

    def execute(self, template, arguments):
        # The real bind, deliberately: Section 4.4's refusals are part of what
        # the runtime relies on, and a fake that skipped them would let a test
        # pass against a runtime that binds an unallowed parameter.
        bound = template.bind(arguments)
        self._database.calls.append((template.name, dict(bound)))
        rows = self._database.rows.get(template.name, ())
        return Execution(
            rows=tuple(dict(row) for row in rows), bound_parameters=bound
        )


def _complete(template_name, values):
    """Fill every column the template registers, so a row is never partial.

    A row missing a column the runtime reads would fail with a KeyError that
    says nothing about the contract. Building from `result_columns` means a
    column added to a template shows up here as a null rather than as a
    mystery.
    """
    columns = get(template_name).result_columns
    unknown = sorted(set(values) - set(columns))
    assert not unknown, f"{template_name} has no column(s) {unknown}"
    return {column: values.get(column) for column in columns}


def candidate_row(scope=None, **overrides):
    return dict((scope or BASE) | overrides)


def message_row(scope=None, *, superseded_by=None, **overrides):
    values = {
        **(scope or BASE),
        "message_key": "SAMPLE_MSG_ENGINE_STATUS",
        "transmit_mode": "SAMPLE_MODE_CYCLIC",
        "transmit_period_ms": 10,
        "payload_byte_length": 8,
        "frame_identifier": 256,
        **_superseded("", superseded_by),
        **overrides,
    }
    return _complete("TPL_MESSAGE_FACTS_V1", values)


def signal_row(scope=None, *, superseded_by=None, **overrides):
    values = {
        **(scope or BASE),
        "message_key": "SAMPLE_MSG_ENGINE_STATUS",
        "signal_key": "SAMPLE_SIG_ENGINE_SPEED",
        "unit_label": "SAMPLE_UNIT_RPM",
        "scale_factor": decimal.Decimal("0.250"),
        "scale_offset": decimal.Decimal("0.000"),
        "bit_width": 16,
        "bit_offset": 8,
        **_superseded("", superseded_by),
        **overrides,
    }
    return _complete("TPL_SIGNAL_FACTS_V1", values)


def mapping_row(
    *,
    asserting=None,
    source=None,
    target=None,
    asserting_superseded_by=None,
    source_superseded_by=None,
    target_superseded_by=None,
    **overrides,
):
    values = {
        **{f"asserting_{k}": v for k, v in (asserting or BASE).items()},
        **{f"source_{k}": v for k, v in (source or BASE).items()},
        **{f"target_{k}": v for k, v in (target or BASE).items()},
        "source_message_key": "SAMPLE_MSG_ENGINE_STATUS",
        "source_signal_key": "SAMPLE_SIG_ENGINE_SPEED",
        "target_message_key": "SAMPLE_MSG_TRANSMISSION_STATE",
        "target_signal_key": "SAMPLE_SIG_GEAR_POSITION",
        "mapping_key": "SAMPLE_MAP_SPEED_TO_GEAR",
        "transform_kind": "SAMPLE_TRANSFORM_LINEAR",
        **_superseded("asserting_", asserting_superseded_by),
        **_superseded("source_", source_superseded_by),
        **_superseded("target_", target_superseded_by),
        **overrides,
    }
    return _complete("TPL_SIGNAL_MAPPING_V1", values)


def _superseded(prefix, scope):
    return {
        f"{prefix}superseded_by_{name}": (None if scope is None else scope[name])
        for name in SCOPE_DIMENSIONS
    }
