"""entity-discovery-v0.1 Section 8.1: DX-001 to DX-016 against a real
PostgreSQL database loaded from `fixtures/`.

tests/ proves the route's decisions given rows; this file proves the rows.
DX-004 asserts that the registered SQL returns two entities for a term that
is one entity's lookup key and another's alias, which only a real query can
show; DX-007 asserts that the case-only variant reaches the lexical template
and comes back at tier 3; DX-016 asserts truncation over a fixture tree the
test builds, because the registered occurrences cannot reach eleven (#143).

Every case asserts the three Section 7 structures with their required keys,
`registry_digest` included (Section 8, row "Sections 5 and 7").
"""

import json
import os
import pathlib
import shutil
import tempfile
import unittest

from evidence_first_rag import ProducingLayer, SnapshotScope
from evidence_first_rag.discovery import (
    Discovery,
    DiscoveryLimitationKind,
    DiscoveryRequest,
    DiscoveryStatus,
    K,
    candidate_set_id,
    validate,
)
from evidence_first_rag.runtime.connection import PsycopgDatabase

from . import support

DATABASE = "mvp_test_discovery"

POWERTRAIN = {"project_code": "SAMPLE_PROJECT_ALPHA", "revision_label": "SAMPLE_REV_A", "network_name": "SAMPLE_NET_POWERTRAIN", "snapshot_label": "SAMPLE_SNAP_BASE"}
REVISED = POWERTRAIN | {"snapshot_label": "SAMPLE_SNAP_REVISED"}
CHASSIS_A = POWERTRAIN | {"network_name": "SAMPLE_NET_CHASSIS"}
CHASSIS_B = CHASSIS_A | {"revision_label": "SAMPLE_REV_B"}

PROVENANCE = ("fixtures/registry/approved_entity.jsonl", "fixtures/registry/approved_alias.jsonl")


def setUpModule():
    support.build(DATABASE)


def tearDownModule():
    support.drop(DATABASE)


def discovery(database=DATABASE):
    return Discovery(
        database=PsycopgDatabase(connection_parameters={
            "dbname": database, "user": "mvp_runtime", "password": os.environ["MVP_RUNTIME_PASSWORD"],
            "host": os.environ.get("PGHOST"), "port": os.environ.get("PGPORT"),
        }),
        fixture_provenance=PROVENANCE,
    )


def stored_digest(database=DATABASE):
    with support.connect(database, "runtime") as connection, connection.cursor() as cursor:
        cursor.execute("SELECT registry_digest FROM mvp.entity_registry_state")
        return cursor.fetchone()[0]


class FixtureCase(unittest.TestCase):
    def answer(self, arguments, database=DATABASE):
        result = discovery(database).execute(DiscoveryRequest(arguments=arguments))
        self.assert_evidence(result, database)
        return result

    def assert_evidence(self, result, database):
        bundle = result.evidence_bundle
        self.assertEqual(bundle.contract_identifier, "entity-discovery-v0.1")
        self.assertEqual(bundle.contract_version, "0.2.0")
        self.assertEqual(bundle.runtime_contract_identifier, "mvp-v0.1")
        self.assertEqual(bundle.route, "entity_discovery")
        self.assertEqual(bundle.collation, "C")
        self.assertIsInstance(result.limitations, tuple)
        self.assertEqual(result.source_trace.fixture_provenance, PROVENANCE)
        if bundle.read_only_safeguards.connection_opened:
            self.assertEqual(bundle.read_only_safeguards.role_name, "mvp_runtime")
            self.assertTrue(bundle.read_only_safeguards.read_only_transaction)
        if result.status in (DiscoveryStatus.RESOLVED, DiscoveryStatus.CANDIDATES, DiscoveryStatus.NOT_FOUND):
            # Section 7: registry_digest on every result a discovery template
            # produced, and it is the stored one.
            self.assertEqual(bundle.registry_digest, stored_digest(database))
            self.assertRegex(bundle.registry_built_at, r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
            self.assertEqual(bundle.method_identifier, "M-LEX-1")

    def kinds(self, result):
        return [limitation.kind for limitation in result.limitations]


class AutoResolution(FixtureCase):
    def test_dx_001_a_message_key_unique_in_scope_resolves_at_tier_1(self):
        result = self.answer(POWERTRAIN | {"entity_kind": "message", "term": "SAMPLE_MSG_ENGINE_STATUS"})
        self.assertIs(result.status, DiscoveryStatus.RESOLVED)
        self.assertEqual(result.resolved.match_tier, 1)
        self.assertEqual(result.resolved.reference.message_key, "SAMPLE_MSG_ENGINE_STATUS")
        self.assertEqual(result.resolved.scope, SnapshotScope(**POWERTRAIN))
        self.assertEqual(result.evidence_bundle.template_name, "TPL_DISCOVERY_EXACT_V1")
        self.assertEqual(result.source_trace.entity_approval_reference, "SAMPLE_APPROVAL_M3_001")

    def test_dx_002_an_approved_alias_resolves_at_tier_2_with_provenance_in_the_trace(self):
        result = self.answer(POWERTRAIN | {"entity_kind": "message", "term": "SAMPLE_ALIAS_GEARBOX_STATE"})
        self.assertIs(result.status, DiscoveryStatus.RESOLVED)
        self.assertEqual(result.resolved.match_tier, 2)
        self.assertEqual(result.resolved.match_kind, "approved_alias")
        self.assertEqual(result.resolved.reference.message_key, "SAMPLE_MSG_TRANSMISSION_STATE")
        self.assertEqual(result.resolved.alias.approval_reference, "SAMPLE_APPROVAL_M3_101")
        self.assertEqual(result.resolved.alias.asserting_scope, SnapshotScope(**POWERTRAIN))
        self.assertEqual(len(result.source_trace.alias_provenance), 1)

    def test_dx_003_a_spelling_variant_resolves_at_tier_2(self):
        result = self.answer(POWERTRAIN | {"entity_kind": "message", "term": "SAMPLE_MSG_TRANSMISION_STATE"})
        self.assertIs(result.status, DiscoveryStatus.RESOLVED)
        self.assertEqual(result.resolved.match_tier, 2)
        self.assertEqual(result.resolved.match_kind, "spelling_variant")

    def test_dx_004_a_lookup_key_that_is_anothers_alias_abstains_into_two_candidates(self):
        result = self.answer(POWERTRAIN | {"entity_kind": "signal", "term": "SAMPLE_SIG_GEAR_POSITION"})
        self.assertIs(result.status, DiscoveryStatus.CANDIDATES)
        self.assertIsNone(result.resolved)
        self.assertEqual(
            [(c.match_tier, c.reference.signal_key) for c in result.candidates],
            [(1, "SAMPLE_SIG_GEAR_POSITION"), (2, "SAMPLE_SIG_FAULT_CODE")],
        )
        self.assertIn(DiscoveryLimitationKind.NO_REFERENCE_RESOLVED, self.kinds(result))

    def test_dx_005_one_signal_key_under_two_parents_abstains_into_two_candidates(self):
        result = self.answer(POWERTRAIN | {"entity_kind": "signal", "term": "SAMPLE_SIG_TEMPERATURE"})
        self.assertIs(result.status, DiscoveryStatus.CANDIDATES)
        self.assertEqual(
            sorted(c.reference.message_key for c in result.candidates),
            ["SAMPLE_MSG_ENGINE_STATUS", "SAMPLE_MSG_TRANSMISSION_STATE"],
        )
        self.assertEqual(len(result.source_trace.parent_messages), 2)

    def test_dx_005_with_the_parent_supplied_it_resolves(self):
        result = self.answer(POWERTRAIN | {"entity_kind": "signal", "term": "SAMPLE_SIG_TEMPERATURE", "parent_message_key": "SAMPLE_MSG_ENGINE_STATUS"})
        self.assertIs(result.status, DiscoveryStatus.RESOLVED)
        self.assertEqual(result.resolved.reference.message_key, "SAMPLE_MSG_ENGINE_STATUS")

    def test_dx_006_a_key_in_two_snapshots_resolves_in_the_requested_one_only(self):
        for scope in (POWERTRAIN, REVISED):
            with self.subTest(snapshot=scope["snapshot_label"]):
                result = self.answer(scope | {"entity_kind": "message", "term": "SAMPLE_MSG_ENGINE_STATUS"})
                self.assertIs(result.status, DiscoveryStatus.RESOLVED)
                self.assertEqual(result.resolved.scope, SnapshotScope(**scope))

    def test_dx_007_a_case_only_difference_is_candidates_at_tier_3_never_resolved(self):
        result = self.answer(POWERTRAIN | {"entity_kind": "message", "term": "sample_msg_engine_status"})
        self.assertIs(result.status, DiscoveryStatus.CANDIDATES)
        self.assertEqual([c.match_tier for c in result.candidates], [3])
        self.assertEqual(result.evidence_bundle.template_name, "TPL_DISCOVERY_LEXICAL_V1")
        self.assertIsNone(result.resolved)

    def test_dx_008_a_descriptive_term_is_a_tier_4_candidate_ranked_first(self):
        result = self.answer(POWERTRAIN | {"entity_kind": "signal", "term": "engine speed"})
        self.assertIs(result.status, DiscoveryStatus.CANDIDATES)
        self.assertEqual(result.candidates[0].reference.signal_key, "SAMPLE_SIG_ENGINE_SPEED")
        self.assertEqual(result.candidates[0].match_tier, 4)
        self.assertEqual(result.candidates[0].rank, 1)
        # Section 4.6: one entity once, carrying its best match -- the alias
        # SAMPLE_ALIAS_ENGINE_ROTATION_SPEED also contains the tokens and
        # sorts first in byte order, and adds no second candidate.
        self.assertEqual(len(result.candidates), 1)
        self.assertEqual(result.candidates[0].matched_text, "SAMPLE_ALIAS_ENGINE_ROTATION_SPEED")

    def test_dx_009_no_match_at_any_tier_is_not_found_with_the_allowlist_limitation(self):
        result = self.answer(POWERTRAIN | {"entity_kind": "signal", "term": "SAMPLE_SIG_NOTHING_LIKE_THIS"})
        self.assertIs(result.status, DiscoveryStatus.NOT_FOUND)
        self.assertIn(DiscoveryLimitationKind.NOT_IN_REGISTRY, self.kinds(result))
        self.assertEqual(result.evidence_bundle.resolved_scope, SnapshotScope(**POWERTRAIN))

    def test_dx_015_a_loaded_occurrence_absent_from_the_registry_is_not_found(self):
        # The fixture that proves the registry is an allowlist. Both are in
        # the loaded data (mvp-v0.1 FX-001/FX-002 return them) and neither is
        # approved.
        for kind, term in (("message", "SAMPLE_MSG_DIAGNOSTIC_EVENT"), ("signal", "SAMPLE_SIG_WHEEL_SPEED_FR")):
            with self.subTest(kind=kind):
                scope = POWERTRAIN if kind == "message" else CHASSIS_A
                result = self.answer(scope | {"entity_kind": kind, "term": term})
                self.assertIs(result.status, DiscoveryStatus.NOT_FOUND)
                detail = [l for l in result.limitations if l.kind is DiscoveryLimitationKind.NOT_IN_REGISTRY][0].detail
                self.assertIn("not absence from the data", detail)


class ScopeAndRequest(FixtureCase):
    def test_dx_010_a_network_no_snapshot_has_is_a_coverage_gap(self):
        result = self.answer(POWERTRAIN | {"network_name": "SAMPLE_NET_BODY", "entity_kind": "message", "term": "SAMPLE_MSG_ENGINE_STATUS"})
        self.assertIs(result.status, DiscoveryStatus.COVERAGE_GAP)
        self.assertEqual(result.evidence_bundle.template_name, "TPL_SNAPSHOT_CANDIDATES_V1")
        self.assertEqual(result.evidence_bundle.registry_digest, "")

    def test_dx_011_an_omitted_snapshot_label_is_ambiguous_and_executes_no_discovery_template(self):
        arguments = {k: v for k, v in POWERTRAIN.items() if k != "snapshot_label"} | {"entity_kind": "message", "term": "SAMPLE_MSG_ENGINE_STATUS"}
        result = self.answer(arguments)
        self.assertIs(result.status, DiscoveryStatus.AMBIGUOUS)
        self.assertEqual({s.snapshot_label for s in result.candidate_scopes}, {"SAMPLE_SNAP_BASE", "SAMPLE_SNAP_REVISED"})
        self.assertEqual(result.evidence_bundle.template_name, "TPL_SNAPSHOT_CANDIDATES_V1")
        self.assertEqual(result.evidence_bundle.registry_digest, "")

    def test_dx_012_an_empty_term_and_an_over_long_term_open_no_connection(self):
        for term in ("   ", "a" * 201):
            with self.subTest(term=term[:5]):
                result = self.answer(POWERTRAIN | {"entity_kind": "message", "term": term})
                self.assertIs(result.status, DiscoveryStatus.INVALID_REQUEST)
                self.assertFalse(result.evidence_bundle.read_only_safeguards.connection_opened)

    def test_dx_013_a_parent_with_a_message_kind_is_invalid(self):
        result = self.answer(POWERTRAIN | {"entity_kind": "message", "term": "x", "parent_message_key": "SAMPLE_MSG_ENGINE_STATUS"})
        self.assertIs(result.status, DiscoveryStatus.INVALID_REQUEST)

    def test_dx_014_an_entity_kind_outside_the_two_is_unsupported_with_the_layer_recorded(self):
        result = self.answer(POWERTRAIN | {"entity_kind": "SAMPLE_KIND_FRAME", "term": "x"})
        self.assertIs(result.status, DiscoveryStatus.UNSUPPORTED)
        self.assertIs(result.source_trace.producing_layer, ProducingLayer.RUNTIME)
        self.assertFalse(result.evidence_bundle.read_only_safeguards.connection_opened)


class TheCandidateSetAndProvenance(FixtureCase):
    def test_dx_020_an_alias_asserted_by_a_superseded_snapshot_names_it(self):
        result = self.answer(CHASSIS_A | {"entity_kind": "message", "term": "SAMPLE_ALIAS_WHEEL_SPEEDS"})
        self.assertIs(result.status, DiscoveryStatus.RESOLVED)
        self.assertIn(DiscoveryLimitationKind.SUPERSEDED_SNAPSHOT, self.kinds(result))
        detail = [l for l in result.limitations if l.kind is DiscoveryLimitationKind.SUPERSEDED_SNAPSHOT][0].detail
        self.assertIn("SAMPLE_REV_B", detail)

    def test_the_candidate_set_id_recomputes_and_is_stable_across_runs(self):
        arguments = POWERTRAIN | {"entity_kind": "signal", "term": "SAMPLE_SIG_GEAR_POSITION"}
        first = self.answer(arguments)
        second = self.answer(arguments)
        self.assertEqual(first.evidence_bundle.candidate_set_id, second.evidence_bundle.candidate_set_id)
        self.assertEqual(
            first.evidence_bundle.candidate_set_id,
            candidate_set_id(validate(DiscoveryRequest(arguments=arguments)), stored_digest(), first.candidates),
        )

    def test_two_runs_are_byte_identical_with_built_at_removed(self):
        # Section 6: byte-identical with registry_built_at removed,
        # candidate_set_id included. built_at is provisioning provenance and
        # identical within one database, so here even that holds.
        arguments = POWERTRAIN | {"entity_kind": "signal", "term": "SAMPLE_SIG_TEMPERATURE"}
        self.assertEqual(self.answer(arguments), self.answer(arguments))

    def test_no_surrogate_key_and_no_attribute_reaches_a_candidate(self):
        result = self.answer(POWERTRAIN | {"entity_kind": "signal", "term": "SAMPLE_SIG_TEMPERATURE"})
        for candidate in result.candidates:
            fields = candidate.digest_fields()
            self.assertFalse(any(k.endswith("_id") for k in fields))
            self.assertNotIn("scale_factor", fields)


class DX016OverATestBuiltTree(unittest.TestCase):
    """More than k entities at one tier. Unreachable from the registered
    occurrences (#141, #143): the largest kind-in-snapshot group is five
    signals. The tree the test builds adds eleven signal occurrences under
    one parent in one snapshot and approves them all, so a term whose one
    token every added key contains matches eleven entities at tier 4."""

    DATABASE = "mvp_test_discovery_016"
    PARENT = POWERTRAIN | {"message_key": "SAMPLE_MSG_DIAGNOSTIC_EVENT"}

    @classmethod
    def setUpClass(cls):
        cls.directory = pathlib.Path(tempfile.mkdtemp())
        fixtures = cls.directory / "fixtures"
        shutil.copytree(support.FIXTURES, fixtures)
        signals = [json.loads(l) for l in (fixtures / "signal_occurrence.jsonl").read_text().splitlines()]
        entities = [json.loads(l) for l in (fixtures / "registry" / "approved_entity.jsonl").read_text().splitlines()]
        for i in range(11):
            key = f"SAMPLE_SIG_PROBE_{i:02d}"
            signals.append({"message": cls.PARENT, "signal_key": key, "unit_label": None, "scale_factor": 1, "scale_offset": 0, "bit_width": 8, "bit_offset": 0})
            entities.append({"entity_kind": "signal", "reference": cls.PARENT | {"signal_key": key}, "approval_reference": f"SAMPLE_APPROVAL_PROBE_{i:02d}", "approved_at": "2026-03-05T00:00:00Z"})
        (fixtures / "signal_occurrence.jsonl").write_text("".join(json.dumps(r) + "\n" for r in signals))
        (fixtures / "registry" / "approved_entity.jsonl").write_text("".join(json.dumps(r) + "\n" for r in entities))
        support.build(cls.DATABASE, fixtures)

    @classmethod
    def tearDownClass(cls):
        support.drop(cls.DATABASE)
        shutil.rmtree(cls.directory, ignore_errors=True)

    def test_dx_016_exactly_ten_are_listed_and_the_truncation_is_recorded(self):
        result = discovery(self.DATABASE).execute(DiscoveryRequest(arguments=POWERTRAIN | {"entity_kind": "signal", "term": "probe"}))
        self.assertIs(result.status, DiscoveryStatus.CANDIDATES)
        self.assertEqual(len(result.candidates), K)
        self.assertEqual([c.rank for c in result.candidates], list(range(1, K + 1)))
        self.assertTrue(all(c.match_tier == 4 for c in result.candidates))
        self.assertEqual(result.evidence_bundle.row_count, 11)
        self.assertIn(DiscoveryLimitationKind.TRUNCATED_BY_LIMIT, [l.kind for l in result.limitations])
        # Byte order within the tier: PROBE_00 .. PROBE_09 listed, PROBE_10 cut.
        self.assertEqual(result.candidates[-1].reference.signal_key, "SAMPLE_SIG_PROBE_09")


if __name__ == "__main__":
    unittest.main(verbosity=2)
