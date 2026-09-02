"""Provision the database: apply the SQL in lexical order, then load.

Section 3.4 fixes the shape of this: "Version-controlled DDL and grant
scripts, applied in lexical order." They are applied by `psql` exactly as
committed, so the files in `sql/` are the provisioning path rather than a
description of it, and anyone can run them by hand and get the same database.

Two directories, applied in order, because they have different targets:

  sql/cluster/   the maintenance database, as the cluster superuser. Creates
                 the two roles of Section 4.3 and the database of Section 6.
  sql/database/  the application database, as the provisioning identity.
                 Creates the schema of Section 4.1 and the grants of 4.3.

Then the loader runs, as the provisioning identity, in one transaction —
Section 3.4 puts it "inside the same provisioning step ... before the runtime
identity ever connects", and Section 4.11 forbids a partial load.

Passwords come from the environment and are passed to psql as variables. No
password is committed, and none appears in a SQL file.
"""

import argparse
import os
import pathlib
import subprocess
import sys

import psycopg

from . import fixtures, loader

MAINTENANCE_DATABASE = "postgres"
DEFAULT_DATABASE = "mvp"
PROVISIONING_ROLE = "mvp_provisioning"


def psql_command(
    database: str, user: str, path: pathlib.Path, variables: dict
) -> list[str]:
    """Build the psql argv for one SQL file.

    Pure, and separate from running it, so a test can assert what does and does
    not appear here. Nothing secret may: argv is readable by any process on the
    host through `ps` or /proc/<pid>/cmdline for as long as psql runs. The role
    passwords travel in the environment instead, and the SQL reads them with
    `\getenv`; only `database_name`, which is not a secret, is passed as a
    variable.

    ON_ERROR_STOP is what makes "applied in lexical order" meaningful: without
    it psql reports an error and carries on, and a later file would be applied
    to a database the earlier one failed to build.
    """
    command = [
        "psql",
        "--no-psqlrc",
        "--quiet",
        "--set", "ON_ERROR_STOP=1",
        "--dbname", database,
        "--username", user,
        "--file", str(path),
    ]
    for name, value in variables.items():
        command += ["--set", f"{name}={value}"]
    return command


def _psql(database: str, user: str, password: str, path: pathlib.Path, variables: dict) -> None:
    """Apply one SQL file, failing the whole run on the first error."""
    command = psql_command(database, user, path, variables)

    # PGPASSWORD and the MVP_* role passwords reach psql through the
    # environment, which other processes cannot read, rather than through argv,
    # which they can.
    environment = dict(os.environ, PGPASSWORD=password)
    result = subprocess.run(command, env=environment, capture_output=True, text=True)
    if result.returncode != 0:
        sys.stderr.write(result.stdout + result.stderr)
        raise SystemExit(f"provisioning failed applying {path}")


def _drop_database(user: str, password: str, database: str) -> None:
    """Remove the application database so the next run starts from empty."""
    environment = dict(os.environ, PGPASSWORD=password)
    subprocess.run(
        [
            "psql", "--no-psqlrc", "--quiet",
            "--set", "ON_ERROR_STOP=1",
            "--dbname", MAINTENANCE_DATABASE,
            "--username", user,
            "--command", f'DROP DATABASE IF EXISTS "{database}" WITH (FORCE)',
        ],
        env=environment,
        capture_output=True,
        text=True,
        check=True,
    )


def _scripts(directory: pathlib.Path) -> list[pathlib.Path]:
    """The .sql files of one directory, in lexical order.

    sorted() over the file names is the whole ordering rule. The numeric
    prefixes exist so that lexical order is also the dependency order a reader
    would guess.
    """
    if not directory.is_dir():
        raise SystemExit(f"missing SQL directory: {directory}")
    return sorted(directory.glob("*.sql"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--sql", type=pathlib.Path, default=pathlib.Path("sql"))
    parser.add_argument("--fixtures", type=pathlib.Path, default=pathlib.Path("fixtures"))
    parser.add_argument("--database", default=DEFAULT_DATABASE)
    parser.add_argument(
        "--recreate",
        action="store_true",
        help=(
            "drop the application database first. Section 3.4 puts"
            " reproducibility in re-provisioning rather than migration"
            " history, so rebuilding from empty is the supported path."
        ),
    )
    arguments = parser.parse_args(argv)

    superuser = os.environ.get("PGUSER", "postgres")
    superuser_password = os.environ.get("PGPASSWORD", "")
    # Read here so an unset variable fails immediately with a name, rather than
    # inside psql as an empty password. They are not passed on any command
    # line: the SQL reads them from the environment with `\getenv`, and the
    # loader below hands the provisioning one to psycopg directly.
    provisioning_password = os.environ["MVP_PROVISIONING_PASSWORD"]
    os.environ["MVP_RUNTIME_PASSWORD"]

    # Section 4.11: parse every file before opening a transaction. A file that
    # cannot be parsed must not reach a database that is half built.
    parsed = fixtures.read(arguments.fixtures)

    if arguments.recreate:
        _drop_database(superuser, superuser_password, arguments.database)

    for script in _scripts(arguments.sql / "cluster"):
        _psql(
            MAINTENANCE_DATABASE,
            superuser,
            superuser_password,
            script,
            {"database_name": arguments.database},
        )

    for script in _scripts(arguments.sql / "database"):
        _psql(arguments.database, PROVISIONING_ROLE, provisioning_password, script, {})

    # One transaction for the whole load. psycopg does not autocommit, so an
    # exception leaves the context manager without a commit and the rows are
    # rolled back: Section 4.11's "either loads every row of every file or
    # leaves the database absent."
    with psycopg.connect(
        dbname=arguments.database,
        user=PROVISIONING_ROLE,
        password=provisioning_password,
        host=os.environ.get("PGHOST"),
        port=os.environ.get("PGPORT"),
    ) as connection:
        counts = loader.load(connection, parsed)

    print(
        "Provisioned: "
        + ", ".join(f"{table} {count}" for table, count in counts.items())
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
