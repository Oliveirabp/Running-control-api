// Modo TV: mapa de ocupação por linha, indicadores, diagnóstico e fila de atenção.
import { api, esc, fmtClock, fmtShort, fmtTime, live } from "./api.js";

const $ = (s) => document.querySelector(s);
const REFRESH_MS = 15000;
const ROTATE_MS = 20000;
const QUEUE_MAX = 8;

const state = { settings: null, active: [], fetchedAt: 0, line: null, rotate: false, rotateTimer: null };

/* ---------- Dados ---------- */

async function refresh() {
  try {
    const [settings, active] = await Promise.all([api("/settings"), api("/records/active")]);
    state.settings = settings;
    state.active = active;
    state.fetchedAt = Date.now();
    if (!state.line || !settings.lines.includes(state.line)) {
      const fromUrl = new URLSearchParams(location.search).get("linha");
      state.line = settings.lines.find((l) => l === String(fromUrl || "").toUpperCase()) || settings.lines[0];
    }
    render();
  } catch {
    /* mantém a última tela; o indicador "atualizado há" fica vermelho */
  }
}

const lineName = (l) => l.replace(/^LINHA\s*/, "Linha ");
const groupOf = (loc) => { const m = /^G(\d+)(?:-(\d+))?$/.exec(loc || ""); return m ? [Number(m[1]), m[2] ? Number(m[2]) : null] : [0, null]; };
const rowOf = (pos) => Number(/(\d+)$/.exec(pos || "")?.[1] || 0);
const colorOf = (r) => (r.tipo === "Aging" && (r.status === "ok" || r.status === "warn" || r.status === "paused") ? "aging" : r.status);

/* ---------- Renderização ---------- */

function render() {
  const s = state.settings;
  if (!s) return;
  const now = Date.now();
  const all = state.active.map((r) => live(r, state.fetchedAt, now));
  const recs = all.filter((r) => r.linha_producao === state.line);

  // Abas das linhas, com contador de atrasadas
  $("#lines").innerHTML = s.lines.map((l) => {
    const late = all.filter((r) => r.linha_producao === l && r.status === "crit").length;
    return `<button class="line-btn" data-line="${esc(l)}" aria-current="${l === state.line}">${esc(lineName(l))}
      <span class="badge ${late ? "bad" : "good"}">${late || "✓"}</span></button>`;
  }).join("");

  const perSide = s.rows_per_side * s.group_capacity.reduce((a, b) => a + b, 0);
  const capacity = perSide * 2;
  const n = (st) => recs.filter((r) => r.status === st).length;
  const aging = recs.filter((r) => r.tipo === "Aging").length;
  const occ = capacity ? recs.length / capacity : 0;
  const pct = (v) => `${Math.round(v * 100)}%`;

  $("#kpis").innerHTML = `
    <div class="kpi"><div class="kpi-label">Ocupação</div><div class="kpi-value">${pct(occ)}</div>
      <div class="bar"><i style="width:${Math.min(100, occ * 100)}%"></i></div><div class="kpi-sub">${recs.length} de ${capacity} posições</div></div>
    <div class="kpi"><div class="kpi-label">Livres</div><div class="kpi-value">${capacity - recs.length}</div><div class="kpi-sub">posições</div></div>
    <div class="kpi ok"><div class="kpi-label">No prazo</div><div class="kpi-value">${n("ok")}</div><div class="kpi-sub">carregando</div></div>
    <div class="kpi warn"><div class="kpi-label">Vencendo</div><div class="kpi-value">${n("warn")}</div><div class="kpi-sub">próximas do limite</div></div>
    <div class="kpi crit ${n("crit") ? "on" : ""}"><div class="kpi-label">Atrasadas</div><div class="kpi-value">${n("crit")}</div><div class="kpi-sub">retirar agora</div></div>
    <div class="kpi paused"><div class="kpi-label">Pausadas</div><div class="kpi-value">${n("paused")}</div><div class="kpi-sub">sem expediente</div></div>
    <div class="kpi aging"><div class="kpi-label">Aging</div><div class="kpi-value">${aging}</div><div class="kpi-sub">${pct(capacity ? aging / capacity : 0)} das posições</div></div>
    <div class="kpi diag"><div class="kpi-label">Diagnóstico</div><div class="kpi-text">${esc(diagnose(recs, occ))}</div></div>`;

  for (const [lado, el] of [["Lado A", $("#side-a")], ["Lado B", $("#side-b")]]) {
    el.innerHTML = sideMap(s, recs.filter((r) => r.lado === lado), lado, perSide);
  }
  $("#queue").innerHTML = queue(all);
  $("#legend-rule").textContent = `Limite ${s.threshold_min} min · amarelo a partir de ${Math.round(Math.max(s.threshold_min * 0.5, s.threshold_min - 15))} min`;
}

/** Leitura em uma frase: onde está o gargalo agora. */
function diagnose(recs, occ) {
  const late = recs.filter((r) => r.status === "crit").length;
  const aging = recs.filter((r) => r.tipo === "Aging").length;
  const parts = [];
  if (!recs.length) return "Estação vazia nesta linha.";
  if (late && occ < 0.5) parts.push(`${late} peça(s) atrasada(s) com ${Math.round(occ * 100)}% de ocupação: sobra espaço, falta retirada. O gargalo é tempo, não posição.`);
  else if (late) parts.push(`${late} peça(s) atrasada(s) e ${Math.round(occ * 100)}% de ocupação: retirar as atrasadas libera posição para a linha.`);
  else parts.push("Nenhuma peça atrasada: fluxo sob controle.");
  if (occ >= 0.85) parts.push("Ocupação acima de 85%: risco de faltar posição.");
  if (aging / recs.length > 0.5) parts.push(`Aging ocupa ${Math.round((aging / recs.length) * 100)}% das peças na estação — capacidade presa por dias.`);
  return parts.join(" · ");
}

function sideMap(s, recs, lado, perSide) {
  const groups = s.group_capacity.length;
  // Distribui as peças nas vagas de cada célula (linha × grupo). Vaga explícita (G3-4) tem prioridade.
  const cells = new Map();
  const key = (row, g) => `${row}:${g}`;
  for (const r of recs) {
    const [g, vaga] = groupOf(r.localizacao);
    const row = rowOf(r.posicao);
    if (!g || !row) continue;
    if (!cells.has(key(row, g))) cells.set(key(row, g), { fixed: new Map(), loose: [] });
    const c = cells.get(key(row, g));
    if (vaga && !c.fixed.has(vaga)) c.fixed.set(vaga, r);
    else c.loose.push(r);
  }

  let html = `<div class="side-head"><h2>${esc(lineName(state.line))} — ${esc(lado)}</h2><span>${recs.length}/${perSide} · ${Math.round((recs.length / perSide) * 100)}%</span></div>`;
  html += `<div class="map" style="--groups:${groups};--rows:${s.rows_per_side}"><div></div>`;
  html += s.group_capacity.map((_, i) => `<div class="gh">G${i + 1}</div>`).join("");
  for (let row = 1; row <= s.rows_per_side; row++) {
    const rowCount = recs.filter((r) => rowOf(r.posicao) === row).length;
    const rowCap = s.group_capacity.reduce((a, b) => a + b, 0);
    html += `<div class="rh"><b>L${row}</b><small>${rowCount}/${rowCap}</small></div>`;
    s.group_capacity.forEach((cap, gi) => {
      const c = cells.get(key(row, gi + 1)) || { fixed: new Map(), loose: [] };
      const slots = Array.from({ length: cap }, (_, i) => c.fixed.get(i + 1) || null);
      for (const r of c.loose) {
        const free = slots.indexOf(null);
        if (free >= 0) slots[free] = r;
      }
      // Grade fixa de 5 colunas × 2 linhas por célula; grupos menores (G7 = 5) deixam o resto vazio.
      const total = Math.max(10, Math.ceil(cap / 5) * 5);
      let inner = "";
      for (let i = 0; i < total; i++) {
        const r = slots[i];
        if (i >= cap) inner += `<i class="slot ghost"></i>`;
        else if (!r) inner += `<i class="slot"></i>`;
        else inner += `<i class="slot ${colorOf(r)}" title="${esc(`${r.pcba} · ${r.nome} · ${fmtShort(r.tempo)}`)}"></i>`;
      }
      html += `<div class="cell half">${inner}</div>`;
    });
  }
  return html + "</div>";
}

function queue(all) {
  // Todas as linhas: atrasadas primeiro (mais atrasada no topo), depois as que estão vencendo.
  const items = all
    .filter((r) => r.status === "crit" || r.status === "warn")
    .sort((a, b) => (a.status === "crit") === (b.status === "crit") ? a.restante - b.restante : a.status === "crit" ? -1 : 1);
  if (!items.length) return `<div class="q-empty">Nenhuma peça atrasada ou vencendo. ✓</div>`;
  const shown = items.slice(0, QUEUE_MAX).map((r) => {
    const cls = r.status === "crit" ? "" : r.tipo === "Aging" ? "aging" : "warn";
    const time = r.status === "crit" ? `+${fmtShort(-r.restante)}` : `${r.tipo === "Aging" ? "⏳ " : ""}${fmtShort(r.restante)}`;
    const tipo = r.tipo === "Aging" ? `AGING ${Math.round(r.limite_min / 60)}h · ` : "";
    const nivel = r.alertas_enviados ? ` · N${r.alertas_enviados}${r.ciente_em ? " ✓" : ""}` : "";
    return `<div class="q-item ${cls}">
      <div class="q-top"><span class="q-pos">${esc(r.lado)} · ${esc(r.posicao.replace("Linha ", "L"))} · ${esc(r.localizacao)}</span><span class="q-time">${time}</span></div>
      <div class="q-sub"><b>${esc(lineName(r.linha_producao))}</b> · ${tipo}PCBA …${esc(r.pcba.slice(-8))} · ${esc(String(r.nome).split(" ")[0])} · entrada ${fmtTime(r.entrada_em)}${nivel}</div>
    </div>`;
  });
  const more = items.length > QUEUE_MAX ? `<div class="q-more">+ ${items.length - QUEUE_MAX} na fila</div>` : "";
  return shown.join("") + more;
}

/* ---------- Controles ---------- */

function setLine(l) {
  state.line = l;
  const u = new URL(location.href);
  u.searchParams.set("linha", l);
  history.replaceState(null, "", u);
  render();
}

function bind() {
  $("#lines").addEventListener("click", (e) => {
    const b = e.target.closest("[data-line]");
    if (b) setLine(b.dataset.line);
  });
  $("#b-rotate").addEventListener("click", (e) => {
    state.rotate = !state.rotate;
    e.currentTarget.setAttribute("aria-pressed", String(state.rotate));
    clearInterval(state.rotateTimer);
    if (state.rotate) {
      state.rotateTimer = setInterval(() => {
        const ls = state.settings?.lines || [];
        if (ls.length > 1) setLine(ls[(ls.indexOf(state.line) + 1) % ls.length]);
      }, ROTATE_MS);
    }
  });
  $("#b-full").addEventListener("click", () => {
    if (document.fullscreenElement) document.exitFullscreen();
    else document.documentElement.requestFullscreen?.();
  });
}

function clock() {
  $("#clock").textContent = fmtClock();
  const el = $("#updated");
  if (!state.fetchedAt) return;
  const ago = Math.round((Date.now() - state.fetchedAt) / 1000);
  el.textContent = ago < 60 ? `atualizado há ${ago}s` : `sem atualização há ${Math.floor(ago / 60)} min`;
  el.classList.toggle("stale", ago > 60);
}

bind();
refresh();
setInterval(refresh, REFRESH_MS);
setInterval(clock, 1000);
setInterval(render, 5000); // avança tempos e cores entre as consultas
clock();
