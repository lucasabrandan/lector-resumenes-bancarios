"""
Modelos SQLAlchemy — tablas de la base de datos.

Separados del modelo de dominio Pydantic a propósito:
- Pydantic (app/domain/models.py): validación y lógica de negocio.
- SQLAlchemy (este archivo): persistencia.

La conversión entre ambos vive en app/services/.
"""

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


TODOS_LOS_PERMISOS = ["dashboard", "upload", "movimientos", "reporte", "percepciones", "monotributo", "clientes", "usuarios"]


class UsuarioClienteDB(Base):
    """Tabla de asignacion usuario <-> cliente."""

    __tablename__ = "usuario_cliente"

    usuario_id: Mapped[int] = mapped_column(Integer, ForeignKey("usuarios.id", ondelete="CASCADE"), primary_key=True)
    cliente_id: Mapped[int] = mapped_column(Integer, ForeignKey("clientes.id", ondelete="CASCADE"), primary_key=True)


class ClienteDB(Base):
    """Cliente del estudio contable."""

    __tablename__ = "clientes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(String(200), nullable=False)
    cuit: Mapped[str | None] = mapped_column(String(13))
    categoria: Mapped[str] = mapped_column(String(50), default="General")
    # Para monotributistas: categoria ARCA (A-K) y actividad
    categoria_monotributo: Mapped[str | None] = mapped_column(String(1))
    actividad_monotributo: Mapped[str] = mapped_column(String(20), default="servicios")
    activo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    creado: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    usuarios: Mapped[list["UsuarioDB"]] = relationship(
        "UsuarioDB", secondary="usuario_cliente", back_populates="clientes",
    )
    movimientos: Mapped[list["MovimientoDB"]] = relationship("MovimientoDB", back_populates="cliente")


class UsuarioDB(Base):
    """Usuario del sistema."""

    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    nombre: Mapped[str] = mapped_column(String(100), nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    permisos: Mapped[str] = mapped_column(String(500), default="dashboard,movimientos,reporte", nullable=False)
    creado: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    clientes: Mapped[list["ClienteDB"]] = relationship(
        "ClienteDB", secondary="usuario_cliente", back_populates="usuarios",
    )

    def tiene_permiso(self, permiso: str) -> bool:
        return permiso in self.permisos.split(",")

    def lista_permisos(self) -> list[str]:
        return [p for p in self.permisos.split(",") if p]

    def es_admin(self) -> bool:
        return self.tiene_permiso("usuarios")

    def ids_clientes(self) -> list[int]:
        return [c.id for c in self.clientes]


class MovimientoDB(Base):
    """Un movimiento bancario persistido."""

    __tablename__ = "movimientos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Origen
    banco: Mapped[str] = mapped_column(String(50), nullable=False)
    cuenta: Mapped[str] = mapped_column(String(50), nullable=False)
    archivo_origen: Mapped[str | None] = mapped_column(String(255))
    pagina_origen: Mapped[int | None] = mapped_column(Integer)

    # Cliente asociado
    cliente_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("clientes.id"), nullable=True)
    cliente: Mapped["ClienteDB | None"] = relationship("ClienteDB", back_populates="movimientos")

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
        Index("ix_movimientos_cliente", "cliente_id"),
    )


class ComprobanteDB(Base):
    """Comprobante emitido importado desde ARCA (Mis Comprobantes)."""

    __tablename__ = "comprobantes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    cliente_id: Mapped[int] = mapped_column(Integer, ForeignKey("clientes.id", ondelete="CASCADE"), nullable=False)
    cliente: Mapped["ClienteDB"] = relationship("ClienteDB")

    fecha: Mapped[date] = mapped_column(Date, nullable=False)
    tipo_comprobante: Mapped[str] = mapped_column(String(50), nullable=False)  # Factura C, Nota de Credito C, etc.
    punto_venta: Mapped[int] = mapped_column(Integer, nullable=False)
    numero_desde: Mapped[int] = mapped_column(Integer, nullable=False)
    numero_hasta: Mapped[int] = mapped_column(Integer, nullable=False)
    cod_autorizacion: Mapped[str | None] = mapped_column(String(30))
    tipo_doc_receptor: Mapped[str | None] = mapped_column(String(10))
    nro_doc_receptor: Mapped[str | None] = mapped_column(String(15))
    denominacion_receptor: Mapped[str | None] = mapped_column(String(300))
    moneda: Mapped[str] = mapped_column(String(5), default="PES")
    tipo_cambio: Mapped[float] = mapped_column(Numeric(14, 6), default=1.0)
    importe_total: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)

    # Para saber de qué archivo vino y detectar duplicados
    archivo_origen: Mapped[str | None] = mapped_column(String(255))
    creado: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_comprobantes_cliente_fecha", "cliente_id", "fecha"),
    )
