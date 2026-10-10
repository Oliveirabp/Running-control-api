"""Senhas com bcrypt e sessões com JWT."""

from datetime import UTC, datetime, timedelta

import bcrypt
import jwt
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.exceptions import DomainError, Unprocessable
from app.models import Admin

ALGORITHM = "HS256"
MIN_PASSWORD = 8
WEAK = {"12345678", "123456789", "password", "senha123", "senha1234", "admin123", "admin1234", "qwerty123", "abc12345"}


class Unauthorized(DomainError):
    status_code = 401


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except ValueError:
        return False


def check_strength(plain: str) -> None:
    if len(plain) < MIN_PASSWORD:
        raise Unprocessable("SENHA_FRACA", f"A senha precisa ter pelo menos {MIN_PASSWORD} caracteres.")
    if plain.lower() in WEAK or len(set(plain)) <= 2:
        raise Unprocessable("SENHA_FRACA", "Senha fraca demais. Escolha outra.")


def upsert_admin(db: Session, email: str, password: str, nome: str = "Administrador", cargo: str = "") -> Admin:
    email = email.strip().lower()
    check_strength(password)
    admin = db.scalars(select(Admin).where(Admin.email == email)).first()
    if admin is None:
        admin = Admin(email=email, nome=nome, cargo=cargo, senha_hash=hash_password(password))
        db.add(admin)
    else:
        admin.senha_hash = hash_password(password)
        admin.ativo = True
    db.commit()
    return admin


def bootstrap_admin(db: Session) -> None:
    """Cria o primeiro administrador a partir de ADMIN_EMAIL/ADMIN_PASSWORD, se ainda não houver nenhum."""
    if db.scalar(select(func.count()).select_from(Admin)):
        return
    if settings.admin_email and settings.admin_password:
        upsert_admin(db, settings.admin_email, settings.admin_password)


def authenticate(db: Session, email: str, password: str) -> Admin:
    admin = db.scalars(select(Admin).where(Admin.email == email.strip().lower(), Admin.ativo.is_(True))).first()
    # Mensagem única para e-mail ou senha errados: não revela quais e-mails existem.
    if admin is None or not verify_password(password, admin.senha_hash):
        raise Unauthorized("CREDENCIAIS_INVALIDAS", "E-mail ou senha inválidos.")
    return admin


def create_token(admin: Admin, now: datetime | None = None) -> str:
    now = now or datetime.now(UTC)
    payload = {"sub": admin.email, "iat": now, "exp": now + timedelta(hours=settings.jwt_expire_hours)}
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)


def admin_from_token(db: Session, token: str) -> Admin:
    try:
        data = jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError as e:
        raise Unauthorized("SESSAO_EXPIRADA", "Sessão expirada. Faça login novamente.") from e
    except jwt.InvalidTokenError as e:
        raise Unauthorized("TOKEN_INVALIDO", "Sessão inválida. Faça login novamente.") from e
    admin = db.scalars(select(Admin).where(Admin.email == data.get("sub"), Admin.ativo.is_(True))).first()
    if admin is None:
        raise Unauthorized("TOKEN_INVALIDO", "Administrador não encontrado ou inativo.")
    return admin
