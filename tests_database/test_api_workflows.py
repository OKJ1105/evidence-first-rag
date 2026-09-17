"""api-v0.1 Section 8.1: the workflow fixtures, over HTTP, against a real
PostgreSQL database.

`tests/test_api_surface.py` proves the surface's decisions given results. This
file is where the steps whose expected value is a **registered** `FX-*` or
`DX-*` outcome are proved: Section 8.1 says a fixture citing one of those
cases takes "that case's registered result, serialized", and only the
registered data can supply it. The division is `mvp-v0.1`'s, and it is why
both files exist.

`WF-003` is why this file matters more than its size suggests. It is the whole
target path -- a request that names no canonical reference, the candidate list
that follows, a caller's selection, and a fact with its sources -- and until
this module ran it had never gone end to end against real rows through the
surface a reader would use.

Not here: `WF-007` to `WF-010`, `WF-017`, `WF-018` and `WF-022`, which inject a
proposal or a fault and so assert nothing about what the database returns; they
are in `tests/`. `WF-011` and `WF-014` are refusals decided before any
connection opens and are there too.

**This module runs in `database-checks`**, which installs the `api` extra --
the repository owner's recorded decision on #179, made after an earlier
revision of this file had to defer these rows for want of it. The skip below
fires only outside that job, where there is no database to run against.
"""

import json
import os
import unittest

from evidence_first_rag import Status
from evidence_first_rag.discovery import DiscoveryStatus
from evidence_first_rag.runtime.connection import PsycopgDatabase

from . import guards, support

try:
    from fastapi.testclient import TestClient

    from evidence_first_rag.api import as_json
    from evidence_first_rag.api.app import CONTRACT_IDENTIFIER, CONTRACT_VERSION, create_app, services

    HAS_API = True
except ImportError:  # pragma: no cover - exercised by the driver-free job
    HAS_API = False

DATABASE = "mvp_test_api"

POWERTRAIN = {
    "project_code": "SAMPLE_PROJECT_ALPHA",
    "revision_label": "SAMPLE_REV_A",
    "network_name": "SAMPLE_NET_POWERTRAIN",
    "snapshot_label": "SAMPLE_SNAP_BASE",
}
CHASSIS_A = POWERTRAIN | {"network_name": "SAMPLE_NET_CHASSIS"}

PROVENANCE = (
    "fixtures/source_snapshot.jsonl",
    "fixtures/message_occurrence.jsonl",
    "fixtures/signal_occurrence.jsonl",
    "fixtures/signal_mapping.jsonl",
    "fixtures/registry/approved_entity.jsonl",
    "fixtures/registry/approved_alias.jsonl",
)


# This fires only where the rows were never going to run anyway -- a checkout
# with no database. It is not the #101 failure, which is a skip standing in
# for evidence something claimed: `database-checks` installs the extra and
# executes this module, so the rows below are discharged rather than deferred.
def setUpModule():
    """Skip where nothing could have run; **fail where it was meant to.**

    Thirteen registered Section 8.1 rows live here -- `WF-003` among them --
    and every one of them is reported by a single install line in a workflow
    file. Drop `.[api]` from it and this module skips, a skip is green, and
    nothing anywhere says the rows stopped running.

    An earlier revision skipped in both cases, correctly at the time: that
    install line was not a change a writer session could make, and a job red on
    every run for a reason nobody on the branch may fix is not evidence either.
    The repository owner recorded the line on #179, so that reason is gone.

    The decision itself is `guards.missing_dependency`, which needs neither a
    driver nor a database, so `tests/test_suite_layout.py` asserts all three of
    its branches in every job rather than leaving them to be observed here.
    """
    outcome = guards.missing_dependency(
        installed=HAS_API, provisioned=bool(os.environ.get("MVP_RUNTIME_PASSWORD"))
    )
    if outcome is not None:
        raise outcome
    support.build(DATABASE)


def tearDownModule():
    if HAS_API:
        support.drop(DATABASE)


def connection_parameters(database=DATABASE, **overrides):
    return {
        "dbname": database,
        "user": "mvp_runtime",
        "password": os.environ["MVP_RUNTIME_PASSWORD"],
        "host": os.environ.get("PGHOST"),
        "port": os.environ.get("PGPORT"),
    } | overrides


def client(**overrides):
    """The surface over the provisioned database, as the runtime identity.

    No adapter: Section 4.7 makes the credential optional and every route but
    `/v1/ask` works without one, and an `/v1/ask` step here would call a model.
    """
    return TestClient(
        create_app(
            services(
                PsycopgDatabase(connection_parameters=connection_parameters(**overrides)),
                fixture_provenance=PROVENANCE,
            )
        )
    )


@unittest.skipUnless(HAS_API, "the api extra is not installed")
class WorkflowCase(unittest.TestCase):
    """What every step of every fixture owes, in one place."""

    @classmethod
    def setUpClass(cls):
        cls.client = client()

    def step(self, path, body, *, status):
        """One request, its Section 4.2 envelope checked, its result returned."""
        response = self.client.post(path, json=body)
        self.assertEqual(response.status_code, 200, response.text)
        document = json.loads(response.text)
        self.assertEqual(set(document), {"result", "rendered", "contract"})
        result = document["result"]
        self.assertEqual(result["status"], status)
        # Section 7: the three structures on every outcome, negative ones
        # included -- asserted here rather than only in `tests/`, because these
        # are the results the registered data actually produces.
        for key in ("evidence_bundle", "source_trace", "limitations"):
            self.assertIn(key, result)
        return document


class TheFactRoute(WorkflowCase):
    """`WF-001`, `WF-002`, `WF-015` and `WF-019` over the registered cases."""

    def test_wf_001_fx_001_reaches_the_wire_as_the_registered_success(self):
        document = self.step(
            "/v1/query",
            {"route": "message_facts", "arguments": POWERTRAIN | {"message_key": "SAMPLE_MSG_ENGINE_STATUS"}},
            status=Status.SUCCESS.value,
        )
        # `FX-001`'s registered assertions, read off the serialized result.
        self.assertEqual(len(document["result"]["rows"]), 1)
        self.assertEqual(document["result"]["rows"][0]["frame_identifier"], 256)
        self.assertIsInstance(document["rendered"], str)
        self.assertNotIn("proposal", document)

    def test_wf_002_fx_105_carries_its_scopes_in_the_source_trace(self):
        arguments = {k: v for k, v in POWERTRAIN.items() if k != "snapshot_label"}
        document = self.step(
            "/v1/query",
            {"route": "message_facts", "arguments": arguments | {"message_key": "SAMPLE_MSG_ENGINE_STATUS"}},
            status=Status.AMBIGUOUS.value,
        )
        result = document["result"]
        # Section 4.4: the candidate scopes an `mvp-v0.1` `ambiguous` requires
        # live in `source_trace.contributing_scopes`, and the top-level
        # `candidate_scopes` belongs to a discovery result alone.
        self.assertEqual(
            sorted(scope["snapshot_label"] for scope in result["source_trace"]["contributing_scopes"]),
            ["SAMPLE_SNAP_BASE", "SAMPLE_SNAP_REVISED"],
        )
        self.assertNotIn("candidate_scopes", result)
        self.assertIsNone(result["evidence_bundle"]["resolved_scope"])

    def test_wf_015_fx_106_is_a_coverage_gap_with_its_entry(self):
        document = self.step(
            "/v1/query",
            {
                "route": "message_facts",
                "arguments": POWERTRAIN
                | {"network_name": "SAMPLE_NET_BODY", "message_key": "SAMPLE_MSG_ENGINE_STATUS"},
            },
            status=Status.COVERAGE_GAP.value,
        )
        self.assertTrue(document["result"]["limitations"])
        self.assertIsNone(document["result"]["evidence_bundle"]["resolved_scope"])

    def test_wf_019_fx_107_does_not_serialize_as_an_empty_success(self):
        """The one way a negative could reach a reader as an answer."""
        document = self.step(
            "/v1/query",
            {"route": "message_facts", "arguments": POWERTRAIN | {"message_key": "SAMPLE_MSG_ABSENT"}},
            status=Status.NOT_FOUND.value,
        )
        result = document["result"]
        self.assertEqual(result["rows"], [])
        self.assertNotEqual(result["status"], Status.SUCCESS.value)
        # The scope resolved and the template ran: "asked and found nothing",
        # which is what tells this from a request that never reached the data.
        self.assertIsNotNone(result["evidence_bundle"]["resolved_scope"])
        self.assertEqual(result["evidence_bundle"]["template_name"], "TPL_MESSAGE_FACTS_V1")
        self.assertEqual(result["evidence_bundle"]["row_count"], 0)


class TheDiscoveryRoutes(WorkflowCase):
    """`WF-004`, `WF-005`, `WF-015`'s discovery half, `WF-020` and `WF-021`."""

    def test_wf_004_dx_001_resolves_then_the_reference_answers(self):
        found = self.step(
            "/v1/discover",
            {"arguments": POWERTRAIN | {"entity_kind": "message", "term": "SAMPLE_MSG_ENGINE_STATUS"}},
            status=DiscoveryStatus.RESOLVED.value,
        )
        self.assertEqual(found["result"]["resolved"]["match_tier"], 1)
        # Section 4.2: a discovery result defines no renderer.
        self.assertIsNone(found["rendered"])
        reference = found["result"]["resolved"]["reference"]

        answered = self.step(
            "/v1/query",
            {
                "route": "message_facts",
                "arguments": POWERTRAIN | {"message_key": reference["message_key"]},
            },
            status=Status.SUCCESS.value,
        )
        self.assertIsInstance(answered["rendered"], str)

    def test_wf_005_dx_015_ends_the_workflow_in_the_registry(self):
        """The registry is an allowlist: the occurrence is in the loaded data
        and not approved, and the result says the second without claiming the
        first."""
        for kind, term, scope in (
            ("message", "SAMPLE_MSG_DIAGNOSTIC_EVENT", POWERTRAIN),
            ("signal", "SAMPLE_SIG_WHEEL_SPEED_FR", CHASSIS_A),
        ):
            with self.subTest(kind=kind):
                document = self.step(
                    "/v1/discover",
                    {"arguments": scope | {"entity_kind": kind, "term": term}},
                    status=DiscoveryStatus.NOT_FOUND.value,
                )
                details = " ".join(entry["detail"] for entry in document["result"]["limitations"])
                self.assertIn("not absence from the data", details)

    def test_wf_015_dx_010_is_a_coverage_gap(self):
        document = self.step(
            "/v1/discover",
            {
                "arguments": POWERTRAIN
                | {"network_name": "SAMPLE_NET_BODY", "entity_kind": "message", "term": "SAMPLE_MSG_ENGINE_STATUS"}
            },
            status=DiscoveryStatus.COVERAGE_GAP.value,
        )
        self.assertEqual(document["result"]["evidence_bundle"]["template_name"], "TPL_SNAPSHOT_CANDIDATES_V1")

    def test_wf_020_dx_011_is_ambiguous_with_its_scopes_and_no_discovery(self):
        arguments = {k: v for k, v in POWERTRAIN.items() if k != "snapshot_label"}
        document = self.step(
            "/v1/discover",
            {"arguments": arguments | {"entity_kind": "message", "term": "SAMPLE_MSG_ENGINE_STATUS"}},
            status=DiscoveryStatus.AMBIGUOUS.value,
        )
        result = document["result"]
        self.assertEqual(
            sorted(scope["snapshot_label"] for scope in result["candidate_scopes"]),
            ["SAMPLE_SNAP_BASE", "SAMPLE_SNAP_REVISED"],
        )
        # That contract's Section 4.3: no discovery template executed.
        self.assertEqual(result["evidence_bundle"]["template_name"], "TPL_SNAPSHOT_CANDIDATES_V1")
        self.assertEqual(result["evidence_bundle"]["registry_digest"], "")

    def test_wf_021_dx_014_is_a_result_and_never_a_400(self):
        """An unknown enumeration value looks structural and is not, so a
        surface that refused it would drop the evidence obligation for a
        registered status family."""
        document = self.step(
            "/v1/discover",
            {"arguments": POWERTRAIN | {"entity_kind": "SAMPLE_KIND_FRAME", "term": "SAMPLE_TERM"}},
            status=DiscoveryStatus.UNSUPPORTED.value,
        )
        self.assertEqual(document["result"]["source_trace"]["producing_layer"], "runtime")
        self.assertIs(
            document["result"]["evidence_bundle"]["read_only_safeguards"]["connection_opened"], False
        )


class TheTargetPath(WorkflowCase):
    """`WF-003`. The path this milestone exists for, against the registered
    data, through the surface a reader would use."""

    def test_the_three_steps_reach_a_fact_carrying_its_selection(self):
        # Step 1. `FX-111`'s shape: a complete scope and no lookup key, so no
        # canonical reference can be formed.
        first = self.step(
            "/v1/query",
            {"route": "signal_facts", "arguments": dict(POWERTRAIN)},
            status=Status.NEEDS_ENTITY_DISCOVERY.value,
        )
        self.assertTrue(first["result"]["limitations"])

        # Step 2. The caller issues the discovery request. `DX-004`'s
        # collision: one entity's lookup key is another's approved alias.
        discovery = POWERTRAIN | {"entity_kind": "signal", "term": "SAMPLE_SIG_GEAR_POSITION"}
        second = self.step(
            "/v1/discover", {"arguments": discovery}, status=DiscoveryStatus.CANDIDATES.value
        )
        candidates = second["result"]["candidates"]
        self.assertGreaterEqual(len(candidates), 2)
        # Section 4.1: `rank` is a JSON number on the way out and its decimal
        # text on the way back.
        self.assertIsInstance(candidates[0]["rank"], int)
        digest = second["result"]["evidence_bundle"]["candidate_set_id"]
        self.assertTrue(digest)

        # Step 3. The caller cites the set it was given and names one rank.
        third = self.step(
            "/v1/select",
            {
                "arguments": discovery
                | {
                    "candidate_set_id": digest,
                    "selected_rank": str(candidates[0]["rank"]),
                    "target_route": "signal_facts",
                }
            },
            status=Status.SUCCESS.value,
        )
        result = third["result"]
        # `entity-discovery-v0.1` Section 4.8's record, and Section 7's
        # explicit-selection entry beside it.
        self.assertIsNotNone(result["evidence_bundle"]["selection"])
        self.assertEqual(result["evidence_bundle"]["selection"]["selected_rank"], candidates[0]["rank"])
        self.assertTrue(result["limitations"])
        self.assertTrue(result["rows"])
        self.assertIsInstance(third["rendered"], str)

    def test_wf_006_dx_018_a_stale_digest_runs_no_fact_template(self):
        discovery = POWERTRAIN | {"entity_kind": "signal", "term": "SAMPLE_SIG_GEAR_POSITION"}
        document = self.step(
            "/v1/select",
            {
                "arguments": discovery
                | {"candidate_set_id": "b" * 64, "selected_rank": "1", "target_route": "signal_facts"}
            },
            status=DiscoveryStatus.INVALID_REQUEST.value,
        )
        # A refused selection is this contract's result, not a fact one: it
        # carries `candidates`, which `as_json` makes the discriminator.
        self.assertIn("candidates", document["result"])
        self.assertNotIn("rows", document["result"])


class TheSurfaceProperties(WorkflowCase):
    """`WF-012`, `WF-013`, and Section 7 over the registered results."""

    def test_wf_012_two_identical_requests_produce_identical_bodies(self):
        body = {"route": "message_facts", "arguments": POWERTRAIN | {"message_key": "SAMPLE_MSG_ENGINE_STATUS"}}
        first = self.client.post("/v1/query", json=body)
        second = self.client.post("/v1/query", json=body)
        self.assertEqual(first.content, second.content)

    def test_wf_013_health_names_three_contracts_and_opens_no_connection(self):
        # Pointed at a port nothing listens on, so a probe that opened a
        # connection would fail rather than quietly succeed.
        probe = client(port="1")
        response = probe.get("/v1/health")
        self.assertEqual(response.status_code, 200)
        document = json.loads(response.text)
        self.assertEqual(set(document), {"contracts", "adapter_configured"})
        self.assertEqual(
            document["contracts"],
            {CONTRACT_IDENTIFIER: CONTRACT_VERSION, "mvp-v0.1": "0.6.1", "entity-discovery-v0.1": "0.3.1"},
        )
        self.assertIs(document["adapter_configured"], False)

    def test_wf_016_an_unreachable_database_is_503_with_no_result(self):
        unreachable = client(port="1")
        for path, body in (
            ("/v1/query", {"route": "message_facts", "arguments": POWERTRAIN | {"message_key": "SAMPLE_MSG_ENGINE_STATUS"}}),
            ("/v1/discover", {"arguments": POWERTRAIN | {"entity_kind": "message", "term": "SAMPLE_MSG_ENGINE_STATUS"}}),
        ):
            with self.subTest(path=path):
                response = unreachable.post(path, json=body)
                self.assertEqual(response.status_code, 503)
                document = json.loads(response.text)
                self.assertEqual(set(document), {"refusal", "detail"})
                self.assertEqual(document["refusal"], "database_unavailable")
                # Section 4.5: the detail names no host, port or credential --
                # and this request had a real one to leak.
                for secret in (os.environ["MVP_RUNTIME_PASSWORD"], "mvp_runtime", DATABASE):
                    self.assertNotIn(secret, response.text)

    def test_section_7_the_wire_result_is_the_runtimes_own(self):
        """The surface adds no key, removes none, renames none, reorders no
        list -- asserted against the result the entry point produced, over the
        registered data rather than over a fake."""
        from evidence_first_rag.runtime import Request, Runtime

        arguments = POWERTRAIN | {"message_key": "SAMPLE_MSG_ENGINE_STATUS"}
        produced = Runtime(
            database=PsycopgDatabase(connection_parameters=connection_parameters()),
            fixture_provenance=PROVENANCE,
        ).execute(Request(route="message_facts", arguments=arguments))
        document = self.step(
            "/v1/query", {"route": "message_facts", "arguments": arguments}, status=Status.SUCCESS.value
        )
        self.assertEqual(document["result"], as_json(produced))
