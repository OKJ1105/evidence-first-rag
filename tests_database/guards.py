"""What a database suite does when the thing it needs is not installed.

One function, no driver and no database, so the decision it makes can be
asserted from `tests/` in every job rather than only observed in the one job
that provisions PostgreSQL. A guard whose branches are never executed by a
test is a guard nobody has checked.
"""

import unittest


def missing_dependency(*, installed: bool, provisioned: bool) -> BaseException | None:
    """What to raise before a database suite runs, or `None` to run it.

    Three cases, and the middle one is the whole point:

    - **installed** -- nothing to raise; the suite runs.
    - **not installed, not provisioned** -- `SkipTest`. A checkout with no
      database environment was never going to run these rows, and saying so is
      honest.
    - **not installed, provisioned** -- `RuntimeError`. A job that stood up
      PostgreSQL meant the rows to run. Skipping there reports green for rows
      that never executed, which is exactly the failure #101 put the
      `adapter-checks` job in the tree to prevent.

    The discriminator is the **database environment**, not the dependency,
    because the dependency is what went missing and cannot testify about
    itself. Returned rather than raised so a caller decides where the traceback
    starts, and so a test can name the type without catching anything.
    """
    if installed:
        return None
    if provisioned:
        return RuntimeError(
            "this job provisioned a database, so its rows were meant to run,"
            " and the dependency they need is not installed. Skipping would"
            " report green for rows that never executed. Install the extra in"
            " the job that runs them, in .github/workflows/repository-checks.yml."
        )
    return unittest.SkipTest(
        "there is no database environment here; these rows are discharged by"
        " the job that provisions one"
    )
