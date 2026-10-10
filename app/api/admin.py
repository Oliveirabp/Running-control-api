"""Rotas que exigem administrador autenticado."""

from datetime import datetime

from fastapi import APIRouter, Depends, status
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.api.deps import current_admin, get_config, get_sender
from app.api.records import to_out
from app.clock import get_now
from app.db import get_db
from app.models import Admin, DelayReason, Setting
from app.schemas import BaselineIn, CheckSummaryOut, ReasonsIn, RecordOut, ResponsibleRow, ThresholdIn
from app.services import quality as quality_svc
from app.services import records as records_svc
from app.services import responsibles as resp_svc
from app.services.alerts import run_overdue_check
from app.services.config_store import MOTIVO_PAUSA, AppConfig
from app.services.mailer import EmailSender

router = APIRouter(prefix="/admin", tags=["Administração"], dependencies=[Depends(current_admin)])


@router.put("/threshold", response_model=ThresholdIn)
def set_threshold(body: ThresholdIn, db: Session = Depends(get_db)):
    db.merge(Setting(key="threshold_min", value=str(body.threshold_min)))
    db.commit()
    return body


@router.put("/reasons", response_model=list[str])
def set_reasons(body: ReasonsIn, db: Session = Depends(get_db)):
    """Substitui a lista de motivos. A pausa programada é sempre incluída pelo sistema."""
    limpos: list[str] = []
    for r in body.reasons:
        r = r.strip()
        if r and r.casefold() != MOTIVO_PAUSA.casefold() and r.casefold() not in {x.casefold() for x in limpos}:
            limpos.append(r)
    db.execute(delete(DelayReason))
    db.add_all(DelayReason(texto=r) for r in limpos)
    db.commit()
    return limpos + [MOTIVO_PAUSA]


@router.get("/responsibles", response_model=list[ResponsibleRow])
def get_responsibles(db: Session = Depends(get_db)):
    return resp_svc.list_matrix(db)


@router.put("/responsibles", response_model=list[ResponsibleRow])
def put_responsibles(rows: list[ResponsibleRow], db: Session = Depends(get_db)):
    return resp_svc.replace_matrix(db, [r.model_dump() for r in rows])


@router.post("/alerts/run", response_model=CheckSummaryOut)
def run_alerts_now(db: Session = Depends(get_db), cfg: AppConfig = Depends(get_config),
                   now: datetime = Depends(get_now), sender: EmailSender = Depends(get_sender)):
    """Executa a verificação de atrasos imediatamente (o agendador faz isso a cada minuto)."""
    return run_overdue_check(db, cfg, now, sender).__dict__


@router.delete("/records/{record_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_record(record_id: str, db: Session = Depends(get_db)):
    records_svc.delete_record(db, record_id)


@router.put("/baseline", response_model=BaselineIn)
def set_baseline(body: BaselineIn, db: Session = Depends(get_db)):
    """Linha de base do kaizen: o tempo médio ANTES da melhoria e de onde veio a medição.
    Congelada aqui, ela transforma o ganho em número auditável no KPI."""
    db.merge(Setting(key="baseline_min", value=str(body.minutos)))
    db.merge(Setting(key="baseline_fonte", value=body.fonte.strip()))
    db.commit()
    return body


@router.post("/records/{record_id}/close-forgotten", response_model=RecordOut)
def close_forgotten(record_id: str, db: Session = Depends(get_db), cfg: AppConfig = Depends(get_config),
                    now: datetime = Depends(get_now), admin: Admin = Depends(current_admin)):
    """Encerra uma saída esquecida: motivo "Esqueceu de remover" + marca de ajuste (fora das médias)."""
    return to_out(quality_svc.close_forgotten(db, cfg, now, record_id, admin), now, cfg)
