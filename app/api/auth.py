"""
Autenticación con cookie firmada y usuarios en base de datos.
"""

import os

from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from fastapi import Depends, Request
from fastapi.responses import RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware
from sqlalchemy.orm import Session

from app.db.base import get_db, SessionLocal
from app.db.models import UsuarioDB
from app.services.usuarios import obtener_por_username

SECRET_KEY = os.environ.get("SECRET_KEY", "change-me")

COOKIE_NAME = "session"
MAX_AGE = 60 * 60 * 24 * 7  # 7 dias

_serializer = URLSafeTimedSerializer(SECRET_KEY)

RUTAS_PUBLICAS = {"/login", "/health"}

# Mapa ruta -> permiso requerido
PERMISOS_RUTA: dict[str, str] = {
    "/": "dashboard",
    "/upload": "upload",
    "/upload/eliminar": "upload",
    "/movimientos": "movimientos",
    "/reporte": "reporte",
    "/reporte/descargar": "reporte",
    "/percepciones": "percepciones",
    "/percepciones/descargar": "percepciones",
    "/conceptos": "movimientos",
    "/conceptos/descargar": "movimientos",
    "/sircreb": "sircreb",
    "/sircreb/descargar": "sircreb",
    "/monotributo": "monotributo",
    "/usuarios": "usuarios",
}

# Prefijos de ruta -> permiso (para rutas dinamicas como /usuarios/1/editar)
PERMISOS_PREFIJO: dict[str, str] = {
    "/monotributo": "monotributo",
    "/sircreb": "sircreb",
    "/usuarios": "usuarios",
}


def crear_cookie(username: str) -> str:
    return _serializer.dumps(username)


def leer_cookie(token: str) -> str | None:
    try:
        return _serializer.loads(token, max_age=MAX_AGE)
    except (BadSignature, SignatureExpired):
        return None


def obtener_usuario_actual(request: Request, db: Session = Depends(get_db)) -> UsuarioDB | None:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    username = leer_cookie(token)
    if not username:
        return None
    return obtener_por_username(username, db)


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Permitir rutas publicas y archivos estaticos
        if path in RUTAS_PUBLICAS or path.startswith("/static"):
            return await call_next(request)

        token = request.cookies.get(COOKIE_NAME)
        username = leer_cookie(token) if token else None

        if not username:
            return RedirectResponse("/login", status_code=303)

        # Verificar que el usuario existe y esta activo
        db = SessionLocal()
        try:
            usuario = obtener_por_username(username, db)
            if not usuario or not usuario.activo:
                response = RedirectResponse("/login", status_code=303)
                response.delete_cookie(COOKIE_NAME)
                return response

            # Verificar permiso para la ruta (exacta o por prefijo)
            permiso_requerido = PERMISOS_RUTA.get(path)
            if not permiso_requerido:
                for prefijo, perm in PERMISOS_PREFIJO.items():
                    if path.startswith(prefijo):
                        permiso_requerido = perm
                        break
            if permiso_requerido and not usuario.tiene_permiso(permiso_requerido):
                return RedirectResponse("/", status_code=303)

            # Guardar datos del usuario en request.state
            request.state.usuario = usuario
        finally:
            db.close()

        return await call_next(request)
