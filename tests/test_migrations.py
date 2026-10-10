"""As migrações criam exatamente o esquema dos modelos — e voltam atrás sem erro."""

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text

from app import models  # noqa: F401
from app.db import Base
from app.migrate import alembic_config
from tests.conftest import TEST_DATABASE_URL


def test_migracoes_em_dia_com_os_modelos(tmp_path):
    url = TEST_DATABASE_URL or f"sqlite:///{tmp_path / 'mig.db'}"
    engine = create_engine(url)
    with engine.begin() as conn:  # parte de um banco vazio
        Base.metadata.drop_all(conn)
        conn.execute(text("DROP TABLE IF EXISTS alembic_version"))
    cfg = alembic_config(url)

    command.upgrade(cfg, "head")
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn, opts={"compare_type": True}), Base.metadata)
    assert diff == [], f"Modelos mudaram sem migração: {diff}"

    command.downgrade(cfg, "base")
    assert set(inspect(engine).get_table_names()) <= {"alembic_version"}
    engine.dispose()
