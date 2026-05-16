# 📊 Lector de Resúmenes Bancarios

> Procesador automático de extractos bancarios argentinos para conciliación contable y presentaciones ante ARCA (ex AFIP).

[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg)](https://fastapi.tiangolo.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

## 🎯 Problema que resuelve

Los contadores argentinos pierden horas cada mes procesando manualmente los extractos bancarios para:

- Conciliar movimientos.
- Calcular el **Impuesto a los Débitos y Créditos (Ley 25.413)** para ARCA.
- Detectar movimientos duplicados o faltantes.
- Generar reportes mensuales agrupados.

Cada banco entrega los datos en formatos distintos (PDF, CSV, XLS) con estructuras propias, y los errores de centavos en los totales son frecuentes. Este proyecto automatiza ese flujo.

## ⚙️ Stack técnico

| Capa | Tecnología | Por qué |
|---|---|---|
| Backend | **FastAPI** + Python 3.11 | Tipado fuerte, validación automática, async |
| Validación | **Pydantic v2** | Modelos seguros, sin float para dinero |
| Parsers | **pdfplumber**, **pandas**, **openpyxl** | Extracción multi-formato |
| Persistencia | **SQLAlchemy 2** + **SQLite** (dev) / **PostgreSQL** (prod) | Aritmética decimal exacta |
| Frontend | **Jinja2** + **HTMX** (MVP) | Sin build, una sola codebase |
| Tests | **pytest** + **pytest-cov** | Cobertura objetivo: >80% |

## 🏗️ Arquitectura

```
┌─────────────┐   ┌──────────────┐   ┌──────────────┐   ┌──────────────┐
│   Upload    │──▶│   Parser     │──▶│ Normalizador │──▶│   Reporte    │
│ (PDF/XLS)   │   │ (Strategy)   │   │  + Dedupe    │   │  (XLSX/PDF)  │
└─────────────┘   └──────────────┘   └──────────────┘   └──────────────┘
                         │                   │
                         ▼                   ▼
                  ┌──────────────┐    ┌──────────────┐
                  │ Movimiento   │    │   SQLite /   │
                  │  Bancario    │    │  PostgreSQL  │
                  │  (Pydantic)  │    │              │
                  └──────────────┘    └──────────────┘
```

Patrones aplicados:

- **Strategy Pattern**: cada banco implementa una interfaz `ParserBanco` común.
- **Factory Pattern**: detección automática del parser según el archivo.
- **Repository Pattern**: separación entre lógica de dominio y persistencia.

## 📦 Instalación

```bash
# Clonar
git clone https://github.com/TU-USUARIO/lector-resumenes-bancarios.git
cd lector-resumenes-bancarios

# Crear entorno virtual
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# .venv\Scripts\activate   # Windows

# Instalar dependencias
pip install -r requirements.txt

# Correr la app
uvicorn app.api.main:app --reload
```

Luego abrir: http://localhost:8000

## 🧪 Tests

```bash
pytest                          # Correr todos los tests
pytest --cov=app                # Con cobertura
pytest tests/unit -v            # Solo unit tests
```

## 📚 Documentación

| Documento | Para qué sirve |
|---|---|
| [docs/adr/](docs/adr) | Architecture Decision Records: el "por qué" de cada decisión técnica |
| [docs/bitacora.md](docs/bitacora.md) | Diario de desarrollo: aprendizajes y obstáculos |
| [docs/dominio.md](docs/dominio.md) | Glosario del dominio bancario y contable |

## 🏦 Bancos soportados

| Banco | Estado | Formato |
|---|---|---|
| Supervielle | 🚧 En desarrollo | PDF (cuenta corriente) |
| Santander | 📋 Planeado | PDF, XLSX |
| Galicia | 📋 Planeado | PDF, CSV |
| BBVA | 📋 Planeado | PDF, XLSX |

## 📝 Licencia

MIT — ver [LICENSE](LICENSE).

## 👨‍💻 Autor

Proyecto desarrollado como ejercicio de aprendizaje en desarrollo backend con Python.
