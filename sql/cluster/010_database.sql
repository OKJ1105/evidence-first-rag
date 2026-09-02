-- Section 6: the application database and the collation every comparison and
-- ordering in this contract is defined against.
--
-- Run against the maintenance database as the cluster superuser, after
-- 000_roles.sql. The database name is a variable so that provisioning can
-- build a second database from the same scripts, which is how the Section 6
-- repeatability assertion compares two provisioning runs.
--
-- `TEMPLATE template0` is required, not stylistic: template1 carries the
-- cluster's own locale, and copying it would silently inherit whatever the
-- host initialised with. Section 6 chose `C` because byte-wise ordering is
-- identical on every platform and PostgreSQL build, where ICU and libc
-- collations drift between a local container and a managed service. Taking
-- the cluster default would give up exactly that guarantee, and the
-- data-level invariant check asserts the collation it got rather than
-- trusting this file to have asked for it.

CREATE DATABASE :"database_name"
    TEMPLATE template0
    ENCODING 'UTF8'
    LC_COLLATE 'C'
    LC_CTYPE 'C';

REVOKE CONNECT ON DATABASE :"database_name" FROM PUBLIC;
GRANT CONNECT ON DATABASE :"database_name" TO mvp_runtime;

-- Section 4.3 gives the provisioning identity CREATE and INSERT on the
-- application schema, and nothing else. Deliberately no OWNER clause above:
-- owning the database would carry DROP DATABASE and ALTER DATABASE with it,
-- neither of which that table lists. The cluster superuser owns the database
-- and the provisioning identity is granted exactly the CREATE it needs to
-- build the schema inside it.
--
-- One privilege remains wider than the contract's table reads, and it is
-- inherent rather than chosen: in PostgreSQL the creator of a table owns it,
-- so an identity granted CREATE necessarily gains ALTER, DROP and TRUNCATE
-- over what it creates. Section 4.3's vocabulary has no way to say "CREATE
-- but not own". tests_database/test_roles.py pins the resulting privilege set
-- so it is examined rather than assumed, and the gap is open as an Issue.
GRANT CONNECT, CREATE ON DATABASE :"database_name" TO mvp_provisioning;
