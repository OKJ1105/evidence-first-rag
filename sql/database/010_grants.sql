-- Section 4.3: what each identity may do, applied after 000_schema.sql so the
-- four tables exist to be granted on.
--
-- Run against the application database as the provisioning identity.

-- The provisioning identity owns the schema, so it already holds CREATE and
-- INSERT there. Nothing to grant it; ownership is the grant.

-- Nobody reaches the application schema except the two identities.
REVOKE ALL ON SCHEMA mvp FROM PUBLIC;

-- Section 4.3: the runtime identity gets SELECT only, on the four tables, and
-- no CREATE, INSERT, UPDATE, DELETE, TRUNCATE, or DDL. Granting table by
-- table rather than with ALL TABLES IN SCHEMA is deliberate: a table added
-- later is not silently readable, it is a decision.
GRANT USAGE ON SCHEMA mvp TO mvp_runtime;
GRANT SELECT ON mvp.source_snapshot     TO mvp_runtime;
GRANT SELECT ON mvp.message_occurrence  TO mvp_runtime;
GRANT SELECT ON mvp.signal_occurrence   TO mvp_runtime;
GRANT SELECT ON mvp.signal_mapping      TO mvp_runtime;

-- No default privileges are set for future objects. Section 4.10 proves the
-- runtime cannot write; a default that granted something to a table nobody
-- has reviewed would make that proof narrower than it looks.
