"""Servicio de gestión de comprobantes ARCA."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy.orm import Session

from app.db.models import ComprobanteDB
from app.parsers.arca_comprobantes import ComprobanteARCA


def guardar_comprobantes(
    comprobantes: list[ComprobanteARCA],
    cliente_id: int,
    archivo_origen: str,
    db: Session,
) -> int:
    """Persiste comprobantes parseados. Retorna cantidad guardada."""
    for c in comprobantes:
        db.add(ComprobanteDB(
            cliente_id=cliente_id,
            fecha=c.fecha,
            tipo_comprobante=c.tipo_comprobante,
            punto_venta=c.punto_venta,
            numero_desde=c.numero_desde,
            numero_hasta=c.numero_hasta,
            cod_autorizacion=c.cod_autorizacion,
            tipo_doc_receptor=c.tipo_doc_receptor,
            nro_doc_receptor=c.nro_doc_receptor,
            denominacion_receptor=c.denominacion_receptor,
            moneda=c.moneda,
            tipo_cambio=float(c.tipo_cambio),
            importe_total=float(c.importe_total),
            archivo_origen=archivo_origen,
        ))
    db.commit()
    return len(comprobantes)


def archivo_comprobantes_ya_cargado(nombre_archivo: str, cliente_id: int, db: Session) -> int:
    """Retorna cantidad de comprobantes ya cargados de ese archivo para ese cliente."""
    return (
        db.query(ComprobanteDB)
        .filter(
            ComprobanteDB.archivo_origen == nombre_archivo,
            ComprobanteDB.cliente_id == cliente_id,
        )
        .count()
    )


def eliminar_comprobantes_por_archivo(nombre_archivo: str, cliente_id: int, db: Session) -> int:
    """Elimina comprobantes de un archivo. Retorna cantidad eliminada."""
    count = (
        db.query(ComprobanteDB)
        .filter(
            ComprobanteDB.archivo_origen == nombre_archivo,
            ComprobanteDB.cliente_id == cliente_id,
        )
        .delete()
    )
    db.commit()
    return count


def listar_archivos_comprobantes(db: Session, cliente_id: int | None = None) -> list[dict]:
    """Lista archivos de comprobantes cargados con resumen."""
    from sqlalchemy import func
    query = (
        db.query(
            ComprobanteDB.archivo_origen,
            ComprobanteDB.cliente_id,
            func.count(ComprobanteDB.id).label("cantidad"),
            func.min(ComprobanteDB.fecha).label("fecha_desde"),
            func.max(ComprobanteDB.fecha).label("fecha_hasta"),
            func.sum(ComprobanteDB.importe_total).label("total"),
        )
        .group_by(ComprobanteDB.archivo_origen, ComprobanteDB.cliente_id)
    )
    if cliente_id is not None:
        query = query.filter(ComprobanteDB.cliente_id == cliente_id)

    return [
        {
            "archivo": r.archivo_origen,
            "cliente_id": r.cliente_id,
            "cantidad": r.cantidad,
            "fecha_desde": r.fecha_desde,
            "fecha_hasta": r.fecha_hasta,
            "total": Decimal(str(r.total)).quantize(Decimal("0.01")),
        }
        for r in query.all()
    ]
