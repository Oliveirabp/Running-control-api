// Running Control — cliente da API e utilidades compartilhadas pelas telas.

const TOKEN_KEY = "rc.token";
const THEME_KEY = "rc.theme";

function store(kind) {
  try { return window[kind]; } catch { return null; }
}

export const auth = {
  get() { try { return store("sessionStorage")?.getItem(TOKEN_KEY) || ""; } catch { return ""; } },
  set(t) { try { store("sessionStorage")?.setItem(TOKEN_KEY, t); } catch { /* sem storage */ } },
  clear() { try { store("sessionStorage")?.removeItem(TOKEN_KEY); } catch { /* sem storage */ } },
};

/** Erro de negócio vindo da API: { code, message, errors[] }. */
export class ApiError extends Error {
  constructor(status, body) {
    const detail = Array.isArray(body?.detail)
      ? body.detail.map((d) => `${(d.loc || []).slice(1).join(".")}: ${d.msg}`)
      : [];
    super(body?.message || (typeof body?.detail === "string" ? body.detail : "") || `Erro ${status}`);
    this.status = status;
    this.code = body?.code || (status === 422 ? "VALIDACAO" : `HTTP_${status}`);
    this.errors = body?.errors?.length ? body.errors : detail;
  }
}

export async function api(path, { method = "GET", body, form, admin = false } = {}) {
  const headers = { Accept: "application/json" };
  let payload;
  if (form) {
    payload = new URLSearchParams(form);
  } else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }
  if (admin && auth.get()) headers.Authorization = `Bearer ${auth.get()}`;

  let res;
  try {
    res = await fetch(path, { method, headers, body: payload });
  } catch {
    throw new ApiError(0, { code: "SEM_CONEXAO", message: "Sem conexão com o servidor." });
  }
  if (res.status === 204) return null;
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    if (res.status === 401 && admin) auth.clear();
    throw new ApiError(res.status, data);
  }
  return data;
}

/* ---------- Formatação ---------- */

const TZ = "America/Sao_Paulo";
const fDate = new Intl.DateTimeFormat("pt-BR", { timeZone: TZ, day: "2-digit", month: "2-digit", year: "numeric" });
const fTime = new Intl.DateTimeFormat("pt-BR", { timeZone: TZ, hour: "2-digit", minute: "2-digit" });
const fClock = new Intl.DateTimeFormat("pt-BR", { timeZone: TZ, hour: "2-digit", minute: "2-digit", second: "2-digit" });

export const fmtDate = (iso) => (iso ? fDate.format(new Date(iso)) : "—");
export const fmtTime = (iso) => (iso ? fTime.format(new Date(iso)) : "—");
export const fmtClock = (d = new Date()) => fClock.format(d);

/** 125 → "2h 05min"; 7 → "7min". */
export function fmtMin(min) {
  const m = Math.max(0, Math.floor(min));
  const h = Math.floor(m / 60);
  return h ? `${h}h ${String(m % 60).padStart(2, "0")}min` : `${m}min`;
}

/** Versão compacta para o Modo TV: "+1h05" / "47h59" / "12min". */
export function fmtShort(min) {
  const m = Math.max(0, Math.floor(min));
  const h = Math.floor(m / 60);
  return h ? `${h}h${String(m % 60).padStart(2, "0")}` : `${m}min`;
}

export function esc(v) {
  return String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

/* ---------- Tempo ao vivo ----------
   A API devolve o tempo calculado no instante da consulta. Entre uma consulta e outra,
   a tela avança o relógio localmente — exceto para Running em pausa programada,
   cujo relógio está parado. A próxima consulta corrige qualquer diferença. */

export function live(rec, fetchedAt, now = Date.now()) {
  const frozen = rec.status === "paused" && rec.tipo !== "Aging";
  const tempo = rec.tempo_min + (frozen ? 0 : (now - fetchedAt) / 60000);
  let status = rec.status;
  if (status !== "paused") status = tempo >= rec.limite_min ? "crit" : tempo >= rec.warn_min ? "warn" : "ok";
  return { ...rec, tempo, status, restante: rec.limite_min - tempo };
}

export const STATUS_LABEL = {
  ok: "No prazo",
  warn: "Vencendo",
  crit: "Atrasado",
  paused: "Pausado",
};

/* ---------- UI comum ---------- */

export function toast(msg, kind = "", errors = []) {
  let box = document.querySelector(".toasts");
  if (!box) {
    box = document.createElement("div");
    box.className = "toasts";
    box.setAttribute("role", "status");
    box.setAttribute("aria-live", "polite");
    document.body.append(box);
  }
  const el = document.createElement("div");
  el.className = `toast ${kind}`;
  el.innerHTML = esc(msg) + (errors.length ? `<ul>${errors.map((e) => `<li>${esc(e)}</li>`).join("")}</ul>` : "");
  box.append(el);
  setTimeout(() => el.remove(), errors.length ? 7000 : 4000);
}

export function toastError(err) {
  toast(err.message || "Erro inesperado.", "err", err.errors || []);
}

export function initTheme() {
  const saved = (() => { try { return localStorage.getItem(THEME_KEY); } catch { return null; } })();
  const dark = saved ? saved === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
  document.documentElement.dataset.theme = dark ? "dark" : "light";
  document.querySelector("[data-theme-toggle]")?.addEventListener("click", () => {
    const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem(THEME_KEY, next); } catch { /* sem storage */ }
  });
}

export function startClock(el) {
  const tick = () => { el.textContent = fmtClock(); };
  tick();
  setInterval(tick, 1000);
}

/** Abre um modal simples; resolve com o valor de `collect()` ou null se cancelado. */
export function modal({ title, subtitle = "", body, okText = "Confirmar", okClass = "btn-primary", collect, focus }) {
  return new Promise((resolve) => {
    const back = document.createElement("div");
    back.className = "modal-back";
    back.innerHTML = `
      <div class="modal" role="dialog" aria-modal="true" aria-labelledby="m-title">
        <div class="modal-head"><h3 id="m-title">${esc(title)}</h3>${subtitle ? `<div class="muted">${subtitle}</div>` : ""}</div>
        <form class="modal-body">${body}</form>
        <div class="modal-foot">
          <button type="button" class="btn btn-ghost" data-cancel>Cancelar</button>
          <button type="button" class="btn ${okClass}" data-ok>${esc(okText)}</button>
        </div>
      </div>`;
    const form = back.querySelector("form");
    const close = (v) => { back.remove(); document.removeEventListener("keydown", onKey); resolve(v); };
    const ok = () => {
      const v = collect ? collect(form) : true;
      if (v !== undefined && v !== null && v !== false) close(v);
    };
    const onKey = (e) => { if (e.key === "Escape") close(null); };
    back.addEventListener("click", (e) => { if (e.target === back) close(null); });
    back.querySelector("[data-cancel]").onclick = () => close(null);
    back.querySelector("[data-ok]").onclick = ok;
    form.addEventListener("submit", (e) => { e.preventDefault(); ok(); });
    document.addEventListener("keydown", onKey);
    document.body.append(back);
    (form.querySelector(focus || "input,select,textarea") || back.querySelector("[data-ok]")).focus();
  });
}
