"""`deploy-v0.1` Section 8.1: the deployed cases that are read over the network.

`DP-005`, `DP-009`, `DP-010`, `DP-012` and `DP-019`, run by the deploy job against the
deployed `surface`, `relay` and database. Each case returns `(passed, detail)`
and never raises for a failed expectation, so one case cannot hide the next.

Every request goes through `fetch`, which takes a method, a URL, headers and a
body and returns `(status, headers, body)` without following redirects. The
job passes the real one; the tests pass a stand-in, so each expectation is
exercised without a network.

**Nothing here raises its way out of the run.** A connection that produced no
answer comes back as `UNREACHABLE` with the reason as the body, a case that
raises anyway is recorded as that case failing, and `main` writes the artifact
in a `finally`. `deploy-v0.1` Section 4.8 requires a failure to be recorded,
and a case that aborted the step would leave every later case with no verdict
at all -- which is not the same thing as a failure, and reads as neither.

**`DP-012` costs one model call and is the only case here that does.**
`DP-009` sends requests that the relay refuses as malformed after counting
them, so it reaches no model.
"""

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request

FOREIGN_ORIGIN = "https://foreign.invalid"
FORGED_ADDRESS = "203.0.113.7"
RATE_WINDOW_LIMIT = 6
DP012_TEXT = "What is SAMPLE_ALIAS_GEARBOX_STATE?"
RELAY_BLOCK_TYPES = {"text", "mcp_tool_use", "mcp_tool_result"}
RELAY_MODEL = "claude-haiku-4-5"

# What a refusal for want of TLS says. The server's exact wording is the
# platform's to choose, so the terms are matched rather than the sentence: a
# refusal that names none of them is some other refusal and fails the case.
TLS_REQUIRED_TERMS = ("ssl", "tls", "encryption", "secure transport")

# The status `fetch` reports for a request that produced no answer at all. Not
# an HTTP code, so no case can read it as one: every expectation below wants a
# particular status, and this is none of them.
UNREACHABLE = 0

# `api-v0.1` Section 4.5 and `relay-v0.1` Section 4.6: the refusal both apps
# answer an `OPTIONS` with, in a JSON body. Positive evidence that the app
# itself answered, which the platform's own error page for a container that has
# not finished starting is not.
METHOD_NOT_ALLOWED = 405
METHOD_NOT_ALLOWED_REFUSAL = "method_not_allowed"

# `api-v0.1` Section 4.5 puts CORS on `/v1/select`, `/v1/query` and
# `/v1/discover`, and explicitly not on `/v1/ask`. The surface preflight is
# aimed at one of the three, so a grant widened to a foreign origin on the
# routes that implement CORS fails the case. `/v1/ask` is probed too, but it
# cannot be the only probe: no grant can be carried there whatever the
# deployment is configured with, so on its own it asserts nothing.
SURFACE_CORS_PATH = "/v1/query"


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


_OPENER = urllib.request.build_opener(_NoRedirect)


def fetch(method, url, headers=None, body=None, timeout=90):
    """One request, redirects not followed. Returns `(status, headers, bytes)`.

    An `HTTPError` is an answer -- the server chose that code -- so it is
    returned like any other. A request that produced *no* answer returns
    `UNREACHABLE` with the reason as the body instead of raising: `urllib`
    raises `URLError`, `TimeoutError` or `ssl.SSLError` for a refused socket, a
    handshake that failed, a name that does not resolve, and a `timeout` a
    cold-starting container outlasts, and every one of those would otherwise
    leave the run at whichever case happened to hit it first, costing the rest
    of the cases their verdict. `OSError` is the one base all of them share --
    and it is the base of `HTTPError` as well, so that clause comes first.
    """
    request = urllib.request.Request(url, data=body, headers=headers or {}, method=method)
    try:
        with _OPENER.open(request, timeout=timeout) as response:
            return response.status, dict(response.headers), response.read()
    except urllib.error.HTTPError as answered:
        return answered.code, dict(answered.headers), answered.read()
    except OSError as unanswered:
        return UNREACHABLE, {}, _reason(unanswered).encode()


def _header(headers, name):
    for key, value in headers.items():
        if key.lower() == name.lower():
            return value
    return None


# Host names and addresses never reach a recorded detail: the record is
# committed, and the database's host is not public (#239 B4).
_HOSTNAME = re.compile(r"\b[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)+\.[a-z]{2,}\b", re.IGNORECASE)
_ADDRESS = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b|\b[0-9a-f]{0,4}(?::[0-9a-f]{0,4}){2,7}\b", re.IGNORECASE)


def redact(text):
    """`text` with every host name and IP address replaced by a placeholder."""
    return _ADDRESS.sub("<address>", _HOSTNAME.sub("<host>", text))


def _reason(error):
    """An exception as one line of detail: its type and its first line.

    The type alone does not tell a name that does not resolve from a firewall
    rule that has not propagated, and that is the distinction the reader of a
    failed database check needs.
    """
    first = redact((str(error).strip().splitlines() or [""])[0])
    return f"{type(error).__name__}: {first[:200]}" if first else type(error).__name__


def _refusal(raw):
    """The `refusal` kind of a JSON refusal body, or `None` if it is not one."""
    try:
        document = json.loads(raw)
    except ValueError:
        return None
    return document.get("refusal") if isinstance(document, dict) else None


def _answer(status, raw):
    """A status for a detail line, carrying the reason when there was no answer.

    For a case that does not otherwise read the body, `UNREACHABLE` on its own
    would not tell a name that does not resolve from a socket that timed out.
    """
    if status != UNREACHABLE:
        return str(status)
    return f"{UNREACHABLE} ({redact(raw.decode(errors='replace'))[:200]})"


def dp005_https(fetch, host):
    """Plain HTTP on the app's host is redirected to HTTPS."""
    status, headers, raw = fetch("GET", f"http://{host}/")
    location = _header(headers, "location") or ""
    if status in (301, 302, 307, 308) and location.startswith(f"https://{host}"):
        return True, f"{status} to {location}"
    return False, f"plain HTTP answered {_answer(status, raw)}, location {location!r}"


def dp005_foreign_origin(fetch, url):
    """A preflight from an origin other than the registered one is not allowed.

    Two things have to hold, and the second is why a missing
    `Access-Control-Allow-Origin` is not enough by itself. The answer must
    grant that origin nothing -- no header naming it or `*` -- **and** it must
    be the app's own answer: the 405 `method_not_allowed` refusal both apps give
    an `OPTIONS`, or, where a preflight is admitted at all, a 204 whose grant
    names some other origin.

    Anything else fails the case. The platform's 502 or 503 for a container that
    has not finished starting carries no `Access-Control-Allow-Origin` either,
    and so does a host that answered nothing; reading that silence as a refusal
    would record the Section 4.5 guarantee for a process that never ran. Only
    the app's own vocabulary tells a refusal from an absence.
    """
    status, headers, raw = fetch(
        "OPTIONS",
        url,
        {"Origin": FOREIGN_ORIGIN, "Access-Control-Request-Method": "POST"},
    )
    allowed = _header(headers, "access-control-allow-origin")
    if allowed in (FOREIGN_ORIGIN, "*"):
        return False, f"{url} allowed {FOREIGN_ORIGIN} ({status})"
    if status == METHOD_NOT_ALLOWED and _refusal(raw) == METHOD_NOT_ALLOWED_REFUSAL:
        return True, f"{url} refused the preflight as {METHOD_NOT_ALLOWED_REFUSAL}"
    if status == 204 and allowed:
        return True, f"{url} admitted the preflight for {allowed!r}, not {FOREIGN_ORIGIN}"
    return False, (
        f"{url} answered {status}, which is neither the app's own refusal nor a"
        f" grant to another origin: {raw[:200]!r}"
    )


def dp005_database_requires_tls(connect, operational_error):
    """A connection with TLS disabled is refused by the server, for that reason.

    A control connection with `sslmode=require` runs first, the same discipline
    `deployed.refused_writes` uses: it establishes that the host resolves, the
    firewall rule is in place, and the database name and credential are good,
    so that the plaintext attempt failing is attributable to the missing TLS
    rather than to a connection that could never have been made. Without the
    control, an unpropagated firewall rule or an exceeded `connect_timeout`
    reads as the server refusing plaintext when it would have accepted it.

    `operational_error` is `psycopg.OperationalError`: the server answering and
    refusing. A failure of any other type is a fault in the check itself, not
    the guarantee, and fails the case. So does a refusal whose message does not
    name the requirement, since only that names TLS as the reason.
    """
    try:
        with connect(sslmode="require") as connection, connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception as unreachable:  # noqa: BLE001 - the control failing fails the case
        return False, f"the TLS control connection failed: {_reason(unreachable)}"

    try:
        with connect(sslmode="disable"):
            pass
    except operational_error as refused:
        matched = [term for term in TLS_REQUIRED_TERMS if term in str(refused).lower()]
        if matched:
            # A fixed sentence: the driver's message names the server.
            return True, f"refused for want of TLS (matched {matched[0]!r})"
        return False, f"refused, but not for want of TLS: {_reason(refused)}"
    except Exception as other:  # noqa: BLE001 - not the server refusing
        return False, f"the plaintext attempt failed before any refusal: {_reason(other)}"
    return False, "the server accepted a connection without TLS"


def _initialize(origin=None):
    headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
    if origin:
        headers["Origin"] = origin
    body = json.dumps({
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "dp-010", "version": "0"}},
    }).encode()
    return headers, body


def dp010(fetch, surface_host):
    """`/mcp` serves a call with no `Origin` and refuses a foreign one."""
    url = f"https://{surface_host}/mcp"
    plain_status, _, plain_raw = fetch("POST", url, *_initialize())
    foreign_status, _, foreign_raw = fetch("POST", url, *_initialize(FOREIGN_ORIGIN))
    passed = plain_status == 200 and foreign_status >= 400
    return passed, (
        f"no Origin: {_answer(plain_status, plain_raw)};"
        f" foreign Origin: {_answer(foreign_status, foreign_raw)}"
    )


def dp009(fetch, relay_host):
    """A forged forwarded-for header does not buy a separate rate-limit key.

    Seven malformed requests inside one window, alternating a forged header
    and none. Malformed requests are counted before they are refused, and no
    model is called. If the forged entry were the key, neither key would reach
    seven; if the platform's appended entry is the key, the seventh is refused.
    """
    statuses = []
    for index in range(RATE_WINDOW_LIMIT + 1):
        headers = {"Content-Type": "application/json"}
        if index % 2 == 0:
            headers["X-Forwarded-For"] = FORGED_ADDRESS
        # Short, so seven requests stay inside the 60-second window (#239 N9).
        status, _, _ = fetch("POST", f"https://{relay_host}/chat", headers, b"{}", timeout=5)
        statuses.append(status)
    passed = statuses[:RATE_WINDOW_LIMIT] == [400] * RATE_WINDOW_LIMIT and statuses[-1] == 429
    return passed, f"statuses {statuses}"


def dp012(fetch, relay_host):
    """One deployed `POST /chat`: what the relay controls, and one term it does not.

    HTTP 200, the Section 4.3 block types, `scope_checks` and `relay.model` are
    the relay's own. Since `deploy-v0.1` `0.6.2` the case also requires at least
    one `discover_entity` call answered by a tool result that is not a refusal
    (#286) -- and whether the model calls the tool is not in this repository's
    control, so this one case carries a term the relay does not decide. The
    model's words are asserted no more than before.
    """
    body = json.dumps({"messages": [{"role": "user", "content": DP012_TEXT}]}).encode()
    status, _, raw = fetch("POST", f"https://{relay_host}/chat", {"Content-Type": "application/json"}, body)
    if status != 200:
        return False, f"answered {status}: {raw[:200]!r}"
    try:
        document = json.loads(raw)
    except ValueError:
        return False, "the answer is not JSON"
    content = document.get("content")
    problems = []
    if not content:
        problems.append("no content was passed through")
    if not isinstance(content, list) or not all(
        isinstance(block, dict) and block.get("type") in RELAY_BLOCK_TYPES for block in content
    ):
        problems.append("a content block outside Section 4.3's types")
    calls = [
        block for block in content or []
        if isinstance(block, dict) and block.get("type") == "mcp_tool_use" and block.get("name") == "discover_entity"
    ]
    checks = document.get("scope_checks")
    if not isinstance(checks, list) or len(checks) != len(calls):
        problems.append(f"{len(calls)} discover_entity calls but scope_checks {checks!r}")
    # #286: the deployed relay-to-`/mcp` round trip is what the chat page
    # depends on, so a run in which the model called no tool, or no call came
    # back as a tool result that is not a refusal, asserts nothing about it.
    results = [
        block for block in content or []
        if isinstance(block, dict) and block.get("type") == "mcp_tool_result"
        and not (block.get("is_error") or block.get("isError"))
    ]
    if not calls:
        problems.append("no discover_entity call, so the deployed tool round trip was not exercised")
    elif not results:
        problems.append("no tool result that is not a refusal")
    if (document.get("relay") or {}).get("model") != RELAY_MODEL:
        problems.append(f"relay.model is {(document.get('relay') or {}).get('model')!r}")
    # Block types only, never a block's text or input: they say which way the
    # answer went without carrying the model's words or a person's (#286).
    shape = [block.get("type") for block in content or [] if isinstance(block, dict)]
    if problems:
        return False, "; ".join(problems) + f"; block types {shape}"
    return True, (
        f"200 with {len(content)} blocks and {len(calls)} discover_entity calls,"
        f" {len(results)} answered; block types {shape}"
    )


# `api-v0.1` Section 4.5 and `relay-v0.1` Section 4.1: the four headers an
# admitted preflight carries, beside `Access-Control-Allow-Origin`.
ADMITTED_PREFLIGHT_HEADERS = {
    "access-control-allow-methods": "POST",
    "access-control-allow-headers": "content-type",
    "vary": "Origin",
}


def dp019_registered_origin(fetch, url, origin):
    """A preflight from the registered origin is admitted (`deploy-v0.1` `0.6.3`).

    `DP-005` shows that a foreign origin is refused, which a deployment that
    admits no origin at all also passes. This is the other half: the origin
    Section 4.6 records gets HTTP 204 and the grant naming it exactly, with the
    other three headers. The origin itself stays out of the detail, as every
    host name does.
    """
    status, headers, raw = fetch(
        "OPTIONS",
        url,
        {"Origin": origin, "Access-Control-Request-Method": "POST"},
    )
    allowed = _header(headers, "access-control-allow-origin")
    if status != 204:
        return False, f"{url} answered the registered origin's preflight with {_answer(status, raw)}"
    if allowed != origin:
        return False, f"{url} admitted the preflight but granted {'another origin' if allowed else 'no origin'}"
    wrong = [
        name for name, value in ADMITTED_PREFLIGHT_HEADERS.items() if _header(headers, name) != value
    ]
    if wrong:
        return False, f"{url} admitted the preflight without the registered {', '.join(wrong)}"
    return True, f"{url} admitted the registered origin's preflight with the four headers"


def _guarded(case, *arguments):
    """One case, with an exception it did not expect recorded as it failing.

    Every expectation above fails without raising, so reaching this is a fault
    in the check rather than an unmet guarantee -- but a fault in one case must
    not cost the other cases their verdict.
    """
    try:
        return case(*arguments)
    except Exception as fault:  # noqa: BLE001 - one case's fault is one case's failure
        return False, f"the check itself raised: {_reason(fault)}"


def run(fetch, surface_host, relay_host, connect, operational_error, pause=time.sleep, into=None, origin=None):
    """Every case, in an order where none spends another's budget.

    `DP-012` goes first and `DP-009` last, after a full window, so the one
    model call is not refused by the rate limit `DP-009` then exhausts.

    `into`, when given, is the dictionary the verdicts are written to, filled
    case by case as they are reached. That is what lets `main` record a partial
    result set: something that stops the run outright -- not a case failing, but
    the process being interrupted -- still leaves every verdict reached before
    it where the artifact is written from.
    """
    results = {} if into is None else into

    def record(case, passed, detail):
        results[case] = {"passed": passed, "detail": detail}

    record("DP-005 surface redirect", *_guarded(dp005_https, fetch, surface_host))
    record("DP-005 relay redirect", *_guarded(dp005_https, fetch, relay_host))
    record(
        f"DP-005 surface foreign origin on {SURFACE_CORS_PATH}",
        *_guarded(dp005_foreign_origin, fetch, f"https://{surface_host}{SURFACE_CORS_PATH}"),
    )
    record(
        "DP-005 surface foreign origin on /v1/ask",
        *_guarded(dp005_foreign_origin, fetch, f"https://{surface_host}/v1/ask"),
    )
    record(
        "DP-005 relay foreign origin",
        *_guarded(dp005_foreign_origin, fetch, f"https://{relay_host}/chat"),
    )
    if origin:
        record(
            f"DP-019 surface registered origin on {SURFACE_CORS_PATH}",
            *_guarded(dp019_registered_origin, fetch, f"https://{surface_host}{SURFACE_CORS_PATH}", origin),
        )
        record(
            "DP-019 relay registered origin",
            *_guarded(dp019_registered_origin, fetch, f"https://{relay_host}/chat", origin),
        )
    else:
        record("DP-019", False, "no registered origin was passed to the check")
    record("DP-005 database TLS", *_guarded(dp005_database_requires_tls, connect, operational_error))
    record("DP-010", *_guarded(dp010, fetch, surface_host))
    record("DP-012", *_guarded(dp012, fetch, relay_host))
    pause(61)
    record("DP-009", *_guarded(dp009, fetch, relay_host))
    return results


def main(argv=None) -> int:
    import os

    import psycopg

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--surface", required=True)
    parser.add_argument("--relay", required=True)
    parser.add_argument("--origin", required=True, help="the registered origin, deploy-v0.1 Section 4.6")
    parser.add_argument("--out", default="http-checks.json")
    arguments = parser.parse_args(argv)

    # Read before any case runs, so a step that stopped exporting a variable
    # raises here instead of arriving inside a case as a caught exception.
    parameters = {
        "dbname": os.environ.get("MVP_DATABASE", "mvp"),
        "user": "mvp_runtime",
        "password": os.environ["MVP_RUNTIME_PASSWORD"],
        "host": os.environ["PGHOST"],
        "port": os.environ.get("PGPORT", "5432"),
        "connect_timeout": 15,
    }

    def connect(**extra):
        return psycopg.connect(**parameters, **extra)

    # In a `finally`, because the artifact is the deploy record's evidence for
    # these cases (Section 8.2) and a run that stopped partway has more to
    # record than nothing: what it did establish, and which cases never ran.
    results = {}
    try:
        run(
            fetch,
            arguments.surface,
            arguments.relay,
            connect,
            psycopg.OperationalError,
            into=results,
            origin=arguments.origin,
        )
    finally:
        with open(arguments.out, "w", encoding="utf-8") as handle:
            json.dump(results, handle, indent=2)

    for case, result in results.items():
        print(("ok  " if result["passed"] else "FAIL"), case, "-", result["detail"])
    return 0 if all(result["passed"] for result in results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
