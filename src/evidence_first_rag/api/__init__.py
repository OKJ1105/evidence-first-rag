"""Contract `api-v0.1`: the surface a caller reaches the runtime through.

Two modules, and the split is the contract's. `serialize` is Section 4.4 -- a
normalized result becomes a JSON document and the document becomes the result
back, with no route, no connection and no driver anywhere in it. `app` is
Sections 4.1 to 4.3 and 4.5: the five routes, the envelope that wraps what
`serialize` wrote, and the six refusals.

`app` is deliberately not re-exported here. It needs the `api` extra and
`serialize` needs nothing, so a module that imported both would make
`from evidence_first_rag.api import as_json` fail on an install that never
asked for a web framework -- and `tests/test_api_serialize.py` would then need
one to run.
"""

from .serialize import NUMERIC_COLUMNS, as_json, dumps, from_json

__all__ = ["as_json", "from_json", "dumps", "NUMERIC_COLUMNS"]
