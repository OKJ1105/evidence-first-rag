"""`deploy-v0.1` Section 4.8: what the deploy job runs against the deployed resources.

Two things live here, both called from `.github/workflows/deploy.yml`:

- **`DP-004`**, the runtime identity cannot write. The same four statements
  `tests_database/test_roles.py` and the local stack's check use, plus `DROP`,
  each run with `default_transaction_read_only` turned off first, so that only
  a privilege refusal counts. A refusal of any other kind is not Section 4.4's
  guarantee and fails the case.
- **The rollback target**: the commit of the newest committed deploy record
  under `docs/acceptance/milestone-5/` whose outcome is a pass. Section 4.8 rolls
  a failed deploy back to it in both halves. None exists before the first
  passing deploy, and then there is nothing to roll back to.

Connection parameters come from the environment the job exports, never from a
command line.
"""

import argparse
import json
import os
import pathlib
import sys

WRITES = {
    "INSERT": "INSERT INTO mvp.source_snapshot"
    " (project_code, revision_label, network_name, snapshot_label, ingested_at)"
    " VALUES ('X', 'X', 'X', 'X', now())",
    "UPDATE": "UPDATE mvp.source_snapshot SET project_code = 'X'",
    "DELETE": "DELETE FROM mvp.source_snapshot",
    "CREATE": "CREATE TABLE mvp.intruder (id integer)",
    "DROP": "DROP TABLE mvp.source_snapshot",
}

RECORDS = pathlib.Path("docs/acceptance/milestone-5")


def runtime_parameters(environment) -> dict:
    return {
        "dbname": environment.get("MVP_DATABASE", "mvp"),
        "user": "mvp_runtime",
        "password": environment["MVP_RUNTIME_PASSWORD"],
        "host": environment["PGHOST"],
        "port": environment.get("PGPORT", "5432"),
        "sslmode": "require",
    }


def refused_writes(connect, errors) -> dict:
    """`DP-004`: statement name to `"refused"` or the reason it is not.

    `connect` opens a runtime connection; `errors` is `psycopg.errors`. A read
    runs first, so a connection that failed outright is never read as five
    refusals.
    """
    with connect() as connection, connection.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM mvp.source_snapshot")
        cursor.fetchone()

    outcome = {}
    for name, statement in WRITES.items():
        with connect() as connection:
            connection.autocommit = True
            with connection.cursor() as cursor:
                cursor.execute("SET default_transaction_read_only = off")
                try:
                    cursor.execute(statement)
                except errors.InsufficientPrivilege:
                    outcome[name] = "refused"
                except Exception as other:  # noqa: BLE001 - any other refusal fails the case
                    outcome[name] = f"refused by {type(other).__name__}, not by privilege"
                else:
                    outcome[name] = "performed"
    return outcome


def last_passing_commit(records: pathlib.Path = RECORDS):
    """The commit of the newest passing deploy record, or `None`."""
    # A missing directory is a mistake in the path, not "no passing deploy
    # yet": the directory is committed before the first deploy (#237 N2).
    if not records.is_dir():
        raise FileNotFoundError(f"no deploy records directory at {records}")
    passing = []
    for path in sorted(records.glob("deploy-*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        if record.get("outcome") == "success" and record.get("deployed_checks") == "pass":
            passing.append((record["date"], record["commit"]))
    return max(passing)[1] if passing else None


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("writes", help="DP-004 against the deployed database")
    commands.add_parser("last-passing", help="print the rollback target, or nothing")
    arguments = parser.parse_args(argv)

    if arguments.command == "last-passing":
        commit = last_passing_commit()
        print(commit or "")
        return 0

    import psycopg

    parameters = runtime_parameters(os.environ)
    outcome = refused_writes(lambda: psycopg.connect(**parameters), psycopg.errors)
    print(json.dumps({"DP-004": outcome}))
    return 0 if all(value == "refused" for value in outcome.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
