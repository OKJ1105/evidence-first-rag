"""`deploy-v0.1` Section 6 and Section 8.1: `DP-006`, `DP-007`'s comparison and `DP-011`.

The **stable digest** of a provisioned database is what Section 6 says two
environments must agree on: the row count of every table, the stored
`registry_digest`, and the committed template digests. The `mvp-v0.1` Section
4.10 state digest's highest transaction identifier is left out, because two
instances number their transactions independently.

Row counts and template digests are read from a conformance artifact (the
runner records both); `registry_digest` is read from the database, as the
runtime identity, because the artifact does not carry it.

- `DP-006`: the deployed and the local stable digests of one commit are equal.
- `DP-007`: the deployed and the local runs give every registered case the
  same verdict.
- `DP-011`: after a rollback, the restored stable digest equals the one the
  last passing deploy recorded.
"""

import argparse
import json
import sys


def stable_digest(conformance: dict, registry_digest: str) -> dict:
    """The part of a provisioned state two environments must agree on."""
    after = conformance["state_digest"]["after"]
    return {
        "row_counts": dict(sorted(after["row_counts"].items())),
        "registry_digest": registry_digest,
        "templates": sorted(
            (template["name"], template["version"], template["sha256"])
            for template in conformance["environment"]["registered_templates"]
        ),
    }


def verdicts(conformance: dict) -> dict:
    """Each registered case's verdict, keyed by its identifier."""
    return {fixture["identifier"]: fixture["verdict"] for fixture in conformance["fixtures"]}


def differences(left: dict, right: dict) -> list:
    """The top-level keys, and for row counts the tables, on which two differ."""
    found = []
    for key in sorted(set(left) | set(right)):
        if key == "row_counts" and isinstance(left.get(key), dict) and isinstance(right.get(key), dict):
            for table in sorted(set(left[key]) | set(right[key])):
                if left[key].get(table) != right[key].get(table):
                    found.append(f"row_counts.{table}")
        elif left.get(key) != right.get(key):
            found.append(key)
    return found


def read_registry_digest(connection) -> str:
    with connection.cursor() as cursor:
        cursor.execute("SELECT registry_digest FROM mvp.entity_registry_state")
        rows = cursor.fetchall()
    if len(rows) != 1:
        raise ValueError(f"expected one entity_registry_state row, found {len(rows)}")
    return rows[0][0]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    record = commands.add_parser("record", help="write the stable digest of the database PG* names")
    record.add_argument("--conformance", required=True)
    record.add_argument("--out", required=True)
    compare = commands.add_parser("compare", help="DP-006 and DP-007 between two environments")
    compare.add_argument("--deployed-digest", required=True)
    compare.add_argument("--local-digest", required=True)
    compare.add_argument("--deployed-conformance", required=True)
    compare.add_argument("--local-conformance", required=True)
    restored = commands.add_parser("restored", help="DP-011 against the last passing record")
    restored.add_argument("--digest", required=True)
    restored.add_argument("--expected", required=True, help="the stable digest the last passing record holds")
    arguments = parser.parse_args(argv)

    def load(path):
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)

    if arguments.command == "record":
        import os

        import psycopg

        with psycopg.connect(
            dbname=os.environ.get("MVP_DATABASE", "mvp"),
            # The runtime identity can read the table and cannot write
            # (#243 N1): nothing here needs the provisioning identity.
            user="mvp_runtime",
            password=os.environ["MVP_RUNTIME_PASSWORD"],
            host=os.environ["PGHOST"],
            port=os.environ.get("PGPORT", "5432"),
        ) as connection:
            digest = stable_digest(load(arguments.conformance), read_registry_digest(connection))
        with open(arguments.out, "w", encoding="utf-8") as handle:
            json.dump(digest, handle, indent=2)
        return 0

    if arguments.command == "compare":
        digest_diff = differences(load(arguments.deployed_digest), load(arguments.local_digest))
        deployed, local = verdicts(load(arguments.deployed_conformance)), verdicts(load(arguments.local_conformance))
        verdict_diff = sorted(case for case in set(deployed) | set(local) if deployed.get(case) != local.get(case))
        print(json.dumps({
            "DP-006": {"passed": not digest_diff, "differs_on": digest_diff},
            "DP-007": {"passed": not verdict_diff, "differs_on": verdict_diff},
        }))
        return 0 if not digest_diff and not verdict_diff else 1

    diff = differences(load(arguments.digest), load(arguments.expected))
    print(json.dumps({"DP-011": {"passed": not diff, "differs_on": diff}}))
    return 0 if not diff else 1


if __name__ == "__main__":
    sys.exit(main())
