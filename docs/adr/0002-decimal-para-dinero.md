# ADR-0002: Uso de `Decimal` para montos monetarios

- **Estado**: ✅ Aceptado
- **Fecha**: 2025-05-16
- **Autor**: Equipo

## Contexto

Estamos construyendo un sistema que procesa movimientos bancarios y genera reportes contables para presentar a ARCA (organismo de recaudación de Argentina). La contadora controla los totales **centavo por centavo**: si la suma de los movimientos de un mes difiere en $0,01 del extracto bancario, hay que encontrar el error.

Python tiene dos tipos numéricos disponibles para esto:

1. **`float`** (IEEE 754 punto flotante binario): rápido, pero impreciso.
2. **`decimal.Decimal`** (aritmética decimal exacta): más lento, pero exacto.

## Decisión

**Usar `Decimal` para TODOS los campos monetarios en todo el sistema.** Cero excepciones.

Aplicar la siguiente regla en todos los modelos Pydantic:

```python
importe: Decimal = Field(...)

@field_validator("importe")
@classmethod
def dos_decimales(cls, v: Decimal) -> Decimal:
    return v.quantize(Decimal("0.01"))
```

Y en la base de datos:

```sql
importe NUMERIC(15, 2) NOT NULL   -- ✅ correcto
-- importe REAL                    -- ❌ NUNCA
-- importe FLOAT                   -- ❌ NUNCA
```

## Alternativas consideradas

### Alternativa A: Usar `float`

```python
>>> 0.1 + 0.2
0.30000000000000004

>>> sum([0.1] * 10)
0.9999999999999999
```

Esto pasa porque muchos números decimales no se pueden representar exactamente en binario. Al sumar 1500 movimientos de un extracto, las diferencias se acumulan.

- **Pros**: Performance (~10x más rápido que Decimal).
- **Contras**: Error silencioso en sumatorias. Para un proyecto contable es **inaceptable**.
- **Por qué se descartó**: la corrección es innegociable en finanzas. La performance no es un problema en nuestro caso (1500 movimientos parseados en segundos, no necesitamos milisegundos).

### Alternativa B: Usar enteros representando centavos

Ej: `importe_centavos: int = 12345` para representar $123.45.

- **Pros**: Velocidad de int, sin imprecisión.
- **Contras**: Toda la aritmética y serialización debe acordarse de dividir/multiplicar por 100. Aumenta el riesgo de bugs por errores humanos.
- **Por qué se descartó**: Decimal nos da lo mejor de ambos mundos. Si performance fuera crítica, sería una opción.

### Alternativa C: Usar `float` y redondear al final

- **Pros**: Performance.
- **Contras**: El redondeo solo en el resultado final no soluciona errores acumulados intermedios. Y "redondear al final" es ambiguo: ¿al guardar? ¿al mostrar? ¿al sumar?
- **Por qué se descartó**: parches sobre un cimiento podrido nunca son buena idea.

## Consecuencias

### Positivas

- ✅ Cero errores de centavos en sumatorias.
- ✅ Compatibilidad con la columna `NUMERIC` de PostgreSQL/SQLite.
- ✅ Cumple expectativas de auditoría contable (presentaciones a ARCA).
- ✅ Pydantic acepta `Decimal` nativamente, sin código custom.

### Negativas / Trade-offs

- ⚠️ Performance ~10x menor que `float`. Mitigación: nuestros volúmenes son pequeños (~1500 movimientos por extracto, ~20.000/mes en producción).
- ⚠️ Las librerías estadísticas (numpy, scikit-learn) no manejan Decimal nativamente. Mitigación: para reportes estadísticos, convertir a float **solo al final**.

### Cosas a revisitar

- 🔄 Si en el futuro hacemos análisis estadístico masivo (ej: ML para detectar fraudes), evaluar tener una "vista" en float separada del modelo canónico.

## Demostración del problema

Script para probar y nunca olvidarse:

```python
from decimal import Decimal

# Con float (mal)
movimientos_float = [0.1, 0.2, 0.3]
print(sum(movimientos_float))  # 0.6000000000000001 ❌

# Con Decimal (bien)
movimientos_dec = [Decimal("0.1"), Decimal("0.2"), Decimal("0.3")]
print(sum(movimientos_dec))    # 0.6 ✅
```

## Referencias

- [Python docs: decimal module](https://docs.python.org/3/library/decimal.html)
- [What Every Computer Scientist Should Know About Floating-Point Arithmetic](https://docs.oracle.com/cd/E19957-01/806-3568/ncg_goldberg.html)
- [Pydantic Decimal support](https://docs.pydantic.dev/latest/api/standard_library_types/#decimaldecimal)
