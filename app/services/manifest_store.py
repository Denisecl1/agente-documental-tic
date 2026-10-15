
"""Almacenamiento del manifiesto documental en PostgreSQL."""

import os
import psycopg
from psycopg.types.json import Jsonb


def get_connection():
    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        raise RuntimeError(
            "No se configuró DATABASE_URL para PostgreSQL."
        )

    return psycopg.connect(database_url, connect_timeout=10)


def init_database(conn):
    """Crea la tabla del manifiesto si todavía no existe."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS agent_manifest (
            id TEXT PRIMARY KEY,
            payload JSONB NOT NULL,
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)


def load_manifest():
    """Recupera el manifiesto almacenado en Neon."""
    with get_connection() as conn:
        init_database(conn)

        row = conn.execute(
            "SELECT payload FROM agent_manifest WHERE id = %s",
            ("default",)
        ).fetchone()

        if row:
            return row[0]

        return {
            "vector_store_id": "",
            "documents": {}
        }


def save_manifest(data):
    """Guarda o actualiza el manifiesto en Neon."""
    with get_connection() as conn:
        init_database(conn)

        conn.execute("""
            INSERT INTO agent_manifest (id, payload, updated_at)
            VALUES (%s, %s, NOW())
            ON CONFLICT (id)
            DO UPDATE SET
                payload = EXCLUDED.payload,
                updated_at = NOW()
        """, ("default", Jsonb(data)))
