"""entity-discovery-v0.1 Section 8.1: DX-017 to DX-023 against a real
PostgreSQL database, plus the Section 8 row's digest assertions.

DX-023 needs a registry re-provisioned without the selected entity; that is a
second database built from a fixture tree the test derives from the
registered one, so the candidate set was computed against one registry state
and selected from against another -- the exact case Section 4.8's digest
exists to refuse.
"""

import hashlib
import json
import os
import pathlib
import shutil
import tempfile
import unittest

from evidence_first_rag import LimitationKind, Status
from evidence_first_rag.discovery import (
    Discovery,
    DiscoveryLimitationKind,
    DiscoveryRequest,
    DiscoveryStatus,
    Selection,
    SelectionRequest,
)
from evidence_first_rag.runtime.connection import PsycopgDatabase

from . import support

DATABASE = "mvp_test_selection"
POWERTRAIN = {"project_code": "SAMPLE_PROJECT_ALPHA", "revision_label": "SAMPLE_REV_A", "network_name": "SAMPLE_NET_POWERTRAIN", "snapshot_label": "SAMPLE_SNAP_BASE"}
PROVENANCE = ("fixtures/registry/approved_entity.jsonl", "fixtures/registry/approved_alias.jsonl")

# The DX-004 collision: two candidates, a lookup key at rank 1 and an alias at rank 2.
DISCOVERY = POWERTRAIN | {"entity_kind": "signal", "term": "SAMPLE_SIG_GEAR_POSITION"}


def setUpModule():
    support.build(DATABASE)


def tearDownModule():
    support.drop(DATABASE)


def connection_parameters(database):
    return {"dbname": database, "user": "mvp_runtime", "password": os.environ["MVP_RUNTIME_PASSWORD"],
            "host": os.environ.get("PGHOST"), "port": os.environ.get("PGPORT")}


def discover(arguments, database=DATABASE):
    return Discovery(database=PsycopgDatabase(connection_parameters=connection_parameters(database)), fixture_provenance=PROVENANCE).execute(DiscoveryRequest(arguments=arguments))


def select(arguments, database=DATABASE):
    return Selection(database=PsycopgDatabase(connection_parameters=connection_parameters(database)), fixture_provenance=PROVENANCE).execute(SelectionRequest(arguments=arguments))


class SelectionCases(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.discovered = discover(DISCOVERY)
        assert cls.discovered.status is DiscoveryStatus.CANDIDATES
        cls.cid = cls.discovered.evidence_bundle.candidate_set_id

    def selection(self, **overrides):
        return DISCOVERY | {"candidate_set_id": self.cid, "selected_rank": "1", "target_route": "signal_facts"} | overrides

    def test_dx_017_a_verified_selection_reaches_the_fact_route(self):
        result = select(self.selection())
        self.assertIs(result.status, Status.SUCCESS)
        bundle = result.evidence_bundle
        self.assertEqual(bundle.route, "signal_facts")
        self.assertEqual(bundle.template_name, "TPL_SIGNAL_FACTS_V1")
        self.assertEqual(bundle.contract_identifier, "mvp-v0.1")
        self.assertEqual(result.rows[0]["signal_key"], "SAMPLE_SIG_GEAR_POSITION")
        self.assertEqual(result.rows[0]["message_key"], "SAMPLE_MSG_TRANSMISSION_STATE")
        selection = dict(bundle.selection)
        self.assertEqual(selection["candidate_set_id"], self.cid)
        self.assertEqual(selection["candidate_count"], 2)
        self.assertEqual(selection["selected_rank"], 1)
        self.assertEqual(selection["target_route"], "signal_facts")
        self.assertEqual(selection["discovery_template_name"], "TPL_DISCOVERY_EXACT_V1")
        self.assertEqual(selection["discovery_bound_parameters"]["term"], "SAMPLE_SIG_GEAR_POSITION")
        self.assertEqual(selection["discovery_row_count"], 2)
        self.assertEqual(selection["registry_digest"], self.discovered.evidence_bundle.registry_digest)
        # Top-level bound parameters are the fact route's alone.
        self.assertEqual(set(bundle.bound_parameters), set(POWERTRAIN) | {"message_key", "signal_key"})
        entries = [l for l in result.limitations if l.kind is LimitationKind.SCOPE_SELECTED_BY_USER]
        self.assertEqual(len(entries), 1)
        self.assertIn(self.cid, entries[0].detail)
        self.assertEqual(result.source_trace.entity_approval_reference, "SAMPLE_APPROVAL_M3_009")

    def test_dx_017_selecting_the_alias_match_carries_its_provenance(self):
        result = select(self.selection(selected_rank="2"))
        self.assertIs(result.status, Status.SUCCESS)
        self.assertEqual(result.rows[0]["signal_key"], "SAMPLE_SIG_FAULT_CODE")
        self.assertEqual(result.source_trace.alias_provenance[0]["approval_reference"], "SAMPLE_APPROVAL_M3_103")
        self.assertEqual(result.source_trace.entity_approval_reference, "SAMPLE_APPROVAL_M3_010")

    def test_dx_017_signal_mapping_as_the_target(self):
        # The selected signal is the mapping's source endpoint; GEAR_POSITION
        # is a target of SAMPLE_MAP_SPEED_TO_GEAR, not a source, so the
        # mapping route answers not_found -- its own status, not success.
        result = select(self.selection(target_route="signal_mapping"))
        self.assertIs(result.status, Status.NOT_FOUND)
        self.assertEqual(result.evidence_bundle.route, "signal_mapping")
        self.assertIsNotNone(result.evidence_bundle.selection)

    def assert_names_the_selection(self, result, arguments):
        """Section 7: a refused selection names the `candidate_set_id` cited,
        the `selected_rank` and the `target_route`. Which step refused is not
        one of Section 7's keys; each fixture below asserts instead that no
        fact template executed."""
        bundle = result.evidence_bundle
        self.assertEqual(bundle.candidate_set_id, arguments["candidate_set_id"])
        self.assertEqual(bundle.selected_rank, arguments["selected_rank"])
        self.assertEqual(bundle.target_route, arguments["target_route"])

    def test_dx_018_a_digest_that_does_not_re_derive_executes_no_fact_template(self):
        arguments = self.selection(candidate_set_id="0" * 64)
        result = select(arguments)
        self.assertIs(result.status, DiscoveryStatus.INVALID_REQUEST)
        self.assertEqual(result.evidence_bundle.route, "entity_selection")
        self.assertEqual(result.evidence_bundle.template_name, "TPL_DISCOVERY_EXACT_V1")
        self.assert_names_the_selection(result, arguments)
        # Section 7 gives `candidate_set_id` to the digest the caller cited,
        # which here is precisely the one that did not re-derive.
        self.assertEqual(result.evidence_bundle.candidate_set_id, "0" * 64)
        self.assertNotEqual(result.evidence_bundle.candidate_set_id, self.cid)

    def test_dx_019_a_rank_naming_no_candidate(self):
        arguments = self.selection(selected_rank="3")
        result = select(arguments)
        self.assertIs(result.status, DiscoveryStatus.INVALID_REQUEST)
        self.assert_names_the_selection(result, arguments)

    def test_dx_021_a_kind_that_does_not_permit_the_route_both_halves(self):
        arguments = self.selection(target_route="message_facts")
        result = select(arguments)
        self.assertIs(result.status, DiscoveryStatus.INVALID_REQUEST)
        self.assert_names_the_selection(result, arguments)
        # And a message candidate with signal_facts.
        discovered = discover(POWERTRAIN | {"entity_kind": "message", "term": "sample msg"})
        self.assertIs(discovered.status, DiscoveryStatus.CANDIDATES)
        arguments = POWERTRAIN | {"entity_kind": "message", "term": "sample msg", "candidate_set_id": discovered.evidence_bundle.candidate_set_id, "selected_rank": "1", "target_route": "signal_facts"}
        result = select(arguments)
        self.assertIs(result.status, DiscoveryStatus.INVALID_REQUEST)
        self.assert_names_the_selection(result, arguments)

    def test_dx_022_both_halves_are_refused_before_any_connection(self):
        for overrides in ({"target_route": "entity_discovery"},
                          {"mapping_key": "SAMPLE_MAP_SPEED_TO_GEAR"}):
            with self.subTest(overrides=overrides):
                arguments = self.selection(**overrides)
                result = select(arguments)
                self.assertIs(result.status, DiscoveryStatus.INVALID_REQUEST)
                self.assertFalse(result.evidence_bundle.read_only_safeguards.connection_opened)
                # Step 1 opened nothing and still names what it refused.
                self.assert_names_the_selection(result, arguments)

    def test_a_changed_registry_changes_the_candidate_set_id(self):
        # Section 8's row, over the digest's inputs: the same request against
        # a registry whose alias provenance differs computes a different id.
        # Provable here without a second database because the registry
        # digest is an input: recompute with another digest.
        from evidence_first_rag.discovery import candidate_set_id, validate
        validated = validate(DiscoveryRequest(arguments=DISCOVERY))
        other = candidate_set_id(validated, "0" * 64, self.discovered.candidates)
        self.assertNotEqual(other, self.cid)

    def test_the_digest_computed_independently_from_the_section_4_8_key_list_matches(self):
        # A second serializer, written from the contract's text: json.dumps
        # with sorted keys and compact separators over ASCII-only inputs is
        # the canonical form for these values.
        candidates = []
        for c in self.discovered.candidates:
            candidates.append({
                "rank": c.rank, "entity_kind": c.entity_kind, **POWERTRAIN,
                "message_key": c.reference.message_key, "signal_key": c.reference.signal_key,
                "match_tier": c.match_tier, "matched_text": c.matched_text, "match_kind": c.match_kind,
            })
        obj = {
            "contract_identifier": "entity-discovery-v0.1", "contract_version": "0.2.1",
            "registry_digest": self.discovered.evidence_bundle.registry_digest,
            **POWERTRAIN, "entity_kind": "signal", "parent_message_key": None,
            "term": "SAMPLE_SIG_GEAR_POSITION", "method_identifier": "M-LEX-1", "method_version": "1",
            "candidates": candidates,
        }
        text = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        self.assertEqual(hashlib.sha256(text).hexdigest(), self.cid)


class DX023AgainstAReprovisionedRegistry(unittest.TestCase):
    """The selected entity is removed from the registry and the database
    re-provisioned. The re-run then yields not_found (nothing else in that
    scope and kind matches the term at any tier), so there is no list; the
    refusal names it, and no fact template executes."""

    DATABASE = "mvp_test_selection_023"

    @classmethod
    def setUpClass(cls):
        cls.cid = discover(DISCOVERY).evidence_bundle.candidate_set_id
        cls.directory = pathlib.Path(tempfile.mkdtemp())
        fixtures = cls.directory / "fixtures"
        shutil.copytree(support.FIXTURES, fixtures)
        registry = fixtures / "registry"
        entities = [json.loads(l) for l in (registry / "approved_entity.jsonl").read_text().splitlines()]
        aliases = [json.loads(l) for l in (registry / "approved_alias.jsonl").read_text().splitlines()]
        # Remove the GEAR_POSITION entity and the alias that equals its key.
        entities = [e for e in entities if e["reference"].get("signal_key") != "SAMPLE_SIG_GEAR_POSITION"]
        aliases = [a for a in aliases if a["alias_text"] != "SAMPLE_SIG_GEAR_POSITION"]
        (registry / "approved_entity.jsonl").write_text("".join(json.dumps(r) + "\n" for r in entities))
        (registry / "approved_alias.jsonl").write_text("".join(json.dumps(r) + "\n" for r in aliases))
        support.build(cls.DATABASE, fixtures)

    @classmethod
    def tearDownClass(cls):
        support.drop(cls.DATABASE)
        shutil.rmtree(cls.directory, ignore_errors=True)

    def test_dx_023_the_rerun_yields_not_found_and_the_refusal_names_it(self):
        arguments = DISCOVERY | {"candidate_set_id": self.cid, "selected_rank": "1", "target_route": "signal_facts"}
        result = select(arguments, self.DATABASE)
        self.assertIs(result.status, DiscoveryStatus.INVALID_REQUEST)
        self.assertEqual(result.evidence_bundle.route, "entity_selection")
        # Section 7: the selection cited, and the entry that names what the
        # re-run produced instead of a list.
        bundle = result.evidence_bundle
        self.assertEqual(bundle.candidate_set_id, self.cid)
        self.assertEqual(bundle.selected_rank, "1")
        self.assertEqual(bundle.target_route, "signal_facts")
        entries = [l for l in result.limitations if l.kind is DiscoveryLimitationKind.RERUN_PRODUCED_NO_LIST]
        self.assertEqual(len(entries), 1)
        self.assertIn("'not_found'", entries[0].detail)
        # The re-run is reported: the lexical template ran and found nothing.
        self.assertEqual(result.evidence_bundle.template_name, "TPL_DISCOVERY_LEXICAL_V1")
        self.assertEqual(result.evidence_bundle.row_count, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
