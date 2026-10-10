"""Plano de ação (PDCA): quem faz o quê, até quando, e o que resultou."""

from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings as env
from app.domain.position import normalize_line
from app.exceptions import NotFound, Unprocessable
from app.models import ETAPAS_PDCA, Action, Admin

CONCLUIDA = "Concluída"


def list_actions(db: Session) -> list[Action]:
    return list(db.scalars(select(Action).order_by(Action.prazo, Action.criado_em)))


def is_late(a: Action, now: datetime) -> bool:
    return a.etapa != CONCLUIDA and a.prazo < now.astimezone(env.timezone).date()


def _validate(data: dict) -> dict:
    erros = []
    clean = {k: str(data.get(k) or "").strip() for k in ("linha", "origem", "problema", "acao", "responsavel", "resultado")}
    if not clean["problema"]:
        erros.append("Descreva o problema.")
    if not clean["acao"]:
        erros.append("Descreva a ação.")
    if not clean["responsavel"]:
        erros.append("Informe o responsável.")
    prazo = data.get("prazo")
    if not isinstance(prazo, date):
        erros.append("Informe o prazo.")
    etapa = data.get("etapa") or "Planejar"
    if etapa not in ETAPAS_PDCA:
        erros.append(f"Etapa inválida. Use: {', '.join(ETAPAS_PDCA)}.")
    if etapa == CONCLUIDA and not clean["resultado"]:
        erros.append('Para concluir, registre o resultado obtido (o "Verificar" do PDCA).')
    if erros:
        raise Unprocessable("ACAO_INVALIDA", "Revise a ação.", erros)
    clean["linha"] = normalize_line(clean["linha"]) if clean["linha"] else ""
    return {**clean, "prazo": prazo, "etapa": etapa}


def save(db: Session, now: datetime, admin: Admin, data: dict, action_id: str | None = None) -> Action:
    v = _validate(data)
    if action_id:
        a = db.get(Action, action_id)
        if a is None:
            raise NotFound("ACAO_NAO_ENCONTRADA", "Ação não encontrada.")
        era_concluida = a.etapa == CONCLUIDA
    else:
        a = Action(criado_em=now, criado_por=admin.nome)
        db.add(a)
        era_concluida = False
    for k, val in v.items():
        setattr(a, k, val)
    a.atualizado_em, a.atualizado_por = now, admin.nome
    if v["etapa"] == CONCLUIDA and not era_concluida:
        a.concluido_em = now
    elif v["etapa"] != CONCLUIDA:
        a.concluido_em = None
    db.commit()
    return a


def delete(db: Session, action_id: str) -> None:
    a = db.get(Action, action_id)
    if a is None:
        raise NotFound("ACAO_NAO_ENCONTRADA", "Ação não encontrada.")
    db.delete(a)
    db.commit()
