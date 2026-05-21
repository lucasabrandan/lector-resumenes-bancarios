"""Tests para el parser de SIRCREB (percepciones/retenciones IIBB)."""

from datetime import date
from decimal import Decimal

import pytest

from app.parsers.sircreb import (
    JURISDICCIONES,
    TipoRegistro,
    _detectar_formato,
    _formatear_cuit,
    _parse_cuit,
    _parse_decimal,
    _parse_fecha,
    parsear_sircreb,
)


# ============================================================================
# Helpers
# ============================================================================


class TestParseFecha:
    def test_fecha_normal(self):
        assert _parse_fecha("03/12/2015") == date(2015, 12, 3)

    def test_fecha_con_espacios(self):
        assert _parse_fecha("  01/01/2024  ") == date(2024, 1, 1)

    def test_fecha_invalida(self):
        with pytest.raises(ValueError):
            _parse_fecha("2024-01-01")


class TestParseDecimal:
    def test_con_punto(self):
        assert _parse_decimal("12342.03") == Decimal("12342.03")

    def test_con_coma(self):
        assert _parse_decimal("12342,03") == Decimal("12342.03")

    def test_vacio(self):
        assert _parse_decimal("") == Decimal("0")

    def test_con_ceros(self):
        assert _parse_decimal("00000559.89") == Decimal("559.89")


class TestParseCuit:
    def test_con_guiones(self):
        assert _parse_cuit("30-10010010-6") == "30100100106"

    def test_sin_guiones(self):
        assert _parse_cuit("30100100106") == "30100100106"


class TestFormatearCuit:
    def test_formateo(self):
        assert _formatear_cuit("30100100106") == "30-10010010-6"

    def test_ya_formateado(self):
        assert _formatear_cuit("30-10010010-6") == "30-10010010-6"


# ============================================================================
# Jurisdicciones
# ============================================================================


class TestJurisdicciones:
    def test_24_jurisdicciones(self):
        assert len(JURISDICCIONES) == 24

    def test_capital_federal(self):
        assert JURISDICCIONES[901] == "Capital Federal"

    def test_buenos_aires(self):
        assert JURISDICCIONES[902] == "Buenos Aires"

    def test_cordoba(self):
        assert JURISDICCIONES[904] == "Córdoba"

    def test_tucuman(self):
        assert JURISDICCIONES[924] == "Tucumán"


# ============================================================================
# Parser SIRCAR (Convenio Multilateral) — Percepciones
# ============================================================================


SIRCAR_PERCEPCIONES = """\
1,1,A,000100012345,30123456789,15/03/2024,50000.00,3.00,1500.00,011,904
2,1,B,000200054321,20987654321,20/03/2024,100000.00,2.50,2500.00,011,921
3,102,A,000300099999,27111222333,25/03/2024,30000.00,1.50,450.00,011,913
"""


class TestSircarPercepciones:
    def test_parsea_tres_registros(self):
        r = parsear_sircreb(SIRCAR_PERCEPCIONES, "percepciones.txt", "sircar_percepciones")
        assert len(r.percepciones) == 3
        assert len(r.errores) == 0

    def test_primer_registro(self):
        r = parsear_sircreb(SIRCAR_PERCEPCIONES, "percepciones.txt", "sircar_percepciones")
        p = r.percepciones[0]
        assert p.jurisdiccion == 904
        assert p.jurisdiccion_nombre == "Córdoba"
        assert p.cuit_agente == "30-12345678-9"
        assert p.fecha == date(2024, 3, 15)
        assert p.tipo == TipoRegistro.PERCEPCION
        assert p.monto_sujeto == Decimal("50000.00")
        assert p.alicuota == Decimal("3.00")
        assert p.monto_retenido == Decimal("1500.00")
        assert p.regimen == "011"

    def test_segundo_registro_santa_fe(self):
        r = parsear_sircreb(SIRCAR_PERCEPCIONES, "percepciones.txt", "sircar_percepciones")
        p = r.percepciones[1]
        assert p.jurisdiccion == 921
        assert p.jurisdiccion_nombre == "Santa Fe"
        assert p.monto_retenido == Decimal("2500.00")

    def test_nota_credito(self):
        r = parsear_sircreb(SIRCAR_PERCEPCIONES, "percepciones.txt", "sircar_percepciones")
        p = r.percepciones[2]
        assert p.tipo_comprobante == "102"
        assert p.jurisdiccion == 913
        assert p.jurisdiccion_nombre == "Mendoza"

    def test_formato_detectado(self):
        r = parsear_sircreb(SIRCAR_PERCEPCIONES, "percepciones.txt", "sircar_percepciones")
        assert r.formato_detectado == "SIRCAR Percepciones"


# ============================================================================
# Parser SIRCAR — Retenciones
# ============================================================================


SIRCAR_RETENCIONES = """\
1,1,1,000100012345,30123456789,10/04/2024,80000.00,2.00,1600.00,005,904
2,1,2,000200054321,20987654321,15/04/2024,60000.00,3.00,1800.00,005,908
"""


class TestSircarRetenciones:
    def test_parsea_dos_registros(self):
        r = parsear_sircreb(SIRCAR_RETENCIONES, "retenciones.txt", "sircar_retenciones")
        assert len(r.percepciones) == 2
        assert len(r.errores) == 0

    def test_primer_registro(self):
        r = parsear_sircreb(SIRCAR_RETENCIONES, "retenciones.txt", "sircar_retenciones")
        p = r.percepciones[0]
        assert p.tipo == TipoRegistro.RETENCION
        assert p.jurisdiccion == 904
        assert p.monto_retenido == Decimal("1600.00")

    def test_segundo_entre_rios(self):
        r = parsear_sircreb(SIRCAR_RETENCIONES, "retenciones.txt", "sircar_retenciones")
        p = r.percepciones[1]
        assert p.jurisdiccion == 908
        assert p.jurisdiccion_nombre == "Entre Ríos"


# ============================================================================
# Parser ARBA (Buenos Aires) — Percepciones
# ============================================================================


# Formato ancho fijo: CUIT(13) + Fecha(10) + TipoComp(1) + Letra(1) + Suc(4) + Emis(8) + MontoImp(12) + ImpPerc(11) + TipoOp(1) = 61
ARBA_PERCEPCIONES = """\
30-12345678-903/05/2024FA000100012345000050000.0000001500.00A
20-98765432-110/05/2024RB000200054321000100000.0000002500.00A
27-11122233-315/05/2024CA000300099999000030000.00-0000450.00A
"""


class TestArbaPercepciones:
    def test_parsea_tres_registros(self):
        r = parsear_sircreb(ARBA_PERCEPCIONES, "arba_perc.txt", "arba_percepciones")
        assert len(r.percepciones) == 3
        assert len(r.errores) == 0

    def test_jurisdiccion_buenos_aires(self):
        r = parsear_sircreb(ARBA_PERCEPCIONES, "arba_perc.txt", "arba_percepciones")
        for p in r.percepciones:
            assert p.jurisdiccion == 902
            assert p.jurisdiccion_nombre == "Buenos Aires"

    def test_primer_registro(self):
        r = parsear_sircreb(ARBA_PERCEPCIONES, "arba_perc.txt", "arba_percepciones")
        p = r.percepciones[0]
        assert p.cuit_agente == "30-12345678-9"
        assert p.fecha == date(2024, 5, 3)
        assert p.tipo_comprobante == "F"
        assert p.letra_comprobante == "A"
        assert p.monto_sujeto == Decimal("50000.00")
        assert p.monto_retenido == Decimal("1500.00")

    def test_formato_detectado(self):
        r = parsear_sircreb(ARBA_PERCEPCIONES, "arba_perc.txt", "arba_percepciones")
        assert r.formato_detectado == "ARBA Percepciones"


# ============================================================================
# Parser ARBA — Retenciones
# ============================================================================


# Formato ancho fijo: CUIT(13) + Fecha(10) + Suc(4) + Emis(8) + ImpRet(11) + TipoOp(1) = 47
# ImpRet 11 chars con 2 decimales: 99999999.99
ARBA_RETENCIONES = """\
30-12345678-903/05/202400010001234500001600.00A
20-98765432-110/05/202400020005432100001800.00A
27-11122233-315/05/202400030009999900000450.00B
"""


class TestArbaRetenciones:
    def test_parsea_dos_registros_ignora_baja(self):
        """La tercera línea tiene tipo B (baja), se ignora."""
        r = parsear_sircreb(ARBA_RETENCIONES, "arba_ret.txt", "arba_retenciones")
        assert len(r.percepciones) == 2
        assert len(r.errores) == 0

    def test_primer_registro(self):
        r = parsear_sircreb(ARBA_RETENCIONES, "arba_ret.txt", "arba_retenciones")
        p = r.percepciones[0]
        assert p.tipo == TipoRegistro.RETENCION
        assert p.monto_retenido == Decimal("1600.00")
        assert p.jurisdiccion == 902


# ============================================================================
# Detección de formato
# ============================================================================


class TestDeteccionFormato:
    def test_detecta_sircar_percepciones(self):
        lineas = SIRCAR_PERCEPCIONES.strip().splitlines()
        assert _detectar_formato(lineas, "percepciones.txt") == "sircar_percepciones"

    def test_detecta_sircar_retenciones(self):
        lineas = SIRCAR_RETENCIONES.strip().splitlines()
        assert _detectar_formato(lineas, "retenciones.txt") == "sircar_retenciones"

    def test_autodeteccion_sircar(self):
        r = parsear_sircreb(SIRCAR_PERCEPCIONES, "archivo.txt")
        assert r.formato_detectado == "SIRCAR Percepciones"
        assert len(r.percepciones) == 3


# ============================================================================
# Errores y edge cases
# ============================================================================


class TestErrores:
    def test_linea_vacia(self):
        r = parsear_sircreb("\n\n\n", "vacio.txt", "sircar_percepciones")
        assert len(r.percepciones) == 0
        assert len(r.errores) == 0

    def test_pocos_campos(self):
        r = parsear_sircreb("1,2,3", "malo.txt", "sircar_percepciones")
        assert len(r.percepciones) == 0
        assert len(r.errores) == 1

    def test_fecha_invalida(self):
        linea = "1,1,A,000100012345,30123456789,99/99/9999,50000.00,3.00,1500.00,011,904"
        r = parsear_sircreb(linea, "malo.txt", "sircar_percepciones")
        assert len(r.percepciones) == 0
        assert len(r.errores) == 1

    def test_formato_desconocido(self):
        r = parsear_sircreb("abc", "raro.txt", "formato_inexistente")
        assert len(r.percepciones) == 0
        assert len(r.errores) == 1
        assert "desconocido" in r.errores[0].lower() or "Formato" in r.errores[0]
