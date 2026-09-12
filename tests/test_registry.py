"""Section 4.4: the registered templates and the registry safeguards -- mvp-v0.1's
four, and entity-discovery-v0.1's three registered under the same rules."""

import unittest

from evidence_first_rag.evidence import LimitationKind
from evidence_first_rag.registry import (
    FORBIDDEN_KEYWORDS,
    REGISTERED,
    LimitMeaning,
    ParameterError,
    TemplateError,
    UnregisteredTemplate,
    get,
    names,
)
from evidence_first_rag.registry.registry import (
    TPL_DISCOVERY_EXACT_V1,
    TPL_DISCOVERY_LEXICAL_V1,
    TPL_MESSAGE_FACTS_V1,
    TPL_REGISTRY_STATE_V1,
    TPL_SIGNAL_FACTS_V1,
    TPL_SIGNAL_MAPPING_V1,
    TPL_SNAPSHOT_CANDIDATES_V1,
)

# `Template` is deliberately not part of the package's public surface (see
# `tests/test_registry_surface.py`): its constructor accepts SQL text, and
# exporting it would be the arbitrary-SQL interface AGENTS.md forbids. These
# tests exercise the registration safeguards directly, so they reach into the
# internal module rather than the public `evidence_first_rag.registry`.
from evidence_first_rag.registry.template import _SEAL, Template

SCOPE = ("project_code", "revision_label", "network_name", "snapshot_label")
FULL_SCOPE = {
    "project_code": "SAMPLE_PROJECT_ALPHA",
    "revision_label": "SAMPLE_REV_A",
    "network_name": "SAMPLE_NET_POWERTRAIN",
    "snapshot_label": "SAMPLE_SNAP_BASE",
}


def valid_template(**overrides):
    """A template that satisfies every Section 4.4 rule, for tests that break
    exactly one of them."""
    values = {
        "seal": _SEAL,
        "name": "TPL_SAMPLE_V1",
        "version": "1",
        "sql": "SELECT a FROM mvp.t WHERE a = %(a)s ORDER BY a NULLS LAST LIMIT 5",
        "required_parameters": ("a",),
        "result_columns": ("a",),
        "ordering": ("a",),
        "row_limit": 5,
        "limit_meaning": LimitMeaning.TRUNCATES,
        "declared_limitations": (LimitationKind.TRUNCATED_BY_LIMIT,),
    }
    values.update(overrides)
    return Template(**values)


class TheRegistryHoldsExactlyTheSevenOfTheTwoContracts(unittest.TestCase):
    def test_the_names_are_the_two_section_4_4s(self):
        self.assertEqual(
            names(),
            (
                "TPL_SNAPSHOT_CANDIDATES_V1",
                "TPL_MESSAGE_FACTS_V1",
                "TPL_SIGNAL_FACTS_V1",
                "TPL_SIGNAL_MAPPING_V1",
                "TPL_REGISTRY_STATE_V1",
                "TPL_DISCOVERY_EXACT_V1",
                "TPL_DISCOVERY_LEXICAL_V1",
            ),
        )

    def test_an_unregistered_name_is_refused(self):
        # Section 4.4: "Execution is refused for any template name not in the
        # registry."
        for candidate in ("TPL_ANYTHING_V1", "", "SELECT 1", None, 3, "tpl_message_facts_v1"):
            with self.subTest(candidate=candidate):
                with self.assertRaises(UnregisteredTemplate):
                    get(candidate)

    def test_each_registered_name_resolves_to_itself(self):
        for template in REGISTERED:
            with self.subTest(template=template.name):
                self.assertIs(get(template.name), template)


class TheAllowedParameters(unittest.TestCase):
    """Section 4.4's allowlist, per template."""

    EXPECTED = {
        "TPL_SNAPSHOT_CANDIDATES_V1": (set(), set(SCOPE)),
        "TPL_MESSAGE_FACTS_V1": (set(SCOPE) | {"message_key"}, set()),
        "TPL_SIGNAL_FACTS_V1": (set(SCOPE) | {"message_key", "signal_key"}, set()),
        "TPL_SIGNAL_MAPPING_V1": (
            set(SCOPE) | {"message_key", "signal_key"},
            {"mapping_key"},
        ),
        # entity-discovery-v0.1 Section 4.4.
        "TPL_REGISTRY_STATE_V1": (set(), set()),
        "TPL_DISCOVERY_EXACT_V1": (set(SCOPE) | {"entity_kind", "term"}, {"parent_message_key"}),
        "TPL_DISCOVERY_LEXICAL_V1": (
            set(SCOPE) | {"entity_kind", "normalized_term"},
            {"parent_message_key"},
        ),
    }

    def test_each_template_allows_what_section_4_4_lists(self):
        for template in REGISTERED:
            required, optional = self.EXPECTED[template.name]
            with self.subTest(template=template.name):
                self.assertEqual(set(template.required_parameters), required)
                self.assertEqual(set(template.optional_parameters), optional)

    def test_a_parameter_outside_the_allowlist_is_refused(self):
        with self.assertRaises(ParameterError) as raised:
            TPL_MESSAGE_FACTS_V1.bind(
                FULL_SCOPE | {"message_key": "SAMPLE_MSG_A", "table_name": "mvp.t"}
            )
        self.assertIn("not in the allowlist", str(raised.exception))

    def test_a_missing_required_parameter_is_refused(self):
        with self.assertRaises(ParameterError) as raised:
            TPL_MESSAGE_FACTS_V1.bind(FULL_SCOPE)
        self.assertIn("message_key", str(raised.exception))

    def test_a_null_required_parameter_is_refused(self):
        # Section 4.2 forbids the runtime from supplying a missing scope
        # dimension; a null in a required slot is that, arriving as a value.
        with self.assertRaises(ParameterError):
            TPL_MESSAGE_FACTS_V1.bind(
                FULL_SCOPE | {"message_key": "SAMPLE_MSG_A", "project_code": None}
            )

    def test_an_omitted_optional_parameter_binds_as_null(self):
        bound = TPL_SIGNAL_MAPPING_V1.bind(
            FULL_SCOPE | {"message_key": "SAMPLE_MSG_A", "signal_key": "SAMPLE_SIG_A"}
        )
        self.assertIsNone(bound["mapping_key"])
        self.assertEqual(set(bound), set(TPL_SIGNAL_MAPPING_V1.allowed_parameters))

    def test_the_bound_mapping_cannot_be_edited_afterwards(self):
        bound = TPL_MESSAGE_FACTS_V1.bind(FULL_SCOPE | {"message_key": "SAMPLE_MSG_A"})
        with self.assertRaises(TypeError):
            bound["message_key"] = "SAMPLE_MSG_B"

    def test_candidates_accepts_every_subset_of_scope(self):
        # Section 4.4 marks all four optional so that an under-specified scope
        # can be answered with candidates rather than a guess.
        for omitted in SCOPE:
            with self.subTest(omitted=omitted):
                arguments = {k: v for k, v in FULL_SCOPE.items() if k != omitted}
                bound = TPL_SNAPSHOT_CANDIDATES_V1.bind(arguments)
                self.assertIsNone(bound[omitted])


class TheRegistrationSafeguards(unittest.TestCase):
    """Section 4.4, enforced at construction so an unsafe template has no
    representation to reach execution with."""

    def test_the_sample_template_is_valid(self):
        # So that a test below passing for the wrong reason is visible.
        self.assertEqual(valid_template().name, "TPL_SAMPLE_V1")

    def test_sql_that_does_not_begin_with_select_is_refused(self):
        with self.assertRaises(TemplateError) as raised:
            valid_template(sql="WITH x AS (SELECT 1) SELECT a FROM x ORDER BY a NULLS LAST LIMIT 5")
        self.assertIn("must begin with SELECT", str(raised.exception))

    def test_every_prohibited_keyword_is_refused_at_registration(self):
        # Section 4.4 lists thirteen. Each one is tried, so a keyword dropped
        # from the scan fails here.
        for keyword in FORBIDDEN_KEYWORDS:
            with self.subTest(keyword=keyword):
                with self.assertRaises(TemplateError) as raised:
                    valid_template(
                        sql=f"SELECT a FROM mvp.t WHERE a = %(a)s"
                        f" AND b = '{keyword} something'"
                        f" ORDER BY a NULLS LAST LIMIT 5"
                    )
                self.assertIn(keyword, str(raised.exception))

    def test_the_thirteen_keywords_are_section_4_4s(self):
        self.assertEqual(
            FORBIDDEN_KEYWORDS,
            ("INSERT", "UPDATE", "DELETE", "MERGE", "CREATE", "DROP", "ALTER",
             "TRUNCATE", "GRANT", "REVOKE", "COPY", "CALL", "DO"),
        )

    def test_a_keyword_inside_a_longer_word_is_not_a_false_positive(self):
        # `updated_at` is not an UPDATE. A substring scan would refuse this,
        # and the usual repair for that is to weaken the scan.
        template = valid_template(
            sql="SELECT updated_at FROM mvp.t WHERE a = %(a)s"
            " ORDER BY updated_at NULLS LAST LIMIT 5",
            result_columns=("updated_at",),
            ordering=("updated_at",),
        )
        self.assertIn("updated_at", template.sql)

    def test_a_positional_placeholder_is_refused(self):
        # Section 4.4 binds every variable as a named parameter.
        with self.assertRaises(TemplateError) as raised:
            valid_template(sql="SELECT a FROM mvp.t WHERE a = %s ORDER BY a NULLS LAST LIMIT 5")
        self.assertIn("positional placeholder", str(raised.exception))

    def test_sql_binding_an_undeclared_parameter_is_refused(self):
        with self.assertRaises(TemplateError) as raised:
            valid_template(
                sql="SELECT a FROM mvp.t WHERE a = %(a)s AND b = %(b)s"
                " ORDER BY a NULLS LAST LIMIT 5"
            )
        self.assertIn("'b'", str(raised.exception))

    def test_an_allowed_parameter_the_sql_never_binds_is_refused(self):
        with self.assertRaises(TemplateError) as raised:
            valid_template(required_parameters=("a", "unused"))
        self.assertIn("unused", str(raised.exception))

    def test_a_template_without_an_ordering_clause_is_refused(self):
        with self.assertRaises(TemplateError):
            valid_template(sql="SELECT a FROM mvp.t WHERE a = %(a)s LIMIT 5")

    def test_an_ordering_term_without_explicit_nulls_last_is_refused(self):
        # Section 6: NULLS LAST is "written explicitly in every registered
        # template's ordering clause rather than left to the database default."
        with self.assertRaises(TemplateError) as raised:
            valid_template(
                sql="SELECT a, b FROM mvp.t WHERE a = %(a)s"
                " ORDER BY a NULLS LAST, b LIMIT 5",
                result_columns=("a", "b"),
                ordering=("a", "b"),
            )
        self.assertIn("NULLS LAST", str(raised.exception))

    def test_sql_that_does_not_carry_its_declared_limit_is_refused(self):
        with self.assertRaises(TemplateError) as raised:
            valid_template(row_limit=7)
        self.assertIn("LIMIT 7", str(raised.exception))

    def test_a_declared_limit_that_is_a_prefix_of_the_sql_limit_is_refused(self):
        # Review finding B2. The check used to be substring containment, and
        # "LIMIT 2" is a substring of "LIMIT 200", so a template could declare
        # an overflow detector while the database returned up to 200 rows and
        # `truncated()` reported a false limitation. The test above missed it
        # because 7 against 5 shares no prefix; this is the pair that does.
        with self.assertRaises(TemplateError):
            valid_template(
                row_limit=2,
                sql="SELECT a FROM mvp.t WHERE a = %(a)s ORDER BY a NULLS LAST LIMIT 200",
                limit_meaning=LimitMeaning.DETECTS_OVERFLOW,
                declared_limitations=(),
            )

    def test_a_declared_ordering_that_disagrees_with_the_sql_is_refused(self):
        # Review finding N2, the same class as the row limit: metadata that can
        # silently disagree with the SQL it describes. `ordering` is what the
        # runtime and the conformance runner reason about, so a template whose
        # declaration does not match its ORDER BY has them reasoning about a
        # query that does not exist.
        with self.assertRaises(TemplateError) as raised:
            valid_template(
                sql="SELECT a, b FROM mvp.t WHERE a = %(a)s ORDER BY b NULLS LAST LIMIT 5",
                result_columns=("a", "b"),
                ordering=("a",),
            )
        self.assertIn("ordering term 0", str(raised.exception))

    def test_a_one_letter_column_is_compared_exactly_not_by_containment(self):
        # The case that caught a first attempt at the check above: "NULLS
        # LAST" contains an A, so a substring test passes for a column named
        # `a` no matter what the SQL actually orders by. Same defect the row
        # limit had before B2; asserted so it cannot come back.
        with self.assertRaises(TemplateError):
            valid_template(
                sql="SELECT a, z FROM mvp.t WHERE a = %(a)s ORDER BY z NULLS LAST LIMIT 5",
                result_columns=("a", "z"),
                ordering=("a",),
            )

    def test_a_declared_ordering_with_the_wrong_number_of_terms_is_refused(self):
        with self.assertRaises(TemplateError) as raised:
            valid_template(
                sql="SELECT a, b FROM mvp.t WHERE a = %(a)s"
                " ORDER BY a NULLS LAST, b NULLS LAST LIMIT 5",
                result_columns=("a", "b"),
                ordering=("a",),
            )
        self.assertIn("ordering term(s)", str(raised.exception))

    def test_a_result_column_the_select_does_not_produce_is_refused(self):
        with self.assertRaises(TemplateError) as raised:
            valid_template(result_columns=("secret",))
        self.assertIn("secret", str(raised.exception))

    def test_a_parameter_that_is_both_required_and_optional_is_refused(self):
        with self.assertRaises(TemplateError):
            valid_template(required_parameters=("a",), optional_parameters=("a",))


class TheLimitsAndTheirMeanings(unittest.TestCase):
    """Section 4.4's limits table, including the column that says what hitting
    the limit means. The two meanings are not interchangeable."""

    EXPECTED = {
        "TPL_SNAPSHOT_CANDIDATES_V1": (100, LimitMeaning.TRUNCATES),
        "TPL_MESSAGE_FACTS_V1": (2, LimitMeaning.DETECTS_OVERFLOW),
        "TPL_SIGNAL_FACTS_V1": (2, LimitMeaning.DETECTS_OVERFLOW),
        "TPL_SIGNAL_MAPPING_V1": (200, LimitMeaning.TRUNCATES),
        # entity-discovery-v0.1 Section 4.4: "The row limit is 11 because k
        # is 10", the truncation pattern; the state row is at most one.
        "TPL_REGISTRY_STATE_V1": (1, LimitMeaning.DETECTS_OVERFLOW),
        "TPL_DISCOVERY_EXACT_V1": (11, LimitMeaning.TRUNCATES),
        "TPL_DISCOVERY_LEXICAL_V1": (11, LimitMeaning.TRUNCATES),
    }

    def test_each_template_carries_the_limit_section_4_4_fixes(self):
        for template in REGISTERED:
            limit, meaning = self.EXPECTED[template.name]
            with self.subTest(template=template.name):
                self.assertEqual(template.row_limit, limit)
                self.assertEqual(template.limit_meaning, meaning)

    def test_the_limit_is_in_the_registered_sql_not_only_the_metadata(self):
        # A limit the caller could raise is not a limit. It lives in the text
        # Section 4.4 puts beyond the caller's reach.
        for template in REGISTERED:
            with self.subTest(template=template.name):
                self.assertIn(f"LIMIT {template.row_limit}", template.sql)

    def test_two_rows_from_a_facts_template_is_an_overflow(self):
        # Section 4.4: "a second row means the loaded database violates its own
        # invariants, and the runtime reports a failure (conformance class
        # `data`) instead of silently returning one of several."
        for template in (TPL_MESSAGE_FACTS_V1, TPL_SIGNAL_FACTS_V1):
            with self.subTest(template=template.name):
                self.assertFalse(template.rows_are_overflow(0))
                self.assertFalse(template.rows_are_overflow(1))
                self.assertTrue(template.rows_are_overflow(2))
                # An overflow is a fault, not a truncated result.
                self.assertFalse(template.truncated(2))

    def test_a_negative_row_count_is_refused_by_both_checks(self):
        # N1: `rows_are_overflow` already refused a negative count;
        # `truncated` returned False for the same input instead of raising.
        # A corrupted row count should fail the same way through both paths.
        for template in REGISTERED:
            with self.subTest(template=template.name):
                with self.assertRaises(ValueError):
                    template.rows_are_overflow(-1)
                with self.assertRaises(ValueError):
                    template.truncated(-1)

    def test_a_facts_template_declares_no_truncation_limitation(self):
        for template in (TPL_MESSAGE_FACTS_V1, TPL_SIGNAL_FACTS_V1):
            with self.subTest(template=template.name):
                self.assertEqual(template.declared_limitations, ())

    def test_a_truncating_template_declares_the_truncation(self):
        for template in (TPL_SNAPSHOT_CANDIDATES_V1, TPL_SIGNAL_MAPPING_V1):
            with self.subTest(template=template.name):
                self.assertIn(
                    LimitationKind.TRUNCATED_BY_LIMIT, template.declared_limitations
                )
                self.assertTrue(template.truncated(template.row_limit))
                self.assertFalse(template.truncated(template.row_limit - 1))
                self.assertFalse(template.rows_are_overflow(template.row_limit))

    def test_a_truncating_template_that_declares_nothing_is_refused(self):
        with self.assertRaises(TemplateError):
            valid_template(declared_limitations=())

    def test_an_overflow_detector_that_claims_truncation_is_refused(self):
        with self.assertRaises(TemplateError):
            valid_template(limit_meaning=LimitMeaning.DETECTS_OVERFLOW)


class TheOrderingIsTotal(unittest.TestCase):
    """Section 6: "Every ordering is total. Where the declared columns could
    tie, the template appends its surrogate key as the final tiebreaker so that
    row order is reproducible." """

    # The templates whose declared columns can tie, and the surrogate each
    # appends. Candidates is absent on purpose: Section 4.1's unique
    # constraint over the four scope dimensions makes its ordering total
    # already, so a tiebreaker would be noise.
    TIEBREAKERS = {
        "TPL_MESSAGE_FACTS_V1": "message_occurrence_id",
        "TPL_SIGNAL_FACTS_V1": "signal_occurrence_id",
        "TPL_SIGNAL_MAPPING_V1": "signal_mapping_id",
    }

    def test_every_template_declares_an_ordering(self):
        for template in REGISTERED:
            with self.subTest(template=template.name):
                self.assertTrue(template.ordering)

    def test_the_declared_ordering_appears_in_the_sql(self):
        for template in REGISTERED:
            with self.subTest(template=template.name):
                clause = template.sql.split("ORDER BY", 1)[1]
                for column in template.ordering:
                    self.assertIn(column, clause)

    def test_the_tiebreaker_is_the_last_ordering_term(self):
        for name, surrogate in self.TIEBREAKERS.items():
            with self.subTest(template=name):
                self.assertEqual(get(name).ordering[-1], surrogate)

    def test_the_candidates_ordering_needs_no_tiebreaker(self):
        self.assertEqual(TPL_SNAPSHOT_CANDIDATES_V1.ordering, SCOPE)

    def test_no_surrogate_key_appears_in_any_result_column_list(self):
        # Section 4.2: "No surrogate key appears in any public payload."
        # Ordering by one is fine; returning one is not.
        surrogates = {
            "snapshot_id",
            "message_occurrence_id",
            "signal_occurrence_id",
            "signal_mapping_id",
            "asserting_snapshot_id",
            "source_signal_occurrence_id",
            "target_signal_occurrence_id",
            "approved_entity_id",
            "approved_alias_id",
            "entity_match_term_id",
        }
        for template in REGISTERED:
            with self.subTest(template=template.name):
                self.assertEqual(set(template.result_columns) & surrogates, set())


class TheCandidatesTemplateReturnsScopeOnly(unittest.TestCase):
    def test_it_returns_the_four_scope_columns_and_nothing_else(self):
        # Section 4.4: "It returns scope columns only; it returns no message,
        # signal, or mapping facts."
        self.assertEqual(TPL_SNAPSHOT_CANDIDATES_V1.result_columns, SCOPE)

    def test_its_sql_mentions_no_fact_table(self):
        text = TPL_SNAPSHOT_CANDIDATES_V1.sql
        for table in ("message_occurrence", "signal_occurrence", "signal_mapping"):
            with self.subTest(table=table):
                self.assertNotIn(table, text)


class TheMappingTemplateIdentifiesEveryScopeSeparately(unittest.TestCase):
    """Section 4.5 and Section 7: one entry per asserting relation, carrying
    the asserting snapshot and both endpoint snapshots separately identified."""

    def test_it_returns_all_three_scopes(self):
        columns = TPL_SIGNAL_MAPPING_V1.result_columns
        for prefix in ("asserting_", "source_", "target_"):
            with self.subTest(prefix=prefix):
                for dimension in SCOPE:
                    self.assertIn(prefix + dimension, columns)

    def test_both_endpoints_carry_a_complete_canonical_signal_reference(self):
        columns = TPL_SIGNAL_MAPPING_V1.result_columns
        for prefix in ("source_", "target_"):
            with self.subTest(prefix=prefix):
                self.assertIn(prefix + "message_key", columns)
                self.assertIn(prefix + "signal_key", columns)


if __name__ == "__main__":
    unittest.main(verbosity=2)
