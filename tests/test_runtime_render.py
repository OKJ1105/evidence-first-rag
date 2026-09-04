"""Section 4.8 rendering, and Section 4.9's check `E1`.

`E1`: "Every value in the rendered answer is present in the normalized
result." The test below is that check, run over an answer for each of the
seven statuses, plus its mirror: every piece of fixed text came from the
registered table rather than from anywhere else.

Both directions are needed. Checking only the values would pass a renderer
that invented a sentence carrying no substituted value ("this result is
probably complete"), which is the qualifier Section 4.8 prohibits. Checking
only the prose would pass one that substituted a number it computed.
"""

import decimal
import unittest

from evidence_first_rag import LimitationKind, Status
from evidence_first_rag.runtime import Request, Runtime, compose, render
from evidence_first_rag.runtime.render import values_of
from evidence_first_rag.runtime.render import (
    COLUMN_LABELS,
    FRAGMENTS,
    OPENING,
    SUPERSESSION_MARKER,
    Answer,
    Prose,
    Value,
)

from .runtime_support import (
    BASE,
    CHASSIS,
    CHASSIS_B,
    FakeDatabase,
    REVISED,
    candidate_row,
    mapping_row,
    message_row,
)

CANDIDATES = "TPL_SNAPSHOT_CANDIDATES_V1"
MESSAGE_FACTS = "TPL_MESSAGE_FACTS_V1"
SIGNAL_MAPPING = "TPL_SIGNAL_MAPPING_V1"
MESSAGE = BASE | {"message_key": "SAMPLE_MSG_ENGINE_STATUS"}
SIGNAL = MESSAGE | {"signal_key": "SAMPLE_SIG_ENGINE_SPEED"}

FIXED_TEXT = frozenset(FRAGMENTS.values()) | frozenset(OPENING.values()) | COLUMN_LABELS


def answered(route, arguments, rows, scope=None, **request):
    database = FakeDatabase({CANDIDATES: (candidate_row(scope or BASE),), **rows})
    return Runtime(database=database).execute(
        Request(route=route, arguments=arguments, **request)
    )


def one_of_each_status():
    """A result for every one of the seven Section 5 families."""
    superseded = mapping_row(
        asserting=CHASSIS,
        source=CHASSIS,
        target=CHASSIS_B,
        asserting_superseded_by=CHASSIS_B,
        source_superseded_by=CHASSIS_B,
    )
    return {
        Status.SUCCESS: answered(
            "message_facts", MESSAGE, {MESSAGE_FACTS: (message_row(),)}
        ),
        Status.NOT_FOUND: answered("message_facts", MESSAGE, {MESSAGE_FACTS: ()}),
        Status.COVERAGE_GAP: Runtime(database=FakeDatabase({CANDIDATES: ()})).execute(
            Request(route="message_facts", arguments=MESSAGE)
        ),
        Status.AMBIGUOUS: Runtime(
            database=FakeDatabase(
                {CANDIDATES: (candidate_row(BASE), candidate_row(REVISED))}
            )
        ).execute(
            Request(
                route="message_facts",
                arguments={k: v for k, v in MESSAGE.items() if k != "snapshot_label"},
            )
        ),
        Status.UNSUPPORTED: answered("message_fact", MESSAGE, {}),
        Status.INVALID_REQUEST: answered("message_facts", {"nonsense": "x"}, {}),
        Status.NEEDS_ENTITY_DISCOVERY: answered("message_facts", BASE, {}),
        # Not an eighth status: a `success` that also carries three of the
        # `limitations` kinds, so the renderer is exercised on entries too.
        "success with limitations": answered(
            "signal_mapping",
            {**CHASSIS, "message_key": "SAMPLE_MSG_ENGINE_STATUS", "signal_key": "SAMPLE_SIG_ENGINE_SPEED"},
            {SIGNAL_MAPPING: (superseded,)},
            scope=CHASSIS,
            scope_selected_by_user=True,
        ),
    }


class EveryValueInTheAnswerIsInTheResult(unittest.TestCase):
    """Check `E1`."""

    def test_for_every_status(self):
        for label, result in one_of_each_status().items():
            with self.subTest(status=getattr(label, "value", label)):
                answer = compose(result)
                unexplained = set(answer.values()) - values_of(result)
                self.assertEqual(unexplained, set())

    def test_the_answer_is_not_empty_for_any_of_them(self):
        # An `E1` that passed because nothing was rendered would prove nothing.
        for label, result in one_of_each_status().items():
            with self.subTest(status=getattr(label, "value", label)):
                self.assertGreater(len(compose(result).values()), 0)
                self.assertIn(result.status.value, render(result))

    def test_the_check_fails_on_an_answer_that_added_a_value(self):
        # The check itself, probed. A renderer that inserted a fact the result
        # does not contain has to be caught here, and a check nobody has seen
        # fail is a check nobody knows works.
        result = one_of_each_status()[Status.SUCCESS]
        tampered = Answer(segments=compose(result).segments + (Value("20"),))
        self.assertNotEqual(set(tampered.values()) - values_of(result), set())


class EveryFixedWordCameFromTheRegisteredText(unittest.TestCase):
    """Section 4.8's other half: the renderer adds no qualifier and no
    inference, so its prose is a closed set rather than free text."""

    def test_for_every_status(self):
        for label, result in one_of_each_status().items():
            with self.subTest(status=getattr(label, "value", label)):
                unregistered = set(compose(result).prose()) - FIXED_TEXT
                self.assertEqual(unregistered, set())

    def test_the_check_fails_on_an_answer_that_added_a_qualifier(self):
        # The mirror probe. A sentence that carries no substituted value slips
        # past `E1` entirely, which is why this direction is checked at all.
        result = one_of_each_status()[Status.SUCCESS]
        tampered = Answer(
            segments=compose(result).segments + (Prose(" This looks complete."),)
        )
        self.assertNotEqual(set(tampered.prose()) - FIXED_TEXT, set())

    def test_every_status_has_its_own_opening_sentence(self):
        self.assertEqual(set(OPENING), set(Status))
        self.assertEqual(len(set(OPENING.values())), len(Status))


class TheRenderedValuesKeepTheirStoredForm(unittest.TestCase):
    def test_a_numeric_value_is_not_rounded_or_reformatted(self):
        # Section 6: "Numeric values are returned with the precision stored in
        # the schema; no rounding occurs in the runtime or the renderer."
        result = answered(
            "signal_facts",
            SIGNAL,
            {
                "TPL_SIGNAL_FACTS_V1": (
                    {
                        **message_row(),
                        "signal_key": "SAMPLE_SIG_ENGINE_SPEED",
                        "unit_label": "SAMPLE_UNIT_RPM",
                        "scale_factor": decimal.Decimal("0.250"),
                        "scale_offset": decimal.Decimal("0.000"),
                        "bit_width": 16,
                        "bit_offset": 8,
                        "transmit_mode": None,
                        "transmit_period_ms": None,
                        "payload_byte_length": None,
                        "frame_identifier": None,
                    },
                )
            },
        )
        self.assertIn("0.250", render(result))
        self.assertNotIn("0.25,", render(result))

    def test_a_null_renders_as_the_registered_token_and_not_as_a_phrase(self):
        result = answered(
            "message_facts",
            MESSAGE,
            {MESSAGE_FACTS: (message_row(transmit_period_ms=None),)},
        )
        self.assertIn("transmit_period_ms: null", render(result))

    def test_a_current_snapshot_adds_no_supersession_noise(self):
        # Review finding N3. A routine success carries four supersession
        # columns that are null, and rendering them would pad every answer
        # with absence. They are omitted only when empty.
        text = render(
            answered("message_facts", MESSAGE, {MESSAGE_FACTS: (message_row(),)})
        )
        self.assertNotIn("superseded_by", text)
        self.assertIn("frame_identifier: 256", text)

    def test_a_supersession_that_carries_a_value_is_still_rendered(self):
        text = render(
            answered(
                "message_facts",
                {**CHASSIS, "message_key": "SAMPLE_MSG_ENGINE_STATUS"},
                {MESSAGE_FACTS: (message_row(CHASSIS, superseded_by=CHASSIS_B),)},
                scope=CHASSIS,
            )
        )
        self.assertIn("superseded_by_revision_label: SAMPLE_REV_B", text)

    def test_the_marker_matches_every_registered_supersession_column(self):
        # Matched rather than listed, so this is the test that the match is
        # the right one: a column the registry builds and the marker misses
        # would be rendered as null noise again.
        from evidence_first_rag.registry import REGISTERED

        built = {
            column
            for template in REGISTERED
            for column in template.result_columns
            if column.endswith(("_project_code", "_revision_label", "_network_name", "_snapshot_label"))
            and "superseded" in column
        }
        self.assertEqual(len(built), 16)
        for column in built:
            self.assertIn(SUPERSESSION_MARKER, column)

    def test_a_candidate_list_renders_every_candidate(self):
        result = one_of_each_status()[Status.AMBIGUOUS]
        text = render(result)
        self.assertIn("SAMPLE_SNAP_BASE", text)
        self.assertIn("SAMPLE_SNAP_REVISED", text)

    def test_a_negative_outcome_still_renders_its_limitations(self):
        result = one_of_each_status()[Status.COVERAGE_GAP]
        text = render(result)
        self.assertIn(LimitationKind.COVERAGE_NOT_ESTABLISHED.value, text)
        # A `limitations` detail is user-facing prose, so it carries the scope
        # it names in the contract's own vocabulary rather than as a repr of
        # whatever structure the runtime happened to hold it in.
        self.assertIn("network_name=SAMPLE_NET_POWERTRAIN", text)
        self.assertNotIn("{'", text)

    def test_the_prose_carries_no_doubled_separator(self):
        for label, result in one_of_each_status().items():
            with self.subTest(status=getattr(label, "value", label)):
                self.assertNotIn("  ", render(result))


if __name__ == "__main__":
    unittest.main(verbosity=2)
