"""Parse the registry fixture files into typed rows.

entity-discovery-v0.1 Section 4.2: the registry is loaded "from
version-controlled JSON Lines files under `fixtures/`", in the same
provisioning phase as the mvp-v0.1 Section 4.11 fixtures, and a partial load
aborts. So this module is the registry's half of `fixtures.py`: pure, no
database, every parse and every reference construction done before the loader
opens a transaction, and a row that cannot be typed is a `FixtureError`
naming the file and line.

The files live in `fixtures/registry/` rather than beside the mvp-v0.1 files.
`scripts/checks/test_validate_fixtures.py` pins `fixtures/*.jsonl` to exactly
the four mvp-v0.1 tables, and Section 4.2's "under `fixtures/`" is satisfied
by a subdirectory.

A row names its entity by the Section 4.2 canonical reference of the
occurrence -- the four scope dimensions and `message_key`, plus `signal_key`
for a signal -- never by a surrogate. The reference comes out as the
mvp-v0.1 types, which refuse a partial scope at construction.

What is checked here and what is not. The two enumerations (Section 4.2 rule
3) and the presence of every provenance column are checked here, because they
are properties of a line. Rule 1 (an alias's asserting snapshot is its
entity's own) and rule 5 (a match text normalizes to at least one token) are
checked by the loader, which is where the entity's occurrence and the derived
surface exist; the parser only carries what the loader needs to check them.
"""

import dataclasses
import datetime
import json
import pathlib
import re

from ..references import MessageReference, SignalReference, SnapshotScope
from .fixtures import FixtureError

# Section 4.2: one file per authored table. `entity_match_term` and
# `entity_registry_state` are derived at load and have no file.
TABLES = ("approved_entity", "approved_alias")

SUBDIRECTORY = "registry"

# Section 4.1 / Section 4.2 rule 3.
ENTITY_KINDS = ("message", "signal")

# Section 4.2's timestamp form: RFC 3339, UTC, second precision, trailing Z.
# Required of the fixture text itself rather than normalized from it (review
# N7 on #142): the columns are `timestamp` without time zone, so a value
# carrying an offset would have that offset silently discarded by the cast
# and then re-emitted into the digest as `Z` -- an instant the file never
# stated, and one a second conforming implementation would not compute.
TIMESTAMP = re.compile(r"\A\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z")
ALIAS_KINDS = ("approved_alias", "spelling_variant")


@dataclasses.dataclass(frozen=True, kw_only=True)
class ApprovedEntityRow:
    entity_kind: str
    reference: MessageReference | SignalReference
    approval_reference: str
    approved_at: str


@dataclasses.dataclass(frozen=True, kw_only=True)
class ApprovedAliasRow:
    entity_kind: str
    reference: MessageReference | SignalReference
    alias_text: str
    alias_kind: str
    asserting_scope: SnapshotScope
    approval_reference: str
    approved_at: str


@dataclasses.dataclass(frozen=True, kw_only=True)
class RegistrySet:
    """Every row of both files, parsed, or a FixtureError instead."""

    entities: tuple[ApprovedEntityRow, ...]
    aliases: tuple[ApprovedAliasRow, ...]


def read(directory: pathlib.Path) -> RegistrySet:
    """Parse both registry files under `directory / "registry"`, or raise
    FixtureError. `directory` is the same `fixtures/` the mvp-v0.1 parser
    reads, so one `--fixtures` argument names both."""
    registry = directory / SUBDIRECTORY
    return RegistrySet(
        entities=tuple(
            _entity(where, row) for where, row in _lines(registry, "approved_entity")
        ),
        aliases=tuple(
            _alias(where, row) for where, row in _lines(registry, "approved_alias")
        ),
    )


def _lines(directory: pathlib.Path, table: str):
    path = directory / f"{table}.jsonl"
    if not path.is_file():
        raise FixtureError(f"{path}: missing")
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        where = f"{path}:{number}"
        if not raw.strip():
            raise FixtureError(f"{where}: blank line; one line is one row")
        try:
            row = json.loads(raw)
        except json.JSONDecodeError as error:
            raise FixtureError(f"{where}: not valid JSON: {error}") from error
        if not isinstance(row, dict):
            raise FixtureError(f"{where}: line is not a JSON object")
        yield where, row


def _columns(where: str, row: dict, declared: tuple[str, ...]) -> None:
    missing = sorted(set(declared) - set(row))
    extra = sorted(set(row) - set(declared))
    if missing:
        raise FixtureError(f"{where}: missing columns {missing}")
    if extra:
        raise FixtureError(f"{where}: unexpected columns {extra}")


def _text(where: str, row: dict, field: str) -> str:
    value = row[field]
    if not isinstance(value, str) or value == "":
        raise FixtureError(f"{where}: {field} must be a non-empty string")
    return value


def _timestamp(where: str, row: dict, field: str) -> str:
    value = _text(where, row, field)
    if not TIMESTAMP.match(value):
        raise FixtureError(
            f"{where}: {field} {value!r} is not an RFC 3339 UTC timestamp of the"
            f" form YYYY-MM-DDThh:mm:ssZ (Section 4.2)"
        )
    try:
        datetime.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as error:
        raise FixtureError(f"{where}: {field} {value!r}: {error}") from error
    return value


def _enumerated(where: str, row: dict, field: str, allowed: tuple[str, ...]) -> str:
    value = _text(where, row, field)
    if value not in allowed:
        raise FixtureError(
            f"{where}: {field} {value!r} is not one of {list(allowed)} (Section 4.2 rule 3)"
        )
    return value


def _scope(where: str, field: str, value: object) -> SnapshotScope:
    if not isinstance(value, dict):
        raise FixtureError(f"{where}: {field} is not an object")
    try:
        return SnapshotScope(**value)
    except (TypeError, ValueError) as error:
        raise FixtureError(f"{where}: {field}: {error}") from error


def _reference(where: str, entity_kind: str, value: object):
    """The canonical reference of the entity's occurrence, typed by kind.

    A message reference carries exactly the five mvp-v0.1 Section 4.2 keys; a
    signal reference carries six. A reference with the wrong number for its
    kind -- a `signal_key` on a message, none on a signal -- is refused here,
    so the loader never has to decide which table to look in.
    """
    if not isinstance(value, dict):
        raise FixtureError(f"{where}: reference is not an object")
    rest = dict(value)
    message_key = rest.pop("message_key", None)
    signal_key = rest.pop("signal_key", None)
    try:
        message = MessageReference(scope=_scope(where, "reference", rest), message_key=message_key)
        if entity_kind == "message":
            if signal_key is not None:
                raise ValueError("a message reference carries no signal_key")
            return message
        return SignalReference(message=message, signal_key=signal_key)
    except (TypeError, ValueError) as error:
        raise FixtureError(f"{where}: reference: {error}") from error


def _entity(where: str, row: dict) -> ApprovedEntityRow:
    _columns(where, row, ("entity_kind", "reference", "approval_reference", "approved_at"))
    kind = _enumerated(where, row, "entity_kind", ENTITY_KINDS)
    return ApprovedEntityRow(
        entity_kind=kind,
        reference=_reference(where, kind, row["reference"]),
        approval_reference=_text(where, row, "approval_reference"),
        approved_at=_timestamp(where, row, "approved_at"),
    )


def _alias(where: str, row: dict) -> ApprovedAliasRow:
    _columns(
        where,
        row,
        (
            "entity_kind",
            "reference",
            "alias_text",
            "alias_kind",
            "asserting_snapshot",
            "approval_reference",
            "approved_at",
        ),
    )
    kind = _enumerated(where, row, "entity_kind", ENTITY_KINDS)
    return ApprovedAliasRow(
        entity_kind=kind,
        reference=_reference(where, kind, row["reference"]),
        alias_text=_text(where, row, "alias_text"),
        alias_kind=_enumerated(where, row, "alias_kind", ALIAS_KINDS),
        asserting_scope=_scope(where, "asserting_snapshot", row["asserting_snapshot"]),
        approval_reference=_text(where, row, "approval_reference"),
        approved_at=_timestamp(where, row, "approved_at"),
    )
