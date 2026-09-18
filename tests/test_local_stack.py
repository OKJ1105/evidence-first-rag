"""`api-v0.1` Section 4.7, the half that is a property of the stack.

`tests/test_api_serve.py` asserts what the entry point reads. This asserts what
the stack *hands* it, which is a different question and the one the contract's
sentence is actually about: "The surface process never holds the provisioning
credentials." A surface that never reads them still holds them if the file that
starts it puts them in its environment.

**These are assertions over a file, and that is a weaker thing than a run.**
The run is the CI job named in the pull request, which starts the stack and
drives `WF-003` through it; a container runtime is not available to the writer
(`docker info` fails in that environment), so these are what can be checked
from a clean checkout. They are kept because they fail for a reason a run would
not explain: a run against a surface holding the provisioning password passes,
because holding a credential it does not use changes no response.

The critical assertions read the text rather than a parsed document, so they
run wherever the suite does. PyYAML is used for the structural ones, which are
brittle as text, and the module says so where it skips.
"""

import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "compose.yaml"
DOCKERFILE = ROOT / "Dockerfile"

TEXT = COMPOSE.read_text(encoding="utf-8")


def assignments(variable: str) -> list[str]:
    """The lines that *set* `variable`, which is not the same as naming it.

    `MVP_RUNTIME_PASSWORD: ${MVP_RUNTIME_PASSWORD:-…}` names it twice and sets
    it once: the second is the interpolation reading the person's own
    environment. Counting occurrences would have made every assertion below
    off by the number of defaults.
    """
    return [
        line.strip()
        for line in TEXT.splitlines()
        if line.strip().startswith(variable + ":")
    ]

# The credentials that provision. `db/provision.py` reads all three: the
# cluster superuser's password through `PGPASSWORD`, and the two role
# passwords by name. The surface's environment may carry exactly one of them.
PROVISIONING_ONLY = ("MVP_PROVISIONING_PASSWORD", "PGPASSWORD", "PGUSER")


class TheStackSeparatesTheTwoIdentities(unittest.TestCase):
    """Section 4.7, and `mvp-v0.1` Section 4.3's read-only grants behind it."""

    def test_each_provisioning_credential_is_named_exactly_once(self):
        """Once is the provisioning service. Twice is the surface having been
        given one too -- which is what this test exists to catch, and which no
        request to a running stack would reveal.

        Asserted as a count rather than by reading the surface block, so that
        it holds however the file is reorganised: a second occurrence is a
        second service carrying it, wherever it is written.
        """
        for variable in PROVISIONING_ONLY:
            with self.subTest(variable=variable):
                self.assertEqual(
                    len(assignments(variable)),
                    1,
                    f"{variable} is set in more than one service",
                )

    def test_the_runtime_password_reaches_both(self):
        """The provisioning service creates the role with it; the surface
        connects with it. Two services, so two occurrences -- and this is the
        assertion that makes the count above meaningful rather than a rule
        that every variable appears once."""
        self.assertEqual(len(assignments("MVP_RUNTIME_PASSWORD")), 2)

    def test_no_password_is_written_as_a_literal_default_without_saying_so(self):
        """Every default in this file is a `_not_a_secret` value for a stack on
        loopback holding `SAMPLE_*` fixtures. A default that did not say so
        would be a credential in the repository, which Section 4.7's last
        sentence forbids."""
        defaults = [
            line.strip()
            for line in TEXT.splitlines()
            if "PASSWORD" in line and ":-" in line
        ]
        self.assertGreaterEqual(len(defaults), 3)
        for line in defaults:
            with self.subTest(line=line):
                self.assertIn("not_a_secret", line)


class TheProvisioningPathIsTheOneCiRuns(unittest.TestCase):
    """Decision D on #169: the local stack must be the path the deployment
    reuses, so it may not provision its own way."""

    def test_the_stack_provisions_by_calling_the_committed_module(self):
        self.assertIn("evidence_first_rag.db.provision", TEXT)

    def test_the_stack_contains_no_sql_of_its_own(self):
        """A `CREATE`, `GRANT` or `INSERT` here would be the second schema
        path Charter Section 9's Milestone 5 gate forbids -- and it would
        drift from `sql/` silently, because nothing compares them."""
        upper = TEXT.upper()
        for statement in ("CREATE TABLE", "CREATE ROLE", "GRANT ", "INSERT INTO"):
            with self.subTest(statement=statement):
                self.assertNotIn(statement, upper)

    def test_the_database_is_the_pinned_major_version(self):
        """`mvp-v0.1` Section 3.4 pins PostgreSQL 17. A stack on another major
        version would provision and pass while testing a different engine."""
        self.assertIn("image: postgres:17", TEXT)


class TheAdapterCredentialIsOptional(unittest.TestCase):
    """Section 4.7: absent, `/v1/ask` refuses and every other route works."""

    def test_the_stack_starts_with_no_adapter_credential_set(self):
        """`${ANTHROPIC_API_KEY:-}` is the whole obligation in one line: the
        variable is passed through if the person has one, and is empty if they
        do not, rather than being required."""
        self.assertIn("ANTHROPIC_API_KEY: ${ANTHROPIC_API_KEY:-}", TEXT)

    def test_no_key_is_written_into_the_file(self):
        """The credential is read from the environment, never committed."""
        self.assertNotIn("sk-ant", TEXT)
        self.assertNotIn("sk-ant", DOCKERFILE.read_text(encoding="utf-8"))


class TheImageCarriesWhatTheContractNeeds(unittest.TestCase):
    def test_it_installs_the_api_extra_and_not_the_adapter_one(self):
        """The adapter extra in the image would make a model library a
        dependency of a stack that answers four of five routes without one."""
        dockerfile = DOCKERFILE.read_text(encoding="utf-8")
        self.assertIn('".[api]"', dockerfile)
        self.assertNotIn("[adapter]", dockerfile)
        self.assertNotIn("[api,adapter]", dockerfile)

    def test_it_carries_psql_for_the_provisioning_path(self):
        """`db/provision.py` applies the committed SQL with `psql`. Without the
        client the provisioning container fails at the first script, after the
        stack has already started a database."""
        self.assertIn("postgresql-client", DOCKERFILE.read_text(encoding="utf-8"))

    def test_it_copies_the_page_the_surface_serves(self):
        """`api-v0.1` Section 4.6's page is served from `ui/`. An image without
        it starts, answers every `/v1` route, and returns nothing at `/` --
        which is the slice #186 added being absent from the stack that is
        supposed to demonstrate it."""
        self.assertIn("COPY ui ", DOCKERFILE.read_text(encoding="utf-8"))


@unittest.skipUnless(
    importlib.util.find_spec("yaml") is not None, "PyYAML is not installed"
)
class TheServicesStartInTheRightOrder(unittest.TestCase):
    """Structural assertions, which are brittle as text. The identity and
    provisioning rules above are not among them: those run everywhere."""

    @classmethod
    def setUpClass(cls):
        import yaml

        cls.document = yaml.safe_load(TEXT)
        cls.services = cls.document["services"]

    def test_the_three_services_and_no_others(self):
        self.assertEqual(set(self.services), {"database", "provisioning", "surface"})

    def test_provisioning_waits_for_a_healthy_database(self):
        """Not for a started one: `postgres` accepts connections only after its
        own initialisation, and the first SQL script would fail against a
        container that exists but is not listening."""
        self.assertEqual(
            self.services["provisioning"]["depends_on"]["database"]["condition"],
            "service_healthy",
        )

    def test_the_surface_waits_for_provisioning_to_have_succeeded(self):
        """`service_completed_successfully`, not `service_started`: a surface
        over a half-loaded database answers `not_found` for data that is on its
        way in, which is a true answer to the wrong question."""
        self.assertEqual(
            self.services["surface"]["depends_on"]["provisioning"]["condition"],
            "service_completed_successfully",
        )

    def test_the_surface_environment_carries_no_provisioning_credential(self):
        """The same prohibition as the count above, read off the parsed
        document. Both, because the count is robust to reorganisation and this
        is robust to a name appearing in a comment."""
        environment = self.services["surface"]["environment"]
        for variable in PROVISIONING_ONLY:
            with self.subTest(variable=variable):
                self.assertNotIn(variable, environment)

    def test_both_ports_are_bound_to_loopback(self):
        """A database with a documented password, or a surface over it, on
        `0.0.0.0` is on whatever network the machine is on."""
        for service in ("database", "surface"):
            with self.subTest(service=service):
                for mapping in self.services[service]["ports"]:
                    self.assertTrue(
                        str(mapping).startswith("127.0.0.1:"),
                        f"{service} publishes {mapping} beyond loopback",
                    )

    def test_the_surface_runs_the_factory_entry_point(self):
        """`--factory`, because `serve.build` reads the environment when it is
        called. Importing a module-level app would read it at import time."""
        command = self.services["surface"]["command"]
        self.assertIn("--factory", command)
        self.assertIn("evidence_first_rag.api.serve:build", command)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
