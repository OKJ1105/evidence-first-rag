"""`deploy-v0.1` `DP-008`, without a network or Azure: the requests go to a
stand-in `fetch`, and each app's log download is a zip built here."""

import io
import json
import unittest
import zipfile

from evidence_first_rag.api import request_log
from evidence_first_rag.deploy import http_checks, log_checks

MARKER = "SAMPLE_DP008_TEST"

# What each deployed app answers its marked request with: the surface's
# `api-v0.1` Section 4.2 envelope, and the relay's Section 4.6 refusal of a
# conversation ending with its own turn.
SURFACE_ANSWER = (200, json.dumps({
    "result": {"status": "not_found"},
    "rendered": None,
    "contract": {"identifier": "api-v0.1", "version": "0.2.0"},
}).encode())
RELAY_ANSWER = (400, json.dumps({"refusal": "malformed_request", "detail": "SAMPLE_DETAIL"}).encode())


def zip_of(files: dict) -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        for name, text in files.items():
            archive.writestr(name, text)
    return stream.getvalue()


class Recorder:
    def __init__(self, surface=SURFACE_ANSWER, relay=RELAY_ANSWER):
        self.requests = []
        self.answers = {log_checks.DISCOVER_PATH: surface, log_checks.CHAT_PATH: relay}

    def __call__(self, method, url, headers=None, body=None, timeout=90):
        self.requests.append((method, url, body))
        path = url.split("?", 1)[0]
        route = log_checks.DISCOVER_PATH if path.endswith(log_checks.DISCOVER_PATH) else log_checks.CHAT_PATH
        status, raw = self.answers[route]
        return status, {}, raw


def run(logs, marker=MARKER, fetch=None):
    fetch = Recorder() if fetch is None else fetch
    pauses, reads = [], []

    def download(app):
        reads.append(app)
        return zip_of(logs[app])

    result = log_checks.dp008(
        fetch, download, "SAMPLE_SURFACE_HOST", "SAMPLE_RELAY_HOST",
        "surface", "relay", marker=marker, pause=pauses.append,
    )
    return result, fetch, pauses, reads


# Each app's own record of a request to its route, as the deployed process
# writes it: `api/request_log.py:log_line`'s Section 4.7 JSON line for the
# surface (#259), and `relay/app.py:log_line`'s Section 4.10 line for the relay.
CLEAN = {
    "surface": {"LogFiles/app.log": request_log.log_line(
        path="/v1/discover", http_status=200, latency_ms=1.0,
        body=b'{"contract":{"identifier":"api-v0.1"},"result":{"status":"found"}}',
    )},
    "relay": {"LogFiles/app.log": json.dumps({
        "timestamp": "2026-01-01T00:00:00+00:00",
        "path": "/chat",
        "http_status": 400,
        "latency_ms": 1.0,
        "refusal": "malformed_request",
    }, separators=(",", ":"))},
}

# What the platform's own HTTP log records: the request line, and nothing an
# app wrote. It carries each route, so it must not meet the control alone.
PLATFORM_ONLY = {
    "surface": {"LogFiles/http/RawLogs/sample.log": "2026-01-01T00:00:00 SAMPLE-SURFACE POST /v1/discover - 443 - - 200 0 0 12"},
    "relay": {"LogFiles/http/RawLogs/sample.log": "2026-01-01T00:00:00 SAMPLE-RELAY POST /chat - 443 - - 400 0 0 12"},
}


class TheCase(unittest.TestCase):
    def test_clean_logs_that_show_both_requests_pass(self):
        (passed, _), _, _, _ = run(CLEAN)
        self.assertTrue(passed)

    def test_the_marker_in_any_file_fails_and_names_the_file_not_the_line(self):
        logs = {**CLEAN, "relay": {**CLEAN["relay"], "LogFiles/docker.log": f"body: What is {MARKER}?"}}
        (passed, detail), _, _, _ = run(logs)
        self.assertFalse(passed)
        self.assertIn("LogFiles/docker.log", detail)
        self.assertNotIn("What is", detail)

    def test_a_store_that_never_shows_the_request_fails(self):
        logs = {"surface": CLEAN["surface"], "relay": {"LogFiles/app.log": ""}}
        (passed, detail), _, pauses, _ = run(logs)
        self.assertFalse(passed)
        self.assertIn("relay", detail)
        # The failing store's file names, never its lines (#256 N6).
        self.assertIn("LogFiles/app.log", detail)
        # No pause after the last read (#256 N3).
        self.assertEqual(pauses.count(log_checks.PAUSE_SECONDS), log_checks.ATTEMPTS - 1)

    def test_a_pass_says_the_control_may_be_an_earlier_line(self):
        """#256 N7: the evidence claims no more than the run established."""
        (passed, detail), _, _, _ = run(CLEAN)
        self.assertTrue(passed)
        self.assertIn("may be an earlier request's", detail)

    def test_a_pass_records_the_file_names_the_download_held(self):
        """#279 B2: the committed record says which files the store carried, so
        a later run holding fewer -- a logging switch turned off with it -- is
        readable against it. Names only, never a line."""
        (passed, detail), _, _, _ = run(CLEAN)
        self.assertTrue(passed)
        self.assertIn("LogFiles/app.log", detail)
        self.assertNotIn('"http_status"', detail)

    def test_a_pass_is_not_concluded_before_the_minimum_reads(self):
        (_, _), _, pauses, _ = run(CLEAN)
        self.assertEqual(pauses.count(log_checks.PAUSE_SECONDS), log_checks.MINIMUM_READS - 1)


class ThePositiveControl(unittest.TestCase):
    """#255 B2: the control wants the app's own record, not the route string.

    The platform's HTTP log holds the request line for both apps, and holds no
    line that could ever carry a body. A download of it alone leaves the stream
    Section 4.7 constrains uninspected, so it fails the case rather than
    passing it.
    """

    def test_the_platform_http_log_alone_does_not_meet_the_control(self):
        (passed, detail), _, _, _ = run(PLATFORM_ONLY)
        self.assertFalse(passed)
        self.assertIn("surface", detail)
        self.assertIn("relay", detail)

    def test_the_relay_needs_its_own_record_not_a_bare_path(self):
        logs = {**CLEAN, "relay": {"LogFiles/app.log": '{"path":"/chat"}'}}
        (passed, detail), _, _, _ = run(logs)
        self.assertFalse(passed)
        self.assertIn("relay", detail)
        self.assertNotIn("surface", detail)

    def test_the_surface_needs_its_own_record_not_uvicorns_access_line(self):
        """#268 N7: the line DP-008 relied on before this record existed."""
        access = 'INFO:     <address>:0 - "POST /v1/discover HTTP/1.1" 200 OK'
        logs = {**CLEAN, "surface": {"LogFiles/app.log": access}}
        (passed, detail), _, _, _ = run(logs)
        self.assertFalse(passed)
        self.assertIn("surface", detail)
        self.assertNotIn("relay", detail)

    def test_terms_spread_over_separate_lines_are_not_one_record(self):
        logs = {**CLEAN, "relay": {"LogFiles/app.log": '{"path":"/chat"}\n{"http_status":400}'}}
        (passed, _), _, _, _ = run(logs)
        self.assertFalse(passed)


class TheRequestsHaveToBeAnswered(unittest.TestCase):
    """#255 B1: a request the app never processed cannot pass the case.

    The control above is met by earlier calls to the same routes, so the
    marker's absence from the store says nothing unless the marker reached the
    app. Neither answer's body reaches the recorded detail.
    """

    def test_a_rate_limited_relay_fails_the_case_and_reads_no_log(self):
        rate_limited = (429, json.dumps({"refusal": "rate_limited", "detail": "SAMPLE_DETAIL"}).encode())
        (passed, detail), _, _, reads = run(CLEAN, fetch=Recorder(relay=rate_limited))
        self.assertFalse(passed)
        self.assertIn("429", detail)
        self.assertEqual(reads, [])

    def test_an_unreachable_relay_fails_the_case(self):
        unanswered = (http_checks.UNREACHABLE, b"TimeoutError: timed out")
        (passed, detail), _, _, _ = run(CLEAN, fetch=Recorder(relay=unanswered))
        self.assertFalse(passed)
        self.assertIn("TimeoutError", detail)

    def test_an_unreachable_surface_fails_the_case(self):
        unanswered = (http_checks.UNREACHABLE, b"URLError: name not known")
        (passed, detail), _, _, _ = run(CLEAN, fetch=Recorder(surface=unanswered))
        self.assertFalse(passed)
        self.assertIn("surface", detail)

    def test_a_platform_error_page_for_the_surface_fails_the_case(self):
        """A 502 for a container that has not finished starting is not the
        app's own answer, whatever the log store then shows."""
        (passed, detail), _, _, _ = run(CLEAN, fetch=Recorder(surface=(502, b"<html>502</html>")))
        self.assertFalse(passed)
        self.assertIn("502", detail)

    def test_a_200_that_is_not_the_surfaces_envelope_fails_the_case(self):
        (passed, _), _, _, _ = run(CLEAN, fetch=Recorder(surface=(200, b'{"ok":true}')))
        self.assertFalse(passed)


class TheRequests(unittest.TestCase):
    def test_the_marker_travels_in_the_body_and_the_url_query(self):
        """#279: Section 4.7 binds a request's URL too, so the marker is in
        both, and a store that records request targets fails the case."""
        _, fetch, _, _ = run(CLEAN)
        self.assertEqual(len(fetch.requests), 2)
        for method, url, body in fetch.requests:
            self.assertEqual(method, "POST")
            self.assertTrue(url.endswith(f"?{log_checks.MARKER_QUERY}={MARKER}"))
            self.assertIn(MARKER, body.decode())

    def test_a_platform_log_recording_the_query_string_fails_the_case(self):
        """#279: the request line the platform's HTTP log would write."""
        line = f"2026-01-01T00:00:00 SAMPLE-SURFACE POST /v1/discover q={MARKER} 443 - - 200 0 0 12"
        logs = {**CLEAN, "surface": {**CLEAN["surface"], "LogFiles/http/RawLogs/sample.log": line}}
        (passed, detail), _, _, _ = run(logs)
        self.assertFalse(passed)
        self.assertIn("LogFiles/http/RawLogs/sample.log", detail)
        self.assertNotIn(line, detail)

    def test_the_chat_request_is_refused_before_any_model_call(self):
        """It ends with the relay's turn, which Section 4.2 refuses."""
        _, fetch, _, _ = run(CLEAN)
        chat = json.loads(fetch.requests[1][2])
        self.assertEqual(chat["messages"][-1]["role"], "assistant")

    def test_the_relay_request_waits_out_the_rate_window(self):
        _, _, pauses, _ = run(CLEAN)
        self.assertEqual(pauses[0], log_checks.RATE_WINDOW_SECONDS)

    def test_each_run_draws_a_fresh_marker(self):
        first, second = log_checks.fresh_marker(), log_checks.fresh_marker()
        self.assertNotEqual(first, second)
        self.assertTrue(first.startswith("SAMPLE_"))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
