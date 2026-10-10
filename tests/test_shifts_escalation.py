"""Turnos e regras de escalonamento (domínio puro)."""

import pytest

from app.domain.escalation import LEVELS, MatrixRow, parse_emails, recipients_for
from app.domain.shifts import FORA, TURNO_1, TURNO_2, turno_of
from tests.conftest import SP, local


@pytest.mark.parametrize("dt,esperado", [
    (local(2026, 10, 7, 7, 30), TURNO_1),   # quarta, início do turno 1
    (local(2026, 10, 7, 17, 28), TURNO_1),
    (local(2026, 10, 7, 17, 29), FORA),     # intervalo entre turnos
    (local(2026, 10, 7, 17, 30), TURNO_2),
    (local(2026, 10, 8, 2, 59), TURNO_2),   # madrugada de quinta
    (local(2026, 10, 8, 3, 0), FORA),
    (local(2026, 10, 10, 1, 0), TURNO_2),   # sábado de madrugada ainda é turno 2 de sexta
    (local(2026, 10, 10, 10, 0), FORA),     # sábado de dia
    (local(2026, 10, 5, 1, 0), FORA),       # segunda de madrugada: domingo não tem turno
])
def test_turno_of(dt, esperado):
    assert turno_of(dt, SP) == esperado


def test_parse_emails_remove_duplicados_e_normaliza():
    assert parse_emails(" A@x.com; b@x.com,\na@X.com ") == ("a@x.com", "b@x.com")


MATRIZ = [
    MatrixRow("LINHA 1", "Monitor", ("m1@x.com",), ("m1n@x.com",)),
    MatrixRow("LINHA 3", "Monitor", ("m3@x.com",), ("m3n@x.com",)),
    MatrixRow("LINHA 3", "Lider", ("l3@x.com",), ()),
    MatrixRow("TODAS", "Auditor", ("aud@x.com",), ("audn@x.com",)),
    MatrixRow("TODAS", "Supervisor", ("sup@x.com",), ("sup@x.com",)),
]


def test_nivel1_so_monitor_da_linha_no_turno_em_vigor():
    assert recipients_for(MATRIZ, "LINHA 3", LEVELS[0], TURNO_1, TURNO_1) == ["m3@x.com"]
    assert recipients_for(MATRIZ, "LINHA 3", LEVELS[0], TURNO_2, TURNO_1) == ["m3n@x.com"]


def test_nivel2_lider_e_auditor_incluindo_linha_todas():
    assert recipients_for(MATRIZ, "LINHA 3", LEVELS[1], TURNO_1, TURNO_1) == ["l3@x.com", "aud@x.com"]


def test_nivel3_supervisor_sem_duplicar():
    assert recipients_for(MATRIZ, "LINHA 1", LEVELS[2], TURNO_2, TURNO_1) == ["sup@x.com"]


def test_fora_de_turno_usa_turno_da_entrada_e_depois_os_dois():
    assert recipients_for(MATRIZ, "LINHA 3", LEVELS[0], FORA, TURNO_2) == ["m3n@x.com"]
    assert recipients_for(MATRIZ, "LINHA 3", LEVELS[0], FORA, FORA) == ["m3@x.com", "m3n@x.com"]
