"""
Entry point de la aplicación FastAPI.

Registra las rutas HTML (Jinja + HTMX) y crea las tablas al arrancar.
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.db.base import crear_tablas


@asynccontextmanager
async def lifespan(app: FastAPI):
    crear_tablas()
    yield


app = FastAPI(
    title="Lector de Resúmenes Bancarios",
    description="Procesador de extractos bancarios argentinos para ARCA.",
    version="0.1.0",
    lifespan=lifespan,
)

# Archivos estáticos (CSS, JS)
_STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
_STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

# Rutas HTML
from app.api.routes.views import router as views_router
app.include_router(views_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "healthy"}
