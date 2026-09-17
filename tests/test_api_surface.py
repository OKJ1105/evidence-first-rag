"""api-v0.1 Sections 4.1 to 4.3 and 4.5 to 7: the HTTP surface.

Section 8.1 registers twenty-two workflow fixtures and Section 8 registers a
row of tests beside them. Both are here, and none of them needs a driver, a
database, a socket or a model: every step runs against the fakes the runtime
and discovery suites already use, and every `/v1/ask` step **injects the
proposal**, which is the division Section 8.1 states.

**What a step's citation of a registered case means here.** Where a fixture
names `FX-001` or `DX-017`, this file builds that case's *shape* -- its route,
its arguments, and rows of the form the registered SQL returns -- and asserts
what the surface does with the result. The split is `mvp-v0.1`'s: `tests/`
proves the decisions given rows, `tests_database/` proves the rows.

**The second half is deferred, not done here.** The module
`test_api_workflows.py` in `tests_database/` runs the same steps against a
real PostgreSQL, but no CI job installs the `api` extra where a database is
provisioned, so it skips;
ADR-0003 records why and whose decision changes it. Read this file as evidence
for what the surface decides, and not for what the registered SQL returns.

Section 6's determinism, Section 7's evidence key sets, and Section 4.3's
"the surface never joins" are properties of this layer alone, so they are
asserted here and nowhere else.
"""

import contextlib
import dataclasses
import pathlib
import json
import unittest

from evidence_first_rag import Result, Status
from evidence_first_rag.api import as_json, dumps
from evidence_first_rag.discovery import (
    Discovery,
    DiscoveryRequest,
    DiscoveryResult,
    DiscoveryStatus,
    Selection,
    SelectionRequest,
)
from evidence_first_rag.runtime import Request, Runtime, render
from evidence_first_rag.runtime.faults import ConnectionUnavailable, Fault

from .discovery_support import BASE, MESSAGE, SIGNAL, database, discovery_row
from .runtime_support import CHASSIS, FakeDatabase, candidate_row, mapping_row, message_row, signal_row

try:
    import fastapi  # noqa: F401
    from fastapi.testclient import TestClient

    from evidence_first_rag.api.app import (
        CONTRACT_IDENTIFIER,
        CONTRACT_VERSION,
        CONTRACTS,
        REFUSALS,
        AdapterUnavailable,
        Services,
        SurfaceProposer,
        create_app,
        verbatim_arguments,
    )
    from evidence_first_rag.adapter.revalidation import Proposal

    HAS_API = True
except ImportError:  # pragma: no cover - exercised by the driver-free job
    HAS_API = False


PROVENANCE = ("fixtures/registry/approved_entity.jsonl",)

FACT_MESSAGE = BASE | {"message_key": "SAMPLE_MSG_ENGINE_STATUS"}
FACT_SIGNAL = FACT_MESSAGE | {"signal_key": "SAMPLE_SIG_ENGINE_SPEED"}

# `DX-017`'s shape: two signal candidates, the second matched by an approved
# alias, so a selection of rank 2 carries alias provenance into the fact
# result. The pair `WF-003` selects from.
TWO_SIGNALS = (
    discovery_row(
        entity_kind="signal",
        message_key="SAMPLE_MSG_TRANSMISSION_STATE",
        signal_key="SAMPLE_SIG_GEAR_POSITION",
    ),
    discovery_row(
        entity_kind="signal",
        message_key="SAMPLE_MSG_DIAGNOSTIC_EVENT",
        signal_key="SAMPLE_SIG_FAULT_CODE",
        match_tier=2,
        match_kind="approved_alias",
        match_text="SAMPLE_SIG_GEAR_POSITION",
    ),
)
SELECT_TERM = SIGNAL | {"term": "SAMPLE_SIG_GEAR_POSITION"}

# The text `WF-008`'s injected proposals are evaluated against. Its four scope
# values appear in it verbatim and its message key does not, which is what
# makes one proposal's `verbatim` list name all four and the other's name none.
ASK_TEXT = (
    "In SAMPLE_PROJECT_ALPHA SAMPLE_REV_A on SAMPLE_NET_POWERTRAIN"
    " at SAMPLE_SNAP_BASE, what is there?"
)


# --------------------------------------------------------------------------
# Building a surface.
# --------------------------------------------------------------------------


class Counting:
    """One entry point, with every call it received recorded.

    Section 4.3's `G3` is that the surface makes **at most one** entry-point
    call per request, and a promise is not a test. Wrapping the services is how
    the count becomes observable from outside the app.
    """

    def __init__(self, inner):
        self.inner = inner
        self.calls = []

    @property
    def fixture_provenance(self):
        # `adapter.answer` reads this off the runtime to build a refused
        # result's trace, so a wrapper that hid it would change what the
        # `/v1/ask` refusal path records.
        return self.inner.fixture_provenance

    def execute(self, request):
        self.calls.append(request)
        return self.inner.execute(request)


def fact_database(rows=None, *, scope=None, candidates=None, **discovery_rows):
    """One fake serving the scope query, both discovery templates and the
    fact templates, because one surface has one database behind it."""
    found = (candidate_row(scope or BASE),) if candidates is None else tuple(candidates)
    db = database(candidates=found, **discovery_rows)
    db.rows.update(rows or {})
    return db


def surface(db, *, proposer=None):
    """A client and the counted services behind it."""
    services = Services(
        runtime=Counting(Runtime(database=db, fixture_provenance=PROVENANCE)),
        discovery=Counting(Discovery(database=db, fixture_provenance=PROVENANCE)),
        selection=Counting(Selection(database=db, fixture_provenance=PROVENANCE)),
        proposer=proposer,
    )
    return TestClient(create_app(services)), services


def dispatches(services) -> int:
    return len(services.runtime.calls) + len(services.discovery.calls) + len(services.selection.calls)


@dataclasses.dataclass
class InjectedProposer:
    """What the adapter returned, supplied by the fixture (Section 8.1).

    The step is then deterministic and costs nothing, and what it tests is
    steps 2 and 3 of Section 4.3 rather than the model -- which `mvp-v0.1`
    Section 8.3 measures elsewhere.
    """

    proposal: object
    calls: list = dataclasses.field(default_factory=list)

    def propose(self, request_text):
        self.calls.append(request_text)
        return self.proposal


@dataclasses.dataclass
class FailingProposer:
    """A transport condition: the adapter could not be reached (Section 4.5)."""

    def propose(self, request_text):
        raise AdapterUnavailable("SAMPLE_TRANSPORT_CONDITION")


@dataclasses.dataclass
class Call:
    """The record `adapter.Adapter` keeps of one call, as far as
    `SurfaceProposer` reads it."""

    text: str
    stop_reason: str | None = "end_turn"


@dataclasses.dataclass
class RecordingAdapter:
    """An `Adapter` double: it returns a proposal and keeps the raw text.

    `SurfaceProposer` reads the text off the record to decide which side of
    Section 4.5's transport boundary a call fell on, so a double has to carry
    one for that decision to be exercised at all.
    """

    text: str
    proposal: object
    stop_reason: str | None = "end_turn"
    calls: tuple = ()

    def propose(self, request_text):
        self.calls = self.calls + (Call(text=self.text, stop_reason=self.stop_reason),)
        return self.proposal


# What a driver's connection error actually reads like. Carried by the fake so
# that a surface interpolating the exception into `detail` leaks it into a
# response body, and the test below sees it.
DRIVER_MESSAGE = (
    "connection to server at \"db.SAMPLE-INTERNAL.local\" (10.0.0.7), port 5432"
    " failed: FATAL: password authentication failed for user \"mvp_runtime\""
)


class Unreachable:
    """A database no session can be opened against (Section 4.5)."""

    def session(self):
        raise ConnectionUnavailable(DRIVER_MESSAGE)


@dataclasses.dataclass
class Faulty:
    """A database whose sessions open and whose statements fail.

    `WF-017`'s injected `statement_timeout`: `mvp-v0.1` Section 4.4 makes it an
    operational fault rather than a status, and `runtime/connection.py` raises
    `Fault` for exactly this. Injected at the statement rather than at the
    connection, because the two are different rows of Section 4.5's table and a
    test that conflated them would pass for a surface that did.
    """

    inner: object

    @contextlib.contextmanager
    def session(self):
        with self.inner.session() as session:
            yield FaultySession(session)


@dataclasses.dataclass
class FaultySession:
    inner: object

    @property
    def role_name(self):
        return self.inner.role_name

    @property
    def read_only_transaction(self):
        return self.inner.read_only_transaction

    def execute(self, template, arguments):
        raise Fault("SAMPLE_STATEMENT_TIMEOUT")


@dataclasses.dataclass
class Exploding:
    """An entry point that raises what no handler names.

    `runtime/connection.py` wraps two driver conditions as
    `ConnectionUnavailable` and `Fault`. A third -- and any defect in the
    surface itself -- is neither, and Section 4.5 still admits only six kinds.
    Raised from the entry point rather than patched into the app, because the
    claim under test is about what leaves the surface and not about where the
    exception came from.
    """

    fixture_provenance: tuple = PROVENANCE

    def execute(self, request):
        raise RuntimeError("SAMPLE_UNEXPECTED_CONDITION")


def envelope_of(response) -> dict:
    return json.loads(response.text)


@unittest.skipUnless(HAS_API, "the api extra is not installed")
class SurfaceCase(unittest.TestCase):
    """The assertions every result-bearing response owes, in one place."""

    def assert_result_envelope(self, response, *, proposal: bool = False):
        """Section 4.2's key table, exactly. A key not in it is a defect."""
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "application/json")
        document = envelope_of(response)
        expected = {"result", "rendered", "contract"} | ({"proposal"} if proposal else set())
        self.assertEqual(set(document), expected)
        self.assertEqual(
            document["contract"], {"identifier": CONTRACT_IDENTIFIER, "version": CONTRACT_VERSION}
        )
        return document

    def assert_refusal(self, response, kind):
        """Section 4.5: two keys, the fixed code, and no result."""
        self.assertEqual(response.status_code, REFUSALS[kind])
        document = envelope_of(response)
        self.assertEqual(set(document), {"refusal", "detail"})
        self.assertEqual(document["refusal"], kind)
        self.assertIsInstance(document["detail"], str)
        self.assertNotIn("result", document)

    def assert_carries(self, document, result):
        """Section 4.2: `result` is the whole of what the runtime returned, and
        `rendered` is the Section 4.8 answer or `null`."""
        self.assertEqual(document["result"], as_json(result))
        self.assertEqual(
            document["rendered"], render(result) if isinstance(result, Result) else None
        )


# --------------------------------------------------------------------------
# Section 4.1: the five routes and their fixed dispatch.
# --------------------------------------------------------------------------


class TheFiveRoutes(SurfaceCase):
    """`WF-001`, `WF-004`, `WF-005`, `WF-006`, `WF-013`, `WF-014`."""

    def test_wf_001_query_returns_a_fact_with_no_proposal(self):
        db = fact_database({"TPL_MESSAGE_FACTS_V1": (message_row(),)})
        client, services = surface(db)
        response = client.post("/v1/query", json={"route": "message_facts", "arguments": FACT_MESSAGE})
        document = self.assert_result_envelope(response)
        self.assertEqual(document["result"]["status"], Status.SUCCESS.value)
        # Section 4.2: `proposal` is on `/v1/ask` only, and absent elsewhere --
        # absent rather than null, which is the one place Section 4.4's
        # never-omitted rule does not reach, because it governs the result.
        self.assertNotIn("proposal", document)
        self.assertEqual(dispatches(services), 1)

    def test_wf_004_discover_resolves_then_query_answers(self):
        db = fact_database(
            {"TPL_MESSAGE_FACTS_V1": (message_row(),)}, exact=(discovery_row(),)
        )
        client, services = surface(db)
        found = self.assert_result_envelope(client.post("/v1/discover", json={"arguments": MESSAGE}))
        self.assertEqual(found["result"]["status"], DiscoveryStatus.RESOLVED.value)
        self.assertEqual(found["result"]["resolved"]["match_tier"], 1)
        # Section 4.2: a discovery result defines no renderer, so `rendered` is
        # null rather than prose the surface invented.
        self.assertIsNone(found["rendered"])

        answered = self.assert_result_envelope(
            client.post("/v1/query", json={"route": "message_facts", "arguments": FACT_MESSAGE})
        )
        self.assertEqual(answered["result"]["status"], Status.SUCCESS.value)
        self.assertIsInstance(answered["rendered"], str)

    def test_wf_005_discover_not_found_ends_the_workflow(self):
        db = fact_database({"TPL_MESSAGE_FACTS_V1": (message_row(),)})
        client, services = surface(db)
        document = self.assert_result_envelope(client.post("/v1/discover", json={"arguments": MESSAGE}))
        self.assertEqual(document["result"]["status"], DiscoveryStatus.NOT_FOUND.value)
        # "the workflow ends and nothing else was executed": the fact template
        # is loaded and was never reached.
        self.assertFalse(db.ran("TPL_MESSAGE_FACTS_V1"))
        self.assertEqual(dispatches(services), 1)

    def test_wf_006_select_refuses_and_no_fact_template_runs(self):
        # `DX-018`'s shape: a cited digest that the re-run does not derive.
        db = fact_database({"TPL_SIGNAL_FACTS_V1": (signal_row(),)}, exact=TWO_SIGNALS)
        client, _ = surface(db)
        document = self.assert_result_envelope(
            client.post(
                "/v1/select",
                json={
                    "arguments": SELECT_TERM
                    | {
                        "candidate_set_id": "b" * 64,
                        "selected_rank": "1",
                        "target_route": "signal_facts",
                    }
                },
            )
        )
        self.assertEqual(document["result"]["status"], DiscoveryStatus.INVALID_REQUEST.value)
        self.assertFalse(db.ran("TPL_SIGNAL_FACTS_V1"))

    def test_wf_013_health_names_three_contracts_and_opens_no_connection(self):
        db = fact_database()
        client, services = surface(db)
        response = client.get("/v1/health")
        self.assertEqual(response.status_code, 200)
        document = envelope_of(response)
        # Section 4.5: neither a result nor a refusal; a client has three
        # branches and tells this one by the absence of both keys.
        self.assertEqual(set(document), {"contracts", "adapter_configured"})
        self.assertNotIn("result", document)
        self.assertNotIn("refusal", document)
        self.assertEqual(
            document["contracts"],
            {"api-v0.1": "0.1.0", "mvp-v0.1": "0.6.1", "entity-discovery-v0.1": "0.3.1"},
        )
        # `export-v0.1` is not among them: it is not in this tree and no route
        # here serves one.
        self.assertNotIn("export-v0.1", document["contracts"])
        self.assertIs(document["adapter_configured"], False)
        self.assertEqual(db.sessions, 0)
        self.assertEqual(dispatches(services), 0)

    def test_health_reports_an_adapter_when_one_is_configured(self):
        client, _ = surface(fact_database(), proposer=FailingProposer())
        self.assertIs(envelope_of(client.get("/v1/health"))["adapter_configured"], True)

    def test_wf_014_a_registered_non_fact_route_on_query_is_unsupported(self):
        """Section 3.3 reading 4: `entity_discovery` and `entity_selection` are
        registered in the five-route union and are still not fact routes, so
        `/v1/query` refuses them at the entry point it dispatches to -- not as
        the unregistered-route refusal, which is a different thing."""
        for route in ("entity_discovery", "entity_selection", "SAMPLE_NOT_A_ROUTE"):
            with self.subTest(route=route):
                db = fact_database({"TPL_MESSAGE_FACTS_V1": (message_row(),)})
                client, _ = surface(db)
                document = self.assert_result_envelope(
                    client.post("/v1/query", json={"route": route, "arguments": FACT_MESSAGE})
                )
                self.assertEqual(document["result"]["status"], Status.UNSUPPORTED.value)
                self.assertEqual(document["result"]["source_trace"]["producing_layer"], "runtime")
                self.assertFalse(db.ran("TPL_MESSAGE_FACTS_V1"))
                self.assertFalse(db.ran("TPL_DISCOVERY_EXACT_V1"))


# --------------------------------------------------------------------------
# `WF-003`: the whole target path.
# --------------------------------------------------------------------------


class TheTargetPath(SurfaceCase):
    """`WF-003`. The path this milestone exists to make run end to end:
    a question that cannot be answered, candidates, a person's selection, a
    fact with its sources."""

    def setUp(self):
        self.db = fact_database(
            {
                "TPL_SIGNAL_FACTS_V1": (
                    signal_row(
                        message_key="SAMPLE_MSG_DIAGNOSTIC_EVENT",
                        signal_key="SAMPLE_SIG_FAULT_CODE",
                    ),
                )
            },
            exact=TWO_SIGNALS,
        )
        self.client, self.services = surface(self.db)

    def test_the_three_steps_reach_a_fact_with_its_selection_record(self):
        # Step 1. `FX-111`'s shape: a request naming no canonical reference.
        first = self.assert_result_envelope(
            self.client.post("/v1/query", json={"route": "signal_facts", "arguments": BASE})
        )
        self.assertEqual(first["result"]["status"], Status.NEEDS_ENTITY_DISCOVERY.value)
        # Section 4.3: "that is where the surface stops". No discovery ran.
        self.assertFalse(self.db.ran("TPL_DISCOVERY_EXACT_V1"))
        self.assertEqual(len(self.services.discovery.calls), 0)

        # Step 2. The caller issues the discovery request.
        second = self.assert_result_envelope(
            self.client.post("/v1/discover", json={"arguments": SELECT_TERM})
        )
        self.assertEqual(second["result"]["status"], DiscoveryStatus.CANDIDATES.value)
        self.assertEqual(len(second["result"]["candidates"]), 2)
        digest = second["result"]["evidence_bundle"]["candidate_set_id"]

        # Step 3. The caller cites the returned set and names one rank.
        third = self.assert_result_envelope(
            self.client.post(
                "/v1/select",
                json={
                    "arguments": SELECT_TERM
                    | {
                        "candidate_set_id": digest,
                        "selected_rank": "2",
                        "target_route": "signal_facts",
                    }
                },
            )
        )
        self.assertEqual(third["result"]["status"], Status.SUCCESS.value)
        # `entity-discovery-v0.1` Section 4.8: the dispatched selection carries
        # the `selection` record, and Section 7 carries the explicit-selection
        # entry -- cited by that description, because no contract fixes a
        # `kind` string for it.
        self.assertIsNotNone(third["result"]["evidence_bundle"]["selection"])
        self.assertEqual(third["result"]["evidence_bundle"]["selection"]["selected_rank"], 2)
        self.assertTrue(third["result"]["limitations"])
        # The tier-2 candidate was chosen, so its alias provenance travelled.
        self.assertIsNotNone(third["result"]["source_trace"]["alias_provenance"])

    def test_the_selected_rank_is_sent_back_as_decimal_text(self):
        """Section 4.1 states the asymmetry rather than leaving it to be
        discovered: a discovery response serializes `rank` as a JSON number and
        the caller sends its decimal text back."""
        candidates = envelope_of(
            self.client.post("/v1/discover", json={"arguments": SELECT_TERM})
        )["result"]["candidates"]
        rank = candidates[1]["rank"]
        self.assertIsInstance(rank, int)
        # A caller echoing the number itself is `malformed_request` by name.
        self.assert_refusal(
            self.client.post(
                "/v1/select",
                json={"arguments": {**SELECT_TERM, "selected_rank": rank, "target_route": "signal_facts"}},
            ),
            "malformed_request",
        )


# --------------------------------------------------------------------------
# Section 4.3: the natural-language route.
# --------------------------------------------------------------------------


class TheNaturalLanguageRoute(SurfaceCase):
    """`WF-007` to `WF-009` and `WF-018`, each with an injected proposal."""

    def ask(self, proposal, *, rows=None, text=ASK_TEXT, **discovery_rows):
        db = fact_database(rows or {}, **discovery_rows)
        client, services = surface(db, proposer=InjectedProposer(proposal=proposal))
        response = client.post("/v1/ask", json={"request_text": text})
        return response, db, services

    def test_wf_007_a_passing_proposal_answers_and_carries_itself(self):
        text = f"{ASK_TEXT} SAMPLE_MSG_ENGINE_STATUS"
        proposal = Proposal(route="message_facts", arguments=dict(FACT_MESSAGE))
        response, _, services = self.ask(
            proposal, rows={"TPL_MESSAGE_FACTS_V1": (message_row(),)}, text=text
        )
        document = self.assert_result_envelope(response, proposal=True)
        self.assertEqual(document["result"]["status"], Status.SUCCESS.value)
        # Section 4.2: `route` and `arguments` are the adapter's output exactly
        # as returned and before revalidation.
        self.assertEqual(document["proposal"]["route"], "message_facts")
        self.assertEqual(document["proposal"]["arguments"], dict(FACT_MESSAGE))
        self.assertEqual(document["proposal"]["verbatim"], sorted(FACT_MESSAGE))
        self.assertEqual(len(services.runtime.calls), 1)

    def test_wf_008a_a_complete_verbatim_scope_with_no_lookup_key(self):
        """An `mvp-v0.1` Section 8.3 family `D` case: the four scope values are
        present in the request text, so the verbatim check passes, and the one
        defect is the missing lookup key."""
        response, db, _ = self.ask(Proposal(route="message_facts", arguments=dict(BASE)))
        document = self.assert_result_envelope(response, proposal=True)
        self.assertEqual(document["result"]["status"], Status.NEEDS_ENTITY_DISCOVERY.value)
        self.assertEqual(document["proposal"]["verbatim"], sorted(BASE))
        self.assertFalse(db.ran("TPL_DISCOVERY_EXACT_V1"))

    def test_wf_008b_a_lookup_key_whose_scope_values_are_invented(self):
        """The `FX-112` shape: the proposal carries its lookup key and its
        scope values are absent from the request text, so the one defect is the
        verbatim check.

        **Neither status depends on the order revalidation checks in.** (a)
        passes the verbatim check and then has one defect; (b) has one defect
        and no missing key. A case with both at once would register a status
        the ordering decides, which Section 3.3 reading 3 forbids.
        """
        invented = {name: f"SAMPLE_INVENTED_{name.upper()}" for name in BASE}
        response, _, _ = self.ask(
            Proposal(route="message_facts", arguments=invented | {"message_key": "SAMPLE_MSG_ENGINE_STATUS"}),
            text=ASK_TEXT,
        )
        document = self.assert_result_envelope(response, proposal=True)
        self.assertEqual(document["result"]["status"], Status.INVALID_REQUEST.value)
        self.assertEqual(document["proposal"]["verbatim"], [])

    def test_wf_009_an_unsupported_proposal_names_the_adapter_as_the_layer(self):
        response, db, services = self.ask(Proposal(route="unsupported", arguments={}))
        document = self.assert_result_envelope(response, proposal=True)
        self.assertEqual(document["result"]["status"], Status.UNSUPPORTED.value)
        self.assertEqual(document["result"]["source_trace"]["producing_layer"], "adapter")
        # Revalidation refuses the Section 4.6 literal before anything is
        # executed, so the runtime is never reached and no connection opens.
        self.assertEqual(len(services.runtime.calls), 0)
        self.assertEqual(db.sessions, 0)

    def test_wf_018_a_proposal_outside_the_vocabulary_is_a_result_never_a_503(self):
        """Section 4.3 step 1: every parseable proposal goes to revalidation,
        including one the Section 4.6 vocabulary does not contain. Returning a
        bodiless refusal would drop the evidence obligation Section 3.3
        inherits for every negative outcome.

        **`WF-018` is outstanding and this slice does not claim it.** Its
        registered row fixes the first case's producing layer at `adapter`,
        and the `mvp-v0.1` path this route dispatches through records
        `runtime`. Which of the two is wrong is a change to an accepted
        contract under its Section 10, so it is the repository owner's
        recorded disposition and not a writer's or a test's. What is asserted
        here is the part of the row the surface decides and the disagreement
        does not touch: a 200 carrying a status and its evidence structures,
        never a 503. The layer itself is recorded, as behaviour and not as
        acceptance evidence, in the test below.
        """
        cases = {
            "route outside the vocabulary": (
                Proposal(route="SAMPLE_NOT_A_ROUTE", arguments=dict(FACT_MESSAGE)),
                Status.UNSUPPORTED,
            ),
            "argument the route does not allow": (
                Proposal(route="message_facts", arguments=dict(FACT_MESSAGE) | {"nonsense": "SAMPLE_X"}),
                Status.INVALID_REQUEST,
            ),
        }
        text = f"{ASK_TEXT} SAMPLE_MSG_ENGINE_STATUS SAMPLE_X"
        for name, (proposal, status) in cases.items():
            with self.subTest(case=name):
                response, _, _ = self.ask(proposal, text=text)
                document = self.assert_result_envelope(response, proposal=True)
                self.assertEqual(document["result"]["status"], status.value)
                # Each carries its evidence structures, which a 503 has none of.
                for key in ("evidence_bundle", "source_trace", "limitations"):
                    self.assertIn(key, document["result"])

    def test_the_layer_on_a_proposal_outside_the_vocabulary_is_the_runtimes(self):
        """Section 5: the trace is `mvp-v0.1`'s to decide and this surface's to
        carry unchanged. `runtime/request.py` reads the Section 4.6 literal as
        the adapter's own refusal and anything else as the runtime declining to
        recognise what it was sent, so a route outside the vocabulary is
        `runtime` here.

        **This contradicts `api-v0.1` Section 8.1's `WF-018` row, which says
        `adapter`.** This test records what the system does; it does not
        resolve the contradiction and must not be read as the row's acceptance
        evidence. Either that row or `mvp-v0.1`'s layer attribution has to
        change, and both are accepted contracts, so the resolution is the
        repository owner's recorded decision. Until one is recorded, `WF-018`
        is outstanding.
        """
        text = f"{ASK_TEXT} SAMPLE_MSG_ENGINE_STATUS SAMPLE_X"
        response, _, _ = self.ask(
            Proposal(route="SAMPLE_NOT_A_ROUTE", arguments=dict(FACT_MESSAGE)), text=text
        )
        document = self.assert_result_envelope(response, proposal=True)
        self.assertEqual(document["result"]["source_trace"]["producing_layer"], "runtime")
        # `invalid_request` records no layer: `mvp-v0.1` sets one for
        # `unsupported` alone, and Section 4.4's never-omitted rule makes that
        # visible as `null` rather than as a missing key. No row of Section 8.1
        # fixes this one, so it is not in dispute.
        response, _, _ = self.ask(
            Proposal(route="message_facts", arguments=dict(FACT_MESSAGE) | {"nonsense": "SAMPLE_X"}),
            text=text,
        )
        document = self.assert_result_envelope(response, proposal=True)
        self.assertIsNone(document["result"]["source_trace"]["producing_layer"])

    def test_verbatim_is_this_contracts_rule_and_not_revalidations_return(self):
        """Section 4.2 makes `verbatim` the surface's own computation. On the
        path where revalidation *passed* there is nothing to read it off, and
        that is exactly where a UI is about to offer these values as defaults
        (Section 4.6, obligation 4)."""
        text = "SAMPLE_PROJECT_ALPHA and SAMPLE_MSG_ENGINE_STATUS_EXTENDED"
        proposal = Proposal(
            route="message_facts",
            arguments={
                "project_code": "SAMPLE_PROJECT_ALPHA",
                "message_key": "SAMPLE_MSG_ENGINE_STATUS",
            },
        )
        # One value stands on its own; the other is only a prefix of a longer
        # identifier, which the rule's boundary class rejects.
        self.assertEqual(verbatim_arguments(proposal, text), ["project_code"])
        # And a mixed list is reported even though revalidation refused, so the
        # report is not derived from whether the request survived.
        response, _, _ = self.ask(proposal, text=text)
        document = self.assert_result_envelope(response, proposal=True)
        self.assertEqual(document["result"]["status"], Status.INVALID_REQUEST.value)
        self.assertEqual(document["proposal"]["verbatim"], ["project_code"])

    def test_a_proposal_whose_arguments_are_not_a_mapping_names_nothing(self):
        # Section 4.6 makes adapter output untrusted; a report on a malformed
        # proposal is the empty list, not a refusal.
        self.assertEqual(verbatim_arguments(Proposal(route="message_facts", arguments=None), "x"), [])

    def test_a_proposal_outside_the_json_vocabulary_is_still_an_envelope(self):
        """Section 4.2 puts untrusted adapter output on the wire, and
        `Adapter.read` passes `route` and a non-conforming `arguments` through
        unchanged -- so a model that answered with a number reaches this key.
        A float and a negative integer are outside what the Section 4.4
        canonical rules write; serializing one raw raises inside the handler
        and the caller gets the framework's plain-text 500, which is a non-200
        carrying neither a result nor one of Section 4.5's six refusals.
        """
        proposal = Proposal(
            route="message_facts",
            arguments={"snapshot_label": -1, "project_code": 1.5, "message_key": ["SAMPLE_A", 2]},
        )
        response, _, _ = self.ask(proposal)
        document = self.assert_result_envelope(response, proposal=True)
        # A result at 200: revalidation refuses the values, and its refusal is
        # a status family rather than a transport condition (Section 4.5).
        self.assertEqual(document["result"]["status"], Status.INVALID_REQUEST.value)
        # What the vocabulary carries is unchanged -- the string, the array,
        # the non-negative integer inside it -- and only what it cannot carry
        # becomes text. Dropping the value instead would make an off-schema
        # proposal indistinguishable from one that carried nothing.
        self.assertEqual(
            document["proposal"]["arguments"],
            {"snapshot_label": "-1", "project_code": "1.5", "message_key": ["SAMPLE_A", 2]},
        )
        self.assertEqual(document["proposal"]["verbatim"], [])

    def test_a_route_that_is_not_a_string_is_a_result_too(self):
        response, _, _ = self.ask(Proposal(route=-1, arguments={}))
        document = self.assert_result_envelope(response, proposal=True)
        self.assertEqual(document["result"]["status"], Status.UNSUPPORTED.value)
        self.assertEqual(document["proposal"]["route"], "-1")


# --------------------------------------------------------------------------
# Section 4.5: the six refusals.
# --------------------------------------------------------------------------


class TheRefusals(SurfaceCase):
    """`WF-010`, `WF-011`, `WF-016`, `WF-017`, `WF-022`, and the table itself."""

    def test_wf_010_no_adapter_configured_calls_nothing(self):
        db = fact_database({"TPL_MESSAGE_FACTS_V1": (message_row(),)})
        client, services = surface(db)
        self.assert_refusal(client.post("/v1/ask", json={"request_text": ASK_TEXT}), "adapter_unavailable")
        # Section 4.3: not the baseline, which `mvp-v0.1` Section 4.7 keeps off
        # every public interface, and not any other resolver.
        self.assertEqual(dispatches(services), 0)
        self.assertEqual(db.sessions, 0)

    def test_wf_011_the_four_surface_refusals(self):
        client, _ = surface(fact_database())
        cases = [
            ("a body that is not an object", lambda: client.request(
                "POST", "/v1/query", content=b"[]", headers={"content-type": "application/json"}
            ), "malformed_request"),
            ("a body with an extra key", lambda: client.post(
                "/v1/query", json={"route": "message_facts", "arguments": {}, "extra": "SAMPLE_X"}
            ), "malformed_request"),
            ("an unknown path", lambda: client.post("/v1/nowhere", json={}), "unknown_route"),
            ("GET on a POST route", lambda: client.get("/v1/query"), "method_not_allowed"),
        ]
        for name, call, kind in cases:
            with self.subTest(case=name):
                self.assert_refusal(call(), kind)

    def test_wf_016_an_unreachable_database_is_503_and_produces_no_status(self):
        client, _ = surface(Unreachable())
        for path, body in (
            ("/v1/query", {"route": "message_facts", "arguments": FACT_MESSAGE}),
            ("/v1/discover", {"arguments": MESSAGE}),
        ):
            with self.subTest(path=path):
                response = client.post(path, json=body)
                self.assert_refusal(response, "database_unavailable")
                self.assertNotIn("status", envelope_of(response))

    def test_wf_017_an_injected_statement_timeout_is_500_and_produces_no_status(self):
        client, _ = surface(Faulty(inner=fact_database({"TPL_MESSAGE_FACTS_V1": (message_row(),)})))
        response = client.post("/v1/query", json={"route": "message_facts", "arguments": FACT_MESSAGE})
        self.assert_refusal(response, "runtime_fault")
        self.assertNotIn("status", envelope_of(response))

    def test_wf_022_the_transport_conditions_wf_010_does_not_reach(self):
        """The dangerous direction this closes: an implementation that answered
        unparseable adapter output with a 200 result over a fabricated empty
        proposal would present a model failure as a runtime outcome."""
        unsupported = Proposal(route="unsupported", arguments={})
        cases = {
            "the call raises": FailingProposer(),
            "bytes that are not JSON": SurfaceProposer(
                adapter=RecordingAdapter(text="SAMPLE_NOT_JSON", proposal=unsupported)
            ),
            "JSON that is not an object": SurfaceProposer(
                adapter=RecordingAdapter(text="[1, 2]", proposal=unsupported)
            ),
        }
        for name, proposer in cases.items():
            with self.subTest(case=name):
                db = fact_database({"TPL_MESSAGE_FACTS_V1": (message_row(),)})
                client, services = surface(db, proposer=proposer)
                self.assert_refusal(
                    client.post("/v1/ask", json={"request_text": ASK_TEXT}), "adapter_unavailable"
                )
                self.assertEqual(dispatches(services), 0)

    def test_a_model_that_declined_is_a_proposal_and_not_a_transport_failure(self):
        """The other side of the same boundary. `stop_reason == "refusal"` is
        the model saying "no route applies", which `mvp-v0.1` Section 4.6 gives
        it a vocabulary for -- so it is a result, at 200."""
        proposer = SurfaceProposer(
            adapter=RecordingAdapter(
                text="", proposal=Proposal(route="unsupported", arguments={}), stop_reason="refusal"
            )
        )
        client, _ = surface(fact_database(), proposer=proposer)
        document = self.assert_result_envelope(
            client.post("/v1/ask", json={"request_text": ASK_TEXT}), proposal=True
        )
        self.assertEqual(document["result"]["status"], Status.UNSUPPORTED.value)

    def test_a_refusal_detail_is_never_derived_from_what_was_raised(self):
        """Section 4.5: `detail` "names no credential, host, path, or row".

        The guarantee is not that the exception happened to be harmless -- it
        is that the surface writes its own sentence. A driver's message carries
        a host, an address, a port, a role and a reason, and interpolating it
        would put all five in a response body.
        """
        client, _ = surface(Unreachable())
        response = client.post("/v1/query", json={"route": "message_facts", "arguments": FACT_MESSAGE})
        self.assert_refusal(response, "database_unavailable")
        for leaked in (
            "db.SAMPLE-INTERNAL.local", "10.0.0.7", "5432", "mvp_runtime", "password authentication"
        ):
            with self.subTest(leaked=leaked):
                self.assertNotIn(leaked, response.text)

    def test_an_unreachable_connection_is_not_a_fault(self):
        """The two are different rows of Section 4.5's table -- 503 for a
        request that never ran, 500 for one that ran and failed -- so they have
        to be distinguishable by type rather than by reading a message. If
        `ConnectionUnavailable` were a `Fault`, a tree that dropped its handler
        would answer an unreachable database with 500 and nothing would say so.
        """
        self.assertFalse(issubclass(ConnectionUnavailable, Fault))
        self.assertFalse(issubclass(Fault, ConnectionUnavailable))
        self.assertNotEqual(REFUSALS["database_unavailable"], REFUSALS["runtime_fault"])

    def test_an_exception_no_handler_names_is_still_one_of_the_six_kinds(self):
        """Section 4.5 is the whole of what a non-200 may say, so "every
        non-200 is written by `refusal`" has to be a property of the module
        rather than of the list of exceptions someone thought of. Without the
        catch-all the framework answers with plain-text `Internal Server
        Error`: a non-200 carrying neither a result nor a refusal.
        """
        services = Services(runtime=Exploding(), discovery=Exploding(), selection=Exploding())
        # The framework re-raises after this response is sent, so a server logs
        # the condition and an ordinary test still sees the exception. This
        # client asks for the response instead, which is what Section 4.5
        # governs.
        client = TestClient(create_app(services), raise_server_exceptions=False)
        response = client.post(
            "/v1/query", json={"route": "message_facts", "arguments": FACT_MESSAGE}
        )
        self.assert_refusal(response, "runtime_fault")
        self.assertEqual(response.headers["content-type"], "application/json")
        # Nothing read off what was raised, for the reason every other refusal
        # detail is the surface's own sentence.
        self.assertNotIn("SAMPLE_UNEXPECTED_CONDITION", response.text)

    def test_the_table_is_six_kinds_with_the_codes_the_contract_fixes(self):
        self.assertEqual(
            REFUSALS,
            {
                "malformed_request": 400,
                "unknown_route": 404,
                "method_not_allowed": 405,
                "adapter_unavailable": 503,
                "database_unavailable": 503,
                "runtime_fault": 500,
            },
        )

    def test_unknown_route_governs_the_v1_namespace_and_nothing_else(self):
        """Without this, Section 4.6 would oblige a UI a person opens while
        Section 4.5 turned `GET /` into a 404, and the demo Charter Section 9's
        fourth deliverable exists for could not be served at all."""
        client, _ = surface(fact_database())
        for path in ("/", "/ui", "/static/app.js"):
            with self.subTest(path=path):
                response = client.get(path)
                self.assertEqual(response.status_code, 404)
                # Neither a result nor a refusal: this contract says nothing
                # about the path, so the body claims nothing either.
                self.assertNotEqual(response.headers["content-type"], "application/json")

    def test_a_trailing_slash_under_v1_is_unknown_route_and_not_a_redirect(self):
        """Section 4.5 fixes a 200 result and six refusal codes; a 307 is
        neither, and the path it redirects to is one Section 4.1 does not
        name. The framework would answer one by default, so this is the
        assertion that the default stays off."""
        client, services = surface(fact_database({"TPL_MESSAGE_FACTS_V1": (message_row(),)}))
        for path in ("/v1/query/", "/v1/discover/", "/v1/select/", "/v1/ask/", "/v1/health/"):
            with self.subTest(path=path):
                response = client.post(
                    path, json={"route": "message_facts", "arguments": FACT_MESSAGE}
                )
                self.assert_refusal(response, "unknown_route")
        # The client follows redirects, so a surface that issued one would
        # have reached an entry point here rather than a refusal.
        self.assertEqual(dispatches(services), 0)

    def test_no_refusal_detail_names_a_host_path_or_credential(self):
        """Section 4.5: `detail` is text that names no credential, host, path,
        or row. Run through the repository's own scanner rather than a second
        list of patterns here, so the two cannot come to disagree -- and over
        every refusal the surface can produce, not a sample."""
        import sys

        sys.path.insert(0, "scripts/checks")
        import scan_sensitive_strings

        client, _ = surface(Unreachable())
        details = {
            "database_unavailable": client.post(
                "/v1/query", json={"route": "message_facts", "arguments": FACT_MESSAGE}
            ),
            "unknown_route": client.post("/v1/nowhere", json={}),
            "method_not_allowed": client.get("/v1/query"),
            "adapter_unavailable": client.post("/v1/ask", json={"request_text": ASK_TEXT}),
            "malformed_request": client.post(
                "/v1/query", json={"route": "x", "arguments": {}, "y": "z"}
            ),
        }
        client, _ = surface(Faulty(inner=fact_database({"TPL_MESSAGE_FACTS_V1": (message_row(),)})))
        details["runtime_fault"] = client.post(
            "/v1/query", json={"route": "message_facts", "arguments": FACT_MESSAGE}
        )
        # Every kind in the table is covered, so a kind added later fails here
        # until its detail has been read.
        self.assertEqual(set(details), set(REFUSALS))
        for kind, response in details.items():
            with self.subTest(kind=kind):
                self.assert_refusal(response, kind)
                failures = []
                scan_sensitive_strings.scan_text(
                    envelope_of(response)["detail"],
                    pathlib.Path("refusal-detail.txt"),
                    failures,
                )
                self.assertEqual(failures, [])


def _patterns(patterns):
    """The scan's patterns as `(name, regex)` pairs, whichever shape it keeps
    them in."""
    if isinstance(patterns, dict):
        return list(patterns.items())
    pairs = []
    for entry in patterns:
        if isinstance(entry, str):
            pairs.append((entry, entry))
        else:
            pairs.append((str(getattr(entry, "name", entry[0])), getattr(entry, "pattern", entry[-1])))
    return pairs


# --------------------------------------------------------------------------
# Section 5: every status reaches the wire as the one the runtime produced.
# --------------------------------------------------------------------------


def _status_cases():
    """One surface request per status family, keyed by the name a failure
    reports. `WF-002`, `WF-015`, `WF-019`, `WF-020` and `WF-021` are named
    rows here; the rest are the families the other fixtures reach."""
    return {
        # mvp-v0.1 Section 5, all seven.
        "success": ("/v1/query", {"route": "message_facts", "arguments": FACT_MESSAGE},
                    fact_database({"TPL_MESSAGE_FACTS_V1": (message_row(),)})),
        # `WF-019`: `FX-107`'s shape. The one way a negative could reach a
        # reader as an answer is by serializing as an empty `success`.
        "not_found": ("/v1/query", {"route": "message_facts", "arguments": FACT_MESSAGE},
                      fact_database({"TPL_MESSAGE_FACTS_V1": ()})),
        # `WF-002`: `FX-105`'s shape, two candidate scopes and no snapshot label.
        "ambiguous": ("/v1/query",
                      {"route": "message_facts",
                       "arguments": {k: v for k, v in FACT_MESSAGE.items() if k != "snapshot_label"}},
                      fact_database({})),
        # `WF-015`: `FX-106`'s shape, the one negative family no other step reaches.
        "coverage_gap": ("/v1/query",
                         {"route": "message_facts",
                          "arguments": FACT_MESSAGE | {"network_name": "SAMPLE_NET_ABSENT"}},
                         fact_database({}, candidates=())),
        "invalid_request": ("/v1/query",
                            {"route": "message_facts", "arguments": FACT_MESSAGE | {"nonsense": "SAMPLE_X"}},
                            fact_database({})),
        "unsupported": ("/v1/query", {"route": "SAMPLE_NOT_A_ROUTE", "arguments": FACT_MESSAGE},
                        fact_database({})),
        "needs_entity_discovery": ("/v1/query", {"route": "message_facts", "arguments": BASE},
                                   fact_database({})),
        # entity-discovery-v0.1 Section 5, all seven.
        "resolved": ("/v1/discover", {"arguments": MESSAGE},
                     fact_database({}, exact=(discovery_row(),))),
        "candidates": ("/v1/discover", {"arguments": SELECT_TERM},
                       fact_database({}, exact=TWO_SIGNALS)),
        "discovery/not_found": ("/v1/discover", {"arguments": MESSAGE}, fact_database({})),
        # `WF-015`'s discovery half: `DX-010`'s shape.
        "discovery/coverage_gap": ("/v1/discover",
                                   {"arguments": MESSAGE | {"network_name": "SAMPLE_NET_ABSENT"}},
                                   fact_database({}, candidates=())),
        # `WF-020`: `DX-011`'s shape. That contract's Section 4.3 executes no
        # discovery template when the scope does not resolve.
        "discovery/ambiguous": ("/v1/discover",
                                {"arguments": {k: v for k, v in MESSAGE.items() if k != "snapshot_label"}},
                                fact_database({})),
        "discovery/invalid_request": ("/v1/discover", {"arguments": MESSAGE | {"nonsense": "SAMPLE_X"}},
                                      fact_database({})),
        # `WF-021`: `DX-014`'s shape, an `entity_kind` outside the two. Never a
        # 400: an unknown enumeration value looks structural and is not, so a
        # surface that refused it would drop the evidence obligation for a
        # registered status family.
        "discovery/unsupported": ("/v1/discover", {"arguments": MESSAGE | {"entity_kind": "SAMPLE_KIND"}},
                                  fact_database({})),
    }


class StatusPassThrough(SurfaceCase):
    """`WF-002`, `WF-015`, `WF-019` to `WF-021`, and the width of the set."""

    def responses(self):
        for name, (path, body, db) in _status_cases().items():
            client, services = surface(db)
            yield name, client.post(path, json=body), db, services

    def test_every_status_reaches_the_wire_at_200(self):
        for name, response, _, _ in self.responses():
            with self.subTest(case=name):
                document = self.assert_result_envelope(response)
                self.assertEqual(document["result"]["status"], name.split("/")[-1])

    def test_the_set_reaches_every_member_of_both_vocabularies(self):
        """Section 8: "a test enumerating both vocabularies and asserting that
        every member is named by at least one registered case, so this row
        cannot silently stop being true"."""
        reached = {"fact": set(), "discovery": set()}
        for name, response, _, _ in self.responses():
            document = envelope_of(response)["result"]
            family = "discovery" if "candidates" in document else "fact"
            reached[family].add(document["status"])
        self.assertEqual(reached["fact"], {member.value for member in Status})
        self.assertEqual(reached["discovery"], {member.value for member in DiscoveryStatus})

    def test_wf_019_a_not_found_does_not_serialize_as_an_empty_success(self):
        _, (path, body, db) = "not_found", _status_cases()["not_found"]
        client, _ = surface(db)
        document = self.assert_result_envelope(client.post(path, json=body))["result"]
        self.assertEqual(document["status"], Status.NOT_FOUND.value)
        self.assertNotEqual(document["status"], Status.SUCCESS.value)
        self.assertEqual(document["rows"], [])
        # The distinguishing evidence is present, not implied by an empty list:
        # the template that ran and the scope it resolved are both on the wire,
        # which is what tells a reader "asked and found nothing" from "never
        # asked".
        self.assertTrue(document["evidence_bundle"]["template_name"])
        self.assertIsNotNone(document["evidence_bundle"]["resolved_scope"])
        self.assertEqual(document["evidence_bundle"]["row_count"], 0)

    def test_wf_020_an_ambiguous_discovery_executes_no_discovery_template(self):
        path, body, db = _status_cases()["discovery/ambiguous"]
        client, _ = surface(db)
        document = self.assert_result_envelope(client.post(path, json=body))["result"]
        self.assertEqual(document["status"], DiscoveryStatus.AMBIGUOUS.value)
        self.assertTrue(document["candidate_scopes"])
        self.assertFalse(db.ran("TPL_DISCOVERY_EXACT_V1"))
        self.assertFalse(db.ran("TPL_DISCOVERY_LEXICAL_V1"))

    def test_wf_021_an_unknown_entity_kind_is_a_result_and_never_a_400(self):
        path, body, db = _status_cases()["discovery/unsupported"]
        client, _ = surface(db)
        response = client.post(path, json=body)
        self.assertEqual(response.status_code, 200)
        document = self.assert_result_envelope(response)["result"]
        self.assertEqual(document["status"], DiscoveryStatus.UNSUPPORTED.value)
        self.assertIsNotNone(document["source_trace"]["producing_layer"])

    def test_wf_002_an_ambiguous_carries_its_scopes_inside_the_source_trace(self):
        """Section 4.4: an `mvp-v0.1` `ambiguous` carries the candidate scopes
        its Section 4.2 requires inside `source_trace.contributing_scopes`, not
        in a top-level key. The two are different keys with similar names."""
        path, body, db = _status_cases()["ambiguous"]
        client, _ = surface(db)
        document = self.assert_result_envelope(client.post(path, json=body))["result"]
        self.assertEqual(document["status"], Status.AMBIGUOUS.value)
        self.assertTrue(document["source_trace"]["contributing_scopes"])
        self.assertNotIn("candidate_scopes", document)

    def test_wf_015_both_coverage_gaps_carry_their_required_entry(self):
        for name in ("coverage_gap", "discovery/coverage_gap"):
            with self.subTest(case=name):
                path, body, db = _status_cases()[name]
                client, _ = surface(db)
                document = self.assert_result_envelope(client.post(path, json=body))["result"]
                self.assertEqual(document["status"], "coverage_gap")
                self.assertTrue(document["limitations"])


# --------------------------------------------------------------------------
# Sections 6 and 7: determinism, and the evidence that survives to the wire.
# --------------------------------------------------------------------------


class Determinism(SurfaceCase):
    """`WF-012`. Section 4.2 admits no timestamp or identifier and Section 4.4
    fixes one serialization, so the bytes are a function of the request."""

    def test_wf_012_two_identical_requests_produce_identical_bodies(self):
        for name, (path, body, db) in _status_cases().items():
            with self.subTest(case=name):
                client, _ = surface(db)
                first = client.post(path, json=body)
                second = client.post(path, json=body)
                self.assertEqual(first.content, second.content)

    def test_two_surfaces_over_the_same_state_agree_byte_for_byte(self):
        # A second app over a second database loaded the same way: the bytes
        # are a property of the request and the state, not of one process.
        path, body, _ = _status_cases()["success"]
        bodies = set()
        for _ in range(2):
            client, _ = surface(fact_database({"TPL_MESSAGE_FACTS_V1": (message_row(),)}))
            bodies.add(client.post(path, json=body).content)
        self.assertEqual(len(bodies), 1)


class TheEvidenceSurvives(SurfaceCase):
    """Section 7: the surface adds no key to a result, removes none, renames
    none, and reorders no list -- on every outcome, negative ones included."""

    def test_every_response_carries_the_runtimes_own_structures(self):
        for name, (path, body, db) in _status_cases().items():
            with self.subTest(case=name):
                client, services = surface(db)
                document = self.assert_result_envelope(client.post(path, json=body))
                entry_point = services.discovery if path == "/v1/discover" else services.runtime
                self.assertEqual(len(entry_point.calls), 1)
                # The result the entry point produced, serialized, is the
                # result on the wire -- compared as the whole document rather
                # than key by key, so a key added here would fail.
                produced = entry_point.inner.execute(entry_point.calls[0])
                self.assert_carries(document, produced)

    def test_the_three_structures_are_on_every_outcome(self):
        for name, (path, body, db) in _status_cases().items():
            with self.subTest(case=name):
                client, _ = surface(db)
                result = envelope_of(client.post(path, json=body))["result"]
                for key in ("evidence_bundle", "source_trace", "limitations"):
                    self.assertIn(key, result)

    def test_a_field_with_no_value_is_null_rather_than_absent(self):
        """Section 4.4's rule, at the surface: absence is visible rather than
        ambiguous, which is what lets the two tests above compare key sets."""
        path, body, db = _status_cases()["needs_entity_discovery"]
        client, _ = surface(db)
        bundle = envelope_of(client.post(path, json=body))["result"]["evidence_bundle"]
        self.assertIn("resolved_scope", bundle)
        self.assertIsNone(bundle["resolved_scope"])


# --------------------------------------------------------------------------
# The prohibitions.
# --------------------------------------------------------------------------


class WhatTheSurfaceNeverDoes(SurfaceCase):
    """Section 4.1's "no allowlist of its own", Section 4.3's `G3`, and the
    join the surface does not make."""

    def test_g3_at_most_one_entry_point_call_per_request(self):
        for name, (path, body, db) in _status_cases().items():
            with self.subTest(case=name):
                client, services = surface(db)
                client.post(path, json=body)
                self.assertEqual(dispatches(services), 1)

    def test_the_surface_refuses_no_route_name_and_no_argument_name(self):
        """Section 4.1: `arguments` reaches the entry point as it arrived.
        Every value below is refused *somewhere* -- but as a result at 200 by
        the contract that owns the vocabulary, never as a 400 here."""
        cases = [
            ("/v1/query", {"route": "SAMPLE_NOT_A_ROUTE", "arguments": {}}),
            ("/v1/query", {"route": "message_facts", "arguments": {"SAMPLE_NOT_A_PARAMETER": "x"}}),
            ("/v1/query", {"route": "", "arguments": {}}),
            ("/v1/discover", {"arguments": {"SAMPLE_NOT_A_PARAMETER": "x"}}),
            ("/v1/discover", {"arguments": {}}),
            ("/v1/select", {"arguments": {}}),
        ]
        for path, body in cases:
            with self.subTest(path=path, body=sorted(body)):
                client, _ = surface(fact_database({}))
                response = client.post(path, json=body)
                self.assertEqual(response.status_code, 200)
                self.assertIn("result", envelope_of(response))

    def test_a_needs_entity_discovery_response_triggers_no_discovery(self):
        """Section 4.3: "that is where the surface stops". There is no code
        path from this result to a discovery request; the caller makes it."""
        db = fact_database({}, exact=TWO_SIGNALS)
        client, services = surface(db)
        document = self.assert_result_envelope(
            client.post("/v1/query", json={"route": "message_facts", "arguments": BASE})
        )
        self.assertEqual(document["result"]["status"], Status.NEEDS_ENTITY_DISCOVERY.value)
        self.assertEqual(len(services.discovery.calls), 0)
        self.assertEqual(len(services.selection.calls), 0)
        self.assertFalse(db.ran("TPL_DISCOVERY_EXACT_V1"))
        self.assertFalse(db.ran("TPL_DISCOVERY_LEXICAL_V1"))

    def test_no_route_accepts_a_key_section_4_1_does_not_name(self):
        """Over all four bodied routes, including a key another route names --
        the case a per-route model would get right and a shared one would not."""
        bodies = {
            "/v1/query": {"route": "message_facts", "arguments": {}},
            "/v1/ask": {"request_text": "SAMPLE_TEXT"},
            "/v1/discover": {"arguments": {}},
            "/v1/select": {"arguments": {}},
        }
        for path, body in bodies.items():
            for intruder in ("request_text", "route", "arguments", "SAMPLE_UNKNOWN"):
                if intruder in body:
                    continue
                with self.subTest(path=path, key=intruder):
                    client, services = surface(fact_database({}))
                    response = client.post(path, json={**body, intruder: "SAMPLE_VALUE"})
                    self.assert_refusal(response, "malformed_request")
                    self.assertEqual(dispatches(services), 0)

    def test_a_missing_key_and_a_non_string_value_are_both_structural(self):
        client, _ = surface(fact_database({}))
        for body in (
            {"arguments": {}},                                   # /v1/query, no route
            {"route": "message_facts"},                          # no arguments
            {"route": 3, "arguments": {}},                       # route not a string
            {"route": "message_facts", "arguments": {"a": 3}},   # a value not a string
            {"route": "message_facts", "arguments": []},         # arguments not an object
        ):
            with self.subTest(body=sorted(body)):
                self.assert_refusal(client.post("/v1/query", json=body), "malformed_request")


class NoFrameworkDefaultEscapes(SurfaceCase):
    """The framework is a router and a body parser. None of its defaults is
    this contract's vocabulary, so none of them may reach a caller."""

    def test_no_response_carries_a_list_valued_detail(self):
        """FastAPI's validation failure is HTTP 422 with a list-valued
        `detail` naming the field that failed. Section 4.5 fixes 400 with a
        string one, and a refusal that quoted the request would put a value
        read off it into the body."""
        client, _ = surface(fact_database({}))
        responses = [
            client.post("/v1/query", json={"route": "message_facts", "arguments": {}, "x": 1}),
            client.post("/v1/ask", json={}),
            client.request("POST", "/v1/discover", content=b"not json",
                           headers={"content-type": "application/json"}),
            client.post("/v1/nowhere", json={}),
            client.get("/v1/discover"),
        ]
        for response in responses:
            with self.subTest(status=response.status_code):
                self.assertNotEqual(response.status_code, 422)
                document = envelope_of(response)
                self.assertIsInstance(document["detail"], str)
                self.assertEqual(set(document), {"refusal", "detail"})

    def test_a_malformed_body_is_never_quoted_back(self):
        client, _ = surface(fact_database({}))
        secret = "SAMPLE_VALUE_THAT_MUST_NOT_BE_ECHOED"
        response = client.post("/v1/query", json={"route": "message_facts", "arguments": {}, "x": secret})
        self.assert_refusal(response, "malformed_request")
        self.assertNotIn(secret, response.text)

    def test_the_body_is_this_contracts_serialization_and_not_a_library_default(self):
        """Section 6's byte identity is a claim about an escape set and a key
        order. `json.dumps` defaults would give neither."""
        path, body, db = _status_cases()["success"]
        client, _ = surface(db)
        response = client.post(path, json=body)
        document = envelope_of(response)
        # The body is what `dumps` writes, and nothing else wrote it.
        self.assertEqual(response.text, dumps(document))
        # Python's own default would separate with spaces and escape non-ASCII;
        # asserting the two differ is what makes this test fail for a surface
        # that handed the document to a library serializer.
        self.assertNotEqual(response.text, json.dumps(document, sort_keys=True))
        # Keys byte-wise sorted, asserted at the top level where every key is
        # this contract's own. A rendered answer carries prose, so a search for
        # `", "` over the whole body would be testing the answer instead.
        top_level = [key for key in document]
        self.assertEqual(
            [response.text.index(f'"{key}":') for key in sorted(top_level)],
            sorted(response.text.index(f'"{key}":') for key in top_level),
        )

    def test_a_non_ascii_value_travels_as_utf_8_rather_than_escaped(self):
        """`ensure_ascii` would hide the text inside `\\uXXXX` escapes, which
        `dumps` does not do and Section 4.4 does not permit."""
        # Asserted over a value the wire really carries: a `term` is normalized
        # before it is bound, so the non-ASCII text reaches a response as the
        # candidate's `matched_text`. An assertion over a `SAMPLE_*` identifier
        # would pass under either setting.
        term = "SAMPLE_TERM_\u00c9"
        client, _ = surface(
            fact_database({}, exact=(discovery_row(match_text=term),))
        )
        response = client.post("/v1/discover", json={"arguments": MESSAGE | {"term": term}})
        self.assertEqual(response.status_code, 200)
        self.assertIn(term, response.text)
        self.assertNotIn("\\u00c9", response.text)
