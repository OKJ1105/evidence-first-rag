"""Section 4.2 scope enforcement: what the runtime refuses to decide.

The assertions here are mostly negative, and that is the shape of the section.
Section 4.2 fixes what the runtime must *not* do -- supply a dimension, take
the newest `ingested_at`, take the highest `revision_label`, take the only
loaded row -- so most of what is checked below is that a code path did not
run, or that a value was left null rather than filled in.
"""

import unittest

from evidence_first_rag import LimitationKind, SnapshotScope, Status
from evidence_first_rag.runtime import DataFault, Request, Runtime

from .runtime_support import BASE, CHASSIS_B, FakeDatabase, REVISED, candidate_row, message_row

CANDIDATES = "TPL_SNAPSHOT_CANDIDATES_V1"
MESSAGE_FACTS = "TPL_MESSAGE_FACTS_V1"
MESSAGE = BASE | {"message_key": "SAMPLE_MSG_ENGINE_STATUS"}


def without(mapping, *names):
    return {key: value for key, value in mapping.items() if key not in names}


def answer(arguments, rows, route="message_facts", **request):
    database = FakeDatabase(rows)
    result = Runtime(database=database).execute(
        Request(route=route, arguments=arguments, **request)
    )
    return database, result


class TheCandidateQueryRunsOnEveryRequest(unittest.TestCase):
    """It is what makes `not_found` and `coverage_gap` different outcomes."""

    def test_a_fully_scoped_request_still_resolves_its_scope_first(self):
        database, result = answer(
            MESSAGE,
            {CANDIDATES: (candidate_row(),), MESSAGE_FACTS: (message_row(),)},
        )
        self.assertIs(result.status, Status.SUCCESS)
        self.assertEqual([name for name, _ in database.calls], [CANDIDATES, MESSAGE_FACTS])

    def test_it_binds_only_the_dimensions_the_request_carried(self):
        # Section 4.2: "The runtime never supplies a missing `project_code`,
        # `revision_label`, `network_name`, or `snapshot_label`." An omitted
        # dimension is bound as null, which the registered SQL reads as "not
        # narrowed by this dimension" -- the runtime chooses no value for it.
        database, _ = answer(
            without(MESSAGE, "snapshot_label"),
            {CANDIDATES: (candidate_row(),)},
        )
        self.assertEqual(
            database.bound(CANDIDATES),
            {
                "project_code": "SAMPLE_PROJECT_ALPHA",
                "revision_label": "SAMPLE_REV_A",
                "network_name": "SAMPLE_NET_POWERTRAIN",
                "snapshot_label": None,
            },
        )

    def test_the_lookup_key_never_reaches_the_candidate_query(self):
        # Section 4.4 fixes the candidate template's allowlist as the four
        # scope dimensions. A `message_key` bound here would be an unallowed
        # parameter, and `bind` would refuse it.
        database, _ = answer(MESSAGE, {CANDIDATES: (candidate_row(),), MESSAGE_FACTS: ()})
        self.assertNotIn("message_key", database.bound(CANDIDATES))


class NoCandidateIsACoverageGap(unittest.TestCase):
    def setUp(self):
        self.database, self.result = answer(
            MESSAGE | {"network_name": "SAMPLE_NET_BODY"}, {CANDIDATES: ()}
        )

    def test_the_status_is_coverage_gap_and_not_not_found(self):
        # Section 5: `coverage_gap` is "returned instead of `not_found`
        # whenever coverage cannot be established".
        self.assertIs(self.result.status, Status.COVERAGE_GAP)

    def test_the_routes_own_template_is_never_reached(self):
        self.assertFalse(self.database.ran(MESSAGE_FACTS))

    def test_it_states_what_coverage_could_not_be_established(self):
        entry = next(
            limitation
            for limitation in self.result.limitations
            if limitation.kind is LimitationKind.COVERAGE_NOT_ESTABLISHED
        )
        self.assertIn("SAMPLE_NET_BODY", entry.detail)

    def test_nothing_was_resolved(self):
        self.assertIsNone(self.result.evidence_bundle.resolved_scope)
        self.assertEqual(self.result.evidence_bundle.row_count, 0)

    def test_a_connection_was_opened_and_the_bundle_says_so(self):
        # Section 5 lists the three statuses that open none, and this is not
        # one of them: establishing that coverage is absent takes a query.
        safeguards = self.result.evidence_bundle.read_only_safeguards
        self.assertTrue(safeguards.connection_opened)
        self.assertTrue(safeguards.read_only_transaction)
        self.assertEqual(self.result.evidence_bundle.template_name, CANDIDATES)


class AnUnderSpecifiedScopeIsAmbiguous(unittest.TestCase):
    def test_two_candidates_are_both_listed(self):
        # `FX-105`.
        _, result = answer(
            without(MESSAGE, "snapshot_label"),
            {CANDIDATES: (candidate_row(BASE), candidate_row(REVISED))},
        )
        self.assertIs(result.status, Status.AMBIGUOUS)
        self.assertEqual(
            [row["snapshot_label"] for row in result.rows],
            ["SAMPLE_SNAP_BASE", "SAMPLE_SNAP_REVISED"],
        )
        self.assertEqual(
            result.source_trace.contributing_scopes,
            (SnapshotScope(**BASE), SnapshotScope(**REVISED)),
        )

    def test_one_candidate_is_still_ambiguous(self):
        # `FX-113`, and contract version 0.4.0's recorded decision: "One
        # matching candidate is still `ambiguous`." Resolving it would be the
        # selection of "the only loaded row" that Section 4.2 forbids.
        database, result = answer(
            {"message_key": "SAMPLE_MSG_WHEEL_SPEED"}
            | without(CHASSIS_B, "snapshot_label"),
            {CANDIDATES: (candidate_row(CHASSIS_B),)},
        )
        self.assertIs(result.status, Status.AMBIGUOUS)
        self.assertEqual(len(result.rows), 1)
        self.assertFalse(database.ran(MESSAGE_FACTS))

    def test_the_candidate_count_is_never_the_threshold(self):
        # The two halves of the same rule. An implementation that answered one
        # of these and not the other would have made the count its rule, which
        # is the reading Section 4.2 rejects.
        for rows in ((candidate_row(BASE),), (candidate_row(BASE), candidate_row(REVISED))):
            with self.subTest(candidates=len(rows)):
                _, result = answer(without(MESSAGE, "snapshot_label"), {CANDIDATES: rows})
                self.assertIs(result.status, Status.AMBIGUOUS)

    def test_nothing_is_resolved_and_no_facts_are_returned(self):
        _, result = answer(
            without(MESSAGE, "snapshot_label"),
            {CANDIDATES: (candidate_row(BASE), candidate_row(REVISED))},
        )
        self.assertIsNone(result.evidence_bundle.resolved_scope)
        for row in result.rows:
            self.assertEqual(set(row), set(BASE))

    def test_the_candidates_are_listed_in_the_order_the_template_returned(self):
        # Section 6 puts the ordering in the registered template and forbids
        # the caller from applying its own. A runtime that re-sorted the
        # candidates would be applying one.
        _, result = answer(
            without(MESSAGE, "snapshot_label"),
            {CANDIDATES: (candidate_row(REVISED), candidate_row(BASE))},
        )
        self.assertEqual(
            [row["snapshot_label"] for row in result.rows],
            ["SAMPLE_SNAP_REVISED", "SAMPLE_SNAP_BASE"],
        )

    def test_a_full_candidate_page_records_the_truncation(self):
        # Section 4.4 caps the candidate template at 100 and Section 7 requires
        # a `limitations` entry "when a result was truncated by a limit".
        rows = tuple(
            candidate_row(BASE | {"snapshot_label": f"SAMPLE_SNAP_{index:03d}"})
            for index in range(100)
        )
        _, result = answer(without(MESSAGE, "snapshot_label"), {CANDIDATES: rows})
        self.assertTrue(
            any(
                limitation.kind is LimitationKind.TRUNCATED_BY_LIMIT
                for limitation in result.limitations
            )
        )


class AScopeThatCannotResolveIsAFault(unittest.TestCase):
    def test_a_complete_scope_matching_two_snapshots_is_a_data_fault(self):
        # Section 4.1 makes the four dimensions unique, so this cannot happen
        # against a database that satisfies its own constraints. Answering it
        # would mean picking one of several, which Section 4.2 forbids, and no
        # Section 5 status describes a database that contradicts itself.
        with self.assertRaises(DataFault) as raised:
            answer(MESSAGE, {CANDIDATES: (candidate_row(BASE), candidate_row(REVISED))})
        self.assertEqual(raised.exception.conformance_class, "data")


class NoRequestCanClaimAUserSelection(unittest.TestCase):
    """Section 7's `scope_selected_by_user` entry has no producer in this slice.

    Removed on review: `Request` is what untrusted adapter output becomes
    (Section 4.6), so a flag on it would let the adapter claim a user chose a
    scope when none did, and the runtime would record the claim as provenance.
    This test pins the absence so that the flag does not quietly return
    without the trusted path that would have to vouch for it.
    """

    def test_the_request_type_carries_no_selection_flag(self):
        import dataclasses

        from evidence_first_rag.runtime import Request

        self.assertNotIn(
            "scope_selected_by_user", {f.name for f in dataclasses.fields(Request)}
        )

    def test_a_fully_scoped_request_records_no_selection(self):
        _, result = answer(
            MESSAGE, {CANDIDATES: (candidate_row(),), MESSAGE_FACTS: (message_row(),)}
        )
        self.assertFalse(
            any(
                limitation.kind is LimitationKind.SCOPE_SELECTED_BY_USER
                for limitation in result.limitations
            )
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
