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

    return query.order_by(MovimientoDB.fecha, MovimientoDB.id).offset(offset).limit(limite).all()


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
