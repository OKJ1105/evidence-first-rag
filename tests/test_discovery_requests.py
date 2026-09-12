"""entity-discovery-v0.1 Section 4.3 validation, and the statuses that open
no connection (Section 5).

Every refusal asserts the outcome *and* that the database was never asked
for a session: a route that produced the right status after connecting would
satisfy Section 5 and break Section 4.3.
"""

import unittest

from evidence_first_rag import ProducingLayer
from evidence_first_rag.discovery import (
    Discovery,
    DiscoveryRequest,
    DiscoveryStatus,
    validate,
)
from evidence_first_rag.discovery.request import (
    ROUTE,
    TERM_BYTE_LIMIT,
    DiscoveryRefusal,
    allowed_parameters,
)

from .discovery_support import BASE, MESSAGE, SIGNAL, database


def answer(arguments):
    db = database()
    return db, Discovery(database=db).execute(DiscoveryRequest(arguments=arguments))


class TheAllowlist(unittest.TestCase):
    def test_it_is_section_4_3s_table(self):
        self.assertEqual(
            set(allowed_parameters()),
            set(BASE) | {"entity_kind", "term", "parent_message_key"},
        )

    def test_the_route_name(self):
        self.assertEqual(ROUTE, "entity_discovery")


class ARequestThatOpensNoConnection(unittest.TestCase):
    """Section 5: `invalid_request` and `unsupported` open no connection;
    Section 4.3: no discovery template executes."""

    def assert_refused(self, arguments, status, detail_fragment=None):
        db, result = answer(arguments)
        self.assertIs(result.status, status)
        self.assertEqual(db.sessions, 0)
        self.assertFalse(result.evidence_bundle.read_only_safeguards.connection_opened)
        self.assertEqual(result.evidence_bundle.template_name, "")
        self.assertEqual(result.evidence_bundle.registry_digest, "")
        self.assertEqual(result.evidence_bundle.route, "entity_discovery")
        self.assertEqual(dict(result.evidence_bundle.bound_parameters), {})
        if detail_fragment is not None:
            with self.assertRaises(DiscoveryRefusal) as raised:
                validate(DiscoveryRequest(arguments=arguments))
            self.assertIn(detail_fragment, str(raised.exception))
        return result

    def test_dx_014_an_entity_kind_outside_the_two_is_unsupported_by_the_runtime(self):
        result = self.assert_refused(MESSAGE | {"entity_kind": "SAMPLE_KIND_FRAME"}, DiscoveryStatus.UNSUPPORTED)
        # Section 5: "the trace records the producing layer."
        self.assertIs(result.source_trace.producing_layer, ProducingLayer.RUNTIME)

    def test_dx_013_a_parent_message_key_with_a_message_kind_is_invalid(self):
        self.assert_refused(
            MESSAGE | {"parent_message_key": "SAMPLE_MSG_ENGINE_STATUS"},
            DiscoveryStatus.INVALID_REQUEST, "parent_message_key",
        )

    def test_a_parent_message_key_with_a_signal_kind_is_permitted(self):
        db, result = answer(SIGNAL | {"parent_message_key": "SAMPLE_MSG_ENGINE_STATUS"})
        self.assertEqual(db.sessions, 1)
        self.assertEqual(db.bound("TPL_DISCOVERY_EXACT_V1")["parent_message_key"], "SAMPLE_MSG_ENGINE_STATUS")

    def test_dx_012_an_empty_term(self):
        self.assert_refused(MESSAGE | {"term": ""}, DiscoveryStatus.INVALID_REQUEST, "empty")

    def test_dx_012_a_whitespace_only_term_has_no_token(self):
        # Non-empty as text, and Section 4.3 still refuses it: "at least one
        # token after the Section 4.5 normalization".
        self.assert_refused(MESSAGE | {"term": " \t "}, DiscoveryStatus.INVALID_REQUEST, "no token")

    def test_dx_012_a_term_of_only_separators_has_no_token(self):
        self.assert_refused(MESSAGE | {"term": "___-..."}, DiscoveryStatus.INVALID_REQUEST, "no token")

    def test_dx_012_a_term_over_200_bytes(self):
        self.assert_refused(MESSAGE | {"term": "a" * (TERM_BYTE_LIMIT + 1)}, DiscoveryStatus.INVALID_REQUEST, "bytes")

    def test_the_limit_is_in_bytes_not_characters(self):
        # 100 three-byte characters plus one letter: 301 bytes, 101 characters.
        # Section 4.3 says why: "a character count would make the same term
        # valid or invalid depending on an implementation's string type."
        term = "あ" * 100 + "a"
        self.assertEqual(len(term), 101)
        self.assert_refused(MESSAGE | {"term": term}, DiscoveryStatus.INVALID_REQUEST, "bytes")

    def test_a_term_of_exactly_200_bytes_is_accepted(self):
        db, result = answer(MESSAGE | {"term": "a" * TERM_BYTE_LIMIT})
        self.assertEqual(db.sessions, 1)

    def test_an_argument_outside_the_allowlist(self):
        self.assert_refused(MESSAGE | {"k": "3"}, DiscoveryStatus.INVALID_REQUEST, "allowlist")

    def test_a_missing_term(self):
        self.assert_refused(BASE | {"entity_kind": "message"}, DiscoveryStatus.INVALID_REQUEST, "missing")

    def test_a_missing_entity_kind(self):
        self.assert_refused(BASE | {"term": "x"}, DiscoveryStatus.INVALID_REQUEST, "missing")

    def test_a_contradictory_value(self):
        # Two values for one argument is the only shape a contradiction can
        # take in a mapping.
        self.assert_refused(MESSAGE | {"revision_label": ["SAMPLE_REV_A", "SAMPLE_REV_B"]}, DiscoveryStatus.INVALID_REQUEST, "values")

    def test_a_non_string_value(self):
        self.assert_refused(MESSAGE | {"term": 7}, DiscoveryStatus.INVALID_REQUEST, "string")

    def test_arguments_that_are_not_a_mapping(self):
        self.assert_refused(["term"], DiscoveryStatus.INVALID_REQUEST, "mapping")

    def test_validation_runs_before_the_kind_check(self):
        # A malformed request is answered as malformed even when it also
        # names an unsupported kind: the allowlist is read first.
        self.assert_refused(MESSAGE | {"entity_kind": "frame", "k": "3"}, DiscoveryStatus.INVALID_REQUEST)


class TheValidatedRequest(unittest.TestCase):
    def test_it_carries_the_normalized_term(self):
        validated = validate(DiscoveryRequest(arguments=MESSAGE | {"term": "Engine-Status 2"}))
        self.assertEqual(validated.normalized_term, ("engine", "status", "2"))
        self.assertEqual(validated.term, "Engine-Status 2")

    def test_scope_completeness_is_not_decided_here(self):
        # Section 4.3: ambiguous and coverage_gap depend on the candidate
        # query, so an incomplete scope validates.
        arguments = {k: v for k, v in MESSAGE.items() if k != "snapshot_label"}
        validated = validate(DiscoveryRequest(arguments=arguments))
        self.assertFalse(validated.scope_is_complete)
        self.assertIsNone(validated.scope_arguments["snapshot_label"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
