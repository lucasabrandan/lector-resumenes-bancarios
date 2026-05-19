"""
Tests del parser de Supervielle.

Estrategia de testing:
    - Tests UNITARIOS (este archivo): probamos cada método con strings
      hardcoded. Rápidos (< 1ms cada uno) y reproducibles.
    - Tests de INTEGRACIÓN (otra carpeta): tocan el PDF real. Más lentos
      pero validan el flujo completo.
"""

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from app.domain.models import SignoMovimiento
from app.parsers.supervielle_pdf import (
    ErrorValidacionSaldo,
    MovimientoCrudo,
    ParserSupervielle,
)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def parser() -> ParserSupervielle:
    """Una instancia fresca del parser por cada test."""
    return ParserSupervielle()


def crear_crudo(
    monto: str = "30.00",
    saldo: str = "-1000.00",
    concepto: str = "Test movimiento",
) -> MovimientoCrudo:
    """Factory helper: crea un MovimientoCrudo con valores razonables.

    Útil para que cada test solo escriba lo que importa para ese caso.
    """
    return MovimientoCrudo(
        fecha=date(2024, 1, 15),
        concepto=concepto,
        numero_operacion="0123456789",
        monto=Decimal(monto),
        saldo_posterior=Decimal(saldo),
        pagina=1,
    )


# ============================================================================
# Tests de helpers internos
# ============================================================================


class TestParserFecha:
    """El método _parsear_fecha convierte el formato argentino DD/MM/YY."""

    def test_fecha_2024(self, parser: ParserSupervielle):
        assert parser._parsear_fecha("03/01/24") == date(2024, 1, 3)

    def test_fecha_2025(self, parser: ParserSupervielle):
        assert parser._parsear_fecha("28/02/25") == date(2025, 2, 28)

    def test_fecha_invalida_explota(self, parser: ParserSupervielle):
        """Si el formato no es DD/MM/YY, queremos que explote claramente."""
        with pytest.raises(ValueError):
            parser._parsear_fecha("2024-01-03")  # formato ISO, no argentino


class TestParserMonto:
    """El método _parsear_monto maneja el formato 'X,XXX.XX' del PDF."""

    def test_monto_simple(self, parser: ParserSupervielle):
        assert parser._parsear_monto("30.00") == Decimal("30.00")

    def test_monto_con_separador_miles(self, parser: ParserSupervielle):
        assert parser._parsear_monto("60,000.00") == Decimal("60000.00")

    def test_monto_negativo(self, parser: ParserSupervielle):
        assert parser._parsear_monto("-48,650.65") == Decimal("-48650.65")

    def test_siempre_dos_decimales(self, parser: ParserSupervielle):
        assert parser._parsear_monto("1,234.56") == Decimal("1234.56")


# ============================================================================
# Tests del parser de línea
# ============================================================================


class TestParserLinea:
    """Tests del método _parsear_linea con líneas reales del PDF."""

    def test_linea_movimiento_simple(self, parser: ParserSupervielle):
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
        linea = "04/01/24 CRED BCA ELECTR INTERBANC EXEN 0002508600 60,000.00 11,201.31"
        crudo = parser._parsear_linea(linea, num_pagina=2)

        assert crudo is not None
        assert crudo.concepto == "CRED BCA ELECTR INTERBANC EXEN"
        assert crudo.monto == Decimal("60000.00")
        assert crudo.saldo_posterior == Decimal("11201.31")

    def test_linea_movimiento_con_saldo_negativo(self, parser: ParserSupervielle):
        linea = "09/01/24 Compra Visa Débito 2692515355 26,200.00 -125,659.14"
        crudo = parser._parsear_linea(linea, num_pagina=2)
        assert crudo is not None
        assert crudo.saldo_posterior == Decimal("-125659.14")

    def test_linea_de_continuacion_devuelve_none(self, parser: ParserSupervielle):
        linea = "Operación 317063975 Generada el 03/01/24"
        assert parser._parsear_linea(linea, num_pagina=2) is None

    def test_linea_de_header_devuelve_none(self, parser: ParserSupervielle):
        linea = "Fecha Concepto Débito Crédito Saldo"
        assert parser._parsear_linea(linea, num_pagina=2) is None

    def test_linea_de_subtotal_devuelve_none(self, parser: ParserSupervielle):
        linea = "SUBTOTAL -48,650.63"
        assert parser._parsear_linea(linea, num_pagina=2) is None

    def test_linea_vacia_devuelve_none(self, parser: ParserSupervielle):
        assert parser._parsear_linea("", num_pagina=2) is None
        assert parser._parsear_linea("   ", num_pagina=2) is None

    def test_linea_cuentas_propias_devuelve_none(self, parser: ParserSupervielle):
        assert parser._parsear_linea("Cuentas Propias", num_pagina=2) is None


# ============================================================================
# Tests de archivo inexistente
# ============================================================================


class TestParsearArchivoInexistente:
    def test_archivo_inexistente_lanza_filenotfound(
        self, parser: ParserSupervielle, tmp_path
    ):
        ruta_falsa = tmp_path / "no_existe.pdf"
        with pytest.raises(FileNotFoundError, match="No encontré"):
            parser.parsear_crudos(ruta_falsa)


# ============================================================================
# Tests de inferencia de signo (NUEVO en iteración 3.2)
# ============================================================================


class TestInferenciaSigno:
    """El método _inferir_signo determina DEBITO/CREDITO por variación de saldo."""

    def test_saldo_bajo_es_debito(self, parser: ParserSupervielle):
        """Caso típico: una compra. El saldo baja, es DEBITO."""
        # Saldo pasó de -1000 a -1030. Bajó 30 → DEBITO de 30.
        crudo = crear_crudo(monto="30.00", saldo="-1030.00")
        signo = parser._inferir_signo(crudo, saldo_anterior=Decimal("-1000.00"))
        assert signo == SignoMovimiento.DEBITO

    def test_saldo_subio_es_credito(self, parser: ParserSupervielle):
        """Caso típico: una transferencia recibida. El saldo sube, es CREDITO."""
        # Saldo pasó de -1000 a 59000. Subió 60000 → CREDITO de 60000.
        crudo = crear_crudo(monto="60000.00", saldo="59000.00")
        signo = parser._inferir_signo(crudo, saldo_anterior=Decimal("-1000.00"))
        assert signo == SignoMovimiento.CREDITO

    def test_de_negativo_a_negativo_pero_mas_negativo_es_debito(
        self, parser: ParserSupervielle
    ):
        """Edge case: ambos saldos negativos, pero más sobregirado."""
        # -500 → -800. Bajó 300, DEBITO.
        crudo = crear_crudo(monto="300.00", saldo="-800.00")
        signo = parser._inferir_signo(crudo, saldo_anterior=Decimal("-500.00"))
        assert signo == SignoMovimiento.DEBITO

    def test_de_negativo_a_positivo_es_credito(self, parser: ParserSupervielle):
        """Cuenta sobregirada que recibe transferencia y queda en azul."""
        # -100 → 900. Subió 1000, CREDITO.
        crudo = crear_crudo(monto="1000.00", saldo="900.00")
        signo = parser._inferir_signo(crudo, saldo_anterior=Decimal("-100.00"))
        assert signo == SignoMovimiento.CREDITO

    def test_centavos_chiquitos(self, parser: ParserSupervielle):
        """Movimientos de pocos centavos (típicos de impuestos)."""
        # -24665.80 → -24672.10. Bajó 6.30 → DEBITO.
        crudo = crear_crudo(monto="6.30", saldo="-24672.10")
        signo = parser._inferir_signo(crudo, saldo_anterior=Decimal("-24665.80"))
        assert signo == SignoMovimiento.DEBITO


# ============================================================================
# Tests de validación de saldo — el corazón del "fail loud"
# ============================================================================


class TestValidacionSaldo:
    """Si el monto no coincide con la variación, el parser DEBE explotar."""

    def test_monto_que_no_cuadra_explota(self, parser: ParserSupervielle):
        """El saldo bajó 30 pero el monto dice 50: inconsistente."""
        crudo = crear_crudo(monto="50.00", saldo="-1030.00")
        with pytest.raises(ErrorValidacionSaldo):
            parser._inferir_signo(crudo, saldo_anterior=Decimal("-1000.00"))

    def test_diferencia_de_un_centavo_explota(self, parser: ParserSupervielle):
        """Aunque sea un centavo, el parser explota. En contabilidad eso importa."""
        # Saldo bajó 30.01, pero el monto dice 30.00 (diferencia 1 centavo)
        crudo = crear_crudo(monto="30.00", saldo="-1030.01")
        with pytest.raises(ErrorValidacionSaldo):
            parser._inferir_signo(crudo, saldo_anterior=Decimal("-1000.00"))

    def test_error_incluye_datos_de_debugging(self, parser: ParserSupervielle):
        """El error debe mostrar info útil para que la contadora encuentre
        el problema en el PDF original."""
        crudo = crear_crudo(
            monto="50.00",
            saldo="-1030.00",
            concepto="Compra rara que no cuadra",
        )

        with pytest.raises(ErrorValidacionSaldo) as exc_info:
            parser._inferir_signo(crudo, saldo_anterior=Decimal("-1000.00"))

        # El mensaje debe ser informativo
        mensaje = str(exc_info.value)
        assert "Compra rara que no cuadra" in mensaje
        assert "Página" in mensaje
        assert "Diferencia" in mensaje

        # Y los atributos para debugging programático
        error = exc_info.value
        assert error.movimiento == crudo
        assert error.saldo_anterior == Decimal("-1000.00")
        assert error.variacion_esperada == Decimal("30.00")
        assert error.diferencia == Decimal("-20.00")  # esperado 30, monto 50


# ============================================================================
# Tests de extracción del número de cuenta
# ============================================================================


class TestExtraerNumeroCuenta:
    """El parser debe identificar la cuenta del header del PDF."""

    def test_regex_matchea_formato_estandar(self, parser: ParserSupervielle):
        """El header tipo 'CUENTA CORRIENTE EN PESOS Nro.: 05114474-003'."""
        texto = "CUENTA CORRIENTE EN PESOS Nro.: 05114474-003"
        match = parser._RE_NUMERO_CUENTA.search(texto)
        assert match is not None
        assert match.group("cuenta") == "05114474-003"

    def test_regex_es_insensible_a_mayusculas(self, parser: ParserSupervielle):
        texto = "cuenta corriente en pesos nro: 12345678-001"
        match = parser._RE_NUMERO_CUENTA.search(texto)
        assert match is not None
        assert match.group("cuenta") == "12345678-001"


# ============================================================================
# Tests de líneas de detalle adicional (iteración 3.4)
# ============================================================================


class TestDetalleAdicional:
    """El parser captura líneas de detalle que siguen a cada movimiento."""

    def test_movimiento_sin_detalle(self, parser: ParserSupervielle):
        """Un movimiento solo, sin líneas de continuación."""
        texto = "03/01/24 Comisión Permanencia saldo DR 0970804935 30.00 -48,680.65"
        crudos = parser._parsear_pagina(texto, num_pagina=1)
        assert len(crudos) == 1
        assert crudos[0].detalle_adicional is None

    def test_movimiento_con_una_linea_detalle(self, parser: ParserSupervielle):
        """Compra Visa con el nombre del comercio debajo."""
        texto = (
            "09/01/24 Compra Visa Débito 2692515355 26,200.00 -125,659.14\n"
            "70760 MERPAGO DIEGO 0110 00:13"
        )
        crudos = parser._parsear_pagina(texto, num_pagina=1)
        assert len(crudos) == 1
        assert crudos[0].detalle_adicional == "70760 MERPAGO DIEGO 0110 00:13"

    def test_movimiento_con_varias_lineas_detalle(self, parser: ParserSupervielle):
        """Transferencia con 'Cuentas Propias' y CBU/CUIT destino."""
        texto = (
            "04/01/24 CRED BCA ELECTR INTERBANC EXEN 0002508600 60,000.00 11,201.31\n"
            "Cuentas Propias\n"
            "30717751848 FUNDICIONES VANELLA SRL"
        )
        crudos = parser._parsear_pagina(texto, num_pagina=1)
        assert len(crudos) == 1
        assert crudos[0].detalle_adicional == (
            "Cuentas Propias\n30717751848 FUNDICIONES VANELLA SRL"
        )

    def test_pago_servicio_con_identificacion(self, parser: ParserSupervielle):
        """Pago de servicios con comercio + IDENTIFICACION."""
        texto = (
            "19/01/24 Pago de Servicios 2633023378 8,397.28 250,478.66\n"
            "626832 MOVISTARHOGAR 0119 15:09\n"
            "IDENTIFICACION: 0530263259894"
        )
        crudos = parser._parsear_pagina(texto, num_pagina=1)
        assert len(crudos) == 1
        assert "MOVISTARHOGAR" in crudos[0].detalle_adicional
        assert "IDENTIFICACION: 0530263259894" in crudos[0].detalle_adicional

    def test_detalle_no_incluye_subtotal(self, parser: ParserSupervielle):
        """SUBTOTAL es ruido del PDF, no detalle del movimiento."""
        texto = (
            "02/01/24 IVA 0207502811 0.01 -48,650.63\n"
            "SUBTOTAL -48,650.63\n"
            "1"
        )
        crudos = parser._parsear_pagina(texto, num_pagina=1)
        assert len(crudos) == 1
        assert crudos[0].detalle_adicional is None

    def test_detalle_no_incluye_numero_pagina(self, parser: ParserSupervielle):
        """Los números sueltos (paginado del PDF) no son detalle."""
        texto = (
            "02/01/24 IVA 0207502811 0.01 -48,650.63\n"
            "2"
        )
        crudos = parser._parsear_pagina(texto, num_pagina=1)
        assert len(crudos) == 1
        assert crudos[0].detalle_adicional is None

    def test_dos_movimientos_cada_uno_con_su_detalle(self, parser: ParserSupervielle):
        """Cada movimiento recibe solo SUS líneas de detalle."""
        texto = (
            "03/01/24 Comisión Permanencia saldo DR 0970804935 30.00 -48,680.65\n"
            "Operación 317063975 Generada el 03/01/24\n"
            "03/01/24 IVA 0970804935 6.30 -48,686.95\n"
            "Operación 317063975 Generada el 03/01/24"
        )
        crudos = parser._parsear_pagina(texto, num_pagina=1)
        assert len(crudos) == 2
        assert "317063975" in crudos[0].detalle_adicional
        assert "317063975" in crudos[1].detalle_adicional

    def test_movimiento_con_operacion_detalle(self, parser: ParserSupervielle):
        """La línea 'Operación XXX Generada el...' es detalle real."""
        texto = (
            "02/01/24 Comisión Permanencia saldo DR 0970802127 30.00 -24,665.80\n"
            "Operación 317060434 Generada el 02/01/24"
        )
        crudos = parser._parsear_pagina(texto, num_pagina=1)
        assert len(crudos) == 1
        assert crudos[0].detalle_adicional == "Operación 317060434 Generada el 02/01/24"

    def test_detalle_no_incluye_headers_repetidos(self, parser: ParserSupervielle):
        """Los headers que se repiten en cada página no son detalle."""
        texto = (
            "02/01/24 IVA 0207502811 0.01 -48,650.63\n"
            "SUBTOTAL -48,650.63\n"
            "1\n"
            "I.V.A. RESPONSABLE INSCRIPTO - C.U.I.T. Nº 33-50000517-9\n"
            "RESUMEN DE CUENTA DESDE 01/01/24 HASTA 24/06/25\n"
            "CUENTA CORRIENTE EN PESOS Nro.: 05114474-003\n"
            "DETALLE DE MOVIMIENTOS\n"
            "Fecha Concepto Débito Crédito Saldo"
        )
        crudos = parser._parsear_pagina(texto, num_pagina=1)
        assert len(crudos) == 1
        assert crudos[0].detalle_adicional is None