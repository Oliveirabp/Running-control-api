"""Fluxos de ponta a ponta pela API."""

from tests.conftest import local

ENTRADA = {
    "matricula": "012107", "pcba": "PCBA-001",
    "linha_producao": "Linha 3", "lado": "Lado A", "posicao": "Linha L1", "localizacao": "G3",
}


def entrar(client, **extra):
    return client.post("/records/entries", json={**ENTRADA, **extra})


def test_health(client):
    assert client.get("/health").json()["status"] == "ok"


def test_settings_padrao(client):
    s = client.get("/settings").json()
    assert s["threshold_min"] == 60
    assert s["aging_options_h"] == [12, 24]
    assert s["lines"] == ["LINHA 1", "LINHA 2", "LINHA 3"]
    assert "Pausa programada (sem expediente)" in s["reasons"]


def test_entrada_padroniza_e_resolve_nome(client):
    r = entrar(client)
    assert r.status_code == 201
    body = r.json()
    assert body["nome"] == "Ana Souza" and body["matricula"] == "12107"
    assert (body["linha_producao"], body["posicao"]) == ("LINHA 3", "Linha 1")
    assert body["status"] == "ok" and body["limite_min"] == 60


def test_matricula_desconhecida(client):
    r = entrar(client, matricula="999")
    assert r.status_code == 404 and r.json()["code"] == "MATRICULA_NAO_ENCONTRADA"


def test_posicao_invalida_retorna_todos_os_erros(client):
    r = entrar(client, lado="Lado C", localizacao="G9")
    assert r.status_code == 422
    assert r.json()["code"] == "POSICAO_INVALIDA" and len(r.json()["errors"]) == 2


def test_pcba_duplicada_na_estacao(client):
    entrar(client)
    r = entrar(client, pcba="pcba-001")
    assert r.status_code == 409 and r.json()["code"] == "PCBA_JA_NA_ESTACAO"


def test_aging_exige_duracao_cadastrada(client):
    r = entrar(client, tipo="Aging", aging_horas=48)
    assert r.status_code == 422 and r.json()["code"] == "AGING_DURACAO_INVALIDA"
    ok = entrar(client, tipo="Aging", aging_horas=24)
    assert ok.status_code == 201 and ok.json()["limite_min"] == 1440


def test_saida_no_prazo_dispensa_motivo(client, clock):
    rid = entrar(client).json()["id"]
    clock.set(local(2026, 10, 7, 10, 40))
    r = client.post(f"/records/{rid}/exit", json={"motivo": "Troca de turno"})
    assert r.status_code == 200
    assert r.json()["motivo"] == "" and r.json()["tempo_min"] == 40


def test_saida_em_atraso_exige_motivo_valido(client, clock):
    rid = entrar(client).json()["id"]
    clock.set(local(2026, 10, 7, 11, 30))
    r = client.post(f"/records/{rid}/exit", json={})
    assert r.status_code == 422 and r.json()["code"] == "MOTIVO_OBRIGATORIO"
    r = client.post(f"/records/{rid}/exit", json={"motivo": "Não sei"})
    assert r.json()["code"] == "MOTIVO_INVALIDO"
    r = client.post(f"/records/{rid}/exit", json={"motivo": "Troca de turno"})
    assert r.status_code == 200 and r.json()["motivo"] == "Troca de turno" and r.json()["em_atraso"]


def test_saida_pela_leitura_do_pcba(client, clock):
    entrar(client)
    clock.set(local(2026, 10, 7, 10, 20))
    r = client.post("/records/exit-by-pcba", json={"pcba": " pcba-001 "})
    assert r.status_code == 200 and r.json()["saida_em"]
    r = client.post("/records/exit-by-pcba", json={"pcba": "PCBA-001"})
    assert r.status_code == 404 and r.json()["code"] == "PCBA_FORA_DA_ESTACAO"


def test_pausa_programada_e_registrada_na_saida(client, clock):
    clock.set(local(2026, 10, 7, 2, 30))  # quarta, 02:30
    rid = entrar(client).json()["id"]
    clock.set(local(2026, 10, 7, 3, 35))
    ativo = client.get("/records/active").json()[0]
    assert ativo["status"] == "paused" and round(ativo["tempo_min"]) == 30
    clock.set(local(2026, 10, 7, 8, 5))  # 65 min efetivos
    r = client.post(f"/records/{rid}/exit", json={"motivo": "Pausa programada (sem expediente)"})
    assert r.status_code == 200 and r.json()["pausa_programada"] and round(r.json()["tempo_min"]) == 65


def test_historico_ordenado_pela_saida(client, clock):
    a = entrar(client, pcba="A").json()["id"]
    b = entrar(client, pcba="B").json()["id"]
    clock.set(local(2026, 10, 7, 10, 10))
    client.post(f"/records/{a}/exit", json={})
    clock.set(local(2026, 10, 7, 10, 20))
    client.post(f"/records/{b}/exit", json={})
    assert [r["pcba"] for r in client.get("/records/history").json()] == ["B", "A"]
    assert client.get("/records/active").json() == []


def test_colaboradores(client, auth):
    novo = {"matricula": "0555", "nome": "Beatriz Rocha"}
    assert client.post("/employees", json=novo).status_code == 401  # cadastro exige administrador
    assert client.post("/employees", json=novo, headers=auth).status_code == 201
    assert client.post("/employees", json={"matricula": "555", "nome": "Outra"}, headers=auth).json()["code"] == "MATRICULA_DUPLICADA"
    assert client.delete("/employees/555").status_code == 401
    assert client.delete("/employees/555", headers=auth).status_code == 204
    assert [e["matricula"] for e in client.get("/employees").json()] == ["12107", "1002"]  # ordenado por nome


def test_historico_sobrevive_a_saida_do_colaborador(client, clock, auth):
    """O registro guarda um retrato de quem fez a entrada (sem chave estrangeira)."""
    rid = entrar(client).json()["id"]
    clock.set(local(2026, 10, 7, 10, 20))
    client.post(f"/records/{rid}/exit", json={})
    assert client.delete("/employees/12107", headers=auth).status_code == 204
    hist = client.get("/records/history").json()
    assert hist[0]["nome"] == "Ana Souza" and hist[0]["matricula"] == "12107"
