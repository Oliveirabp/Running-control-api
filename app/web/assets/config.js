// Configurações do administrador: login JWT, regras, matriz de escalonamento, colaboradores e operação.
import { api, auth, esc, fmtDate, fmtTime, initTheme, modal, toast, toastError } from "./api.js";

const $ = (s) => document.querySelector(s);
const PAUSA = "Pausa programada (sem expediente)";
const FUNCOES = ["Monitor", "Lider", "Auditor", "Supervisor"];
const state = { settings: null, employees: [], eq: "" };

/* ---------- Sessão ---------- */

async function boot() {
  initTheme();
  bindLogin();
  if (auth.get()) {
    try {
      const me = await api("/auth/me", { admin: true });
      return enter(me);
    } catch { /* token vencido: cai no login */ }
  }
  showLogin();
}

function showLogin(msg = "") {
  $("#admin-view").classList.add("hidden");
  $("#who").classList.add("hidden");
  $("#logout").classList.add("hidden");
  $("#login-view").classList.remove("hidden");
  $("#l-err").textContent = msg;
  $("#l-email").focus();
}

function bindLogin() {
  $("#login").addEventListener("submit", async (e) => {
    e.preventDefault();
    const btn = $("#l-btn");
    btn.disabled = true;
    $("#l-err").textContent = "";
    try {
      const t = await api("/auth/login", { method: "POST", form: { username: $("#l-email").value, password: $("#l-pass").value } });
      auth.set(t.access_token);
      $("#l-pass").value = "";
      enter(await api("/auth/me", { admin: true }));
    } catch (err) {
      $("#l-err").textContent = err.message;
      $("#l-pass").select();
    } finally {
      btn.disabled = false;
    }
  });
  $("#logout").addEventListener("click", () => { auth.clear(); showLogin(); });
}

/** Qualquer 401 durante o uso (sessão expirada) volta para o login. */
async function adminCall(path, opts = {}) {
  try {
    return await api(path, { ...opts, admin: true });
  } catch (err) {
    if (err.status === 401) showLogin(err.message);
    throw err;
  }
}

async function enter(me) {
  $("#login-view").classList.add("hidden");
  $("#admin-view").classList.remove("hidden");
  $("#who").textContent = me.nome ? `${me.nome} · ${me.email}` : me.email;
  $("#who").classList.remove("hidden");
  $("#logout").classList.remove("hidden");
  if (!enter.bound) { bindAdmin(); enter.bound = true; }
  await loadAll();
}

/* ---------- Carga ---------- */

async function loadAll() {
  try {
    const [settings, matrix, employees, active] = await Promise.all([
      api("/settings"), adminCall("/admin/responsibles"), api("/employees"), api("/records/active"),
    ]);
    state.settings = settings;
    $("#i-limit").value = settings.threshold_min;
    $("#i-reasons").value = settings.reasons.filter((r) => r !== PAUSA).join("\n");
    showBaseline({ minutos: settings.baseline_min, fonte: settings.baseline_fonte });
    renderMatrix(matrix);
    state.employees = employees;
    renderEmployees();
    renderActive(active);
  } catch (err) {
    if (err.status !== 401) toastError(err);
  }
}

/* ---------- Abas ---------- */

function bindAdmin() {
  document.querySelectorAll("[data-tab]").forEach((b) =>
    b.addEventListener("click", () => {
      document.querySelectorAll("[data-tab]").forEach((x) => x.setAttribute("aria-selected", String(x === b)));
      document.querySelectorAll("[data-panel]").forEach((p) => p.classList.toggle("hidden", p.dataset.panel !== b.dataset.tab));
    }),
  );

  // Regras
  $("#f-limit").addEventListener("submit", async (e) => {
    e.preventDefault();
    try {
      const r = await adminCall("/admin/threshold", { method: "PUT", body: { threshold_min: Number($("#i-limit").value) } });
      toast(`Limite salvo: ${r.threshold_min} min.`, "ok");
    } catch (err) { if (err.status !== 401) toastError(err); }
  });
  $("#f-reasons").addEventListener("submit", async (e) => {
    e.preventDefault();
    const reasons = $("#i-reasons").value.split("\n").map((s) => s.trim()).filter(Boolean);
    try {
      const r = await adminCall("/admin/reasons", { method: "PUT", body: { reasons } });
      $("#i-reasons").value = r.filter((x) => x !== PAUSA).join("\n");
      toast(`${r.length} motivos salvos.`, "ok");
    } catch (err) { if (err.status !== 401) toastError(err); }
  });

  $("#f-base").addEventListener("submit", async (e) => {
    e.preventDefault();
    const fonte = $("#i-fonte").value.trim();
    if (!fonte) { toast("Registre a fonte da medição — é ela que torna o ganho auditável.", "err"); return $("#i-fonte").focus(); }
    try {
      const r = await adminCall("/admin/baseline", { method: "PUT", body: { minutos: Number($("#i-base").value), fonte } });
      showBaseline(r);
      toast(`Linha de base salva: ${r.minutos} min.`, "ok");
    } catch (err) { if (err.status !== 401) toastError(err); }
  });

  // Responsáveis
  $("#r-add").addEventListener("click", () => { $("#r-rows").insertAdjacentHTML("beforeend", matrixRow({})); });
  $("#r-rows").addEventListener("click", (e) => { if (e.target.closest("[data-del]")) e.target.closest("tr").remove(); });
  $("#r-rows").addEventListener("change", (e) => {
    if (!e.target.matches("[data-f=funcao]")) return;
    const linha = e.target.closest("tr").querySelector("[data-f=linha]");
    const sup = e.target.value === "Supervisor";
    if (sup) linha.value = "TODAS";
    linha.disabled = sup;
  });
  $("#r-save").addEventListener("click", saveMatrix);

  // Colaboradores
  $("#f-emp").addEventListener("submit", async (e) => {
    e.preventDefault();
    try {
      const emp = await adminCall("/employees", { method: "POST", body: { matricula: $("#e-mat").value, nome: $("#e-nome").value } });
      state.employees.push(emp);
      state.employees.sort((a, b) => a.nome.localeCompare(b.nome, "pt-BR"));
      renderEmployees();
      toast(`${emp.nome} cadastrado(a).`, "ok");
      $("#e-mat").value = ""; $("#e-nome").value = ""; $("#e-mat").focus();
    } catch (err) { if (err.status !== 401) toastError(err); }
  });
  $("#e-q").addEventListener("input", (e) => { state.eq = e.target.value.trim().toLowerCase(); renderEmployees(); });
  $("#e-rows").addEventListener("click", async (e) => {
    const b = e.target.closest("[data-del]");
    if (!b) return;
    const ok = await modal({ title: "Remover colaborador?", subtitle: esc(b.dataset.nome), body: "", okText: "Remover", okClass: "btn-danger" });
    if (!ok) return;
    try {
      await adminCall(`/employees/${encodeURIComponent(b.dataset.del)}`, { method: "DELETE" });
      state.employees = state.employees.filter((x) => x.matricula !== b.dataset.del);
      renderEmployees();
    } catch (err) { if (err.status !== 401) toastError(err); }
  });

  // Operação
  $("#o-run").addEventListener("click", async () => {
    try {
      const s = await adminCall("/admin/alerts/run", { method: "POST" });
      const out = $("#o-result");
      out.classList.remove("hidden");
      out.textContent = [
        `Peças na estação: ${s.ativos}`,
        `Em atraso: ${s.em_atraso}  ·  pausadas/adiadas: ${s.pausados}`,
        `E-mails enviados agora: ${s.enviados}  (N1 ${s.por_nivel["1"]} · N2 ${s.por_nivel["2"]} · N3 ${s.por_nivel["3"]})`,
        s.sem_destinatario.length ? `Sem destinatário cadastrado: ${s.sem_destinatario.join(", ")}` : "",
        s.erros.length ? `Erros: ${s.erros.join(" | ")}` : "",
      ].filter(Boolean).join("\n");
    } catch (err) { if (err.status !== 401) toastError(err); }
  });
  $("#o-rows").addEventListener("click", async (e) => {
    const b = e.target.closest("[data-del]");
    if (!b) return;
    const ok = await modal({
      title: "Excluir registro?",
      subtitle: `PCBA <b class="mono">${esc(b.dataset.pcba)}</b>. Não dá para desfazer.`,
      body: "", okText: "Excluir", okClass: "btn-danger",
    });
    if (!ok) return;
    try {
      await adminCall(`/admin/records/${b.dataset.del}`, { method: "DELETE" });
      toast("Registro excluído.", "ok");
      renderActive(await api("/records/active"));
    } catch (err) { if (err.status !== 401) toastError(err); }
  });
}

function showBaseline(b) {
  if (!b || !b.minutos) { $("#base-now").textContent = "sem linha de base: o ganho ainda não aparece nos Indicadores"; return; }
  $("#base-now").textContent = `em uso: ${b.minutos} min · ${b.fonte || "sem fonte"}`;
  $("#i-base").value = b.minutos;
  $("#i-fonte").value = b.fonte || "";
}

/* ---------- Matriz ---------- */

function matrixRow(r) {
  const lines = [...(state.settings?.lines || []), "TODAS"];
  const sup = r.funcao === "Supervisor";
  const linha = sup ? "TODAS" : r.linha || lines[0];
  return `<tr>
    <td><select class="select" data-f="linha" ${sup ? "disabled" : ""}>${lines.map((l) => `<option value="${esc(l)}" ${l === linha ? "selected" : ""}>${esc(l.replace(/^LINHA/, "Linha"))}</option>`).join("")}</select></td>
    <td><select class="select" data-f="funcao">${FUNCOES.map((f) => `<option ${f === (r.funcao || "Monitor") ? "selected" : ""}>${f}</option>`).join("")}</select></td>
    <td><input class="input" data-f="turno1" value="${esc(r.turno1 || "")}" placeholder="nome@example.com"></td>
    <td><input class="input" data-f="turno2" value="${esc(r.turno2 || "")}" placeholder="nome@example.com"></td>
    <td><button class="btn btn-ghost btn-sm" data-del title="Remover linha">✕</button></td>
  </tr>`;
}

function renderMatrix(rows) {
  $("#r-rows").innerHTML = rows.length ? rows.map(matrixRow).join("") : matrixRow({});
}

async function saveMatrix() {
  const rows = [...document.querySelectorAll("#r-rows tr")].map((tr) => {
    const v = (f) => tr.querySelector(`[data-f=${f}]`).value.trim();
    return { linha: v("linha"), funcao: v("funcao"), turno1: v("turno1"), turno2: v("turno2") };
  }).filter((r) => r.turno1 || r.turno2);
  try {
    const saved = await adminCall("/admin/responsibles", { method: "PUT", body: rows });
    renderMatrix(saved);
    toast(`Matriz salva: ${saved.length} linha(s).`, "ok");
  } catch (err) { if (err.status !== 401) toastError(err); }
}

/* ---------- Listas ---------- */

function renderEmployees() {
  const list = state.employees.filter((e) => !state.eq || `${e.matricula} ${e.nome}`.toLowerCase().includes(state.eq));
  $("#e-count").textContent = state.employees.length;
  $("#e-rows").innerHTML = list.map((e) => `<tr>
    <td class="mono">${esc(e.matricula)}</td><td class="name">${esc(e.nome)}</td>
    <td class="right"><button class="btn btn-ghost btn-sm" data-del="${esc(e.matricula)}" data-nome="${esc(e.nome)}">Remover</button></td>
  </tr>`).join("") || `<tr><td colspan="3" class="empty">Nenhum colaborador.</td></tr>`;
}

function renderActive(active) {
  $("#o-rows").innerHTML = active.map((r) => `<tr>
    <td class="mono">${esc(r.pcba)}</td>
    <td>${esc(`${r.linha_producao.replace(/^LINHA/, "Linha")} · ${r.lado} · ${r.posicao} · ${r.localizacao}`)}</td>
    <td class="mono muted">${fmtDate(r.entrada_em)} ${fmtTime(r.entrada_em)}</td>
    <td class="right"><button class="btn btn-ghost btn-sm" data-del="${r.id}" data-pcba="${esc(r.pcba)}">Excluir</button></td>
  </tr>`).join("") || `<tr><td colspan="4" class="empty">Nenhuma peça na estação.</td></tr>`;
}

boot();
