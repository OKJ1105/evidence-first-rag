"""entity-discovery-v0.1 Section 4.8: the selection path's seven steps, over
recorded rows.

Every refusal asserts that no fact template executed -- the recorded calls
name what ran -- and every dispatch asserts that the mvp-v0.1 result came
back with exactly the additions Section 4.8 enumerates and nothing else.
"""

import unittest

from evidence_first_rag import LimitationKind, ProducingLayer, Status
from evidence_first_rag.discovery import (
    Discovery,
    DiscoveryLimitationKind,
    DiscoveryRequest,
    DiscoveryStatus,
    Selection,
    SelectionRequest,
)
from evidence_first_rag.discovery.request import DiscoveryRefusal
from evidence_first_rag.discovery.selection import allowed_parameters, validate

from .discovery_support import BASE, MESSAGE, SIGNAL, database, discovery_row
from .runtime_support import message_row, signal_row

PROVENANCE = ("fixtures/registry/approved_entity.jsonl",)

TWO_SIGNALS = (
    discovery_row(entity_kind="signal", message_key="SAMPLE_MSG_TRANSMISSION_STATE", signal_key="SAMPLE_SIG_GEAR_POSITION"),
    discovery_row(entity_kind="signal", message_key="SAMPLE_MSG_DIAGNOSTIC_EVENT", signal_key="SAMPLE_SIG_FAULT_CODE",
                  match_tier=2, match_kind="approved_alias", match_text="SAMPLE_SIG_GEAR_POSITION"),
)
DISCOVERY = SIGNAL | {"term": "SAMPLE_SIG_GEAR_POSITION"}


def digest_for(arguments, **rows):
    """The candidate_set_id a discovery over these rows produces."""
    db = database(**rows)
    return Discovery(database=db).execute(DiscoveryRequest(arguments=arguments)).evidence_bundle.candidate_set_id


def select(arguments, **rows):
    rows.setdefault("exact", TWO_SIGNALS)
    rows.setdefault("TPL_SIGNAL_FACTS_V1", ())
    facts = rows.pop("TPL_SIGNAL_FACTS_V1")
    mapping = rows.pop("TPL_SIGNAL_MAPPING_V1", ())
    message = rows.pop("TPL_MESSAGE_FACTS_V1", ())
    db = database(**rows)
    db.rows["TPL_SIGNAL_FACTS_V1"] = tuple(facts)
    db.rows["TPL_SIGNAL_MAPPING_V1"] = tuple(mapping)
    db.rows["TPL_MESSAGE_FACTS_V1"] = tuple(message)
    result = Selection(database=db, fixture_provenance=PROVENANCE).execute(SelectionRequest(arguments=arguments))
    return db, result


def fact_templates_ran(db):
    return [name for name, _ in db.calls if name in ("TPL_MESSAGE_FACTS_V1", "TPL_SIGNAL_FACTS_V1", "TPL_SIGNAL_MAPPING_V1")]


class TheAllowlist(unittest.TestCase):
    def test_it_is_the_discovery_arguments_plus_the_four(self):
        self.assertEqual(
            set(allowed_parameters()),
            set(BASE) | {"entity_kind", "term", "parent_message_key", "candidate_set_id", "selected_rank", "target_route", "mapping_key"},
        )

    def test_a_parameter_naming_a_method_is_refused(self):
        # Section 4.9: a method is not an argument. Section 8's row.
        db, result = select(DISCOVERY | {"candidate_set_id": "a" * 64, "selected_rank": "1", "target_route": "signal_facts", "method_identifier": "M-LEX-1"})
        self.assertIs(result.status, DiscoveryStatus.INVALID_REQUEST)
        self.assertEqual(db.sessions, 0)


    def test_an_unknown_argument_is_refused_against_this_routes_own_allowlist(self):
        # Section 4.8 gives `entity_selection` its own argument table. Leaving
        # the check to the discovery validator would still refuse, but against
        # Section 4.3's shorter list and in that route's name, so a caller
        # reading the refusal is told the wrong table.
        arguments = DISCOVERY | {"candidate_set_id": "a" * 64, "selected_rank": "1", "target_route": "signal_facts", "snapshot_id": "SAMPLE"}
        db, result = select(arguments)
        self.assertIs(result.status, DiscoveryStatus.INVALID_REQUEST)
        self.assertEqual(db.sessions, 0)
        # A refusal before any connection carries no limitations, so the
        # allowlist it was measured against is asserted at the validator.
        with self.assertRaises(DiscoveryRefusal) as raised:
            validate(SelectionRequest(arguments=arguments))
        self.assertIn("entity_selection", raised.exception.detail)
        for name in ("candidate_set_id", "selected_rank", "target_route", "mapping_key"):
            self.assertIn(name, raised.exception.detail)


class StepOneOpensNoConnection(unittest.TestCase):
    def assert_refused_closed(self, arguments, fragment):
        db, result = select(arguments)
        bundle = result.evidence_bundle
        self.assertIs(result.status, DiscoveryStatus.INVALID_REQUEST)
        self.assertEqual(bundle.route, "entity_selection")
        self.assertEqual(db.sessions, 0)
        self.assertFalse(bundle.read_only_safeguards.connection_opened)
        # Section 7: a refusal that opened nothing still names the selection
        # it refused -- the caller's citation is not something the runtime
        # bound, so the no-connection empty-value rule does not reach it. A
        # result that named none of the three could not be traced back to the
        # request that produced it.
        for name in ("candidate_set_id", "selected_rank", "target_route"):
            self.assertEqual(getattr(bundle, name), arguments.get(name, ""))
        with self.assertRaises(Exception) as raised:
            validate(SelectionRequest(arguments=arguments))
        self.assertIn(fragment, str(raised.exception))

    def test_dx_022_a_target_route_outside_the_three(self):
        self.assert_refused_closed(DISCOVERY | {"candidate_set_id": "a" * 64, "selected_rank": "1", "target_route": "entity_discovery"}, "target_route")

    def test_dx_022_a_mapping_key_without_signal_mapping(self):
        self.assert_refused_closed(DISCOVERY | {"candidate_set_id": "a" * 64, "selected_rank": "1", "target_route": "signal_facts", "mapping_key": "SAMPLE_MAP_X"}, "mapping_key")

    def test_a_missing_selection_argument(self):
        self.assert_refused_closed(DISCOVERY | {"candidate_set_id": "a" * 64, "target_route": "signal_facts"}, "missing")

    def test_a_rank_that_is_not_a_positive_integer(self):
        # "²" and "٣" are `str.isdigit()` but not ASCII: the first
        # raises in `int()`, the second would smuggle a rank past a runtime
        # whose comparisons are byte-defined.
        for rank in ("0", "-1", "one", "1.5", "²", "٣"):
            with self.subTest(rank=rank):
                self.assert_refused_closed(DISCOVERY | {"candidate_set_id": "a" * 64, "selected_rank": rank, "target_route": "signal_facts"}, "selected_rank")

    def test_a_selection_argument_that_is_not_a_string_is_refused_not_coerced(self):
        # Every request argument is text. Coercing an int rank to "3" would
        # accept a request shape the contract does not describe, and would
        # make `selected_rank` the one argument with two accepted types.
        arguments = DISCOVERY | {"candidate_set_id": "a" * 64, "selected_rank": 1, "target_route": "signal_facts"}
        db, result = select(arguments)
        self.assertIs(result.status, DiscoveryStatus.INVALID_REQUEST)
        self.assertEqual(db.sessions, 0)
        with self.assertRaises(DiscoveryRefusal) as raised:
            validate(SelectionRequest(arguments=arguments))
        self.assertIn("must be a string", raised.exception.detail)

    def test_the_discovery_half_is_validated_as_entity_discovery_validates_it(self):
        db, result = select(DISCOVERY | {"entity_kind": "frame", "candidate_set_id": "a" * 64, "selected_rank": "1", "target_route": "signal_facts"})
        self.assertIs(result.status, DiscoveryStatus.UNSUPPORTED)
        self.assertIs(result.source_trace.producing_layer, ProducingLayer.RUNTIME)
        self.assertEqual(db.sessions, 0)


class StepsFourToSixRefuseAfterTheRerun(unittest.TestCase):
    def setUp(self):
        self.cid = digest_for(DISCOVERY, exact=TWO_SIGNALS)

    def assert_refused_reporting_the_rerun(self, db, result, arguments):
        bundle = result.evidence_bundle
        self.assertIs(result.status, DiscoveryStatus.INVALID_REQUEST)
        self.assertEqual(bundle.route, "entity_selection")
        # Section 7 (as #88 amended it): the re-run is reported.
        self.assertTrue(bundle.read_only_safeguards.connection_opened)
        self.assertEqual(bundle.template_name, "TPL_DISCOVERY_EXACT_V1")
        self.assertEqual(bundle.registry_digest, "a" * 64)
        self.assertEqual(bundle.row_count, 2)
        self.assert_names_the_selection(result, arguments)
        # And no fact template executed.
        self.assertEqual(fact_templates_ran(db), [])

    def assert_names_the_selection(self, result, arguments):
        """Section 7: the citation a refusal has to carry.

        The three values the caller cited, so the refusal can be traced back
        to the request that produced it. Which of steps 4, 5 and 6 refused is
        not among them: Section 7's key list for a refused selection does not
        contain a reason field, and each step's own fixture asserts that no
        fact template ran, which is what a skipped check would break.
        """
        bundle = result.evidence_bundle
        # Section 7 assigns the cited digest to `candidate_set_id` itself.
        self.assertEqual(bundle.candidate_set_id, arguments["candidate_set_id"])
        self.assertEqual(bundle.selected_rank, arguments["selected_rank"])
        self.assertEqual(bundle.target_route, arguments["target_route"])

    def test_dx_018_a_digest_that_does_not_re_derive(self):
        arguments = DISCOVERY | {"candidate_set_id": "0" * 64, "selected_rank": "1", "target_route": "signal_facts"}
        db, result = select(arguments)
        self.assert_refused_reporting_the_rerun(db, result, arguments)
        self.assertNotIn(DiscoveryLimitationKind.RERUN_PRODUCED_NO_LIST, [l.kind for l in result.limitations])
        # The key Section 7 names carries the caller's value, which is the
        # one that differs from what the re-run derived.
        self.assertEqual(result.evidence_bundle.candidate_set_id, "0" * 64)
        self.assertNotEqual(result.evidence_bundle.candidate_set_id, self.cid)

    def test_dx_019_a_rank_naming_no_candidate(self):
        arguments = DISCOVERY | {"candidate_set_id": self.cid, "selected_rank": "3", "target_route": "signal_facts"}
        db, result = select(arguments)
        self.assert_refused_reporting_the_rerun(db, result, arguments)

    def test_dx_021_a_signal_candidate_with_message_facts(self):
        arguments = DISCOVERY | {"candidate_set_id": self.cid, "selected_rank": "1", "target_route": "message_facts"}
        db, result = select(arguments)
        self.assert_refused_reporting_the_rerun(db, result, arguments)

    def test_dx_021_a_message_candidate_with_signal_facts(self):
        rows = (discovery_row(match_tier=4), discovery_row(message_key="SAMPLE_MSG_X", match_tier=4))
        cid = digest_for(MESSAGE | {"term": "sample"}, lexical=rows)
        arguments = MESSAGE | {"term": "sample", "candidate_set_id": cid, "selected_rank": "1", "target_route": "signal_facts"}
        db, result = select(arguments, exact=(), lexical=rows)
        self.assertIs(result.status, DiscoveryStatus.INVALID_REQUEST)
        self.assert_names_the_selection(result, arguments)
        self.assertEqual(fact_templates_ran(db), [])

    def test_dx_023_a_rerun_that_produced_no_list_is_named(self):
        # The re-run resolves (one tier-1 row), so there is no list.
        arguments = DISCOVERY | {"candidate_set_id": self.cid, "selected_rank": "1", "target_route": "signal_facts"}
        db, result = select(arguments, exact=(TWO_SIGNALS[0],))
        self.assertIs(result.status, DiscoveryStatus.INVALID_REQUEST)
        self.assert_names_the_selection(result, arguments)
        entry = [l for l in result.limitations if l.kind is DiscoveryLimitationKind.RERUN_PRODUCED_NO_LIST]
        self.assertEqual(len(entry), 1)
        self.assertIn("'resolved'", entry[0].detail)
        self.assertEqual(fact_templates_ran(db), [])

    def test_a_rerun_that_found_nothing_is_named_too(self):
        db, result = select(DISCOVERY | {"candidate_set_id": self.cid, "selected_rank": "1", "target_route": "signal_facts"}, exact=(), lexical=())
        entry = [l for l in result.limitations if l.kind is DiscoveryLimitationKind.RERUN_PRODUCED_NO_LIST]
        self.assertIn("'not_found'", entry[0].detail)
        self.assertEqual(fact_templates_ran(db), [])

    def test_the_outcome_check_precedes_the_digest_check(self):
        # A wrong digest AND no list: the caller is told there is no list,
        # which is the actionable fact (discover again).
        db, result = select(DISCOVERY | {"candidate_set_id": "0" * 64, "selected_rank": "1", "target_route": "signal_facts"}, exact=(TWO_SIGNALS[0],))
        self.assertIn(DiscoveryLimitationKind.RERUN_PRODUCED_NO_LIST, [l.kind for l in result.limitations])


    def test_the_reruns_own_limitations_survive_into_the_refusal(self):
        # Section 7 as #88 amended it: a refusal reports the re-run. A
        # superseded snapshot the re-run recorded is a fact about the list
        # the caller selected from, so dropping it on the way out would hide
        # why the digest or the rank no longer fits.
        successor = BASE | {"snapshot_label": "SAMPLE_SNAP_SUCCESSOR"}
        rows = tuple(discovery_row(entity_kind="signal", message_key=m, signal_key=s, superseded_by=successor)
                     for m, s in (("SAMPLE_MSG_TRANSMISSION_STATE", "SAMPLE_SIG_GEAR_POSITION"),
                                  ("SAMPLE_MSG_DIAGNOSTIC_EVENT", "SAMPLE_SIG_FAULT_CODE")))
        cid = digest_for(DISCOVERY, exact=rows)
        db, result = select(DISCOVERY | {"candidate_set_id": cid, "selected_rank": "9", "target_route": "signal_facts"}, exact=rows)
        self.assertIs(result.status, DiscoveryStatus.INVALID_REQUEST)
        self.assertIn(DiscoveryLimitationKind.SUPERSEDED_SNAPSHOT, [l.kind for l in result.limitations])
        self.assertEqual(fact_templates_ran(db), [])

    def test_the_rerun_is_told_the_fixture_provenance_the_route_holds(self):
        # Section 7 requires the fixture provenance on every trace. The
        # re-run is this route's only discovery execution, so a re-run driven
        # without it produces a refusal that cites no fixtures at all.
        db, result = select(DISCOVERY | {"candidate_set_id": "0" * 64, "selected_rank": "1", "target_route": "signal_facts"})
        self.assertIs(result.status, DiscoveryStatus.INVALID_REQUEST)
        self.assertEqual(tuple(result.source_trace.fixture_provenance), PROVENANCE)


class StepSevenDispatches(unittest.TestCase):
    def setUp(self):
        self.cid = digest_for(DISCOVERY, exact=TWO_SIGNALS)
        self.facts = (signal_row(message_key="SAMPLE_MSG_TRANSMISSION_STATE", signal_key="SAMPLE_SIG_GEAR_POSITION"),)

    def dispatch(self, rank="1", target="signal_facts", **extra):
        return select(DISCOVERY | {"candidate_set_id": self.cid, "selected_rank": rank, "target_route": target, **extra},
                      TPL_SIGNAL_FACTS_V1=self.facts, TPL_SIGNAL_MAPPING_V1=())

    def test_dx_017_the_mvp_result_comes_back_with_the_selection_record(self):
        db, result = self.dispatch()
        self.assertIs(result.status, Status.SUCCESS)
        bundle = result.evidence_bundle
        # The top level is the fact route's alone (Section 4.8, "two
        # templates execute on this path, and both are evidenced").
        self.assertEqual(bundle.route, "signal_facts")
        self.assertEqual(bundle.template_name, "TPL_SIGNAL_FACTS_V1")
        self.assertEqual(bundle.contract_identifier, "mvp-v0.1")
        self.assertEqual(set(bundle.bound_parameters), set(BASE) | {"message_key", "signal_key"})
        # And the re-run is beside it, in the selection record.
        selection = dict(bundle.selection)
        self.assertEqual(set(selection), {
            "contract_identifier", "contract_version", "registry_digest", "registry_built_at",
            "method_identifier", "method_version", "candidate_set_id", "selected_rank", "candidate_count",
            "target_route", "discovery_template_name", "discovery_template_version",
            "discovery_bound_parameters", "discovery_row_count",
        })
        self.assertEqual(selection["contract_identifier"], "entity-discovery-v0.1")
        self.assertEqual(selection["candidate_set_id"], self.cid)
        self.assertEqual(selection["selected_rank"], 1)
        self.assertEqual(selection["candidate_count"], 2)
        self.assertEqual(selection["target_route"], "signal_facts")
        self.assertEqual(selection["discovery_template_name"], "TPL_DISCOVERY_EXACT_V1")
        self.assertEqual(selection["discovery_bound_parameters"]["term"], "SAMPLE_SIG_GEAR_POSITION")
        self.assertEqual(selection["discovery_row_count"], 2)
        self.assertEqual(selection["registry_digest"], "a" * 64)

    def test_the_dispatched_request_is_the_candidates_complete_reference(self):
        db, result = self.dispatch()
        bound = db.bound("TPL_SIGNAL_FACTS_V1")
        self.assertEqual(bound["message_key"], "SAMPLE_MSG_TRANSMISSION_STATE")
        self.assertEqual(bound["signal_key"], "SAMPLE_SIG_GEAR_POSITION")
        self.assertEqual(fact_templates_ran(db), ["TPL_SIGNAL_FACTS_V1"])

    def test_the_explicit_selection_entry_names_digest_count_and_route(self):
        db, result = self.dispatch()
        entries = [l for l in result.limitations if l.kind is LimitationKind.SCOPE_SELECTED_BY_USER]
        self.assertEqual(len(entries), 1)
        for fragment in (self.cid, "of 2 candidates", "signal_facts"):
            self.assertIn(fragment, entries[0].detail)

    def test_the_trace_carries_the_entitys_approval_and_alias_provenance_when_an_alias_matched(self):
        # Rank 2 is the alias match.
        db, result = select(DISCOVERY | {"candidate_set_id": self.cid, "selected_rank": "2", "target_route": "signal_facts"},
                            TPL_SIGNAL_FACTS_V1=(signal_row(message_key="SAMPLE_MSG_DIAGNOSTIC_EVENT", signal_key="SAMPLE_SIG_FAULT_CODE"),))
        self.assertIs(result.status, Status.SUCCESS)
        self.assertEqual(result.source_trace.entity_approval_reference, "SAMPLE_APPROVAL_M3_001")
        self.assertEqual(len(result.source_trace.alias_provenance), 1)
        self.assertEqual(result.source_trace.alias_provenance[0]["approval_reference"], "SAMPLE_APPROVAL_M3_101")
        self.assertEqual(result.source_trace.alias_provenance[0]["snapshot_label"], "SAMPLE_SNAP_BASE")

    def test_a_lookup_key_selection_carries_no_alias_provenance(self):
        db, result = self.dispatch()
        self.assertEqual(result.source_trace.alias_provenance, ())
        self.assertEqual(result.source_trace.entity_approval_reference, "SAMPLE_APPROVAL_M3_001")

    def test_signal_mapping_passes_the_mapping_key_through(self):
        db, result = self.dispatch(target="signal_mapping", mapping_key="SAMPLE_MAP_SPEED_TO_GEAR")
        self.assertEqual(db.bound("TPL_SIGNAL_MAPPING_V1")["mapping_key"], "SAMPLE_MAP_SPEED_TO_GEAR")
        self.assertIs(result.status, Status.NOT_FOUND)  # no mapping rows recorded
        self.assertIsNotNone(result.evidence_bundle.selection)

    def test_the_fact_routes_own_status_is_returned_not_success_by_fiat(self):
        db, result = select(DISCOVERY | {"candidate_set_id": self.cid, "selected_rank": "1", "target_route": "signal_facts"}, TPL_SIGNAL_FACTS_V1=())
        self.assertIs(result.status, Status.NOT_FOUND)

    def test_target_route_is_not_a_digest_input(self):
        # Section 8's row: one selection digest serves both permitted routes.
        a, _ = self.dispatch(target="signal_facts")
        b, _ = self.dispatch(target="signal_mapping")
        # Both dispatched, so both re-derivations matched the one digest.
        self.assertEqual(fact_templates_ran(a), ["TPL_SIGNAL_FACTS_V1"])
        self.assertEqual(fact_templates_ran(b), ["TPL_SIGNAL_MAPPING_V1"])

class AnIncompleteScopeIsRefusedNotFaulted(unittest.TestCase):
    """#318: a selection whose scope is incomplete. Its step-2 re-run takes
    the Section 4.3 incomplete-scope path, which forms no candidate list, so
    the selection is this contract's `invalid_request` naming the re-run --
    `DX-023`'s refusal -- and never a fault."""

    UNSCOPED = {k: v for k, v in DISCOVERY.items() if k != "snapshot_label"}
    SELECT = {"candidate_set_id": "0" * 64, "selected_rank": "1", "target_route": "signal_facts"}

    def assert_refused(self, result, outcome):
        self.assertIs(result.status, DiscoveryStatus.INVALID_REQUEST)
        entry = [l for l in result.limitations if l.kind is DiscoveryLimitationKind.RERUN_PRODUCED_NO_LIST]
        self.assertEqual(len(entry), 1)
        self.assertIn(f"'{outcome}'", entry[0].detail)
        self.assertIsNone(result.evidence_bundle.scope_search)

    def test_a_rerun_that_lists_scopes(self):
        db, result = select(self.UNSCOPED | self.SELECT)
        self.assert_refused(result, "ambiguous")
        self.assertEqual(fact_templates_ran(db), [])

    def test_a_rerun_found_in_no_scope(self):
        db, result = select(self.UNSCOPED | self.SELECT, exact=(), lexical=())
        self.assert_refused(result, "not_found")
        self.assertEqual(fact_templates_ran(db), [])

    def test_a_rerun_above_the_bound_that_searched_nothing(self):
        from evidence_first_rag.discovery import service

        original = service.SCOPE_SEARCH_BOUND
        service.SCOPE_SEARCH_BOUND = 0
        try:
            db, result = select(self.UNSCOPED | self.SELECT)
        finally:
            service.SCOPE_SEARCH_BOUND = original
        self.assert_refused(result, "ambiguous")
        self.assertEqual(result.evidence_bundle.registry_digest, "")
        self.assertEqual(fact_templates_ran(db), [])

    def test_a_rerun_that_is_a_coverage_gap(self):
        db, result = select(DISCOVERY | self.SELECT, candidates=())
        self.assert_refused(result, "coverage_gap")
        self.assertEqual(fact_templates_ran(db), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
