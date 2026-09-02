"""No public arbitrary-SQL, arbitrary-table, or arbitrary-column interface.

Charter Section 3.1 and AGENTS.md fix this boundary, and Section 4.4 states it
as a registry safeguard: "No public interface accepts SQL text, a table name,
or a column name from a caller."

That is a claim about what the module does *not* have, and an absence is not
something a normal test observes. So this file enumerates the public surface
and pins it. Adding an entry point that takes SQL has to fail here rather than
pass review, and adding any new export has to be a deliberate edit to the list
below — which is the point at which somebody asks what it accepts.
"""

import inspect
import unittest

from evidence_first_rag import registry

# Every name the package exports. Changing this list is the review moment.
PUBLIC_SURFACE = {
    "FORBIDDEN_KEYWORDS",
    "LimitMeaning",
    "ParameterError",
    "REGISTERED",
    "SCHEMA",
    "TPL_MESSAGE_FACTS_V1",
    "TPL_SIGNAL_FACTS_V1",
    "TPL_SIGNAL_MAPPING_V1",
    "TPL_SNAPSHOT_CANDIDATES_V1",
    "Template",
    "TemplateError",
    "UnregisteredTemplate",
    "get",
    "names",
}

# Parameter names that would mean a caller is handing over SQL, a table, or a
# column. Section 4.4 forbids an interface that accepts any of them.
CALLER_SUPPLIED_SQL = {
    "sql", "query", "statement", "text", "where", "order_by", "ordering_clause",
    "table", "table_name", "tables", "schema_name", "relation",
    "column", "column_name", "columns", "select", "projection", "expression",
}


class ThePublicSurfaceIsPinned(unittest.TestCase):
    def test_all_matches_the_list_this_file_reviews(self):
        self.assertEqual(set(registry.__all__), PUBLIC_SURFACE)

    def test_nothing_public_is_exported_outside_all(self):
        exported = {
            name
            for name in dir(registry)
            if not name.startswith("_")
            and not inspect.ismodule(getattr(registry, name))
        }
        self.assertEqual(exported, PUBLIC_SURFACE)


class NoEntryPointAcceptsSqlFromACaller(unittest.TestCase):
    def public_callables(self):
        for name in sorted(registry.__all__):
            value = getattr(registry, name)
            if inspect.isfunction(value):
                yield f"{name}()", value
            elif inspect.isclass(value):
                for method_name, method in inspect.getmembers(value, inspect.isfunction):
                    if not method_name.startswith("_"):
                        yield f"{name}.{method_name}()", method

    def test_no_public_callable_takes_a_sql_table_or_column_parameter(self):
        for label, function in self.public_callables():
            parameters = set(inspect.signature(function).parameters) - {"self", "cls"}
            offending = sorted(parameters & CALLER_SUPPLIED_SQL)
            with self.subTest(callable=label):
                self.assertEqual(
                    offending,
                    [],
                    f"{label} accepts {offending} from a caller (Section 4.4)",
                )

    def test_the_registry_lookup_takes_a_name_and_nothing_else(self):
        # `get()` is the only way in. If it ever grew a second parameter, that
        # parameter would be the thing a caller could use to change the query.
        self.assertEqual(list(inspect.signature(registry.get).parameters), ["name"])

    def test_a_template_cannot_be_edited_after_registration(self):
        # Frozen: the SQL a template carries is the SQL that was reviewed.
        import dataclasses

        with self.assertRaises(dataclasses.FrozenInstanceError):
            registry.TPL_MESSAGE_FACTS_V1.sql = "SELECT 1"

    def test_the_sql_of_every_registered_template_is_committed_text(self):
        # Charter Section 3.1: "The committed public query-template registry
        # contains the inspectable SQL." Not assembled at import time from
        # anything a caller could reach -- the only interpolation is the schema
        # constant, which is a provisioning fact, not caller input.
        for template in registry.REGISTERED:
            with self.subTest(template=template.name):
                self.assertIn("SELECT", template.sql)
                self.assertIn(registry.SCHEMA + ".", template.sql)
                self.assertNotIn("{", template.sql)


if __name__ == "__main__":
    unittest.main(verbosity=2)
