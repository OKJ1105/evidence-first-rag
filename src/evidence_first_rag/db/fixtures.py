"""Parse the registered JSON Lines fixtures into typed rows.

Pure: no database, no driver, no connection. Section 4.11 says a fixture file
that fails to parse aborts provisioning, so every parse and every reference
construction happens here, before the loader opens a transaction. A file that
would fail cannot get as far as a partially written database.

The reference tuples come out as the Section 4.2 types from this package, not
as dicts. Those types refuse a partial scope at construction, which makes a
fixture with a hole in its scope a parse failure rather than a row the loader
would have to check for later.

Sections cited are from docs/contracts/mvp-v0.1.md at version 0.3.0.
"""

import dataclasses
import decimal
import json
import pathlib

from ..references import MessageReference, SignalReference, SnapshotScope

# Section 4.11: one file per Section 4.1 table, named for the table it loads.
TABLES = (
    "source_snapshot",
    "message_occurrence",
    "signal_occurrence",
    "signal_mapping",
)


class FixtureError(Exception):
    """A fixture file could not be parsed, or a row could not be typed.

    Section 4.11 makes this fatal to provisioning. It carries the file and
    line so that the failure names the row, not just the file.
    """


@dataclasses.dataclass(frozen=True, kw_only=True)
class SnapshotRow:
    scope: SnapshotScope
    superseded_by: SnapshotScope | None
    ingested_at: str


@dataclasses.dataclass(frozen=True, kw_only=True)
class MessageRow:
    reference: MessageReference
    transmit_mode: str | None
    transmit_period_ms: int | None
    payload_byte_length: int | None
    frame_identifier: int | None


@dataclasses.dataclass(frozen=True, kw_only=True)
class SignalRow:
    reference: SignalReference
    unit_label: str | None
    scale_factor: decimal.Decimal | None
    scale_offset: decimal.Decimal | None
    bit_width: int | None
    bit_offset: int | None


@dataclasses.dataclass(frozen=True, kw_only=True)
class MappingRow:
    asserting_scope: SnapshotScope
    source_signal: SignalReference
    target_signal: SignalReference
    mapping_key: str
    transform_kind: str | None


@dataclasses.dataclass(frozen=True, kw_only=True)
class FixtureSet:
    """Every row of every file, parsed. Either all four files parsed or the
    caller got a FixtureError instead of one of these."""

    snapshots: tuple[SnapshotRow, ...]
    messages: tuple[MessageRow, ...]
    signals: tuple[SignalRow, ...]
    mappings: tuple[MappingRow, ...]


def read(directory: pathlib.Path) -> FixtureSet:
    """Parse all four fixture files, or raise FixtureError."""
    return FixtureSet(
        snapshots=tuple(
            _snapshot(where, row) for where, row in _lines(directory, "source_snapshot")
        ),
        messages=tuple(
            _message(where, row)
            for where, row in _lines(directory, "message_occurrence")
        ),
        signals=tuple(
            _signal(where, row) for where, row in _lines(directory, "signal_occurrence")
        ),
        mappings=tuple(
            _mapping(where, row) for where, row in _lines(directory, "signal_mapping")
        ),
    )


def _lines(directory: pathlib.Path, table: str):
    """Yield (location, row) for each line of one fixture file.

    Numbers are parsed as Decimal rather than float. `scale_factor` and
    `scale_offset` are `numeric` in Section 4.1, and Section 6 requires values
    to be returned with the precision stored in the schema; routing 0.1
    through a binary float first would store the nearest double instead of the
    number the fixture wrote.
    """
    path = directory / f"{table}.jsonl"
    if not path.is_file():
        raise FixtureError(f"{path}: missing")
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        where = f"{path}:{number}"
        if not raw.strip():
            raise FixtureError(f"{where}: blank line; one line is one row")
        try:
            row = json.loads(raw, parse_float=decimal.Decimal)
        except json.JSONDecodeError as error:
            raise FixtureError(f"{where}: not valid JSON: {error}") from error
        if not isinstance(row, dict):
            raise FixtureError(f"{where}: line is not a JSON object")
        yield where, row


def _scope(where: str, field: str, value: object) -> SnapshotScope:
    if not isinstance(value, dict):
        raise FixtureError(f"{where}: {field} is not an object")
    try:
        return SnapshotScope(**value)
    except (TypeError, ValueError) as error:
        raise FixtureError(f"{where}: {field}: {error}") from error


def _message_reference(where: str, field: str, value: object) -> MessageReference:
    if not isinstance(value, dict):
        raise FixtureError(f"{where}: {field} is not an object")
    rest = dict(value)
    message_key = rest.pop("message_key", None)
    try:
        return MessageReference(
            scope=_scope(where, field, rest), message_key=message_key
        )
    except (TypeError, ValueError) as error:
        raise FixtureError(f"{where}: {field}: {error}") from error


def _signal_reference(where: str, field: str, value: object) -> SignalReference:
    if not isinstance(value, dict):
        raise FixtureError(f"{where}: {field} is not an object")
    rest = dict(value)
    signal_key = rest.pop("signal_key", None)
    try:
        return SignalReference(
            message=_message_reference(where, field, rest), signal_key=signal_key
        )
    except (TypeError, ValueError) as error:
        raise FixtureError(f"{where}: {field}: {error}") from error


def _columns(where: str, row: dict, declared: tuple[str, ...]) -> None:
    """Section 4.1 fixes the column set; a fixture carrying more or fewer is a
    different table than the one the schema creates."""
    missing = sorted(set(declared) - set(row))
    extra = sorted(set(row) - set(declared))
    if missing:
        raise FixtureError(f"{where}: missing columns {missing}")
    if extra:
        raise FixtureError(f"{where}: unexpected columns {extra}")


def _optional(where: str, row: dict, field: str, expected: type):
    value = row[field]
    if value is None:
        return None
    # bool is an int in Python; an integer column that accepted True would
    # store 1 and lose the fixture's intent.
    if expected is int and isinstance(value, bool):
        raise FixtureError(f"{where}: {field} must be an integer, not a bool")
    if expected is decimal.Decimal and isinstance(value, int) and not isinstance(value, bool):
        return decimal.Decimal(value)
    if not isinstance(value, expected):
        raise FixtureError(
            f"{where}: {field} must be {expected.__name__} or null,"
            f" not {type(value).__name__}"
        )
    return value


def _snapshot(where: str, row: dict) -> SnapshotRow:
    _columns(
        where,
        row,
        (
            "project_code",
            "revision_label",
            "network_name",
            "snapshot_label",
            "superseded_by",
            "ingested_at",
        ),
    )
    superseded = row["superseded_by"]
    return SnapshotRow(
        scope=_scope(
            where,
            "scope",
            {
                key: row[key]
                for key in (
                    "project_code",
                    "revision_label",
                    "network_name",
                    "snapshot_label",
                )
            },
        ),
        superseded_by=(
            None if superseded is None else _scope(where, "superseded_by", superseded)
        ),
        ingested_at=_required_text(where, row, "ingested_at"),
    )


def _required_text(where: str, row: dict, field: str) -> str:
    value = row[field]
    if not isinstance(value, str) or value == "":
        raise FixtureError(f"{where}: {field} must be a non-empty string")
    return value


def _message(where: str, row: dict) -> MessageRow:
    _columns(
        where,
        row,
        (
            "snapshot",
            "message_key",
            "transmit_mode",
            "transmit_period_ms",
            "payload_byte_length",
            "frame_identifier",
        ),
    )
    scope = _scope(where, "snapshot", row["snapshot"])
    return MessageRow(
        reference=MessageReference(
            scope=scope, message_key=_required_text(where, row, "message_key")
        ),
        transmit_mode=_optional(where, row, "transmit_mode", str),
        transmit_period_ms=_optional(where, row, "transmit_period_ms", int),
        payload_byte_length=_optional(where, row, "payload_byte_length", int),
        frame_identifier=_optional(where, row, "frame_identifier", int),
    )


def _signal(where: str, row: dict) -> SignalRow:
    _columns(
        where,
        row,
        (
            "message",
            "signal_key",
            "unit_label",
            "scale_factor",
            "scale_offset",
            "bit_width",
            "bit_offset",
        ),
    )
    return SignalRow(
        reference=SignalReference(
            message=_message_reference(where, "message", row["message"]),
            signal_key=_required_text(where, row, "signal_key"),
        ),
        unit_label=_optional(where, row, "unit_label", str),
        scale_factor=_optional(where, row, "scale_factor", decimal.Decimal),
        scale_offset=_optional(where, row, "scale_offset", decimal.Decimal),
        bit_width=_optional(where, row, "bit_width", int),
        bit_offset=_optional(where, row, "bit_offset", int),
    )


def _mapping(where: str, row: dict) -> MappingRow:
    _columns(
        where,
        row,
        (
            "asserting_snapshot",
            "source_signal",
            "target_signal",
            "mapping_key",
            "transform_kind",
        ),
    )
    return MappingRow(
        asserting_scope=_scope(where, "asserting_snapshot", row["asserting_snapshot"]),
        source_signal=_signal_reference(where, "source_signal", row["source_signal"]),
        target_signal=_signal_reference(where, "target_signal", row["target_signal"]),
        mapping_key=_required_text(where, row, "mapping_key"),
        transform_kind=_optional(where, row, "transform_kind", str),
    )
