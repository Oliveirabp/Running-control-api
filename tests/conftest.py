import os
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_sender
from app.clock import get_now
from app.db import Base, get_db
from app.main import create_app
from app.models import Employee
from app.services import config_store
from app.services.auth import upsert_admin
from app.services.mailer import MemorySender

SP = ZoneInfo("America/Sao_Paulo")


def local(y, m, d, hh, mm=0):
    """Instante no horário de São Paulo (2026-10-07 é uma quarta-feira)."""
    return datetime(y, m, d, hh, mm, tzinfo=SP)


class Clock:
    def __init__(self, start):
        self.now = start

    def set(self, dt):
        self.now = dt

    def __call__(self):
        return self.now


@pytest.fixture
def clock():
    return Clock(local(2026, 10, 7, 10, 0))


ADMIN_EMAIL = "admin@example.com"
ADMIN_PASSWORD = "Troca-Esta-Senha-9"


@pytest.fixture
def outbox():
    return MemorySender()


TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL", "")  # ex.: postgresql+psycopg://rc:rc@localhost/rc_test


def make_test_engine():
    """SQLite em memória por padrão; com TEST_DATABASE_URL, roda tudo contra o PostgreSQL."""
    if TEST_DATABASE_URL:
        engine = create_engine(TEST_DATABASE_URL)
        Base.metadata.drop_all(engine)
        return engine
    return create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)


@pytest.fixture
def client(clock, outbox):
    engine = make_test_engine()
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with Session() as db:
        config_store.seed(db)
        db.add_all([Employee(matricula="12107", nome="Ana Souza"), Employee(matricula="1002", nome="Carlos Lima")])
        db.commit()
        upsert_admin(db, ADMIN_EMAIL, ADMIN_PASSWORD, nome="Admin Teste")

    def _db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app = create_app(init_db=False)
    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_now] = clock
    app.dependency_overrides[get_sender] = lambda: outbox
    with TestClient(app) as c:
        yield c
    engine.dispose()


@pytest.fixture
def auth(client):
    r = client.post("/auth/login", data={"username": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}
