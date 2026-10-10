"""A interface web é servida pela própria API."""

import pytest


@pytest.mark.parametrize("path,marker", [
    ("/", "Registrar entrada"), ("/tv", "Fila de atenção"), ("/config", "Acesso do administrador"),
    ("/indicadores", "Leitura executiva"), ("/plano", "Qualidade dos dados"),
])
def test_paginas(client, path, marker):
    r = client.get(path)
    assert r.status_code == 200 and "text/html" in r.headers["content-type"]
    assert marker in r.text


@pytest.mark.parametrize("asset", ["api.js", "painel.js", "tv.js", "config.js", "kpi.js", "plano.js", "actions-ui.js",
                                   "style.css", "tv.css", "config.css", "analytics.css", "vendor/chart.umd.min.js"])
def test_assets(client, asset):
    assert client.get(f"/assets/{asset}").status_code == 200


def test_paginas_fora_da_documentacao(client):
    paths = client.get("/openapi.json").json()["paths"]
    assert "/" not in paths and "/tv" not in paths


def test_settings_traz_linha_de_base(client, auth):
    assert client.get("/settings").json()["baseline_min"] is None
    client.put("/admin/baseline", json={"minutos": 80, "fonte": "medição de teste"}, headers=auth)
    s = client.get("/settings").json()
    assert (s["baseline_min"], s["baseline_fonte"]) == (80, "medição de teste")


def test_registro_traz_inicio_do_amarelo(client):
    from tests.test_records_api import entrar
    assert entrar(client).json()["warn_min"] == 45
