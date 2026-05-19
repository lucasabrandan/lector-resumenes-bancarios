"""
Rutas HTML server-rendered con Jinja2 + HTMX.

Estas son las páginas que ve la contadora en el navegador.
"""

import json
from pathlib import Path

from markupsafe import Markup

from fastapi import APIRouter, Depends, Request, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.services.movimientos import (
    procesar_pdf,
    listar_movimientos,
    contar_movimientos,
    contar_movimientos_filtrados,
    obtener_cuentas,
    distribucion_por_tipo,
    distribucion_mensual,
)
from app.reports.ley_25413 import generar_reporte_ley_25413, resumen_general, exportar_reporte_xlsx

router = APIRouter()

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))


# --------------------------------------------------------------------------
# Dashboard (página principal)
# --------------------------------------------------------------------------

@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, db: Session = Depends(get_db)):
    total = contar_movimientos(db)
    context = {
        "request": request,
        "total_movimientos": total,
        "distribucion": [],
    }

    if total > 0:
        context["resumen"] = resumen_general(db)
        context["reporte_ley"] = generar_reporte_ley_25413(db)
        context["distribucion"] = distribucion_por_tipo(db)
        context["dist_mensual_json"] = Markup(json.dumps(distribucion_mensual(db)))

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
    buscar: str | None = None,
    fecha_desde: str | None = None,
    fecha_hasta: str | None = None,
    pagina: int = 1,
    db: Session = Depends(get_db),
):
    from datetime import date as date_type
    from app.domain.models import TipoMovimiento

    por_pagina = 50
    offset = (pagina - 1) * por_pagina

    # Parsear fechas
    fd = date_type.fromisoformat(fecha_desde) if fecha_desde else None
    fh = date_type.fromisoformat(fecha_hasta) if fecha_hasta else None

    movimientos = listar_movimientos(
        db, tipo=tipo, buscar=buscar, fecha_desde=fd, fecha_hasta=fh,
        limite=por_pagina, offset=offset,
    )
    total = contar_movimientos_filtrados(db, tipo=tipo, buscar=buscar, fecha_desde=fd, fecha_hasta=fh)
    total_paginas = max(1, (total + por_pagina - 1) // por_pagina)

    tipos = [t.value for t in TipoMovimiento]

    return templates.TemplateResponse("movimientos.html", {
        "request": request,
        "movimientos": movimientos,
        "tipo_filtro": tipo,
        "buscar": buscar,
        "fecha_desde": fecha_desde,
        "fecha_hasta": fecha_hasta,
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


@router.get("/reporte/descargar")
async def descargar_reporte(db: Session = Depends(get_db)):
    reporte = generar_reporte_ley_25413(db)
    xlsx = exportar_reporte_xlsx(reporte)
    return StreamingResponse(
        xlsx,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=reporte_ley_25413.xlsx"},
    )
