"""Section 4.3 and Section 6: the two identities, and the database they open."""

import unittest

import psycopg

from . import support

DATABASE = "mvp_test_roles"


def setUpModule():
    support.build(DATABASE)


def tearDownModule():
    support.drop(DATABASE)


class TheDatabaseCollation(unittest.TestCase):
    """Section 6: `ENCODING UTF8`, `LC_COLLATE='C'`, `LC_CTYPE='C'`."""

    def test_it_reports_c_collation_and_utf8(self):
        with support.connect(DATABASE) as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT datcollate, datctype, pg_encoding_to_char(encoding)"
                " FROM pg_database WHERE datname = current_database()"
            )
            collate, ctype, encoding = cursor.fetchone()
        self.assertEqual(collate, "C")
        self.assertEqual(ctype, "C")
        self.assertEqual(encoding, "UTF8")

    def test_text_ordering_is_byte_wise(self):
        # The observable consequence of `C`. Under a typical libc or ICU
        # collation, punctuation and case are folded into the ordering and
        # 'SAMPLE_a' sorts before 'SAMPLE_B'; byte order puts uppercase first.
        with support.connect(DATABASE) as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT k FROM (VALUES ('SAMPLE_a'), ('SAMPLE_B')) AS v(k) ORDER BY k"
            )
            ordered = [row[0] for row in cursor.fetchall()]
        self.assertEqual(ordered, ["SAMPLE_B", "SAMPLE_a"])


class TheRuntimeIdentityCannotWrite(unittest.TestCase):
    """Section 4.3: SELECT only. Section 4.10 requires the four refusals, and
    requires them to originate from PostgreSQL privileges rather than from an
    application guard."""

    WRITES = {
        "INSERT": "INSERT INTO mvp.source_snapshot"
                  " (project_code, revision_label, network_name, snapshot_label, ingested_at)"
                  " VALUES ('X', 'X', 'X', 'X', now())",
        "UPDATE": "UPDATE mvp.source_snapshot SET project_code = 'X'",
        "DELETE": "DELETE FROM mvp.source_snapshot",
        "CREATE TABLE": "CREATE TABLE mvp.intruder (id integer)",
    }

    def test_it_can_read(self):
        with support.connect(DATABASE, "runtime") as connection, connection.cursor() as cursor:
            cursor.execute("SELECT count(*) FROM mvp.source_snapshot")
            self.assertEqual(cursor.fetchone()[0], 4)

    def test_each_of_the_four_writes_is_refused(self):
        for name, statement in self.WRITES.items():
            with self.subTest(statement=name):
                with support.connect(DATABASE, "runtime") as connection:
                    with self.assertRaises(psycopg.Error):
                        with connection.cursor() as cursor:
                            cursor.execute(statement)

    def test_the_refusal_comes_from_privileges_not_the_transaction_mode(self):
        # Section 4.10: "Refusal must originate from PostgreSQL privileges,
        # not from an application guard." The role also defaults to a
        # read-only transaction, which would refuse a write on its own and
        # hide whether the grants are right. Turning that default off for the
        # session isolates the privilege: the write must still be refused, and
        # refused as InsufficientPrivilege.
        for name, statement in self.WRITES.items():
            with self.subTest(statement=name):
                with support.connect(DATABASE, "runtime") as connection:
                    # autocommit first: `default_transaction_read_only` takes
                    # effect on the next transaction to begin, and psycopg has
                    # already opened one by the time a cursor runs. Setting it
                    # inside that transaction would change nothing, and the
                    # write would be refused by the transaction mode again --
                    # which is the very thing this test is trying to rule out.
                    connection.autocommit = True
                    with connection.cursor() as cursor:
                        cursor.execute("SET default_transaction_read_only = off")
                        cursor.execute("SHOW default_transaction_read_only")
                        self.assertEqual(cursor.fetchone()[0], "off")
                        with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                            cursor.execute(statement)

    def test_it_holds_no_write_grant_on_any_of_the_four_tables(self):
        tables = (
            "source_snapshot",
            "message_occurrence",
            "signal_occurrence",
            "signal_mapping",
        )
        with support.connect(DATABASE) as connection, connection.cursor() as cursor:
            for table in tables:
                for privilege in ("INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES"):
                    with self.subTest(table=table, privilege=privilege):
                        cursor.execute(
                            "SELECT has_table_privilege('mvp_runtime', %s, %s)",
                            (f"mvp.{table}", privilege),
                        )
                        self.assertFalse(cursor.fetchone()[0])
                cursor.execute(
                    "SELECT has_table_privilege('mvp_runtime', %s, 'SELECT')",
                    (f"mvp.{table}",),
                )
                self.assertTrue(cursor.fetchone()[0])

    def test_it_cannot_create_in_the_application_schema(self):
        with support.connect(DATABASE) as connection, connection.cursor() as cursor:
            cursor.execute("SELECT has_schema_privilege('mvp_runtime', 'mvp', 'CREATE')")
            self.assertFalse(cursor.fetchone()[0])
            cursor.execute("SELECT has_schema_privilege('mvp_runtime', 'mvp', 'USAGE')")
            self.assertTrue(cursor.fetchone()[0])


class TheProvisioningIdentityIsBounded(unittest.TestCase):
    """Section 4.3 gives the provisioning identity `CREATE`, `INSERT` on the
    application schema. Review finding N2 observed that the code gave it more
    than that, and it was right; these tests pin what it actually holds, so
    the part that cannot be narrowed is examined rather than assumed.

    What was narrowed: it no longer owns the database, so `DROP DATABASE` and
    `ALTER DATABASE` are out of reach.

    What remains, and why: PostgreSQL gives the creator of a table ownership
    of it, so an identity granted `CREATE` necessarily gains `ALTER`, `DROP`
    and `TRUNCATE` over what it creates. Section 4.3's vocabulary has no way
    to express "CREATE but not own". Closing that would mean the superuser
    creating the tables and the provisioning identity only inserting -- which
    contradicts the `CREATE` the same table grants it. The mismatch is between
    the contract's privilege vocabulary and PostgreSQL's model, so it is the
    repository owner's to resolve rather than something to paper over here.
    """

    def test_it_is_not_a_superuser_and_cannot_make_roles_or_databases(self):
        with support.connect(DATABASE) as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT rolsuper, rolcreaterole, rolcreatedb, rolbypassrls,"
                " rolreplication FROM pg_roles WHERE rolname = 'mvp_provisioning'"
            )
            for name, held in zip(
                ("superuser", "createrole", "createdb", "bypassrls", "replication"),
                cursor.fetchone(),
            ):
                with self.subTest(attribute=name):
                    self.assertFalse(held)

    def test_it_does_not_own_the_database(self):
        # Ownership would carry DROP DATABASE and ALTER DATABASE, neither of
        # which Section 4.3's table lists.
        with support.connect(DATABASE) as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_catalog.pg_get_userbyid(datdba) FROM pg_database"
                " WHERE datname = current_database()"
            )
            self.assertNotEqual(cursor.fetchone()[0], "mvp_provisioning")

    def test_it_holds_the_create_it_needs_and_the_insert_section_4_3_grants(self):
        with support.connect(DATABASE) as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT has_database_privilege('mvp_provisioning', current_database(), 'CREATE')"
            )
            self.assertTrue(cursor.fetchone()[0])
            cursor.execute(
                "SELECT has_table_privilege('mvp_provisioning', 'mvp.source_snapshot', 'INSERT')"
            )
            self.assertTrue(cursor.fetchone()[0])

    def test_it_owns_what_it_creates_and_that_is_recorded_not_hidden(self):
        # The residual N2 gap, asserted rather than left implicit. If a later
        # slice narrows it, this test fails and the narrowing gets noticed.
        with support.connect(DATABASE) as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT nspowner::regrole::text FROM pg_namespace WHERE nspname = 'mvp'"
            )
            self.assertEqual(cursor.fetchone()[0], "mvp_provisioning")
            for table in (
                "source_snapshot",
                "message_occurrence",
                "signal_occurrence",
                "signal_mapping",
            ):
                with self.subTest(table=table):
                    cursor.execute(
                        "SELECT relowner::regrole::text FROM pg_class c"
                        " JOIN pg_namespace n ON n.oid = c.relnamespace"
                        " WHERE n.nspname = 'mvp' AND c.relname = %s",
                        (table,),
                    )
                    self.assertEqual(cursor.fetchone()[0], "mvp_provisioning")


class TheRuntimeRoleConfiguration(unittest.TestCase):
    def test_statement_timeout_is_five_seconds(self):
        # Section 4.4. Read from the role rather than the session, because the
        # contract sets it "at the role level by provisioning".
        with support.connect(DATABASE, "runtime") as connection, connection.cursor() as cursor:
            cursor.execute("SHOW statement_timeout")
            self.assertEqual(cursor.fetchone()[0], "5s")

    def test_connections_default_to_a_read_only_transaction(self):
        with support.connect(DATABASE, "runtime") as connection, connection.cursor() as cursor:
            cursor.execute("SHOW default_transaction_read_only")
            self.assertEqual(cursor.fetchone()[0], "on")


if __name__ == "__main__":
    unittest.main(verbosity=2)
