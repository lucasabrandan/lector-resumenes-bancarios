"""
Modelo de dominio: representación canónica de un movimiento bancario.

Este módulo define el "contrato" que todos los parsers de bancos deben cumplir.
Cualquier parser (Supervielle, Santander, Galicia, etc.) debe producir instancias
de `MovimientoBancario` para que el resto del sistema funcione homogéneamente.

Decisiones de diseño documentadas en: docs/adr/0001-modelo-dominio.md
"""

from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# ============================================================================
# Enums: valores cerrados validados
# ============================================================================


class Moneda(str, Enum):
    """Monedas soportadas. Heredar de `str` permite serialización JSON limpia."""

    ARS = "ARS"
    USD = "USD"


class TipoMovimiento(str, Enum):
    """
    Categorización de movimientos para reportes a ARCA.

    Se inspira en los conceptos reales encontrados en extractos de Supervielle.
    Mantener esta lista CERRADA: si un parser encuentra algo nuevo, agregar
    explícitamente acá y documentarlo en el ADR correspondiente.
    """

    # Movimientos de tarjeta / compra
    COMPRA_DEBITO = "COMPRA_DEBITO"      # Compra Visa Débito, Mastercard Débito
    EXTRACCION_ATM = "EXTRACCION_ATM"

    # Transferencias y débitos electrónicos
    TRANSFERENCIA_ENVIADA = "TRANSFERENCIA_ENVIADA"
    TRANSFERENCIA_RECIBIDA = "TRANSFERENCIA_RECIBIDA"
    DEBIN = "DEBIN"                       # Débito inmediato
    HOMEBANKING = "HOMEBANKING"

    # Cheques
    CHEQUE_DEPOSITADO = "CHEQUE_DEPOSITADO"
    CHEQUE_PAGADO = "CHEQUE_PAGADO"
    CHEQUE_RECHAZADO = "CHEQUE_RECHAZADO"

    # Servicios y préstamos
    PAGO_SERVICIO = "PAGO_SERVICIO"
    PRESTAMO_DESEMBOLSO = "PRESTAMO_DESEMBOLSO"
    PRESTAMO_CUOTA = "PRESTAMO_CUOTA"

    # Cargos del banco
    COMISION = "COMISION"
    IVA = "IVA"
    PERCEPCION_IVA = "PERCEPCION_IVA"
    # El Impuesto Ley 25.413 (al cheque) se separa en dos categorías porque
    # el banco lo reporta diferenciado: cuánto cobró sobre los débitos del
    # mes y cuánto sobre los créditos. Es lo que va a ARCA por separado.
    # Ver ADR-0006 para el por qué de la separación.
    IMPUESTO_LEY_25413_SOBRE_DEBITOS = "IMPUESTO_LEY_25413_SOBRE_DEBITOS"
    IMPUESTO_LEY_25413_SOBRE_CREDITOS = "IMPUESTO_LEY_25413_SOBRE_CREDITOS"
    IMPUESTO_SELLOS = "IMPUESTO_SELLOS"
    INTERES = "INTERES"

    # Ajustes y otros
    DEVOLUCION = "DEVOLUCION"
    EMBARGO = "EMBARGO"
    OTRO = "OTRO"


class SignoMovimiento(str, Enum):
    """
    Indica si el movimiento sale (DEBITO) o entra (CREDITO) en la cuenta.

    En cuentas corrientes esto es FUNDAMENTAL: el mismo concepto puede ser
    débito o crédito (ej: una transferencia es débito si la enviás, crédito
    si la recibís).
    """

    DEBITO = "DEBITO"      # Sale plata de la cuenta
    CREDITO = "CREDITO"    # Entra plata en la cuenta


# ============================================================================
# Modelo principal
# ============================================================================


class MovimientoBancario(BaseModel):
    """
    Representación canónica de un movimiento de cuenta bancaria.

    Inmutable (`frozen=True`): una vez creado, no se modifica. Si necesitás
    cambiar algo, creás uno nuevo con `.model_copy(update={...})`.

    Strict (`extra="forbid"`): no permite campos no declarados, lo que detecta
    bugs en parsers de inmediato.
    """

    model_config = ConfigDict(
        frozen=True,
        str_strip_whitespace=True,
        extra="forbid",
    )

    # ------------------------------------------------------------------
    # Identificación de origen
    # ------------------------------------------------------------------

    banco: str = Field(
        ...,
        min_length=2,
        max_length=50,
        description="Banco emisor en mayúsculas: 'SUPERVIELLE', 'SANTANDER', etc.",
    )

    cuenta: str = Field(
        ...,
        min_length=1,
        max_length=50,
        description="Identificador de la cuenta (ej: '05114474-003')",
    )

    # ------------------------------------------------------------------
    # Fechas
    # ------------------------------------------------------------------

    fecha: date = Field(
        ...,
        description="Fecha del movimiento según el extracto",
    )

    # ------------------------------------------------------------------
    # Descripción
    # ------------------------------------------------------------------

    concepto: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Texto crudo del concepto tal como aparece en el extracto",
    )

    detalle_adicional: Optional[str] = Field(
        None,
        max_length=1000,
        description="Líneas adicionales del concepto (CBU destino, comercio, etc.)",
    )

    numero_operacion: Optional[str] = Field(
        None,
        max_length=30,
        description="Número interno de operación que asigna el banco",
    )

    # ------------------------------------------------------------------
    # Montos (¡el corazón del asunto!)
    # ------------------------------------------------------------------

    importe: Decimal = Field(
        ...,
        gt=Decimal("0"),
        description="Monto absoluto del movimiento, SIEMPRE positivo. El signo "
        "se expresa con el campo `signo`. Esto evita ambigüedades.",
    )

    signo: SignoMovimiento = Field(
        ...,
        description="DEBITO (sale) o CREDITO (entra)",
    )

    saldo_posterior: Optional[Decimal] = Field(
        None,
        description="Saldo de la cuenta DESPUÉS de este movimiento, según el "
        "extracto. Permite validar la integridad al reprocesar.",
    )

    moneda: Moneda = Field(default=Moneda.ARS)
    tipo: TipoMovimiento = Field(default=TipoMovimiento.OTRO)

    # ------------------------------------------------------------------
    # Trazabilidad y deduplicación
    # ------------------------------------------------------------------

    hash_movimiento: Optional[str] = Field(
        None,
        max_length=64,
        description="Hash SHA-256 calculado sobre campos clave. Se llena en "
        "una etapa posterior, no en el parser.",
    )

    archivo_origen: Optional[str] = Field(
        None,
        max_length=255,
        description="Nombre del archivo del que se parseó. Útil para auditoría.",
    )

    pagina_origen: Optional[int] = Field(
        None,
        ge=1,
        description="Página del PDF donde apareció. Útil para debugging.",
    )

    # ------------------------------------------------------------------
    # Validators
    # ------------------------------------------------------------------

    @field_validator("importe", "saldo_posterior")
    @classmethod
    def dos_decimales(cls, v: Optional[Decimal]) -> Optional[Decimal]:
        """Garantiza que los montos siempre tengan exactamente 2 decimales.

        Esto previene basura tipo Decimal('123.4567') que rompería sumatorias
        y comparaciones de centavos."""
        if v is None:
            return None
        return v.quantize(Decimal("0.01"))

    @field_validator("banco")
    @classmethod
    def banco_uppercase(cls, v: str) -> str:
        """Normaliza el nombre del banco a mayúsculas para evitar duplicados
        tipo 'Supervielle' vs 'SUPERVIELLE'."""
        return v.upper()

    @model_validator(mode="after")
    def validar_consistencia(self) -> "MovimientoBancario":
        """Validaciones que dependen de más de un campo a la vez."""
        # Si es un impuesto a débitos/créditos, no debería ser un crédito
        # gigante (esos son devoluciones, que tienen otro tipo).
        # Esta es una regla de negocio: documentar bien por qué se valida.
        return self


# ============================================================================
# Helper para construir movimientos (Factory simple)
# ============================================================================


def crear_movimiento_desde_dict(data: dict) -> MovimientoBancario:
    """
    Factory helper para crear movimientos desde un diccionario.

    Útil en tests y en parsers, encapsula la creación y deja un único punto
    donde, si en el futuro agregamos lógica (ej: calcular el hash), se hace acá.
    """
    return MovimientoBancario.model_validate(data)