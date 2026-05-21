"""Servicio de gestión de clientes del estudio contable."""

from sqlalchemy.orm import Session

from app.db.models import ClienteDB, UsuarioDB, UsuarioClienteDB


def listar_clientes(db: Session, solo_activos: bool = False) -> list[ClienteDB]:
    query = db.query(ClienteDB)
    if solo_activos:
        query = query.filter(ClienteDB.activo == True)
    return query.order_by(ClienteDB.nombre).all()


def listar_clientes_de_usuario(usuario: UsuarioDB, db: Session) -> list[ClienteDB]:
    """Devuelve los clientes asignados al usuario. Si es admin, devuelve todos."""
    if usuario.es_admin():
        return listar_clientes(db, solo_activos=True)
    return (
        db.query(ClienteDB)
        .join(UsuarioClienteDB)
        .filter(UsuarioClienteDB.usuario_id == usuario.id, ClienteDB.activo == True)
        .order_by(ClienteDB.nombre)
        .all()
    )


def obtener_por_id(cliente_id: int, db: Session) -> ClienteDB | None:
    return db.get(ClienteDB, cliente_id)


def crear_cliente(nombre: str, cuit: str | None, categoria: str, db: Session) -> ClienteDB:
    cliente = ClienteDB(nombre=nombre, cuit=cuit or None, categoria=categoria)
    db.add(cliente)
    db.commit()
    db.refresh(cliente)
    return cliente


def actualizar_cliente(
    cliente_id: int,
    nombre: str,
    cuit: str | None,
    categoria: str,
    activo: bool,
    db: Session,
    categoria_monotributo: str | None = None,
    actividad_monotributo: str | None = None,
) -> ClienteDB | None:
    cliente = db.get(ClienteDB, cliente_id)
    if not cliente:
        return None
    cliente.nombre = nombre
    cliente.cuit = cuit or None
    cliente.categoria = categoria
    cliente.activo = activo
    if categoria == "Monotributo":
        cliente.categoria_monotributo = categoria_monotributo
        cliente.actividad_monotributo = actividad_monotributo or "servicios"
    else:
        cliente.categoria_monotributo = None
    db.commit()
    db.refresh(cliente)
    return cliente


def eliminar_cliente(cliente_id: int, db: Session) -> bool:
    cliente = db.get(ClienteDB, cliente_id)
    if not cliente:
        return False
    db.delete(cliente)
    db.commit()
    return True


def asignar_usuarios(cliente_id: int, usuario_ids: list[int], db: Session) -> None:
    """Reemplaza la lista de usuarios asignados a un cliente."""
    db.query(UsuarioClienteDB).filter(UsuarioClienteDB.cliente_id == cliente_id).delete()
    for uid in usuario_ids:
        db.add(UsuarioClienteDB(usuario_id=uid, cliente_id=cliente_id))
    db.commit()


def ids_clientes_de_usuario(usuario: UsuarioDB, db: Session) -> list[int] | None:
    """Devuelve lista de IDs de clientes del usuario, o None si es admin (= ve todo)."""
    if usuario.es_admin():
        return None
    rows = (
        db.query(UsuarioClienteDB.cliente_id)
        .filter(UsuarioClienteDB.usuario_id == usuario.id)
        .all()
    )
    return [r[0] for r in rows]


def ids_clientes_no_monotributo(db: Session, cliente_ids: list[int] | None = None) -> list[int] | None:
    """Filtra cliente_ids excluyendo monotributistas. Para reportes Ley 25.413."""
    query = db.query(ClienteDB.id).filter(ClienteDB.categoria != "Monotributo")
    if cliente_ids is not None:
        query = query.filter(ClienteDB.id.in_(cliente_ids))
        return [r[0] for r in query.all()]
    # Admin (None) — devolver solo los no-monotributistas
    return [r[0] for r in query.all()]
