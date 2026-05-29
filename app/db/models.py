"""
Modelos SQLAlchemy — tablas de la base de datos.

Separados del modelo de dominio Pydantic a propósito:
- Pydantic (app/domain/models.py): validación y lógica de negocio.
- SQLAlchemy (este archivo): persistencia.

La conversión entre ambos vive en app/services/.
"""

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Index, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


TODOS_LOS_PERMISOS = ["dashboard", "upload", "movimientos", "reporte", "percepciones", "sircreb", "monotributo", "usuarios", "configuracion"]


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

    def tiene_permiso(self, permiso: str) -> bool:
        return permiso in self.permisos.split(",")

    def lista_permisos(self) -> list[str]:
        return [p for p in self.permisos.split(",") if p]

    def es_admin(self) -> bool:
        return self.tiene_permiso("usuarios")


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

    # Timestamp de carga (para auto-expiración)
    creado: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_movimientos_fecha", "fecha"),
        Index("ix_movimientos_cuenta_fecha", "cuenta", "fecha"),
        Index("ix_movimientos_tipo", "tipo"),
    )


class ComprobanteDB(Base):
    """Comprobante emitido importado desde ARCA (Mis Comprobantes)."""

    __tablename__ = "comprobantes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    fecha: Mapped[date] = mapped_column(Date, nullable=False)
    tipo_comprobante: Mapped[str] = mapped_column(String(50), nullable=False)
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

    archivo_origen: Mapped[str | None] = mapped_column(String(255))
    creado: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_comprobantes_fecha", "fecha"),
    )


class ConfiguracionDB(Base):
    """Configuracion global del sistema (una sola fila)."""

    __tablename__ = "configuracion"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    retencion_horas: Mapped[int] = mapped_column(Integer, default=24, nullable=False)
    actualizado: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class PercepcionIIBBDB(Base):
    """Percepción o retención de IIBB importada desde SIRCREB/ARBA."""

    __tablename__ = "percepciones_iibb"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    jurisdiccion: Mapped[int] = mapped_column(Integer, nullable=False)
    jurisdiccion_nombre: Mapped[str] = mapped_column(String(50), nullable=False)
    cuit_agente: Mapped[str] = mapped_column(String(13), nullable=False)
    fecha: Mapped[date] = mapped_column(Date, nullable=False)
    tipo: Mapped[str] = mapped_column(String(20), nullable=False)  # PERCEPCION / RETENCION
    monto_sujeto: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    alicuota: Mapped[float | None] = mapped_column(Numeric(6, 2))
    monto_retenido: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    regimen: Mapped[str | None] = mapped_column(String(10))
    tipo_comprobante: Mapped[str | None] = mapped_column(String(5))
    letra_comprobante: Mapped[str | None] = mapped_column(String(1))
    numero_comprobante: Mapped[str | None] = mapped_column(String(20))

    archivo_origen: Mapped[str | None] = mapped_column(String(255))
    creado: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_percepciones_iibb_fecha", "fecha"),
        Index("ix_percepciones_iibb_jurisdiccion", "jurisdiccion"),
    )
