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
import types
import unittest

HERE = pathlib.Path(__file__).resolve().parent


def repository_root():
    """The repository the check is running *in*, not the one it was read from.

    `HERE.parent.parent` is the obvious way and it is wrong here. The loop
    registers this file as `{baseDir}/scripts/checks/...`, so under the loop
    it is read from the **base** checkout while the command runs with the
    **branch** checkout as its working directory — and `agent-loop.yml` gives
    `fetch-depth: 0` to the branch checkout only, leaving base shallow.
    Anchoring to `__file__` would point the positive case at a shallow
    repository, where the scan reports CANNOT RUN by design: a permanent red
    on every pull request that no branch could fix, because the loop reads
    base's copy of both the manifest and this file.

    Resolving from the working directory is right in every place this runs:
    CI (`fetch-depth: 0`, cwd the checkout), the loop (cwd the branch
    checkout), and a developer's clone.
    """
    return pathlib.Path(
        subprocess.run(
            ("git", "rev-parse", "--show-toplevel"),
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    )


REPOSITORY = repository_root()

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

    def test_every_chunk_boundary_is_crossed(self):
        # O2 on #97. Reading every version at once made peak memory the size
        # of the whole history, and this scan deliberately does not skip
        # vendored or build output — so one committed binary would put that
        # past a runner's budget, and an OOM-killed security check reads as
        # an infrastructure flake rather than as a finding. Chunking is only
        # safe if nothing falls between two chunks, so the smallest possible
        # chunk is driven over a count that is not a multiple of it.
        self.module.BATCH = 1
        files = {f"f{index}.md": f"line {index}\n" for index in range(6)}
        files["last.md"] = "id " + AWS_KEY + "\n"
        self.repository.commit("many", **files)
        self.assertIn("last.md", self.assert_fails("issued-credential"))

    def test_a_chunk_that_divides_the_work_unevenly_loses_nothing(self):
        self.module.BATCH = 3
        files = {f"g{index}.md": f"line {index}\n" for index in range(7)}
        files["g7.md"] = "id " + AWS_KEY + "\n"
        self.repository.commit("uneven", **files)
        self.assertIn("g7.md", self.assert_fails("issued-credential"))

    def test_the_count_is_the_same_whatever_the_chunk_size(self):
        for index in range(4):
            self.repository.commit(f"c{index}", **{f"h{index}.md": f"{index}\n"})
        self.module.BATCH = 1000
        whole = self.assert_passes()
        self.module.BATCH = 2
        self.assertEqual(whole, self.assert_passes())

    def test_many_blobs_are_all_read(self):
        # The batch reader's offsets, over enough objects that a systematic
        # off-by-one would land the credential outside what is scanned.
        files = {f"f{index}.md": f"line {index}\n" * index for index in range(1, 30)}
        files["f29.md"] = "id " + AWS_KEY + "\n"
        self.repository.commit("many", **files)
        self.assert_fails("issued-credential")


class TestWhatThePassLineClaims(HistoryCheck):
    def test_it_says_what_it_did_not_read(self):
        # B2 on #97. The scan reads file contents and nothing else; commit
        # messages, tag messages and identities are published too and are as
        # decidable by these rules. A PASS that reads as "the history is
        # clean" when it means "every file version is clean" is how a release
        # gate comes to rest on an incomplete basis, so the pass says so.
        output = self.assert_passes()
        self.assertIn("commit messages, tag messages and author identities", output)
        self.assertIn("are not read", output)


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

    def test_a_failure_deeper_in_the_run_still_reports_cannot_run(self):
        # N1 on #97. Only the first two git calls used to be guarded, so a
        # `cat-file --batch` that failed — a partial clone, a corrupt object —
        # printed a traceback. "Nothing found" and "could not look" are the
        # two answers a scan must never blur, and a traceback says the second
        # one badly.
        def unreadable(names):
            raise RuntimeError("git could not read 0123456789")

        self.module.contents = unreadable
        output = self.assert_fails("CANNOT RUN")
        self.assertIn("could not read", output)

    def test_a_git_failure_deeper_in_the_run_reports_it_too(self):
        def failing(names):
            raise subprocess.CalledProcessError(
                128, ("git", "cat-file"), stderr=b"fatal: bad object"
            )

        self.module.contents = failing
        self.assertIn("bad object", self.assert_fails("CANNOT RUN"))

    def test_a_repository_with_no_commits_fails(self):
        bare = self.directory / "fresh"
        bare.mkdir()
        subprocess.run(("git", "init", "--quiet"), cwd=bare, check=True)
        self.module.WORK_TREE = bare
        self.assert_fails("CANNOT RUN")


class TestAMalformedBatchStream(HistoryCheck):
    """#104. `git cat-file --batch` can exit 0 having written a stream the
    parse cannot read.

    A failing git is already covered by `TestWhenItCannotRun`. This is the
    other shape: git reports success and what it wrote is short or misframed,
    which is what a partial clone, a full disk, or a killed subprocess look
    like from here. Each case is asserted through `main()` rather than against
    `contents()` alone, because what is being tested is the answer an operator
    reads, not which exception type was raised on the way.

    Real git serves every other call, so the walk that produces the object
    names is the real one and only the batch read is chosen by the test.
    """

    def batch_writes(self, stream):
        real = subprocess.run

        def run(arguments, **keywords):
            if tuple(arguments[:3]) == ("git", "cat-file", "--batch"):
                return subprocess.CompletedProcess(arguments, 0, stream, b"")
            return real(arguments, **keywords)

        # `main()` resolves `subprocess.CalledProcessError` through the module
        # too, so the stand-in has to carry it or the handler stops existing.
        self.module.subprocess = types.SimpleNamespace(
            run=run, CalledProcessError=subprocess.CalledProcessError
        )

    def object_name(self):
        """The one blob this repository holds, as git names it."""
        return self.repository.git("rev-parse", "HEAD:README.md").strip()

    def framed(self, body):
        """A well-formed frame for `body`, sized the way git sizes one."""
        return f"{self.object_name()} blob {len(body)}\n".encode() + body + b"\n"

    def headed(self, size_field, rest):
        """A frame whose header names the object actually requested.

        The name guard fires earlier than the size, length and separator
        guards and subsumes all three when the header names something else,
        so a test aimed at any of them has to get the name right or it
        silently stops testing what it says it does. That happened to three
        tests here when #110 added the guard, and this is what keeps it from
        happening again. (Two guards do precede it — mid-header and field
        count — so it is not the earliest of all of them.)
        """
        return f"{self.object_name()} blob {size_field}\n".encode() + rest

    def test_a_header_that_never_ends_reports_cannot_run(self):
        # `stream.index` raised ValueError here, which no handler caught, so
        # the operator got a traceback instead of a sentence.
        self.batch_writes(b"deadbeefdeadbeef blob 99999")
        self.assertIn("mid-header", self.assert_fails("CANNOT RUN"))

    def test_a_size_that_is_not_a_number_reports_cannot_run(self):
        # The second ValueError, from `int(header[2])`.
        self.batch_writes(self.headed("xyz", b"hello\n"))
        self.assertIn("unreadable size", self.assert_fails("CANNOT RUN"))

    def test_a_body_shorter_than_its_header_declares_reports_cannot_run(self):
        """The one that failed OPEN, which is why it matters most.

        Python's slice returns what it has rather than raising, so a short
        final frame produced no exception at all: the scan read five bytes of
        a file version declaring ninety-nine thousand, found nothing in them,
        and printed PASS. Verified before the fix — it exited 0 on exactly
        this stream.
        """
        self.batch_writes(self.headed(99999, b"short"))
        output = self.assert_fails("CANNOT RUN")
        self.assertIn("truncated", output)
        self.assertIn("wrote 5", output)

    def test_a_whole_frame_is_still_read_and_still_scanned(self):
        """The guard has to be seen not to fire on a good stream.

        A length check is one `!=` away from rejecting everything, and an
        off-by-one in the slice beside it would drop the last byte of every
        file version silently. So the frame here is exact, and what it carries
        is a credential the scan must still find — which it can only do by
        reading the body whole.
        """
        self.batch_writes(self.framed(b"id " + AWS_KEY.encode() + b"\n"))
        self.assertIn("issued-credential", self.assert_fails("issued-credential"))

    def test_a_whole_frame_carrying_nothing_sensitive_still_passes(self):
        self.batch_writes(self.framed(b"# Sample\n"))
        self.assertIn("PASS", self.assert_passes())

    def test_a_frame_that_is_not_terminated_reports_cannot_run(self):
        """O1 on #108. The last way this parse could desynchronise silently.

        A frame whose declared size is *short* of what git wrote passes the
        length check — the slice is exactly as long as the header claimed —
        and leaves the cursor inside the leftover content, where the next
        header is read out of file content. `test_a_blob_whose_content_looks
        _like_a_batch_header_is_read_correctly` shows a blob can imitate one,
        so that ends in a body mapped to the wrong name rather than in an
        error, and the path is what decides which rules apply to it.
        """
        self.batch_writes(self.headed(5, b"abcdefghijklmnopqrst\n"))
        self.assertIn("misframed", self.assert_fails("CANNOT RUN"))

    def test_a_frame_answering_for_another_object_reports_cannot_run(self):
        """#110. The definitive desynchronisation guard.

        The separator check before it is probabilistic: it catches a
        desynchronised cursor only when the leftover bytes fail to look like
        a frame, and `test_a_blob_whose_content_looks_like_a_batch_header_is
        _read_correctly` commits a blob proving they can. Whatever they
        resemble, they do not begin with the name that was asked for.
        """
        self.batch_writes(b"0" * 40 + b" blob 5\nabcde\n")
        self.assertIn("desynchronised", self.assert_fails("CANNOT RUN"))

    def test_two_whole_frames_are_read_in_the_order_they_were_requested(self):
        """The guard must not reject git's real answer — over more than one
        frame, which is the only version of that claim worth making.

        A one-frame version of this test asserted nothing that
        `test_a_whole_frame_carrying_nothing_sensitive_still_passes` did not
        already assert: byte-for-byte the same body, so no mutation could
        fail one without failing the other. Round 1 on #114 found that, and
        it was the third test in this slice to name something it did not
        test.

        Two frames make it earn the name. It fails if the guard rejects a
        name git echoed back, and it fails if the arithmetic after the first
        body lands the cursor anywhere but on the second header — which is
        the property the name guard is there to detect and which one frame
        cannot exercise at all.
        """
        self.repository.commit("second", **{"notes.md": "nothing\n"})
        bodies = {
            self.repository.git("rev-parse", "HEAD:README.md").strip(): b"# Sample\n",
            self.repository.git("rev-parse", "HEAD:notes.md").strip(): b"nothing\n",
        }
        # `contents()` requests `sorted({name ...})`, and the stream has to
        # answer in that order or the parse is reading the wrong frame.
        self.batch_writes(
            b"".join(
                f"{name} blob {len(body)}\n".encode() + body + b"\n"
                for name, body in sorted(bodies.items())
            )
        )
        self.assertIn("PASS", self.assert_passes())

    def test_a_header_name_that_is_not_utf_8_reports_cannot_run(self):
        """B1 on #114. The guard read `header[0]` as strict UTF-8.

        In the case it exists for, `header[0]` is blob content, and this scan
        deliberately reads binary history rather than skipping it — so the
        decode raised `UnicodeDecodeError`, a `ValueError` that no handler in
        `main()` catches. The operator got a traceback from the one guard
        added to stop exactly that. Verified before the fix: it escaped
        `main()` and `sys.exit` never ran.
        """
        self.batch_writes(b"\xff\xfe\xfd blob 5\nabcde\n")
        self.assertIn("desynchronised", self.assert_fails("CANNOT RUN"))

    def test_no_diagnostic_echoes_what_the_stream_carried(self):
        """N2 on #108. A diagnostic may not publish what a finding masks.

        Every finding in this module is reduced to four characters and a
        length, because a credential printed into a CI log is exposed a
        second time. A diagnostic printed to the same log has no licence to
        do otherwise — and a desynchronised parse is reading blob content as
        a header, so each of these three paths can be reached with a
        credential sitting where git's framing should be.
        """
        streams = {
            "mid-header": b"id " + AWS_KEY.encode(),
            "too few header fields": AWS_KEY.encode() + b"\nrest\n",
            "unreadable size": self.headed(AWS_KEY, b"x\n"),
            # The credential sits in the *name* field, which is where a
            # desynchronised cursor puts file content: the guard reads
            # `header[0]`, so that is the token a diagnostic would leak.
            # An earlier version of this entry put a placeholder name
            # there and a credential in the body, and asserted nothing —
            # the mutation probe caught it.
            "wrong object": AWS_KEY.encode() + b" blob 5\nabcde\n",
        }
        for where, stream in streams.items():
            with self.subTest(where=where):
                self.batch_writes(stream)
                output = self.assert_fails("CANNOT RUN")
                self.assertNotIn(AWS_KEY, output)


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


class TestWhereTheRepositoryUnderTestComesFrom(unittest.TestCase):
    """B1 on #97. Nothing pinned which checkout the positive case reads, and
    the loop runs this file from a shallow one."""

    def test_it_follows_the_working_directory_not_this_file(self):
        directory = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, directory, ignore_errors=True)
        elsewhere = Repository(directory / "elsewhere")
        elsewhere.commit("first", **{"README.md": "# Sample\n"})

        here = pathlib.Path.cwd()
        self.addCleanup(os.chdir, here)
        os.chdir(elsewhere.path)
        # `resolve()` because a temporary directory is a symlink on macOS.
        self.assertEqual(repository_root().resolve(), elsewhere.path.resolve())
        self.assertNotEqual(repository_root().resolve(), HERE.parent.parent)

    def test_the_loop_checks_out_the_branch_with_the_whole_history(self):
        # The other half of what the fix rests on: resolving from the working
        # directory is only safe while the working directory the loop gives
        # its checks has the whole history. `repository-checks.yml` has the
        # same assertion for CI in `TestTheCheckIsRegistered`.
        workflow = (
            REPOSITORY / ".github/workflows/agent-loop.yml"
        ).read_text(encoding="utf-8")
        step = workflow[workflow.index("Check out the branch under review") :]
        step = step[: step.index("\n      - ")]
        self.assertIn("fetch-depth: 0", step)


class TestTheRepositoryHistory(unittest.TestCase):
    """The positive case, and what stops a probe above from being written out
    whole: this file is committed, so a whole probe would fail the scan over
    this repository's own history from that commit onward, permanently."""

    def test_this_repository_passes(self):
        module = load_module("scan_history_sensitive_strings")
        module.WORK_TREE = repository_root()
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
