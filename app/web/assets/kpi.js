// Indicadores: a API calcula tudo (app/domain/kpi.py); esta tela só filtra e desenha.
import { api, esc, fmtDate, fmtTime, initTheme, toastError } from "./api.js";
import { actionForm, currentAdmin } from "./actions-ui.js";

const $ = (s) => document.querySelector(s);
const charts = {};
let data = null;
let admin = null;

/* ---------- Formatação (espelha app/domain/kpi.py) ---------- */
const fmtMin = (m) => {
  if (m == null || Number.isNaN(m)) return "—";
  if (m < 1) return `${Math.round(m * 60)}s`;
  if (m < 60) return `${m < 10 ? m.toFixed(1).replace(".", ",") : Math.round(m)} min`;
  const h = Math.floor(Math.round(m) / 60);
  return `${h}h ${String(Math.round(m) % 60).padStart(2, "0")}min`;
};
const fmtPct = (p, d = 0) => (p == null ? "—" : `${(p * 100).toFixed(d).replace(".", ",")}%`);
const fmtInt = (n) => (n == null ? "—" : n.toLocaleString("pt-BR"));
const fmtH = (h) => `${Math.abs(h) >= 100 ? Math.round(h).toLocaleString("pt-BR") : h.toFixed(1).replace(".", ",")} h`;
const lineLabel = (l) => String(l || "").replace(/^LINHA/, "Linha");
const bold = (t) => esc(t).replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
const isoLocal = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();

/* ---------- Filtros ---------- */
function range() {
  const p = $("#f-periodo").value;
  const hoje = new Date();
  if (p === "custom") return { inicio: $("#f-ini").value, fim: $("#f-fim").value };
  if (p === "mes") return { inicio: isoLocal(new Date(hoje.getFullYear(), hoje.getMonth(), 1)), fim: isoLocal(hoje) };
  return { inicio: isoLocal(new Date(hoje.getTime() - (Number(p) - 1) * 864e5)), fim: isoLocal(hoje) };
}

async function load() {
  const r = range();
  if (!r.inicio || !r.fim) return;
  const q = new URLSearchParams({ inicio: r.inicio, fim: r.fim });
  if ($("#f-linha").value) q.set("linha", $("#f-linha").value);
  if ($("#f-turno").value) q.set("turno", $("#f-turno").value);
  try {
    data = await api(`/kpi?${q}`);
    render();
  } catch (e) {
    toastError(e);
  }
}

function fillLines(lines) {
  const sel = $("#f-linha");
  const cur = sel.value;
  sel.innerHTML = `<option value="">Todas as linhas</option>` + lines.map((l) => `<option value="${esc(l)}">${esc(lineLabel(l))}</option>`).join("");
  sel.value = lines.includes(cur) ? cur : "";
}

/* ---------- Render ---------- */
function delta(cur, prev, { goodWhen = "down", pp = false } = {}) {
  if (cur == null || prev == null || (!pp && !prev)) return `<div class="delta">sem base anterior</div>`;
  const diff = pp ? (cur - prev) * 100 : ((cur - prev) / prev) * 100;
  const txt = pp ? `${diff >= 0 ? "+" : ""}${diff.toFixed(1).replace(".", ",")} p.p.` : `${diff >= 0 ? "+" : ""}${diff.toFixed(0)}%`;
  const flat = Math.abs(diff) < 0.5;
  const arrow = flat ? "●" : diff > 0 ? "▲" : "▼";
  const cls = flat ? "" : (goodWhen === "down" ? diff < 0 : diff > 0) ? "good" : "bad";
  return `<div class="delta ${cls}" title="Comparação com o período imediatamente anterior, de mesma duração">${arrow} ${txt} vs anterior</div>`;
}

function render() {
  const d = data;
  const st = d.resumo, pv = d.anterior;
  fillLines(d.linhas_disponiveis);
  const per = `${fmtDate(d.periodo.inicio + "T12:00:00")} a ${fmtDate(d.periodo.fim + "T12:00:00")}`;
  $("#subtitle").textContent = `${per} · ${fmtInt(st.n)} carregamentos de running concluídos · limite ${d.limite_min} min`;

  $("#cards").innerHTML = `
    <div class="card kpi"><div class="kpi-label">Tempo médio</div><div class="kpi-value">${fmtMin(st.media)}</div><div class="kpi-sub">permanência por peça</div>${delta(st.media, pv.media)}</div>
    <div class="card kpi"><div class="kpi-label">Mediana · P90</div><div class="kpi-value">${fmtMin(st.p50)}</div><div class="kpi-sub">90% das peças em até ${fmtMin(st.p90)}</div>${delta(st.p90, pv.p90)}</div>
    <div class="card kpi k-ok"><div class="kpi-label">Dentro do limite</div><div class="kpi-value">${fmtPct(st.no_limite, 1)}</div><div class="kpi-sub">concluídos em até ${d.limite_min} min</div>${delta(st.no_limite, pv.no_limite, { goodWhen: "up", pp: true })}</div>
    <div class="card kpi k-crit"><div class="kpi-label">Alertas gerados</div><div class="kpi-value">${fmtInt(st.alertas)}</div><div class="kpi-sub">${fmtPct(st.n ? st.alertas / st.n : null, 1)} dos carregamentos (≥ limite + ${d.tolerancia_min} min)</div>${delta(st.n ? st.alertas / st.n : null, pv.n ? pv.alertas / pv.n : null, { pp: true })}</div>
    <div class="card kpi k-warn"><div class="kpi-label">Agora na estação</div><div class="kpi-value">${d.agora.running}</div><div class="kpi-sub">running · ${d.agora.atrasados} em atraso · ${d.agora.aging} em aging</div><div class="delta">tempo real</div></div>`;

  renderGain(d);
  renderInsights(d);

  const has = st.n > 0;
  $("#content").classList.toggle("hidden", !has);
  $("#empty").classList.toggle("hidden", has);
  if (!has) return;
  renderCharts(d);
  renderPareto(d.pareto);
  renderReaction(d.reacao);
  renderHeat(d);
  renderRank(d);
  renderTop(d.maiores);
}

function renderGain(d) {
  const g = d.ganho, el = $("#gain");
  if (!d.linha_de_base.minutos) {
    el.innerHTML = `<div class="gain empty"><div class="g-label">Ganho do kaizen</div>
      <div>Linha de base não definida. Sem ela, o ganho do kaizen não está no sistema — e um ganho que não está no sistema vira opinião na próxima revisão de orçamento.
      <span class="muted">Defina em Configurações → Regras.</span></div></div>`;
    return;
  }
  if (!g) { el.innerHTML = ""; return; }
  const pos = g.minutos >= 0;
  el.innerHTML = `<div class="gain ${pos ? "" : "bad"}">
    <div><div class="g-label">${pos ? "Ganho do kaizen no período" : "Regressão no período"}</div><div class="g-num">${pos ? "" : "+"}${fmtH(Math.abs(g.minutos) / 60)}</div>
      <div class="g-sub">de permanência ${pos ? "a menos" : "a mais"} que a linha de base</div></div>
    <div><div class="g-label">Tempo médio</div><div class="g-num">${fmtMin(g.linha_de_base)} → ${fmtMin(d.resumo.media)}</div><div class="g-sub">${pos ? "−" : "+"}${fmtPct(Math.abs(g.reducao))} vs linha de base</div></div>
    <div><div class="g-label">Por dia</div><div class="g-num">${fmtH(Math.abs(g.horas_por_dia))}</div><div class="g-sub">de estação ${pos ? "liberadas" : "a mais"}</div></div>
    <div><div class="g-label">Capacidade</div><div class="g-num">${pos ? `+${fmtInt(g.carregamentos_extras)}` : "—"}</div><div class="g-sub">carregamentos com a mesma ocupação</div></div>
  </div><div class="muted small" style="margin:-10px 0 16px">Linha de base: ${esc(g.fonte || `${g.linha_de_base} min`)}</div>`;
}

const TIPO_LABEL = {
  ganho: "Ganho do kaizen", aging: "Aging Test", dados: "Qualidade dos dados", sla: "Aderência ao limite",
  tendencia: "Tendência", linha: "Linha gargalo", turno: "Turnos", variabilidade: "Variabilidade",
  faixa: "Faixa horária", dias: "Dias acima do limite", motivo: "Motivo de atraso", reacao: "Reação aos alertas",
};
const ICO = { good: "✓", warn: "!", bad: "✕", "": "•" };
function renderInsights(d) {
  $("#ins-note").textContent = admin ? "+ Ação transforma o ponto em item do Plano de ação" : "gerada pelas mesmas regras a cada consulta";
  $("#insights").innerHTML = d.leitura.map((i, k) => {
    const act = admin && (i.nivel === "warn" || i.nivel === "bad") && i.tipo !== "agora"
      ? `<button class="btn btn-ghost btn-sm" data-k="${k}">+ Ação</button>` : "";
    return `<li class="${i.nivel || "neutral"}"><span class="ico" aria-hidden="true">${ICO[i.nivel] ?? "•"}</span><span class="txt">${bold(i.texto)}</span>${act}</li>`;
  }).join("");
}

/* ---------- Gráficos (Chart.js local; um eixo por gráfico) ---------- */
function theme() {
  return { s1: css("--s1"), s2: css("--s2"), warn: css("--warn"), crit: css("--crit"), grid: css("--border"), text: css("--text-2") };
}

function chart(id, cfg) {
  charts[id]?.destroy();
  const c = theme();
  Chart.defaults.color = c.text;
  Chart.defaults.borderColor = c.grid;
  Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;
  charts[id] = new Chart(document.getElementById(id), {
    ...cfg,
    options: {
      responsive: true, maintainAspectRatio: false, animation: false,
      interaction: { mode: "index", intersect: false },
      ...cfg.options,
      plugins: { legend: { display: false }, ...(cfg.options?.plugins || {}) },
    },
  });
}

/** Linha de referência (limite) desenhada sobre o gráfico. */
const limitLine = {
  id: "limitLine",
  afterDatasetsDraw(ch, _a, opts) {
    if (opts?.value == null) return;
    const horizontal = ch.options.indexAxis === "y";
    const scale = horizontal ? ch.scales.x : ch.scales.y;
    const px = scale.getPixelForValue(opts.value);
    const { ctx, chartArea: a } = ch;
    ctx.save();
    ctx.strokeStyle = opts.color; ctx.lineWidth = 1.5; ctx.setLineDash([5, 4]);
    ctx.beginPath();
    if (horizontal) { ctx.moveTo(px, a.top); ctx.lineTo(px, a.bottom); } else { ctx.moveTo(a.left, px); ctx.lineTo(a.right, px); }
    ctx.stroke();
    ctx.setLineDash([]); ctx.fillStyle = opts.color; ctx.font = "600 11px " + Chart.defaults.font.family;
    // Rótulo com fundo da superfície, no canto esquerdo (longe dos últimos pontos da série).
    if (!horizontal) { ctx.restore(); return; } // nos gráficos verticais a nota do card explica o tracejado
    const w = ctx.measureText(opts.label).width + 8;
    const [x, y] = horizontal ? [px + 4, a.top + 2] : [a.left + 6, px - 16];
    ctx.fillStyle = getComputedStyle(document.documentElement).getPropertyValue("--surface").trim();
    ctx.fillRect(x - 4, y, w, 14);
    ctx.fillStyle = opts.color;
    ctx.fillText(opts.label, x, y + 11);
    ctx.restore();
  },
};

function renderCharts(d) {
  const c = theme();
  const lim = { value: d.limite_min, color: c.crit, label: `limite ${d.limite_min} min` };
  const mins = { ticks: { callback: (v) => `${v} min` }, beginAtZero: true, grid: { color: c.grid } };
  const tipMin = (ctx) => `${ctx.dataset.label}: ${fmtMin(ctx.parsed.y ?? ctx.parsed.x)}`;
  const dias = d.diario.map((x) => x.dia.slice(8, 10) + "/" + x.dia.slice(5, 7));

  chart("ch-daily", {
    type: "line",
    data: { labels: dias, datasets: [
      { label: "Tempo médio", data: d.diario.map((x) => x.media), borderColor: c.s1, backgroundColor: c.s1, borderWidth: 2, pointRadius: 3, pointHoverRadius: 5, spanGaps: true, tension: 0.25 },
      { label: "P90", data: d.diario.map((x) => x.p90), borderColor: c.s2, backgroundColor: c.s2, borderWidth: 2, pointRadius: 3, pointHoverRadius: 5, spanGaps: true, tension: 0.25, borderDash: [] },
    ] },
    options: {
      scales: { y: { ...mins, suggestedMax: d.limite_min * 1.2 }, x: { grid: { display: false } } },
      plugins: {
        legend: { display: true, position: "top", align: "end", labels: { boxWidth: 10, boxHeight: 10 } },
        tooltip: { callbacks: { label: tipMin, afterBody: (it) => `Carregamentos: ${d.diario[it[0].dataIndex].n}` } },
        limitLine: lim,
      },
    },
    plugins: [limitLine],
  });

  chart("ch-volume", {
    type: "bar",
    data: { labels: dias, datasets: [{ label: "Carregamentos", data: d.diario.map((x) => x.n), backgroundColor: c.s1, borderRadius: 3, maxBarThickness: 22 }] },
    options: { scales: { y: { beginAtZero: true, ticks: { precision: 0, maxTicksLimit: 3 } }, x: { grid: { display: false }, ticks: { display: false } } },
      plugins: { tooltip: { callbacks: { label: (x) => `${x.parsed.y} carregamentos` } } } },
  });

  chart("ch-linha", {
    type: "bar",
    data: { labels: d.por_linha.map((x) => lineLabel(x.chave)), datasets: [{ label: "Tempo médio", data: d.por_linha.map((x) => x.media), backgroundColor: c.s1, borderRadius: 4, maxBarThickness: 26 }] },
    options: { indexAxis: "y", scales: { x: { ...mins, suggestedMax: d.limite_min * 1.2 }, y: { grid: { display: false } } },
      plugins: { tooltip: { callbacks: { label: (x) => `Média ${fmtMin(x.parsed.x)} · ${d.por_linha[x.dataIndex].n} carregamentos` } }, limitLine: lim } },
    plugins: [limitLine],
  });

  chart("ch-turno", {
    type: "bar",
    data: { labels: d.por_turno.map((x) => `${x.chave} (${x.n})`), datasets: [
      { label: "Tempo médio", data: d.por_turno.map((x) => x.media), backgroundColor: c.s1, borderRadius: 4, maxBarThickness: 40 },
      { label: "P90", data: d.por_turno.map((x) => x.p90), backgroundColor: c.s2, borderRadius: 4, maxBarThickness: 40 },
    ] },
    options: { scales: { y: { ...mins, suggestedMax: d.limite_min * 1.2 }, x: { grid: { display: false } } },
      plugins: { legend: { display: true, position: "top", align: "end", labels: { boxWidth: 10, boxHeight: 10 } }, tooltip: { callbacks: { label: tipMin } }, limitLine: lim } },
    plugins: [limitLine],
  });

  const color = { ok: c.s1, warn: c.warn, crit: c.crit };
  chart("ch-dist", {
    type: "bar",
    data: { labels: d.distribuicao.map((b) => (b.ate == null ? `≥ ${b.de}` : `${b.de}–${b.ate}`)),
      datasets: [{ label: "Peças", data: d.distribuicao.map((b) => b.n), backgroundColor: d.distribuicao.map((b) => color[b.classe]), borderRadius: 3, categoryPercentage: 0.94, barPercentage: 0.94 }] },
    options: { scales: { y: { beginAtZero: true, ticks: { precision: 0 } }, x: { grid: { display: false }, title: { display: true, text: "minutos" } } },
      plugins: { tooltip: { callbacks: { title: (it) => `${it[0].label} min`, label: (x) => `${x.parsed.y} peças` } } } },
  });

  chart("ch-faixa", {
    type: "bar",
    data: { labels: d.por_faixa.map((x) => x.rotulo.slice(0, 5)), datasets: [{ label: "Tempo médio", data: d.por_faixa.map((x) => x.media), backgroundColor: c.s1, borderRadius: 3 }] },
    options: { scales: { y: { ...mins, suggestedMax: d.limite_min * 1.2 }, x: { grid: { display: false } } },
      plugins: { tooltip: { callbacks: { title: (it) => d.por_faixa[it[0].dataIndex].rotulo, label: (x) => `Média ${fmtMin(x.parsed.y)} · ${d.por_faixa[x.dataIndex].n} entradas` } }, limitLine: lim } },
    plugins: [limitLine],
  });
}

function renderPareto(p) {
  if (!p.total) { $("#pareto").innerHTML = `<div class="muted">Nenhuma peça chegou ao limite no período. ✓</div>`; return; }
  const max = p.itens[0].n;
  const cut = p.itens.findIndex((x) => x.acumulado >= 0.8);
  $("#pareto").innerHTML = `<div class="pareto">${p.itens.map((x, i) => `
    <div class="p-row" title="${esc(x.motivo)}: ${x.n} peças (${fmtPct(x.pct, 1)}) · acumulado ${fmtPct(x.acumulado, 1)}">
      <span class="p-name">${esc(x.motivo)}</span>
      <span class="p-bar ${x.motivo.startsWith("Não informado") ? "muted" : ""}"><i style="width:${(x.n / max) * 100}%"></i></span>
      <span class="p-val"><b>${x.n}</b> · ${fmtPct(x.acumulado)}</span>
    </div>`).join("")}</div>
    <div class="p-cut">${cut >= 0 ? `${cut + 1} motivo(s) explicam ${fmtPct(p.itens[cut].acumulado)} dos ${p.total} atrasos — é onde a ação rende mais.` : ""} Valor à direita = peças · % acumulado.</div>`;
}

function renderReaction(r) {
  const card = (l, v, s) => `<div class="mini"><div class="kpi-label">${l}</div><div class="v">${v}</div><div class="kpi-sub">${s}</div></div>`;
  $("#react-cards").innerHTML =
    card("Alertas", fmtInt(r.alertas), "chegaram ao nível 1") +
    card("Com ciente", fmtPct(r.taxa), `${r.com_ciente} de ${r.alertas}`) +
    card("Reação média", fmtMin(r.media), `mediana ${fmtMin(r.mediana)}`) +
    card("Em até 5 min", fmtPct(r.ate_5min), "antes do nível 2");
  $("#react-rows").innerHTML = r.por_linha.length ? r.por_linha.map((x) => `<tr>
    <td>${esc(lineLabel(x.linha))}</td><td class="num">${x.alertas}</td><td class="num">${fmtPct(x.taxa)}</td>
    <td class="num">${fmtMin(x.media)}</td><td class="num">${fmtPct(x.ate_5min)}</td></tr>`).join("")
    : `<tr><td colspan="5" class="empty">Nenhum alerta emitido no período.</td></tr>`;
}

function heatCls(avg, lim) { return avg == null ? "h-na" : avg > lim ? "h-crit" : avg > lim * 0.8 ? "h-warn" : "h-ok"; }
function renderHeat(d) {
  const turnos = ["Turno 1", "Turno 2", "Fora de turno"].filter((t) => d.linha_turno.some((l) => l.turnos[t].n));
  $("#heat-head").innerHTML = `<tr><th>Linha</th>${turnos.map((t) => `<th>${t}</th>`).join("")}<th>Geral</th></tr>`;
  const cell = (s) => (s.n ? `<td class="cell ${heatCls(s.media, d.limite_min)}">${fmtMin(s.media)}<small>${s.n} peças · ${fmtPct(s.no_limite)} no limite</small></td>` : `<td class="cell h-na">—</td>`);
  $("#heat-rows").innerHTML = d.linha_turno.map((l) => `<tr><td>${esc(lineLabel(l.linha))}</td>${turnos.map((t) => cell(l.turnos[t])).join("")}${cell(l.geral)}</tr>`).join("");
}

function renderRank(d) {
  $("#rank-rows").innerHTML = d.por_linha.map((l) => {
    const st = l.media > d.limite_min ? `<span class="pill crit">Crítico</span>` : l.p90 > d.limite_min ? `<span class="pill warn">Atenção</span>` : `<span class="pill ok">OK</span>`;
    const cor = l.no_limite >= 0.95 ? "var(--ok)" : l.no_limite >= 0.85 ? "var(--warn)" : "var(--crit)";
    return `<tr><td>${esc(lineLabel(l.chave))}</td><td class="num">${l.n}</td><td class="num">${fmtMin(l.media)}</td><td class="num">${fmtMin(l.p90)}</td>
      <td><span class="meter"><span class="track"><i style="width:${Math.round(l.no_limite * 100)}%;background:${cor}"></i></span><span class="mono">${fmtPct(l.no_limite)}</span></span></td>
      <td class="num">${l.alertas}</td><td>${st}</td></tr>`;
  }).join("");
}

function renderTop(list) {
  $("#top-rows").innerHTML = list.map((x) => `<tr><td class="mono">${esc(x.pcba)}</td><td>${esc(lineLabel(x.linha))}</td><td>${esc(x.turno)}</td>
    <td class="mono muted">${fmtDate(x.entrada_em)} ${fmtTime(x.entrada_em)}</td>
    <td class="right"><span class="chip ${x.minutos > data.limite_min ? "crit" : "ok"}">${fmtMin(x.minutos)}</span></td></tr>`).join("");
}

/* ---------- Eventos ---------- */
async function boot() {
  initTheme();
  admin = await currentAdmin();
  $("#f-periodo").addEventListener("change", (e) => {
    const custom = e.target.value === "custom";
    $("#w-custom").classList.toggle("hidden", !custom);
    if (custom && !$("#f-ini").value) {
      $("#f-ini").value = isoLocal(new Date(Date.now() - 29 * 864e5));
      $("#f-fim").value = isoLocal(new Date());
    }
    load();
  });
  ["#f-ini", "#f-fim", "#f-linha", "#f-turno"].forEach((s) => $(s).addEventListener("change", load));
  $("#insights").addEventListener("click", async (e) => {
    const b = e.target.closest("[data-k]");
    if (!b || !data) return;
    const i = data.leitura[Number(b.dataset.k)];
    const saved = await actionForm({
      origem: `Indicadores · ${TIPO_LABEL[i.tipo] || i.tipo} · ${fmtDate(data.periodo.inicio + "T12:00:00")} a ${fmtDate(data.periodo.fim + "T12:00:00")}`,
      problema: i.texto.replace(/\*\*/g, ""),
      linha: data.filtros.linha || "",
    }, data.linhas_disponiveis);
    if (saved) b.replaceWith(Object.assign(document.createElement("a"), { href: "/plano", className: "btn btn-ghost btn-sm", textContent: "Ver no plano →" }));
  });
  // Troca de tema: redesenha os gráficos com as cores do tema novo.
  new MutationObserver(() => data && data.resumo.n && renderCharts(data)).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
  await load();
  setInterval(load, 5 * 60 * 1000);
}

boot();
