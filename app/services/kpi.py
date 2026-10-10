"""Monta os indicadores de um período a partir do banco (o cálculo fica em app/domain/kpi.py)."""

from dataclasses import asdict
from datetime import date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings as env
from app.domain import kpi as K
from app.domain.shifts import turno_of
from app.exceptions import Unprocessable
from app.models import TIPO_AGING, Record
from app.services.config_store import AppConfig
from app.services.records import time_of

TURNOS = ("Turno 1", "Turno 2", "Fora de turno")


def _bounds(inicio: date, fim: date) -> tuple[datetime, datetime]:
    tz = env.timezone
    return datetime.combine(inicio, time.min, tz), datetime.combine(fim + timedelta(days=1), time.min, tz)


def _sample(r: Record) -> K.Sample:
    local = r.entrada_em.astimezone(env.timezone)
    reacao = None
    if r.alerta1_em and r.ciente_em:
        reacao = max(0.0, (r.ciente_em - r.alerta1_em).total_seconds() / 60)
    return K.Sample(
        entrada=r.entrada_em, minutos=float(r.duracao_efetiva_min or 0), linha=r.linha_producao,
        turno=turno_of(r.entrada_em, env.timezone), faixa=K.faixa_of(local),
        pcba=r.pcba, nome=r.nome, motivo=r.motivo, reacao_min=reacao, alertado=r.alerta1_em is not None,
    )


def build(db: Session, cfg: AppConfig, now: datetime, inicio: date, fim: date,
          linha: str | None = None, turno: str | None = None) -> dict:
    if fim < inicio:
        raise Unprocessable("PERIODO_INVALIDO", "A data final é anterior à inicial.")
    if (fim - inicio).days > 366:
        raise Unprocessable("PERIODO_INVALIDO", "Período máximo: 1 ano.")
    if turno and turno not in TURNOS:
        raise Unprocessable("TURNO_INVALIDO", f"Turno inválido. Use: {', '.join(TURNOS)}.")

    dias = (fim - inicio).days + 1
    ini, end = _bounds(inicio, fim)
    prev_ini = ini - timedelta(days=dias)
    limite = float(cfg.threshold_min)
    aberto_lim = K.LIMITE_ABERTO_H * 60

    def ok_filters(r: Record) -> bool:
        return (not linha or r.linha_producao == linha) and (not turno or turno_of(r.entrada_em, env.timezone) == turno)

    rows = db.scalars(select(Record).where(
        Record.entrada_em >= prev_ini, Record.entrada_em < end,
    )).all()
    ativos = db.scalars(select(Record).where(Record.saida_em.is_(None))).all()

    atual, anterior, excluidos = [], [], []
    aging_conc = aging_alem = 0
    for r in rows:
        if not ok_filters(r) or r.saida_em is None:
            continue
        if r.tipo == TIPO_AGING:
            if r.entrada_em >= ini:
                aging_conc += 1
                real = (r.saida_em - r.entrada_em).total_seconds() / 60
                aging_alem += real > (r.planejado_min or 0)
            continue
        dur = float(r.duracao_efetiva_min or 0)
        if r.ajuste or dur > aberto_lim:
            if r.entrada_em >= ini:
                excluidos.append({"pcba": r.pcba, "linha": r.linha_producao, "entrada_em": r.entrada_em,
                                  "minutos": round(dur), "motivo": "ajuste" if r.ajuste else f"acima de {K.LIMITE_ABERTO_H}h"})
            continue
        (atual if r.entrada_em >= ini else anterior).append(_sample(r))

    run_ativos, aging_ativos, aging_venc, atrasados = 0, 0, 0, 0
    for r in ativos:
        if not ok_filters(r):
            continue
        rt = time_of(r, now, cfg)
        if r.tipo == TIPO_AGING:
            aging_ativos += 1
            aging_venc += rt.overdue
        else:
            run_ativos += 1
            atrasados += rt.overdue and not rt.paused_now

    st = K.stats([x.minutos for x in atual], limite)
    st_prev = K.stats([x.minutos for x in anterior], limite)
    por_linha = K.group(atual, lambda x: x.linha, limite)
    por_turno = K.group(atual, lambda x: x.turno, limite)
    por_faixa = K.group(atual, lambda x: x.faixa, limite)
    diario = K.daily(atual, inicio, min(fim, now.astimezone(env.timezone).date()), env.timezone, limite)
    p_total, p_itens = K.pareto(atual, limite)
    reacao = K.reaction(atual)
    dias_decorridos = max(1, min(dias, (now.astimezone(env.timezone).date() - inicio).days + 1))
    ganho = K.gain(atual, cfg.baseline_min, cfg.baseline_fonte, dias_decorridos)

    leitura = K.insights(K.InsightContext(
        limite=limite, st=st, anterior=st_prev, por_linha=por_linha, por_turno=por_turno, por_faixa=por_faixa,
        dias=diario, pareto_total=p_total, pareto_itens=p_itens, reacao=reacao, ganho=ganho,
        tem_linha_de_base=cfg.baseline_min is not None, excluidos=len(excluidos),
        aging_concluidos=aging_conc, aging_alem=aging_alem, aging_ativos=aging_ativos, aging_vencidos=aging_venc,
        ativos=run_ativos, atrasados_agora=atrasados,
    ))

    linhas_presentes = sorted(por_linha)
    heat = []
    for ln in linhas_presentes:
        sub = [x for x in atual if x.linha == ln]
        cells = {t: asdict(K.stats([x.minutos for x in sub if x.turno == t], limite)) for t in TURNOS}
        heat.append({"linha": ln, "turnos": cells, "geral": asdict(por_linha[ln])})
    reacao_linhas = [
        {"linha": ln, **asdict(K.reaction([x for x in atual if x.linha == ln]))}
        for ln in sorted({x.linha for x in atual if x.alertado})
    ]

    return {
        "periodo": {"inicio": inicio, "fim": fim, "dias": dias},
        "filtros": {"linha": linha, "turno": turno},
        "limite_min": limite,
        "tolerancia_min": K.TOLERANCIA_MIN,
        "linha_de_base": {"minutos": cfg.baseline_min, "fonte": cfg.baseline_fonte},
        "resumo": asdict(st),
        "anterior": asdict(st_prev),
        "agora": {"running": run_ativos, "atrasados": atrasados, "aging": aging_ativos, "aging_vencidos": aging_venc},
        "ganho": asdict(ganho) if ganho else None,
        "leitura": [asdict(i) for i in leitura],
        "diario": [{"dia": d, **asdict(s)} for d, s in diario],
        "por_linha": sorted(({"chave": k, **asdict(s)} for k, s in por_linha.items()), key=lambda x: -x["media"]),
        "por_turno": [{"chave": t, **asdict(por_turno[t])} for t in TURNOS if t in por_turno],
        "por_faixa": [{"chave": i, "rotulo": K.faixa_label(i), **asdict(por_faixa[i])} for i in range(24) if i in por_faixa],
        "distribuicao": [asdict(b) for b in K.distribution(atual, limite)],
        "pareto": {"total": p_total, "itens": [asdict(p) for p in p_itens]},
        "reacao": {**asdict(reacao), "por_linha": reacao_linhas},
        "linha_turno": heat,
        "maiores": [
            {"pcba": x.pcba, "linha": x.linha, "turno": x.turno, "nome": x.nome, "entrada_em": x.entrada,
             "minutos": round(x.minutos, 1), "motivo": x.motivo}
            for x in sorted(atual, key=lambda x: -x.minutos)[:10]
        ],
        "excluidos": excluidos,
        "linhas_disponiveis": sorted({r.linha_producao for r in rows} | set(cfg.lines)),
    }
