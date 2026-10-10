"""Casos de uso de entrada e saída de peças."""

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings as env
from app.domain.position import PositionError, normalize_matricula, validate_position
from app.domain.time_rules import RecordTime, record_time
from app.exceptions import Conflict, NotFound, Unprocessable
from app.models import TIPO_AGING, TIPO_RUNNING, Employee, Record
from app.services.config_store import AppConfig


def time_of(rec: Record, now: datetime, cfg: AppConfig) -> RecordTime:
    return record_time(rec.tipo, rec.planejado_min, rec.entrada_em, rec.saida_em or now, cfg.threshold_min, env.timezone)


def find_employee(db: Session, matricula: str) -> Employee:
    alvo = normalize_matricula(matricula)
    for emp in db.scalars(select(Employee)):
        if normalize_matricula(emp.matricula) == alvo:
            return emp
    raise NotFound("MATRICULA_NAO_ENCONTRADA", "Matrícula não encontrada na base de colaboradores.")


def active_by_pcba(db: Session, pcba: str) -> Record | None:
    alvo = pcba.strip().upper()
    return db.scalars(
        select(Record).where(Record.saida_em.is_(None), func.upper(Record.pcba) == alvo)
    ).first()


def register_entry(
    db: Session, cfg: AppConfig, now: datetime, *, matricula: str, pcba: str,
    linha_producao: str, lado: str, posicao: str, localizacao: str,
    tipo: str = TIPO_RUNNING, aging_horas: int | None = None,
) -> Record:
    pcba = (pcba or "").strip()
    if not pcba:
        raise Unprocessable("PCBA_OBRIGATORIA", "Informe a PCBA.")
    emp = find_employee(db, matricula)

    try:
        pos = validate_position(linha_producao, lado, posicao, localizacao, cfg.layout, cfg.lines)
    except PositionError as e:
        raise Unprocessable("POSICAO_INVALIDA", "Posição inválida.", e.errors) from e

    planejado = None
    if tipo == TIPO_AGING:
        if aging_horas not in cfg.aging_options_h:
            raise Unprocessable(
                "AGING_DURACAO_INVALIDA",
                f"Duração de aging inválida. Opções: {', '.join(map(str, cfg.aging_options_h))} h.",
            )
        planejado = aging_horas * 60
    elif tipo != TIPO_RUNNING:
        raise Unprocessable("TIPO_INVALIDO", "Tipo de teste deve ser Running ou Aging.")

    # Poka-yoke: o mesmo PCBA não entra duas vezes enquanto está na estação.
    dup = active_by_pcba(db, pcba)
    if dup:
        local = dup.entrada_em.astimezone(env.timezone).strftime("%d/%m %H:%M")
        raise Conflict(
            "PCBA_JA_NA_ESTACAO",
            f"PCBA {pcba} já está na estação (entrada às {local}, {dup.localizacao}). Registre a saída antes.",
        )

    rec = Record(
        matricula=emp.matricula, nome=emp.nome, pcba=pcba,
        linha_producao=pos.linha_producao, lado=pos.lado, posicao=pos.posicao, localizacao=pos.localizacao,
        tipo=tipo, planejado_min=planejado, entrada_em=now,
    )
    db.add(rec)
    db.commit()
    return rec


def register_exit(db: Session, cfg: AppConfig, now: datetime, record_id: str, motivo: str | None = None) -> Record:
    rec = db.get(Record, record_id)
    if rec is None or rec.saida_em is not None:
        raise NotFound("REGISTRO_ATIVO_NAO_ENCONTRADO", "Registro ativo não encontrado (a saída pode já ter sido registrada).")

    rt = record_time(rec.tipo, rec.planejado_min, rec.entrada_em, now, cfg.threshold_min, env.timezone)
    motivo = (motivo or "").strip()
    if rt.overdue:
        if not motivo:
            raise Unprocessable("MOTIVO_OBRIGATORIO", "Peça em atraso: informe o motivo para registrar a saída.")
        if motivo.casefold() not in {m.casefold() for m in cfg.reasons}:
            raise Unprocessable("MOTIVO_INVALIDO", f"Motivo inválido: {motivo}")
    else:
        motivo = ""

    rec.saida_em = now
    rec.motivo = motivo
    rec.duracao_efetiva_min = round(rt.minutes, 2)
    rec.pausa_programada = rt.had_pause
    db.commit()
    return rec


def register_exit_by_pcba(db: Session, cfg: AppConfig, now: datetime, pcba: str, motivo: str | None = None) -> Record:
    rec = active_by_pcba(db, pcba)
    if rec is None:
        raise NotFound("PCBA_FORA_DA_ESTACAO", f"PCBA {pcba.strip()} não está na estação.")
    return register_exit(db, cfg, now, rec.id, motivo)


def list_active(db: Session) -> list[Record]:
    return list(db.scalars(select(Record).where(Record.saida_em.is_(None)).order_by(Record.entrada_em)))


def list_history(db: Session, limit: int = 200) -> list[Record]:
    return list(
        db.scalars(select(Record).where(Record.saida_em.is_not(None)).order_by(Record.saida_em.desc()).limit(limit))
    )


def acknowledge(db: Session, now: datetime, record_id: str, matricula: str) -> tuple[Record, bool]:
    """Registra quem assumiu o tratamento do alerta (leitura do crachá). Retorna (registro, já_existia)."""
    emp = find_employee(db, matricula)
    rec = db.get(Record, record_id)
    if rec is None:
        raise NotFound("REGISTRO_NAO_ENCONTRADO", "Registro não encontrado.")
    if rec.saida_em is not None:
        raise Conflict("SAIDA_JA_REGISTRADA", "Esta peça já teve a saída registrada.")
    if rec.ciente_em is not None:
        return rec, True
    rec.ciente_em, rec.ciente_matricula, rec.ciente_nome = now, emp.matricula, emp.nome
    db.commit()
    return rec, False


def delete_record(db: Session, record_id: str) -> None:
    rec = db.get(Record, record_id)
    if rec is None:
        raise NotFound("REGISTRO_NAO_ENCONTRADO", "Registro não encontrado.")
    db.delete(rec)
    db.commit()
