"""`api-v0.1` Section 4.7: the three decisions the entry point makes.

`api/serve.py` is the one module that reads an environment, and each of the
three things it decides is an obligation of Section 4.7 rather than a
convenience. So each is asserted here over an environment handed in, with no
database, no container and no server: `build` opens no connection, which is
what makes that possible.

The fourth obligation of Section 4.7 -- that the *stack* separates the two
identities -- is not this module's to satisfy and is asserted in
`tests/test_local_stack.py` against the compose file.
"""

import ast
import pathlib
import unittest

# The module is read from disk unconditionally and imported conditionally.
# Two of the obligations below are properties of its *source* -- what it may
# not name -- and those hold whether or not the `api` extra is installed, so
# they are asserted in every job rather than skipped in the ones that would
# leave the prohibition unchecked (#101).
SERVE_PATH = (
    pathlib.Path(__file__).resolve().parents[1]
    / "src"
    / "evidence_first_rag"
    / "api"
    / "serve.py"
)

try:
    from evidence_first_rag.api import serve

    HAS_API = True
except ImportError:  # pragma: no cover - exercised by the extra-free job
    serve = None
    HAS_API = False

# A password-shaped value that is not a password. Every string in this file is
# `SAMPLE_*` for the reason AGENTS.md gives: a test fixture that looks like a
# credential is read as one by whoever finds it next.
RUNTIME_PASSWORD = "SAMPLE_RUNTIME_NOT_A_SECRET"

BASE = {"MVP_RUNTIME_PASSWORD": RUNTIME_PASSWORD, "PGHOST": "database", "PGPORT": "5432"}

SERVE_SOURCE = SERVE_PATH.read_text(encoding="utf-8")


def code_only(source: str) -> str:
    """`source` with its comments and docstrings removed, and nothing else.

    The prohibition below is about what the module **reads**, not what it says.
    Checked against the raw text it fails on the docstring that explains the
    rule, which would push the explanation out of the file to satisfy a test.

    **Docstrings, not every string.** An earlier version of this dropped every
    string literal, which removed `environment["MVP_PROVISIONING_PASSWORD"]`
    along with the prose -- so the assertion below passed over a module that
    read exactly what it may not. A mutation adding that read survived it, and
    that is how it was found. Only the first statement of a module, class or
    function is dropped, and only where it is a bare string: that is what a
    docstring is, and no other statement matches it.

    `ast.unparse` rather than a second pass over tokens, because it drops
    comments by construction -- they are not in the tree.
    """
    tree = ast.parse(source)
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if not isinstance(body, list) or not body:
            continue
        if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        first = body[0]
        if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
            if isinstance(first.value.value, str):
                del body[0]
    return ast.unparse(tree)


SERVE_CODE = code_only(SERVE_SOURCE)


class TheSourceNamesNoProvisioningCredential(unittest.TestCase):
    """The prohibition, as a property of the file. Runs everywhere, because a
    job without the `api` extra is exactly where a skip would hide it."""

    def test_the_provisioning_password_is_not_read_anywhere_in_this_module(self):
        """`connection_parameters` reading it would be caught by the behaviour
        assertion below; a second function added later, reading it for a
        migration or a health probe, would not be."""
        self.assertNotIn("MVP_PROVISIONING_PASSWORD", SERVE_CODE)
        # The superuser's, too: `db/provision.py` reads `PGPASSWORD`, and the
        # surface holding it would reach the database as the cluster owner.
        self.assertNotIn("PGPASSWORD", SERVE_CODE)
        # And the stripping itself, so the assertions above cannot pass by
        # removing everything: the module's own identifiers survive it.
        self.assertIn("RUNTIME_PASSWORD_VARIABLE", SERVE_CODE)
        self.assertIn(
            "MVP_PROVISIONING_PASSWORD",
            SERVE_SOURCE,
            "the docstring stopped explaining the rule",
        )

    def test_the_read_only_role_is_a_constant_rather_than_a_variable(self):
        """Read from the environment, the read-only guarantee would sit behind
        a value nobody reviews."""
        self.assertIn('RUNTIME_ROLE = "mvp_runtime"', SERVE_SOURCE)


@unittest.skipUnless(HAS_API, "the api extra is not installed")
class TheConnectionIsTheRuntimeIdentitys(unittest.TestCase):
    """Section 4.7: "The surface process never holds the provisioning
    credentials", and `mvp-v0.1` Section 4.3 makes that identity read-only."""

    def test_the_role_is_the_read_only_one_and_is_not_configurable(self):
        """A deployment that wanted to serve as the provisioning identity
        would have to change this file in a pull request. That is the point:
        an environment variable would put the read-only guarantee behind a
        value nobody reviews."""
        parameters = serve.connection_parameters(BASE | {"MVP_RUNTIME_ROLE": "postgres"})
        self.assertEqual(parameters["user"], "mvp_runtime")
        self.assertEqual(parameters["password"], RUNTIME_PASSWORD)

    def test_a_missing_runtime_password_fails_by_name(self):
        """Rather than starting a surface that answers every request
        `database_unavailable`, which reports a database condition for a
        deployment mistake."""
        with self.assertRaises(KeyError) as raised:
            serve.connection_parameters({"PGHOST": "database"})
        self.assertIn("MVP_RUNTIME_PASSWORD", str(raised.exception))

    def test_the_host_and_port_travel_as_given(self):
        parameters = serve.connection_parameters(BASE)
        self.assertEqual(parameters["host"], "database")
        self.assertEqual(parameters["port"], "5432")
        self.assertEqual(parameters["dbname"], "mvp")
        self.assertEqual(
            serve.connection_parameters(BASE | {"MVP_DATABASE": "mvp_other"})["dbname"],
            "mvp_other",
        )


@unittest.skipUnless(HAS_API, "the api extra is not installed")
class TheAdapterIsOptional(unittest.TestCase):
    """Section 4.7: "The adapter credential is read from the environment and is
    optional; absent, `/v1/ask` refuses per Section 4.5 and every other route
    works."""

    def test_no_credential_means_no_proposer(self):
        self.assertIsNone(serve.proposer({}))
        self.assertIsNone(serve.proposer({"ANTHROPIC_API_KEY": ""}))

    def test_the_surface_still_builds_without_one(self):
        """The half that matters: a stack that would not start without a model
        key would make the LLM a dependency of a system built not to need
        one."""
        app = serve.build(BASE)
        # `build` returns the app wrapped in the Section 4.7 request log.
        served = {route.path for route in app.app.routes}
        for path in ("/v1/query", "/v1/ask", "/v1/discover", "/v1/select", "/v1/health"):
            self.assertIn(path, served)

    def test_a_credential_builds_a_proposer_over_the_adapter(self):
        """Section 4.5's transport boundary is `SurfaceProposer`'s, so the
        entry point may not hand the adapter to the surface directly."""
        try:
            import anthropic  # noqa: F401
        except ImportError:
            self.skipTest("the adapter extra is not installed")
        from evidence_first_rag.api.app import SurfaceProposer

        built = serve.proposer({"ANTHROPIC_API_KEY": "SAMPLE_KEY_NOT_A_SECRET"})
        self.assertIsInstance(built, SurfaceProposer)


@unittest.skipUnless(HAS_API, "the api extra is not installed")
class TheProvenanceIsTheCommittedFixtures(unittest.TestCase):
    """`mvp-v0.1` Section 4.7 makes the provenance the caller's to state and
    never the runtime's to discover, so the entry point is the caller that
    states it."""

    def test_every_recorded_path_is_a_file_in_this_repository(self):
        """A provenance naming a file that is not here would put a path on
        every `source_trace` that no reader can open."""
        root = SERVE_PATH.resolve().parents[3]
        self.assertEqual(len(serve.FIXTURE_PROVENANCE), 6)
        for relative in serve.FIXTURE_PROVENANCE:
            with self.subTest(path=relative):
                self.assertTrue((root / relative).is_file(), relative)

    def test_the_fixture_tree_has_no_file_the_provenance_omits(self):
        """The direction the list above cannot check: a seventh fixture added
        to the tree and not recorded here would be loaded and never named."""
        root = SERVE_PATH.resolve().parents[3]
        present = {
            str(path.relative_to(root))
            for path in (root / "fixtures").rglob("*.jsonl")
        }
        self.assertEqual(present, set(serve.FIXTURE_PROVENANCE))


@unittest.skipUnless(HAS_API, "the api extra is not installed")
class TheRegisteredOriginComesFromTheEnvironment(unittest.TestCase):
    """`api-v0.1` Section 4.5 (`0.2.0`): `EFR_CORS_ORIGIN`, unset in the stack."""

    ORIGIN = "https://sample-origin.example"
    PREFLIGHT = {"Origin": ORIGIN, "Access-Control-Request-Method": "POST"}

    def test_set_it_admits_a_preflight(self):
        from fastapi.testclient import TestClient

        client = TestClient(serve.build({**BASE, "EFR_CORS_ORIGIN": self.ORIGIN}))
        self.assertEqual(client.options("/v1/query", headers=self.PREFLIGHT).status_code, 204)

    def test_unset_or_empty_it_admits_none(self):
        from fastapi.testclient import TestClient

        for environment in (BASE, {**BASE, "EFR_CORS_ORIGIN": ""}):
            client = TestClient(serve.build(environment))
            self.assertEqual(client.options("/v1/query", headers=self.PREFLIGHT).status_code, 405)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
