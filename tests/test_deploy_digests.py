"""`deploy-v0.1` `DP-006`, `DP-007`'s comparison and `DP-011`, without a database."""

import copy
import json
import pathlib
import tempfile
import unittest

from evidence_first_rag.deploy import digests


def conformance(**overrides):
    document = {
        "state_digest": {
            "before": {"row_counts": {"a": 1}, "highest_transaction_id": "1"},
            "after": {"row_counts": {"b": 2, "a": 1}, "highest_transaction_id": "900"},
        },
        "environment": {"registered_templates": [
            {"name": "t2", "version": "1", "sha256": "bb"},
            {"name": "t1", "version": "1", "sha256": "aa"},
        ]},
        "fixtures": [{"identifier": "FX-001", "verdict": "pass"}, {"identifier": "FX-002", "verdict": "pass"}],
    }
    document.update(overrides)
    return document


class TheStableDigest(unittest.TestCase):
    def test_the_transaction_identifier_is_left_out(self):
        left = digests.stable_digest(conformance(), "r")
        other = conformance()
        other["state_digest"]["after"]["highest_transaction_id"] = "12345"
        self.assertEqual(left, digests.stable_digest(other, "r"))
        self.assertNotIn("highest_transaction_id", json.dumps(left))

    def test_order_does_not_matter(self):
        reordered = conformance()
        reordered["environment"]["registered_templates"].reverse()
        self.assertEqual(digests.stable_digest(conformance(), "r"), digests.stable_digest(reordered, "r"))


class TheDifferences(unittest.TestCase):
    def base(self):
        return digests.stable_digest(conformance(), "r")

    def test_equal_states_differ_on_nothing(self):
        self.assertEqual(digests.differences(self.base(), self.base()), [])

    def test_a_row_count_names_its_table(self):
        other = copy.deepcopy(self.base())
        other["row_counts"]["b"] = 3
        self.assertEqual(digests.differences(self.base(), other), ["row_counts.b"])

    def test_a_missing_table_is_a_difference(self):
        other = copy.deepcopy(self.base())
        del other["row_counts"]["a"]
        self.assertEqual(digests.differences(self.base(), other), ["row_counts.a"])

    def test_the_registry_digest(self):
        self.assertEqual(digests.differences(self.base(), digests.stable_digest(conformance(), "other")), ["registry_digest"])

    def test_a_template_digest(self):
        changed = conformance()
        changed["environment"]["registered_templates"][0]["sha256"] = "cc"
        self.assertEqual(digests.differences(self.base(), digests.stable_digest(changed, "r")), ["templates"])


class TheCommandLine(unittest.TestCase):
    def write(self, directory, name, document):
        path = pathlib.Path(directory) / name
        path.write_text(json.dumps(document))
        return str(path)

    def test_compare_passes_equal_and_fails_a_verdict_change(self):
        with tempfile.TemporaryDirectory() as directory:
            digest = self.write(directory, "d.json", digests.stable_digest(conformance(), "r"))
            same = self.write(directory, "c.json", conformance())
            changed = self.write(directory, "x.json", conformance(fixtures=[{"identifier": "FX-001", "verdict": "fail"}, {"identifier": "FX-002", "verdict": "pass"}]))
            arguments = ["compare", "--deployed-digest", digest, "--local-digest", digest, "--local-conformance", same]
            self.assertEqual(digests.main(arguments + ["--deployed-conformance", same]), 0)
            self.assertEqual(digests.main(arguments + ["--deployed-conformance", changed]), 1)

    def test_restored_compares_against_the_expected_digest(self):
        with tempfile.TemporaryDirectory() as directory:
            good = digests.stable_digest(conformance(), "r")
            restored = self.write(directory, "r.json", good)
            expected = self.write(directory, "e.json", good)
            other = self.write(directory, "o.json", dict(good, registry_digest="x"))
            self.assertEqual(digests.main(["restored", "--digest", restored, "--expected", expected]), 0)
            self.assertEqual(digests.main(["restored", "--digest", restored, "--expected", other]), 1)


if __name__ == "__main__":
    unittest.main()
