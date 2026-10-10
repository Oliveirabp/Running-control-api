"""Validação da posição: tolerante na leitura, rígida no que não existe."""

import pytest

from app.domain.position import PositionError, normalize_line, normalize_matricula, validate_position

LINHAS = {"LINHA 1", "LINHA 2", "LINHA 3"}


@pytest.mark.parametrize(
    "lado, pos, loc, esperado",
    [
        ("Lado A", "Linha L1", "G1", ("Lado A", "Linha 1", "G1")),
        ("LADO-B", "L01", "G-03", ("Lado B", "Linha 1", "G3")),
        ("a", "Linha 6", "Grupo 7", ("Lado A", "Linha 6", "G7")),
        ("Lado A", "1\r", "G3-7", ("Lado A", "Linha 1", "G3-7")),
    ],
)
def test_aceita_variacoes_e_padroniza(lado, pos, loc, esperado):
    p = validate_position("Linha 3", lado, pos, loc, valid_lines=LINHAS)
    assert (p.lado, p.posicao, p.localizacao) == esperado
    assert p.linha_producao == "LINHA 3"


@pytest.mark.parametrize(
    "lp, lado, pos, loc, trecho",
    [
        ("Linha 4", "Lado A", "L1", "G1", "não cadastrada"),
        ("Linha 1", "Lado C", "L1", "G1", "Lado"),
        ("Linha 1", "Lado A", "Linha L7", "G1", "Posição"),
        ("Linha 1", "Lado A", "L1", "G8", "Localização"),
        ("Linha 1", "Lado A", "L1", "G7-6", "Vaga 6"),
    ],
)
def test_rejeita_o_que_nao_existe(lp, lado, pos, loc, trecho):
    with pytest.raises(PositionError) as e:
        validate_position(lp, lado, pos, loc, valid_lines=LINHAS)
    assert any(trecho in msg for msg in e.value.errors)


def test_lista_todos_os_erros_de_uma_vez():
    with pytest.raises(PositionError) as e:
        validate_position("Linha 9", "Lado C", "L9", "G9", valid_lines=LINHAS)
    assert len(e.value.errors) == 4


@pytest.mark.parametrize("bruto, norm", [("línha 01", "LINHA 1"), ("linha3", "LINHA 3"), ("Linha-2", "LINHA 2")])
def test_normaliza_linha(bruto, norm):
    assert normalize_line(bruto) == norm


@pytest.mark.parametrize("bruto, norm", [("012107", "12107"), (" 12107\r", "12107"), ("0", "0")])
def test_normaliza_matricula(bruto, norm):
    assert normalize_matricula(bruto) == norm
