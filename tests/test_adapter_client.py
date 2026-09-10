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
import pathlib
import types
import unittest

HAS_SDK = importlib.util.find_spec("anthropic") is not None

if HAS_SDK:
    from evidence_first_rag.adapter import client as adapter_client

REQUEST = "facts for SAMPLE_MSG_ENGINE_STATUS in SAMPLE_PROJECT_ALPHA"

# A sentinel for "the attribute is not there at all", which `None` cannot
# express as a default.
NOTHING = object()


class RecordingClient:
    """Stands in for `anthropic.Anthropic`. Records, never calls."""

    def __init__(self, response):
        self._response = response
        self.calls = []
        self.messages = types.SimpleNamespace(create=self._create)

    def _create(self, **keywords):
        self.calls.append(keywords)
        return self._response


def response(text, stop_reason="end_turn", usage=NOTHING, blocks=None):
    """A stub response. `usage=NOTHING` means the attribute is absent entirely.

    Absent and `None` are different cases and both occur: an SDK that never
    reported usage, and a stub that reports it as nothing. `_usage_as_json`
    must survive both, so the helper has to be able to produce both.
    """
    fields = {
        "stop_reason": stop_reason,
        "content": blocks
        if blocks is not None
        else [types.SimpleNamespace(type="text", text=text)],
    }
    if usage is not NOTHING:
        fields["usage"] = usage
    return types.SimpleNamespace(**fields)


class Usage:
    """A stand-in for the SDK's usage model, which dumps rather than maps."""

    def __init__(self, **counts):
        self._counts = counts

    def model_dump(self):
        return dict(self._counts)


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

    def test_a_repeated_key_survives_as_a_contradiction(self):
        # Section 8.1 registers `FX-110` as "two different `revision_label`
        # values". Plain `json.loads` keeps the last and drops the first, so
        # the contradiction disappeared before revalidation could see it and
        # `FX-110` was unreachable through the adapter -- found by an external
        # review, and reproduced. A Python mapping cannot hold one key twice,
        # so the two values are kept as a list, which the runtime already
        # refuses as contradictory.
        raw = (
            '{"route":"message_facts","arguments":{'
            '"revision_label":"SAMPLE_REV_A",'
            '"revision_label":"SAMPLE_REV_B",'
            '"message_key":"SAMPLE_MSG_ENGINE_STATUS"}}'
        )
        proposal = adapter_client.Adapter.read(response(raw))
        self.assertEqual(
            dict(proposal.arguments)["revision_label"],
            ["SAMPLE_REV_A", "SAMPLE_REV_B"],
        )

    def test_three_of_the_same_key_are_all_kept(self):
        raw = '{"route":"message_facts","arguments":{"x":"1","x":"2","x":"3"}}'
        proposal = adapter_client.Adapter.read(response(raw))
        self.assertEqual(dict(proposal.arguments)["x"], ["1", "2", "3"])

    def test_a_single_key_is_untouched(self):
        # The guard must not turn every argument into a list.
        proposal = adapter_client.Adapter.read(response(proposal_json()))
        self.assertEqual(
            dict(proposal.arguments), {"message_key": "SAMPLE_MSG_ENGINE_STATUS"}
        )

    def test_the_contradiction_reaches_invalid_request_end_to_end(self):
        from evidence_first_rag.adapter import answer
        from evidence_first_rag.runtime import Runtime
        from evidence_first_rag import Status
        from .runtime_support import BASE, FakeDatabase

        raw = (
            '{"route":"message_facts","arguments":{'
            + ",".join(f'"{k}":"{v}"' for k, v in BASE.items())
            + ',"revision_label":"SAMPLE_REV_B"'
            ',"message_key":"SAMPLE_MSG_ENGINE_STATUS"}}'
        )
        proposal = adapter_client.Adapter.read(response(raw))
        database = FakeDatabase({})
        result = answer(
            Runtime(database=database),
            proposal,
            "SAMPLE_PROJECT_ALPHA SAMPLE_REV_A SAMPLE_REV_B"
            " SAMPLE_NET_POWERTRAIN SAMPLE_SNAP_BASE SAMPLE_MSG_ENGINE_STATUS",
        )
        self.assertIs(result.status, Status.INVALID_REQUEST)
        self.assertEqual(database.sessions, 0)

    def test_a_proposal_is_passed_on_unfiltered(self):
        # An adapter that cleaned up its own output would hide the failures
        # the Milestone 2 comparison exists to measure. A route the contract
        # does not know reaches revalidation, which refuses it.
        proposal = adapter_client.Adapter.read(
            response(json.dumps({"route": "drop_tables", "arguments": {"x": "y"}}))
        )
        self.assertEqual(proposal.route, "drop_tables")




@unittest.skipUnless(HAS_SDK, "the adapter extra is not installed")
class EveryCallLeavesARecord(unittest.TestCase):
    """#90. `propose` returned `self.read(response)` and dropped the response,
    so the first Milestone 2 comparison could report forty-eight refusals
    without showing one thing the model wrote.

    Nothing here spends a credential or opens a socket: the client is the
    same recording stub the request assertions use.
    """

    def adapter(self, *responses):
        """An adapter whose stub answers with `responses` in turn."""
        answers = list(responses)

        class Sequenced:
            def __init__(inner):
                inner.messages = types.SimpleNamespace(
                    create=lambda **keywords: answers.pop(0)
                )

        return adapter_client.Adapter(client=Sequenced())

    def test_a_call_records_the_text_the_stop_reason_and_the_usage(self):
        adapter = self.adapter(
            response(proposal_json(), usage=Usage(input_tokens=11, output_tokens=4))
        )
        adapter.propose(REQUEST)
        (call,) = adapter.calls
        self.assertEqual(call.text, proposal_json())
        self.assertEqual(call.stop_reason, "end_turn")
        self.assertEqual(call.usage, {"input_tokens": 11, "output_tokens": 4})
        self.assertEqual(
            call.as_json(),
            {
                "text": proposal_json(),
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 11, "output_tokens": 4},
            },
        )

    def test_the_records_are_in_call_order(self):
        first, second, third = proposal_json(), "not json", proposal_json(route="signal_facts")
        adapter = self.adapter(response(first), response(second), response(third))
        for _ in range(3):
            adapter.propose(REQUEST)
        self.assertEqual([call.text for call in adapter.calls], [first, second, third])

    def test_the_recorded_text_is_the_text_read_parsed(self):
        # The whole point of the raw file is to explain a proposal. If the
        # record and the parse could take different blocks, it would explain
        # a proposal that was never made from it. One extraction, asserted.
        blocks = [
            types.SimpleNamespace(type="thinking", text="ignored"),
            types.SimpleNamespace(type="text", text=proposal_json()),
            types.SimpleNamespace(type="text", text='{"route":"signal_facts"}'),
        ]
        stub = response("", blocks=blocks)
        adapter = self.adapter(stub)
        proposal = adapter.propose(REQUEST)
        (call,) = adapter.calls
        self.assertEqual(call.text, proposal_json())
        self.assertEqual(proposal.route, "message_facts")
        self.assertEqual(adapter_client.Adapter.read(stub).route, proposal.route)

    def test_a_refusal_is_recorded_as_a_refusal_not_as_an_empty_answer(self):
        # `read` turns both a refusal and unparseable text into `unsupported`.
        # The record is what tells them apart afterwards.
        adapter = self.adapter(response("", stop_reason="refusal"), response("not json"))
        self.assertEqual(adapter.propose(REQUEST).route, "unsupported")
        self.assertEqual(adapter.propose(REQUEST).route, "unsupported")
        refused, unparseable = adapter.calls
        self.assertEqual(refused.stop_reason, "refusal")
        self.assertEqual(refused.text, "")
        self.assertEqual(unparseable.stop_reason, "end_turn")
        self.assertEqual(unparseable.text, "not json")

    def test_usage_is_none_rather_than_empty_when_the_sdk_exposed_nothing(self):
        # A run that could not observe its cost must not report zero.
        for label, stub in (
            ("absent", response(proposal_json())),
            ("none", response(proposal_json(), usage=None)),
            ("opaque", response(proposal_json(), usage=object())),
        ):
            with self.subTest(usage=label):
                adapter = self.adapter(stub)
                adapter.propose(REQUEST)
                self.assertIsNone(adapter.calls[0].usage)

    def test_a_usage_whose_dump_is_not_a_mapping_is_none_rather_than_a_crash(self):
        # Found by a stub, not by reasoning: a `Mock` grows `model_dump` on
        # demand and returns another `Mock`, and `dict()` of that raised.
        # The token count is the least important thing a run produces, so it
        # must never be the thing that ends one.
        class Broken:
            def model_dump(self):
                return "not a mapping"

        class Raising:
            def model_dump(self):
                raise RuntimeError("the SDK changed shape")

        for label, usage in (("non-mapping", Broken()), ("raising", Raising())):
            with self.subTest(dump=label):
                adapter = self.adapter(response(proposal_json(), usage=usage))
                proposal = adapter.propose(REQUEST)
                self.assertIsNone(adapter.calls[0].usage)
                # And the proposal still came through, which is the point.
                self.assertEqual(proposal.route, "message_facts")

    def test_a_usage_that_is_already_a_mapping_is_taken_as_one(self):
        adapter = self.adapter(response(proposal_json(), usage={"input_tokens": 7}))
        adapter.propose(REQUEST)
        self.assertEqual(adapter.calls[0].usage, {"input_tokens": 7})

    def test_the_record_survives_json(self):
        # It is written to a file; a usage payload that could not serialise
        # would fail the run rather than the test.
        adapter = self.adapter(
            response(proposal_json(), usage=Usage(input_tokens=1, cache_read_input_tokens=2))
        )
        adapter.propose(REQUEST)
        document = adapter.calls[0].as_json()
        self.assertEqual(json.loads(json.dumps(document)), document)

    def test_calls_is_a_snapshot_the_caller_cannot_edit(self):
        adapter = self.adapter(response(proposal_json()))
        adapter.propose(REQUEST)
        snapshot = adapter.calls
        self.assertIsInstance(snapshot, tuple)
        self.assertEqual(len(adapter.calls), 1)
        self.assertEqual(len(snapshot), 1)

    def test_a_fresh_adapter_shares_no_records_with_another(self):
        # A mutable default on a dataclass field is the classic way for two
        # instances to end up with one list. `default_factory` is not, and
        # this is the probe that says so.
        first = adapter_client.Adapter(client=object())
        second = adapter_client.Adapter(client=object())
        first._records.append("x")
        self.assertEqual(second.calls, ())

    def test_recording_sends_nothing_new(self):
        # Charter Section 3.3 and Section 4.6 fix what the adapter may be
        # told. This slice records what came back; the request must be
        # byte-identical to what it was before.
        stub = RecordingClient(response(proposal_json()))
        adapter_client.Adapter(client=stub).propose(REQUEST)
        sent = stub.calls[0]
        self.assertEqual(
            sorted(sent),
            ["max_tokens", "messages", "model", "output_config", "system", "thinking"],
        )
        self.assertEqual(sent["messages"], [{"role": "user", "content": REQUEST}])


class NothingIsDefinedAfterTheMainGuard(unittest.TestCase):
    """`unittest.main()` exits, so anything below it does not exist.

    Eleven tests were appended after the guard in this file and
    `python3 -m tests.test_adapter_client` reported 14 passing with no sign
    that the class carrying #90's client-side evidence had never been
    defined. `unittest discover` sets `__name__` to the module name, so the
    guard is false and the class appears -- which is why every registered
    check stayed green. Raised as N1 on #99 and reproduced before fixing.

    #17 rule 9: this is the check, and the diff it was written against is
    the failure it has been seen to catch.
    """

    def test_the_guard_is_the_last_thing_in_this_file(self):
        lines = pathlib.Path(__file__).read_text().splitlines()
        guards = [i for i, line in enumerate(lines) if line.startswith("if __name__ ==")]
        self.assertEqual(len(guards), 1, "expected exactly one __main__ guard")
        below = [
            line
            for line in lines[guards[0] + 1 :]
            if line and not line.startswith((" ", "\t"))
        ]
        self.assertEqual(below, [], "these are silently undefined on a direct run")


if __name__ == "__main__":
    unittest.main(verbosity=2)
