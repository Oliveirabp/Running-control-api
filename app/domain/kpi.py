"""
Indicadores (KPI) do running test — funções puras, sem banco e sem HTTP.

Na versão Apps Script esses cálculos rodavam no navegador. Aqui ficam no backend,
cobertos por testes, e a tela só desenha o que recebe.

Convenções (iguais às do sistema original):
- Só entram carregamentos de RUNNING concluídos. Aging tem prazo próprio e visão separada.
- Registro com mais de 24 h (saída esquecida) ou encerrado por ajuste fica FORA das médias,
  mas é contado — cada um é uma falha de registro.
- "No limite" = duração ≤ limite. "Alerta" = duração ≥ limite + tolerância (nível 1).
"""

import math
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

TOLERANCIA_MIN = 5          # o nível 1 do escalonamento sai no limite + 5 min
LIMITE_ABERTO_H = 24        # acima disso é saída esquecida
MOTIVO_NAO_INFORMADO = "Não informado"
ANCORA_FAIXA_MIN = 7 * 60 + 30  # faixas horárias começam no início do Turno 1 (07:30)


@dataclass(frozen=True)
class Sample:
    """Um carregamento de running concluído."""

    entrada: datetime
    minutos: float
    linha: str
    turno: str
    faixa: int
    pcba: str = ""
    nome: str = ""
    motivo: str = ""
    reacao_min: float | None = None   # do 1º alerta ao ciente
    alertado: bool = False


@dataclass(frozen=True)
class Stats:
    n: int = 0
    media: float | None = None
    p50: float | None = None
    p90: float | None = None
    no_limite: float | None = None   # fração 0–1
    acima: int = 0
    alertas: int = 0


# ---------------------------------------------------------------- estatística

def quantile(sorted_vals: list[float], q: float) -> float | None:
    """Quantil com interpolação linear (o mesmo método do numpy por padrão)."""
    if not sorted_vals:
        return None
    pos = (len(sorted_vals) - 1) * q
    lo, hi = math.floor(pos), math.ceil(pos)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (pos - lo)


def stats(values: list[float], limite: float, tol: float = TOLERANCIA_MIN) -> Stats:
    s = sorted(values)
    if not s:
        return Stats()
    return Stats(
        n=len(s),
        media=sum(s) / len(s),
        p50=quantile(s, 0.5),
        p90=quantile(s, 0.9),
        no_limite=sum(1 for v in s if v <= limite) / len(s),
        acima=sum(1 for v in s if v > limite),
        alertas=sum(1 for v in s if v >= limite + tol),
    )


def group(samples: list[Sample], key, limite: float) -> dict:
    buckets: dict = defaultdict(list)
    for x in samples:
        buckets[key(x)].append(x.minutos)
    return {k: stats(v, limite) for k, v in buckets.items()}


# ---------------------------------------------------------------- recortes

def faixa_of(local: datetime) -> int:
    """Índice 0–23 da faixa horária de 1 h, ancorada em 07:30."""
    m = local.hour * 60 + local.minute
    return ((m - ANCORA_FAIXA_MIN) % 1440) // 60


def faixa_label(i: int) -> str:
    ini = (ANCORA_FAIXA_MIN + i * 60) % 1440
    fim = (ini + 60) % 1440
    return f"{ini // 60:02d}:{ini % 60:02d}–{fim // 60:02d}:{fim % 60:02d}"


def daily(samples: list[Sample], inicio: date, fim: date, tz: ZoneInfo, limite: float) -> list[tuple[date, Stats]]:
    by_day: dict = defaultdict(list)
    for x in samples:
        by_day[x.entrada.astimezone(tz).date()].append(x.minutos)
    out, d = [], inicio
    while d <= fim and len(out) < 400:
        out.append((d, stats(by_day.get(d, []), limite)))
        d += timedelta(days=1)
    return out


@dataclass(frozen=True)
class Bin:
    de: int
    ate: int | None   # None = sem teto
    n: int
    classe: str       # ok | warn (acima do limite) | crit (chegou ao alerta)


def distribution(samples: list[Sample], limite: float, tol: float = TOLERANCIA_MIN, passo: int = 15) -> list[Bin]:
    """Faixas de 15 min até 2× o limite; a última junta o restante."""
    topo = max(passo, math.ceil(2 * limite / passo) * passo)
    edges = list(range(0, topo, passo))
    counts = Counter()
    for x in samples:
        i = min(int(x.minutos // passo), len(edges))
        counts[i] += 1
    bins = []
    for i, a in enumerate(edges + [topo]):
        b = a + passo if i < len(edges) else None
        classe = "crit" if a >= limite + tol else "warn" if a >= limite else "ok"
        bins.append(Bin(a, b, counts[i], classe))
    return bins


@dataclass(frozen=True)
class ParetoItem:
    motivo: str
    n: int
    pct: float
    acumulado: float


def pareto(samples: list[Sample], limite: float) -> tuple[int, list[ParetoItem]]:
    """Motivos das peças que chegaram ao limite, do mais para o menos frequente."""
    atrasadas = [x for x in samples if x.minutos >= limite]
    c = Counter((x.motivo or MOTIVO_NAO_INFORMADO) for x in atrasadas)
    total, acc, out = len(atrasadas), 0, []
    for motivo, n in sorted(c.items(), key=lambda kv: (-kv[1], kv[0])):
        acc += n
        out.append(ParetoItem(motivo, n, n / total, acc / total))
    return total, out


@dataclass(frozen=True)
class Reaction:
    alertas: int = 0
    com_ciente: int = 0
    taxa: float | None = None
    media: float | None = None
    mediana: float | None = None
    ate_5min: float | None = None


def reaction(samples: list[Sample]) -> Reaction:
    alertadas = [x for x in samples if x.alertado]
    r = sorted(x.reacao_min for x in alertadas if x.reacao_min is not None)
    if not alertadas:
        return Reaction()
    return Reaction(
        alertas=len(alertadas),
        com_ciente=len(r),
        taxa=len(r) / len(alertadas),
        media=sum(r) / len(r) if r else None,
        mediana=quantile(r, 0.5),
        ate_5min=sum(1 for v in r if v <= 5) / len(r) if r else None,
    )


@dataclass(frozen=True)
class Gain:
    linha_de_base: float
    fonte: str
    minutos: float           # positivo = permanência economizada
    horas_por_dia: float
    reducao: float           # fração vs linha de base
    carregamentos_extras: int


def gain(samples: list[Sample], baseline: float | None, fonte: str, dias: int) -> Gain | None:
    """Ganho do kaizen: minutos de estação liberados frente à linha de base congelada."""
    if not baseline or not samples:
        return None
    soma = sum(x.minutos for x in samples)
    media = soma / len(samples)
    minutos = len(samples) * baseline - soma
    return Gain(
        linha_de_base=baseline, fonte=fonte, minutos=minutos,
        horas_por_dia=minutos / 60 / max(1, dias),
        reducao=(baseline - media) / baseline,
        carregamentos_extras=max(0, math.floor(minutos / media)) if media > 0 else 0,
    )


# ---------------------------------------------------------------- leitura executiva

def fmt_min(m: float | None) -> str:
    if m is None or (isinstance(m, float) and math.isnan(m)):
        return "—"
    if m < 1:
        return f"{round(m * 60)}s"
    if m < 60:
        return (f"{m:.1f}".replace(".", ",") if m < 10 else f"{round(m)}") + " min"
    h, r = divmod(round(m), 60)
    return f"{h}h {r:02d}min"


def fmt_pct(p: float | None, dec: int = 0) -> str:
    return "—" if p is None else f"{p * 100:.{dec}f}".replace(".", ",") + "%"


def fmt_horas(h: float) -> str:
    return (f"{round(h):,}".replace(",", ".") if abs(h) >= 100 else f"{h:.1f}".replace(".", ",")) + " h"


@dataclass(frozen=True)
class Insight:
    nivel: str   # good | warn | bad | "" (neutro)
    # tipo: ganho | aging | dados | sla | tendencia | linha | turno | variabilidade | faixa | dias | motivo | reacao | agora
    tipo: str
    texto: str   # **negrito** marcado com asteriscos duplos


@dataclass
class InsightContext:
    limite: float
    st: Stats
    anterior: Stats
    por_linha: dict
    por_turno: dict
    por_faixa: dict
    dias: list
    pareto_total: int
    pareto_itens: list
    reacao: Reaction
    ganho: Gain | None
    tem_linha_de_base: bool
    excluidos: int
    aging_concluidos: int
    aging_alem: int
    aging_ativos: int
    aging_vencidos: int
    ativos: int
    atrasados_agora: int
    extra: dict = field(default_factory=dict)


def insights(c: InsightContext, tol: float = TOLERANCIA_MIN) -> list[Insight]:
    """Uma leitura em frases do que os números dizem — gerada pelas mesmas regras sempre."""
    out: list[Insight] = []
    st, limite = c.st, c.limite

    if c.ganho:
        g = c.ganho
        if g.minutos >= 0:
            out.append(Insight("good", "ganho",
                f"Ganho do kaizen: **{fmt_horas(g.minutos / 60)}** de permanência a menos que a linha de base "
                f"({fmt_min(g.linha_de_base)} → {fmt_min(st.media)}, −{fmt_pct(g.reducao)}). Isso equivale a "
                f"**{g.carregamentos_extras} carregamentos** a mais com a mesma ocupação. "
                "Um ganho que não está no sistema vira opinião — este está."))
        else:
            out.append(Insight("bad", "ganho",
                f"Alerta de regressão: o tempo médio ({fmt_min(st.media)}) está **acima da linha de base** do kaizen "
                f"({fmt_min(g.linha_de_base)}). O ganho está se perdendo — {fmt_horas(-g.minutos / 60)} a mais no período."))
    elif not c.tem_linha_de_base:
        out.append(Insight("warn", "ganho",
            "Linha de base do kaizen não definida: o ganho ainda não é mensurável no sistema. "
            "Um ganho que não está no sistema vira opinião na próxima revisão de orçamento."))

    if c.aging_concluidos or c.aging_ativos:
        share = c.aging_concluidos / (st.n + c.aging_concluidos) if st.n + c.aging_concluidos else 0
        txt = f"Aging Test (fora das métricas de running): **{c.aging_concluidos}** concluído(s) no período"
        if c.aging_alem:
            txt += f", **{c.aging_alem}** além da duração planejada"
        txt += f"; **{c.aging_ativos}** na estação agora"
        if c.aging_vencidos:
            txt += f", **{c.aging_vencidos}** já vencido(s)"
        txt += "."
        if share >= 0.2:
            txt += f" Aging representa {fmt_pct(share)} das entradas — vale confirmar se a classificação está correta."
        out.append(Insight("warn" if c.aging_vencidos or c.aging_alem else "", "aging", txt))

    if c.excluidos:
        out.append(Insight("warn", "dados",
            f"**{c.excluidos}** registro(s) com mais de {LIMITE_ABERTO_H}h (saídas esquecidas) ficaram fora das médias. "
            "Cada um é uma falha de registro — veja Qualidade dos dados no Plano de ação."))

    if not st.n:
        out.append(Insight("", "sla", "Nenhum carregamento de running concluído no período e filtros escolhidos."))
        out.append(_agora(c))
        return out

    min_n = max(3, round(st.n * 0.05))

    sla_nivel = "good" if st.no_limite >= 0.95 else "warn" if st.no_limite >= 0.85 else "bad"
    txt = f"**{fmt_pct(st.no_limite, 1)}** dos carregamentos ficaram dentro do limite de {limite:g} min. "
    txt += (f"**{st.acima}** passaram do limite e **{st.alertas}** chegaram ao alerta (≥ {limite + tol:g} min)."
            if st.acima else "Nenhuma peça passou do limite.")
    out.append(Insight(sla_nivel, "sla", txt))

    if c.anterior.n and c.anterior.media:
        d = (st.media - c.anterior.media) / c.anterior.media * 100
        par = f"({fmt_min(c.anterior.media)} → {fmt_min(st.media)})"
        if abs(d) < 3:
            out.append(Insight("", "tendencia", f"Tempo médio **estável** em relação ao período anterior {par}."))
        else:
            out.append(Insight("bad" if d > 0 else "good", "tendencia",
                f"Tempo médio **{'subiu' if d > 0 else 'caiu'} {abs(d):.0f}%** em relação ao período anterior {par}."))

    linhas = sorted(((k, s) for k, s in c.por_linha.items() if s.n >= min_n), key=lambda kv: -kv[1].media)
    if len(linhas) >= 2:
        (pk, pior), (mk, melhor) = linhas[0], linhas[-1]
        acima = (pior.media - st.media) / st.media * 100
        rel = f"{acima:.0f}% acima" if acima >= 0 else f"{abs(acima):.0f}% abaixo"
        txt = f"**{_nome_linha(pk)}** tem o maior tempo médio ({fmt_min(pior.media)}, {rel} da média geral)"
        txt += f" e concentra **{fmt_pct(pior.acima / st.acima)}** das peças acima do limite." if st.acima else "."
        txt += f" Referência: **{_nome_linha(mk)}** com {fmt_min(melhor.media)}."
        out.append(Insight("bad" if pior.media > limite else "warn" if acima > 15 else "", "linha", txt))

    t1, t2 = c.por_turno.get("Turno 1"), c.por_turno.get("Turno 2")
    if t1 and t2 and t1.n >= 3 and t2.n >= 3:
        diff = t2.media - t1.media
        pct = abs(diff) / min(t1.media, t2.media) * 100
        if pct < 5:
            txt = f"Turnos **equilibrados**: Turno 1 com {fmt_min(t1.media)} e Turno 2 com {fmt_min(t2.media)}."
        else:
            lento, rapido = ("Turno 2", "Turno 1") if diff > 0 else ("Turno 1", "Turno 2")
            txt = (f"**{lento}** opera {fmt_min(abs(diff))} mais lento que o {rapido} ({pct:.0f}%): "
                   f"{fmt_min(t1.media)} no Turno 1 vs {fmt_min(t2.media)} no Turno 2.")
        out.append(Insight("warn" if pct > 20 else "", "turno", txt))
    fora = c.por_turno.get("Fora de turno")
    if fora and fora.n:
        out.append(Insight("warn", "turno",
            f"**{fora.n}** carregamentos ({fmt_pct(fora.n / st.n, 1)}) tiveram entrada fora do horário dos turnos, "
            f"com média de {fmt_min(fora.media)}."))

    if st.p90 is not None and st.p50:
        ratio = st.p90 / st.p50
        txt = (f"Variabilidade: metade das peças sai em até **{fmt_min(st.p50)}**, mas 1 em cada 10 fica mais de "
               f"**{fmt_min(st.p90)}**")
        if ratio > 2:
            txt += " — a média esconde uma cauda longa; o ganho está em atacar os casos extremos."
        elif st.p90 > limite:
            txt += " — a dispersão é baixa, mas o patamar inteiro está alto: o problema é do processo, não de casos isolados."
        else:
            txt += " — processo consistente e dentro do limite."
        out.append(Insight("bad" if st.p90 > limite else "warn" if ratio > 2 else "good", "variabilidade", txt))

    faixas = sorted(((k, s) for k, s in c.por_faixa.items() if s.n >= min_n), key=lambda kv: -kv[1].media)
    if len(faixas) >= 3:
        k, s = faixas[0]
        out.append(Insight("bad" if s.media > limite else "", "faixa",
            f"Faixa horária mais lenta: **{faixa_label(k)}**, com média de {fmt_min(s.media)} em {s.n} carregamentos."))

    com_dado = [s for _, s in c.dias if s.n]
    if len(com_dado) >= 3:
        acima_dias = sum(1 for s in com_dado if s.media > limite)
        out.append(Insight("warn" if acima_dias else "good", "dias",
            f"**{acima_dias} de {len(com_dado)}** dias com operação fecharam com tempo médio acima do limite."))

    top = next((p for p in c.pareto_itens if p.motivo != MOTIVO_NAO_INFORMADO), None)
    if st.acima and top:
        out.append(Insight("warn", "motivo",
            f"Principal motivo de atraso: **{top.motivo}** ({fmt_pct(top.pct)} das peças em atraso). "
            "É por aqui que a próxima ação do kaizen deve começar."))

    r = c.reacao
    if r.alertas >= 3:
        txt = f"**{fmt_pct(r.taxa)}** dos alertas tiveram ciente"
        if r.media is not None:
            txt += f", com reação média de **{fmt_min(r.media)}**"
        txt += "."
        if r.taxa < 0.6:
            txt += " Alerta sem confirmação é ruído — vale revisar quem está recebendo."
        out.append(Insight("good" if r.taxa >= 0.9 else "warn" if r.taxa >= 0.6 else "bad", "reacao", txt))

    out.append(_agora(c))
    return out


def _agora(c: InsightContext) -> Insight:
    return Insight("bad" if c.atrasados_agora else "good", "agora",
        f"Neste momento: **{c.ativos}** peça(s) de running na estação, **{c.atrasados_agora}** acima do limite.")


def _nome_linha(v: str) -> str:
    return v.replace("LINHA", "Linha") if v.startswith("LINHA") else v
