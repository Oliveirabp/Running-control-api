"""Turnos de trabalho."""

from datetime import datetime, time
from zoneinfo import ZoneInfo

TURNO_1 = "Turno 1"
TURNO_2 = "Turno 2"
FORA = "Fora de turno"


def turno_of(dt: datetime, tz: ZoneInfo) -> str:
    """Turno 1: seg–sex 07:30–17:28 · Turno 2: seg–sex 17:30–23:59 e ter–sáb 00:00–03:00."""
    local = dt.astimezone(tz)
    wd, t = local.weekday(), local.time()
    if wd <= 4 and time(7, 30) <= t <= time(17, 28, 59):
        return TURNO_1
    if wd <= 4 and t >= time(17, 30):
        return TURNO_2
    if 1 <= wd <= 5 and t < time(3, 0):
        return TURNO_2
    return FORA
