from datetime import datetime

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_config
from app.clock import get_now
from app.db import get_db
from app.domain.time_rules import status_of, warn_at_min
from app.models import Record
from app.schemas import AckIn, AckOut, EntryIn, ExitByPcbaIn, ExitIn, RecordOut
from app.services import records as svc
from app.services.config_store import AppConfig

router = APIRouter(prefix="/records", tags=["Registros"])


def to_out(rec: Record, now: datetime, cfg: AppConfig) -> RecordOut:
    rt = svc.time_of(rec, now, cfg)
    if rec.saida_em is not None and rec.duracao_efetiva_min is not None:
        minutes = rec.duracao_efetiva_min  # valor congelado na saída
    else:
        minutes = rt.minutes
    return RecordOut(
        id=rec.id, matricula=rec.matricula, nome=rec.nome, pcba=rec.pcba,
        linha_producao=rec.linha_producao, lado=rec.lado, posicao=rec.posicao, localizacao=rec.localizacao,
        tipo=rec.tipo, planejado_min=rec.planejado_min, entrada_em=rec.entrada_em, saida_em=rec.saida_em,
        motivo=rec.motivo, pausa_programada=rec.pausa_programada, ajuste=rec.ajuste or "",
        alertas_enviados=sum(1 for n in (1, 2, 3) if rec.alert_sent_at(n)),
        ciente_em=rec.ciente_em, ciente_nome=rec.ciente_nome,
        tempo_min=round(minutes, 2), limite_min=rt.limit_min, warn_min=round(warn_at_min(rt.limit_min), 2),
        status=status_of(rt) if rec.saida_em is None else ("crit" if rt.overdue else "ok"),
        em_atraso=rt.overdue,
    )


@router.post("/entries", response_model=RecordOut, status_code=status.HTTP_201_CREATED)
def create_entry(body: EntryIn, db: Session = Depends(get_db), cfg: AppConfig = Depends(get_config),
                 now: datetime = Depends(get_now)):
    rec = svc.register_entry(db, cfg, now, **body.model_dump())
    return to_out(rec, now, cfg)


@router.get("/active", response_model=list[RecordOut])
def active(db: Session = Depends(get_db), cfg: AppConfig = Depends(get_config), now: datetime = Depends(get_now)):
    return [to_out(r, now, cfg) for r in svc.list_active(db)]


@router.get("/history", response_model=list[RecordOut])
def history(limit: int = Query(200, ge=1, le=5000), db: Session = Depends(get_db),
            cfg: AppConfig = Depends(get_config), now: datetime = Depends(get_now)):
    return [to_out(r, now, cfg) for r in svc.list_history(db, limit)]


@router.post("/{record_id}/exit", response_model=RecordOut)
def exit_record(record_id: str, body: ExitIn, db: Session = Depends(get_db),
                cfg: AppConfig = Depends(get_config), now: datetime = Depends(get_now)):
    return to_out(svc.register_exit(db, cfg, now, record_id, body.motivo), now, cfg)


@router.post("/exit-by-pcba", response_model=RecordOut)
def exit_by_pcba(body: ExitByPcbaIn, db: Session = Depends(get_db),
                 cfg: AppConfig = Depends(get_config), now: datetime = Depends(get_now)):
    """Poka-yoke: a leitura do QR do PCBA registra a saída."""
    return to_out(svc.register_exit_by_pcba(db, cfg, now, body.pcba, body.motivo), now, cfg)


@router.post("/{record_id}/ack", response_model=AckOut)
def acknowledge(record_id: str, body: AckIn, db: Session = Depends(get_db), now: datetime = Depends(get_now)):
    """Ciente do alerta pela leitura do crachá. Não interrompe o escalonamento — só a saída encerra."""
    rec, existed = svc.acknowledge(db, now, record_id, body.matricula)
    return AckOut(ja_registrado=existed, ciente_nome=rec.ciente_nome, ciente_em=rec.ciente_em)
