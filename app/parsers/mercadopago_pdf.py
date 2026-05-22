"""
Parser de resúmenes de cuenta MercadoPago en PDF.

Extrae movimientos del "RESUMEN DE CUENTA" que MercadoPago permite descargar
desde la app/web. El formato es un PDF con una tabla de 5 columnas:
    Fecha | Descripción | ID de la operación | Valor | Saldo

Datos del encabezado (página 1):
    - Titular, CVU, CUIT/CUIL
    - Periodo (mes/año)
    - Saldo inicial, Entradas, Salidas, Saldo final

Particularidades del formato:
    - Fechas en formato DD-MM-YYYY.
    - Montos con $ y signo negativo para egresos (ej: $ -87.500,00).
    - Separador de miles: punto. Separador decimal: coma.
    - Descripción puede ocupar 2 líneas (ej: "Transferencia enviada Zulma\nAdalia,arce").
    - El saldo siempre es positivo (es el saldo posterior).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pdfplumber

from app.domain.models import MovimientoBancario, SignoMovimiento, TipoMovimiento
from app.parsers.clasificador_mp import clasificar_mp


# ============================================================================
# Excepciones
# ============================================================================

class ParserMercadoPagoError(Exception):
    """Error genérico del parser de MercadoPago."""


class ErrorCuadreMercadoPago(ParserMercadoPagoError):
    """El saldo final calculado no coincide con el del encabezado."""

    def __init__(
        self,
        saldo_inicial: Decimal,
        saldo_final_esperado: Decimal,
        saldo_final_calculado: Decimal,
        total_entradas: Decimal,
        total_salidas: Decimal,
    ) -> None:
        self.saldo_inicial = saldo_inicial
        self.saldo_final_esperado = saldo_final_esperado
        self.saldo_final_calculado = saldo_final_calculado
        self.diferencia = saldo_final_esperado - saldo_final_calculado
        super().__init__(
            f"Cuadre de saldo MercadoPago no coincide:\n"
            f"  Saldo inicial:        ${saldo_inicial:,.2f}\n"
            f"  Entradas:             ${total_entradas:,.2f}\n"
            f"  Salidas:              ${total_salidas:,.2f}\n"
            f"  Saldo final esperado: ${saldo_final_esperado:,.2f}\n"
            f"  Saldo final calculado:${saldo_final_calculado:,.2f}\n"
            f"  Diferencia:           ${self.diferencia:,.2f}"
        )


# ============================================================================
# DTOs internos
# ============================================================================

@dataclass
class EncabezadoMP:
    """Datos del encabezado del resumen."""
    titular: str = ""
    cvu: str = ""
    cuit: str = ""
    periodo: str = ""
    saldo_inicial: Decimal = Decimal("0")
    saldo_final: Decimal = Decimal("0")
    entradas: Decimal = Decimal("0")
    salidas: Decimal = Decimal("0")


@dataclass
class ResumenMP:
    """Resumen de totales del PDF procesado."""
    titular: str
    cvu: str
    cuit: str
    periodo: str
    saldo_inicial: Decimal
    saldo_final: Decimal
    entradas: Decimal
    salidas: Decimal
    cantidad_movimientos: int


@dataclass
class MovimientoRawMP:
    """Movimiento crudo extraído del PDF antes de convertir a dominio."""
    fecha: date
    descripcion: str
    id_operacion: str
    valor: Decimal  # con signo (negativo = egreso)
    saldo: Decimal
    pagina: int


# ============================================================================
# Regex patterns
# ============================================================================

_RE_FECHA = re.compile(r"^(\d{2}-\d{2}-\d{4})")
_RE_MONTO = re.compile(r"\$\s*(-?[\d.]+,\d{2})")
_RE_ID_OP = re.compile(r"\b(\d{12,15})\b")
_RE_CVU = re.compile(r"CVU:\s*(\d+)")
_RE_CUIT = re.compile(r"CUIT/?CUIL:\s*([\d-]+)")
_RE_SALDO_INICIAL = re.compile(r"Saldo\s+inicial:\s*\$\s*([\d.,]+)")
_RE_SALDO_FINAL = re.compile(r"Saldo\s+final:\s*\$\s*([\d.,]+)")
_RE_ENTRADAS = re.compile(r"Entradas:\s*\$\s*([\d.,]+)")
_RE_SALIDAS = re.compile(r"Salidas:\s*\$\s*([\d.,]+)")

# Palabras clave de ruido
_RUIDO = {
    "RESUMEN DE CUENTA", "DETALLE DE MOVIMIENTOS",
    "ID de la", "operación",
}


# ============================================================================
# Helpers
# ============================================================================

def _parsear_monto_ar(texto: str) -> Decimal:
    """Convierte '1.234.567,89' o '-87.500,00' a Decimal."""
    limpio = texto.replace(".", "").replace(",", ".")
    return Decimal(limpio)


def _es_linea_movimiento(linea: str) -> bool:
    """Determina si una línea empieza con una fecha DD-MM-YYYY."""
    return bool(_RE_FECHA.match(linea.strip()))


def _extraer_montos_de_linea(linea: str) -> list[Decimal]:
    """Extrae todos los montos ($ xxx) de una línea."""
    matches = _RE_MONTO.findall(linea)
    return [_parsear_monto_ar(m) for m in matches]


def _es_ruido(linea: str) -> bool:
    """Determina si una línea es ruido (encabezado, pie, etc.)."""
    if not linea:
        return True
    if linea in _RUIDO:
        return True
    if linea.startswith("Fecha") and ("operaci" in linea or "Valor" in linea):
        return True
    if re.match(r"^\d+/\d+$", linea):
        return True
    if "Mercado Libre S.R.L" in linea or "Fecha de generaci" in linea:
        return True
    if any(kw in linea for kw in ["CVU:", "CUIT", "Periodo:", "Saldo inicial",
                                   "Entradas:", "Salidas:", "canales"]):
        return True
    return False


# ============================================================================
# Parser principal
# ============================================================================

class ParserMercadoPago:
    """Parser de PDFs de resumen de cuenta MercadoPago."""

    def parsear(self, ruta_pdf: Path) -> list[MovimientoBancario]:
        """Parsea un PDF de MercadoPago y devuelve MovimientoBancario[]."""
        movimientos, _ = self.parsear_con_resumen(ruta_pdf)
        return movimientos

    def parsear_con_resumen(self, ruta_pdf: Path) -> tuple[list[MovimientoBancario], ResumenMP]:
        """Parsea un PDF de MercadoPago y devuelve (movimientos, resumen).

        Valida que saldo_inicial + entradas - salidas == saldo_final.
        """
        if not ruta_pdf.exists():
            raise ParserMercadoPagoError(f"Archivo no encontrado: {ruta_pdf}")

        lineas_por_pagina = self._extraer_texto(ruta_pdf)
        encabezado = self._parsear_encabezado(lineas_por_pagina.get(1, []))
        cvu = encabezado.cvu or "MERCADOPAGO"

        movimientos_raw = self._extraer_movimientos(lineas_por_pagina)
        movimientos = self._convertir_a_dominio(movimientos_raw, cvu, ruta_pdf.name)

        # Calcular totales desde los movimientos parseados
        total_entradas = sum(r.valor for r in movimientos_raw if r.valor > 0)
        total_salidas = abs(sum(r.valor for r in movimientos_raw if r.valor < 0))

        # Validar cuadre si tenemos saldo inicial y final del encabezado
        if encabezado.saldo_inicial and encabezado.saldo_final:
            saldo_calculado = encabezado.saldo_inicial + total_entradas - total_salidas
            if saldo_calculado != encabezado.saldo_final:
                raise ErrorCuadreMercadoPago(
                    saldo_inicial=encabezado.saldo_inicial,
                    saldo_final_esperado=encabezado.saldo_final,
                    saldo_final_calculado=saldo_calculado,
                    total_entradas=total_entradas,
                    total_salidas=total_salidas,
                )

        resumen = ResumenMP(
            titular=encabezado.titular,
            cvu=encabezado.cvu,
            cuit=encabezado.cuit,
            periodo=encabezado.periodo,
            saldo_inicial=encabezado.saldo_inicial,
            saldo_final=encabezado.saldo_final,
            entradas=total_entradas,
            salidas=total_salidas,
            cantidad_movimientos=len(movimientos),
        )

        return movimientos, resumen

    def _extraer_texto(self, ruta_pdf: Path) -> dict[int, list[str]]:
        """Extrae texto por página. Devuelve {nro_pagina: [lineas]}."""
        resultado = {}
        with pdfplumber.open(str(ruta_pdf)) as pdf:
            for i, page in enumerate(pdf.pages, start=1):
                texto = page.extract_text(x_tolerance=2, y_tolerance=2)
                if texto:
                    resultado[i] = texto.split("\n")
        return resultado

    def _parsear_encabezado(self, lineas: list[str]) -> EncabezadoMP:
        """Extrae datos del encabezado de la primera página."""
        enc = EncabezadoMP()
        texto = "\n".join(lineas)

        m = _RE_CVU.search(texto)
        if m:
            enc.cvu = m.group(1)

        m = _RE_CUIT.search(texto)
        if m:
            enc.cuit = m.group(1)

        m = _RE_SALDO_INICIAL.search(texto)
        if m:
            enc.saldo_inicial = _parsear_monto_ar(m.group(1))

        m = _RE_SALDO_FINAL.search(texto)
        if m:
            enc.saldo_final = _parsear_monto_ar(m.group(1))

        m = _RE_ENTRADAS.search(texto)
        if m:
            enc.entradas = _parsear_monto_ar(m.group(1))

        m = _RE_SALIDAS.search(texto)
        if m:
            enc.salidas = _parsear_monto_ar(m.group(1))

        # Titular: primera línea no vacía que no sea "RESUMEN DE CUENTA"
        for linea in lineas:
            l = linea.strip()
            if l and "RESUMEN DE CUENTA" not in l and "Mercado Libre" not in l and "Fecha de generaci" not in l:
                enc.titular = l
                break

        # Periodo
        m = re.search(r"Periodo:\s*(.+)", texto)
        if m:
            enc.periodo = m.group(1).strip()

        return enc

    def _extraer_movimientos(self, lineas_por_pagina: dict[int, list[str]]) -> list[MovimientoRawMP]:
        """Extrae movimientos crudos de todas las páginas.

        Descripciones largas se parten en varias líneas:
            Transferencia enviada Zulma       <- prefijo
            01-04-2026 152807626280 $ -87.500,00 $ 757.874,72
            Adalia,arce                       <- sufijo

        Estrategia: stream global de líneas, asignar prefijo/sufijo
        según posición relativa entre líneas con fecha.
        """
        # Stream global de líneas útiles con su página
        todas: list[tuple[str, int]] = []
        for pagina, lineas in sorted(lineas_por_pagina.items()):
            for linea in lineas:
                l = linea.strip()
                if not _es_ruido(l):
                    todas.append((l, pagina))

        # Descartar líneas previas al primer movimiento (nombre del titular)
        while todas and not _es_linea_movimiento(todas[0][0]):
            todas.pop(0)

        # Identificar índices con fecha
        indices_fecha = [i for i, (l, _) in enumerate(todas) if _es_linea_movimiento(l)]
        if not indices_fecha:
            return []

        movimientos: list[MovimientoRawMP] = []

        for pos, idx in enumerate(indices_fecha):
            linea, pagina = todas[idx]
            fecha_match = _RE_FECHA.match(linea)
            fecha = datetime.strptime(fecha_match.group(1), "%d-%m-%Y").date()

            # Líneas sin-fecha entre el mov anterior y este
            prev_idx = indices_fecha[pos - 1] if pos > 0 else -1
            entre = [todas[k][0] for k in range(prev_idx + 1, idx)
                     if not _es_linea_movimiento(todas[k][0])]
            # Heurística: si esta línea-fecha tiene descripción inline,
            # las non-fecha antes son sufijo del anterior (no nuestro prefijo).
            # Si NO tiene desc inline, las non-fecha antes son nuestro prefijo.
            tiene_desc_inline = self._tiene_descripcion_inline(linea)
            if pos == 0:
                prefijo_parts = entre if not tiene_desc_inline else []
            elif len(entre) == 0:
                prefijo_parts = []
            elif len(entre) == 1:
                # 1 línea: es prefijo nuestro si no tenemos desc inline
                prefijo_parts = entre if not tiene_desc_inline else []
            else:
                # 2+: primera=sufijo anterior, resto=prefijo nuestro
                prefijo_parts = entre[1:] if not tiene_desc_inline else []

            # Sufijo: líneas sin-fecha inmediatamente después
            next_idx = indices_fecha[pos + 1] if pos + 1 < len(indices_fecha) else len(todas)
            entre_despues = [todas[k][0] for k in range(idx + 1, next_idx)
                             if not _es_linea_movimiento(todas[k][0])]
            # Solo tomar como sufijo si la siguiente línea-fecha tiene desc inline
            # (lo que significa que entre_despues[0] es nuestro sufijo, no su prefijo)
            if entre_despues and not tiene_desc_inline:
                sufijo_parts = [entre_despues[0]]
            elif entre_despues and len(entre_despues) >= 2:
                # Tiene desc inline, pero hay 2+ líneas: primera es sufijo nuestro
                sufijo_parts = [entre_despues[0]]
            else:
                sufijo_parts = []

            # Construir línea completa
            desc_parts = prefijo_parts + [linea] + sufijo_parts
            linea_completa = " ".join(desc_parts)

            mov = self._parsear_linea_movimiento(linea_completa, fecha, pagina)
            if mov:
                movimientos.append(mov)

        return movimientos

    @staticmethod
    def _tiene_descripcion_inline(linea_fecha: str) -> bool:
        """Verifica si una línea con fecha tiene descripción inline.

        Ej: '01-04-2026 Rendimientos 1741802919500 $ 450,10 $ 845.374,72' -> True
        Ej: '01-04-2026 152807626280 $ -87.500,00 $ 757.874,72' -> False
        """
        sin_fecha = _RE_FECHA.sub("", linea_fecha).strip()
        sin_montos = _RE_MONTO.sub("", sin_fecha).replace("$", "")
        sin_id = _RE_ID_OP.sub("", sin_montos)
        resto = re.sub(r"\s+", "", sin_id)
        return len(resto) > 0

    def _parsear_linea_movimiento(
        self, linea: str, fecha: date, pagina: int
    ) -> MovimientoRawMP | None:
        """Parsea una línea (posiblemente multi-línea unida) en un MovimientoRawMP."""
        montos = _extraer_montos_de_linea(linea)
        if len(montos) < 2:
            return None

        saldo = montos[-1]
        valor = montos[-2]

        # Extraer ID de operación
        id_op = ""
        id_match = _RE_ID_OP.search(linea)
        if id_match:
            id_op = id_match.group(1)

        # Extraer descripción: quitar fecha, ID, y montos
        sin_fecha = _RE_FECHA.sub("", linea).strip()

        # Quitar todos los montos ($ xxx)
        descripcion = _RE_MONTO.sub("", sin_fecha)
        # Quitar los signos $ sueltos
        descripcion = descripcion.replace("$", "")

        # Quitar el ID de operación
        if id_op:
            descripcion = descripcion.replace(id_op, "")

        # Limpiar espacios múltiples
        descripcion = re.sub(r"\s+", " ", descripcion).strip()

        # Quitar la fecha repetida que aparece en la línea completa
        # (la línea contiene "prefijo DD-MM-YYYY ... sufijo")
        descripcion = re.sub(r"\d{2}-\d{2}-\d{4}", "", descripcion).strip()
        descripcion = re.sub(r"\s+", " ", descripcion).strip()

        if not descripcion:
            descripcion = "Movimiento"

        return MovimientoRawMP(
            fecha=fecha,
            descripcion=descripcion,
            id_operacion=id_op,
            valor=valor,
            saldo=saldo,
            pagina=pagina,
        )

    def _convertir_a_dominio(
        self,
        movimientos_raw: list[MovimientoRawMP],
        cvu: str,
        nombre_archivo: str,
    ) -> list[MovimientoBancario]:
        """Convierte movimientos crudos a modelo de dominio."""
        resultado: list[MovimientoBancario] = []

        for raw in movimientos_raw:
            signo = SignoMovimiento.CREDITO if raw.valor >= 0 else SignoMovimiento.DEBITO
            importe = abs(raw.valor)

            if importe == 0:
                continue

            tipo = clasificar_mp(raw.descripcion)

            mov = MovimientoBancario(
                banco="MERCADOPAGO",
                cuenta=cvu,
                fecha=raw.fecha,
                concepto=raw.descripcion,
                detalle_adicional=None,
                numero_operacion=raw.id_operacion or None,
                importe=importe,
                signo=signo,
                saldo_posterior=raw.saldo,
                moneda="ARS",
                tipo=tipo,
                archivo_origen=nombre_archivo,
                pagina_origen=raw.pagina,
            )
            resultado.append(mov)

        return resultado


# ============================================================================
# Detección de formato
# ============================================================================

def es_pdf_mercadopago(ruta_pdf: Path) -> bool:
    """Detecta si un PDF es un resumen de MercadoPago."""
    try:
        with pdfplumber.open(str(ruta_pdf)) as pdf:
            if not pdf.pages:
                return False
            texto = pdf.pages[0].extract_text(x_tolerance=2, y_tolerance=2) or ""
            return (
                "RESUMEN DE CUENTA" in texto
                and ("mercado" in texto.lower() or "CVU:" in texto)
                and "DETALLE DE MOVIMIENTOS" in texto
            )
    except Exception:
        return False
