"""The normalized result: one shape for all seven outcomes.

Section 5 requires every status — including every negative one — to carry an
`evidence_bundle`, a `source_trace`, and a `limitations` list. Making the
three required keyword arguments is what turns that from a rule into a shape:
a result that omits one does not construct.

The cross-field rules below are the ones Section 5 states unconditionally,
and only those. Where two Sections read differently the type stays out of it,
so that a later slice resolves the question in the open rather than inheriting
a decision this one made quietly.
"""

import dataclasses
import types
from collections.abc import Mapping

from .evidence import EvidenceBundle, Limitation, LimitationKind, SourceTrace
from .status import OPENS_NO_CONNECTION, Status

# One row of a result. Section 4.4 fixes the result column list and its order
# per template, so the columns belong to the registry rather than to this
# type; a mapping preserves the order the template declared.
Row = Mapping[str, object]

# Section 7 requires an entry for these two outcomes unconditionally. The
# other three conditions Section 7 lists depend on data this type cannot see.
REQUIRED_LIMITATION = types.MappingProxyType(
    {
        Status.COVERAGE_GAP: LimitationKind.COVERAGE_NOT_ESTABLISHED,
        Status.NEEDS_ENTITY_DISCOVERY: LimitationKind.ENTITY_DISCOVERY_NOT_IMPLEMENTED,
    }
)


@dataclasses.dataclass(frozen=True, kw_only=True)
class Result:
    """The normalized result envelope of Sections 5 and 7."""

    status: Status
    evidence_bundle: EvidenceBundle
    source_trace: SourceTrace
    limitations: tuple[Limitation, ...] = ()
    rows: tuple[Row, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.status, Status):
            raise ValueError("status must be a Status")
        if not isinstance(self.evidence_bundle, EvidenceBundle):
            raise ValueError("evidence_bundle must be an EvidenceBundle")
        if not isinstance(self.source_trace, SourceTrace):
            raise ValueError("source_trace must be a SourceTrace")
        object.__setattr__(self, "limitations", _limitations(self.limitations))
        object.__setattr__(self, "rows", _rows(self.rows))

        # Section 5, closing paragraph: these three open no database
        # connection. The bundle already refuses to record execution when no
        # connection was opened; this is the other half, so that a status
        # cannot claim a connection the family forbids.
        if self.status in OPENS_NO_CONNECTION:
            if self.evidence_bundle.read_only_safeguards.connection_opened:
                raise ValueError(
                    f"{self.status.value} opens no database connection (Section 5)"
                )
            if self.rows:
                raise ValueError(f"{self.status.value} returns no rows (Section 5)")

        # Section 5: `success` means the registered template returned at
        # least one row. A success carrying nothing is a `not_found` that
        # reported the wrong family.
        if self.status is Status.SUCCESS:
            if not self.rows:
                raise ValueError("success requires at least one row (Section 5)")
            if self.evidence_bundle.row_count < 1:
                raise ValueError("success requires a row_count of at least 1 (Section 5)")

        # Section 5: `not_found` means no row matched the lookup key.
        if self.status is Status.NOT_FOUND:
            if self.rows:
                raise ValueError("not_found returns no rows (Section 5)")
            if self.evidence_bundle.row_count != 0:
                raise ValueError("not_found requires a row_count of 0 (Section 5)")

        # Section 7: the trace records the producing layer for `unsupported`.
        if (
            self.status is Status.UNSUPPORTED
            and self.source_trace.producing_layer is None
        ):
            raise ValueError(
                "unsupported must record its producing layer (Section 7)"
            )

        required = REQUIRED_LIMITATION.get(self.status)
        if required is not None and not self.has_limitation(required):
            raise ValueError(
                f"{self.status.value} requires a {required.value} limitation (Section 7)"
            )

    def has_limitation(self, kind: LimitationKind) -> bool:
        return any(limitation.kind is kind for limitation in self.limitations)


def _limitations(value: object) -> tuple[Limitation, ...]:
    if isinstance(value, str) or not hasattr(value, "__iter__"):
        raise ValueError("limitations must be an iterable of Limitation")
    items = tuple(value)
    for index, item in enumerate(items):
        if not isinstance(item, Limitation):
            raise ValueError(f"limitations[{index}] must be a Limitation")
    return items


def _rows(value: object) -> tuple[Row, ...]:
    """Copy each row into a mapping the result's holder cannot mutate.

    Section 4.9's check `A1` compares a result with its registered expectation
    field by field. A result whose rows can be edited after construction is
    not the thing that was compared.
    """
    if isinstance(value, (str, Mapping)) or not hasattr(value, "__iter__"):
        raise ValueError("rows must be an iterable of mappings")
    rows = []
    for index, row in enumerate(value):
        if not isinstance(row, Mapping):
            raise ValueError(f"rows[{index}] must be a mapping")
        for column in row:
            if not isinstance(column, str) or column == "":
                raise ValueError(f"rows[{index}] has a column name that is not text")
        rows.append(types.MappingProxyType(dict(row)))
    return tuple(rows)
