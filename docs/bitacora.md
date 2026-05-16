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
