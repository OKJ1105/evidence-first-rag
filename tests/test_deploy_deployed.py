"""`deploy-v0.1` Section 4.8's two helpers, without a database."""

import json
import pathlib
import tempfile
import unittest

from evidence_first_rag.deploy import deployed


class Refusals:
    class InsufficientPrivilege(Exception):
        pass

    class ReadOnlySqlTransaction(Exception):
        pass


class FakeConnection:
    def __init__(self, behaviour):
        self.behaviour = behaviour
        self.autocommit = False

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def cursor(self):
        return self

    def execute(self, statement):
        self.behaviour(statement)

    def fetchone(self):
        return (1,)


class TheWrites(unittest.TestCase):
    def outcome(self, behaviour):
        return deployed.refused_writes(lambda: FakeConnection(behaviour), Refusals)

    def test_a_privilege_refusal_of_every_write_passes(self):
        def behaviour(statement):
            if statement.split()[0] in {"INSERT", "UPDATE", "DELETE", "CREATE", "DROP"}:
                raise Refusals.InsufficientPrivilege()

        self.assertEqual(set(self.outcome(behaviour).values()), {"refused"})

    def test_a_write_that_succeeds_is_reported(self):
        def behaviour(statement):
            if statement.startswith(("INSERT", "UPDATE", "CREATE", "DROP")):
                raise Refusals.InsufficientPrivilege()

        self.assertEqual(self.outcome(behaviour)["DELETE"], "performed")

    def test_a_refusal_by_transaction_mode_is_not_a_pass(self):
        def behaviour(statement):
            if statement.startswith(("INSERT", "UPDATE", "DELETE", "CREATE", "DROP")):
                raise Refusals.ReadOnlySqlTransaction()

        self.assertTrue(all(value != "refused" for value in self.outcome(behaviour).values()))

    def test_every_write_the_contract_names_is_tried(self):
        self.assertEqual(set(deployed.WRITES), {"INSERT", "UPDATE", "DELETE", "CREATE", "DROP"})


class TheRollbackTarget(unittest.TestCase):
    def records(self, *rows):
        directory = pathlib.Path(tempfile.mkdtemp())
        for index, row in enumerate(rows):
            (directory / f"deploy-{index}.json").write_text(json.dumps(row))
        return directory

    def test_none_before_the_first_passing_deploy(self):
        self.assertIsNone(deployed.last_passing_commit(self.records()))
        failed = {"date": "2026-01-01T00:00:00+00:00", "commit": "a" * 40, "outcome": "failure", "deployed_checks": "fail"}
        self.assertIsNone(deployed.last_passing_commit(self.records(failed)))

    def test_the_newest_passing_record_wins(self):
        old = {"date": "2026-01-01T00:00:00+00:00", "commit": "a" * 40, "outcome": "success", "deployed_checks": "pass"}
        new = {"date": "2026-02-01T00:00:00+00:00", "commit": "b" * 40, "outcome": "success", "deployed_checks": "pass"}
        newer_failed = {"date": "2026-03-01T00:00:00+00:00", "commit": "c" * 40, "outcome": "failure", "deployed_checks": "fail"}
        self.assertEqual(deployed.last_passing_commit(self.records(old, new, newer_failed)), "b" * 40)

    def test_the_commit_being_deployed_is_never_its_own_target(self):
        old = {"date": "2026-01-01T00:00:00+00:00", "commit": "a" * 40, "outcome": "success", "deployed_checks": "pass"}
        same = {"date": "2026-02-01T00:00:00+00:00", "commit": "b" * 40, "outcome": "success", "deployed_checks": "pass"}
        self.assertEqual(deployed.last_passing_commit(self.records(old, same), excluding="b" * 40), "a" * 40)

    def test_the_expected_digest_is_the_passing_records(self):
        digest = {"row_counts": {"a": 1}, "registry_digest": "r", "templates": []}
        passing = {"date": "2026-01-01T00:00:00+00:00", "commit": "a" * 40, "outcome": "success", "deployed_checks": "pass", "stable_digest": digest}
        failed = {"date": "2026-02-01T00:00:00+00:00", "commit": "b" * 40, "outcome": "failure", "deployed_checks": "fail", "stable_digest": {}}
        records = self.records(passing, failed)
        self.assertEqual(deployed.stable_digest_of("a" * 40, records), digest)
        with self.assertRaises(ValueError):
            deployed.stable_digest_of("b" * 40, records)

    def test_a_passing_record_without_a_digest_is_an_error(self):
        bare = {"date": "2026-01-01T00:00:00+00:00", "commit": "a" * 40, "outcome": "success", "deployed_checks": "pass"}
        with self.assertRaises(ValueError):
            deployed.stable_digest_of("a" * 40, self.records(bare))

    def test_a_missing_records_directory_is_an_error(self):
        with self.assertRaises(FileNotFoundError):
            deployed.last_passing_commit(pathlib.Path(tempfile.mkdtemp()) / "absent")

    def test_the_committed_records_directory_exists(self):
        self.assertTrue((pathlib.Path(__file__).resolve().parents[1] / deployed.RECORDS).is_dir())

    def test_a_run_whose_checks_did_not_run_is_not_passing(self):
        unchecked = {"date": "2026-01-01T00:00:00+00:00", "commit": "a" * 40, "outcome": "success", "deployed_checks": "not run"}
        self.assertIsNone(deployed.last_passing_commit(self.records(unchecked)))


if __name__ == "__main__":
    unittest.main()
