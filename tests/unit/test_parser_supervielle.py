"""
Tests del parser de Supervielle.

Estrategia de testing:
    - Tests UNITARIOS que NO tocan archivos: probamos cada método privado
      con strings hardcoded. Son rápidos (< 1ms cada uno) y reproducibles.
    - Tests de INTEGRACIÓN que sí tocan el PDF real: corren en CI con un
      fixture (data/raw/...). Más lentos pero validan el flujo completo.

Estructura:
    tests/unit/test_parser_supervielle.py     ← este archivo (sin archivos)
    tests/integration/test_parser_supervielle_integracion.py  ← con PDF real
"""

from datetime import date
from decimal import Decimal

import pytest

from app.parsers.supervielle_pdf import MovimientoCrudo, ParserSupervielle


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def parser() -> ParserSupervielle:
    """Una instancia fresca del parser por cada test."""
    return ParserSupervielle()


# ============================================================================
# Tests de helpers internos (los más simples y rápidos)
# ============================================================================


class TestParserFecha:
    """El método _parsear_fecha convierte el formato argentino DD/MM/YY."""

    def test_fecha_2024(self, parser: ParserSupervielle):
        assert parser._parsear_fecha("03/01/24") == date(2024, 1, 3)

    def test_fecha_2025(self, parser: ParserSupervielle):
        assert parser._parsear_fecha("28/02/25") == date(2025, 2, 28)

    def test_fecha_invalida_explota(self, parser: ParserSupervielle):
        """Si el formato no es DD/MM/YY, queremos que explote claramente,
        no que devuelva una fecha incorrecta silenciosamente."""
        with pytest.raises(ValueError):
            parser._parsear_fecha("2024-01-03")  # formato ISO, no argentino


class TestParserMonto:
    """El método _parsear_monto maneja el formato 'X,XXX.XX' del PDF."""

    def test_monto_simple(self, parser: ParserSupervielle):
        assert parser._parsear_monto("30.00") == Decimal("30.00")

    def test_monto_con_separador_miles(self, parser: ParserSupervielle):
        """'60,000.00' (formato Supervielle) → Decimal('60000.00')."""
        assert parser._parsear_monto("60,000.00") == Decimal("60000.00")

    def test_monto_negativo(self, parser: ParserSupervielle):
        """Los saldos pueden ser negativos (cuenta en sobregiro)."""
        assert parser._parsear_monto("-48,650.65") == Decimal("-48650.65")

    def test_siempre_dos_decimales(self, parser: ParserSupervielle):
        """Garantía contra basura tipo Decimal('100.456789')."""
        # El parser asume entrada con 2 decimales, así que esto solo prueba
        # que el quantize no rompe entrada bien formada.
        resultado = parser._parsear_monto("1,234.56")
        assert resultado == Decimal("1234.56")
        # Pydantic acepta este Decimal como válido (2 decimales exactos)


# ============================================================================
# Tests del parser de línea (el corazón del extractor)
# ============================================================================


class TestParserLinea:
    """Tests del método _parsear_linea con líneas reales del PDF."""

    def test_linea_movimiento_simple(self, parser: ParserSupervielle):
        """Caso típico: una comisión."""
        linea = "03/01/24 Comisión Permanencia saldo DR 0970804935 30.00 -48,680.65"
        crudo = parser._parsear_linea(linea, num_pagina=2)

        assert crudo is not None
        assert crudo.fecha == date(2024, 1, 3)
        assert crudo.concepto == "Comisión Permanencia saldo DR"
        assert crudo.numero_operacion == "0970804935"
        assert crudo.monto == Decimal("30.00")
        assert crudo.saldo_posterior == Decimal("-48680.65")
        assert crudo.pagina == 2

    def test_linea_movimiento_con_monto_grande(self, parser: ParserSupervielle):
        """Caso con separador de miles (crédito por transferencia)."""
        linea = "04/01/24 CRED BCA ELECTR INTERBANC EXEN 0002508600 60,000.00 11,201.31"
        crudo = parser._parsear_linea(linea, num_pagina=2)

        assert crudo is not None
        assert crudo.concepto == "CRED BCA ELECTR INTERBANC EXEN"
        assert crudo.monto == Decimal("60000.00")
        assert crudo.saldo_posterior == Decimal("11201.31")

    def test_linea_movimiento_con_saldo_negativo(self, parser: ParserSupervielle):
        """Caso típico de cuenta corriente: saldo en sobregiro."""
        linea = "09/01/24 Compra Visa Débito 2692515355 26,200.00 -125,659.14"
        crudo = parser._parsear_linea(linea, num_pagina=2)

        assert crudo is not None
        assert crudo.saldo_posterior == Decimal("-125659.14")

    def test_linea_de_continuacion_devuelve_none(self, parser: ParserSupervielle):
        """Las líneas de detalle no son movimientos."""
        linea = "Operación 317063975 Generada el 03/01/24"
        crudo = parser._parsear_linea(linea, num_pagina=2)
        assert crudo is None

    def test_linea_de_header_devuelve_none(self, parser: ParserSupervielle):
        """El header del PDF no es un movimiento."""
        linea = "Fecha Concepto Débito Crédito Saldo"
        crudo = parser._parsear_linea(linea, num_pagina=2)
        assert crudo is None

    def test_linea_de_subtotal_devuelve_none(self, parser: ParserSupervielle):
        """Las líneas de SUBTOTAL no son movimientos."""
        linea = "SUBTOTAL -48,650.63"
        crudo = parser._parsear_linea(linea, num_pagina=2)
        assert crudo is None

    def test_linea_vacia_devuelve_none(self, parser: ParserSupervielle):
        """Robustez: líneas vacías no deberían romper el parser."""
        assert parser._parsear_linea("", num_pagina=2) is None
        assert parser._parsear_linea("   ", num_pagina=2) is None

    def test_linea_cuentas_propias_devuelve_none(self, parser: ParserSupervielle):
        """Otra línea de detalle típica."""
        linea = "Cuentas Propias"
        crudo = parser._parsear_linea(linea, num_pagina=2)
        assert crudo is None


# ============================================================================
# Tests del archivo completo (sin todavía tocar el PDF real)
# ============================================================================


class TestParsearArchivoInexistente:
    """Comportamiento ante errores de archivo."""

    def test_archivo_inexistente_lanza_filenotfound(
        self, parser: ParserSupervielle, tmp_path
    ):
        """Si el archivo no existe, error claro."""
        from pathlib import Path

        ruta_falsa = tmp_path / "no_existe.pdf"
        with pytest.raises(FileNotFoundError, match="No encontré"):
            parser.parsear_crudos(ruta_falsa)
