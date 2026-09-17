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

from ..registry import UnregisteredTemplate, get
from .execution import Execution
from .faults import ConnectionUnavailable, Fault


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
        try:
            connection = psycopg.connect(
                row_factory=dict_row, **dict(self.connection_parameters)
            )
        except psycopg.OperationalError as unreachable:
            # `api-v0.1` Section 4.5 answers this with `database_unavailable`
            # at HTTP 503, and a request that ran and failed with
            # `runtime_fault` at 500. Translated here because this is the one
            # module that imports the driver: a surface that caught
            # `psycopg.OperationalError` itself would have to import psycopg to
            # name it, and `tests/` would then need the driver to test a
            # refusal that opens no connection. Narrow on purpose --
            # `OperationalError` from `connect` is the connection failing;
            # anything else psycopg raises here is a defect and stays raw.
            raise ConnectionUnavailable(
                "no session could be opened, so the request was never attempted"
            ) from unreachable
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
        runtime supplying a null scope dimension live.

        **`template` is checked for identity against the registry first**, and
        that check is the difference between this method carrying a query and
        not. An external review demonstrated the hole it closes: nothing here
        constrained the argument's type, so any object exposing `.name`,
        `.sql` and `.bind` reached `cursor.execute` -- a plain
        `SimpleNamespace` carrying `DELETE FROM mvp.source_snapshot` was run
        through this method and arrived at the driver intact. The read-only
        role would have refused that particular statement, but an arbitrary
        `SELECT` over any table, with no `LIMIT` and no `ORDER BY`, was fully
        available, which is precisely the "arbitrary-table, arbitrary-column
        interface" Charter Section 3.1 forbids.

        Identity, not a type check: `isinstance(template, Template)` would
        pass a forged instance, and Issue #28 established that one can be
        built with no import at all. `get(name) is template` passes only for
        the four objects `registry.py` constructed for itself.
        """
        self._must_be_registered(template)
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

    @staticmethod
    def _must_be_registered(template) -> None:
        """Refuse anything that is not one of the four registered objects.

        Raised as a `Fault` rather than returned as a status: Section 5's
        seven families are claims about a request, and a caller reaching this
        boundary with an unregistered template is a defect in the runtime, not
        an answer to give somebody.
        """
        try:
            registered = get(getattr(template, "name", None))
        except UnregisteredTemplate as unknown:
            raise Fault(
                f"the session was handed {type(template).__name__} naming"
                f" {getattr(template, 'name', None)!r}, which the registry does"
                f" not hold; Section 4.4 refuses execution for any template"
                f" name not in the registry"
            ) from unknown
        if template is not registered:
            raise Fault(
                f"the session was handed an object claiming to be"
                f" {registered.name}, but it is not the registered template of"
                f" that name; Section 4.4 makes the committed SQL the only text"
                f" this boundary may run"
            )
