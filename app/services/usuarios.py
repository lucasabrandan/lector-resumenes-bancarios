"""Servicio de gestión de usuarios."""

import hashlib

from sqlalchemy.orm import Session

from app.db.models import UsuarioDB, TODOS_LOS_PERMISOS


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def autenticar(username: str, password: str, db: Session) -> UsuarioDB | None:
    usuario = db.query(UsuarioDB).filter_by(username=username, activo=True).first()
    if usuario and usuario.password_hash == hash_password(password):
        return usuario
    return None


def obtener_por_username(username: str, db: Session) -> UsuarioDB | None:
    return db.query(UsuarioDB).filter_by(username=username).first()


def obtener_por_id(usuario_id: int, db: Session) -> UsuarioDB | None:
    return db.get(UsuarioDB, usuario_id)


def listar_usuarios(db: Session) -> list[UsuarioDB]:
    return db.query(UsuarioDB).order_by(UsuarioDB.username).all()


def crear_usuario(
    username: str,
    password: str,
    nombre: str,
    permisos: list[str],
    db: Session,
) -> UsuarioDB:
    usuario = UsuarioDB(
        username=username,
        password_hash=hash_password(password),
        nombre=nombre,
        permisos=",".join(permisos),
    )
    db.add(usuario)
    db.commit()
    db.refresh(usuario)
    return usuario


def actualizar_usuario(
    usuario_id: int,
    nombre: str,
    permisos: list[str],
    activo: bool,
    db: Session,
    nueva_password: str | None = None,
) -> UsuarioDB | None:
    usuario = db.get(UsuarioDB, usuario_id)
    if not usuario:
        return None
    usuario.nombre = nombre
    usuario.permisos = ",".join(permisos)
    usuario.activo = activo
    if nueva_password:
        usuario.password_hash = hash_password(nueva_password)
    db.commit()
    db.refresh(usuario)
    return usuario


def eliminar_usuario(usuario_id: int, db: Session) -> bool:
    usuario = db.get(UsuarioDB, usuario_id)
    if not usuario:
        return False
    db.delete(usuario)
    db.commit()
    return True


def crear_admin_si_no_existe(db: Session) -> None:
    """Crea el usuario admin por defecto si no hay ningun usuario."""
    if db.query(UsuarioDB).count() > 0:
        _migrar_permisos_nuevos(db)
        return
    crear_usuario(
        username="admin",
        password="admin123",
        nombre="Administrador",
        permisos=TODOS_LOS_PERMISOS,
        db=db,
    )


def _migrar_permisos_nuevos(db: Session) -> None:
    """Agrega permisos nuevos a admins existentes que no los tengan."""
    admins = db.query(UsuarioDB).all()
    for u in admins:
        if not u.tiene_permiso("usuarios"):
            continue
        permisos_actuales = u.lista_permisos()
        faltantes = [p for p in TODOS_LOS_PERMISOS if p not in permisos_actuales]
        if faltantes:
            u.permisos = ",".join(permisos_actuales + faltantes)
    db.commit()
