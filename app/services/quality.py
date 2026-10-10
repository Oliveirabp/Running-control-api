"""Qualidade dos dados: o que está errado no registro e distorce os indicadores."""

from collections import Counter
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings as env
from app.domain.kpi import LIMITE_ABERTO_H
from app.domain.position import PositionError, validate_position
from app.exceptions import Conflict, NotFound
from app.models import Admin, Record
from app.services.config_store import AppConfig
from app.services.records import time_of

MOTIVO_SAIDA_ESQUECIDA = "Esqueceu de remover"


def report(db: Session, cfg: AppConfig, now: datetime) -> dict:
    abertos = []
    for r in db.scalars(select(Record).where(Record.saida_em.is_(None)).order_by(Record.entrada_em)):
        rt = time_of(r, now, cfg)
        # Running: aberto há mais de 24 h efetivas. Aging: passou da duração planejada + 24 h.
        lim = (rt.limit_min if rt.aging else 0) + LIMITE_ABERTO_H * 60
        if rt.minutes >= lim:
            abertos.append({
                "id": r.id, "pcba": r.pcba, "linha": r.linha_producao, "lado": r.lado, "posicao": r.posicao,
                "localizacao": r.localizacao, "nome": r.nome, "entrada_em": r.entrada_em, "tipo": r.tipo,
                "minutos": round(rt.minutes),
            })

    invalidas, fora = [], Counter()
    for r in db.scalars(select(Record).where(Record.ajuste == "").order_by(Record.entrada_em.desc()).limit(5000)):
        try:
            # O layout pode ter mudado depois da entrada: confere contra o layout atual.
            validate_position(r.linha_producao, r.lado, r.posicao, r.localizacao, cfg.layout, None)
        except PositionError as e:
            invalidas.append({"id": r.id, "pcba": r.pcba, "entrada_em": r.entrada_em, "aberto": r.saida_em is None,
                              "posicao": f"{r.lado} · {r.posicao} · {r.localizacao}", "erros": e.errors})
        if cfg.lines and r.linha_producao not in cfg.lines:
            fora[r.linha_producao] += 1

    return {
        "limite_aberto_h": LIMITE_ABERTO_H,
        "abertos": abertos,
        "posicoes_invalidas": {"total": len(invalidas), "itens": invalidas[:40]},
        "linhas_fora_do_cadastro": [{"linha": ln, "n": n} for ln, n in fora.most_common()],
        "volume": {
            "registros": db.scalar(select(func.count()).select_from(Record)) or 0,
            "ajustados": db.scalar(select(func.count()).select_from(Record).where(Record.ajuste != "")) or 0,
        },
    }


def close_forgotten(db: Session, cfg: AppConfig, now: datetime, record_id: str, admin: Admin) -> Record:
    """
    Encerra uma saída esquecida. O registro recebe o motivo "Esqueceu de remover" e a marca
    de ajuste: sai das médias dos KPIs, mas fica rastreável (quem encerrou e quando).
    """
    rec = db.get(Record, record_id)
    if rec is None:
        raise NotFound("REGISTRO_NAO_ENCONTRADO", "Registro não encontrado.")
    if rec.saida_em is not None:
        raise Conflict("SAIDA_JA_REGISTRADA", "Este registro já foi encerrado.")
    rt = time_of(rec, now, cfg)
    carimbo = now.astimezone(env.timezone).strftime("%d/%m/%Y %H:%M")
    rec.saida_em = now
    rec.motivo = MOTIVO_SAIDA_ESQUECIDA
    rec.duracao_efetiva_min = round(rt.minutes, 2)
    rec.pausa_programada = rt.had_pause
    rec.ajuste = f"Saída esquecida — encerrado por {admin.nome} em {carimbo}"
    db.commit()
    return rec
