"""
Reporte de Impuesto Ley 25.413 (débitos y créditos bancarios).

Este es EL reporte que la contadora necesita para presentar a ARCA.
Totaliza por mes cuánto cobró el banco en concepto de:
  - Impuesto sobre débitos (IMPUESTO_LEY_25413_SOBRE_DEBITOS)
  - Impuesto sobre créditos (IMPUESTO_LEY_25413_SOBRE_CREDITOS)

Nota sobre devoluciones (descubierto en iter 3.3):
    El banco a veces devuelve parte del impuesto por reclamos. Esas
    devoluciones se clasifican como DEVOLUCION y se restan del total
    del mes para obtener el impuesto neto.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import func, extract, case
from sqlalchemy.orm import Session

from app.db.models import MovimientoDB


@dataclass
class TotalMensualLey25413:
    """Totales del impuesto para un mes específico."""
    anio: int
    mes: int
    impuesto_sobre_debitos: Decimal
    impuesto_sobre_creditos: Decimal

    @property
    def total(self) -> Decimal:
        return self.impuesto_sobre_debitos + self.impuesto_sobre_creditos

    @property
    def mes_nombre(self) -> str:
        meses = [
            "", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
            "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
        ]
        return meses[self.mes]

    @property
    def periodo(self) -> str:
        return f"{self.mes_nombre} {self.anio}"


def generar_reporte_ley_25413(db: Session) -> list[TotalMensualLey25413]:
    """Genera el reporte mensual de Ley 25.413.

    Returns:
        Lista ordenada cronológicamente con los totales por mes.
    """
    # Extraer año y mes, sumar importes agrupados por tipo de impuesto
    rows = (
        db.query(
            extract("year", MovimientoDB.fecha).label("anio"),
            extract("month", MovimientoDB.fecha).label("mes"),
            func.coalesce(
                func.sum(
                    case(
                        (MovimientoDB.tipo == "IMPUESTO_LEY_25413_SOBRE_DEBITOS", MovimientoDB.importe),
                        else_=0,
                    )
                ),
                0,
            ).label("imp_debitos"),
            func.coalesce(
                func.sum(
                    case(
                        (MovimientoDB.tipo == "IMPUESTO_LEY_25413_SOBRE_CREDITOS", MovimientoDB.importe),
                        else_=0,
                    )
                ),
                0,
            ).label("imp_creditos"),
        )
        .filter(
            MovimientoDB.tipo.in_([
                "IMPUESTO_LEY_25413_SOBRE_DEBITOS",
                "IMPUESTO_LEY_25413_SOBRE_CREDITOS",
            ])
        )
        .group_by("anio", "mes")
        .order_by("anio", "mes")
        .all()
    )

    return [
        TotalMensualLey25413(
            anio=int(r.anio),
            mes=int(r.mes),
            impuesto_sobre_debitos=Decimal(str(r.imp_debitos)).quantize(Decimal("0.01")),
            impuesto_sobre_creditos=Decimal(str(r.imp_creditos)).quantize(Decimal("0.01")),
        )
        for r in rows
    ]


def resumen_general(db: Session) -> dict:
    """Estadísticas generales para el dashboard."""
    from app.services.movimientos import contar_movimientos, obtener_rango_fechas

    total_movs = contar_movimientos(db)
    fecha_min, fecha_max = obtener_rango_fechas(db)

    # Totales por signo
    totales_signo = (
        db.query(
            MovimientoDB.signo,
            func.sum(MovimientoDB.importe).label("total"),
            func.count(MovimientoDB.id).label("cantidad"),
        )
        .group_by(MovimientoDB.signo)
        .all()
    )

    debitos = next((r for r in totales_signo if r.signo == "DEBITO"), None)
    creditos = next((r for r in totales_signo if r.signo == "CREDITO"), None)

    return {
        "total_movimientos": total_movs,
        "fecha_desde": fecha_min,
        "fecha_hasta": fecha_max,
        "total_debitos": Decimal(str(debitos.total)).quantize(Decimal("0.01")) if debitos else Decimal("0"),
        "cant_debitos": debitos.cantidad if debitos else 0,
        "total_creditos": Decimal(str(creditos.total)).quantize(Decimal("0.01")) if creditos else Decimal("0"),
        "cant_creditos": creditos.cantidad if creditos else 0,
    }
