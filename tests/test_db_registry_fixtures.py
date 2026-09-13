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


def _reserved_absent():
    """`RESERVED_ABSENT` from `scripts/checks/validate_fixtures.py`.

    Loaded by path rather than imported, because `scripts/` is not a package
    on the path. Reading it there rather than restating it here keeps one
    list: `fixtures/README.md` says the reservation lives in the validator,
    and a Section 4.10 `Q-NOMATCH` pool that copied the names could pass
    while the validator no longer enforced their absence.
    """
    import importlib.util

    path = REPOSITORY / "scripts" / "checks" / "validate_fixtures.py"
    specification = importlib.util.spec_from_file_location("_validate_fixtures", path)
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module.RESERVED_ABSENT


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
        self.assertEqual(len(parsed.entities), 17)
        self.assertEqual(len(parsed.aliases), 6)

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

    def test_a_timestamp_with_an_offset_is_refused(self):
        # Section 4.2's form is UTC with a trailing Z. An offset would be
        # discarded by the timestamp cast and re-emitted as Z in the digest,
        # nine hours from the instant the file stated (review N7 on #142).
        rows = _rows("approved_entity")
        rows[0]["approved_at"] = "2026-03-05T09:00:00+09:00"
        self.write("approved_entity", rows)
        self.assert_refused("RFC 3339")

    def test_a_timestamp_that_is_not_a_date_is_refused_before_any_transaction(self):
        rows = _rows("approved_alias")
        rows[0]["approved_at"] = "not-a-date"
        self.write("approved_alias", rows)
        self.assert_refused("RFC 3339")

    def test_a_timestamp_with_an_impossible_date_is_refused(self):
        rows = _rows("approved_alias")
        rows[0]["approved_at"] = "2026-02-30T00:00:00Z"
        self.write("approved_alias", rows)
        self.assert_refused("approved_at")

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


class TheRowsCanCarryASection410EvaluationSet(unittest.TestCase):
    """Section 4.10's authoring rules are satisfiable from these files.

    Rule 4 asks for five cases in each of eight classes and rule 6, as
    `discovery/evaluation.py` implements it, makes every case term distinct
    after the Section 4.5 normalization. Four classes draw their term from a
    name the registry holds, or from one reserved as absent, so those four
    are the ones the fixture tree can make unsatisfiable. Nothing here
    registers a case -- Section 8.3 does that, and these are pools rather
    than sets -- but a row removed from `fixtures/` silently shrinks a pool, and a
    class that can no longer reach five is a registration that cannot be
    authored. These four assertions are where that is noticed.

    The pools are disjoint by construction: a key approved in two snapshots
    is `Q-COLLIDE`'s and is excluded from `Q-EXACT`'s, because one term can
    serve only one case.
    """

    MINIMUM = 5  # discovery.evaluation.MINIMUM_PER_CLASS, Section 4.10 rule 4.

    @classmethod
    def setUpClass(cls):
        cls.parsed = registry_fixtures.read(REGISTERED)
        cls.mvp = fixtures.read(REGISTERED)

    def key_of(self, row):
        reference = row.reference
        return reference.message_key if row.entity_kind == "message" else reference.signal_key

    def resolving(self, text, kind, scope):
        """The approved entities a term equal to `text` reaches at tier 1 or 2.

        Section 4.5's table: tier 1 is a `lookup_key` equal byte for byte,
        tier 2 an alias equal byte for byte. Section 4.7 resolves only when
        the two together name exactly one entity.
        """
        reached = set()
        for row in self.parsed.entities:
            if row.entity_kind == kind and row.reference.scope == scope and self.key_of(row) == text:
                reached.add(row.reference)
        for alias in self.parsed.aliases:
            if alias.entity_kind == kind and alias.reference.scope == scope and alias.alias_text == text:
                reached.add(alias.reference)
        return reached

    def snapshots_of_each_key(self):
        scopes = {}
        for row in self.parsed.entities:
            scopes.setdefault((row.entity_kind, self.key_of(row)), set()).add(row.reference.scope)
        return scopes

    def test_five_lookup_keys_can_carry_a_q_exact_case(self):
        # A Q-EXACT case registers `resolved`, so its key must reach exactly
        # one entity in its scope and kind. A key approved in more than one
        # snapshot is reserved for Q-COLLIDE.
        scopes = self.snapshots_of_each_key()
        pool = {
            self.key_of(row)
            for row in self.parsed.entities
            if len(scopes[(row.entity_kind, self.key_of(row))]) == 1
            and len(self.resolving(self.key_of(row), row.entity_kind, row.reference.scope)) == 1
        }
        self.assertGreaterEqual(
            len(pool), self.MINIMUM,
            f"Q-EXACT can draw {sorted(pool)}; Section 4.10 rule 4 needs {self.MINIMUM}",
        )

    def test_five_lookup_keys_can_carry_a_q_collide_case(self):
        # "A fully scoped request for a key that exists in two snapshots",
        # registering `resolved` in the named one -- so the key must be
        # approved in two snapshots and resolve in at least one of them.
        pool = set()
        for (kind, key), scopes in self.snapshots_of_each_key().items():
            if len(scopes) < 2:
                continue
            if any(len(self.resolving(key, kind, scope)) == 1 for scope in scopes):
                pool.add(key)
        self.assertGreaterEqual(
            len(pool), self.MINIMUM,
            f"Q-COLLIDE can draw {sorted(pool)}; Section 4.10 rule 4 needs {self.MINIMUM}",
        )

    def test_five_alias_texts_can_carry_a_q_alias_case(self):
        # A Q-ALIAS case registers `resolved` too, so an alias that is also
        # another entity's lookup key -- DX-004 -- is not one of these.
        pool = {
            alias.alias_text
            for alias in self.parsed.aliases
            if len(self.resolving(alias.alias_text, alias.entity_kind, alias.reference.scope)) == 1
        }
        self.assertGreaterEqual(
            len(pool), self.MINIMUM,
            f"Q-ALIAS can draw {sorted(pool)}; Section 4.10 rule 4 needs {self.MINIMUM}",
        )

    def test_five_reserved_names_can_carry_a_q_nomatch_case(self):
        # Rule 1 makes a Q-NOMATCH term an identifier that is "reserved
        # [in the fixtures] as absent", and the class registers `not_found`,
        # which needs the term to match at no tier -- including tier 4, where
        # every token of the term must occur in some entity's match tokens.
        # The names are read from the one place `fixtures/README.md` says
        # reservation lives, so this test and the validator cannot disagree.
        reserved = _reserved_absent()
        pool = reserved.get("message_key", []) + reserved.get("signal_key", [])
        self.assertGreaterEqual(
            len(pool), self.MINIMUM,
            f"Q-NOMATCH can draw {sorted(pool)}; Section 4.10 rule 4 needs {self.MINIMUM}",
        )
        loaded = {r.reference.message_key for r in self.mvp.messages} | {
            r.reference.signal_key for r in self.mvp.signals
        }
        tokens = set()
        for row in self.parsed.entities:
            tokens.update(normalize(self.key_of(row)))
        for alias in self.parsed.aliases:
            tokens.update(normalize(alias.alias_text))
        for name in pool:
            self.assertNotIn(name, loaded, f"{name} is reserved as absent")
            self.assertFalse(
                set(normalize(name)) <= tokens,
                f"{name} would match at tier 4; every one of its tokens is a match token",
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
