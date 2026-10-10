# Changelog

## 1.0.0 — 2026-10-10

**Etapa 5 — pronto para produção**
- PostgreSQL 16 como banco de produção (SQLite continua no desenvolvimento).
- Migrações com Alembic, aplicadas na inicialização; teste garante que migrações e modelos estão em dia.
- Docker (multi-stage, sem root, healthcheck) e Docker Compose com PostgreSQL e volume persistente.
- CI no GitHub Actions: ruff, testes em SQLite e PostgreSQL, e o compose subindo de ponta a ponta.
- O histórico de registros sobrevive à remoção do colaborador do cadastro (sem chave estrangeira; retrato de matrícula e nome).
- Limites de tamanho dos campos alinhados ao banco (PostgreSQL rejeita texto maior que a coluna).

## 0.4.0

**Etapa 4 — indicadores e plano de ação**
- `/kpi` com resumo, período anterior, ganho do kaizen, leitura executiva e recortes (diário, linha, turno, faixa horária, distribuição, Pareto, reação, linha × turno, maiores permanências).
- Linha de base do kaizen com fonte obrigatória.
- Plano de ação PDCA; concluir exige resultado; “+ Ação” a partir da leitura executiva.
- Qualidade dos dados: saídas esquecidas encerradas como ajuste (fora das médias, rastreáveis).

## 0.3.0

**Etapa 3 — interface web**
- Painel do operador, Modo TV e Configurações, servidos pela própria API.

## 0.2.0

**Etapa 2 — segurança e alertas**
- Login de administrador (JWT + bcrypt), alertas escalonados por e-mail em 3 níveis, ciente, agendador.

## 0.1.0

**Etapa 1 — núcleo**
- Regras de tempo efetivo, aging, posição e poka-yoke; API de entrada e saída; testes.
