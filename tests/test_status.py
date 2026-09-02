"""Section 5: the status set is closed, and three families open no connection."""

import unittest

from evidence_first_rag import OPENS_NO_CONNECTION, Status

# Section 5's table, transcribed. Written out rather than derived from the
# enum so that a member removed from the enum fails here instead of quietly
# shrinking what the test checks.
SECTION_5_STATUSES = (
    "success",
    "not_found",
    "coverage_gap",
    "unsupported",
    "ambiguous",
    "invalid_request",
    "needs_entity_discovery",
)


class TheStatusSetIsClosed(unittest.TestCase):
    def test_the_seven_families_are_exactly_section_5s(self):
        self.assertEqual(
            sorted(status.value for status in Status), sorted(SECTION_5_STATUSES)
        )

    def test_an_unlisted_status_cannot_be_constructed(self):
        for candidate in ("partial_success", "error", "", "SUCCESS"):
            with self.subTest(candidate=candidate):
                with self.assertRaises(ValueError):
                    Status(candidate)


class TheNoConnectionFamilies(unittest.TestCase):
    def test_section_5_names_exactly_these_three(self):
        self.assertEqual(
            OPENS_NO_CONNECTION,
            frozenset(
                {
                    Status.UNSUPPORTED,
                    Status.INVALID_REQUEST,
                    Status.NEEDS_ENTITY_DISCOVERY,
                }
            ),
        )

    def test_the_families_that_may_open_one_are_not_in_it(self):
        for status in (
            Status.SUCCESS,
            Status.NOT_FOUND,
            Status.COVERAGE_GAP,
            Status.AMBIGUOUS,
        ):
            with self.subTest(status=status):
                self.assertNotIn(status, OPENS_NO_CONNECTION)


if __name__ == "__main__":
    unittest.main(verbosity=2)
