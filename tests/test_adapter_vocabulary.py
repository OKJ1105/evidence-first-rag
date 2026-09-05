"""Section 4.6: what the adapter is given, and what it must never be given.

"The adapter receives the user request and the route, argument, and
scope-vocabulary metadata required to fill the schema. It receives no database
rows, no fixture contents, and no evidence bundle, per Charter Section 3.3."

Issue #16 says why this needs a test rather than a review: "otherwise 'the
model only picks a route' becomes untrue by accident as the payload grows."
So the payload is built and then searched for every identifier the fixtures
contain.
"""

import json
import pathlib
import re
import unittest

from evidence_first_rag import SCOPE_DIMENSIONS, UNSUPPORTED_ROUTE, Route
from evidence_first_rag.adapter import vocabulary
from evidence_first_rag.runtime.request import allowed_parameters

FIXTURES = pathlib.Path(__file__).resolve().parent.parent / "fixtures"
SAMPLE = re.compile(r"SAMPLE_[A-Za-z0-9_]+")


def everything_the_adapter_is_told() -> str:
    return vocabulary.instructions() + vocabulary.as_text(vocabulary.payload()) + json.dumps(
        vocabulary.schema()
    )


class TheCallCarriesNoDatabaseContent(unittest.TestCase):
    def fixture_identifiers(self):
        found = set()
        for path in FIXTURES.glob("*.jsonl"):
            found.update(SAMPLE.findall(path.read_text()))
        return found

    def test_no_fixture_identifier_appears_anywhere_in_the_payload(self):
        told = everything_the_adapter_is_told()
        leaked = sorted(name for name in self.fixture_identifiers() if name in told)
        self.assertEqual(leaked, [])

    def test_the_search_would_notice_one(self):
        # Probed, because a scan over an empty set passes quietly.
        self.assertTrue(self.fixture_identifiers())
        self.assertIn(
            "SAMPLE_MSG_ENGINE_STATUS",
            self.fixture_identifiers(),
            "the fixtures no longer contain the identifier this probe uses",
        )

    def test_the_payload_names_no_scope_value_at_all(self):
        # Even a value that is not in today's fixtures would be database
        # content tomorrow. The scope vocabulary is dimension *names* and what
        # they mean; an adapter that needs a value reads it in the request.
        told = everything_the_adapter_is_told()
        self.assertEqual(SAMPLE.findall(told), [])

    def test_it_carries_no_evidence_vocabulary(self):
        told = everything_the_adapter_is_told()
        for word in ("evidence_bundle", "source_trace", "limitations", "row_count"):
            with self.subTest(word=word):
                self.assertNotIn(word, told)


class ThePayloadIsBuiltFromTheContract(unittest.TestCase):
    def test_it_lists_the_three_routes_and_their_allowlists(self):
        payload = vocabulary.payload()
        self.assertEqual(
            [route["name"] for route in payload["routes"]],
            [route.value for route in Route],
        )
        for entry, route in zip(payload["routes"], Route):
            with self.subTest(route=route.value):
                self.assertEqual(tuple(entry["arguments"]), allowed_parameters(route))

    def test_it_names_the_four_scope_dimensions_and_nothing_else(self):
        payload = vocabulary.payload()
        self.assertEqual(
            [dimension["name"] for dimension in payload["scope_dimensions"]],
            list(SCOPE_DIMENSIONS),
        )

    def test_it_offers_section_4_6s_unsupported_literal(self):
        self.assertEqual(vocabulary.payload()["unsupported_route"], UNSUPPORTED_ROUTE)

    def test_the_text_form_is_stable_so_the_prefix_can_cache(self):
        self.assertEqual(
            vocabulary.as_text(vocabulary.payload()),
            vocabulary.as_text(vocabulary.payload()),
        )


class TheSchemaClosesWhatItCan(unittest.TestCase):
    def test_the_route_enum_is_the_three_plus_the_literal(self):
        schema = vocabulary.schema()
        self.assertEqual(
            schema["properties"]["route"]["enum"],
            [route.value for route in Route] + [UNSUPPORTED_ROUTE],
        )

    def test_no_argument_outside_the_union_of_the_allowlists_is_accepted(self):
        schema = vocabulary.schema()
        self.assertFalse(schema["properties"]["arguments"]["additionalProperties"])
        self.assertEqual(
            sorted(schema["properties"]["arguments"]["properties"]),
            sorted({name for route in Route for name in allowed_parameters(route)}),
        )

    def test_the_schema_cannot_express_the_per_route_allowlist(self):
        # Recorded rather than hidden: `signal_key` is a valid property here
        # even for `message_facts`, because one flat object cannot say "the
        # allowlist of whichever route you chose". Revalidation refuses that
        # case, and `tests/test_adapter_revalidation.py` asserts the refusal --
        # this test exists so nobody reads the schema as the enforcement.
        arguments = vocabulary.schema()["properties"]["arguments"]["properties"]
        self.assertIn("signal_key", arguments)
        self.assertNotIn("signal_key", allowed_parameters(Route.MESSAGE_FACTS))


if __name__ == "__main__":
    unittest.main(verbosity=2)
