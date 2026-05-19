"""
Modelos SQLAlchemy — tablas de la base de datos.

Separados del modelo de dominio Pydantic a propósito:
- Pydantic (app/domain/models.py): validación y lógica de negocio.
- SQLAlchemy (este archivo): persistencia.

La conversión entre ambos vive en app/services/.
"""

from datetime import date

from sqlalchemy import Date, Index, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MovimientoDB(Base):
    """Un movimiento bancario persistido."""

    __tablename__ = "movimientos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Origen
    banco: Mapped[str] = mapped_column(String(50), nullable=False)
    cuenta: Mapped[str] = mapped_column(String(50), nullable=False)
    archivo_origen: Mapped[str | None] = mapped_column(String(255))
    pagina_origen: Mapped[int | None] = mapped_column(Integer)

    # Datos del movimiento
    fecha: Mapped[date] = mapped_column(Date, nullable=False)
    concepto: Mapped[str] = mapped_column(String(500), nullable=False)
    detalle_adicional: Mapped[str | None] = mapped_column(Text)
    numero_operacion: Mapped[str | None] = mapped_column(String(30))

    # Montos
    importe: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    signo: Mapped[str] = mapped_column(String(10), nullable=False)  # DEBITO/CREDITO
    saldo_posterior: Mapped[float | None] = mapped_column(Numeric(14, 2))
    moneda: Mapped[str] = mapped_column(String(3), default="ARS")

    # Clasificación
    tipo: Mapped[str] = mapped_column(String(50), default="OTRO")

    __table_args__ = (
        Index("ix_movimientos_fecha", "fecha"),
        Index("ix_movimientos_cuenta_fecha", "cuenta", "fecha"),
        Index("ix_movimientos_tipo", "tipo"),
    )
