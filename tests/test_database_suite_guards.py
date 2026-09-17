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

import unittest

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


if __name__ == "__main__":
    unittest.main(verbosity=2)
