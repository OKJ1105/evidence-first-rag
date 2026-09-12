-- entity-discovery-v0.1 Section 4.1: the approved entity registry. Four
-- tables, additional to the four of mvp-v0.1 Section 4.1 and referencing
-- them.
--
-- Run against the application database as the provisioning identity, after
-- 000_schema.sql (the tables referenced here) and 010_grants.sql. Applied in
-- lexical order like every other file in this directory (mvp-v0.1 Section
-- 3.4); the registry grants follow in 030_registry_grants.sql.
--
-- Column order is the order Section 4.1 declares and is normative for the
-- schema. Surrogate keys are GENERATED ALWAYS identity columns for the same
-- reason the mvp-v0.1 tables' are (Section 4.11): a fixture never carries
-- one, and a loader that tried to supply one is refused by the database.

-- The allowlist. One row per entity occurrence that discovery may return.
CREATE TABLE mvp.approved_entity (
    approved_entity_id     bigint    GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    entity_kind            text      NOT NULL,
    message_occurrence_id  bigint        NULL REFERENCES mvp.message_occurrence (message_occurrence_id),
    signal_occurrence_id   bigint        NULL REFERENCES mvp.signal_occurrence (signal_occurrence_id),
    approval_reference     text      NOT NULL,
    approved_at            timestamp NOT NULL,

    -- Section 4.2 rule 3: no other value is loadable.
    CONSTRAINT approved_entity_kind_enumerated
        CHECK (entity_kind IN ('message', 'signal')),

    -- Section 4.1: exactly one of the two occurrence references is non-null,
    -- and it is the one `entity_kind` names. The two foreign keys above are
    -- what make Charter Section 9's "resolvable in the approved data scope"
    -- a constraint rather than a check: a registry row naming an occurrence
    -- that is not loaded cannot exist.
    CONSTRAINT approved_entity_one_occurrence
        CHECK (
            (entity_kind = 'message' AND message_occurrence_id IS NOT NULL AND signal_occurrence_id IS NULL)
         OR (entity_kind = 'signal'  AND signal_occurrence_id  IS NOT NULL AND message_occurrence_id IS NULL)
        )
);

-- Section 4.1: "an occurrence is approved once or not at all." Partial
-- unique indexes, one per reference, over its non-null rows. A plain UNIQUE
-- on a nullable column would also do in PostgreSQL, which treats nulls as
-- distinct, but the partial form says what it means and the invariant check
-- looks for exactly this shape.
CREATE UNIQUE INDEX approved_entity_message_once
    ON mvp.approved_entity (message_occurrence_id)
    WHERE message_occurrence_id IS NOT NULL;
CREATE UNIQUE INDEX approved_entity_signal_once
    ON mvp.approved_entity (signal_occurrence_id)
    WHERE signal_occurrence_id IS NOT NULL;

-- Lookup metadata for an approved entity.
CREATE TABLE mvp.approved_alias (
    approved_alias_id      bigint    GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    approved_entity_id     bigint    NOT NULL REFERENCES mvp.approved_entity (approved_entity_id),
    alias_text             text      NOT NULL,
    alias_kind             text      NOT NULL,
    asserting_snapshot_id  bigint    NOT NULL REFERENCES mvp.source_snapshot (snapshot_id),
    approval_reference     text      NOT NULL,
    approved_at            timestamp NOT NULL,

    -- Section 4.2 rule 3.
    CONSTRAINT approved_alias_kind_enumerated
        CHECK (alias_kind IN ('approved_alias', 'spelling_variant')),

    -- Section 4.1. And, deliberately, NO unique constraint on `alias_text`
    -- alone: two entities may carry the same approved alias, and an alias
    -- may equal another entity's lookup key. Section 4.7 makes such a term
    -- abstain into candidates (DX-004); a uniqueness constraint here would
    -- turn that fail-closed outcome into a load-time error. The invariant
    -- check asserts the absence rather than trusting this comment.
    CONSTRAINT approved_alias_text_per_entity
        UNIQUE (approved_entity_id, alias_text)
);

-- The derived matching surface. Built during provisioning from the two
-- tables above, never authored: Section 4.2 rule 2 makes every row a
-- function of a row in one of them, and the invariant check recomputes it.
CREATE TABLE mvp.entity_match_term (
    entity_match_term_id   bigint  GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    approved_entity_id     bigint  NOT NULL REFERENCES mvp.approved_entity (approved_entity_id),
    match_kind             text    NOT NULL,
    match_text             text    NOT NULL,
    match_tokens           text[]  NOT NULL,
    approved_alias_id      bigint      NULL REFERENCES mvp.approved_alias (approved_alias_id),

    CONSTRAINT entity_match_term_kind_enumerated
        CHECK (match_kind IN ('lookup_key', 'approved_alias', 'spelling_variant')),

    -- Section 4.1: `approved_alias_id` is non-null exactly when the kind is
    -- not `lookup_key`. It carries the provenance Section 7 puts in the trace.
    CONSTRAINT entity_match_term_alias_when_not_key
        CHECK ((match_kind = 'lookup_key') = (approved_alias_id IS NULL)),

    -- Section 4.1 says `match_tokens` is never empty and Section 4.2 rule 5
    -- refuses the row at load. The loader refuses it first, with the file
    -- and line; this is the database saying the same thing about any row
    -- that reached it by another path.
    CONSTRAINT entity_match_term_has_a_token
        CHECK (cardinality(match_tokens) > 0),

    CONSTRAINT entity_match_term_per_entity
        UNIQUE (approved_entity_id, match_kind, match_text)
);

-- Exactly one row, written by the provisioning identity after the three
-- tables above are loaded. Exactly the two columns Section 4.1 declares, in
-- its order: "column order is normative for the schema definition", and the
-- data-level check asserts every registry table's column list against the
-- contract's.
CREATE TABLE mvp.entity_registry_state (
    registry_digest  text      NOT NULL,
    built_at         timestamp NOT NULL
);

-- Section 4.1: "A check constraint permits at most one row." Recorded as a
-- deviation in mechanism, not in effect: a PostgreSQL CHECK constraint sees
-- one row and cannot count them, so the rule is a unique index over a
-- constant expression -- every row has the same key, so a second row is a
-- UniqueViolation. Chosen over a constant column carrying a unique
-- constraint (review N6/O2 on #142) because that column would be one the
-- contract's column table does not declare, and TPL_REGISTRY_STATE_V1 later
-- registers a result column list that must match Section 4.1's.
CREATE UNIQUE INDEX entity_registry_state_at_most_one_row
    ON mvp.entity_registry_state ((true));
