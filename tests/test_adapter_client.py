"""The pinned call Section 4.6 fixes, asserted without spending anything.

The request is built against a recording stub rather than sent. What the model
would *answer* is the Milestone 2 comparison's question and needs a credential
and the owner's registered thresholds; what the request *contains* is fixed by
the contract and can be checked here for free.

Skipped when the SDK is absent. `anthropic` is an optional extra
(`pip install evidence-first-rag[adapter]`) because Charter Section 3.1 keeps
the model outside the path that produces facts, so the `repository-checks` CI
job -- which installs nothing -- has no SDK and no business failing over one.
"""

import importlib.util
import json
import types
import unittest

HAS_SDK = importlib.util.find_spec("anthropic") is not None

if HAS_SDK:
    from evidence_first_rag.adapter import client as adapter_client

REQUEST = "facts for SAMPLE_MSG_ENGINE_STATUS in SAMPLE_PROJECT_ALPHA"


class RecordingClient:
    """Stands in for `anthropic.Anthropic`. Records, never calls."""

    def __init__(self, response):
        self._response = response
        self.calls = []
        self.messages = types.SimpleNamespace(create=self._create)

    def _create(self, **keywords):
        self.calls.append(keywords)
        return self._response


def response(text, stop_reason="end_turn"):
    return types.SimpleNamespace(
        stop_reason=stop_reason,
        content=[types.SimpleNamespace(type="text", text=text)],
    )


def proposal_json(**overrides):
    document = {
        "route": "message_facts",
        "arguments": {"message_key": "SAMPLE_MSG_ENGINE_STATUS"},
    }
    document.update(overrides)
    return json.dumps(document)


@unittest.skipUnless(HAS_SDK, "the adapter extra is not installed")
class TheCallIsTheOneSection46Pins(unittest.TestCase):
    def call(self, text=proposal_json()):
        stub = RecordingClient(response(text))
        proposal = adapter_client.Adapter(client=stub).propose(REQUEST)
        return stub.calls[0], proposal

    def test_the_model_is_the_pinned_identifier(self):
        call, _ = self.call()
        self.assertEqual(call["model"], "claude-opus-5")
        self.assertEqual(adapter_client.MODEL, "claude-opus-5")

    def test_the_decoding_configuration_is_the_recorded_one(self):
        call, _ = self.call()
        recorded = adapter_client.Adapter.configuration()
        self.assertEqual(call["max_tokens"], recorded["max_tokens"])
        self.assertEqual(call["thinking"], recorded["thinking"])
        self.assertEqual(call["output_config"]["effort"], recorded["output_config"]["effort"])

    def test_the_recorded_configuration_is_json_and_immutable_at_the_source(self):
        # Section 4.6 requires it recorded with the evaluation run, so it has
        # to survive a round trip into the artifact; and a caller that mutated
        # the returned dict must not change what the next run records.
        recorded = adapter_client.Adapter.configuration()
        self.assertEqual(json.loads(json.dumps(recorded)), recorded)
        recorded["model"] = "something-else"
        self.assertEqual(adapter_client.Adapter.configuration()["model"], "claude-opus-5")

    def test_the_output_is_schema_constrained(self):
        call, _ = self.call()
        fmt = call["output_config"]["format"]
        self.assertEqual(fmt["type"], "json_schema")
        self.assertEqual(
            fmt["schema"]["properties"]["route"]["enum"],
            ["message_facts", "signal_facts", "signal_mapping", "unsupported"],
        )

    def test_the_request_text_is_the_only_thing_after_the_cached_prefix(self):
        call, _ = self.call()
        self.assertEqual(call["messages"], [{"role": "user", "content": REQUEST}])
        self.assertEqual(len(call["system"]), 2)
        self.assertEqual(call["system"][1]["cache_control"], {"type": "ephemeral"})

    def test_no_assistant_prefill_is_sent(self):
        # Prefill returns a 400 on Claude Opus 5; a request that carried one
        # would fail at the gate rather than here.
        call, _ = self.call()
        self.assertEqual([m["role"] for m in call["messages"]], ["user"])


@unittest.skipUnless(HAS_SDK, "the adapter extra is not installed")
class ReadingAResponseNeverRaises(unittest.TestCase):
    """Section 4.6 gives the adapter one way to say "no route applies", and a
    model that declined or answered nonsense has said exactly that. Raising
    would make the comparison harness lose a case it should count."""

    def test_a_well_formed_answer_becomes_a_proposal(self):
        proposal = adapter_client.Adapter.read(response(proposal_json()))
        self.assertEqual(proposal.route, "message_facts")
        self.assertEqual(
            dict(proposal.arguments), {"message_key": "SAMPLE_MSG_ENGINE_STATUS"}
        )

    def test_a_refusal_becomes_unsupported(self):
        proposal = adapter_client.Adapter.read(response("", stop_reason="refusal"))
        self.assertEqual(proposal.route, "unsupported")

    def test_unparseable_or_wrongly_shaped_output_becomes_unsupported(self):
        for text in ("", "not json", "[1, 2, 3]", "null"):
            with self.subTest(text=text):
                self.assertEqual(
                    adapter_client.Adapter.read(response(text)).route, "unsupported"
                )

    def test_a_proposal_is_passed_on_unfiltered(self):
        # An adapter that cleaned up its own output would hide the failures
        # the Milestone 2 comparison exists to measure. A route the contract
        # does not know reaches revalidation, which refuses it.
        proposal = adapter_client.Adapter.read(
            response(json.dumps({"route": "drop_tables", "arguments": {"x": "y"}}))
        )
        self.assertEqual(proposal.route, "drop_tables")


if __name__ == "__main__":
    unittest.main(verbosity=2)
