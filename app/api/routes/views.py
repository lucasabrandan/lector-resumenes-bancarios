"""
Rutas HTML server-rendered con Jinja2 + HTMX.

Estas son las páginas que ve la contadora en el navegador.
"""

from pathlib import Path

from fastapi import APIRouter, Depends, Request, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.services.movimientos import (
    procesar_pdf,
    listar_movimientos,
    contar_movimientos,
    obtener_cuentas,
)
from app.reports.ley_25413 import generar_reporte_ley_25413, resumen_general

router = APIRouter()

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))


# --------------------------------------------------------------------------
# Dashboard (página principal)
# --------------------------------------------------------------------------

@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, db: Session = Depends(get_db)):
    total = contar_movimientos(db)
    context = {"request": request, "total_movimientos": total}

    if total > 0:
        context["resumen"] = resumen_general(db)
        context["reporte_ley"] = generar_reporte_ley_25413(db)

    return templates.TemplateResponse("dashboard.html", context)


# --------------------------------------------------------------------------
# Upload de PDF
# --------------------------------------------------------------------------

@router.get("/upload", response_class=HTMLResponse)
async def upload_page(request: Request):
    return templates.TemplateResponse("upload.html", {"request": request})


@router.post("/upload")
async def upload_pdf(
    request: Request,
    archivo: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    if not archivo.filename or not archivo.filename.lower().endswith(".pdf"):
        return templates.TemplateResponse("upload.html", {
            "request": request,
            "error": "Solo se aceptan archivos PDF.",
        })

    # Guardar temporalmente
    tmp_dir = Path("data/uploads")
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = tmp_dir / archivo.filename

    contenido = await archivo.read()
    tmp_path.write_bytes(contenido)

    try:
        cantidad = procesar_pdf(tmp_path, db)
        return templates.TemplateResponse("upload.html", {
            "request": request,
            "exito": f"Se procesaron {cantidad:,} movimientos del archivo '{archivo.filename}'.",
        })
    except Exception as e:
        return templates.TemplateResponse("upload.html", {
            "request": request,
            "error": f"Error al procesar el PDF: {e}",
        })


# --------------------------------------------------------------------------
# Lista de movimientos
# --------------------------------------------------------------------------

@router.get("/movimientos", response_class=HTMLResponse)
async def movimientos_page(
    request: Request,
    tipo: str | None = None,
    pagina: int = 1,
    db: Session = Depends(get_db),
):
    por_pagina = 50
    offset = (pagina - 1) * por_pagina

    movimientos = listar_movimientos(db, tipo=tipo, limite=por_pagina, offset=offset)
    total = contar_movimientos(db)
    total_paginas = (total + por_pagina - 1) // por_pagina

    # Tipos disponibles para el filtro
    from app.domain.models import TipoMovimiento
    tipos = [t.value for t in TipoMovimiento]

    return templates.TemplateResponse("movimientos.html", {
        "request": request,
        "movimientos": movimientos,
        "tipo_filtro": tipo,
        "tipos": tipos,
        "pagina": pagina,
        "total_paginas": total_paginas,
        "total": total,
    })


# --------------------------------------------------------------------------
# Reporte Ley 25.413
# --------------------------------------------------------------------------

@router.get("/reporte", response_class=HTMLResponse)
async def reporte_page(request: Request, db: Session = Depends(get_db)):
    reporte = generar_reporte_ley_25413(db)
    return templates.TemplateResponse("reporte.html", {
        "request": request,
        "reporte": reporte,
    })
