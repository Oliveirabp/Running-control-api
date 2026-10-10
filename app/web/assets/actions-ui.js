// Formulário de ação (PDCA) compartilhado entre Indicadores ("+ Ação") e Plano de ação.
import { api, auth, esc, toast, toastError } from "./api.js";

export const ETAPAS = ["Planejar", "Executar", "Verificar", "Agir", "Concluída"];

/** Administrador logado? (token válido no sessionStorage) */
export async function currentAdmin() {
  if (!auth.get()) return null;
  try { return await api("/auth/me", { admin: true }); } catch { return null; }
}

const lineLabel = (l) => (l || "").replace(/^LINHA/, "Linha");

/**
 * Abre o formulário. `a` pode ser uma ação existente (edição) ou um rascunho com
 * { origem, problema, linha }. Resolve com a ação salva, `"deleted"` ou null.
 */
export function actionForm(a = {}, lines = []) {
  const editing = Boolean(a.id);
  const today = new Date();
  const in14 = new Date(today.getTime() + 14 * 864e5).toISOString().slice(0, 10);
  return new Promise((resolve) => {
    const back = document.createElement("div");
    back.className = "modal-back";
    back.innerHTML = `
      <div class="modal wide" role="dialog" aria-modal="true" aria-labelledby="a-title">
        <div class="modal-head"><h3 id="a-title">${editing ? "Editar ação" : "Nova ação"}</h3>
          ${a.origem ? `<div class="muted small">Origem: ${esc(a.origem)}</div>` : ""}</div>
        <form class="modal-body form-modal" novalidate>
          <div class="field"><label for="a-prob">Problema</label><textarea class="input" id="a-prob" rows="2" required>${esc(a.problema || "")}</textarea></div>
          <div class="field"><label for="a-acao">Ação (o que será feito)</label><textarea class="input" id="a-acao" rows="2" required>${esc(a.acao || "")}</textarea></div>
          <div class="row2">
            <div class="field"><label for="a-resp">Responsável</label><input class="input" id="a-resp" value="${esc(a.responsavel || "")}" required></div>
            <div class="field"><label for="a-prazo">Prazo</label><input class="input" id="a-prazo" type="date" value="${esc(a.prazo || in14)}" required></div>
          </div>
          <div class="row2">
            <div class="field"><label for="a-linha">Linha</label><select class="select" id="a-linha">
              <option value="">Todas as linhas</option>
              ${lines.map((l) => `<option value="${esc(l)}" ${l === a.linha ? "selected" : ""}>${esc(lineLabel(l))}</option>`).join("")}
            </select></div>
            <div class="field"><label for="a-etapa">Etapa (PDCA)</label><select class="select" id="a-etapa">
              ${ETAPAS.map((e) => `<option ${e === (a.etapa || "Planejar") ? "selected" : ""}>${e}</option>`).join("")}
            </select></div>
          </div>
          <div class="field"><label for="a-res">Resultado obtido <span class="muted">(obrigatório para concluir)</span></label><textarea class="input" id="a-res" rows="2">${esc(a.resultado || "")}</textarea></div>
          <div class="hint err" id="a-err" role="alert"></div>
        </form>
        <div class="modal-foot">
          ${editing ? '<button type="button" class="btn btn-ghost" data-del style="margin-right:auto;color:var(--crit)">Excluir</button>' : ""}
          <button type="button" class="btn btn-ghost" data-cancel>Cancelar</button>
          <button type="button" class="btn btn-primary" data-ok>${editing ? "Salvar" : "Criar ação"}</button>
        </div>
      </div>`;
    const $ = (s) => back.querySelector(s);
    const close = (v) => { back.remove(); document.removeEventListener("keydown", onKey); resolve(v); };
    const onKey = (e) => { if (e.key === "Escape") close(null); };
    document.addEventListener("keydown", onKey);
    back.addEventListener("click", (e) => { if (e.target === back) close(null); });
    $("[data-cancel]").onclick = () => close(null);

    $("[data-ok]").onclick = async () => {
      const body = {
        problema: $("#a-prob").value, acao: $("#a-acao").value, responsavel: $("#a-resp").value,
        prazo: $("#a-prazo").value || null, linha: $("#a-linha").value, etapa: $("#a-etapa").value,
        resultado: $("#a-res").value, origem: a.origem || "",
      };
      $("[data-ok]").disabled = true;
      try {
        const saved = await api(editing ? `/actions/${a.id}` : "/actions", { method: editing ? "PUT" : "POST", body, admin: true });
        toast(editing ? "Ação atualizada." : "Ação criada no Plano de ação.", "ok");
        close(saved);
      } catch (err) {
        $("#a-err").innerHTML = esc(err.message) + (err.errors?.length ? `<br>${err.errors.map(esc).join("<br>")}` : "");
        if (err.status === 401) toastError(err);
      } finally {
        $("[data-ok]").disabled = false;
      }
    };

    if (editing) {
      $("[data-del]").onclick = async () => {
        if (!confirm("Excluir esta ação? Não dá para desfazer.")) return;
        try {
          await api(`/actions/${a.id}`, { method: "DELETE", admin: true });
          toast("Ação excluída.", "ok");
          close("deleted");
        } catch (err) { toastError(err); }
      };
    }
    document.body.append(back);
    $(a.problema ? "#a-acao" : "#a-prob").focus();
  });
}
