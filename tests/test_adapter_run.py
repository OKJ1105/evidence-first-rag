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
import contextlib
import io
import re
import tempfile
import types
import unittest
import unittest.mock

from evidence_first_rag import CONTRACT_IDENTIFIER, CONTRACT_VERSION
from evidence_first_rag.adapter import Baseline, Proposal, Thresholds, measure
from evidence_first_rag.adapter import run as runner
from evidence_first_rag.adapter import vocabulary
from evidence_first_rag.adapter.evaluation import CURATED, EVALUATION_SET, THRESHOLDS, family
from evidence_first_rag.adapter.revalidation import _is_verbatim_token, answer
from evidence_first_rag.conformance.normalize import normalize as normalize_result
from evidence_first_rag.evidence import (
    EvidenceBundle,
    ProducingLayer,
    ReadOnlySafeguards,
    SourceTrace,
)
from evidence_first_rag.references import SCOPE_DIMENSIONS
from evidence_first_rag.result import Result
from evidence_first_rag.runtime import Runtime
from evidence_first_rag.status import OPENS_NO_CONNECTION, Status

from .runtime_support import FakeDatabase, candidate_row, message_row

WORKFLOW = (
    pathlib.Path(__file__).resolve().parent.parent
    / ".github"
    / "workflows"
    / "milestone-2-comparison.yml"
)

HAS_SDK = importlib.util.find_spec("anthropic") is not None
# The driver is its own guard, because the two dependencies arrive by
# different routes and one flag for both is a guess.
#
# `psycopg[binary]` is a *base* dependency and `anthropic` is the `adapter`
# extra (`pyproject.toml`), so `pip install -e ".[adapter]"` installs both
# and never reproduces this. What does: `tests/` runs from a clean checkout
# with nothing installed -- `tests/__init__.py` puts `src/` on the path --
# so a writer who adds only `pip install anthropic` to that checkout has the
# SDK and no driver. Under `HAS_SDK` alone, importing `runtime.connection`
# then fails the whole module at load and takes every unrelated test in it
# down. That is the environment this session was in while discharging #90's
# acceptance evidence, and it is why CI never saw it: both CI jobs have
# neither dependency and the dispatched workflow has both.
HAS_DRIVER = importlib.util.find_spec("psycopg") is not None

if HAS_SDK:
    from evidence_first_rag.adapter import client as adapter_client
    from evidence_first_rag.adapter.client import MODEL as REAL_MODEL
    from evidence_first_rag.adapter.client import Adapter

if HAS_DRIVER:
    from evidence_first_rag.runtime import connection as runtime_connection

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


# Section 5's three no-connection statuses, as the artifact spells them.
NO_CONNECTION = frozenset(status.value for status in OPENS_NO_CONNECTION)

# The `P` cases that route to `message_facts` with a `message_key`, which is
# the shape both refusal families in the first Milestone 2 run took: a
# required lookup key absent, or a value that is not in the request text.
MESSAGE_KEY_CASES = tuple(
    case
    for case in EVALUATION_SET
    if family(case) == "P"
    and case.expected_route == "message_facts"
    and "message_key" in case.expected_arguments
)
MESSAGE_KEY_IDENTIFIERS = frozenset(case.identifier for case in MESSAGE_KEY_CASES)

# An identifier of the registered shape that appears in no request text.
NOT_IN_ANY_REQUEST = "SAMPLE_MSG_NOWHERE_IN_THE_REQUEST"


def without_the_message_key(text):
    """`perfect`, except that it drops the one required lookup key.

    The twenty-one-case refusal family from the first run: the route is
    determined and the scope is complete, but no canonical reference can be
    formed, so Section 5 makes the outcome terminal `needs_entity_discovery`.
    """
    case = BY_TEXT[text]
    if case.identifier in MESSAGE_KEY_IDENTIFIERS:
        arguments = {
            name: value
            for name, value in case.expected_arguments.items()
            if name != "message_key"
        }
        return Proposal(route=case.expected_route, arguments=arguments)
    return perfect(text)


def inventing_the_message_key(text):
    """`perfect`, except that the lookup key is not in the request text.

    The twelve-case family: Section 4.6 lets the adapter extract only values
    explicitly present in the request, and this is the check that stands
    between a plausible identifier and a lookup that would return real facts
    about the wrong thing.
    """
    case = BY_TEXT[text]
    if case.identifier in MESSAGE_KEY_IDENTIFIERS:
        return Proposal(
            route=case.expected_route,
            arguments=dict(case.expected_arguments) | {"message_key": NOT_IN_ANY_REQUEST},
        )
    return perfect(text)


class RefusingRuntime:
    """A runtime that refuses everything, including what revalidation passed.

    Not a thing the real `Runtime` can be -- that is the point. It exists to
    break `TheRuntimeNeverRefusesWhatRevalidationAccepted`, so that the
    invariant is a check that has been seen to fail rather than a claim
    (#17 rule 9).
    """

    fixture_provenance = ()

    def execute(self, request):
        return Result(
            status=Status.UNSUPPORTED,
            evidence_bundle=EvidenceBundle(
                route="message_facts",
                read_only_safeguards=ReadOnlySafeguards(
                    role_name="", read_only_transaction=False, connection_opened=False
                ),
            ),
            source_trace=SourceTrace(producing_layer=ProducingLayer.RUNTIME),
        )


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

    def test_it_records_the_output_schema_by_digest(self):
        # #111. The schema travels inside `output_config`, the same object
        # whose `effort` Section 4.6 pins, and until now it was in neither
        # `DECODING` nor `prompt_digest` -- so two runs sent different
        # schemas and recorded identical digests. That is how the `d2f08cb8`
        # comparison was decided by an input nothing recorded.
        digest = self.document["schema_digest"]
        self.assertEqual(
            digest,
            hashlib.sha256(
                vocabulary.as_text(vocabulary.schema()).encode("utf-8")
            ).hexdigest(),
        )
        self.assertEqual(digest, runner.schema_digest())
        self.assertTrue(re.fullmatch(r"[0-9a-f]{64}", digest))

    def test_the_schema_digest_moves_when_the_schema_does(self):
        # Rule 9 as a permanent probe rather than a one-off mutation: a
        # digest that did not change with its subject would record nothing.
        before = runner.schema_digest()
        real = vocabulary.schema
        try:
            vocabulary.schema = lambda: {**real(), "x": 1}
            self.assertNotEqual(runner.schema_digest(), before)
        finally:
            vocabulary.schema = real
        self.assertEqual(runner.schema_digest(), before)

    def test_it_carries_every_case_in_registered_order_and_ran_against_a_database(self):
        outcomes = self.document["report"]["adapter_outcomes"]
        self.assertEqual([o["identifier"] for o in outcomes], [c.identifier for c in EVALUATION_SET])
        self.assertEqual(len(outcomes), 48)
        self.assertTrue(self.document["report"]["executed_against_a_database"])
        self.assertTrue(all("refused_as" in o for o in outcomes))

    def test_the_baseline_in_the_artifact_is_the_measured_floor(self):
        # The whole document rather than two fields, and measured against the
        # same runtime the artifact used: without one the weakening check has
        # nothing to read, so the two sides would not be comparing the same
        # thing.
        #
        # `Metrics` carries four fields; `task_coverage` and
        # `false_resolution` are properties derived from them. So widening
        # this assertion cannot catch a wrong ratio -- both sides would
        # compute it the same way -- and the only fields it adds are `total`
        # and `weakened_negatives`. Under this runtime nothing is weakened,
        # which makes that half vacuous here; the test below is where it
        # earns its keep.
        metrics, _ = measure(EVALUATION_SET, Baseline(CURATED).resolve, empty_runtime())
        recorded = self.document["report"]["baseline"]
        self.assertEqual(recorded, metrics.as_json())
        self.assertEqual(recorded["correct"], 22)
        self.assertEqual(recorded["false_resolutions"], 0)

    def test_the_recorded_baseline_carries_the_weakened_negatives(self):
        # The case the two-field form could not see. Against a database that
        # answers everything, the baseline weakens two registered negatives
        # while `correct` stays 22 and `false_resolutions` stays 0 -- so a
        # regression that stopped recording weakening would have passed a
        # check that read only those two.
        runtime = indiscriminate_runtime()
        document = runner.perform(
            propose=perfect, runtime=runtime, model="m", decoding=DECODING
        )
        metrics, _ = measure(
            EVALUATION_SET, Baseline(CURATED).resolve, indiscriminate_runtime()
        )
        recorded = document["report"]["baseline"]
        self.assertEqual(recorded, metrics.as_json())
        self.assertEqual(recorded["correct"], 22)
        self.assertEqual(recorded["false_resolutions"], 0)
        self.assertEqual(
            recorded["weakened_negatives"], ["EV-P-FX-106-0", "EV-P-FX-107-0"]
        )

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


class TheOutcomeSaysWhatWasProposedAndWhyItWasRefused(unittest.TestCase):
    """#89. The first Milestone 2 run refused all forty-eight proposals and
    the artifact could not say what any of them had proposed or which check
    stopped it.

    Every assertion below reads `as_json` output through the written
    document rather than the dataclass, because the artifact is what #58 is
    decided on and a field that never reaches the JSON is not recorded.
    """

    def setUp(self):
        self.document = runner.perform(
            propose=perfect, runtime=empty_runtime(), model="claude-opus-5", decoding=DECODING
        )
        self.outcomes = {
            outcome["identifier"]: outcome
            for outcome in self.document["report"]["adapter_outcomes"]
        }

    def outcomes_for(self, resolve):
        document = runner.perform(
            propose=resolve, runtime=empty_runtime(), model="m", decoding=DECODING
        )
        return {
            outcome["identifier"]: outcome
            for outcome in document["report"]["adapter_outcomes"]
        }

    def test_every_positive_case_records_the_arguments_it_proposed(self):
        seen = 0
        for case in EVALUATION_SET:
            if family(case) != "P":
                continue
            outcome = self.outcomes[case.identifier]
            self.assertEqual(
                outcome["proposed_arguments"], dict(case.expected_arguments), case.identifier
            )
            self.assertIsNone(outcome["refusal_detail"], case.identifier)
            self.assertIsNone(outcome["producing_layer"], case.identifier)
            seen += 1
        self.assertEqual(seen, 33)

    def test_a_positive_case_that_reached_the_empty_database_records_its_coverage_gap(self):
        # #89's first acceptance bullet asks for `limitations` `[]` here. It
        # cannot be: `empty_runtime()` holds no rows, so every accepted
        # proposal resolves to `coverage_gap`, and Section 7 requires that
        # status to carry a `coverage_not_established` entry -- `Result`
        # refuses to construct without one. `[]` is the value when the field
        # does not apply, which on this runtime is only the refused cases.
        # Recorded rather than worked around: emptying it would discard the
        # one thing the runtime said about the outcome.
        outcome = self.outcomes["EV-P-FX-001-0"]
        self.assertEqual(outcome["status"], "coverage_gap")
        self.assertEqual(
            [entry["kind"] for entry in outcome["limitations"]], ["coverage_not_established"]
        )

    def test_a_missing_lookup_key_is_needs_entity_discovery_and_names_the_key(self):
        outcomes = self.outcomes_for(without_the_message_key)
        for case in MESSAGE_KEY_CASES:
            outcome = outcomes[case.identifier]
            self.assertEqual(outcome["refused_as"], "needs_entity_discovery", case.identifier)
            self.assertIn("message_key", outcome["refusal_detail"], case.identifier)
            self.assertNotIn("message_key", outcome["proposed_arguments"], case.identifier)

    def test_a_refused_needs_entity_discovery_outcome_carries_the_one_limitation(self):
        outcomes = self.outcomes_for(without_the_message_key)
        for case in MESSAGE_KEY_CASES:
            outcome = outcomes[case.identifier]
            self.assertEqual(
                [entry["kind"] for entry in outcome["limitations"]],
                ["entity_discovery_not_implemented"],
                case.identifier,
            )

    def test_a_value_that_is_not_in_the_request_text_is_invalid_request(self):
        outcomes = self.outcomes_for(inventing_the_message_key)
        for case in MESSAGE_KEY_CASES:
            outcome = outcomes[case.identifier]
            self.assertEqual(outcome["refused_as"], "invalid_request", case.identifier)
            self.assertIn("message_key", outcome["refusal_detail"], case.identifier)
            self.assertEqual(
                outcome["proposed_arguments"]["message_key"],
                NOT_IN_ANY_REQUEST,
                case.identifier,
            )

    def test_an_unsupported_outcome_records_the_layer_that_produced_it(self):
        # Section 5: "the trace records whether the adapter or the runtime
        # produced it". `perfect` emits the adapter's own `unsupported`
        # literal for the `U` cases, so the layer is the adapter.
        unsupported = [
            self.outcomes[case.identifier]
            for case in EVALUATION_SET
            if family(case) == "U"
        ]
        self.assertEqual(len(unsupported), 6)
        for outcome in unsupported:
            self.assertEqual(outcome["producing_layer"], "adapter")

    def test_a_contradictory_scope_survives_serialisation_as_the_two_values(self):
        # FX-110's registered shape: the adapter proposed two values for one
        # dimension, which arrive as a list inside one argument name. A
        # `dict[str, str]` that dropped anything non-textual would erase the
        # case the artifact is read to find.
        contradictory = [
            self.outcomes[case.identifier]
            for case in EVALUATION_SET
            if family(case) == "X"
        ]
        self.assertEqual(len(contradictory), 5)
        for outcome in contradictory:
            self.assertEqual(outcome["refused_as"], "invalid_request")
            values = list(outcome["proposed_arguments"].values())
            self.assertEqual(len(values), 1)
            self.assertTrue(values[0].startswith("["), values[0])
            for value in values:
                self.assertIsInstance(value, str)

    def test_a_run_without_a_runtime_leaves_the_two_runtime_fields_empty(self):
        document = runner.perform(
            propose=perfect, runtime=None, model="m", decoding=DECODING
        )
        for outcome in document["report"]["adapter_outcomes"]:
            self.assertEqual(outcome["limitations"], [])
            self.assertIsNone(outcome["producing_layer"])

    def test_the_report_gains_nothing_at_the_top_level(self):
        # #89: the new content belongs to an outcome, not to the report.
        self.assertEqual(
            sorted(self.document["report"]),
            [
                "adapter",
                "adapter_outcomes",
                "baseline",
                "baseline_outcomes",
                "decoding",
                "executed_against_a_database",
                "model",
                "started_at",
            ],
        )
        self.assertEqual(
            sorted(self.document),
            [
                "contract_identifier",
                "contract_version",
                "decoding",
                "judgement",
                "model",
                "prompt_digest",
                "report",
                "run_identifier",
                "schema_digest",
                "started_at",
                "thresholds",
            ],
        )

    def test_the_baseline_outcomes_carry_the_same_four_fields(self):
        # `measure` is one function and both resolvers go through it, but the
        # artifact records two lists and only one of them is read by default.
        for outcome in self.document["report"]["baseline_outcomes"]:
            for field in (
                "proposed_arguments",
                "refusal_detail",
                "limitations",
                "producing_layer",
            ):
                self.assertIn(field, outcome, outcome["identifier"])


class TheLimitationShapeIsTheOneAlreadyRegistered(unittest.TestCase):
    """`limitations` is serialised the way `conformance/normalize.py` does it.

    #89: "using whatever serialisation `Limitation` already has; do not
    invent one". That shape is the one check `A1` compares a result against,
    and a comment asserting the two agree would not notice either moving.
    """

    def test_every_outcome_matches_the_registered_serialisation(self):
        _, outcomes = measure(EVALUATION_SET, perfect, empty_runtime())
        entries = 0
        for case, outcome in zip(EVALUATION_SET, outcomes):
            result = answer(empty_runtime(), perfect(case.text), case.text)
            self.assertEqual(
                outcome.as_json()["limitations"],
                normalize_result(result)["limitations"],
                case.identifier,
            )
            entries += len(outcome.limitations)
        # 33 `coverage_gap` cases and 4 terminal `needs_entity_discovery`
        # ones; the 5 `invalid_request` and 6 `unsupported` refusals carry
        # none, which is what makes the comparison above non-vacuous.
        self.assertEqual(entries, 37)

    def test_the_comparison_discriminates(self):
        # #17 rule 9. A limitation whose kind was written some other way
        # fails the assertion above, so it is a check that can fail.
        _, outcomes = measure(EVALUATION_SET, perfect, empty_runtime())
        carrying = next(o for o in outcomes if o.limitations)
        self.assertNotEqual(
            [{"kind": limitation.kind.name, "detail": limitation.detail}
             for limitation in carrying.limitations],
            carrying.as_json()["limitations"],
        )


class TheRuntimeNeverRefusesWhatRevalidationAccepted(unittest.TestCase):
    """Why `refusal_detail` has one source and not two.

    #89's table asks for the detail of "the runtime's own refusal when
    revalidation passed and the runtime refused". That combination cannot
    occur on the adapter path: `answer` revalidates with the runtime's own
    `runtime.request.validate`, then hands the *same* `Request` to the
    runtime, which validates it again with the same pure function. So a
    proposal that passed revalidation is never refused by the runtime, and
    `Runtime.execute` swallows its `Refusal` into a `Result` besides, so
    there would be no detail left to read.

    That is an argument, and #17 rule 9 says an argument is not evidence.
    This is the check.
    """

    RESOLVERS = (perfect, without_the_message_key, inventing_the_message_key)

    def test_an_accepted_proposal_never_comes_back_refused(self):
        for resolve in self.RESOLVERS:
            _, outcomes = measure(EVALUATION_SET, resolve, empty_runtime())
            for outcome in outcomes:
                if outcome.accepted:
                    self.assertNotIn(outcome.status, NO_CONNECTION, outcome.identifier)
                    self.assertIsNone(outcome.refusal_detail, outcome.identifier)
                else:
                    self.assertIn(outcome.status, NO_CONNECTION, outcome.identifier)
                    self.assertIsNotNone(outcome.refusal_detail, outcome.identifier)

    def test_the_invariant_discriminates(self):
        # A runtime that refuses what revalidation accepted is exactly the
        # shape the unreachable branch would take. Under it the assertion
        # above inverts, which is what makes the `None` above a finding
        # rather than an omission.
        _, outcomes = measure(EVALUATION_SET, perfect, RefusingRuntime())
        accepted = [outcome for outcome in outcomes if outcome.accepted]
        self.assertTrue(accepted)
        for outcome in accepted:
            self.assertIn(outcome.status, NO_CONNECTION)
            self.assertIsNone(outcome.refusal_detail)


class StubCall:
    """A `Call` without the SDK, so the `run.py` half is testable everywhere.

    `client.py` cannot be imported when the adapter extra is absent, and
    `repository-checks` installs nothing. Gating every assertion about the
    raw document on the SDK would leave the file that decides what gets
    written -- and what deliberately does not -- covered only in a job that
    spends a credential.
    """

    def __init__(self, text, usage=None, stop_reason="end_turn"):
        self.text = text
        self.usage = usage
        self.stop_reason = stop_reason

    def as_json(self):
        return {"text": self.text, "stop_reason": self.stop_reason, "usage": self.usage}


class StubRecorder:
    def __init__(self, *calls):
        self.calls = tuple(calls)


class TheSecondArtifactAndWhatTheFirstGainsFromIt(unittest.TestCase):
    """#90, on the `run.py` side. No SDK, no network, no database."""

    def test_the_raw_path_sits_beside_the_artifact(self):
        self.assertEqual(
            runner.raw_path(pathlib.Path("milestone-2-comparison.json")).name,
            "milestone-2-comparison.raw.json",
        )
        self.assertEqual(
            runner.raw_path(pathlib.Path("/tmp/out/x.json")),
            pathlib.Path("/tmp/out/x.raw.json"),
        )
        # Derived, not configured: the two files cannot be pointed at
        # unrelated places, which is what makes the workflow's paths
        # predictable from the one `--artifact` it passes.
        self.assertEqual(
            runner.raw_path(runner.DEFAULT_ARTIFACT).parent,
            runner.DEFAULT_ARTIFACT.parent,
        )

    def test_usage_totals_sums_every_call(self):
        recorder = StubRecorder(
            StubCall("a", {"input_tokens": 10, "output_tokens": 3}),
            StubCall("b", {"input_tokens": 5, "output_tokens": 2}),
        )
        self.assertEqual(
            runner.usage_totals(recorder.calls),
            {"input_tokens": 15, "output_tokens": 5},
        )

    def test_usage_totals_sums_only_what_adds_up(self):
        # A usage payload may carry nested breakdowns beside its counts. A
        # total is only meaningful for a number; the per-call records keep
        # whatever the SDK returned, in full, so nothing is lost here.
        totals = runner.usage_totals(
            (
                StubCall("a", {"input_tokens": 4, "cache_creation": {"x": 1}, "ok": True}),
                StubCall("b", {"input_tokens": 6, "cache_creation": {"x": 2}}),
            )
        )
        self.assertEqual(totals, {"input_tokens": 10})

    def test_usage_totals_is_none_rather_than_zero_when_nothing_reported(self):
        # A run that could not observe its cost has not observed a cost of
        # zero -- the rule `Report.executed` applies to a run that touched no
        # database.
        self.assertIsNone(runner.usage_totals(()))
        self.assertIsNone(runner.usage_totals((StubCall("a"), StubCall("b", {}))))

    def test_the_main_artifact_gains_usage_totals_only_when_there_are_any(self):
        with_usage = runner.perform(
            propose=perfect,
            runtime=empty_runtime(),
            model="m",
            decoding=DECODING,
            recorder=StubRecorder(StubCall("a", {"input_tokens": 9})),
        )
        self.assertEqual(with_usage["usage_totals"], {"input_tokens": 9})

        for label, recorder in (
            ("no recorder", None),
            ("no usage", StubRecorder(StubCall("a"))),
        ):
            with self.subTest(recorder=label):
                document = runner.perform(
                    propose=perfect,
                    runtime=empty_runtime(),
                    model="m",
                    decoding=DECODING,
                    recorder=recorder,
                )
                self.assertNotIn("usage_totals", document)

    def test_the_raw_document_ties_itself_to_the_run(self):
        recorder = StubRecorder(StubCall("first", {"input_tokens": 2}), StubCall("second"))
        document = runner.perform(
            propose=perfect,
            runtime=empty_runtime(),
            model="m",
            decoding=DECODING,
            recorder=recorder,
        )
        raw = runner.raw_document(document, recorder.calls)
        self.assertEqual(raw["run_identifier"], document["run_identifier"])
        self.assertEqual([entry["text"] for entry in raw["calls"]], ["first", "second"])
        self.assertEqual(raw["usage_totals"], {"input_tokens": 2})
        # The raw file carries no report, no judgement and no thresholds:
        # it is what the calls returned, not a second opinion on them.
        # `usage_totals` is repeated from the main artifact on purpose, so
        # this file is readable on its own; `run_identifier` is what ties
        # the two halves together.
        self.assertEqual(sorted(raw), ["calls", "run_identifier", "usage_totals"])
        self.assertEqual(raw["usage_totals"], document["usage_totals"])

    def test_the_raw_document_is_json(self):
        recorder = StubRecorder(StubCall("t", {"input_tokens": 1}))
        document = runner.perform(
            propose=perfect, runtime=empty_runtime(), model="m", decoding=DECODING,
            recorder=recorder,
        )
        raw = runner.raw_document(document, recorder.calls)
        self.assertEqual(json.loads(json.dumps(raw)), raw)

    def test_the_report_and_the_outcomes_are_untouched_by_recording(self):
        # #90 adds one key to the main artifact and nothing else. A recorder
        # that changed a metric would change what the Section 8 gate reads.
        without = runner.perform(
            propose=perfect, runtime=empty_runtime(), model="m", decoding=DECODING
        )
        with_recorder = runner.perform(
            propose=perfect, runtime=empty_runtime(), model="m", decoding=DECODING,
            recorder=StubRecorder(StubCall("t", {"input_tokens": 1})),
        )
        # `started_at` is the wall clock and `run_identifier` is a fresh
        # uuid; everything else in the report is a measurement and must be
        # identical, recorder or not.
        for document in (without, with_recorder):
            document["report"].pop("started_at")
        self.assertEqual(without["report"], with_recorder["report"])
        self.assertEqual(without["judgement"], with_recorder["judgement"])
        self.assertEqual(
            sorted(set(with_recorder) - set(without)), ["usage_totals"]
        )


class TheWorkflowUploadsBothFilesUnderSeparateNames(unittest.TestCase):
    """Two artifacts, not one zip with two files in it.

    Raised as N4 on #99: shipping both under the name `milestone-2-comparison`
    means the writer who downloads "the artifact" to commit the acceptance
    record unpacks the never-committed file into the checkout beside it,
    where one `git add -A` commits it. Nothing mechanical catches that.
    Separate names mean downloading the one you need cannot hand you the one
    you must not commit.

    Read as text rather than YAML because `repository-checks` installs
    nothing, so a test importing PyYAML would skip in the one job that
    always runs. What can actually drift is the filename -- `run.py` derives
    it and the workflow names it, and nothing else ties the two together.
    """

    def setUp(self):
        self.text = WORKFLOW.read_text()

    def test_the_upload_names_the_file_the_runner_actually_writes(self):
        written = runner.raw_path(runner.DEFAULT_ARTIFACT).name
        self.assertEqual(written, "milestone-2-comparison.raw.json")
        self.assertIn(f"path: {written}\n", self.text)
        self.assertIn(f"path: {runner.DEFAULT_ARTIFACT.name}\n", self.text)

    def test_the_dispatch_step_passes_the_artifact_the_paths_derive_from(self):
        self.assertIn(f"--artifact {runner.DEFAULT_ARTIFACT.name}", self.text)

    def test_the_workflow_says_the_raw_file_is_never_committed(self):
        # Not decoration. The rule lives nowhere a check can enforce it, so
        # the next reader of this file has to be told by the file.
        #
        # This asserted `"never" in text` and `"committed" in text` and could
        # not fail: "Never on push, pull_request, or a schedule" has been on
        # line 3 since #57, and "committed" appears in the main artifact's
        # own comment. Deleting every word of the raw-upload block left it
        # green. Raised as N6 on #99 -- #17 rule 9, in a test written to
        # protect this slice's one safety property. Now anchored to the step
        # that carries the rule.
        self.assertIn("name: Upload the raw record, which is never committed", self.text)
        self.assertIn("is **never committed**:", self.text)

    def test_no_single_artifact_carries_both_files(self):
        # N4's structural property, asserted without PyYAML so it runs in
        # every job rather than only where an optional dependency happens to
        # be installed. `path: |` is the multi-file form: its absence is what
        # says the two files cannot travel in one download.
        self.assertNotIn("path: |", self.text)
        self.assertEqual(self.text.count("uses: actions/upload-artifact"), 2)
        self.assertIn("name: milestone-2-comparison\n", self.text)
        self.assertIn("name: milestone-2-comparison-raw\n", self.text)

    @unittest.skipUnless(
        importlib.util.find_spec("yaml") is not None, "PyYAML is not installed"
    )
    def test_each_file_is_its_own_artifact(self):
        # The assertion N4 is really about: not that both names appear, but
        # that no single artifact carries both. Skipped where PyYAML is
        # absent; the text assertions above always run.
        import yaml

        document = yaml.safe_load(self.text)
        uploads = [
            step
            for step in document["jobs"]["comparison"]["steps"]
            if str(step.get("uses", "")).startswith("actions/upload-artifact")
        ]
        self.assertEqual(len(uploads), 2)
        by_name = {step["with"]["name"]: step["with"] for step in uploads}
        self.assertEqual(
            by_name["milestone-2-comparison"]["path"].strip(),
            runner.DEFAULT_ARTIFACT.name,
        )
        self.assertEqual(
            by_name["milestone-2-comparison-raw"]["path"].strip(),
            runner.raw_path(runner.DEFAULT_ARTIFACT).name,
        )
        for settings in uploads:
            self.assertEqual(settings["with"]["if-no-files-found"], "error")
            # One file each. A `path:` that grew a second entry would put the
            # never-committed file back in the acceptance download.
            self.assertEqual(len(settings["with"]["path"].split()), 1)


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


@unittest.skipUnless(HAS_SDK, "the adapter extra is not installed")
class TheRealAdapterRecordsEveryCallOverTheWholeSet(unittest.TestCase):
    """#90's acceptance evidence, end to end, against the real `Adapter`.

    The client is a stub that echoes the request it was handed, so record
    *n* is identifiably case *n*: 48 identical records would satisfy a count
    and prove nothing about order. No credential is spent and no socket is
    opened.
    """

    TOKENS = {"input_tokens": 10, "output_tokens": 3}

    class EchoingUsage:
        """The SDK returns a model object, not a mapping. So does this."""

        def __init__(self, counts):
            self._counts = counts

        def model_dump(self):
            return dict(self._counts)

    def adapter(self, *, usage=True):
        tokens = self.TOKENS

        class Echoing:
            def __init__(inner):
                inner.messages = types.SimpleNamespace(create=inner._create)

            def _create(inner, **keywords):
                asked = keywords["messages"][0]["content"]
                body = json.dumps({"route": "unsupported", "arguments": {}, "asked": asked})
                fields = {
                    "stop_reason": "end_turn",
                    "content": [types.SimpleNamespace(type="text", text=body)],
                }
                if usage:
                    # A `Mock` would be wrong here: it invents `usage` and
                    # `model_dump` on demand, so the "SDK exposed nothing"
                    # case could not be expressed at all.
                    fields["usage"] = TheRealAdapterRecordsEveryCallOverTheWholeSet.EchoingUsage(
                        tokens
                    )
                return types.SimpleNamespace(**fields)

        return Adapter(client=Echoing())

    def run_once(self, *, usage=True):
        adapter = self.adapter(usage=usage)
        document = runner.perform(
            propose=adapter.propose,
            runtime=empty_runtime(),
            model=REAL_MODEL,
            decoding=DECODING,
            recorder=adapter,
        )
        return adapter, document

    def test_one_record_per_case_in_registered_order_carrying_the_stubs_text(self):
        adapter, document = self.run_once()
        raw = runner.raw_document(document, adapter.calls)
        self.assertEqual(len(raw["calls"]), 48)
        self.assertEqual(len(EVALUATION_SET), 48)
        for case, entry in zip(EVALUATION_SET, raw["calls"]):
            self.assertEqual(json.loads(entry["text"])["asked"], case.text, case.identifier)
            self.assertEqual(entry["stop_reason"], "end_turn")
            self.assertEqual(entry["usage"], self.TOKENS)

    def test_the_totals_are_the_sum_over_all_forty_eight_calls(self):
        _, document = self.run_once()
        self.assertEqual(
            document["usage_totals"],
            {"input_tokens": 10 * 48, "output_tokens": 3 * 48},
        )

    def test_a_stub_exposing_no_usage_leaves_the_key_out_and_raises_nothing(self):
        adapter, document = self.run_once(usage=False)
        self.assertNotIn("usage_totals", document)
        raw = runner.raw_document(document, adapter.calls)
        self.assertEqual(len(raw["calls"]), 48)
        self.assertIsNone(raw["usage_totals"])
        self.assertTrue(all(entry["usage"] is None for entry in raw["calls"]))

    def test_the_baseline_makes_no_model_call(self):
        # `compare` runs both resolvers. Only the adapter's is the model's,
        # and 48 rather than 96 records is what says so.
        adapter, _ = self.run_once()
        self.assertEqual(len(adapter.calls), 48)


@unittest.skipUnless(HAS_SDK, "the adapter extra is not installed")
@unittest.skipUnless(HAS_DRIVER, "the database driver is not installed")
class TheWiringWritesBothFilesAndHandsOverTheRecorder(unittest.TestCase):
    """`main` is what a dispatched run executes, and #90 changes what it writes.

    `TheWiringPassesTheRealPin` below watches the pin the same way. The
    model and the database are replaced, so this spends no credential,
    opens no connection and makes no network call.
    """

    def test_main_writes_the_artifact_and_the_raw_file_beside_it(self):
        with tempfile.TemporaryDirectory() as directory:
            artifact = pathlib.Path(directory) / "comparison.json"
            with (
                unittest.mock.patch.object(
                    adapter_client.Adapter,
                    "from_environment",
                    classmethod(lambda cls: cls(client=object())),
                ),
                unittest.mock.patch.object(
                    runtime_connection, "PsycopgDatabase", lambda **keywords: object()
                ),
                unittest.mock.patch.object(
                    runner, "perform", lambda **keywords: self.document
                ),
            ):
                with contextlib.redirect_stdout(io.StringIO()) as printed:
                    code = runner.main(["--artifact", str(artifact)])
            self.assertEqual(code, 0)
            raw = runner.raw_path(artifact)
            self.assertTrue(artifact.exists(), "main did not write the artifact")
            self.assertTrue(raw.exists(), "main did not write the raw record")
            self.assertEqual(
                json.loads(raw.read_text())["run_identifier"],
                json.loads(artifact.read_text())["run_identifier"],
            )
            # The operator is told where the second file went and that it is
            # not for committing.
            self.assertIn(raw.name, printed.getvalue())
            self.assertIn("not committed", printed.getvalue())

    def test_main_prints_the_artifact_after_the_summary_and_never_the_raw_record(self):
        # #117. The writer session that drives the comparison cannot download
        # an Actions artifact, but it can read the job log. So the main
        # document -- the one that is committed under `docs/acceptance/` when
        # a run is adopted -- follows the summary on stdout, byte for byte
        # what `write` stored. The raw record does not: it is an artifact
        # and nothing else, for the reasons `run.py` gives.
        with tempfile.TemporaryDirectory() as directory:
            artifact = pathlib.Path(directory) / "comparison.json"
            with (
                unittest.mock.patch.object(
                    adapter_client.Adapter,
                    "from_environment",
                    classmethod(lambda cls: cls(client=object())),
                ),
                unittest.mock.patch.object(
                    runtime_connection, "PsycopgDatabase", lambda **keywords: object()
                ),
                unittest.mock.patch.object(
                    runner, "perform", lambda **keywords: self.document
                ),
            ):
                with contextlib.redirect_stdout(io.StringIO()) as printed:
                    runner.main(["--artifact", str(artifact)])
            output = printed.getvalue()
            stored = artifact.read_text()
            self.assertTrue(output.endswith(stored), "the artifact text is not the tail of stdout")
            head = output[: -len(stored)]
            self.assertIn("Comparison:", head)
            self.assertIn("not committed", head)
            # The tail parses back to exactly the written document.
            self.assertEqual(json.loads(output[len(head):]), json.loads(stored))
            raw = json.loads(runner.raw_path(artifact).read_text())
            self.assertIn("calls", raw)
            self.assertNotIn('"calls"', output)

    def test_main_hands_the_runner_the_adapter_as_the_recorder(self):
        # The recorder has to be the *same* object whose `propose` ran, or
        # the raw file records a different adapter's calls -- which is to
        # say, none.
        recorded = {}

        def recording_perform(**keywords):
            recorded.update(keywords)
            return self.document

        with tempfile.TemporaryDirectory() as directory:
            artifact = pathlib.Path(directory) / "artifact.json"
            with (
                unittest.mock.patch.object(runner, "perform", recording_perform),
                unittest.mock.patch.object(
                    adapter_client.Adapter,
                    "from_environment",
                    classmethod(lambda cls: cls(client=object())),
                ),
                unittest.mock.patch.object(
                    runtime_connection, "PsycopgDatabase", lambda **keywords: object()
                ),
            ):
                with contextlib.redirect_stdout(io.StringIO()):
                    runner.main(["--artifact", str(artifact)])
        recorder = recorded["recorder"]
        self.assertIsInstance(recorder, Adapter)
        self.assertIs(recorded["propose"].__self__, recorder)

    def setUp(self):
        self.document = runner.perform(
            propose=perfect, runtime=empty_runtime(), model=REAL_MODEL, decoding=DECODING
        )


@unittest.skipUnless(HAS_SDK, "the adapter extra is not installed")
@unittest.skipUnless(HAS_DRIVER, "the database driver is not installed")
class TheWiringPassesTheRealPin(unittest.TestCase):
    """#77 gap 1. `main` is what the dispatched workflow runs, and until now
    nothing watched it.

    `ThePinIsTheRealAdapterConfiguration` asserts that `perform` records the
    configuration it is handed. It does not assert that `main` hands it the
    real one, and `main` is the only caller in a dispatched run. Mutating
    `main` to pass a stale `pinned_decoding` left the entire suite green,
    which is how this gap was found rather than argued about; contract
    Section 4.6's model-pinning row is marked Automated and merge-blocking,
    so the evidence for it cannot stop one call short of the caller.

    The model and the database are replaced, so this spends no credential,
    opens no connection and makes no network call.
    """

    def recorded_call(self):
        """Run `main` with `perform` recording, and return its keywords."""
        recorded = {}

        def recording_perform(**keywords):
            recorded.update(keywords)
            return self.document

        with tempfile.TemporaryDirectory() as directory:
            artifact = pathlib.Path(directory) / "artifact.json"
            with (
                unittest.mock.patch.object(runner, "perform", recording_perform),
                unittest.mock.patch.object(
                    adapter_client.Adapter,
                    "from_environment",
                    classmethod(lambda cls: cls(client=object())),
                ),
                unittest.mock.patch.object(
                    runtime_connection, "PsycopgDatabase", lambda **keywords: object()
                ),
            ):
                # `main` prints its one-line summary; the test is about what
                # it passed, not what it said.
                with contextlib.redirect_stdout(io.StringIO()):
                    code = runner.main(["--artifact", str(artifact)])
            self.assertEqual(code, 0)
            self.assertTrue(artifact.exists(), "main did not write the artifact")
        return recorded

    def setUp(self):
        self.document = runner.perform(
            propose=perfect, runtime=empty_runtime(), model=REAL_MODEL, decoding=DECODING
        )

    def test_main_hands_the_runner_the_real_model_and_configuration(self):
        recorded = self.recorded_call()
        self.assertEqual(recorded["model"], REAL_MODEL)
        self.assertEqual(recorded["decoding"], Adapter.configuration())

    def test_main_hands_the_runner_the_real_configuration_as_the_pin(self):
        # The half the earlier fix left open: `judge` is what enforces
        # Section 4.6, and it reads `pinned_decoding`.
        recorded = self.recorded_call()
        self.assertEqual(recorded["pinned_decoding"], Adapter.configuration())
        self.assertIn("thinking", recorded["pinned_decoding"])
