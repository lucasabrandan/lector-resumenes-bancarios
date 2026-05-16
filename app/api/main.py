"""
Entry point de la aplicación FastAPI.

Por ahora es un "hola mundo" mínimo solo para verificar el setup.
A medida que avancemos, vamos a registrar acá los routers de:
  - app.api.routes.views (HTML server-rendered)
  - app.api.routes.api   (JSON REST)
"""

from fastapi import FastAPI

app = FastAPI(
    title="Lector de Resúmenes Bancarios",
    description="Procesador de extractos bancarios argentinos para ARCA.",
    version="0.1.0",
)


@app.get("/")
async def root() -> dict[str, str]:
    """Endpoint de salud — confirma que la app arrancó."""
    return {
        "status": "ok",
        "app": "Lector de Resúmenes Bancarios",
        "version": "0.1.0",
        "docs": "/docs",
    }


@app.get("/health")
async def health() -> dict[str, str]:
    """Endpoint para monitoring."""
    return {"status": "healthy"}
