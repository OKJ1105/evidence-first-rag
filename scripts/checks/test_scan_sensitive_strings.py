"""Negative tests for scan_sensitive_strings.py.

A scan nobody has seen fail is a scan nobody knows works, and a secret scanner
is the worst place to learn that late: it is quiet in exactly the same way
whether it is working or looking for the wrong thing. Each test here builds a
tree, breaks exactly one rule in it, and asserts that the scan fails and says
which rule. The exemptions are probed from both sides — the exempt form passes
and the same string without its exemption fails — so an exemption that has
quietly swallowed a rule is visible.

The probe strings are assembled from pieces on purpose. This file is inside
the tree the scan reads, so a probe written out whole would make the scan fail
on the repository itself. `TestTheRepositoryTree` is what keeps that honest:
it runs the scan over the real repository and asserts it passes.

Run directly (`python3 scripts/checks/test_scan_sensitive_strings.py`) or
through `python3 -m unittest`. Standard library only, like everything else in
scripts/checks.
"""

import contextlib
import importlib.util
import io
import json
import os
import pathlib
import shutil
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
REPOSITORY = HERE.parent.parent

CHECK = "scripts/checks/scan_sensitive_strings.py"
CHECK_TESTS = "scripts/checks/test_scan_sensitive_strings.py"


def load_module():
    """Import scan_sensitive_strings.py by path, so this file does not depend
    on the checks directory being an importable package."""
    spec = importlib.util.spec_from_file_location(
        "scan_sensitive_strings", HERE / "scan_sensitive_strings.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ScanCheck(unittest.TestCase):
    """Runs the scan over a tree this test builds."""

    def setUp(self):
        self.module = load_module()
        self.directory = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.directory, ignore_errors=True)
        self.module.ROOT = self.directory
        self.write("README.md", "# Sample\n\nNothing sensitive here.\n")

    def write(self, name, text):
        path = self.directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def run_check(self):
        """Return (exit code, printed output)."""
        captured = io.StringIO()
        with contextlib.redirect_stdout(captured):
            code = self.module.main()
        return code, captured.getvalue()

    def assert_fails(self, fragment):
        code, output = self.run_check()
        self.assertEqual(code, 1, f"expected failure, got pass:\n{output}")
        self.assertIn(fragment, output)
        return output

    def assert_passes(self):
        code, output = self.run_check()
        self.assertEqual(code, 0, f"expected pass, got failure:\n{output}")
        return output


class TestTheEmptyTree(ScanCheck):
    def test_a_tree_with_nothing_sensitive_passes(self):
        self.assertIn("Sensitive strings: PASS", self.assert_passes())


class TestPrivateKeys(ScanCheck):
    def test_a_private_key_block_fails(self):
        self.write("keys.txt", "-----BEGIN" + " RSA PRIVATE KEY-----\nMIIE\n")
        self.assert_fails("private-key")

    def test_an_unlabelled_private_key_block_fails(self):
        self.write("keys.txt", "-----BEGIN" + " PRIVATE KEY-----\n")
        self.assert_fails("private-key")

    def test_a_public_key_block_passes(self):
        self.write("keys.txt", "-----BEGIN" + " PUBLIC KEY-----\n")
        self.assert_passes()


class TestIssuedCredentials(ScanCheck):
    def test_an_aws_access_key_id_fails(self):
        self.write("notes.md", "id " + "AKIA" + "IOSFODNN7EXAMPLE" + "\n")
        self.assert_fails("issued-credential")

    def test_a_github_token_fails(self):
        self.write("notes.md", "t " + "ghp_" + "A" * 36 + "\n")
        self.assert_fails("issued-credential")

    def test_an_anthropic_key_fails(self):
        self.write("notes.md", "k " + "sk-ant-" + "api03-" + "b" * 40 + "\n")
        self.assert_fails("issued-credential")

    def test_a_google_key_fails(self):
        self.write("notes.md", "k " + "AIza" + "c" * 35 + "\n")
        self.assert_fails("issued-credential")

    def test_a_slack_token_fails(self):
        self.write("notes.md", "t " + "xoxb-" + "1234567890-abcdef" + "\n")
        self.assert_fails("issued-credential")

    def test_a_prose_word_that_starts_with_a_prefix_passes(self):
        # The prefixes are only useful if they do not fire on ordinary text.
        self.write("notes.md", "The AKIAS in the diagram are not keys.\n")
        self.assert_passes()


class TestAssignedSecrets(ScanCheck):
    def test_a_quoted_literal_in_yaml_fails(self):
        self.write("config.yml", 'api_key: "' + "k7Qm2Xb9Zr4T" + '"\n')
        self.assert_fails("assigned-secret")

    def test_a_bare_literal_in_yaml_fails(self):
        self.write("config.yml", "database_password: " + "k7Qm2Xb9Zr4T" + "\n")
        self.assert_fails("assigned-secret")

    def test_a_quoted_literal_in_python_fails(self):
        # The expression-source exemption covers bare values only. A literal
        # still has to be quoted to be one, and a quoted one is caught.
        self.write("app.py", 'PASSWORD = "' + "k7Qm2Xb9Zr4T" + '"\n')
        self.assert_fails("assigned-secret")

    def test_a_bare_name_in_python_passes(self):
        self.write("app.py", "connect(password=provisioning_password)\n")
        self.assert_passes()

    def test_the_same_bare_name_in_yaml_fails(self):
        # The other side of the exemption above: outside a language where a
        # bare value is an expression, the same text is read as a value.
        self.write("config.yml", "password: provisioning_password\n")
        self.assert_fails("assigned-secret")

    def test_a_value_one_character_under_the_threshold_passes(self):
        value = "a" * (self.module.MINIMUM_SECRET_LENGTH - 1)
        self.write("config.yml", 'token: "' + value + '"\n')
        self.assert_passes()

    def test_a_value_at_the_threshold_fails(self):
        value = "a" * self.module.MINIMUM_SECRET_LENGTH
        self.write("config.yml", 'token: "' + value + '"\n')
        self.assert_fails("assigned-secret")

    def test_a_github_actions_expression_passes(self):
        self.write("w.yml", "  API_TOKEN: ${{ " + "secrets.SOME_NAME }}\n")
        self.assert_passes()

    def test_a_shell_expansion_passes(self):
        self.write("run.sh", "export DB_PASSWORD=$" + "DEPLOY_PASSWORD\n")
        self.assert_passes()

    def test_a_psql_interpolation_passes(self):
        self.write("roles.sql", "ALTER ROLE r PASSWORD :" + "'runtime_password';\n")
        self.assert_passes()

    def test_the_same_shape_outside_sql_is_read_as_a_value_and_fails(self):
        # The exemption's real other side, and the reason it is restricted to
        # .sql: psql interpolation exists in psql. The identical characters in
        # a configuration file are an assignment, and its value is checked.
        self.write("config.yml", "password:'" + "k7Qm2Xb9Zr4T" + "'\n")
        self.assert_fails("assigned-secret")

    def test_a_space_before_the_quote_is_not_interpolation_and_fails(self):
        # `:'name'` is one token. A space between them is an ordinary
        # assignment of a quoted literal, in a .sql file as anywhere else.
        self.write("roles.sql", "ALTER ROLE r PASSWORD : '" + "k7Qm2Xb9Zr4T" + "';\n")
        self.assert_fails("assigned-secret")

    def test_an_equals_sign_in_a_sql_file_fails(self):
        # .sql is an expression source, so a bare value there is a name. A
        # quoted one is still a literal and is still caught.
        self.write("roles.sql", "ALTER ROLE r PASSWORD = '" + "k7Qm2Xb9Zr4T" + "';\n")
        self.assert_fails("assigned-secret")

    def test_the_sql_interpolation_exemption_covers_whatever_it_quotes(self):
        # Recorded rather than claimed away: inside a .sql file the exemption
        # applies to the quoted text whatever it looks like, because psql's
        # grammar admits no literal in that position for it to be told apart
        # from. This asserts the residual so a later reader finds it stated.
        self.write("roles.sql", "ALTER ROLE r PASSWORD :" + "'k7Qm2Xb9Zr4T';\n")
        self.assert_passes()

    def test_a_placeholder_value_passes(self):
        self.write("w.yml", "  POSTGRES_PASSWORD: ci_superuser_" + "not_a_secret\n")
        self.assert_passes()

    def test_the_same_value_without_its_placeholder_marker_fails(self):
        # The placeholder convention is an exemption, so it is probed from
        # both sides: without the marker the identical line is a finding.
        self.write("w.yml", "  POSTGRES_PASSWORD: ci_superuser_" + "kQ7mXb9Zr\n")
        self.assert_fails("assigned-secret")

    def test_a_name_that_is_not_about_secrets_passes(self):
        self.write("config.yml", "project_code: " + "SAMPLE_PROJECT_ALPHA" + "\n")
        self.assert_passes()


class TestCredentialsInUrls(ScanCheck):
    def test_a_password_in_a_url_fails(self):
        self.write("notes.md", "postgres://svc:" + "k7Qm2Xb9Zr4T" + "@db.example.com/x\n")
        self.assert_fails("url-credentials")

    def test_a_url_without_credentials_passes(self):
        self.write("notes.md", "https://" + "db.example.com/x\n")
        self.assert_passes()


class TestInternalHosts(ScanCheck):
    def test_an_internal_tld_fails(self):
        self.write("notes.md", "https://" + "build.internal/status\n")
        self.assert_fails("internal-host")

    def test_a_private_address_fails(self):
        self.write("notes.md", "http://" + "10.4.2.9:8080/status\n")
        self.assert_fails("internal-host")

    def test_another_private_range_fails(self):
        self.write("notes.md", "http://" + "192.168.1.10/status\n")
        self.assert_fails("internal-host")

    def test_a_public_host_passes(self):
        self.write("notes.md", "https://" + "github.com/OKJ1105/evidence-first-rag\n")
        self.assert_passes()

    def test_loopback_passes(self):
        # The database tests and the CI service container both talk to
        # localhost; a rule that fired on it would be turned off within a day.
        self.write("notes.md", "postgres://" + "localhost:5432/mvp\n")
        self.assert_passes()


class TestLocalMachinePaths(ScanCheck):
    def test_a_macos_home_directory_fails(self):
        self.write("notes.md", "see /Users/" + "jdoe/checkouts/mvp\n")
        self.assert_fails("local-machine-path")

    def test_a_linux_home_directory_fails(self):
        self.write("notes.md", "see /home/" + "jdoe/checkouts/mvp\n")
        self.assert_fails("local-machine-path")

    def test_a_windows_home_directory_fails(self):
        self.write("notes.md", "see C:\\Users\\" + "jdoe\\mvp\n")
        self.assert_fails("local-machine-path")

    def test_the_runner_home_directory_passes(self):
        self.write("notes.md", "the checkout is at /home/" + "runner/work/mvp\n")
        self.assert_passes()

    def test_a_documentation_stand_in_passes(self):
        self.write("notes.md", "clone it under /home/" + "user/src\n")
        self.assert_passes()


class TestPersonalEmail(ScanCheck):
    def test_an_address_fails(self):
        self.write("notes.md", "contact " + "a.person" + "@" + "somecompany.com\n")
        self.assert_fails("personal-email")

    def test_a_github_no_reply_address_passes(self):
        self.write("notes.md", "206027169+OKJ1105" + "@" + "users.noreply.github.com\n")
        self.assert_passes()

    def test_a_reserved_documentation_domain_passes(self):
        self.write("notes.md", "owner" + "@" + "example.com\n")
        self.assert_passes()

    def test_a_package_specifier_passes(self):
        # The regression this rule was corrected for: an npm specifier carries
        # a version after an at-sign and is not an address.
        self.write("w.yml", "run: npm install -g @anthropic-ai/claude-code@2.1.252\n")
        self.assert_passes()


class TestWhatIsReported(ScanCheck):
    def test_a_credential_is_not_printed_in_full(self):
        value = "k7Qm2Xb9" + "Zr4TdW1p"
        self.write("config.yml", 'api_key: "' + value + '"\n')
        output = self.assert_fails("assigned-secret")
        self.assertNotIn(value, output)
        self.assertIn("(16 characters)", output)

    def test_an_address_is_not_printed_in_full_either(self):
        # A finding never reprints what it found, whichever rule produced it:
        # the address a personal-email hit names is the thing not to repeat
        # into a log, exactly as a credential is.
        local, domain = "a.person", "somecompany.com"
        self.write("notes.md", "contact " + local + "@" + domain + "\n")
        output = self.assert_fails("personal-email")
        self.assertNotIn(domain, output)
        self.assertIn("(24 characters)", output)

    def test_a_host_is_not_printed_in_full_either(self):
        self.write("notes.md", "https://" + "build.internal/status\n")
        output = self.assert_fails("internal-host")
        self.assertNotIn("build.internal", output)

    def test_the_file_and_line_are_never_masked(self):
        # What makes a masked finding actionable: the reader opens the line.
        self.write("deep/notes.md", "\n" + "see /Users/" + "jdoe/checkouts\n")
        self.assertIn("deep/notes.md:2:", self.assert_fails("local-machine-path"))

    def test_the_finding_names_the_file_the_line_and_the_clause(self):
        self.write("deep/config.yml", "\n\n" + 'token: "' + "k7Qm2Xb9Zr4T" + '"\n')
        output = self.assert_fails("assigned-secret")
        self.assertIn("deep/config.yml:3:", output)
        self.assertIn("AGENTS.md: never add credentials or secrets", output)

    def test_the_mask_keeps_a_short_value_unreadable(self):
        self.assertEqual(self.module.mask("abc"), "***")


class TestWhatIsScanned(ScanCheck):
    def test_a_nested_file_is_scanned(self):
        self.write("a/b/c/notes.md", "id " + "AKIA" + "IOSFODNN7EXAMPLE" + "\n")
        self.assert_fails("issued-credential")

    def test_a_file_with_no_extension_is_scanned(self):
        self.write("Dockerfile", "ENV API_TOKEN=" + "k7Qm2Xb9Zr4T" + "\n")
        self.assert_fails("assigned-secret")

    def test_a_binary_file_is_scanned_rather_than_skipped(self):
        # Decoding with replacement rather than skipping is deliberate: a
        # credential pasted into a binary file is still ASCII.
        path = self.directory / "blob.bin"
        path.write_bytes(b"\x00\x01\xff " + b"AKIA" + b"IOSFODNN7EXAMPLE" + b"\x00")
        self.assert_fails("issued-credential")

    def test_a_symlink_target_is_scanned(self):
        # A link is how a local machine path arrives in the tree without any
        # file containing one, so the target as written is read.
        os.symlink("/Users/" + "jdoe/checkouts/mvp", self.directory / "checkout")
        self.assert_fails("local-machine-path")

    def test_a_symlink_is_not_followed_out_of_the_tree(self):
        # The target is read as text, not opened. Following it would read
        # outside the repository, which is not what a repository scan reports.
        outside = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, outside, ignore_errors=True)
        (outside / "keys.txt").write_text(
            "id " + "AKIA" + "IOSFODNN7EXAMPLE" + "\n", encoding="utf-8"
        )
        os.symlink(outside / "keys.txt", self.directory / "keys.txt")
        self.assert_passes()

    def test_a_broken_symlink_does_not_crash_the_scan(self):
        os.symlink(self.directory / "nowhere", self.directory / "dangling")
        self.assert_passes()

    def test_a_skipped_directory_is_not_scanned(self):
        # Asserted so the exclusion stays deliberate and visible rather than
        # being discovered later as a hole.
        self.write("node_modules/x/index.js", 'k = "' + "AKIA" + "IOSFODNN7EXAMPLE" + '"\n')
        self.assert_passes()

    def test_the_scanned_file_count_is_reported(self):
        self.write("one.md", "nothing\n")
        self.write("two.md", "nothing\n")
        self.assertIn("(3 files scanned)", self.assert_passes())


class TestTheRepositoryTree(unittest.TestCase):
    """The positive case. Also what keeps the probes above from being written
    out whole: a probe that matched would fail here."""

    def test_the_repository_tree_passes(self):
        module = load_module()
        module.ROOT = REPOSITORY
        captured = io.StringIO()
        with contextlib.redirect_stdout(captured):
            code = module.main()
        output = captured.getvalue()
        self.assertEqual(code, 0, output)
        self.assertIn("Sensitive strings: PASS", output)


class TestTheCheckIsRegistered(unittest.TestCase):
    """A check that runs nowhere is not a check. Both registrations are
    additive entries permitted by #17 rule 2's `.github/` carve-out."""

    def test_the_agent_loop_runs_both_commands(self):
        manifest = json.loads(
            (REPOSITORY / ".github/agent-checks.json").read_text(encoding="utf-8")
        )
        commands = [" ".join(check["command"]) for check in manifest["checks"]]
        for script in (CHECK, CHECK_TESTS):
            with self.subTest(script=script):
                self.assertTrue(
                    any(script in command for command in commands),
                    f"{script} is not in .github/agent-checks.json",
                )

    def test_ci_runs_both_commands(self):
        workflow = (
            REPOSITORY / ".github/workflows/repository-checks.yml"
        ).read_text(encoding="utf-8")
        for script in (CHECK, CHECK_TESTS):
            with self.subTest(script=script):
                self.assertIn(script, workflow)


if __name__ == "__main__":
    unittest.main(verbosity=2)
