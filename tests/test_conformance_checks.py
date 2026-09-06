"""Section 4.9's checks, and the ways each one could pass without meaning it.

Most of these are probes rather than confirmations. A conformance check that
has only ever been seen to pass is a check nobody knows works, and `B1` in
particular is the kind of assertion that is easy to write so that it cannot
fail -- so the tests below spend most of their effort on making each one fail
for the right reason.
"""

import unittest

from evidence_first_rag.registry import REGISTERED, TPL_MESSAGE_FACTS_V1
from evidence_first_rag.conformance import checks
from evidence_first_rag.conformance.cases import BY_IDENTIFIER
from evidence_first_rag.conformance.recording import PortExecution

REGISTERED_SQL = TPL_MESSAGE_FACTS_V1.sql
CANDIDATES_SQL = next(t.sql for t in REGISTERED if t.name == "TPL_SNAPSHOT_CANDIDATES_V1")


def port(name="TPL_MESSAGE_FACTS_V1", sql=REGISTERED_SQL, row_count=1):
    return PortExecution(template_name=name, sql=sql, row_count=row_count)


class B1RefusesToPassVacuously(unittest.TestCase):
    """`B1` asserts a negative -- that nothing came from outside the registry
    -- and a negative is satisfied by an empty world. These are the ways the
    world could be empty."""

    def test_a_run_that_executed_nothing_while_claiming_connections_fails(self):
        result = checks.b1([], [], 3)
        self.assertFalse(result.passed)
        self.assertIn("vacuously", result.detail)

    def test_a_driver_that_saw_less_than_the_port_ran_fails(self):
        # The recorder is the instrument. If it under-counts, everything it
        # did not see is unchecked, and `B1` would pass on the subset it did.
        result = checks.b1([REGISTERED_SQL], [port(), port()], 1)
        self.assertFalse(result.passed)
        self.assertIn("not seeing every execution", result.detail)

    def test_a_run_with_no_fixtures_at_all_is_allowed_to_pass(self):
        # The one honest empty case: nothing claimed a connection either.
        self.assertTrue(checks.b1([], [], 0).passed)


class B1TrustsOnlyTheCommittedText(unittest.TestCase):
    """Issue #28: the registry seal is bypassable with no import at all, so a
    `Template` proves nothing about where its SQL came from."""

    def test_a_statement_that_is_not_a_registered_text_fails(self):
        result = checks.b1(["SELECT 1"], [], 1)
        self.assertFalse(result.passed)
        self.assertEqual(result.failure_class, "runtime")

    def test_a_registered_name_does_not_launder_unregistered_sql(self):
        # The defect this test exists to prevent: comparing template *names*.
        # A forged template may call itself anything, so a name-based check
        # would pass exactly the case it is meant to catch.
        forged = "SELECT secret FROM mvp.source_snapshot ORDER BY secret NULLS LAST LIMIT 1"
        result = checks.b1([forged], [port(sql=forged)], 1)
        self.assertFalse(result.passed)

    def test_every_registered_text_is_accepted(self):
        statements = [template.sql for template in REGISTERED]
        self.assertTrue(checks.b1(statements, [], 1).passed)

    def test_a_near_miss_is_not_close_enough(self):
        # Byte-exact on purpose. A statement differing by one character is a
        # different query, and Section 4.4 makes the committed text the thing
        # that was reviewed.
        result = checks.b1([REGISTERED_SQL + " "], [], 1)
        self.assertFalse(result.passed)


class B2SeparatesFactsFromCandidates(unittest.TestCase):
    def test_a_negative_outcome_returning_facts_fails(self):
        result = checks.b2([("FX-107", "not_found", [port(row_count=1)])])
        self.assertFalse(result.passed)
        self.assertIn("FX-107", result.detail)

    def test_an_ambiguous_outcome_may_return_candidate_rows(self):
        # Section 4.4 registers the candidate template so that `ambiguous` can
        # list scopes; those rows are not a factual success.
        result = checks.b2(
            [("FX-105", "ambiguous", [port("TPL_SNAPSHOT_CANDIDATES_V1", CANDIDATES_SQL, 2)])]
        )
        self.assertTrue(result.passed)

    def test_a_success_returning_facts_is_not_its_business(self):
        self.assertTrue(checks.b2([("FX-001", "success", [port(row_count=1)])]).passed)


class B3RequiresTheRefusalToComeFromPrivileges(unittest.TestCase):
    """Section 4.10: "Refusal must originate from PostgreSQL privileges, not
    from an application guard."""

    def refusals(self, **overrides):
        recorded = {
            name: {"refused": True, "sqlstate": "42501", "from_privileges": True}
            for name in ("INSERT", "UPDATE", "DELETE", "CREATE TABLE")
        }
        recorded.update(overrides)
        return recorded

    def test_all_four_refused_by_privilege_passes(self):
        self.assertTrue(checks.b3(self.refusals()).passed)

    def test_a_write_that_succeeded_fails(self):
        result = checks.b3(
            self.refusals(INSERT={"refused": False, "sqlstate": None, "from_privileges": False})
        )
        self.assertFalse(result.passed)
        self.assertIn("INSERT", result.detail)

    def test_a_refusal_from_the_transaction_mode_is_not_enough(self):
        # `25006` is read_only_sql_transaction: the session refused before the
        # grant was consulted, so the grant is untested and B3 says so.
        result = checks.b3(
            self.refusals(
                UPDATE={"refused": True, "sqlstate": "25006", "from_privileges": False}
            )
        )
        self.assertFalse(result.passed)
        self.assertIn("not by privileges", result.detail)


class B4AndC1AndD1(unittest.TestCase):
    def test_b4_fails_when_the_digest_moved(self):
        before = {"row_counts": {"source_snapshot": 4}, "highest_transaction_id": "700"}
        self.assertTrue(checks.b4(before, dict(before)).passed)
        self.assertFalse(checks.b4(before, {**before, "row_counts": {"source_snapshot": 5}}).passed)

    def test_c1_reports_the_invariant_failures_it_was_given(self):
        self.assertTrue(checks.c1([]).passed)
        broken = checks.c1(["source_snapshot is missing a unique constraint"])
        self.assertFalse(broken.passed)
        self.assertEqual(broken.failure_class, "data")

    def test_c1_also_asserts_the_session_statement_timeout(self):
        # Review finding N2 on #38. `db/invariants.py` reads the role's
        # configured value; this is what the runtime's session actually got,
        # which a per-session override could make differ. Section 4.4 fixes
        # the value the runtime runs with.
        self.assertTrue(checks.c1([], statement_timeout="5s").passed)
        drifted = checks.c1([], statement_timeout="30s")
        self.assertFalse(drifted.passed)
        self.assertEqual(drifted.failure_class, "data")
        self.assertIn("statement_timeout", drifted.detail)

    def test_c1_leaves_the_callers_failure_list_alone(self):
        # It appends its own finding, so it must not append into the list it
        # was handed -- two runs sharing one invariant result would otherwise
        # accumulate duplicates and make `D1` fail.
        failures = []
        checks.c1(failures, statement_timeout="30s")
        self.assertEqual(failures, [])

    def test_d1_fails_on_any_difference_and_names_where(self):
        first = {"verdict": "pass", "fixtures": [{"identifier": "FX-001"}]}
        self.assertTrue(checks.d1(first, dict(first)).passed)
        diverged = checks.d1(first, {"verdict": "pass", "fixtures": [{"identifier": "FX-002"}]})
        self.assertFalse(diverged.passed)
        self.assertIn("fixtures[0].identifier", diverged.detail)


class A1IsOneEqualityThatNamesThePathAndTheClass(unittest.TestCase):
    """Section 4.9: "one equality, not a set of independent field checks. On
    failure the runner reports the first diverging path and uses it only to
    assign a failure class."""

    def document(self, **overrides):
        base = {
            "status": "success",
            "rows": [{"message_key": "SAMPLE_MSG_ENGINE_STATUS", "transmit_period_ms": 10}],
            "evidence_bundle": {
                "route": "message_facts",
                "bound_parameters": {"message_key": "SAMPLE_MSG_ENGINE_STATUS"},
                "resolved_scope": {"snapshot_label": "SAMPLE_SNAP_BASE"},
            },
        }
        base.update(overrides)
        return base

    def case(self):
        return BY_IDENTIFIER["FX-001"]

    def test_equal_documents_pass(self):
        self.assertTrue(checks.a1(self.case(), self.document(), self.document()).passed)

    def test_a_missing_expectation_is_a_contract_failure_not_a_crash(self):
        result = checks.a1(self.case(), self.document(), None)
        self.assertFalse(result.passed)
        self.assertEqual(result.failure_class, "contract")

    def test_a_row_value_is_classed_data(self):
        actual = self.document()
        expected = self.document(
            rows=[{"message_key": "SAMPLE_MSG_ENGINE_STATUS", "transmit_period_ms": 20}]
        )
        result = checks.a1(self.case(), actual, expected)
        self.assertFalse(result.passed)
        self.assertEqual(result.failure_class, "data")
        self.assertIn("rows[0].transmit_period_ms", result.detail)

    def test_a_status_is_classed_contract(self):
        result = checks.a1(self.case(), self.document(), self.document(status="not_found"))
        self.assertEqual(result.failure_class, "contract")

    def test_an_argument_is_classed_retrieval(self):
        expected = self.document()
        expected["evidence_bundle"] = dict(
            expected["evidence_bundle"], bound_parameters={"message_key": "SAMPLE_MSG_OTHER"}
        )
        result = checks.a1(self.case(), self.document(), expected)
        self.assertEqual(result.failure_class, "retrieval")

    def test_a_resolved_scope_is_classed_data_even_though_it_sits_in_evidence(self):
        expected = self.document()
        expected["evidence_bundle"] = dict(
            expected["evidence_bundle"], resolved_scope={"snapshot_label": "SAMPLE_SNAP_REVISED"}
        )
        result = checks.a1(self.case(), self.document(), expected)
        self.assertEqual(result.failure_class, "data")

    def test_an_extra_field_on_either_side_is_a_divergence(self):
        # "in full" cuts both ways: a result carrying a field the expectation
        # does not know about is not equal to it.
        self.assertFalse(
            checks.a1(self.case(), self.document(extra=1), self.document()).passed
        )
        self.assertFalse(
            checks.a1(self.case(), self.document(), self.document(extra=1)).passed
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
