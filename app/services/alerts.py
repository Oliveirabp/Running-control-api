"""Verificação periódica de atrasos e envio dos alertas escalonados."""

import html as html_lib
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings as env
from app.domain.escalation import LEVELS, Level, MatrixRow, due_levels, parse_emails, recipients_for
from app.domain.shifts import FORA, turno_of
from app.domain.time_rules import RecordTime
from app.models import TIPO_AGING, AlertLog, Record, Responsible
from app.services.config_store import AppConfig
from app.services.mailer import EmailSender
from app.services.records import time_of


@dataclass
class CheckSummary:
    ativos: int = 0
    em_atraso: int = 0
    pausados: int = 0
    enviados: int = 0
    por_nivel: dict[int, int] = field(default_factory=lambda: {lv.nivel: 0 for lv in LEVELS})
    sem_destinatario: list[str] = field(default_factory=list)
    erros: list[str] = field(default_factory=list)


def load_matrix(db: Session) -> list[MatrixRow]:
    return [
        MatrixRow(r.linha, r.funcao, parse_emails(r.turno1), parse_emails(r.turno2))
        for r in db.scalars(select(Responsible))
    ]


def _fmt_tempo(minutos: float) -> str:
    h, m = divmod(int(minutos), 60)
    return f"{h}h {m:02d}min" if h else f"{m}min"


def _linha_legivel(v: str) -> str:
    return v.title() if v.upper().startswith("LINHA") else f"Linha {v}"


def build_email(rec: Record, rt: RecordTime, level: Level, turno: str) -> tuple[str, str, str]:
    """(assunto, texto, html) — o mesmo padrão de mensagem do sistema original."""
    entrada = rec.entrada_em.astimezone(env.timezone).strftime("%d/%m/%Y %H:%M")
    alocacao = f"{_linha_legivel(rec.linha_producao)}, {rec.lado}, {rec.posicao} Posição {rec.localizacao}"
    aging = f"[Aging {int(rec.planejado_min / 60)}h]" if rec.tipo == TIPO_AGING else ""
    subject = f"[Nível {level.nivel}/{len(LEVELS)}]{aging} Notificação Automática: Prazo de atividade vencido! — PCBA {rec.pcba}"

    if rec.ciente_em:
        hora = rec.ciente_em.astimezone(env.timezone).strftime("%H:%M")
        ciente = f"Ciente registrado por {rec.ciente_nome} às {hora}. A peça ainda não foi removida."
    else:
        ciente = "Ninguém confirmou ciência deste alerta até agora."
    proximo = next((lv for lv in LEVELS if lv.nivel == level.nivel + 1), None)
    link = f"{env.app_base_url.rstrip('/')}/?ciente={rec.id}"

    text = (
        "Olá,\n\n"
        "Notificação Automática: Prazo de atividade vencido!\n\n"
        f"Este é um alerta automático para informar que o prazo de permanência da peça alocada em {alocacao} foi atingido.\n\n"
        "O status atual do item consta em atraso.\n"
        "Solicita-se a remoção imediata da peça deste local!\n\n"
        f"Colaborador (entrada): {rec.nome} ({rec.matricula})\n"
        f"Horário de entrada: {entrada}\n"
        f"Turno responsável: {turno}\n"
        f"Tempo decorrido: {_fmt_tempo(rt.minutes)}\n\n"
        f"Escalonamento: nível {level.nivel} de {len(LEVELS)} — {level.rotulo}.\n{ciente}\n"
        + (f"Se a peça não for removida, o alerta sobe para: {proximo.rotulo} "
           f"(limite + {proximo.apos_min} min).\n" if proximo else "")
        + ("" if rec.ciente_em else f"\nConfirmar ciência: {link}\n")
    )
    body = html_lib.escape(text).replace("\n", "<br>")
    button = "" if rec.ciente_em else (
        f'<p><a href="{html_lib.escape(link)}" style="display:inline-block;background:#0B2545;color:#fff;'
        'text-decoration:none;font-weight:bold;padding:11px 20px;border-radius:7px;">Confirmar ciência</a></p>'
    )
    html = f'<div style="font-family:Arial,sans-serif;font-size:14px;color:#0F2036;">{body}</div>{button}'
    return subject, text, html


def run_overdue_check(db: Session, cfg: AppConfig, now: datetime, sender: EmailSender) -> CheckSummary:
    summary = CheckSummary()
    matrix = load_matrix(db)
    turno_agora = turno_of(now, env.timezone)

    for rec in db.scalars(select(Record).where(Record.saida_em.is_(None))):
        summary.ativos += 1
        rt = time_of(rec, now, cfg)
        if rt.paused_now:
            summary.pausados += 1
            continue
        if not rt.overdue:
            continue
        summary.em_atraso += 1
        if rt.alert_deferred:
            summary.pausados += 1
            continue

        sent = {lv.nivel for lv in LEVELS if rec.alert_sent_at(lv.nivel)}
        turno_entrada = turno_of(rec.entrada_em, env.timezone)
        turno_email = turno_agora if turno_agora != FORA else turno_entrada
        for level in due_levels(rt, sent):
            to = recipients_for(matrix, rec.linha_producao, level, turno_agora, turno_entrada)
            if not to:
                # Não marca como enviado: assim que houver responsável cadastrado, o próximo ciclo envia.
                summary.sem_destinatario.append(f"{rec.pcba} (nível {level.nivel})")
                continue
            try:
                sender.send(to, *build_email(rec, rt, level, turno_email))
            except Exception as e:  # uma falha não interrompe os demais
                summary.erros.append(f"{rec.pcba} (nível {level.nivel}): {e}")
                continue
            rec.mark_alert(level.nivel, now)
            db.add(AlertLog(record_id=rec.id, nivel=level.nivel, enviado_em=now, destinatarios=", ".join(to)))
            summary.enviados += 1
            summary.por_nivel[level.nivel] += 1
    db.commit()
    return summary
