"""
Clasificador de tipos de movimiento bancario.

Mapea el "concepto" (texto descriptivo del banco) al `TipoMovimiento`
correspondiente del modelo de dominio.

Filosofía de diseño: "Configuration over Code"
    Las reglas viven en una lista declarativa de tuplas (patrón, tipo).
    El algoritmo de clasificación es una función simple de 5 líneas que
    recorre las reglas en orden y devuelve el primer match.

    Para agregar un caso nuevo: agregás una línea a la lista, nada más.
    El orden importa: las reglas más específicas van primero.

Decisiones de diseño:
    - Por qué un módulo separado del parser: Single Responsibility Principle.
      El parser sabe extraer del PDF, el clasificador sabe categorizar texto.
    - Por qué regex y no `in`: permite patrones más expresivos (palabras
      completas con \\b, alternativas con |, insensible a mayúsculas).
    - Por qué retornar `TipoMovimiento.OTRO` como default y no levantar
      excepción: un concepto desconocido NO es un error fatal. Marcar como
      OTRO y dejar que el sistema lo reporte permite descubrir conceptos
      nuevos sin romper el parsing.
"""

from __future__ import annotations

import re
from typing import Pattern

from app.domain.models import TipoMovimiento


# ============================================================================
# Reglas de clasificación
# ============================================================================
#
# Lista de (patrón_regex, tipo). El orden importa: la primera regla que
# matchea gana. Por eso las más específicas van PRIMERO.
#
# Ej: "Percepción I.V.A." debe matchear ANTES que "I.V.A." simple,
# o si no, una percepción terminaría clasificada como IVA común.
# ============================================================================

# Cada regla es: (patrón en string, tipo asignado).
# Los patrones se compilan a Pattern al cargar el módulo (más eficiente).
_REGLAS_RAW: list[tuple[str, TipoMovimiento]] = [
    # ---- IMPUESTOS (los más específicos primero) ----
    # El Impuesto Ley 25.413 termina en /DB cuando se aplicó sobre un débito,
    # y en /CR cuando se aplicó sobre un crédito. ARCA los reporta separados.
    # Ver ADR-0006.
    (r"Impuesto\s+Débitos\s+y\s+Créditos/DB", TipoMovimiento.IMPUESTO_LEY_25413_SOBRE_DEBITOS),
    (r"Impuesto\s+Débitos\s+y\s+Créditos/CR", TipoMovimiento.IMPUESTO_LEY_25413_SOBRE_CREDITOS),
    (r"IMPUESTO\s+A\s+LOS\s+SELLOS", TipoMovimiento.IMPUESTO_SELLOS),

    # ---- PERCEPCIONES (antes que IVA simple) ----
    (r"Percepción\s+I\.?V\.?A\.?", TipoMovimiento.PERCEPCION_IVA),
    (r"I\.V\.A\.\s+Percep", TipoMovimiento.PERCEPCION_IVA),

    # ---- IVA simple ----
    (r"\bIVA\b", TipoMovimiento.IVA),
    (r"\bI\.V\.A\.", TipoMovimiento.IVA),

    # ---- INTERESES (antes que comisión, hay 'Contras.Ints.Sobreg.') ----
    (r"Intereses\s+de\s+Sobregiro", TipoMovimiento.INTERES),
    (r"Contras\.?\s*Ints?\.?\s*Sobreg", TipoMovimiento.INTERES),

    # ---- COMISIONES ----
    (r"Comisi[oó]n", TipoMovimiento.COMISION),
    (r"Comision", TipoMovimiento.COMISION),
    (r"COMIS\.", TipoMovimiento.COMISION),
    (r"Com\.Cheque\s+Pagado", TipoMovimiento.COMISION),
    (r"Gestión\s+de\s+Cobranza", TipoMovimiento.COMISION),
    (r"Comisiones\s+Cheques", TipoMovimiento.COMISION),

    # ---- CHEQUES (rechazados antes que pagados/depositados) ----
    (r"Cheque\s+Rechazado", TipoMovimiento.CHEQUE_RECHAZADO),
    (r"Rechazo\s+(?:Por\s+)?Cheque|Rechazo\s+Por\s+Cta", TipoMovimiento.CHEQUE_RECHAZADO),
    (r"Pago\s+Cheque\s+de\s+Cámara", TipoMovimiento.CHEQUE_PAGADO),
    (r"Acreditación\s+Cheque", TipoMovimiento.CHEQUE_DEPOSITADO),
    (r"Acreditación\s+de\s+Cheques", TipoMovimiento.CHEQUE_DEPOSITADO),
    (r"Depósito\s+Cámara", TipoMovimiento.CHEQUE_DEPOSITADO),

    # ---- TRANSFERENCIAS Y MOVIMIENTOS ELECTRÓNICOS ----
    (r"CRED\s+BCA\s+ELECTR\s+INTERBANC", TipoMovimiento.TRANSFERENCIA_RECIBIDA),
    (r"Crédito\s+por\s+Transferencia", TipoMovimiento.TRANSFERENCIA_RECIBIDA),
    (r"Transferencia\s+por\s+CBU", TipoMovimiento.TRANSFERENCIA_ENVIADA),
    (r"Debito\s+Transf\.\s+HomeBanking", TipoMovimiento.HOMEBANKING),
    (r"Debito\s+DEBIN", TipoMovimiento.DEBIN),

    # ---- TARJETA DE DÉBITO ----
    # "Reverso Compra Visa" ANTES que "Compra Visa" para que matchee como DEVOLUCION
    (r"Reverso\s+Compra\s+Visa", TipoMovimiento.DEVOLUCION),
    (r"Compra\s+Visa\s+Débito", TipoMovimiento.COMPRA_DEBITO),

    # ---- ATM ----
    # "Devolución Extracción" ANTES que "Extracción" para que matchee como DEVOLUCION
    (r"Devolución\s+Extracción\s+ATM", TipoMovimiento.DEVOLUCION),
    (r"Extracción\s+ATM", TipoMovimiento.EXTRACCION_ATM),

    # ---- SERVICIOS ----
    (r"Pago\s+de\s+Servicios", TipoMovimiento.PAGO_SERVICIO),

    # ---- PRÉSTAMOS ----
    (r"Pago\s+Automático\s+de\s+Préstamo", TipoMovimiento.PRESTAMO_CUOTA),
    (r"Préstamos?\s*-?\s*Desembolso", TipoMovimiento.PRESTAMO_DESEMBOLSO),
    (r"Descto\.\s+Docum", TipoMovimiento.PRESTAMO_DESEMBOLSO),

    # ---- DEVOLUCIONES ----
    (r"Devolución\s+Imp\.?\s+Débitos", TipoMovimiento.DEVOLUCION),
    (r"Devolución", TipoMovimiento.DEVOLUCION),
    (r"Reintegro", TipoMovimiento.DEVOLUCION),

    # ---- EMBARGOS Y JUDICIALES ----
    (r"Embargo\s+Judicial", TipoMovimiento.EMBARGO),
    (r"Débito\s+por\s+Pago\s+de\s+Multa", TipoMovimiento.OTRO),
]

# Compilamos los patrones una sola vez al cargar el módulo.
# Cada regex usado mil veces sin recompilar = ahorro real de CPU.
_REGLAS: list[tuple[Pattern[str], TipoMovimiento]] = [
    (re.compile(patron, flags=re.IGNORECASE), tipo)
    for patron, tipo in _REGLAS_RAW
]


# ============================================================================
# API pública
# ============================================================================


def clasificar(concepto: str) -> TipoMovimiento:
    """Mapea un concepto del extracto a un TipoMovimiento.

    Args:
        concepto: texto descriptivo tal como aparece en el extracto
                  (ej: "Compra Visa Débito", "Comisión Permanencia saldo DR").

    Returns:
        El TipoMovimiento correspondiente. Si no matchea ninguna regla,
        devuelve TipoMovimiento.OTRO.

    Ejemplos:
        >>> clasificar("Comisión Permanencia saldo DR")
        <TipoMovimiento.COMISION: 'COMISION'>

        >>> clasificar("Impuesto Débitos y Créditos/DB")
        <TipoMovimiento.IMPUESTO_DEBITO_CREDITO: 'IMPUESTO_DEBITO_CREDITO'>

        >>> clasificar("Algo totalmente desconocido")
        <TipoMovimiento.OTRO: 'OTRO'>
    """
    for patron, tipo in _REGLAS:
        if patron.search(concepto):
            return tipo
    return TipoMovimiento.OTRO


def cantidad_de_reglas() -> int:
    """Retorna cuántas reglas hay cargadas. Útil para tests y monitoring."""
    return len(_REGLAS)