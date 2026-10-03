"""api-v0.1 Section 4.4: a result becomes a document and the document becomes
the result back.

Section 8's row for Section 4.4 registers "a round-trip test: every `FX-*` and
`DX-*` result serialized and read back equals the original; a test that a
numeric column value survives as its stored decimal text". `RESULTS` below is
that set: one result per structural case, built through the same fakes the
runtime and discovery suites use, so nothing here needs a driver or a
database.

The round trip is asserted on the **object**, not on the document. Comparing
two documents would pass for a function that dropped a key on the way out and
never looked for it on the way back, which is the failure mode Section 4.4's
never-omitted rule exists to prevent -- and the one
`conformance/normalize.py` has today for the selection record (#176).
"""

import dataclasses
import decimal
import json
import unittest

from evidence_first_rag import Limitation, LimitationKind, Result, Status
from evidence_first_rag.api import NUMERIC_COLUMNS, as_json, dumps, from_json
from evidence_first_rag.discovery import (
    Discovery,
    DiscoveryRequest,
    DiscoveryResult,
    DiscoveryStatus,
    Selection,
    SelectionRequest,
)
from evidence_first_rag.runtime import Request, Runtime

from .discovery_support import BASE, MESSAGE, SIGNAL, database, discovery_row
from .runtime_support import CHASSIS, FakeDatabase, candidate_row, mapping_row, message_row, signal_row

PROVENANCE = ("fixtures/registry/approved_entity.jsonl",)

FACT_MESSAGE = BASE | {"message_key": "SAMPLE_MSG_ENGINE_STATUS"}
FACT_SIGNAL = FACT_MESSAGE | {"signal_key": "SAMPLE_SIG_ENGINE_SPEED"}

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


def fact(route, arguments, rows, scope=None, candidates=None, **request) -> Result:
    """One `mvp-v0.1` result, through the real runtime over fake rows.

    `candidates=()` is how a test reaches `coverage_gap`: Section 5 assigns
    zero matching snapshots to it, and the candidate template is the only
    thing that can report zero.
    """
    found = (candidate_row(scope or BASE),) if candidates is None else tuple(candidates)
    database = FakeDatabase({"TPL_SNAPSHOT_CANDIDATES_V1": found, **rows})
    return Runtime(database=database, fixture_provenance=PROVENANCE).execute(
        Request(route=route, arguments=arguments, **request)
    )


def discover(arguments, **rows) -> DiscoveryResult:
    return Discovery(database=database(**rows), fixture_provenance=PROVENANCE).execute(
        DiscoveryRequest(arguments=arguments)
    )


def dispatched_selection() -> Result:
    """A selection that reached a fact route, so its result carries the
    Section 4.8 `selection` record and the selected candidate's alias
    provenance. The one shape `conformance/normalize.py` drops (#176), and the
    reason this module exists."""
    digest = discover(SELECT_TERM, exact=TWO_SIGNALS).evidence_bundle.candidate_set_id
    db = database(exact=TWO_SIGNALS)
    db.rows["TPL_SIGNAL_FACTS_V1"] = (
        signal_row(message_key="SAMPLE_MSG_DIAGNOSTIC_EVENT", signal_key="SAMPLE_SIG_FAULT_CODE"),
    )
    return Selection(database=db, fixture_provenance=PROVENANCE).execute(
        SelectionRequest(
            arguments=SELECT_TERM | {
                "candidate_set_id": digest,
                "selected_rank": "2",
                "target_route": "signal_facts",
            }
        )
    )


def _results() -> dict:
    """One result per structural case, keyed by the name a failure reports."""
    return {
        # mvp-v0.1 Section 5, all seven.
        "success/message_facts": fact("message_facts", FACT_MESSAGE, {"TPL_MESSAGE_FACTS_V1": (message_row(),)}),
        "success/signal_facts": fact("signal_facts", FACT_SIGNAL, {"TPL_SIGNAL_FACTS_V1": (signal_row(),)}),
        "success/signal_mapping": fact("signal_mapping", FACT_SIGNAL, {"TPL_SIGNAL_MAPPING_V1": (mapping_row(),)}),
        "success/superseded": fact(
            "signal_mapping", FACT_SIGNAL, {"TPL_SIGNAL_MAPPING_V1": (mapping_row(asserting_superseded_by=CHASSIS),)}
        ),
        "not_found": fact("message_facts", FACT_MESSAGE, {"TPL_MESSAGE_FACTS_V1": ()}),
        "ambiguous": fact(
            "message_facts",
            {k: v for k, v in FACT_MESSAGE.items() if k != "snapshot_label"},
            {},
            scope=BASE,
        ),
        "coverage_gap": fact("message_facts", FACT_MESSAGE | {"network_name": "SAMPLE_NET_ABSENT"}, {}, candidates=()),
        "invalid_request": fact("message_facts", FACT_MESSAGE | {"nonsense": "SAMPLE_X"}, {}),
        "unsupported": fact("SAMPLE_NOT_A_ROUTE", FACT_MESSAGE, {}),
        "needs_entity_discovery": fact("message_facts", BASE, {}),
        "selection/dispatched": dispatched_selection(),
        # entity-discovery-v0.1 Section 5, all seven.
        "resolved": discover(MESSAGE, exact=(discovery_row(),)),
        "candidates": discover(SELECT_TERM, exact=TWO_SIGNALS),
        "resolved/alias": discover(
            MESSAGE | {"term": "SAMPLE_ALIAS_ENGINE"},
            exact=(discovery_row(match_tier=2, match_kind="approved_alias", match_text="SAMPLE_ALIAS_ENGINE"),),
        ),
        "discovery/not_found": discover(MESSAGE),
        "discovery/coverage_gap": discover(MESSAGE | {"network_name": "SAMPLE_NET_ABSENT"}, candidates=()),
        "discovery/ambiguous": discover({k: v for k, v in MESSAGE.items() if k != "snapshot_label"}, exact=(discovery_row(),)),
        # `0.4.0`: above the Section 4.3 bound, listed and not searched.
        "discovery/ambiguous/unsearched": discover(
            {k: v for k, v in MESSAGE.items() if k != "snapshot_label"},
            candidates=tuple(candidate_row(BASE | {"snapshot_label": f"SAMPLE_SNAP_{n:02d}"}) for n in range(11)),
        ),
        # `0.4.0`: searched in every candidate scope and matched in none.
        "discovery/not_found/incomplete_scope": discover({k: v for k, v in MESSAGE.items() if k != "snapshot_label"}),
        "discovery/invalid_request": discover(MESSAGE | {"nonsense": "SAMPLE_X"}),
        "discovery/unsupported": discover(MESSAGE | {"entity_kind": "SAMPLE_KIND"}),
    }


RESULTS = _results()


class EveryResultSurvivesTheRoundTrip(unittest.TestCase):
    """Section 8's registered row, over every structural case."""

    def test_every_case_reads_back_equal(self):
        for name, result in RESULTS.items():
            with self.subTest(case=name):
                self.assertEqual(from_json(as_json(result)), result)

    def test_the_set_reaches_every_status_of_both_vocabularies(self):
        # A round-trip test is only as wide as its inputs, so the width is
        # asserted rather than assumed: a status family added to either
        # contract fails here until a case reaches it.
        self.assertEqual(
            {r.status for r in RESULTS.values() if isinstance(r, Result)},
            set(Status),
        )
        self.assertEqual(
            {r.status for r in RESULTS.values() if isinstance(r, DiscoveryResult)},
            set(DiscoveryStatus),
        )

    def test_a_document_survives_json_itself(self):
        # `as_json` producing a dict proves nothing about what a socket
        # carries; this is the same round trip through the text.
        for name, result in RESULTS.items():
            with self.subTest(case=name):
                self.assertEqual(from_json(json.loads(dumps(as_json(result)))), result)


class TheEvidenceMilestoneThreeAdded(unittest.TestCase):
    """The three fields `conformance/normalize.py` does not emit (#176), which
    is why this module is a second projection rather than a call to it."""

    def setUp(self):
        self.result = RESULTS["selection/dispatched"]
        self.document = as_json(self.result)

    def test_the_dispatched_selection_is_a_success_carrying_the_record(self):
        # `DX-017`'s shape. If this stops holding the rest of the class is
        # asserting things about a result that is not the one it means.
        self.assertIs(self.result.status, Status.SUCCESS)
        self.assertIsNotNone(self.result.evidence_bundle.selection)

    def test_the_selection_record_reaches_the_document(self):
        record = self.document["evidence_bundle"]["selection"]
        self.assertEqual(record["candidate_set_id"], self.result.evidence_bundle.selection["candidate_set_id"])
        # Section 4.8 requires the step-2 re-run's own execution evidence
        # inside the record. A projection that carried the record but flattened
        # what is nested in it would pass a shallower assertion.
        self.assertEqual(
            record["discovery_bound_parameters"],
            dict(self.result.evidence_bundle.selection["discovery_bound_parameters"]),
        )

    def test_alias_provenance_and_the_approval_reference_reach_the_document(self):
        trace = self.document["source_trace"]
        self.assertEqual(len(trace["alias_provenance"]), 1)
        self.assertEqual(trace["entity_approval_reference"], self.result.source_trace.entity_approval_reference)
        self.assertNotEqual(trace["entity_approval_reference"], "")

    def test_all_three_survive_the_round_trip(self):
        back = from_json(self.document)
        self.assertEqual(back.evidence_bundle.selection, self.result.evidence_bundle.selection)
        self.assertEqual(back.source_trace.alias_provenance, self.result.source_trace.alias_provenance)
        self.assertEqual(
            back.source_trace.entity_approval_reference, self.result.source_trace.entity_approval_reference
        )


class ANumericColumnIsItsStoredDecimalText(unittest.TestCase):
    """Section 4.4's one value rule that is not the obvious one, and the reason
    for it: a JSON number would pass through a binary float, and `mvp-v0.1`
    Section 6 forbids rounding anywhere."""

    def test_it_is_written_as_text(self):
        row = as_json(RESULTS["success/signal_facts"])["rows"][0]
        self.assertEqual(row["scale_factor"], "0.250")
        self.assertEqual(row["scale_offset"], "0.000")

    def test_the_trailing_zeros_are_the_stored_ones(self):
        # `Decimal("0.250")` and `Decimal("0.25")` compare equal, so a test
        # that only compared values would pass on a projection that
        # normalized the digits away. The column records a precision and
        # Section 6 says no part of the runtime may change it.
        self.assertEqual(str(from_json(as_json(RESULTS["success/signal_facts"])).rows[0]["scale_factor"]), "0.250")

    def test_it_reads_back_a_decimal(self):
        value = from_json(as_json(RESULTS["success/signal_facts"])).rows[0]["scale_factor"]
        self.assertIsInstance(value, decimal.Decimal)

    def test_a_value_no_float_can_hold_survives_exactly(self):
        # The rule's whole purpose. This value has more significant digits
        # than a binary double carries, so a projection that wrote it as a
        # JSON number would hand back a different number -- and `repr` of the
        # float it would become is asserted to differ, so the test fails on
        # the defect rather than on the comparison being loose.
        stored = "1.100000000000000088817841970012523"
        result = fact(
            "signal_facts",
            FACT_SIGNAL,
            {"TPL_SIGNAL_FACTS_V1": (signal_row(scale_factor=decimal.Decimal(stored)),)},
        )
        self.assertEqual(as_json(result)["rows"][0]["scale_factor"], stored)
        self.assertEqual(str(from_json(as_json(result)).rows[0]["scale_factor"]), stored)
        self.assertNotEqual(repr(float(stored)), stored)

    def test_an_integer_column_stays_a_json_number(self):
        row = as_json(RESULTS["success/message_facts"])["rows"][0]
        self.assertIsInstance(row["transmit_period_ms"], int)
        self.assertNotIsInstance(row["transmit_period_ms"], str)

    def test_the_two_named_columns_are_the_only_ones_converted(self):
        # The conversion is by column name because Section 4.4 names the
        # columns. A name outside the two is text and stays text, even when
        # its value looks like a number.
        self.assertEqual(NUMERIC_COLUMNS, ("scale_factor", "scale_offset"))
        self.assertEqual(from_json(as_json(RESULTS["success/signal_facts"])).rows[0]["unit_label"], "SAMPLE_UNIT_RPM")


class AFieldWithNoValueIsNullRatherThanAbsent(unittest.TestCase):
    """Section 4.4. An omitted key and a dropped key look the same to a
    reader, and Section 7 requires every key on every outcome including the
    negative ones."""

    def test_a_refused_request_carries_every_key_with_empty_values(self):
        document = as_json(RESULTS["invalid_request"])
        bundle = document["evidence_bundle"]
        self.assertIsNone(bundle["resolved_scope"])
        self.assertIsNone(bundle["selection"])
        self.assertEqual(bundle["bound_parameters"], {})
        self.assertEqual(document["rows"], [])
        self.assertEqual(document["source_trace"]["alias_provenance"], [])
        self.assertIsNone(document["source_trace"]["producing_layer"])

    def test_an_unsupported_outcome_names_its_producing_layer(self):
        # The one negative field that is not empty, and Section 7 requires it.
        self.assertEqual(as_json(RESULTS["unsupported"])["source_trace"]["producing_layer"], "runtime")

    def test_a_discovery_refusal_carries_every_key(self):
        bundle = as_json(RESULTS["discovery/invalid_request"])["evidence_bundle"]
        for name in ("registry_digest", "method_identifier", "candidate_set_id", "matched_text", "target_route"):
            with self.subTest(key=name):
                self.assertEqual(bundle[name], "")
        self.assertIsNone(bundle["match_tier"])

    def test_no_key_of_either_result_type_is_missing_from_its_document(self):
        # The assertion that keeps this class honest as the types change: a
        # field added to a result and not to the projection fails here rather
        # than being noticed by a reader of the wire.
        for name, result in RESULTS.items():
            with self.subTest(case=name):
                document = as_json(result)
                for field in ("status", "evidence_bundle", "source_trace", "limitations"):
                    self.assertIn(field, document)
                self.assertEqual(
                    set(document["evidence_bundle"]),
                    {f.name for f in _fields(result.evidence_bundle)},
                )
                self.assertEqual(
                    set(document["source_trace"]),
                    {f.name for f in _fields(result.source_trace)},
                )


class TheDumpIsTheOneTextTheDocumentHas(unittest.TestCase):
    """Section 6: two identical requests produce byte-identical bodies. That
    holds only if one document has one text."""

    def test_keys_are_sorted_byte_wise(self):
        text = dumps(as_json(RESULTS["success/message_facts"]))
        keys = [k for k in ("evidence_bundle", "limitations", "rows", "source_trace", "status")]
        self.assertEqual([text.index(f'"{k}"') for k in keys], sorted(text.index(f'"{k}"') for k in keys))

    def test_there_is_no_insignificant_whitespace(self):
        text = dumps(as_json(RESULTS["success/message_facts"]))
        self.assertNotIn(", ", text)
        self.assertNotIn(": ", text)
        self.assertNotIn("\n", text)

    def test_the_same_result_dumps_identically_twice(self):
        for name, result in RESULTS.items():
            with self.subTest(case=name):
                self.assertEqual(dumps(as_json(result)), dumps(as_json(result)))

    def test_text_is_utf8_rather_than_escaped_ascii(self):
        # `ensure_ascii` would hide the text inside `\uXXXX` escapes, which is
        # still valid JSON and is not the UTF-8 Section 4.4 fixes.
        #
        # Asserted over a non-ASCII value, because an assertion over an ASCII
        # one passes under either setting -- a mutation that turned
        # `ensure_ascii` on survived an earlier version of this test that
        # looked for a `SAMPLE_*` identifier. A discovery `term` is the one
        # value here that need not be ASCII: entity-discovery-v0.1 Section 4.3
        # bounds it in *bytes* of UTF-8 for exactly that reason, so this is a
        # value the wire really carries rather than one invented to fail a
        # mutation.
        term = "SAMPLE_TERM_\u00c9"
        text = dumps(as_json(discover(MESSAGE | {"term": term}, exact=(discovery_row(match_text=term),))))
        self.assertIn(term, text)
        self.assertNotIn("\\u00c9", text)


class TheSelectionRecordHoldsOnlyJsonTypes(unittest.TestCase):
    """The guarantee `_mapping_json` rests on, asserted against the record the
    runtime builds rather than trusted.

    `_value_object` converts a decimal back by column name, and no name in
    the Section 4.8 record is one of the two Section 4.4 names -- so a decimal
    or a tuple added to that record would be written correctly and read back
    as text or as a list, on the one path this module exists to protect, with
    no round-trip test failing. What stops that is Section 4.8 enumerating the
    record's contents as strings, integers and mappings of those. This is that
    enumeration checked against reality.
    """

    def test_every_value_in_the_record_is_a_json_type(self):
        record = RESULTS["selection/dispatched"].evidence_bundle.selection
        self.assertTrue(record)
        for name, value in record.items():
            with self.subTest(key=name):
                self.assertTrue(_is_json_native(value), f"{name} is a {type(value).__name__}")

    def test_every_value_in_an_alias_provenance_entry_is_a_json_type(self):
        entries = RESULTS["selection/dispatched"].source_trace.alias_provenance
        self.assertTrue(entries)
        for index, entry in enumerate(entries):
            for name, value in entry.items():
                with self.subTest(entry=index, key=name):
                    self.assertTrue(_is_json_native(value), f"{name} is a {type(value).__name__}")


class TheEscapeSetIsTheContractsRatherThanAnyLibrarysDefault(unittest.TestCase):
    """Section 4.4 cites entity-discovery-v0.1 Section 4.2's canonical rules,
    and those fix U+0000-U+001F as `\\u` plus four lower-case hexadecimal
    digits. `json.dumps` writes a newline as `\\n` instead -- valid JSON, and
    not the byte sequence two implementations are required to agree on, which
    is what Section 6 is about. `canonical.py`'s own docstring names this
    divergence as the reason it does not use `json.dumps`."""

    def _with_detail(self, detail):
        base = RESULTS["success/message_facts"]
        return dataclasses.replace(
            base,
            limitations=(Limitation(kind=LimitationKind.TRUNCATED_BY_LIMIT, detail=detail),),
        )

    def test_a_control_character_is_escaped_the_contracts_way(self):
        text = dumps(as_json(self._with_detail("a\nb\tc")))
        self.assertIn("a\\u000ab\\u0009c", text)
        self.assertNotIn("a\\nb", text)

    def test_the_escapes_are_lower_case_hexadecimal(self):
        self.assertIn("\\u001f", dumps(as_json(self._with_detail("a\u001fb"))))

    def test_a_quote_and_a_backslash_take_the_short_escape(self):
        text = dumps(as_json(self._with_detail('a"b\\c')))
        self.assertIn('a\\"b\\\\c', text)

    def test_a_detail_with_a_control_character_still_round_trips(self):
        result = self._with_detail("a\nb")
        self.assertEqual(from_json(json.loads(dumps(as_json(result)))), result)


class WhatTheModuleRefuses(unittest.TestCase):
    def test_a_value_no_registered_column_produces_raises(self):
        result = fact(
            "message_facts", FACT_MESSAGE, {"TPL_MESSAGE_FACTS_V1": (message_row(transmit_mode=object()),)}
        )
        with self.assertRaises(TypeError):
            as_json(result)

    def test_something_that_is_not_a_result_raises(self):
        with self.assertRaises(TypeError):
            as_json({"status": "success"})

    def test_a_document_that_is_neither_shape_raises(self):
        with self.assertRaises(ValueError):
            from_json({"status": "success"})


def _fields(value):
    return dataclasses.fields(value)


def _is_json_native(value) -> bool:
    if isinstance(value, (str, bool, int, type(None))):
        return True
    if isinstance(value, list):
        return all(_is_json_native(item) for item in value)
    if hasattr(value, "items"):
        return all(_is_json_native(item) for item in value.values())
    return False


if __name__ == "__main__":
    unittest.main(verbosity=2)
