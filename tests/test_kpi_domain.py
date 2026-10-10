"""Regras dos indicadores (funções puras)."""

from datetime import UTC, date, datetime

import pytest

from app.domain import kpi as K
from tests.conftest import SP, local


def s(minutos, linha="LINHA 1", turno="Turno 1", motivo="", alertado=False, reacao=None, entrada=None, faixa=0):
    return K.Sample(entrada=entrada or datetime(2026, 10, 7, 13, tzinfo=UTC), minutos=minutos, linha=linha,
                    turno=turno, faixa=faixa, motivo=motivo, alertado=alertado, reacao_min=reacao)


def test_quantil_interpolado():
    assert K.quantile([10, 20, 30, 40], 0.5) == 25
    assert K.quantile([10, 20, 30, 40, 50, 60, 70, 80, 90, 100], 0.9) == pytest.approx(91)
    assert K.quantile([], 0.5) is None


def test_stats_limite_e_alerta():
    st = K.stats([30, 60, 61, 64, 65, 120], limite=60)
    assert st.n == 6 and st.media == pytest.approx(66.67, abs=0.01)
    assert st.no_limite == pytest.approx(2 / 6)     # ≤ 60
    assert st.acima == 4                            # > 60
    assert st.alertas == 2                          # ≥ 65 (limite + 5)


def test_stats_vazio():
    assert K.stats([], 60) == K.Stats()


def test_faixa_horaria_ancorada_no_turno_1():
    assert K.faixa_of(local(2026, 10, 7, 7, 30)) == 0
    assert K.faixa_of(local(2026, 10, 7, 8, 29)) == 0
    assert K.faixa_of(local(2026, 10, 7, 7, 29)) == 23
    assert K.faixa_label(0) == "07:30–08:30" and K.faixa_label(23) == "06:30–07:30"


def test_distribuicao_classifica_faixas():
    bins = K.distribution([s(5), s(59), s(62), s(70), s(500)], limite=60)
    assert bins[0].de == 0 and bins[0].n == 1
    assert bins[-1].ate is None and bins[-1].n == 1            # 500 cai na última faixa (≥ 120)
    assert next(b for b in bins if b.de == 60).classe == "warn"  # passou do limite
    assert next(b for b in bins if b.de == 75).classe == "crit"  # chegou ao alerta
    assert sum(b.n for b in bins) == 5


def test_pareto_ordena_e_acumula():
    total, itens = K.pareto([s(70, motivo="Troca de turno"), s(80, motivo="Troca de turno"),
                             s(90, motivo="Falha no aparelho"), s(61), s(30, motivo="ignorado")], limite=60)
    assert total == 4
    assert [i.motivo for i in itens] == ["Troca de turno", "Falha no aparelho", K.MOTIVO_NAO_INFORMADO]
    assert itens[0].pct == 0.5 and itens[-1].acumulado == 1.0


def test_reacao_aos_alertas():
    r = K.reaction([s(70, alertado=True, reacao=3), s(80, alertado=True, reacao=9), s(90, alertado=True), s(20)])
    assert (r.alertas, r.com_ciente) == (3, 2)
    assert r.taxa == pytest.approx(2 / 3) and r.media == 6 and r.ate_5min == 0.5


def test_ganho_contra_linha_de_base():
    g = K.gain([s(50), s(60), s(70)], baseline=95, fonte="cronoanálise", dias=3)
    assert g.minutos == 3 * 95 - 180 and g.reducao == pytest.approx((95 - 60) / 95)
    assert g.carregamentos_extras == 1  # 105 min economizados / 60 min de média
    assert K.gain([s(50)], None, "", 1) is None


def test_diario_preenche_dias_sem_operacao():
    d = K.daily([s(40, entrada=local(2026, 10, 7, 10))], date(2026, 10, 6), date(2026, 10, 8), SP, 60)
    assert [x[0].day for x in d] == [6, 7, 8] and [x[1].n for x in d] == [0, 1, 0]


@pytest.mark.parametrize("m,txt", [(0.5, "30s"), (7.25, "7,2 min"), (45, "45 min"), (125, "2h 05min"), (None, "—")])
def test_fmt_min(m, txt):
    assert K.fmt_min(m) == txt


def ctx(**kw):
    base = dict(limite=60, st=K.Stats(), anterior=K.Stats(), por_linha={}, por_turno={}, por_faixa={}, dias=[],
                pareto_total=0, pareto_itens=[], reacao=K.Reaction(), ganho=None, tem_linha_de_base=False,
                excluidos=0, aging_concluidos=0, aging_alem=0, aging_ativos=0, aging_vencidos=0, ativos=0, atrasados_agora=0)
    return K.InsightContext(**{**base, **kw})


def test_leitura_sem_linha_de_base_e_sem_dados():
    out = K.insights(ctx())
    tipos = [i.tipo for i in out]
    assert tipos == ["ganho", "sla", "agora"]
    assert out[0].nivel == "warn" and "não definida" in out[0].texto


def test_leitura_aponta_linha_gargalo_turno_e_motivo():
    amostra = [s(40, "LINHA 1", "Turno 1")] * 10 + [s(90, "LINHA 2", "Turno 2", motivo="Troca de turno")] * 10
    st = K.stats([x.minutos for x in amostra], 60)
    total, itens = K.pareto(amostra, 60)
    out = K.insights(ctx(
        st=st, anterior=K.stats([50] * 10, 60),
        por_linha=K.group(amostra, lambda x: x.linha, 60), por_turno=K.group(amostra, lambda x: x.turno, 60),
        pareto_total=total, pareto_itens=itens, tem_linha_de_base=True,
    ))
    by = {i.tipo: i for i in out}
    assert by["sla"].nivel == "bad" and "**50,0%**" in by["sla"].texto
    assert by["tendencia"].nivel == "bad" and "subiu 30%" in by["tendencia"].texto
    assert "**Linha 2** tem o maior tempo médio" in by["linha"].texto and by["linha"].nivel == "bad"
    assert "**Turno 2** opera" in by["turno"].texto
    assert "**Troca de turno**" in by["motivo"].texto
    assert "ganho" not in by  # tem linha de base, mas sem ganho calculado


def test_leitura_regressao_do_ganho():
    g = K.gain([s(100)] * 4, baseline=80, fonte="x", dias=1)
    out = K.insights(ctx(st=K.stats([100] * 4, 60), ganho=g, tem_linha_de_base=True))
    assert out[0].tipo == "ganho" and out[0].nivel == "bad" and "regressão" in out[0].texto
