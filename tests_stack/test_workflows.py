"""`api-v0.1` Section 8: the registered rows, against the stack, over HTTP.

The acceptance row for Section 4.7 reads: "The stack provisions from a clean
state and `WF-001` to `WF-015` pass against it (`WF-016` and `WF-017` inject a
fault and run against it separately); a test that the surface process holds no
provisioning credential." This module is the first half of that sentence.

**Twelve of the fifteen rows are here.** `WF-007`, `WF-008` and `WF-009` each
drive `/v1/ask` with an *injected* proposal, and a stack has no way to inject
one: its adapter is either a real model or absent, and Section 4.3 admits no
second proposer. They run in `tests/test_api_surface.py` against an injected
proposal, which is where a fixture can be one. `WF-010` — `/v1/ask` with no
adapter configured — is here, because that is a property of the stack as
started rather than of an injection.

**Standard library only, and no import of this repository's package.** A
caller that imported `evidence_first_rag` would be exercising the code again
against the stack's database; what is being checked here is the stack, reached
the way a person reaches it. So the expected values below are written out
rather than read from the modules that produce them, which is the same reason
`tests_database/test_api_workflows.py` pins the health document as literals.

Run by the `local-stack` CI job after `docker compose up --wait`, and by the
deploy job against the deployed surface, with `EFR_STACK_URL` naming whichever
one it is. Nothing here provisions or tears down: the stack is the fixture, and
`await_health` waits for it to be serving before the first row runs.
"""

import json
import os
import time
import unittest
import urllib.error
import urllib.request

# The surface `compose.yaml` publishes. Absent, there is no stack and these
# rows were never going to run.
STACK_URL_VARIABLE = "EFR_STACK_URL"

# How long the surface is given to start answering, and how often it is asked.
#
# The local stack is healthy before its job reaches here (`compose.yaml`'s
# healthcheck, and `up --wait`), so the budget is for the deployed surface:
# `deploy.yml` restarts both apps onto a freshly pushed image and then runs
# these rows, and nothing in that job waits for the platform to finish pulling
# it. A budget is not a measurement of that platform. What it buys is that a
# start-up slower than the budget fails as itself, with `await_health`'s
# message, rather than as a WF row failing against a surface that was not
# serving yet -- which in the deploy job is a failure that rolls a correct
# deploy back (#236 B2).
READY_BUDGET_SECONDS = 600
READY_INTERVAL_SECONDS = 5

POWERTRAIN = {
    "project_code": "SAMPLE_PROJECT_ALPHA",
    "revision_label": "SAMPLE_REV_A",
    "network_name": "SAMPLE_NET_POWERTRAIN",
    "snapshot_label": "SAMPLE_SNAP_BASE",
}
CHASSIS_A = POWERTRAIN | {"network_name": "SAMPLE_NET_CHASSIS"}
# `FX-105` and `DX-011`: the scope that matches two snapshots.
UNDER_SPECIFIED = {name: value for name, value in POWERTRAIN.items() if name != "snapshot_label"}

BASE_URL = None


def setUpModule():
    """Skip where nothing could have run; **fail where it was meant to.**

    The same two branches as `tests_database`'s guard, for the same reason. No
    `EFR_STACK_URL` means no stack, and reporting these rows skipped is what is
    true. A URL that is set and unreachable is the job having started a stack
    and meant them to run: a skip there would be #101's failure, green standing
    in for rows that never executed.

    Between those two sits a state that is neither: a surface that is starting.
    `await_health` is what tells it from the second, so a stack that is coming
    up is waited for and a stack that never comes up still fails.
    """
    global BASE_URL
    configured = os.environ.get(STACK_URL_VARIABLE)
    if not configured:
        raise unittest.SkipTest(f"{STACK_URL_VARIABLE} is not set; there is no stack to drive")
    BASE_URL = configured.rstrip("/")
    await_health()


def await_health(
    *,
    budget=READY_BUDGET_SECONDS,
    interval=READY_INTERVAL_SECONDS,
    pause=time.sleep,
    clock=time.monotonic,
):
    """Poll `/v1/health` until it answers 200 with a JSON document.

    `api-v0.1` Section 4.5 makes `/v1/health` the one route that opens no
    connection, so it answers as soon as the process is serving and says nothing
    about the database -- the same reason `compose.yaml` probes it.

    Every way a surface that is not serving yet answers is retried: a refused
    connection, a status that is not 200, and a body that is not JSON, which is
    how a platform's own start-up page arrives and which `call` reports as a
    `JSONDecodeError` rather than the `OSError` a refused connection raises.

    Returns the health document. Raises `RuntimeError` naming the budget and the
    last answer when the budget runs out, which is a message no failing row
    produces.
    """
    deadline = clock() + budget
    while True:
        try:
            status, document, _ = call("/v1/health")
            if status == 200 and isinstance(document, dict):
                return document
            answer = f"HTTP {status}"
        except OSError as unreachable:
            answer = f"{type(unreachable).__name__}: {unreachable}"
        except json.JSONDecodeError as unparsable:
            answer = f"a body that is not JSON ({unparsable})"
        if clock() >= deadline:
            raise RuntimeError(
                f"{STACK_URL_VARIABLE} is {BASE_URL} and /v1/health did not answer"
                f" 200 with a JSON document within {budget}s: the stack was meant"
                f" to be running. Its last answer was {answer}."
            )
        pause(interval)


def call(path, body=None):
    """One request against the stack. Returns `(status, parsed, raw bytes)`.

    The raw bytes are returned for `WF-012`, which is a claim about bytes and
    not about a value that compares equal.
    """
    request = urllib.request.Request(
        BASE_URL + path,
        data=None if body is None else json.dumps(body).encode(),
        headers={} if body is None else {"content-type": "application/json"},
        method="GET" if body is None else "POST",
    )
    try:
        with urllib.request.urlopen(request) as response:
            raw = response.read()
            return response.status, json.loads(raw), raw
    except urllib.error.HTTPError as refused:
        raw = refused.read()
        return refused.code, json.loads(raw), raw


class StackCase(unittest.TestCase):
    """What every step of every row owes, in one place."""

    def step(self, path, body, *, status):
        """One request, its Section 4.2 envelope checked, its document returned."""
        code, document, _ = call(path, body)
        self.assertEqual(code, 200, document)
        self.assertEqual(set(document), {"result", "rendered", "contract"})
        self.assertEqual(document["result"]["status"], status)
        # Section 7's three structures, on every outcome including the
        # negative ones. Asserted here rather than only in `tests/` because
        # these are the results the provisioned data actually produces.
        for key in ("evidence_bundle", "source_trace", "limitations"):
            self.assertIn(key, document["result"])
        return document


class TheFactRoute(StackCase):
    """`WF-001`, `WF-002`, `WF-015`'s fact half, and `WF-019`."""

    def test_wf_001_the_registered_success_reaches_the_wire(self):
        document = self.step(
            "/v1/query",
            {"route": "message_facts", "arguments": POWERTRAIN | {"message_key": "SAMPLE_MSG_ENGINE_STATUS"}},
            status="success",
        )
        self.assertEqual(len(document["result"]["rows"]), 1)
        self.assertEqual(document["result"]["rows"][0]["frame_identifier"], 256)
        self.assertIsInstance(document["rendered"], str)
        self.assertNotIn("proposal", document)

    def test_wf_002_an_under_specified_scope_is_ambiguous_with_its_scopes(self):
        document = self.step(
            "/v1/query",
            {
                "route": "message_facts",
                "arguments": UNDER_SPECIFIED | {"message_key": "SAMPLE_MSG_ENGINE_STATUS"},
            },
            status="ambiguous",
        )
        result = document["result"]
        # Section 4.4: an `mvp-v0.1` ambiguous carries its scopes in the trace,
        # and the top-level `candidate_scopes` belongs to discovery alone.
        self.assertEqual(
            sorted(scope["snapshot_label"] for scope in result["source_trace"]["contributing_scopes"]),
            ["SAMPLE_SNAP_BASE", "SAMPLE_SNAP_REVISED"],
        )
        self.assertNotIn("candidate_scopes", result)

    def test_wf_015_a_network_outside_the_snapshot_is_a_coverage_gap(self):
        document = self.step(
            "/v1/query",
            {
                "route": "message_facts",
                "arguments": POWERTRAIN
                | {"network_name": "SAMPLE_NET_BODY", "message_key": "SAMPLE_MSG_ENGINE_STATUS"},
            },
            status="coverage_gap",
        )
        self.assertTrue(document["result"]["limitations"])

    def test_wf_019_a_not_found_does_not_serialize_as_an_empty_success(self):
        """The one way a negative could reach a reader as an answer."""
        document = self.step(
            "/v1/query",
            {"route": "message_facts", "arguments": POWERTRAIN | {"message_key": "SAMPLE_MSG_ABSENT"}},
            status="not_found",
        )
        result = document["result"]
        self.assertEqual(result["rows"], [])
        # The scope resolved and the template ran: "asked and found nothing",
        # which is what tells this from a request that never reached the data.
        self.assertIsNotNone(result["evidence_bundle"]["resolved_scope"])
        self.assertEqual(result["evidence_bundle"]["template_name"], "TPL_MESSAGE_FACTS_V1")
        self.assertEqual(result["evidence_bundle"]["row_count"], 0)


class TheDiscoveryRoutes(StackCase):
    """`WF-004`, `WF-005`, `WF-015`'s discovery half, `WF-020` and `WF-021`."""

    def test_wf_004_a_term_resolves_and_the_reference_then_answers(self):
        found = self.step(
            "/v1/discover",
            {"arguments": POWERTRAIN | {"entity_kind": "message", "term": "SAMPLE_MSG_ENGINE_STATUS"}},
            status="resolved",
        )
        self.assertEqual(found["result"]["resolved"]["match_tier"], 1)
        # Section 4.2: a discovery result defines no renderer.
        self.assertIsNone(found["rendered"])

        answered = self.step(
            "/v1/query",
            {
                "route": "message_facts",
                "arguments": POWERTRAIN | {"message_key": found["result"]["resolved"]["reference"]["message_key"]},
            },
            status="success",
        )
        self.assertIsInstance(answered["rendered"], str)

    def test_wf_005_an_unapproved_occurrence_ends_the_workflow(self):
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
                    status="not_found",
                )
                details = " ".join(entry["detail"] for entry in document["result"]["limitations"])
                self.assertIn("not absence from the data", details)

    def test_wf_015_a_discovery_outside_the_snapshot_is_a_coverage_gap(self):
        document = self.step(
            "/v1/discover",
            {
                "arguments": POWERTRAIN
                | {"network_name": "SAMPLE_NET_BODY", "entity_kind": "message", "term": "SAMPLE_MSG_ENGINE_STATUS"}
            },
            status="coverage_gap",
        )
        self.assertEqual(
            document["result"]["evidence_bundle"]["template_name"], "TPL_SNAPSHOT_CANDIDATES_V1"
        )

    def test_wf_020_an_under_specified_discovery_is_ambiguous_and_runs_nothing(self):
        document = self.step(
            "/v1/discover",
            {"arguments": UNDER_SPECIFIED | {"entity_kind": "message", "term": "SAMPLE_MSG_ENGINE_STATUS"}},
            status="ambiguous",
        )
        result = document["result"]
        self.assertEqual(
            sorted(scope["snapshot_label"] for scope in result["candidate_scopes"]),
            ["SAMPLE_SNAP_BASE", "SAMPLE_SNAP_REVISED"],
        )
        # `entity-discovery-v0.1` Section 4.3: no discovery template executed.
        self.assertEqual(result["evidence_bundle"]["registry_digest"], "")

    def test_wf_021_an_unknown_entity_kind_is_a_result_and_never_a_400(self):
        """An unknown enumeration value looks structural and is not, so a
        surface that refused it would drop the evidence obligation for a
        registered status family."""
        self.step(
            "/v1/discover",
            {"arguments": POWERTRAIN | {"entity_kind": "SAMPLE_KIND_FRAME", "term": "SAMPLE_TERM"}},
            status="unsupported",
        )


class TheTargetPath(StackCase):
    """`WF-003` and `WF-006`. The path this milestone exists for, against the
    data the stack provisioned, through the surface a person opens."""

    def test_wf_003_the_three_steps_reach_a_fact_carrying_its_selection(self):
        first = self.step(
            "/v1/query",
            {"route": "signal_facts", "arguments": dict(POWERTRAIN)},
            status="needs_entity_discovery",
        )
        self.assertTrue(first["result"]["limitations"])

        discovery = POWERTRAIN | {"entity_kind": "signal", "term": "SAMPLE_SIG_GEAR_POSITION"}
        second = self.step("/v1/discover", {"arguments": discovery}, status="candidates")
        candidates = second["result"]["candidates"]
        self.assertGreaterEqual(len(candidates), 2)
        # Section 4.1: `rank` is a JSON number on the way out.
        self.assertIsInstance(candidates[0]["rank"], int)
        digest = second["result"]["evidence_bundle"]["candidate_set_id"]
        self.assertTrue(digest)

        third = self.step(
            "/v1/select",
            {
                "arguments": discovery
                | {
                    "candidate_set_id": digest,
                    # Section 4.1: and its decimal text on the way back.
                    "selected_rank": str(candidates[0]["rank"]),
                    "target_route": "signal_facts",
                }
            },
            status="success",
        )
        result = third["result"]
        self.assertEqual(result["evidence_bundle"]["selection"]["selected_rank"], candidates[0]["rank"])
        self.assertTrue(result["rows"])
        self.assertTrue(result["limitations"])
        self.assertIsInstance(third["rendered"], str)

    def test_wf_006_a_stale_digest_runs_no_fact_template(self):
        document = self.step(
            "/v1/select",
            {
                "arguments": POWERTRAIN
                | {
                    "entity_kind": "signal",
                    "term": "SAMPLE_SIG_GEAR_POSITION",
                    "candidate_set_id": "b" * 64,
                    "selected_rank": "1",
                    "target_route": "signal_facts",
                }
            },
            status="invalid_request",
        )
        # A refused selection is a discovery result, not a fact one.
        self.assertIn("candidates", document["result"])
        self.assertNotIn("rows", document["result"])


class TheSurfaceProperties(StackCase):
    """`WF-010` to `WF-014`, and Section 4.6's page."""

    def test_wf_010_no_adapter_configured_refuses_and_calls_nothing(self):
        """Section 4.7 makes the credential optional, and the stack starts
        without one: every route above answered, and this one refuses.

        Until B3 on #192 this was green for the wrong reason -- the image
        carried no `anthropic`, so `serve.proposer` failed at the import and
        would have refused with a credential too. It passed either way, which
        is the #101 shape. The image now installs the adapter extra, so the
        refusal here is the *absent credential*, which is the obligation.
        """
        status, document, _ = call("/v1/ask", {"request_text": "SAMPLE_TEXT"})
        self.assertEqual(status, 503)
        self.assertEqual(set(document), {"refusal", "detail"})
        self.assertEqual(document["refusal"], "adapter_unavailable")

    def test_wf_011_the_four_surface_refusals(self):
        for name, path, body, code, kind in (
            ("not an object", "/v1/query", ["SAMPLE"], 400, "malformed_request"),
            (
                "an extra key",
                "/v1/query",
                {"route": "message_facts", "arguments": {}, "extra": "SAMPLE"},
                400,
                "malformed_request",
            ),
            ("an unknown path", "/v1/nowhere", {}, 404, "unknown_route"),
            ("a known path, wrong method", "/v1/query", None, 405, "method_not_allowed"),
        ):
            with self.subTest(case=name):
                status, document, _ = call(path, body)
                self.assertEqual(status, code, document)
                self.assertEqual(set(document), {"refusal", "detail"})
                self.assertEqual(document["refusal"], kind)
                self.assertNotIn("result", document)

    def test_wf_012_two_identical_requests_produce_identical_bytes(self):
        """Section 6, on the wire rather than over a value: identical bodies,
        compared as bytes, because that is what the contract claims."""
        body = {"route": "message_facts", "arguments": POWERTRAIN | {"message_key": "SAMPLE_MSG_ENGINE_STATUS"}}
        _, _, first = call("/v1/query", body)
        _, _, second = call("/v1/query", body)
        self.assertEqual(first, second)

    def test_wf_013_health_names_three_contracts_and_no_fourth(self):
        status, document, _ = call("/v1/health")
        self.assertEqual(status, 200)
        self.assertEqual(set(document), {"contracts", "adapter_configured"})
        # Literals, deliberately: read from the modules that produce them, this
        # would assert that a dict equals itself.
        self.assertEqual(
            document["contracts"],
            {"api-v0.1": "0.2.0", "mvp-v0.1": "0.6.1", "entity-discovery-v0.1": "0.3.1"},
        )
        # Section 4.7's optional adapter, as the stack started.
        self.assertFalse(document["adapter_configured"])

    def test_wf_014_a_non_fact_route_name_is_unsupported_and_never_a_refusal(self):
        for route in ("entity_discovery", "entity_selection", "SAMPLE_NOT_A_ROUTE"):
            with self.subTest(route=route):
                document = self.step(
                    "/v1/query",
                    {
                        "route": route,
                        "arguments": POWERTRAIN | {"message_key": "SAMPLE_MSG_ENGINE_STATUS"},
                    },
                    status="unsupported",
                )
                # Section 5: the refusal is the runtime's, at the entry point
                # it dispatched to, and not the surface's unregistered-route
                # refusal -- which is a different thing and a 404.
                self.assertEqual(document["result"]["source_trace"]["producing_layer"], "runtime")

    def test_the_page_is_served_from_the_stack(self):
        """Section 4.6. The image carries `ui/`, and an image that did not
        would serve every `/v1` route and nothing at `/`."""
        request = urllib.request.Request(BASE_URL + "/")
        with urllib.request.urlopen(request) as page:
            text = page.read().decode()
            self.assertEqual(page.status, 200)
            self.assertTrue(page.headers.get("content-type", "").startswith("text/html"))
        self.assertIn('id="discover-panel"', text)
        self.assertIn("./view.mjs", text)

    def test_the_module_the_page_imports_is_served_as_javascript(self):
        with urllib.request.urlopen(urllib.request.Request(BASE_URL + "/view.mjs")) as module:
            body = module.read().decode()
            self.assertEqual(module.status, 200)
            # A module script served as anything else is refused by the
            # browser, and the page renders nothing while every check passes.
            self.assertIn("javascript", module.headers.get("content-type", ""))
        self.assertIn("export function viewFor", body)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
