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
import unittest

from evidence_first_rag import SCOPE_DIMENSIONS, UNSUPPORTED_ROUTE, Route
from evidence_first_rag.adapter import vocabulary
from evidence_first_rag.runtime.request import allowed_parameters

from .support import SAMPLE, loaded_identifiers


def everything_the_adapter_is_told() -> str:
    return vocabulary.instructions() + vocabulary.as_text(vocabulary.payload()) + json.dumps(
        vocabulary.schema()
    )


class TheCallCarriesNoDatabaseContent(unittest.TestCase):
    def test_no_fixture_identifier_appears_anywhere_in_the_payload(self):
        told = everything_the_adapter_is_told()
        leaked = sorted(name for name in loaded_identifiers() if name in told)
        self.assertEqual(leaked, [])

    def test_the_search_would_notice_one(self):
        # Probed, because a scan over an empty set passes quietly.
        self.assertTrue(loaded_identifiers())
        self.assertIn(
            "SAMPLE_MSG_ENGINE_STATUS",
            loaded_identifiers(),
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


class TheInstructionsNameTheJudgementFamilies(unittest.TestCase):
    """Section 8.3's `U`, `X` and `D` families, as rules in the fixed text.

    Offline this can only assert the text; the evidence that the rules land
    is the comparison run, read per case on #91. What these tests hold is
    that the rules stay in the prompt and keep their operative wording.
    """

    def test_the_operation_rule_names_every_unsupported_operation_of_section_8_3(self):
        # "export, compare, diff, dump-the-scope, similarity, or any write"
        # is the contract's own list for the `U` family. Each names an
        # operation verb: the rule turns on what is asked for, not on how
        # many rows the answer would have.
        text = vocabulary.instructions()
        for operation in ("export", "compare", "diff", "what changed",
                          "dump the entire contents of a scope", "similar", "delete"):
            self.assertIn(operation, text, f"the operation rule does not name {operation!r}")
        self.assertIn("even when it names valid identifiers", text)
        self.assertIn("'Export the facts' is not a request for the facts", text)

    def test_the_operation_rule_hands_a_scopes_contents_to_the_missing_key_rule(self):
        # `EV-D-1` and `EV-D-3` ask which messages or mappings a scope
        # contains. That is a determined route with no key, not a dump, and
        # the operation rule has to say so or it would claim them first.
        text = vocabulary.instructions()
        self.assertIn(
            "Asking which messages, signals or mappings a scope contains is not a dump",
            text,
        )

    def test_the_contradiction_rule_says_emit_every_value_not_choose_or_omit(self):
        text = vocabulary.instructions()
        self.assertIn("two or more different values for one argument", text)
        self.assertIn("do not choose one and do not leave the argument out", text)
        self.assertIn("emit one entry per value, all under that same name", text)

    def test_the_missing_key_rule_keeps_the_route(self):
        text = vocabulary.instructions()
        self.assertIn("keep the route and leave that key out", text)
        self.assertIn(f"Do not answer {UNSUPPORTED_ROUTE!r} for a missing key", text)

    def test_the_operation_rule_comes_before_the_missing_key_rule(self):
        # A request to dump a whole scope must meet the operation rule
        # first, or the missing-key rule would pull it into a route.
        text = vocabulary.instructions()
        self.assertLess(text.index("The routes read facts and nothing else"),
                        text.index("keep the route and leave that key out"))


class TheSchemaClosesWhatItCan(unittest.TestCase):
    def test_the_route_enum_is_the_three_plus_the_literal(self):
        schema = vocabulary.schema()
        self.assertEqual(
            schema["properties"]["route"]["enum"],
            [route.value for route in Route] + [UNSUPPORTED_ROUTE],
        )

    def test_the_arguments_are_a_list_of_pairs_with_no_order_to_be_locked_out_of(self):
        # #111. The enumeration was an ordered mapping, and the model could
        # not emit a key sorted before one it had already written -- which
        # made `message_key` and `network_name` unreachable on every positive
        # case of the `d2f08cb8` run. The API refuses an object with open
        # names (every object must carry `additionalProperties: false`), so
        # the names live in a list, whose elements have no order among them.
        arguments = vocabulary.schema()["properties"]["arguments"]
        self.assertEqual(arguments["type"], "array")
        # Nothing on the array itself reintroduces an ordering or a count.
        self.assertEqual(sorted(arguments), ["items", "type"])
        item = arguments["items"]
        self.assertEqual(item["type"], "object")
        self.assertIs(item["additionalProperties"], False)
        self.assertEqual(item["required"], ["name", "value"])
        self.assertEqual(sorted(item["properties"]), ["name", "value"])
        self.assertEqual(item["properties"]["value"], {"type": "string"})

    def test_the_name_enum_is_the_union_of_the_allowlists_not_a_per_route_one(self):
        # The seven names are closed at the schema again, as they were
        # before #111 -- but as an enum on a list element, not as ordered
        # properties. It is the *union*: `signal_key` is accepted on
        # `message_facts` here, and nobody should read the schema as the
        # per-route enforcement. Section 4.6 puts that in deterministic
        # revalidation, and `tests/test_adapter_revalidation.py` asserts the
        # refusal.
        name = vocabulary.schema()["properties"]["arguments"]["items"]["properties"]["name"]
        union = sorted({n for route in Route for n in allowed_parameters(route)})
        self.assertEqual(name, {"type": "string", "enum": union})
        self.assertIn("signal_key", name["enum"])
        self.assertNotIn("signal_key", allowed_parameters(Route.MESSAGE_FACTS))
        # Sorted, so the enum text is stable and the schema digest with it;
        # an enum's order constrains nothing the model emits.
        self.assertEqual(name["enum"], sorted(name["enum"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
