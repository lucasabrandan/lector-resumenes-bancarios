"""
Script exploratorio — Día 2: entender el dato real antes de parsear.

NO ES PARTE DEL PARSER FINAL. Este script es código DESCARTABLE cuyo único
propósito es entender la estructura de los archivos que tenemos. Una vez que
hayamos terminado de explorar, este código NO va a producción: lo que se queda
es el aprendizaje y el parser real (que escribiremos en app/parsers/).

Por qué este paso existe:
    Los tutoriales suelen saltarse esta fase y van directo a codear. En la vida
    real, el dato siempre tiene sorpresas: columnas corridas, valores faltantes,
    encodings raros. Explorar primero ahorra HORAS de debugging después.

Cómo correrlo:
    1. Asegurate de tener pdfplumber y pandas instalados (están en requirements.txt).
    2. Coloca el archivo PDF en una carpeta (NO la subas al repo: contiene datos
       reales de una empresa). Sugerencia: crear data/raw/ y agregarla al .gitignore.
    3. Ajustá la ruta `ARCHIVO_PDF` abajo a donde tengas el archivo.
    4. python scripts/explorar_supervielle.py
"""

import re
from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pdfplumber

# ============================================================================
# Configuración (ajustar a tu máquina)
# ============================================================================

ARCHIVO_PDF = Path("data/raw/fundiciones_vanella_extracto.pdf")
ARCHIVO_XLSX = Path("data/raw/Superville_completo_06-2024_a_05-2025.xlsx")


# ============================================================================
# Helpers
# ============================================================================


def encabezado(titulo: str) -> None:
    """Imprime un encabezado decorado."""
    print(f"\n{'=' * 70}")
    print(f"  {titulo}")
    print(f"{'=' * 70}")


def es_fecha(val) -> bool:
    """Check robusto: cubre datetime, Timestamp y todo lo que tenga .date().

    Aprendido a las malas: pandas devuelve datetime.datetime en algunos casos
    y pd.Timestamp en otros, según cómo se haya parseado el Excel. Esto cubre
    ambos.
    """
    if pd.isna(val):
        return False
    return isinstance(val, (datetime, pd.Timestamp))


# ============================================================================
# PASO 1 — Clasificar las hojas del Excel
# ============================================================================


def explorar_hojas_xlsx(archivo: Path) -> None:
    """¿Qué hojas hay y de qué tipo?"""
    encabezado("PASO 1 — Hojas del XLSX intermedio")

    xl = pd.ExcelFile(archivo)
    table_sheets = [s for s in xl.sheet_names if s.startswith("Table")]
    meses = [
        "ENERO", "FEBRERO", "MARZO", "ABRIL", "MAYO", "JUNIO",
        "JULIO", "AGOSTO", "SEPTIEMBRE", "OCTUBRE", "NOVIEMBRE", "DICIEMBRE",
    ]
    mensuales = [s for s in xl.sheet_names if any(m in s.upper() for m in meses)]
    otras = [s for s in xl.sheet_names if s not in table_sheets and s not in mensuales]

    print(f"Total de hojas: {len(xl.sheet_names)}")
    print(f"  Hojas 'Table N' (post-Tabula): {len(table_sheets)}")
    print(f"  Hojas mensuales (trabajo de la contadora): {len(mensuales)}")
    print(f"  Otras: {len(otras)}")
    print()
    print("LECCIÓN: las hojas mensuales son trabajo manual de la contadora.")
    print("NO son fuente confiable (ver Paso 3).")


# ============================================================================
# PASO 2 — Estructura de una hoja mensual
# ============================================================================


def explorar_hoja_mensual(archivo: Path, hoja: str = "MARZO 2024") -> None:
    """Ver cómo es una hoja mensual por dentro."""
    encabezado(f"PASO 2 — Estructura de '{hoja}'")

    df = pd.read_excel(archivo, sheet_name=hoja, header=None)
    print(f"Shape: {df.shape}")
    print()
    print("Primeras 8 filas (solo columnas no vacías):")
    print("-" * 70)
    for idx in range(min(8, len(df))):
        row = df.iloc[idx]
        valores = [f"[{c}]={str(v)[:30]}" for c, v in enumerate(row) if pd.notna(v)]
        print(f"  Fila {idx:3d}: " + " | ".join(valores))


# ============================================================================
# PASO 3 — El hallazgo crítico: el saldo se corre de columna
# ============================================================================


def detectar_columnas_corridas(archivo: Path, hoja: str = "MARZO 2024") -> None:
    """
    Demostrar que las hojas mensuales tienen filas con columnas mal alineadas.

    Hipótesis: en algunas filas, el saldo (que debería estar en col 4) aparece
    en col 3 (donde debería ir el crédito), porque la extracción del PDF original
    no detectó bien los bordes de columna.
    """
    encabezado(f"PASO 3 — Detección de filas mal alineadas en '{hoja}'")

    df = pd.read_excel(archivo, sheet_name=hoja, header=None)
    sospechosas = 0
    ejemplos: list[tuple[int, str, float]] = []

    for idx in range(len(df)):
        if not es_fecha(df.iloc[idx, 0]):
            continue
        concepto = df.iloc[idx, 1]
        debito = df.iloc[idx, 2]
        credito = df.iloc[idx, 3]
        saldo = df.iloc[idx, 4]

        # Caso sospechoso: hay débito Y crédito a la vez (no debería pasar)
        # O hay un crédito gigante en un concepto que claramente es débito.
        # O el saldo (col 4) está vacío pero hay valor en col 3.
        if pd.notna(debito) and pd.notna(credito) and pd.isna(saldo):
            sospechosas += 1
            if len(ejemplos) < 5:
                ejemplos.append((idx, str(concepto)[:35], float(credito)))

    print(f"Filas sospechosas (débito + crédito + sin saldo): {sospechosas}")
    print("\nPrimeros 5 ejemplos:")
    for fila, concepto, valor_mal_ubicado in ejemplos:
        print(f"  Fila {fila}: '{concepto}' → valor {valor_mal_ubicado:,.2f} "
              f"está en col 3 (Crédito) pero es el saldo")

    print("\n💡 CONCLUSIÓN: el XLSX intermedio tiene datos corruptos por")
    print("   la extracción de PDF. NO es fuente confiable.")


# ============================================================================
# PASO 4 — El PDF original es la verdad
# ============================================================================


def explorar_pdf(archivo: Path, pagina: int = 2) -> None:
    """Ver el texto del PDF, que es la fuente original."""
    encabezado(f"PASO 4 — Texto crudo del PDF (página {pagina})")

    with pdfplumber.open(archivo) as pdf:
        print(f"Total de páginas: {len(pdf.pages)}")
        p = pdf.pages[pagina - 1]
        texto = p.extract_text()
        print(f"\nPrimeras 20 líneas de la página {pagina}:")
        print("-" * 70)
        for i, linea in enumerate(texto.split("\n")[:20]):
            print(f"  {i:3d}: {linea}")


# ============================================================================
# PASO 5 — Patrón regex para extraer movimientos del PDF
# ============================================================================


# Cada línea de movimiento sigue el patrón:
#   DD/MM/YY Concepto NumeroOperacion Monto Saldo
# donde Monto y Saldo usan formato argentino: punto como separador de miles,
# coma NO, decimal con punto (ej: "1,234.56" pero a veces "1.234,56" según banco).
# En Supervielle vimos: "60,000.00" → separador miles ",", decimal "."
RE_MOVIMIENTO = re.compile(
    r"^"
    r"(?P<fecha>\d{2}/\d{2}/\d{2})\s+"
    r"(?P<concepto>.+?)\s+"
    r"(?P<numero_op>\d{6,15})\s+"
    r"(?P<monto>-?[\d,]+\.\d{2})\s+"
    r"(?P<saldo>-?[\d,]+\.\d{2})"
    r"\s*$"
)


def parsear_monto(s: str) -> Decimal:
    """Convierte '60,000.00' o '-1,234.56' a Decimal."""
    return Decimal(s.replace(",", "")).quantize(Decimal("0.01"))


def extraer_movimientos_pdf(archivo: Path, max_paginas: int = 5) -> list[dict]:
    """Extrae movimientos del PDF aplicando la regex sobre cada línea."""
    encabezado(f"PASO 5 — Extracción regex (primeras {max_paginas} páginas)")

    movimientos: list[dict] = []
    matches_por_pagina = []

    with pdfplumber.open(archivo) as pdf:
        for num_pag, pagina in enumerate(pdf.pages[:max_paginas], start=1):
            texto = pagina.extract_text() or ""
            matches_pag = 0
            for linea in texto.split("\n"):
                m = RE_MOVIMIENTO.match(linea.strip())
                if m:
                    movimientos.append({
                        "pagina": num_pag,
                        "fecha": datetime.strptime(m.group("fecha"), "%d/%m/%y").date(),
                        "concepto": m.group("concepto").strip(),
                        "numero_op": m.group("numero_op"),
                        "monto": parsear_monto(m.group("monto")),
                        "saldo": parsear_monto(m.group("saldo")),
                    })
                    matches_pag += 1
            matches_por_pagina.append((num_pag, matches_pag))

    print(f"Total movimientos extraídos: {len(movimientos)}")
    print(f"\nMatches por página: {matches_por_pagina}")
    print(f"\nPrimeros 8 movimientos:")
    print("-" * 90)
    for m in movimientos[:8]:
        print(f"  p{m['pagina']} | {m['fecha']} | {m['concepto'][:35]:<35} "
              f"| ${m['monto']:>12,.2f} | saldo ${m['saldo']:>15,.2f}")

    return movimientos


# ============================================================================
# PASO 6 — Validación por variación de saldo
# ============================================================================


def validar_por_saldos(movimientos: list[dict]) -> None:
    """
    El truco que descubrimos: el signo del movimiento se infiere por la
    variación del saldo. Y eso nos sirve como check de consistencia.
    """
    encabezado("PASO 6 — Validación: ¿el monto coincide con la variación de saldo?")

    errores = 0
    primeros_5 = []

    for i in range(1, len(movimientos)):
        anterior = movimientos[i - 1]["saldo"]
        actual = movimientos[i]["saldo"]
        variacion = actual - anterior
        monto = movimientos[i]["monto"]

        # |variacion| debería igualar al monto
        if abs(variacion) != monto:
            errores += 1
            if len(primeros_5) < 5:
                primeros_5.append({
                    "idx": i,
                    "concepto": movimientos[i]["concepto"][:30],
                    "monto": monto,
                    "variacion": variacion,
                    "diff": abs(variacion) - monto,
                })

    print(f"Movimientos validados: {len(movimientos) - 1}")
    print(f"Errores de cuadre: {errores}")
    if errores > 0:
        print("\nPrimeros 5 errores (necesitan investigación):")
        for e in primeros_5:
            print(f"  #{e['idx']}: {e['concepto']} → "
                  f"monto ${e['monto']} vs variación ${e['variacion']} "
                  f"(diff ${e['diff']})")
    else:
        print("\n✅ ¡Todos los movimientos cuadran con la variación de saldo!")


# ============================================================================
# Entry point
# ============================================================================


def main() -> None:
    """Ejecuta toda la exploración paso a paso."""
    print("\n🔬 EXPLORACIÓN DEL DATO REAL — Supervielle\n")

    if ARCHIVO_XLSX.exists():
        explorar_hojas_xlsx(ARCHIVO_XLSX)
        explorar_hoja_mensual(ARCHIVO_XLSX)
        detectar_columnas_corridas(ARCHIVO_XLSX)
    else:
        print(f"⚠️ No encontré {ARCHIVO_XLSX}. Saltando exploración del XLSX.")

    if ARCHIVO_PDF.exists():
        explorar_pdf(ARCHIVO_PDF)
        movimientos = extraer_movimientos_pdf(ARCHIVO_PDF)
        validar_por_saldos(movimientos)
    else:
        print(f"\n⚠️ No encontré {ARCHIVO_PDF}. Saltando exploración del PDF.")

    print("\n" + "=" * 70)
    print("✅ Exploración completa. Ver docs/bitacora.md sección 'Día 2'")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
