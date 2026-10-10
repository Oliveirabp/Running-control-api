"""Regras de tempo: pausa programada, aging e cores."""

import pytest

from app.domain.time_rules import RecordTime, effective_minutes, record_time, status_of, warn_at_min
from tests.conftest import SP, local

# 2026-10-07 = quarta · 2026-10-10 = sábado · 2026-10-12 = segunda · 2026-10-13 = terça


@pytest.mark.parametrize(
    "entrada, agora, minutos, pausado",
    [
        (local(2026, 10, 7, 2, 30), local(2026, 10, 7, 3, 35), 30, True),    # madrugada: para às 03:00
        (local(2026, 10, 7, 2, 30), local(2026, 10, 7, 7, 30), 30, False),   # volta às 07:30
        (local(2026, 10, 7, 2, 30), local(2026, 10, 7, 8, 5), 65, False),    # 30 + 35
        (local(2026, 10, 10, 2, 30), local(2026, 10, 12, 7, 40), 40, False),  # fim de semana inteiro pausado
        (local(2026, 10, 12, 6, 0), local(2026, 10, 12, 8, 0), 30, False),   # segunda antes das 07:30
        (local(2026, 10, 12, 20, 0), local(2026, 10, 12, 21, 10), 70, False),  # turno normal
        (local(2026, 10, 13, 2, 0), local(2026, 10, 13, 4, 0), 60, True),    # terça madrugada
        (local(2026, 10, 7, 10, 0), local(2026, 10, 7, 11, 10), 70, False),  # quarta, sem pausa
    ],
)
def test_tempo_efetivo(entrada, agora, minutos, pausado):
    r = effective_minutes(entrada, agora, SP)
    assert round(r.minutes) == minutos
    assert r.paused_now is pausado


def test_tempo_efetivo_marca_que_teve_pausa():
    assert effective_minutes(local(2026, 10, 7, 2, 30), local(2026, 10, 7, 8, 0), SP).had_pause
    assert not effective_minutes(local(2026, 10, 7, 9, 0), local(2026, 10, 7, 10, 0), SP).had_pause


def test_aging_usa_tempo_real_e_prazo_proprio():
    rt = record_time("Aging", 24 * 60, local(2026, 10, 10, 2, 0), local(2026, 10, 11, 4, 0), 60, SP)
    assert rt.aging and round(rt.minutes) == 26 * 60  # sem desconto do fim de semana
    assert rt.limit_min == 1440 and rt.overdue
    assert rt.alert_deferred  # vence no domingo: alerta espera o expediente


def test_running_usa_limite_configurado():
    rt = record_time("Running", None, local(2026, 10, 7, 9, 0), local(2026, 10, 7, 10, 5), 60, SP)
    assert rt.limit_min == 60 and rt.overdue and not rt.aging


@pytest.mark.parametrize("limite, inicio_amarelo", [(60, 45), (20, 10), (1440, 1320), (720, 600)])
def test_inicio_do_amarelo(limite, inicio_amarelo):
    assert warn_at_min(limite) == inicio_amarelo


@pytest.mark.parametrize(
    "minutos, pausado, esperado", [(30, False, "ok"), (50, False, "warn"), (60, False, "crit"), (90, True, "paused")]
)
def test_status(minutos, pausado, esperado):
    assert status_of(RecordTime(minutos, 60, False, pausado, False, False)) == esperado
