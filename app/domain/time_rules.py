"""
Tempo de permanência.

Running charge: conta o tempo EFETIVO — o relógio para nas janelas sem expediente
(sábado 03:00 → segunda 07:30 e terça a sexta 03:00 → 07:30) e volta ao fim delas.

Aging Test: conta o tempo REAL contra a duração planejada (o teste roda
fisicamente mesmo sem expediente); alertas que vencerem numa janela sem
expediente ficam adiados para a retomada.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

MON, TUE, WED, THU, FRI, SAT, SUN = range(7)


@dataclass(frozen=True)
class WeeklyWindow:
    """Janela semanal sem expediente: de (dia, hora) até (dia, hora)."""

    start_weekday: int
    start: time
    end_weekday: int
    end: time
    nome: str = ""


DEFAULT_WINDOWS: tuple[WeeklyWindow, ...] = (
    WeeklyWindow(SAT, time(3, 0), MON, time(7, 30), "Fim de semana"),
    *(WeeklyWindow(d, time(3, 0), d, time(7, 30), "Madrugada") for d in (TUE, WED, THU, FRI)),
)


@dataclass(frozen=True)
class Interval:
    start: datetime
    end: datetime


def pause_intervals(
    start: datetime, end: datetime, tz: ZoneInfo, windows: tuple[WeeklyWindow, ...] = DEFAULT_WINDOWS
) -> list[Interval]:
    """Intervalos sem expediente (em UTC) que tocam [start, end], já mesclados."""
    first: date = start.astimezone(tz).date() - timedelta(days=8)
    last: date = end.astimezone(tz).date()
    found: list[Interval] = []
    day = first
    while day <= last:
        for w in windows:
            if day.weekday() != w.start_weekday:
                continue
            ini = datetime.combine(day, w.start, tz)
            days_ahead = (w.end_weekday - w.start_weekday) % 7
            fim = datetime.combine(day + timedelta(days=days_ahead), w.end, tz)
            if fim <= ini:
                fim += timedelta(days=7)
            if fim > start and ini < end:
                found.append(Interval(ini.astimezone(UTC), fim.astimezone(UTC)))
        day += timedelta(days=1)
    found.sort(key=lambda i: i.start)
    merged: list[Interval] = []
    for it in found:
        if merged and it.start <= merged[-1].end:
            merged[-1] = Interval(merged[-1].start, max(merged[-1].end, it.end))
        else:
            merged.append(it)
    return merged


@dataclass(frozen=True)
class EffectiveTime:
    minutes: float
    paused_now: bool
    had_pause: bool


def effective_minutes(
    entry: datetime, now: datetime, tz: ZoneInfo, windows: tuple[WeeklyWindow, ...] = DEFAULT_WINDOWS
) -> EffectiveTime:
    """Minutos de permanência descontando as janelas sem expediente."""
    if now <= entry:
        return EffectiveTime(0.0, False, False)
    paused = timedelta()
    paused_now = False
    for it in pause_intervals(entry, now, tz, windows):
        ini, fim = max(it.start, entry), min(it.end, now)
        if fim > ini:
            paused += fim - ini
        if it.start <= now < it.end:
            paused_now = True
    total = (now - entry) - paused
    return EffectiveTime(max(total.total_seconds(), 0) / 60, paused_now, paused > timedelta())


@dataclass(frozen=True)
class RecordTime:
    minutes: float
    limit_min: float
    aging: bool
    paused_now: bool
    alert_deferred: bool
    had_pause: bool

    @property
    def overdue(self) -> bool:
        return self.minutes >= self.limit_min


def record_time(
    tipo: str,
    planejado_min: int | None,
    entry: datetime,
    now: datetime,
    running_limit_min: float,
    tz: ZoneInfo,
    windows: tuple[WeeklyWindow, ...] = DEFAULT_WINDOWS,
) -> RecordTime:
    """Tempo e limite de um registro conforme o tipo de teste."""
    if tipo == "Aging" and planejado_min:
        real = max((now - entry).total_seconds(), 0) / 60
        in_pause = any(it.start <= now < it.end for it in pause_intervals(now, now + timedelta(seconds=1), tz, windows))
        return RecordTime(real, float(planejado_min), True, False, in_pause, False)
    eff = effective_minutes(entry, now, tz, windows)
    return RecordTime(eff.minutes, float(running_limit_min), False, eff.paused_now, False, eff.had_pause)


def warn_at_min(limit_min: float) -> float:
    """Início do amarelo: últimos 15 min (ou metade, se o limite for curto); prazos longos, últimas 2 h."""
    if limit_min > 180:
        return limit_min - max(120.0, limit_min * 0.05)
    return max(limit_min * 0.5, limit_min - 15)


def status_of(rt: RecordTime) -> str:
    """ok | warn | crit | paused — a mesma regra de cores da tela e do Modo TV."""
    if rt.paused_now:
        return "paused"
    if rt.minutes >= rt.limit_min:
        return "crit"
    if rt.minutes >= warn_at_min(rt.limit_min):
        return "warn"
    return "ok"
