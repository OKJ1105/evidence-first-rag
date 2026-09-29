"""`deploy-v0.1` `DP-008`, without a network or Azure: the requests go to a
stand-in `fetch`, and each app's log download is a zip built here."""

import io
import json
import unittest
import zipfile

from evidence_first_rag.deploy import log_checks

MARKER = "SAMPLE_DP008_TEST"


def zip_of(files: dict) -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        for name, text in files.items():
            archive.writestr(name, text)
    return stream.getvalue()


class Recorder:
    def __init__(self):
        self.requests = []

    def __call__(self, method, url, headers=None, body=None, timeout=90):
        self.requests.append((method, url, body))
        return (200 if url.endswith("/v1/discover") else 400), {}, b"{}"


def run(logs, marker=MARKER):
    fetch = Recorder()
    pauses = []
    result = log_checks.dp008(
        fetch, lambda app: zip_of(logs[app]), "SAMPLE_SURFACE_HOST", "SAMPLE_RELAY_HOST",
        "surface", "relay", marker=marker, pause=pauses.append,
    )
    return result, fetch, pauses


CLEAN = {
    "surface": {"LogFiles/app.log": '{"path": "/v1/discover", "status": 200}'},
    "relay": {"LogFiles/app.log": '{"path": "/chat", "status": 400, "refusal": "malformed_request"}'},
}


class TheCase(unittest.TestCase):
    def test_clean_logs_that_show_both_requests_pass(self):
        (passed, _), _, _ = run(CLEAN)
        self.assertTrue(passed)

    def test_the_marker_in_any_file_fails_and_names_the_file_not_the_line(self):
        logs = {**CLEAN, "relay": {**CLEAN["relay"], "LogFiles/docker.log": f"body: What is {MARKER}?"}}
        (passed, detail), _, _ = run(logs)
        self.assertFalse(passed)
        self.assertIn("LogFiles/docker.log", detail)
        self.assertNotIn("What is", detail)

    def test_a_store_that_never_shows_the_request_fails(self):
        logs = {"surface": CLEAN["surface"], "relay": {"LogFiles/app.log": ""}}
        (passed, detail), _, pauses = run(logs)
        self.assertFalse(passed)
        self.assertIn("relay", detail)
        self.assertEqual(pauses.count(log_checks.PAUSE_SECONDS), log_checks.ATTEMPTS)

    def test_a_pass_is_not_concluded_before_the_minimum_reads(self):
        (_, _), _, pauses = run(CLEAN)
        self.assertEqual(pauses.count(log_checks.PAUSE_SECONDS), log_checks.MINIMUM_READS - 1)


class TheRequests(unittest.TestCase):
    def test_the_marker_travels_in_the_body_never_the_url(self):
        _, fetch, _ = run(CLEAN)
        self.assertEqual(len(fetch.requests), 2)
        for method, url, body in fetch.requests:
            self.assertEqual(method, "POST")
            self.assertNotIn(MARKER, url)
            self.assertIn(MARKER, body.decode())

    def test_the_chat_request_is_refused_before_any_model_call(self):
        """It ends with the relay's turn, which Section 4.2 refuses."""
        _, fetch, _ = run(CLEAN)
        chat = json.loads(fetch.requests[1][2])
        self.assertEqual(chat["messages"][-1]["role"], "assistant")

    def test_the_relay_request_waits_out_the_rate_window(self):
        _, _, pauses = run(CLEAN)
        self.assertEqual(pauses[0], log_checks.RATE_WINDOW_SECONDS)

    def test_each_run_draws_a_fresh_marker(self):
        first, second = log_checks.fresh_marker(), log_checks.fresh_marker()
        self.assertNotEqual(first, second)
        self.assertTrue(first.startswith("SAMPLE_"))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
