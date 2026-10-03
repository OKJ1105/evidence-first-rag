"""`deploy-v0.1` `DP-001`, `DP-013` and `DP-015`, read off the workflow files.

The workflow is text this repository commits, and these three cases are
decided by that text alone, so they run in every job with no Azure. What only a
run can show is the deployed cases', on the owner's first deploy.
"""

import pathlib
import re
import subprocess
import tempfile
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
    """DP-013: a deploy starts only by hand, from `main`, through the owner's
    account (the owner or the writer session, ADR-0007), and only this file
    can start one."""

    def test_the_only_trigger_is_workflow_dispatch(self):
        self.assertEqual(re.findall(r"^  (\w+):", top_level("on"), re.MULTILINE), ["workflow_dispatch"])
        # Its inputs are the three #265 registers, and nothing else.
        self.assertEqual(
            re.findall(r"^      (\w+):", top_level("on"), re.MULTILINE), ["mode", "cases", "create_missing_secrets"]
        )

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

    def test_every_firewall_rule_command_names_the_server_by_server_name(self):
        """Azure CLI's `flexible-server firewall-rule` takes the server as
        `--server-name` and the rule as `--name`; `--rule-name` is not an
        argument and fails the command (run 36660167510)."""
        commands = re.findall(r"az postgres flexible-server firewall-rule (\w+)(.*?)--output", code(TEXT), re.S)
        self.assertEqual(sorted(verb for verb, _ in commands), ["create", "delete", "delete", "list"])
        for verb, arguments in commands:
            with self.subTest(verb=verb):
                self.assertIn('--server-name "${{ steps.infra.outputs.serverName }}"', arguments)
                self.assertNotIn("--rule-name", arguments)
                if verb != "list":
                    self.assertRegex(arguments, r'--name "(\$stale|deploy-runner-\$\{\{ github\.run_id \}\}|\$\{\{ steps\.firewall\.outputs\.rule \}\})"')

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
        self.assertRegex(rollback, r"(?m)^        if: failure\(\) && steps\.infra\.outcome == 'success' && env\.MODE == 'deploy'$")
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


class TheChecksMode(unittest.TestCase):
    """#265, `DP-017`: `mode: checks` changes no deployed resource, and the
    fast groups run before the slow ones, which a fast failure skips."""

    MUTATING = (
        "Create the database passwords that do not exist yet",
        "Build and push the image",
        "Restart both apps on the pushed image",
        "Provision the database from this commit",
    )

    def test_every_step_that_changes_a_resource_is_deploy_only(self):
        for name in self.MUTATING:
            with self.subTest(step=name):
                self.assertRegex(step(name), r"(?m)^        if: env\.MODE == 'deploy'$")
        self.assertIn("env.MODE == 'deploy'", step("Roll back to the last passing commit"))

    def test_a_checks_run_applies_no_template(self):
        infra = step("Apply the provisioning definitions")
        branch = infra[infra.index('if [ "$MODE" = "checks" ]'):]
        self.assertLess(branch.index("exit 0"), branch.index("az deployment group create"))
        self.assertNotIn("az deployment group create", branch[:branch.index("exit 0")])
        self.assertIn('echo "DEPLOYED_COMMIT=$deployed" >> "$GITHUB_ENV"', branch)
        self.assertIn('COMMIT="${DEPLOYED_COMMIT:-$COMMIT}"', step("Run the deployed checks"))

    def test_a_checks_run_pulls_the_deployed_image_for_the_scan(self):
        """#266 B1: DP-003's image half reads the local store, which only the
        deploy-mode build fills, so a checks run pulls the running image."""
        infra = step("Apply the provisioning definitions")
        branch = infra[infra.index('if [ "$MODE" = "checks" ]'):infra.index("exit 0")]
        self.assertIn("az acr login --name", branch)
        self.assertIn('/evidence-first-rag:$deployed"', branch[branch.index("docker pull"):])

    def test_only_the_owners_input_creates_a_missing_secret(self):
        """#266 B2: a missing password stops the run unless the owner started
        it with `create_missing_secrets`."""
        create = step("Create the database passwords that do not exist yet")
        self.assertIn("CREATE_MISSING_SECRETS: ${{ inputs.create_missing_secrets }}", create)
        gate = create.index('if [ "$CREATE_MISSING_SECRETS" != "true" ]')
        self.assertLess(gate, create.index("az keyvault secret set"))
        self.assertIn("exit 1", create[gate:create.index("az keyvault secret set")])

    def selection(self, mode, cases):
        """The step's own group selection, run by bash."""
        checks = step("Run the deployed checks")
        body = code(checks[checks.index('check_groups="'):checks.index('skipped=""')])
        body = "\n".join(line.strip() for line in body.splitlines())
        completed = subprocess.run(
            ["bash", "-c", body + '\necho "$selected"'],
            env={"MODE": mode, "CASES": cases, "PATH": "/usr/bin:/bin"},
            capture_output=True, text=True, check=False,
        )
        return completed.returncode, completed.stdout.split()

    def test_a_deploy_runs_every_group_whatever_cases_says(self):
        status, selected = self.selection("deploy", "HTTP")
        self.assertEqual(status, 0)
        self.assertEqual(selected, ["AZURE", "HTTP", "DP-004", "DP-007", "WF/MC", "DP-008", "DP-006"])

    def test_cases_narrow_a_checks_run_and_dp_006_brings_dp_007(self):
        self.assertEqual(self.selection("checks", "HTTP,AZURE")[1], ["HTTP", "AZURE"])
        self.assertEqual(self.selection("checks", "DP-006")[1], ["DP-006", "DP-007"])

    def test_an_unknown_group_stops_the_run(self):
        self.assertEqual(self.selection("checks", "HTTP,DP-999")[0], 2)

    def test_the_fast_groups_run_first_and_a_failure_skips_the_slow(self):
        checks = "\n".join(line.strip() for line in code(step("Run the deployed checks")).splitlines())
        order = [checks.index(f"want {group}") for group in ("AZURE", "HTTP", "DP-004")]
        gate = checks.index('if [ -n "$failed" ]; then\nfor group in DP-007 WF/MC DP-008 DP-006')
        slow = [checks.index(f"want {group};") for group in ("DP-007", "WF/MC", "DP-008", "DP-006")]
        self.assertEqual(order, sorted(order))
        self.assertTrue(max(order) < gate < min(slow))
        # DP-003's scan is not a group: it gates the upload, so it always runs.
        self.assertNotIn("want DP-003", checks)
        self.assertGreater(checks.index("evidence_first_rag.deploy.secrets_scan"), max(slow))

    def test_a_narrowed_run_without_a_database_group_opens_no_firewall(self):
        """#266 N5."""
        opened = step("Open the database firewall to this runner")
        self.assertIn(
            "if: env.MODE == 'deploy' || env.CASES == '' || contains(env.CASES, 'DP-004')"
            " || contains(env.CASES, 'DP-007') || contains(env.CASES, 'DP-006')",
            opened,
        )

    def test_an_early_exit_records_every_group_as_skipped(self):
        """#266 N6: the trap writes the outputs when the step exits before the
        groups run."""
        checks = step("Run the deployed checks")
        body = code(checks[checks.index('check_groups="'):checks.index("# The restarted apps")])
        body = "\n".join(line.strip() for line in body.splitlines())
        with tempfile.NamedTemporaryFile("r", suffix=".out") as output:
            completed = subprocess.run(
                ["bash", "-c", body + "\nexit 1"],
                env={"MODE": "checks", "CASES": "HTTP,DP-004", "GITHUB_OUTPUT": output.name, "PATH": "/usr/bin:/bin"},
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(completed.returncode, 1)
            self.assertEqual(output.read().splitlines(), ["skipped=HTTP DP-004", "ran="])

    def test_the_record_says_what_ran_and_what_was_skipped(self):
        record = step("Write the deploy record")
        for field in ('"mode": os.environ["MODE"]', '"checks_ran"', '"checks_skipped"'):
            self.assertIn(field, record)


class TheSecretScan(unittest.TestCase):
    """`DP-003`'s image, workflow and artifact half runs in the checks step,
    after every artifact that step writes; a second run after the deploy record
    covers what is written later (#254 B3). Both records are uploaded."""

    def test_the_scan_runs_last_and_fails_the_step(self):
        checks = step("Run the deployed checks")
        scan = checks.index("evidence_first_rag.deploy.secrets_scan")
        self.assertGreater(scan, checks.index("tee compare.json"))
        self.assertIn('failed="$failed DP-003"', checks[scan:])
        for artifact in ("conformance.json", "http-checks.json", "azure-checks.json", "compare.json", "log-checks.json"):
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

    def test_a_finding_withholds_the_deploy_record(self):
        """#254 B5: a file that may carry a value is never uploaded."""
        self.assertIn("id: record_scan", step("Scan the deploy record"))
        self.assertIn('echo "secret_scan=fail" >> "$GITHUB_OUTPUT"', step("Run the deployed checks"))
        upload = step("Upload the deploy record")
        self.assertIn("steps.record_scan.outcome != 'failure'", upload)
        self.assertIn("steps.checks.outputs.secret_scan != 'fail'", upload)
        records = step("Upload the scan records")
        self.assertIn("if: always()\n", records)
        self.assertNotIn("deploy-record.json", records)
        for record in ("secret-scan.json", "secret-scan-record.json"):
            self.assertIn(record, records)

    def test_an_unfinished_record_scan_still_publishes_the_cleared_evidence(self):
        """#260 N11: only a finding (exit 1) is published as one; a scan that
        did not finish keeps the record withheld but uploads what the checks
        step's own scan cleared."""
        scan = step("Scan the deploy record")
        self.assertIn('[ "$status" -ne 1 ] || echo "finding=yes" >> "$GITHUB_OUTPUT"', scan)
        self.assertIn('exit "$status"', scan)
        evidence = step("Upload the checks evidence")
        self.assertIn(
            "if: always() && steps.record_scan.outcome == 'failure' && steps.record_scan.outputs.finding != 'yes'"
            " && steps.checks.outputs.secret_scan != 'fail'",
            evidence,
        )
        for withheld in ("deploy-record.json", "provision.txt", "restored-"):
            self.assertNotIn(withheld, evidence)
        checks = step("Run the deployed checks")
        cleared = checks[checks.index("--artifacts", checks.index("secrets_scan")):checks.index("--out secret-scan.json")]
        for name in re.findall(r"[\w-]+\.json", evidence):
            self.assertIn(name, cleared)

    def test_the_checks_scan_seeks_the_admin_password_too(self):
        """#254 N8: all three passwords, the admin one handed to the scan alone."""
        checks = step("Run the deployed checks")
        self.assertIn('admin_password="$(read_secret postgres-admin-password)"', checks)
        self.assertIn('echo "::add-mask::$admin_password"', checks)
        self.assertIn('PGPASSWORD="$admin_password" python -m evidence_first_rag.deploy.secrets_scan', checks)
        self.assertNotIn("export PGPASSWORD=\"$admin_password", checks)


class TheLogCheck(unittest.TestCase):
    """`DP-008` runs in the checks step, after `DP-009` has used the relay's
    window, and its record is uploaded."""

    def test_the_log_check_runs_after_the_http_checks_and_fails_the_step(self):
        checks = step("Run the deployed checks")
        position = checks.index("evidence_first_rag.deploy.log_checks")
        self.assertGreater(position, checks.index("evidence_first_rag.deploy.http_checks"))
        self.assertIn('failed="$failed DP-008"', checks[position:])

    def test_the_log_record_is_uploaded(self):
        self.assertIn("log-checks.json", step("Upload the deploy record"))


class TheInstall(unittest.TestCase):
    def test_the_package_is_installed_editable(self):
        """Run 36662412772: `pip install .` shipped no expected results, so the
        deployed conformance runner found none registered (DP-007)."""
        self.assertIn("run: python -m pip install --quiet -e .", step("Install the package"))


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


class TheCorsOrigin(unittest.TestCase):
    """`DP-018`, `deploy-v0.1` Section 4.6: the origin the contract records is
    the one the template sets on both apps and the one `DP-019` sends."""

    def test_the_workflow_passes_the_recorded_origin(self):
        deploy = (ROOT / "docs" / "contracts" / "deploy-v0.1.md").read_text(encoding="utf-8")
        recorded = re.search(r"\*\*The portfolio site's origin\*\* is \*\*`(https://[^`/]+)`\*\*", deploy)
        self.assertIsNotNone(recorded, "deploy-v0.1 Section 4.6: no bold origin after 'The portfolio site's origin is' -- update this pattern if the sentence was reworded")
        origin = recorded.group(1)
        workflow = (ROOT / ".github" / "workflows" / "deploy.yml").read_text(encoding="utf-8")
        self.assertIn(f"      CORS_ORIGIN: {origin}\n", workflow)
        self.assertIn('"corsOrigin": {"value": os.environ["CORS_ORIGIN"]}', step("Apply the provisioning definitions"))
        self.assertIn('--origin "$CORS_ORIGIN"', step("Run the deployed checks"))


class TheRunnerAddress(unittest.TestCase):
    """`DP-020`: the runner's address is masked before anything could print it,
    and reaches the check through the environment, never a command line."""

    def test_masked_and_passed_in_the_environment(self):
        checks = step("Run the deployed checks")
        fetched = checks.index('RUNNER_ADDRESS="$(curl')
        masked = checks.index('echo "::add-mask::$RUNNER_ADDRESS"')
        run = checks.index("python -m evidence_first_rag.deploy.log_checks")
        self.assertLess(fetched, masked)
        self.assertLess(masked, run)
        self.assertNotIn("--address", checks)
        self.assertNotIn('"$RUNNER_ADDRESS" \\', checks)

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
