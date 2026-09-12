"""entity-discovery-v0.1 Section 4.5: the normalization, with no database.

The Section 4.2 derived surface and the Section 4.4 lexical template both
bind what this function returns, so a change here changes every
`match_tokens` row and every `registry_digest`. Each rule of the definition
is asserted on its own, and the cases below include the ones Section 4.5
calls out: the case-only difference that must reach tier 3 and never tier 1,
and a non-ASCII byte mapped to a separator.
"""

import unittest

from evidence_first_rag.discovery import normalize


class TheDefinition(unittest.TestCase):
    def test_ascii_upper_case_is_lowered(self):
        self.assertEqual(normalize("SAMPLE_MSG_ENGINE_STATUS"), ["sample", "msg", "engine", "status"])

    def test_a_case_only_difference_normalizes_to_the_same_tokens(self):
        # Section 4.5: "a term differing from a stored key only by case" is
        # tier 3 -- equal after normalization, not before.
        self.assertEqual(
            normalize("sample_msg_engine_status"), normalize("SAMPLE_MSG_ENGINE_STATUS")
        )

    def test_every_non_alphanumeric_character_is_a_separator(self):
        self.assertEqual(normalize("a-b.c d\te/f"), ["a", "b", "c", "d", "e", "f"])

    def test_digits_survive(self):
        self.assertEqual(normalize("SIG_42_X9"), ["sig", "42", "x9"])

    def test_runs_of_separators_produce_no_empty_token(self):
        self.assertEqual(normalize("  a___b  "), ["a", "b"])

    def test_order_is_preserved(self):
        self.assertEqual(normalize("b a"), ["b", "a"])

    def test_a_text_with_no_token_normalizes_to_the_empty_list(self):
        # Section 4.2 rule 5 and Section 4.3 decide what emptiness means; the
        # function only reports it.
        for text in ("", "   ", "___", "-.-"):
            with self.subTest(text=repr(text)):
                self.assertEqual(normalize(text), [])


class ItIsDefinedOnBytes(unittest.TestCase):
    def test_a_non_ascii_letter_is_a_separator_not_a_letter(self):
        # Section 4.5: "no locale ... a non-ASCII byte ... this normalization
        # maps to a separator." str.lower() would have kept the letter.
        self.assertEqual(normalize("caféx"), ["caf", "x"])

    def test_a_non_ascii_upper_case_letter_is_not_case_folded(self):
        # Unicode folding would give a letter; the contract's rule gives a
        # separator. The two differ exactly here.
        self.assertEqual(normalize("Éa"), ["a"])

    def test_unicode_case_folding_is_not_applied(self):
        # The observable difference between "defined on bytes" and
        # str.lower() with an ASCII character class. Unicode folds the
        # Kelvin sign (U+212A) to the ASCII letter k, so that implementation
        # would produce a token from a term that contains no ASCII letter at
        # all; Section 4.5's rule maps its three bytes to separators.
        self.assertEqual(normalize("\u212a"), [])
        self.assertEqual(normalize("SIG_\u212a_1"), ["sig", "1"])

    def test_a_multi_byte_character_is_one_run_of_separators(self):
        # Three UTF-8 bytes, all separators, no token between them.
        self.assertEqual(normalize("aあb"), ["a", "b"])

    def test_the_result_is_ascii(self):
        for token in normalize("SAMPLE_é_MIX_あ_42"):
            with self.subTest(token=token):
                token.encode("ascii")

    def test_it_takes_a_str(self):
        with self.assertRaises(TypeError):
            normalize(b"bytes")


if __name__ == "__main__":
    unittest.main(verbosity=2)
