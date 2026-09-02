-- Section 4.1: the four tables, their column order, and every constraint that
-- carries an identity or scope invariant.
--
-- Run against the application database as the provisioning identity.
--
-- Column order below is the order Section 4.1 declares and is normative for
-- the schema: identity columns first, then columns that carry interpretation,
-- then columns that describe wire encoding.

CREATE SCHEMA mvp;

-- Section 4.11: surrogate keys are PostgreSQL identity columns, assigned at
-- load. GENERATED ALWAYS rather than BY DEFAULT, so a loader that tried to
-- supply one from a fixture would be refused by the database. Section 4.11
-- forbids surrogate values in fixture files; this makes that a constraint
-- rather than a convention.

CREATE TABLE mvp.source_snapshot (
    snapshot_id     bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    project_code    text        NOT NULL,
    revision_label  text        NOT NULL,
    network_name    text        NOT NULL,
    snapshot_label  text        NOT NULL,
    superseded_by   bigint          NULL REFERENCES mvp.source_snapshot (snapshot_id),
    ingested_at     timestamptz NOT NULL,

    -- Section 4.1. The four dimensions of Section 4.2 identify at most one
    -- snapshot, which is what lets a complete scope resolve to exactly one.
    CONSTRAINT source_snapshot_scope_key
        UNIQUE (project_code, revision_label, network_name, snapshot_label),

    -- Section 4.2 exposes `superseded_by` in `limitations`; a snapshot that
    -- superseded itself would make that entry meaningless.
    CONSTRAINT source_snapshot_not_self_superseding
        CHECK (superseded_by IS DISTINCT FROM snapshot_id)
);

CREATE TABLE mvp.message_occurrence (
    message_occurrence_id bigint  GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    snapshot_id           bigint  NOT NULL REFERENCES mvp.source_snapshot (snapshot_id),
    message_key           text    NOT NULL,
    transmit_mode         text        NULL,
    transmit_period_ms    integer     NULL,
    payload_byte_length   integer     NULL,
    frame_identifier      integer     NULL,

    -- Section 4.1: "the constraint that keeps identically named messages in
    -- different snapshots distinct." FX-101 is the fixture that exercises it.
    CONSTRAINT message_occurrence_key
        UNIQUE (snapshot_id, message_key)
);

CREATE TABLE mvp.signal_occurrence (
    signal_occurrence_id  bigint  GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    message_occurrence_id bigint  NOT NULL REFERENCES mvp.message_occurrence (message_occurrence_id),
    signal_key            text    NOT NULL,
    unit_label            text        NULL,
    scale_factor          numeric     NULL,
    scale_offset          numeric     NULL,
    bit_width             integer     NULL,
    bit_offset            integer     NULL,

    -- Section 4.1: "the constraint that keeps identically named signals under
    -- different parent messages distinct." FX-102 exercises it.
    --
    -- Section 4.1 also PROHIBITS a snapshot-level unique constraint on
    -- `signal_key`. There is deliberately no such constraint here, and the
    -- data-level invariant check asserts its absence rather than trusting
    -- this comment: a schema that added one would still load the registered
    -- fixtures, and would only fail later, on data nobody has yet.
    CONSTRAINT signal_occurrence_key
        UNIQUE (message_occurrence_id, signal_key)
);

CREATE TABLE mvp.signal_mapping (
    signal_mapping_id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    asserting_snapshot_id      bigint NOT NULL REFERENCES mvp.source_snapshot (snapshot_id),
    source_signal_occurrence_id bigint NOT NULL REFERENCES mvp.signal_occurrence (signal_occurrence_id),
    target_signal_occurrence_id bigint NOT NULL REFERENCES mvp.signal_occurrence (signal_occurrence_id),
    mapping_key                text   NOT NULL,
    transform_kind             text       NULL,

    -- Section 4.1. Endpoints may belong to snapshots other than the asserting
    -- snapshot; that is the cross-snapshot case Charter Section 3.6 governs,
    -- and FX-104 loads one.
    CONSTRAINT signal_mapping_relation_key
        UNIQUE (asserting_snapshot_id, source_signal_occurrence_id, target_signal_occurrence_id)
);
