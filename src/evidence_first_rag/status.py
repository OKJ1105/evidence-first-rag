"""Section 5 status families.

All seven, as a closed enumeration. Section 5 is a table of exactly seven
rows, and a status outside them is not a status this runtime may produce, so
`Status("almost_found")` raises rather than documenting a rule nobody
enforces.
"""

import enum


class Status(enum.Enum):
    """The seven outcome families of Section 5."""

    SUCCESS = "success"
    NOT_FOUND = "not_found"
    COVERAGE_GAP = "coverage_gap"
    UNSUPPORTED = "unsupported"
    AMBIGUOUS = "ambiguous"
    INVALID_REQUEST = "invalid_request"
    NEEDS_ENTITY_DISCOVERY = "needs_entity_discovery"


# Section 5, final paragraph: "For `unsupported`, `invalid_request`, and
# `needs_entity_discovery`, no database connection is opened and the evidence
# bundle records that." Section 7 then makes `template_name`,
# `template_version`, `resolved_scope`, and `bound_parameters` empty for
# exactly these three. The set is named once so that the result type can
# enforce both obligations from the same list.
OPENS_NO_CONNECTION = frozenset(
    {
        Status.UNSUPPORTED,
        Status.INVALID_REQUEST,
        Status.NEEDS_ENTITY_DISCOVERY,
    }
)
