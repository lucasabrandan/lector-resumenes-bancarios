"""
Configuración de SQLAlchemy: engine, sesión y Base declarativa.

SQLite para desarrollo. Migrar a PostgreSQL es cambiar una línea
(la URL de conexión).
"""

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

# La DB vive en la raíz del proyecto, fuera de app/.
_DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "lector.db"
_DB_PATH.parent.mkdir(parents=True, exist_ok=True)

DATABASE_URL = f"sqlite:///{_DB_PATH}"

engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    """Dependency de FastAPI: una sesión por request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def crear_tablas():
    """Crea todas las tablas. Para desarrollo rápido, sin Alembic."""
    import app.db.models  # noqa: F401 — registra todos los modelos antes de create_all
    Base.metadata.create_all(bind=engine)
    _migrar_columnas()


def _migrar_columnas():
    """Agrega columnas nuevas a tablas existentes (mini-migración sin Alembic)."""
    import sqlite3
    conn = sqlite3.connect(str(_DB_PATH))
    cursor = conn.cursor()

    _add_column_if_missing(cursor, "movimientos", "creado", "DATETIME")
    _add_column_if_missing(cursor, "configuracion", "id", None)  # tabla nueva, skip

    conn.commit()
    conn.close()


def _add_column_if_missing(cursor, table: str, column: str, col_type: str | None):
    """Agrega una columna si no existe en la tabla."""
    if col_type is None:
        return
    try:
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
    except Exception:
        pass  # ya existe
