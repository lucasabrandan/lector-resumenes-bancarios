"""
Servicio de movimientos: orquesta parsing, persistencia y consultas.

Es el "caso de uso" central de la app. El front y la API llaman acá,
nunca al parser o a la DB directamente.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

from sqlalchemy import func, extract
from sqlalchemy.orm import Session

from app.db.models import MovimientoDB
from app.domain.models import MovimientoBancario, SignoMovimiento, TipoMovimiento, Moneda
from app.parsers.supervielle_pdf import ParserSupervielle


def archivo_ya_cargado(nombre_archivo: str, db: Session) -> int:
    """Devuelve la cantidad de movimientos ya cargados de este archivo, o 0."""
    return (
        db.query(func.count(MovimientoDB.id))
        .filter(MovimientoDB.archivo_origen == nombre_archivo)
        .scalar() or 0
    )


def procesar_pdf(ruta_pdf: Path, db: Session, cliente_id: int | None = None) -> int:
    """Parsea un PDF de Supervielle y guarda los movimientos en la DB.

    Returns:
        Cantidad de movimientos guardados.
    """
    parser = ParserSupervielle()
    movimientos = parser.parsear(ruta_pdf)

    nombre_archivo = ruta_pdf.name

    registros = []
    for m in movimientos:
        registro = MovimientoDB(
            banco=m.banco,
            cuenta=m.cuenta,
            archivo_origen=nombre_archivo,
            pagina_origen=m.pagina_origen,
            cliente_id=cliente_id,
            fecha=m.fecha,
            concepto=m.concepto,
            detalle_adicional=m.detalle_adicional,
            numero_operacion=m.numero_operacion,
            importe=float(m.importe),
            signo=m.signo.value,
            saldo_posterior=float(m.saldo_posterior) if m.saldo_posterior is not None else None,
            moneda=m.moneda.value,
            tipo=m.tipo.value,
        )
        registros.append(registro)

    db.add_all(registros)
    db.commit()
    return len(registros)


def eliminar_por_archivo(nombre_archivo: str, db: Session) -> int:
    """Elimina todos los movimientos de un archivo. Devuelve cantidad eliminada."""
    cantidad = (
        db.query(MovimientoDB)
        .filter(MovimientoDB.archivo_origen == nombre_archivo)
        .delete(synchronize_session=False)
    )
    db.commit()
    return cantidad


def listar_archivos_cargados(db: Session, cliente_ids: list[int] | None = None) -> list[dict]:
    """Lista archivos procesados con stats. Si cliente_ids es None, muestra todos."""
    query = db.query(
        MovimientoDB.archivo_origen,
        MovimientoDB.cliente_id,
        func.count(MovimientoDB.id).label("cantidad"),
        func.min(MovimientoDB.fecha).label("fecha_min"),
        func.max(MovimientoDB.fecha).label("fecha_max"),
    )
    if cliente_ids is not None:
        query = query.filter(MovimientoDB.cliente_id.in_(cliente_ids))
    rows = (
        query
        .group_by(MovimientoDB.archivo_origen, MovimientoDB.cliente_id)
        .order_by(MovimientoDB.archivo_origen)
        .all()
    )
    return [
        {
            "archivo": r.archivo_origen,
            "cliente_id": r.cliente_id,
            "cantidad": r.cantidad,
            "fecha_min": r.fecha_min,
            "fecha_max": r.fecha_max,
        }
        for r in rows
    ]


def _aplicar_filtro_clientes(query, cliente_ids: list[int] | None):
    """Aplica filtro por cliente_ids. None = sin filtro (admin)."""
    if cliente_ids is not None:
        query = query.filter(MovimientoDB.cliente_id.in_(cliente_ids))
    return query


def listar_movimientos(
    db: Session,
    cuenta: str | None = None,
    tipo: str | None = None,
    fecha_desde: date | None = None,
    fecha_hasta: date | None = None,
    buscar: str | None = None,
    limite: int = 100,
    offset: int = 0,
    cliente_ids: list[int] | None = None,
) -> list[MovimientoDB]:
    """Consulta movimientos con filtros opcionales."""
    query = db.query(MovimientoDB)
    query = _aplicar_filtro_clientes(query, cliente_ids)

    if cuenta:
        query = query.filter(MovimientoDB.cuenta == cuenta)
    if tipo:
        query = query.filter(MovimientoDB.tipo == tipo)
    if fecha_desde:
        query = query.filter(MovimientoDB.fecha >= fecha_desde)
    if fecha_hasta:
        query = query.filter(MovimientoDB.fecha <= fecha_hasta)
    if buscar:
        query = query.filter(MovimientoDB.concepto.ilike(f"%{buscar}%"))

    return query.order_by(MovimientoDB.fecha, MovimientoDB.id).offset(offset).limit(limite).all()


def contar_movimientos_filtrados(
    db: Session,
    tipo: str | None = None,
    fecha_desde: date | None = None,
    fecha_hasta: date | None = None,
    buscar: str | None = None,
    cliente_ids: list[int] | None = None,
) -> int:
    """Total de movimientos con filtros aplicados."""
    query = db.query(func.count(MovimientoDB.id))
    query = _aplicar_filtro_clientes(query, cliente_ids)
    if tipo:
        query = query.filter(MovimientoDB.tipo == tipo)
    if fecha_desde:
        query = query.filter(MovimientoDB.fecha >= fecha_desde)
    if fecha_hasta:
        query = query.filter(MovimientoDB.fecha <= fecha_hasta)
    if buscar:
        query = query.filter(MovimientoDB.concepto.ilike(f"%{buscar}%"))
    return query.scalar() or 0


def contar_movimientos(db: Session, cliente_ids: list[int] | None = None) -> int:
    """Total de movimientos en la DB."""
    query = db.query(func.count(MovimientoDB.id))
    query = _aplicar_filtro_clientes(query, cliente_ids)
    return query.scalar() or 0


def obtener_cuentas(db: Session) -> list[str]:
    """Lista de cuentas únicas en la DB."""
    rows = db.query(MovimientoDB.cuenta).distinct().all()
    return [r[0] for r in rows]


def obtener_rango_fechas(db: Session) -> tuple[date | None, date | None]:
    """Fecha mínima y máxima de los movimientos."""
    resultado = db.query(
        func.min(MovimientoDB.fecha),
        func.max(MovimientoDB.fecha),
    ).first()
    return (resultado[0], resultado[1]) if resultado else (None, None)


def distribucion_por_tipo(db: Session, cliente_ids: list[int] | None = None) -> list[dict]:
    """Cantidad y total por tipo de movimiento, ordenado por cantidad desc."""
    query = db.query(
        MovimientoDB.tipo,
        func.count(MovimientoDB.id).label("cantidad"),
        func.sum(MovimientoDB.importe).label("total"),
    )
    query = _aplicar_filtro_clientes(query, cliente_ids)
    rows = (
        query
        .group_by(MovimientoDB.tipo)
        .order_by(func.count(MovimientoDB.id).desc())
        .all()
    )
    return [{"tipo": r.tipo, "cantidad": r.cantidad, "total": float(r.total)} for r in rows]


def distribucion_mensual(db: Session, cliente_ids: list[int] | None = None) -> dict:
    """Distribucion por tipo agrupada por mes.

    Returns:
        Dict con clave "YYYY-MM" y valor lista de {tipo, cantidad, total}.
    """
    query = db.query(
        extract("year", MovimientoDB.fecha).label("anio"),
        extract("month", MovimientoDB.fecha).label("mes"),
        MovimientoDB.tipo,
        func.count(MovimientoDB.id).label("cantidad"),
        func.sum(MovimientoDB.importe).label("total"),
    )
    query = _aplicar_filtro_clientes(query, cliente_ids)
    rows = (
        query
        .group_by("anio", "mes", MovimientoDB.tipo)
        .order_by("anio", "mes", func.count(MovimientoDB.id).desc())
        .all()
    )

    resultado: dict[str, list[dict]] = {}
    for r in rows:
        clave = f"{int(r.anio)}-{int(r.mes):02d}"
        if clave not in resultado:
            resultado[clave] = []
        resultado[clave].append({
            "tipo": r.tipo,
            "cantidad": r.cantidad,
            "total": float(r.total),
        })
    return resultado
