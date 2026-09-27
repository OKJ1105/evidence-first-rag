"""`deploy-v0.1` Section 8.1: the deployed cases that are read over the network.

`DP-005`, `DP-009`, `DP-010` and `DP-012`, run by the deploy job against the
deployed `surface`, `relay` and database. Each case returns `(passed, detail)`
and never raises for a failed expectation, so one case cannot hide the next.

Every request goes through `fetch`, which takes a method, a URL, headers and a
body and returns `(status, headers, body)` without following redirects. The
job passes the real one; the tests pass a stand-in, so each expectation is
exercised without a network.

**`DP-012` costs one model call and is the only case here that does.**
`DP-009` sends requests that the relay refuses as malformed after counting
them, so it reaches no model.
"""

import argparse
import json
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


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


_OPENER = urllib.request.build_opener(_NoRedirect)


def fetch(method, url, headers=None, body=None, timeout=90):
    """One request, redirects not followed. Returns `(status, headers, bytes)`."""
    request = urllib.request.Request(url, data=body, headers=headers or {}, method=method)
    try:
        with _OPENER.open(request, timeout=timeout) as response:
            return response.status, dict(response.headers), response.read()
    except urllib.error.HTTPError as answered:
        return answered.code, dict(answered.headers), answered.read()


def _header(headers, name):
    for key, value in headers.items():
        if key.lower() == name.lower():
            return value
    return None


def _reason(error):
    """An exception as one line of detail: its type and its first line.

    The type alone does not tell a name that does not resolve from a firewall
    rule that has not propagated, and that is the distinction the reader of a
    failed database check needs.
    """
    first = (str(error).strip().splitlines() or [""])[0]
    return f"{type(error).__name__}: {first[:200]}" if first else type(error).__name__


def dp005_https(fetch, host):
    """Plain HTTP on the app's host is redirected to HTTPS."""
    status, headers, _ = fetch("GET", f"http://{host}/")
    location = _header(headers, "location") or ""
    if status in (301, 302, 307, 308) and location.startswith(f"https://{host}"):
        return True, f"{status} to {location}"
    return False, f"plain HTTP answered {status}, location {location!r}"


def dp005_foreign_origin(fetch, url):
    """A preflight from an origin other than the registered one is not allowed.

    Refused means the answer grants that origin nothing: no
    `Access-Control-Allow-Origin` naming it or `*`.
    """
    status, headers, _ = fetch(
        "OPTIONS",
        url,
        {"Origin": FOREIGN_ORIGIN, "Access-Control-Request-Method": "POST"},
    )
    allowed = _header(headers, "access-control-allow-origin")
    if allowed in (FOREIGN_ORIGIN, "*"):
        return False, f"{url} allowed {FOREIGN_ORIGIN} ({status})"
    return True, f"{url} answered {status} and allowed no foreign origin"


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
        if any(term in str(refused).lower() for term in TLS_REQUIRED_TERMS):
            return True, f"refused: {_reason(refused)}"
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
    plain_status, _, _ = fetch("POST", url, *_initialize())
    foreign_status, _, _ = fetch("POST", url, *_initialize(FOREIGN_ORIGIN))
    passed = plain_status == 200 and foreign_status >= 400
    return passed, f"no Origin: {plain_status}; foreign Origin: {foreign_status}"


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
        status, _, _ = fetch("POST", f"https://{relay_host}/chat", headers, b"{}")
        statuses.append(status)
    passed = statuses[:RATE_WINDOW_LIMIT] == [400] * RATE_WINDOW_LIMIT and statuses[-1] == 429
    return passed, f"statuses {statuses}"


def dp012(fetch, relay_host):
    """One deployed `POST /chat`, asserting what the relay controls."""
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
    if (document.get("relay") or {}).get("model") != RELAY_MODEL:
        problems.append(f"relay.model is {(document.get('relay') or {}).get('model')!r}")
    return (not problems), "; ".join(problems) or f"200 with {len(content)} blocks and {len(calls)} discover_entity calls"


def run(fetch, surface_host, relay_host, connect, operational_error, pause=time.sleep):
    """Every case, in an order where none spends another's budget.

    `DP-012` goes first and `DP-009` last, after a full window, so the one
    model call is not refused by the rate limit `DP-009` then exhausts.
    """
    results = {
        "DP-005 surface redirect": dp005_https(fetch, surface_host),
        "DP-005 relay redirect": dp005_https(fetch, relay_host),
        "DP-005 surface foreign origin": dp005_foreign_origin(fetch, f"https://{surface_host}/v1/ask"),
        "DP-005 relay foreign origin": dp005_foreign_origin(fetch, f"https://{relay_host}/chat"),
        "DP-005 database TLS": dp005_database_requires_tls(connect, operational_error),
        "DP-010": dp010(fetch, surface_host),
        "DP-012": dp012(fetch, relay_host),
    }
    pause(61)
    results["DP-009"] = dp009(fetch, relay_host)
    return {case: {"passed": passed, "detail": detail} for case, (passed, detail) in results.items()}


def main(argv=None) -> int:
    import os

    import psycopg

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--surface", required=True)
    parser.add_argument("--relay", required=True)
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

    results = run(fetch, arguments.surface, arguments.relay, connect, psycopg.OperationalError)
    with open(arguments.out, "w", encoding="utf-8") as handle:
        json.dump(results, handle, indent=2)
    for case, result in results.items():
        print(("ok  " if result["passed"] else "FAIL"), case, "-", result["detail"])
    return 0 if all(result["passed"] for result in results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
