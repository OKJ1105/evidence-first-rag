"""entity-discovery-v0.1 Sections 4.3 (scope), 4.5-4.7 (tiers, candidates,
auto-resolution), 5 and 7: the route's decisions over recorded rows.

What the real templates return for the registered fixtures is asserted in
tests_database/test_discovery_fixtures.py. These tests hand the route rows
and assert what it decides and records.
"""

import unittest

from evidence_first_rag import SnapshotScope
from evidence_first_rag.discovery import (
    Discovery,
    DiscoveryLimitationKind,
    DiscoveryRequest,
    DiscoveryStatus,
    K,
    candidate_set_id,
    canonical_json,
    sha256_hex,
    validate,
)
from evidence_first_rag.runtime import DataFault

from .discovery_support import BASE, CHASSIS, CHASSIS_B, MESSAGE, REVISED, SIGNAL, STATE_ROW, candidate_row, database, discovery_row

PROVENANCE = ("fixtures/registry/approved_entity.jsonl", "fixtures/registry/approved_alias.jsonl")


def run(arguments, **rows):
    db = database(**rows)
    result = Discovery(database=db, fixture_provenance=PROVENANCE).execute(DiscoveryRequest(arguments=arguments))
    return db, result


def kinds(result):
    return [limitation.kind for limitation in result.limitations]


class ScopeIsAPrecondition(unittest.TestCase):
    """Section 4.3: the mvp-v0.1 candidate query runs first, unchanged. A
    complete scope runs the method in its one snapshot; an incomplete one,
    since `0.4.0`, in each candidate scope within the bound."""

    # `0.4.0`, Section 4.3: an incomplete scope within the bound is searched
    # in each candidate scope, and only the scopes where the term matched
    # are listed. Nothing is resolved.

    def test_dx_011_only_the_scopes_where_the_term_matched_are_listed(self):
        arguments = {k: v for k, v in MESSAGE.items() if k != "snapshot_label"}
        db, result = run(
            arguments,
            candidates=(candidate_row(BASE), candidate_row(REVISED)),
            exact=(discovery_row(REVISED),),
            scoped=True,
        )
        self.assertIs(result.status, DiscoveryStatus.AMBIGUOUS)
        self.assertEqual(result.candidate_scopes, (SnapshotScope(**REVISED),))
        self.assertIsNone(result.resolved)
        self.assertEqual(result.candidates, ())
        search = result.evidence_bundle.scope_search
        self.assertTrue(search.searched)
        self.assertEqual(search.candidate_scope_count, 2)
        self.assertEqual([entry.matched for entry in search.scopes], [False, True])
        self.assertEqual(search.scopes[1].match_tier, 1)
        self.assertEqual(search.scopes[1].template_name, "TPL_DISCOVERY_EXACT_V1")
        # Each candidate scope ran the method bound to that scope.
        exact_scopes = [p["snapshot_label"] for name, p in db.calls if name == "TPL_DISCOVERY_EXACT_V1"]
        self.assertEqual(exact_scopes, ["SAMPLE_SNAP_BASE", "SAMPLE_SNAP_REVISED"])
        # The bundle names the candidate query and the registry state it searched.
        self.assertEqual(result.evidence_bundle.template_name, "TPL_SNAPSHOT_CANDIDATES_V1")
        self.assertEqual(result.evidence_bundle.registry_digest, "a" * 64)
        self.assertIsNone(result.evidence_bundle.resolved_scope)
        self.assertIn(DiscoveryLimitationKind.SCOPES_SEARCHED, kinds(result))

    def test_dx_024_one_matching_scope_is_still_ambiguous(self):
        # mvp-v0.1 Section 4.2 as amended, and Charter Section 3.3: one is
        # still ambiguous, never resolved and never a candidate list.
        arguments = {k: v for k, v in MESSAGE.items() if k != "snapshot_label"}
        db, result = run(arguments, candidates=(candidate_row(BASE),), exact=(discovery_row(BASE),), scoped=True)
        self.assertIs(result.status, DiscoveryStatus.AMBIGUOUS)
        self.assertEqual(result.candidate_scopes, (SnapshotScope(**BASE),))
        self.assertIsNone(result.resolved)
        self.assertEqual(result.candidates, ())

    def test_dx_025_no_match_in_any_candidate_scope_is_not_found(self):
        arguments = {k: v for k, v in MESSAGE.items() if k != "snapshot_label"}
        db, result = run(arguments, candidates=(candidate_row(BASE), candidate_row(REVISED)), scoped=True)
        self.assertIs(result.status, DiscoveryStatus.NOT_FOUND)
        self.assertEqual(result.candidate_scopes, ())
        search = result.evidence_bundle.scope_search
        self.assertTrue(search.searched)
        self.assertEqual([entry.matched for entry in search.scopes], [False, False])
        # Both tiers were tried in each scope before concluding.
        self.assertEqual(len([n for n, _ in db.calls if n == "TPL_DISCOVERY_LEXICAL_V1"]), 2)
        self.assertIn(DiscoveryLimitationKind.NOT_IN_REGISTRY, kinds(result))
        self.assertIn(DiscoveryLimitationKind.SCOPES_SEARCHED, kinds(result))
        self.assertIn("all 2 candidate scopes", result.limitations[0].detail)

    def test_dx_026_above_the_bound_every_scope_is_listed_and_none_searched(self):
        from evidence_first_rag.discovery import service

        arguments = {k: v for k, v in MESSAGE.items() if k != "snapshot_label"}
        original = service.SCOPE_SEARCH_BOUND
        service.SCOPE_SEARCH_BOUND = 1
        try:
            db, result = run(
                arguments,
                candidates=(candidate_row(BASE), candidate_row(REVISED)),
                exact=(discovery_row(BASE),),
                scoped=True,
            )
        finally:
            service.SCOPE_SEARCH_BOUND = original
        self.assertEqual(original, 10)
        self.assertEqual(result.evidence_bundle.scope_search.bound, 1)
        self.assertIs(result.status, DiscoveryStatus.AMBIGUOUS)
        self.assertEqual(len(result.candidate_scopes), 2)
        self.assertFalse(db.ran("TPL_DISCOVERY_EXACT_V1"))
        self.assertFalse(db.ran("TPL_DISCOVERY_LEXICAL_V1"))
        self.assertFalse(db.ran("TPL_REGISTRY_STATE_V1"))
        self.assertEqual(result.evidence_bundle.registry_digest, "")
        self.assertFalse(result.evidence_bundle.scope_search.searched)
        self.assertIn(DiscoveryLimitationKind.SCOPES_NOT_SEARCHED, kinds(result))

    def test_dx_010_a_scope_no_snapshot_has_is_a_coverage_gap(self):
        db, result = run(MESSAGE | {"network_name": "SAMPLE_NET_BODY"}, candidates=())
        self.assertIs(result.status, DiscoveryStatus.COVERAGE_GAP)
        self.assertFalse(db.ran("TPL_DISCOVERY_EXACT_V1"))
        self.assertIn(DiscoveryLimitationKind.COVERAGE_NOT_ESTABLISHED, kinds(result))
        self.assertIn("SAMPLE_NET_BODY", result.limitations[0].detail)

    def test_the_candidate_query_runs_even_for_a_complete_scope(self):
        db, result = run(MESSAGE, exact=(discovery_row(),))
        self.assertTrue(db.ran("TPL_SNAPSHOT_CANDIDATES_V1"))
        self.assertEqual(db.calls[0][0], "TPL_SNAPSHOT_CANDIDATES_V1")

    def test_two_snapshots_for_a_complete_scope_is_a_data_fault(self):
        with self.assertRaises(DataFault):
            run(MESSAGE, candidates=(candidate_row(BASE), candidate_row(BASE)))

    def test_a_missing_registry_state_row_is_a_data_fault(self):
        with self.assertRaises(DataFault):
            run(MESSAGE, state=())


class TheMethod(unittest.TestCase):
    """Section 4.9 M-LEX-1: exact first; lexical only when E(T) is empty."""

    def test_the_lexical_template_does_not_run_when_the_exact_one_matched(self):
        db, result = run(MESSAGE, exact=(discovery_row(),))
        self.assertTrue(db.ran("TPL_DISCOVERY_EXACT_V1"))
        self.assertFalse(db.ran("TPL_DISCOVERY_LEXICAL_V1"))

    def test_the_lexical_template_runs_with_the_normalized_term_when_it_did_not(self):
        db, result = run(MESSAGE | {"term": "Engine Status"}, lexical=(discovery_row(match_tier=4),))
        self.assertTrue(db.ran("TPL_DISCOVERY_LEXICAL_V1"))
        bound = db.bound("TPL_DISCOVERY_LEXICAL_V1")
        self.assertEqual(bound["normalized_term"], ["engine", "status"])
        self.assertNotIn("term", bound)

    def test_the_exact_template_binds_the_term_byte_for_byte(self):
        db, _ = run(MESSAGE | {"term": "Engine Status"}, exact=(discovery_row(match_text="Engine Status", match_kind="approved_alias", match_tier=2),))
        self.assertEqual(db.bound("TPL_DISCOVERY_EXACT_V1")["term"], "Engine Status")

    def test_the_registry_state_is_read_in_the_same_session(self):
        db, result = run(MESSAGE, exact=(discovery_row(),))
        self.assertEqual(db.sessions, 1)
        self.assertEqual(result.evidence_bundle.registry_digest, "a" * 64)
        self.assertEqual(result.evidence_bundle.registry_built_at, "2026-09-12T00:00:00Z")
        self.assertEqual(result.evidence_bundle.method_identifier, "M-LEX-1")
        self.assertEqual(result.evidence_bundle.method_version, "1")


class AutoResolution(unittest.TestCase):
    """Section 4.7: resolved exactly when E(T) holds one entity."""

    def test_dx_001_one_tier_1_match_resolves(self):
        db, result = run(MESSAGE, exact=(discovery_row(),))
        self.assertIs(result.status, DiscoveryStatus.RESOLVED)
        self.assertEqual(result.resolved.match_tier, 1)
        self.assertEqual(result.resolved.reference.message_key, "SAMPLE_MSG_ENGINE_STATUS")
        self.assertEqual(result.candidates, ())
        self.assertEqual(result.evidence_bundle.match_tier, 1)
        self.assertEqual(result.evidence_bundle.matched_text, "SAMPLE_MSG_ENGINE_STATUS")
        self.assertEqual(result.evidence_bundle.candidate_set_id, "")
        self.assertEqual(result.source_trace.entity_approval_reference, "SAMPLE_APPROVAL_M3_001")
        self.assertEqual(result.source_trace.resolved_scope, SnapshotScope(**BASE))
        self.assertNotIn(DiscoveryLimitationKind.NO_REFERENCE_RESOLVED, kinds(result))

    def test_dx_002_one_tier_2_alias_match_resolves_with_provenance(self):
        row = discovery_row(message_key="SAMPLE_MSG_TRANSMISSION_STATE", match_tier=2, match_kind="approved_alias", match_text="SAMPLE_ALIAS_GEARBOX_STATE")
        db, result = run(MESSAGE | {"term": "SAMPLE_ALIAS_GEARBOX_STATE"}, exact=(row,))
        self.assertIs(result.status, DiscoveryStatus.RESOLVED)
        self.assertEqual(result.resolved.match_tier, 2)
        self.assertEqual(result.resolved.alias.approval_reference, "SAMPLE_APPROVAL_M3_101")
        self.assertEqual(result.resolved.alias.approved_at, "2026-03-05T00:00:00Z")
        self.assertEqual(result.resolved.alias.asserting_scope, SnapshotScope(**BASE))
        self.assertEqual(len(result.source_trace.alias_provenance), 1)

    def test_dx_004_two_entities_at_tiers_1_and_2_are_candidates(self):
        rows = (
            discovery_row(entity_kind="signal", message_key="SAMPLE_MSG_TRANSMISSION_STATE", signal_key="SAMPLE_SIG_GEAR_POSITION"),
            discovery_row(entity_kind="signal", message_key="SAMPLE_MSG_DIAGNOSTIC_EVENT", signal_key="SAMPLE_SIG_FAULT_CODE", match_tier=2, match_kind="approved_alias", match_text="SAMPLE_SIG_GEAR_POSITION"),
        )
        db, result = run(SIGNAL | {"term": "SAMPLE_SIG_GEAR_POSITION"}, exact=rows)
        self.assertIs(result.status, DiscoveryStatus.CANDIDATES)
        self.assertIsNone(result.resolved)
        self.assertEqual([c.match_tier for c in result.candidates], [1, 2])
        self.assertIn(DiscoveryLimitationKind.NO_REFERENCE_RESOLVED, kinds(result))

    def test_dx_005_the_same_key_under_two_parents_is_candidates(self):
        rows = (
            discovery_row(entity_kind="signal", message_key="SAMPLE_MSG_ENGINE_STATUS", signal_key="SAMPLE_SIG_TEMPERATURE"),
            discovery_row(entity_kind="signal", message_key="SAMPLE_MSG_TRANSMISSION_STATE", signal_key="SAMPLE_SIG_TEMPERATURE"),
        )
        db, result = run(SIGNAL, exact=rows)
        self.assertIs(result.status, DiscoveryStatus.CANDIDATES)
        # Every signal candidate carries its complete reference, parent included.
        self.assertEqual({c.reference.message_key for c in result.candidates}, {"SAMPLE_MSG_ENGINE_STATUS", "SAMPLE_MSG_TRANSMISSION_STATE"})
        self.assertEqual(len(result.source_trace.parent_messages), 2)

    def test_dx_007_a_single_tier_3_match_never_resolves(self):
        db, result = run(MESSAGE | {"term": "sample_msg_engine_status"}, lexical=(discovery_row(match_tier=3),))
        self.assertIs(result.status, DiscoveryStatus.CANDIDATES)
        self.assertEqual(result.candidates[0].match_tier, 3)
        self.assertIsNone(result.resolved)

    def test_dx_008_a_tier_4_match_is_a_ranked_candidate(self):
        db, result = run(SIGNAL | {"term": "engine speed"}, lexical=(discovery_row(entity_kind="signal", signal_key="SAMPLE_SIG_ENGINE_SPEED", match_tier=4),))
        self.assertIs(result.status, DiscoveryStatus.CANDIDATES)
        self.assertEqual(result.candidates[0].rank, 1)
        self.assertEqual(result.candidates[0].match_tier, 4)

    def test_dx_009_and_dx_015_no_match_is_not_found_with_the_allowlist_limitation(self):
        db, result = run(MESSAGE | {"term": "SAMPLE_MSG_DIAGNOSTIC_EVENT"})
        self.assertIs(result.status, DiscoveryStatus.NOT_FOUND)
        self.assertTrue(db.ran("TPL_DISCOVERY_LEXICAL_V1"))
        self.assertIn(DiscoveryLimitationKind.NOT_IN_REGISTRY, kinds(result))
        self.assertIn("not absence from the data", result.limitations[0].detail)
        self.assertEqual(result.evidence_bundle.resolved_scope, SnapshotScope(**BASE))
        self.assertEqual(result.source_trace.contributing_scopes, ())


class TheCandidateContract(unittest.TestCase):
    """Section 4.6: k = 10, ranks, truncation, and no attribute."""

    def rows(self, n):
        return tuple(discovery_row(message_key=f"SAMPLE_MSG_{i:02d}", match_tier=4) for i in range(n))

    def test_dx_016_an_eleventh_row_means_truncation_and_exactly_ten_are_listed(self):
        db, result = run(MESSAGE | {"term": "sample"}, lexical=self.rows(11))
        self.assertIs(result.status, DiscoveryStatus.CANDIDATES)
        self.assertEqual(len(result.candidates), K)
        self.assertEqual([c.rank for c in result.candidates], list(range(1, 11)))
        self.assertIn(DiscoveryLimitationKind.TRUNCATED_BY_LIMIT, kinds(result))
        self.assertEqual(result.evidence_bundle.row_count, 11)
        self.assertEqual(result.evidence_bundle.candidate_count, 10)

    def test_ten_rows_are_not_a_truncation(self):
        db, result = run(MESSAGE | {"term": "sample"}, lexical=self.rows(10))
        self.assertEqual(len(result.candidates), 10)
        self.assertNotIn(DiscoveryLimitationKind.TRUNCATED_BY_LIMIT, kinds(result))

    def test_the_list_keeps_the_templates_order(self):
        rows = (discovery_row(message_key="SAMPLE_MSG_B", match_tier=4), discovery_row(message_key="SAMPLE_MSG_A", match_tier=4))
        db, result = run(MESSAGE | {"term": "sample"}, lexical=rows)
        # The registered ORDER BY is the ordering; the route reranks nothing.
        self.assertEqual([c.reference.message_key for c in result.candidates], ["SAMPLE_MSG_B", "SAMPLE_MSG_A"])

    def test_a_candidate_carries_no_attribute(self):
        db, result = run(MESSAGE, exact=(discovery_row(),))
        fields = set(result.resolved.digest_fields())
        for attribute in ("transmit_period_ms", "frame_identifier", "unit_label", "scale_factor"):
            self.assertNotIn(attribute, fields)


class TheCandidateSetDigest(unittest.TestCase):
    """Section 4.8: exactly the listed keys, canonical JSON, deterministic."""

    def test_it_is_recomputable_from_the_request_and_the_list(self):
        rows = (discovery_row(match_tier=4), discovery_row(message_key="SAMPLE_MSG_TRANSMISSION_STATE", match_tier=4))
        db, result = run(MESSAGE | {"term": "sample msg"}, lexical=rows)
        validated = validate(DiscoveryRequest(arguments=MESSAGE | {"term": "sample msg"}))
        self.assertEqual(result.evidence_bundle.candidate_set_id, candidate_set_id(validated, "a" * 64, result.candidates))

    def test_the_input_is_the_section_4_8_object(self):
        rows = (discovery_row(match_tier=4),) * 1
        db, result = run(MESSAGE | {"term": "sample msg"}, lexical=(discovery_row(match_tier=4), discovery_row(message_key="SAMPLE_MSG_X", match_tier=4)))
        expected = sha256_hex(canonical_json({
            "contract_identifier": "entity-discovery-v0.1",
            "contract_version": "0.4.0",
            "registry_digest": "a" * 64,
            **BASE,
            "entity_kind": "message",
            "parent_message_key": None,
            "term": "sample msg",
            "method_identifier": "M-LEX-1",
            "method_version": "1",
            "candidates": [
                {"rank": 1, "entity_kind": "message", **BASE, "message_key": "SAMPLE_MSG_ENGINE_STATUS", "signal_key": None,
                 "match_tier": 4, "matched_text": "SAMPLE_MSG_ENGINE_STATUS", "match_kind": "lookup_key"},
                {"rank": 2, "entity_kind": "message", **BASE, "message_key": "SAMPLE_MSG_X", "signal_key": None,
                 "match_tier": 4, "matched_text": "SAMPLE_MSG_X", "match_kind": "lookup_key"},
            ],
        }))
        self.assertEqual(result.evidence_bundle.candidate_set_id, expected)

    def test_a_different_registry_digest_changes_it(self):
        rows = (discovery_row(match_tier=4), discovery_row(message_key="SAMPLE_MSG_X", match_tier=4))
        _, a = run(MESSAGE | {"term": "sample"}, lexical=rows)
        _, b = run(MESSAGE | {"term": "sample"}, lexical=rows, state=(STATE_ROW | {"registry_digest": "b" * 64},))
        self.assertNotEqual(a.evidence_bundle.candidate_set_id, b.evidence_bundle.candidate_set_id)

    def test_the_term_is_byte_exact_in_the_digest(self):
        rows = (discovery_row(match_tier=4), discovery_row(message_key="SAMPLE_MSG_X", match_tier=4))
        _, a = run(MESSAGE | {"term": "Sample"}, lexical=rows)
        _, b = run(MESSAGE | {"term": "sample"}, lexical=rows)
        self.assertNotEqual(a.evidence_bundle.candidate_set_id, b.evidence_bundle.candidate_set_id)

    def test_alias_provenance_is_not_in_the_digest(self):
        row = discovery_row(match_tier=4, match_kind="approved_alias", match_text="SAMPLE_ALIAS_X")
        other = discovery_row(message_key="SAMPLE_MSG_X", match_tier=4)
        _, a = run(MESSAGE | {"term": "sample"}, lexical=(row, other))
        _, b = run(MESSAGE | {"term": "sample"}, lexical=(row | {"alias_approval_reference": "SAMPLE_APPROVAL_OTHER"}, other))
        self.assertEqual(a.evidence_bundle.candidate_set_id, b.evidence_bundle.candidate_set_id)


class TheEvidence(unittest.TestCase):
    def test_both_contracts_identities_are_on_every_bundle(self):
        for arguments, rows in ((MESSAGE, {"exact": (discovery_row(),)}), (MESSAGE | {"term": ""}, {})):
            _, result = run(arguments, **rows)
            bundle = result.evidence_bundle
            self.assertEqual(bundle.contract_identifier, "entity-discovery-v0.1")
            self.assertEqual(bundle.contract_version, "0.4.0")
            self.assertEqual(bundle.runtime_contract_identifier, "mvp-v0.1")
            self.assertEqual(bundle.collation, "C")
            self.assertEqual(result.source_trace.fixture_provenance, PROVENANCE)

    def test_the_bundle_records_the_template_that_ran_and_what_it_bound(self):
        db, result = run(MESSAGE, exact=(discovery_row(),))
        self.assertEqual(result.evidence_bundle.template_name, "TPL_DISCOVERY_EXACT_V1")
        self.assertEqual(result.evidence_bundle.template_version, "1")
        self.assertEqual(dict(result.evidence_bundle.bound_parameters), db.bound("TPL_DISCOVERY_EXACT_V1"))
        self.assertEqual(result.evidence_bundle.row_count, 1)

    def test_dx_020_a_superseded_participating_snapshot_is_named(self):
        row = discovery_row(CHASSIS, message_key="SAMPLE_MSG_WHEEL_SPEED", match_tier=2, match_kind="approved_alias", match_text="SAMPLE_ALIAS_WHEEL_SPEEDS", superseded_by=CHASSIS_B)
        _, result = run(CHASSIS | {"entity_kind": "message", "term": "SAMPLE_ALIAS_WHEEL_SPEEDS"}, candidates=(candidate_row(CHASSIS),), exact=(row,))
        self.assertIs(result.status, DiscoveryStatus.RESOLVED)
        self.assertIn(DiscoveryLimitationKind.SUPERSEDED_SNAPSHOT, kinds(result))
        self.assertIn("SAMPLE_REV_B", [l for l in result.limitations if l.kind is DiscoveryLimitationKind.SUPERSEDED_SNAPSHOT][0].detail)

    def test_one_superseded_entry_per_distinct_snapshot(self):
        rows = tuple(discovery_row(CHASSIS, message_key=f"SAMPLE_MSG_{i}", match_tier=4, superseded_by=CHASSIS_B) for i in range(3))
        _, result = run(CHASSIS | {"entity_kind": "message", "term": "sample"}, candidates=(candidate_row(CHASSIS),), lexical=rows)
        self.assertEqual(kinds(result).count(DiscoveryLimitationKind.SUPERSEDED_SNAPSHOT), 1)

    def test_the_session_reports_what_it_opened(self):
        db, result = run(MESSAGE, exact=(discovery_row(),))
        safeguards = result.evidence_bundle.read_only_safeguards
        self.assertTrue(safeguards.connection_opened)
        self.assertTrue(safeguards.read_only_transaction)
        self.assertEqual(safeguards.role_name, db.role_name)


if __name__ == "__main__":
    unittest.main(verbosity=2)
