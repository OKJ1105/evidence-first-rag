"""Section 4.2 canonical references.

Section 4.2 states that the runtime never supplies a missing `project_code`,
`revision_label`, `network_name`, or `snapshot_label`. Written as a runtime
check that rule is one `if` somebody forgets on one path; written as a
construction error it has no path to forget. Every type here rejects a partial
tuple in __post_init__, so a reference that exists is complete by the time
anything can hold it.

The types nest rather than flatten. A signal reference is a message reference
plus a signal key (Section 4.2, and Section 4.4's parameter lists say the same
thing), so composing them makes the parent reference structurally present
instead of re-declaring five fields that could drift.
"""

import dataclasses

from ._validation import required_text

# Section 4.2. The four dimensions, in the order Section 4.4 fixes for the
# candidate template's ordering clause.
SCOPE_DIMENSIONS = ("project_code", "revision_label", "network_name", "snapshot_label")


@dataclasses.dataclass(frozen=True, kw_only=True)
class SnapshotScope:
    """The four scope dimensions that identify exactly one snapshot.

    Section 4.1 puts a unique constraint on this tuple, so a complete scope
    names at most one snapshot. Section 4.2 forbids the runtime from filling
    any dimension in — not by choosing the newest `ingested_at`, not by
    choosing the highest `revision_label`, and not by choosing the only row
    that happens to be loaded.
    """

    project_code: str
    revision_label: str
    network_name: str
    snapshot_label: str

    def __post_init__(self) -> None:
        for dimension in SCOPE_DIMENSIONS:
            required_text(dimension, getattr(self, dimension))

    def as_parameters(self) -> dict[str, str]:
        """The four scope dimensions as named parameters.

        Section 4.4 requires every variable to be bound as a named parameter
        and prohibits string interpolation. The names here are the parameter
        names Section 4.4 allows, which is why the mapping is built from the
        reference rather than reassembled by each caller.
        """
        return {dimension: getattr(self, dimension) for dimension in SCOPE_DIMENSIONS}


@dataclasses.dataclass(frozen=True, kw_only=True)
class MessageReference:
    """A canonical message reference: a complete scope plus `message_key`."""

    scope: SnapshotScope
    message_key: str

    def __post_init__(self) -> None:
        if not isinstance(self.scope, SnapshotScope):
            raise ValueError("scope must be a SnapshotScope")
        required_text("message_key", self.message_key)

    def as_parameters(self) -> dict[str, str]:
        """The five parameters `TPL_MESSAGE_FACTS_V1` requires (Section 4.4)."""
        return {**self.scope.as_parameters(), "message_key": self.message_key}


@dataclasses.dataclass(frozen=True, kw_only=True)
class SignalReference:
    """A canonical signal reference: a message reference plus `signal_key`.

    The `message_key` in the nested reference is the parent message's, which
    is what makes Section 4.1's `(message_occurrence_id, signal_key)`
    constraint reachable from a request. Section 4.2's closing rule — that
    equal `signal_key` values in different snapshots imply nothing — is why
    the parent is carried rather than the signal key alone.
    """

    message: MessageReference
    signal_key: str

    def __post_init__(self) -> None:
        if not isinstance(self.message, MessageReference):
            raise ValueError("message must be a MessageReference")
        required_text("signal_key", self.signal_key)

    @property
    def scope(self) -> SnapshotScope:
        return self.message.scope

    @property
    def message_key(self) -> str:
        return self.message.message_key

    def as_parameters(self) -> dict[str, str]:
        """The six parameters `TPL_SIGNAL_FACTS_V1` requires (Section 4.4)."""
        return {**self.message.as_parameters(), "signal_key": self.signal_key}
