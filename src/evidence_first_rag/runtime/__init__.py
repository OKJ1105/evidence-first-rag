"""The runtime half of contract `mvp-v0.1`: Sections 4.2, 4.5, 4.8, 5 and 7.

`Runtime.execute` takes an untrusted request and returns a normalized result
with the three evidence structures Section 5 requires on every outcome,
including every negative one. `render` turns that result into user-facing
prose by the fixed-template rule of Section 4.8.

Nothing exported here imports psycopg. The database is reached through the
session port in `execution.py`, and `connection.py` -- which does import the
driver -- is imported explicitly by whoever has a database to point it at.
That is what keeps the decision path testable without one.

Section 4.3 keeps the provisioning identity out of this package: nothing here
reads the provisioning credentials, and `db/` is never imported.
"""

from .execution import Execution
from .faults import DataFault, Fault
from .render import Answer, Prose, Value, compose, render, values_of
from .request import Refusal, Request, ValidatedRequest, validate
from .service import Runtime

__all__ = [
    "Answer",
    "DataFault",
    "Execution",
    "Fault",
    "Prose",
    "Refusal",
    "Request",
    "Runtime",
    "ValidatedRequest",
    "Value",
    "compose",
    "render",
    "validate",
    "values_of",
]
