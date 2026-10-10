"""Alertas escalonados, ciente e matriz de responsáveis — pela API."""

from tests.conftest import local
from tests.test_records_api import entrar

MATRIZ = [
    {"linha": "Linha 3", "funcao": "Monitor", "turno1": "mon3@example.com", "turno2": "mon3.noite@example.com"},
    {"linha": "Linha 3", "funcao": "Lider", "turno1": "lider3@example.com", "turno2": ""},
    {"linha": "TODAS", "funcao": "Auditor", "turno1": "auditor@example.com", "turno2": ""},
    {"linha": "", "funcao": "Supervisor", "turno1": "sup@example.com", "turno2": "sup@example.com"},
]


def run(client, auth):
    r = client.post("/admin/alerts/run", headers=auth)
    assert r.status_code == 200, r.text
    return r.json()


def preparar(client, auth):
    r = client.put("/admin/responsibles", json=MATRIZ, headers=auth)
    assert r.status_code == 200, r.text
    return entrar(client).json()["id"]


def test_matriz_valida_e_supervisor_vira_todas(client, auth):
    preparar(client, auth)
    linhas = client.get("/admin/responsibles", headers=auth).json()
    sup = next(r for r in linhas if r["funcao"] == "Supervisor")
    assert sup["linha"] == "TODAS"
    r = client.put("/admin/responsibles", json=[{"linha": "1", "funcao": "Monitor", "turno1": "x@", "turno2": ""}], headers=auth)
    assert r.status_code == 422 and r.json()["code"] == "EMAIL_INVALIDO"
    r = client.put("/admin/responsibles", json=[{"linha": "1", "funcao": "Gerente", "turno1": "", "turno2": ""}], headers=auth)
    assert r.status_code == 422  # rejeitado já na validação do schema


def test_escalonamento_completo(client, auth, clock, outbox):
    preparar(client, auth)                      # entrada quarta 10:00, limite 60 min

    clock.set(local(2026, 10, 7, 11, 4))
    assert run(client, auth)["enviados"] == 0   # atrasada, mas ainda antes de +5

    clock.set(local(2026, 10, 7, 11, 5))
    s = run(client, auth)
    assert s["enviados"] == 1 and s["por_nivel"]["1"] == 1
    assert outbox.sent[-1]["to"] == ["mon3@example.com"]
    assert outbox.sent[-1]["subject"].startswith("[Nível 1/3] Notificação Automática")
    assert "Confirmar ciência" in outbox.sent[-1]["text"]

    clock.set(local(2026, 10, 7, 11, 10))
    assert run(client, auth)["enviados"] == 0   # não reenvia o nível 1

    clock.set(local(2026, 10, 7, 11, 15))
    run(client, auth)
    assert outbox.sent[-1]["to"] == ["lider3@example.com", "auditor@example.com"]

    clock.set(local(2026, 10, 7, 11, 30))
    run(client, auth)
    assert outbox.sent[-1]["to"] == ["sup@example.com"] and len(outbox.sent) == 3

    rec = client.get("/records/active").json()[0]
    assert rec["alertas_enviados"] == 3


def test_ciclo_atrasado_envia_niveis_pendentes_de_uma_vez(client, auth, clock, outbox):
    preparar(client, auth)
    clock.set(local(2026, 10, 7, 11, 40))
    s = run(client, auth)
    assert s["enviados"] == 3 and [m["subject"][:10] for m in outbox.sent] == ["[Nível 1/3", "[Nível 2/3", "[Nível 3/3"]


def test_turno_2_recebe_quando_o_alerta_cai_no_turno_2(client, auth, clock, outbox):
    client.put("/admin/responsibles", json=MATRIZ, headers=auth)
    clock.set(local(2026, 10, 7, 16, 50))
    entrar(client)
    clock.set(local(2026, 10, 7, 17, 55))
    run(client, auth)
    assert outbox.sent[0]["to"] == ["mon3.noite@example.com"]
    assert "Turno responsável: Turno 2" in outbox.sent[0]["text"]


def test_sem_destinatario_nao_marca_e_envia_depois(client, auth, clock, outbox):
    entrar(client)
    clock.set(local(2026, 10, 7, 11, 5))
    s = run(client, auth)
    assert s["enviados"] == 0 and s["sem_destinatario"] == ["PCBA-001 (nível 1)"]
    client.put("/admin/responsibles", json=MATRIZ, headers=auth)
    assert run(client, auth)["enviados"] == 1


def test_saida_encerra_escalonamento(client, auth, clock, outbox):
    rid = preparar(client, auth)
    clock.set(local(2026, 10, 7, 11, 5))
    run(client, auth)
    client.post(f"/records/{rid}/exit", json={"motivo": "Troca de turno"})
    clock.set(local(2026, 10, 7, 12, 0))
    assert run(client, auth)["enviados"] == 0 and len(outbox.sent) == 1


def test_pausa_nao_envia(client, auth, clock, outbox):
    client.put("/admin/responsibles", json=MATRIZ, headers=auth)
    clock.set(local(2026, 10, 7, 2, 0))          # entra 02:00, pausa começa 03:00
    entrar(client)
    clock.set(local(2026, 10, 7, 5, 0))          # dentro da pausa
    s = run(client, auth)
    assert s["enviados"] == 0 and s["pausados"] == 1


def test_aging_adiado_na_pausa_e_enviado_depois(client, auth, clock, outbox):
    client.put("/admin/responsibles", json=MATRIZ, headers=auth)
    clock.set(local(2026, 10, 6, 15, 0))         # terça 15:00, aging 12h vence 03:00 de quarta
    entrar(client, tipo="Aging", aging_horas=12)
    clock.set(local(2026, 10, 7, 4, 0))
    assert run(client, auth)["enviados"] == 0
    clock.set(local(2026, 10, 7, 7, 40))         # após a pausa: todos os níveis vencidos
    s = run(client, auth)
    assert s["enviados"] == 3 and "[Aging 12h]" in outbox.sent[0]["subject"]


def test_ciente_registra_quem_assumiu_e_aparece_no_proximo_email(client, auth, clock, outbox):
    rid = preparar(client, auth)
    clock.set(local(2026, 10, 7, 11, 5))
    run(client, auth)

    clock.set(local(2026, 10, 7, 11, 8))
    r = client.post(f"/records/{rid}/ack", json={"matricula": "1002"})
    assert r.status_code == 200 and r.json()["ja_registrado"] is False and r.json()["ciente_nome"] == "Carlos Lima"
    r = client.post(f"/records/{rid}/ack", json={"matricula": "12107"})
    assert r.json()["ja_registrado"] is True and r.json()["ciente_nome"] == "Carlos Lima"

    clock.set(local(2026, 10, 7, 11, 15))
    run(client, auth)                            # ciente não interrompe a escalada
    assert "Ciente registrado por Carlos Lima às 11:08" in outbox.sent[-1]["text"]
    assert "Confirmar ciência" not in outbox.sent[-1]["html"]


def test_ciente_erros(client, auth):
    rid = preparar(client, auth)
    assert client.post(f"/records/{rid}/ack", json={"matricula": "999"}).status_code == 404
    assert client.post("/records/nao-existe/ack", json={"matricula": "1002"}).status_code == 404
    client.post(f"/records/{rid}/exit", json={})
    r = client.post(f"/records/{rid}/ack", json={"matricula": "1002"})
    assert r.status_code == 409 and r.json()["code"] == "SAIDA_JA_REGISTRADA"


def test_admin_exclui_registro(client, auth):
    rid = preparar(client, auth)
    assert client.delete(f"/admin/records/{rid}", headers=auth).status_code == 204
    assert client.get("/records/active").json() == []
    assert client.delete(f"/admin/records/{rid}", headers=auth).status_code == 404
