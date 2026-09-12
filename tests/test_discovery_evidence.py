"""entity-discovery-v0.1 Sections 4.6, 5 and 7 as type rules: a result that
violates one does not construct.

The rules asserted here are the ones the contract states unconditionally --
`resolved` carries one reference and no list, `candidates` carries a list of
at most k with its digest, no status may claim what it did not do -- so that
the route cannot produce a result the contract forbids by any path.
"""

import unittest

from evidence_first_rag import MessageReference, ProducingLayer, ReadOnlySafeguards, SignalReference, SnapshotScope
from evidence_first_rag.discovery import (
    AliasProvenance,
    Candidate,
    DiscoveryEvidence,
    DiscoveryLimitation,
    DiscoveryLimitationKind,
    DiscoveryResult,
    DiscoveryStatus,
    DiscoveryTrace,
    K,
)

SCOPE = SnapshotScope(project_code="SAMPLE_PROJECT_ALPHA", revision_label="SAMPLE_REV_A", network_name="SAMPLE_NET_POWERTRAIN", snapshot_label="SAMPLE_SNAP_BASE")
MESSAGE = MessageReference(scope=SCOPE, message_key="SAMPLE_MSG_ENGINE_STATUS")
SIGNAL = SignalReference(message=MESSAGE, signal_key="SAMPLE_SIG_TEMPERATURE")
OPENED = ReadOnlySafeguards(role_name="SAMPLE_RUNTIME_ROLE", read_only_transaction=True, connection_opened=True)
CLOSED = ReadOnlySafeguards(role_name="", read_only_transaction=False, connection_opened=False)
ALIAS = AliasProvenance(approval_reference="SAMPLE_APPROVAL_M3_101", approved_at="2026-03-05T00:00:00Z", asserting_scope=SCOPE)


def candidate(rank=1, tier=1, kind="lookup_key", reference=MESSAGE, entity_kind="message"):
    return Candidate(
        rank=rank, entity_kind=entity_kind, reference=reference, match_tier=tier,
        matched_text="SAMPLE_MSG_ENGINE_STATUS", match_kind=kind,
        entity_approval_reference="SAMPLE_APPROVAL_M3_001",
        alias=None if kind == "lookup_key" else ALIAS,
    )


def executed(**overrides):
    values = dict(
        route="entity_discovery", read_only_safeguards=OPENED, row_count=1,
        template_name="TPL_DISCOVERY_EXACT_V1", template_version="1",
        bound_parameters={"term": "x"}, resolved_scope=SCOPE,
        registry_digest="a" * 64, registry_built_at="2026-09-12T00:00:00Z",
        method_identifier="M-LEX-1", method_version="1",
    )
    values.update(overrides)
    return DiscoveryEvidence(**values)


def limitation(kind):
    return DiscoveryLimitation(kind=kind, detail="SAMPLE detail")


class ACandidate(unittest.TestCase):
    def test_a_message_candidate_carries_a_message_reference(self):
        with self.assertRaises(ValueError):
            candidate(reference=SIGNAL)

    def test_a_signal_candidate_carries_a_signal_reference_parent_included(self):
        with self.assertRaises(ValueError):
            candidate(reference=MESSAGE, entity_kind="signal")
        c = candidate(reference=SIGNAL, entity_kind="signal")
        self.assertEqual(c.reference.message_key, "SAMPLE_MSG_ENGINE_STATUS")
        self.assertEqual(c.signal_key, "SAMPLE_SIG_TEMPERATURE")

    def test_alias_provenance_exactly_when_not_a_lookup_key(self):
        with self.assertRaises(ValueError):
            Candidate(rank=1, entity_kind="message", reference=MESSAGE, match_tier=2, matched_text="x", match_kind="approved_alias", entity_approval_reference="SAMPLE_A")
        with self.assertRaises(ValueError):
            Candidate(rank=1, entity_kind="message", reference=MESSAGE, match_tier=1, matched_text="x", match_kind="lookup_key", entity_approval_reference="SAMPLE_A", alias=ALIAS)

    def test_a_tier_outside_one_to_four(self):
        for tier in (0, 5, True):
            with self.subTest(tier=tier), self.assertRaises(ValueError):
                candidate(tier=tier)

    def test_a_rank_below_one(self):
        with self.assertRaises(ValueError):
            candidate(rank=0)

    def test_the_digest_fields_are_exactly_section_4_6s(self):
        # Section 4.8 names them, and "no attribute of the entity ... and no
        # score" (Section 4.6) means nothing else may appear.
        self.assertEqual(
            set(candidate(kind="approved_alias", tier=2).digest_fields()),
            {"rank", "entity_kind", "project_code", "revision_label", "network_name", "snapshot_label",
             "message_key", "signal_key", "match_tier", "matched_text", "match_kind"},
        )
        self.assertIsNone(candidate().digest_fields()["signal_key"])


class TheBundle(unittest.TestCase):
    def test_nothing_is_recorded_as_executed_when_no_connection_was_opened(self):
        for field, value in (("template_name", "T"), ("registry_digest", "a" * 64), ("candidate_set_id", "b" * 64), ("row_count", 1), ("resolved_scope", SCOPE), ("bound_parameters", {"term": "x"})):
            with self.subTest(field=field), self.assertRaises(ValueError):
                DiscoveryEvidence(route="entity_discovery", read_only_safeguards=CLOSED, **{field: value})

    def test_the_digest_and_the_method_are_recorded_together(self):
        with self.assertRaises(ValueError):
            executed(method_identifier="", method_version="")
        with self.assertRaises(ValueError):
            executed(registry_digest="")

    def test_the_candidate_set_id_and_count_are_recorded_together(self):
        with self.assertRaises(ValueError):
            executed(candidate_set_id="c" * 64)
        with self.assertRaises(ValueError):
            executed(candidate_count=2)

    def test_the_match_tier_and_text_are_recorded_together(self):
        with self.assertRaises(ValueError):
            executed(match_tier=1)
        with self.assertRaises(ValueError):
            executed(matched_text="x")

    def test_a_refused_selection_records_its_citation_with_no_connection_opened(self):
        # Section 4.8 step 1 opens nothing, and Section 7 still requires the
        # `candidate_set_id` cited, the `selected_rank` and the `target_route`
        # named: those are the caller's own values, not anything the runtime
        # bound, so the no-connection empty-value rule does not reach them.
        bundle = DiscoveryEvidence(
            route="entity_selection", read_only_safeguards=CLOSED,
            cited_candidate_set_id="c" * 64, selected_rank="1",
            target_route="signal_facts", refusal_detail="SAMPLE reason",
        )
        self.assertEqual(bundle.selected_rank, "1")
        self.assertEqual(bundle.cited_candidate_set_id, "c" * 64)

    def test_both_contracts_are_named(self):
        bundle = executed()
        self.assertEqual(bundle.contract_identifier, "entity-discovery-v0.1")
        self.assertEqual(bundle.runtime_contract_identifier, "mvp-v0.1")
        self.assertEqual(bundle.collation, "C")


class AResult(unittest.TestCase):
    def resolved(self, **overrides):
        values = dict(
            status=DiscoveryStatus.RESOLVED,
            evidence_bundle=executed(match_tier=1, matched_text="SAMPLE_MSG_ENGINE_STATUS"),
            source_trace=DiscoveryTrace(resolved_scope=SCOPE, entity_approval_reference="SAMPLE_APPROVAL_M3_001"),
            resolved=candidate(),
        )
        values.update(overrides)
        return DiscoveryResult(**values)

    def candidates(self, n=2, **overrides):
        listed = tuple(candidate(rank=i, tier=4) for i in range(1, n + 1))
        values = dict(
            status=DiscoveryStatus.CANDIDATES,
            evidence_bundle=executed(candidate_set_id="c" * 64, candidate_count=n, row_count=n),
            source_trace=DiscoveryTrace(resolved_scope=SCOPE),
            limitations=(limitation(DiscoveryLimitationKind.NO_REFERENCE_RESOLVED),),
            candidates=listed,
        )
        values.update(overrides)
        return DiscoveryResult(**values)

    def test_a_valid_resolved_and_a_valid_candidates_construct(self):
        self.resolved()
        self.candidates()

    def test_resolved_carries_one_reference_and_no_list(self):
        with self.assertRaises(ValueError):
            self.resolved(resolved=None)
        with self.assertRaises(ValueError):
            self.resolved(candidates=(candidate(),))

    def test_only_tier_1_or_2_may_resolve(self):
        # Section 4.7. A tier-3 "resolution" has no representation.
        with self.assertRaises(ValueError):
            self.resolved(resolved=candidate(tier=3), evidence_bundle=executed(match_tier=3, matched_text="SAMPLE_MSG_ENGINE_STATUS"))

    def test_resolved_carries_no_candidate_set_id(self):
        with self.assertRaises(ValueError):
            self.resolved(evidence_bundle=executed(match_tier=1, matched_text="SAMPLE_MSG_ENGINE_STATUS", candidate_set_id="c" * 64, candidate_count=1))

    def test_resolved_traces_the_entitys_approval_reference(self):
        with self.assertRaises(ValueError):
            self.resolved(source_trace=DiscoveryTrace(resolved_scope=SCOPE))

    def test_candidates_carries_at_least_one_and_at_most_k(self):
        with self.assertRaises(ValueError):
            self.candidates(candidates=(), evidence_bundle=executed(candidate_set_id="c" * 64, candidate_count=0))
        with self.assertRaises(ValueError):
            self.candidates(K + 1)

    def test_candidates_requires_the_digest_and_its_count(self):
        with self.assertRaises(ValueError):
            self.candidates(evidence_bundle=executed())
        with self.assertRaises(ValueError):
            self.candidates(evidence_bundle=executed(candidate_set_id="c" * 64, candidate_count=1))

    def test_candidates_requires_the_no_reference_resolved_entry(self):
        with self.assertRaises(ValueError):
            self.candidates(limitations=())

    def test_ranks_are_positions(self):
        with self.assertRaises(ValueError):
            self.candidates(candidates=(candidate(rank=2, tier=4), candidate(rank=1, tier=4)))

    def test_not_found_requires_the_allowlist_entry(self):
        with self.assertRaises(ValueError):
            DiscoveryResult(status=DiscoveryStatus.NOT_FOUND, evidence_bundle=executed(row_count=0), source_trace=DiscoveryTrace(resolved_scope=SCOPE))
        DiscoveryResult(status=DiscoveryStatus.NOT_FOUND, evidence_bundle=executed(row_count=0), source_trace=DiscoveryTrace(resolved_scope=SCOPE), limitations=(limitation(DiscoveryLimitationKind.NOT_IN_REGISTRY),))

    def test_the_no_connection_statuses_open_none(self):
        for status in (DiscoveryStatus.INVALID_REQUEST, DiscoveryStatus.UNSUPPORTED):
            with self.subTest(status=status), self.assertRaises(ValueError):
                DiscoveryResult(status=status, evidence_bundle=executed(), source_trace=DiscoveryTrace(producing_layer=ProducingLayer.RUNTIME))

    def test_unsupported_records_its_producing_layer_and_nothing_else_does(self):
        closed = DiscoveryEvidence(route="entity_discovery", read_only_safeguards=CLOSED)
        with self.assertRaises(ValueError):
            DiscoveryResult(status=DiscoveryStatus.UNSUPPORTED, evidence_bundle=closed, source_trace=DiscoveryTrace())
        with self.assertRaises(ValueError):
            DiscoveryResult(status=DiscoveryStatus.INVALID_REQUEST, evidence_bundle=closed, source_trace=DiscoveryTrace(producing_layer=ProducingLayer.RUNTIME))

    def test_a_scope_only_status_cites_no_registry_state(self):
        # Section 5: for ambiguous and coverage_gap no discovery template
        # executes, so a registry digest on the bundle would be a claim about
        # a comparison never made.
        for status in (DiscoveryStatus.AMBIGUOUS, DiscoveryStatus.COVERAGE_GAP):
            with self.subTest(status=status), self.assertRaises(ValueError):
                DiscoveryResult(
                    status=status, evidence_bundle=executed(resolved_scope=None),
                    source_trace=DiscoveryTrace(),
                    limitations=(limitation(DiscoveryLimitationKind.COVERAGE_NOT_ESTABLISHED),),
                )

    def test_the_cited_selection_belongs_to_a_refused_selection(self):
        # Section 7 puts the citation on a refused `entity_selection`. A
        # discovery result carrying one would name a selection nobody made.
        for field in ("cited_candidate_set_id", "selected_rank", "target_route", "refusal_detail"):
            with self.subTest(field=field), self.assertRaises(ValueError):
                DiscoveryResult(
                    status=DiscoveryStatus.NOT_FOUND,
                    evidence_bundle=executed(row_count=0, **{field: "SAMPLE"}),
                    source_trace=DiscoveryTrace(resolved_scope=SCOPE),
                    limitations=(limitation(DiscoveryLimitationKind.NOT_IN_REGISTRY),),
                )

    def test_only_ambiguous_lists_candidate_scopes(self):
        with self.assertRaises(ValueError):
            self.resolved(candidate_scopes=(SCOPE,))


if __name__ == "__main__":
    unittest.main(verbosity=2)
