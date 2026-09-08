"""Section 7: the three evidence structures and their empty-value rules."""

import pathlib
import re
import unittest

from evidence_first_rag import (
    COLLATION,
    CONTRACT_IDENTIFIER,
    CONTRACT_VERSION,
    EvidenceBundle,
    Limitation,
    LimitationKind,
    MappingProvenance,
    ProducingLayer,
    ReadOnlySafeguards,
    SourceTrace,
)

from .support import executed_bundle, scope, unexecuted_bundle


class TheBundleCitesThisContract(unittest.TestCase):
    def test_it_defaults_to_the_accepted_identifier_and_version(self):
        bundle = executed_bundle()
        self.assertEqual(bundle.contract_identifier, CONTRACT_IDENTIFIER)
        self.assertEqual(bundle.contract_version, CONTRACT_VERSION)

    def test_the_constants_match_section_1(self):
        self.assertEqual(CONTRACT_IDENTIFIER, "mvp-v0.1")
        self.assertEqual(CONTRACT_VERSION, "0.6.0")

    def test_the_version_constant_is_the_one_the_contract_document_declares(self):
        # The contract and the code have drifted before: 0.6.0 merged while
        # CONTRACT_VERSION still said 0.5.0, so every evidence bundle cited a
        # version the document no longer carried. This reads Section 1's own
        # version line and refuses the drift. Section 7 requires the bundle to
        # carry the version the code claims to satisfy; a constant nobody
        # compares against the document is a claim nobody checks.
        contract = pathlib.Path(__file__).resolve().parents[1] / "docs" / "contracts" / "mvp-v0.1.md"
        match = re.search(r"^\*\*Version:\*\* `(\d+\.\d+\.\d+)`", contract.read_text(), re.M)
        self.assertIsNotNone(match, "Section 1 of the contract has no **Version:** line")
        self.assertEqual(CONTRACT_VERSION, match.group(1))

    def test_it_records_the_section_6_collation(self):
        self.assertEqual(executed_bundle().collation, "C")
        self.assertEqual(COLLATION, "C")


class TheRouteField(unittest.TestCase):
    """`route` is an unconstrained non-empty string in this slice; the closed
    Section 4.5 route set is the routes slice's decision."""

    def test_it_must_be_a_non_empty_string(self):
        with self.assertRaises(ValueError):
            unexecuted_bundle(route="")


class WhenNoDatabaseWasOpened(unittest.TestCase):
    """Section 7's empty-value rules, and Section 5's reason for them."""

    def test_the_bundle_defaults_to_every_empty_value(self):
        bundle = unexecuted_bundle()
        self.assertEqual(bundle.template_name, "")
        self.assertEqual(bundle.template_version, "")
        self.assertEqual(dict(bundle.bound_parameters), {})
        self.assertIsNone(bundle.resolved_scope)
        self.assertEqual(bundle.row_count, 0)

    def test_it_refuses_a_template_name_or_version(self):
        for field in ("template_name", "template_version"):
            with self.subTest(field=field):
                with self.assertRaises(ValueError) as raised:
                    unexecuted_bundle(**{field: "TPL_MESSAGE_FACTS_V1"})
                self.assertIn("no database was opened", str(raised.exception))

    def test_it_refuses_a_resolved_scope(self):
        with self.assertRaises(ValueError):
            unexecuted_bundle(resolved_scope=scope())

    def test_it_refuses_the_arguments_a_rejected_proposal_carried(self):
        # Section 7: arguments that failed revalidation were never bound, and
        # recording them here would present a rejected proposal as a fact.
        with self.assertRaises(ValueError) as raised:
            unexecuted_bundle(bound_parameters={"project_code": "SAMPLE_PROJECT_ALPHA"})
        self.assertIn("no template executed", str(raised.exception))

    def test_it_refuses_a_row_count(self):
        with self.assertRaises(ValueError):
            unexecuted_bundle(row_count=1)


class TheReadOnlySafeguards(unittest.TestCase):
    def test_an_executed_bundle_records_the_runtime_role_and_transaction(self):
        safeguards = executed_bundle().read_only_safeguards
        self.assertTrue(safeguards.connection_opened)
        self.assertTrue(safeguards.read_only_transaction)
        self.assertNotEqual(safeguards.role_name, "")

    def test_an_unopened_connection_claims_no_transaction_or_role(self):
        for overrides in (
            {"read_only_transaction": True},
            {"role_name": "SAMPLE_RUNTIME_ROLE"},
        ):
            with self.subTest(overrides=overrides):
                values = {
                    "role_name": "",
                    "read_only_transaction": False,
                    "connection_opened": False,
                }
                values.update(overrides)
                with self.assertRaises(ValueError):
                    ReadOnlySafeguards(**values)

    def test_an_opened_connection_names_the_runtime_identity(self):
        # Section 7 requires the role name recorded, and Section 4.3 says every
        # connection is opened with the runtime identity. A connection reported
        # as opened under no role is missing evidence, not an empty value.
        with self.assertRaises(ValueError) as raised:
            ReadOnlySafeguards(
                role_name="", read_only_transaction=True, connection_opened=True
            )
        self.assertIn("runtime identity", str(raised.exception))

    def test_an_opened_connection_may_still_report_a_missing_transaction(self):
        # Left representable on purpose: Section 4.10 wants the refusal to come
        # from PostgreSQL, not an application guard, and check B3 exists to
        # catch a connection that was not read-only. Making it unconstructible
        # would lose the evidence rather than prevent the fault.
        safeguards = ReadOnlySafeguards(
            role_name="SAMPLE_RUNTIME_ROLE",
            read_only_transaction=False,
            connection_opened=True,
        )
        self.assertFalse(safeguards.read_only_transaction)

    def test_the_flags_are_bools_not_truthy_values(self):
        with self.assertRaises(ValueError):
            ReadOnlySafeguards(
                role_name="", read_only_transaction=0, connection_opened=0
            )


class TheBundleValidatesItsOwnFields(unittest.TestCase):
    def test_row_count_is_a_non_negative_int(self):
        for bad in (-1, 1.0, True, "1"):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    executed_bundle(row_count=bad)

    def test_bound_parameters_cannot_be_edited_through_the_caller(self):
        parameters = {"message_key": "SAMPLE_MSG_A"}
        bundle = executed_bundle(bound_parameters=parameters)
        parameters["message_key"] = "SAMPLE_MSG_B"
        self.assertEqual(bundle.bound_parameters["message_key"], "SAMPLE_MSG_A")

    def test_bound_parameters_are_named(self):
        with self.assertRaises(ValueError):
            executed_bundle(bound_parameters={1: "SAMPLE_MSG_A"})

    def test_the_safeguards_are_required(self):
        with self.assertRaises(TypeError):
            EvidenceBundle(route="message_facts")


class TheSourceTrace(unittest.TestCase):
    def test_it_defaults_to_empty_and_records_no_producing_layer(self):
        trace = SourceTrace()
        self.assertEqual(trace.contributing_scopes, ())
        self.assertEqual(trace.mapping_provenance, ())
        self.assertEqual(trace.fixture_provenance, ())
        self.assertIsNone(trace.producing_layer)

    def test_the_producing_layer_is_one_of_the_two(self):
        self.assertEqual(
            sorted(layer.value for layer in ProducingLayer), ["adapter", "runtime"]
        )
        with self.assertRaises(ValueError):
            SourceTrace(producing_layer="adapter")

    def test_mapping_provenance_identifies_all_three_scopes_separately(self):
        provenance = MappingProvenance(
            asserting_scope=scope(snapshot_label="SAMPLE_SNAP_ASSERTING"),
            source_endpoint_scope=scope(),
            target_endpoint_scope=scope(snapshot_label="SAMPLE_SNAP_TARGET"),
        )
        trace = SourceTrace(mapping_provenance=(provenance,))
        self.assertEqual(len(trace.mapping_provenance), 1)
        self.assertEqual(
            trace.mapping_provenance[0].asserting_scope.snapshot_label,
            "SAMPLE_SNAP_ASSERTING",
        )

    def test_a_scope_hole_cannot_reach_the_trace(self):
        with self.assertRaises(ValueError):
            SourceTrace(contributing_scopes=("SAMPLE_PROJECT_ALPHA",))

    def test_fixture_provenance_entries_are_named(self):
        trace = SourceTrace(fixture_provenance=("fixtures/message_occurrence.jsonl",))
        self.assertEqual(trace.fixture_provenance[0], "fixtures/message_occurrence.jsonl")
        with self.assertRaises(ValueError):
            SourceTrace(fixture_provenance=("",))


class TheLimitationEntries(unittest.TestCase):
    def test_the_five_kinds_are_section_7s_required_entries(self):
        self.assertEqual(
            sorted(kind.value for kind in LimitationKind),
            [
                "coverage_not_established",
                "entity_discovery_not_implemented",
                "scope_selected_by_user",
                "superseded_snapshot",
                "truncated_by_limit",
            ],
        )

    def test_an_entry_has_to_say_something(self):
        with self.assertRaises(ValueError):
            Limitation(kind=LimitationKind.TRUNCATED_BY_LIMIT, detail="")

    def test_an_unlisted_kind_cannot_be_constructed(self):
        with self.assertRaises(ValueError):
            LimitationKind("probably_fine")


if __name__ == "__main__":
    unittest.main(verbosity=2)
