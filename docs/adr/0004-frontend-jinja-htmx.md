# ADR-0004: Frontend con Jinja2 + HTMX (MVP)

- **Estado**: ✅ Aceptado
- **Fecha**: 2025-05-16
- **Autor**: Equipo

## Contexto

Necesitamos una interfaz web para que la contadora:

1. Suba archivos de extractos (PDF/XLSX).
2. Vea los movimientos procesados.
3. Filtre por mes / tipo de movimiento.
4. Descargue reportes generados.

El proyecto es de aprendizaje con foco en backend (Python/FastAPI). La usuaria final es una contadora, no un usuario consumer; lo importante es **claridad y funcionalidad**, no estética sofisticada.

## Decisión

**Para el MVP, usar FastAPI + Jinja2 + HTMX, sin frontend separado.**

- **Jinja2**: motor de templates server-side, FastAPI lo soporta nativamente.
- **HTMX**: librería JS pequeña (~14KB) que permite interactividad (forms, parciales, lazy loading) sin escribir JavaScript propio.

Posterior al MVP funcional, evaluar agregar un frontend React **solo si**:
- El proyecto justifica un portfolio full-stack.
- Aparecen interacciones complejas que HTMX no resuelve elegantemente.

## Alternativas consideradas

### Alternativa A: React (Vite) + FastAPI como API REST

- **Pros**: Frontend moderno, muy demandado en el mercado, separación clara de capas.
- **Contras**: Doble codebase, doble deploy, doble curva de aprendizaje (TypeScript + ecosistema React), CORS, autenticación más compleja.
- **Por qué se descartó (por ahora)**: el proyecto es de aprendizaje **backend**. Agregar React desviaría foco. Además, la usuaria final no se beneficia de SPA.

### Alternativa B: Next.js + FastAPI

- **Pros**: SSR + ecosistema React.
- **Contras**: Más complejo que Vite para este caso, overkill.
- **Por qué se descartó**: misma razón que A, más overhead.

### Alternativa C: Streamlit

- **Pros**: 50 líneas de Python y tenés UI funcional.
- **Contras**: UI rígida, performance limitada, no se ve "profesional" en un portfolio.
- **Por qué se descartó**: bueno para prototipos internos, no para esto.

### Alternativa D: Jinja2 + HTMX ✅ **ELEGIDA**

- **Pros**:
  - Una sola codebase (todo Python).
  - Server-side rendering: SEO friendly (no relevante acá pero buena práctica).
  - HTMX permite UX moderna (loading states, parciales, polling) sin SPA.
  - Tendencia creciente (HTMX, Hotwire, Phoenix LiveView): server-rendered moderno está de vuelta.
  - Despliegue trivial: un solo servicio.
- **Contras**:
  - Menos "vistoso" para portfolios que buscan trabajo de frontend.
  - Si la app crece mucho en interactividad, puede quedar corto.

## Consecuencias

### Positivas

- ✅ Foco en backend, que es el objetivo del proyecto.
- ✅ Deploy simple: un solo `uvicorn` corriendo.
- ✅ Tests E2E más simples (sin headless browser obligatorio).
- ✅ Aprendizaje de patrones server-rendered, que están volviendo.

### Negativas / Trade-offs

- ⚠️ Si en el futuro queremos una app móvil nativa, vamos a necesitar la API REST desacoplada (mitigación: estructurar los routers de FastAPI desde el día 1 separando rutas HTML de rutas JSON).
- ⚠️ Menos exposición a tecnologías frontend modernas, si eso es objetivo de aprendizaje.

### Mitigación clave

**Estructurar los endpoints de FastAPI en dos grupos:**

```
app/api/routes/
├── views.py    # Devuelven HTML (Jinja2) → para la web
└── api.py      # Devuelven JSON → reutilizable por React/móvil después
```

Esto significa que el día que quieras agregar React, ya tenés una API REST funcional debajo. No tirás nada.

### Cosas a revisitar

- 🔄 Cuando el MVP esté funcionando, evaluar si vale agregar React encima como ejercicio adicional.
- 🔄 Si aparecen vistas con muchísima interactividad (drag-and-drop, gráficos en tiempo real), considerar React puntualmente para esa vista.

## Referencias

- HTMX: https://htmx.org/
- Jinja2 en FastAPI: https://fastapi.tiangolo.com/advanced/templates/
- Carson Gross, "Hypermedia Systems": https://hypermedia.systems/
