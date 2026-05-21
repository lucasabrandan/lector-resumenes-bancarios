"""Tests del parser de Mis Comprobantes ARCA."""

from datetime import date
from decimal import Decimal

import pytest

from app.parsers.arca_comprobantes import (
    ComprobanteARCA,
    parsear_csv,
    _parsear_fecha,
    _parsear_decimal,
    _normalizar_encabezado,
)


# --- Helpers ---

CSV_HEADER = "Fecha;Tipo;Punto de Venta;Número Desde;Número Hasta;Cód. Autorización;Tipo Doc. Receptor;Nro. Doc. Receptor;Denominación Receptor;Tipo Cambio;Moneda;Imp. Neto Gravado;Imp. Neto No Gravado;Imp. Op. Exentas;IVA;Imp. Total"

def _csv_line(
    fecha="2025-06-15",
    tipo="Factura C",
    pv="3",
    nro_desde="120",
    nro_hasta="120",
    cod_aut="12345678901234",
    tipo_doc="80",
    nro_doc="20123456789",
    denom="CLIENTE DE PRUEBA",
    tc="1",
    moneda="PES",
    neto="10000,00",
    no_grav="0,00",
    exento="0,00",
    iva="0,00",
    total="10000,00",
):
    return f"{fecha};{tipo};{pv};{nro_desde};{nro_hasta};{cod_aut};{tipo_doc};{nro_doc};{denom};{tc};{moneda};{neto};{no_grav};{exento};{iva};{total}"


def _build_csv(*lines):
    all_lines = [CSV_HEADER] + list(lines)
    return "\n".join(all_lines).encode("utf-8")


# --- Tests de utilidades ---

class TestParsearFecha:
    def test_formato_iso(self):
        assert _parsear_fecha("2025-06-15") == date(2025, 6, 15)

    def test_formato_barra(self):
        assert _parsear_fecha("15/06/2025") == date(2025, 6, 15)

    def test_formato_guion_dmy(self):
        assert _parsear_fecha("15-06-2025") == date(2025, 6, 15)

    def test_formato_invalido(self):
        with pytest.raises(ValueError):
            _parsear_fecha("junio 2025")


class TestParsearDecimal:
    def test_con_coma(self):
        assert _parsear_decimal("10.500,50") == Decimal("10500.50")

    def test_vacio(self):
        assert _parsear_decimal("") == Decimal("0.00")

    def test_guion(self):
        assert _parsear_decimal("-") == Decimal("0.00")

    def test_sin_separador_miles(self):
        assert _parsear_decimal("1500,00") == Decimal("1500.00")


class TestNormalizarEncabezado:
    def test_acentos(self):
        assert _normalizar_encabezado("Cód. Autorización") == "cod autorizacion"

    def test_imp_total(self):
        assert "imp total" in _normalizar_encabezado("Imp. Total")


# --- Tests del parser CSV ---

class TestParsearCSV:
    def test_un_comprobante(self):
        csv = _build_csv(_csv_line())
        result = parsear_csv(csv)
        assert len(result) == 1
        c = result[0]
        assert c.fecha == date(2025, 6, 15)
        assert c.tipo_comprobante == "Factura C"
        assert c.punto_venta == 3
        assert c.numero_desde == 120
        assert c.importe_total == Decimal("10000.00")

    def test_multiples_comprobantes(self):
        csv = _build_csv(
            _csv_line(fecha="2025-06-01", total="5000,00"),
            _csv_line(fecha="2025-06-15", total="3000,00"),
            _csv_line(fecha="2025-06-20", total="2000,00"),
        )
        result = parsear_csv(csv)
        assert len(result) == 3
        totales = [c.importe_total for c in result]
        assert totales == [Decimal("5000.00"), Decimal("3000.00"), Decimal("2000.00")]

    def test_nota_de_credito(self):
        csv = _build_csv(
            _csv_line(tipo="Nota de Crédito C", total="1500,00"),
        )
        result = parsear_csv(csv)
        assert len(result) == 1
        c = result[0]
        assert c.es_nota_credito is True
        assert c.importe_con_signo == Decimal("-1500.00")

    def test_factura_no_es_nota_credito(self):
        csv = _build_csv(_csv_line(tipo="Factura C"))
        c = parsear_csv(csv)[0]
        assert c.es_nota_credito is False
        assert c.importe_con_signo == Decimal("10000.00")

    def test_fila_titulo_antes_de_encabezado(self):
        """ARCA a veces pone una fila titulo como 'Mis Comprobantes' antes del encabezado."""
        raw = "Mis Comprobantes - Emitidos\n" + CSV_HEADER + "\n" + _csv_line()
        result = parsear_csv(raw.encode("utf-8"))
        assert len(result) == 1

    def test_filas_vacias_ignoradas(self):
        csv = _build_csv(
            _csv_line(),
            ";;;;;;;;;;;;;;;",  # fila vacía
            _csv_line(total="2000,00"),
        )
        result = parsear_csv(csv)
        assert len(result) == 2

    def test_csv_vacio(self):
        result = parsear_csv(b"")
        assert result == []

    def test_formato_fecha_barra(self):
        csv = _build_csv(_csv_line(fecha="15/06/2025"))
        result = parsear_csv(csv)
        assert result[0].fecha == date(2025, 6, 15)

    def test_separador_coma(self):
        """Algunos CSV usan coma en vez de punto y coma."""
        header = CSV_HEADER.replace(";", ",")
        linea = _csv_line(total="5000,00").replace(";", ",")
        # Cuando el separador es coma, los decimales no usan coma
        # Ajustamos para que el total sea un número sin coma decimal
        header_coma = "Fecha,Tipo,Punto de Venta,Número Desde,Número Hasta,Cód. Autorización,Tipo Doc. Receptor,Nro. Doc. Receptor,Denominación Receptor,Tipo Cambio,Moneda,Imp. Neto Gravado,Imp. Neto No Gravado,Imp. Op. Exentas,IVA,Imp. Total"
        linea_coma = "2025-06-15,Factura C,3,120,120,12345678901234,80,20123456789,CLIENTE,1,PES,5000.00,0.00,0.00,0.00,5000.00"
        raw = (header_coma + "\n" + linea_coma).encode("utf-8")
        result = parsear_csv(raw)
        assert len(result) == 1


class TestComprobanteARCA:
    def test_importe_con_signo_factura(self):
        c = ComprobanteARCA(
            fecha=date(2025, 1, 1), tipo_comprobante="Factura C",
            punto_venta=1, numero_desde=1, numero_hasta=1,
            cod_autorizacion=None, tipo_doc_receptor=None,
            nro_doc_receptor=None, denominacion_receptor=None,
            moneda="PES", tipo_cambio=Decimal("1"), importe_total=Decimal("5000"),
        )
        assert c.importe_con_signo == Decimal("5000")

    def test_importe_con_signo_nota_debito(self):
        c = ComprobanteARCA(
            fecha=date(2025, 1, 1), tipo_comprobante="Nota de Débito C",
            punto_venta=1, numero_desde=1, numero_hasta=1,
            cod_autorizacion=None, tipo_doc_receptor=None,
            nro_doc_receptor=None, denominacion_receptor=None,
            moneda="PES", tipo_cambio=Decimal("1"), importe_total=Decimal("500"),
        )
        assert c.es_nota_credito is False
        assert c.importe_con_signo == Decimal("500")
