"""`deploy-v0.1` `DP-003`'s image, workflow and artifact half, without Docker.

The exported filesystem is a tar stream and the image configuration a
dictionary, so each is built here from `SAMPLE_*` values.
"""

import io
import json
import pathlib
import tarfile
import tempfile
import unittest

from evidence_first_rag.deploy import secrets_scan

VALUE = "SAMPLE_KNOWN_SECRET_VALUE_7Q2"
# Assembled at run time, so the repository scan does not read this file as holding one.
SHAPED = "-----BEGIN " + "PRIVATE KEY-----"


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
        secrets_scan.scan_image_filesystem(tar_of(files), [VALUE], findings, secrets_scan._shape_rules())
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
        secrets_scan.scan_image_config(config, [VALUE], findings, secrets_scan._shape_rules())
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
                    ["--image", "SAMPLE_IMAGE", "--workflows", directory, "--out", str(out)], environment={}
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
                    ["--image", "SAMPLE_IMAGE", "--workflows", directory, "--out", str(out)],
                    environment={"MVP_RUNTIME_PASSWORD": VALUE},
                )
            finally:
                secrets_scan.scan_image = original
            record = json.loads(out.read_text())["DP-003 image, workflows, artifact"]
            self.assertEqual(status, 1)
            self.assertEqual(record["error"], "the scan itself failed: OSError")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
