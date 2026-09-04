"""Section 4.5's three approved routes, as a closed set.

Section 4.5 fixes exactly three route names and Section 4.6 adds one more
value the adapter may emit: the literal `unsupported`. Written as an
enumeration, a route outside the three has no representation, so
`Route("message_fact")` raises rather than reaching a dispatch table that
would have to notice.

The `unsupported` literal is deliberately *not* a member. It is not a route
the runtime dispatches; it is the adapter's way of saying no route applies
(Section 4.6), and making it a fourth member would let it be looked up in the
route-to-template map that Section 4.5 defines for the three.

This module holds no dispatch logic and imports nothing from this package.
`EvidenceBundle.route` (see `evidence.py`) records a route on every result,
including the negative ones, so the name a result carries has to be reachable
from the type surface without pulling the runtime in behind it.
"""

import enum


class Route(enum.Enum):
    """The three approved routes of Section 4.5."""

    MESSAGE_FACTS = "message_facts"
    SIGNAL_FACTS = "signal_facts"
    SIGNAL_MAPPING = "signal_mapping"


# Section 4.6: the adapter's structured output carries "one of the three names
# in Section 4.5 or the literal `unsupported`". Named here so that the runtime
# recognises the adapter's own refusal rather than treating it as one more
# unknown route -- Section 5 requires the trace to record which layer produced
# an `unsupported` outcome, and those two cases have different answers.
UNSUPPORTED_ROUTE = "unsupported"


def route_or_none(value: object) -> Route | None:
    """`value` as a Route, or None when it is not one of the three names.

    Accepts a Route unchanged so that a caller inside this package does not
    have to round-trip through the string form. Everything else is untrusted
    adapter output (Section 4.6), which is why an unknown value returns None
    rather than raising: the runtime turns it into a status, and a raised
    exception would have to be caught somewhere to do that anyway.
    """
    if isinstance(value, Route):
        return value
    if isinstance(value, str):
        try:
            return Route(value)
        except ValueError:
            return None
    return None
