"""No secret reaches the psql command line.

Review finding N3: argv is readable by any process on the host through `ps`
or /proc/<pid>/cmdline for as long as the process runs. On the CI runner the
passwords are job-scoped throwaways, but `sql/cluster/000_roles.sql` is
written to be re-runnable locally, and a developer's password would leak the
same way.

The command is built by a pure function so this can be asserted without a
database, which also means it runs in the agent loop's manifest rather than
only in the CI job that needs a server.
"""

import importlib
import pathlib
import sys
import unittest
from unittest import mock

from evidence_first_rag.db import commands

SECRET = "SAMPLE_PASSWORD_THAT_MUST_NOT_APPEAR"


class TheCommandCarriesNoSecret(unittest.TestCase):
    def command(self, variables=None):
        return commands.psql_command(
            "mvp",
            "mvp_provisioning",
            pathlib.Path("sql/cluster/000_roles.sql"),
            variables if variables is not None else {"database_name": "mvp"},
        )

    def test_no_argument_contains_a_password(self):
        # The whole argv, joined, is what `ps auxww` prints.
        self.assertNotIn(SECRET, " ".join(self.command()))

    def test_the_password_variable_names_are_absent_too(self):
        # Not just the value: a `--set provisioning_password=...` pair would
        # put the value beside the name, so the name's absence is the simpler
        # thing to assert and the harder one to satisfy by accident.
        joined = " ".join(self.command())
        for name in ("provisioning_password", "runtime_password", "PGPASSWORD"):
            with self.subTest(name=name):
                self.assertNotIn(name, joined)

    def test_the_database_name_is_still_passed_as_a_variable(self):
        # Not a secret, and the SQL needs it to build a second database for
        # the Section 6 repeatability comparison.
        self.assertIn("database_name=mvp", self.command())

    def test_it_stops_on_the_first_error(self):
        # Without this, psql reports an error and carries on, and a later file
        # would be applied to a database the earlier one failed to build.
        self.assertIn("ON_ERROR_STOP=1", self.command())

    def test_a_variable_a_caller_passes_still_reaches_argv(self):
        # The guarantee is about what provisioning puts there, not a promise
        # that the function sanitises anything. If a later caller passed a
        # secret it would leak, and this test says so out loud rather than
        # letting the file imply a protection it does not provide.
        self.assertIn(
            f"leaked={SECRET}", self.command({"leaked": SECRET})
        )


class TheRolesScriptReadsItsPasswordsFromTheEnvironment(unittest.TestCase):
    def test_it_uses_getenv_for_both_roles(self):
        text = pathlib.Path("sql/cluster/000_roles.sql").read_text(encoding="utf-8")
        self.assertIn("\\getenv provisioning_password MVP_PROVISIONING_PASSWORD", text)
        self.assertIn("\\getenv runtime_password MVP_RUNTIME_PASSWORD", text)

    def test_no_sql_file_contains_a_literal_password(self):
        # The scripts are committed and inspectable; a password in one would
        # be a credential in the repository, which AGENTS.md forbids outright.
        for path in sorted(pathlib.Path("sql").rglob("*.sql")):
            with self.subTest(path=str(path)):
                text = path.read_text(encoding="utf-8")
                self.assertNotIn("PASSWORD '", text)
                self.assertNotIn('PASSWORD "', text)


if __name__ == "__main__":
    unittest.main(verbosity=2)


class ThisSuiteRunsWithoutTheDriver(unittest.TestCase):
    """The repository-checks job installs neither the package nor psycopg.

    It runs `unittest discover --start-directory tests`, so anything under
    tests/ has to import with the driver absent. This is the guard for that:
    an earlier revision of this file imported provision.py, which imports
    psycopg at module level, and CI failed on the import rather than on
    anything the tests assert. It passed locally only because a developer who
    had run `pip install -e .` had psycopg present.

    Blocking a module by binding its name to None in sys.modules is the
    documented way to make `import` raise, and reproduces the CI condition
    exactly rather than approximating it.
    """

    DRIVER_FREE = (
        "evidence_first_rag.db.commands",
        "evidence_first_rag.db.fixtures",
    )

    def test_the_modules_tests_import_need_no_psycopg(self):
        for name in self.DRIVER_FREE:
            with self.subTest(module=name):
                with mock.patch.dict(sys.modules):
                    for loaded in [m for m in sys.modules if m.startswith("evidence_first_rag")]:
                        del sys.modules[loaded]
                    sys.modules["psycopg"] = None
                    module = importlib.import_module(name)
                    self.assertIsNotNone(module)

    def test_the_guard_itself_works(self):
        # If blocking psycopg stopped raising, the test above would pass for
        # the wrong reason and the next import of a driver-using module from
        # tests/ would reach CI unnoticed.
        with mock.patch.dict(sys.modules):
            for loaded in [m for m in sys.modules if m.startswith("evidence_first_rag")]:
                del sys.modules[loaded]
            sys.modules["psycopg"] = None
            with self.assertRaises(ImportError):
                importlib.import_module("evidence_first_rag.db.provision")
