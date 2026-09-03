"""Section 4.4's fixed SQL template registry.

The public surface is deliberately small, and its smallness is the point.
Charter Section 3.1 and AGENTS.md forbid any public arbitrary-SQL,
arbitrary-table, or arbitrary-column interface; nothing exported here accepts
SQL text, a table name, or a column name from a caller, and
`tests/test_registry_surface.py` enumerates this list so that adding one has
to fail a test.

`Template` itself is not exported. Its constructor accepts SQL text, so a
caller who could reach it could build an unreviewed query that satisfies every
registration safeguard without ever being one of the four templates Section
4.4 registers. The only Templates that exist are the four `registry.py`
builds for itself; `get(name)` is the intended way anything outside this
package reaches one. Being left out of `__all__` does not stop a direct
`evidence_first_rag.registry.template` import, so
`tests/test_registry_surface.py` additionally scans the source tree and fails
if anything outside this package imports `Template` from there -- the
enforcement this docstring's claim depends on, not just the export list.
"""

from .registry import (
    REGISTERED,
    SCHEMA,
    TPL_MESSAGE_FACTS_V1,
    TPL_SIGNAL_FACTS_V1,
    TPL_SIGNAL_MAPPING_V1,
    TPL_SNAPSHOT_CANDIDATES_V1,
    get,
    names,
)
from .template import (
    FORBIDDEN_KEYWORDS,
    LimitMeaning,
    ParameterError,
    TemplateError,
    UnregisteredTemplate,
)

__all__ = [
    "FORBIDDEN_KEYWORDS",
    "LimitMeaning",
    "ParameterError",
    "REGISTERED",
    "SCHEMA",
    "TPL_MESSAGE_FACTS_V1",
    "TPL_SIGNAL_FACTS_V1",
    "TPL_SIGNAL_MAPPING_V1",
    "TPL_SNAPSHOT_CANDIDATES_V1",
    "TemplateError",
    "UnregisteredTemplate",
    "get",
    "names",
]
