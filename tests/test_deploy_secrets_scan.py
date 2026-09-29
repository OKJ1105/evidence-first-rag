"""`deploy-v0.1` `DP-003`'s image, workflow and artifact half, without Docker.

The exported filesystem is a tar stream and the image configuration a
dictionary, so each is built here from `SAMPLE_*` values.
"""

import importlib.util
import io
import json
import os
import pathlib
import tarfile
import tempfile
import unittest

from evidence_first_rag.deploy import secrets_scan

REPOSITORY = pathlib.Path(__file__).resolve().parents[1]
# Named from this file so the suite does not depend on the working directory;
# what the deploy job does with the module's own default is its own test below.
SCANNER = REPOSITORY / "scripts" / "checks" / "scan_sensitive_strings.py"

VALUE = "SAMPLE_KNOWN_SECRET_VALUE_7Q2"
# Assembled at run time, so the repository scan does not read this file as holding one.
SHAPED = "-----BEGIN " + "PRIVATE KEY-----"
ASSIGNED_VALUE = "Q" * 43
# Same reason: the name and the operator never meet in this file's own text.
ASSIGNED = "sample_admin_password" + ": " + '"' + ASSIGNED_VALUE + '"'


def tar_of(files: dict) -> io.BytesIO:
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w") as archive:
        for name, text in files.items():
            data = text.encode("utf-8")
            info = tarfile.TarInfo(name)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
    stream.seek(0)
    return stream


class TheImageFilesystem(unittest.TestCase):
    def scan(self, files):
        findings = []
        secrets_scan.scan_image_filesystem(tar_of(files), [VALUE], findings, secrets_scan._shape_rules(SCANNER))
        return findings

    def test_a_known_value_is_found_anywhere(self):
        findings = self.scan({"usr/lib/somewhere.txt": f"x {VALUE} y"})
        self.assertEqual([f["test"] for f in findings], ["known value 1"])

    def test_a_shape_is_found_in_this_repositorys_files(self):
        findings = self.scan({"app/src/leak.py": SHAPED})
        self.assertEqual([f["test"] for f in findings], ["private-key"])

    def test_a_shape_outside_app_is_not_read(self):
        """Installed packages ship test vectors; only the known value is sought there."""
        self.assertEqual(self.scan({"usr/lib/python3.11/test/key.pem": SHAPED}), [])

    def test_a_clean_image_has_no_finding(self):
        self.assertEqual(self.scan({"app/src/ok.py": "SAMPLE_OK = 1", "etc/os-release": "x"}), [])


class TheImageConfig(unittest.TestCase):
    def scan(self, config):
        findings = []
        secrets_scan.scan_image_config(config, [VALUE], findings, secrets_scan._shape_rules(SCANNER))
        return findings

    def test_a_secret_setting_in_the_image_is_found_whatever_its_value(self):
        findings = self.scan({"Env": ["PATH=/usr/bin", "ANTHROPIC_API_KEY=SAMPLE_PLACEHOLDER"]})
        self.assertEqual([f["test"] for f in findings], ["secret setting in image"])

    def test_a_known_value_in_a_label_is_found(self):
        findings = self.scan({"Labels": {"note": VALUE}})
        self.assertEqual([f["test"] for f in findings], ["known value 1"])

    def test_the_usual_environment_is_clean(self):
        self.assertEqual(self.scan({"Env": ["PATH=/usr/local/bin", "LANG=C.UTF-8"], "Cmd": ["python3"]}), [])


class TheReport(unittest.TestCase):
    def test_no_finding_carries_the_value(self):
        findings = []
        secrets_scan.scan_text(f"a={VALUE}", "artifact:x.json", [VALUE], findings)
        self.assertNotIn(VALUE, json.dumps(findings))
        self.assertEqual(findings, [{"where": "artifact:x.json", "test": "known value 1"}])

    def test_the_known_values_come_from_the_exported_variables(self):
        environment = {"MVP_RUNTIME_PASSWORD": VALUE, "MVP_PROVISIONING_PASSWORD": "", "OTHER": "SAMPLE_X"}
        self.assertEqual(secrets_scan.known_values(environment), [VALUE])

    def test_the_case_fails_when_no_secret_was_provided(self):
        with tempfile.TemporaryDirectory() as directory:
            out = pathlib.Path(directory) / "scan.json"
            original = secrets_scan.scan_image
            secrets_scan.scan_image = lambda *arguments: None
            try:
                status = secrets_scan.main(
                    ["--image", "SAMPLE_IMAGE", "--workflows", directory, "--out", str(out),
                     "--scanner", str(SCANNER)],
                    environment={},
                )
            finally:
                secrets_scan.scan_image = original
            self.assertEqual(status, 1)
            self.assertFalse(json.loads(out.read_text())["DP-003 image, workflows, artifact"]["passed"])

    def test_a_scan_that_raises_is_recorded_as_a_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            out = pathlib.Path(directory) / "scan.json"
            original = secrets_scan.scan_image

            def broken(*arguments):
                raise OSError("SAMPLE")

            secrets_scan.scan_image = broken
            try:
                status = secrets_scan.main(
                    ["--image", "SAMPLE_IMAGE", "--workflows", directory, "--out", str(out),
                     "--scanner", str(SCANNER)],
                    environment={"MVP_RUNTIME_PASSWORD": VALUE},
                )
            finally:
                secrets_scan.scan_image = original
            record = json.loads(out.read_text())["DP-003 image, workflows, artifact"]
            self.assertEqual(status, 1)
            self.assertEqual(record["error"], "the scan itself failed: OSError")

    def test_a_scanner_that_cannot_be_loaded_is_recorded_rather_than_raised(self):
        """The rules are loaded inside the scan, so a scanner that is not
        where the job looked leaves a record instead of a traceback (#253 B1)."""
        with tempfile.TemporaryDirectory() as directory:
            out = pathlib.Path(directory) / "scan.json"
            status = secrets_scan.main(
                ["--image", "SAMPLE_IMAGE", "--workflows", directory, "--out", str(out),
                 "--scanner", str(pathlib.Path(directory) / "absent.py")],
                environment={"MVP_RUNTIME_PASSWORD": VALUE},
            )
            record = json.loads(out.read_text())["DP-003 image, workflows, artifact"]
            self.assertEqual(status, 1)
            self.assertFalse(record["passed"])
            self.assertEqual(record["error"], "the scan itself failed: FileNotFoundError")


class TheScopeOfTheRecord(unittest.TestCase):
    """`passed` is a verdict over what the scan read. The record names those
    targets and states what it leaves out, so a file a later deploy step writes
    into the uploaded artifact is never covered by implication (#253 B3)."""

    def run_over(self, directory, artifacts, image=None):
        out = pathlib.Path(directory) / "scan.json"
        original = secrets_scan.scan_image
        secrets_scan.scan_image = image or (lambda *arguments: None)
        try:
            status = secrets_scan.main(
                ["--image", "SAMPLE_IMAGE", "--workflows", str(pathlib.Path(directory) / "workflows"),
                 "--artifacts", *artifacts, "--out", str(out), "--scanner", str(SCANNER)],
                environment={"MVP_RUNTIME_PASSWORD": VALUE},
            )
        finally:
            secrets_scan.scan_image = original
        return status, json.loads(out.read_text())["DP-003 image, workflows, artifact"]

    def test_the_record_names_every_target_it_read(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            (root / "workflows").mkdir()
            (root / "workflows" / "sample.yml").write_text("name: Sample\n", encoding="utf-8")
            (root / "kept.json").write_text("{}\n", encoding="utf-8")
            status, record = self.run_over(directory, [str(root / "kept.json")])
            self.assertEqual(status, 0)
            self.assertTrue(record["passed"])
            self.assertEqual(record["scanned"]["image"], "SAMPLE_IMAGE")
            self.assertEqual(record["scanned"]["workflows"], [(root / "workflows" / "sample.yml").as_posix()])
            self.assertEqual(record["scanned"]["artifacts"], [(root / "kept.json").as_posix()])

    def test_a_file_that_was_not_there_is_not_named_as_read(self):
        """An artifact a failed step never wrote is absent from `scanned`,
        rather than counted as a target that passed."""
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            (root / "workflows").mkdir()
            _status, record = self.run_over(directory, [str(root / "absent.json")])
            self.assertEqual(record["scanned"]["artifacts"], [])

    def test_a_passing_record_states_what_it_does_not_cover(self):
        with tempfile.TemporaryDirectory() as directory:
            (pathlib.Path(directory) / "workflows").mkdir()
            _status, record = self.run_over(directory, [])
            self.assertEqual(record["limitations"], list(secrets_scan.LIMITATIONS))
            self.assertTrue(record["limitations"])

    def test_an_image_the_scan_did_not_finish_is_not_named_as_read(self):
        with tempfile.TemporaryDirectory() as directory:
            (pathlib.Path(directory) / "workflows").mkdir()

            def broken(*arguments):
                raise OSError("SAMPLE")

            status, record = self.run_over(directory, [], image=broken)
            self.assertEqual(status, 1)
            self.assertIsNone(record["scanned"]["image"])


class TheScannerLocation(unittest.TestCase):
    """The deploy job installs the package (`pip install .`), so the module
    runs from site-packages while the job's working directory is the checkout.
    The scanner is found from the second, never from the first (#253 B1)."""

    def test_the_default_is_read_from_the_working_directory(self):
        self.assertFalse(secrets_scan.SCANNER.is_absolute())
        self.assertTrue((REPOSITORY / secrets_scan.SCANNER).is_file())

    def test_the_rules_load_when_the_module_sits_outside_the_repository(self):
        with tempfile.TemporaryDirectory() as directory:
            installed = pathlib.Path(directory) / "secrets_scan.py"
            installed.write_bytes(pathlib.Path(secrets_scan.__file__).read_bytes())
            specification = importlib.util.spec_from_file_location("installed_scan", installed)
            module = importlib.util.module_from_spec(specification)
            specification.loader.exec_module(module)
            here = os.getcwd()
            os.chdir(REPOSITORY)
            try:
                loaded = [name for name, _find in module._shape_rules()]
            finally:
                os.chdir(here)
            self.assertEqual(loaded, list(secrets_scan.SHAPE_RULES))


class TheCredentialRules(unittest.TestCase):
    def test_every_credential_rule_the_scanner_defines_is_applied(self):
        """`deploy-v0.1` Section 8 asks `DP-003` for every secret pattern the
        sensitive-string scan defines (#253 B2)."""
        scanner = secrets_scan._scanner(SCANNER)
        defined = [name for name, clause, _find in scanner.RULES if "credentials or secrets" in clause]
        self.assertEqual(sorted(secrets_scan.SHAPE_RULES), sorted(defined))

    def test_a_secret_assigned_under_a_secret_name_is_found(self):
        findings = []
        secrets_scan.scan_text(
            ASSIGNED, "workflow:.github/workflows/sample.yml", [VALUE], findings,
            secrets_scan._shape_rules(SCANNER), ".github/workflows/sample.yml",
        )
        self.assertEqual([f["test"] for f in findings], ["assigned-secret"])
        self.assertNotIn(ASSIGNED_VALUE, json.dumps(findings))


class TheRecordRun(unittest.TestCase):
    """#254 B3 and N3, N4: the second run over the files written after the
    checks step, with no image and no workflows."""

    def test_the_record_run_reads_only_the_named_files(self):
        with tempfile.TemporaryDirectory() as directory:
            record = pathlib.Path(directory) / "deploy-record.json"
            record.write_text('{"provisioned": "SAMPLE_OK"}')
            out = pathlib.Path(directory) / "scan.json"
            called = []
            original = secrets_scan.scan_image
            secrets_scan.scan_image = lambda *arguments: called.append(arguments)
            try:
                status = secrets_scan.main(
                    ["--workflows", "none", "--artifacts", str(record), "--out", str(out)],
                    environment={"PGPASSWORD": VALUE},
                )
            finally:
                secrets_scan.scan_image = original
            document = json.loads(out.read_text())["DP-003 image, workflows, artifact"]
        self.assertEqual(status, 0)
        self.assertEqual(called, [])
        self.assertEqual(document["scanned"], {"image": None, "workflows": [], "artifacts": [record.as_posix()]})

    def test_the_admin_password_is_a_known_value(self):
        self.assertEqual(secrets_scan.known_values({"PGPASSWORD": VALUE}), [VALUE])

    def test_the_image_filesystem_reports_how_many_own_files_it_read(self):
        stream = tar_of({"app/src/a.py": "x", "app/src/b.py": "y", "usr/lib/c": "z"})
        self.assertEqual(secrets_scan.scan_image_filesystem(stream, [VALUE], [], secrets_scan._shape_rules()), 2)

    def test_a_secret_under_a_secret_shaped_name_in_the_image_env_is_found(self):
        findings = []
        value = "S" * 20
        secrets_scan.scan_image_config({"Env": [f"DB_PASSWORD={value}"]}, [], findings, secrets_scan._shape_rules())
        self.assertEqual([f["test"] for f in findings], ["assigned-secret"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
