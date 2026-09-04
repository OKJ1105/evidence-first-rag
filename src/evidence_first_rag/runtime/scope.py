"""Section 4.2 scope enforcement: what the runtime may and may not decide.

The whole of this module exists to *not* choose a snapshot. Section 4.2: "The
runtime never supplies a missing `project_code`, `revision_label`,
`network_name`, or `snapshot_label`. It never selects the newest
`ingested_at`, the highest `revision_label`, or the only loaded row." There is
no ordering here, no `max`, no fallback and no default; the candidate query is
run, and what comes back either identifies one snapshot because the request
did, or it does not.

Section 4.2 as amended in contract version `0.4.0` also settles the threshold:
"When a request omits or under-specifies scope and one or more candidate
snapshots match, the runtime returns `ambiguous` ... One matching candidate is
still `ambiguous`." So the candidate count is not consulted for anything
except telling `coverage_gap` (zero) from `ambiguous` (one or more). An
implementation that branched on "exactly one" would be selecting the only
loaded row, which is the rule immediately above.
"""

import dataclasses

from ..references import SCOPE_DIMENSIONS, SnapshotScope
from ..registry import get
from .execution import Execution
from .faults import DataFault
from .request import CANDIDATES_TEMPLATE, ValidatedRequest


@dataclasses.dataclass(frozen=True, kw_only=True)
class Candidates:
    """What `TPL_SNAPSHOT_CANDIDATES_V1` returned for a request's scope."""

    scopes: tuple[SnapshotScope, ...]
    execution: Execution
    truncated: bool

    @property
    def row_count(self) -> int:
        return len(self.execution.rows)


def candidates(session, request: ValidatedRequest) -> Candidates:
    """Run the candidate query for `request`'s scope, whatever it holds.

    Run on every route and every request, including a fully scoped one. That
    is what makes Section 5's `not_found` and `coverage_gap` distinguishable:
    both return no facts, and the difference is whether the scope named a
    snapshot that exists. A runtime that only ran the route's own template
    would see zero rows in both cases and would have to guess.
    """
    template = get(CANDIDATES_TEMPLATE)
    run = session.execute(template, request.scope_arguments)
    scopes = tuple(
        SnapshotScope(**{name: row[name] for name in SCOPE_DIMENSIONS})
        for row in run.rows
    )
    return Candidates(
        scopes=scopes,
        execution=run,
        truncated=template.truncated(len(run.rows)),
    )


def resolved(request: ValidatedRequest, found: Candidates) -> SnapshotScope:
    """The one snapshot a complete scope names.

    Only called once the caller has established that the request's scope is
    complete and that at least one candidate matched. More than one candidate
    for a complete scope contradicts the Section 4.1 unique constraint on the
    four dimensions, so it is a fault in what was loaded rather than an
    outcome: answering it would mean picking one of several, which is the
    thing Section 4.2 forbids.
    """
    if len(found.scopes) != 1:
        raise DataFault(
            f"a complete scope matched {len(found.scopes)} snapshots; Section"
            f" 4.1 makes (project_code, revision_label, network_name,"
            f" snapshot_label) unique, so the loaded database contradicts it"
        )
    return found.scopes[0]
