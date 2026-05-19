"""
Parser de extractos en PDF del Banco Supervielle (cuenta corriente).

Este es el primer parser concreto del proyecto. Cuando agreguemos más bancos
(Santander, Galicia, BBVA), todos heredarán de una clase abstracta común
`ParserBancoBase` (Strategy Pattern). Por ahora, vamos directo: primero hacer
que UNO funcione bien antes de generalizar.

Decisiones de diseño documentadas en: docs/adr/0005-parsear-pdf-no-xlsx.md

Estado actual (Iteración 3.2):
    ✅ Extracción cruda de movimientos del PDF con regex.
    ✅ Inferencia del signo (DEBITO/CREDITO) por variación de saldo.
    ✅ Validación cruzada: |variación de saldo| debe == monto.
    ✅ Conversión a MovimientoBancario (modelo de dominio).
    ⏳ Próximas iteraciones: clasificación de tipo, detalle adicional.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pdfplumber

from app.domain.models import MovimientoBancario, SignoMovimiento, TipoMovimiento


# ============================================================================
# Excepciones del dominio del parser
# ============================================================================


class ParserError(Exception):
    """Excepción base del parser. Permite capturar todas las excepciones
    del parser con un solo `except ParserError`."""


class ErrorValidacionSaldo(ParserError):
    """El monto extraído del PDF no coincide con la variación de saldo.

    Esto indica que el parser cometió un error (probablemente la regex
    matcheó mal), o que el PDF tiene una inconsistencia interna.

    En lugar de "adivinar" o devolver datos incorrectos silenciosamente,
    elegimos hacer "fail loud, fail early": explotar con un error claro
    que indique exactamente dónde está el problema.

    Atributos para debugging:
        movimiento: el MovimientoCrudo problemático.
        saldo_anterior: el saldo del movimiento previo.
        variacion_esperada: |saldo_actual - saldo_anterior|.
        diferencia: variacion_esperada - monto.
    """

    def __init__(
        self,
        movimiento: "MovimientoCrudo",
        saldo_anterior: Decimal,
    ) -> None:
        self.movimiento = movimiento
        self.saldo_anterior = saldo_anterior
        self.variacion_esperada = abs(movimiento.saldo_posterior - saldo_anterior)
        self.diferencia = self.variacion_esperada - movimiento.monto

        super().__init__(
            f"\n  Inconsistencia en movimiento del PDF:\n"
            f"    Fecha:      {movimiento.fecha}\n"
            f"    Concepto:   {movimiento.concepto}\n"
            f"    Página:     {movimiento.pagina}\n"
            f"    Monto:      ${movimiento.monto:,}\n"
            f"    Variación:  ${self.variacion_esperada:,} "
            f"(saldo {saldo_anterior:,} → {movimiento.saldo_posterior:,})\n"
            f"    Diferencia: ${self.diferencia:,}"
        )


# ============================================================================
# DTO interno del parser
# ============================================================================


@dataclass(frozen=True, slots=True)
class MovimientoCrudo:
    """Movimiento tal como aparece en el PDF, sin interpretar.

    Es inmutable (frozen) y eficiente en memoria (slots).

    Lo separamos del modelo de dominio `MovimientoBancario` a propósito:
    el parser produce estos crudos, y una etapa de transformación los
    convierte al modelo canónico. Esta separación se llama
    "Anti-Corruption Layer": el formato del banco no contamina el dominio.
    """

    fecha: date
    concepto: str
    numero_operacion: str
    monto: Decimal             # SIEMPRE positivo (signo se infiere después)
    saldo_posterior: Decimal   # puede ser negativo si la cuenta está en sobregiro
    pagina: int                # para trazabilidad / debugging


# ============================================================================
# Parser
# ============================================================================


class ParserSupervielle:
    """Parser para extractos en PDF del Banco Supervielle (cuenta corriente).

    Uso típico:
        parser = ParserSupervielle()

        # Para uso de producción (con validación):
        movimientos = parser.parsear(Path("extracto.pdf"))
        # → list[MovimientoBancario] con signo inferido y validado

        # Para debugging (solo extracción, sin validación):
        crudos = parser.parsear_crudos(Path("extracto.pdf"))
        # → list[MovimientoCrudo]
    """

    BANCO = "SUPERVIELLE"

    # Patrón de cada movimiento dentro del PDF.
    # Formato observado: "DD/MM/YY  Concepto  NumeroOperacion  Monto  Saldo"
    _RE_MOVIMIENTO = re.compile(
        r"^"
        r"(?P<fecha>\d{2}/\d{2}/\d{2})\s+"
        r"(?P<concepto>.+?)\s+"
        r"(?P<numero_op>\d{6,15})\s+"
        r"(?P<monto>-?[\d,]+\.\d{2})\s+"
        r"(?P<saldo>-?[\d,]+\.\d{2})"
        r"\s*$"
    )

    # Patrón para extraer el número de cuenta del header.
    # Ej: "CUENTA CORRIENTE EN PESOS Nro.: 05114474-003"
    _RE_NUMERO_CUENTA = re.compile(
        r"CUENTA\s+CORRIENTE\s+EN\s+PESOS\s+Nro\.?\s*:?\s*(?P<cuenta>[\d\-]+)",
        re.IGNORECASE,
    )

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

    def parsear(self, ruta_pdf: Path) -> list[MovimientoBancario]:
        """Parsea el PDF y devuelve movimientos validados del modelo de dominio.

        Raises:
            FileNotFoundError: si el archivo no existe.
            ValueError: si el archivo no parece ser un extracto de Supervielle.
            ErrorValidacionSaldo: si algún movimiento no cuadra (el parser
                explota antes que devolver basura).
        """
        crudos = self.parsear_crudos(ruta_pdf)
        numero_cuenta = self._extraer_numero_cuenta(ruta_pdf)
        return self._convertir_a_dominio(crudos, numero_cuenta)

    def parsear_crudos(self, ruta_pdf: Path) -> list[MovimientoCrudo]:
        """Devuelve solo los movimientos crudos del PDF, sin validar.

        Útil para debugging y exploración. Para producción usar `parsear()`.
        """
        if not ruta_pdf.exists():
            raise FileNotFoundError(f"No encontré el archivo: {ruta_pdf}")

        movimientos: list[MovimientoCrudo] = []

        with pdfplumber.open(ruta_pdf) as pdf:
            for num_pagina, pagina in enumerate(pdf.pages, start=1):
                texto = pagina.extract_text() or ""
                movimientos.extend(self._parsear_pagina(texto, num_pagina))

        if not movimientos:
            raise ValueError(
                f"No se encontraron movimientos en {ruta_pdf}. "
                "¿Es realmente un extracto de Supervielle?"
            )

        return movimientos

    # ------------------------------------------------------------------
    # Métodos privados — extracción de texto
    # ------------------------------------------------------------------

    def _parsear_pagina(self, texto: str, num_pagina: int) -> list[MovimientoCrudo]:
        """Extrae los movimientos crudos de UNA página del PDF."""
        movimientos: list[MovimientoCrudo] = []
        for linea in texto.split("\n"):
            crudo = self._parsear_linea(linea.strip(), num_pagina)
            if crudo is not None:
                movimientos.append(crudo)
        return movimientos

    def _parsear_linea(self, linea: str, num_pagina: int) -> MovimientoCrudo | None:
        """Intenta parsear UNA línea. Devuelve None si no es un movimiento."""
        match = self._RE_MOVIMIENTO.match(linea)
        if match is None:
            return None

        return MovimientoCrudo(
            fecha=self._parsear_fecha(match.group("fecha")),
            concepto=match.group("concepto").strip(),
            numero_operacion=match.group("numero_op"),
            monto=self._parsear_monto(match.group("monto")),
            saldo_posterior=self._parsear_monto(match.group("saldo")),
            pagina=num_pagina,
        )

    def _extraer_numero_cuenta(self, ruta_pdf: Path) -> str:
        """Lee la primera página del PDF para extraer el número de cuenta."""
        with pdfplumber.open(ruta_pdf) as pdf:
            texto = pdf.pages[0].extract_text() or ""

        match = self._RE_NUMERO_CUENTA.search(texto)
        if match is None:
            raise ValueError(
                "No pude extraer el número de cuenta del PDF. "
                "¿El header tiene el formato esperado?"
            )

        return match.group("cuenta")

    # ------------------------------------------------------------------
    # Métodos privados — inferencia y validación
    # ------------------------------------------------------------------

    def _convertir_a_dominio(
        self,
        crudos: list[MovimientoCrudo],
        numero_cuenta: str,
    ) -> list[MovimientoBancario]:
        """Convierte cada MovimientoCrudo a MovimientoBancario validado."""
        movimientos: list[MovimientoBancario] = []
        saldo_anterior: Decimal | None = None

        for crudo in crudos:
            if saldo_anterior is None:
                # Primer movimiento: no podemos validar contra el saldo
                # anterior porque no lo tenemos. Asumimos signo por el
                # signo del saldo posterior (heurística temporal hasta
                # que en una iteración futura leamos el "saldo del período
                # anterior" del header del PDF).
                signo = (
                    SignoMovimiento.CREDITO
                    if crudo.saldo_posterior > Decimal("0")
                    else SignoMovimiento.DEBITO
                )
            else:
                signo = self._inferir_signo(crudo, saldo_anterior)

            movimiento = MovimientoBancario(
                banco=self.BANCO,
                cuenta=numero_cuenta,
                fecha=crudo.fecha,
                concepto=crudo.concepto,
                numero_operacion=crudo.numero_operacion,
                importe=crudo.monto,
                signo=signo,
                saldo_posterior=crudo.saldo_posterior,
                tipo=TipoMovimiento.OTRO,  # clasificación viene en iter 3.4
                pagina_origen=crudo.pagina,
            )
            movimientos.append(movimiento)
            saldo_anterior = crudo.saldo_posterior

        return movimientos

    def _inferir_signo(
        self,
        crudo: MovimientoCrudo,
        saldo_anterior: Decimal,
    ) -> SignoMovimiento:
        """Infiere si el movimiento es DEBITO o CREDITO por variación de saldo.

        Aprovecha para VALIDAR que el monto coincida con la variación.
        Si no coincide, lanza ErrorValidacionSaldo. Fail loud, fail early.
        """
        variacion = crudo.saldo_posterior - saldo_anterior

        if abs(variacion) != crudo.monto:
            raise ErrorValidacionSaldo(
                movimiento=crudo,
                saldo_anterior=saldo_anterior,
            )

        return SignoMovimiento.CREDITO if variacion > 0 else SignoMovimiento.DEBITO

    # ------------------------------------------------------------------
    # Métodos privados — utilidades de parsing
    # ------------------------------------------------------------------

    @staticmethod
    def _parsear_fecha(s: str) -> date:
        """'03/01/24' → date(2024, 1, 3). Argentina: DD/MM/YY."""
        return datetime.strptime(s, "%d/%m/%y").date()

    @staticmethod
    def _parsear_monto(s: str) -> Decimal:
        """'60,000.00' → Decimal('60000.00'); '-1,234.56' → Decimal('-1234.56')."""
        return Decimal(s.replace(",", "")).quantize(Decimal("0.01"))