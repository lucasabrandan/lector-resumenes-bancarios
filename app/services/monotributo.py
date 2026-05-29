"""
Servicio de control de monotributo.

Topes de facturación por categoría según ARCA (vigencia 2025).
Se actualizan en enero y julio de cada año.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.db.models import ComprobanteDB


# Topes ANUALES de facturación bruta por categoría (vigencia julio 2025).
TOPES_MONOTRIBUTO: dict[str, dict[str, Decimal]] = {
    "A": {"servicios": Decimal("7881162.98"),   "comercio": Decimal("7881162.98")},
    "B": {"servicios": Decimal("11721606.82"),  "comercio": Decimal("11721606.82")},
    "C": {"servicios": Decimal("16415848.98"),  "comercio": Decimal("16415848.98")},
    "D": {"servicios": Decimal("20380564.14"),  "comercio": Decimal("20380564.14")},
    "E": {"servicios": Decimal("24015585.78"),  "comercio": Decimal("28232424.90")},
    "F": {"servicios": Decimal("29985990.30"),  "comercio": Decimal("35278199.22")},
    "G": {"servicios": Decimal("35978802.78"),  "comercio": Decimal("42333839.10")},
    "H": {"servicios": Decimal("54288420.42"),  "comercio": Decimal("54288420.42")},
    "I": {"servicios": None,                    "comercio": Decimal("59657000.88")},
    "J": {"servicios": None,                    "comercio": Decimal("68318348.86")},
    "K": {"servicios": None,                    "comercio": Decimal("77776382.56")},
}

CATEGORIAS_MONOTRIBUTO = list(TOPES_MONOTRIBUTO.keys())


def tope_anual(categoria: str, actividad: str = "servicios") -> Decimal | None:
    """Tope anual de facturación para la categoría y actividad."""
    cat = TOPES_MONOTRIBUTO.get(categoria.upper())
    if not cat:
        return None
    clave = "comercio" if actividad == "ambas" else actividad
    return cat.get(clave)


def tope_semestral(categoria: str, actividad: str = "servicios") -> Decimal | None:
    """Tope del semestre (anual / 2)."""
    anual = tope_anual(categoria, actividad)
    if anual is None:
        return None
    return (anual / 2).quantize(Decimal("0.01"))


def _rango_semestre_actual(hoy: date | None = None) -> tuple[date, date]:
    """Devuelve (inicio, fin) del semestre actual."""
    if hoy is None:
        hoy = date.today()
    if hoy.month <= 6:
        return date(hoy.year, 1, 1), date(hoy.year, 6, 30)
    else:
        return date(hoy.year, 7, 1), date(hoy.year, 12, 31)


@dataclass
class ResumenMonotributo:
    """Resumen de facturación del semestre actual."""
    acumulado_facturacion: Decimal
    semestre_label: str
    cantidad_comprobantes: int


def generar_panel_monotributo(
    db: Session,
    hoy: date | None = None,
) -> ResumenMonotributo | None:
    """Genera resumen de comprobantes del semestre actual."""
    inicio, fin = _rango_semestre_actual(hoy)

    if inicio.month == 1:
        semestre_label = f"Enero - Junio {inicio.year}"
    else:
        semestre_label = f"Julio - Diciembre {inicio.year}"

    result = (
        db.query(
            func.coalesce(
                func.sum(
                    case(
                        (ComprobanteDB.tipo_comprobante.ilike("%nota de cr%"), -ComprobanteDB.importe_total),
                        else_=ComprobanteDB.importe_total,
                    )
                ),
                0,
            ).label("total"),
            func.count(ComprobanteDB.id).label("cantidad"),
        )
        .filter(
            ComprobanteDB.fecha >= inicio,
            ComprobanteDB.fecha <= fin,
        )
        .first()
    )

    if not result or result.cantidad == 0:
        return None

    return ResumenMonotributo(
        acumulado_facturacion=Decimal(str(result.total)).quantize(Decimal("0.01")),
        semestre_label=semestre_label,
        cantidad_comprobantes=result.cantidad,
    )
