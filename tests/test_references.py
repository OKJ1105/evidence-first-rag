"""Section 4.2: a canonical reference cannot be built with a scope hole."""

import dataclasses
import unittest

from evidence_first_rag import (
    SCOPE_DIMENSIONS,
    MessageReference,
    SignalReference,
    SnapshotScope,
)

from .support import scope

# Section 4.2 forbids the runtime from supplying a missing dimension. These
# are the ways a caller might hand one over anyway.
ABSENT_VALUES = ("", None, 0, False, [])


class AScopeIsCompleteOrItDoesNotExist(unittest.TestCase):
    def test_the_four_dimensions_are_section_4_2s(self):
        self.assertEqual(
            SCOPE_DIMENSIONS,
            ("project_code", "revision_label", "network_name", "snapshot_label"),
        )

    def test_every_dimension_rejects_an_absent_value(self):
        for dimension in SCOPE_DIMENSIONS:
            for absent in ABSENT_VALUES:
                with self.subTest(dimension=dimension, absent=absent):
                    with self.assertRaises(ValueError) as raised:
                        scope(**{dimension: absent})
                    self.assertIn(dimension, str(raised.exception))

    def test_a_missing_dimension_is_a_construction_error(self):
        with self.assertRaises(TypeError):
            SnapshotScope(
                project_code="SAMPLE_PROJECT_ALPHA",
                revision_label="SAMPLE_REV_A",
                network_name="SAMPLE_NET_POWERTRAIN",
            )

    def test_a_complete_scope_is_frozen(self):
        with self.assertRaises(dataclasses.FrozenInstanceError):
            scope().project_code = "SAMPLE_PROJECT_BETA"

    def test_the_parameters_are_the_four_section_4_4_allows(self):
        self.assertEqual(set(scope().as_parameters()), set(SCOPE_DIMENSIONS))


class AMessageReference(unittest.TestCase):
    def test_it_rejects_an_absent_message_key(self):
        for absent in ABSENT_VALUES:
            with self.subTest(absent=absent):
                with self.assertRaises(ValueError):
                    MessageReference(scope=scope(), message_key=absent)

    def test_it_rejects_a_scope_that_is_not_one(self):
        with self.assertRaises(ValueError):
            MessageReference(scope="SAMPLE_PROJECT_ALPHA", message_key="SAMPLE_MSG_A")

    def test_its_parameters_are_the_five_tpl_message_facts_v1_requires(self):
        reference = MessageReference(scope=scope(), message_key="SAMPLE_MSG_A")
        self.assertEqual(
            set(reference.as_parameters()), set(SCOPE_DIMENSIONS) | {"message_key"}
        )


class ASignalReference(unittest.TestCase):
    def setUp(self):
        self.message = MessageReference(scope=scope(), message_key="SAMPLE_MSG_A")

    def test_it_rejects_an_absent_signal_key(self):
        for absent in ABSENT_VALUES:
            with self.subTest(absent=absent):
                with self.assertRaises(ValueError):
                    SignalReference(message=self.message, signal_key=absent)

    def test_it_cannot_be_built_on_a_bare_message_key(self):
        # Section 4.2: equal signal keys under different parents are
        # different signals, so the parent travels with the reference.
        with self.assertRaises(ValueError):
            SignalReference(message="SAMPLE_MSG_A", signal_key="SAMPLE_SIG_A")

    def test_it_exposes_the_parent_scope_and_key(self):
        reference = SignalReference(message=self.message, signal_key="SAMPLE_SIG_A")
        self.assertEqual(reference.scope, scope())
        self.assertEqual(reference.message_key, "SAMPLE_MSG_A")

    def test_its_parameters_are_the_six_tpl_signal_facts_v1_requires(self):
        reference = SignalReference(message=self.message, signal_key="SAMPLE_SIG_A")
        self.assertEqual(
            set(reference.as_parameters()),
            set(SCOPE_DIMENSIONS) | {"message_key", "signal_key"},
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
