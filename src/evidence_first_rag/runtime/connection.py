"""The one implementation of the session port that talks to PostgreSQL.

Section 4.3: "The runtime opens every connection with the runtime identity
inside a read-only transaction. The runtime never holds the provisioning
credentials." Both halves are structural here. The connection parameters are
handed in, and nothing in this module reads the provisioning environment
variables that `db/provision.py` uses; and every session sets `read_only`
before it runs anything.

This is the only module in `runtime/` that imports psycopg, and it is
deliberately not imported by `runtime/__init__.py`. The decision path in
`service.py` reasons about the port in `execution.py`, so `tests/` runs the
whole of Sections 4.2, 4.5, 4.8 and 5 from a clean checkout with neither the
driver nor a database, and `tests_database/` runs the same code against the
service container that holds the registered fixtures.

Section 4.10 requires a write refusal to originate from PostgreSQL privileges
"not from an application guard", so there is no application-level write check
here. What the session reports is what it asked for; what the database allowed
is what `tests_database/test_roles.py` asserts.
"""

import contextlib
import dataclasses
from collections.abc import Mapping

import psycopg
from psycopg.rows import dict_row

from .execution import Execution
from .faults import Fault


@dataclasses.dataclass(frozen=True, kw_only=True)
class PsycopgDatabase:
    """Opens a read-only session per request, as the runtime identity.

    One connection per request rather than a pool, and it is closed on the way
    out. The scope-resolution query and the route's own query run in one
    read-only transaction at REPEATABLE READ, so both see the same database
    state: under PostgreSQL's default READ COMMITTED, a snapshot committed
    between the two statements would be visible to the second and not the
    first, and the evidence would then describe two databases. Not a threat
    the fixtures exercise -- the runtime identity cannot write, and
    provisioning loads once -- but the claim "one result, one state" is cheap
    to make true and expensive to make false later.
    """

    connection_parameters: Mapping[str, object]

    @contextlib.contextmanager
    def session(self):
        connection = psycopg.connect(
            row_factory=dict_row, **dict(self.connection_parameters)
        )
        try:
            # Set before any statement runs, so the first transaction the
            # session opens is already read-only. Section 4.3 wants the
            # transaction read-only, not the queries inspected.
            connection.read_only = True
            connection.isolation_level = psycopg.IsolationLevel.REPEATABLE_READ
            yield PsycopgSession(connection=connection)
        finally:
            # A read-only transaction has nothing to commit, and rolling back
            # says so rather than relying on close() to decide.
            connection.rollback()
            connection.close()


@dataclasses.dataclass(frozen=True, kw_only=True)
class PsycopgSession:
    """One open connection, restricted to the registered templates."""

    connection: object

    @property
    def role_name(self) -> str:
        """The identity the connection was opened with (Section 7).

        Read from the connection's own parameters rather than from a
        `SELECT current_user`. Section 4.4 registers four templates and that
        is not one of them, and Section 4.9's check `B1` asserts that no SQL
        executed during a run originated outside the registry.
        """
        return self.connection.info.user

    @property
    def read_only_transaction(self) -> bool:
        return self.connection.read_only is True

    def execute(self, template, arguments) -> Execution:
        """Bind and run one registered template.

        Binding goes through `template.bind`, which is where Section 4.4's
        allowlist, its required-parameter refusal, and its prohibition on the
        runtime supplying a null scope dimension live. There is no path here
        that reaches `cursor.execute` with anything but `template.sql`.
        """
        bound = template.bind(arguments)
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(template.sql, dict(bound))
                rows = tuple(dict(row) for row in cursor.fetchall())
        except psycopg.errors.QueryCanceled as cancelled:
            # Section 4.4: the runtime identity runs with `statement_timeout =
            # 5s`, and "a timeout is an operational fault, not an outcome: it
            # fails the request rather than producing a status family, and the
            # conformance runner classes it `runtime`."
            raise Fault(
                f"{template.name} was cancelled by the database, which is what"
                f" the runtime role's statement_timeout does; Section 4.4 makes"
                f" this an operational fault and not a status"
            ) from cancelled
        return Execution(rows=rows, bound_parameters=bound)
