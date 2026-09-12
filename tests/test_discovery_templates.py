"""entity-discovery-v0.1 Section 4.4: the three registered discovery
templates, at the template level and with no database.

Registration already ran mvp-v0.1 Section 4.4's safeguards (SELECT-only,
no forbidden keyword, named parameters, NULLS LAST, the limit in the text).
What is asserted here is this contract's own table: the parameters, the
ordering, the limit of 11 because k is 10, the state template's two columns,
and -- Section 4.12 at the payload -- that no result column is an attribute
of the entity.
"""

import unittest

from evidence_first_rag.registry import (
    TPL_DISCOVERY_EXACT_V1,
    TPL_DISCOVERY_LEXICAL_V1,
    TPL_REGISTRY_STATE_V1,
    LimitMeaning,
    ParameterError,
)

SCOPE = ("project_code", "revision_label", "network_name", "snapshot_label")
FULL = {"project_code": "SAMPLE_PROJECT_ALPHA", "revision_label": "SAMPLE_REV_A", "network_name": "SAMPLE_NET_POWERTRAIN", "snapshot_label": "SAMPLE_SNAP_BASE"}

# mvp-v0.1 Section 4.1's attribute columns. Section 4.12: a discovery result
# carries none of them, "and the registered result column list is where that
# is enforced" (Section 4.4).
ATTRIBUTES = ("transmit_mode", "transmit_period_ms", "payload_byte_length", "frame_identifier",
              "unit_label", "scale_factor", "scale_offset", "bit_width", "bit_offset", "transform_kind")


class TheStateTemplate(unittest.TestCase):
    def test_it_takes_no_parameter_and_returns_exactly_section_4_1s_two_columns(self):
        self.assertEqual(TPL_REGISTRY_STATE_V1.allowed_parameters, ())
        self.assertEqual(TPL_REGISTRY_STATE_V1.result_columns, ("registry_digest", "built_at"))
        self.assertNotIn("*", TPL_REGISTRY_STATE_V1.sql.split("FROM")[0])

    def test_its_limit_is_one(self):
        self.assertEqual(TPL_REGISTRY_STATE_V1.row_limit, 1)


class TheDiscoveryTemplates(unittest.TestCase):
    TEMPLATES = (TPL_DISCOVERY_EXACT_V1, TPL_DISCOVERY_LEXICAL_V1)

    def test_the_parameters_are_section_4_4s(self):
        self.assertEqual(set(TPL_DISCOVERY_EXACT_V1.required_parameters), set(SCOPE) | {"entity_kind", "term"})
        self.assertEqual(set(TPL_DISCOVERY_LEXICAL_V1.required_parameters), set(SCOPE) | {"entity_kind", "normalized_term"})
        for template in self.TEMPLATES:
            self.assertEqual(template.optional_parameters, ("parent_message_key",))

    def test_the_row_limit_is_11_because_k_is_10_and_it_truncates(self):
        for template in self.TEMPLATES:
            with self.subTest(template=template.name):
                self.assertEqual(template.row_limit, 11)
                self.assertIs(template.limit_meaning, LimitMeaning.TRUNCATES)
                self.assertTrue(template.truncated(11))
                self.assertFalse(template.truncated(10))
                self.assertFalse(template.rows_are_overflow(11))

    def test_the_ordering_is_section_4_4s(self):
        for template in self.TEMPLATES:
            with self.subTest(template=template.name):
                self.assertEqual(template.ordering, ("match_tier", "message_key", "signal_key", "match_text"))
                self.assertIn("signal_key NULLS LAST", template.sql)

    def test_no_result_column_is_an_attribute(self):
        for template in self.TEMPLATES:
            with self.subTest(template=template.name):
                self.assertEqual(set(template.result_columns) & set(ATTRIBUTES), set())
                for attribute in ATTRIBUTES:
                    self.assertNotIn(attribute, template.sql)

    def test_every_candidate_column_section_4_6_needs_is_returned(self):
        for template in self.TEMPLATES:
            columns = set(template.result_columns)
            for needed in SCOPE + ("entity_kind", "message_key", "signal_key", "match_tier", "match_kind", "match_text",
                                   "entity_approval_reference", "alias_approval_reference", "alias_approved_at",
                                   "alias_snapshot_label", "superseded_by_snapshot_label"):
                with self.subTest(template=template.name, column=needed):
                    self.assertIn(needed, columns)

    def test_no_surrogate_key_is_returned(self):
        for template in self.TEMPLATES + (TPL_REGISTRY_STATE_V1,):
            for column in template.result_columns:
                self.assertFalse(column.endswith("_id"), column)

    def test_the_exact_template_matches_byte_for_byte(self):
        # Section 4.5 tiers 1 and 2: "equals T byte for byte". The SQL
        # compares match_text with the bound term and nothing normalizes it.
        self.assertIn("x.match_text = %(term)s", TPL_DISCOVERY_EXACT_V1.sql)
        self.assertNotIn("lower(", TPL_DISCOVERY_EXACT_V1.sql.lower().replace("lower(", "lower("))
        self.assertNotIn("LOWER", TPL_DISCOVERY_EXACT_V1.sql.upper().split("CASE")[0])

    def test_the_lexical_template_binds_one_array(self):
        # Section 4.4: "a variable number of tokens is one bound parameter and
        # not an assembled query."
        self.assertIn("@> %(normalized_term)s::text[]", TPL_DISCOVERY_LEXICAL_V1.sql)
        self.assertIn("= %(normalized_term)s::text[] THEN 3 ELSE 4", TPL_DISCOVERY_LEXICAL_V1.sql)

    def test_one_row_per_entity(self):
        # Section 4.6: one entity appears at most once, carrying its best
        # match. The NOT EXISTS clause is what makes the 11-row limit count
        # entities.
        for template in self.TEMPLATES:
            self.assertIn("NOT EXISTS", template.sql)
            self.assertIn("y.approved_entity_id = x.approved_entity_id", template.sql)

    def test_the_dedup_comparison_is_total_because_it_names_match_kind(self):
        # Section 4.6's two stated keys -- tier, then match_text -- tie when
        # one entity holds one match_text under two kinds, which the unique
        # constraint on (entity, match_kind, match_text) permits: an approved
        # alias equal to its own entity's lookup key. Both rows normalize
        # alike, so both take the same lexical tier, and a two-element
        # comparison holds neither below the other and keeps both -- one
        # entity listed twice, tied on all four ORDER BY keys. The third
        # element is Section 4.6's own last ordering key: match_kind ranked
        # lookup_key, approved_alias, spelling_variant.
        for template in self.TEMPLATES:
            with self.subTest(template=template.name):
                dedup = template.sql.split("NOT EXISTS", 1)[1].split("ORDER BY", 1)[0]
                for side in ("x", "y"):
                    self.assertIn(f"CASE {side}.match_kind", dedup)
                self.assertIn("WHEN 'lookup_key' THEN 1", dedup)
                self.assertIn("WHEN 'approved_alias' THEN 2", dedup)
                self.assertIn("ELSE 3 END", dedup)

    def test_a_parameter_outside_the_allowlist_is_refused(self):
        with self.assertRaises(ParameterError):
            TPL_DISCOVERY_EXACT_V1.bind(FULL | {"entity_kind": "message", "term": "x", "k": "3"})

    def test_a_missing_required_parameter_is_refused(self):
        with self.assertRaises(ParameterError):
            TPL_DISCOVERY_EXACT_V1.bind(FULL | {"entity_kind": "message"})
        with self.assertRaises(ParameterError):
            TPL_DISCOVERY_LEXICAL_V1.bind(FULL | {"entity_kind": "message", "term": "x"})

    def test_the_optional_parent_binds_as_null_when_omitted(self):
        bound = TPL_DISCOVERY_EXACT_V1.bind(FULL | {"entity_kind": "signal", "term": "x"})
        self.assertIsNone(bound["parent_message_key"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
