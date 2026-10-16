
"""Aplicación Archivo TIC IA: modo local y autenticación web."""

import hmac
import json
import logging
import os
import secrets

from pathlib import Path
from ipaddress import ip_address

from cryptography.fernet import InvalidToken
from dotenv import load_dotenv

from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2 import id_token

from app.core.config import settings
from app.models.documento import AskRequest, AskResponse
from app.services.sync_service import SyncService
from app.services.agent_service import AgentService
from app.services.oauth_web_service import create_web_flow
from app.services.oauth_token_store import (
    get_cipher,
    save_google_credentials,
)


# ---------------------------------------------------------
# CONFIGURACIÓN GENERAL
# ---------------------------------------------------------

load_dotenv()

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[1]

app = FastAPI(
    title="Archivo TIC IA",
    version="1.1.0"
)

app.mount(
    "/assets",
    StaticFiles(directory=ROOT / "assets"),
    name="assets"
)

STATE_COOKIE = "__Host-tic_oauth_state"
SESSION_COOKIE = "__Host-tic_session"

STATE_TTL = 600
SESSION_TTL = 8 * 60 * 60


# ---------------------------------------------------------
# FUNCIONES DE SEGURIDAD
# ---------------------------------------------------------

def is_vercel():
    """Detecta si la aplicación se ejecuta en Vercel."""
    return os.getenv("VERCEL") == "1"


def allowed_email():
    """Obtiene la cuenta de Google autorizada."""

    email = os.getenv(
        "GOOGLE_ALLOWED_EMAIL", ""
    ).strip().lower()

    if not email:
        raise HTTPException(
            status_code=503,
            detail="Falta configurar GOOGLE_ALLOWED_EMAIL"
        )

    return email


def require_web_login(request: Request):
    """
    Protege las API cuando se ejecutan en Vercel.

    En localhost mantiene el funcionamiento
    original de la práctica académica.
    """

    if not is_vercel():
        return

    email = allowed_email()

    if not os.getenv("OAUTH_TOKEN_ENCRYPTION_KEY"):
        raise HTTPException(
            status_code=503,
            detail="Autenticación web no configurada"
        )

    session = request.cookies.get(SESSION_COOKIE)

    if not session:
        raise HTTPException(
            status_code=401,
            detail="Debes iniciar sesión con Google"
        )

    try:
        payload = json.loads(
            get_cipher().decrypt(
                session.encode("ascii"),
                ttl=SESSION_TTL
            ).decode("utf-8")
        )

        if payload.get("email") != email:
            raise HTTPException(
                status_code=401,
                detail="Sesión no autorizada"
            )

    except (
        InvalidToken,
        ValueError,
        UnicodeError,
        TypeError,
    ):
        raise HTTPException(
            status_code=401,
            detail="Sesión inválida o vencida"
        )


def local_only(request: Request):
    """
    Permite la sincronización administrativa
    únicamente desde localhost.
    """

    # Bloquear la sincronización en Vercel
    if is_vercel():
        raise HTTPException(
            status_code=403,
            detail=(
                "La sincronización administrativa "
                "no está disponible en Vercel"
            )
        )

    host = request.client.host if request.client else ""

    try:
        if not ip_address(host).is_loopback:
            raise ValueError()

    except ValueError:
        raise HTTPException(
            status_code=403,
            detail="Sincronización disponible solo desde localhost"
        )

    key = settings.local_admin_key

    if key and request.headers.get("X-Admin-Key") != key:
        raise HTTPException(
            status_code=401,
            detail="Clave administrativa incorrecta"
        )


# ---------------------------------------------------------
# INTERFAZ PRINCIPAL
# ---------------------------------------------------------

@app.get("/")
def index():
    """Muestra la interfaz web Archivo TIC IA."""

    return FileResponse(ROOT / "index.html")


# ---------------------------------------------------------
# GOOGLE OAUTH WEB - INICIO DE SESIÓN
# ---------------------------------------------------------

@app.get("/auth/google/login")
def google_login():
    """
    Inicia el proceso de autorización OAuth
    utilizando la cuenta de Google permitida.
    """

    if not is_vercel():
        raise HTTPException(
            status_code=403,
            detail="La autenticación web está reservada para Vercel"
        )

    allowed_email()

    try:
        cipher = get_cipher()

        # Estado aleatorio para prevenir CSRF
        state = secrets.token_urlsafe(32)

        flow = create_web_flow(state=state)

        # Generar la URL de autorización de Google
        authorization_url, _ = flow.authorization_url(
            access_type="offline",
            prompt="consent"
        )

        # Conservar el estado y verificador PKCE
        payload = {
            "state": state,
            "code_verifier": flow.code_verifier
        }

        encrypted = cipher.encrypt(
            json.dumps(payload).encode("utf-8")
        ).decode("ascii")

    except (RuntimeError, ValueError):
        raise HTTPException(
            status_code=503,
            detail="Configuración OAuth web incompleta"
        )

    response = RedirectResponse(
        url=authorization_url,
        status_code=302
    )

    # Cookie temporal y protegida
    response.set_cookie(
        key=STATE_COOKIE,
        value=encrypted,
        max_age=STATE_TTL,
        secure=True,
        httponly=True,
        samesite="lax",
        path="/"
    )

    return response


# ---------------------------------------------------------
# GOOGLE OAUTH WEB - CALLBACK
# ---------------------------------------------------------

@app.get("/auth/google/callback")
def google_callback(request: Request):
    """
    Recibe el código de Google, valida la identidad
    y almacena las credenciales cifradas en Neon.
    """

    if not is_vercel():
        raise HTTPException(
            status_code=403,
            detail="Callback web no disponible en localhost"
        )

    # Comprobar si Google rechazó la autorización
    if request.query_params.get("error"):
        raise HTTPException(
            status_code=400,
            detail="Google no concedió la autorización"
        )

    encrypted_state = request.cookies.get(STATE_COOKIE)
    received_state = request.query_params.get("state")

    if not encrypted_state or not received_state:
        raise HTTPException(
            status_code=400,
            detail="Falta el estado de autenticación"
        )

    # -----------------------------------------------------
    # VALIDAR ESTADO OAUTH Y RECUPERAR PKCE
    # -----------------------------------------------------

    try:
        payload = json.loads(
            get_cipher().decrypt(
                encrypted_state.encode("ascii"),
                ttl=STATE_TTL
            ).decode("utf-8")
        )

        expected_state = payload["state"]
        code_verifier = payload["code_verifier"]

        if not hmac.compare_digest(
            received_state,
            expected_state
        ):
            raise ValueError("Estado OAuth incorrecto")

    except (
        InvalidToken,
        ValueError,
        KeyError,
        TypeError,
        UnicodeError,
    ):
        raise HTTPException(
            status_code=400,
            detail="Estado OAuth inválido o vencido"
        )

    # -----------------------------------------------------
    # INTERCAMBIAR CÓDIGO Y VALIDAR IDENTIDAD
    # -----------------------------------------------------

    try:
        flow = create_web_flow(
            state=expected_state,
            code_verifier=code_verifier
        )

        # Obtener directamente el código enviado por Google
        authorization_code = request.query_params.get("code")

        if not authorization_code:
            raise ValueError(
                "Google no devolvió un código de autorización"
            )

        # Intercambiar el código por credenciales OAuth
        flow.fetch_token(code=authorization_code)

        credentials = flow.credentials

        # Verificar el token de identidad de Google
        if not credentials.id_token:
            raise ValueError(
                "Google no devolvió un token de identidad"
            )

        claims = id_token.verify_oauth2_token(
            credentials.id_token,
            GoogleRequest(),
            os.getenv("GOOGLE_WEB_CLIENT_ID")
        )

    except Exception as exc:
        # Registrar solamente el tipo de error,
        # sin publicar tokens ni códigos de Google
        logger.error(
            "Error al validar OAuth: %s",
            type(exc).__name__
        )

        raise HTTPException(
            status_code=400,
            detail="No fue posible validar la autorización de Google"
        )

    # -----------------------------------------------------
    # VERIFICAR QUE LA CUENTA ESTÉ AUTORIZADA
    # -----------------------------------------------------

    email = str(
        claims.get("email", "")
    ).strip().lower()

    verified = claims.get("email_verified") is True

    if not verified or email != allowed_email():
        raise HTTPException(
            status_code=403,
            detail="La cuenta de Google no está autorizada"
        )

    # -----------------------------------------------------
    # GUARDAR CREDENCIALES CIFRADAS EN NEON
    # -----------------------------------------------------

    try:
        save_google_credentials(credentials)

        # Crear una sesión cifrada del usuario autorizado
        session_data = json.dumps(
            {"email": email}
        ).encode("utf-8")

        session_value = get_cipher().encrypt(
            session_data
        ).decode("ascii")

    except Exception as exc:
        logger.error(
            "Error al guardar autorización OAuth: %s",
            type(exc).__name__
        )

        raise HTTPException(
            status_code=503,
            detail="No se pudo guardar la autorización en Neon"
        )

    # -----------------------------------------------------
    # CREAR SESIÓN Y REGRESAR A LA APLICACIÓN
    # -----------------------------------------------------

    response = RedirectResponse(
        url="/",
        status_code=303
    )

    # Eliminar el estado OAuth temporal
    response.delete_cookie(
        key=STATE_COOKIE,
        path="/",
        secure=True,
        httponly=True,
        samesite="lax"
    )

    # Crear cookie de sesión protegida
    response.set_cookie(
        key=SESSION_COOKIE,
        value=session_value,
        max_age=SESSION_TTL,
        secure=True,
        httponly=True,
        samesite="lax",
        path="/"
    )

    return response


# ---------------------------------------------------------
# GOOGLE OAUTH WEB - CERRAR SESIÓN
# ---------------------------------------------------------

@app.get("/auth/google/logout")
def google_logout():
    """Cierra la sesión web del navegador."""

    response = RedirectResponse(
        url="/",
        status_code=303
    )

    response.delete_cookie(
        key=SESSION_COOKIE,
        path="/",
        secure=True,
        httponly=True,
        samesite="lax"
    )

    return response


# ---------------------------------------------------------
# API - ESTADO DE LA APLICACIÓN
# ---------------------------------------------------------

@app.get("/api/health")
def health():
    """Comprueba el estado básico de la aplicación."""

    return {
        "status": "ok",
        "configured": bool(
            settings.openai_api_key
            and settings.drive_folder_id
        )
    }


# ---------------------------------------------------------
# API - DOCUMENTOS INDEXADOS
# ---------------------------------------------------------

@app.get(
    "/api/documents",
    dependencies=[Depends(require_web_login)]
)
def documents():
    """Devuelve los documentos registrados."""

    doc = SyncService.load_manifest()

    return {
        "documents": list(
            doc.get("documents", {}).values()
        ),
        "indexed": len(
            doc.get("documents", {})
        ),
        "vector_store_configured": bool(
            settings.vector_store_id
            or doc.get("vector_store_id")
        )
    }


# ---------------------------------------------------------
# API - CONSULTAR AL AGENTE CON IA
# ---------------------------------------------------------

@app.post(
    "/api/ask",
    response_model=AskResponse,
    dependencies=[Depends(require_web_login)]
)
def ask(payload: AskRequest):
    """Realiza preguntas al agente documental."""

    try:
        if not settings.openai_api_key:
            raise ValueError("Falta OPENAI_API_KEY")

        return AgentService().ask(
            payload.question,
            payload.use_search
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc)
        )

    except Exception:
        raise HTTPException(
            status_code=502,
            detail="Error al consultar OpenAI"
        )


# ---------------------------------------------------------
# API - SINCRONIZACIÓN DE GOOGLE DRIVE
# ---------------------------------------------------------

@app.post(
    "/api/sync",
    dependencies=[Depends(local_only)]
)
def sync():
    """
    Sincroniza documentos con Google Drive.

    Por seguridad, esta operación administrativa
    permanece disponible únicamente en localhost.
    """

    try:
        if not settings.openai_api_key:
            raise ValueError("Falta OPENAI_API_KEY")

        return SyncService().sync()

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc)
        )

    except Exception:
        raise HTTPException(
            status_code=502,
            detail="Sincronización fallida. Revisa los registros."
        )
