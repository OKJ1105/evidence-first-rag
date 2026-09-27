"""`deploy-v0.1` `DP-001`, `DP-013` and `DP-015`, read off the workflow files.

The workflow is text this repository commits, and these three cases are
decided by that text alone, so they run in every job with no Azure. What only a
run can show is the deployed cases', on the owner's first deploy.
"""

import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
DEPLOY = WORKFLOWS / "deploy.yml"
TEXT = DEPLOY.read_text(encoding="utf-8")
# No YAML parser is a dependency of this package, so the file is read by its
# layout: top-level keys at column 0, jobs at two spaces, steps at six.


def top_level(key: str) -> str:
    match = re.search(rf"^{key}:\n(.*?)(?=^\S|\Z)", TEXT, re.MULTILINE | re.DOTALL)
    if match is None:
        raise AssertionError(f"no top-level `{key}` in deploy.yml")
    return match.group(1)


def jobs() -> dict:
    return dict(re.findall(r"^  (\w[\w-]*):\n(.*?)(?=^  \w|\Z)", top_level("jobs") + "\n", re.MULTILINE | re.DOTALL))


def steps(job: str) -> list:
    return re.split(r"^      - ", job, flags=re.MULTILINE)[1:]


def step(name: str) -> str:
    found = [body for body in steps(jobs()["deploy"]) if body.startswith(f"name: {name}\n")]
    if len(found) != 1:
        raise AssertionError(f"expected one step named {name!r}")
    return found[0]

GUARD = "github.actor == 'OKJ1105' && github.triggering_actor == 'OKJ1105' && github.ref == 'refs/heads/main'"
DEPLOY_SECRETS = {"postgres-admin-password", "mvp-provisioning-password", "mvp-runtime-password"}


def logs_in(job: str) -> bool:
    return "azure/login" in job or re.search(r"(^|\s)az ", job) is not None


def code(text: str) -> str:
    """The text with YAML and shell `#` comments removed."""
    return "\n".join(re.split(r"(?:^|(?<=\s))#(?![{!])", line, maxsplit=1)[0] for line in text.splitlines())


class TheStart(unittest.TestCase):
    """DP-013: only the owner starts a deploy, and only this file can."""

    def test_the_only_trigger_is_workflow_dispatch(self):
        self.assertEqual(re.findall(r"^  (\w+):", top_level("on"), re.MULTILINE), ["workflow_dispatch"])
        self.assertEqual(top_level("on").strip(), "workflow_dispatch:")

    def test_every_job_that_logs_in_names_production_and_opens_with_the_guard(self):
        azure = [job for job in jobs().values() if logs_in(job)]
        self.assertTrue(azure)
        for job in azure:
            self.assertRegex(job, r"(?m)^    environment: production$")
            condition = re.search(r"(?m)^    if: (.*)$", job)
            self.assertIsNotNone(condition)
            self.assertTrue(condition.group(1).startswith(GUARD), condition.group(1))
            # The guard is the job's first condition: nothing runs before it.
            self.assertLess(job.index("    if: "), job.index("    steps:"))

    def test_no_other_workflow_logs_in_to_azure(self):
        """DP-013 covers every file: a job anywhere that logs in must carry the
        guard, and the only such job is this file's (#235 N3)."""
        for path in WORKFLOWS.glob("*.y*ml"):
            if path == DEPLOY:
                continue
            with self.subTest(path=path.name):
                self.assertFalse(logs_in(code(path.read_text(encoding="utf-8"))))

    def test_a_stale_runner_rule_is_removed_before_a_new_one_opens(self):
        opened = step("Open the database firewall to this runner")
        self.assertLess(opened.index("firewall-rule delete"), opened.index("firewall-rule create"))

    def test_no_other_workflow_names_the_production_environment(self):
        for path in WORKFLOWS.glob("*.y*ml"):
            if path == DEPLOY:
                continue
            with self.subTest(path=path.name):
                self.assertNotRegex(code(path.read_text(encoding="utf-8")), r"\bproduction\b")


class TheProvisioning(unittest.TestCase):
    """DP-001: the deployed database is built by the module CI runs."""

    def test_provisioning_is_the_committed_module_and_nothing_else(self):
        body = code(TEXT)
        self.assertEqual(re.findall(r"python -m evidence_first_rag\.db\.provision[^\n]*", body),
                         ["python -m evidence_first_rag.db.provision --recreate | tee provision.txt"])
        self.assertNotRegex(body, r"\bpsql\b")
        self.assertNotRegex(body, r"--(sql|fixtures)\b")

    def test_the_firewall_closes_whatever_happened(self):
        close = step("Close the database firewall")
        self.assertRegex(close, r"(?m)^        if: always\(\)")
        self.assertIn("firewall-rule delete", close)


class TheSecrets(unittest.TestCase):
    """DP-015: three secrets, written once, never printed."""

    def test_only_the_three_database_secrets_are_named(self):
        body = code(TEXT)
        self.assertNotIn("anthropic", body.lower())
        vault = "\n".join(line for line in body.splitlines() if "keyvault secret" in line)
        named = set(re.findall(r"--name \"?([a-z][a-z0-9-]+)\"?", vault)) | set(re.findall(r"read_secret ([a-z][a-z0-9-]+)", body))
        loop = re.search(r"for name in ([^;]+);", body)
        self.assertIsNotNone(loop)
        named |= set(loop.group(1).split())
        named.discard("name")
        self.assertEqual(named, DEPLOY_SECRETS)

    def test_no_secret_is_reached_without_naming_it(self):
        """A vault-wide role would let a listing read every secret, the
        Anthropic key among them, without naming one (#233 B2)."""
        body = code(TEXT)
        self.assertNotRegex(body, r"keyvault secret (list|backup|download|delete|purge|recover)")
        for line in body.splitlines():
            if "keyvault secret" in line:
                with self.subTest(line=line.strip()):
                    self.assertRegex(line, r"--name \"?(\$name|postgres-admin-password|mvp-provisioning-password|mvp-runtime-password|\$1)\"?( |$)")
        # `read_secret` passes its argument through, so every call names one.
        for name in re.findall(r"read_secret ([^\s)\"]+)", body):
            with self.subTest(name=name):
                self.assertIn(name, DEPLOY_SECRETS)

    def test_a_secret_is_written_only_when_it_does_not_exist(self):
        create = step("Create the database passwords that do not exist yet")
        self.assertLess(create.index("secret show"), create.index("continue"))
        self.assertLess(create.index("continue"), create.index("secret set"))
        self.assertIn("--file", create)
        # "Found nothing" is the not-found answer, not any failure (#235 B1):
        # every other failure exits before the write.
        self.assertIn('2>"$error" || status=$?', create)
        self.assertIn('if [ "$status" -eq 0 ]; then', create)
        self.assertLess(create.index("if ! grep -q 'SecretNotFound'"), create.index("exit 1"))
        self.assertLess(create.index("exit 1"), create.index("secret set"))
        self.assertNotIn("2>/dev/null", create)
        self.assertNotRegex(create, r"secret set[^\n]*--value")

    def test_every_secret_read_into_the_shell_is_masked(self):
        for body in steps(jobs()["deploy"]):
            for variable in re.findall(r"^\s*(\w+)=\"\$\((?:az keyvault secret show|read_secret)", body, re.MULTILINE):
                with self.subTest(step=body.splitlines()[0], variable=variable):
                    self.assertIn(f'echo "::add-mask::${variable}"', body)
        self.assertNotRegex(code(TEXT), r"\${{\s*secrets\.")


if __name__ == "__main__":
    unittest.main()
