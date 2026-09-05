"""Section 4.6 revalidation, and the five request-level fixture cases.

`FX-108` to `FX-112` are registered in Section 8.1 as properties of a request
or of the adapter rather than of the database, which is why they land in this
slice. Each one is a way a proposal can be wrong, and each has a Section 5
status the contract fixes for it.

The one that matters most is `FX-112`. The others describe a proposal that is
obviously malformed; that one describes a proposal that is *well formed and
false* -- a plausible identifier the request never contained. Nothing
downstream can tell it from a correct one, because the database will happily
return real facts about it.
"""

import unittest

from evidence_first_rag import (
    LimitationKind,
    OPENS_NO_CONNECTION,
    ProducingLayer,
    Status,
    UNSUPPORTED_ROUTE,
)
from evidence_first_rag.adapter import Proposal, answer, refused, revalidate
from evidence_first_rag.runtime import Request, Runtime
from evidence_first_rag.runtime.request import Refusal

from .runtime_support import BASE, FakeDatabase, candidate_row, message_row

SCOPE_TEXT = (
    "SAMPLE_PROJECT_ALPHA SAMPLE_REV_A SAMPLE_NET_POWERTRAIN SAMPLE_SNAP_BASE"
)
REQUEST = f"what are the facts for SAMPLE_MSG_ENGINE_STATUS in {SCOPE_TEXT}"
ARGUMENTS = BASE | {"message_key": "SAMPLE_MSG_ENGINE_STATUS"}


def runtime(rows=None):
    database = FakeDatabase(rows or {})
    return Runtime(database=database, fixture_provenance=("fixtures/",)), database


def refusal_from(proposal, text=REQUEST):
    with unittest.TestCase().assertRaises(Refusal):
        revalidate(proposal, text)


class ACleanProposalPassesThrough(unittest.TestCase):
    def test_it_becomes_the_request_the_runtime_executes(self):
        request = revalidate(Proposal(route="message_facts", arguments=ARGUMENTS), REQUEST)
        self.assertIsInstance(request, Request)
        self.assertEqual(request.route, "message_facts")

    def test_the_whole_path_reaches_a_success(self):
        engine, database = runtime(
            {
                "TPL_SNAPSHOT_CANDIDATES_V1": (candidate_row(),),
                "TPL_MESSAGE_FACTS_V1": (message_row(),),
            }
        )
        result = answer(engine, Proposal(route="message_facts", arguments=ARGUMENTS), REQUEST)
        self.assertIs(result.status, Status.SUCCESS)
        self.assertEqual(database.sessions, 1)


class TheFiveRequestLevelFixtures(unittest.TestCase):
    def outcome(self, proposal, text=REQUEST):
        engine, database = runtime()
        result = answer(engine, proposal, text)
        return result, database

    def test_fx_108_a_request_outside_the_three_routes(self):
        result, database = self.outcome(Proposal(route="delete_everything", arguments={}))
        self.assertIs(result.status, Status.UNSUPPORTED)
        self.assertIs(result.source_trace.producing_layer, ProducingLayer.RUNTIME)
        self.assertEqual(database.sessions, 0)

    def test_fx_108_the_adapters_own_literal_records_the_adapter(self):
        result, _ = self.outcome(Proposal(route=UNSUPPORTED_ROUTE, arguments={}))
        self.assertIs(result.status, Status.UNSUPPORTED)
        self.assertIs(result.source_trace.producing_layer, ProducingLayer.ADAPTER)

    def test_fx_109_a_parameter_outside_the_route_allowlist(self):
        result, database = self.outcome(
            Proposal(
                route="message_facts",
                arguments=ARGUMENTS | {"signal_key": "SAMPLE_SIG_ENGINE_SPEED"},
            ),
            f"{REQUEST} SAMPLE_SIG_ENGINE_SPEED",
        )
        self.assertIs(result.status, Status.INVALID_REQUEST)
        self.assertEqual(database.sessions, 0)

    def test_fx_110_a_contradictory_scope(self):
        result, database = self.outcome(
            Proposal(
                route="message_facts",
                arguments=ARGUMENTS | {"revision_label": ["SAMPLE_REV_A", "SAMPLE_REV_B"]},
            ),
            f"{REQUEST} SAMPLE_REV_B",
        )
        self.assertIs(result.status, Status.INVALID_REQUEST)
        self.assertEqual(database.sessions, 0)

    def test_fx_111_a_route_with_no_canonical_reference_formable(self):
        result, database = self.outcome(Proposal(route="message_facts", arguments=BASE))
        self.assertIs(result.status, Status.NEEDS_ENTITY_DISCOVERY)
        self.assertEqual(database.sessions, 0)
        self.assertTrue(
            any(
                limitation.kind is LimitationKind.ENTITY_DISCOVERY_NOT_IMPLEMENTED
                for limitation in result.limitations
            )
        )

    def test_fx_112_an_argument_value_absent_from_the_request(self):
        # The dangerous one. Everything about this proposal is well formed --
        # the route exists, the names are allowed, the scope is complete --
        # and the message key is one the user never wrote.
        result, database = self.outcome(
            Proposal(
                route="message_facts",
                arguments=ARGUMENTS | {"message_key": "SAMPLE_MSG_INVENTED"},
            )
        )
        self.assertIs(result.status, Status.INVALID_REQUEST)
        self.assertEqual(database.sessions, 0)

    def test_every_one_of_them_opens_no_connection(self):
        for status, proposal, text in (
            (Status.UNSUPPORTED, Proposal(route="nope"), REQUEST),
            (
                Status.INVALID_REQUEST,
                Proposal(route="message_facts", arguments={"nonsense": "x"}),
                f"{REQUEST} x",
            ),
            (
                Status.NEEDS_ENTITY_DISCOVERY,
                Proposal(route="message_facts", arguments=BASE),
                REQUEST,
            ),
        ):
            with self.subTest(status=status.value):
                result, database = self.outcome(proposal, text)
                self.assertIs(result.status, status)
                self.assertIn(status, OPENS_NO_CONNECTION)
                self.assertEqual(database.sessions, 0)
                self.assertFalse(
                    result.evidence_bundle.read_only_safeguards.connection_opened
                )


class NoInventedValueSurvives(unittest.TestCase):
    """Section 4.6: "may extract only values explicitly present in the request"."""

    def test_each_scope_dimension_is_checked_not_just_the_lookup_key(self):
        for dimension in BASE:
            with self.subTest(dimension=dimension):
                refusal_from(
                    Proposal(
                        route="message_facts",
                        arguments=ARGUMENTS | {dimension: "SAMPLE_INVENTED"},
                    )
                )

    def test_a_rewrite_is_not_an_extraction(self):
        # Charter Section 9's Milestone 2 gate: "explicit canonical entity
        # references are preserved rather than rewritten". A case-folded copy
        # of a value in the request is a rewrite, and Section 6 makes
        # comparison byte-exact everywhere else in this contract.
        lowered = REQUEST.lower()
        refusal_from(Proposal(route="message_facts", arguments=ARGUMENTS), lowered)

    def test_a_value_the_request_does_contain_is_accepted(self):
        # The other half: the check must not be so strict that nothing passes.
        revalidate(Proposal(route="message_facts", arguments=ARGUMENTS), REQUEST)

    def test_request_text_that_is_not_a_string_is_refused(self):
        for text in (None, 42, ["a"]):
            with self.subTest(text=text):
                refusal_from(Proposal(route="message_facts", arguments=ARGUMENTS), text)

    def test_an_empty_proposal_needs_entity_discovery_rather_than_passing(self):
        with self.assertRaises(Refusal) as raised:
            revalidate(Proposal(route="message_facts", arguments={}), REQUEST)
        self.assertIs(raised.exception.status, Status.NEEDS_ENTITY_DISCOVERY)


class TheAdaptersRefusalEvidenceMatchesTheRuntimes(unittest.TestCase):
    """`refused` builds a Result in the adapter layer, because the runtime has
    no request text and no proposal to refuse. This is what stops the two
    drifting: for a refusal both layers can see, they must produce the same
    evidence."""

    def test_they_agree_field_for_field(self):
        engine, _ = runtime()
        for proposal in (
            Proposal(route="not_a_route", arguments={}),
            Proposal(route="message_facts", arguments={"nonsense": "x"}),
            Proposal(route="message_facts", arguments=BASE),
        ):
            with self.subTest(route=proposal.route):
                through_adapter = answer(engine, proposal, f"{REQUEST} x")
                through_runtime = engine.execute(
                    Request(route=proposal.route, arguments=proposal.arguments)
                )
                self.assertEqual(through_adapter, through_runtime)


if __name__ == "__main__":
    unittest.main(verbosity=2)
