// Plano de ação (quadro PDCA) + qualidade dos dados.
import { api, esc, fmtDate, fmtMin, fmtTime, initTheme, modal, toast, toastError } from "./api.js";
import { ETAPAS, actionForm, currentAdmin } from "./actions-ui.js";

const $ = (s) => document.querySelector(s);
const LETRA = { Planejar: "P", Executar: "D", Verificar: "C", Agir: "A", "Concluída": "✓" };
const lineLabel = (l) => String(l || "").replace(/^LINHA/, "Linha");
const state = { actions: [], lines: [], admin: null, linha: "" };

async function boot() {
  initTheme();
  state.admin = await currentAdmin();
  $("#b-new").classList.toggle("hidden", !state.admin);
  $("#b-login").classList.toggle("hidden", Boolean(state.admin));
  try {
    const s = await api("/settings");
    state.lines = s.lines;
    $("#f-linha").innerHTML += s.lines.map((l) => `<option value="${esc(l)}">${esc(lineLabel(l))}</option>`).join("");
  } catch (e) { toastError(e); }
  $("#f-linha").addEventListener("change", (e) => { state.linha = e.target.value; render(); });
  $("#b-new").addEventListener("click", async () => {
    if (await actionForm({ linha: state.linha }, state.lines)) await load();
  });
  $("#board").addEventListener("click", async (e) => {
    const card = e.target.closest("[data-id]");
    if (!card || !state.admin) return;
    const a = state.actions.find((x) => x.id === card.dataset.id);
    if (a && await actionForm(a, state.lines)) await load();
  });
  $("#board").addEventListener("keydown", (e) => { if (e.key === "Enter" && e.target.matches("[data-id]")) e.target.click(); });
  $("#quality").addEventListener("click", onQualityClick);
  await Promise.all([load(), loadQuality()]);
}

async function load() {
  try {
    state.actions = await api("/actions");
    render();
  } catch (e) { toastError(e); }
}

function render() {
  const list = state.actions.filter((a) => !state.linha || a.linha === state.linha || a.linha === "");
  const abertas = list.filter((a) => a.etapa !== "Concluída");
  const atrasadas = abertas.filter((a) => a.atrasada).length;
  const mes = new Date().toISOString().slice(0, 7);
  const concl = list.filter((a) => a.concluido_em && a.concluido_em.slice(0, 7) === mes).length;
  const noPrazo = list.filter((a) => a.concluido_em);
  const pctPrazo = noPrazo.length ? Math.round((noPrazo.filter((a) => a.concluido_em.slice(0, 10) <= a.prazo).length / noPrazo.length) * 100) : null;
  $("#summary").innerHTML = `
    <span class="chip-sum">Abertas <b>${abertas.length}</b></span>
    <span class="chip-sum ${atrasadas ? "bad" : ""}">Atrasadas <b>${atrasadas}</b></span>
    <span class="chip-sum">Concluídas no mês <b>${concl}</b></span>
    <span class="chip-sum">Concluídas no prazo <b>${pctPrazo == null ? "—" : pctPrazo + "%"}</b></span>
    ${state.admin ? "" : '<span class="chip-sum">Somente leitura — entre como administrador para criar e mover ações</span>'}`;

  $("#board").innerHTML = ETAPAS.map((et) => {
    const items = list.filter((a) => a.etapa === et);
    return `<div class="col"><div class="col-head"><span class="letter">${LETRA[et]}</span>${et}<span class="count">${items.length}</span></div>
      ${items.map(card).join("") || '<div class="col-empty">Nada aqui.</div>'}</div>`;
  }).join("");
}

function card(a) {
  const prazo = fmtDate(a.prazo + "T12:00:00");
  return `<article class="act ${a.atrasada ? "late" : ""} ${state.admin ? "clickable" : ""}" data-id="${a.id}" ${state.admin ? 'tabindex="0" title="Clique para editar"' : ""}>
    <div class="a-top">${a.linha ? `<span class="tag" style="background:var(--accent-soft);color:var(--accent)">${esc(lineLabel(a.linha))}</span>` : '<span class="tag" style="background:var(--surface-alt)">Todas</span>'}
      ${a.origem.startsWith("Indicadores") ? '<span title="Criada a partir da leitura executiva">· do KPI</span>' : ""}</div>
    <div class="a-prob">${esc(a.problema)}</div>
    <div class="a-acao">→ ${esc(a.acao)}</div>
    <div class="a-foot"><span>${esc(a.responsavel)}</span><span class="${a.atrasada ? "late-txt" : ""}">${a.atrasada ? "atrasada · " : ""}${prazo}</span></div>
    ${a.resultado ? `<div class="a-res">Resultado: ${esc(a.resultado)}</div>` : ""}
  </article>`;
}

/* ---------- Qualidade dos dados ---------- */
async function loadQuality() {
  try {
    const q = await api("/quality");
    const ab = q.abertos.length
      ? `<table class="data compact"><thead><tr><th>PCBA</th><th>Posição</th><th>Colaborador</th><th>Entrada</th><th class="right">Tempo</th><th></th></tr></thead><tbody>
        ${q.abertos.map((r) => `<tr><td class="mono">${esc(r.pcba)}${r.tipo === "Aging" ? ' <span class="tag aging">AGING</span>' : ""}</td>
          <td>${esc(`${lineLabel(r.linha)} · ${r.lado} · ${r.posicao} · ${r.localizacao}`)}</td><td>${esc(r.nome)}</td>
          <td class="mono muted">${fmtDate(r.entrada_em)} ${fmtTime(r.entrada_em)}</td><td class="right"><span class="chip crit">${fmtMin(r.minutos)}</span></td>
          <td class="right">${state.admin ? `<button class="btn btn-ghost btn-sm" data-close="${r.id}" data-pcba="${esc(r.pcba)}">Encerrar como esquecida</button>` : ""}</td></tr>`).join("")}
        </tbody></table>`
      : `<p class="muted">✓ Nenhum registro aberto há mais de ${q.limite_aberto_h} h.</p>`;
    const inv = q.posicoes_invalidas.total
      ? `<p><b>${q.posicoes_invalidas.total}</b> registro(s) com posição fora do layout atual (o layout mudou depois da entrada?).</p>`
      : `<p class="muted">✓ Todas as posições batem com o layout atual.</p>`;
    const fora = q.linhas_fora_do_cadastro.length
      ? `<p>Linhas fora do cadastro: ${q.linhas_fora_do_cadastro.map((x) => `<b>${esc(lineLabel(x.linha))}</b> (${x.n})`).join(", ")}.</p>`
      : `<p class="muted">✓ Todas as linhas registradas estão cadastradas.</p>`;
    $("#quality").innerHTML = `
      <h3 class="q-title">Registros abertos há mais de ${q.limite_aberto_h} h <span class="muted">(saída esquecida)</span></h3>
      <div class="table-wrap">${ab}</div>
      <p class="muted small">Encerrar como esquecida registra o motivo “Esqueceu de remover” e marca o registro como ajuste: ele sai das médias dos indicadores, mas continua rastreável (quem encerrou e quando).</p>
      ${inv}${fora}
      <p class="muted small">Banco: ${q.volume.registros.toLocaleString("pt-BR")} registros · ${q.volume.ajustados} encerrados por ajuste.</p>`;
  } catch (e) { toastError(e); }
}

async function onQualityClick(e) {
  const b = e.target.closest("[data-close]");
  if (!b) return;
  const ok = await modal({
    title: "Encerrar como saída esquecida?",
    subtitle: `PCBA <b class="mono">${esc(b.dataset.pcba)}</b>. O registro sai das médias dos indicadores e fica marcado como ajuste.`,
    body: "", okText: "Encerrar", okClass: "btn-danger",
  });
  if (!ok) return;
  try {
    await api(`/admin/records/${b.dataset.close}/close-forgotten`, { method: "POST", admin: true });
    toast("Registro encerrado como saída esquecida.", "ok");
    await loadQuality();
  } catch (err) { toastError(err); }
}

boot();
