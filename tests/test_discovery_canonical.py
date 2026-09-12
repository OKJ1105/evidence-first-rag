"""entity-discovery-v0.1 Section 4.2: canonical JSON, with no database.

The contract states its rules inline "so that the digest does not depend on
any library's defaults", and warns that "a JSON writer that ASCII-escapes
non-ASCII characters, or that emits a space after a colon, produces a
different digest and is non-conforming." So these tests assert the rules one
at a time, and the two places where `json.dumps` -- the obvious
implementation -- would have produced different bytes are asserted as
differences rather than left to a reader's memory.
"""

import hashlib
import json
import unittest

from evidence_first_rag.discovery import CanonicalError, canonical_json, sha256_hex


class TheRules(unittest.TestCase):
    def test_keys_are_sorted_and_no_whitespace_appears(self):
        self.assertEqual(canonical_json({"b": 1, "a": 2}), b'{"a":2,"b":1}')

    def test_keys_sort_by_utf8_bytes(self):
        # "Z" (0x5a) < "a" (0x61) < "é" (0xc3 0xa9). A locale-aware sort
        # could put "a" before "Z"; byte order does not.
        self.assertEqual(
            canonical_json({"a": 0, "Z": 0, "é": 0}), '{"Z":0,"a":0,"é":0}'.encode("utf-8")
        )

    def test_non_ascii_is_written_as_itself(self):
        # The rule json.dumps breaks by default (ensure_ascii=True).
        self.assertEqual(canonical_json("café"), "\"café\"".encode("utf-8"))
        self.assertNotEqual(canonical_json("café"), json.dumps("café").encode("utf-8"))

    def test_the_escape_set_is_rfc_8259s_minimum(self):
        self.assertEqual(canonical_json('"'), b'"\\""')
        self.assertEqual(canonical_json("\\"), b'"\\\\"')
        self.assertEqual(canonical_json("/"), b'"/"')

    def test_control_characters_are_four_lower_case_hex_digits(self):
        # The rule json.dumps breaks even with ensure_ascii=False: it writes
        # a newline as the two characters \n.
        self.assertEqual(canonical_json("\n"), b'"\\u000a"')
        self.assertEqual(canonical_json("\x00\x1f"), b'"\\u0000\\u001f"')
        self.assertNotEqual(canonical_json("\n"), json.dumps("\n", ensure_ascii=False).encode())

    def test_delete_and_above_are_not_escaped(self):
        # U+007F is not in U+0000-U+001F, so it is written as itself.
        self.assertEqual(canonical_json("\x7f"), "\"\x7f\"".encode("utf-8"))

    def test_absent_is_null(self):
        self.assertEqual(canonical_json({"signal_key": None}), b'{"signal_key":null}')

    def test_an_integer_is_its_shortest_decimal_form(self):
        self.assertEqual(canonical_json([0, 7, 10]), b"[0,7,10]")

    def test_arrays_keep_their_order(self):
        self.assertEqual(canonical_json(["b", "a"]), b'["b","a"]')
        self.assertEqual(canonical_json(("b", "a")), b'["b","a"]')

    def test_nesting(self):
        self.assertEqual(
            canonical_json({"tokens": ["x", "y"], "inner": {"k": None}}),
            b'{"inner":{"k":null},"tokens":["x","y"]}',
        )

    def test_the_output_is_valid_json_that_round_trips(self):
        value = {"a": "q\"\\\né/", "b": [1, None, {"c": "d"}]}
        self.assertEqual(json.loads(canonical_json(value)), value)


class WhatIsRefused(unittest.TestCase):
    """Section 4.2: "No other number appears in any digest input." A value
    outside the vocabulary is refused rather than serialized somehow."""

    def test_a_float(self):
        with self.assertRaises(CanonicalError):
            canonical_json(1.5)

    def test_a_bool(self):
        # True is an int in Python; it must not become 1.
        with self.assertRaises(CanonicalError):
            canonical_json(True)

    def test_a_negative_integer(self):
        with self.assertRaises(CanonicalError):
            canonical_json(-1)

    def test_a_non_string_key(self):
        with self.assertRaises(CanonicalError):
            canonical_json({1: "a"})

    def test_an_arbitrary_object(self):
        with self.assertRaises(CanonicalError):
            canonical_json(object())


class TheDigest(unittest.TestCase):
    def test_it_is_lower_case_hex_sha256(self):
        self.assertEqual(sha256_hex(b"abc"), hashlib.sha256(b"abc").hexdigest())
        digest = sha256_hex(b"")
        self.assertEqual(len(digest), 64)
        self.assertEqual(digest, digest.lower())


if __name__ == "__main__":
    unittest.main(verbosity=2)
