"""
Tests del clasificador de tipos de movimiento.

Estrategia:
    Cada regla del clasificador tiene su propio test. Esto puede parecer
    repetitivo pero es exactamente lo que queremos: si alguien cambia una
    regla por error, los tests fallan y nos avisan EXACTAMENTE qué se rompió.

    Además, estos tests sirven como DOCUMENTACIÓN VIVA: leyéndolos, otro dev
    entiende qué patrón mapea a qué tipo sin tener que leer la regex.

Patrón de test: pytest.mark.parametrize
    En lugar de escribir 20 tests casi idénticos, usamos parametrize para
    generar todos los casos con una sola función. Es la forma profesional
    de hacer tests de tipo "tabla de casos".
"""

import pytest

from app.domain.models import TipoMovimiento
from app.parsers.clasificador import cantidad_de_reglas, clasificar


# ============================================================================
# Tests de clasificación correcta — casos reales del PDF de Supervielle
# ============================================================================
#
# Cada tupla es: (concepto del PDF, tipo esperado).
# Todos los conceptos son STRINGS REALES sacados del PDF, no inventados.
# ============================================================================


CASOS_REALES = [
    # IMPUESTOS (Ley 25.413 separado en /DB y /CR — ver ADR-0006)
    ("Impuesto Débitos y Créditos/DB", TipoMovimiento.IMPUESTO_LEY_25413_SOBRE_DEBITOS),
    ("Impuesto Débitos y Créditos/CR", TipoMovimiento.IMPUESTO_LEY_25413_SOBRE_CREDITOS),
    ("IMPUESTO A LOS SELLOS", TipoMovimiento.IMPUESTO_SELLOS),

    # RETENCIONES (antes que percepciones)
    ("Retención de IVA", TipoMovimiento.RETENCION_IVA),
    ("Retención I.V.A.", TipoMovimiento.RETENCION_IVA),
    ("Retención de Ing. Brutos", TipoMovimiento.RETENCION_IIBB),
    ("Retención IIBB", TipoMovimiento.RETENCION_IIBB),
    ("Retención de Ganancias", TipoMovimiento.RETENCION_GANANCIAS),
    ("Retencion Ganancias", TipoMovimiento.RETENCION_GANANCIAS),
    ("Retención de SUSS", TipoMovimiento.RETENCION_SUSS),
    ("Retención Seg. Social", TipoMovimiento.RETENCION_SUSS),

    # PERCEPCIONES (antes que IVA simple)
    ("Percepción Ing. Brutos", TipoMovimiento.PERCEPCION_IIBB),
    ("Percepción de IIBB", TipoMovimiento.PERCEPCION_IIBB),
    ("Percepcion de Ing. Brutos", TipoMovimiento.PERCEPCION_IIBB),
    ("Percepción de Ganancias", TipoMovimiento.PERCEPCION_GANANCIAS),
    ("Percepción I.V.A. RG. 3337", TipoMovimiento.PERCEPCION_IVA),
    ("I.V.A. Percep. Resp. Inscripto", TipoMovimiento.PERCEPCION_IVA),

    # IVA SIMPLE
    ("IVA", TipoMovimiento.IVA),

    # INTERESES
    ("Intereses de Sobregiro", TipoMovimiento.INTERES),
    ("Contras.Ints.Sobreg.", TipoMovimiento.INTERES),

    # COMISIONES
    ("Comisión Permanencia saldo DR", TipoMovimiento.COMISION),
    ("Comision Mantenimiento Paquete", TipoMovimiento.COMISION),
    ("Comisión Exceso ATM", TipoMovimiento.COMISION),
    ("Comisión Consulta Cámara", TipoMovimiento.COMISION),
    ("Comisión Riesgo Contigente", TipoMovimiento.COMISION),
    ("Com.Cheque Pagado por clearing", TipoMovimiento.COMISION),
    ("COMIS.TRANSFERENCIAS", TipoMovimiento.COMISION),
    ("Gestión de Cobranza de Cheques", TipoMovimiento.COMISION),
    ("Comisiones Cheques O/Bancos", TipoMovimiento.COMISION),

    # CHEQUES
    ("Cheque Rechazado Dep. de 48 hs", TipoMovimiento.CHEQUE_RECHAZADO),
    ("Rechazo Cheque por Sin Fondos", TipoMovimiento.CHEQUE_RECHAZADO),
    ("Rechazo Por Cta Embargada S/F", TipoMovimiento.CHEQUE_RECHAZADO),
    ("Pago Cheque de Cámara Recibida", TipoMovimiento.CHEQUE_PAGADO),
    ("Acreditación Cheque Dep.48 Hs.", TipoMovimiento.CHEQUE_DEPOSITADO),
    ("Acreditación de Cheques 48 hs", TipoMovimiento.CHEQUE_DEPOSITADO),
    ("Depósito Cámara SPV 24 hs.", TipoMovimiento.CHEQUE_DEPOSITADO),

    # TRANSFERENCIAS
    ("CRED BCA ELECTR INTERBANC EXEN", TipoMovimiento.TRANSFERENCIA_RECIBIDA),
    ("Crédito por Transferencia", TipoMovimiento.TRANSFERENCIA_RECIBIDA),
    ("Transferencia por CBU", TipoMovimiento.TRANSFERENCIA_ENVIADA),
    ("Debito Transf. HomeBanking", TipoMovimiento.HOMEBANKING),
    ("Debito DEBIN", TipoMovimiento.DEBIN),

    # TARJETA
    ("Compra Visa Débito", TipoMovimiento.COMPRA_DEBITO),
    ("Reverso Compra Visa Débito", TipoMovimiento.DEVOLUCION),

    # ATM
    ("Extracción ATM", TipoMovimiento.EXTRACCION_ATM),
    ("Devolución Extracción ATM", TipoMovimiento.DEVOLUCION),

    # SERVICIOS Y PRÉSTAMOS
    ("Pago de Servicios", TipoMovimiento.PAGO_SERVICIO),
    ("Pago Automático de Préstamo", TipoMovimiento.PRESTAMO_CUOTA),
    ("Préstamos - Desembolso", TipoMovimiento.PRESTAMO_DESEMBOLSO),
    ("Descto. Docum.- Acreditación", TipoMovimiento.PRESTAMO_DESEMBOLSO),

    # DEVOLUCIONES
    ("Devolución Imp. Débitos", TipoMovimiento.DEVOLUCION),
    ("Reintegro 50% de Multa Cobrada", TipoMovimiento.DEVOLUCION),

    # EMBARGO
    ("Embargo Judicial", TipoMovimiento.EMBARGO),
]


@pytest.mark.parametrize("concepto, tipo_esperado", CASOS_REALES)
def test_clasificacion_casos_reales(concepto: str, tipo_esperado: TipoMovimiento):
    """Cada concepto real del PDF debe clasificarse al tipo esperado.

    Si este test falla, leé el output: pytest te dice exactamente qué
    caso falló, qué se esperaba y qué se devolvió.
    """
    resultado = clasificar(concepto)
    assert resultado == tipo_esperado, (
        f"Concepto '{concepto}' clasificó como {resultado.value} "
        f"pero se esperaba {tipo_esperado.value}"
    )


# ============================================================================
# Tests de orden de reglas — los casos sensibles a precedencia
# ============================================================================


class TestPrecedenciaDeReglas:
    """El orden de las reglas importa. Estos tests blindan ese orden.

    Si alguien reordena la lista de reglas y rompe la precedencia,
    estos tests fallan inmediatamente.
    """

    def test_percepcion_iva_no_es_iva_simple(self):
        """'Percepción I.V.A.' debe matchear PERCEPCION_IVA, no IVA."""
        assert clasificar("Percepción I.V.A. RG. 3337") == TipoMovimiento.PERCEPCION_IVA

    def test_percepcion_iibb_no_es_percepcion_iva(self):
        """'Percepción Ing. Brutos' es PERCEPCION_IIBB, no PERCEPCION_IVA."""
        assert clasificar("Percepción Ing. Brutos") == TipoMovimiento.PERCEPCION_IIBB

    def test_retencion_iva_no_es_iva_simple(self):
        """'Retención de IVA' es RETENCION_IVA, no IVA."""
        assert clasificar("Retención de IVA") == TipoMovimiento.RETENCION_IVA

    def test_retencion_ganancias_no_es_otro(self):
        """'Retención de Ganancias' es RETENCION_GANANCIAS."""
        assert clasificar("Retención de Ganancias") == TipoMovimiento.RETENCION_GANANCIAS

    def test_comision_riesgo_es_comision(self):
        """'Comisión Riesgo' es una COMISION, no un tipo aparte."""
        assert clasificar("Comisión Riesgo Contigente") == TipoMovimiento.COMISION

    def test_cheque_rechazado_no_es_cheque_pagado(self):
        """'Cheque Rechazado' debe matchear CHEQUE_RECHAZADO específicamente."""
        assert clasificar("Cheque Rechazado Dep. de 48 hs") == TipoMovimiento.CHEQUE_RECHAZADO

    def test_devolucion_extraccion_es_devolucion_no_extraccion(self):
        """Una devolución de extracción es DEVOLUCION, no EXTRACCION."""
        assert clasificar("Devolución Extracción ATM") == TipoMovimiento.DEVOLUCION


# ============================================================================
# Tests de robustez
# ============================================================================


class TestRobustez:
    """El clasificador no debe romperse ante inputs raros."""

    def test_concepto_vacio_devuelve_otro(self):
        """String vacío no matchea nada, retorna OTRO."""
        assert clasificar("") == TipoMovimiento.OTRO

    def test_concepto_desconocido_devuelve_otro(self):
        """Algo totalmente nuevo se marca como OTRO (no levanta excepción)."""
        assert clasificar("Concepto súper extraño que nadie había visto") == TipoMovimiento.OTRO

    def test_concepto_solo_espacios(self):
        """Solo whitespace retorna OTRO."""
        assert clasificar("   \t\n   ") == TipoMovimiento.OTRO

    def test_clasificador_es_case_insensitive(self):
        """Da igual mayúsculas o minúsculas en el patrón."""
        assert clasificar("compra visa débito") == TipoMovimiento.COMPRA_DEBITO
        assert clasificar("COMPRA VISA DÉBITO") == TipoMovimiento.COMPRA_DEBITO

    def test_clasificador_tiene_reglas_cargadas(self):
        """Sanity check: el módulo debe tener reglas cargadas al iniciarse."""
        assert cantidad_de_reglas() > 20, "Deberían haber al menos 20 reglas"