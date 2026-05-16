# 📓 Bitácora de desarrollo

Diario informal del proyecto. Anotá acá cosas que aprendiste, errores que te costó resolver, recursos útiles. Cronológico, formato libre.

---

## 2025-05-16 — Día 1: Setup inicial y descubrimiento del dominio

### Lo que hicimos

- Definimos el modelo de dominio `MovimientoBancario` con Pydantic v2.
- Configuramos la estructura de carpetas del proyecto.
- Documentamos las primeras 4 decisiones técnicas en ADRs.

### Lo más importante que aprendí hoy

**El dato real corrige el diseño.**

Empezamos asumiendo que íbamos a procesar resúmenes de **tarjeta de crédito** (con campos como `cuota_actual`, `tarjeta_ultimos_4`, etc.). Al analizar los archivos reales que pasó la contadora descubrimos que en realidad son **extractos de cuenta corriente** del Banco Supervielle, con un dominio completamente distinto:

- No hay "compras con cuotas"; hay débitos y créditos.
- Hay un saldo running que debe cuadrar.
- Los conceptos son muy heterogéneos: comisiones, IVA, transferencias, cheques, DEBIN, préstamos, etc.

Por eso refactorizamos `MovimientoBancario` antes de escribir más código. **Conclusión:** siempre mirar los datos reales antes de codear. No diseñar a ciegas.

### Sobre el output final

El objetivo principal del reporte que necesita la contadora es el **Impuesto a los Débitos y Créditos (Ley 25.413)** para presentar a ARCA. Lo vimos en la última página del PDF de Supervielle, donde el propio banco totaliza:

```
Imp Ley 25413 s/Debitos 01/24    14487.74
Imp Ley 25413 s/Creditos 01/24    3876.13
Imp Ley 25413 s/Debitos 02/24    10312.99
...
```

Esto es lo que tenemos que poder regenerar y validar.

### Recursos útiles encontrados hoy

- [HTMX](https://htmx.org/) — alternativa moderna a React para apps server-rendered.
- [pdfplumber docs](https://github.com/jsvine/pdfplumber) — para parsear PDFs tabulares.
- [Pydantic v2 migration guide](https://docs.pydantic.dev/latest/migration/) — diferencias con v1.

### Errores y bloqueos del día

(Ninguno todavía, recién arrancamos. ¡Pronto!)

### Próximos pasos

1. Crear el repo en GitHub y subir el setup inicial.
2. Escribir tests para el modelo `MovimientoBancario`.
3. Empezar con el parser de Supervielle (primer banco): empezar por la versión XLSX que ya viene tabular, y dejar el PDF para después.

---

## 2025-05-16 — Día 2: Exploración del dato real (cambia el plan)

### Lo que hicimos

- Repo creado en GitHub: https://github.com/lucasabrandan/lector-resumenes-bancarios
- Sesión completa de **scripting exploratorio** sobre los tres archivos de la contadora.
- Script reproducible: `scripts/explorar_supervielle.py`.
- ADR-0005 documentando el cambio de estrategia: parsear el PDF, no el XLSX.

### Lo más importante que aprendí hoy

**El XLSX intermedio NO es fuente confiable.** El plan original era parsear el XLSX porque ya viene tabular y "más fácil". Al explorar el dato real descubrimos que en ~10 filas por mes el saldo aparece corrido a la columna "Crédito", por una extracción defectuosa del PDF que hizo Tabula (o similar). Si hubiéramos avanzado con esa estrategia, los totales nunca habrían cuadrado y no sabríamos por qué.

**El método del scripting exploratorio es ORO.** Detectamos:

1. Hojas con nombres inconsistentes (`FEBREROO-2024`, `FEBRERO`, `FEBRERO 2024`) → evidencia de trabajo manual iterativo.
2. Columnas con totales-de-la-contadora mezcladas con datos del extracto (cols 9 y 10).
3. La regla crítica: **el signo del movimiento se infiere por la variación del saldo**, no por la columna donde aparece el monto.

**Validación gratis**: como cada movimiento tiene un saldo posterior, podemos validar que `|saldo_actual − saldo_anterior| == monto`. Si no cuadra, el parser falló. Lo probé con las primeras 5 páginas del PDF y **cuadran 131/131 movimientos**, cero errores.

### El reporte que espera la contadora (descubrimiento en cols 9-10 del XLSX)

Por mes, su reporte tiene:

- **Saldo inicial** del mes.
- **Créditos agrupados por concepto** (transferencias, depósitos, etc.) con sus totales.
- **Débitos agrupados por concepto** (comisiones, IVA, impuestos, compras, etc.) con sus totales.
- **Saldo final** y verificación de cuadre.
- El total de débitos del mes es **lo que va a ARCA** (Impuesto Ley 25.413).

### Bugs cazados (en mi propio código)

1. **`isinstance(fecha, pd.Timestamp)` no matchea `datetime.datetime`.** Pandas devuelve uno u otro según cómo se haya cargado el Excel. Solución: `isinstance(val, (datetime, pd.Timestamp))`.
2. **Asumir que las columnas están donde dice el header.** Falso en datos reales. Hay que validar fila por fila.

### Recursos útiles encontrados hoy

- pdfplumber + regex resultó suficiente para Supervielle. No hizo falta `extract_tables()`.
- El formato de fecha argentino `dd/mm/yy` se parsea con `strptime(s, "%d/%m/%y")`.

### Próximos pasos

1. Escribir el parser real `app/parsers/supervielle_pdf.py` basado en los patrones del script exploratorio.
2. Tests del parser con fixtures reales (anonimizar primero los datos: CUIT, nombres, números de cuenta).
3. Después de Supervielle funcionando: refactorizar a Strategy Pattern para acomodar futuros bancos.

---

<!-- Plantilla para nuevas entradas:

## YYYY-MM-DD — Día N: Título corto

### Lo que hicimos

-

### Lo más importante que aprendí hoy

### Recursos útiles encontrados hoy

-

### Errores y bloqueos del día

-

### Próximos pasos

-

---

-->
