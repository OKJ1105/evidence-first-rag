"""`deploy-v0.1` Section 4.9 / `relay-v0.1` Section 8.3: the computation's
own arithmetic and its registered maximal request.

The two network reads (the Retail Prices API and the token-counting endpoint)
run only in the owner's environment, so they are not exercised here. What is
asserted is that the request they count is the largest the relay admits, and
that the arithmetic is Section 8.3's.
"""

import json
import pathlib
import unittest

try:
    from evidence_first_rag.deploy import cost
    from evidence_first_rag.relay import app as relay

    HAS_RELAY = True
except ImportError:  # pragma: no cover - exercised by the extra-free job
    HAS_RELAY = False

ROOT = pathlib.Path(__file__).resolve().parents[1]


@unittest.skipUnless(HAS_RELAY, "the api extra is not installed")
class TheMaximalRequest(unittest.TestCase):
    def test_the_relay_admits_it(self):
        body = relay._serialized({"messages": cost.maximal_messages()})
        self.assertEqual(relay.parse_request(body), cost.maximal_messages())

    def test_it_is_within_one_relay_turn_of_the_bound(self):
        """Maximal: the body is under 128 KiB by less than the slack the nine
        relay turns share, so no admitted request is larger by more."""
        body = relay._serialized({"messages": cost.maximal_messages()})
        self.assertLessEqual(len(body), relay.BODY_MAX_BYTES)
        self.assertGreater(len(body), relay.BODY_MAX_BYTES - 16)

    def test_it_carries_the_most_person_turns(self):
        messages = cost.maximal_messages()
        persons = [turn for turn in messages if turn["role"] == "user"]
        self.assertEqual(len(persons), relay.PERSON_TURN_LIMIT)
        self.assertTrue(all(len(turn["content"]) == 500 for turn in persons))

    def test_the_filler_is_not_one_repeated_character(self):
        """A run of one character merges into multi-character tokens, so a
        body filled with it is maximal in bytes and not in tokens. Every turn
        carries mixed-case noise instead, and the same noise every run."""
        messages = cost.maximal_messages()
        for turn in messages:
            text = turn["content"] if turn["role"] == "user" else turn["content"][0]["text"]
            self.assertGreater(len(set(text)), 32)
            self.assertLess(max(text.count(character) for character in set(text)), len(text) // 8)
        self.assertEqual(messages, cost.maximal_messages())

    def test_the_bound_is_the_byte_floor_when_the_filler_counts_below_it(self):
        """No admitted body carries more than one token per byte, so the bound
        never sits below that, whatever the filler happens to count."""
        self.assertEqual(cost.byte_floor_tokens(1_000), 1_000 + relay.BODY_MAX_BYTES)
        body = relay._serialized({"messages": cost.maximal_messages()})
        self.assertGreaterEqual(cost.byte_floor_tokens(0), len(body))

    def test_the_tool_result_carries_the_contracts_candidate_limit(self):
        """`entity-discovery-v0.1` Section 4.6 fixes the list at k = 10. The
        registered envelope carries two, which is not a maximal result."""
        envelope = json.loads(cost.maximal_tool_result(ROOT / "tests" / "ui_envelopes.json"))
        result = envelope["result"]
        self.assertEqual(cost.DISCOVERY_CANDIDATE_LIMIT, 10)
        self.assertEqual(result["evidence_bundle"]["candidate_count"], 10)
        self.assertEqual(len(result["candidates"]), 10)
        self.assertEqual([c["rank"] for c in result["candidates"]], list(range(1, 11)))
        self.assertEqual(len(result["source_trace"]["alias_provenance"]), 10)
        self.assertEqual(len(result["source_trace"]["parent_messages"]), 10)

    def test_the_tool_result_invents_nothing_the_registry_does_not_hold(self):
        """Only the lengths the contract fixes are taken to their bound: every
        candidate and trace entry is one the registered envelope carries."""
        registered = json.loads((ROOT / "tests" / "ui_envelopes.json").read_text(encoding="utf-8"))
        original = registered["candidates"]["result"]
        widened = json.loads(cost.maximal_tool_result(ROOT / "tests" / "ui_envelopes.json"))["result"]
        for candidate in widened["candidates"]:
            self.assertIn(
                {**candidate, "rank": None},
                [{**one, "rank": None} for one in original["candidates"]],
            )
        for key in ("alias_provenance", "parent_messages"):
            for entry in widened["source_trace"][key]:
                self.assertIn(entry, original["source_trace"][key])


@unittest.skipUnless(HAS_RELAY, "the api extra is not installed")
class TheArithmetic(unittest.TestCase):
    def test_the_ceiling_is_section_8_3s_formula(self):
        # 8,000 JPY a month is 266.67 a day; at 1 JPY a call, 266.
        self.assertEqual(cost.daily_ceiling(8000, 1.0), 266)
        self.assertEqual(cost.daily_ceiling(8000, 3.0), 88)

    def test_each_tool_round_bills_the_input_again(self):
        common = dict(input_tokens=1_000_000, tool_result_tokens=0, input_usd=1.0, output_usd=0.0, jpy_per_usd=100)
        one = cost.cost_per_call_jpy(tool_calls=1, **common)
        three = cost.cost_per_call_jpy(tool_calls=3, **common)
        self.assertAlmostEqual(one, 200.0)  # two input passes
        self.assertAlmostEqual(three, 400.0)  # four input passes

    def test_the_accumulated_results_are_billed_with_every_later_pass(self):
        """Pass k carries the k - 1 results already in the conversation, so N
        rounds bill a result 1, 3, 6, 10 times -- not N times."""
        common = dict(
            input_tokens=0, tool_result_tokens=1_000_000,
            input_usd=1.0, output_usd=0.0, jpy_per_usd=1,
        )
        billed = [cost.cost_per_call_jpy(tool_calls=calls, **common) for calls in (1, 2, 3, 4)]
        self.assertEqual([round(one) for one in billed], [1, 3, 6, 10])

    def test_output_is_max_tokens(self):
        per_call = cost.cost_per_call_jpy(
            input_tokens=0, tool_result_tokens=0, tool_calls=1,
            input_usd=0.0, output_usd=1_000_000 / relay.MAX_TOKENS, jpy_per_usd=1,
        )
        self.assertAlmostEqual(per_call, 1_000_000 / relay.MAX_TOKENS * relay.MAX_TOKENS / 1e6)

    def test_the_fixed_cost_covers_every_registered_meter(self):
        prices = {name: 1.0 for name in cost.METERS}
        # plan 730 h + server 730 h + storage 32 GB + registry 30 days
        self.assertEqual(cost.monthly_fixed_jpy(prices), 730 + 730 + 32 + 30)
        self.assertEqual(
            set(cost.METERS),
            {"app_service_plan_b1_linux", "postgresql_b1ms_compute", "postgresql_storage_gb", "container_registry_basic"},
        )


@unittest.skipUnless(HAS_RELAY, "the api extra is not installed")
class TheMeterReading(unittest.TestCase):
    """`matched_item` is the whole of the read that does not need the network:
    the item list stands in for what the Retail Prices API returns."""

    def priced(self, meter, unit=None, price=1.0):
        return {
            "productName": "P", "skuName": "S", "meterName": "M",
            "unitOfMeasure": meter["unit_of_measure"] if unit is None else unit,
            "retailPrice": price,
        }

    def test_the_one_match_at_the_registered_unit_is_returned(self):
        meter = cost.METERS["postgresql_storage_gb"]
        item = self.priced(meter, price=2.5)
        self.assertEqual(cost.matched_item([item], meter), item)

    def test_no_match_and_two_matches_stop_the_run(self):
        meter = cost.METERS["container_registry_basic"]
        item = self.priced(meter)
        for items in ([], [item, dict(item)]):
            with self.assertRaises(SystemExit):
                cost.matched_item(items, meter)

    def test_a_price_quoted_per_another_unit_stops_the_run(self):
        """The filter still matches one item, so only the unit catches it: a
        plan quoted per 10 Hours would be ten times the fixed cost, and
        storage quoted per TB/Month a thousandth of it."""
        for name, wrong in (("app_service_plan_b1_linux", "10 Hours"), ("postgresql_storage_gb", "1 TB/Month")):
            meter = cost.METERS[name]
            with self.assertRaises(SystemExit):
                cost.matched_item([self.priced(meter, unit=wrong)], meter)

    def test_a_missing_unit_stops_the_run(self):
        meter = cost.METERS["postgresql_b1ms_compute"]
        with self.assertRaises(SystemExit):
            cost.matched_item([{"retailPrice": 1.0}], meter)

    def test_every_registered_unit_is_the_one_the_arithmetic_multiplies(self):
        """`monthly_fixed_jpy` multiplies by `UNITS_PER_MONTH[per]`, so each
        registered unit must be one of that period and one unit of it."""
        for name, meter in cost.METERS.items():
            unit = meter["unit_of_measure"]
            period = unit.split("/")[-1].split()[-1].lower()
            self.assertEqual(period, meter["per"], name)
            self.assertTrue(unit.startswith("1"), name)
            self.assertIn(meter["per"], cost.UNITS_PER_MONTH, name)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
