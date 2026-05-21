"""
Parser de archivos SIRCREB (retenciones/percepciones bancarias de IIBB).

Soporta dos formatos de archivo:

1. **SIRCAR (Convenio Multilateral)**: archivo TXT delimitado por comas,
   descargado desde SIFERE Web Consultas. Es el formato estándar para
   todas las jurisdicciones adheridas al Convenio Multilateral.
   Diseño de registro según Anexo de la Comisión Arbitral (ca.gob.ar).

2. **ARBA (Buenos Aires)**: archivo TXT de ancho fijo, descargado desde
   el sitio de ARBA. Formato propio de la provincia de Buenos Aires.

Referencia de jurisdicciones: Convenio Multilateral, códigos 901-924.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from enum import Enum
from pathlib import Path
from typing import Optional


# ============================================================================
# Códigos de jurisdicción — Convenio Multilateral
# ============================================================================

JURISDICCIONES: dict[int, str] = {
    901: "Capital Federal",
    902: "Buenos Aires",
    903: "Catamarca",
    904: "Córdoba",
    905: "Corrientes",
    906: "Chaco",
    907: "Chubut",
    908: "Entre Ríos",
    909: "Formosa",
    910: "Jujuy",
    911: "La Pampa",
    912: "La Rioja",
    913: "Mendoza",
    914: "Misiones",
    915: "Neuquén",
    916: "Río Negro",
    917: "Salta",
    918: "San Juan",
    919: "San Luis",
    920: "Santa Cruz",
    921: "Santa Fe",
    922: "Santiago del Estero",
    923: "Tierra del Fuego",
    924: "Tucumán",
}


class TipoRegistro(str, Enum):
    PERCEPCION = "PERCEPCION"
    RETENCION = "RETENCION"


# ============================================================================
# Modelo de datos
# ============================================================================


@dataclass
class PercepcionIIBB:
    """Una percepción o retención de IIBB parseada del archivo SIRCREB."""

    jurisdiccion: int
    jurisdiccion_nombre: str
    cuit_agente: str
    fecha: date
    tipo: TipoRegistro
    monto_sujeto: Decimal
    alicuota: Optional[Decimal]
    monto_retenido: Decimal
    regimen: Optional[str] = None
    tipo_comprobante: Optional[str] = None
    letra_comprobante: Optional[str] = None
    numero_comprobante: Optional[str] = None


@dataclass
class ResultadoSIRCREB:
    """Resultado del parseo de un archivo SIRCREB."""

    percepciones: list[PercepcionIIBB]
    errores: list[str]
    archivo: str
    formato_detectado: str


# ============================================================================
# Funciones auxiliares
# ============================================================================


def _parse_fecha(texto: str) -> date:
    """Parsea fecha en formato dd/mm/aaaa."""
    texto = texto.strip()
    partes = texto.split("/")
    if len(partes) != 3:
        raise ValueError(f"Fecha inválida: '{texto}' (esperado dd/mm/aaaa)")
    dia, mes, anio = int(partes[0]), int(partes[1]), int(partes[2])
    return date(anio, mes, dia)


def _parse_decimal(texto: str) -> Decimal:
    """Parsea un monto numérico. Acepta punto o coma como separador decimal."""
    texto = texto.strip().replace(",", ".")
    if not texto:
        return Decimal("0")
    return Decimal(texto).quantize(Decimal("0.01"))


def _parse_cuit(texto: str) -> str:
    """Normaliza CUIT: acepta con o sin guiones, devuelve sin guiones."""
    return texto.strip().replace("-", "")


def _formatear_cuit(cuit: str) -> str:
    """Formatea CUIT: 20123456789 -> 20-12345678-9."""
    cuit = cuit.replace("-", "")
    if len(cuit) == 11:
        return f"{cuit[:2]}-{cuit[2:10]}-{cuit[10]}"
    return cuit


# ============================================================================
# Parser SIRCAR (Convenio Multilateral) — delimitado por comas
# ============================================================================
#
# Diseño de registro N° 1 (percepciones):
#   1. Número de Renglón (Numérico 5)
#   2. Tipo de Comprobante (Numérico 3)
#   3. Letra del Comprobante (Char 1)
#   4. Número de Comprobante con punto de venta (Numérico 12)
#   5. CUIT Contribuyente (Numérico 11)
#   6. Fecha de Percepción (dd/mm/aaaa)
#   7. Monto Sujeto a Percepción (999999999.99)
#   8. Alícuota (999.99)
#   9. Monto Percibido (999999999.99)
#  10. Tipo de Régimen de Percepción (Numérico 3)
#  11. Jurisdicción (Numérico 3)
#
# Diseño de registro N° 1 (retenciones):
#   1. Número de Renglón (Numérico 5)
#   2. Origen del Comprobante (Numérico 1)
#   3. Tipo de Comprobante (Numérico 1): 1=Retención, 2=Anulación
#   4. Número de Comprobante (Numérico 12)
#   5. CUIT Contribuyente (Numérico 11)
#   6. Fecha de Retención (dd/mm/aaaa)
#   7. Monto Sujeto a Retención (999999999.99)
#   8. Alícuota (999.99)
#   9. Monto Retenido (999999999.99)
#  10. Tipo de Régimen (Numérico 3)
#  11. Jurisdicción (Numérico 3)
# ============================================================================


def _parsear_sircar_percepciones(lineas: list[str], archivo: str) -> ResultadoSIRCREB:
    """Parsea archivo SIRCAR de percepciones (delimitado por comas, 11+ campos)."""
    percepciones: list[PercepcionIIBB] = []
    errores: list[str] = []

    for num_linea, linea in enumerate(lineas, 1):
        linea = linea.strip()
        if not linea:
            continue

        campos = linea.split(",")
        if len(campos) < 11:
            errores.append(f"Línea {num_linea}: esperados >= 11 campos, encontrados {len(campos)}")
            continue

        try:
            jurisdiccion = int(campos[10].strip())
            jurisdiccion_nombre = JURISDICCIONES.get(jurisdiccion, f"Desconocida ({jurisdiccion})")
            cuit = _parse_cuit(campos[4])
            fecha = _parse_fecha(campos[5])
            monto_sujeto = _parse_decimal(campos[6])
            alicuota = _parse_decimal(campos[7])
            monto_percibido = _parse_decimal(campos[8])
            regimen = campos[9].strip()

            # Tipo comprobante: valores 102, 106, 120 son notas de crédito (anulaciones)
            tipo_comp = campos[1].strip()
            letra_comp = campos[2].strip()
            nro_comp = campos[3].strip()

            percepciones.append(PercepcionIIBB(
                jurisdiccion=jurisdiccion,
                jurisdiccion_nombre=jurisdiccion_nombre,
                cuit_agente=_formatear_cuit(cuit),
                fecha=fecha,
                tipo=TipoRegistro.PERCEPCION,
                monto_sujeto=monto_sujeto,
                alicuota=alicuota,
                monto_retenido=monto_percibido,
                regimen=regimen,
                tipo_comprobante=tipo_comp,
                letra_comprobante=letra_comp if letra_comp else None,
                numero_comprobante=nro_comp,
            ))
        except (ValueError, InvalidOperation) as e:
            errores.append(f"Línea {num_linea}: {e}")

    return ResultadoSIRCREB(
        percepciones=percepciones,
        errores=errores,
        archivo=archivo,
        formato_detectado="SIRCAR Percepciones",
    )


def _parsear_sircar_retenciones(lineas: list[str], archivo: str) -> ResultadoSIRCREB:
    """Parsea archivo SIRCAR de retenciones (delimitado por comas, 11+ campos)."""
    percepciones: list[PercepcionIIBB] = []
    errores: list[str] = []

    for num_linea, linea in enumerate(lineas, 1):
        linea = linea.strip()
        if not linea:
            continue

        campos = linea.split(",")
        if len(campos) < 11:
            errores.append(f"Línea {num_linea}: esperados >= 11 campos, encontrados {len(campos)}")
            continue

        try:
            jurisdiccion = int(campos[10].strip())
            jurisdiccion_nombre = JURISDICCIONES.get(jurisdiccion, f"Desconocida ({jurisdiccion})")
            cuit = _parse_cuit(campos[4])
            fecha = _parse_fecha(campos[5])
            monto_sujeto = _parse_decimal(campos[6])
            alicuota = _parse_decimal(campos[7])
            monto_retenido = _parse_decimal(campos[8])
            regimen = campos[9].strip()

            # tipo_comprobante campo 2: 1=Retención, 2=Anulación
            tipo_comp = campos[2].strip()
            nro_comp = campos[3].strip()

            percepciones.append(PercepcionIIBB(
                jurisdiccion=jurisdiccion,
                jurisdiccion_nombre=jurisdiccion_nombre,
                cuit_agente=_formatear_cuit(cuit),
                fecha=fecha,
                tipo=TipoRegistro.RETENCION,
                monto_sujeto=monto_sujeto,
                alicuota=alicuota,
                monto_retenido=monto_retenido,
                regimen=regimen,
                tipo_comprobante=tipo_comp,
                numero_comprobante=nro_comp,
            ))
        except (ValueError, InvalidOperation) as e:
            errores.append(f"Línea {num_linea}: {e}")

    return ResultadoSIRCREB(
        percepciones=percepciones,
        errores=errores,
        archivo=archivo,
        formato_detectado="SIRCAR Retenciones",
    )


# ============================================================================
# Parser ARBA (Buenos Aires) — ancho fijo
# ============================================================================
#
# Percepciones (Diseño 1.1):
#   Pos 1-13:  CUIT contribuyente (99-99999999-9)
#   Pos 14-23: Fecha percepción (dd/mm/aaaa)
#   Pos 24:    Tipo comprobante (F/R/C/D/V/E/H/I)
#   Pos 25:    Letra comprobante (A/B/C o blanco)
#   Pos 26-29: Número sucursal (4 dígitos)
#   Pos 30-37: Número emisión (8 dígitos)
#   Pos 38-49: Monto imponible (12 con 2 dec)
#   Pos 50-60: Importe percepción (11 con 2 dec)
#   Pos 61:    Tipo operación (A=Alta, B=Baja, M=Modif)
#
# Retenciones (Diseño 1.7):
#   Pos 1-13:  CUIT contribuyente (99-99999999-9)
#   Pos 14-23: Fecha retención (dd/mm/aaaa)
#   Pos 24-27: Número sucursal (4 dígitos)
#   Pos 28-35: Número emisión (8 dígitos)
#   Pos 36-46: Importe retención (11 con 2 dec)
#   Pos 47:    Tipo operación (A/B/M)
# ============================================================================


def _parsear_arba_percepciones(lineas: list[str], archivo: str) -> ResultadoSIRCREB:
    """Parsea archivo ARBA de percepciones (ancho fijo, 61 chars)."""
    percepciones: list[PercepcionIIBB] = []
    errores: list[str] = []

    for num_linea, linea in enumerate(lineas, 1):
        linea = linea.rstrip("\n\r")
        if not linea:
            continue

        if len(linea) < 60:
            errores.append(f"Línea {num_linea}: largo {len(linea)}, esperado >= 60")
            continue

        try:
            cuit = linea[0:13].strip()
            fecha = _parse_fecha(linea[13:23].strip())
            tipo_comp = linea[23:24].strip()
            letra_comp = linea[24:25].strip()
            nro_sucursal = linea[25:29].strip()
            nro_emision = linea[29:37].strip()
            monto_sujeto = _parse_decimal(linea[37:49])
            monto_percibido = _parse_decimal(linea[49:60])
            tipo_op = linea[60:61].strip() if len(linea) > 60 else "A"

            if tipo_op == "B":
                continue  # Baja: ignorar

            percepciones.append(PercepcionIIBB(
                jurisdiccion=902,
                jurisdiccion_nombre="Buenos Aires",
                cuit_agente=cuit,
                fecha=fecha,
                tipo=TipoRegistro.PERCEPCION,
                monto_sujeto=monto_sujeto,
                alicuota=None,
                monto_retenido=monto_percibido,
                tipo_comprobante=tipo_comp,
                letra_comprobante=letra_comp if letra_comp else None,
                numero_comprobante=f"{nro_sucursal}-{nro_emision}",
            ))
        except (ValueError, InvalidOperation) as e:
            errores.append(f"Línea {num_linea}: {e}")

    return ResultadoSIRCREB(
        percepciones=percepciones,
        errores=errores,
        archivo=archivo,
        formato_detectado="ARBA Percepciones",
    )


def _parsear_arba_retenciones(lineas: list[str], archivo: str) -> ResultadoSIRCREB:
    """Parsea archivo ARBA de retenciones (ancho fijo, 47 chars)."""
    percepciones: list[PercepcionIIBB] = []
    errores: list[str] = []

    for num_linea, linea in enumerate(lineas, 1):
        linea = linea.rstrip("\n\r")
        if not linea:
            continue

        if len(linea) < 46:
            errores.append(f"Línea {num_linea}: largo {len(linea)}, esperado >= 46")
            continue

        try:
            cuit = linea[0:13].strip()
            fecha = _parse_fecha(linea[13:23].strip())
            nro_sucursal = linea[23:27].strip()
            nro_emision = linea[27:35].strip()
            monto_retenido = _parse_decimal(linea[35:46])
            tipo_op = linea[46:47].strip() if len(linea) > 46 else "A"

            if tipo_op == "B":
                continue

            percepciones.append(PercepcionIIBB(
                jurisdiccion=902,
                jurisdiccion_nombre="Buenos Aires",
                cuit_agente=cuit,
                fecha=fecha,
                tipo=TipoRegistro.RETENCION,
                monto_sujeto=Decimal("0"),
                alicuota=None,
                monto_retenido=monto_retenido,
                numero_comprobante=f"{nro_sucursal}-{nro_emision}",
            ))
        except (ValueError, InvalidOperation) as e:
            errores.append(f"Línea {num_linea}: {e}")

    return ResultadoSIRCREB(
        percepciones=percepciones,
        errores=errores,
        archivo=archivo,
        formato_detectado="ARBA Retenciones",
    )


# ============================================================================
# Detección automática de formato
# ============================================================================


def _detectar_formato(lineas: list[str], nombre_archivo: str) -> str:
    """Detecta el formato del archivo basándose en contenido y nombre.

    Returns:
        "sircar_percepciones", "sircar_retenciones",
        "arba_percepciones", "arba_retenciones", o "desconocido".
    """
    nombre = nombre_archivo.lower()

    # Por nombre de archivo: SIFERE usa letras al final
    # -P- o termina en P.txt = percepciones, -R- = retenciones, -B- = bancarias
    if "arba" in nombre or nombre.endswith((".902", "-902")):
        # Intentar detectar por largo de línea
        for linea in lineas:
            linea = linea.strip()
            if not linea:
                continue
            if "," in linea:
                # ARBA no usa comas, es ancho fijo
                break
            if len(linea) >= 55 and len(linea) <= 65:
                return "arba_percepciones"
            if len(linea) >= 40 and len(linea) <= 50:
                return "arba_retenciones"
            break

    # Buscar primera línea con datos
    for linea in lineas:
        linea = linea.strip()
        if not linea:
            continue

        # Si tiene comas, es formato SIRCAR
        if "," in linea:
            campos = linea.split(",")
            if len(campos) >= 11:
                # Diferenciar percepciones de retenciones:
                # Percepciones campo 2 (tipo comprobante) tiene valores altos (1-7, 20, 102, etc)
                # Retenciones campo 2 (origen comprobante) es 1 o 2
                # y campo 3 (tipo comprobante) también es 1 o 2
                try:
                    campo2 = int(campos[1].strip())
                    campo3_str = campos[2].strip()
                    # En percepciones, campo 3 es letra (A, B, C, E, M, Z)
                    # En retenciones, campo 3 es numérico (1 o 2)
                    if campo3_str.isdigit() and int(campo3_str) <= 2 and campo2 <= 3:
                        return "sircar_retenciones"
                    else:
                        return "sircar_percepciones"
                except ValueError:
                    return "sircar_percepciones"

        # Sin comas: formato ancho fijo (ARBA)
        if len(linea) >= 55:
            return "arba_percepciones"
        if len(linea) >= 40:
            return "arba_retenciones"

        break

    return "desconocido"


# ============================================================================
# API pública
# ============================================================================


def parsear_sircreb(
    contenido: str,
    nombre_archivo: str,
    formato: str | None = None,
) -> ResultadoSIRCREB:
    """Parsea un archivo SIRCREB/SIRCAR/ARBA.

    Args:
        contenido: texto completo del archivo TXT.
        nombre_archivo: nombre del archivo (para detección de formato).
        formato: forzar formato. Si es None, se autodetecta.
            Valores: "sircar_percepciones", "sircar_retenciones",
                     "arba_percepciones", "arba_retenciones".

    Returns:
        ResultadoSIRCREB con las percepciones/retenciones parseadas.
    """
    lineas = contenido.splitlines()

    if formato is None:
        formato = _detectar_formato(lineas, nombre_archivo)

    parsers = {
        "sircar_percepciones": _parsear_sircar_percepciones,
        "sircar_retenciones": _parsear_sircar_retenciones,
        "arba_percepciones": _parsear_arba_percepciones,
        "arba_retenciones": _parsear_arba_retenciones,
    }

    parser = parsers.get(formato)
    if parser is None:
        return ResultadoSIRCREB(
            percepciones=[],
            errores=[f"Formato desconocido: '{formato}'. "
                     f"Formatos soportados: {', '.join(parsers.keys())}"],
            archivo=nombre_archivo,
            formato_detectado=formato,
        )

    return parser(lineas, nombre_archivo)


def parsear_archivo_sircreb(
    ruta: str | Path,
    formato: str | None = None,
    encoding: str = "latin-1",
) -> ResultadoSIRCREB:
    """Parsea un archivo SIRCREB desde disco.

    Args:
        ruta: path al archivo TXT.
        formato: forzar formato (None = autodetectar).
        encoding: encoding del archivo (default: latin-1, estándar en AFIP).
    """
    path = Path(ruta)
    contenido = path.read_text(encoding=encoding)
    return parsear_sircreb(contenido, path.name, formato)
