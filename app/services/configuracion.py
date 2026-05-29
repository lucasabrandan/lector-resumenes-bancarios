"""
Servicio de configuración global y purga automática de datos.

El admin define cuántas horas se retienen los datos financieros.
Los datos más viejos se eliminan automáticamente.
"""

from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.db.models import ConfiguracionDB, MovimientoDB, ComprobanteDB, PercepcionIIBBDB


# Opciones que se muestran en la UI
OPCIONES_RETENCION = [
    (0, "No borrar automaticamente"),
    (1, "1 hora"),
    (6, "6 horas"),
    (12, "12 horas"),
    (24, "24 horas (1 dia)"),
    (72, "3 dias"),
    (168, "7 dias"),
    (720, "30 dias"),
]


def obtener_config(db: Session) -> ConfiguracionDB:
    """Devuelve la configuración, creándola si no existe."""
    config = db.query(ConfiguracionDB).first()
    if not config:
        config = ConfiguracionDB(retencion_horas=0)
        db.add(config)
        db.commit()
        db.refresh(config)
    return config


def actualizar_retencion(horas: int, db: Session) -> ConfiguracionDB:
    """Actualiza el tiempo de retención."""
    config = obtener_config(db)
    config.retencion_horas = horas
    config.actualizado = datetime.utcnow()
    db.commit()
    db.refresh(config)
    return config


def purgar_datos_expirados(db: Session) -> dict[str, int]:
    """Elimina datos cuyo timestamp 'creado' supere el tiempo de retención.

    Returns dict con cantidad eliminada por tabla.
    """
    config = obtener_config(db)
    if config.retencion_horas == 0:
        return {"movimientos": 0, "comprobantes": 0, "percepciones_iibb": 0}

    limite = datetime.utcnow() - timedelta(hours=config.retencion_horas)

    resultado = {}
    resultado["movimientos"] = (
        db.query(MovimientoDB)
        .filter(MovimientoDB.creado < limite)
        .delete(synchronize_session=False)
    )
    resultado["comprobantes"] = (
        db.query(ComprobanteDB)
        .filter(ComprobanteDB.creado < limite)
        .delete(synchronize_session=False)
    )
    resultado["percepciones_iibb"] = (
        db.query(PercepcionIIBBDB)
        .filter(PercepcionIIBBDB.creado < limite)
        .delete(synchronize_session=False)
    )
    db.commit()
    return resultado


def label_retencion(horas: int) -> str:
    """Devuelve la etiqueta legible para un valor de horas."""
    for valor, label in OPCIONES_RETENCION:
        if valor == horas:
            return label
    return f"{horas} horas"
