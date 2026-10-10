# Running Control

[![CI](https://github.com/Oliveirabp/running-control-api/actions/workflows/ci.yml/badge.svg)](https://github.com/Oliveirabp/running-control-api/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.13-3776AB)
![FastAPI](https://img.shields.io/badge/FastAPI-0.143-009688)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1)
![License](https://img.shields.io/badge/licen%C3%A7a-MIT-green)

Sistema para controlar a permanência de peças (PCBAs) em estações de carregamento (*running test*): entrada e saída por QR code, tempo efetivo com pausa programada, Aging Test com prazo próprio, alertas escalonados por e-mail, Modo TV, indicadores com leitura executiva e Plano de ação (PDCA).

Nasceu em Google Apps Script num projeto Kaizen (Lean Six Sigma Green Belt), cujo problema era simples de enunciar e caro de ignorar: **peças esquecidas na estação**. Esta é a reescrita em Python, com as regras de negócio isoladas e testadas.

![Painel do operador](docs/img/painel.png)

## Stack

**Python 3.13 · FastAPI · SQLAlchemy 2 · Alembic · PostgreSQL 16 (SQLite no desenvolvimento) · APScheduler · JWT + bcrypt · HTML/JS sem build + Chart.js · pytest · ruff · Docker Compose · GitHub Actions**

## Telas

A interface é servida pela própria API e só conversa com ela pelos endpoints documentados. Nenhuma regra de negócio é duplicada no navegador.

| Rota | Tela | Para quem |
|---|---|---|
| `/` | **Painel**: entrada e saída por leitor de QR (Enter avança o campo), tempo ao vivo, ciente, histórico | Operador |
| `/tv` | **Modo TV**: mapa de ocupação por linha, indicadores, diagnóstico e fila de atenção; gira as linhas sozinho | Parede da estação |
| `/indicadores` | **Indicadores**: tempo médio, P90, aderência ao limite, ganho do kaizen, leitura executiva e gráficos | Liderança / reunião diária |
| `/plano` | **Plano de ação**: quadro PDCA e qualidade dos dados | Liderança (edição com login) |
| `/config` | **Configurações**: limite, motivos, linha de base, matriz de responsáveis, colaboradores | Administrador (login) |

![Modo TV](docs/img/modo-tv.png)

Detalhes que vieram do chão de fábrica:

- O leitor de QR “digita” e envia Enter; o formulário avança sozinho e, depois de registrar, mantém crachá, linha e lado — o operador costuma alocar várias peças seguidas.
- Saída de peça atrasada abre a lista de motivos antes de gravar; o link **Confirmar ciência** do e-mail abre o painel direto no modal de ciente.
- Entre as consultas (a cada 15 s) o tempo avança no navegador, exceto para Running em pausa programada, cujo relógio está parado.
- O Modo TV mostra “sem atualização há X min” em vermelho se perder a conexão, para ninguém confiar numa tela congelada.

## Do dado à ação

O sistema fecha o ciclo de melhoria contínua: o chão de fábrica registra, os indicadores dizem onde está o problema e o Plano de ação registra o que foi decidido.

![Indicadores](docs/img/indicadores.png)

- **Ganho do kaizen auditável.** O administrador congela a *linha de base* (tempo médio antes da melhoria) com a fonte da medição. A partir daí o ganho aparece em horas de estação liberadas e carregamentos a mais com a mesma ocupação — e vira alerta de regressão se o tempo voltar a subir.
- **Leitura executiva.** As mesmas regras, sempre: aderência ao limite, tendência vs período anterior, linha gargalo, diferença entre turnos, cauda longa (P90 / mediana), faixa horária crítica, principal motivo de atraso e reação aos alertas. Cada ponto amarelo ou vermelho tem um botão **+ Ação** que cria o item no Plano de ação já com a origem.
- **Comparação honesta.** Contagens de períodos com volumes diferentes não são comparadas diretamente: alertas são comparados como taxa (p.p.), e o período anterior tem sempre a mesma duração.
- **Qualidade dos dados.** Registros abertos há mais de 24 h aparecem para tratamento. Encerrar como “saída esquecida” grava o motivo e uma marca de ajuste: o registro sai das médias, mas continua rastreável (quem encerrou e quando).
- **Aging fora das médias.** O Aging Test tem prazo próprio; entra na leitura como visão separada para não distorcer o tempo de running.

![Plano de ação](docs/img/plano-de-acao.png)

Os gráficos usam Chart.js empacotado no projeto (sem CDN — redes de fábrica costumam bloquear) e seguem duas regras: um eixo por gráfico e paleta validada para daltonismo.

## Regras de negócio isoladas

O valor do sistema está nas regras, não nas telas. Por isso elas vivem em `app/domain/` como funções puras — sem banco e sem HTTP — e são cobertas por testes:

| Regra | Onde | O que garante |
|---|---|---|
| **Tempo efetivo** | `domain/time_rules.py` | O relógio para nas janelas sem expediente (sábado 03:00 → segunda 07:30; terça a sexta 03:00 → 07:30). Peça que entra às 02:30 de quarta tem 30 min às 07:30, não 5 h. |
| **Aging Test** | `domain/time_rules.py` | Tempo real contra a duração planejada (12 h / 24 h); alerta que vence sem expediente fica adiado. |
| **Cores** | `domain/time_rules.py` | `ok` → `warn` (últimos 15 min) → `crit`; `paused` durante a pausa. |
| **Posição** | `domain/position.py` | Aceita “Linha L1”, “L01”, “LADO-A”, “G-03”, “Grupo 3”; grava “Linha 1”, “Lado A”, “G3”. Rejeita o que não existe no layout e devolve **todos** os erros de uma vez. |
| **Poka-yoke** | `services/records.py` | PCBA não entra duas vezes; saída de peça em atraso exige motivo válido. |
| **Turnos** | `domain/shifts.py` | Turno 1 seg–sex 07:30–17:28; Turno 2 seg–sex 17:30 → 03:00 do dia seguinte. |
| **Escalonamento** | `domain/escalation.py` | Nível 1 (+5 min) Monitor da linha · Nível 2 (+15) Líder e Auditor · Nível 3 (+30) Supervisor. Cada nível sai uma única vez e vai para o turno **em vigor** no momento do alerta. |
| **Ciente** | `services/records.py` | Registra quem assumiu o alerta (crachá), mas **não** interrompe a escalada: só a saída da peça encerra. |
| **KPI** | `domain/kpi.py` | Quantis interpolados, aderência ≤ limite, alerta ≥ limite + 5, faixas horárias ancoradas em 07:30, Pareto, reação, ganho e leitura executiva. |

Erros de negócio voltam com **código estável**, para o front-end decidir pela chave e não pelo texto:

```json
{ "code": "POSICAO_INVALIDA", "message": "Posição inválida.",
  "errors": ["Lado \"Lado C\" inválido (use Lado A ou Lado B).", "Localização \"G9\" inválida (use G1 a G7)."] }
```

## Arquitetura

```
app/
├── domain/        regras puras (tempo, posição, turnos, escalonamento, KPI)
├── services/      casos de uso (registros, alertas, KPI, plano de ação, qualidade)
├── api/           rotas FastAPI (finas: validam, chamam o serviço, serializam)
├── web/           telas (HTML + JS sem build) e assets
├── models.py      SQLAlchemy 2 (datas sempre em UTC)
├── schemas.py     contratos Pydantic
├── migrate.py     aplica as migrações (Alembic) na inicialização
├── scheduler.py   verificação de atrasos a cada minuto (APScheduler)
├── clock.py       relógio injetável (os testes “congelam” o tempo)
└── main.py        aplicação e tratamento de erros
migrations/        versões do esquema (Alembic)
scripts/           create_admin.py · demo_data.py
tests/             pytest: regras puras + fluxos de ponta a ponta pela API
.github/workflows/ CI: lint, testes em SQLite e PostgreSQL, Docker Compose de ponta a ponta
```

## Como rodar

### Com Docker (recomendado)

```bash
cp .env.example .env    # preencha JWT_SECRET, ADMIN_EMAIL, ADMIN_PASSWORD e POSTGRES_PASSWORD
docker compose up -d --build
```

Sobe a aplicação e um PostgreSQL 16 com volume persistente. O banco não fica exposto fora do compose, e as migrações são aplicadas na inicialização. Para dados de demonstração: `docker compose exec app python -m scripts.demo_data`.

### Sem Docker (desenvolvimento)

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env                                 # preencha JWT_SECRET, ADMIN_EMAIL e ADMIN_PASSWORD
python -m scripts.demo_data                          # opcional: dados fictícios para explorar as telas
uvicorn app.main:app --reload
```

Usa SQLite por padrão; para PostgreSQL, ajuste `DATABASE_URL` no `.env`.

- Painel: http://localhost:8000 · Indicadores: `/indicadores` · Plano: `/plano` · Modo TV: `/tv` · Configurações: `/config`
- Documentação interativa da API: http://localhost:8000/docs

Na primeira execução: limite de 60 min, aging 12 h/24 h, layout G1–G7 (10,10,10,10,10,10,5), 6 linhas por lado, linhas de produção **Linha 1, Linha 2 e Linha 3** e os motivos de atraso padrão.

### Testes e qualidade

```bash
pytest                                                                   # SQLite em memória
TEST_DATABASE_URL=postgresql+psycopg://usuario:senha@localhost/teste pytest   # contra PostgreSQL real
ruff check .
```

A suíte inclui um teste que garante que **as migrações criam exatamente o esquema dos modelos** (e voltam atrás sem erro) — se alguém mudar um modelo sem gerar migração, o CI falha.

### Migrações

```bash
alembic revision --autogenerate -m "descrição da mudança"   # depois de alterar app/models.py
alembic upgrade head                                         # a aplicação também faz isso ao iniciar
```

## Segurança

- **Nenhuma senha no código.** O primeiro administrador vem de `ADMIN_EMAIL`/`ADMIN_PASSWORD` no `.env` e só é criado se o banco estiver vazio. Para criar ou redefinir depois, sem deixar a senha em arquivo nem no histórico do terminal:
  ```bash
  python -m scripts.create_admin admin@example.com --nome "Seu Nome"   # a senha é pedida de forma oculta
  ```
- Senhas guardadas com **bcrypt**; mínimo de 8 caracteres e lista de senhas óbvias recusadas.
- Sessão por **JWT** (HS256) com expiração (`JWT_EXPIRE_HOURS`). Sem `JWT_SECRET`, a API gera uma chave temporária e avisa no log.
- Login com mensagem única para e-mail ou senha errados — não revela quais e-mails existem.
- Rotas de operação (entrada, saída, ciente) são abertas para o chão de fábrica; configuração, colaboradores, matriz de responsáveis, plano de ação e exclusão exigem administrador.
- No navegador, o token fica em `sessionStorage` (some ao fechar a aba) e qualquer resposta 401 devolve para o login.
- Container sem root, banco fora da rede externa, `.env` fora do Git e da imagem.

## Alertas por e-mail

O agendador roda a cada `CHECK_EVERY_SECONDS` e, para cada peça em atraso, envia os níveis que já venceram e ainda não foram enviados. Peças pausadas não geram alerta; Aging que vence sem expediente é avisado na volta. Sem destinatário cadastrado, o nível **não** é marcado como enviado — sai no ciclo seguinte ao cadastro.

Sem `SMTP_HOST`, os e-mails vão só para o log, o que permite desenvolver sem servidor de e-mail. A matriz de responsáveis é cadastrada por linha e função, com e-mails separados por turno:

```json
[
  {"linha": "Linha 1", "funcao": "Monitor",    "turno1": "monitor.l1@example.com", "turno2": "monitor.l1.noite@example.com"},
  {"linha": "TODAS",   "funcao": "Auditor",    "turno1": "auditor@example.com",    "turno2": ""},
  {"linha": "",        "funcao": "Supervisor", "turno1": "supervisor@example.com", "turno2": "supervisor@example.com"}
]
```

> O agendador roda dentro do processo da aplicação, por isso o container usa **um** processo do uvicorn. Para escalar horizontalmente, o próximo passo é separar o agendador num serviço próprio (ou usar um lock no banco) para não duplicar e-mails.

## Endpoints

| Método | Rota | Descrição |
|---|---|---|
| GET | `/health` | Saúde e versão |
| GET | `/employees` | Lista colaboradores |
| POST | `/employees` | Cadastra colaborador 🔒 |
| DELETE | `/employees/{matricula}` | Remove colaborador (o histórico dele é preservado) 🔒 |
| POST | `/records/entries` | Registra entrada (Running ou Aging) |
| GET | `/records/active` | Peças na estação, com tempo, limite e status calculados agora |
| GET | `/records/history` | Peças que já saíram |
| POST | `/records/{id}/exit` | Registra saída (motivo obrigatório se em atraso) |
| POST | `/records/exit-by-pcba` | Saída pela leitura do QR do PCBA |
| POST | `/records/{id}/ack` | Ciente do alerta (matrícula de quem assumiu) |
| GET | `/settings` | Limite, aging, layout, linhas, motivos e linha de base |
| POST | `/auth/login` | Login de administrador (form OAuth2: `username` = e-mail) |
| GET | `/auth/me` | Administrador da sessão 🔒 |
| PUT | `/admin/threshold` | Altera o limite em minutos 🔒 |
| PUT | `/admin/reasons` | Substitui os motivos de atraso 🔒 |
| PUT | `/admin/baseline` | Linha de base do kaizen (minutos + fonte) 🔒 |
| GET / PUT | `/admin/responsibles` | Matriz de escalonamento 🔒 |
| POST | `/admin/alerts/run` | Executa a verificação de atrasos agora 🔒 |
| DELETE | `/admin/records/{id}` | Exclui um registro 🔒 |
| POST | `/admin/records/{id}/close-forgotten` | Encerra saída esquecida (ajuste, fora das médias) 🔒 |
| GET | `/kpi` | Indicadores do período (`inicio`, `fim`, `linha`, `turno`) |
| GET | `/quality` | Qualidade dos dados |
| GET | `/actions` | Plano de ação |
| POST / PUT / DELETE | `/actions[/{id}]` | Cria, edita e exclui ações (concluir exige resultado) 🔒 |

🔒 = exige `Authorization: Bearer <token>` (no `/docs`, use o botão **Authorize**).

## Histórico

Construído em 5 etapas — veja o [CHANGELOG](CHANGELOG.md):

1. Domínio, modelo de dados, API de entrada/saída e testes
2. Autenticação (JWT + bcrypt), alertas escalonados por e-mail, ciente e agendador
3. Interface web e Modo TV consumindo a API
4. Indicadores com leitura executiva e Plano de ação (PDCA)
5. PostgreSQL, migrações (Alembic), Docker Compose e CI no GitHub Actions

## Licença

[MIT](LICENSE). Inclui [Chart.js](https://www.chartjs.org) 4.4.7 (MIT) em `app/web/assets/vendor/`.
