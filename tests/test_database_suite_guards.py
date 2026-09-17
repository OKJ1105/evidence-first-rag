"""`tests_database/guards.py`: what a database suite does when its dependency
is missing.

Here rather than in `tests_database/` because that is the point of the module.
The decision runs in `setUpModule`, before any test in that tree exists to
assert it, and in a job this tree's checks do not reach. Split out, it needs
neither a driver nor a database, so all three branches are executed in every
job -- including the one that installs nothing.

What it protects: `tests_database/test_api_workflows.py` carries thirteen
registered `api-v0.1` Section 8.1 rows, `WF-003` among them, and every one of
them is reported by a single install line in a workflow file. Drop the extra
from it and the module skips; a skip is green, and nothing says the rows
stopped running. That is the failure #101 put the `adapter-checks` job in the
tree to prevent, one job over.
"""

import ast
import os
import pathlib
import unittest
import unittest.mock

from tests_database.guards import missing_dependency


class WhenTheDependencyIsInstalled(unittest.TestCase):
    def test_nothing_is_raised_and_the_suite_runs(self):
        for provisioned in (True, False):
            with self.subTest(provisioned=provisioned):
                self.assertIsNone(
                    missing_dependency(installed=True, provisioned=provisioned)
                )


class WhenItIsMissing(unittest.TestCase):
    """The discriminator is the database environment, not the dependency."""

    def test_no_database_is_a_skip(self):
        # A checkout that provisioned nothing was never going to run these
        # rows, so reporting them as skipped is what is true.
        outcome = missing_dependency(installed=False, provisioned=False)
        self.assertIsInstance(outcome, unittest.SkipTest)

    def test_a_provisioned_database_is_a_failure(self):
        # The case the module exists for. A job that stood PostgreSQL up meant
        # the rows to run; skipping there reports green for rows that never
        # executed.
        outcome = missing_dependency(installed=False, provisioned=True)
        self.assertIsInstance(outcome, RuntimeError)
        self.assertNotIsInstance(outcome, unittest.SkipTest)

    def test_the_two_outcomes_are_not_the_same_kind_of_thing(self):
        # A skip is green and a RuntimeError is red. If these ever became the
        # same type the guard would be decorative, and the tests above would
        # both still pass on an `isinstance` that happened to hold.
        skip = missing_dependency(installed=False, provisioned=False)
        failure = missing_dependency(installed=False, provisioned=True)
        self.assertNotIsInstance(skip, type(failure))
        self.assertNotIsInstance(failure, type(skip))


class WhatTheFailureSays(unittest.TestCase):
    """A red build has to tell whoever reads it what to do."""

    def setUp(self):
        self.detail = str(missing_dependency(installed=False, provisioned=True))

    def test_it_names_the_file_to_edit(self):
        self.assertIn(".github/workflows/repository-checks.yml", self.detail)

    def test_it_says_why_skipping_would_be_wrong(self):
        # Not "install the extra" alone: the reader has to see that the
        # alternative reports green for rows that did not run, or the obvious
        # fix looks like relaxing the guard.
        self.assertIn("never executed", self.detail)

    def test_it_names_no_credential_host_or_path_of_its_own(self):
        import pathlib
        import sys

        sys.path.insert(0, "scripts/checks")
        import scan_sensitive_strings

        failures = []
        scan_sensitive_strings.scan_text(
            self.detail, pathlib.Path("guard-detail.txt"), failures
        )
        self.assertEqual(failures, [])


class TheGuardIsWiredIn(unittest.TestCase):
    """That `setUpModule` applies the decision, asserted by reading it.

    The class above pins what `missing_dependency` decides. That is not the
    same as the guard being armed: change `provisioned=` to `False`, or raise
    only on a `SkipTest`, and every assertion above still passes while the
    thirteen Section 8.1 rows go quiet again -- the precise failure this exists
    to prevent.

    Read with `ast` rather than executed, for the reason the guard was split
    out in the first place: running `setUpModule` needs the extra and a
    database, and this has to hold in the job that installs neither. It is the
    idiom `tests/test_suite_layout.py` already uses over this tree.
    """

    @classmethod
    def setUpClass(cls):
        source = (
            pathlib.Path(__file__).resolve().parents[1]
            / "tests_database"
            / "test_api_workflows.py"
        ).read_text()
        module = ast.parse(source)
        cls.function = next(
            node
            for node in module.body
            if isinstance(node, ast.FunctionDef) and node.name == "setUpModule"
        )
        cls.call = next(
            node
            for node in ast.walk(cls.function)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "missing_dependency"
        )

    def keyword(self, name):
        return next(k for k in self.call.keywords if k.arg == name)

    def test_it_asks_the_guard_at_all(self):
        self.assertEqual(ast.unparse(self.call.func), "guards.missing_dependency")

    def test_installed_is_the_module_s_own_import_result(self):
        # Not a literal, and not something narrower: whether the dependency is
        # there is exactly what `HAS_API` records.
        self.assertEqual(ast.unparse(self.keyword("installed").value), "HAS_API")

    def test_provisioned_is_read_from_the_database_environment(self):
        # The discriminator. A literal here -- `False` above all -- disarms the
        # failure branch while leaving the call in place, which is the change
        # this test exists to catch.
        expression = ast.unparse(self.keyword("provisioned").value)
        self.assertIn("MVP_RUNTIME_PASSWORD", expression)
        self.assertNotIn("True", expression)
        self.assertNotIn("False", expression)

    def test_whatever_the_guard_returns_is_raised(self):
        # Unconditionally on a non-None value. Narrowing this to `SkipTest`
        # would keep all three branches correct and still never fail a job.
        raises = [n for n in ast.walk(self.function) if isinstance(n, ast.Raise)]
        self.assertEqual(len(raises), 1)
        guard = next(n for n in ast.walk(self.function) if isinstance(n, ast.If))
        self.assertEqual(ast.unparse(guard.test), "outcome is not None")
        self.assertEqual(ast.unparse(raises[0]), "raise outcome")

    def test_nothing_runs_before_the_guard_has_decided(self):
        """`support.build` provisions a database. Reaching it before the
        decision means a job doing the work it was about to be told it could
        not do -- and on the failure branch, doing it and then raising.

        Only the docstring is skipped. An earlier version of this test
        discarded every `ast.Expr`, which is what a bare `support.build(...)`
        call is, so it discarded exactly the statement it was written to catch:
        the mutation that provisions first survived it.
        """
        body = list(self.function.body)
        if (
            body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            body = body[1:]
        self.assertTrue(body, "setUpModule has no body beyond its docstring")
        self.assertIsInstance(
            body[0], ast.Assign, f"the first statement is {ast.unparse(body[0])!r}"
        )
        self.assertIn("missing_dependency", ast.unparse(body[0]))


try:
    import psycopg  # noqa: F401
    import fastapi  # noqa: F401

    from tests_database import test_api_workflows

    CAN_IMPORT_THE_SUITE = True
except ImportError:  # pragma: no cover - the extra-free job takes this path
    CAN_IMPORT_THE_SUITE = False


@unittest.skipUnless(CAN_IMPORT_THE_SUITE, "the database suite's imports are not installed")
class TheGuardRunsWhenSetUpModuleDoes(unittest.TestCase):
    """`setUpModule` executed, not read.

    `TheGuardIsWiredIn` reads the source, which is what works in the job that
    installs nothing. It cannot see anything the text does not say -- a
    `HAS_API` rebound between the import and the call, a `guards` shadowed by
    something else. This runs the function against a recorded stand-in, in the
    jobs whose imports allow it, so the two together cover reading and running.

    `support.build` is never reached: the stand-in returns an exception on both
    calls below, and `setUpModule` raises it. Nothing here provisions, drops or
    touches a database.
    """

    def drive(self, *, provisioned, returns):
        """Call `setUpModule` with the guard replaced, and report the call."""
        seen = {}

        def recorder(**keywords):
            seen.update(keywords)
            return returns

        environment = dict(os.environ)
        environment.pop("MVP_RUNTIME_PASSWORD", None)
        if provisioned:
            environment["MVP_RUNTIME_PASSWORD"] = "SAMPLE_NOT_A_REAL_VALUE"

        original = test_api_workflows.guards.missing_dependency
        test_api_workflows.guards.missing_dependency = recorder
        try:
            with unittest.mock.patch.dict(os.environ, environment, clear=True):
                raised = None
                try:
                    test_api_workflows.setUpModule()
                except BaseException as outcome:  # noqa: BLE001 - that is the assertion
                    raised = outcome
        finally:
            test_api_workflows.guards.missing_dependency = original
        return seen, raised

    def test_it_reports_whether_the_dependency_is_installed(self):
        seen, _ = self.drive(provisioned=False, returns=RuntimeError("SAMPLE_SENTINEL"))
        self.assertIn("installed", seen)
        self.assertIs(seen["installed"], test_api_workflows.HAS_API)

    def test_it_reports_the_database_environment_as_it_finds_it(self):
        # Both directions. A wiring that ignored the environment, or swapped
        # the two keywords, agrees with one of these and not the other.
        for provisioned in (True, False):
            with self.subTest(provisioned=provisioned):
                seen, _ = self.drive(
                    provisioned=provisioned, returns=RuntimeError("SAMPLE_SENTINEL")
                )
                self.assertIs(seen["provisioned"], provisioned)

    def test_whatever_the_guard_returns_reaches_the_caller(self):
        for returns in (RuntimeError("SAMPLE_SENTINEL"), unittest.SkipTest("SAMPLE_SENTINEL")):
            with self.subTest(kind=type(returns).__name__):
                _, raised = self.drive(provisioned=True, returns=returns)
                self.assertIs(raised, returns)

    def test_a_guard_that_permits_the_run_does_not_raise(self):
        # `None` is the third outcome, and the one that must not be confused
        # with the other two: it reaches `support.build`, which has no database
        # here, so it raises something that is not the sentinel.
        _, raised = self.drive(provisioned=True, returns=None)
        self.assertIsNotNone(raised, "setUpModule returned without provisioning")
        self.assertNotIsInstance(raised, unittest.SkipTest)
        self.assertNotIn("SAMPLE_SENTINEL", str(raised))


if __name__ == "__main__":
    unittest.main(verbosity=2)
