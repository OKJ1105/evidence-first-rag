"""The session port refuses anything the registry does not itself hold.

Charter Section 3.1 forbids an arbitrary-SQL, arbitrary-table or
arbitrary-column interface, and `runtime/execution.py` claimed "there is no
shape of call through this boundary that carries a query". An external review
showed the claim was false: nothing constrained the `template` argument, so a
`SimpleNamespace` with `.name`, `.sql` and `.bind` reached `cursor.execute`
intact.

Skipped when psycopg is absent, because `connection.py` is the one runtime
module that imports it and the `repository-checks` CI job installs nothing.
The same behaviour is asserted against a real database in
`tests_database/test_conformance_run.py`.
"""

import importlib.util
import types
import unittest

HAS_DRIVER = importlib.util.find_spec("psycopg") is not None

if HAS_DRIVER:
    from evidence_first_rag.registry import TPL_MESSAGE_FACTS_V1, get
    from evidence_first_rag.runtime.connection import PsycopgSession
    from evidence_first_rag.runtime.faults import Fault


class RecordingCursor:
    def __init__(self, seen):
        self._seen = seen

    def __enter__(self):
        return self

    def __exit__(self, *unused):
        return False

    def execute(self, sql, parameters=None):
        self._seen.append(sql)

    def fetchall(self):
        return []


def connection(seen):
    return types.SimpleNamespace(
        cursor=lambda: RecordingCursor(seen),
        info=types.SimpleNamespace(user="mvp_runtime"),
        read_only=True,
    )


@unittest.skipUnless(HAS_DRIVER, "psycopg is not installed")
class OnlyARegisteredTemplateReachesTheDriver(unittest.TestCase):
    def test_a_duck_typed_object_is_refused(self):
        # The review's input, verbatim. It used to reach the driver.
        seen = []
        duck = types.SimpleNamespace(
            name="x",
            sql="DELETE FROM mvp.source_snapshot",
            bind=lambda arguments: dict(arguments),
        )
        with self.assertRaises(Fault):
            PsycopgSession(connection=connection(seen)).execute(duck, {"k": "v"})
        self.assertEqual(seen, [])

    def test_an_object_taking_a_registered_name_is_refused_too(self):
        # Identity, not name, and not `isinstance`: Issue #28 established that
        # a real `Template` can be forged with no import at all, so a type
        # check would pass exactly the case this exists to catch.
        seen = []
        impostor = types.SimpleNamespace(
            name="TPL_MESSAGE_FACTS_V1",
            sql="SELECT 1",
            bind=lambda arguments: dict(arguments),
        )
        with self.assertRaises(Fault) as raised:
            PsycopgSession(connection=connection(seen)).execute(impostor, {})
        self.assertIn("not the registered template", str(raised.exception))
        self.assertEqual(seen, [])

    def test_a_nameless_object_is_refused(self):
        seen = []
        for nameless in (
            types.SimpleNamespace(sql="SELECT 1", bind=lambda a: {}),
            types.SimpleNamespace(name=None, sql="SELECT 1", bind=lambda a: {}),
            types.SimpleNamespace(name=42, sql="SELECT 1", bind=lambda a: {}),
        ):
            with self.subTest(name=getattr(nameless, "name", "<absent>")):
                with self.assertRaises(Fault):
                    PsycopgSession(connection=connection(seen)).execute(nameless, {})
        self.assertEqual(seen, [])

    def test_the_four_registered_templates_still_run(self):
        # The other half: a guard that refused everything would satisfy the
        # tests above and break the runtime.
        seen = []
        session = PsycopgSession(connection=connection(seen))
        session.execute(
            TPL_MESSAGE_FACTS_V1,
            {
                "project_code": "SAMPLE_PROJECT_ALPHA",
                "revision_label": "SAMPLE_REV_A",
                "network_name": "SAMPLE_NET_POWERTRAIN",
                "snapshot_label": "SAMPLE_SNAP_BASE",
                "message_key": "SAMPLE_MSG_ENGINE_STATUS",
            },
        )
        self.assertEqual(seen, [TPL_MESSAGE_FACTS_V1.sql])

    def test_the_check_compares_identity_with_what_get_returns(self):
        self.assertIs(get("TPL_MESSAGE_FACTS_V1"), TPL_MESSAGE_FACTS_V1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
