"""Load the parsed fixtures, resolving natural keys to surrogate keys.

Section 4.11 fixes two things this module implements. Fixture rows reference
each other by natural keys only, so every reference is resolved here rather
than carried in the files; and there is no partial load, so the whole load is
one transaction that either commits every row of every file or leaves the
database as it found it.

The loader runs as the provisioning identity, inside the provisioning step,
before the runtime identity ever connects (Section 3.4).
"""

from .fixtures import FixtureSet
from .registry_fixtures import RegistrySet
from ..references import MessageReference, SignalReference, SnapshotScope

SCHEMA = "mvp"


class UnresolvedReference(Exception):
    """A fixture named a row that no fixture creates.

    Section 4.11 makes this fatal: "a reference that does not resolve, aborts
    provisioning." Raised inside the transaction, so the caller's rollback is
    what leaves no partial load.
    """


def load(
    connection, fixtures: FixtureSet, registry: RegistrySet | None = None
) -> dict[str, int]:
    """Load every row of `fixtures`, then of `registry`. Returns the row
    count per table.

    The caller owns the transaction. `provision.py` wraps this in one and
    rolls back on any exception, which is what Section 4.11's all-or-nothing
    rule requires; a caller that committed per table would defeat it.

    The registry (entity-discovery-v0.1 Section 4.2) loads inside the same
    transaction, after the four tables it references, and a failure in it
    rolls back those four as well: "a refresh is a re-provision", and there
    is no state in which the mvp-v0.1 rows are loaded and the registry that
    names them is not. `registry` is optional so that a caller with only the
    mvp-v0.1 files still has a loader; provisioning always passes it.
    """
    with connection.cursor() as cursor:
        snapshots = _load_snapshots(cursor, fixtures)
        messages = _load_messages(cursor, fixtures, snapshots)
        signals = _load_signals(cursor, fixtures, messages)
        mappings = _load_mappings(cursor, fixtures, snapshots, signals)
        counts = {
            "source_snapshot": len(snapshots),
            "message_occurrence": len(messages),
            "signal_occurrence": len(signals),
            "signal_mapping": len(mappings),
        }
        if registry is not None:
            # Imported here rather than at the top: registry.py imports this
            # module for SCHEMA and UnresolvedReference.
            from . import registry as registry_loader

            counts.update(registry_loader.load(cursor, registry, snapshots, messages, signals))

    return counts


def _load_snapshots(cursor, fixtures: FixtureSet) -> dict[SnapshotScope, int]:
    """Insert snapshots, then resolve `superseded_by` in a second pass.

    Two passes because a snapshot may be superseded by one that appears later
    in the file, and Section 4.11 does not order the file. Inserting the
    reference as null first and updating it afterwards means file order
    carries no meaning, which is what keeps the load reproducible.
    """
    identifiers: dict[SnapshotScope, int] = {}
    for row in fixtures.snapshots:
        cursor.execute(
            f"""
            INSERT INTO {SCHEMA}.source_snapshot
                (project_code, revision_label, network_name, snapshot_label,
                 superseded_by, ingested_at)
            VALUES (%(project_code)s, %(revision_label)s, %(network_name)s,
                    %(snapshot_label)s, NULL, %(ingested_at)s)
            RETURNING snapshot_id
            """,
            {**row.scope.as_parameters(), "ingested_at": row.ingested_at},
        )
        identifiers[row.scope] = cursor.fetchone()[0]

    for row in fixtures.snapshots:
        if row.superseded_by is None:
            continue
        successor = identifiers.get(row.superseded_by)
        if successor is None:
            raise UnresolvedReference(
                f"source_snapshot {row.scope} is superseded by"
                f" {row.superseded_by}, which no fixture creates"
            )
        cursor.execute(
            f"UPDATE {SCHEMA}.source_snapshot SET superseded_by = %s WHERE snapshot_id = %s",
            (successor, identifiers[row.scope]),
        )

    return identifiers


def _load_messages(
    cursor, fixtures: FixtureSet, snapshots: dict[SnapshotScope, int]
) -> dict[MessageReference, int]:
    identifiers: dict[MessageReference, int] = {}
    for row in fixtures.messages:
        snapshot_id = snapshots.get(row.reference.scope)
        if snapshot_id is None:
            raise UnresolvedReference(
                f"message_occurrence {row.reference.message_key} names snapshot"
                f" {row.reference.scope}, which no fixture creates"
            )
        cursor.execute(
            f"""
            INSERT INTO {SCHEMA}.message_occurrence
                (snapshot_id, message_key, transmit_mode, transmit_period_ms,
                 payload_byte_length, frame_identifier)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING message_occurrence_id
            """,
            (
                snapshot_id,
                row.reference.message_key,
                row.transmit_mode,
                row.transmit_period_ms,
                row.payload_byte_length,
                row.frame_identifier,
            ),
        )
        identifiers[row.reference] = cursor.fetchone()[0]
    return identifiers


def _load_signals(
    cursor, fixtures: FixtureSet, messages: dict[MessageReference, int]
) -> dict[SignalReference, int]:
    identifiers: dict[SignalReference, int] = {}
    for row in fixtures.signals:
        parent = messages.get(row.reference.message)
        if parent is None:
            raise UnresolvedReference(
                f"signal_occurrence {row.reference.signal_key} names parent message"
                f" {row.reference.message}, which no fixture creates"
            )
        cursor.execute(
            f"""
            INSERT INTO {SCHEMA}.signal_occurrence
                (message_occurrence_id, signal_key, unit_label, scale_factor,
                 scale_offset, bit_width, bit_offset)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING signal_occurrence_id
            """,
            (
                parent,
                row.reference.signal_key,
                row.unit_label,
                row.scale_factor,
                row.scale_offset,
                row.bit_width,
                row.bit_offset,
            ),
        )
        identifiers[row.reference] = cursor.fetchone()[0]
    return identifiers


def _load_mappings(
    cursor,
    fixtures: FixtureSet,
    snapshots: dict[SnapshotScope, int],
    signals: dict[SignalReference, int],
) -> list[int]:
    identifiers: list[int] = []
    for row in fixtures.mappings:
        asserting = snapshots.get(row.asserting_scope)
        if asserting is None:
            raise UnresolvedReference(
                f"signal_mapping {row.mapping_key} is asserted by snapshot"
                f" {row.asserting_scope}, which no fixture creates"
            )
        endpoints = []
        for end, reference in (("source", row.source_signal), ("target", row.target_signal)):
            signal_id = signals.get(reference)
            if signal_id is None:
                raise UnresolvedReference(
                    f"signal_mapping {row.mapping_key} names {end} signal"
                    f" {reference}, which no fixture creates"
                )
            endpoints.append(signal_id)

        cursor.execute(
            f"""
            INSERT INTO {SCHEMA}.signal_mapping
                (asserting_snapshot_id, source_signal_occurrence_id,
                 target_signal_occurrence_id, mapping_key, transform_kind)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING signal_mapping_id
            """,
            (asserting, endpoints[0], endpoints[1], row.mapping_key, row.transform_kind),
        )
        identifiers.append(cursor.fetchone()[0])
    return identifiers
