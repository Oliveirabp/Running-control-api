"""
Validação e padronização da posição física da peça.

Aceita as variações reais das etiquetas (“Linha L1”, “L01”, “LADO-A”, “G-03”,
“Grupo 3”) e devolve sempre o mesmo padrão: “Lado A”, “Linha 1”, “G3”.
"""

import re
import unicodedata
from dataclasses import dataclass

_CTRL = re.compile(r"[\x00-\x1f\x7f]")
_LADO = re.compile(r"^(?:LADO)?\s*[-:.]?\s*([AB])$", re.I)
_POS = re.compile(r"^(?:LINHA)?\s*[-:.]?\s*(?:L)?\s*[-:.]?\s*0*(\d+)$", re.I)
_LOC = re.compile(r"^(?:GRUPO|G)\s*[-:.]?\s*0*(\d+)(?:\s*[-./ ]\s*0*(\d+))?$", re.I)
_LINE_NUM = re.compile(r"^LINHA\s*[-:.]?\s*0*(\d+)$")


def _clean(v: str | None) -> str:
    return _CTRL.sub("", v or "").strip()


def normalize_line(v: str | None) -> str:
    """'línha 01' -> 'LINHA 1'. Sem acento, maiúsculo, número sem zeros à esquerda."""
    t = unicodedata.normalize("NFD", _clean(v))
    t = "".join(c for c in t if unicodedata.category(c) != "Mn").upper()
    return _LINE_NUM.sub(r"LINHA \1", t)


@dataclass(frozen=True)
class Layout:
    group_capacity: tuple[int, ...] = (10, 10, 10, 10, 10, 10, 5)  # G1..G7
    rows_per_side: int = 6  # Linha 1..6 em cada lado


@dataclass(frozen=True)
class Position:
    linha_producao: str
    lado: str
    posicao: str
    localizacao: str


class PositionError(ValueError):
    def __init__(self, errors: list[str]):
        super().__init__(" ".join(errors))
        self.errors = errors


def validate_position(
    linha_producao: str, lado: str, posicao: str, localizacao: str,
    layout: Layout = Layout(), valid_lines: set[str] | None = None,
) -> Position:
    errors: list[str] = []

    lp = normalize_line(linha_producao)
    if not lp:
        errors.append("Linha de produção vazia.")
    elif valid_lines and lp not in valid_lines:
        errors.append(f'Linha de produção "{linha_producao}" não cadastrada (válidas: {", ".join(sorted(valid_lines))}).')

    m_lado = _LADO.match(_clean(lado))
    if not m_lado:
        errors.append(f'Lado "{lado}" inválido (use Lado A ou Lado B).')

    m_pos = _POS.match(_clean(posicao))
    n_pos = int(m_pos.group(1)) if m_pos else 0
    if not m_pos or not 1 <= n_pos <= layout.rows_per_side:
        errors.append(f'Posição "{posicao}" inválida (use Linha 1 a Linha {layout.rows_per_side}).')

    m_loc = _LOC.match(_clean(localizacao))
    g = int(m_loc.group(1)) if m_loc else 0
    vaga = int(m_loc.group(2)) if m_loc and m_loc.group(2) else None
    if not m_loc or not 1 <= g <= len(layout.group_capacity):
        errors.append(f'Localização "{localizacao}" inválida (use G1 a G{len(layout.group_capacity)}).')
    elif vaga is not None and not 1 <= vaga <= layout.group_capacity[g - 1]:
        errors.append(f"Vaga {vaga} não existe no G{g} (máximo {layout.group_capacity[g - 1]}).")

    if errors:
        raise PositionError(errors)
    return Position(
        linha_producao=lp,
        lado=f"Lado {m_lado.group(1).upper()}",
        posicao=f"Linha {n_pos}",
        localizacao=f"G{g}" + (f"-{vaga}" if vaga is not None else ""),
    )


def normalize_matricula(v: str | None) -> str:
    """'012107\\r' -> '12107'."""
    t = _clean(v).upper()
    return re.sub(r"^0+(?=\d)", "", t)
