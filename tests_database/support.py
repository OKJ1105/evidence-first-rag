"""Provisioning helpers shared by the database tests."""

import os
import pathlib

import psycopg

from evidence_first_rag.db import provision

REPOSITORY = pathlib.Path(__file__).resolve().parent.parent
FIXTURES = REPOSITORY / "fixtures"
SQL = REPOSITORY / "sql"


def build(database: str, fixtures: pathlib.Path = FIXTURES) -> None:
    """Provision `database` from empty. Raises if provisioning fails."""
    provision.main(
        [
            "--sql", str(SQL),
            "--fixtures", str(fixtures),
            "--database", database,
            "--recreate",
        ]
    )


def drop(database: str) -> None:
    provision._drop_database(
        os.environ.get("PGUSER", "postgres"), os.environ.get("PGPASSWORD", ""), database
    )


def connect(database: str, role: str = "provisioning"):
    """Open a connection as one of the two Section 4.3 identities."""
    user, password = {
        "provisioning": ("mvp_provisioning", os.environ["MVP_PROVISIONING_PASSWORD"]),
        "runtime": ("mvp_runtime", os.environ["MVP_RUNTIME_PASSWORD"]),
    }[role]
    return psycopg.connect(
        dbname=database,
        user=user,
        password=password,
        host=os.environ.get("PGHOST"),
        port=os.environ.get("PGPORT"),
    )


# Contract-visible content per table, with every surrogate key projected back
# to the natural key it stands for. Section 4.11 permits two provisioning runs
# to assign different surrogate values, so a repeatability comparison that
# included them would fail for a reason Section 6 explicitly allows.
CONTRACT_VISIBLE = {
    "source_snapshot": """
        SELECT s.project_code, s.revision_label, s.network_name, s.snapshot_label,
               u.project_code, u.revision_label, u.network_name, u.snapshot_label,
               s.ingested_at
        FROM mvp.source_snapshot s
        LEFT JOIN mvp.source_snapshot u ON u.snapshot_id = s.superseded_by
        ORDER BY s.project_code, s.revision_label, s.network_name, s.snapshot_label
    """,
    "message_occurrence": """
        SELECT s.project_code, s.revision_label, s.network_name, s.snapshot_label,
               m.message_key, m.transmit_mode, m.transmit_period_ms,
               m.payload_byte_length, m.frame_identifier
        FROM mvp.message_occurrence m
        JOIN mvp.source_snapshot s ON s.snapshot_id = m.snapshot_id
        ORDER BY s.project_code, s.revision_label, s.network_name, s.snapshot_label,
                 m.message_key
    """,
    "signal_occurrence": """
        SELECT s.project_code, s.revision_label, s.network_name, s.snapshot_label,
               m.message_key, g.signal_key, g.unit_label, g.scale_factor,
               g.scale_offset, g.bit_width, g.bit_offset
        FROM mvp.signal_occurrence g
        JOIN mvp.message_occurrence m ON m.message_occurrence_id = g.message_occurrence_id
        JOIN mvp.source_snapshot s ON s.snapshot_id = m.snapshot_id
        ORDER BY s.project_code, s.revision_label, s.network_name, s.snapshot_label,
                 m.message_key, g.signal_key
    """,
    "signal_mapping": """
        SELECT a.project_code, a.revision_label, a.network_name, a.snapshot_label,
               p.snapshot_label, sm.message_key, sg.signal_key,
               q.snapshot_label, tm.message_key, tg.signal_key,
               x.mapping_key, x.transform_kind
        FROM mvp.signal_mapping x
        JOIN mvp.source_snapshot a ON a.snapshot_id = x.asserting_snapshot_id
        JOIN mvp.signal_occurrence sg ON sg.signal_occurrence_id = x.source_signal_occurrence_id
        JOIN mvp.message_occurrence sm ON sm.message_occurrence_id = sg.message_occurrence_id
        JOIN mvp.source_snapshot p ON p.snapshot_id = sm.snapshot_id
        JOIN mvp.signal_occurrence tg ON tg.signal_occurrence_id = x.target_signal_occurrence_id
        JOIN mvp.message_occurrence tm ON tm.message_occurrence_id = tg.message_occurrence_id
        JOIN mvp.source_snapshot q ON q.snapshot_id = tm.snapshot_id
        ORDER BY x.mapping_key, x.signal_mapping_id
    """,
    # entity-discovery-v0.1 Section 4.1. Every surrogate projected to the
    # natural key of the occurrence, alias or snapshot it stands for, so the
    # Section 6 repeatability comparison covers the registry too.
    "approved_entity": """
        SELECT e.entity_kind,
               s.project_code, s.revision_label, s.network_name, s.snapshot_label,
               COALESCE(m.message_key, pm.message_key), g.signal_key,
               e.approval_reference, e.approved_at
        FROM mvp.approved_entity e
        LEFT JOIN mvp.message_occurrence m ON m.message_occurrence_id = e.message_occurrence_id
        LEFT JOIN mvp.signal_occurrence g ON g.signal_occurrence_id = e.signal_occurrence_id
        LEFT JOIN mvp.message_occurrence pm ON pm.message_occurrence_id = g.message_occurrence_id
        JOIN mvp.source_snapshot s ON s.snapshot_id = COALESCE(m.snapshot_id, pm.snapshot_id)
        ORDER BY 1, 2, 3, 4, 5, 6, 7
    """,
    "approved_alias": """
        SELECT s.project_code, s.revision_label, s.network_name, s.snapshot_label,
               COALESCE(m.message_key, pm.message_key), g.signal_key,
               a.alias_text, a.alias_kind,
               t.project_code, t.revision_label, t.network_name, t.snapshot_label,
               a.approval_reference, a.approved_at
        FROM mvp.approved_alias a
        JOIN mvp.approved_entity e ON e.approved_entity_id = a.approved_entity_id
        LEFT JOIN mvp.message_occurrence m ON m.message_occurrence_id = e.message_occurrence_id
        LEFT JOIN mvp.signal_occurrence g ON g.signal_occurrence_id = e.signal_occurrence_id
        LEFT JOIN mvp.message_occurrence pm ON pm.message_occurrence_id = g.message_occurrence_id
        JOIN mvp.source_snapshot s ON s.snapshot_id = COALESCE(m.snapshot_id, pm.snapshot_id)
        JOIN mvp.source_snapshot t ON t.snapshot_id = a.asserting_snapshot_id
        ORDER BY 1, 2, 3, 4, 5, 6, 7
    """,
    "entity_match_term": """
        SELECT s.project_code, s.revision_label, s.network_name, s.snapshot_label,
               COALESCE(m.message_key, pm.message_key), g.signal_key,
               x.match_kind, x.match_text, x.match_tokens, a.alias_text
        FROM mvp.entity_match_term x
        JOIN mvp.approved_entity e ON e.approved_entity_id = x.approved_entity_id
        LEFT JOIN mvp.approved_alias a ON a.approved_alias_id = x.approved_alias_id
        LEFT JOIN mvp.message_occurrence m ON m.message_occurrence_id = e.message_occurrence_id
        LEFT JOIN mvp.signal_occurrence g ON g.signal_occurrence_id = e.signal_occurrence_id
        LEFT JOIN mvp.message_occurrence pm ON pm.message_occurrence_id = g.message_occurrence_id
        JOIN mvp.source_snapshot s ON s.snapshot_id = COALESCE(m.snapshot_id, pm.snapshot_id)
        ORDER BY 1, 2, 3, 4, 5, 6, 7, 8
    """,
    # `built_at` is provisioning provenance and differs between two runs, as
    # Section 6 says it may; only the digest is contract-visible.
    "entity_registry_state": "SELECT registry_digest FROM mvp.entity_registry_state",
}


def contract_visible(database: str) -> dict[str, list[tuple]]:
    """Read every table's contract-visible content, in template order."""
    contents = {}
    with connect(database) as connection, connection.cursor() as cursor:
        for table, query in CONTRACT_VISIBLE.items():
            cursor.execute(query)
            contents[table] = cursor.fetchall()
    return contents
