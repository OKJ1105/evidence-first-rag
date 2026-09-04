"""Every statement the runner issues that is not a registered template.

All of it, in one file, on purpose. Section 4.9's check `B1` says "No SQL
executed during the run originated outside the registry", and Section 4.10
requires the runner to record a database state digest, to attempt four writes
and see them refused, and to read the runtime role's `statement_timeout`. Those
obligations are both in the contract, so `B1` cannot mean that no statement
outside the registry ever reaches the connection -- it means the *runtime*,
answering a fixture, executes only registered templates. The runner's own
instrumentation is a different actor asking a different question.

Keeping that instrumentation here makes the distinction auditable rather than
asserted: `tests/test_conformance_surface.py` fails if a SQL string appears in
any other module of this package, so the set of non-registry statements is
this file and a reader can finish it in a minute.

None of it writes. The digest counts rows and reads a snapshot; the refusal
probes are expected to be refused, and run on their own connection so that a
refusal cannot poison the transaction a fixture is using.
"""

# Section 4.1's four tables. Written out rather than discovered, so that a
# table added to the schema without being added here fails the digest's own
# test instead of quietly leaving a table unwatched.
TABLES = ("source_snapshot", "message_occurrence", "signal_occurrence", "signal_mapping")

SCHEMA = "mvp"

# Section 4.10's four refusals. The statements are the ones
# `tests_database/test_roles.py` asserts as a property of the roles; here they
# are executed again so that the artifact records the refusal, which is what
# Section 4.10 asks for -- "an assertion that passes in a test file nobody
# reads is not the same as a recorded result".
REFUSALS = {
    "INSERT": (
        f"INSERT INTO {SCHEMA}.source_snapshot"
        " (project_code, revision_label, network_name, snapshot_label, ingested_at)"
        " VALUES ('SAMPLE_PROBE', 'SAMPLE_PROBE', 'SAMPLE_PROBE', 'SAMPLE_PROBE', now())"
    ),
    "UPDATE": f"UPDATE {SCHEMA}.source_snapshot SET project_code = 'SAMPLE_PROBE'",
    "DELETE": f"DELETE FROM {SCHEMA}.source_snapshot",
    "CREATE TABLE": f"CREATE TABLE {SCHEMA}.sample_probe (id integer)",
}


def state_digest(connection) -> dict:
    """Section 4.10's digest: row counts per table, and the visible transaction id.

    **Which transaction identifier, and why it matters.** Section 4.10 asks for
    "the highest transaction identifier visible to the runtime identity", and
    there are two candidates. `pg_snapshot_xmax(pg_current_snapshot())` reads
    the cluster's counter; `max(xmin)` over the four tables reads the newest
    transaction that wrote a row this identity can select. This uses the
    second, and the choice is forced rather than stylistic.

    The cluster counter is global. It advances for autovacuum, for another
    database on the same server, for anything at all -- measured here at eight
    per invariant-check run and moving under unrelated activity in a different
    database entirely. Section 4.9's `D1` requires two runs to produce
    identical artifacts, excluding only the run identifier and the timestamp,
    so a digest built on the cluster counter makes `D1` fail intermittently
    for reasons that have nothing to do with the run. Section 4.10 and Section
    4.9 would then be unsatisfiable together.

    `max(xmin)` is a property of the rows rather than of the server. It is
    unchanged by activity elsewhere, and it changes when this data is written,
    which is what a state digest is for. It is also strictly the better
    detector: a rewrite that preserved every row count would leave the counts
    identical and move this.

    Read as text because a transaction identifier is 32-bit and wraps; the
    digest compares it for equality and never for order.

    Caveat, recorded rather than hidden: `VACUUM FREEZE` rewrites `xmin` to
    the frozen sentinel, so a freeze between two digests would move this
    without any data change. Freezing requires a table age far beyond a run,
    and the row counts alongside are unaffected.
    """
    digest = {"row_counts": {}, "highest_transaction_id": None}
    highest = 0
    with connection.cursor() as cursor:
        for table in TABLES:
            # The table name comes from the tuple above, never from a caller.
            cursor.execute(f"SELECT count(*) FROM {SCHEMA}.{table}")
            digest["row_counts"][table] = cursor.fetchone()[0]
            cursor.execute(
                f"SELECT coalesce(max(xmin::text::bigint), 0) FROM {SCHEMA}.{table}"
            )
            highest = max(highest, cursor.fetchone()[0])
    digest["highest_transaction_id"] = str(highest)
    return digest


def statement_timeout(connection) -> str:
    """The runtime role's `statement_timeout`, as PostgreSQL reports it."""
    with connection.cursor() as cursor:
        cursor.execute("SHOW statement_timeout")
        return cursor.fetchone()[0]


def refusals(connect) -> dict:
    """Attempt each Section 4.10 write and record how it was refused.

    `connect` is called per statement and must yield a fresh connection as the
    runtime identity: a refused statement aborts its transaction, so reusing
    one would make every refusal after the first a consequence of the previous
    failure rather than of the privilege being tested.

    The recorded value is PostgreSQL's own SQLSTATE. Section 4.10 requires the
    refusal to "originate from PostgreSQL privileges, not from an application
    guard", and `42501` (insufficient_privilege) is the database saying which
    it was; a refusal that arrived as `25006` (read_only_sql_transaction)
    would mean the transaction mode answered first and the grant is untested.
    """
    recorded = {}
    for name, statement in REFUSALS.items():
        with connect() as connection:
            # Section 4.3 gives the runtime identity SELECT only, and the role
            # also defaults to a read-only transaction. Turning that default
            # off isolates the privilege, which is the thing Section 4.10 says
            # the refusal must come from.
            connection.read_only = False
            try:
                with connection.cursor() as cursor:
                    cursor.execute(statement)
            except Exception as refused:  # noqa: BLE001 - the refusal is the result
                recorded[name] = {
                    "refused": True,
                    "sqlstate": getattr(refused, "sqlstate", None),
                    "from_privileges": getattr(refused, "sqlstate", None) == "42501",
                }
            else:
                recorded[name] = {
                    "refused": False,
                    "sqlstate": None,
                    "from_privileges": False,
                }
            connection.rollback()
    return recorded
