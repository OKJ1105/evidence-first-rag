"""`relay-v0.1`: the relay, built from the environment.

The one module in `relay/` that reads an environment, and it reads exactly the
three keys `deploy-v0.1` Section 4.6 gives `relay`:

- `ANTHROPIC_API_KEY`, required, and handed to the SDK and nowhere else. It is
  never logged, returned or echoed (Section 4.8).
- `EFR_RELAY_MCP_URL`, required: the deployment's public `/mcp` URL, which the
  Messages API connector calls.
- `EFR_RELAY_DAILY_CEILING`, the Section 8.3 count. Unset, empty, or anything
  but a positive integer registers **no** ceiling, and then every request is
  refused `daily_ceiling_reached` (Section 4.6): the relay fails closed and
  never runs uncapped.

**It reads no database variable.** Section 4.8 runs the relay in a process
that holds no database credential, and `tests/test_relay.py` (`RL-017`)
asserts that this module names none.

Entry point, called rather than imported so that importing reads nothing:

    uvicorn --factory evidence_first_rag.relay.serve:build
"""

import os
import re

from .app import create_app

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


def build(environment=None):
    """The `POST /chat` relay over the Anthropic API."""
    environment = os.environ if environment is None else environment
    return create_app(
        anthropic_caller(environment["ANTHROPIC_API_KEY"]),
        mcp_url=environment["EFR_RELAY_MCP_URL"],
        ceiling=daily_ceiling(environment),
    )
