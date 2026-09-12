-- entity-discovery-v0.1 Section 3.3, extension 2: the runtime identity reads
-- the four registry tables. Applied after 020_registry.sql so they exist to
-- be granted on.
--
-- Run against the application database as the provisioning identity.
--
-- This is the decision 010_grants.sql said a later table would be: "a table
-- added later is not silently readable, it is a decision." The decision is
-- recorded in the accepted contract, Section 3.3: this contract grants the
-- runtime identity SELECT on its own tables and no other privilege on them,
-- and mvp-v0.1 Section 4.3's "SELECT only on the four tables" is read as
-- enumerating that contract's own tables rather than exhausting the role's
-- grants. A role holding SELECT on both sets and nothing else conforms to
-- both documents. Whether mvp-v0.1 is patched to name these tables outright
-- remains the owner's (entity-discovery-v0.1 Section 9).
--
-- Table by table, as 010_grants.sql does, and no default privileges for
-- future objects: Section 4.12 says discovery writes nothing, and
-- tests_database/test_registry.py proves the four refusals come from these
-- grants rather than from the transaction mode.
GRANT SELECT ON mvp.approved_entity        TO mvp_runtime;
GRANT SELECT ON mvp.approved_alias         TO mvp_runtime;
GRANT SELECT ON mvp.entity_match_term      TO mvp_runtime;
GRANT SELECT ON mvp.entity_registry_state  TO mvp_runtime;
