"""Section 4.4's fixed SQL template registry.

The public surface is deliberately small, and its smallness is the point.
Charter Section 3.1 and AGENTS.md forbid any public arbitrary-SQL,
arbitrary-table, or arbitrary-column interface; nothing exported here accepts
SQL text, a table name, or a column name from a caller, and
`tests/test_registry_surface.py` enumerates this list so that adding one has
to fail a test.
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
    Template,
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
    "Template",
    "TemplateError",
    "UnregisteredTemplate",
    "get",
    "names",
]
