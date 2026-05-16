# ADR-0005: Parsear el PDF original, no el XLSX intermedio

- **Estado**: ✅ Aceptado
- **Fecha**: 2025-05-16
- **Autor**: Equipo

## Contexto

La contadora nos entregó tres archivos para entender su flujo de trabajo:

1. `fundiciones_vanella_extracto.pdf` — el extracto original del Banco Supervielle.
2. `Superville_completo_06-2024_a_05-2025.xlsx` — el extracto post-Tabula, donde ella organiza por mes.
3. `lucas.xlsx` — el reporte final que entrega.

La hipótesis inicial era parsear el archivo (2) porque ya viene tabulado y "más limpio" que el PDF. Sin embargo, al explorar el dato real (ver `scripts/explorar_supervielle.py`), encontramos problemas críticos.

### Problemas encontrados en el XLSX intermedio

1. **Columnas corridas**: en aproximadamente 10 filas de cada hoja mensual, el valor del saldo aparece en la columna "Crédito" (col 3) en lugar de la columna "Saldo" (col 4). Esto rompe completamente las sumatorias de créditos.

   ```
   Ejemplo (Fila 84 de MARZO 2024):
       Col 0: 2024-03-11
       Col 1: Impuesto Débitos y Créditos/DB
       Col 2: 411.46           ← débito (correcto)
       Col 3: 564,305.67       ← debería ser crédito; en realidad es el SALDO
       Col 4: NaN              ← acá debería ir el saldo
   ```

2. **Hojas con nombres inconsistentes**: "ENERO FIN..", "FEBREROO-2024" (con doble O), "FEBRERO" sin año y "FEBRERO 2024" como hojas separadas. Evidencia de trabajo iterativo manual.

3. **Filas mezcladas**: en las columnas 9-10 de las hojas mensuales conviven los movimientos del extracto con los totales que la contadora calcula a mano, mezclados en las mismas filas.

4. **Solo 4 hojas "Table"** post-Tabula vs **19 hojas mensuales** trabajadas a mano: confirma que el XLSX es mayormente trabajo manual, no extracción automática.

### Lo que sí funcionó parsear

Al probar `pdfplumber` sobre el PDF original, el texto extraído tiene una estructura **consistente y predecible**:

```
DD/MM/YY  Concepto  NumeroOperacion  Monto  Saldo
[líneas de continuación opcionales con detalle]
```

Y descubrimos que **el signo del movimiento (débito/crédito) se puede inferir** por la variación del saldo entre líneas consecutivas, lo que nos da una verificación automática de la extracción.

## Decisión

**Parsear el PDF original con `pdfplumber`**, no el XLSX intermedio.

El XLSX queda como referencia para validar nuestros totales contra los que calculó la contadora, pero no como input del parser.

### Algoritmo del parser

1. Para cada página del PDF, extraer texto línea por línea.
2. Aplicar una regex que matchea: `fecha + concepto + nro_operacion + monto + saldo`.
3. Para cada movimiento, comparar el saldo con el del movimiento anterior:
   - Si el saldo subió → es **CRÉDITO**, importe = saldo_actual − saldo_anterior.
   - Si el saldo bajó → es **DÉBITO**, importe = saldo_anterior − saldo_actual.
4. **Validación automática**: `|saldo_actual − saldo_anterior|` debe ser igual al monto extraído de la línea. Si no coincide, levantar excepción.
5. Líneas que no matchean la regex se consideran "detalle adicional" del movimiento anterior (ej: "Operación XXX Generada el...", "Cuentas Propias", "CBU:..."), y se agregan al campo `detalle_adicional`.

## Alternativas consideradas

### Alternativa A: Parsear el XLSX intermedio

- **Pros**: Tabular, no requiere regex compleja.
- **Contras**: 10+ filas por mes están corruptas por la extracción defectuosa del PDF original. Tendríamos que detectar y corregir esas corrupciones, lo cual es más frágil que ir a la fuente.
- **Por qué se descartó**: el XLSX es trabajo manual, no fuente.

### Alternativa B: Pedirle a la contadora que use una herramienta diferente

- **Por qué se descartó**: el objetivo del proyecto es exactamente **liberarla** de hacer trabajo manual. Si la solución requiere que ella siga haciendo trabajo manual, fallamos.

### Alternativa C: OCR sobre imágenes del PDF

- **Pros**: Funciona aún si el PDF es escaneado.
- **Contras**: Mucho más lento, requiere Tesseract o similares, más caro en infra, menos preciso.
- **Por qué se descartó (por ahora)**: el PDF de Supervielle es texto nativo (`pdfplumber.extract_text()` funciona perfectamente). Si llega un banco con PDFs escaneados, se reabre la decisión.

### Alternativa D: Parser tabular con `pdfplumber.extract_tables()`

- **Pros**: Aprovecha la detección automática de tablas de pdfplumber.
- **Contras**: Igual problema que Tabula: la detección de columnas falla en filas con "Pago Cheque de Cámara Recibida" o cuando hay líneas de detalle.
- **Por qué se descartó**: la extracción línea por línea + regex es más robusta para este formato específico.

## Consecuencias

### Positivas

- ✅ Fuente única y confiable: el PDF original del banco.
- ✅ Validación automática por variación de saldo (atrapa errores de parsing).
- ✅ Independiente del trabajo manual de la contadora.
- ✅ Se puede aplicar el mismo enfoque a otros bancos (cambiando la regex).

### Negativas / Trade-offs

- ⚠️ La regex debe ser específica por banco (cada uno tiene formato propio).
- ⚠️ Si Supervielle cambia el formato del PDF, hay que actualizar la regex (mitigación: tests con fixtures reales que detectan esto inmediatamente).
- ⚠️ El parsing es más lento que leer un XLSX, pero seguimos lejos de cualquier problema de performance (70 páginas en pocos segundos).

### Cosas a revisitar

- 🔄 Si en el futuro algún banco entrega XLSX desde su HomeBanking (no post-Tabula), evaluar parsearlo directamente. Bancos como Galicia exportan CSV nativo desde su web.
- 🔄 Si aparecen PDFs escaneados, sumar OCR como fallback.

## Referencias

- Exploración: `scripts/explorar_supervielle.py`
- Bitácora: `docs/bitacora.md` — sección "Día 2"
- pdfplumber: https://github.com/jsvine/pdfplumber
