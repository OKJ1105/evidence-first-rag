"""`deploy-v0.1` `DP-005`, `DP-009`, `DP-010` and `DP-012`, against stand-ins.

Each case is driven through a fake `fetch`, so what it accepts and what it
refuses is exercised here; that the deployed apps answer this way is the
first deploy's to show.
"""

import io
import json
import ssl
import unittest
import urllib.error

from evidence_first_rag.deploy import http_checks as checks


def answering(table):
    """A `fetch` that answers from `(method, url-suffix) -> callable(headers, body)`."""
    calls = []

    def fetch(method, url, headers=None, body=None):
        calls.append((method, url, dict(headers or {}), body))
        for (want_method, suffix), answer in table.items():
            if method == want_method and url.endswith(suffix):
                return answer(headers or {}, body)
        raise AssertionError(f"unexpected {method} {url}")

    fetch.calls = calls
    return fetch


class TheRedirect(unittest.TestCase):
    def test_a_redirect_to_https_passes(self):
        fetch = answering({("GET", "host/"): lambda h, b: (301, {"Location": "https://host/"}, b"")})
        self.assertTrue(checks.dp005_https(fetch, "host")[0])

    def test_plain_http_served_fails(self):
        fetch = answering({("GET", "host/"): lambda h, b: (200, {}, b"")})
        self.assertFalse(checks.dp005_https(fetch, "host")[0])

    def test_a_served_page_with_a_location_header_is_not_a_redirect(self):
        fetch = answering({("GET", "host/"): lambda h, b: (200, {"Location": "https://host/"}, b"")})
        self.assertFalse(checks.dp005_https(fetch, "host")[0])

    def test_a_redirect_elsewhere_fails(self):
        fetch = answering({("GET", "host/"): lambda h, b: (302, {"Location": "https://other/"}, b"")})
        self.assertFalse(checks.dp005_https(fetch, "host")[0])


def refusal_body(kind=checks.METHOD_NOT_ALLOWED_REFUSAL):
    """What both apps answer an `OPTIONS` with: a Section 4.5 refusal document."""
    return json.dumps({"refusal": kind, "detail": "This route accepts POST only."}).encode()


class TheForeignOrigin(unittest.TestCase):
    """No grant to the foreign origin, and the app itself the one refusing."""

    def probe(self, status, headers=None, body=b""):
        fetch = answering({("OPTIONS", "/chat"): lambda h, b: (status, headers or {}, body)})
        return checks.dp005_foreign_origin(fetch, "https://relay/chat")

    def test_the_apps_own_refusal_passes(self):
        passed, detail = self.probe(405, body=refusal_body())
        self.assertTrue(passed, detail)

    def test_a_grant_to_the_foreign_origin_or_any_fails(self):
        for granted in (checks.FOREIGN_ORIGIN, "*"):
            passed, detail = self.probe(204, {"Access-Control-Allow-Origin": granted})
            self.assertFalse(passed, granted)
            self.assertIn(checks.FOREIGN_ORIGIN, detail)

    def test_an_admitted_preflight_granting_another_origin_passes(self):
        passed, detail = self.probe(204, {"Access-Control-Allow-Origin": "https://registered.invalid"})
        self.assertTrue(passed, detail)

    def test_a_platform_error_from_an_app_that_never_ran_fails(self):
        # No `Access-Control-Allow-Origin` here either, and that is the point:
        # App Service's own answer for a container still starting says nothing
        # about the grant, and recording it as a refusal would report the
        # Section 4.5 guarantee for a process that answered nothing.
        for status in (502, 503, 404):
            passed, detail = self.probe(status, body=b"<html>Service Unavailable</html>")
            self.assertFalse(passed, status)
            self.assertIn(str(status), detail)

    def test_an_unreachable_host_fails(self):
        passed, _ = self.probe(checks.UNREACHABLE, body=b"URLError: connection refused")
        self.assertFalse(passed)

    def test_a_405_that_is_not_the_apps_refusal_fails(self):
        # The framework's plain-text 405, or a gateway's: the status alone is
        # not the app's vocabulary.
        self.assertFalse(self.probe(405, body=b"Method Not Allowed")[0])
        self.assertFalse(self.probe(405, body=refusal_body("something_else"))[0])


class Refused(Exception):
    """Stands in for `psycopg.OperationalError`: the server answered and refused."""


class FakeCursor:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, statement):
        self.statement = statement

    def fetchone(self):
        return (1,)


class FakeConnection:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def cursor(self):
        self.opened = FakeCursor()
        return self.opened


def connecting(**per_mode):
    """A `connect` answering per `sslmode`: an exception is raised, else opened."""
    modes = []

    def connect(**kwargs):
        modes.append(kwargs["sslmode"])
        answer = per_mode[kwargs["sslmode"]]
        if isinstance(answer, BaseException):
            raise answer
        return FakeConnection()

    connect.modes = modes
    return connect


class TheDatabaseTls(unittest.TestCase):
    """The TLS control comes first, and only a refusal for want of TLS passes."""

    def test_a_refusal_naming_tls_after_a_good_control_passes(self):
        connect = connecting(require=None, disable=Refused("FATAL: SSL connection is required"))
        passed, detail = checks.dp005_database_requires_tls(connect, Refused)
        self.assertTrue(passed, detail)
        self.assertEqual(connect.modes, ["require", "disable"])

    def test_every_wording_of_the_requirement_is_recognized(self):
        for wording in ("SSL is required", "TLS required", "no encryption", "secure transport required"):
            connect = connecting(require=None, disable=Refused(wording))
            self.assertTrue(checks.dp005_database_requires_tls(connect, Refused)[0], wording)

    def test_the_control_failing_fails_the_case_and_no_plaintext_is_tried(self):
        # The server here would have accepted plaintext — `disable` opens — but
        # the runner cannot reach it. That is not the guarantee, and passing the
        # case on it would record the opposite of what is true.
        connect = connecting(require=Refused("connection timeout expired"), disable=None)
        passed, detail = checks.dp005_database_requires_tls(connect, Refused)
        self.assertFalse(passed)
        self.assertIn("control", detail)
        self.assertEqual(connect.modes, ["require"])

    def test_a_refusal_for_another_reason_fails(self):
        connect = connecting(require=None, disable=Refused("connection timeout expired"))
        passed, detail = checks.dp005_database_requires_tls(connect, Refused)
        self.assertFalse(passed)
        self.assertIn("timeout expired", detail)

    def test_a_client_side_fault_is_not_a_refusal(self):
        connect = connecting(require=None, disable=KeyError("MVP_RUNTIME_PASSWORD"))
        passed, detail = checks.dp005_database_requires_tls(connect, Refused)
        self.assertFalse(passed)
        self.assertIn("KeyError", detail)

    def test_an_accepted_plain_connection_fails(self):
        connect = connecting(require=None, disable=None)
        self.assertFalse(checks.dp005_database_requires_tls(connect, Refused)[0])


class TheMcpOrigins(unittest.TestCase):
    def fetch(self, plain, foreign):
        return answering({("POST", "/mcp"): lambda h, b: ((foreign if "Origin" in h else plain), {}, b"")})

    def test_served_without_origin_and_refused_with_a_foreign_one(self):
        self.assertTrue(checks.dp010(self.fetch(200, 403), "surface")[0])

    def test_a_served_foreign_origin_fails(self):
        self.assertFalse(checks.dp010(self.fetch(200, 200), "surface")[0])

    def test_a_refused_plain_call_fails(self):
        self.assertFalse(checks.dp010(self.fetch(403, 403), "surface")[0])


class TheRateLimitKey(unittest.TestCase):
    def fetch(self, keyed_by_forged_header):
        counts = {}

        def answer(headers, body):
            self.assertEqual(body, b"{}")  # malformed: no model is reached
            key = headers.get("X-Forwarded-For", "runner") if keyed_by_forged_header else "runner"
            counts[key] = counts.get(key, 0) + 1
            return (429 if counts[key] > checks.RATE_WINDOW_LIMIT else 400), {}, b""

        return answering({("POST", "/chat"): answer})

    def test_one_key_for_forged_and_plain_passes(self):
        fetch = self.fetch(keyed_by_forged_header=False)
        self.assertTrue(checks.dp009(fetch, "relay")[0])
        self.assertEqual(sum("X-Forwarded-For" in call[2] for call in fetch.calls), 4)

    def test_a_key_taken_from_the_forged_header_fails(self):
        self.assertFalse(checks.dp009(self.fetch(keyed_by_forged_header=True), "relay")[0])


class TheChatCall(unittest.TestCase):
    def fetch(self, document, status=200):
        def answer(headers, body):
            self.assertEqual(json.loads(body), {"messages": [{"role": "user", "content": checks.DP012_TEXT}]})
            return status, {}, json.dumps(document).encode()

        return answering({("POST", "/chat"): answer})

    def good(self, **overrides):
        document = {
            "content": [
                {"type": "text", "text": "..."},
                {"type": "mcp_tool_use", "name": "discover_entity", "id": "x", "input": {}},
                {"type": "mcp_tool_result", "tool_use_id": "x", "content": []},
            ],
            "scope_checks": [{}],
            "relay": {"model": checks.RELAY_MODEL},
        }
        document.update(overrides)
        return document

    def test_a_conforming_answer_passes(self):
        self.assertTrue(checks.dp012(self.fetch(self.good()), "relay")[0])

    def test_a_refusal_fails(self):
        self.assertFalse(checks.dp012(self.fetch({"error": "x"}, status=503), "relay")[0])

    def test_an_unregistered_block_type_fails(self):
        document = self.good(content=[{"type": "tool_use"}])
        self.assertFalse(checks.dp012(self.fetch(document), "relay")[0])

    def test_a_missing_scope_check_fails(self):
        self.assertFalse(checks.dp012(self.fetch(self.good(scope_checks=[])), "relay")[0])

    def test_another_model_fails(self):
        self.assertFalse(checks.dp012(self.fetch(self.good(relay={"model": "other"})), "relay")[0])


class TheOrder(unittest.TestCase):
    def test_the_model_call_comes_before_the_rate_limit_is_spent(self):
        order = []

        def fetch(method, url, headers=None, body=None):
            order.append((method, url))
            if url.endswith("/chat") and method == "POST" and body != b"{}":
                return 503, {}, b"{}"
            return 400, {}, b""

        waited = []
        connect = connecting(require=Refused("unreachable"), disable=Refused("unreachable"))
        checks.run(fetch, "surface", "relay", connect, Refused, pause=waited.append)
        chat = [i for i, (m, u) in enumerate(order) if m == "POST" and u.endswith("/chat")]
        self.assertEqual(len(chat), 1 + checks.RATE_WINDOW_LIMIT + 1)
        self.assertEqual(waited, [61])

    def test_the_surface_preflight_is_aimed_at_a_route_that_carries_cors(self):
        order = []

        def fetch(method, url, headers=None, body=None):
            order.append((method, url))
            return 400, {}, b""

        connect = connecting(require=Refused("unreachable"), disable=Refused("unreachable"))
        checks.run(fetch, "surface", "relay", connect, Refused, pause=lambda seconds: None)
        preflights = [url for method, url in order if method == "OPTIONS"]
        self.assertIn(f"https://surface{checks.SURFACE_CORS_PATH}", preflights)
        self.assertIn("https://surface/v1/ask", preflights)


class TheTransport(unittest.TestCase):
    """A request that produced no answer is a status, not an exception."""

    def fetch_through(self, error):
        class Opener:
            def open(self, request, timeout=None):
                raise error

        original = checks._OPENER
        checks._OPENER = Opener()
        try:
            return checks.fetch("GET", "https://host/")
        finally:
            checks._OPENER = original

    def test_no_answer_is_reported_as_unreachable_with_the_reason(self):
        for error in (
            urllib.error.URLError("connection refused"),
            TimeoutError("timed out"),
            ssl.SSLError("handshake failure"),
        ):
            status, headers, raw = self.fetch_through(error)
            self.assertEqual(status, checks.UNREACHABLE)
            self.assertEqual(headers, {})
            self.assertIn(type(error).__name__, raw.decode())

    def test_an_http_error_is_still_the_servers_answer(self):
        # `HTTPError` is an `OSError` too, so this is what fixes the order of
        # the two clauses: a 503 the server chose must not be recorded as a
        # request that never got there.
        error = urllib.error.HTTPError(
            "https://host/", 503, "Service Unavailable", {"Retry-After": "1"}, io.BytesIO(b"body")
        )
        status, headers, raw = self.fetch_through(error)
        self.assertEqual((status, raw), (503, b"body"))
        self.assertEqual(checks._header(headers, "retry-after"), "1")


class AFaultInOneCase(unittest.TestCase):
    """One case cannot cost the others their verdict, or the artifact its rows."""

    def unreachable(self):
        return connecting(require=Refused("unreachable"), disable=Refused("unreachable"))

    def test_a_case_that_raises_fails_and_the_rest_still_run(self):
        def fetch(method, url, headers=None, body=None):
            if url.endswith("/mcp"):
                raise RuntimeError("a defect in the check")
            return 400, {}, b""

        results = checks.run(
            fetch, "surface", "relay", self.unreachable(), Refused, pause=lambda seconds: None
        )
        self.assertFalse(results["DP-010"]["passed"])
        self.assertIn("RuntimeError", results["DP-010"]["detail"])
        self.assertIn("DP-009", results)

    def test_into_holds_the_verdicts_reached_before_a_run_that_stops(self):
        # Not a case failing -- the process being stopped. `main` writes the
        # artifact from this dictionary in a `finally`, so what it holds when
        # the run does not finish is what the deploy record gets.
        def fetch(method, url, headers=None, body=None):
            return 400, {}, b""

        def interrupted(seconds):
            raise KeyboardInterrupt

        recorded = {}
        with self.assertRaises(KeyboardInterrupt):
            checks.run(
                fetch,
                "surface",
                "relay",
                self.unreachable(),
                Refused,
                pause=interrupted,
                into=recorded,
            )
        self.assertIn("DP-012", recorded)
        self.assertNotIn("DP-009", recorded)


if __name__ == "__main__":
    unittest.main()
