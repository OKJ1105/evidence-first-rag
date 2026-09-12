"""The Section 4.9 runner against a real database, and the ways it can fail.

A conformance runner is the thing that says whether everything else works, so
a runner that only ever reports `pass` is the least trustworthy component in
the repository. Most of this file makes it say `fail`.

The load-bearing one is `B1AgainstTheSealBypass`. Issue #28 established that a
`Template` can be forged with no import at all, so `B1` cannot rest on the
seal, on `isinstance`, or on a template's name. That class builds the forgery
#28 describes, runs it through the runtime's own session, and requires `B1` to
catch it.
"""

import json
import os
import unittest

from evidence_first_rag import LimitationKind
from evidence_first_rag.conformance import checks, expected, probes, runner
from evidence_first_rag.conformance.artifact import Verdict, comparable
from evidence_first_rag.conformance.cases import REGISTERED
from evidence_first_rag.conformance.recording import RecordingDatabase, recording_cursor
from evidence_first_rag.db import invariants
from evidence_first_rag.registry import TPL_MESSAGE_FACTS_V1
from evidence_first_rag.runtime.connection import PsycopgDatabase
from evidence_first_rag.runtime.faults import Fault

from . import support

DATABASE = "mvp_test_conformance"


def setUpModule():
    support.build(DATABASE)


def tearDownModule():
    support.drop(DATABASE)


def runtime_parameters():
    return {
        "dbname": DATABASE,
        "user": "mvp_runtime",
        "password": os.environ["MVP_RUNTIME_PASSWORD"],
        "host": os.environ.get("PGHOST"),
        "port": os.environ.get("PGPORT"),
    }


def probe_connection():
    import psycopg

    return psycopg.connect(**runtime_parameters())


def invariant_failures():
    import psycopg

    with psycopg.connect(
        dbname=DATABASE,
        user="mvp_provisioning",
        password=os.environ["MVP_PROVISIONING_PASSWORD"],
        host=os.environ.get("PGHOST"),
        port=os.environ.get("PGPORT"),
    ) as connection:
        failures = invariants.check(connection)
        connection.rollback()
    return failures


def open_runtime_database(cursor_factory):
    return PsycopgDatabase(
        connection_parameters=runtime_parameters() | {"cursor_factory": cursor_factory}
    )


def one_run():
    return runner.run(
        open_runtime_database,
        probe_connection=probe_connection,
        invariant_failures=invariant_failures(),
    )


class TheRunPassesAgainstTheRegisteredFixtures(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.artifact = runner.run_twice(
            open_runtime_database,
            probe_connection=probe_connection,
            invariant_failures=invariant_failures(),
        )
        cls.document = cls.artifact.as_json()

    def test_the_verdict_is_pass(self):
        self.assertIs(self.artifact.verdict, Verdict.PASS)
        self.assertEqual(self.artifact.failed, ())

    def test_every_registered_fixture_ran_and_passed(self):
        self.assertEqual(
            [fixture["identifier"] for fixture in self.document["fixtures"]],
            [case.identifier for case in REGISTERED],
        )
        for fixture in self.document["fixtures"]:
            with self.subTest(identifier=fixture["identifier"]):
                self.assertEqual(fixture["verdict"], "pass")
                self.assertIsNone(fixture["failure_class"])

    def test_every_group_is_represented(self):
        # Section 4.9 groups the checks A to E and says each exists because an
        # obligation requires it. A run missing a group is a run that did not
        # check something the contract asked for.
        groups = {check["group"] for check in self.document["checks"]}
        groups |= {
            check["group"]
            for fixture in self.document["fixtures"]
            for check in fixture["checks"]
        }
        self.assertEqual(groups, {"A", "B", "C", "D", "E"})

    def test_the_artifact_records_the_section_4_10_evidence(self):
        self.assertEqual(
            self.document["state_digest"]["before"], self.document["state_digest"]["after"]
        )
        for name in ("INSERT", "UPDATE", "DELETE", "CREATE TABLE"):
            with self.subTest(statement=name):
                recorded = self.document["refusals"][name]
                self.assertTrue(recorded["refused"])
                self.assertEqual(recorded["sqlstate"], "42501")

    def test_it_records_the_registered_statement_timeout(self):
        # Section 4.4 fixes `statement_timeout = 5s` at the role level.
        self.assertEqual(self.document["environment"]["statement_timeout"], "5s")

    def test_the_runtime_identity_is_the_one_that_connected(self):
        self.assertEqual(self.document["environment"]["runtime_roles"], ["mvp_runtime"])

    def test_it_records_the_committed_template_digests(self):
        registered = self.document["environment"]["registered_templates"]
        # mvp-v0.1 Section 4.4's four, and entity-discovery-v0.1 Section 4.4's
        # three registered beside them (#143). The artifact records every
        # committed text B1 compared against, so the count is the registry's.
        self.assertEqual(len(registered), 7)
        for entry in registered:
            with self.subTest(template=entry["name"]):
                self.assertEqual(len(entry["sha256"]), 64)

    def test_the_artifact_is_json(self):
        self.assertEqual(json.loads(json.dumps(self.document)), self.document)


class D1ComparesTwoRuns(unittest.TestCase):
    def test_two_runs_are_identical_once_the_two_named_fields_are_removed(self):
        # Both runs share one invariant-check result, which is how
        # `runner.run_twice` calls them and, per the next test, the only way
        # `D1` can hold.
        failures = invariant_failures()
        first = runner.run(
            open_runtime_database,
            probe_connection=probe_connection,
            invariant_failures=failures,
        ).as_json()
        second = runner.run(
            open_runtime_database,
            probe_connection=probe_connection,
            invariant_failures=failures,
        ).as_json()
        self.assertNotEqual(first["run_identifier"], second["run_identifier"])
        self.assertEqual(comparable(first), comparable(second))

    def test_run_twice_produces_a_passing_d1(self):
        artifact = runner.run_twice(
            open_runtime_database,
            probe_connection=probe_connection,
            invariant_failures=invariant_failures(),
        )
        determinism = next(c for c in artifact.run_checks if c.identifier == "D1")
        self.assertTrue(determinism.passed, determinism.detail)

    def test_the_digest_is_stable_while_only_the_runtime_identity_reads(self):
        # Section 4.9 excludes exactly two fields from `D1`, so everything
        # else in the artifact has to be reproducible -- including the
        # transaction identifier Section 4.10 puts in the digest. It is,
        # because the runtime identity cannot write and a refused statement is
        # never assigned one.
        with probe_connection() as connection:
            first = probes.state_digest(connection)
            connection.rollback()
        probes.refusals(probe_connection)
        for case in REGISTERED[:3]:
            runner.run(
                open_runtime_database,
                probe_connection=probe_connection,
                invariant_failures=[],
            )
        with probe_connection() as connection:
            second = probes.state_digest(connection)
            connection.rollback()
        self.assertEqual(first, second)

    def test_the_digest_ignores_transactions_that_wrote_nothing_visible(self):
        # `db/invariants.py` proves constraint enforcement by inserting rows
        # inside savepoints and rolling them back. Those inserts consume
        # cluster transaction identifiers, which is why Section 4.10's digest
        # is built on `max(xmin)` over the four tables rather than on the
        # cluster counter: a transaction that left no visible row is not a
        # change to the state this identity can read, and a digest that moved
        # for one would make `D1` fail for something that did not happen.
        with probe_connection() as connection:
            before = probes.state_digest(connection)
            connection.rollback()
        invariant_failures()
        probes.refusals(probe_connection)
        with probe_connection() as connection:
            after = probes.state_digest(connection)
            connection.rollback()
        self.assertEqual(before, after)

    def test_the_digest_still_notices_a_write_that_preserves_row_counts(self):
        # The other half. A digest that ignored everything would satisfy the
        # test above and be worthless, so this one changes the data without
        # changing a single count and requires the digest to move.
        import psycopg

        with probe_connection() as connection:
            before = probes.state_digest(connection)
            connection.rollback()
        with psycopg.connect(
            dbname=DATABASE,
            user="mvp_provisioning",
            password=os.environ["MVP_PROVISIONING_PASSWORD"],
            host=os.environ.get("PGHOST"),
            port=os.environ.get("PGPORT"),
            autocommit=True,
        ) as connection, connection.cursor() as cursor:
            cursor.execute("UPDATE mvp.source_snapshot SET ingested_at = ingested_at")
        with probe_connection() as connection:
            after = probes.state_digest(connection)
            connection.rollback()
        self.assertEqual(before["row_counts"], after["row_counts"])
        self.assertNotEqual(
            before["highest_transaction_id"], after["highest_transaction_id"]
        )


class B1AgainstTheSealBypass(unittest.TestCase):
    """Issue #28's forgery, run for real, with `B1` required to catch it."""

    ROGUE_SQL = (
        "SELECT s.project_code\n"
        "  FROM mvp.source_snapshot AS s\n"
        " WHERE s.project_code = %(project_code)s\n"
        " ORDER BY s.project_code NULLS LAST\n"
        " LIMIT 5"
    )

    def forge(self):
        """A working template carrying unregistered SQL, built #28's way.

        `type(TPL_MESSAGE_FACTS_V1)` needs no import, and `_SEAL` is an
        underscore-prefixed module attribute that nothing stops another module
        from importing. It takes a *registered name* on purpose: that is the
        case a name-based `B1` would wave through.
        """
        from evidence_first_rag.registry.template import _SEAL, LimitMeaning

        rogue_class = type(TPL_MESSAGE_FACTS_V1)
        return rogue_class(
            seal=_SEAL,
            name="TPL_MESSAGE_FACTS_V1",
            version="2",
            sql=self.ROGUE_SQL,
            required_parameters=("project_code",),
            result_columns=("project_code",),
            ordering=("project_code",),
            row_limit=5,
            limit_meaning=LimitMeaning.TRUNCATES,
            declared_limitations=(LimitationKind.TRUNCATED_BY_LIMIT,),
        )

    def test_the_forgery_still_works_or_the_seal_was_closed(self):
        try:
            rogue = self.forge()
        except Exception as refused:  # noqa: BLE001
            self.skipTest(f"the seal now refuses the #28 path: {refused}")
        self.assertEqual(rogue.name, "TPL_MESSAGE_FACTS_V1")
        self.assertNotEqual(rogue.sql, TPL_MESSAGE_FACTS_V1.sql)

    def test_the_session_port_now_refuses_the_forgery_outright(self):
        """The defence moved from detection to prevention.

        When this class was written the forgery *ran*: `PsycopgSession.execute`
        type-checked nothing, so any object with `.name`, `.sql` and `.bind`
        reached the driver, and `B1` catching it afterwards was the whole
        guarantee. An external review found that hole, and the port now
        requires identity with the registered object -- so this forgery no
        longer executes at all, even though it takes a registered name.
        """
        try:
            rogue = self.forge()
        except Exception as refused:  # noqa: BLE001
            self.skipTest(f"the seal now refuses the #28 path: {refused}")

        statements = []
        database = RecordingDatabase(open_runtime_database(recording_cursor(statements)))
        with database.session() as session:
            with self.assertRaises(Fault) as raised:
                session.execute(rogue, {"project_code": "SAMPLE_PROJECT_ALPHA"})
        self.assertIn("not the registered template", str(raised.exception))
        # Nothing reached the database, so there is nothing for `B1` to find.
        self.assertEqual(statements, [])

    def test_b1_still_catches_the_statement_if_it_reaches_the_driver(self):
        """Prevention and detection are separate claims, so both are asserted.

        The port refuses the forgery today. `B1` is what holds if some future
        path reaches `cursor.execute` without passing that check -- which is
        exactly the assumption the review showed to be false last time, so it
        is not one to rest on again. Here the statement is handed to `B1`
        directly, as the driver would have recorded it.
        """
        try:
            rogue = self.forge()
        except Exception as refused:  # noqa: BLE001
            self.skipTest(f"the seal now refuses the #28 path: {refused}")

        result = checks.b1([rogue.sql], [], 1)
        self.assertFalse(result.passed)
        self.assertEqual(result.failure_class, "runtime")
        self.assertIn("without matching a registered template text", result.detail)

    def test_the_same_run_would_pass_a_name_based_check(self):
        # Why `B1` compares texts and never names. This is the check that was
        # not written, shown failing to catch what the real one catches.
        try:
            rogue = self.forge()
        except Exception as refused:  # noqa: BLE001
            self.skipTest(f"the seal now refuses the #28 path: {refused}")
        from evidence_first_rag.registry import names

        self.assertIn(rogue.name, names())


class TheRunnerFailsWhenItShould(unittest.TestCase):
    def test_a_corrupted_expectation_fails_a1_and_names_the_path(self):
        original = expected.registered("FX-001")
        tampered = json.loads(json.dumps(original))
        tampered["rows"][0]["transmit_period_ms"] = 999
        result = checks.a1(REGISTERED[0], original, tampered)
        self.assertFalse(result.passed)
        self.assertEqual(result.failure_class, "data")
        self.assertIn("rows[0].transmit_period_ms", result.detail)

    def test_a_failing_check_makes_the_whole_run_fail(self):
        artifact = one_run()
        self.assertIs(artifact.verdict, Verdict.PASS)
        broken = runner.dataclasses.replace(
            artifact,
            run_checks=artifact.run_checks
            + (checks.c1(["source_snapshot lost a unique constraint"]),),
        )
        self.assertIs(broken.verdict, Verdict.FAIL)

    def test_the_refusal_probes_leave_nothing_behind(self):
        # They attempt four writes. Section 4.10 requires the database
        # unchanged from the run's start to its end, so the probes must not be
        # the thing that changes it.
        with probe_connection() as connection:
            before = probes.state_digest(connection)
            connection.rollback()
        probes.refusals(probe_connection)
        with probe_connection() as connection:
            after = probes.state_digest(connection)
            connection.rollback()
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main(verbosity=2)
