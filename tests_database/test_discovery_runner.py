"""entity-discovery-v0.1 Sections 4.10 and 4.11: a run against the registered
fixtures.

`tests/test_discovery_runner.py` proves what the runner records given rows;
this proves the numbers over the real registry, through the real templates
and the real selection path. The cases here are **authored by this test**,
and are not the Section 8.3 set: they exercise the runner against a real
database, which the registered set is not yet wired to. One case per class,
deliberately below rule 4's five -- and the artifact says so, which is the
assertion at the end.

**One authoring constraint this set ran into, recorded for the registration
slice.** Rule 6 is "No two case texts are equal after the Section 4.5
normalization", and it is over the whole set, not per class. The obvious
first draft used `SAMPLE_MSG_ENGINE_STATUS` as the term for Q-EXACT,
Q-COLLIDE, Q-SCOPE and Q-OUT -- four different *requests*, differing in
scope or kind, but one *text* -- and the rule refused it. So a registration
has to give each case its own term: Q-COLLIDE here names a key that exists
in two CHASSIS snapshots rather than reusing Q-EXACT's, and Q-SCOPE and
Q-OUT name different entities again. That is the rule working, not a defect
in it: two cases with one text measure the same retrieval twice.
"""

import contextlib
import io
import json
import os
import pathlib
import tempfile
import unittest
import unittest.mock

from evidence_first_rag import MessageReference, Route, SignalReference, SnapshotScope
from evidence_first_rag.discovery import REGISTERED_SET, Discovery, EvaluationCase, Selection
from evidence_first_rag.discovery.evaluation import REGISTERED_AGAINST_DIGEST, THRESHOLDS
from evidence_first_rag.discovery.request import DiscoveryRequest
from evidence_first_rag.discovery.runner import FIXTURE_PROVENANCE, main, perform
from evidence_first_rag.runtime.connection import PsycopgDatabase

from . import support

DATABASE = "mvp_test_discovery_runner"

POWERTRAIN = {
    "project_code": "SAMPLE_PROJECT_ALPHA", "revision_label": "SAMPLE_REV_A",
    "network_name": "SAMPLE_NET_POWERTRAIN", "snapshot_label": "SAMPLE_SNAP_BASE",
}
REVISED = POWERTRAIN | {"snapshot_label": "SAMPLE_SNAP_REVISED"}
CHASSIS_B = POWERTRAIN | {"revision_label": "SAMPLE_REV_B", "network_name": "SAMPLE_NET_CHASSIS"}
SCOPE = SnapshotScope(**POWERTRAIN)
REVISED_SCOPE = SnapshotScope(**REVISED)
CHASSIS_B_SCOPE = SnapshotScope(**CHASSIS_B)


def message(scope, key):
    return MessageReference(scope=scope, message_key=key)


def signal(scope, parent, key):
    return SignalReference(message=message(scope, parent), signal_key=key)


def setUpModule():
    support.build(DATABASE)


def tearDownModule():
    support.drop(DATABASE)


def database():
    return PsycopgDatabase(connection_parameters={
        "dbname": DATABASE, "user": "mvp_runtime", "password": os.environ["MVP_RUNTIME_PASSWORD"],
        "host": os.environ.get("PGHOST"), "port": os.environ.get("PGPORT"),
    })


def registry_state():
    with support.connect(DATABASE, "runtime") as connection, connection.cursor() as cursor:
        cursor.execute("SELECT registry_digest, built_at FROM mvp.entity_registry_state")
        digest, built_at = cursor.fetchone()
    return {"registry_digest": digest, "registry_built_at": built_at.strftime("%Y-%m-%dT%H:%M:%SZ")}


# One case per class, over the registered fixtures. Each is written from what
# fixtures/registry/README.md says the rows make reachable.
CASES = (
    EvaluationCase(
        identifier="SAMPLE-EXACT-1", query_class="Q-EXACT",
        arguments=POWERTRAIN | {"entity_kind": "message", "term": "SAMPLE_MSG_ENGINE_STATUS"},
        expected_outcome="resolved",
        expected_references=(message(SCOPE, "SAMPLE_MSG_ENGINE_STATUS"),),
        target_route=Route.MESSAGE_FACTS,
    ),
    EvaluationCase(
        identifier="SAMPLE-ALIAS-1", query_class="Q-ALIAS",
        arguments=POWERTRAIN | {"entity_kind": "message", "term": "SAMPLE_ALIAS_GEARBOX_STATE"},
        expected_outcome="resolved",
        expected_references=(message(SCOPE, "SAMPLE_MSG_TRANSMISSION_STATE"),),
        target_route=Route.MESSAGE_FACTS,
    ),
    EvaluationCase(
        identifier="SAMPLE-SEMANTIC-1", query_class="Q-SEMANTIC",
        arguments=POWERTRAIN | {"entity_kind": "signal", "term": "engine speed"},
        expected_outcome="candidates",
        expected_references=(signal(SCOPE, "SAMPLE_MSG_ENGINE_STATUS", "SAMPLE_SIG_ENGINE_SPEED"),),
        rank_bound=1, target_route=Route.SIGNAL_FACTS,
    ),
    EvaluationCase(
        # The key exists in both CHASSIS snapshots; the request names one.
        identifier="SAMPLE-COLLIDE-1", query_class="Q-COLLIDE",
        arguments=CHASSIS_B | {"entity_kind": "message", "term": "SAMPLE_MSG_WHEEL_SPEED"},
        expected_outcome="resolved",
        expected_references=(message(CHASSIS_B_SCOPE, "SAMPLE_MSG_WHEEL_SPEED"),),
        target_route=Route.MESSAGE_FACTS,
    ),
    EvaluationCase(
        identifier="SAMPLE-MULTI-1", query_class="Q-MULTI",
        arguments=POWERTRAIN | {"entity_kind": "signal", "term": "SAMPLE_SIG_GEAR_POSITION"},
        expected_outcome="candidates",
        expected_references=(
            signal(SCOPE, "SAMPLE_MSG_TRANSMISSION_STATE", "SAMPLE_SIG_GEAR_POSITION"),
            signal(SCOPE, "SAMPLE_MSG_DIAGNOSTIC_EVENT", "SAMPLE_SIG_FAULT_CODE"),
        ),
        target_route=Route.SIGNAL_FACTS,
    ),
    EvaluationCase(
        identifier="SAMPLE-NOMATCH-1", query_class="Q-NOMATCH",
        arguments=POWERTRAIN | {"entity_kind": "signal", "term": "SAMPLE_SIG_NOTHING_LIKE_THIS"},
        expected_outcome="not_found",
    ),
    EvaluationCase(
        identifier="SAMPLE-SCOPE-1", query_class="Q-SCOPE",
        arguments={k: v for k, v in POWERTRAIN.items() if k != "snapshot_label"}
        | {"entity_kind": "message", "term": "SAMPLE_MSG_TRANSMISSION_STATE"},
        expected_outcome="ambiguous",
    ),
    EvaluationCase(
        identifier="SAMPLE-OUT-1", query_class="Q-OUT",
        arguments=POWERTRAIN | {"entity_kind": "SAMPLE_KIND_FRAME", "term": "SAMPLE_SIG_TEMPERATURE"},
        expected_outcome="unsupported",
    ),
)


class ARunOverTheRegisteredFixtures(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db = database()
        cls.document = perform(
            CASES,
            discovery=Discovery(database=db),
            selection=Selection(database=db),
            registry_state=registry_state(),
            run_id="SAMPLE_RUN",
        )
        cls.by_identifier = {record["identifier"]: record for record in cls.document["cases"]}

    def test_every_case_produced_the_outcome_its_class_registers(self):
        for case in CASES:
            with self.subTest(case=case.identifier):
                self.assertEqual(
                    self.by_identifier[case.identifier]["observed"]["status"],
                    case.expected_outcome,
                )

    def test_the_run_names_the_registry_state_it_executed_against(self):
        stored = registry_state()
        self.assertEqual(self.document["registry_digest"], stored["registry_digest"])
        self.assertEqual(self.document["registry_built_at"], stored["registry_built_at"])
        # And every case that reached a discovery template cites the same one.
        for case in CASES:
            observed = self.by_identifier[case.identifier]["observed"]
            if observed["status"] in ("resolved", "candidates", "not_found"):
                with self.subTest(case=case.identifier):
                    self.assertEqual(observed["registry_digest"], stored["registry_digest"])

    def test_the_metrics_are_the_ones_these_outcomes_give(self):
        overall = self.document["metrics"]["overall"]
        self.assertEqual(overall["total"], len(CASES))
        # Five cases name a target; each finds it, and the three resolved
        # ones plus the two lists put every target at rank 1 -- except
        # Q-MULTI, whose worst-ranked reference is at 2.
        self.assertEqual(overall["recall_at_k"]["recall_at_1"], 0.8)
        self.assertEqual(overall["recall_at_k"]["recall_at_5"], 1.0)
        # No case resolved where the registration says otherwise, and no
        # resolution landed on the wrong reference.
        self.assertEqual(overall["false_resolution"], 0.0)
        # Five cases register a non-resolved outcome; all five abstained.
        self.assertEqual(overall["correct_abstention"], 1.0)
        self.assertEqual(overall["over_abstention"], 0.0)
        # Every case that names a route completed through it.
        self.assertEqual(overall["task_completion"], 1.0)

    def test_q_semantic_meets_its_registered_rank_bound(self):
        record = self.by_identifier["SAMPLE-SEMANTIC-1"]
        ranks = {c["signal_key"]: c["rank"] for c in record["observed"]["candidates"]}
        self.assertLessEqual(ranks["SAMPLE_SIG_ENGINE_SPEED"], record["expected"]["rank_bound"])

    def test_q_collide_resolves_in_the_named_snapshot_only(self):
        # Section 4.10: "the other snapshot's occurrence must be absent."
        # SAMPLE_MSG_WHEEL_SPEED is approved in both CHASSIS snapshots.
        record = self.by_identifier["SAMPLE-COLLIDE-1"]
        self.assertEqual(record["observed"]["resolved"]["revision_label"], "SAMPLE_REV_B")
        self.assertEqual(record["observed"]["resolved"]["network_name"], "SAMPLE_NET_CHASSIS")

    def test_q_multi_completes_through_the_selection_path(self):
        # Section 4.11: "A case whose registered outcome is `candidates`
        # completes through the Section 4.8 selection path, selecting the
        # registered target."
        record = self.by_identifier["SAMPLE-MULTI-1"]
        self.assertEqual(record["observed"]["completion"]["status"], "success")
        self.assertEqual(record["observed"]["completion"]["selected_rank"], 1)

    def test_q_scope_executed_no_discovery_template(self):
        record = self.by_identifier["SAMPLE-SCOPE-1"]
        self.assertEqual(record["observed"]["registry_digest"], "")
        self.assertEqual(record["observed"]["candidates"], [])

    def test_per_class_numbers_are_reported_for_every_class_present(self):
        by_class = self.document["metrics"]["per_class"]
        self.assertEqual(
            list(by_class),
            ["Q-EXACT", "Q-ALIAS", "Q-SEMANTIC", "Q-SCOPE", "Q-COLLIDE", "Q-MULTI", "Q-NOMATCH", "Q-OUT"],
        )
        self.assertEqual(by_class["Q-EXACT"]["task_completion"], 1.0)
        self.assertIsNone(by_class["Q-NOMATCH"]["task_completion"])

    def test_latency_is_recorded_and_positive(self):
        self.assertGreater(self.document["metrics"]["overall"]["latency"]["median_seconds"], 0.0)
        for record in self.document["cases"]:
            self.assertGreater(record["latency_seconds"], 0.0)

    def test_the_set_is_reported_as_not_satisfying_the_authoring_rules(self):
        # One case per class is below rule 4's five, and the artifact says so
        # rather than reporting numbers as if the set were registrable. This
        # is what a registration slice has to clear before Section 8.3 can
        # carry these numbers.
        failures = self.document["authoring_failures"]
        self.assertEqual(sum(1 for failure in failures if "rule 4" in failure), 8)
        # And nothing else: every term is distinct after normalization
        # (rule 6) and every identifier is SAMPLE_* (rule 1).
        self.assertFalse([failure for failure in failures if "rule 4" not in failure])

    def test_these_numbers_are_judged_by_nothing_because_nobody_registered_them(self):
        # The run above is recent, executes against the registry the
        # registration names, and clears every bar in Section 8.3 -- and is
        # still not judged, because these eight cases are this file's and not
        # the registered forty. Charter Section 9 registers the task
        # definitions before the run, so a set a run chose for itself is
        # measured by nothing however well it scores.
        judgement = self.document["judgement"]
        self.assertFalse(judgement["judged"])
        self.assertFalse(judgement["adoptable"])
        self.assertIn("not the one Section 8.3 registers", judgement["reasons"][0])


class TheRegisteredSetAgainstTheRegisteredFixtures(unittest.TestCase):
    """Section 8.3's forty cases, through the registered templates, judged.

    The class above drives cases this file authors, to prove the runner
    records what it observed. This one drives the **registered** set against
    the registry it was authored against, which is the run the Milestone 3
    gate is about. It asserts the shape and the judgement, not a
    hand-written expected number per class: the numbers are what Section
    4.11 computes, and re-stating them here would be a second copy to drift
    rather than a check.
    """

    @classmethod
    def setUpClass(cls):
        db = database()
        cls.state = registry_state()
        cls.document = perform(
            REGISTERED_SET,
            discovery=Discovery(database=db),
            selection=Selection(database=db),
            registry_state=cls.state,
        )
        cls.judgement = cls.document["judgement"]

    def test_the_registry_is_the_one_the_set_was_authored_against(self):
        # Section 8.3 item 2, and Section 4.10 rule 8: if these ever differ,
        # the judgement below is about a different registry and the run is
        # not a run over this set.
        self.assertEqual(self.state["registry_digest"], REGISTERED_AGAINST_DIGEST)

    def test_every_case_ran_and_the_set_breaks_no_authoring_rule(self):
        self.assertEqual(len(self.document["cases"]), len(REGISTERED_SET))
        self.assertEqual(self.document["authoring_failures"], [])

    def test_the_run_is_judged_because_the_registration_precedes_it(self):
        self.assertTrue(self.judgement["judged"], self.judgement["reasons"])
        self.assertLess(self.judgement["registered_at"], self.document["started_at"])

    def test_every_registered_class_is_measured(self):
        self.assertEqual(sorted(self.document["metrics"]["per_class"]), sorted(THRESHOLDS))

    def test_a_cell_the_registration_gives_no_denominator_is_null(self):
        # Section 8.3: a number there is a defect. Asserted over the real
        # run rather than only in the judge, so the metrics and the
        # registration cannot disagree unnoticed.
        for name, registered in THRESHOLDS.items():
            measured = self.document["metrics"]["per_class"][name]
            flat = {k: v for k, v in measured.items() if k != "recall_at_k"} | measured["recall_at_k"]
            for field, bar in registered.as_json().items():
                if bar == "no denominator":
                    with self.subTest(query_class=name, quantity=field):
                        self.assertIsNone(flat[field])

    def test_m_lex_1_clears_the_registered_conditions(self):
        # Not a foregone conclusion, and not the point of the test: what is
        # asserted is that the judge reached a verdict on real numbers and
        # said why if it refused. Section 8 keeps adoption a person's, so a
        # true here adopts nothing.
        self.assertEqual(self.judgement["reasons"], [])
        self.assertTrue(self.judgement["adoptable"])


class TheCommandLineAgainstARealDatabase(unittest.TestCase):
    """The two exit codes, which no test without a database can reach.

    `adapter/run.py` uses the same pair for the same rule: 0 when the run was
    judged, adoptable or not, and 2 when it was not. An unjudged run must not
    be cited, and a red job is how that is said -- so the code has to be
    wrong in the safe direction, and that is only checkable where a run can
    actually happen.
    """

    def run_main(self):
        """`main` over the registered set, with the artifact thrown away.

        It patches nothing on `runner_module`: `main` reads `REGISTERED_SET`
        itself, and a caller that needs a different registration patches the
        constant that decides it at its own call site, as
        `test_an_unjudged_run_exits_two` does.
        """
        with tempfile.TemporaryDirectory() as directory:
            artifact = pathlib.Path(directory) / "run.json"
            printed = io.StringIO()
            with unittest.mock.patch.dict(os.environ, {"MVP_RUNTIME_USER": "mvp_runtime"}):
                with contextlib.redirect_stdout(printed):
                    code = main(["--database", DATABASE, "--artifact", str(artifact)])
            # Read as text, not parsed: the acceptance record is committed as
            # bytes taken from the log, so the comparison below has to be one.
            self.written = artifact.read_text() if artifact.exists() else None
            self.printed = printed.getvalue()
            document = json.loads(self.written) if self.written is not None else None
        return code, document

    def assert_the_log_carries_the_artifact(self):
        """#117: the document follows the summary on stdout, byte for byte.

        Compared as text rather than as parsed JSON. Two documents that parse
        equal can differ in key order, indentation and trailing newline, and
        the acceptance record commits the bytes -- a reader checking the
        committed file against the job log compares characters.
        """
        self.assertIsNotNone(self.written)
        summary, _, rest = self.printed.partition("\n")
        self.assertIn("Discovery run: judged=", summary)
        self.assertEqual(rest[-len(self.written):], self.written)
        self.assertTrue(rest.endswith(self.written))

    def test_the_run_names_the_fixtures_it_executed_against(self):
        """Section 7: "the fixture provenance that actually exists".

        `main` built `Discovery` and `Selection` with no provenance, so
        every result the recorded run produced -- and every `mvp-v0.1`
        result `task_completion` dispatched through them -- described no
        fixtures at all. Nothing false was published, because the Section
        4.10 artifact serializes no `source_trace`; the obligation was unmet
        on results that were then discarded. Asserted on what `main` hands
        the two services, because that is what every result in the run
        inherits.
        """
        from evidence_first_rag.discovery import selection as selection_module
        from evidence_first_rag.discovery import service as service_module

        seen = {}

        def recorder(name, real):
            def build(**arguments):
                seen[name] = arguments.get("fixture_provenance", ())
                return real(**arguments)
            return build

        with unittest.mock.patch.object(
            service_module, "Discovery", recorder("discovery", Discovery)
        ), unittest.mock.patch.object(
            selection_module, "Selection", recorder("selection", Selection)
        ):
            code, _ = self.run_main()

        self.assertEqual(code, 0)
        self.assertEqual(seen["discovery"], FIXTURE_PROVENANCE)
        self.assertEqual(seen["selection"], FIXTURE_PROVENANCE)

    def test_a_result_from_that_run_carries_the_provenance(self):
        # The constant reaching the constructor is not the obligation; a
        # result describing the fixtures is. Driven over the real database
        # as `main` drives it.
        service = Discovery(
            database=database(), fixture_provenance=FIXTURE_PROVENANCE
        )
        case = next(c for c in REGISTERED_SET if c.expected_outcome == "resolved")
        result = service.execute(DiscoveryRequest(arguments=dict(case.arguments)))
        self.assertEqual(result.status.value, "resolved")
        self.assertEqual(
            result.source_trace.fixture_provenance, FIXTURE_PROVENANCE
        )

    def test_a_judged_run_prints_the_document_it_wrote(self):
        # The Milestone 3 artifact expires with the Actions run that produced
        # it, and the writer environment is refused the blob host it is
        # served from, so the job log is where the acceptance record comes
        # from. Milestone 2's record says exactly that of its own.
        self.run_main()
        self.assert_the_log_carries_the_artifact()

    def test_a_judged_run_exits_zero_and_writes_the_artifact(self):
        code, document = self.run_main()
        self.assertEqual(code, 0)
        self.assertTrue(document["judgement"]["judged"])
        self.assertEqual(len(document["cases"]), len(REGISTERED_SET))

    def test_an_unjudged_run_exits_two(self):
        # A registration recorded after the run is not a pre-registration,
        # whatever the document says (Charter Section 9). The run still
        # happens and the artifact is still written -- it is inspectable --
        # but the command says, in its exit code, that nothing here may be
        # cited.
        from evidence_first_rag.discovery import judgement as judgement_module

        with unittest.mock.patch.object(judgement_module, "REGISTERED_AT", "2099-01-01T00:00:00Z"):
            code, document = self.run_main()
        self.assertEqual(code, 2)
        self.assertFalse(document["judgement"]["judged"])
        self.assertFalse(document["judgement"]["adoptable"])
        # An unjudged run is still one a reader may inspect: the exit code
        # says it must not be cited, not that it must not be read. Same
        # reason `milestone-3-run.yml` uploads with `if: always()`.
        self.assert_the_log_carries_the_artifact()


if __name__ == "__main__":
    unittest.main(verbosity=2)
