"""
Rutas HTML server-rendered con Jinja2 + HTMX.

Estas son las páginas que ve la contadora en el navegador.
"""

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.db.models import TODOS_LOS_PERMISOS
from app.services.movimientos import (
    procesar_pdf,
    listar_movimientos,
    contar_movimientos,
    contar_movimientos_filtrados,
    obtener_cuentas,
    archivo_ya_cargado,
    eliminar_por_archivo,
    limpiar_todos_los_datos,
    listar_archivos_cargados,
    exportar_movimientos_xlsx,
    resumen_mercadopago,
)
from app.services.usuarios import (
    listar_usuarios,
    crear_usuario,
    obtener_por_id,
    obtener_por_username,
    actualizar_usuario,
    eliminar_usuario,
)
from app.services.clientes import (
    listar_clientes,
    listar_clientes_de_usuario,
    obtener_por_id as obtener_cliente_por_id,
    crear_cliente,
    actualizar_cliente,
    eliminar_cliente,
    asignar_usuarios,
    ids_clientes_de_usuario,
)
from app.reports.ley_25413 import generar_reporte_ley_25413, resumen_general, exportar_reporte_xlsx
from app.reports.percepciones import generar_reporte_percepciones, resumen_totales, exportar_percepciones_xlsx
from app.reports.conceptos_recurrentes import (
    generar_reporte_conceptos,
    exportar_conceptos_xlsx,
    periodo_label,
)
from app.services.monotributo import generar_panel_monotributo, CATEGORIAS_MONOTRIBUTO
from app.services.comprobantes import (
    guardar_comprobantes,
    archivo_comprobantes_ya_cargado,
    eliminar_comprobantes_por_archivo,
    listar_archivos_comprobantes,
)
from app.parsers.arca_comprobantes import parsear_archivo
from app.parsers.supervielle_pdf import ParserError, ErrorValidacionSaldo
from app.parsers.mercadopago_pdf import ParserMercadoPagoError, ErrorCuadreMercadoPago
from app.parsers.sircreb import parsear_sircreb
from app.services.sircreb import (
    guardar_percepciones_iibb,
    archivo_sircreb_ya_cargado,
    eliminar_sircreb_por_archivo,
    listar_archivos_sircreb,
    generar_reporte_sircreb,
    resumen_totales_sircreb,
    exportar_sircreb_xlsx,
)

router = APIRouter()
logger = logging.getLogger(__name__)

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))


def _fecha_ar(value) -> str:
    """Filtro Jinja2: convierte date/datetime a dd/mm/aaaa."""
    if value is None:
        return "-"
    if hasattr(value, "strftime"):
        return value.strftime("%d/%m/%Y")
    # Si es string ISO (yyyy-mm-dd), reformatear
    s = str(value)
    if len(s) == 10 and s[4] == "-":
        return f"{s[8:10]}/{s[5:7]}/{s[0:4]}"
    return s


templates.env.filters["fecha_ar"] = _fecha_ar


def _ctx(request: Request, **kwargs) -> dict:
    """Contexto base con datos del usuario logueado."""
    usuario = getattr(request.state, "usuario", None)
    return {"request": request, "usuario": usuario, **kwargs}


def _get_cliente_ids(request: Request, db: Session) -> list[int] | None:
    """IDs de clientes visibles para el usuario. None = admin, ve todo."""
    usuario = getattr(request.state, "usuario", None)
    if not usuario:
        return []
    return ids_clientes_de_usuario(usuario, db)


# --------------------------------------------------------------------------
# Dashboard (página principal)
# --------------------------------------------------------------------------

@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, db: Session = Depends(get_db)):
    cids = _get_cliente_ids(request, db)
    total = contar_movimientos(db, cliente_ids=cids)
    context = _ctx(request, total_movimientos=total)

    if total > 0:
        context["resumen"] = resumen_general(db, cliente_ids=cids)
        context["reporte_ley"] = generar_reporte_ley_25413(db, cliente_ids=cids)

    return templates.TemplateResponse("dashboard.html", context)


@router.post("/limpiar-datos")
async def limpiar_datos(request: Request, db: Session = Depends(get_db)):
    cids = _get_cliente_ids(request, db)
    resultado = limpiar_todos_los_datos(db, cliente_ids=cids)
    total = sum(resultado.values())
    partes = []
    if resultado["movimientos"]:
        partes.append(f"{resultado['movimientos']:,} movimientos")
    if resultado["comprobantes"]:
        partes.append(f"{resultado['comprobantes']:,} comprobantes")
    if resultado["percepciones_iibb"]:
        partes.append(f"{resultado['percepciones_iibb']:,} percepciones IIBB")
    if partes:
        msg = f"Se eliminaron {', '.join(partes)}."
    else:
        msg = "No habia datos para eliminar."
    context = _ctx(request, total_movimientos=0, limpiar_exito=msg)
    return templates.TemplateResponse("dashboard.html", context)


# --------------------------------------------------------------------------
# Detalle mensual para dashboard (JSON)
# --------------------------------------------------------------------------

@router.get("/api/dashboard/mes-detalle")
async def mes_detalle(request: Request, anio: int, mes: int, db: Session = Depends(get_db)):
    """Devuelve desglose de movimientos por tipo para un mes específico."""
    from sqlalchemy import func, extract
    from app.db.models import MovimientoDB
    from app.services.movimientos import _aplicar_filtro_clientes

    cids = _get_cliente_ids(request, db)
    query = (
        db.query(
            MovimientoDB.tipo,
            MovimientoDB.signo,
            func.sum(MovimientoDB.importe).label("total"),
            func.count(MovimientoDB.id).label("cantidad"),
        )
        .filter(
            extract("year", MovimientoDB.fecha) == anio,
            extract("month", MovimientoDB.fecha) == mes,
        )
        .group_by(MovimientoDB.tipo, MovimientoDB.signo)
        .order_by(func.sum(MovimientoDB.importe).desc())
    )
    query = _aplicar_filtro_clientes(query, cids)
    rows = query.all()

    datos = [
        {"tipo": r.tipo, "signo": r.signo, "total": float(r.total), "cantidad": r.cantidad}
        for r in rows
    ]
    return JSONResponse({"anio": anio, "mes": mes, "datos": datos})


# --------------------------------------------------------------------------
# Upload de PDF
# --------------------------------------------------------------------------

@router.get("/upload", response_class=HTMLResponse)
async def upload_page(request: Request, db: Session = Depends(get_db)):
    cids = _get_cliente_ids(request, db)
    usuario = getattr(request.state, "usuario", None)
    clientes_disponibles = listar_clientes_de_usuario(usuario, db) if usuario else []
    return templates.TemplateResponse("upload.html", _ctx(
        request,
        archivos=listar_archivos_cargados(db, cliente_ids=cids),
        clientes=clientes_disponibles,
    ))


@router.post("/upload")
async def upload_pdf(
    request: Request,
    db: Session = Depends(get_db),
):
    cids = _get_cliente_ids(request, db)
    usuario = getattr(request.state, "usuario", None)
    clientes_disponibles = listar_clientes_de_usuario(usuario, db) if usuario else []
    ctx = _ctx(request, archivos=listar_archivos_cargados(db, cliente_ids=cids), clientes=clientes_disponibles)

    # Leer form (multipart)
    form = await request.form()
    archivo = form.get("archivo")
    cliente_id_str = str(form.get("cliente_id", ""))
    cliente_id = int(cliente_id_str) if cliente_id_str else None

    if not archivo or not getattr(archivo, "filename", None) or not archivo.filename.lower().endswith(".pdf"):
        ctx["error"] = "Solo se aceptan archivos PDF."
        return templates.TemplateResponse("upload.html", ctx)

    if not cliente_id:
        ctx["error"] = "Debes seleccionar un cliente."
        return templates.TemplateResponse("upload.html", ctx)

    # Detectar duplicado
    existentes = archivo_ya_cargado(archivo.filename, db)
    if existentes > 0:
        ctx["error"] = (
            f"El archivo '{archivo.filename}' ya fue cargado "
            f"({existentes:,} movimientos). Eliminalo primero si queres reprocesarlo."
        )
        return templates.TemplateResponse("upload.html", ctx)

    # Guardar temporalmente
    tmp_dir = Path("data/uploads")
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = tmp_dir / archivo.filename

    contenido = await archivo.read()
    tmp_path.write_bytes(contenido)

    try:
        cantidad, resumen_mp = procesar_pdf(tmp_path, db, cliente_id=cliente_id)
        ctx["archivos"] = listar_archivos_cargados(db, cliente_ids=cids)
        cliente = obtener_cliente_por_id(cliente_id, db)
        nombre_cliente = cliente.nombre if cliente else "?"
        ctx["exito"] = f"Se procesaron {cantidad:,} movimientos del archivo '{archivo.filename}' para el cliente '{nombre_cliente}'."
        if resumen_mp:
            ctx["resumen_mp"] = resumen_mp
        return templates.TemplateResponse("upload.html", ctx)
    except ErrorCuadreMercadoPago as e:
        logger.error("Cuadre MercadoPago en '%s': %s", archivo.filename, e)
        ctx["error"] = (
            f"El archivo '{archivo.filename}' tiene una inconsistencia de saldo. "
            f"Los movimientos no cuadran con los totales del encabezado. "
            f"Diferencia: ${e.diferencia:,.2f}"
        )
        return templates.TemplateResponse("upload.html", ctx)
    except ErrorValidacionSaldo as e:
        logger.error("Inconsistencia de saldo en '%s': %s", archivo.filename, e)
        ctx["error"] = (
            f"El archivo '{archivo.filename}' tiene una inconsistencia interna: "
            f"un movimiento no cuadra con el saldo (pagina {e.movimiento.pagina}, "
            f"concepto '{e.movimiento.concepto}'). "
            f"Revisa que el PDF este completo y no tenga paginas faltantes."
        )
        return templates.TemplateResponse("upload.html", ctx)
    except ParserMercadoPagoError as e:
        logger.error("Error de parser MercadoPago en '%s': %s", archivo.filename, e)
        ctx["error"] = (
            f"Error al leer el PDF de MercadoPago '{archivo.filename}'. "
            f"Detalle: {e}"
        )
        return templates.TemplateResponse("upload.html", ctx)
    except ValueError as e:
        logger.warning("PDF no reconocido '%s': %s", archivo.filename, e)
        ctx["error"] = (
            f"No se pudo procesar '{archivo.filename}'. "
            f"Verifica que sea un extracto de Banco Supervielle o MercadoPago. "
            f"Detalle: {e}"
        )
        return templates.TemplateResponse("upload.html", ctx)
    except ParserError as e:
        logger.error("Error de parser en '%s': %s", archivo.filename, e)
        ctx["error"] = (
            f"Error al leer el PDF '{archivo.filename}'. "
            f"El archivo podria estar danado o tener un formato inesperado. "
            f"Detalle: {e}"
        )
        return templates.TemplateResponse("upload.html", ctx)
    except Exception as e:
        logger.exception("Error inesperado procesando '%s'", archivo.filename)
        ctx["error"] = (
            f"Error inesperado al procesar '{archivo.filename}'. "
            f"Si el problema persiste, contacta al administrador."
        )
        return templates.TemplateResponse("upload.html", ctx)


@router.post("/upload/eliminar")
async def eliminar_archivo(
    request: Request,
    db: Session = Depends(get_db),
):
    form = await request.form()
    nombre = form.get("archivo")
    if not nombre:
        return RedirectResponse("/upload", status_code=303)

    cids = _get_cliente_ids(request, db)
    usuario = getattr(request.state, "usuario", None)
    clientes_disponibles = listar_clientes_de_usuario(usuario, db) if usuario else []
    cantidad = eliminar_por_archivo(str(nombre), db)
    ctx = _ctx(
        request,
        archivos=listar_archivos_cargados(db, cliente_ids=cids),
        clientes=clientes_disponibles,
        exito=f"Se eliminaron {cantidad:,} movimientos del archivo '{nombre}'.",
    )
    return templates.TemplateResponse("upload.html", ctx)


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

    cids = _get_cliente_ids(request, db)
    movimientos = listar_movimientos(
        db, tipo=tipo, buscar=buscar, fecha_desde=fd, fecha_hasta=fh,
        limite=por_pagina, offset=offset, cliente_ids=cids,
    )
    total = contar_movimientos_filtrados(db, tipo=tipo, buscar=buscar, fecha_desde=fd, fecha_hasta=fh, cliente_ids=cids)
    total_paginas = max(1, (total + por_pagina - 1) // por_pagina)

    tipos = [t.value for t in TipoMovimiento]

    return templates.TemplateResponse("movimientos.html", _ctx(
        request,
        movimientos=movimientos,
        tipo_filtro=tipo,
        buscar=buscar,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
        tipos=tipos,
        pagina=pagina,
        total_paginas=total_paginas,
        total=total,
    ))


@router.get("/movimientos/descargar")
async def descargar_movimientos(
    request: Request,
    tipo: str | None = None,
    buscar: str | None = None,
    fecha_desde: str | None = None,
    fecha_hasta: str | None = None,
    db: Session = Depends(get_db),
):
    from datetime import date as date_type

    fd = date_type.fromisoformat(fecha_desde) if fecha_desde else None
    fh = date_type.fromisoformat(fecha_hasta) if fecha_hasta else None

    cids = _get_cliente_ids(request, db)
    movimientos = listar_movimientos(
        db, tipo=tipo, buscar=buscar, fecha_desde=fd, fecha_hasta=fh,
        limite=100_000, offset=0, cliente_ids=cids,
    )
    xlsx = exportar_movimientos_xlsx(movimientos)
    return StreamingResponse(
        xlsx,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=movimientos.xlsx"},
    )


# --------------------------------------------------------------------------
# Reporte Ley 25.413
# --------------------------------------------------------------------------

@router.get("/reporte", response_class=HTMLResponse)
async def reporte_page(request: Request, db: Session = Depends(get_db)):
    cids = _get_cliente_ids(request, db)
    reporte = generar_reporte_ley_25413(db, cliente_ids=cids)
    return templates.TemplateResponse("reporte.html", _ctx(request, reporte=reporte))


@router.get("/reporte/descargar")
async def descargar_reporte(request: Request, db: Session = Depends(get_db)):
    cids = _get_cliente_ids(request, db)
    reporte = generar_reporte_ley_25413(db, cliente_ids=cids)
    xlsx = exportar_reporte_xlsx(reporte)
    return StreamingResponse(
        xlsx,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=reporte_ley_25413.xlsx"},
    )


# --------------------------------------------------------------------------
# Percepciones y Retenciones
# --------------------------------------------------------------------------

@router.get("/percepciones", response_class=HTMLResponse)
async def percepciones_page(request: Request, db: Session = Depends(get_db)):
    cids = _get_cliente_ids(request, db)
    reporte = generar_reporte_percepciones(db, cliente_ids=cids)
    totales = resumen_totales(reporte)
    return templates.TemplateResponse("percepciones.html", _ctx(
        request, reporte=reporte, totales=totales))


@router.get("/percepciones/descargar")
async def descargar_percepciones(request: Request, db: Session = Depends(get_db)):
    cids = _get_cliente_ids(request, db)
    reporte = generar_reporte_percepciones(db, cliente_ids=cids)
    xlsx = exportar_percepciones_xlsx(reporte)
    return StreamingResponse(
        xlsx,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=percepciones_retenciones.xlsx"},
    )


# --------------------------------------------------------------------------
# SIRCREB — Percepciones/Retenciones IIBB
# --------------------------------------------------------------------------


def _sircreb_ctx(request: Request, db: Session, **kwargs) -> dict:
    """Contexto comun para la pagina SIRCREB."""
    cids = _get_cliente_ids(request, db)
    usuario = getattr(request.state, "usuario", None)
    clientes_disponibles = listar_clientes_de_usuario(usuario, db) if usuario else []
    archivos = listar_archivos_sircreb(db, cliente_ids=cids)
    reporte = generar_reporte_sircreb(db, cliente_ids=cids)
    totales = resumen_totales_sircreb(reporte) if reporte else None
    return _ctx(
        request,
        clientes=clientes_disponibles,
        archivos_sircreb=archivos,
        reporte=reporte,
        totales=totales,
        **kwargs,
    )


@router.get("/sircreb", response_class=HTMLResponse)
async def sircreb_page(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse("sircreb.html", _sircreb_ctx(request, db))


@router.post("/sircreb")
async def sircreb_upload(request: Request, db: Session = Depends(get_db)):
    """Sube un archivo SIRCREB (TXT)."""
    form = await request.form()
    archivo = form.get("archivo")
    cliente_id_str = str(form.get("cliente_id", ""))
    cliente_id = int(cliente_id_str) if cliente_id_str else None
    formato = str(form.get("formato", "")).strip() or None

    if not archivo or not getattr(archivo, "filename", None):
        return templates.TemplateResponse("sircreb.html",
            _sircreb_ctx(request, db, error="Selecciona un archivo."))

    ext = archivo.filename.lower().rsplit(".", 1)[-1] if "." in archivo.filename else ""
    if ext not in ("txt", "csv"):
        return templates.TemplateResponse("sircreb.html",
            _sircreb_ctx(request, db, error="Solo se aceptan archivos TXT o CSV."))

    if not cliente_id:
        return templates.TemplateResponse("sircreb.html",
            _sircreb_ctx(request, db, error="Selecciona un cliente."))

    existentes = archivo_sircreb_ya_cargado(archivo.filename, cliente_id, db)
    if existentes > 0:
        return templates.TemplateResponse("sircreb.html",
            _sircreb_ctx(request, db,
                error=f"El archivo '{archivo.filename}' ya fue cargado ({existentes} registros). Eliminalo primero si queres reprocesarlo."))

    contenido_bytes = await archivo.read()
    try:
        contenido = contenido_bytes.decode("latin-1")
    except UnicodeDecodeError:
        contenido = contenido_bytes.decode("utf-8", errors="replace")

    try:
        resultado = parsear_sircreb(contenido, archivo.filename, formato)
    except Exception as e:
        logger.exception("Error parseando SIRCREB '%s'", archivo.filename)
        return templates.TemplateResponse("sircreb.html",
            _sircreb_ctx(request, db,
                error=f"Error al leer '{archivo.filename}': {e}"))

    if resultado.errores and not resultado.percepciones:
        errores_txt = "; ".join(resultado.errores[:5])
        return templates.TemplateResponse("sircreb.html",
            _sircreb_ctx(request, db,
                error=f"No se pudieron parsear registros de '{archivo.filename}'. Errores: {errores_txt}"))

    if not resultado.percepciones:
        return templates.TemplateResponse("sircreb.html",
            _sircreb_ctx(request, db,
                error=f"No se encontraron percepciones/retenciones en '{archivo.filename}'. Verifica el formato del archivo."))

    cantidad = guardar_percepciones_iibb(resultado.percepciones, cliente_id, archivo.filename, db)
    msg = f"Se importaron {cantidad:,} registros desde '{archivo.filename}' (formato: {resultado.formato_detectado})."
    if resultado.errores:
        msg += f" {len(resultado.errores)} lineas con errores fueron ignoradas."

    return templates.TemplateResponse("sircreb.html",
        _sircreb_ctx(request, db, exito=msg))


@router.post("/sircreb/eliminar")
async def sircreb_eliminar(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    archivo = str(form.get("archivo", ""))
    cliente_id = int(str(form.get("cliente_id", "0")))

    if archivo and cliente_id:
        eliminados = eliminar_sircreb_por_archivo(archivo, cliente_id, db)
        return templates.TemplateResponse("sircreb.html",
            _sircreb_ctx(request, db,
                exito=f"Se eliminaron {eliminados} registros del archivo '{archivo}'."))
    return RedirectResponse("/sircreb", status_code=303)


@router.get("/sircreb/descargar")
async def sircreb_descargar(request: Request, db: Session = Depends(get_db)):
    cids = _get_cliente_ids(request, db)
    reporte = generar_reporte_sircreb(db, cliente_ids=cids)
    xlsx = exportar_sircreb_xlsx(reporte)
    return StreamingResponse(
        xlsx,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=sircreb_iibb.xlsx"},
    )


# --------------------------------------------------------------------------
# Conceptos Recurrentes
# --------------------------------------------------------------------------

@router.get("/conceptos", response_class=HTMLResponse)
async def conceptos_page(
    request: Request,
    tipo: str | None = None,
    signo: str | None = None,
    buscar: str | None = None,
    fecha_desde: str | None = None,
    fecha_hasta: str | None = None,
    db: Session = Depends(get_db),
):
    from datetime import date as date_type
    from app.domain.models import TipoMovimiento

    fd = date_type.fromisoformat(fecha_desde) if fecha_desde else None
    fh = date_type.fromisoformat(fecha_hasta) if fecha_hasta else None

    cids = _get_cliente_ids(request, db)
    reporte = generar_reporte_conceptos(
        db, cliente_ids=cids, tipo=tipo, signo=signo,
        buscar=buscar, fecha_desde=fd, fecha_hasta=fh,
    )

    # Construir query string para el link de descarga
    params = []
    if tipo:
        params.append(f"tipo={tipo}")
    if signo:
        params.append(f"signo={signo}")
    if buscar:
        params.append(f"buscar={buscar}")
    if fecha_desde:
        params.append(f"fecha_desde={fecha_desde}")
    if fecha_hasta:
        params.append(f"fecha_hasta={fecha_hasta}")
    query_string = "&".join(params)

    tipos = [t.value for t in TipoMovimiento]

    return templates.TemplateResponse("conceptos.html", _ctx(
        request,
        reporte=reporte,
        tipo_filtro=tipo,
        signo_filtro=signo,
        buscar=buscar,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
        tipos=tipos,
        query_string=query_string,
        periodo_label=periodo_label,
    ))


@router.get("/conceptos/descargar")
async def descargar_conceptos(
    request: Request,
    tipo: str | None = None,
    signo: str | None = None,
    buscar: str | None = None,
    fecha_desde: str | None = None,
    fecha_hasta: str | None = None,
    db: Session = Depends(get_db),
):
    from datetime import date as date_type

    fd = date_type.fromisoformat(fecha_desde) if fecha_desde else None
    fh = date_type.fromisoformat(fecha_hasta) if fecha_hasta else None

    cids = _get_cliente_ids(request, db)
    reporte = generar_reporte_conceptos(
        db, cliente_ids=cids, tipo=tipo, signo=signo,
        buscar=buscar, fecha_desde=fd, fecha_hasta=fh,
    )
    xlsx = exportar_conceptos_xlsx(reporte)
    return StreamingResponse(
        xlsx,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=conceptos_recurrentes.xlsx"},
    )


# --------------------------------------------------------------------------
# Panel MercadoPago
# --------------------------------------------------------------------------

@router.get("/mercadopago", response_class=HTMLResponse)
async def mercadopago_page(request: Request, db: Session = Depends(get_db)):
    cids = _get_cliente_ids(request, db)
    resumen = resumen_mercadopago(db, cliente_ids=cids)
    return templates.TemplateResponse("mercadopago.html", _ctx(request, resumen=resumen))


# --------------------------------------------------------------------------
# Panel de Monotributo
# --------------------------------------------------------------------------

@router.get("/monotributo", response_class=HTMLResponse)
async def monotributo_page(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse("monotributo.html",
        _monotributo_ctx(request, db))


def _monotributo_ctx(request: Request, db: Session, **kwargs) -> dict:
    """Contexto comun para renderizar la pagina de monotributo."""
    cids = _get_cliente_ids(request, db)
    panel = generar_panel_monotributo(db, cliente_ids=cids)
    usuario = getattr(request.state, "usuario", None)
    clientes_mono = listar_clientes_de_usuario(usuario, db) if usuario else []
    clientes_mono = [c for c in clientes_mono if c.categoria == "Monotributo"]
    archivos_comp = listar_archivos_comprobantes(db)
    return _ctx(
        request,
        panel=panel,
        categorias_monotributo=CATEGORIAS_MONOTRIBUTO,
        clientes_mono=clientes_mono,
        archivos_comprobantes=archivos_comp,
        **kwargs,
    )


@router.post("/monotributo/upload")
async def upload_comprobantes(request: Request, db: Session = Depends(get_db)):
    """Sube un archivo de Mis Comprobantes ARCA (CSV/Excel)."""
    form = await request.form()
    archivo = form.get("archivo")
    cliente_id_str = str(form.get("cliente_id", ""))
    cliente_id = int(cliente_id_str) if cliente_id_str else None

    if not archivo or not getattr(archivo, "filename", None):
        return templates.TemplateResponse("monotributo.html",
            _monotributo_ctx(request, db, error="Selecciona un archivo."))

    ext = archivo.filename.lower().rsplit(".", 1)[-1] if "." in archivo.filename else ""
    if ext not in ("csv", "xlsx", "xls"):
        return templates.TemplateResponse("monotributo.html",
            _monotributo_ctx(request, db, error="Solo se aceptan archivos CSV o Excel (.xlsx/.xls)."))

    if not cliente_id:
        return templates.TemplateResponse("monotributo.html",
            _monotributo_ctx(request, db, error="Selecciona un cliente."))

    # Detectar duplicado
    existentes = archivo_comprobantes_ya_cargado(archivo.filename, cliente_id, db)
    if existentes > 0:
        return templates.TemplateResponse("monotributo.html",
            _monotributo_ctx(request, db,
                error=f"El archivo '{archivo.filename}' ya fue cargado ({existentes} comprobantes). Eliminalo primero si queres reprocesarlo."))

    contenido = await archivo.read()
    try:
        comprobantes = parsear_archivo(archivo.filename, contenido)
    except ValueError as e:
        logger.warning("Comprobantes no reconocidos '%s': %s", archivo.filename, e)
        return templates.TemplateResponse("monotributo.html",
            _monotributo_ctx(request, db,
                error=f"No se pudo leer '{archivo.filename}'. Verifica que sea un archivo exportado desde ARCA (Mis Comprobantes Emitidos). Detalle: {e}"))
    except Exception as e:
        logger.exception("Error inesperado parseando comprobantes '%s'", archivo.filename)
        return templates.TemplateResponse("monotributo.html",
            _monotributo_ctx(request, db,
                error=f"Error inesperado al procesar '{archivo.filename}'. Si el problema persiste, contacta al administrador."))

    if not comprobantes:
        return templates.TemplateResponse("monotributo.html",
            _monotributo_ctx(request, db,
                error=f"No se encontraron comprobantes en '{archivo.filename}'. Verifica que el archivo tenga datos y que las columnas incluyan Fecha, Tipo e Imp. Total."))

    cantidad = guardar_comprobantes(comprobantes, cliente_id, archivo.filename, db)
    return templates.TemplateResponse("monotributo.html",
        _monotributo_ctx(request, db,
            exito=f"Se cargaron {cantidad} comprobantes desde '{archivo.filename}'."))


@router.post("/monotributo/eliminar-archivo")
async def eliminar_archivo_comprobantes(request: Request, db: Session = Depends(get_db)):
    """Elimina comprobantes de un archivo cargado."""
    form = await request.form()
    archivo = str(form.get("archivo", ""))
    cliente_id = int(str(form.get("cliente_id", "0")))

    if archivo and cliente_id:
        eliminados = eliminar_comprobantes_por_archivo(archivo, cliente_id, db)
        return templates.TemplateResponse("monotributo.html",
            _monotributo_ctx(request, db,
                exito=f"Se eliminaron {eliminados} comprobantes del archivo '{archivo}'."))
    return RedirectResponse("/monotributo", status_code=303)


# --------------------------------------------------------------------------
# Gestion de usuarios (solo admin)
# --------------------------------------------------------------------------

ETIQUETAS_PERMISOS = {
    "dashboard": "Dashboard",
    "upload": "Subir PDF",
    "movimientos": "Movimientos",
    "reporte": "Reportes",
    "percepciones": "Percepciones/Retenciones",
    "sircreb": "SIRCREB (IIBB)",
    "monotributo": "Panel Monotributo",
    "clientes": "Gestionar clientes",
    "usuarios": "Gestionar usuarios",
}

DESCRIPCIONES_PERMISOS = {
    "dashboard": "ver resumen general",
    "upload": "subir extractos bancarios",
    "movimientos": "ver lista de movimientos",
    "reporte": "ver y descargar reporte Ley 25.413",
    "percepciones": "ver reporte de percepciones y retenciones sufridas",
    "sircreb": "importar archivos SIRCREB y ver percepciones IIBB por jurisdiccion",
    "monotributo": "ver panel de monotributo y cargar comprobantes",
    "clientes": "crear, editar y eliminar clientes",
    "usuarios": "administrar usuarios y permisos",
}


@router.get("/usuarios", response_class=HTMLResponse)
async def usuarios_page(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse("usuarios.html", _ctx(
        request,
        usuarios=listar_usuarios(db),
        todos_los_permisos=TODOS_LOS_PERMISOS,
        etiquetas=ETIQUETAS_PERMISOS,
        descripciones=DESCRIPCIONES_PERMISOS,
    ))


@router.post("/usuarios/crear")
async def usuarios_crear(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    username = str(form.get("username", "")).strip().lower()
    password = str(form.get("password", ""))
    nombre = str(form.get("nombre", "")).strip()
    permisos = form.getlist("permisos")

    base_ctx = dict(
        usuarios=listar_usuarios(db),
        todos_los_permisos=TODOS_LOS_PERMISOS,
        etiquetas=ETIQUETAS_PERMISOS,
        descripciones=DESCRIPCIONES_PERMISOS,
    )

    if not username or not password or not nombre:
        return templates.TemplateResponse("usuarios.html", _ctx(
            request, error="Todos los campos son obligatorios.", **base_ctx,
        ))

    if obtener_por_username(username, db):
        return templates.TemplateResponse("usuarios.html", _ctx(
            request, error=f"El usuario '{username}' ya existe.", **base_ctx,
        ))

    crear_usuario(username, password, nombre, permisos, db)
    base_ctx["usuarios"] = listar_usuarios(db)
    return templates.TemplateResponse("usuarios.html", _ctx(
        request, exito=f"Usuario '{username}' creado.", **base_ctx,
    ))


@router.get("/usuarios/{usuario_id}/editar", response_class=HTMLResponse)
async def usuarios_editar_form(request: Request, usuario_id: int, db: Session = Depends(get_db)):
    usuario_edit = obtener_por_id(usuario_id, db)
    if not usuario_edit:
        return RedirectResponse("/usuarios", status_code=303)

    return templates.TemplateResponse("usuario_editar.html", _ctx(
        request,
        usuario_edit=usuario_edit,
        todos_los_permisos=TODOS_LOS_PERMISOS,
        etiquetas=ETIQUETAS_PERMISOS,
        descripciones=DESCRIPCIONES_PERMISOS,
    ))


@router.post("/usuarios/{usuario_id}/editar")
async def usuarios_editar(request: Request, usuario_id: int, db: Session = Depends(get_db)):
    form = await request.form()
    nombre = str(form.get("nombre", "")).strip()
    permisos = form.getlist("permisos")
    activo = form.get("activo") == "on"
    nueva_password = str(form.get("password", "")).strip() or None

    usuario_edit = actualizar_usuario(usuario_id, nombre, permisos, activo, db, nueva_password)
    if not usuario_edit:
        return RedirectResponse("/usuarios", status_code=303)

    return templates.TemplateResponse("usuario_editar.html", _ctx(
        request,
        usuario_edit=usuario_edit,
        todos_los_permisos=TODOS_LOS_PERMISOS,
        etiquetas=ETIQUETAS_PERMISOS,
        descripciones=DESCRIPCIONES_PERMISOS,
        exito="Usuario actualizado.",
    ))


@router.post("/usuarios/{usuario_id}/eliminar")
async def usuarios_eliminar(request: Request, usuario_id: int, db: Session = Depends(get_db)):
    # No permitir que el admin se elimine a si mismo
    usuario_actual = getattr(request.state, "usuario", None)
    if usuario_actual and usuario_actual.id == usuario_id:
        return RedirectResponse("/usuarios", status_code=303)

    eliminar_usuario(usuario_id, db)
    return RedirectResponse("/usuarios", status_code=303)


# --------------------------------------------------------------------------
# Gestion de clientes (admin o con permiso "clientes")
# --------------------------------------------------------------------------

CATEGORIAS_CLIENTE = ["General", "Monotributo", "Responsable Inscripto", "Sociedad", "Autonomo"]


@router.get("/clientes", response_class=HTMLResponse)
async def clientes_page(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse("clientes.html", _ctx(
        request,
        clientes=listar_clientes(db),
        categorias=CATEGORIAS_CLIENTE,
        usuarios=listar_usuarios(db),
    ))


@router.post("/clientes/crear")
async def clientes_crear(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    nombre = str(form.get("nombre", "")).strip()
    cuit = str(form.get("cuit", "")).strip()
    categoria = str(form.get("categoria", "General"))

    base_ctx = dict(
        clientes=listar_clientes(db),
        categorias=CATEGORIAS_CLIENTE,
        usuarios=listar_usuarios(db),
    )

    if not nombre:
        return templates.TemplateResponse("clientes.html", _ctx(
            request, error="El nombre es obligatorio.", **base_ctx,
        ))

    crear_cliente(nombre, cuit, categoria, db)
    base_ctx["clientes"] = listar_clientes(db)
    return templates.TemplateResponse("clientes.html", _ctx(
        request, exito=f"Cliente '{nombre}' creado.", **base_ctx,
    ))


@router.get("/clientes/{cliente_id}/editar", response_class=HTMLResponse)
async def clientes_editar_form(request: Request, cliente_id: int, db: Session = Depends(get_db)):
    cliente = obtener_cliente_por_id(cliente_id, db)
    if not cliente:
        return RedirectResponse("/clientes", status_code=303)

    return templates.TemplateResponse("cliente_editar.html", _ctx(
        request,
        cliente=cliente,
        categorias=CATEGORIAS_CLIENTE,
        categorias_monotributo=CATEGORIAS_MONOTRIBUTO,
        usuarios=listar_usuarios(db),
        usuarios_asignados=[u.id for u in cliente.usuarios],
    ))


@router.post("/clientes/{cliente_id}/editar")
async def clientes_editar(request: Request, cliente_id: int, db: Session = Depends(get_db)):
    form = await request.form()
    nombre = str(form.get("nombre", "")).strip()
    cuit = str(form.get("cuit", "")).strip()
    categoria = str(form.get("categoria", "General"))
    categoria_monotributo = str(form.get("categoria_monotributo", "")).strip().upper() or None
    actividad_monotributo = str(form.get("actividad_monotributo", "servicios")).strip()
    activo = form.get("activo") == "on"
    usuario_ids = [int(uid) for uid in form.getlist("usuarios")]

    cliente = actualizar_cliente(cliente_id, nombre, cuit, categoria, activo, db,
                                 categoria_monotributo=categoria_monotributo,
                                 actividad_monotributo=actividad_monotributo)
    if not cliente:
        return RedirectResponse("/clientes", status_code=303)

    asignar_usuarios(cliente_id, usuario_ids, db)
    db.refresh(cliente)

    return templates.TemplateResponse("cliente_editar.html", _ctx(
        request,
        cliente=cliente,
        categorias=CATEGORIAS_CLIENTE,
        categorias_monotributo=CATEGORIAS_MONOTRIBUTO,
        usuarios=listar_usuarios(db),
        usuarios_asignados=[u.id for u in cliente.usuarios],
        exito="Cliente actualizado.",
    ))


@router.post("/clientes/{cliente_id}/eliminar")
async def clientes_eliminar(request: Request, cliente_id: int, db: Session = Depends(get_db)):
    eliminar_cliente(cliente_id, db)
    return RedirectResponse("/clientes", status_code=303)
