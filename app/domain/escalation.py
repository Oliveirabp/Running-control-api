"""
Escalonamento de alertas — minutos APÓS o limite da peça.

Cada nível é enviado uma única vez por peça, e só para quando a saída é registrada.
O "ciente" não interrompe a escalada: ele registra quem assumiu, mas o problema
só termina com a peça fora da estação.
"""

from dataclasses import dataclass

from app.domain.shifts import FORA, TURNO_1, TURNO_2
from app.domain.time_rules import RecordTime


@dataclass(frozen=True)
class Level:
    nivel: int
    apos_min: int
    funcoes: tuple[str, ...]
    rotulo: str


LEVELS: tuple[Level, ...] = (
    Level(1, 5, ("Monitor",), "Monitor da linha"),
    Level(2, 15, ("Lider", "Auditor"), "Líder de produção e Auditor de qualidade"),
    Level(3, 30, ("Supervisor",), "Supervisor"),
)
LINHA_TODAS = "TODAS"


def due_levels(rt: RecordTime, already_sent: set[int]) -> list[Level]:
    """Níveis que devem ser enviados agora para esta peça."""
    if rt.paused_now or rt.alert_deferred:
        return []
    return [lv for lv in LEVELS if lv.nivel not in already_sent and rt.minutes >= rt.limit_min + lv.apos_min]


@dataclass(frozen=True)
class MatrixRow:
    linha: str
    funcao: str
    turno1: tuple[str, ...]
    turno2: tuple[str, ...]


def parse_emails(raw: str) -> tuple[str, ...]:
    out: list[str] = []
    for e in raw.replace(";", ",").replace("\n", ",").split(","):
        e = e.strip().lower()
        if e and e not in out:
            out.append(e)
    return tuple(out)


def recipients_for(matrix: list[MatrixRow], linha: str, level: Level, turno_agora: str, turno_entrada: str) -> list[str]:
    """Quem recebe: o turno EM VIGOR no momento do alerta; fora de turno, o da entrada; senão, os dois."""
    turno = turno_agora if turno_agora != FORA else turno_entrada
    emails: list[str] = []
    for row in matrix:
        if row.funcao not in level.funcoes:
            continue
        if row.funcao != "Supervisor" and row.linha not in (linha, LINHA_TODAS):
            continue
        pool = row.turno1 if turno == TURNO_1 else row.turno2 if turno == TURNO_2 else row.turno1 + row.turno2
        for e in pool:
            if e not in emails:
                emails.append(e)
    return emails
