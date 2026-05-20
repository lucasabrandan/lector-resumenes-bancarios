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
