"""entity-discovery-v0.1 Section 4.6: one candidate, and the alias provenance
Section 7 carries beside it.

A candidate "carries exactly" the fields listed here and "no attribute of the
entity ... and no score". The type has no field for an attribute to go in,
which is how Section 4.12's "it returns no fact" holds at the payload.
"""

import dataclasses

from .._validation import required_text
from ..references import MessageReference, SignalReference, SnapshotScope

ENTITY_KINDS = ("message", "signal")
MATCH_KINDS = ("lookup_key", "approved_alias", "spelling_variant")

# Section 4.5. Tiers 1 and 2 are auto-resolution eligible; 3 and 4 are not.
AUTO_RESOLVABLE_TIERS = frozenset({1, 2})


@dataclasses.dataclass(frozen=True, kw_only=True)
class AliasProvenance:
    """Section 7: for a match whose `match_kind` is not `lookup_key`, the
    alias's `approval_reference`, its `approved_at`, and the four scope
    dimensions of its asserting snapshot."""

    approval_reference: str
    approved_at: str
    asserting_scope: SnapshotScope

    def __post_init__(self) -> None:
        required_text("approval_reference", self.approval_reference)
        required_text("approved_at", self.approved_at)
        if not isinstance(self.asserting_scope, SnapshotScope):
            raise ValueError("asserting_scope must be a SnapshotScope")


@dataclasses.dataclass(frozen=True, kw_only=True)
class Candidate:
    """One approved entity, with its complete canonical reference and the
    evidence of how it matched (Section 4.6).

    `reference` is a `MessageReference` for a message and a `SignalReference`
    -- parent included -- for a signal, so a signal candidate always carries
    the complete reference Section 4.3 requires. `alias` is None exactly when
    `match_kind` is `lookup_key`.
    """

    rank: int
    entity_kind: str
    reference: MessageReference | SignalReference
    match_tier: int
    matched_text: str
    match_kind: str
    entity_approval_reference: str
    alias: AliasProvenance | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.rank, int) or isinstance(self.rank, bool) or self.rank < 1:
            raise ValueError("rank is a 1-based position")
        if self.entity_kind not in ENTITY_KINDS:
            raise ValueError(f"entity_kind must be one of {ENTITY_KINDS}")
        expected = MessageReference if self.entity_kind == "message" else SignalReference
        if not isinstance(self.reference, expected):
            raise ValueError(f"a {self.entity_kind} candidate carries a {expected.__name__}")
        if not isinstance(self.match_tier, int) or isinstance(self.match_tier, bool) or not 1 <= self.match_tier <= 4:
            raise ValueError("match_tier is 1, 2, 3 or 4 (Section 4.5)")
        required_text("matched_text", self.matched_text)
        if self.match_kind not in MATCH_KINDS:
            raise ValueError(f"match_kind must be one of {MATCH_KINDS}")
        required_text("entity_approval_reference", self.entity_approval_reference)
        # Section 4.1: `approved_alias_id` is non-null exactly when the kind
        # is not `lookup_key`; the candidate carries the same rule.
        if (self.match_kind == "lookup_key") != (self.alias is None):
            raise ValueError("alias provenance is present exactly when match_kind is not lookup_key")
        if self.alias is not None and not isinstance(self.alias, AliasProvenance):
            raise ValueError("alias must be an AliasProvenance")

    @property
    def scope(self) -> SnapshotScope:
        return self.reference.scope

    @property
    def message_key(self) -> str:
        return self.reference.message_key

    @property
    def signal_key(self) -> str | None:
        return self.reference.signal_key if self.entity_kind == "signal" else None

    def digest_fields(self) -> dict:
        """The Section 4.8 candidate object: exactly the Section 4.6 fields,
        alias provenance excluded ("derivable from the registry the digest
        already names")."""
        scope = self.scope
        return {
            "rank": self.rank,
            "entity_kind": self.entity_kind,
            "project_code": scope.project_code,
            "revision_label": scope.revision_label,
            "network_name": scope.network_name,
            "snapshot_label": scope.snapshot_label,
            "message_key": self.message_key,
            "signal_key": self.signal_key,
            "match_tier": self.match_tier,
            "matched_text": self.matched_text,
            "match_kind": self.match_kind,
        }
