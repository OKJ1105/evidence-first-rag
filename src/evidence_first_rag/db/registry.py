"""Load the approved entity registry and write its digest.

entity-discovery-v0.1 Sections 4.1 and 4.2. Runs inside the same transaction
as `loader.load`, as the provisioning identity, after the mvp-v0.1 tables are
loaded: every `approved_entity` row is a foreign key into one of them, so the
occurrence has to exist first, and Section 4.2 says the registry is loaded
"in the same provisioning phase ... before the runtime identity ever
connects". A failure anywhere raises inside that transaction, and the
caller's rollback is what leaves no partial load -- of the registry or of the
mvp-v0.1 rows it references.

Three things happen here that no fixture file authors:

1. `entity_match_term` is derived (Section 4.2 rule 2): one `lookup_key` row
   per approved entity carrying that occurrence's key, and one row per alias
   carrying its text, each with `match_tokens` from the Section 4.5
   normalization. Rule 5 refuses a text that normalizes to nothing.
2. Rule 1 is enforced: an alias's asserting snapshot must be its entity's
   own. The parser cannot check this -- it has the alias's scope and the
   entity's reference, but only here are both resolved against loaded rows.
3. The digest (Section 4.2) is computed **from the loaded rows, read back
   after the load**, not from the fixture objects, and written to
   `entity_registry_state`. The contract says why: "so the digest covers what
   the runtime will read."
"""

import datetime

from ..discovery import canonical_json, normalize, sha256_hex
from ..references import MessageReference, SignalReference, SnapshotScope
from .fixtures import FixtureError
from .loader import SCHEMA, UnresolvedReference
from .registry_fixtures import RegistrySet

# Section 4.2, the seven entity keys every digest line carries -- the
# `approved_entity` line's nine keys less its own `approval_reference` and
# `approved_at`. `entity_kind` is one of the seven: an alias line and a match
# term line carry it too, as the Section 4.8 candidate object does.
# `signal_key` is null for a message.
_ENTITY_KEYS = (
    "entity_kind",
    "project_code",
    "revision_label",
    "network_name",
    "snapshot_label",
    "message_key",
    "signal_key",
)


class IntegrityError(Exception):
    """A Section 4.2 integrity rule failed at load.

    Fatal to provisioning like an unresolved reference: raised inside the
    transaction so that the rollback leaves nothing loaded.
    """


def load(
    cursor,
    registry: RegistrySet,
    snapshots: dict[SnapshotScope, int],
    messages: dict[MessageReference, int],
    signals: dict[SignalReference, int],
) -> dict[str, int]:
    """Load the registry, derive the match surface, write the digest.

    `snapshots`, `messages` and `signals` are the natural-key-to-surrogate
    maps `loader.load` built while loading the mvp-v0.1 tables. Returns row
    counts per table, `entity_registry_state` included.
    """
    entities = _load_entities(cursor, registry, messages, signals)
    aliases = _load_aliases(cursor, registry, entities, snapshots)
    terms = _derive_match_terms(cursor, registry, entities, aliases)
    digest = compute_digest(cursor)
    cursor.execute(
        f"INSERT INTO {SCHEMA}.entity_registry_state (registry_digest, built_at)"
        f" VALUES (%s, %s)",
        (digest, datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)),
    )
    return {
        "approved_entity": len(entities),
        "approved_alias": len(aliases),
        "entity_match_term": terms,
        "entity_registry_state": 1,
    }


def _occurrence(row, messages, signals):
    """The surrogate of the occurrence a registry row names, by kind."""
    if row.entity_kind == "message":
        identifier = messages.get(row.reference)
    else:
        identifier = signals.get(row.reference)
    if identifier is None:
        raise UnresolvedReference(
            f"{row.entity_kind} {row.reference} is named by the registry,"
            f" and no fixture loads that occurrence"
        )
    return identifier


def _load_entities(cursor, registry, messages, signals):
    identifiers: dict[tuple, int] = {}
    for row in registry.entities:
        occurrence = _occurrence(row, messages, signals)
        cursor.execute(
            f"""
            INSERT INTO {SCHEMA}.approved_entity
                (entity_kind, message_occurrence_id, signal_occurrence_id,
                 approval_reference, approved_at)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING approved_entity_id
            """,
            (
                row.entity_kind,
                occurrence if row.entity_kind == "message" else None,
                occurrence if row.entity_kind == "signal" else None,
                row.approval_reference,
                row.approved_at,
            ),
        )
        identifiers[(row.entity_kind, row.reference)] = cursor.fetchone()[0]
    return identifiers


def _load_aliases(cursor, registry, entities, snapshots):
    identifiers: list[tuple[int, int, str]] = []
    for row in registry.aliases:
        entity = entities.get((row.entity_kind, row.reference))
        if entity is None:
            raise UnresolvedReference(
                f"alias {row.alias_text!r} names {row.entity_kind} {row.reference},"
                f" which the registry does not approve"
            )
        # Section 4.2 rule 1. An alias asserted by another snapshot would be
        # a cross-snapshot claim, which Charter Section 3.6 makes a relation
        # (a signal_mapping row), never a naming fact.
        if row.asserting_scope != row.reference.scope:
            raise IntegrityError(
                f"alias {row.alias_text!r} is asserted by {row.asserting_scope},"
                f" not by its entity's own snapshot {row.reference.scope}"
                f" (Section 4.2 rule 1)"
            )
        asserting = snapshots.get(row.asserting_scope)
        if asserting is None:
            raise UnresolvedReference(
                f"alias {row.alias_text!r} is asserted by snapshot"
                f" {row.asserting_scope}, which no fixture creates"
            )
        cursor.execute(
            f"""
            INSERT INTO {SCHEMA}.approved_alias
                (approved_entity_id, alias_text, alias_kind, asserting_snapshot_id,
                 approval_reference, approved_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING approved_alias_id
            """,
            (
                entity,
                row.alias_text,
                row.alias_kind,
                asserting,
                row.approval_reference,
                row.approved_at,
            ),
        )
        identifiers.append((cursor.fetchone()[0], entity, row.alias_text))
    return identifiers


def _tokens(text: str, what: str) -> list[str]:
    """Section 4.2 rule 5: a match text with no token is refused at load."""
    tokens = normalize(text)
    if not tokens:
        raise IntegrityError(
            f"{what} {text!r} normalizes to no token under Section 4.5"
            f" (Section 4.2 rule 5)"
        )
    return tokens


def _derive_match_terms(cursor, registry, entities, aliases) -> int:
    """Section 4.2 rule 2: one `lookup_key` row per entity, one row per alias."""
    count = 0
    for row in registry.entities:
        key = (
            row.reference.message_key
            if row.entity_kind == "message"
            else row.reference.signal_key
        )
        cursor.execute(
            f"""
            INSERT INTO {SCHEMA}.entity_match_term
                (approved_entity_id, match_kind, match_text, match_tokens, approved_alias_id)
            VALUES (%s, 'lookup_key', %s, %s, NULL)
            """,
            (entities[(row.entity_kind, row.reference)], key, _tokens(key, "lookup key")),
        )
        count += 1
    for (alias_id, entity_id, alias_text), row in zip(aliases, registry.aliases):
        cursor.execute(
            f"""
            INSERT INTO {SCHEMA}.entity_match_term
                (approved_entity_id, match_kind, match_text, match_tokens, approved_alias_id)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (entity_id, row.alias_kind, alias_text, _tokens(alias_text, "alias"), alias_id),
        )
        count += 1
    return count


# --- The digest ------------------------------------------------------------
#
# Section 4.2 fixes the keys per table and the order: every approved_entity
# line, then every approved_alias line, then every entity_match_term line;
# within a group, sorted byte-wise by the serialized line; each line
# terminated by "\n"; SHA-256 of the concatenation. Natural keys only.
#
# The three queries below project every surrogate back to the natural key it
# stands for. They are the only place the digest's inputs are defined, and
# `registry_invariants.py` recomputes through the same function so that the
# stored value and the recomputation cannot drift apart; the *independent*
# computation Section 8 asks for lives in tests_database/test_registry.py,
# written from the contract's table rather than from this code.

_ENTITY_LINES = f"""
    SELECT e.entity_kind,
           s.project_code, s.revision_label, s.network_name, s.snapshot_label,
           COALESCE(m.message_key, pm.message_key) AS message_key,
           g.signal_key,
           e.approval_reference, e.approved_at
    FROM {SCHEMA}.approved_entity e
    LEFT JOIN {SCHEMA}.message_occurrence m  ON m.message_occurrence_id = e.message_occurrence_id
    LEFT JOIN {SCHEMA}.signal_occurrence  g  ON g.signal_occurrence_id  = e.signal_occurrence_id
    LEFT JOIN {SCHEMA}.message_occurrence pm ON pm.message_occurrence_id = g.message_occurrence_id
    JOIN {SCHEMA}.source_snapshot s ON s.snapshot_id = COALESCE(m.snapshot_id, pm.snapshot_id)
"""

_ALIAS_LINES = f"""
    SELECT e.entity_kind,
           s.project_code, s.revision_label, s.network_name, s.snapshot_label,
           COALESCE(m.message_key, pm.message_key) AS message_key,
           g.signal_key,
           a.alias_text, a.alias_kind,
           t.project_code, t.revision_label, t.network_name, t.snapshot_label,
           a.approval_reference, a.approved_at
    FROM {SCHEMA}.approved_alias a
    JOIN {SCHEMA}.approved_entity e ON e.approved_entity_id = a.approved_entity_id
    LEFT JOIN {SCHEMA}.message_occurrence m  ON m.message_occurrence_id = e.message_occurrence_id
    LEFT JOIN {SCHEMA}.signal_occurrence  g  ON g.signal_occurrence_id  = e.signal_occurrence_id
    LEFT JOIN {SCHEMA}.message_occurrence pm ON pm.message_occurrence_id = g.message_occurrence_id
    JOIN {SCHEMA}.source_snapshot s ON s.snapshot_id = COALESCE(m.snapshot_id, pm.snapshot_id)
    JOIN {SCHEMA}.source_snapshot t ON t.snapshot_id = a.asserting_snapshot_id
"""

_TERM_LINES = f"""
    SELECT e.entity_kind,
           s.project_code, s.revision_label, s.network_name, s.snapshot_label,
           COALESCE(m.message_key, pm.message_key) AS message_key,
           g.signal_key,
           x.match_kind, x.match_text, x.match_tokens,
           a.alias_text
    FROM {SCHEMA}.entity_match_term x
    JOIN {SCHEMA}.approved_entity e ON e.approved_entity_id = x.approved_entity_id
    LEFT JOIN {SCHEMA}.approved_alias a ON a.approved_alias_id = x.approved_alias_id
    LEFT JOIN {SCHEMA}.message_occurrence m  ON m.message_occurrence_id = e.message_occurrence_id
    LEFT JOIN {SCHEMA}.signal_occurrence  g  ON g.signal_occurrence_id  = e.signal_occurrence_id
    LEFT JOIN {SCHEMA}.message_occurrence pm ON pm.message_occurrence_id = g.message_occurrence_id
    JOIN {SCHEMA}.source_snapshot s ON s.snapshot_id = COALESCE(m.snapshot_id, pm.snapshot_id)
"""


def timestamp(value: datetime.datetime) -> str:
    """Section 4.2: RFC 3339, UTC, second precision, trailing `Z`.

    The columns are `timestamp` without time zone, loaded from fixture text
    that ends in `Z`, so the stored value is already UTC; a value that carried
    a zone would be converted first rather than have its zone dropped.
    """
    if value.tzinfo is not None:
        value = value.astimezone(datetime.timezone.utc).replace(tzinfo=None)
    return value.replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def digest_lines(cursor) -> list[bytes]:
    """Every digest line, in Section 4.2's order, from the loaded rows."""
    lines: list[bytes] = []
    for query, shape in ((_ENTITY_LINES, _entity_line), (_ALIAS_LINES, _alias_line), (_TERM_LINES, _term_line)):
        cursor.execute(query)
        group = sorted(canonical_json(shape(row)) + b"\n" for row in cursor.fetchall())
        lines.extend(group)
    return lines


def compute_digest(cursor) -> str:
    """Section 4.2's `registry_digest` over the rows the runtime will read."""
    return sha256_hex(b"".join(digest_lines(cursor)))


def _entity_keys(row) -> dict:
    """The seven Section 4.2 entity keys, from a row whose leading columns are
    `entity_kind` and the six reference keys in `_ENTITY_KEYS` order."""
    return dict(zip(_ENTITY_KEYS, row[:7]))


def _entity_line(row) -> dict:
    keys = _entity_keys(row)
    approval_reference, approved_at = row[7], row[8]
    return {
        **keys,
        "approval_reference": approval_reference,
        "approved_at": timestamp(approved_at),
    }


def _alias_line(row) -> dict:
    keys = _entity_keys(row)
    (alias_text, alias_kind, a_project, a_revision, a_network, a_snapshot,
     approval_reference, approved_at) = row[7:]
    return {
        **keys,
        "alias_text": alias_text,
        "alias_kind": alias_kind,
        "asserting_project_code": a_project,
        "asserting_revision_label": a_revision,
        "asserting_network_name": a_network,
        "asserting_snapshot_label": a_snapshot,
        "approval_reference": approval_reference,
        "approved_at": timestamp(approved_at),
    }


def _term_line(row) -> dict:
    keys = _entity_keys(row)
    match_kind, match_text, match_tokens, alias_text = row[7:]
    return {
        **keys,
        "match_kind": match_kind,
        "match_text": match_text,
        "match_tokens": list(match_tokens),
        "alias_text": alias_text,
    }
