"""Configurações persistidas no banco, com valores padrão e carga inicial."""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings as env
from app.domain.position import Layout, normalize_line
from app.models import DelayReason, ProductionLine, Setting

MOTIVO_PAUSA = "Pausa programada (sem expediente)"
MOTIVOS_PADRAO = (
    "Falha no aparelho",
    "Troca de turno",
    "Intervalo para refeição",
    "Esqueceu de remover",
    "Produto divergente do plano atual",
)
DEFAULTS = {
    "threshold_min": "60",
    "aging_options_h": "12,24",
    "group_capacity": "10,10,10,10,10,10,5",
    "rows_per_side": "6",
    "baseline_min": "",     # linha de base do kaizen (tempo médio ANTES), em minutos
    "baseline_fonte": "",   # de onde veio a medição — é o que torna o ganho auditável
}


@dataclass(frozen=True)
class AppConfig:
    threshold_min: int
    aging_options_h: tuple[int, ...]
    layout: Layout
    lines: set[str]
    reasons: tuple[str, ...]
    baseline_min: float | None = None
    baseline_fonte: str = ""


def _ints(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in v.replace(";", ",").split(",") if x.strip())


def seed(db: Session) -> None:
    """Carga inicial idempotente: configurações, linhas e motivos padrão."""
    for k, v in DEFAULTS.items():
        if db.get(Setting, k) is None:
            db.add(Setting(key=k, value=v))
    if not db.scalars(select(ProductionLine)).first():
        for nome in env.seed_lines:
            db.add(ProductionLine(nome=normalize_line(nome)))
    if not db.scalars(select(DelayReason)).first():
        for m in MOTIVOS_PADRAO:
            db.add(DelayReason(texto=m))
    db.commit()


def load(db: Session) -> AppConfig:
    raw = {s.key: s.value for s in db.scalars(select(Setting))}
    val = lambda k: raw.get(k, DEFAULTS[k])  # noqa: E731
    reasons = tuple(r.texto for r in db.scalars(select(DelayReason).order_by(DelayReason.id))) + (MOTIVO_PAUSA,)
    return AppConfig(
        threshold_min=int(val("threshold_min")),
        aging_options_h=_ints(val("aging_options_h")),
        layout=Layout(group_capacity=_ints(val("group_capacity")), rows_per_side=int(val("rows_per_side"))),
        lines={pl.nome for pl in db.scalars(select(ProductionLine))},
        reasons=reasons,
        baseline_min=float(val("baseline_min")) if val("baseline_min") else None,
        baseline_fonte=val("baseline_fonte"),
    )
