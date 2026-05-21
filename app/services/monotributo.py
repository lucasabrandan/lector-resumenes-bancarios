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

from app.db.models import ClienteDB, ComprobanteDB, MovimientoDB


# Topes ANUALES de facturación bruta por categoría (vigencia julio 2025).
# Fuente: ARCA / ex-AFIP.
# El semestre se calcula como tope_anual / 2.
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
    # "ambas" usa el tope de comercio (siempre >= servicios)
    clave = "comercio" if actividad == "ambas" else actividad
    return cat.get(clave)


def tope_semestral(categoria: str, actividad: str = "servicios") -> Decimal | None:
    """Tope del semestre (anual / 2). La recategorización es semestral."""
    anual = tope_anual(categoria, actividad)
    if anual is None:
        return None
    return (anual / 2).quantize(Decimal("0.01"))


def _rango_semestre_actual(hoy: date | None = None) -> tuple[date, date]:
    """Devuelve (inicio, fin) del semestre actual para recategorización.
    Semestre 1: enero-junio, Semestre 2: julio-diciembre.
    """
    if hoy is None:
        hoy = date.today()
    if hoy.month <= 6:
        return date(hoy.year, 1, 1), date(hoy.year, 6, 30)
    else:
        return date(hoy.year, 7, 1), date(hoy.year, 12, 31)


@dataclass
class ResumenMonotributo:
    """Resumen de un cliente monotributista para el panel de control."""
    cliente_id: int
    nombre: str
    cuit: str | None
    categoria: str
    actividad: str
    tope_semestral: Decimal
    acumulado_facturacion: Decimal
    semestre_label: str
    fuente: str  # "arca" o "banco"

    @property
    def porcentaje_usado(self) -> float:
        if self.tope_semestral == 0:
            return 0.0
        return float((self.acumulado_facturacion / self.tope_semestral) * 100)

    @property
    def disponible(self) -> Decimal:
        return self.tope_semestral - self.acumulado_facturacion

    @property
    def estado(self) -> str:
        p = self.porcentaje_usado
        if p >= 95:
            return "critico"
        elif p >= 80:
            return "alerta"
        elif p >= 60:
            return "atencion"
        return "ok"


def generar_panel_monotributo(
    db: Session,
    cliente_ids: list[int] | None = None,
    hoy: date | None = None,
) -> list[ResumenMonotributo]:
    """Genera el panel de control de monotributistas.

    Calcula el acumulado de créditos (ingresos) del semestre actual
    para cada cliente monotributista y lo compara contra el tope.
    """
    inicio, fin = _rango_semestre_actual(hoy)

    if inicio.month == 1:
        semestre_label = f"Enero - Junio {inicio.year}"
    else:
        semestre_label = f"Julio - Diciembre {inicio.year}"

    # Obtener clientes monotributistas
    query = db.query(ClienteDB).filter(
        ClienteDB.categoria == "Monotributo",
        ClienteDB.categoria_monotributo.isnot(None),
        ClienteDB.activo == True,
    )
    if cliente_ids is not None:
        query = query.filter(ClienteDB.id.in_(cliente_ids))

    clientes = query.order_by(ClienteDB.nombre).all()

    if not clientes:
        return []

    ids = [c.id for c in clientes]

    # Facturación desde comprobantes ARCA (fuente principal).
    # Facturas suman, Notas de Crédito restan.
    acum_arca = dict(
        db.query(
            ComprobanteDB.cliente_id,
            func.coalesce(
                func.sum(
                    case(
                        (ComprobanteDB.tipo_comprobante.ilike("%nota de cr%"), -ComprobanteDB.importe_total),
                        else_=ComprobanteDB.importe_total,
                    )
                ),
                0,
            ).label("total"),
        )
        .filter(
            ComprobanteDB.cliente_id.in_(ids),
            ComprobanteDB.fecha >= inicio,
            ComprobanteDB.fecha <= fin,
        )
        .group_by(ComprobanteDB.cliente_id)
        .all()
    )

    # Fallback: créditos bancarios (para clientes sin comprobantes cargados)
    acum_banco = dict(
        db.query(
            MovimientoDB.cliente_id,
            func.coalesce(func.sum(MovimientoDB.importe), 0).label("total"),
        )
        .filter(
            MovimientoDB.cliente_id.in_(ids),
            MovimientoDB.signo == "CREDITO",
            MovimientoDB.fecha >= inicio,
            MovimientoDB.fecha <= fin,
        )
        .group_by(MovimientoDB.cliente_id)
        .all()
    )

    resultado = []
    for c in clientes:
        actividad = c.actividad_monotributo or "servicios"
        tope = tope_semestral(c.categoria_monotributo, actividad)
        if tope is None:
            continue

        # Priorizar comprobantes ARCA; si no hay, usar créditos bancarios
        if c.id in acum_arca:
            acum = Decimal(str(acum_arca[c.id])).quantize(Decimal("0.01"))
            fuente = "arca"
        else:
            acum = Decimal(str(acum_banco.get(c.id, 0))).quantize(Decimal("0.01"))
            fuente = "banco"

        resultado.append(ResumenMonotributo(
            cliente_id=c.id,
            nombre=c.nombre,
            cuit=c.cuit,
            categoria=c.categoria_monotributo,
            actividad=actividad,
            tope_semestral=tope,
            acumulado_facturacion=acum,
            semestre_label=semestre_label,
            fuente=fuente,
        ))

    # Ordenar por % usado descendente (los más urgentes primero)
    resultado.sort(key=lambda r: r.porcentaje_usado, reverse=True)
    return resultado
