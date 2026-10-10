"""
Cria um administrador ou redefine a senha de um existente.

    python -m scripts.create_admin admin@example.com --nome "Seu Nome" --cargo "Eng. de Qualidade"

A senha é pedida no terminal (não aparece na tela nem fica no histórico).
"""

import argparse
import getpass

from app import migrate
from app.db import SessionLocal
from app.services.auth import upsert_admin


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("email")
    p.add_argument("--nome", default="Administrador")
    p.add_argument("--cargo", default="")
    a = p.parse_args()
    senha = getpass.getpass("Senha: ")
    if senha != getpass.getpass("Repita a senha: "):
        raise SystemExit("As senhas não conferem.")
    migrate.upgrade()
    with SessionLocal() as db:
        admin = upsert_admin(db, a.email, senha, a.nome, a.cargo)
    print(f"Administrador pronto: {admin.email}")


if __name__ == "__main__":
    main()
