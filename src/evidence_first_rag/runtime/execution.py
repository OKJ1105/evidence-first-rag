"""The narrow opening between the runtime and a database.

Everything the runtime needs from PostgreSQL is here: open a session as the
Section 4.3 runtime identity, run a registered template, get rows back. The
port is this small on purpose. Section 4.4 forbids any public interface that
accepts SQL text, a table name, or a column name from a caller, so `execute`
takes a registered `Template` and a mapping of arguments and nothing else --
there is no shape of call through this boundary that carries a query.

Keeping the port here rather than in `connection.py` also keeps the driver out
of the runtime's import graph. `service.py` reasons about sessions and never
imports psycopg, which is what lets the whole decision path be tested from a
clean checkout with no database and no driver installed.
"""

import dataclasses
import types
from collections.abc import Mapping

from ..result import Row


@dataclasses.dataclass(frozen=True, kw_only=True)
class Execution:
    """One registered template, run once.

    `bound_parameters` is what the session actually bound, returned rather
    than re-derived by the caller. Section 7 requires the evidence bundle to
    contain "exactly the parameters bound, with values", and a caller that
    computed that mapping a second time would be recording what it believes
    was bound rather than what was.
    """

    rows: tuple[Row, ...]
    bound_parameters: Mapping[str, object]

    def __post_init__(self) -> None:
        object.__setattr__(self, "rows", tuple(self.rows))
        object.__setattr__(
            self, "bound_parameters", types.MappingProxyType(dict(self.bound_parameters))
        )


class Session:
    """What `Runtime` expects of an open database session.

    Not inherited from -- it documents the three names a session has to
    provide, and `connection.py` provides them over psycopg while the tests
    provide them over recorded rows. Both are checked against this docstring
    rather than against a base class, because a base class here would invite
    partial implementations that inherit a default nobody meant.

    - `role_name`: the identity the connection was opened with. Section 7
      requires it in `read_only_safeguards`, and Section 4.3 says which
      identity it must be.
    - `read_only_transaction`: whether the session opened a read-only
      transaction. Reported, never asserted: Section 4.10 requires the
      refusal of a write to come from PostgreSQL rather than from an
      application guard, so a session that failed to open read-only records
      that fact instead of raising over it.
    - `execute(template, arguments)`: bind through `template.bind` -- which is
      where Section 4.4's allowlist and required-parameter refusals live --
      and run the registered SQL. Returns an `Execution`.
    """

    def __init__(self) -> None:
        raise TypeError(
            "Session documents the session protocol; it is not constructed."
            " connection.PsycopgSession implements it over a database."
        )
