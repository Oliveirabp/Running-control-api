"""Matriz de escalonamento (responsáveis por linha e turno)."""

import re

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.domain.escalation import LINHA_TODAS, parse_emails
from app.domain.position import normalize_line
from app.exceptions import Unprocessable
from app.models import ProductionLine, Responsible

FUNCOES = ("Monitor", "Lider", "Auditor", "Supervisor")
_EMAIL = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def replace_matrix(db: Session, rows: list[dict]) -> list[Responsible]:
    """Regrava a matriz inteira e garante que cada linha citada exista no cadastro de linhas."""
    novos: list[Responsible] = []
    for r in rows:
        funcao = r["funcao"]
        if funcao not in FUNCOES:
            raise Unprocessable("FUNCAO_INVALIDA", f"Função inválida: {funcao}. Use {', '.join(FUNCOES)}.")
        linha = LINHA_TODAS if funcao == "Supervisor" else normalize_line(r["linha"])
        t1, t2 = parse_emails(r.get("turno1", "")), parse_emails(r.get("turno2", ""))
        invalidos = [e for e in t1 + t2 if not _EMAIL.match(e)]
        if invalidos:
            raise Unprocessable("EMAIL_INVALIDO", f"E-mail inválido ({linha} / {funcao}): {', '.join(invalidos)}")
        novos.append(Responsible(linha=linha, funcao=funcao, turno1=", ".join(t1), turno2=", ".join(t2)))

    db.execute(delete(Responsible))
    db.add_all(novos)
    existentes = {pl.nome for pl in db.scalars(select(ProductionLine))}
    for linha in {n.linha for n in novos} - existentes - {LINHA_TODAS}:
        db.add(ProductionLine(nome=linha))
    db.commit()
    return novos


def list_matrix(db: Session) -> list[Responsible]:
    return list(db.scalars(select(Responsible).order_by(Responsible.linha, Responsible.funcao)))
