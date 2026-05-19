# ADR-0006: Separar el Impuesto Ley 25.413 en dos tipos (sobre débitos / sobre créditos)

- **Estado**: ✅ Aceptado
- **Fecha**: 2025-05-19
- **Autor**: Equipo
- **Reemplaza a**: parte de ADR-0001 (la categorización original)

## Contexto

Durante la **iteración 3.3** (clasificación automática de `TipoMovimiento`), implementamos un clasificador que mapeaba todos los movimientos cuyo concepto empezara con "Impuesto Débitos y Créditos" a una única categoría: `TipoMovimiento.IMPUESTO_DEBITO_CREDITO`.

Al validar contra los totales oficiales que el propio Banco Supervielle imprime al final del PDF (página 69), descubrimos diferencias sistemáticas:

```
Mes        Oficial Débitos     Nuestro Total        Diferencia
01/2024    $14,487.74          $18,363.87           +$3,876.13
02/2024    $10,312.99          $19,642.99           +$9,330.00
...
```

Al investigar, notamos que **las diferencias coincidían exactamente con los totales oficiales de "Imp Ley 25413 s/Creditos"** de cada mes. Es decir, nuestros totales mezclaban dos métricas distintas que el banco reporta separadas.

### El descubrimiento

El concepto del extracto siempre termina con un sufijo:

- **`Impuesto Débitos y Créditos/DB`**: el impuesto se cobró por un **débito** previo (compra, transferencia enviada, comisión, etc.).
- **`Impuesto Débitos y Créditos/CR`**: el impuesto se cobró por un **crédito** previo (transferencia recibida, depósito de cheque, etc.).

**Ambos son débitos en la cuenta** (siempre sale plata), pero **ARCA los reporta separadamente** porque las alícuotas pueden ser distintas (en la práctica, ambas son 0.6%, pero la normativa permite que difieran).

El banco lo confirma en la última página del extracto, donde detalla por mes:

```
Imp Ley 25413 s/Debitos 01/24   14487.74
Imp Ley 25413 s/Creditos 01/24   3876.13
```

### Validación de la hipótesis

Re-corriendo el parser con los conceptos separados por sufijo (`/DB` vs `/CR`), los totales **cuadran al centavo** contra los oficiales del banco en los 17 meses del extracto:

```
Mes        Oficial /DB      Nuestro /DB      Diff
01/2024    $14,487.74       $14,487.74       $0.00  ✅
02/2024    $10,312.99       $10,312.99       $0.00  ✅
... (todos los meses ✅)
```

## Decisión

Reemplazar el enum único:

```python
class TipoMovimiento(str, Enum):
    IMPUESTO_DEBITO_CREDITO = "IMPUESTO_DEBITO_CREDITO"  # ❌ ya no
```

Por dos enums específicos:

```python
class TipoMovimiento(str, Enum):
    IMPUESTO_LEY_25413_SOBRE_DEBITOS = "IMPUESTO_LEY_25413_SOBRE_DEBITOS"
    IMPUESTO_LEY_25413_SOBRE_CREDITOS = "IMPUESTO_LEY_25413_SOBRE_CREDITOS"
```

Y actualizar las reglas del clasificador para usar el sufijo del concepto:

```python
(r"Impuesto\s+Débitos\s+y\s+Créditos/DB", TipoMovimiento.IMPUESTO_LEY_25413_SOBRE_DEBITOS),
(r"Impuesto\s+Débitos\s+y\s+Créditos/CR", TipoMovimiento.IMPUESTO_LEY_25413_SOBRE_CREDITOS),
```

## Alternativas consideradas

### Alternativa A: Mantener un solo tipo y agrupar después

- **Pros**: Modelo más simple, menos enums.
- **Contras**: La distinción se perdería si más adelante alguien filtra solo por tipo. Habría que recordar siempre "y además filtrá por sufijo del concepto".
- **Por qué se descartó**: el modelo de dominio debe reflejar las distinciones reales del negocio. Si ARCA los pide separados, nuestro modelo los debe modelar separados.

### Alternativa B: Usar el campo `signo` para distinguir

- **Pros**: Reutiliza una propiedad existente.
- **Contras**: **Ambos impuestos son técnicamente DEBITO** (sale plata de la cuenta). El signo no los diferencia.
- **Por qué se descartó**: el dominio nos contradice; los datos reales mostraron que es semánticamente incorrecto.

### Alternativa C: Agregar un campo nuevo `aplica_sobre: Literal["DEBITO", "CREDITO"]`

- **Pros**: Más estructurado.
- **Contras**: Solo aplica a este tipo de movimiento, agregaría un campo que sería `None` para el 99% de los movimientos.
- **Por qué se descartó**: viola YAGNI ("You Aren't Gonna Need It"). Si en el futuro aparecen otros impuestos con la misma distinción, lo reconsideramos.

## Consecuencias

### Positivas

- ✅ Los totales del sistema cuadran al centavo contra los oficiales del banco.
- ✅ La contadora puede generar el reporte ARCA agrupando por tipo directamente, sin tener que mirar el sufijo del concepto.
- ✅ El modelo de dominio refleja la realidad fiscal argentina.
- ✅ Nombre del enum más descriptivo y específico (Ley 25.413 es la norma específica).

### Negativas / Trade-offs

- ⚠️ Romper un código que ya estaba en uso (`IMPUESTO_DEBITO_CREDITO` aparecía en tests y código). Mitigación: refactor controlado con tests como red de seguridad.
- ⚠️ Un enum más que mantener.

### Cosas a revisitar

- 🔄 Si más adelante encontramos un banco que NO usa el sufijo `/DB`/`/CR` en sus extractos, habrá que inferir la distinción de otra manera (ej: mirando el movimiento previo en el extracto).

## Referencias

- Validación de hipótesis: comparación contra última página del PDF "Imp Ley 25413 s/Debitos/Creditos".
- Ley 25.413 (texto oficial): https://servicios.infoleg.gob.ar/infolegInternet/anexos/65000-69999/66345/norma.htm
- Código modificado: `app/domain/models.py`, `app/parsers/clasificador.py`.
- Tests actualizados: `tests/unit/test_movimiento.py`, `tests/unit/test_clasificador.py`.