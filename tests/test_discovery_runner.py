"""entity-discovery-v0.1 Section 4.10: what a run records, over recorded rows.

`perform` is pure with respect to the database -- `discovery` and `selection`
arrive as arguments -- so the artifact's shape, the per-case record and the
`task_completion` dispatch are all assertable here. The run against the
registered fixtures is `tests_database/test_discovery_runner.py`.
"""

import contextlib
import io
import json
import unittest

from evidence_first_rag import MessageReference, Route, SignalReference, SnapshotScope
from evidence_first_rag.discovery import Discovery, EvaluationCase, Selection
from evidence_first_rag.discovery.runner import DEFAULT_ARTIFACT, main, observe, perform

from .discovery_support import BASE, STATE_ROW, candidate_row, database, discovery_row
from .runtime_support import message_row, signal_row

SCOPE = SnapshotScope(**BASE)
ENGINE = MessageReference(scope=SCOPE, message_key="SAMPLE_MSG_ENGINE_STATUS")
GEARBOX = MessageReference(scope=SCOPE, message_key="SAMPLE_MSG_TRANSMISSION_STATE")
TEMPERATURE = SignalReference(message=ENGINE, signal_key="SAMPLE_SIG_TEMPERATURE")

REGISTRY_STATE = {"registry_digest": "a" * 64, "registry_built_at": "2026-09-12T00:00:00Z"}


def case(identifier, query_class, term, **overrides):
    from evidence_first_rag.discovery.evaluation import EXPECTED_OUTCOME, NAMES_A_TARGET

    values = {
        "identifier": identifier,
        "query_class": query_class,
        "arguments": BASE | {"entity_kind": "message", "term": term},
        "expected_outcome": EXPECTED_OUTCOME[query_class][0],
    }
    if query_class in NAMES_A_TARGET:
        values["expected_references"] = (ENGINE,)
        values["target_route"] = Route.MESSAGE_FACTS
    if query_class == "Q-SEMANTIC":
        values["rank_bound"] = 1
    values.update(overrides)
    return EvaluationCase(**values)


def run(cases, *, exact=(), lexical=(), facts=(), clock=None):
    db = database(exact=exact, lexical=lexical)
    db.rows["TPL_MESSAGE_FACTS_V1"] = tuple(facts)
    db.rows["TPL_SIGNAL_FACTS_V1"] = ()
    db.rows["TPL_SIGNAL_MAPPING_V1"] = ()
    ticks = iter(clock or (0.0, 0.25))
    document = perform(
        cases,
        discovery=Discovery(database=db),
        selection=Selection(database=db),
        registry_state=REGISTRY_STATE,
        run_id="SAMPLE_RUN",
        started_at="2026-09-12T00:00:00Z",
        clock=lambda: next(ticks),
    )
    return db, document


class TheArtifact(unittest.TestCase):
    """Section 4.10: "One artifact per run, per method: the method identifier
    and version, this contract's identifier and version, the registry_digest
    and built_at the run executed against, the run's start instant, every
    case ... and the Section 4.11 metrics per class and over the set." """

    def setUp(self):
        self.db, self.document = run(
            [case("Q-1", "Q-EXACT", "SAMPLE_MSG_ENGINE_STATUS")],
            exact=(discovery_row(),),
            facts=(message_row(),),
        )

    def test_it_carries_everything_section_4_10_names(self):
        self.assertEqual(self.document["method_identifier"], "M-LEX-1")
        self.assertEqual(self.document["method_version"], "1")
        self.assertEqual(self.document["contract_identifier"], "entity-discovery-v0.1")
        self.assertEqual(self.document["contract_version"], "0.2.0")
        self.assertEqual(self.document["registry_digest"], "a" * 64)
        self.assertEqual(self.document["registry_built_at"], "2026-09-12T00:00:00Z")
        self.assertEqual(self.document["started_at"], "2026-09-12T00:00:00Z")
        self.assertEqual(self.document["run_id"], "SAMPLE_RUN")
        self.assertEqual(len(self.document["cases"]), 1)
        self.assertIn("overall", self.document["metrics"])
        self.assertIn("per_class", self.document["metrics"])

    def test_every_case_records_its_request_expectation_and_result(self):
        record = self.document["cases"][0]
        self.assertEqual(record["identifier"], "Q-1")
        self.assertEqual(record["query_class"], "Q-EXACT")
        self.assertEqual(record["request"]["term"], "SAMPLE_MSG_ENGINE_STATUS")
        self.assertEqual(record["expected"]["outcome"], "resolved")
        self.assertEqual(record["expected"]["references"][0]["message_key"], "SAMPLE_MSG_ENGINE_STATUS")
        self.assertEqual(record["expected"]["target_route"], "message_facts")
        self.assertEqual(record["observed"]["status"], "resolved")
        self.assertEqual(record["observed"]["resolved"]["message_key"], "SAMPLE_MSG_ENGINE_STATUS")
        self.assertEqual(record["observed"]["registry_digest"], "a" * 64)

    def test_it_is_json(self):
        json.loads(json.dumps(self.document))

    def test_operational_complexity_is_recorded_and_is_not_a_number(self):
        # Section 4.11: "not a number. A recorded description ... which the
        # repository owner weighs at adoption."
        self.assertIsInstance(self.document["operational_complexity"], str)
        self.assertIn("no dependency", self.document["operational_complexity"])

    def test_no_verdict_appears_anywhere(self):
        # The runner never adopts: Section 8.3 registers no thresholds yet,
        # and adoption is a recorded human decision in any case.
        text = json.dumps(self.document).lower()
        for word in ("adopt", "threshold", "pass", "verdict"):
            self.assertNotIn(word, text)

    def test_the_authoring_failures_of_the_set_are_recorded(self):
        # A run over a set that breaks an authoring rule says so in its own
        # artifact rather than reporting numbers as if the set were sound.
        self.assertTrue(self.document["authoring_failures"])
        self.assertTrue(any("rule 4" in failure for failure in self.document["authoring_failures"]))


class TaskCompletionDispatches(unittest.TestCase):
    def test_a_resolved_case_goes_straight_to_the_fact_route(self):
        # Section 4.8: "A resolved outcome carries no candidate_set_id and
        # needs no selection. Its one reference is used directly."
        db, document = run(
            [case("Q-1", "Q-EXACT", "SAMPLE_MSG_ENGINE_STATUS")],
            exact=(discovery_row(),),
            facts=(message_row(),),
        )
        self.assertTrue(db.ran("TPL_MESSAGE_FACTS_V1"))
        self.assertEqual(db.bound("TPL_MESSAGE_FACTS_V1")["message_key"], "SAMPLE_MSG_ENGINE_STATUS")
        self.assertEqual(document["cases"][0]["observed"]["completion"], {"status": "success"})
        self.assertEqual(document["metrics"]["overall"]["task_completion"], 1.0)

    def test_a_candidates_case_goes_through_the_selection_path_at_the_targets_rank(self):
        registered = case(
            "Q-1", "Q-MULTI", "sample msg",
            expected_references=(GEARBOX,), target_route=Route.MESSAGE_FACTS,
        )
        rows = (discovery_row(match_tier=4), discovery_row(message_key="SAMPLE_MSG_TRANSMISSION_STATE", match_tier=4))
        db, document = run([registered], lexical=rows, facts=(message_row(message_key="SAMPLE_MSG_TRANSMISSION_STATE"),))
        self.assertEqual(document["cases"][0]["observed"]["completion"]["selected_rank"], 2)
        self.assertEqual(document["metrics"]["overall"]["task_completion"], 1.0)
        # The fact route was reached through the verified path, so the
        # discovery templates ran twice: once for the case, once for the
        # selection's re-derivation.
        self.assertEqual(sum(1 for name, _ in db.calls if name == "TPL_DISCOVERY_LEXICAL_V1"), 2)

    def test_a_candidates_case_that_resolved_is_not_completed_by_that_resolution(self):
        # Section 4.11: "A case whose registered outcome is `candidates`
        # completes through the Section 4.8 selection path, selecting the
        # registered target." A run that returns an unlicensed `resolved` --
        # already a false_resolution, even on the registered target -- never
        # produced the candidate list the class must complete through, so no
        # end-to-end credit is available to it.
        db, document = run(
            [case("Q-1", "Q-MULTI", "SAMPLE_MSG_ENGINE_STATUS")],
            exact=(discovery_row(),),
            facts=(message_row(),),
        )
        self.assertEqual(document["metrics"]["overall"]["task_completion"], 0.0)
        self.assertEqual(document["metrics"]["overall"]["false_resolution"], 1.0)
        self.assertIn("resolved", document["cases"][0]["observed"]["completion"]["reason"])
        self.assertFalse(db.ran("TPL_MESSAGE_FACTS_V1"))

    def test_a_target_absent_from_the_list_is_not_a_completion(self):
        registered = case("Q-1", "Q-MULTI", "sample msg", expected_references=(GEARBOX,), target_route=Route.MESSAGE_FACTS)
        db, document = run([registered], lexical=(discovery_row(match_tier=4), discovery_row(message_key="SAMPLE_MSG_X", match_tier=4)))
        self.assertEqual(document["metrics"]["overall"]["task_completion"], 0.0)
        self.assertIn("not in the candidate list", document["cases"][0]["observed"]["completion"]["reason"])
        self.assertFalse(db.ran("TPL_MESSAGE_FACTS_V1"))

    def test_a_discovery_that_did_not_reach_a_list_is_not_a_completion(self):
        db, document = run([case("Q-1", "Q-EXACT", "SAMPLE_MSG_ENGINE_STATUS")])
        self.assertEqual(document["metrics"]["overall"]["task_completion"], 0.0)
        self.assertIn("not_found", document["cases"][0]["observed"]["completion"]["reason"])

    def test_a_fact_route_that_answers_not_found_is_not_a_completion(self):
        # Section 4.11: task_completion is "returns `success` carrying that
        # reference", so the fact route's own status decides.
        db, document = run([case("Q-1", "Q-EXACT", "SAMPLE_MSG_ENGINE_STATUS")], exact=(discovery_row(),), facts=())
        self.assertEqual(document["metrics"]["overall"]["task_completion"], 0.0)

    def test_a_route_that_succeeds_on_another_reference_is_not_a_completion(self):
        # Section 4.11: task_completion is the route returning `success`
        # **carrying that reference**. A run that resolves to a different
        # entity and answers about it is a success for the wrong question.
        registered = case(
            "Q-1", "Q-EXACT", "SAMPLE_MSG_ENGINE_STATUS",
            expected_references=(GEARBOX,), target_route=Route.MESSAGE_FACTS,
        )
        db, document = run([registered], exact=(discovery_row(),), facts=(message_row(),))
        self.assertEqual(document["cases"][0]["observed"]["completion"], {"status": "success"})
        self.assertEqual(db.bound("TPL_MESSAGE_FACTS_V1")["message_key"], "SAMPLE_MSG_ENGINE_STATUS")
        self.assertEqual(document["metrics"]["overall"]["task_completion"], 0.0)

    def test_a_case_naming_no_route_is_not_in_the_denominator(self):
        db, document = run([case("Q-1", "Q-NOMATCH", "SAMPLE_MSG_ABSENT")])
        self.assertIsNone(document["metrics"]["overall"]["task_completion"])
        self.assertIsNone(document["cases"][0]["observed"]["completion"])


class OneCase(unittest.TestCase):
    def test_observe_records_the_latency_the_clock_measured(self):
        db = database(exact=(discovery_row(),))
        ticks = iter((10.0, 10.75))
        outcome, record = observe(
            case("Q-1", "Q-EXACT", "SAMPLE_MSG_ENGINE_STATUS"),
            Discovery(database=db), Selection(database=db), clock=lambda: next(ticks),
        )
        self.assertEqual(outcome.latency_seconds, 0.75)
        self.assertEqual(record["latency_seconds"], 0.75)

    def test_a_candidates_outcome_records_the_ranked_list(self):
        db = database(lexical=(discovery_row(match_tier=4), discovery_row(message_key="SAMPLE_MSG_X", match_tier=4)))
        outcome, record = observe(
            case("Q-1", "Q-SEMANTIC", "sample msg"),
            Discovery(database=db), Selection(database=db), clock=lambda: 0.0,
        )
        self.assertEqual([rank for _, rank in outcome.ranked], [1, 2])
        self.assertEqual([c["rank"] for c in record["observed"]["candidates"]], [1, 2])
        self.assertNotEqual(record["observed"]["candidate_set_id"], "")

    def test_a_resolved_outcome_is_the_reference_at_rank_1(self):
        # Section 4.11's own words for how a resolution enters the metrics.
        db = database(exact=(discovery_row(),))
        outcome, _ = observe(
            case("Q-1", "Q-EXACT", "SAMPLE_MSG_ENGINE_STATUS"),
            Discovery(database=db), Selection(database=db), clock=lambda: 0.0,
        )
        self.assertEqual(outcome.ranked, ((ENGINE, 1),))
        self.assertEqual(outcome.resolved_reference, ENGINE)


class TheCommandLine(unittest.TestCase):
    def test_it_refuses_to_run_while_section_8_3_is_reserved(self):
        # Charter Section 9: a run over an unregistered set must not be
        # cited, so the runner declines to produce one. Exit 2, as the
        # Milestone 2 runner exits 2 for the same ordering rule.
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            self.assertEqual(main(["--artifact", "/dev/null"]), 2)
        # Exit 2 alone does not distinguish the reserved-set refusal from the
        # unwired-database refusal that follows it, so the reason is asserted.
        self.assertIn("Section 8.3", stderr.getvalue())
        self.assertIn("no evaluation set is registered", stderr.getvalue())

    def test_the_default_artifact_is_named_for_the_milestone(self):
        self.assertEqual(DEFAULT_ARTIFACT.name, "milestone-3-discovery-run.json")


if __name__ == "__main__":
    unittest.main(verbosity=2)
