"""Aplica as migrações do banco (equivale a `alembic upgrade head`)."""

from pathlib import Path

from alembic import command
from alembic.config import Config

from app.config import settings

ROOT = Path(__file__).resolve().parent.parent


def alembic_config(url: str | None = None) -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "migrations"))
    cfg.set_main_option("sqlalchemy.url", (url or settings.database_url).replace("%", "%%"))
    return cfg


def upgrade(url: str | None = None) -> None:
    command.upgrade(alembic_config(url), "head")


if __name__ == "__main__":
    upgrade()
    print("Banco atualizado.")
