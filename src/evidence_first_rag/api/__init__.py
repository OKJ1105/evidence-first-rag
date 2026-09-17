"""Contract `api-v0.1`: the surface a caller reaches the runtime through.

Section 4.4 is implemented here and nothing else is yet. The module holds no
route, opens no connection, and imports no driver: a normalized result goes in
and a JSON document comes out, or the reverse.
"""

from .serialize import NUMERIC_COLUMNS, as_json, dumps, from_json

__all__ = ["as_json", "from_json", "dumps", "NUMERIC_COLUMNS"]
