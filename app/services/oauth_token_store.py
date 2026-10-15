
"""Almacenamiento cifrado de credenciales OAuth en Neon."""

import json
import os

from cryptography.fernet import Fernet, InvalidToken
from google.oauth2.credentials import Credentials

from app.services.manifest_store import get_connection


TOKEN_ID = "primary"


def get_cipher():
    """Obtiene la clave de cifrado desde el entorno."""

    key = os.getenv("OAUTH_TOKEN_ENCRYPTION_KEY")

    if not key:
        raise RuntimeError(
            "Falta OAUTH_TOKEN_ENCRYPTION_KEY"
        )

    try:
        return Fernet(key.encode("ascii"))
    except (ValueError, UnicodeEncodeError) as exc:
        raise RuntimeError(
            "La clave de cifrado OAuth no es válida"
        ) from exc


def init_token_table(conn):
    """Crea la tabla de tokens si no existe."""

    conn.execute("""
        CREATE TABLE IF NOT EXISTS oauth_tokens (
            id TEXT PRIMARY KEY,
            encrypted_token BYTEA NOT NULL,
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)


def save_google_credentials(credentials: Credentials):
    """Cifra y guarda las credenciales de Google."""

    payload = credentials.to_json().encode("utf-8")

    encrypted = get_cipher().encrypt(payload)

    with get_connection() as conn:
        init_token_table(conn)

        conn.execute("""
            INSERT INTO oauth_tokens
                (id, encrypted_token, updated_at)
            VALUES (%s, %s, NOW())
            ON CONFLICT (id)
            DO UPDATE SET
                encrypted_token = EXCLUDED.encrypted_token,
                updated_at = NOW()
        """, (TOKEN_ID, encrypted))


def load_google_credentials():
    """Recupera y descifra las credenciales guardadas."""

    with get_connection() as conn:
        init_token_table(conn)

        row = conn.execute(
            """
            SELECT encrypted_token
            FROM oauth_tokens
            WHERE id = %s
            """,
            (TOKEN_ID,)
        ).fetchone()

    if row is None:
        return None

    try:
        decrypted = get_cipher().decrypt(row[0])
        data = json.loads(decrypted.decode("utf-8"))

        return Credentials.from_authorized_user_info(data)

    except (InvalidToken, ValueError, KeyError) as exc:
        raise RuntimeError(
            "No se pudieron recuperar las credenciales OAuth"
        ) from exc
