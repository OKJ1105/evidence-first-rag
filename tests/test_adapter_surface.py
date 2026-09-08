"""Three absences Section 4.7 and Section 4.6 state, kept true by reading source.

- **The baseline is never a fallback.** Section 4.7: "it is not a product
  path, it is not exposed by any public interface, and it is not a fallback
  when the adapter fails." That last one is what a well-meaning later change
  adds, so the import graph is where it is prevented.
- **Only `client.py` imports the SDK.** Everything else in this package is
  testable with no model, no network and no credential, which is what lets the
  pure suite cover Sections 4.6 and 4.7 from a clean checkout.
- **No public entry point takes SQL, a table, or a column.** The same claim
  `tests/test_registry_surface.py` and `tests/test_runtime_surface.py` pin for
  their packages.
"""

import ast
import inspect
import pathlib
import subprocess
import sys
import unittest

from evidence_first_rag import adapter

PACKAGE = pathlib.Path(adapter.__file__).resolve().parent

PUBLIC_SURFACE = {
    "Baseline",
    "CURATED",
    "CuratedEntry",
    "EVALUATION_SET",
    "EvaluationCase",
    "Judgement",
    "Metrics",
    "Outcome",
    "Proposal",
    "Report",
    "THRESHOLDS",
    "Thresholds",
    "answer",
    "compare",
    "judge",
    "measure",
    "normalize",
    "refused",
    "revalidate",
}

CALLER_SUPPLIED_SQL = {
    "sql", "query", "statement", "text", "where", "order_by", "ordering_clause",
    "table", "table_name", "tables", "schema_name", "relation",
    "column", "column_name", "columns", "select", "projection", "expression",
}


def modules():
    return sorted(path for path in PACKAGE.glob("*.py"))


def imported_modules(tree):
    """Every module name imported, relative or absolute.

    Two shapes bite here, and both were found by probing this helper rather
    than by reading it:

    - `from .baseline import X` puts the leading dots in `node.level` and
      leaves `node.module` as the bare `"baseline"`, so a test looking for
      `".baseline"` matches nothing and passes for the wrong reason.
    - `from . import baseline` has `node.module` of `None`, and the module
      name is in the *aliases*. A helper that only read `node.module` skipped
      that form completely -- which is the shape a fallback import would most
      naturally take.
    """
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.add(node.module.split(".")[-1])
            else:
                names.update(alias.name for alias in node.names)
    return names


class TheBaselineIsNeverAFallback(unittest.TestCase):
    def test_no_module_on_the_answering_path_imports_it(self):
        # Checked as imports rather than as the word, so that a docstring
        # explaining why the baseline is not a fallback does not itself fail
        # the test -- and so that an actual import cannot hide in a comment's
        # shadow.
        for name in ("revalidation.py", "client.py", "vocabulary.py", "comparison.py"):
            with self.subTest(module=name):
                imported = imported_modules(ast.parse((PACKAGE / name).read_text()))
                self.assertNotIn("baseline", imported)

    def test_the_probe_would_catch_a_fallback_being_added(self):
        # A scan that matches nothing passes quietly, so this is the shape it
        # is looking for.
        for source in ("from .baseline import Baseline\n", "from . import baseline\n"):
            with self.subTest(source=source.strip()):
                self.assertIn("baseline", imported_modules(ast.parse(source)))

    def test_the_baseline_module_imports_no_model_client(self):
        imported = imported_modules(ast.parse((PACKAGE / "baseline.py").read_text()))
        self.assertNotIn("client", imported)
        self.assertNotIn("anthropic", imported)


class OnlyTheClientImportsTheSdk(unittest.TestCase):
    def test_no_other_module_imports_anthropic(self):
        importers = [
            path.name for path in modules() if "anthropic" in imported_modules(ast.parse(path.read_text()))
        ]
        self.assertEqual(importers, ["client.py"])

    def test_the_client_is_not_part_of_the_public_surface(self):
        self.assertNotIn("Adapter", adapter.__all__)
        self.assertNotIn("client", adapter.__all__)

    def test_no_module_level_sdk_import_in_the_package_init(self):
        tree = ast.parse((PACKAGE / "__init__.py").read_text())
        self.assertNotIn("client", imported_modules(tree))

    def test_importing_the_package_pulls_in_no_sdk(self):
        """The claim, in a fresh interpreter.

        `dir(adapter)` cannot answer this: importing
        `evidence_first_rag.adapter.client` anywhere -- including from another
        test file -- binds `client` as an attribute of the package, so a
        `dir()` assertion passes or fails depending on which tests ran first.
        A subprocess with an empty module table is the only honest form, and
        it is also the environment `repository-checks` actually provides.
        """
        source = (
            "import sys, pathlib;"
            "sys.path.insert(0, 'src');"
            "import evidence_first_rag.adapter;"
            "assert 'anthropic' not in sys.modules, 'the SDK was imported';"
            "print('clean')"
        )
        finished = subprocess.run(
            [sys.executable, "-c", source],
            capture_output=True,
            text=True,
            cwd=pathlib.Path(__file__).resolve().parent.parent,
        )
        self.assertEqual(finished.returncode, 0, finished.stderr)
        self.assertIn("clean", finished.stdout)


class ThePublicSurfaceIsPinned(unittest.TestCase):
    def test_all_matches_the_list_this_file_reviews(self):
        self.assertEqual(set(adapter.__all__), PUBLIC_SURFACE)

    def test_nothing_public_is_exported_outside_all(self):
        exported = {
            name
            for name in dir(adapter)
            if not name.startswith("_") and not inspect.ismodule(getattr(adapter, name))
        }
        self.assertEqual(exported, PUBLIC_SURFACE)

    def test_no_public_callable_takes_sql_a_table_or_a_column(self):
        for name in sorted(adapter.__all__):
            value = getattr(adapter, name)
            owner = value if inspect.isclass(value) else type(value)
            targets = [(f"{name}()", value)] if inspect.isfunction(value) else []
            if owner.__module__.split(".")[0] == "evidence_first_rag":
                targets += [
                    (f"{name}.{method}()", function)
                    for method, function in inspect.getmembers(owner, inspect.isfunction)
                    if not method.startswith("__")
                ]
            for label, target in targets:
                with self.subTest(callable=label):
                    parameters = set(inspect.signature(target).parameters)
                    self.assertEqual(parameters & CALLER_SUPPLIED_SQL, set())


class TheAdapterNeverDecides(unittest.TestCase):
    """Section 4.6: "The adapter never selects a template, writes SQL, chooses
    ordering, or judges conformance."""

    def test_no_module_names_a_registered_template(self):
        for path in modules():
            with self.subTest(module=path.name):
                source = path.read_text()
                self.assertNotIn("TPL_", source)

    def test_no_module_carries_sql(self):
        for path in modules():
            with self.subTest(module=path.name):
                upper = path.read_text().upper()
                for keyword in ("SELECT ", "INSERT ", "ORDER BY"):
                    self.assertNotIn(keyword, upper)


if __name__ == "__main__":
    unittest.main(verbosity=2)
