"""Section 4.5 validation, and the three statuses that open no connection.

Section 4.5: "Route validation runs before any database access." Every test
here asserts the outcome *and* that the database was never asked for a
session, because a runtime that produced the right status after connecting
would satisfy Section 5 and break Section 4.5.
"""

import unittest

from evidence_first_rag import (
    LimitationKind,
    OPENS_NO_CONNECTION,
    ProducingLayer,
    Route,
    Status,
    UNSUPPORTED_ROUTE,
)
from evidence_first_rag.runtime import Request, Runtime
from evidence_first_rag.runtime.request import (
    ROUTE_TEMPLATE,
    allowed_parameters,
    required_lookup_keys,
)

from .runtime_support import BASE, FakeDatabase

SCOPE = tuple(BASE)
MESSAGE = BASE | {"message_key": "SAMPLE_MSG_ENGINE_STATUS"}
SIGNAL = MESSAGE | {"signal_key": "SAMPLE_SIG_ENGINE_SPEED"}


def answer(request, rows=None):
    database = FakeDatabase(rows)
    return database, Runtime(database=database).execute(request)


class TheRoutesAreSection45s(unittest.TestCase):
    def test_there_are_exactly_three(self):
        self.assertEqual(
            [route.value for route in Route],
            ["message_facts", "signal_facts", "signal_mapping"],
        )

    def test_each_route_dispatches_to_the_template_section_4_5_names(self):
        self.assertEqual(
            {route.value: name for route, name in ROUTE_TEMPLATE.items()},
            {
                "message_facts": "TPL_MESSAGE_FACTS_V1",
                "signal_facts": "TPL_SIGNAL_FACTS_V1",
                "signal_mapping": "TPL_SIGNAL_MAPPING_V1",
            },
        )

    def test_the_allowlists_are_the_arguments_section_4_5_requires(self):
        # Derived from the registered template rather than restated in the
        # runtime, so this is the test that stops a template change from
        # widening a route. Section 4.5: message_facts takes a canonical
        # message reference; signal_facts takes a canonical signal reference;
        # signal_mapping takes the source endpoint's signal reference plus an
        # optional `mapping_key`.
        self.assertEqual(allowed_parameters(Route.MESSAGE_FACTS), SCOPE + ("message_key",))
        self.assertEqual(
            allowed_parameters(Route.SIGNAL_FACTS), SCOPE + ("message_key", "signal_key")
        )
        self.assertEqual(
            allowed_parameters(Route.SIGNAL_MAPPING),
            SCOPE + ("message_key", "signal_key", "mapping_key"),
        )

    def test_the_lookup_keys_are_the_required_arguments_that_are_not_scope(self):
        self.assertEqual(required_lookup_keys(Route.MESSAGE_FACTS), ("message_key",))
        self.assertEqual(
            required_lookup_keys(Route.SIGNAL_FACTS), ("message_key", "signal_key")
        )
        self.assertEqual(
            required_lookup_keys(Route.SIGNAL_MAPPING), ("message_key", "signal_key")
        )


class AnUnknownRouteIsUnsupported(unittest.TestCase):
    def test_it_records_the_runtime_as_the_producing_layer(self):
        database, result = answer(Request(route="message_fact", arguments=MESSAGE))
        self.assertIs(result.status, Status.UNSUPPORTED)
        self.assertIs(result.source_trace.producing_layer, ProducingLayer.RUNTIME)
        self.assertEqual(database.sessions, 0)

    def test_the_adapters_own_literal_records_the_adapter(self):
        # Section 4.6 lets the adapter emit `unsupported` itself, and Section 5
        # requires the trace to say which layer produced the outcome. The two
        # cases are different facts about where the request stopped.
        _, result = answer(Request(route=UNSUPPORTED_ROUTE))
        self.assertIs(result.status, Status.UNSUPPORTED)
        self.assertIs(result.source_trace.producing_layer, ProducingLayer.ADAPTER)

    def test_a_route_object_is_accepted_without_a_round_trip(self):
        _, result = answer(
            Request(route=Route.MESSAGE_FACTS, arguments=MESSAGE),
            {"TPL_SNAPSHOT_CANDIDATES_V1": ()},
        )
        self.assertIs(result.status, Status.COVERAGE_GAP)

    def test_the_bundle_records_the_route_that_was_asked_for(self):
        _, result = answer(Request(route="message_fact"))
        self.assertEqual(result.evidence_bundle.route, "message_fact")

    def test_an_unusable_route_is_recorded_as_section_4_6s_literal(self):
        # Section 7 requires a `route` on every result and the bundle refuses
        # an empty one, so a route that is not text still needs a name. The
        # fallback is the contract's own word for "no route applies", not a
        # token this runtime invented.
        for unusable in (None, 42, ""):
            with self.subTest(route=unusable):
                _, result = answer(Request(route=unusable))
                self.assertEqual(result.evidence_bundle.route, UNSUPPORTED_ROUTE)


class AMalformedRequestIsInvalid(unittest.TestCase):
    def refusal(self, **request):
        database, result = answer(Request(**request))
        self.assertEqual(database.sessions, 0)
        return result

    def test_a_parameter_outside_the_route_allowlist(self):
        result = self.refusal(
            route="message_facts", arguments=MESSAGE | {"signal_key": "SAMPLE_SIG_X"}
        )
        self.assertIs(result.status, Status.INVALID_REQUEST)

    def test_arguments_that_are_not_a_mapping(self):
        result = self.refusal(route="message_facts", arguments=["project_code"])
        self.assertIs(result.status, Status.INVALID_REQUEST)

    def test_an_argument_name_that_is_not_text(self):
        result = self.refusal(route="message_facts", arguments={1: "SAMPLE"})
        self.assertIs(result.status, Status.INVALID_REQUEST)

    def test_a_value_that_is_not_text(self):
        result = self.refusal(
            route="message_facts", arguments=MESSAGE | {"message_key": 256}
        )
        self.assertIs(result.status, Status.INVALID_REQUEST)

    def test_an_empty_value(self):
        result = self.refusal(route="message_facts", arguments=MESSAGE | {"message_key": ""})
        self.assertIs(result.status, Status.INVALID_REQUEST)

    def test_a_dimension_carrying_two_values_is_contradictory(self):
        # Section 8.1 registers `FX-110` as "two different `revision_label`
        # values". A mapping holds one value per name, so the second value has
        # to arrive inside the first, and this is the shape it takes.
        result = self.refusal(
            route="message_facts",
            arguments=MESSAGE | {"revision_label": ["SAMPLE_REV_A", "SAMPLE_REV_B"]},
        )
        self.assertIs(result.status, Status.INVALID_REQUEST)



class AMissingLookupKeyNeedsEntityDiscovery(unittest.TestCase):
    def test_a_message_facts_request_without_a_message_key(self):
        database, result = answer(Request(route="message_facts", arguments=BASE))
        self.assertIs(result.status, Status.NEEDS_ENTITY_DISCOVERY)
        self.assertEqual(database.sessions, 0)

    def test_a_signal_facts_request_without_a_signal_key(self):
        _, result = answer(Request(route="signal_facts", arguments=MESSAGE))
        self.assertIs(result.status, Status.NEEDS_ENTITY_DISCOVERY)

    def test_it_states_that_entity_discovery_is_not_implemented(self):
        # Section 7 fixes what the entry has to say, not merely that there is
        # one.
        _, result = answer(Request(route="message_facts", arguments=BASE))
        entry = next(
            limitation
            for limitation in result.limitations
            if limitation.kind is LimitationKind.ENTITY_DISCOVERY_NOT_IMPLEMENTED
        )
        self.assertIn("Entity Discovery is not implemented in v0.1", entry.detail)

    def test_an_omitted_scope_dimension_is_not_this_outcome(self):
        # Section 4.2 governs a missing scope dimension and sends it to
        # `ambiguous`, so the split between the two rules is which argument is
        # missing, not that something is.
        incomplete = {k: v for k, v in MESSAGE.items() if k != "snapshot_label"}
        _, result = answer(
            Request(route="message_facts", arguments=incomplete),
            {"TPL_SNAPSHOT_CANDIDATES_V1": (dict(BASE),)},
        )
        self.assertIs(result.status, Status.AMBIGUOUS)


class EveryRefusalCarriesItsEvidence(unittest.TestCase):
    """Section 5: all three structures on every outcome, negatives included."""

    def cases(self):
        return {
            Status.UNSUPPORTED: Request(route="message_fact"),
            Status.INVALID_REQUEST: Request(route="message_facts", arguments={"x": "1"}),
            Status.NEEDS_ENTITY_DISCOVERY: Request(
                route="message_facts", arguments=BASE
            ),
        }

    def test_each_of_the_three_records_that_no_connection_was_opened(self):
        for status, request in self.cases().items():
            with self.subTest(status=status.value):
                database, result = answer(request)
                self.assertIs(result.status, status)
                self.assertIn(status, OPENS_NO_CONNECTION)
                self.assertEqual(database.sessions, 0)
                safeguards = result.evidence_bundle.read_only_safeguards
                self.assertFalse(safeguards.connection_opened)
                self.assertFalse(safeguards.read_only_transaction)
                self.assertEqual(safeguards.role_name, "")

    def test_each_of_the_three_reports_the_explicit_empty_values(self):
        for status, request in self.cases().items():
            with self.subTest(status=status.value):
                bundle = answer(request)[1].evidence_bundle
                self.assertEqual(bundle.template_name, "")
                self.assertEqual(bundle.template_version, "")
                self.assertIsNone(bundle.resolved_scope)
                self.assertEqual(bundle.row_count, 0)

    def test_a_rejected_proposal_is_never_reported_as_bound(self):
        # Section 7: the arguments an adapter proposed and revalidation
        # rejected "are never reported as such", because recording them "would
        # present a rejected proposal as a fact the runtime acted on".
        _, result = answer(
            Request(route="message_facts", arguments=MESSAGE | {"signal_key": "SAMPLE"})
        )
        self.assertIs(result.status, Status.INVALID_REQUEST)
        self.assertEqual(dict(result.evidence_bundle.bound_parameters), {})

    def test_each_of_the_three_names_this_contract(self):
        for status, request in self.cases().items():
            with self.subTest(status=status.value):
                bundle = answer(request)[1].evidence_bundle
                self.assertEqual(bundle.contract_identifier, "mvp-v0.1")
                self.assertEqual(bundle.collation, "C")

    def test_the_fixture_provenance_it_was_told_reaches_every_trace(self):
        runtime = Runtime(
            database=FakeDatabase(), fixture_provenance=("fixtures/source_snapshot.jsonl",)
        )
        result = runtime.execute(Request(route="message_fact"))
        self.assertEqual(
            result.source_trace.fixture_provenance, ("fixtures/source_snapshot.jsonl",)
        )

    def test_a_runtime_told_nothing_claims_no_provenance(self):
        _, result = answer(Request(route="message_fact"))
        self.assertEqual(result.source_trace.fixture_provenance, ())


if __name__ == "__main__":
    unittest.main(verbosity=2)
