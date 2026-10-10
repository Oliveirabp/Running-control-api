// Painel do operador: entrada, saída, ciente e acompanhamento em tempo real.
import { api, esc, fmtDate, fmtMin, fmtTime, initTheme, live, modal, startClock, toast, toastError } from "./api.js";

const $ = (s) => document.querySelector(s);
const REFRESH_MS = 15000;

const state = {
  settings: null,
  employees: new Map(),
  active: [],
  history: [],
  fetchedAt: Date.now(),
  tab: "active",
  q: "",
  shown: new Map(), // id -> status exibido (para saber quando reordenar)
};

const normMat = (v) => String(v || "").replace(/[\x00-\x1f\x7f]/g, "").trim().toUpperCase().replace(/^0+(?=\d)/, "");

/* ---------- Carga inicial ---------- */

async function boot() {
  initTheme();
  startClock($("#clock"));
  try {
    const [settings, employees] = await Promise.all([api("/settings"), api("/employees")]);
    state.settings = settings;
    employees.forEach((e) => state.employees.set(normMat(e.matricula), e.nome));
    fillForm(settings);
  } catch (e) {
    toastError(e);
  }
  bindForm();
  bindTable();
  await refresh();
  setInterval(refresh, REFRESH_MS);
  setInterval(tick, 1000);
  openAckFromLink();
}

function fillForm(s) {
  const lastLine = (() => { try { return localStorage.getItem("rc.linha"); } catch { return null; } })();
  $("#f-linha").innerHTML = s.lines
    .map((l) => `<option value="${esc(l)}" ${l === lastLine ? "selected" : ""}>${esc(l.replace(/^LINHA/, "Linha"))}</option>`)
    .join("");
  $("#l-pos").innerHTML = Array.from({ length: s.rows_per_side }, (_, i) => `<option value="Linha ${i + 1}">`).join("");
  $("#l-loc").innerHTML = s.group_capacity.map((_, i) => `<option value="G${i + 1}">`).join("");
  $("#f-aging").innerHTML = s.aging_options_h.map((h) => `<option value="${h}">${h} horas</option>`).join("");
}

/* ---------- Formulário de entrada ---------- */

function seg(el) {
  el.addEventListener("click", (e) => {
    const b = e.target.closest("button");
    if (!b) return;
    el.querySelectorAll("button").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
    el.dispatchEvent(new Event("change"));
  });
  return () => el.querySelector('[aria-pressed="true"]').dataset.v;
}

function bindForm() {
  const form = $("#entry");
  const lado = seg($("#f-lado"));
  const tipo = seg($("#f-tipo"));
  $("#f-tipo").addEventListener("change", () => { $("#w-aging").hidden = tipo() !== "Aging"; });

  // Nome do colaborador aparece ao ler o crachá.
  const mat = $("#f-mat");
  const showName = () => {
    const h = $("#h-mat");
    const v = normMat(mat.value);
    const nome = state.employees.get(v);
    h.className = "hint" + (v ? (nome ? " ok" : " err") : "");
    h.textContent = v ? nome || "Matrícula não cadastrada" : "";
    mat.setAttribute("aria-invalid", String(Boolean(v && !nome)));
  };
  mat.addEventListener("input", showName);

  // Leitor de QR "digita" e envia Enter: avança para o próximo campo.
  const order = ["#f-mat", "#f-pcba", "#f-pos", "#f-loc"];
  order.forEach((sel, i) => {
    $(sel).addEventListener("keydown", (e) => {
      if (e.key !== "Enter") return;
      e.preventDefault();
      if (i < order.length - 1) $(order[i + 1]).focus();
      else form.requestSubmit();
    });
  });

  $("#f-linha").addEventListener("change", (e) => {
    try { localStorage.setItem("rc.linha", e.target.value); } catch { /* sem storage */ }
  });

  form.addEventListener("reset", () => setTimeout(() => { showName(); $("#entry-msg").textContent = ""; }));

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const body = {
      matricula: mat.value,
      pcba: $("#f-pcba").value,
      linha_producao: $("#f-linha").value,
      lado: lado(),
      posicao: $("#f-pos").value,
      localizacao: $("#f-loc").value,
      tipo: tipo(),
      aging_horas: tipo() === "Aging" ? Number($("#f-aging").value) : null,
    };
    const btn = $("#b-entry");
    btn.disabled = true;
    try {
      const r = await api("/records/entries", { method: "POST", body });
      toast(`Entrada registrada: ${r.pcba} · ${r.lado} · ${r.posicao} · ${r.localizacao}`, "ok");
      $("#entry-msg").textContent = `Última: ${r.pcba} às ${fmtTime(r.entrada_em)}`;
      // Mantém crachá, linha, lado e tipo (o operador costuma alocar várias peças seguidas).
      ["#f-pcba", "#f-pos", "#f-loc"].forEach((s) => { $(s).value = ""; });
      $("#f-pcba").focus();
      await refresh();
    } catch (err) {
      toastError(err);
      if (err.code === "MATRICULA_NAO_ENCONTRADA") mat.focus();
      else if (err.code === "PCBA_JA_NA_ESTACAO" || err.code === "PCBA_OBRIGATORIA") $("#f-pcba").focus();
      else if (err.code === "POSICAO_INVALIDA") $("#f-pos").focus();
    } finally {
      btn.disabled = false;
    }
  });

  // Saída pela leitura do QR
  $("#exit").addEventListener("submit", async (e) => {
    e.preventDefault();
    const input = $("#f-exit");
    const pcba = input.value.trim();
    if (!pcba) return input.focus();
    const ok = await doExit({ pcba });
    if (ok) input.value = "";
    input.focus();
  });
}

/* ---------- Saída e ciente ---------- */

async function askReason(rec) {
  const reasons = state.settings?.reasons || [];
  return modal({
    title: "Peça em atraso",
    subtitle: rec ? `PCBA <b class="mono">${esc(rec.pcba)}</b> · ${esc(rec.lado)} · ${esc(rec.posicao)} · ${esc(rec.localizacao)}<br>Informe o motivo para registrar a saída.` : "Informe o motivo para registrar a saída.",
    body: `<div class="reason-list">${reasons
      .map((r, i) => `<label><input type="radio" name="m" value="${esc(r)}" ${i === 0 ? "checked" : ""}> ${esc(r)}</label>`)
      .join("")}</div>`,
    okText: "Registrar saída",
    okClass: "btn-danger",
    collect: (f) => f.querySelector("input[name=m]:checked")?.value,
  });
}

/** Registra a saída por id ou por PCBA; pede o motivo quando a API exigir. */
async function doExit({ id, pcba }, rec = null, motivo = null) {
  try {
    const path = id ? `/records/${id}/exit` : "/records/exit-by-pcba";
    const body = id ? { motivo } : { pcba, motivo };
    const r = await api(path, { method: "POST", body });
    toast(`Saída registrada: ${r.pcba} · ${fmtMin(r.tempo_min)}${r.motivo ? ` · ${r.motivo}` : ""}`, "ok");
    await refresh();
    return true;
  } catch (err) {
    if (err.code === "MOTIVO_OBRIGATORIO" && !motivo) {
      const target = rec || state.active.find((x) => x.pcba.toUpperCase() === String(pcba).toUpperCase());
      const m = await askReason(target);
      return m ? doExit({ id, pcba }, rec, m) : false;
    }
    toastError(err);
    return false;
  }
}

async function doAck(rec) {
  const mat = await modal({
    title: "Confirmar ciência do alerta",
    subtitle: `PCBA <b class="mono">${esc(rec.pcba)}</b> · ${esc(rec.lado)} · ${esc(rec.posicao)} · ${esc(rec.localizacao)}<br>O ciente registra quem assumiu; a escalada só para com a saída da peça.`,
    body: `<div class="field"><label for="m-mat">Matrícula (crachá)</label><input class="input scan" id="m-mat" inputmode="numeric" required><div class="hint" id="m-hint"></div></div>`,
    okText: "Registrar ciente",
    okClass: "btn-warn",
    collect: (f) => {
      const v = f.querySelector("#m-mat").value.trim();
      if (!v) { f.querySelector("#m-mat").focus(); return null; }
      return v;
    },
  });
  if (!mat) return;
  try {
    const r = await api(`/records/${rec.id}/ack`, { method: "POST", body: { matricula: mat } });
    toast(r.ja_registrado ? `A ciência já havia sido registrada por ${r.ciente_nome}.` : `Ciência registrada: ${r.ciente_nome}.`, "ok");
    await refresh();
  } catch (err) {
    toastError(err);
  }
}

/** Link "Confirmar ciência" do e-mail: /?ciente=<id>. */
function openAckFromLink() {
  const id = new URLSearchParams(location.search).get("ciente");
  if (!id) return;
  history.replaceState(null, "", location.pathname);
  const rec = state.active.find((r) => r.id === id);
  if (rec) doAck(rec);
  else toast("Este alerta já foi encerrado: a saída da peça foi registrada.", "");
}

/* ---------- Tabela ---------- */

const HEAD = {
  active: ["Matrícula", "Colaborador", "PCBA", "Linha", "Lado", "Posição", "Local.", "Entrada", "Duração", "Alerta", ""],
  history: ["Matrícula", "Colaborador", "PCBA", "Linha", "Posição", "Entrada", "Saída", "Duração", "Motivo"],
};

function bindTable() {
  document.querySelectorAll("[data-tab]").forEach((b) =>
    b.addEventListener("click", async () => {
      state.tab = b.dataset.tab;
      document.querySelectorAll("[data-tab]").forEach((x) => x.setAttribute("aria-selected", String(x === b)));
      if (state.tab === "history") await loadHistory();
      render();
    }),
  );
  $("#q").addEventListener("input", (e) => { state.q = e.target.value.trim().toLowerCase(); render(); });
  $("#rows").addEventListener("click", (e) => {
    const b = e.target.closest("button[data-act]");
    if (!b) return;
    const rec = state.active.find((r) => r.id === b.dataset.id);
    if (!rec) return;
    if (b.dataset.act === "ack") doAck(rec);
    if (b.dataset.act === "exit") {
      const l = live(rec, state.fetchedAt);
      if (l.status === "crit") askReason(rec).then((m) => m && doExit({ id: rec.id }, rec, m));
      else doExit({ id: rec.id }, rec);
    }
  });
}

async function refresh() {
  try {
    state.active = await api("/records/active");
    state.fetchedAt = Date.now();
    if (state.tab === "history") await loadHistory();
    render();
  } catch (e) {
    if (e.code === "SEM_CONEXAO") $("#entry-msg").textContent = "Sem conexão — tentando novamente…";
    else toastError(e);
  }
}

async function loadHistory() {
  state.history = await api("/records/history?limit=300");
}

function matches(r) {
  if (!state.q) return true;
  return [r.pcba, r.nome, r.matricula, r.linha_producao, r.lado, r.posicao, r.localizacao, r.motivo]
    .join(" ").toLowerCase().includes(state.q);
}

function durationCell(r) {
  if (r.tipo === "Aging") {
    const planned = Math.round(r.limite_min / 60);
    let sub;
    if (r.status === "crit") sub = `<span class="sub crit">+${fmtMin(-r.restante)} além do planejado</span>`;
    else if (r.status === "paused") sub = `<span class="sub paused">sem expediente · alerta adiado</span>`;
    else sub = `<span class="sub aging">faltam ${fmtMin(r.restante)}</span>`;
    const chip = r.status === "crit" ? "crit" : "aging";
    return `<span class="dur"><span class="chip ${chip}">${fmtMin(r.tempo)}</span><span><span class="tag aging">AGING ${planned}H</span> ${sub}</span></span>`;
  }
  let sub = "";
  if (r.status === "crit") sub = `<span class="sub crit">+${fmtMin(-r.restante)} além do limite${r.tempo >= 1440 ? " · saída esquecida?" : ""}</span>`;
  else if (r.status === "warn") sub = `<span class="sub warn">faltam ${fmtMin(r.restante)}</span>`;
  else if (r.status === "paused") sub = `<span class="sub paused">pausado · sem expediente</span>`;
  return `<span class="dur"><span class="chip ${r.status}">${fmtMin(r.tempo)}</span>${sub}</span>`;
}

function alertCell(r) {
  if (!r.alertas_enviados) return `<span class="muted">—</span>`;
  const lvl = `<span class="tag lvl" title="Nível de escalonamento já enviado">N${r.alertas_enviados}</span>`;
  if (r.ciente_em) {
    const first = String(r.ciente_nome || "").split(" ")[0];
    return `<span class="ack">${lvl}<span class="ack-ok" title="Ciente em ${fmtDate(r.ciente_em)} ${fmtTime(r.ciente_em)}">✓ ${esc(first)} ${fmtTime(r.ciente_em)}</span></span>`;
  }
  return `<span class="ack">${lvl}<button class="btn btn-warn btn-sm" data-act="ack" data-id="${r.id}">Ciente</button></span>`;
}

function render() {
  const tab = state.tab;
  $("#thead").innerHTML = `<tr>${HEAD[tab].map((h) => `<th>${h}</th>`).join("")}</tr>`;
  const now = Date.now();
  const list = (tab === "active" ? state.active.map((r) => live(r, state.fetchedAt, now)) : state.history).filter(matches);

  if (tab === "active") {
    const order = { crit: 0, warn: 1, ok: 2, paused: 3 };
    list.sort((a, b) => order[a.status] - order[b.status] || a.restante - b.restante);
    state.shown = new Map(list.map((r) => [r.id, r.status]));
    $("#rows").innerHTML = list.map((r) => `
      <tr data-row="${r.id}">
        <td class="mono">${esc(r.matricula)}</td>
        <td class="name">${esc(r.nome)}</td>
        <td class="mono">${esc(r.pcba)}</td>
        <td>${esc(r.linha_producao.replace(/^LINHA/, "Linha"))}</td>
        <td>${esc(r.lado)}</td>
        <td>${esc(r.posicao)}</td>
        <td class="mono">${esc(r.localizacao)}</td>
        <td class="mono muted">${fmtDate(r.entrada_em)} ${fmtTime(r.entrada_em)}</td>
        <td data-dur>${durationCell(r)}</td>
        <td>${alertCell(r)}</td>
        <td><div class="actions"><button class="btn btn-ghost btn-sm" data-act="exit" data-id="${r.id}">Saída</button></div></td>
      </tr>`).join("");
  } else {
    $("#rows").innerHTML = list.map((r) => `
      <tr>
        <td class="mono">${esc(r.matricula)}</td>
        <td class="name">${esc(r.nome)}</td>
        <td class="mono">${esc(r.pcba)}${r.tipo === "Aging" ? ` <span class="tag aging">AGING ${Math.round(r.limite_min / 60)}H</span>` : ""}</td>
        <td>${esc(r.linha_producao.replace(/^LINHA/, "Linha"))}</td>
        <td>${esc(`${r.lado} · ${r.posicao} · ${r.localizacao}`)}</td>
        <td class="mono muted">${fmtDate(r.entrada_em)} ${fmtTime(r.entrada_em)}</td>
        <td class="mono muted">${fmtDate(r.saida_em)} ${fmtTime(r.saida_em)}</td>
        <td><span class="chip ${r.em_atraso ? "crit" : "ok"}">${fmtMin(r.tempo_min)}</span></td>
        <td>${r.motivo ? esc(r.motivo) : '<span class="muted">—</span>'}${r.pausa_programada ? ' <span class="tag" style="background:var(--paused-soft);color:var(--paused)">PAUSA</span>' : ""}</td>
      </tr>`).join("");
  }

  const empty = $("#empty");
  empty.classList.toggle("hidden", list.length > 0);
  empty.textContent = state.q ? "Nada encontrado para essa busca." : tab === "active" ? "Nenhuma peça na estação." : "Nenhuma saída registrada ainda.";
  kpis();
}

/** A cada segundo: atualiza só as durações e os indicadores (sem redesenhar a tabela). */
function tick() {
  if (state.tab !== "active") return;
  const now = Date.now();
  let reorder = false;
  for (const rec of state.active) {
    const row = document.querySelector(`[data-row="${rec.id}"] [data-dur]`);
    if (!row) continue;
    const l = live(rec, state.fetchedAt, now);
    if (state.shown.get(rec.id) !== l.status) reorder = true; // mudou de cor: reordena a fila
    const html = durationCell(l);
    if (row.innerHTML !== html) row.innerHTML = html;
  }
  if (reorder) render();
  else kpis();
}

function kpis() {
  const now = Date.now();
  const l = state.active.map((r) => live(r, state.fetchedAt, now));
  const count = (s) => l.filter((r) => r.status === s).length;
  const aging = l.filter((r) => r.tipo === "Aging").length;
  $("#k-total").textContent = l.length;
  $("#k-total-sub").textContent = `${l.length - aging} em running · ${aging} em aging`;
  $("#k-crit").textContent = count("crit");
  $("#k-warn").textContent = count("warn");
  $("#k-paused").textContent = count("paused");
  $("#c-active").textContent = l.length;
}

boot();
