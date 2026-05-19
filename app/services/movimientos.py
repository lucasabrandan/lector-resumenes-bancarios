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


def procesar_pdf(ruta_pdf: Path, db: Session) -> int:
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


def listar_movimientos(
    db: Session,
    cuenta: str | None = None,
    tipo: str | None = None,
    fecha_desde: date | None = None,
    fecha_hasta: date | None = None,
    buscar: str | None = None,
    limite: int = 100,
    offset: int = 0,
) -> list[MovimientoDB]:
    """Consulta movimientos con filtros opcionales."""
    query = db.query(MovimientoDB)

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
) -> int:
    """Total de movimientos con filtros aplicados."""
    query = db.query(func.count(MovimientoDB.id))
    if tipo:
        query = query.filter(MovimientoDB.tipo == tipo)
    if fecha_desde:
        query = query.filter(MovimientoDB.fecha >= fecha_desde)
    if fecha_hasta:
        query = query.filter(MovimientoDB.fecha <= fecha_hasta)
    if buscar:
        query = query.filter(MovimientoDB.concepto.ilike(f"%{buscar}%"))
    return query.scalar() or 0


def contar_movimientos(db: Session) -> int:
    """Total de movimientos en la DB."""
    return db.query(func.count(MovimientoDB.id)).scalar() or 0


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


def distribucion_por_tipo(db: Session) -> list[dict]:
    """Cantidad y total por tipo de movimiento, ordenado por cantidad desc."""
    rows = (
        db.query(
            MovimientoDB.tipo,
            func.count(MovimientoDB.id).label("cantidad"),
            func.sum(MovimientoDB.importe).label("total"),
        )
        .group_by(MovimientoDB.tipo)
        .order_by(func.count(MovimientoDB.id).desc())
        .all()
    )
    return [{"tipo": r.tipo, "cantidad": r.cantidad, "total": float(r.total)} for r in rows]


def distribucion_mensual(db: Session) -> dict:
    """Distribucion por tipo agrupada por mes.

    Returns:
        Dict con clave "YYYY-MM" y valor lista de {tipo, cantidad, total}.
    """
    rows = (
        db.query(
            extract("year", MovimientoDB.fecha).label("anio"),
            extract("month", MovimientoDB.fecha).label("mes"),
            MovimientoDB.tipo,
            func.count(MovimientoDB.id).label("cantidad"),
            func.sum(MovimientoDB.importe).label("total"),
        )
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
