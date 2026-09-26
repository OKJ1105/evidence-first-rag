"""`deploy-v0.1` Section 4.9 and `relay-v0.1` Section 8.3: the cost computation.

Run once by the owner, before the first deploy, in Azure Cloud Shell
([#205](https://github.com/OKJ1105/evidence-first-rag/issues/205#issuecomment-5844938161)).
The writer's environment can reach neither the Azure Retail Prices API nor,
by rule, the Anthropic key, so this module is the writer's half and the run is
the owner's.

What it does, in order:

1. **The fixed monthly cost**, from the live Japan East prices of the four
   billing meters `deploy-v0.1` Section 4.1 creates: the App Service plan, the
   Flexible Server's compute and its storage, and the container registry. Each
   is fetched from the public Retail Prices API in JPY, and each match is
   printed so the owner can see which meter was read.
2. **The per-call upper bound** (`relay-v0.1` Section 8.3). The input tokens of
   a registered maximal request -- 128 KiB of conversation, the Section 4.9
   text and the `discover_entity` definition -- are **counted by the API's
   token-counting endpoint**, not estimated. A registered maximal tool result
   is counted the same way. Output is `max_tokens`. The model's per-token
   prices and the exchange rate are the owner's to read and pass in, with
   where and when they were read: no API publishes them.
3. **The daily ceiling**, by Section 8.3's formula, for each number of tool
   calls per model call from 1 to `--max-tool-calls` (see below).

**Tool calls per model call.** Section 8.3 bounds one call as one request plus
one tool result. With the Messages API's MCP connector, the model may call
`discover_entity` more than once inside one API call, and each round may bill
the conversation as input again. Whether it does is not known to the writer.
So the bound is computed for every N up to `--max-tool-calls`, as N + 1 input
passes plus N tool results plus `max_tokens` of output, and the owner chooses
N. Section 8.3's single-result reading is the N = 1 row.

**The fixed cost is reported beside the formula, not inside it.** Section
8.3's formula divides the whole monthly budget by the per-call bound. The
fixed cost comes out of the same budget, so the output also gives the ceiling
over what remains after it. The owner decides which to register.

The output is one JSON document: prices, counts, dates and the arithmetic. It
holds no secret, and it is the evidence `EFR_RELAY_DAILY_CEILING` is set from.
"""

import argparse
import datetime
import json
import math
import pathlib
import sys
import urllib.parse
import urllib.request

from ..relay.app import MAX_TOKENS, MODEL, PERSON_TURN_MAX_CHARACTERS, RELAY_TURN_MAX_BYTES, SYSTEM_PROMPT
from ..relay.app import BODY_MAX_BYTES, PERSON_TURN_LIMIT, _serialized

PRICES_API = "https://prices.azure.com/api/retail/prices"
REGION = "japaneast"
HOURS_PER_MONTH = 730
DAYS_PER_MONTH = 30

# `deploy-v0.1` Section 4.1's billing meters, each as the Retail Prices API
# filter that selects it. Every one must match exactly one item, or the run
# stops: a guessed meter would be a remembered price.
METERS = {
    "app_service_plan_b1_linux": {
        "filter": (
            "serviceName eq 'Azure App Service' and skuName eq 'B1'"
            " and contains(productName, 'Linux') and priceType eq 'Consumption'"
        ),
        "per": "hour",
        "quantity": 1,
    },
    "postgresql_b1ms_compute": {
        "filter": (
            "serviceName eq 'Azure Database for PostgreSQL' and skuName eq 'B1ms'"
            " and contains(productName, 'Flexible Server') and priceType eq 'Consumption'"
        ),
        "per": "hour",
        "quantity": 1,
    },
    "postgresql_storage_gb": {
        "filter": (
            "serviceName eq 'Azure Database for PostgreSQL'"
            " and contains(productName, 'Flexible Server Storage')"
            " and meterName eq 'Storage Data Stored' and priceType eq 'Consumption'"
        ),
        "per": "month",
        "quantity": 32,
    },
    "container_registry_basic": {
        "filter": (
            "serviceName eq 'Container Registry' and skuName eq 'Basic'"
            " and meterName eq 'Basic Registry Unit' and priceType eq 'Consumption'"
        ),
        "per": "day",
        "quantity": 1,
    },
}

UNITS_PER_MONTH = {"hour": HOURS_PER_MONTH, "day": DAYS_PER_MONTH, "month": 1}


# --------------------------------------------------------------------------
# The registered maximal request (Section 4.2's bounds, all at once).
# --------------------------------------------------------------------------


def maximal_messages() -> list:
    """Ten person's turns of 500 characters, nine relay turns between them,
    each relay turn as large as Section 4.2 admits while the whole body stays
    within 128 KiB. Deterministic: the same list every run."""
    person = {"role": "user", "content": "S" * PERSON_TURN_MAX_CHARACTERS}
    relays = PERSON_TURN_LIMIT - 1
    base = len(_serialized({"messages": [person] * PERSON_TURN_LIMIT}))
    empty_turn = {"role": "assistant", "content": [{"type": "text", "text": ""}]}
    overhead = len(_serialized(empty_turn)) + 1  # the separating comma
    room = (BODY_MAX_BYTES - base) // relays - overhead
    text_size = min(room, RELAY_TURN_MAX_BYTES - len(_serialized([{"type": "text", "text": ""}])))
    relay = {"role": "assistant", "content": [{"type": "text", "text": "S" * text_size}]}
    messages = []
    for index in range(PERSON_TURN_LIMIT):
        messages.append(person)
        if index < relays:
            messages.append(relay)
    return messages


def maximal_tool_result(envelopes_path: pathlib.Path) -> str:
    """The largest `entity-discovery-v0.1` envelope the repository registers,
    as the text a `discover_entity` result carries (`mcp-v0.1` Section 4.2)."""
    envelopes = json.loads(envelopes_path.read_text(encoding="utf-8"))
    discovery = [
        body for name, body in envelopes.items() if name.startswith("discovery") or name == "candidates"
    ]
    return max((json.dumps(body, separators=(",", ":")) for body in discovery), key=len)


# --------------------------------------------------------------------------
# The arithmetic, pure so the tests can drive it.
# --------------------------------------------------------------------------


def monthly_fixed_jpy(unit_prices: dict) -> float:
    """The four meters' monthly cost, from their per-unit JPY prices."""
    return sum(
        unit_prices[name] * UNITS_PER_MONTH[meter["per"]] * meter["quantity"]
        for name, meter in METERS.items()
    )


def cost_per_call_jpy(*, input_tokens, tool_result_tokens, tool_calls, input_usd, output_usd, jpy_per_usd):
    """Section 8.3's bound for one call with `tool_calls` tool rounds.

    Each round may bill the conversation as input again, so N rounds are
    N + 1 input passes, plus N tool results, plus `max_tokens` of output.
    Prices are USD per million tokens.
    """
    input_total = (tool_calls + 1) * input_tokens + tool_calls * tool_result_tokens
    usd = input_total * input_usd / 1e6 + MAX_TOKENS * output_usd / 1e6
    return usd * jpy_per_usd


def daily_ceiling(budget_jpy: float, per_call_jpy: float) -> int:
    """`floor((monthly_budget / 30) / cost_per_call_upper_bound)`."""
    return math.floor((budget_jpy / DAYS_PER_MONTH) / per_call_jpy)


# --------------------------------------------------------------------------
# The two network reads, in the owner's environment only.
# --------------------------------------------------------------------------


def fetch_unit_price(meter_filter: str) -> tuple:
    """(price, the matched item) for the one item the filter selects."""
    query = urllib.parse.urlencode(
        {"currencyCode": "JPY", "$filter": f"armRegionName eq '{REGION}' and {meter_filter}"}
    )
    with urllib.request.urlopen(f"{PRICES_API}?{query}", timeout=30) as response:
        items = json.load(response)["Items"]
    if len(items) != 1:
        names = [(i.get("productName"), i.get("skuName"), i.get("meterName")) for i in items]
        raise SystemExit(f"expected exactly one meter for {meter_filter!r}, got {len(items)}: {names}")
    item = items[0]
    return item["retailPrice"], {
        key: item.get(key)
        for key in ("productName", "skuName", "meterName", "unitOfMeasure", "retailPrice", "effectiveStartDate")
    }


def count_tokens(client, *, messages, tool_result_text=None) -> int:
    """Input tokens, counted by the API, for the Section 4.3 call shape."""
    from ..mcp.surface import DESCRIPTIONS, _SCHEMAS

    tool = {
        "name": "discover_entity",
        "description": DESCRIPTIONS["discover_entity"],
        "input_schema": _SCHEMAS["discover_entity"],
    }
    if tool_result_text is not None:
        messages = [{"role": "user", "content": tool_result_text}]
        return client.messages.count_tokens(model=MODEL, messages=messages).input_tokens
    return client.messages.count_tokens(
        model=MODEL, system=SYSTEM_PROMPT, messages=messages, tools=[tool]
    ).input_tokens


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--budget-jpy", type=float, required=True)
    parser.add_argument("--input-usd-per-mtok", type=float, required=True)
    parser.add_argument("--output-usd-per-mtok", type=float, required=True)
    parser.add_argument("--model-price-source", required=True, help="where and when the model prices were read")
    parser.add_argument("--jpy-per-usd", type=float, required=True)
    parser.add_argument("--fx-source", required=True, help="where and when the exchange rate was read")
    parser.add_argument("--max-tool-calls", type=int, default=5)
    parser.add_argument("--envelopes", type=pathlib.Path, default=pathlib.Path("tests/ui_envelopes.json"))
    args = parser.parse_args(argv)

    import anthropic  # reads ANTHROPIC_API_KEY from the environment

    unit_prices, meters = {}, {}
    for name, meter in METERS.items():
        unit_prices[name], meters[name] = fetch_unit_price(meter["filter"])
    fixed = monthly_fixed_jpy(unit_prices)

    client = anthropic.Anthropic()
    input_tokens = count_tokens(client, messages=maximal_messages())
    tool_result_tokens = count_tokens(
        client, messages=None, tool_result_text=maximal_tool_result(args.envelopes)
    )

    rows = []
    for calls in range(1, args.max_tool_calls + 1):
        per_call = cost_per_call_jpy(
            input_tokens=input_tokens,
            tool_result_tokens=tool_result_tokens,
            tool_calls=calls,
            input_usd=args.input_usd_per_mtok,
            output_usd=args.output_usd_per_mtok,
            jpy_per_usd=args.jpy_per_usd,
        )
        remaining = args.budget_jpy - fixed
        rows.append(
            {
                "tool_calls_per_model_call": calls,
                "cost_per_call_upper_bound_jpy": round(per_call, 4),
                "ceiling_section_8_3": daily_ceiling(args.budget_jpy, per_call),
                "ceiling_after_fixed_cost": daily_ceiling(remaining, per_call) if remaining > 0 else 0,
            }
        )

    json.dump(
        {
            "computed_at": datetime.datetime.now(tz=datetime.timezone.utc).isoformat(),
            "region": REGION,
            "monthly_budget_jpy": args.budget_jpy,
            "azure_meters": meters,
            "monthly_fixed_jpy": round(fixed, 2),
            "model": MODEL,
            "model_prices_usd_per_mtok": {
                "input": args.input_usd_per_mtok,
                "output": args.output_usd_per_mtok,
                "source": args.model_price_source,
            },
            "jpy_per_usd": {"rate": args.jpy_per_usd, "source": args.fx_source},
            "counted_tokens": {
                "maximal_request_input": input_tokens,
                "maximal_tool_result": tool_result_tokens,
                "max_tokens_output": MAX_TOKENS,
            },
            "ceilings": rows,
        },
        sys.stdout,
        indent=2,
        ensure_ascii=False,
    )
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
