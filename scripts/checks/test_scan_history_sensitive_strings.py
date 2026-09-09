"""Negative tests for scan_history_sensitive_strings.py.

Each test builds a real repository, puts exactly one thing in its history, and
asserts what the scan says about it. A history scan is the check most likely to
be quietly wrong — it reads objects nobody looks at, over a history nobody
re-reads — so the cases that matter most are the ones where the tree scan
passes and this one must not.

`TestTheRepositoryHistory` runs it over this repository and asserts a pass,
which is both the positive case and what keeps the probe strings below from
being written out whole: this file is committed, so a whole probe would make
the scan fail on the repository's own history from then on, permanently.

Run directly (`python3 scripts/checks/test_scan_history_sensitive_strings.py`)
or through `python3 -m unittest`. Standard library only, like everything else
in scripts/checks.
"""

import contextlib
import importlib.util
import io
import json
import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
REPOSITORY = HERE.parent.parent

CHECK = "scripts/checks/scan_history_sensitive_strings.py"
CHECK_TESTS = "scripts/checks/test_scan_history_sensitive_strings.py"
TREE_CHECK = "scripts/checks/scan_sensitive_strings.py"

# Assembled from pieces, like every probe in this file. See the module
# docstring: a whole one would enter this repository's history for good.
AWS_KEY = "AKIA" + "IOSFODNN7EXAMPLE"
LITERAL = "k7Qm2Xb9" + "Zr4TdW1p"


def load_module(name):
    spec = importlib.util.spec_from_file_location(name, HERE / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Repository:
    """A throwaway git repository, built commit by commit."""

    def __init__(self, directory):
        self.path = directory
        self.path.mkdir(parents=True, exist_ok=True)
        self.git("init", "--quiet")

    def git(self, *arguments):
        return subprocess.run(
            ("git",) + arguments,
            cwd=self.path,
            capture_output=True,
            check=True,
            text=True,
        ).stdout

    def commit(self, message, **files):
        """Write files (name → text, `None` to delete) and commit."""
        for name, text in files.items():
            path = self.path / name.replace("__", "/")
            path.parent.mkdir(parents=True, exist_ok=True)
            if text is None:
                path.unlink()
            else:
                path.write_text(text, encoding="utf-8")
        self.git("add", "--all")
        self.git(
            "-c",
            "user.email=probe@example.com",
            "-c",
            "user.name=probe",
            "commit",
            "--quiet",
            "--allow-empty",
            "--message",
            message,
        )


class HistoryCheck(unittest.TestCase):
    """Runs the scan over a repository this test built."""

    def setUp(self):
        self.module = load_module("scan_history_sensitive_strings")
        self.directory = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.directory, ignore_errors=True)
        self.repository = Repository(self.directory / "work")
        self.module.WORK_TREE = self.repository.path
        self.repository.commit("first", **{"README.md": "# Sample\n"})

    def run_check(self):
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

    def tree_scan_of(self, directory):
        """What the working-tree scan says about the same repository."""
        tree = load_module("scan_sensitive_strings")
        tree.ROOT = directory
        captured = io.StringIO()
        with contextlib.redirect_stdout(captured):
            code = tree.main()
        return code, captured.getvalue()


class TestTheCleanHistory(HistoryCheck):
    def test_a_history_with_nothing_sensitive_passes(self):
        output = self.assert_passes()
        self.assertIn("Sensitive strings in history: PASS", output)

    def test_the_counts_are_reported(self):
        self.repository.commit("second", **{"notes.md": "nothing\n"})
        self.assertIn("across 2 commits", self.assert_passes())


class TestWhatOnlyTheHistorySees(HistoryCheck):
    """The reason this check exists at all."""

    def test_a_credential_committed_and_then_deleted_is_found(self):
        self.repository.commit("add", **{"keys.txt": "id " + AWS_KEY + "\n"})
        self.repository.commit("remove", **{"keys.txt": None})

        # The working tree is clean, and the tree scan says so. That is not a
        # defect in the tree scan: the file is gone. It is published all the
        # same, and this is the check that sees it.
        code, tree_output = self.tree_scan_of(self.repository.path)
        self.assertEqual(code, 0, tree_output)

        output = self.assert_fails("issued-credential")
        self.assertIn("keys.txt", output)

    def test_a_credential_in_an_earlier_version_of_a_file_that_still_exists(self):
        # The other shape of the same problem: the file survives, the line
        # does not, and only the old blob carries it.
        self.repository.commit("add", **{"config.yml": 'api_key: "' + LITERAL + '"\n'})
        self.repository.commit("scrub", **{"config.yml": "api_key: ${{ secrets.X }}\n"})
        code, _ = self.tree_scan_of(self.repository.path)
        self.assertEqual(code, 0)
        self.assert_fails("assigned-secret")

    def test_a_commit_on_a_branch_not_reachable_from_the_revision_is_not_scanned(self):
        # Declared scope: the history this branch would publish, not whatever
        # refs a checkout happens to carry.
        self.repository.git("checkout", "--quiet", "-b", "elsewhere")
        self.repository.commit("on a branch", **{"keys.txt": "id " + AWS_KEY + "\n"})
        self.repository.git("checkout", "--quiet", "-")
        self.assert_passes()

    def test_and_it_is_found_once_that_branch_is_merged(self):
        # The other side of the scope rule: reachability is the whole test, so
        # merging the branch brings its objects into view.
        self.repository.git("checkout", "--quiet", "-b", "elsewhere")
        self.repository.commit("on a branch", **{"keys.txt": "id " + AWS_KEY + "\n"})
        self.repository.git("checkout", "--quiet", "-")
        self.repository.git(
            "-c",
            "user.email=probe@example.com",
            "-c",
            "user.name=probe",
            "merge",
            "--quiet",
            "--no-edit",
            "elsewhere",
        )
        self.assert_fails("issued-credential")


class TestTheRulesAreTheTreeScanS(HistoryCheck):
    def test_the_rule_set_is_the_same_object(self):
        # Not "equivalent": the same list, loaded from the same file. A rule
        # added to the tree scan is enforced here on the next run.
        tree = load_module("scan_sensitive_strings")
        self.assertEqual(
            [name for name, _, _ in self.module.rules().RULES],
            [name for name, _, _ in tree.RULES],
        )
        self.assertEqual(
            self.module.rules().MINIMUM_SECRET_LENGTH, tree.MINIMUM_SECRET_LENGTH
        )

    def test_a_private_key_in_the_history_is_found(self):
        self.repository.commit(
            "key", **{"id.pem": "-----BEGIN" + " RSA PRIVATE KEY-----\n"}
        )
        self.assert_fails("private-key")

    def test_an_address_in_the_history_is_found(self):
        self.repository.commit(
            "notes", **{"notes.md": "a.person" + "@" + "somecompany.com\n"}
        )
        self.assert_fails("personal-email")

    def test_a_placeholder_is_exempt_in_the_history_too(self):
        self.repository.commit(
            "ci", **{"w.yml": "  POSTGRES_PASSWORD: ci_superuser_" + "not_a_secret\n"}
        )
        self.assert_passes()


class TestThePathDecidesTheRules(HistoryCheck):
    def test_one_blob_at_two_paths_is_judged_at_each(self):
        # `:'name'` is psql interpolation in a .sql file and an assignment
        # anywhere else. The two paths hold byte-identical content, so git
        # stores one object and the scan has to judge it twice.
        #
        # The names are chosen so the exempt path sorts first. Keying the
        # deduplication by object name alone would then keep `a.sql`, drop
        # `z.yml`, and pass — which is exactly what this must not do. A
        # mutation probe found that hole: with the paths the other way round
        # the assertion held whether or not the deduplication was correct.
        line = "PASSWORD :'" + LITERAL + "'\n"
        self.repository.commit("both", **{"a.sql": line, "z.yml": line})
        output = self.assert_fails("assigned-secret")
        self.assertIn("z.yml", output)
        self.assertNotIn("a.sql", output)

    def test_the_same_content_only_in_sql_passes(self):
        self.repository.commit("sql", **{"a.sql": "PASSWORD :'" + LITERAL + "'\n"})
        self.assert_passes()


class TestWhatIsEnumerated(HistoryCheck):
    """`named_objects` decides what gets read at all, so its two properties
    are asserted directly rather than only through a finding that happens to
    depend on them."""

    def paths_of(self, name):
        return sorted(path for object_name, path in self.module.named_objects()
                      if object_name == name)

    def object_at(self, path):
        return self.repository.git("rev-parse", f"HEAD:{path}").strip()

    def test_one_object_at_two_paths_is_two_entries(self):
        # The path decides which rules apply, so the same bytes at two paths
        # are two things to judge, not one.
        self.repository.commit("both", **{"a.sql": "same\n", "z.yml": "same\n"})
        self.assertEqual(self.paths_of(self.object_at("a.sql")), ["a.sql", "z.yml"])

    def test_one_object_at_one_path_across_many_commits_is_one_entry(self):
        # The other half: a file unchanged across fifty commits is read once.
        # This is what keeps the scan linear in distinct content rather than
        # in commits, and it is safe precisely because the rules read only the
        # content and the path.
        for index in range(5):
            self.repository.commit(f"c{index}", **{"other.md": f"{index}\n"})
        self.assertEqual(self.paths_of(self.object_at("README.md")), ["README.md"])


class TestWhatIsScanned(HistoryCheck):
    def test_a_skipped_directory_is_still_scanned_in_the_history(self):
        # The deliberate difference from the tree scan, which ignores these
        # because they are not reviewable content in a working tree. Committed,
        # they are published like anything else.
        self.repository.commit(
            "vendored", **{"node_modules__x__index.js": 'k = "' + AWS_KEY + '"\n'}
        )
        code, tree_output = self.tree_scan_of(self.repository.path)
        self.assertEqual(code, 0, tree_output)
        self.assert_fails("issued-credential")

    def test_a_symlink_target_in_the_history_is_scanned(self):
        # Git stores a symlink's target as the blob's content, so the target
        # is read here for the same reason the tree scan reads `readlink()`.
        os.symlink("/Users/" + "jdoe/checkouts/mvp", self.repository.path / "checkout")
        self.repository.commit("link")
        self.assert_fails("local-machine-path")

    def test_a_blob_whose_content_looks_like_a_batch_header_is_read_correctly(self):
        # `git cat-file --batch` frames each blob with `<name> blob <size>`.
        # Parsing by scanning for the next header instead of by the declared
        # size would desynchronise on content like this, and every later blob
        # would be read at the wrong offset.
        forged = "0000000000000000000000000000000000000000 blob 99\n" * 5
        self.repository.commit(
            "tricky",
            **{"a.md": forged, "b.md": "harmless\n", "c.md": "id " + AWS_KEY + "\n"},
        )
        output = self.assert_fails("issued-credential")
        self.assertIn("c.md", output)

    def test_many_blobs_are_all_read(self):
        # The batch reader's offsets, over enough objects that a systematic
        # off-by-one would land the credential outside what is scanned.
        files = {f"f{index}.md": f"line {index}\n" * index for index in range(1, 30)}
        files["f29.md"] = "id " + AWS_KEY + "\n"
        self.repository.commit("many", **files)
        self.assert_fails("issued-credential")


class TestWhenItCannotRun(HistoryCheck):
    def test_a_shallow_clone_fails_rather_than_passing(self):
        # The one way a history scan goes wrong without anyone noticing.
        self.repository.commit("second", **{"notes.md": "nothing\n"})
        self.repository.commit("third", **{"notes.md": "still nothing\n"})
        shallow = self.directory / "shallow"
        subprocess.run(
            (
                "git",
                "clone",
                "--quiet",
                "--depth",
                "1",
                self.repository.path.as_uri(),
                str(shallow),
            ),
            capture_output=True,
            check=True,
        )
        self.module.WORK_TREE = shallow
        output = self.assert_fails("CANNOT RUN")
        self.assertIn("shallow", output)

    def test_a_directory_that_is_not_a_repository_fails(self):
        self.module.WORK_TREE = self.directory / "empty"
        (self.directory / "empty").mkdir()
        output = self.assert_fails("CANNOT RUN")
        self.assertIn("git failed", output)

    def test_a_repository_with_no_commits_fails(self):
        bare = self.directory / "fresh"
        bare.mkdir()
        subprocess.run(("git", "init", "--quiet"), cwd=bare, check=True)
        self.module.WORK_TREE = bare
        self.assert_fails("CANNOT RUN")


class TestWhatIsReported(HistoryCheck):
    def test_a_credential_is_not_printed_in_full(self):
        self.repository.commit("add", **{"config.yml": 'api_key: "' + LITERAL + '"\n'})
        output = self.assert_fails("assigned-secret")
        self.assertNotIn(LITERAL, output)
        self.assertIn("(16 characters)", output)

    def test_a_finding_names_the_object_the_path_and_the_line(self):
        self.repository.commit("add", **{"deep/config.yml": "\n\nid " + AWS_KEY + "\n"})
        output = self.assert_fails("issued-credential")
        self.assertIn("deep/config.yml:3:", output)
        self.assertIn("AGENTS.md: never add credentials or secrets", output)

    def test_it_says_how_to_find_the_commit_that_carries_the_object(self):
        # A blob name is not something an owner can act on by itself.
        self.repository.commit("add", **{"keys.txt": "id " + AWS_KEY + "\n"})
        output = self.assert_fails("issued-credential")
        self.assertIn("--find-object", output)
        self.assertIn("rewrite", output)


class TestTheRepositoryHistory(unittest.TestCase):
    """The positive case, and what stops a probe above from being written out
    whole: this file is committed, so a whole probe would fail the scan over
    this repository's own history from that commit onward, permanently."""

    def test_this_repository_passes(self):
        module = load_module("scan_history_sensitive_strings")
        module.WORK_TREE = REPOSITORY
        captured = io.StringIO()
        with contextlib.redirect_stdout(captured):
            code = module.main()
        output = captured.getvalue()
        self.assertEqual(code, 0, output)
        self.assertIn("Sensitive strings in history: PASS", output)


class TestTheCheckIsRegistered(unittest.TestCase):
    """A check that runs nowhere is not a check — and this one is also the
    check a shallow checkout would silently defeat."""

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

    def test_ci_checks_out_the_whole_history(self):
        # Without this the scan reports CANNOT RUN rather than passing wrongly,
        # but a check that cannot run on every pull request is not a check
        # either. Asserted here so a later edit to the checkout step fails a
        # test instead of turning this one into a permanent red.
        workflow = (
            REPOSITORY / ".github/workflows/repository-checks.yml"
        ).read_text(encoding="utf-8")
        head = workflow[: workflow.index("Scan the Git history")]
        self.assertIn("fetch-depth: 0", head)


if __name__ == "__main__":
    unittest.main(verbosity=2)
