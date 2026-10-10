"""Indicadores e qualidade dos dados — leitura aberta (a pauta da reunião precisa estar visível)."""

from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_config
from app.clock import get_now
from app.config import settings as env
from app.db import get_db
from app.domain.position import normalize_line
from app.services import kpi as kpi_svc
from app.services import quality as quality_svc
from app.services.config_store import AppConfig

router = APIRouter(tags=["Indicadores"])


@router.get("/kpi")
def kpi(
    inicio: date | None = Query(None, description="Padrão: 30 dias atrás"),
    fim: date | None = Query(None, description="Padrão: hoje"),
    linha: str | None = Query(None, examples=["Linha 1"]),
    turno: str | None = Query(None, examples=["Turno 1"]),
    db: Session = Depends(get_db), cfg: AppConfig = Depends(get_config), now: datetime = Depends(get_now),
):
    """Indicadores do running test no período: resumo, comparação com o período anterior,
    ganho do kaizen, leitura executiva e os recortes para os gráficos."""
    hoje = now.astimezone(env.timezone).date()
    fim = fim or hoje
    inicio = inicio or fim - timedelta(days=29)
    return kpi_svc.build(db, cfg, now, inicio, fim, normalize_line(linha) if linha else None, turno or None)


@router.get("/quality")
def quality(db: Session = Depends(get_db), cfg: AppConfig = Depends(get_config), now: datetime = Depends(get_now)):
    """Registros abertos há mais de 24 h, posições fora do layout atual e linhas fora do cadastro."""
    return quality_svc.report(db, cfg, now)
