"""The registered templates, and the only way to reach one.

mvp-v0.1 Section 4.4 registers four templates and entity-discovery-v0.1
Section 4.4 registers three more under the same safeguards; both say
"Execution is refused for any template name not in the registry." `get()` is
that refusal. There is
no function here that takes SQL text, a table name, or a column name from a
caller: the SQL is written out below, committed, and inspectable, which is
what Charter Section 3.1 requires of the query-template registry.

The `mvp` schema qualifier is the one thing this module shares with the
provisioning slice. Column names come from contract Section 4.1, but the
schema name is a provisioning choice, so the two have to agree; SCHEMA is
named once here so that a disagreement is one edit rather than a search.
"""

from ..evidence import LimitationKind
from .template import _SEAL, LimitMeaning, Template, UnregisteredTemplate

SCHEMA = "mvp"

# Section 4.2's four scope dimensions, as they appear in every template.
_SCOPE = ("project_code", "revision_label", "network_name", "snapshot_label")


def _superseded_by(prefix: str = "") -> tuple[str, ...]:
    """The column names carrying the superseding snapshot's scope.

    Built from `_SCOPE` rather than written out, so that a fifth scope
    dimension could not be added to Section 4.2 and silently leave the
    supersession columns describing four of five.
    """
    return tuple(f"{prefix}superseded_by_{dimension}" for dimension in _SCOPE)


_SUPERSEDED_BY = _superseded_by()


TPL_SNAPSHOT_CANDIDATES_V1 = Template(
    seal=_SEAL,
    name="TPL_SNAPSHOT_CANDIDATES_V1",
    version="1",
    # Section 4.4: "exists so that an `ambiguous` outcome can list candidate
    # scopes without an unregistered query. It returns scope columns only; it
    # returns no message, signal, or mapping facts."
    #
    # Every parameter is optional, and an omitted one matches every value.
    # The null test is in the registered text rather than assembled per call,
    # because Section 4.4 puts the SQL beyond the caller's reach: an absent
    # argument changes what the query matches, never what the query is.
    sql=f"""
SELECT s.project_code,
       s.revision_label,
       s.network_name,
       s.snapshot_label
  FROM {SCHEMA}.source_snapshot AS s
 WHERE (%(project_code)s::text   IS NULL OR s.project_code   = %(project_code)s)
   AND (%(revision_label)s::text IS NULL OR s.revision_label = %(revision_label)s)
   AND (%(network_name)s::text   IS NULL OR s.network_name   = %(network_name)s)
   AND (%(snapshot_label)s::text IS NULL OR s.snapshot_label = %(snapshot_label)s)
 ORDER BY s.project_code NULLS LAST,
          s.revision_label NULLS LAST,
          s.network_name NULLS LAST,
          s.snapshot_label NULLS LAST
 LIMIT 100
""".strip(),
    optional_parameters=_SCOPE,
    result_columns=_SCOPE,
    # Section 4.1 puts a unique constraint on the four scope dimensions, so
    # ordering by all four is already total and needs no surrogate tiebreaker.
    ordering=_SCOPE,
    row_limit=100,
    limit_meaning=LimitMeaning.TRUNCATES,
    declared_limitations=(LimitationKind.TRUNCATED_BY_LIMIT,),
)


# Section 7 requires a `limitations` entry "when any participating snapshot has
# a non-null `superseded_by`", and Section 4.2 requires `superseded_by` itself to
# be exposed there. Neither is reachable unless a registered template returns it:
# the runtime executes nothing outside this registry (Section 4.4), and
# `TPL_SNAPSHOT_CANDIDATES_V1` may not carry it because Section 4.4 fixes that
# template as returning "scope columns only".
#
# So the three fact and mapping templates dereference `superseded_by` into the
# superseding snapshot's four scope dimensions, as `*_superseded_by_*` columns
# that are null when the participating snapshot is current. Section 4.4 fixes
# each template's allowed parameters, ordering, and row limit; it does not fix
# their result column lists, so this is a registration choice rather than a
# contract change. The surrogate `superseded_by` value itself is never returned:
# Section 4.2 keeps surrogate keys out of every public payload.
#
# That change is why these three carry `version="2"` while the candidate
# template stays at "1". The rule: a registered template's SQL text never
# changes under a version it has already carried. Section 7 puts the version
# in every evidence bundle so that a reader can find the exact SQL that
# produced a result, and the name alone (`..._V1`) identifies the template,
# not its text. The name is the contract's identifier and does not move; the
# version is the revision of the text and does.
TPL_MESSAGE_FACTS_V1 = Template(
    seal=_SEAL,
    name="TPL_MESSAGE_FACTS_V1",
    version="2",
    sql=f"""
SELECT s.project_code,
       s.revision_label,
       s.network_name,
       s.snapshot_label,
       m.message_key,
       m.transmit_mode,
       m.transmit_period_ms,
       m.payload_byte_length,
       m.frame_identifier,
       u.project_code   AS superseded_by_project_code,
       u.revision_label AS superseded_by_revision_label,
       u.network_name   AS superseded_by_network_name,
       u.snapshot_label AS superseded_by_snapshot_label
  FROM {SCHEMA}.message_occurrence AS m
  JOIN {SCHEMA}.source_snapshot AS s ON s.snapshot_id = m.snapshot_id
  LEFT JOIN {SCHEMA}.source_snapshot AS u ON u.snapshot_id = s.superseded_by
 WHERE s.project_code   = %(project_code)s
   AND s.revision_label = %(revision_label)s
   AND s.network_name   = %(network_name)s
   AND s.snapshot_label = %(snapshot_label)s
   AND m.message_key    = %(message_key)s
 ORDER BY m.message_key NULLS LAST,
          m.message_occurrence_id NULLS LAST
 LIMIT 2
""".strip(),
    required_parameters=_SCOPE + ("message_key",),
    result_columns=_SCOPE
    + (
        "message_key",
        "transmit_mode",
        "transmit_period_ms",
        "payload_byte_length",
        "frame_identifier",
    )
    + _SUPERSEDED_BY,
    # Section 4.4 declares the ordering as `message_key`. Section 6 requires
    # every ordering to be total, and the surrogate key is the tiebreaker it
    # names for the case where the declared columns tie -- which here means
    # the limit-2 overflow below, since a resolved reference returns one row.
    ordering=("message_key", "message_occurrence_id"),
    # Section 4.4: "The limit is deliberately 2, not 1: a second row means the
    # loaded database violates its own invariants, and the runtime reports a
    # failure (conformance class `data`) instead of silently returning one of
    # several." A detector, not a cap -- so no truncation limitation is
    # declared, because reaching this limit is a fault rather than a result.
    row_limit=2,
    limit_meaning=LimitMeaning.DETECTS_OVERFLOW,
)


TPL_SIGNAL_FACTS_V1 = Template(
    seal=_SEAL,
    name="TPL_SIGNAL_FACTS_V1",
    version="2",
    sql=f"""
SELECT s.project_code,
       s.revision_label,
       s.network_name,
       s.snapshot_label,
       m.message_key,
       g.signal_key,
       g.unit_label,
       g.scale_factor,
       g.scale_offset,
       g.bit_width,
       g.bit_offset,
       u.project_code   AS superseded_by_project_code,
       u.revision_label AS superseded_by_revision_label,
       u.network_name   AS superseded_by_network_name,
       u.snapshot_label AS superseded_by_snapshot_label
  FROM {SCHEMA}.signal_occurrence AS g
  JOIN {SCHEMA}.message_occurrence AS m ON m.message_occurrence_id = g.message_occurrence_id
  JOIN {SCHEMA}.source_snapshot AS s ON s.snapshot_id = m.snapshot_id
  LEFT JOIN {SCHEMA}.source_snapshot AS u ON u.snapshot_id = s.superseded_by
 WHERE s.project_code   = %(project_code)s
   AND s.revision_label = %(revision_label)s
   AND s.network_name   = %(network_name)s
   AND s.snapshot_label = %(snapshot_label)s
   AND m.message_key    = %(message_key)s
   AND g.signal_key     = %(signal_key)s
 ORDER BY m.message_key NULLS LAST,
          g.signal_key NULLS LAST,
          g.signal_occurrence_id NULLS LAST
 LIMIT 2
""".strip(),
    required_parameters=_SCOPE + ("message_key", "signal_key"),
    result_columns=_SCOPE
    + (
        "message_key",
        "signal_key",
        "unit_label",
        "scale_factor",
        "scale_offset",
        "bit_width",
        "bit_offset",
    )
    + _SUPERSEDED_BY,
    ordering=("message_key", "signal_key", "signal_occurrence_id"),
    row_limit=2,
    limit_meaning=LimitMeaning.DETECTS_OVERFLOW,
)


TPL_SIGNAL_MAPPING_V1 = Template(
    seal=_SEAL,
    name="TPL_SIGNAL_MAPPING_V1",
    version="2",
    # Section 4.5: "the result exposes one entry per asserting relation",
    # because Charter Section 3.6 requires the asserting artifact's scope to
    # travel with each relation. That is why the asserting snapshot and both
    # endpoint snapshots appear as separate column groups rather than being
    # merged: Section 7 requires them "separately identified".
    sql=f"""
SELECT a.project_code    AS asserting_project_code,
       a.revision_label  AS asserting_revision_label,
       a.network_name    AS asserting_network_name,
       a.snapshot_label  AS asserting_snapshot_label,
       ss.project_code   AS source_project_code,
       ss.revision_label AS source_revision_label,
       ss.network_name   AS source_network_name,
       ss.snapshot_label AS source_snapshot_label,
       sm.message_key    AS source_message_key,
       sg.signal_key     AS source_signal_key,
       ts.project_code   AS target_project_code,
       ts.revision_label AS target_revision_label,
       ts.network_name   AS target_network_name,
       ts.snapshot_label AS target_snapshot_label,
       tm.message_key    AS target_message_key,
       tg.signal_key     AS target_signal_key,
       x.mapping_key,
       x.transform_kind,
       au.project_code   AS asserting_superseded_by_project_code,
       au.revision_label AS asserting_superseded_by_revision_label,
       au.network_name   AS asserting_superseded_by_network_name,
       au.snapshot_label AS asserting_superseded_by_snapshot_label,
       su.project_code   AS source_superseded_by_project_code,
       su.revision_label AS source_superseded_by_revision_label,
       su.network_name   AS source_superseded_by_network_name,
       su.snapshot_label AS source_superseded_by_snapshot_label,
       tu.project_code   AS target_superseded_by_project_code,
       tu.revision_label AS target_superseded_by_revision_label,
       tu.network_name   AS target_superseded_by_network_name,
       tu.snapshot_label AS target_superseded_by_snapshot_label
  FROM {SCHEMA}.signal_mapping AS x
  JOIN {SCHEMA}.source_snapshot AS a ON a.snapshot_id = x.asserting_snapshot_id
  JOIN {SCHEMA}.signal_occurrence AS sg ON sg.signal_occurrence_id = x.source_signal_occurrence_id
  JOIN {SCHEMA}.message_occurrence AS sm ON sm.message_occurrence_id = sg.message_occurrence_id
  JOIN {SCHEMA}.source_snapshot AS ss ON ss.snapshot_id = sm.snapshot_id
  JOIN {SCHEMA}.signal_occurrence AS tg ON tg.signal_occurrence_id = x.target_signal_occurrence_id
  JOIN {SCHEMA}.message_occurrence AS tm ON tm.message_occurrence_id = tg.message_occurrence_id
  JOIN {SCHEMA}.source_snapshot AS ts ON ts.snapshot_id = tm.snapshot_id
  LEFT JOIN {SCHEMA}.source_snapshot AS au ON au.snapshot_id = a.superseded_by
  LEFT JOIN {SCHEMA}.source_snapshot AS su ON su.snapshot_id = ss.superseded_by
  LEFT JOIN {SCHEMA}.source_snapshot AS tu ON tu.snapshot_id = ts.superseded_by
 WHERE ss.project_code   = %(project_code)s
   AND ss.revision_label = %(revision_label)s
   AND ss.network_name   = %(network_name)s
   AND ss.snapshot_label = %(snapshot_label)s
   AND sm.message_key    = %(message_key)s
   AND sg.signal_key     = %(signal_key)s
   AND (%(mapping_key)s::text IS NULL OR x.mapping_key = %(mapping_key)s)
 ORDER BY x.mapping_key NULLS LAST,
          x.signal_mapping_id NULLS LAST
 LIMIT 200
""".strip(),
    required_parameters=_SCOPE + ("message_key", "signal_key"),
    optional_parameters=("mapping_key",),
    result_columns=(
        "asserting_project_code",
        "asserting_revision_label",
        "asserting_network_name",
        "asserting_snapshot_label",
        "source_project_code",
        "source_revision_label",
        "source_network_name",
        "source_snapshot_label",
        "source_message_key",
        "source_signal_key",
        "target_project_code",
        "target_revision_label",
        "target_network_name",
        "target_snapshot_label",
        "target_message_key",
        "target_signal_key",
        "mapping_key",
        "transform_kind",
    )
    + _superseded_by("asserting_")
    + _superseded_by("source_")
    + _superseded_by("target_"),
    # Section 4.4 declares the ordering as `mapping_key`, `signal_mapping_id`.
    # The surrogate is named by the contract itself here: two mappings may
    # share a key within one asserting snapshot, so the declared column ties.
    ordering=("mapping_key", "signal_mapping_id"),
    row_limit=200,
    limit_meaning=LimitMeaning.TRUNCATES,
    declared_limitations=(LimitationKind.TRUNCATED_BY_LIMIT,),
)


# --- entity-discovery-v0.1 Section 4.4 -------------------------------------
#
# The three discovery templates, "registered under `mvp-v0.1` Section 4.4's
# safeguards, which apply unchanged". They live in this file because the
# `Template` constructor is sealed to this package and `PsycopgSession`
# executes only an object the registry holds, so there is nowhere else a
# discovery template can execute from. The four mvp-v0.1 templates above are
# untouched.
#
# The projection the two discovery templates share. Every column is either a
# canonical-reference column, match evidence, or provenance Section 7 carries
# into the trace; no attribute of the entity appears, which is where Section
# 4.12's "it returns no fact" is enforced (Section 4.4: "the registered result
# column list is where that is enforced"). `message_key` is the entity's own
# key for a message and the parent's for a signal, so every candidate carries
# the complete reference of Section 4.6.
#
# One row per approved entity. Section 4.6 lists one entity once, carrying its
# best match -- lowest tier, then lowest `match_text` in byte order -- and the
# NOT EXISTS clause in each template keeps exactly that row, so the 11-row
# limit is the truncation signal Section 4.4 describes ("an eleventh row means
# the candidate list was truncated") rather than eleven rows that might
# collapse to fewer entities.
_DISCOVERY_COLUMNS = _SCOPE + (
    "entity_kind",
    "message_key",
    "signal_key",
    "match_tier",
    "match_kind",
    "match_text",
    "entity_approval_reference",
    "alias_approval_reference",
    "alias_approved_at",
) + tuple(f"alias_{d}" for d in _SCOPE) + _SUPERSEDED_BY

_DISCOVERY_SELECT = f"""
SELECT s.project_code,
       s.revision_label,
       s.network_name,
       s.snapshot_label,
       e.entity_kind,
       COALESCE(m.message_key, pm.message_key) AS message_key,
       g.signal_key,
       {{tier}} AS match_tier,
       x.match_kind,
       x.match_text,
       e.approval_reference AS entity_approval_reference,
       a.approval_reference AS alias_approval_reference,
       a.approved_at        AS alias_approved_at,
       t.project_code       AS alias_project_code,
       t.revision_label     AS alias_revision_label,
       t.network_name       AS alias_network_name,
       t.snapshot_label     AS alias_snapshot_label,
       u.project_code       AS superseded_by_project_code,
       u.revision_label     AS superseded_by_revision_label,
       u.network_name       AS superseded_by_network_name,
       u.snapshot_label     AS superseded_by_snapshot_label
  FROM {SCHEMA}.entity_match_term AS x
  JOIN {SCHEMA}.approved_entity AS e ON e.approved_entity_id = x.approved_entity_id
  LEFT JOIN {SCHEMA}.message_occurrence AS m ON m.message_occurrence_id = e.message_occurrence_id
  LEFT JOIN {SCHEMA}.signal_occurrence AS g ON g.signal_occurrence_id = e.signal_occurrence_id
  LEFT JOIN {SCHEMA}.message_occurrence AS pm ON pm.message_occurrence_id = g.message_occurrence_id
  JOIN {SCHEMA}.source_snapshot AS s ON s.snapshot_id = COALESCE(m.snapshot_id, pm.snapshot_id)
  LEFT JOIN {SCHEMA}.source_snapshot AS u ON u.snapshot_id = s.superseded_by
  LEFT JOIN {SCHEMA}.approved_alias AS a ON a.approved_alias_id = x.approved_alias_id
  LEFT JOIN {SCHEMA}.source_snapshot AS t ON t.snapshot_id = a.asserting_snapshot_id
 WHERE s.project_code   = %(project_code)s
   AND s.revision_label = %(revision_label)s
   AND s.network_name   = %(network_name)s
   AND s.snapshot_label = %(snapshot_label)s
   AND e.entity_kind    = %(entity_kind)s
   AND (%(parent_message_key)s::text IS NULL OR pm.message_key = %(parent_message_key)s)
   AND {{match}}
   AND NOT EXISTS (
         SELECT 1
           FROM {SCHEMA}.entity_match_term AS y
          WHERE y.approved_entity_id = x.approved_entity_id
            AND {{match_y}}
            AND ({{tier_y}}, y.match_text) < ({{tier}}, x.match_text))
 ORDER BY match_tier NULLS LAST,
          message_key NULLS LAST,
          signal_key NULLS LAST,
          match_text NULLS LAST
 LIMIT 11
""".strip()

# Section 4.5: tier 1 is a lookup key equal byte for byte, tier 2 an alias
# or spelling variant equal byte for byte.
_EXACT_TIER = "CASE WHEN {alias}.match_kind = 'lookup_key' THEN 1 ELSE 2 END"
# Tier 3: the normalized token lists are equal as ordered lists. Tier 4: every
# token of the normalized term occurs in the match tokens. Both over one
# bound array, so "a variable number of tokens is one bound parameter and not
# an assembled query" (Section 4.4).
_LEXICAL_TIER = "CASE WHEN {alias}.match_tokens = %(normalized_term)s::text[] THEN 3 ELSE 4 END"

TPL_REGISTRY_STATE_V1 = Template(
    seal=_SEAL,
    name="TPL_REGISTRY_STATE_V1",
    version="1",
    # entity-discovery-v0.1 Section 4.4: no parameters, at most one row. The
    # ORDER BY is required of every registered template (Section 6) and is
    # over a one-row table; the LIMIT is the contract's 1. `registry_digest`
    # and `built_at` are exactly Section 4.1's two columns, enumerated rather
    # than `*` so that the registered result column list is the schema's.
    sql=f"""
SELECT r.registry_digest,
       r.built_at
  FROM {SCHEMA}.entity_registry_state AS r
 ORDER BY r.registry_digest NULLS LAST
 LIMIT 1
""".strip(),
    result_columns=("registry_digest", "built_at"),
    ordering=("registry_digest",),
    row_limit=1,
    limit_meaning=LimitMeaning.DETECTS_OVERFLOW,
)

TPL_DISCOVERY_EXACT_V1 = Template(
    seal=_SEAL,
    name="TPL_DISCOVERY_EXACT_V1",
    version="1",
    sql=_DISCOVERY_SELECT.format(
        tier=_EXACT_TIER.format(alias="x"),
        tier_y=_EXACT_TIER.format(alias="y"),
        match="x.match_text = %(term)s",
        match_y="y.match_text = %(term)s",
    ),
    required_parameters=_SCOPE + ("entity_kind", "term"),
    optional_parameters=("parent_message_key",),
    result_columns=_DISCOVERY_COLUMNS,
    # entity-discovery-v0.1 Section 4.4's ordering. Total without a
    # surrogate: within one snapshot no two approved entities of one kind
    # share (message_key, signal_key), and one row per entity is kept.
    ordering=("match_tier", "message_key", "signal_key", "match_text"),
    row_limit=11,
    limit_meaning=LimitMeaning.TRUNCATES,
    declared_limitations=(LimitationKind.TRUNCATED_BY_LIMIT,),
)

TPL_DISCOVERY_LEXICAL_V1 = Template(
    seal=_SEAL,
    name="TPL_DISCOVERY_LEXICAL_V1",
    version="1",
    sql=_DISCOVERY_SELECT.format(
        tier=_LEXICAL_TIER.format(alias="x"),
        tier_y=_LEXICAL_TIER.format(alias="y"),
        match="x.match_tokens @> %(normalized_term)s::text[]",
        match_y="y.match_tokens @> %(normalized_term)s::text[]",
    ),
    required_parameters=_SCOPE + ("entity_kind", "normalized_term"),
    optional_parameters=("parent_message_key",),
    result_columns=_DISCOVERY_COLUMNS,
    ordering=("match_tier", "message_key", "signal_key", "match_text"),
    row_limit=11,
    limit_meaning=LimitMeaning.TRUNCATES,
    declared_limitations=(LimitationKind.TRUNCATED_BY_LIMIT,),
)


# mvp-v0.1 Section 4.4 registers the first four; entity-discovery-v0.1
# Section 4.4 the next three. The mapping is the registry, and `get()` below
# is the only way to reach a template by name.
REGISTERED = (
    TPL_SNAPSHOT_CANDIDATES_V1,
    TPL_MESSAGE_FACTS_V1,
    TPL_SIGNAL_FACTS_V1,
    TPL_SIGNAL_MAPPING_V1,
    TPL_REGISTRY_STATE_V1,
    TPL_DISCOVERY_EXACT_V1,
    TPL_DISCOVERY_LEXICAL_V1,
)

_BY_NAME = {template.name: template for template in REGISTERED}


def names() -> tuple[str, ...]:
    """The registered template names: mvp-v0.1 Section 4.4's four, then
    entity-discovery-v0.1 Section 4.4's three, each in its contract's order."""
    return tuple(template.name for template in REGISTERED)


def get(name: object) -> Template:
    """Return the registered template called `name`.

    Section 4.4: "Execution is refused for any template name not in the
    registry." This is the refusal, and it is the only lookup: nothing here
    accepts SQL text, a table name, or a column name from a caller, so a name
    that is not one of the seven has nothing to fall back to.
    """
    template = _BY_NAME.get(name) if isinstance(name, str) else None
    if template is None:
        raise UnregisteredTemplate(
            f"{name!r} is not a registered template; the registry holds"
            f" {list(names())} (Section 4.4)"
        )
    return template
