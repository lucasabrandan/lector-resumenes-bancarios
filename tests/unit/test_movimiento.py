"""
Tests del modelo de dominio MovimientoBancario.

Estos tests son la primera línea de defensa del proyecto: validan que
las reglas de negocio del modelo se respeten en cualquier circunstancia.

Correr con: pytest tests/unit/test_movimiento.py -v
"""

from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.domain.models import (
    MovimientoBancario,
    Moneda,
    SignoMovimiento,
    TipoMovimiento,
    crear_movimiento_desde_dict,
)


# ----------------------------------------------------------------------------
# Helpers (fixtures)
# ----------------------------------------------------------------------------


@pytest.fixture
def datos_movimiento_valido() -> dict:
    """Datos mínimos válidos para crear un MovimientoBancario."""
    return {
        "banco": "SUPERVIELLE",
        "cuenta": "05114474-003",
        "fecha": date(2024, 1, 2),
        "concepto": "Comisión Permanencia saldo DR",
        "importe": Decimal("30.00"),
        "signo": SignoMovimiento.DEBITO,
    }


# ----------------------------------------------------------------------------
# Tests de construcción válida
# ----------------------------------------------------------------------------


class TestConstruccionValida:
    """Casos donde el modelo se debe construir sin problemas."""

    def test_movimiento_minimo_valido(self, datos_movimiento_valido):
        """Un movimiento con los campos mínimos obligatorios se construye OK."""
        mov = MovimientoBancario(**datos_movimiento_valido)

        assert mov.banco == "SUPERVIELLE"
        assert mov.cuenta == "05114474-003"
        assert mov.importe == Decimal("30.00")
        assert mov.signo == SignoMovimiento.DEBITO
        assert mov.moneda == Moneda.ARS  # default
        assert mov.tipo == TipoMovimiento.OTRO  # default

    def test_movimiento_con_todos_los_campos(self, datos_movimiento_valido):
        """Un movimiento con todos los campos opcionales también funciona."""
        datos_completos = {
            **datos_movimiento_valido,
            "detalle_adicional": "Operación 317060434 Generada el 02/01/24",
            "numero_operacion": "0970802127",
            "saldo_posterior": Decimal("-24665.80"),
            "tipo": TipoMovimiento.COMISION,
            "moneda": Moneda.ARS,
            "archivo_origen": "supervielle_2024-01.pdf",
            "pagina_origen": 1,
        }
        mov = MovimientoBancario(**datos_completos)
        assert mov.tipo == TipoMovimiento.COMISION
        assert mov.pagina_origen == 1


# ----------------------------------------------------------------------------
# Tests de validación de tipos
# ----------------------------------------------------------------------------


class TestValidacionDecimal:
    """El campo importe DEBE ser Decimal y con exactamente 2 decimales."""

    def test_importe_se_redondea_a_dos_decimales(self, datos_movimiento_valido):
        """Un Decimal con más decimales se quantize a 2."""
        datos_movimiento_valido["importe"] = Decimal("100.456789")
        mov = MovimientoBancario(**datos_movimiento_valido)
        assert mov.importe == Decimal("100.46")

    def test_importe_no_puede_ser_cero(self, datos_movimiento_valido):
        """importe debe ser > 0 (un movimiento de 0 no tiene sentido)."""
        datos_movimiento_valido["importe"] = Decimal("0")
        with pytest.raises(ValidationError):
            MovimientoBancario(**datos_movimiento_valido)

    def test_importe_no_puede_ser_negativo(self, datos_movimiento_valido):
        """El signo se expresa en `signo`, NO en el importe."""
        datos_movimiento_valido["importe"] = Decimal("-30.00")
        with pytest.raises(ValidationError):
            MovimientoBancario(**datos_movimiento_valido)


class TestNormalizacionBanco:
    """El banco se normaliza siempre a mayúsculas."""

    def test_banco_minusculas_se_pasa_a_mayusculas(self, datos_movimiento_valido):
        datos_movimiento_valido["banco"] = "supervielle"
        mov = MovimientoBancario(**datos_movimiento_valido)
        assert mov.banco == "SUPERVIELLE"

    def test_banco_mixto_se_pasa_a_mayusculas(self, datos_movimiento_valido):
        datos_movimiento_valido["banco"] = "SuPerVielle"
        mov = MovimientoBancario(**datos_movimiento_valido)
        assert mov.banco == "SUPERVIELLE"


# ----------------------------------------------------------------------------
# Tests de campos rechazados / extra
# ----------------------------------------------------------------------------


class TestExtraForbid:
    """El modelo NO acepta campos no declarados."""

    def test_campo_extra_es_rechazado(self, datos_movimiento_valido):
        """Si un parser inventa un campo, el modelo lo rechaza."""
        datos_movimiento_valido["campo_inventado"] = "valor"
        with pytest.raises(ValidationError) as exc_info:
            MovimientoBancario(**datos_movimiento_valido)
        # El error debe mencionar el campo extra
        assert "campo_inventado" in str(exc_info.value)


# ----------------------------------------------------------------------------
# Tests de inmutabilidad
# ----------------------------------------------------------------------------


class TestInmutabilidad:
    """Una vez creado, no se puede modificar."""

    def test_no_se_puede_modificar_un_campo(self, datos_movimiento_valido):
        mov = MovimientoBancario(**datos_movimiento_valido)
        with pytest.raises(ValidationError):
            mov.importe = Decimal("999.00")

    def test_se_puede_crear_copia_modificada(self, datos_movimiento_valido):
        """El patrón correcto es usar .model_copy() para 'modificar'."""
        mov_original = MovimientoBancario(**datos_movimiento_valido)
        mov_nuevo = mov_original.model_copy(update={"importe": Decimal("999.00")})

        assert mov_original.importe == Decimal("30.00")  # no se tocó
        assert mov_nuevo.importe == Decimal("999.00")


# ----------------------------------------------------------------------------
# Tests de regresión basados en datos reales del extracto Supervielle
# ----------------------------------------------------------------------------


class TestCasosRealesSupervielle:
    """
    Casos extraídos del extracto real de Fundiciones Vanella SRL.
    Estos tests son la mejor garantía de que no rompemos lógica al refactorizar.
    """

    def test_comision_permanencia_saldo(self):
        """Movimiento típico de débito por comisión."""
        mov = MovimientoBancario(
            banco="SUPERVIELLE",
            cuenta="05114474-003",
            fecha=date(2024, 1, 2),
            concepto="Comisión Permanencia saldo DR",
            numero_operacion="0970802127",
            importe=Decimal("30.00"),
            signo=SignoMovimiento.DEBITO,
            saldo_posterior=Decimal("-24665.80"),
            tipo=TipoMovimiento.COMISION,
        )
        assert mov.tipo == TipoMovimiento.COMISION

    def test_compra_visa_debito(self):
        """Compra con Visa Débito en comercio."""
        mov = MovimientoBancario(
            banco="SUPERVIELLE",
            cuenta="05114474-003",
            fecha=date(2024, 1, 10),
            concepto="Compra Visa Débito",
            detalle_adicional="503134 LA CABANA 0110 11:30",
            numero_operacion="2690010828",
            importe=Decimal("29080.00"),
            signo=SignoMovimiento.DEBITO,
            saldo_posterior=Decimal("-205196.34"),
            tipo=TipoMovimiento.COMPRA_DEBITO,
        )
        assert mov.tipo == TipoMovimiento.COMPRA_DEBITO
        assert "LA CABANA" in mov.detalle_adicional

    def test_credito_transferencia_interbancaria(self):
        """Ingreso de dinero por transferencia (crédito)."""
        mov = MovimientoBancario(
            banco="SUPERVIELLE",
            cuenta="05114474-003",
            fecha=date(2024, 1, 4),
            concepto="CRED BCA ELECTR INTERBANC EXEN",
            detalle_adicional="Cuentas Propias - FUNDICIONES VANELLA SRL",
            numero_operacion="0002508600",
            importe=Decimal("60000.00"),
            signo=SignoMovimiento.CREDITO,
            saldo_posterior=Decimal("11201.31"),
            tipo=TipoMovimiento.TRANSFERENCIA_RECIBIDA,
        )
        assert mov.signo == SignoMovimiento.CREDITO

    def test_impuesto_ley_25413(self):
        """El movimiento clave para ARCA se modela correctamente.

        Notar que distinguimos si el impuesto se aplicó sobre un débito o un
        crédito (ver ADR-0006). El concepto termina en /DB en este caso.
        """
        mov = MovimientoBancario(
            banco="SUPERVIELLE",
            cuenta="05114474-003",
            fecha=date(2024, 1, 2),
            concepto="Impuesto Débitos y Créditos/DB",
            numero_operacion="0970802127",
            importe=Decimal("0.18"),
            signo=SignoMovimiento.DEBITO,
            saldo_posterior=Decimal("-24672.28"),
            tipo=TipoMovimiento.IMPUESTO_LEY_25413_SOBRE_DEBITOS,
        )
        assert mov.tipo == TipoMovimiento.IMPUESTO_LEY_25413_SOBRE_DEBITOS
        assert mov.importe == Decimal("0.18")


# ----------------------------------------------------------------------------
# Tests del factory helper
# ----------------------------------------------------------------------------


class TestFactoryHelper:
    """El helper crear_movimiento_desde_dict() debe ser equivalente al constructor."""

    def test_factory_funciona(self, datos_movimiento_valido):
        mov_constructor = MovimientoBancario(**datos_movimiento_valido)
        mov_factory = crear_movimiento_desde_dict(datos_movimiento_valido)
        assert mov_constructor == mov_factory