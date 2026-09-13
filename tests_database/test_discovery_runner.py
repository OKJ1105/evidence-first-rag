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

import os
import unittest

from evidence_first_rag import MessageReference, Route, SignalReference, SnapshotScope
from evidence_first_rag.discovery import Discovery, EvaluationCase, Selection
from evidence_first_rag.discovery.runner import perform
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
            started_at="2026-09-12T00:00:00Z",
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
