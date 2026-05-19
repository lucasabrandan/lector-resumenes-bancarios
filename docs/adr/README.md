# Architecture Decision Records (ADRs)

Cada decisión técnica importante del proyecto vive acá como un documento numerado.

## Índice

| # | Título | Estado |
|---|---|---|
| [0001](0001-modelo-dominio.md) | Modelo de dominio: MovimientoBancario | ✅ Aceptado |
| [0002](0002-decimal-para-dinero.md) | Uso de `Decimal` para montos monetarios | ✅ Aceptado |
| [0003](0003-stack-tecnologico.md) | Stack: FastAPI + Pydantic + SQLAlchemy | ✅ Aceptado |
| [0004](0004-frontend-jinja-htmx.md) | Frontend con Jinja2 + HTMX (MVP) | ✅ Aceptado |
| [0005](0005-parsear-pdf-no-xlsx.md) | Parsear el PDF original, no el XLSX intermedio | ✅ Aceptado |
| [0006](0006-tipos-impuesto-separados.md) | Separar el Impuesto Ley 25.413 en dos tipos | ✅ Aceptado |

## Cómo escribir un ADR nuevo

1. Copiar la plantilla [`_template.md`](_template.md).
2. Numerarlo con el siguiente número disponible (ej: `0005-titulo-corto.md`).
3. Completar las secciones: Contexto, Decisión, Alternativas, Consecuencias.
4. Agregarlo al índice de este README.
5. Si reemplaza a un ADR anterior, marcar el anterior como "Superseded by ADR-XXXX".

## Estados posibles

- 🟡 **Propuesto**: en discusión
- ✅ **Aceptado**: en uso
- ❌ **Rechazado**: se evaluó y descartó
- 🔄 **Superseded**: reemplazado por otro ADR (linkear al nuevo)
- 🗑️ **Deprecated**: ya no aplica (ej: la tecnología cambió)