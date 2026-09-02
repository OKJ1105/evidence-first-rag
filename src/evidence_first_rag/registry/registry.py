"""The four registered templates of Section 4.4, and the only way to reach one.

Section 4.4 registers exactly four templates and says "Execution is refused
for any template name not in the registry." `get()` is that refusal. There is
no function here that takes SQL text, a table name, or a column name from a
caller: the SQL is written out below, committed, and inspectable, which is
what Charter Section 3.1 requires of the query-template registry.

The `mvp` schema qualifier is the one thing this module shares with the
provisioning slice. Column names come from contract Section 4.1, but the
schema name is a provisioning choice, so the two have to agree; SCHEMA is
named once here so that a disagreement is one edit rather than a search.
"""

from ..evidence import LimitationKind
from .template import LimitMeaning, Template, UnregisteredTemplate

SCHEMA = "mvp"

# Section 4.2's four scope dimensions, as they appear in every template.
_SCOPE = ("project_code", "revision_label", "network_name", "snapshot_label")


TPL_SNAPSHOT_CANDIDATES_V1 = Template(
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


TPL_MESSAGE_FACTS_V1 = Template(
    name="TPL_MESSAGE_FACTS_V1",
    version="1",
    sql=f"""
SELECT s.project_code,
       s.revision_label,
       s.network_name,
       s.snapshot_label,
       m.message_key,
       m.transmit_mode,
       m.transmit_period_ms,
       m.payload_byte_length,
       m.frame_identifier
  FROM {SCHEMA}.message_occurrence AS m
  JOIN {SCHEMA}.source_snapshot AS s ON s.snapshot_id = m.snapshot_id
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
    ),
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
    name="TPL_SIGNAL_FACTS_V1",
    version="1",
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
       g.bit_offset
  FROM {SCHEMA}.signal_occurrence AS g
  JOIN {SCHEMA}.message_occurrence AS m ON m.message_occurrence_id = g.message_occurrence_id
  JOIN {SCHEMA}.source_snapshot AS s ON s.snapshot_id = m.snapshot_id
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
    ),
    ordering=("message_key", "signal_key", "signal_occurrence_id"),
    row_limit=2,
    limit_meaning=LimitMeaning.DETECTS_OVERFLOW,
)


TPL_SIGNAL_MAPPING_V1 = Template(
    name="TPL_SIGNAL_MAPPING_V1",
    version="1",
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
       x.transform_kind
  FROM {SCHEMA}.signal_mapping AS x
  JOIN {SCHEMA}.source_snapshot AS a ON a.snapshot_id = x.asserting_snapshot_id
  JOIN {SCHEMA}.signal_occurrence AS sg ON sg.signal_occurrence_id = x.source_signal_occurrence_id
  JOIN {SCHEMA}.message_occurrence AS sm ON sm.message_occurrence_id = sg.message_occurrence_id
  JOIN {SCHEMA}.source_snapshot AS ss ON ss.snapshot_id = sm.snapshot_id
  JOIN {SCHEMA}.signal_occurrence AS tg ON tg.signal_occurrence_id = x.target_signal_occurrence_id
  JOIN {SCHEMA}.message_occurrence AS tm ON tm.message_occurrence_id = tg.message_occurrence_id
  JOIN {SCHEMA}.source_snapshot AS ts ON ts.snapshot_id = tm.snapshot_id
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
    ),
    # Section 4.4 declares the ordering as `mapping_key`, `signal_mapping_id`.
    # The surrogate is named by the contract itself here: two mappings may
    # share a key within one asserting snapshot, so the declared column ties.
    ordering=("mapping_key", "signal_mapping_id"),
    row_limit=200,
    limit_meaning=LimitMeaning.TRUNCATES,
    declared_limitations=(LimitationKind.TRUNCATED_BY_LIMIT,),
)


# Section 4.4 registers exactly these four. The mapping is the registry, and
# `get()` below is the only way to reach a template by name.
REGISTERED = (
    TPL_SNAPSHOT_CANDIDATES_V1,
    TPL_MESSAGE_FACTS_V1,
    TPL_SIGNAL_FACTS_V1,
    TPL_SIGNAL_MAPPING_V1,
)

_BY_NAME = {template.name: template for template in REGISTERED}


def names() -> tuple[str, ...]:
    """The registered template names, in the order Section 4.4 lists them."""
    return tuple(template.name for template in REGISTERED)


def get(name: object) -> Template:
    """Return the registered template called `name`.

    Section 4.4: "Execution is refused for any template name not in the
    registry." This is the refusal, and it is the only lookup: nothing here
    accepts SQL text, a table name, or a column name from a caller, so a name
    that is not one of the four has nothing to fall back to.
    """
    template = _BY_NAME.get(name) if isinstance(name, str) else None
    if template is None:
        raise UnregisteredTemplate(
            f"{name!r} is not a registered template; the registry holds"
            f" {list(names())} (Section 4.4)"
        )
    return template
