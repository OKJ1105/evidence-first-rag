"""Section 4.7's baseline: a control group with three prohibitions on it."""

import unittest

from evidence_first_rag import UNSUPPORTED_ROUTE
from evidence_first_rag.adapter import Baseline, CuratedEntry, normalize

TEXT = "facts for SAMPLE_MSG_ENGINE_STATUS"
ENTRY = CuratedEntry(
    text=TEXT, route="message_facts", arguments={"message_key": "SAMPLE_MSG_ENGINE_STATUS"}
)


class ExactMatchMeansExact(unittest.TestCase):
    def test_a_registered_request_resolves_to_its_entry(self):
        proposal = Baseline([ENTRY]).resolve(TEXT)
        self.assertEqual(proposal.route, "message_facts")
        self.assertEqual(
            dict(proposal.arguments), {"message_key": "SAMPLE_MSG_ENGINE_STATUS"}
        )

    def test_anything_else_is_unsupported(self):
        baseline = Baseline([ENTRY])
        for miss in (
            "facts for SAMPLE_MSG_OTHER",
            "facts for SAMPLE_MSG_ENGINE_STATUS please",
            "",
            "SAMPLE_MSG_ENGINE_STATUS",
        ):
            with self.subTest(text=miss):
                self.assertEqual(baseline.resolve(miss).route, UNSUPPORTED_ROUTE)

    def test_whitespace_is_normalized_and_case_is_not(self):
        # Section 6 fixes byte-exact comparison with no case folding for every
        # other comparison in this contract. A baseline that folded case would
        # be more permissive than the runtime it is a control for, which would
        # flatter it on the axis the comparison measures.
        baseline = Baseline([ENTRY])
        self.assertEqual(
            baseline.resolve("  facts   for  SAMPLE_MSG_ENGINE_STATUS ").route,
            "message_facts",
        )
        self.assertEqual(baseline.resolve(TEXT.lower()).route, UNSUPPORTED_ROUTE)

    def test_normalize_collapses_whitespace_only(self):
        self.assertEqual(normalize("  a   b \n c "), "a b c")
        self.assertEqual(normalize("A"), "A")

    def test_there_is_no_ranking_and_no_threshold(self):
        # The baseline has no near-miss behaviour to tune. Its severity is the
        # point: it is the honest floor, not a competitor.
        self.assertFalse(hasattr(Baseline([ENTRY]), "rank"))
        self.assertFalse(hasattr(Baseline([ENTRY]), "threshold"))


class TheTableIsRegisteredData(unittest.TestCase):
    def test_an_unregistered_table_resolves_nothing(self):
        # Contract Section 9 leaves the curated set open, owned by the
        # contract and registered before the Milestone 2 comparison. An empty
        # table is the correct behaviour of a baseline whose entries have not
        # been registered, not a placeholder.
        self.assertEqual(len(Baseline()), 0)
        self.assertEqual(Baseline().resolve(TEXT).route, UNSUPPORTED_ROUTE)

    def test_two_entries_that_normalize_alike_are_refused(self):
        with self.assertRaises(ValueError):
            Baseline([ENTRY, CuratedEntry(text=f"  {TEXT}  ", route="signal_facts")])

    def test_an_entry_needs_text_and_a_route(self):
        for bad in ({"text": "", "route": "message_facts"}, {"text": TEXT, "route": ""}):
            with self.subTest(**bad):
                with self.assertRaises(ValueError):
                    CuratedEntry(**bad)

    def test_an_entrys_arguments_cannot_be_edited_through_the_caller(self):
        arguments = {"message_key": "SAMPLE_MSG_ENGINE_STATUS"}
        entry = CuratedEntry(text=TEXT, route="message_facts", arguments=arguments)
        arguments["message_key"] = "SAMPLE_MSG_OTHER"
        self.assertEqual(entry.arguments["message_key"], "SAMPLE_MSG_ENGINE_STATUS")


if __name__ == "__main__":
    unittest.main(verbosity=2)
