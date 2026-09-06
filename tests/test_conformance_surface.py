"""Two absences the conformance runner's credibility rests on.

**No language model.** Charter Section 3.3 forbids a model from judging
conformance of its own output, and Framework Section 5.7 assigns that
judgement to this contract. That is the single most load-bearing claim this
package makes about itself, and a docstring saying so is not evidence.

**All non-registry SQL in one file.** Section 4.9's `B1` asserts that the
runtime executed only registered templates, while Section 4.10 requires the
runner to issue statements of its own -- a digest, four refusal probes, a
`SHOW`. Both are in the contract, so `B1` has to be scoped to the runtime, and
that scoping is only honest if the runner's own statements are somewhere a
reviewer can find all of them. `probes.py` is that place, and this test is
what keeps it true.
"""

import ast
import pathlib
import unittest

from evidence_first_rag import conformance

PACKAGE = pathlib.Path(conformance.__file__).resolve().parent
PROBES = PACKAGE / "probes.py"

# Anything that would mean a model, a network call, or a subprocess is
# involved in reaching a verdict.
FORBIDDEN_IMPORTS = {
    "anthropic", "openai", "google", "cohere", "mistralai", "ollama", "llama_cpp",
    "transformers", "torch", "requests", "httpx", "urllib", "http", "socket",
    "subprocess", "aiohttp",
}

SQL_KEYWORDS = ("SELECT ", "INSERT ", "UPDATE ", "DELETE ", "CREATE ", "SHOW ", "DROP ")


def modules():
    return sorted(path for path in PACKAGE.glob("*.py"))


def string_constants(tree):
    """Every string literal that is not a docstring."""
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", None)
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                if isinstance(body[0].value.value, str):
                    docstrings.add(id(body[0].value))
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
    ]


class NoLanguageModelReachesAVerdict(unittest.TestCase):
    def test_no_module_imports_a_model_a_network_client_or_a_subprocess(self):
        for path in modules():
            with self.subTest(module=path.name):
                tree = ast.parse(path.read_text())
                imported = set()
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        imported.update(a.name.split(".")[0] for a in node.names)
                    elif isinstance(node, ast.ImportFrom) and node.module:
                        imported.add(node.module.split(".")[0])
                self.assertEqual(imported & FORBIDDEN_IMPORTS, set())

    def test_the_check_would_notice_one(self):
        # The scan itself, probed on a module that does import one, so that
        # this is a test somebody has seen fail rather than a filter that
        # might match nothing.
        tree = ast.parse("import anthropic\n\ndef judge():\n    return 'pass'\n")
        imported = {
            alias.name.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        self.assertTrue(imported & FORBIDDEN_IMPORTS)


class EveryNonRegistryStatementIsInProbes(unittest.TestCase):
    def test_no_other_module_carries_a_sql_literal(self):
        for path in modules():
            if path == PROBES:
                continue
            with self.subTest(module=path.name):
                for literal in string_constants(ast.parse(path.read_text())):
                    upper = literal.upper()
                    found = [word for word in SQL_KEYWORDS if word in upper]
                    self.assertEqual(found, [], f"{path.name} carries SQL: {literal[:80]!r}")

    def test_probes_does_carry_them(self):
        # The other half: if the statements ever move out of `probes.py`, the
        # test above keeps passing for the wrong reason and this one fails.
        literals = " ".join(string_constants(ast.parse(PROBES.read_text()))).upper()
        for word in ("SELECT ", "INSERT ", "UPDATE ", "DELETE ", "CREATE ", "SHOW "):
            with self.subTest(keyword=word.strip()):
                self.assertIn(word, literals)


class ThePureSuiteNeedsNoDriver(unittest.TestCase):
    def test_importing_the_package_pulls_in_no_psycopg(self):
        # The `repository-checks` CI job does not install the package, so a
        # module-level driver import here would fail the whole suite for a
        # reason unrelated to the branch.
        for path in modules():
            with self.subTest(module=path.name):
                tree = ast.parse(path.read_text())
                top_level = [
                    node
                    for node in tree.body
                    if isinstance(node, (ast.Import, ast.ImportFrom))
                ]
                names = set()
                for node in top_level:
                    if isinstance(node, ast.Import):
                        names.update(a.name.split(".")[0] for a in node.names)
                    elif node.module:
                        names.add(node.module.split(".")[0])
                self.assertNotIn("psycopg", names)


if __name__ == "__main__":
    unittest.main(verbosity=2)
