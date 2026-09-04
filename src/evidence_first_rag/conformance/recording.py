"""Two instruments watching one run, at two different depths.

Section 4.9's `B1` — "No SQL executed during the run originated outside the
registry" — is a claim about statements that reached the database. Watching the
runtime's session port would only show what the runtime *meant* to run, so
there are two recorders here and they answer different questions.

`RecordingCursor` sits at the psycopg boundary. Every `execute` on the
connection passes through it, whatever Python issued it, so it sees a
statement that never touched the session port. This is what `B1` reads.

`RecordingDatabase` sits at the port and attributes each execution to the
template and the fixture that asked for it. `B2` needs that attribution — "no
negative outcome reached a factual SQL success" is per fixture — and the
driver recorder cannot supply it, because at that depth a statement is a
string with no fixture attached.

**Why the depth matters here specifically.** Issue #28 established that
`Template`'s seal is bypassable with no import at all: `type(exported_instance)`
hands out the class, and a forged template carrying arbitrary SQL binds
parameters and executes like any other. So no instrument that trusts a
`Template` — its `name`, its `isinstance`, its seal — can establish where a
statement came from. The only trustworthy anchor is the committed SQL text in
`registry.py`, and the only trustworthy place to observe is where the text
meets the driver.
"""

import contextlib
import dataclasses


@dataclasses.dataclass(frozen=True, kw_only=True)
class PortExecution:
    """One template the runtime asked the port to run."""

    template_name: str
    sql: str
    row_count: int


def recording_cursor(sink: list):
    """A psycopg cursor class that appends every statement it runs to `sink`.

    Built per run rather than installed globally, so two runs cannot write
    into each other's record and a leftover sink cannot make an empty run look
    busy.

    psycopg is imported here rather than at module scope so that the pure
    test suite, which runs with no driver installed, can import this module
    for `PortExecution` and the checks that read it.
    """
    import psycopg


    class RecordingCursor(psycopg.Cursor):
        def execute(self, query, params=None, *args, **keywords):
            sink.append(_text(query))
            return super().execute(query, params, *args, **keywords)

    return RecordingCursor


def _text(query) -> str:
    """The statement as text, whatever form psycopg was handed."""
    if isinstance(query, bytes):
        return query.decode("utf-8", "replace")
    return str(query)


class RecordingDatabase:
    """Wraps a database and attributes each execution to its template."""

    def __init__(self, database):
        self._database = database
        self.executions: list[PortExecution] = []

    @contextlib.contextmanager
    def session(self):
        with self._database.session() as session:
            yield _RecordingSession(session, self.executions)

    def since(self, mark: int) -> list[PortExecution]:
        return self.executions[mark:]


class _RecordingSession:
    def __init__(self, session, executions):
        self._session = session
        self._executions = executions
        self.role_name = session.role_name
        self.read_only_transaction = session.read_only_transaction

    def execute(self, template, arguments):
        run = self._session.execute(template, arguments)
        self._executions.append(
            PortExecution(
                template_name=template.name, sql=template.sql, row_count=len(run.rows)
            )
        )
        return run
