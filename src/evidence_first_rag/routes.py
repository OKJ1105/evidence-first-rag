"""Section 4.5 routes, and the literal Section 4.6 puts beside them.

Section 4.5 registers three routes. Section 4.6 says the adapter's `route`
field is "one of the three names in Section 4.5 or the literal
`unsupported`", so the value in a route position is drawn from four
possibilities but only three of them are routes. Keeping `unsupported` out of
the enum preserves that distinction: a caller that receives a `Route` holds an
approved route, and the one value that is not a route has to be named
explicitly.
"""

import enum


class Route(enum.Enum):
    """The three approved routes of Section 4.5."""

    MESSAGE_FACTS = "message_facts"
    SIGNAL_FACTS = "signal_facts"
    SIGNAL_MAPPING = "signal_mapping"


# Section 4.6. The one non-route value a route field may carry.
UNSUPPORTED_ROUTE = "unsupported"


def route_field(value: object) -> Route | str:
    """Return `value` when Section 4.6 permits it in a route field.

    Accepts a `Route` or the literal `unsupported`, and nothing else. The
    return type is a union rather than a normalized string because a caller
    that has an approved route should keep the type that says so.
    """
    if isinstance(value, Route):
        return value
    if value == UNSUPPORTED_ROUTE:
        return UNSUPPORTED_ROUTE
    raise ValueError(
        f"route must be a Route or the literal {UNSUPPORTED_ROUTE!r}, not {value!r}"
    )


def route_name(value: Route | str) -> str:
    """Return the wire name of a value that has passed `route_field`."""
    return value.value if isinstance(value, Route) else value
