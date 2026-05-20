"""
Rutas HTML server-rendered con Jinja2 + HTMX.

Estas son las páginas que ve la contadora en el navegador.
"""

import json
from pathlib import Path

from markupsafe import Markup

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
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
    distribucion_por_tipo,
    distribucion_mensual,
    archivo_ya_cargado,
    eliminar_por_archivo,
    listar_archivos_cargados,
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
from app.services.monotributo import generar_panel_monotributo, CATEGORIAS_MONOTRIBUTO

router = APIRouter()

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))


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
    context = _ctx(request, total_movimientos=total, distribucion=[])

    if total > 0:
        context["resumen"] = resumen_general(db, cliente_ids=cids)
        context["reporte_ley"] = generar_reporte_ley_25413(db, cliente_ids=cids)
        context["distribucion"] = distribucion_por_tipo(db, cliente_ids=cids)
        context["dist_mensual_json"] = Markup(json.dumps(distribucion_mensual(db, cliente_ids=cids)))

    return templates.TemplateResponse("dashboard.html", context)


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
        cantidad = procesar_pdf(tmp_path, db, cliente_id=cliente_id)
        ctx["archivos"] = listar_archivos_cargados(db, cliente_ids=cids)
        cliente = obtener_cliente_por_id(cliente_id, db)
        nombre_cliente = cliente.nombre if cliente else "?"
        ctx["exito"] = f"Se procesaron {cantidad:,} movimientos del archivo '{archivo.filename}' para el cliente '{nombre_cliente}'."
        return templates.TemplateResponse("upload.html", ctx)
    except Exception as e:
        ctx["error"] = f"Error al procesar el PDF: {e}"
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
# Panel de Monotributo
# --------------------------------------------------------------------------

@router.get("/monotributo", response_class=HTMLResponse)
async def monotributo_page(request: Request, db: Session = Depends(get_db)):
    cids = _get_cliente_ids(request, db)
    panel = generar_panel_monotributo(db, cliente_ids=cids)
    return templates.TemplateResponse("monotributo.html", _ctx(
        request,
        panel=panel,
        categorias_monotributo=CATEGORIAS_MONOTRIBUTO,
    ))


# --------------------------------------------------------------------------
# Gestion de usuarios (solo admin)
# --------------------------------------------------------------------------

ETIQUETAS_PERMISOS = {
    "dashboard": "Dashboard",
    "upload": "Subir PDF",
    "movimientos": "Movimientos",
    "reporte": "Reportes",
    "monotributo": "Panel Monotributo",
    "clientes": "Gestionar clientes",
    "usuarios": "Gestionar usuarios",
}


@router.get("/usuarios", response_class=HTMLResponse)
async def usuarios_page(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse("usuarios.html", _ctx(
        request,
        usuarios=listar_usuarios(db),
        todos_los_permisos=TODOS_LOS_PERMISOS,
        etiquetas=ETIQUETAS_PERMISOS,
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
