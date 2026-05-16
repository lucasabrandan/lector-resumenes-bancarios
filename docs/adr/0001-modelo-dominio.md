# ADR-0001: Modelo de dominio — MovimientoBancario

- **Estado**: ✅ Aceptado
- **Fecha**: 2025-05-16
- **Autor**: Equipo

## Contexto

Necesitamos representar en código un movimiento de cuenta bancaria, de forma que sea **única** (un mismo modelo para todos los bancos) y **segura** (validada y sin errores de centavos).

Cada banco entrega sus extractos en formatos distintos:
- Supervielle: PDF con tabla "Fecha / Concepto / Débito / Crédito / Saldo"
- Santander: PDF con tabla similar pero columnas distintas
- Galicia: CSV/Excel con headers en español o inglés según producto

El sistema necesita **un modelo canónico** al que todos los parsers traducen sus datos. Esto es un caso clásico del patrón **"Translate at the boundary"**: en el borde del sistema (parsers) traducís a tu modelo interno, y de ahí en adelante todo el código habla un solo idioma.

Además, descubrimos al analizar los archivos reales de la contadora que **NO estamos modelando consumos de tarjeta de crédito** (como pensábamos al inicio) sino **movimientos de cuenta corriente**, donde:
- Cada movimiento es débito o crédito.
- El saldo se acumula.
- Los conceptos incluyen tipos muy variados: comisiones, IVA, transferencias, cheques, DEBIN, préstamos, etc.

## Decisión

Definir `MovimientoBancario` como un **modelo Pydantic v2 inmutable** con las siguientes características clave:

1. **Campos obligatorios**: `banco`, `cuenta`, `fecha`, `concepto`, `importe`, `signo`.
2. **`importe` siempre positivo** y el signo se expresa por separado en el enum `SignoMovimiento` (DEBITO / CREDITO). Esto es más explícito que usar números negativos.
3. **`importe: Decimal`** (nunca `float`) — ver ADR-0002.
4. **`tipo: TipoMovimiento`**: enum cerrado con categorías predefinidas alineadas a los conceptos que la contadora necesita agrupar.
5. **`frozen=True`**: el movimiento es inmutable una vez creado. Si necesitás "modificarlo", creás uno nuevo.
6. **`extra="forbid"`**: si un parser devuelve un campo no declarado, el modelo lo rechaza. Detecta bugs temprano.
7. **Campos de trazabilidad opcionales**: `archivo_origen`, `pagina_origen`, `hash_movimiento`. Útiles para auditoría y deduplicación pero no obligatorios al parsear.

## Alternativas consideradas

### Alternativa A: Una clase distinta por cada banco

- **Pros**: Cada parser puede usar los nombres "naturales" del banco.
- **Contras**: El resto del código tendría que conocer cada variante, y agregar un banco nuevo requeriría tocar muchos archivos.
- **Por qué se descartó**: rompe el principio Open/Closed. Queremos que el resto del sistema sea agnóstico al banco origen.

### Alternativa B: Usar `dataclass` en lugar de Pydantic

- **Pros**: Es estándar de la librería, no agrega dependencia.
- **Contras**: No valida tipos en runtime. Si un parser devuelve un string donde esperamos Decimal, el bug aparece mucho más tarde.
- **Por qué se descartó**: Pydantic valida en construcción y nos da serialización JSON gratis para la API REST.

### Alternativa C: Importe con signo (positivo o negativo)

- **Pros**: Más compacto, un solo campo.
- **Contras**: Ambigüedad implícita. Un parser podría confundirse y meter un débito como positivo. Además, dificulta agregaciones tipo `SUM(importe) WHERE signo='DEBITO'`.
- **Por qué se descartó**: prefiero hacer explícito el signo. Es una decisión de "código defensivo".

### Alternativa D: `tipo` como string libre

- **Pros**: Flexible, soporta cualquier banco sin cambios de código.
- **Contras**: Imposible agrupar consistentemente. "Compra Visa Débito" vs "compra visa debito" serían dos categorías.
- **Por qué se descartó**: el enum cerrado obliga a pensar dónde encaja cada concepto, y rompe el build si algo no encaja (lo cual es BUENO).

## Consecuencias

### Positivas

- ✅ Una sola fuente de verdad sobre qué es un movimiento bancario.
- ✅ Validación automática al construir: bugs detectados al parsear, no al reportar.
- ✅ Serialización JSON automática para la API.
- ✅ Inmutabilidad reduce bugs por aliasing.
- ✅ Trazabilidad incorporada para auditoría.

### Negativas / Trade-offs

- ⚠️ Agregar un tipo nuevo de movimiento requiere modificar el enum `TipoMovimiento` (no es solo configuración).
- ⚠️ Pydantic agrega ~5-10ms de overhead por movimiento (despreciable para nuestros volúmenes: 1500 movimientos/extracto).

### Cosas a revisitar

- 🔄 Si en el futuro necesitamos soportar movimientos en USD con cotización (extractos de caja de ahorro en dólares), habrá que agregar campos `cotizacion` y `importe_pesos`.
- 🔄 El campo `hash_movimiento` está declarado pero la lógica de generación se definirá en ADR-0005 (deduplicación).

## Referencias

- Patrón Anti-Corruption Layer / Translate at the boundary: Eric Evans, *Domain-Driven Design* (2003).
- Pydantic v2 docs: https://docs.pydantic.dev/latest/
- Código: `app/domain/models.py`
