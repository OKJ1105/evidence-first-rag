"""The `tests_stack` readiness gate, run rather than read.

`tests_stack/test_workflows.py` drives the surface over HTTP, and its guard
decides between "there is no stack" (skip) and "a stack was meant to be running"
(fail). A surface that is *starting* is neither, and `deploy.yml` reaches that
state: it restarts both apps onto a freshly pushed image and then runs those
rows, so a start-up slower than the platform's own answer would have failed the
rows and rolled a correct deploy back (#236 B2).

These cases run `await_health` against a recorded stand-in for `call`. Nothing
here opens a socket and nothing waits on a clock: the budget, the interval, the
pause and the clock are all passed in.
"""

import json
import os
import unittest
import unittest.mock

from tests_stack import test_workflows

# A JSON body's shape is all the gate looks at; `WF-013` is what asserts its
# contents, against a stack.
SERVING = (200, {"contracts": {}, "adapter_configured": False}, b"{}")


class TheReadinessGate(unittest.TestCase):
    """What `await_health` waits for, and what it refuses to wait for."""

    def setUp(self):
        self.original_url = test_workflows.BASE_URL
        test_workflows.BASE_URL = "http://127.0.0.1:1"
        self.slept = []

    def tearDown(self):
        test_workflows.BASE_URL = self.original_url

    def drive(self, answers, *, budget=60.0):
        """Run the gate over `answers`, one per attempt, on a clock that holds.

        The clock does not advance, so `budget=60.0` never runs out and the
        answers decide when the gate returns; `budget=0.0` runs out on the first
        answer that is not a serving one.
        """
        remaining = list(answers)

        def stand_in(path):
            self.assertEqual(path, "/v1/health")
            answer = remaining.pop(0)
            if isinstance(answer, BaseException):
                raise answer
            return answer

        original = test_workflows.call
        test_workflows.call = stand_in
        try:
            return test_workflows.await_health(
                budget=budget, interval=1, pause=self.slept.append, clock=lambda: 0.0
            )
        finally:
            test_workflows.call = original
            self.remaining = remaining

    def test_a_surface_that_is_not_serving_yet_is_waited_for(self):
        """The three answers a starting surface gives, none of them a stack that
        was never started."""
        document = self.drive(
            [
                ConnectionRefusedError("connection refused"),
                json.JSONDecodeError("Expecting value", "<html>503</html>", 0),
                (503, {"refusal": "SAMPLE"}, b"{}"),
                SERVING,
            ]
        )
        self.assertEqual(document, SERVING[1])
        self.assertEqual(self.remaining, [])
        self.assertEqual(self.slept, [1, 1, 1])

    def test_a_serving_surface_is_asked_once_and_not_slept_on(self):
        self.assertEqual(self.drive([SERVING]), SERVING[1])
        self.assertEqual(self.slept, [])

    def test_the_budget_ends_the_wait_with_its_own_message(self):
        """A start-up timeout has to be tellable from a row failing: the rows
        assert documents, and this raises before any of them runs."""
        with self.assertRaises(RuntimeError) as refused:
            self.drive([json.JSONDecodeError("Expecting value", "<html>503</html>", 0)], budget=0.0)
        message = str(refused.exception)
        self.assertIn(test_workflows.STACK_URL_VARIABLE, message)
        self.assertIn(test_workflows.BASE_URL, message)
        self.assertIn("not JSON", message)
        # Failing is the point: a skip here would be #101's green.
        self.assertNotIsInstance(refused.exception, unittest.SkipTest)
        self.assertEqual(self.slept, [])

    def test_the_budget_is_long_enough_to_cover_a_platform_start(self):
        """A budget of a few seconds would leave the deployed run depending on
        platform timing again; the interval bounds how often it asks."""
        self.assertGreaterEqual(test_workflows.READY_BUDGET_SECONDS, 300)
        self.assertGreater(test_workflows.READY_INTERVAL_SECONDS, 0)


class TheGuardUsesTheGate(unittest.TestCase):
    """That `setUpModule` waits, asserted by running it."""

    def setUp(self):
        self.original_url = test_workflows.BASE_URL

    def tearDown(self):
        test_workflows.BASE_URL = self.original_url

    def drive(self, environment):
        waited = []
        original = test_workflows.await_health
        test_workflows.await_health = lambda: waited.append(test_workflows.BASE_URL)
        try:
            with unittest.mock.patch.dict(os.environ, environment, clear=True):
                raised = None
                try:
                    test_workflows.setUpModule()
                except BaseException as outcome:  # noqa: BLE001 - that is the assertion
                    raised = outcome
        finally:
            test_workflows.await_health = original
        return waited, raised

    def test_a_configured_stack_is_waited_for_at_the_url_it_names(self):
        waited, raised = self.drive({test_workflows.STACK_URL_VARIABLE: "http://127.0.0.1:8000/"})
        self.assertIsNone(raised)
        self.assertEqual(waited, ["http://127.0.0.1:8000"])

    def test_no_configured_stack_is_still_a_skip_and_waits_for_nothing(self):
        waited, raised = self.drive({})
        self.assertIsInstance(raised, unittest.SkipTest)
        self.assertEqual(waited, [])


if __name__ == "__main__":
    unittest.main()
