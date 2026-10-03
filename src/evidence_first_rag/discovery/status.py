"""entity-discovery-v0.1 Section 5: the seven outcome families of discovery.

A closed enumeration, and a different one from mvp-v0.1's `Status`, on
purpose. Section 5 is its own table: it has `resolved` and `candidates`,
which mvp-v0.1 lacks, and it does not have `success` -- "its absence is the
point": discovery returns no facts, so a discovery result can never carry
that status, and a shared enumeration would let one. The `success` that ends
a discovery flow is the mvp-v0.1 result of the fact route a selected
reference is passed to (Section 4.8, a later slice).
"""

import enum


class DiscoveryStatus(enum.Enum):
    """The seven status families of Section 5."""

    RESOLVED = "resolved"
    CANDIDATES = "candidates"
    NOT_FOUND = "not_found"
    COVERAGE_GAP = "coverage_gap"
    AMBIGUOUS = "ambiguous"
    INVALID_REQUEST = "invalid_request"
    UNSUPPORTED = "unsupported"


# Section 5, closing paragraph: "For `invalid_request`, `unsupported`, and the
# `ambiguous` case that is refused before dispatch, no discovery template
# executes and the evidence bundle records that no connection was opened for
# discovery." The first two open no connection at all.
OPENS_NO_CONNECTION = frozenset({DiscoveryStatus.INVALID_REQUEST, DiscoveryStatus.UNSUPPORTED})

# The statuses under which no discovery template ran: the two above, plus
# `coverage_gap`, which the mvp-v0.1 candidate query decides alone. Since
# `0.4.0` `ambiguous` is not among them: an incomplete scope within the
# Section 4.3 bound is searched, and `DiscoveryResult` checks that case by
# its `scope_search` instead.
EXECUTES_NO_DISCOVERY_TEMPLATE = OPENS_NO_CONNECTION | {
    DiscoveryStatus.COVERAGE_GAP,
}
