"""
Popula o banco com dados FICTÍCIOS para demonstração (portfólio, prints, testes manuais).

    python -m scripts.demo_data            # usa o horário atual
    python -m scripts.demo_data --limpar   # apaga registros e colaboradores antes

Usa os próprios serviços da aplicação (entrada e saída), então todas as regras valem:
pausa programada, aging, motivo obrigatório em atraso. Em fim de semana as peças
de running aparecem pausadas — é o comportamento correto.
"""

import argparse
import random
from datetime import datetime, time, timedelta

from sqlalchemy import delete, select

from app import migrate
from app.clock import get_now
from app.config import settings as env
from app.db import SessionLocal
from app.models import Action, AlertLog, Employee, Record, Setting
from app.services import config_store
from app.services import records as svc
from app.services.responsibles import replace_matrix

NOMES = [
    "Ana Souza", "Carlos Lima", "Beatriz Rocha", "Diego Martins", "Elisa Prado", "Fábio Nunes",
    "Gabriela Reis", "Henrique Alves", "Isabela Costa", "João Ferreira", "Larissa Melo", "Marcos Vieira",
]
MATRIZ = [
    {"linha": linha, "funcao": f, "turno1": f"{f.lower()}.l{n}@example.com", "turno2": f"{f.lower()}.l{n}.t2@example.com"}
    for n, linha in ((1, "Linha 1"), (2, "Linha 2"), (3, "Linha 3"))
    for f in ("Monitor", "Lider")
] + [
    {"linha": "TODAS", "funcao": "Auditor", "turno1": "auditoria@example.com", "turno2": "auditoria.t2@example.com"},
    {"linha": "TODAS", "funcao": "Supervisor", "turno1": "supervisao@example.com", "turno2": "supervisao@example.com"},
]


def _pos(rng: random.Random, cfg) -> dict:
    return {
        "linha_producao": rng.choice(sorted(cfg.lines)),
        "lado": rng.choice(["Lado A", "Lado B"]),
        "posicao": f"Linha {rng.randint(1, cfg.layout.rows_per_side)}",
        "localizacao": f"G{rng.randint(1, len(cfg.layout.group_capacity))}",
    }


def seed_demo(db, now: datetime, ativos: int = 36, historico_dias: int = 30, seed: int = 7) -> None:
    rng = random.Random(seed)  # noqa: S311 (dados fictícios, não é criptografia)
    config_store.seed(db)
    for i, nome in enumerate(NOMES):
        mat = str(10100 + i * 7)
        if db.get(Employee, mat) is None:
            db.add(Employee(matricula=mat, nome=nome))
    db.commit()
    replace_matrix(db, MATRIZ)
    cfg = config_store.load(db)
    mats = [str(10100 + i * 7) for i in range(len(NOMES))]
    motivos = [m for m in cfg.reasons if "Pausa" not in m] or list(cfg.reasons)

    # Histórico: 30 dias úteis de operação, com a melhoria do kaizen aparecendo aos poucos.
    pesos_motivo = {"Troca de turno": 35, "Esqueceu de remover": 25, "Falha no aparelho": 15,
                    "Intervalo para refeição": 15, "Produto divergente do plano atual": 10}
    motivos_pesados = [m for m in pesos_motivo if m in motivos] or motivos
    base_linha = {"LINHA 1": 36, "LINHA 2": 52, "LINHA 3": 41}
    tz = env.timezone
    hoje = now.astimezone(tz).date()
    seq = 0
    for idade in range(historico_dias, 0, -1):
        dia = hoje - timedelta(days=idade)
        if dia.weekday() > 4:
            continue
        for _ in range(rng.randint(10, 18)):
            turno2 = rng.random() < 0.4
            minuto = rng.randint(17 * 60 + 35, 24 * 60 + 90) if turno2 else rng.randint(7 * 60 + 35, 16 * 60 + 30)
            entrada = datetime.combine(dia, time(0), tz) + timedelta(minutes=minuto)
            pos = _pos(rng, cfg)
            base = base_linha.get(pos["linha_producao"], 50) + (8 if turno2 else 0) + 14 * idade / historico_dias
            dur = max(8.0, base * rng.lognormvariate(0, 0.33))
            saida = entrada + timedelta(minutes=dur)
            if saida >= now - timedelta(hours=2):
                continue
            seq += 1
            rec = svc.register_entry(db, cfg, entrada, matricula=rng.choice(mats), pcba=f"DEMO{100000 + seq}", **pos)
            limite = cfg.threshold_min
            if dur >= limite + 5:   # chegou ao alerta: nível 1, talvez nível 2, ciente na maioria
                rec.mark_alert(1, entrada + timedelta(minutes=limite + 5))
                if dur >= limite + 15:
                    rec.mark_alert(2, entrada + timedelta(minutes=limite + 15))
                if rng.random() < 0.78:
                    rec.ciente_em = entrada + timedelta(minutes=limite + 5 + rng.uniform(1, 12))
                    rec.ciente_matricula, rec.ciente_nome = mats[0], NOMES[0]
            motivo = rng.choices(motivos_pesados, [pesos_motivo.get(m, 10) for m in motivos_pesados])[0]
            try:
                svc.register_exit(db, cfg, saida, rec.id)
            except Exception:  # em atraso: exige motivo
                svc.register_exit(db, cfg, saida, rec.id, motivo)

    # Peças na estação agora: maioria no prazo, algumas vencendo, atrasadas e em aging.
    perfis = [5] * 8 + [20] * 6 + [35] * 5 + [48] * 4 + [52] * 2 + [75] * 3 + [130] * 2 + [-1] * 6
    for i, minutos in enumerate(perfis[:ativos]):
        if minutos == -1:  # aging
            horas = rng.choice(cfg.aging_options_h)
            entrada = now - timedelta(hours=rng.uniform(1, horas + 2))
            svc.register_entry(db, cfg, entrada, matricula=rng.choice(mats), pcba=f"AGING{2000 + i}",
                               tipo="Aging", aging_horas=horas, **_pos(rng, cfg))
        else:
            entrada = now - timedelta(minutes=minutos + rng.uniform(0, 4))
            svc.register_entry(db, cfg, entrada, matricula=rng.choice(mats), pcba=f"0025{rng.randint(10**8, 10**9 - 1)}",
                               **_pos(rng, cfg))
    # Uma peça atrasada já com ciente registrado.
    late = db.scalars(select(Record).where(Record.saida_em.is_(None), Record.tipo == "Running")
                      .order_by(Record.entrada_em)).first()
    if late:
        late.mark_alert(1, now - timedelta(minutes=40))
        late.mark_alert(2, now - timedelta(minutes=30))
        late.ciente_em, late.ciente_matricula, late.ciente_nome = now - timedelta(minutes=28), mats[1], NOMES[1]
        db.commit()

    # Uma saída esquecida (aparece em Qualidade dos dados).
    svc.register_entry(db, cfg, now - timedelta(days=2, hours=3), matricula=mats[3], pcba="ESQUECIDA01", **_pos(rng, cfg))

    # Linha de base do kaizen (fictícia) e um plano de ação de exemplo.
    db.merge(Setting(key="baseline_min", value="72"))
    db.merge(Setting(key="baseline_fonte", value="Medição fictícia de demonstração — 40 amostras antes do kaizen"))
    db.commit()
    if not db.scalars(select(Action)).first():
        autor = "Admin Demo"
        exemplos = [
            ("LINHA 2", "Linha 2 com o maior tempo médio e metade dos atrasos", "Mapear o fluxo de retirada da Linha 2 (gemba) e comparar com a Linha 1", "Líder Linha 2", 6, "Executar", ""),
            ("", "Troca de turno é o principal motivo de atraso", "Incluir a estação no checklist de passagem de turno", "Supervisão", 10, "Planejar", ""),
            ("", "Alertas sem ciente em parte dos casos", "Revisar a matriz de responsáveis do Turno 2", "Qualidade", -2, "Executar", ""),
            ("LINHA 3", "Peças esquecidas após o fim do teste", "Sinal visual (bandeira) nas posições com teste concluído", "Líder Linha 3", 3, "Verificar", ""),
            ("LINHA 1", "Fila na entrada da estação no início do Turno 1", "Escalonar entradas por linha em janelas de 15 min", "Líder Linha 1", -10, "Concluída", "Fila caiu de 9 para 3 peças no pico; tempo médio −6 min"),
        ]
        for linha, prob, acao, resp, prazo_d, etapa, res in exemplos:
            db.add(Action(linha=linha, origem="Demonstração", problema=prob, acao=acao, responsavel=resp,
                          prazo=hoje + timedelta(days=prazo_d), etapa=etapa, resultado=res,
                          criado_em=now - timedelta(days=12), criado_por=autor, atualizado_em=now - timedelta(days=1),
                          atualizado_por=autor, concluido_em=now - timedelta(days=11) if etapa == "Concluída" else None))
        db.commit()


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--limpar", action="store_true", help="apaga registros e colaboradores antes de popular")
    a = p.parse_args()
    migrate.upgrade()
    with SessionLocal() as db:
        if a.limpar:
            for m in (AlertLog, Record, Employee, Action):
                db.execute(delete(m))
            db.commit()
        seed_demo(db, get_now())
    print("Dados de demonstração criados. Abra http://localhost:8000")


if __name__ == "__main__":
    main()
