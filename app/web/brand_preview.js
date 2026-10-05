// Estudio de marca · vista previa (Fase 4). Pantallas con datos de muestra.
// - Ningún botón ni formulario hace nada (no se puede entrar a ningún panel).
// - En el estudio (dentro de la consola, mismo origen): recibe los tokens sin
//   guardar, pide el CSS al generador del servidor y lo aplica al instante;
//   al tocar una pieza le avisa a la consola cuál fue.
// - En el enlace para el cliente: solo muestra; no escucha mensajes.
(() => {
  "use strict";

  const dataEl = document.getElementById("cxPreviewData");
  let data = {};
  try { data = JSON.parse(dataEl ? dataEl.textContent : "{}"); } catch (_) { data = {}; }
  const brand = () => window.CxPanelBrand || null;
  const style = document.getElementById("cxBrandTheme");
  const hasBranding = (b) => b && typeof b === "object" && Object.keys(b).length > 0;
  if (brand() && hasBranding(data.branding)) brand().apply(data.branding);
  // Portal: el logo de la marca en la muestra (misma ruta del mismo origen).
  function setLogo(url) {
    document.querySelectorAll("[data-brand=\"portal.logo\"]").forEach((box) => {
      box.textContent = "";
      if (url && (/^\/brand-media\/[0-9a-f-]{36}\/[0-9a-f-]{36}\.webp$/.test(url) || /^data:image\/(png|jpeg|webp);base64,[A-Za-z0-9+/=]+$/.test(url))) {
        const img = document.createElement("img");
        img.src = url;
        img.alt = "";
        img.className = "cxpv-logo";
        box.appendChild(img);
      } else {
        box.textContent = "C";
      }
    });
  }
  if (data.logo) setLogo(data.logo);

  // Nada navega ni envía: es solo una vista previa.
  document.addEventListener("submit", (event) => event.preventDefault(), true);
  document.addEventListener("keydown", (event) => { if (event.key === "Enter" && event.target && event.target.tagName === "INPUT") event.preventDefault(); }, true);

  const inStudio = data.mode === "studio" && window.parent && window.parent !== window;
  let types = {};
  const post = (message) => { if (inStudio) window.parent.postMessage(message, window.location.origin); };

  function targetOf(el) {
    const piece = el.closest && el.closest("[data-brand]");
    if (piece) return { piece: piece.getAttribute("data-brand") };
    for (let node = el; node && node !== document.body; node = node.parentElement) {
      for (const [type, selectors] of Object.entries(types)) {
        if (selectors.some((sel) => { try { return node.matches(sel); } catch (_) { return false; } })) return { component: type };
      }
    }
    return { background: data.screen };
  }

  function elementsFor(target) {
    if (!target) return [];
    if (target.piece) return Array.from(document.querySelectorAll(`[data-brand="${CSS.escape(target.piece)}"]`));
    if (target.component && types[target.component]) {
      return types[target.component].flatMap((sel) => { try { return Array.from(document.querySelectorAll(sel)); } catch (_) { return []; } });
    }
    return [];
  }

  function highlight(target) {
    document.querySelectorAll(".cxpv-selected").forEach((el) => el.classList.remove("cxpv-selected"));
    elementsFor(target).forEach((el) => el.classList.add("cxpv-selected"));
  }

  function setState(target, state) {
    document.querySelectorAll("[data-cx-state]").forEach((el) => el.removeAttribute("data-cx-state"));
    if (state === "hover" || state === "active") elementsFor(target).forEach((el) => el.setAttribute("data-cx-state", state));
  }

  document.addEventListener("click", (event) => {
    if (event.target && event.target.closest && event.target.closest("a.cxpv-link")) return;  // cambiar de pantalla en el enlace
    event.preventDefault();
    event.stopPropagation();
    if (!inStudio) return;
    const target = targetOf(event.target);
    highlight(target);
    post({ type: "select", target });
  }, true);

  let seq = 0;
  async function render(tokens) {
    const mine = ++seq;
    try {
      const response = await fetch(`/admin-v2/api/brand/${encodeURIComponent(data.company_id)}/render`, {
        method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ tokens, screen: data.screen }),
      });
      const body = await response.json().catch(() => ({}));
      if (mine !== seq) return;
      if (!response.ok) { post({ type: "error", detail: body.detail || `Respuesta ${response.status}` }); return; }
      if (style) style.textContent = String(body.css || "");
      if (brand() && body.branding && data.branding) brand().apply(body.branding);
      if (document.querySelector("[data-brand=\"portal.logo\"]")) setLogo(body.logo || "");
      post({ type: "rendered" });
    } catch (_) {
      post({ type: "error", detail: "No se pudo actualizar la vista previa." });
    }
  }

  if (inStudio) {
    window.addEventListener("message", (event) => {
      if (event.origin !== window.location.origin || event.source !== window.parent) return;
      const m = event.data || {};
      if (m.type === "types" && m.types && typeof m.types === "object") types = m.types;
      else if (m.type === "tokens" && m.tokens) render(m.tokens);
      else if (m.type === "highlight") highlight(m.target);
      else if (m.type === "state") setState(m.target, m.state);
      else if (m.type === "lite") document.documentElement.classList.toggle("cx-lite", m.on === true);
    });
    post({ type: "ready", screen: data.screen });
  }
})();
