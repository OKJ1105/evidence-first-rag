"""mcp-v0.1 Sections 4.1 to 4.6 and 8: the MCP tool surface.

Section 8.1 registers the `MC-*` cases as the `api-v0.1` `WF-*` fixtures
**issued as tool calls**, with the expected `structuredContent` at each step
equal to that fixture's expected envelope. That equality is asserted here
literally: every case below sends the same body to `/v1` through the
`api-v0.1` test client and to the tool through a protocol client over
in-memory streams, over **one** `Services`, and compares the two documents.
Nothing here needs a driver, a database, a socket or a model; every step runs
against the fakes `tests/test_api_surface.py` builds, which is why they are
imported from there rather than written a second time.

What the equality proves is Section 6's second bullet -- that this is a
surface and not a second runtime. What the rest proves is what the contract
adds on top of `api-v0.1`: the `content` blocks (Section 4.2), the refusal
shape (Section 4.3), the descriptions byte for byte (Section 4.4), and that
the server declares tools and nothing else (Section 4.5).
"""

import json
import pathlib
import re
import unittest

from evidence_first_rag import Status
from evidence_first_rag.discovery import DiscoveryStatus

from .discovery_support import discovery_row
from .runtime_support import message_row, signal_row

try:
    import anyio
    import httpx2
    import mcp.types as types
    from mcp import ClientSession
    from mcp.shared.exceptions import MCPError
    from mcp.shared.memory import create_client_server_memory_streams

    from evidence_first_rag.api.app import CONTRACT_IDENTIFIER as API_IDENTIFIER
    from evidence_first_rag.api.app import CONTRACT_VERSION as API_VERSION
    from evidence_first_rag.api.app import create_app
    from evidence_first_rag.api.serialize import as_json, dumps
    from evidence_first_rag.discovery import DiscoveryRequest, SelectionRequest
    from evidence_first_rag.runtime import Request as RuntimeRequest
    from evidence_first_rag.mcp.surface import (
        CONTRACT_IDENTIFIER,
        CONTRACT_VERSION,
        DESCRIPTIONS,
        PATH,
        REFUSALS,
        TOOL_NAMES,
        TOOLS,
        call,
        create_server,
        refusal,
    )

    from .test_api_surface import (
        BASE,
        FACT_MESSAGE,
        MESSAGE,
        SELECT_TERM,
        TWO_SIGNALS,
        Exploding,
        Faulty,
        Unreachable,
        _status_cases,
        dispatches,
        envelope_of,
        fact_database,
        surface,
    )

    HAS_MCP = True
except ImportError:  # pragma: no cover - exercised by the driver-free job
    HAS_MCP = False


# Which tool a `/v1` path's fixture is issued through (Section 4.1's table).
TOOL_FOR = {"/v1/query": "query_facts", "/v1/discover": "discover_entity", "/v1/select": "select_candidate"}

CONTRACT = pathlib.Path(__file__).resolve().parents[1] / "docs" / "contracts" / "mcp-v0.1.md"


# --------------------------------------------------------------------------
# Driving the surface: a protocol client over in-memory streams.
# --------------------------------------------------------------------------


async def _with_session(services, fn):
    """`fn(session)` against a server over `services`, through the real
    protocol layer -- initialization, `tools/list`, `tools/call` -- so that
    what is asserted is what a host receives, not what a handler returned."""
    server = create_server(services)
    async with create_client_server_memory_streams() as (client_streams, server_streams):
        async with anyio.create_task_group() as group:
            group.start_soon(
                server.run, server_streams[0], server_streams[1], server.create_initialization_options()
            )
            async with ClientSession(*client_streams) as session:
                await session.initialize()
                outcome = await fn(session)
            group.cancel_scope.cancel()
    return outcome


def through(services, fn):
    return anyio.run(_with_session, services, fn)


def tool_call(services, name, arguments):
    """One tool call's result, as the client parsed it."""

    async def one(session):
        return await session.call_tool(name, arguments)

    return through(services, one)


@unittest.skipUnless(HAS_MCP, "the api extra is not installed")
class SurfaceCase(unittest.TestCase):
    """The assertions every tool result owes, in one place."""

    def assert_result(self, outcome, *, result_type):
        """Section 4.2: `isError` false, `structuredContent` the envelope,
        `content` its carriage by the result's contract."""
        self.assertIsInstance(outcome, types.CallToolResult)
        self.assertFalse(outcome.is_error)
        document = outcome.structured_content
        self.assertIsNotNone(document)
        self.assertEqual(set(document), {"result", "rendered", "contract"})
        self.assertEqual(document["contract"], {"identifier": API_IDENTIFIER, "version": API_VERSION})
        texts = [block.text for block in outcome.content]
        self.assertTrue(all(block.type == "text" for block in outcome.content))
        if result_type == "fact":
            self.assertEqual(len(texts), 2)
            self.assertEqual(texts[0], document["rendered"])
            self.assertIsInstance(document["rendered"], str)
        else:
            self.assertEqual(len(texts), 1)
            self.assertIsNone(document["rendered"])
        # The JSON block is the canonical serialization of the same document
        # -- `api-v0.1` Section 4.4's one byte representation, not a library
        # default -- and it is the last block whichever kind the result is.
        self.assertEqual(texts[-1], dumps(document))
        self.assertEqual(json.loads(texts[-1]), document)
        return document

    def assert_refusal(self, outcome, kind):
        """Section 4.3: `isError` true, one block, the fixed body, and no
        `structuredContent` -- so a host reading either field tells a refusal
        from a result by the presence of `result`."""
        self.assertIsInstance(outcome, types.CallToolResult)
        self.assertTrue(outcome.is_error)
        self.assertIsNone(outcome.structured_content)
        self.assertEqual(len(outcome.content), 1)
        body = json.loads(outcome.content[0].text)
        self.assertEqual(set(body), {"refusal", "detail"})
        self.assertEqual(body["refusal"], kind)
        self.assertIsInstance(body["detail"], str)
        self.assertNotIn("result", body)
        self.assertNotIn("status", body)

    def assert_equal_to_v1(self, services, client, path, body):
        """Section 8's equality: the tool's `structuredContent` for a body is
        the `/v1` envelope for the same body, over one `Services`."""
        expected = envelope_of(client.post(path, json=body))
        outcome = tool_call(services, TOOL_FOR[path], body)
        kind = "fact" if "rows" in expected["result"] else "discovery"
        document = self.assert_result(outcome, result_type=kind)
        self.assertEqual(document, expected)
        return document


# --------------------------------------------------------------------------
# Section 8.1: the registered cases.
# --------------------------------------------------------------------------


class TheRegisteredCases(SurfaceCase):
    """`MC-001` to `MC-006`, `MC-014`, `MC-015`, `MC-019`, `MC-021`: each the
    `WF-*` fixture of the same number, issued as tool calls, equal to `/v1`."""

    def test_mc_001_query_facts_equals_wf_001(self):
        db = fact_database({"TPL_MESSAGE_FACTS_V1": (message_row(),)})
        client, services = surface(db)
        document = self.assert_equal_to_v1(
            services, client, "/v1/query", {"route": "message_facts", "arguments": FACT_MESSAGE}
        )
        self.assertEqual(document["result"]["status"], Status.SUCCESS.value)

    def test_mc_002_an_ambiguous_fact_result_equals_wf_002_and_is_not_an_error(self):
        path, body, db = _status_cases()["ambiguous"]
        client, services = surface(db)
        document = self.assert_equal_to_v1(services, client, path, body)
        self.assertEqual(document["result"]["status"], Status.AMBIGUOUS.value)
        self.assertTrue(document["result"]["source_trace"]["contributing_scopes"])
        self.assertNotIn("candidate_scopes", document["result"])

    def test_mc_003_the_whole_target_path_as_three_tool_calls(self):
        """`WF-003`: a request naming no canonical reference, the candidate
        list, a person's choice relayed by the caller, a fact with its
        selection record. Three tool calls, three entry-point calls."""
        db = fact_database(
            {
                "TPL_SIGNAL_FACTS_V1": (
                    signal_row(message_key="SAMPLE_MSG_DIAGNOSTIC_EVENT", signal_key="SAMPLE_SIG_FAULT_CODE"),
                )
            },
            exact=TWO_SIGNALS,
        )
        client, services = surface(db)
        # The `/v1` half first, over the same services, so the equality below
        # compares like with like; the fakes are stateless, so order does not
        # change a result.
        first_v1 = envelope_of(client.post("/v1/query", json={"route": "signal_facts", "arguments": BASE}))
        second_v1 = envelope_of(client.post("/v1/discover", json={"arguments": SELECT_TERM}))
        digest = second_v1["result"]["evidence_bundle"]["candidate_set_id"]
        selection = SELECT_TERM | {"candidate_set_id": digest, "selected_rank": "2", "target_route": "signal_facts"}
        third_v1 = envelope_of(client.post("/v1/select", json={"arguments": selection}))
        before = dispatches(services)

        async def three(session):
            first = await session.call_tool("query_facts", {"route": "signal_facts", "arguments": BASE})
            second = await session.call_tool("discover_entity", {"arguments": SELECT_TERM})
            cited = second.structured_content["result"]["evidence_bundle"]["candidate_set_id"]
            third = await session.call_tool(
                "select_candidate",
                {"arguments": SELECT_TERM | {"candidate_set_id": cited, "selected_rank": "2", "target_route": "signal_facts"}},
            )
            return first, second, third

        first, second, third = through(services, three)
        self.assertEqual(self.assert_result(first, result_type="fact"), first_v1)
        self.assertEqual(first.structured_content["result"]["status"], Status.NEEDS_ENTITY_DISCOVERY.value)
        self.assertEqual(self.assert_result(second, result_type="discovery"), second_v1)
        self.assertEqual(second.structured_content["result"]["status"], DiscoveryStatus.CANDIDATES.value)
        self.assertEqual(len(second.structured_content["result"]["candidates"]), 2)
        # A dispatched selection is an `mvp-v0.1` result: two blocks.
        self.assertEqual(self.assert_result(third, result_type="fact"), third_v1)
        self.assertEqual(third.structured_content["result"]["status"], Status.SUCCESS.value)
        self.assertIsNotNone(third.structured_content["result"]["evidence_bundle"]["selection"])
        self.assertTrue(third.structured_content["result"]["limitations"])
        # Section 4.6: one entry-point call per tool call, and no discovery
        # inside the first one -- the surface never joins.
        self.assertEqual(dispatches(services) - before, 3)
        self.assertEqual(len(services.discovery.calls), 2)

    def test_mc_004_discover_resolves_then_query_answers(self):
        db = fact_database({"TPL_MESSAGE_FACTS_V1": (message_row(),)}, exact=(discovery_row(),))
        client, services = surface(db)
        found = self.assert_equal_to_v1(services, client, "/v1/discover", {"arguments": MESSAGE})
        self.assertEqual(found["result"]["status"], DiscoveryStatus.RESOLVED.value)
        answered = self.assert_equal_to_v1(
            services, client, "/v1/query", {"route": "message_facts", "arguments": FACT_MESSAGE}
        )
        self.assertEqual(answered["result"]["status"], Status.SUCCESS.value)

    def test_mc_005_discover_not_found_is_one_block_and_nothing_else_ran(self):
        db = fact_database({"TPL_MESSAGE_FACTS_V1": (message_row(),)})
        client, services = surface(db)
        document = self.assert_equal_to_v1(services, client, "/v1/discover", {"arguments": MESSAGE})
        self.assertEqual(document["result"]["status"], DiscoveryStatus.NOT_FOUND.value)
        self.assertFalse(db.ran("TPL_MESSAGE_FACTS_V1"))

    def test_mc_006_a_refused_selection_is_a_result_and_no_fact_template_ran(self):
        db = fact_database({"TPL_SIGNAL_FACTS_V1": (signal_row(),)}, exact=TWO_SIGNALS)
        client, services = surface(db)
        body = {"arguments": SELECT_TERM | {"candidate_set_id": "b" * 64, "selected_rank": "1", "target_route": "signal_facts"}}
        document = self.assert_equal_to_v1(services, client, "/v1/select", body)
        self.assertEqual(document["result"]["status"], DiscoveryStatus.INVALID_REQUEST.value)
        self.assertFalse(db.ran("TPL_SIGNAL_FACTS_V1"))

    def test_mc_014_a_registered_non_fact_route_is_unsupported_from_the_runtime(self):
        for route in ("entity_discovery", "entity_selection", "SAMPLE_NOT_A_ROUTE"):
            with self.subTest(route=route):
                db = fact_database({"TPL_MESSAGE_FACTS_V1": (message_row(),)})
                client, services = surface(db)
                document = self.assert_equal_to_v1(
                    services, client, "/v1/query", {"route": route, "arguments": FACT_MESSAGE}
                )
                self.assertEqual(document["result"]["status"], Status.UNSUPPORTED.value)
                self.assertEqual(document["result"]["source_trace"]["producing_layer"], "runtime")

    def test_mc_015_both_coverage_gaps_carry_their_entry(self):
        for name in ("coverage_gap", "discovery/coverage_gap"):
            with self.subTest(case=name):
                path, body, db = _status_cases()[name]
                client, services = surface(db)
                document = self.assert_equal_to_v1(services, client, path, body)
                self.assertEqual(document["result"]["status"], "coverage_gap")
                self.assertTrue(document["result"]["limitations"])

    def test_mc_019_a_not_found_is_not_an_error_and_not_an_empty_success(self):
        path, body, db = _status_cases()["not_found"]
        client, services = surface(db)
        document = self.assert_equal_to_v1(services, client, path, body)["result"]
        self.assertEqual(document["status"], Status.NOT_FOUND.value)
        self.assertEqual(document["rows"], [])
        self.assertTrue(document["evidence_bundle"]["template_name"])

    def test_mc_020_an_ambiguous_discovery_executes_no_template_and_is_not_an_error(self):
        path, body, db = _status_cases()["discovery/ambiguous"]
        client, services = surface(db)
        document = self.assert_equal_to_v1(services, client, path, body)["result"]
        self.assertEqual(document["status"], DiscoveryStatus.AMBIGUOUS.value)
        self.assertTrue(document["candidate_scopes"])
        self.assertFalse(db.ran("TPL_DISCOVERY_EXACT_V1"))
        self.assertFalse(db.ran("TPL_DISCOVERY_LEXICAL_V1"))

    def test_mc_021_an_unknown_entity_kind_is_a_result_and_never_an_error(self):
        path, body, db = _status_cases()["discovery/unsupported"]
        client, services = surface(db)
        document = self.assert_equal_to_v1(services, client, path, body)["result"]
        self.assertEqual(document["status"], DiscoveryStatus.UNSUPPORTED.value)
        self.assertIsNotNone(document["source_trace"]["producing_layer"])

    def test_mc_024_an_argument_outside_the_allowlist_is_the_runtimes_invalid_request(self):
        """`FX-109`'s shape: string-valued, exactly the top-level keys, so
        Section 4.3 passes it; refused by the runtime as a result carrying its
        evidence, never by the surface as a refusal. The boundary `MC-011`
        sits on the other side of."""
        db = fact_database({"TPL_MESSAGE_FACTS_V1": (message_row(),)})
        client, services = surface(db)
        for name, arguments in (
            ("a parameter of another route", FACT_MESSAGE | {"mapping_key": "SAMPLE_K"}),
            ("a name no route allows", FACT_MESSAGE | {"nonsense": "SAMPLE_X"}),
        ):
            with self.subTest(case=name):
                body = {"route": "message_facts", "arguments": arguments}
                document = self.assert_equal_to_v1(services, client, "/v1/query", body)["result"]
                self.assertEqual(document["status"], Status.INVALID_REQUEST.value)
                self.assertEqual(document["evidence_bundle"]["bound_parameters"], {})
                self.assertEqual(set(document), {"status", "rows", "evidence_bundle", "source_trace", "limitations"})
        self.assertEqual(db.sessions, 0)
        self.assertFalse(db.ran("TPL_MESSAGE_FACTS_V1"))

    def test_every_status_family_reaches_the_host_equal_to_v1(self):
        """The width of the set: every member of both vocabularies is reached
        by a case here, each equal to `/v1`, none marked an error."""
        reached = {"fact": set(), "discovery": set()}
        for name, (path, body, db) in _status_cases().items():
            with self.subTest(case=name):
                client, services = surface(db)
                document = self.assert_equal_to_v1(services, client, path, body)["result"]
                reached["discovery" if "candidates" in document else "fact"].add(document["status"])
        self.assertEqual(reached["fact"], {member.value for member in Status})
        self.assertEqual(reached["discovery"], {member.value for member in DiscoveryStatus})

    def test_the_evidence_key_sets_are_the_runtimes_own_on_every_outcome(self):
        """Section 7: the surface adds no key to, removes none from, and
        renames none in `result`. Asserted against the runtime's own result
        rather than against `/v1`, so the claim does not rest on the equality
        rows alone."""
        for name, (path, body, db) in _status_cases().items():
            with self.subTest(case=name):
                _, services = surface(db)
                own = as_json(_own_result(services, path, body))
                served = tool_call(services, TOOL_FOR[path], body).structured_content["result"]
                self.assertEqual(set(served["evidence_bundle"]), set(own["evidence_bundle"]))
                self.assertEqual(set(served["source_trace"]), set(own["source_trace"]))
                self.assertEqual(
                    [set(entry) for entry in served["limitations"]],
                    [set(entry) for entry in own["limitations"]],
                )
                self.assertEqual(served, own)


def _own_result(services, path, body):
    """The entry point's own result for a `/v1` body, called directly."""
    if path == "/v1/query":
        return services.runtime.inner.execute(RuntimeRequest(route=body["route"], arguments=body["arguments"]))
    if path == "/v1/discover":
        return services.discovery.inner.execute(DiscoveryRequest(arguments=body["arguments"]))
    return services.selection.inner.execute(SelectionRequest(arguments=body["arguments"]))


# --------------------------------------------------------------------------
# Section 4.2: the content blocks, by contract and not by tool.
# --------------------------------------------------------------------------


class TheContentBlocks(SurfaceCase):
    """`MC-022`."""

    def test_mc_022_the_block_rule_follows_the_results_key_set(self):
        """Section 4.2: decided by the key set `api-v0.1` Section 4.4 fixes --
        `rows` on one, `resolved`/`candidates`/`candidate_scopes` on the other
        -- not by the tool and not by a contract identifier inside the bundle,
        which a discovery bundle carries both of."""
        cases = dict(_status_cases())
        # `MC-006`: a refused selection through the selection tool -- the case
        # that separates the three readings. One block.
        cases["refused selection"] = (
            "/v1/select",
            {"arguments": SELECT_TERM | {"candidate_set_id": "b" * 64, "selected_rank": "1", "target_route": "signal_facts"}},
            fact_database({"TPL_SIGNAL_FACTS_V1": (signal_row(),)}, exact=TWO_SIGNALS),
        )
        for name, (path, body, db) in cases.items():
            with self.subTest(case=name):
                _, services = surface(db)
                outcome = tool_call(services, TOOL_FOR[path], body)
                result = outcome.structured_content["result"]
                kind = "fact" if "rows" in result else "discovery"
                if kind == "discovery":
                    self.assertEqual({"resolved", "candidates", "candidate_scopes"} - set(result), set())
                self.assert_result(outcome, result_type=kind)

    def test_the_rendered_block_is_verbatim_and_not_composed(self):
        """Section 4.2: not prefixed, not suffixed, not joined with the scope
        into a new sentence -- anything else would be a rendering `mvp-v0.1`
        Section 4.8 does not define."""
        db = fact_database({"TPL_MESSAGE_FACTS_V1": (message_row(),)})
        client, services = surface(db)
        rendered = envelope_of(client.post("/v1/query", json={"route": "message_facts", "arguments": FACT_MESSAGE}))["rendered"]
        outcome = tool_call(services, "query_facts", {"route": "message_facts", "arguments": FACT_MESSAGE})
        self.assertEqual(outcome.content[0].text, rendered)

    def test_a_result_carries_nothing_beyond_the_table(self):
        """No `_meta`, no annotation, no second content type (Section 4.2)."""
        _, services = surface(fact_database({"TPL_MESSAGE_FACTS_V1": (message_row(),)}))
        outcome = tool_call(services, "query_facts", {"route": "message_facts", "arguments": FACT_MESSAGE})
        self.assertIsNone(outcome.meta)
        for block in outcome.content:
            self.assertEqual(block.type, "text")
            self.assertIsNone(block.annotations)


# --------------------------------------------------------------------------
# Section 4.3: refusals.
# --------------------------------------------------------------------------


class TheRefusals(SurfaceCase):
    """`MC-011`, `MC-016`, `MC-017`, and the table itself."""

    def test_mc_011_malformed_arguments_are_refused_before_any_dispatch(self):
        _, services = surface(fact_database())
        cases = {
            "no arguments key": ("query_facts", {"route": "message_facts"}),
            "an extra key": ("query_facts", {"route": "message_facts", "arguments": {}, "extra": "SAMPLE_X"}),
            "a non-object arguments": ("query_facts", {"route": "message_facts", "arguments": "SAMPLE_X"}),
            "a numeric selected_rank": ("select_candidate", {"arguments": {**SELECT_TERM, "selected_rank": 2, "target_route": "signal_facts"}}),
            "no arguments at all": ("discover_entity", None),
        }
        for name, (tool, arguments) in cases.items():
            with self.subTest(case=name):
                self.assert_refusal(tool_call(services, tool, arguments), "malformed_request")
        self.assertEqual(dispatches(services), 0)

    def test_mc_016_an_unreachable_database_produces_no_status(self):
        _, services = surface(Unreachable())
        for tool, body in (
            ("query_facts", {"route": "message_facts", "arguments": FACT_MESSAGE}),
            ("discover_entity", {"arguments": MESSAGE}),
        ):
            with self.subTest(tool=tool):
                self.assert_refusal(tool_call(services, tool, body), "database_unavailable")

    def test_mc_017_an_injected_fault_produces_no_status(self):
        _, services = surface(Faulty(inner=fact_database({"TPL_MESSAGE_FACTS_V1": (message_row(),)})))
        outcome = tool_call(services, "query_facts", {"route": "message_facts", "arguments": FACT_MESSAGE})
        self.assert_refusal(outcome, "runtime_fault")

    def test_an_exception_no_handler_names_is_still_one_of_the_three_kinds(self):
        _, services = surface(fact_database())
        services = type(services)(runtime=Exploding(), discovery=services.discovery, selection=services.selection)
        outcome = tool_call(services, "query_facts", {"route": "message_facts", "arguments": FACT_MESSAGE})
        self.assert_refusal(outcome, "runtime_fault")
        self.assertNotIn("SAMPLE_UNEXPECTED_CONDITION", outcome.content[0].text)

    def test_the_same_fault_is_observed_identically_by_both_surfaces(self):
        """Section 4.5: one process, one `Services`. A fault injected into it
        is seen by `/v1` and by the tool as the same kind."""
        client, services = surface(Faulty(inner=fact_database({"TPL_MESSAGE_FACTS_V1": (message_row(),)})))
        body = {"route": "message_facts", "arguments": FACT_MESSAGE}
        self.assertEqual(envelope_of(client.post("/v1/query", json=body))["refusal"], "runtime_fault")
        self.assert_refusal(tool_call(services, "query_facts", body), "runtime_fault")

    def test_a_refusal_detail_names_nothing_read_off_the_call(self):
        _, services = surface(fact_database())
        outcome = tool_call(services, "query_facts", {"route": "SAMPLE_SECRET_ROUTE", "arguments": {}, "x": "SAMPLE_SECRET_VALUE"})
        self.assert_refusal(outcome, "malformed_request")
        self.assertNotIn("SAMPLE_SECRET", outcome.content[0].text)

    def test_an_unknown_tool_is_a_protocol_error_and_not_a_refusal(self):
        """Section 4.3: a name outside Section 4.1 is refused before this
        surface produces a result -- the protocol's own error, not `isError`."""
        _, services = surface(fact_database())

        async def unknown(session):
            # Caught inside the session: raised out of it, the task group would
            # wrap it, and the claim is about the error the client receives.
            try:
                await session.call_tool("SAMPLE_NOT_A_TOOL", {})
            except MCPError as error:
                return error
            return None

        error = through(services, unknown)
        self.assertIsInstance(error, MCPError)
        self.assertEqual(error.error.code, types.INVALID_PARAMS)
        self.assertEqual(dispatches(services), 0)

    def test_the_table_is_three_kinds_and_refusal_admits_no_other(self):
        self.assertEqual(REFUSALS, ("malformed_request", "database_unavailable", "runtime_fault"))
        with self.assertRaises(ValueError):
            refusal("unknown_route", "SAMPLE")


# --------------------------------------------------------------------------
# Sections 4.1, 4.4 and 4.5: the tool list, the descriptions, the server.
# --------------------------------------------------------------------------


def _contract_descriptions() -> dict:
    """Section 4.4's three blockquotes, read off the contract document."""
    text = CONTRACT.read_text()
    found = {}
    for name in ("query_facts", "discover_entity", "select_candidate"):
        match = re.search(rf"^\*\*`{name}`:\*\*\n\n((?:> .*\n?)+)", text, re.M)
        assert match is not None, f"Section 4.4 has no blockquote for {name}"
        lines = [line[2:] for line in match.group(1).splitlines()]
        found[name] = " ".join(line.strip() for line in lines).strip()
    return found


class TheToolList(SurfaceCase):
    """`MC-025`, `MC-023`."""

    def test_mc_025_tools_list_is_exactly_the_three_with_their_fixed_text(self):
        _, services = surface(fact_database())

        async def listing(session):
            return await session.list_tools()

        listed = through(services, listing).tools
        self.assertEqual([tool.name for tool in listed], ["query_facts", "discover_entity", "select_candidate"])
        for tool, expected in zip(listed, TOOLS):
            with self.subTest(tool=tool.name):
                self.assertEqual(tool.description, DESCRIPTIONS[tool.name])
                self.assertEqual(tool.input_schema, expected.input_schema)
                self.assertFalse(tool.input_schema["additionalProperties"])
                # Section 4.1: no `outputSchema`, and none of the other fields
                # a definition may carry.
                self.assertIsNone(tool.output_schema)
                self.assertIsNone(tool.title)
                self.assertIsNone(tool.annotations)
                self.assertIsNone(tool.meta)
        self.assertNotIn("ask", " ".join(tool.name for tool in listed))

    def test_the_descriptions_are_the_contracts_byte_for_byte(self):
        """Section 4.4 fixes them so that `MC-020` can read them; this is the
        reading, against the document rather than against this module."""
        self.assertEqual(DESCRIPTIONS, _contract_descriptions())

    def test_no_tool_accepts_a_key_section_4_1_does_not_name(self):
        for tool in TOOLS:
            with self.subTest(tool=tool.name):
                self.assertFalse(tool.input_schema["additionalProperties"])
                self.assertEqual(set(tool.input_schema["required"]), set(tool.input_schema["properties"]))
                self.assertEqual(tool.input_schema["properties"]["arguments"]["additionalProperties"], {"type": "string"})

    def test_the_schema_and_the_body_model_agree(self):
        """Section 4.1: one rule, stated twice -- the served schema and the
        model `_shape` validates against. A body the schema admits, the model
        admits; a body the schema rejects, the model rejects."""
        _, services = surface(fact_database())
        self.assertFalse(call(services, "query_facts", {"route": "SAMPLE_NOT_A_ROUTE", "arguments": {"a": "b"}}).is_error)
        self.assert_refusal(call(services, "query_facts", {"route": "message_facts", "arguments": {"a": 1}}), "malformed_request")

    def test_mc_023_the_server_declares_tools_and_nothing_else(self):
        _, services = surface(fact_database())

        async def initialization(session):
            return await session.initialize()

        # `initialize` already ran inside `_with_session`; a second call
        # returns the same negotiated result.
        init = through(services, initialization)
        self.assertEqual(init.server_info.name, CONTRACT_IDENTIFIER)
        self.assertEqual(init.server_info.version, CONTRACT_VERSION)
        capabilities = init.capabilities
        self.assertIsNotNone(capabilities.tools)
        self.assertIsNone(capabilities.resources)
        self.assertIsNone(capabilities.prompts)
        self.assertIsNone(capabilities.logging)
        self.assertIsNone(capabilities.completions)

    def test_no_tool_calls_the_adapter(self):
        """Section 4.1: there is no tool over `/v1/ask`. A proposer injected
        into the services is never called by any registered case."""
        calls = []

        class Proposer:
            def propose(self, request_text):
                calls.append(request_text)
                raise AssertionError("called")

        for name, (path, body, db) in _status_cases().items():
            _, services = surface(db, proposer=Proposer())
            tool_call(services, TOOL_FOR[path], body)
        self.assertEqual(calls, [])
        self.assertEqual(set(TOOL_NAMES), {"query_facts", "discover_entity", "select_candidate"})

    def test_the_version_and_identifier_are_the_ones_the_contract_declares(self):
        text = CONTRACT.read_text()
        match = re.search(r"^\*\*Version:\*\* `(\d+\.\d+\.\d+)`", text, re.M)
        self.assertIsNotNone(match)
        self.assertEqual(CONTRACT_VERSION, match.group(1))
        self.assertIn(f"**Identifier:** `{CONTRACT_IDENTIFIER}`", text)


# --------------------------------------------------------------------------
# Section 6: determinism.
# --------------------------------------------------------------------------


class Determinism(SurfaceCase):
    """`MC-012`."""

    def test_mc_012_two_identical_calls_produce_identical_results(self):
        for name, (path, body, db) in _status_cases().items():
            with self.subTest(case=name):
                _, services = surface(db)
                first = tool_call(services, TOOL_FOR[path], body)
                second = tool_call(services, TOOL_FOR[path], body)
                self.assertEqual(first.structured_content, second.structured_content)
                self.assertEqual([b.text for b in first.content], [b.text for b in second.content])


# --------------------------------------------------------------------------
# Section 4.5: the transport, mounted beside `/v1` in one process.
# --------------------------------------------------------------------------


class TheMountedTransport(SurfaceCase):
    """Streamable HTTP at `PATH`, in the `api-v0.1` app, over its lifespan."""

    def test_the_path_answers_over_http_in_the_same_app_as_v1(self):
        db = fact_database({"TPL_MESSAGE_FACTS_V1": (message_row(),)})
        client, services = surface(db)
        app = client.app
        body = {"route": "message_facts", "arguments": FACT_MESSAGE}
        expected = envelope_of(client.post("/v1/query", json=body))

        async def over_http():
            from mcp.client.streamable_http import streamable_http_client

            async with app.router.lifespan_context(app):
                transport = httpx2.ASGITransport(app=app)
                async with httpx2.AsyncClient(transport=transport, base_url="http://testserver") as http:
                    async with streamable_http_client(f"http://testserver{PATH}", http_client=http) as streams:
                        async with ClientSession(streams[0], streams[1]) as session:
                            init = await session.initialize()
                            outcome = await session.call_tool("query_facts", body)
                            return init, outcome

        init, outcome = anyio.run(over_http)
        self.assertEqual(init.server_info.name, CONTRACT_IDENTIFIER)
        self.assertEqual(self.assert_result(outcome, result_type="fact"), expected)

    def test_the_entry_point_runs_off_the_event_loop(self):
        """Section 4.5: every entry-point call opens a connection and runs
        statements, and it runs where `api-v0.1`'s handlers run theirs -- in a
        worker thread, so one slow call does not delay every other call in
        the process. Observed from the entry point: on the event loop a running
        loop is found; in a worker thread there is none."""
        import asyncio

        seen = []

        class Observing:
            fixture_provenance = ()

            def execute(self, request):
                try:
                    asyncio.get_running_loop()
                    seen.append("event loop")
                except RuntimeError:
                    seen.append("worker thread")
                raise RuntimeError("SAMPLE_STOP")

        _, services = surface(fact_database())
        services = type(services)(runtime=Observing(), discovery=services.discovery, selection=services.selection)
        tool_call(services, "query_facts", {"route": "message_facts", "arguments": FACT_MESSAGE})
        self.assertEqual(seen, ["worker thread"])

    def test_the_path_is_not_under_v1(self):
        self.assertFalse(PATH.startswith("/v1"))
        client, _ = surface(fact_database())
        self.assertIn("mcp", {getattr(route, "name", None) for route in client.app.routes})
