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

**Maximal in tokens, not only in bytes.** Section 4.2 admits *any* 128 KiB
body, and a tokenizer charges two bodies of the same size very differently: a
run of one repeated character merges into multi-character tokens, while
high-entropy text approaches one token per byte. So the conversation is filled
with deterministic mixed-case noise rather than a repeated character, and the
counted number is then raised to the byte floor -- one token per admitted body
byte, which a byte-level tokenizer cannot exceed -- so that no admitted
request can cost more than the bound. Both numbers are in the output, with the
filler's measured tokens per byte, because the distance between them is the
owner's evidence that the bound is one.

**Tool calls per model call.** Section 8.3 bounds one call as one request plus
one tool result. With the Messages API's MCP connector, the model may call
`discover_entity` more than once inside one API call, and each round may bill
the conversation as input again. Whether it does is not known to the writer.
So the bound is computed for every N up to `--max-tool-calls`: N + 1 input
passes, each carrying the conversation *and the rounds already accumulated in
it*, plus `max_tokens` of output. The owner chooses N. Section 8.3's
single-result reading is the N = 1 row.

**The fixed cost is reported beside the formula, not inside it.** Section
8.3's formula divides the whole monthly budget by the per-call bound. The
fixed cost comes out of the same budget, so the output also gives the ceiling
over what remains after it. The owner decides which to register.

The output is one JSON document: prices, counts, dates and the arithmetic. It
holds no secret, and it is the evidence `EFR_RELAY_DAILY_CEILING` is set from.
"""

import argparse
import copy
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

# `entity-discovery-v0.1` Section 4.6: `k` = 10, fixed by that contract.
DISCOVERY_CANDIDATE_LIMIT = 10

# `mcp-v0.1` Section 4.2 puts the same document in a result's `content` text
# and in its `structuredContent`. Whether the connector relays one copy or
# both into the conversation is not known to the writer, so the bound assumes
# both.
TOOL_RESULT_CARRIAGE_COPIES = 2

# A byte-level tokenizer emits no token shorter than one byte, so no body
# `relay-v0.1` Section 4.2 admits can carry more than `BODY_MAX_BYTES` tokens
# of conversation. The JSON structure the bound is measured on -- the keys,
# quotes and brackets around each turn -- is more bytes than the API's own
# per-message framing is tokens, so the two do not eat into this.
WORST_CASE_TOKENS_PER_BYTE = 1

# The 64 ASCII characters JSON writes as themselves, so one character is one
# byte and the Section 4.2 size arithmetic below is exact.
FILLER_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"


# --------------------------------------------------------------------------
# The registered maximal request (Section 4.2's bounds, all at once).
# --------------------------------------------------------------------------


def filler(size: int, seed: int) -> str:
    """`size` bytes of deterministic mixed-case noise, from `seed`.

    **Not one repeated character.** A run of one character merges into
    multi-character tokens, so a body filled with it is maximal in bytes and
    nowhere near maximal in tokens -- and a bound computed from it is not a
    bound, because Section 4.2 admits a body of the same size filled with
    base64-like noise that costs several times as much. This is that noise,
    from a fixed linear congruential sequence so the request is the same every
    run.
    """
    state, out = seed, []
    for _ in range(size):
        state = (state * 1103515245 + 12345) % (1 << 31)
        # The high bits: the low bits of a power-of-two modulus cycle in a few
        # thousand draws, which is fewer than one relay turn holds.
        out.append(FILLER_ALPHABET[(state >> 24) % len(FILLER_ALPHABET)])
    return "".join(out)


def maximal_messages() -> list:
    """Ten person's turns of 500 characters, nine relay turns between them,
    each relay turn as large as Section 4.2 admits while the whole body stays
    within 128 KiB. Every turn is `filler`, so the request is maximal in
    tokens and not only in bytes. Deterministic: the same list every run."""
    relays = PERSON_TURN_LIMIT - 1
    sample = {"role": "user", "content": filler(PERSON_TURN_MAX_CHARACTERS, 1)}
    base = len(_serialized({"messages": [sample] * PERSON_TURN_LIMIT}))
    empty_turn = {"role": "assistant", "content": [{"type": "text", "text": ""}]}
    overhead = len(_serialized(empty_turn)) + 1  # the separating comma
    room = (BODY_MAX_BYTES - base) // relays - overhead
    text_size = min(room, RELAY_TURN_MAX_BYTES - len(_serialized([{"type": "text", "text": ""}])))
    messages = []
    for index in range(PERSON_TURN_LIMIT):
        messages.append({"role": "user", "content": filler(PERSON_TURN_MAX_CHARACTERS, 2 * index + 1)})
        if index < relays:
            text = filler(text_size, 2 * index + 2)
            messages.append({"role": "assistant", "content": [{"type": "text", "text": text}]})
    return messages


def maximal_tool_result(envelopes_path: pathlib.Path) -> str:
    """A `discover_entity` result at the contract's bound, as the text the
    connector carries (`mcp-v0.1` Section 4.2's canonical JSON).

    **Why not simply the largest registered envelope.** The repository's
    `candidates` envelope carries two candidates, and `entity-discovery-v0.1`
    Section 4.6 fixes the list at `k` = 10. A result with ten candidates, each
    carrying its alias provenance, with the parent message and the
    alias-provenance entry that come with each, is several times that JSON and
    is what the tool may return. Counting the two-candidate fixture would put
    every row's bound below what one real result can cost.

    So the envelope counted here is the registered one widened to `k`: its own
    largest candidate at ranks 1..`k`, its own alias-provenance and
    parent-message entries repeated to match, and `candidate_count` and
    `row_count` set to `k`. No field and no identifier is invented; only the
    lengths the contract fixes are taken to their bound.
    """
    from ..discovery.canonical import json_text

    envelopes = json.loads(envelopes_path.read_text(encoding="utf-8"))
    envelope = copy.deepcopy(envelopes["candidates"])
    result = envelope["result"]
    widest = max(result["candidates"], key=lambda candidate: len(json.dumps(candidate)))
    result["candidates"] = []
    for rank in range(1, DISCOVERY_CANDIDATE_LIMIT + 1):
        candidate = copy.deepcopy(widest)
        candidate["rank"] = rank
        result["candidates"].append(candidate)
    trace = result["source_trace"]
    for key in ("alias_provenance", "parent_messages"):
        widest_entry = max(trace[key], key=lambda entry: len(json.dumps(entry)))
        trace[key] = [copy.deepcopy(widest_entry) for _ in range(DISCOVERY_CANDIDATE_LIMIT)]
    result["evidence_bundle"]["candidate_count"] = DISCOVERY_CANDIDATE_LIMIT
    result["evidence_bundle"]["row_count"] = DISCOVERY_CANDIDATE_LIMIT
    return json_text(envelope)


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

    Each round may bill the conversation as input again, and **the results
    already in it with it**: pass k carries the conversation plus the k - 1
    tool results accumulated before it. So N rounds are N + 1 input passes of
    the conversation and 0 + 1 + ... + N = N(N+1)/2 billings of a tool result,
    plus `max_tokens` of output. Charging each result once would understate
    the bound at every N above 1 -- five times rather than fifteen at N = 5 --
    and raise the ceiling above what the budget covers.

    Prices are USD per million tokens.
    """
    results = tool_calls * (tool_calls + 1) // 2
    input_total = (tool_calls + 1) * input_tokens + results * tool_result_tokens
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


def byte_floor_tokens(call_overhead: int) -> int:
    """The tokens no admitted request can exceed.

    `call_overhead` is the counted cost of everything outside the body -- the
    Section 4.9 text, the `discover_entity` definition and one turn's framing
    -- and the conversation itself cannot cost more than one token per byte
    Section 4.2 admits. The counted maximal request is what a dense filler
    reaches; this is what no filler can pass, and the bound is the larger.
    """
    return call_overhead + BODY_MAX_BYTES * WORST_CASE_TOKENS_PER_BYTE


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
    messages = maximal_messages()
    request_bytes = len(_serialized({"messages": messages}))
    counted = count_tokens(client, messages=messages)
    # The same call with one character of conversation: the Section 4.9 text,
    # the tool definition and one turn's framing, and nothing else.
    overhead = count_tokens(client, messages=[{"role": "user", "content": "."}])
    floor = byte_floor_tokens(overhead)
    input_tokens = max(counted, floor)
    result_text = maximal_tool_result(args.envelopes)
    tool_result_tokens = TOOL_RESULT_CARRIAGE_COPIES * count_tokens(
        client, messages=None, tool_result_text=result_text
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
                "maximal_request_counted": counted,
                "maximal_request_body_bytes": request_bytes,
                "maximal_request_byte_floor": floor,
                "call_overhead": overhead,
                "filler_tokens_per_byte": round((counted - overhead) / request_bytes, 4),
                "maximal_tool_result": tool_result_tokens,
                "tool_result_carriage_copies": TOOL_RESULT_CARRIAGE_COPIES,
                "tool_result_candidate_count": DISCOVERY_CANDIDATE_LIMIT,
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
