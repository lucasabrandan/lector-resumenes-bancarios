# ADR-0003: Stack tecnológico — FastAPI + Pydantic + SQLAlchemy

- **Estado**: ✅ Aceptado
- **Fecha**: 2025-05-16
- **Autor**: Equipo

## Contexto

Necesitamos elegir el stack tecnológico de backend para una aplicación web que:

1. Reciba archivos (PDF/XLSX/CSV) de extractos bancarios.
2. Los procese según el banco emisor.
3. Almacene movimientos normalizados en una base de datos.
4. Genere reportes (Excel/PDF) descargables.
5. Sirva una interfaz web para que la contadora opere.

El proyecto es además un **ejercicio de aprendizaje**: el autor está estudiando desarrollo backend con Python y quiere profundizar conceptos modernos.

## Decisión

| Capa | Tecnología | Versión |
|---|---|---|
| Lenguaje | Python | 3.11+ |
| Web framework | FastAPI | 0.115+ |
| Validación / modelos | Pydantic | 2.x |
| ORM | SQLAlchemy | 2.x |
| DB (dev) | SQLite | (built-in) |
| DB (prod) | PostgreSQL | 15+ |
| Migrations | Alembic | 1.x |
| Tests | pytest | 8.x |
| Lint / format | Ruff | 0.7+ |
| Type check | mypy | 1.13+ |

## Alternativas consideradas

### Framework web

**Alternativa A: Django + DRF**
- Pros: Batteries-included (admin, auth, ORM), comunidad enorme.
- Contras: Mucho más opinionado, curva de aprendizaje más alta, no async nativo.
- Por qué se descartó: para este proyecto pequeño y enfocado en API + procesamiento, FastAPI es más directo.

**Alternativa B: Flask**
- Pros: Minimalista, muy popular en Argentina, amplia documentación.
- Contras: Sin tipado nativo, sin validación automática, sin docs autogenerados.
- Por qué se descartó: FastAPI cubre lo mismo + tipado moderno + Swagger automático.

**Alternativa C: FastAPI** ✅ **ELEGIDA**
- Pros:
  - Tipado nativo con Pydantic (alineado con nuestro modelo de dominio).
  - Documentación interactiva automática (Swagger UI + ReDoc).
  - Performance excelente (Starlette + uvicorn).
  - Validación de requests/responses gratis.
- Contras:
  - Comunidad más chica que Django/Flask (aunque creciendo fuerte).
  - Async puede confundir al principio.

### ORM

**Alternativa A: Sin ORM, SQL crudo con psycopg/sqlite3**
- Por qué se descartó: para un proyecto en aprendizaje, ORM enseña patrones útiles. SQL crudo será para casos puntuales (queries de reportes complejos).

**Alternativa B: SQLModel**
- Pros: Combina SQLAlchemy + Pydantic en una sola clase, mismo autor que FastAPI.
- Contras: Más nuevo, menos documentación, abstracciones a veces oscuras.
- Por qué se descartó por ahora: preferimos aprender SQLAlchemy "puro" primero. Migrar a SQLModel después es trivial.

**Alternativa C: SQLAlchemy 2.x** ✅ **ELEGIDA**
- Pros:
  - Estándar de la industria Python.
  - La versión 2 tiene tipado moderno con `Mapped[]`.
  - Migrations maduras con Alembic.
- Contras:
  - Curva de aprendizaje más alta.

### Base de datos

**Decisión dual:**
- **SQLite para desarrollo** (sin instalación, archivo único, rapidísimo de levantar).
- **PostgreSQL para producción** (concurrencia real, tipos avanzados como `JSONB`, performance industrial).

Con SQLAlchemy esto es transparente: el código no cambia, solo la URL de conexión.

## Consecuencias

### Positivas

- ✅ Tipado consistente de punta a punta: Pydantic en domain, FastAPI en API, SQLAlchemy 2 en DB.
- ✅ Documentación interactiva gratis: `/docs` y `/redoc`.
- ✅ Stack moderno, en alta demanda en el mercado actual.
- ✅ Tests fáciles gracias a inyección de dependencias de FastAPI.
- ✅ Desarrollo local sin servicios externos (SQLite).

### Negativas / Trade-offs

- ⚠️ Curva de aprendizaje para quien viene de Flask/Django.
- ⚠️ Async puede ser confuso (en este proyecto lo usamos solo donde aporta: endpoints I/O bound).

### Cosas a revisitar

- 🔄 Cuando el proyecto crezca, evaluar si conviene migrar a SQLModel para reducir duplicación entre modelos Pydantic y SQLAlchemy.
- 🔄 Si necesitamos workers (procesar archivos grandes en background), agregar Celery o ARQ.

## Referencias

- FastAPI: https://fastapi.tiangolo.com/
- Pydantic v2: https://docs.pydantic.dev/latest/
- SQLAlchemy 2.0: https://docs.sqlalchemy.org/en/20/
