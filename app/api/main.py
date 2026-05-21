"""
Entry point de la aplicación FastAPI.

Registra las rutas HTML (Jinja + HTMX) y crea las tablas al arrancar.
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Logging: archivo + consola
_LOG_DIR = Path(__file__).resolve().parent.parent.parent / "logs"
_LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(_LOG_DIR / "app.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.db.base import crear_tablas, SessionLocal
from app.api.auth import AuthMiddleware, crear_cookie, COOKIE_NAME
from app.services.usuarios import autenticar, crear_admin_si_no_existe


@asynccontextmanager
async def lifespan(app: FastAPI):
    crear_tablas()
    db = SessionLocal()
    try:
        crear_admin_si_no_existe(db)
    finally:
        db.close()
    yield


app = FastAPI(
    title="Lector de Resúmenes Bancarios",
    description="Procesador de extractos bancarios argentinos para ARCA.",
    version="0.1.0",
    lifespan=lifespan,
)

# Middleware de autenticacion
app.add_middleware(AuthMiddleware)

# Archivos estáticos (CSS, JS)
_STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
_STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

# Templates para login
_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
_login_templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))


# --------------------------------------------------------------------------
# Login / Logout
# --------------------------------------------------------------------------

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return _login_templates.TemplateResponse("login.html", {"request": request})


@app.post("/login", response_class=HTMLResponse)
async def login_submit(request: Request):
    form = await request.form()
    username = str(form.get("username", ""))
    password = str(form.get("password", ""))

    db = SessionLocal()
    try:
        usuario = autenticar(username, password, db)
    finally:
        db.close()

    if usuario:
        response = RedirectResponse("/", status_code=303)
        response.set_cookie(
            COOKIE_NAME, crear_cookie(usuario.username),
            httponly=True, max_age=60 * 60 * 24 * 7,
        )
        return response

    return _login_templates.TemplateResponse("login.html", {
        "request": request,
        "error": "Usuario o contrasena incorrectos.",
    })


@app.get("/logout")
async def logout():
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(COOKIE_NAME)
    return response


# Rutas HTML
from app.api.routes.views import router as views_router
app.include_router(views_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "healthy"}
