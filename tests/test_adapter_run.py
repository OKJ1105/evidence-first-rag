"""The comparison runner: one artifact, no verdict of its own.

No model and no database are involved. `perform` takes the resolver and the
runtime as arguments, so a scripted resolver and the fake database the
runtime tests already use are enough to assert what the artifact carries,
what the exit code means, and that the gate's refusals reach the document.
`main` is the wiring that supplies the real ones and is not exercised here.
"""

import datetime
import hashlib
import importlib.util
import json
import pathlib
import re
import unittest

from evidence_first_rag import CONTRACT_IDENTIFIER, CONTRACT_VERSION
from evidence_first_rag.adapter import Baseline, Proposal, Thresholds, measure
from evidence_first_rag.adapter import run as runner
from evidence_first_rag.adapter import vocabulary
from evidence_first_rag.adapter.evaluation import CURATED, EVALUATION_SET, THRESHOLDS, family
from evidence_first_rag.adapter.revalidation import _is_verbatim_token
from evidence_first_rag.references import SCOPE_DIMENSIONS
from evidence_first_rag.runtime import Runtime

from .runtime_support import FakeDatabase, candidate_row, message_row

HAS_SDK = importlib.util.find_spec("anthropic") is not None

if HAS_SDK:
    from evidence_first_rag.adapter.client import MODEL as REAL_MODEL
    from evidence_first_rag.adapter.client import Adapter

FIXTURES = pathlib.Path(__file__).resolve().parent.parent / "fixtures"
LOADED_SCOPES = [
    {d: json.loads(line)[d] for d in SCOPE_DIMENSIONS}
    for line in (FIXTURES / "source_snapshot.jsonl").read_text().splitlines()
    if line.strip()
]
BY_TEXT = {case.text: case for case in EVALUATION_SET}
DECODING = {"model": "claude-opus-5", "max_tokens": 4096, "output_config": {"effort": "low"}}


def perfect(text):
    """Each case's own registration, as a resolver."""
    case = BY_TEXT[text]
    kind = family(case)
    if kind in {"P", "D"}:
        return Proposal(route=case.expected_route, arguments=dict(case.expected_arguments))
    if kind == "X":
        for dimension in SCOPE_DIMENSIONS:
            values = sorted({s[dimension] for s in LOADED_SCOPES if _is_verbatim_token(s[dimension], text)})
            if len(values) == 2:
                return Proposal(route="message_facts", arguments={dimension: values})
    return Proposal(route="unsupported", arguments={})


def empty_runtime():
    # No rows at all: every accepted proposal resolves to coverage_gap, so
    # nothing is a success and nothing can be weakened. The clean case.
    return Runtime(database=FakeDatabase({}))


def indiscriminate_runtime():
    # The same candidate and message row for every request, whatever its
    # arguments. FX-106 asks about a network no snapshot has; this database
    # answers anyway, so the adapter's coverage_gap becomes a success.
    return Runtime(
        database=FakeDatabase(
            {
                "TPL_SNAPSHOT_CANDIDATES_V1": (candidate_row(),),
                "TPL_MESSAGE_FACTS_V1": (message_row(),),
            }
        )
    )


def later(instant: str, hours: float) -> str:
    moment = datetime.datetime.fromisoformat(instant)
    return (moment + datetime.timedelta(hours=hours)).isoformat()


class TheArtifact(unittest.TestCase):
    def setUp(self):
        self.document = runner.perform(
            propose=perfect, runtime=empty_runtime(), model="claude-opus-5", decoding=DECODING
        )

    def test_it_records_the_contract_the_model_and_the_decoding(self):
        self.assertEqual(self.document["contract_identifier"], CONTRACT_IDENTIFIER)
        self.assertEqual(self.document["contract_version"], CONTRACT_VERSION)
        self.assertEqual(self.document["model"], "claude-opus-5")
        self.assertEqual(self.document["decoding"], DECODING)
        self.assertEqual(self.document["thresholds"], THRESHOLDS.as_json())

    def test_it_records_the_prompt_by_digest(self):
        digest = self.document["prompt_digest"]
        self.assertEqual(
            digest["instructions_sha256"],
            hashlib.sha256(vocabulary.instructions().encode()).hexdigest(),
        )
        self.assertEqual(
            digest["payload_sha256"],
            hashlib.sha256(vocabulary.as_text(vocabulary.payload()).encode()).hexdigest(),
        )
        self.assertEqual(digest, runner.prompt_digest())
        for value in digest.values():
            self.assertTrue(re.fullmatch(r"[0-9a-f]{64}", value))

    def test_it_carries_every_case_in_registered_order_and_ran_against_a_database(self):
        outcomes = self.document["report"]["adapter_outcomes"]
        self.assertEqual([o["identifier"] for o in outcomes], [c.identifier for c in EVALUATION_SET])
        self.assertEqual(len(outcomes), 48)
        self.assertTrue(self.document["report"]["executed_against_a_database"])
        self.assertTrue(all("refused_as" in o for o in outcomes))

    def test_the_baseline_in_the_artifact_is_the_measured_floor(self):
        metrics, _ = measure(EVALUATION_SET, Baseline(CURATED).resolve)
        recorded = self.document["report"]["baseline"]
        self.assertEqual(recorded["correct"], metrics.correct)
        self.assertEqual(recorded["correct"], 22)
        self.assertEqual(recorded["false_resolutions"], 0)

    def test_the_two_irreproducible_fields_are_present_and_distinct_per_run(self):
        again = runner.perform(
            propose=perfect, runtime=empty_runtime(), model="claude-opus-5", decoding=DECODING
        )
        self.assertNotEqual(self.document["run_identifier"], again["run_identifier"])
        self.assertTrue(self.document["started_at"])

    def test_it_is_json_and_writes_where_told(self):
        target = pathlib.Path(__file__).resolve().parent / "_run_artifact.tmp.json"
        try:
            runner.write(target, self.document)
            self.assertEqual(json.loads(target.read_text()), self.document)
        finally:
            target.unlink(missing_ok=True)


@unittest.skipUnless(HAS_SDK, "the adapter extra is not installed")
class ThePinIsTheRealAdapterConfiguration(unittest.TestCase):
    """Section 8's 'the pin is asserted, not assumed', against the real client.

    Every other test in this file hand-types a local `DECODING` mapping,
    which would not notice `client.py`'s `DECODING` drifting -- gaining or
    losing a key -- or `main()` swapping `pinned_decoding=Adapter.configuration()`
    for something stale. This one imports the real `Adapter` and feeds its
    actual `configuration()` through, the same shape `main()` uses, without
    spending a network call.
    """

    def test_the_artifact_records_the_real_adapter_configuration(self):
        configuration = Adapter.configuration()
        document = runner.perform(
            propose=perfect,
            runtime=empty_runtime(),
            model=REAL_MODEL,
            decoding=configuration,
        )
        self.assertEqual(document["model"], REAL_MODEL)
        self.assertEqual(document["decoding"], configuration)
        self.assertIn("thinking", document["decoding"])
        # `pinned_decoding` defaults to `decoding`: if `perform` (or a future
        # `main()`) fed `judge` a different value as the pin, the drift would
        # surface here as a refused, non-adoptable judgement.
        self.assertTrue(document["judgement"]["adoptable"], document["judgement"]["reasons"])


class TheGateReachesTheDocument(unittest.TestCase):
    def test_a_perfect_resolver_against_an_empty_database_clears_the_registered_bar(self):
        document = runner.perform(
            propose=perfect, runtime=empty_runtime(), model="claude-opus-5", decoding=DECODING
        )
        judgement = document["judgement"]
        self.assertTrue(judgement["judged"])
        self.assertTrue(judgement["adoptable"], judgement["reasons"])
        self.assertEqual(document["report"]["adapter"]["task_coverage"], 1.0)
        self.assertEqual(runner.exit_code(document), 0)

    def test_a_database_that_turns_a_registered_negative_into_a_fact_is_weakening(self):
        # FX-106 registers coverage_gap. A database that answers it with a
        # row makes the outcome success, and that is exactly what "without
        # weakening any negative outcome" forbids -- however good the
        # averages look. The runner does not decide this; it records it.
        document = runner.perform(
            propose=perfect, runtime=indiscriminate_runtime(), model="claude-opus-5", decoding=DECODING
        )
        judgement = document["judgement"]
        self.assertTrue(judgement["judged"])
        self.assertFalse(judgement["adoptable"])
        weakened = document["report"]["adapter"]["weakened_negatives"]
        self.assertTrue(any(i.startswith("EV-P-FX-106-") for i in weakened), weakened)
        self.assertTrue(any("weakened" in r for r in judgement["reasons"]))
        self.assertEqual(runner.exit_code(document), 0)  # judged; a measurement, not a verdict

    def test_a_decoding_that_drifted_from_the_pin_is_refused(self):
        document = runner.perform(
            propose=perfect,
            runtime=empty_runtime(),
            model="claude-opus-5",
            decoding=DECODING | {"output_config": {"effort": "high"}},
            pinned_decoding=DECODING,
        )
        self.assertFalse(document["judgement"]["adoptable"])
        self.assertTrue(any("pinned" in r for r in document["judgement"]["reasons"]))

    def test_thresholds_registered_after_the_run_leave_it_unjudged_and_exit_2(self):
        document = runner.perform(
            propose=perfect, runtime=empty_runtime(), model="claude-opus-5", decoding=DECODING
        )
        too_late = Thresholds(
            task_coverage=0.9,
            false_resolution=0.0,
            registered_at=later(document["started_at"], 1),
            contract_version=CONTRACT_VERSION,
        )
        unjudged = runner.perform(
            propose=perfect,
            runtime=empty_runtime(),
            model="claude-opus-5",
            decoding=DECODING,
            thresholds=too_late,
        )
        self.assertFalse(unjudged["judgement"]["judged"])
        self.assertEqual(runner.exit_code(unjudged), 2)

    def test_a_run_that_touched_no_database_is_judged_but_never_adoptable(self):
        document = runner.perform(
            propose=perfect, runtime=None, model="claude-opus-5", decoding=DECODING
        )
        self.assertFalse(document["report"]["executed_against_a_database"])
        self.assertTrue(document["judgement"]["judged"])
        self.assertFalse(document["judgement"]["adoptable"])
        self.assertTrue(any("database" in r for r in document["judgement"]["reasons"]))

    def test_the_summary_never_says_adopt(self):
        document = runner.perform(
            propose=perfect, runtime=empty_runtime(), model="claude-opus-5", decoding=DECODING
        )
        line = runner.summary(document)
        self.assertIn("adoptable=True", line)
        self.assertNotRegex(line.lower(), r"\badopt\b")


class TheModuleStaysImportableWithoutTheSdkOrTheDriver(unittest.TestCase):
    def test_module_level_imports_name_neither(self):
        import ast

        source = pathlib.Path(runner.__file__).read_text()
        tree = ast.parse(source)
        top_level = set()
        for node in tree.body:
            if isinstance(node, ast.Import):
                top_level.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                top_level.add((node.module or "").split(".")[-1])
        self.assertNotIn("anthropic", top_level)
        self.assertNotIn("psycopg", top_level)
        self.assertNotIn("client", top_level)
        self.assertNotIn("connection", top_level)


class TheAdapterPathNeverFallsBackToTheBaseline(unittest.TestCase):
    """#56's remaining acceptance-evidence item, as a probe rather than a read.

    `run.py` imports `Baseline`, and has to: the control group is the point
    of the comparison. What must never happen is the *adapter's* answers
    coming from it. `tests/test_adapter_surface.py` cannot be extended to
    this module the way it covers the answering path, because there the
    absence of the import is the assertion and here the import is required.
    So the separation is asserted where it actually lives: in what `perform`
    passes to `compare`.
    """

    @staticmethod
    def refusing(text):
        """A resolver that proposes nothing for anything."""
        return Proposal(route="unsupported", arguments={})

    def test_a_resolver_that_answers_nothing_scores_its_own_floor(self):
        # A resolver that never routes is correct exactly on the cases that
        # should not resolve, and never on P. Its number is not the
        # baseline's, so a silent substitution would move it.
        document = runner.perform(
            propose=self.refusing, runtime=empty_runtime(), model="m", decoding=DECODING
        )
        expected, _ = measure(EVALUATION_SET, self.refusing, empty_runtime())
        self.assertEqual(document["report"]["adapter"], expected.as_json())
        self.assertNotEqual(
            document["report"]["adapter"]["correct"], document["report"]["baseline"]["correct"]
        )

    def test_the_probe_discriminates(self):
        # Rule 9: a check never seen to fail is not evidence. Hand `perform`
        # the baseline itself as the adapter, which is precisely the shape a
        # fallback would take, and the assertion above inverts.
        document = runner.perform(
            propose=Baseline(CURATED).resolve,
            runtime=empty_runtime(),
            model="m",
            decoding=DECODING,
        )
        self.assertEqual(
            document["report"]["adapter"]["correct"], document["report"]["baseline"]["correct"]
        )
