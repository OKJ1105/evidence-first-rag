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

    def test_the_close_step_does_not_depend_on_the_create_succeeding(self):
        opened = step("Open the database firewall to this runner")
        self.assertLess(opened.index('echo "rule='), opened.index("firewall-rule create"))

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
        # This commit's provisioning, and the rollback's, which runs the same
        # module from the last passing commit's own checkout.
        # This commit's deployed provisioning, the local one DP-006 compares
        # it with, and the rollback's from the last passing commit.
        self.assertEqual(re.findall(r"python -m evidence_first_rag\.db\.provision[^\n]*", body),
                         ["python -m evidence_first_rag.db.provision --recreate | tee provision.txt",
                          "python -m evidence_first_rag.db.provision --recreate > /dev/null &&",
                          "python -m evidence_first_rag.db.provision --recreate)"])
        self.assertIn("(cd previous && PYTHONPATH=src python -m evidence_first_rag.db.provision --recreate)", body)
        self.assertNotRegex(body, r"\bpsql\b")
        self.assertNotRegex(body, r"--(sql|fixtures)\b")

    def test_the_firewall_closes_whatever_happened(self):
        close = step("Close the database firewall")
        self.assertRegex(close, r"(?m)^        if: always\(\)")
        self.assertIn("firewall-rule delete", close)


class TheDeployedChecks(unittest.TestCase):
    """Section 4.8: the checks run inside the window, and a failure rolls back."""

    def test_the_checks_run_before_the_window_closes(self):
        names = [body.splitlines()[0] for body in steps(jobs()["deploy"])]
        order = [names.index(f"name: {name}") for name in (
            "Provision the database from this commit",
            "Run the deployed checks",
            "Roll back to the last passing commit",
            "Close the database firewall",
        )]
        self.assertEqual(order, sorted(order))

    def test_the_checks_wait_for_surface_to_serve_first(self):
        checks = step("Run the deployed checks")
        self.assertLess(checks.index("/v1/health"), checks.index("conformance.runner"))
        self.assertIn("for attempt in $(seq 1 30)", checks)

    def test_a_vault_read_failure_stops_before_any_check(self):
        checks = step("Run the deployed checks")
        for name in ("MVP_PROVISIONING_PASSWORD", "MVP_RUNTIME_PASSWORD"):
            self.assertRegex(checks, rf'{name}="\$\(read_secret [a-z-]+\)" \|\| \{{ echo "Key Vault read failed"; exit 2; \}}')
        self.assertLess(checks.index("Key Vault returned an empty value"), checks.index("conformance.runner"))

    def test_every_check_runs_and_any_failure_fails_the_step(self):
        checks = step("Run the deployed checks")
        for command in (
            "python -m evidence_first_rag.conformance.runner",
            "python -m evidence_first_rag.deploy.deployed writes",
            "--start-directory tests_stack",
            "python -m evidence_first_rag.deploy.http_checks",
            "python -m evidence_first_rag.deploy.azure_checks",
        ):
            self.assertIn(command, checks)
        # No `-e`: one failed check does not stop the next from running.
        self.assertIn("set -uo pipefail", checks)
        self.assertIn('if [ -n "$failed" ]; then', checks)
        self.assertIn("exit 1", checks)

    def test_the_local_side_is_provisioned_into_the_job_scoped_database(self):
        """DP-006: the local provisioning never reaches the deployed server."""
        checks = step("Run the deployed checks")
        local = checks[checks.index("export PGHOST=localhost"):checks.index("digests compare")]
        self.assertIn("PGSSLMODE=disable", local)
        self.assertIn("db.provision --recreate", local)
        self.assertNotIn("steps.infra.outputs.serverHost", local)
        self.assertRegex(jobs()["deploy"], r"(?m)^    services:\n      local:\n        image: postgres:17$")

    def test_the_comparison_fails_the_step(self):
        checks = step("Run the deployed checks")
        self.assertIn('digests compare', checks)
        self.assertIn('|| failed="$failed DP-006/DP-007"', checks)

    def test_the_rollback_compares_the_restored_state(self):
        rollback = step("Roll back to the last passing commit")
        self.assertIn('expected-digest --commit "$target"', rollback)
        self.assertLess(rollback.index("restored-conformance.json"), rollback.index("digests restored"))

    def test_the_rollback_runs_only_on_failure_and_restores_both_halves(self):
        rollback = step("Roll back to the last passing commit")
        # Any failure after the template repointed the apps (#237 B1).
        self.assertRegex(rollback, r"(?m)^        if: failure\(\) && steps\.infra\.outcome == 'success'$")
        # The image half comes before, and does not depend on, the database half.
        self.assertLess(rollback.index("--linux-fx-version"), rollback.index('if [ "${{ steps.firewall.outputs.rule }}" = "" ]'))
        self.assertLess(rollback.index('if [ "${{ steps.firewall.outputs.rule }}" = "" ]'), rollback.index("db.provision"))
        self.assertIn('deploy.deployed last-passing --excluding "$COMMIT"', rollback)
        # Every exit of the step records what happened (#237 B3).
        self.assertEqual(rollback.count('echo "result='), 4)
        # "rolled back" is written only after DP-011 has answered (#243 B1).
        self.assertLess(rollback.index("digests restored"), rollback.index('echo "result=rolled back" >> "$GITHUB_OUTPUT"\n          else'))
        self.assertIn('echo "result=nothing to roll back to"', rollback)
        self.assertIn('--linux-fx-version "DOCKER|$image"', rollback)
        self.assertIn("evidence-first-rag:$target", rollback)


class TheSecretScan(unittest.TestCase):
    """`DP-003`'s image, workflow and artifact half runs in the checks step,
    after every artifact that step writes; a second run after the deploy record
    covers what is written later (#254 B3). Both records are uploaded."""

    def test_the_scan_runs_last_and_fails_the_step(self):
        checks = step("Run the deployed checks")
        scan = checks.index("evidence_first_rag.deploy.secrets_scan")
        self.assertGreater(scan, checks.index("tee compare.json"))
        self.assertIn('failed="$failed DP-003"', checks[scan:])
        for artifact in ("conformance.json", "http-checks.json", "azure-checks.json", "compare.json"):
            self.assertIn(artifact, checks[scan:checks.index("--out secret-scan.json")])

    def test_the_files_written_after_the_checks_are_scanned_before_upload(self):
        """#254 B3: the deploy record embeds provision.txt and is committed."""
        scan = step("Scan the deploy record")
        for artifact in ("deploy-record.json", "provision.txt", "restored-compare.json", "expected-digest.json"):
            self.assertIn(artifact, scan)
        self.assertIn("--out secret-scan-record.json", scan)
        names = [body.split("\n", 1)[0] for body in steps(jobs()["deploy"])]
        order = [names.index(f"name: {name}") for name in ("Write the deploy record", "Scan the deploy record", "Upload the deploy record")]
        self.assertEqual(order, sorted(order))
        self.assertIn("secret-scan-record.json", step("Upload the deploy record"))

    def test_the_scan_record_is_uploaded(self):
        self.assertIn("secret-scan.json", step("Upload the deploy record"))


class TheRelayCeiling(unittest.TestCase):
    """`DP-016`, `deploy-v0.1` Section 4.6: the deploy passes the ceiling `relay-v0.1`
    Section 8.3 registers, so the relay never starts with none (and then
    refuses every request) or with another number."""

    def test_the_workflow_passes_the_registered_ceiling(self):
        contract = (ROOT / "docs" / "contracts" / "relay-v0.1.md").read_text(encoding="utf-8")
        section = contract[contract.index("### 8.3"):contract.index("## 9.")]
        registered = re.search(r"per UTC day, registered before the first deployed run[^*]*\*\*(\d+)\*\*", section)
        self.assertIsNotNone(registered, "relay-v0.1 Section 8.3: no bold ceiling after 'per UTC day, registered before the first deployed run' -- update this pattern if the sentence was reworded")
        infra = step("Apply the provisioning definitions")
        self.assertIn(f'"relayDailyCeiling": {{"value": "{registered.group(1)}"}}', infra)
        # `DP-016`'s second half: the deployment contract names the same number.
        deploy = (ROOT / "docs" / "contracts" / "deploy-v0.1.md").read_text(encoding="utf-8")
        self.assertIn(f"| `EFR_RELAY_DAILY_CEILING` | — | `{registered.group(1)}`,", deploy)


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
