"""`scripts/third_party_licenses.py`: what each row of the license table says."""

import email.message
import importlib.util
import pathlib
import unittest

_PATH = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "third_party_licenses.py"
_SPEC = importlib.util.spec_from_file_location("third_party_licenses", _PATH)
licenses = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(licenses)


class Distribution:
    def __init__(self, name, version, **fields):
        self.version = version
        self.metadata = email.message.Message()
        self.metadata["Name"] = name
        for key, value in fields.items():
            for item in value if isinstance(value, list) else [value]:
                self.metadata[key.replace("_", "-")] = item


class TheRows(unittest.TestCase):
    def test_an_expression_wins_over_classifiers(self):
        row = licenses.rows([Distribution("A", "1", License_Expression="MIT", Classifier=["License :: OSI Approved :: BSD License"])])
        self.assertEqual(row, ["| `a` | 1 | MIT |"])

    def test_classifiers_then_the_license_field_then_none(self):
        rows = licenses.rows([
            Distribution("b", "2", Classifier=["License :: OSI Approved :: MIT License", "Programming Language :: Python"]),
            Distribution("c", "3", License="BSD 3-Clause\nfull text"),
            Distribution("d", "4"),
        ])
        self.assertEqual(rows, ["| `b` | 2 | MIT License |", "| `c` | 3 | BSD 3-Clause |", "| `d` | 4 | (none declared) |"])

    def test_the_installer_and_this_project_are_left_out_and_rows_are_sorted(self):
        rows = licenses.rows([Distribution(name, "1", License_Expression="MIT") for name in ("zeta", "pip", "Alpha", "setuptools", "evidence-first-rag")])
        self.assertEqual(rows, ["| `alpha` | 1 | MIT |", "| `zeta` | 1 | MIT |"])

    def test_a_distribution_with_no_name_is_listed_under_its_directory_name_not_fatal(self):
        # #311 O1: one broken install must not stop the table.
        unnamed = Distribution("x", "5", License_Expression="MIT")
        del unnamed.metadata["Name"]
        unnamed._path = "/site/broken-5.dist-info"
        self.assertEqual(licenses.rows([unnamed]), ["| `broken-5.dist-info` | 5 | MIT |"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
