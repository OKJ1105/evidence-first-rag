"""`deploy-v0.1` Section 8.1: `DP-008`, a person's words reach no log line; `DP-020`, nor a client's address.

One request to each deployed app carries a fresh `SAMPLE_*` marker where a
person's words go:

- to `surface`, as the term of a `POST /v1/discover`;
- to `relay`, inside a person's turn of a `POST /chat` that is refused as
  malformed before any model call, so the case costs nothing.

Each request carries the marker twice: in the body, where a person's words go,
and in the URL's query string, which neither route reads. Section 4.7's "a
person's words may not" be logged binds every line in the platform's log
store, a request's URL included (#279), so a store that records request
targets -- uvicorn's access line, the platform's HTTP log -- fails the case
rather than passing it unexamined.

Both requests have to be answered by the app itself, in the app's own
vocabulary, before the log store is read at all: a request that reached no
application code carries the marker nowhere, and the store's silence about it
would be nothing to record (#255 B1).

The platform's log store is then read through `az webapp log download`, for
both apps, until each app's **own** record of a request to that route is in
the download. That positive control shows the store is capturing the stream
Section 4.7 constrains -- the container's standard output, the one place a
request body could ever appear -- so an empty or unwired log store cannot pass
vacuously. The route string alone would not show that: the platform's own HTTP
log may record the request line for both apps, and a download carrying only that
log would meet a looser control while holding no line that could carry a body
(#255 B2). Whether that log can be turned off without also stopping the
container's standard-output capture is unverified, so `infra/main.bicep` leaves
it as it was, and this case measures it: the marker in the URL fails the case
if any downloaded file records it (#279). The control does not rest on the log
being on or off: each app's control names the shape of its own record. It does not
tie the line to this request: earlier checks call the same routes, so a lagging
store may show theirs first. The marker is fresh per run, so what it can miss
is only a line not yet flushed. So the store is read at least `MINIMUM_READS`
times, over about two minutes, before a pass is concluded, even when the
control is already met by an earlier line. The case passes when both apps'
own records are present and the marker appears in no file of either download.
A finding names the file the marker was in, never the line, and every outcome
-- a pass included -- records the file names the last download held, so what
the store carried on a run is readable off the committed record rather than
reconstructed from the sentence (#279 B2).

Each read is bounded. A log store that never shows the app's own record of the
request fails the case, and the case does not wait forever.
"""

import argparse
import io
import json
import os
import secrets
import subprocess
import sys
import tempfile
import time
import zipfile

# The sibling module's readers, used rather than copied so that a status and a
# JSON refusal body are read the same way in both.
from .http_checks import _answer as answer_detail
from .http_checks import _refusal as refusal_kind
from .http_checks import fetch as network_fetch

MARKER_PREFIX = "SAMPLE_DP008_"
DISCOVER_PATH = "/v1/discover"
CHAT_PATH = "/chat"
# The query parameter that carries the marker in each URL. Neither route reads
# a query string, so its presence changes no answer.
MARKER_QUERY = "q"
ATTEMPTS = 10
MINIMUM_READS = 4
PAUSE_SECONDS = 30
# `DP-009` fills the relay's per-address window just before this case runs.
RATE_WINDOW_SECONDS = 61

# What each app's own answer to its marked request is. `api-v0.1` Section 4.2
# answers `POST /v1/discover` with the envelope carrying this contract
# identifier; `relay-v0.1` Section 4.2 refuses a conversation ending with the
# relay's turn as `malformed_request`, which its Section 4.6 fixes to 400.
SURFACE_CONTRACT = "api-v0.1"
RELAY_REFUSAL = "malformed_request"
RELAY_REFUSAL_STATUS = 400

# Each app's own record of a request to its route: the terms that have to be in
# one line of one file of the download. Not the bare route string, which the
# platform's HTTP log may carry for both apps (#279).
#
# `relay` writes the Section 4.10 record of `relay/app.py:log_line` -- one JSON
# line per request, so `"path"`, the route and `"http_status"` are in it, and in
# no line of the platform's HTTP log. The terms are matched rather than the
# serialized line, so the separators `log_line` writes with are not part of this.
#
# `surface` writes the same shape since #259: `api/request_log.py:log_line`,
# one JSON line per request with `"path"`, the route and `"http_status"`. So
# both controls name the app's own Section 4.7 record, and neither is met by
# uvicorn's access line or the platform's HTTP log.
SURFACE_RECORD = ('"path"', f'"{DISCOVER_PATH}"', '"http_status"')
RELAY_RECORD = ('"path"', f'"{CHAT_PATH}"', '"http_status"')


def fresh_marker() -> str:
    return MARKER_PREFIX + secrets.token_hex(8).upper()


def send(fetch, surface_host, relay_host, marker, pause):
    """The two marked requests, each as `(status, body)`."""
    discover = json.dumps({"arguments": {"entity_kind": "signal", "term": marker}}).encode()
    surface_status, _, surface_raw = fetch(
        "POST", f"https://{surface_host}{DISCOVER_PATH}?{MARKER_QUERY}={marker}",
        {"Content-Type": "application/json"}, discover,
    )
    pause(RATE_WINDOW_SECONDS)
    # Ends with the relay's turn, so Section 4.2 refuses it before any model call.
    chat = json.dumps({
        "messages": [
            {"role": "user", "content": f"What is {marker}?"},
            {"role": "assistant", "content": [{"type": "text", "text": "SAMPLE_REPLY"}]},
        ]
    }).encode()
    relay_status, _, relay_raw = fetch(
        "POST", f"https://{relay_host}{CHAT_PATH}?{MARKER_QUERY}={marker}",
        {"Content-Type": "application/json"}, chat,
    )
    return (surface_status, surface_raw), (relay_status, relay_raw)


def _envelope(raw) -> bool:
    """Whether `raw` is the `api-v0.1` Section 4.2 envelope, which only the
    surface's own route answers with."""
    try:
        document = json.loads(raw)
    except ValueError:
        return False
    contract = document.get("contract") if isinstance(document, dict) else None
    return isinstance(contract, dict) and contract.get("identifier") == SURFACE_CONTRACT


def answered(surface, relay):
    """Whether both marked requests were answered by the apps themselves.

    Not a formality. The marker reaches an app's code only when the app
    answers, and only the app's own vocabulary tells that from an absence:
    `fetch` reports a request that produced no answer as `UNREACHABLE`, the
    platform answers 502 or 503 for a container that has not finished starting,
    and the relay refuses a request over its rate-limit window with 429 in
    `Caps.admit_request` -- before `bounded_body` is read, so the marker is
    never parsed. In each of those the marker never reached the app, while the
    positive control below is still met by other lines: `DP-009`'s seven
    requests each leave the relay's own record, and the surface's store holds
    seven days of `/v1/discover` lines. A case that did not check this would
    record the Section 4.7 guarantee for a request that ran no application
    code (#255 B1).

    No response body reaches the detail. The surface's own answer renders the
    marked term back (Section 4.2) and this detail is committed, so
    `answer_detail` carries the status alone -- or, where there was no answer at
    all, the redacted reason, which is what tells a timed-out socket from a
    name that does not resolve.
    """
    surface_status, surface_raw = surface
    relay_status, relay_raw = relay
    problems = []
    if surface_status != 200 or not _envelope(surface_raw):
        problems.append(
            f"the surface answered {answer_detail(surface_status, surface_raw)},"
            f" not a 200 carrying its own {SURFACE_CONTRACT} envelope"
        )
    if relay_status != RELAY_REFUSAL_STATUS or refusal_kind(relay_raw) != RELAY_REFUSAL:
        problems.append(
            f"the relay answered {answer_detail(relay_status, relay_raw)},"
            f" not its own {RELAY_REFUSAL_STATUS} {RELAY_REFUSAL} refusal"
        )
    return (not problems), "; ".join(problems)


def read_zip(data: bytes):
    """Every file of a log download, as (name, text)."""
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            yield info.filename, archive.read(info).decode("utf-8", errors="replace")


def inspect(files, marker, record):
    """(files the marker is in, whether the app's own record of the request is
    in one of them).

    The marker is looked for in every file, including the platform's own logs.
    The control wants every term of `record` in **one line**: a term in one file
    and another term in another file is not a record of a request.
    """
    marked, seen = [], False
    for name, text in files:
        if marker in text:
            marked.append(name)
        if not seen:
            seen = any(all(term in line for term in record) for line in text.splitlines())
    return marked, seen


def dp008(fetch, download, surface_host, relay_host, surface, relay, marker=None, pause=time.sleep):
    """`download(app)` returns that app's log download as zip bytes."""
    marker = marker or fresh_marker()
    surface_answer, relay_answer = send(fetch, surface_host, relay_host, marker, pause)
    reached, problem = answered(surface_answer, relay_answer)
    if not reached:
        # No log store is read: there is nothing this run put in one.
        return False, f"the marked request reached no application code, so nothing was read: {problem}"
    statuses = f"request statuses {surface_answer[0]} and {relay_answer[0]}"
    marked, seen = {}, {surface: False, relay: False}
    records = {surface: SURFACE_RECORD, relay: RELAY_RECORD}
    # The last download's file names, so the record says what the store did
    # hold, met or not (#256 N6, #279 B2). Names only, never a line.
    names = {surface: [], relay: []}
    for attempt in range(ATTEMPTS):
        for app in (surface, relay):
            files = list(read_zip(download(app)))
            names[app] = sorted(name for name, _ in files)
            found, logged = inspect(files, marker, records[app])
            if found:
                marked[app] = sorted(set(marked.get(app, [])) | set(found))
            seen[app] = seen[app] or logged
        if marked or (attempt + 1 >= MINIMUM_READS and all(seen.values())):
            break
        # No pause after the last read: the outcome is decided (#256 N3).
        if attempt + 1 < ATTEMPTS:
            pause(PAUSE_SECONDS)
    if marked:
        return False, f"the marker is in {marked}; {statuses}"
    if not all(seen.values()):
        missing = sorted(app for app, logged in seen.items() if not logged)
        return False, (
            f"no file downloaded for {missing} holds that app's own record of a request to its"
            f" route, so the stream Section 4.7 constrains was not inspected; {statuses};"
            f" files downloaded: { {app: names[app] for app in missing} }"
        )
    # The control may have been met by an earlier request's line, so the
    # evidence says so rather than claiming more (#256 N7). The file names are
    # recorded on a pass as well, so a committed record says which files the
    # store held and a later run that holds fewer is readable against it
    # (#279 B2) -- which is what a change to the platform's logging switches
    # would show up as. Names only, never a line.
    return True, (
        f"the marker is in no log file of either app; {statuses}; the control was met by a line"
        f" of each app's own shape, which may be an earlier request's; files downloaded: {names}"
    )


# The management site's own request traces. The deploy job's `az webapp log
# download` is itself a request to that site, so its traces may carry the
# runner's address; no visitor reaches it, and `DP-020` reports those files
# apart rather than reading them as a visitor's request (`0.7.0`).
MANAGEMENT_TRACES = "/kudu/"


def dp020(download, surface, relay, address):
    """`deploy-v0.1` `0.7.0`: the runner's own address is in no log file.

    Every earlier case in the run sent its requests to both apps from this
    runner, so its address is what a store recording client addresses would
    hold. One download per app, read after `DP-008` has seen each app's own
    records. A finding names files only, and never the address: the record is
    committed, and the job masks the address in its own output.
    """
    if not address:
        return False, "no runner address was given, so nothing was looked for"
    found, traces, http = {}, {}, {}
    for app in (surface, relay):
        for name, text in read_zip(download(app)):
            if "/http/" in name or name.startswith("http/"):
                http.setdefault(app, []).append(name)
            if address not in text:
                continue
            bucket = traces if MANAGEMENT_TRACES in f"/{name}" else found
            bucket.setdefault(app, []).append(name)
    counts = {app: len(names) for app, names in traces.items()}
    tail = (
        f"management-site trace files holding it: {counts or 'none'};"
        f" HTTP log files in the download: {http or 'none'}"
    )
    if found:
        return False, f"the runner's address is in {found}; {tail}"
    return True, f"the runner's address is in no log file of either app outside the management site; {tail}"


def az_download(group):
    """The real reader: one `az webapp log download` per app, as bytes."""

    def download(app):
        with tempfile.TemporaryDirectory() as directory:
            target = f"{directory}/logs.zip"
            subprocess.run(
                ["az", "webapp", "log", "download", "--resource-group", group, "--name", app, "--log-file", target],
                check=True, capture_output=True, timeout=180,
            )
            with open(target, "rb") as handle:
                return handle.read()

    return download


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    for name in ("group", "surface", "relay", "surface-host", "relay-host"):
        parser.add_argument(f"--{name}", required=True)
    parser.add_argument("--out", default="log-checks.json")
    arguments = parser.parse_args(argv)
    try:
        passed, detail = dp008(
            network_fetch, az_download(arguments.group),
            arguments.surface_host, arguments.relay_host, arguments.surface, arguments.relay,
        )
    except Exception as error:  # noqa: BLE001 - an unfinished case is a failed case, recorded
        passed, detail = False, f"the check itself failed: {type(error).__name__}"
    result = {"DP-008": {"passed": passed, "detail": detail}}
    # Read from the environment, never the command line, so it is in no
    # process listing; the job masks it in its log.
    try:
        found, where = dp020(
            az_download(arguments.group), arguments.surface, arguments.relay,
            os.environ.get("RUNNER_ADDRESS", "").strip(),
        )
    except Exception as error:  # noqa: BLE001 - recorded, as for DP-008
        found, where = False, f"the check itself failed: {type(error).__name__}"
    result["DP-020"] = {"passed": found, "detail": where}
    with open(arguments.out, "w", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2)
    for case, outcome in result.items():
        print(("ok  " if outcome["passed"] else "FAIL"), case, "-", outcome["detail"])
    return 0 if all(outcome["passed"] for outcome in result.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
