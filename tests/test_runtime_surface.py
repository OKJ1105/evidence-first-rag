"""Structural claims about the runtime that no ordinary test would notice.

Three of them, and each is an absence:

- The runtime never holds the provisioning credentials (Section 4.3). Written
  as a rule that is a sentence somebody has to keep remembering; written as an
  import that does not exist it is checkable.
- No public interface accepts SQL text, a table name, or a column name from a
  caller (Section 4.4, Charter Section 3.1). `tests/test_registry_surface.py`
  pins this for the registry; the runtime is the other package a caller
  reaches, so it is pinned here too.
- The decision path does not import the driver, which is what lets `tests/`
  run the whole of Sections 4.2, 4.5, 4.8 and 5 from a clean checkout. The
  driver is installed in this environment, so an accidental import would not
  make the suite fail -- it is caught by reading the source, not by running it.
"""

import inspect
import pathlib
import unittest

from evidence_first_rag import runtime

RUNTIME = pathlib.Path(runtime.__file__).resolve().parent
SOURCE = RUNTIME.parent

# Every name the package exports. Changing this list is the review moment.
PUBLIC_SURFACE = {
    "Answer",
    "DataFault",
    "Execution",
    "Fault",
    "Prose",
    "Refusal",
    "Request",
    "Runtime",
    "ValidatedRequest",
    "Value",
    "compose",
    "render",
    "validate",
    "values_of",
}

# The same list `tests/test_registry_surface.py` uses: parameter names that
# would mean a caller is handing over SQL, a table, or a column.
CALLER_SUPPLIED_SQL = {
    "sql", "query", "statement", "text", "where", "order_by", "ordering_clause",
    "table", "table_name", "tables", "schema_name", "relation",
    "column", "column_name", "columns", "select", "projection", "expression",
}


class ThePublicSurfaceIsPinned(unittest.TestCase):
    def test_all_matches_the_list_this_file_reviews(self):
        self.assertEqual(set(runtime.__all__), PUBLIC_SURFACE)

    def test_nothing_public_is_exported_outside_all(self):
        exported = {
            name
            for name in dir(runtime)
            if not name.startswith("_") and not inspect.ismodule(getattr(runtime, name))
        }
        self.assertEqual(exported, PUBLIC_SURFACE)

    def test_connection_is_not_reachable_through_the_package(self):
        # Importing `runtime` must not pull the driver in behind it.
        self.assertNotIn("connection", dir(runtime))


class NoEntryPointAcceptsSqlFromACaller(unittest.TestCase):
    def test_no_public_callable_takes_sql_a_table_or_a_column(self):
        for name in sorted(runtime.__all__):
            value = getattr(runtime, name)
            owner = value if inspect.isclass(value) else type(value)
            targets = [(f"{name}()", value)] if inspect.isfunction(value) else []
            if owner.__module__.split(".")[0] == "evidence_first_rag":
                targets += [
                    (f"{name}.{method_name}()", method)
                    for method_name, method in inspect.getmembers(
                        owner, inspect.isfunction
                    )
                    if not method_name.startswith("__")
                ]
            for label, target in targets:
                with self.subTest(callable=label):
                    parameters = set(inspect.signature(target).parameters)
                    self.assertEqual(parameters & CALLER_SUPPLIED_SQL, set())


class TheImportGraphSaysWhatTheContractSays(unittest.TestCase):
    def modules(self):
        return sorted(path for path in RUNTIME.glob("*.py"))

    def test_no_runtime_module_imports_the_provisioning_package(self):
        # Section 4.3: "The runtime never holds the provisioning credentials."
        # `db/` is where they are read, so the runtime not importing it is that
        # sentence in a form a test can check.
        for path in self.modules():
            with self.subTest(module=path.name):
                text = path.read_text()
                self.assertNotIn("from ..db", text)
                self.assertNotIn("from evidence_first_rag.db", text)
                self.assertNotIn("import evidence_first_rag.db", text)

    def test_only_connection_imports_the_driver(self):
        importers = [
            path.name for path in self.modules() if "import psycopg" in path.read_text()
        ]
        self.assertEqual(importers, ["connection.py"])

    def test_the_registrys_template_class_is_never_imported_here(self):
        # `tests/test_registry_surface.py` forbids this repository-wide; the
        # runtime is the module most likely to want it, so the claim is
        # restated where it would break first. Templates arrive through
        # `registry.get`, which is the only lookup Section 4.4 registers.
        for path in self.modules():
            with self.subTest(module=path.name):
                self.assertNotIn("import Template", path.read_text())


if __name__ == "__main__":
    unittest.main(verbosity=2)
