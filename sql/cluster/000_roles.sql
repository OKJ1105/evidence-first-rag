-- Section 4.3: two database identities, created by the provisioning path.
--
-- Run against the maintenance database as the cluster superuser, before
-- 010_database.sql, which needs the provisioning identity to own the
-- application database.
--
-- Passwords are supplied by the environment as psql variables, so this file
-- stays inspectable and carries no secret.
--
-- Idempotent by design. Section 3.4 says "reproducibility comes from
-- re-provisioning, not from migration history", so provisioning has to be
-- re-runnable; roles outlive any one application database and are reused by
-- the next one rather than dropped and recreated.

DO $$
BEGIN
    -- The provisioning identity. Section 4.3 gives it CREATE and INSERT on
    -- the application schema; it gets those by owning the schema, in the
    -- application database, not here. It is not a superuser.
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'mvp_provisioning') THEN
        CREATE ROLE mvp_provisioning
            LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
            NOINHERIT NOREPLICATION NOBYPASSRLS;
    END IF;

    -- The runtime identity. Section 4.3 gives it SELECT only, on the four
    -- tables of Section 4.1, granted in the application database once those
    -- tables exist.
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'mvp_runtime') THEN
        CREATE ROLE mvp_runtime
            LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
            NOINHERIT NOREPLICATION NOBYPASSRLS;
    END IF;
END
$$;

ALTER ROLE mvp_provisioning PASSWORD :'provisioning_password';
ALTER ROLE mvp_runtime      PASSWORD :'runtime_password';

-- Section 4.4: "The runtime identity runs with `statement_timeout = 5s`, set
-- at the role level by provisioning." At the role level rather than per
-- session, so a runtime that forgets to set it still gets it.
ALTER ROLE mvp_runtime SET statement_timeout = '5s';

-- Section 4.3, defensively. The runtime opens every connection inside a
-- read-only transaction; the role-level default means a connection that omits
-- it is still read-only. This is a second line, not the enforcement: Section
-- 4.10 requires the refusal to originate from privileges, and the SELECT-only
-- grants in the application database are what provide that.
ALTER ROLE mvp_runtime SET default_transaction_read_only = on;
