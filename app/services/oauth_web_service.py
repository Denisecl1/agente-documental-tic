
"""Configuración OAuth 2.0 web para Google Drive."""

import os

from google_auth_oauthlib.flow import Flow

SCOPES = [
    "openid",
    "email",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/drive.readonly",
]


def create_web_flow(state=None, code_verifier=None):
    """Prepara el flujo OAuth web con credenciales de entorno."""

    client_id = os.getenv("GOOGLE_WEB_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_WEB_CLIENT_SECRET")
    redirect_uri = os.getenv("GOOGLE_WEB_REDIRECT_URI")

    if not all([client_id, client_secret, redirect_uri]):
        raise RuntimeError(
            "Faltan variables de configuración de OAuth web."
        )

    if not redirect_uri.startswith("https://"):
        raise ValueError(
            "La URI de redireccionamiento debe utilizar HTTPS."
        )

    client_config = {
        "web": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [redirect_uri],
        }
    }

    return Flow.from_client_config(
        client_config,
        scopes=SCOPES,
        state=state,
        redirect_uri=redirect_uri,
        code_verifier=code_verifier,
        autogenerate_code_verifier=code_verifier is None,
    )
