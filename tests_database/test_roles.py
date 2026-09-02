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
