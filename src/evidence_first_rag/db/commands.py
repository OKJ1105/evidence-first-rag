"""How provisioning invokes `psql`. No driver, no connection, no database.

Separate from provision.py on purpose. Section 3.4's provisioning path is
version-controlled SQL applied by psql, and what does or does not appear on
that command line is a property worth asserting without a PostgreSQL server
or the psycopg driver present — which is what lets the assertion run in the
agent loop's checks manifest rather than only in the CI job that has both.
"""

import pathlib


def psql_command(
    database: str, user: str, path: pathlib.Path, variables: dict
) -> list[str]:
    """Build the psql argv for one SQL file.

    Nothing secret may appear here: argv is readable by any process on the
    host through `ps` or /proc/<pid>/cmdline for as long as psql runs. The
    role passwords travel in the environment instead, and the SQL reads them
    with `\\getenv`; only `database_name`, which is not a secret, is passed as
    a variable.

    This function does not sanitise what it is given. A caller that passed a
    secret in `variables` would leak it, and tests/test_db_provision_command.py
    says so rather than implying a protection that is not here. The guarantee
    is about what provisioning puts on the command line.

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
