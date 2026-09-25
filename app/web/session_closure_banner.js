/* CLONEXA 048Q: aviso del corte diario en los mini paneles (todas las empresas).
 *
 * Si el sistema cerro un turno de la persona logueada (corte diario o cierre
 * automatico), muestra un recuadro para PROPONER su hora real de salida. La
 * hora queda "declarada por el empleado" y no cuenta para el pago hasta que
 * el administrador la confirme desde el Dashboard.
 *
 * Uso: <script src="/client-static/session_closure_banner.js"
 *              data-token-keys="clonexa_waiter_token_{cid}"></script>
 * {cid} = company_id del link y {type} = panel_type/type del link.
 */
(function () {
  "use strict";
  const script = document.currentScript;
  const params = new URLSearchParams(window.location.search);
  const companyId = params.get("company_id") || params.get("companyId") || "";
  const panelType = (params.get("type") || params.get("panel_type") || "sales").toLowerCase();
  const keys = String((script && script.getAttribute("data-token-keys")) || "")
    .split(",").map((k) => k.trim().replace("{cid}", companyId).replace("{type}", panelType)).filter(Boolean);
  const CHECK_MS = 5 * 60 * 1000;
  let lastToken = "";
  let box = null;

  function readToken() {
    for (const key of keys) {
      for (const store of ["localStorage", "sessionStorage"]) {
        try {
          const value = window[store].getItem(key);
          if (value) return value;
        } catch (_) { /* almacenamiento bloqueado */ }
      }
    }
    return "";
  }

  function esc(value) {
    return String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  function localInput(iso) {
    if (!iso) return "";
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return "";
    return new Intl.DateTimeFormat("sv-SE", {
      timeZone: "America/Bogota", year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false,
    }).format(d).replace(" ", "T");
  }

  async function call(path, options = {}) {
    const res = await fetch(`/api/v1/workforce-sessions/companies/${encodeURIComponent(companyId)}${path}`, {
      ...options,
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${readToken()}` },
    });
    if (!res.ok) throw new Error((await res.text().catch(() => "")) || String(res.status));
    return res.json();
  }

  function html(closures) {
    return `
      <div style="position:fixed;left:12px;right:12px;bottom:12px;z-index:99999;max-width:560px;margin:0 auto;padding:14px 16px;border-radius:16px;background:#2a1d05;border:1px solid #f0b43c;color:#fff;font:14px/1.4 system-ui,sans-serif;box-shadow:0 12px 30px rgba(0,0,0,.45)">
        ${closures.map((item) => `
          <div data-cx-sess-mine="${esc(item.id)}" style="display:grid;gap:8px;margin-bottom:8px">
            <strong>${esc(item.message)}</strong>
            ${item.status === "declared"
              ? `<span>Tu hora declarada: ${esc(localInput(item.declared_end_at).replace("T", " "))}. Falta que el administrador la confirme.</span>`
              : `<span>¿A qué hora saliste realmente? El administrador debe confirmarla antes de que cuente para tu pago.</span>
                 <input type="datetime-local" data-cx-sess-end value="" min="${esc(localInput(item.started_at))}" max="${esc(localInput(item.system_end_at))}" style="min-height:40px;border-radius:10px;padding:6px 10px">
                 <button type="button" data-cx-sess-declare="${esc(item.id)}" style="min-height:40px;border-radius:10px;border:0;background:#f0b43c;color:#1a1204;font-weight:800">Enviar mi hora de salida</button>`}
          </div>
        `).join("")}
        <button type="button" data-cx-sess-hide style="background:none;border:0;color:#f0d7a0;text-decoration:underline">Ocultar</button>
      </div>`;
  }

  async function check() {
    const token = readToken();
    if (!companyId || !token) return;
    lastToken = token;
    let data;
    try {
      data = await call("/closures/mine");
    } catch (_) {
      return;
    }
    const closures = Array.isArray(data && data.closures) ? data.closures : [];
    if (!closures.length) {
      if (box) box.remove();
      box = null;
      return;
    }
    if (!box) {
      box = document.createElement("div");
      box.id = "cxSessionClosureBanner048Q";
      document.body.appendChild(box);
    }
    box.innerHTML = html(closures);
  }

  document.addEventListener("click", async (event) => {
    if (!box || !box.contains(event.target)) return;
    if (event.target.closest("[data-cx-sess-hide]")) {
      box.remove();
      box = null;
      return;
    }
    const button = event.target.closest("[data-cx-sess-declare]");
    if (!button) return;
    const row = button.closest("[data-cx-sess-mine]");
    const value = row && row.querySelector("[data-cx-sess-end]") ? row.querySelector("[data-cx-sess-end]").value : "";
    if (!value) return;
    button.disabled = true;
    try {
      await call(`/closures/${encodeURIComponent(button.getAttribute("data-cx-sess-declare"))}/declare`, {
        method: "POST",
        body: JSON.stringify({ end_at: value }),
      });
    } catch (_) {
      button.disabled = false;
      return;
    }
    await check();
  });

  window.setInterval(() => {
    if (readToken() !== lastToken) check();
  }, 5000);
  window.setInterval(check, CHECK_MS);
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", check);
  else check();
})();
