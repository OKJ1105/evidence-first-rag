"""`relay-v0.1`: the relay, built from the environment.

The one module in `relay/` that reads an environment. `deploy-v0.1` Section 4.6
gives `relay` **four** keys, and this module reads three of them:

- `ANTHROPIC_API_KEY`, required, and handed to the SDK and nowhere else. It is
  never logged, returned or echoed (Section 4.8).
- `EFR_RELAY_MCP_URL`, required: the deployment's public `/mcp` URL, which the
  Messages API connector calls.
- `EFR_RELAY_DAILY_CEILING`, the Section 8.3 count. Unset, empty, or anything
  but a positive integer registers **no** ceiling, and then every request is
  refused `daily_ceiling_reached` (Section 4.6): the relay fails closed and
  never runs uncapped.

**The fourth key, `EFR_CORS_ORIGIN`, is not read, and `deploy-v0.1`'s CORS
obligation on `relay` is wholly unimplemented — the preflight and the response
header both.** `relay-v0.1` Section 3.2 leaves CORS origins to the deployment
contract; `deploy-v0.1` Section 4.5 requires that `relay` allow exactly one
origin, the portfolio site's production origin, and its Section 4.6 gives
`relay` the key that names it. Neither this module nor `app.py` reads it: no response
carries `Access-Control-Allow-Origin` or `Vary: Origin`, and `app.py`'s
`OPTIONS` handling is `relay-v0.1` Section 4.1's `method_not_allowed`, which
refuses a browser's preflight. Setting `EFR_CORS_ORIGIN` on the deployed
`relay` therefore changes nothing: a cross-origin `POST /chat` from the page
still fails in the browser.

**This is the owner's to resolve, and it is not resolved here.** Admitting the
preflight is a minor version of `relay-v0.1` (its Section 1), which is a
recorded human decision under its Section 10 — the same collision `api-v0.1`
resolved at `0.2.0` for `/v1` under `deploy-v0.1` Section 9, option (a). This
module states the gap rather than half-closing it: adding the response header
alone would leave the browser blocked at the preflight and would put a
behaviour on the route that no `relay-v0.1` registered case covers. Nothing is
lost while the gap stands, because `EFR_CORS_ORIGIN` is unset until the site's
origin exists, and an unset value allows no cross-origin call at all
(`deploy-v0.1` Section 4.6's closing note).

**It reads no database variable.** Section 4.8 runs the relay in a process
that holds no database credential, and `tests/test_relay.py` (`RL-017`)
asserts that this module names none.

Entry point, called rather than imported so that importing reads nothing:

    uvicorn --factory evidence_first_rag.relay.serve:build
"""

import logging
import os
import re
import sys

from .app import LOGGER, create_app

# Section 4.6: no retry, and a call that has not answered in 60 seconds failed.
TIMEOUT_SECONDS = 60


def daily_ceiling(environment) -> int | None:
    """The registered ceiling, or `None` where none is."""
    value = environment.get("EFR_RELAY_DAILY_CEILING", "")
    if not re.fullmatch(r"[0-9]+", value) or int(value) < 1:
        return None
    return int(value)


def anthropic_caller(api_key: str, *, http_client=None):
    """A Messages API client returning the response JSON exactly as received.

    The raw response is read rather than the SDK's parsed model, because
    Section 4.4 passes `content` through unchanged and a parsed model would
    add the SDK's defaults to the blocks. The beta travels as the one
    `anthropic-beta` header Section 4.3 names, in `extra_headers` rather than
    `betas`, so that its value is exactly that and nothing else.

    `http_client` is for the test that reads what reaches the wire.
    """
    import anthropic

    client = anthropic.Anthropic(
        api_key=api_key, max_retries=0, timeout=TIMEOUT_SECONDS, http_client=http_client
    )

    def call(body: dict, headers: dict) -> dict:
        raw = client.beta.messages.with_raw_response.create(**body, extra_headers=headers)
        return raw.json()

    return call


def configure_logging(stream=None) -> None:
    """Send Section 4.10's record to standard output, one JSON line each.

    `deploy-v0.1` Section 4.7 reads the relay's lines off standard output.
    Nothing else in the process configures this logger, and the root logger's
    default level would drop an `INFO` line before it is formatted, so the
    served relay would emit nothing. The line is already the whole record, so
    the formatter adds nothing to it. Idempotent: a second build adds no
    second handler.
    """
    if any(getattr(handler, "_relay_record", False) for handler in LOGGER.handlers):
        return
    handler = logging.StreamHandler(sys.stdout if stream is None else stream)
    handler.setFormatter(logging.Formatter("%(message)s"))
    handler._relay_record = True
    LOGGER.addHandler(handler)
    LOGGER.setLevel(logging.INFO)
    LOGGER.propagate = False


def build(environment=None):
    """The `POST /chat` relay over the Anthropic API."""
    environment = os.environ if environment is None else environment
    configure_logging()
    return create_app(
        anthropic_caller(environment["ANTHROPIC_API_KEY"]),
        mcp_url=environment["EFR_RELAY_MCP_URL"],
        ceiling=daily_ceiling(environment),
    )
