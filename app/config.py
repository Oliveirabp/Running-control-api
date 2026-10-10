"""Configuração lida de variáveis de ambiente (ver .env.example)."""

import os
import secrets
import warnings
from dataclasses import dataclass, field
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

load_dotenv()  # lê o .env, se existir; variáveis já definidas no ambiente têm prioridade


def _jwt_secret() -> str:
    v = os.getenv("JWT_SECRET")
    if v:
        if len(v) < 32:
            warnings.warn("JWT_SECRET curto: use pelo menos 32 caracteres.", stacklevel=2)
        return v
    warnings.warn("JWT_SECRET não definido: usando chave temporária (os logins expiram a cada reinício).", stacklevel=2)
    return secrets.token_urlsafe(48)


def _bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "sim"}


@dataclass(frozen=True)
class Settings:
    database_url: str = field(default_factory=lambda: os.getenv("DATABASE_URL", "sqlite:///./running_control.db"))
    timezone: ZoneInfo = field(default_factory=lambda: ZoneInfo(os.getenv("APP_TIMEZONE", "America/Sao_Paulo")))
    jwt_secret: str = field(default_factory=_jwt_secret)
    jwt_expire_hours: int = field(default_factory=lambda: int(os.getenv("JWT_EXPIRE_HOURS", "6")))
    # Primeiro administrador (criado só se não houver nenhum) — a senha nunca fica no código.
    admin_email: str = field(default_factory=lambda: os.getenv("ADMIN_EMAIL", ""))
    admin_password: str = field(default_factory=lambda: os.getenv("ADMIN_PASSWORD", ""))
    # Alertas
    enable_scheduler: bool = field(default_factory=lambda: _bool("ENABLE_SCHEDULER", True))
    check_every_seconds: int = field(default_factory=lambda: int(os.getenv("CHECK_EVERY_SECONDS", "60")))
    app_base_url: str = field(default_factory=lambda: os.getenv("APP_BASE_URL", "http://localhost:8000"))
    smtp_host: str = field(default_factory=lambda: os.getenv("SMTP_HOST", ""))
    smtp_port: int = field(default_factory=lambda: int(os.getenv("SMTP_PORT", "587")))
    smtp_user: str = field(default_factory=lambda: os.getenv("SMTP_USER", ""))
    smtp_password: str = field(default_factory=lambda: os.getenv("SMTP_PASSWORD", ""))
    smtp_from: str = field(default_factory=lambda: os.getenv("SMTP_FROM", "running-control@localhost"))
    smtp_starttls: bool = field(default_factory=lambda: _bool("SMTP_STARTTLS", True))
    seed_lines: tuple[str, ...] = field(
        default_factory=lambda: tuple(
            s.strip() for s in os.getenv("SEED_LINES", "Linha 1,Linha 2,Linha 3").split(",") if s.strip()
        )
    )


settings = Settings()
