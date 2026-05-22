"""
Clasificador de tipos de movimiento para MercadoPago.

Similar al clasificador de Supervielle pero con reglas específicas para
los conceptos que usa MercadoPago en sus resúmenes de cuenta.

Conceptos típicos de MP:
    - Liquidación de dinero (cobros por MP Point / QR)
    - Transferencia enviada/recibida [nombre]
    - Pago [servicio] (SUBE, Movistar, Claro, Personal, Netflix, etc.)
    - Pago de servicio [servicio] (ARCA, Edesur, etc.)
    - Pago con QR [destino]
    - Pago Autoservicio/comercio
    - Rendimientos (intereses del saldo en MP)
    - Compra/Venta de dólar MEP
    - Compra Mercado Libre
    - Devolución de dinero [concepto]
"""

from __future__ import annotations

import re
from typing import Pattern

from app.domain.models import TipoMovimiento


_REGLAS_RAW: list[tuple[str, TipoMovimiento]] = [
    # ---- DEVOLUCIONES (antes que otros) ----
    (r"Devoluci[oó]n", TipoMovimiento.DEVOLUCION),
    (r"Reintegro", TipoMovimiento.DEVOLUCION),

    # ---- TRANSFERENCIAS ----
    (r"Transferencia\s+enviada", TipoMovimiento.TRANSFERENCIA_ENVIADA),
    (r"Transferencia\s+recibida", TipoMovimiento.TRANSFERENCIA_RECIBIDA),

    # ---- PAGOS DE SERVICIOS (específicos primero) ----
    (r"Pago\s+de\s+servicio", TipoMovimiento.PAGO_SERVICIO),
    (r"Pago\s+SUBE", TipoMovimiento.PAGO_SERVICIO),
    (r"Pago\s+Movistar", TipoMovimiento.PAGO_SERVICIO),
    (r"Pago\s+Claro", TipoMovimiento.PAGO_SERVICIO),
    (r"Pago\s+Personal", TipoMovimiento.PAGO_SERVICIO),
    (r"Pago\s+Netflix", TipoMovimiento.PAGO_SERVICIO),
    (r"Pago\s+MUNICIPALIDAD", TipoMovimiento.PAGO_SERVICIO),

    # ---- COMPRAS ----
    (r"Compra\s+Mercado\s+Libre", TipoMovimiento.COMPRA_DEBITO),
    (r"Compra\s+de\s+d[oó]lar\s+MEP", TipoMovimiento.OTRO),
    (r"Venta\s+de\s+d[oó]lar\s+MEP", TipoMovimiento.OTRO),
    (r"Pago\s+con\s+QR", TipoMovimiento.COMPRA_DEBITO),
    (r"Pago\s+Mercado\s+Libre", TipoMovimiento.COMPRA_DEBITO),
    (r"Pago\s+Temu", TipoMovimiento.COMPRA_DEBITO),

    # ---- PAGOS GENÉRICOS (compras en comercios) ----
    # Si empieza con "Pago" y no matcheó antes, es un pago genérico
    (r"^Pago\s+", TipoMovimiento.COMPRA_DEBITO),

    # ---- LIQUIDACIONES (cobros por ventas con MP) ----
    (r"Liquidaci[oó]n\s+de\s+dinero", TipoMovimiento.OTRO),

    # ---- RENDIMIENTOS (intereses del saldo) ----
    (r"Rendimientos", TipoMovimiento.INTERES),
]

_REGLAS: list[tuple[Pattern[str], TipoMovimiento]] = [
    (re.compile(patron, flags=re.IGNORECASE), tipo)
    for patron, tipo in _REGLAS_RAW
]


def clasificar_mp(concepto: str) -> TipoMovimiento:
    """Clasifica un concepto de MercadoPago en un TipoMovimiento."""
    for patron, tipo in _REGLAS:
        if patron.search(concepto):
            return tipo
    return TipoMovimiento.OTRO
