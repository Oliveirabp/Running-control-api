"""KPI, linha de base, qualidade dos dados e plano de ação — pela API."""

from datetime import timedelta

from tests.conftest import local
from tests.test_records_api import entrar


def ciclo(client, clock, entrada, minutos, motivo="Troca de turno", **extra):
    """Entrada em `entrada` e saída `minutos` depois (dias úteis, sem pausa no meio)."""
    clock.set(entrada)
    rid = entrar(client, **extra).json()["id"]
    clock.set(entrada + timedelta(minutes=minutos))
    r = client.post(f"/records/{rid}/exit", json={"motivo": motivo})
    assert r.status_code == 200, r.text
    return rid


def test_kpi_resumo_recortes_e_periodo_anterior(client, clock):
    # período anterior (06/10): 2 peças de 40 min · período atual (07/10): 30, 50, 90 min
    ciclo(client, clock, local(2026, 10, 6, 9), 40, pcba="P0")
    ciclo(client, clock, local(2026, 10, 6, 10), 40, pcba="P1")
    ciclo(client, clock, local(2026, 10, 7, 8), 30, pcba="A")
    ciclo(client, clock, local(2026, 10, 7, 9), 50, pcba="B")
    ciclo(client, clock, local(2026, 10, 7, 18), 90, pcba="C")  # Turno 2, em atraso
    r = client.get("/kpi", params={"inicio": "2026-10-07", "fim": "2026-10-07"})
    assert r.status_code == 200, r.text
    k = r.json()
    assert k["resumo"]["n"] == 3 and k["resumo"]["media"] == 170 / 3
    assert k["resumo"]["acima"] == 1 and k["resumo"]["alertas"] == 1
    assert k["anterior"]["n"] == 2 and k["anterior"]["media"] == 40
    assert {t["chave"]: t["n"] for t in k["por_turno"]} == {"Turno 1": 2, "Turno 2": 1}
    assert k["pareto"]["total"] == 1 and k["pareto"]["itens"][0]["motivo"] == "Troca de turno"
    assert k["maiores"][0]["pcba"] == "C"
    assert any(i["tipo"] == "tendencia" and "subiu" in i["texto"] for i in k["leitura"])
    assert k["linha_turno"][0]["linha"] == "LINHA 3"


def test_kpi_filtros_e_validacao(client, clock):
    ciclo(client, clock, local(2026, 10, 7, 8), 30)
    k = client.get("/kpi", params={"inicio": "2026-10-07", "fim": "2026-10-07", "linha": "Linha 1"}).json()
    assert k["resumo"]["n"] == 0 and k["filtros"]["linha"] == "LINHA 1"
    assert client.get("/kpi", params={"inicio": "2026-10-08", "fim": "2026-10-01"}).json()["code"] == "PERIODO_INVALIDO"
    assert client.get("/kpi", params={"turno": "Turno 9"}).status_code == 422


def test_aging_fica_fora_das_medias(client, clock):
    ciclo(client, clock, local(2026, 10, 7, 8), 30)
    clock.set(local(2026, 10, 7, 8))
    entrar(client, pcba="AG", tipo="Aging", aging_horas=12)
    clock.set(local(2026, 10, 7, 9))
    k = client.get("/kpi", params={"inicio": "2026-10-07", "fim": "2026-10-07"}).json()
    assert k["resumo"]["n"] == 1 and k["agora"]["aging"] == 1
    assert any(i["tipo"] == "aging" for i in k["leitura"])


def test_linha_de_base_gera_ganho(client, clock, auth):
    ciclo(client, clock, local(2026, 10, 7, 8), 30)
    ciclo(client, clock, local(2026, 10, 7, 9), 50)
    assert client.put("/admin/baseline", json={"minutos": 95, "fonte": "x"}).status_code == 401
    r = client.put("/admin/baseline", json={"minutos": 95, "fonte": "Cronoanálise, 40 amostras"}, headers=auth)
    assert r.status_code == 200
    k = client.get("/kpi", params={"inicio": "2026-10-07", "fim": "2026-10-07"}).json()
    assert k["ganho"]["minutos"] == 2 * 95 - 80 and k["linha_de_base"]["fonte"].startswith("Cronoanálise")
    assert k["leitura"][0]["tipo"] == "ganho" and k["leitura"][0]["nivel"] == "good"
    assert client.put("/admin/baseline", json={"minutos": 95, "fonte": ""}, headers=auth).status_code == 422


def test_saida_esquecida_qualidade_e_exclusao_das_medias(client, clock, auth):
    clock.set(local(2026, 10, 5, 8))  # segunda
    rid = entrar(client, pcba="ESQ").json()["id"]
    clock.set(local(2026, 10, 7, 12))  # > 24 h efetivas depois
    q = client.get("/quality").json()
    assert [a["pcba"] for a in q["abertos"]] == ["ESQ"]
    assert client.post(f"/admin/records/{rid}/close-forgotten").status_code == 401
    r = client.post(f"/admin/records/{rid}/close-forgotten", headers=auth)
    assert r.status_code == 200
    assert r.json()["motivo"] == "Esqueceu de remover" and r.json()["ajuste"].startswith("Saída esquecida — encerrado por Admin Teste")
    assert client.get("/quality").json()["abertos"] == []
    k = client.get("/kpi", params={"inicio": "2026-10-05", "fim": "2026-10-07"}).json()
    assert k["resumo"]["n"] == 0 and len(k["excluidos"]) == 1
    assert client.post(f"/admin/records/{rid}/close-forgotten", headers=auth).status_code == 409


ACAO = {"linha": "Linha 2", "origem": "KPI · motivo", "problema": "Troca de turno sem passagem",
        "acao": "Checklist de passagem de turno na estação", "responsavel": "Líder T2", "prazo": "2026-10-20"}


def test_plano_de_acao_ciclo_pdca(client, clock, auth):
    assert client.post("/actions", json=ACAO).status_code == 401
    r = client.post("/actions", json=ACAO, headers=auth)
    assert r.status_code == 201, r.text
    a = r.json()
    assert a["linha"] == "LINHA 2" and a["etapa"] == "Planejar" and a["criado_por"] == "Admin Teste" and not a["atrasada"]

    # concluir exige resultado
    r = client.put(f"/actions/{a['id']}", json={**ACAO, "etapa": "Concluída"}, headers=auth)
    assert r.status_code == 422 and r.json()["code"] == "ACAO_INVALIDA"
    clock.set(local(2026, 10, 15, 10))
    r = client.put(f"/actions/{a['id']}", json={**ACAO, "etapa": "Concluída", "resultado": "Atrasos caíram de 12 para 3/sem"}, headers=auth)
    assert r.json()["concluido_em"] is not None

    # reabrir limpa a conclusão; prazo vencido marca atrasada
    clock.set(local(2026, 10, 25, 10))
    r = client.put(f"/actions/{a['id']}", json={**ACAO, "etapa": "Verificar"}, headers=auth)
    assert r.json()["concluido_em"] is None and r.json()["atrasada"] is True
    assert [x["id"] for x in client.get("/actions").json()] == [a["id"]]  # leitura aberta

    assert client.delete(f"/actions/{a['id']}").status_code == 401
    assert client.delete(f"/actions/{a['id']}", headers=auth).status_code == 204
    assert client.put(f"/actions/{a['id']}", json=ACAO, headers=auth).status_code == 404


def test_acao_campos_obrigatorios(client, auth):
    r = client.post("/actions", json={**ACAO, "problema": " ", "acao": "", "responsavel": ""}, headers=auth)
    assert r.status_code == 422 and len(r.json()["errors"]) == 3
