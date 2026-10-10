"""Login JWT, rotas protegidas e regras de senha."""

from datetime import UTC, datetime, timedelta

import pytest

from app.exceptions import Unprocessable
from app.services.auth import check_strength, create_token
from tests.conftest import ADMIN_EMAIL, ADMIN_PASSWORD


def test_login_ok_e_me(client, auth):
    r = client.get("/auth/me", headers=auth)
    assert r.status_code == 200
    assert r.json()["email"] == ADMIN_EMAIL and "senha_hash" not in r.json()


def test_login_email_case_insensitive(client):
    r = client.post("/auth/login", data={"username": ADMIN_EMAIL.upper(), "password": ADMIN_PASSWORD})
    assert r.status_code == 200


@pytest.mark.parametrize("user,pwd", [(ADMIN_EMAIL, "errada-123"), ("ninguem@example.com", ADMIN_PASSWORD)])
def test_login_invalido_mensagem_unica(client, user, pwd):
    r = client.post("/auth/login", data={"username": user, "password": pwd})
    assert r.status_code == 401
    assert r.json()["code"] == "CREDENCIAIS_INVALIDAS"
    assert r.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize("method,url", [
    ("put", "/admin/threshold"), ("put", "/admin/reasons"), ("get", "/admin/responsibles"),
    ("post", "/admin/alerts/run"), ("delete", "/admin/records/x"),
])
def test_rotas_admin_exigem_token(client, method, url):
    assert getattr(client, method)(url).status_code == 401


def test_token_invalido(client):
    r = client.get("/auth/me", headers={"Authorization": "Bearer abc.def.ghi"})
    assert r.status_code == 401 and r.json()["code"] == "TOKEN_INVALIDO"


def test_token_expirado(client):
    class A:
        email = ADMIN_EMAIL
    velho = create_token(A(), now=datetime.now(UTC) - timedelta(days=2))
    r = client.get("/auth/me", headers={"Authorization": f"Bearer {velho}"})
    assert r.status_code == 401 and r.json()["code"] == "SESSAO_EXPIRADA"


@pytest.mark.parametrize("senha", ["1234", "Admin1234", "aaaaaaaaaa", "12345678"])
def test_senhas_fracas_recusadas(senha):
    with pytest.raises(Unprocessable):
        check_strength(senha)


def test_admin_altera_limite_e_motivos(client, auth):
    assert client.put("/admin/threshold", json={"threshold_min": 90}, headers=auth).status_code == 200
    assert client.get("/settings").json()["threshold_min"] == 90
    r = client.put("/admin/reasons", json={"reasons": ["Falta de operador", " falta de operador ", ""]}, headers=auth)
    assert r.json() == ["Falta de operador", "Pausa programada (sem expediente)"]
