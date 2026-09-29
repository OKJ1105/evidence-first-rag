"""`deploy-v0.1` Section 8.1: `DP-008`, a person's words reach no log line.

One request to each deployed app carries a fresh `SAMPLE_*` marker where a
person's words go:

- to `surface`, as the term of a `POST /v1/discover`;
- to `relay`, inside a person's turn of a `POST /chat` that is refused as
  malformed before any model call, so the case costs nothing.

Both routes take the marker in the body, never in the URL. The platform's HTTP
log records query strings, and Section 4.7 forbids request bodies in logs, not
URLs.

The platform's log store is then read through `az webapp log download`, for
both apps, until each app's log shows a request to that route. That positive
control shows the store is capturing each app's requests, so an empty or
unwired log store cannot pass vacuously. It does not tie the line to this
request: earlier checks call the same routes, so a lagging store may show
theirs first. The marker is fresh per run, so what it can miss is only a line
not yet flushed. So the store is read at least `MINIMUM_READS` times, over
about two minutes, before a pass is concluded, even when the control is
already met by an earlier line. The
case passes when both apps show the path and the marker appears in no file of
either download. A finding names the file the marker was in, never the line.

Each read is bounded. A log store that never shows the request fails the case,
and the case does not wait forever.
"""

import argparse
import io
import json
import secrets
import subprocess
import sys
import tempfile
import time
import zipfile

from .http_checks import fetch as network_fetch

MARKER_PREFIX = "SAMPLE_DP008_"
DISCOVER_PATH = "/v1/discover"
CHAT_PATH = "/chat"
ATTEMPTS = 10
MINIMUM_READS = 4
PAUSE_SECONDS = 30
# `DP-009` fills the relay's per-address window just before this case runs.
RATE_WINDOW_SECONDS = 61


def fresh_marker() -> str:
    return MARKER_PREFIX + secrets.token_hex(8).upper()


def send(fetch, surface_host, relay_host, marker, pause):
    """The two marked requests. Returns their statuses."""
    discover = json.dumps({"arguments": {"entity_kind": "signal", "term": marker}}).encode()
    surface_status, _, _ = fetch(
        "POST", f"https://{surface_host}{DISCOVER_PATH}", {"Content-Type": "application/json"}, discover
    )
    pause(RATE_WINDOW_SECONDS)
    # Ends with the relay's turn, so Section 4.2 refuses it before any model call.
    chat = json.dumps({
        "messages": [
            {"role": "user", "content": f"What is {marker}?"},
            {"role": "assistant", "content": [{"type": "text", "text": "SAMPLE_REPLY"}]},
        ]
    }).encode()
    relay_status, _, _ = fetch(
        "POST", f"https://{relay_host}{CHAT_PATH}", {"Content-Type": "application/json"}, chat
    )
    return surface_status, relay_status


def read_zip(data: bytes):
    """Every file of a log download, as (name, text)."""
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            yield info.filename, archive.read(info).decode("utf-8", errors="replace")


def inspect(files, marker, path):
    """(files the marker is in, whether the request's path was logged)."""
    marked, seen = [], False
    for name, text in files:
        if marker in text:
            marked.append(name)
        if path in text:
            seen = True
    return marked, seen


def dp008(fetch, download, surface_host, relay_host, surface, relay, marker=None, pause=time.sleep):
    """`download(app)` returns that app's log download as zip bytes."""
    marker = marker or fresh_marker()
    statuses = send(fetch, surface_host, relay_host, marker, pause)
    marked, seen = {}, {surface: False, relay: False}
    paths = {surface: DISCOVER_PATH, relay: CHAT_PATH}
    for attempt in range(ATTEMPTS):
        for app in (surface, relay):
            found, logged = inspect(read_zip(download(app)), marker, paths[app])
            if found:
                marked[app] = sorted(set(marked.get(app, [])) | set(found))
            seen[app] = seen[app] or logged
        if marked or (attempt + 1 >= MINIMUM_READS and all(seen.values())):
            break
        pause(PAUSE_SECONDS)
    if marked:
        return False, f"the marker is in {marked}; request statuses {statuses}"
    if not all(seen.values()):
        missing = sorted(app for app, logged in seen.items() if not logged)
        return False, f"the request never appeared in the log store of {missing}; request statuses {statuses}"
    return True, f"the marker is in no log file of either app; request statuses {statuses}"


def az_download(group):
    """The real reader: one `az webapp log download` per app, as bytes."""

    def download(app):
        with tempfile.TemporaryDirectory() as directory:
            target = f"{directory}/logs.zip"
            subprocess.run(
                ["az", "webapp", "log", "download", "--resource-group", group, "--name", app, "--log-file", target],
                check=True, capture_output=True,
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
    with open(arguments.out, "w", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2)
    print(("ok  " if passed else "FAIL"), "DP-008 -", detail)
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
