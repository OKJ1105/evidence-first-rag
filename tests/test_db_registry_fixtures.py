"""entity-discovery-v0.1 Section 4.2's registry files: parsing with no
database, and the structural cases the registered rows must keep reachable.

Two jobs, because `scripts/checks/` is a protected path and the registry
files have no validator there. The first is the parser's own behaviour on a
file that is not well-formed, as tests/test_db_fixtures.py covers for the
mvp-v0.1 files. The second is what `validate_fixtures.py` does for those
files: assert that the rows still carry the structure each Section 8.1 case
depends on, naming the case, so that an edit that removes it fails here
rather than turning a discovery fixture green for the wrong reason.
"""

import json
import pathlib
import re
import shutil
import tempfile
import unittest

from evidence_first_rag.db import fixtures, registry_fixtures
from evidence_first_rag.discovery import normalize
from evidence_first_rag.references import MessageReference, SignalReference

REPOSITORY = pathlib.Path(__file__).resolve().parent.parent
REGISTERED = REPOSITORY / "fixtures"

SAMPLE_IDENTIFIER = re.compile(r"\ASAMPLE_[A-Za-z0-9_.\-]+\Z")

# Section 4.11 of mvp-v0.1 forbids surrogate keys in a fixture file; the
# registry's own are added to that list.
SURROGATE_KEYS = {
    "snapshot_id", "message_occurrence_id", "signal_occurrence_id",
    "approved_entity_id", "approved_alias_id", "entity_match_term_id",
    "asserting_snapshot_id",
}


def _rows(table):
    path = REGISTERED / registry_fixtures.SUBDIRECTORY / f"{table}.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _walk(value):
    if isinstance(value, dict):
        for key, inner in value.items():
            yield key, inner
            yield from _walk(inner)


class TheRegisteredFilesParse(unittest.TestCase):
    def test_both_files_have_rows(self):
        parsed = registry_fixtures.read(REGISTERED)
        self.assertEqual(len(parsed.entities), 12)
        self.assertEqual(len(parsed.aliases), 5)

    def test_the_two_table_names_are_section_4_2s(self):
        self.assertEqual(registry_fixtures.TABLES, ("approved_entity", "approved_alias"))

    def test_a_reference_comes_out_typed_by_kind(self):
        parsed = registry_fixtures.read(REGISTERED)
        for row in parsed.entities:
            with self.subTest(reference=row.reference):
                expected = MessageReference if row.entity_kind == "message" else SignalReference
                self.assertIsInstance(row.reference, expected)


class AFileThatIsNotWellFormed(unittest.TestCase):
    """Section 4.2: a partial load aborts. The parser is where the abort
    happens for a malformed file, before any transaction, naming the line."""

    def setUp(self):
        self.directory = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.directory, ignore_errors=True)
        shutil.copytree(REGISTERED, self.directory / "fixtures")
        self.registry = self.directory / "fixtures" / registry_fixtures.SUBDIRECTORY

    def write(self, table, rows):
        (self.registry / f"{table}.jsonl").write_text(
            "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
        )

    def assert_refused(self, fragment):
        with self.assertRaises(fixtures.FixtureError) as caught:
            registry_fixtures.read(self.directory / "fixtures")
        self.assertIn(fragment, str(caught.exception))

    def test_a_missing_file(self):
        (self.registry / "approved_alias.jsonl").unlink()
        self.assert_refused("missing")

    def test_a_blank_line(self):
        path = self.registry / "approved_entity.jsonl"
        path.write_text(path.read_text() + "\n\n", encoding="utf-8")
        self.assert_refused("blank line")

    def test_a_line_that_is_not_json(self):
        (self.registry / "approved_entity.jsonl").write_text('{"open\n', encoding="utf-8")
        self.assert_refused("not valid JSON")

    def test_an_entity_kind_outside_the_enumeration(self):
        # Section 4.2 rule 3.
        rows = _rows("approved_entity")
        rows[0]["entity_kind"] = "SAMPLE_KIND_OTHER"
        self.write("approved_entity", rows)
        self.assert_refused("rule 3")

    def test_an_alias_kind_outside_the_enumeration(self):
        rows = _rows("approved_alias")
        rows[0]["alias_kind"] = "nickname"
        self.write("approved_alias", rows)
        self.assert_refused("rule 3")

    def test_a_signal_key_on_a_message_reference(self):
        rows = _rows("approved_entity")
        message = next(r for r in rows if r["entity_kind"] == "message")
        message["reference"]["signal_key"] = "SAMPLE_SIG_ENGINE_SPEED"
        self.write("approved_entity", rows)
        self.assert_refused("signal_key")

    def test_a_signal_reference_missing_its_signal_key(self):
        rows = _rows("approved_entity")
        signal = next(r for r in rows if r["entity_kind"] == "signal")
        del signal["reference"]["signal_key"]
        self.write("approved_entity", rows)
        self.assert_refused("signal_key")

    def test_a_reference_with_a_partial_scope(self):
        rows = _rows("approved_alias")
        del rows[0]["reference"]["snapshot_label"]
        self.write("approved_alias", rows)
        self.assert_refused("snapshot_label")

    def test_a_missing_provenance_column(self):
        # Section 4.2: "A row missing any of them cannot be loaded."
        rows = _rows("approved_entity")
        del rows[0]["approval_reference"]
        self.write("approved_entity", rows)
        self.assert_refused("missing columns")

    def test_an_empty_approval_reference(self):
        rows = _rows("approved_alias")
        rows[0]["approval_reference"] = ""
        self.write("approved_alias", rows)
        self.assert_refused("approval_reference")

    def test_an_unexpected_column(self):
        rows = _rows("approved_entity")
        rows[0]["transmit_period_ms"] = 10
        self.write("approved_entity", rows)
        self.assert_refused("unexpected columns")


class TheRegisteredRowsKeepTheStructuralCasesReachable(unittest.TestCase):
    """Section 8.1, the data half. Each assertion names the case an edit
    would break. The cases that depend only on a request (DX-010 to
    DX-014) and on the selection path (DX-017 to DX-023) have no row here."""

    @classmethod
    def setUpClass(cls):
        cls.parsed = registry_fixtures.read(REGISTERED)
        cls.mvp = fixtures.read(REGISTERED)
        cls.loaded_messages = {row.reference for row in cls.mvp.messages}
        cls.loaded_signals = {row.reference for row in cls.mvp.signals}
        cls.approved = {(r.entity_kind, r.reference) for r in cls.parsed.entities}

    def entities(self, kind, scope):
        return [
            r.reference for r in self.parsed.entities
            if r.entity_kind == kind and r.reference.scope == scope
        ]

    def aliases_of(self, reference):
        return [a for a in self.parsed.aliases if a.reference == reference]

    def test_every_identifier_uses_the_sample_convention(self):
        # Section 8.1: "Every fixture uses SAMPLE_* identifiers only."
        for table in registry_fixtures.TABLES:
            for row in _rows(table):
                for key, value in _walk(row):
                    if key == "approved_at" or not isinstance(value, str):
                        continue
                    if key in ("entity_kind", "alias_kind"):
                        continue
                    with self.subTest(table=table, key=key, value=value):
                        self.assertRegex(value, SAMPLE_IDENTIFIER)

    def test_no_surrogate_key_appears_in_a_file(self):
        for table in registry_fixtures.TABLES:
            for row in _rows(table):
                for key, _ in _walk(row):
                    self.assertNotIn(key, SURROGATE_KEYS, table)

    def test_every_approved_occurrence_is_loaded_by_the_mvp_fixtures(self):
        # Section 4.1's foreign keys, checked at the file level so the
        # failure names the row rather than a constraint.
        for row in self.parsed.entities:
            loaded = self.loaded_messages if row.entity_kind == "message" else self.loaded_signals
            with self.subTest(reference=row.reference):
                self.assertIn(row.reference, loaded)

    def test_every_alias_names_an_approved_entity_and_its_own_snapshot(self):
        # Section 4.2 rule 1, at the file level.
        for alias in self.parsed.aliases:
            with self.subTest(alias=alias.alias_text):
                self.assertIn((alias.entity_kind, alias.reference), self.approved)
                self.assertEqual(alias.asserting_scope, alias.reference.scope)

    def test_no_entity_is_approved_twice(self):
        references = [(r.entity_kind, r.reference) for r in self.parsed.entities]
        self.assertEqual(len(references), len(set(references)))

    def test_no_alias_text_repeats_on_one_entity(self):
        pairs = [(a.reference, a.alias_text) for a in self.parsed.aliases]
        self.assertEqual(len(pairs), len(set(pairs)))

    def test_every_match_text_has_a_token(self):
        # Section 4.2 rule 5.
        for row in self.parsed.entities:
            key = row.reference.message_key if row.entity_kind == "message" else row.reference.signal_key
            self.assertTrue(normalize(key), key)
        for alias in self.parsed.aliases:
            self.assertTrue(normalize(alias.alias_text), alias.alias_text)

    # --- The cases ---------------------------------------------------------

    def scope(self, revision="SAMPLE_REV_A", network="SAMPLE_NET_POWERTRAIN", snapshot="SAMPLE_SNAP_BASE"):
        from evidence_first_rag.references import SnapshotScope
        return SnapshotScope(
            project_code="SAMPLE_PROJECT_ALPHA", revision_label=revision,
            network_name=network, snapshot_label=snapshot,
        )

    def test_dx_001_a_message_key_is_approved_and_unique_in_its_scope(self):
        keys = [r.message_key for r in self.entities("message", self.scope())]
        self.assertIn("SAMPLE_MSG_ENGINE_STATUS", keys)
        self.assertEqual(keys.count("SAMPLE_MSG_ENGINE_STATUS"), 1)
        # And no alias in that scope and kind equals it, or E(T) would hold
        # two entities and the case would be DX-004 instead.
        for alias in self.parsed.aliases:
            if alias.entity_kind == "message" and alias.reference.scope == self.scope():
                self.assertNotEqual(alias.alias_text, "SAMPLE_MSG_ENGINE_STATUS", "DX-001")

    def test_dx_002_and_dx_003_an_approved_alias_and_a_spelling_variant_exist(self):
        kinds = {a.alias_kind for a in self.parsed.aliases}
        self.assertIn("approved_alias", kinds, "DX-002")
        self.assertIn("spelling_variant", kinds, "DX-003")

    def test_dx_004_a_lookup_key_is_another_entitys_alias_in_the_same_scope_and_kind(self):
        # Section 4.7's first collision. Section 4.1 refuses a unique
        # constraint on alias_text alone precisely so this row can exist.
        found = False
        for alias in self.parsed.aliases:
            for entity in self.parsed.entities:
                if entity.entity_kind != alias.entity_kind or entity.reference.scope != alias.reference.scope:
                    continue
                if entity.reference == alias.reference:
                    continue
                key = entity.reference.message_key if entity.entity_kind == "message" else entity.reference.signal_key
                if key == alias.alias_text:
                    found = True
        self.assertTrue(found, "DX-004: no lookup key equals another entity's alias in one scope and kind")

    def test_dx_005_one_signal_key_is_approved_under_two_parents_in_one_snapshot(self):
        # Section 4.7's second collision, and Section 4.3's reason for
        # parent_message_key being optional.
        signals = self.entities("signal", self.scope())
        parents = {}
        for reference in signals:
            parents.setdefault(reference.signal_key, set()).add(reference.message_key)
        self.assertTrue(any(len(p) > 1 for p in parents.values()), "DX-005")

    def test_dx_006_the_same_message_key_is_approved_in_two_snapshots(self):
        by_key = {}
        for row in self.parsed.entities:
            if row.entity_kind == "message":
                by_key.setdefault(row.reference.message_key, set()).add(row.reference.scope)
        self.assertTrue(any(len(scopes) > 1 for scopes in by_key.values()), "DX-006")

    def test_dx_007_a_lookup_key_has_a_case_only_variant_that_is_not_registered(self):
        # A term differing only by case reaches tier 3 only if no alias
        # equals the lower-cased form byte for byte -- otherwise it would be
        # tier 2 and resolve.
        texts = {a.alias_text for a in self.parsed.aliases}
        self.assertNotIn("sample_msg_engine_status", texts, "DX-007")

    def test_dx_008_a_descriptive_term_is_contained_in_an_entitys_tokens_at_no_higher_tier(self):
        term = normalize("engine speed")
        matching = [
            r for r in self.parsed.entities
            if r.entity_kind == "signal" and r.reference.scope == self.scope()
            and set(term) <= set(normalize(r.reference.signal_key))
        ]
        self.assertEqual(len(matching), 1, "DX-008: exactly one tier-4 target")
        # And not tier 3: the term is not the whole token list.
        self.assertNotEqual(normalize(matching[0].reference.signal_key), term)

    def test_dx_015_a_loaded_occurrence_is_absent_from_the_registry_in_each_kind(self):
        # The fixture that proves the registry is an allowlist, not a
        # mirror of the loaded data.
        unapproved_messages = self.loaded_messages - {r for k, r in self.approved if k == "message"}
        unapproved_signals = self.loaded_signals - {r for k, r in self.approved if k == "signal"}
        self.assertTrue(unapproved_messages, "DX-015 (message)")
        self.assertTrue(unapproved_signals, "DX-015 (signal)")
        # In a snapshot that also holds approved entities, so the case is
        # "absent from the registry" and not "absent from the data".
        approved_scopes = {r.scope for _, r in self.approved}
        self.assertTrue({r.scope for r in unapproved_messages} & approved_scopes)

    def test_dx_020_an_alias_is_asserted_by_a_superseded_snapshot(self):
        superseded = {row.scope for row in self.mvp.snapshots if row.superseded_by is not None}
        self.assertTrue(
            any(a.asserting_scope in superseded for a in self.parsed.aliases), "DX-020"
        )

    def test_dx_016_is_recorded_as_unreachable_from_these_rows(self):
        # Section 4.6 counts entities, not aliases, and no kind-in-snapshot
        # group of the mvp-v0.1 occurrences reaches eleven. This test pins
        # that fact so that the day it changes -- more occurrences are
        # registered -- the discovery slice knows DX-016 became reachable
        # from the tree. See #141.
        groups = {}
        for row in self.parsed.entities:
            groups.setdefault((row.entity_kind, row.reference.scope), 0)
            groups[(row.entity_kind, row.reference.scope)] += 1
        self.assertLess(max(groups.values()), 11)


if __name__ == "__main__":
    unittest.main(verbosity=2)
