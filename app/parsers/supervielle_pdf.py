"""
Parser de extractos en PDF del Banco Supervielle (cuenta corriente).

Este es el primer parser concreto del proyecto. Cuando agreguemos más bancos
(Santander, Galicia, BBVA), todos heredarán de una clase abstracta común
`ParserBancoBase` (Strategy Pattern). Por ahora, vamos directo: primero hacer
que UNO funcione bien antes de generalizar.

Decisiones de diseño documentadas en: docs/adr/0005-parsear-pdf-no-xlsx.md

Estado actual (Iteración 3.1):
    ✅ Extracción cruda de movimientos del PDF con regex.
    ⏳ Próximas iteraciones: signo, tipo, detalle adicional.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pdfplumber


# ============================================================================
# DTO interno del parser
# ============================================================================
#
# `MovimientoCrudo` es una representación INTERNA del parser, antes de
# convertirla al modelo de dominio `MovimientoBancario`. Lo separamos a
# propósito:
#
#   - El parser produce datos "tal cual están en el PDF" (signo aún no inferido,
#     tipo aún no clasificado).
#   - Después, una etapa de transformación convierte estos crudos en
#     `MovimientoBancario` (que es lo que consume el resto del sistema).
#
# Esta separación se llama "Anti-Corruption Layer": el formato del banco no
# contamina el modelo de dominio.
# ============================================================================


@dataclass(frozen=True, slots=True)
class MovimientoCrudo:
    """Movimiento tal como aparece en el PDF, sin interpretar.

    Es inmutable (frozen) y eficiente en memoria (slots).
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
        movimientos = parser.parsear_crudos(Path("extracto.pdf"))
    """

    # ------------------------------------------------------------------
    # Constantes de clase (compiladas una sola vez)
    # ------------------------------------------------------------------

    # Patrón de cada movimiento dentro del PDF.
    # Formato observado: "DD/MM/YY  Concepto  NumeroOperacion  Monto  Saldo"
    #
    # Notas:
    # - Concepto puede tener espacios, palabras, acentos, slashes (/), puntos.
    #   Por eso usamos un grupo "lazy" (.+?) que matchea lo mínimo posible.
    # - NumeroOperacion es un número de 6 a 15 dígitos (los códigos internos
    #   del banco varían en longitud según el tipo de operación).
    # - Monto y Saldo usan formato argentino con coma como separador de miles
    #   y punto decimal: "1,234.56" o "-1,234.56".
    _RE_MOVIMIENTO = re.compile(
        r"^"
        r"(?P<fecha>\d{2}/\d{2}/\d{2})\s+"
        r"(?P<concepto>.+?)\s+"
        r"(?P<numero_op>\d{6,15})\s+"
        r"(?P<monto>-?[\d,]+\.\d{2})\s+"
        r"(?P<saldo>-?[\d,]+\.\d{2})"
        r"\s*$"
    )

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

    def parsear_crudos(self, ruta_pdf: Path) -> list[MovimientoCrudo]:
        """Lee un PDF de Supervielle y devuelve la lista de movimientos crudos.

        Args:
            ruta_pdf: ruta al archivo PDF del extracto.

        Returns:
            Lista de `MovimientoCrudo`, en el ORDEN en que aparecen en el PDF
            (importante para inferir el signo por variación de saldo en la
            próxima iteración).

        Raises:
            FileNotFoundError: si la ruta no existe.
            ValueError: si el archivo no parece ser un extracto de Supervielle.
        """
        if not ruta_pdf.exists():
            raise FileNotFoundError(f"No encontré el archivo: {ruta_pdf}")

        movimientos: list[MovimientoCrudo] = []

        with pdfplumber.open(ruta_pdf) as pdf:
            for num_pagina, pagina in enumerate(pdf.pages, start=1):
                texto = pagina.extract_text() or ""
                movimientos.extend(
                    self._parsear_pagina(texto, num_pagina)
                )

        if not movimientos:
            raise ValueError(
                f"No se encontraron movimientos en {ruta_pdf}. "
                "¿Es realmente un extracto de Supervielle?"
            )

        return movimientos

    # ------------------------------------------------------------------
    # Métodos privados
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

    @staticmethod
    def _parsear_fecha(s: str) -> date:
        """'03/01/24' → date(2024, 1, 3). Argentina: DD/MM/YY."""
        return datetime.strptime(s, "%d/%m/%y").date()

    @staticmethod
    def _parsear_monto(s: str) -> Decimal:
        """'60,000.00' → Decimal('60000.00'); '-1,234.56' → Decimal('-1234.56').

        Saca los separadores de miles (comas) y convierte a Decimal con
        exactamente 2 decimales, para evitar basura como Decimal('100.456789').
        """
        return Decimal(s.replace(",", "")).quantize(Decimal("0.01"))
