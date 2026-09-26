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

    def test_the_tool_result_is_the_largest_registered_discovery_envelope(self):
        text = cost.maximal_tool_result(ROOT / "tests" / "ui_envelopes.json")
        envelopes = json.loads((ROOT / "tests" / "ui_envelopes.json").read_text(encoding="utf-8"))
        self.assertIn(json.loads(text), list(envelopes.values()))


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


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
