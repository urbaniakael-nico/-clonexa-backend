// Consola v2+ · Buscador Ctrl+K. Busca empresas, secciones, módulos, paquetes
// e interruptores (cuando exista su registro: window.CxSwitchRegistry), con
// acciones rápidas: abrir Ficha, entrar como empresa, copiar links, ir a una
// sección o a un interruptor. Ignora tildes, tolera coincidencias parciales y
// se maneja con teclado (↑ ↓ Enter, Ctrl+Enter para la segunda acción, Esc).
// Solo lee: no guarda nada. Sin estilos ni scripts en línea.
(() => {
  "use strict";

  const h = (v) => String(v ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
  const fold = (v) => String(v ?? "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
  const arr = (v) => (Array.isArray(v) ? v : []);
  const KIND_LABEL = { company: "Empresa", section: "Sección", module: "Módulo", package: "Paquete", switch: "Interruptor" };
  const MAX = 30;

  // ---------------------------------------------------------- búsqueda
  // Puntaje: todas las palabras deben aparecer (al inicio de palabra vale más);
  // si no, se acepta una subsecuencia ("tm" -> The Time Machine).
  function score(query, text, title) {
    const q = fold(query);
    if (!q) return 1;
    const hay = fold(text);
    const words = q.split(" ");
    let total = 0;
    for (const w of words) {
      if (new RegExp(`(^| )${w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}`).test(hay)) total += 3;
      else if (w.length >= 3 && (hay.includes(w) || hay.replace(/ /g, "").includes(w))) total += 2;
      else return loose(q.replace(/ /g, ""), fold(title || text)) ? 0.5 : 0;
    }
    const name = fold(title || "");
    if (name.startsWith(q)) total += 4;
    else if (name && words.every((w) => name.includes(w))) total += 3;
    return total;
  }
  // Respaldo: iniciales ("tm" -> The Time Machine) o, desde 4 letras, letras en orden.
  function loose(needle, hay) {
    const initials = hay.split(" ").map((w) => w[0] || "").join("");
    if (needle.length > 1 && initials.includes(needle)) return true;
    return needle.length >= 4 && subsequence(needle, hay.replace(/ /g, ""));
  }
  function subsequence(needle, hay) {
    let i = 0;
    for (const ch of hay) if (ch === needle[i]) i += 1;
    return needle.length > 1 && i === needle.length;
  }

  function search(index, query) {
    return index.map((item) => ({ item, s: score(query, item.text, item.title) }))
      .filter((r) => r.s > 0)
      .sort((a, b) => b.s - a.s || a.item.order - b.item.order || a.item.title.localeCompare(b.item.title, "es"))
      .slice(0, MAX).map((r) => r.item);
  }

  // ------------------------------------------------------------ índice
  function buildIndex(data) {
    const out = [];
    const push = (kind, title, subtitle, text, actions, order) => out.push({ kind, title, subtitle, text: `${title} ${subtitle} ${text || ""} ${KIND_LABEL[kind]}`, actions, order });
    Object.entries(data.views || {}).forEach(([key, label], i) => push("section", label, "Ir a la sección", key, [{ id: "go", label: "Abrir", view: key }], 10 + i));
    // La auditoría vive en Salud y seguridad (ya no tiene menú propio).
    push("section", "Auditoría", "Últimos registros, en Salud y seguridad", "registros historial cambios", [{ id: "go", label: "Abrir", view: "health", focus: "audit" }], 9);
    const seen = new Set();
    arr(data.companies).forEach((c) => {
      if (!c || !c.id || seen.has(c.id)) return;
      seen.add(c.id);
      const archived = ["archived", "deleted"].includes(String(c.status || "").toLowerCase());
      push("company", c.name || c.slug || c.id, `${c.slug || ""}${c.kind ? ` · ${c.kind}` : ""}${archived ? " · archivada" : ""}`, `${c.slug} ${c.id}`, [
        { id: "ficha", label: "Abrir Ficha", companyId: c.id },
        { id: "enter", label: "Entrar como empresa", companyId: c.id },
        { id: "links", label: "Copiar links", companyId: c.id },
      ], archived ? 40 : 20);
    });
    arr(data.modules).forEach((m) => push("module", m.name || m.code, m.code, `${m.category || ""} ${m.description || ""}`, [{ id: "module", label: "Ver en el catálogo", code: m.code, name: m.name || m.code }], 50));
    arr(data.packages).forEach((p) => push("package", p.name || p.code, p.code, p.description, [{ id: "package", label: "Editar paquete", packageId: p.id }], 60));
    arr(data.switches).forEach((s) => push("switch", s.label || s.key, `${s.group || ""} · ${s.module || ""}`, `${s.key} ${s.description || ""}`, [{ id: "switch", label: "Ir al interruptor", key: s.key }], 30));
    return out;
  }

  // ------------------------------------------------------------ estado
  const model = { open: false, query: "", active: 0, results: [], data: { views: {}, companies: [], modules: null, packages: null }, loading: false };
  let host = null;

  function plus() { return window.CxConsolePlus || null; }

  async function getJson(url) {
    const r = await fetch(url, { credentials: "same-origin", headers: { Accept: "application/json" } });
    if (!r.ok) throw new Error(`Respuesta ${r.status}`);
    return r.json();
  }

  async function loadData() {
    const p = plus();
    model.data.views = (p && p.VIEWS) || {};
    const overview = p && p.state && p.state.overview;
    const companies = [...arr(overview && overview.companies)];
    const loaded = window.CxConsoleCompanies && window.CxConsoleCompanies.model.companies;
    if (arr(loaded).length) companies.push(...loaded);
    model.data.companies = companies;
    model.data.switches = window.CxSwitchRegistry ? arr(window.CxSwitchRegistry.list()) : [];
    refresh();
    if (model.loading) return;
    model.loading = true;
    try {
      const [all, modules, packages, switches] = await Promise.all([
        arr(loaded).length ? loaded : getJson("/api/v1/companies").catch(() => []),
        model.data.modules || getJson("/api/v1/modules").catch(() => []),
        model.data.packages || getJson("/api/v1/packages").catch(() => []),
        window.CxSwitchRegistry ? window.CxSwitchRegistry.load().then(() => window.CxSwitchRegistry.list()).catch(() => []) : [],
      ]);
      model.data.switches = arr(switches);
      model.data.companies = [...companies, ...arr(all)];
      model.data.modules = arr(modules);
      model.data.packages = arr(packages);
    } finally {
      model.loading = false;
      refresh();
    }
  }

  function refresh() {
    model.results = search(buildIndex(model.data), model.query);
    if (model.active >= model.results.length) model.active = Math.max(0, model.results.length - 1);
    draw(false);
  }

  // ------------------------------------------------------------ dibujo
  function panel() {
    const rows = model.results;
    return `<div class="vp-modal vp-palette" data-vpp-backdrop>
      <div class="vp-panel vp-palette-card" role="dialog" aria-modal="true" aria-label="Buscar u ordenar">
        <input class="vp-search vp-palette-input" type="search" placeholder="Busca una empresa, sección, módulo, paquete o interruptor…" value="${h(model.query)}"
          data-vpp-input role="combobox" aria-expanded="true" aria-controls="vpPaletteList" aria-activedescendant="${rows.length ? `vpp-opt-${model.active}` : ""}" autocomplete="off">
        <ul class="vp-palette-list" id="vpPaletteList" role="listbox">${rows.map((r, i) => `
          <li id="vpp-opt-${i}" role="option" aria-selected="${i === model.active}" class="vp-palette-row ${i === model.active ? "is-active" : ""}" data-vpp-row="${i}">
            <span class="vp-palette-kind">${h(KIND_LABEL[r.kind])}</span>
            <span class="vp-palette-text"><b>${h(r.title)}</b><small>${h(r.subtitle)}</small></span>
            <span class="vp-palette-actions">${r.actions.map((a, j) => `<button class="vp-btn vp-btn-sm ${j === 0 ? "vp-btn-primary" : ""}" type="button" tabindex="-1" data-vpp-act="${i}:${j}">${h(a.label)}</button>`).join("")}</span>
          </li>`).join("") || `<li class="vp-empty">${model.loading ? "Cargando…" : "Sin resultados."}</li>`}</ul>
        <p class="vp-palette-help"><span class="vp-kbd">↑ ↓</span> moverse · <span class="vp-kbd">Enter</span> primera acción · <span class="vp-kbd">Ctrl Enter</span> segunda · <span class="vp-kbd">Esc</span> cerrar</p>
      </div></div>`;
  }

  function draw(focus) {
    if (!model.open || typeof document.createElement !== "function") return;
    if (!host) { host = document.createElement("div"); host.id = "vpPalette"; document.body.appendChild(host); }
    const caret = host.querySelector && host.querySelector("[data-vpp-input]") ? host.querySelector("[data-vpp-input]").selectionStart : model.query.length;
    host.innerHTML = panel();
    const input = host.querySelector("[data-vpp-input]");
    if (input) { input.focus(); try { input.setSelectionRange(caret, caret); } catch (_) {} }
    const active = host.querySelector(".vp-palette-row.is-active");
    if (active && active.scrollIntoView) active.scrollIntoView({ block: "nearest" });
    if (focus === false) return;
  }

  function open() {
    model.open = true;
    model.query = "";
    model.active = 0;
    loadData();
    draw(true);
  }
  function close() {
    model.open = false;
    if (host) { host.remove(); host = null; }
  }

  // ------------------------------------------------------------ acciones
  async function copyLinks(companyId) {
    const C = window.CxConsoleCompany;
    const company = model.data.companies.find((c) => c.id === companyId) || { id: companyId };
    const modules = await getJson(`/api/v1/companies/${companyId}/modules?enabled_only=false`).catch(() => []);
    const links = C ? C.accessLinks(company, modules) : [];
    const text = links.map((l) => `${l.title}: ${l.href}`).join("\n");
    try { await navigator.clipboard.writeText(text); toast(`${links.length} links de ${company.name || "la empresa"} copiados.`); }
    catch (_) { toast("No se pudo copiar."); }
  }

  function toast(message) { const p = plus(); if (p && p.toast) p.toast(message); }

  function run(action) {
    const p = plus();
    if (!action) return;
    if (action.id === "go" && p) { close(); p.setView(action.view, action.focus ? { focus: action.focus } : undefined); return; }
    if (action.id === "ficha") { close(); window.location.hash = `#empresa/${encodeURIComponent(action.companyId)}`; return; }
    if (action.id === "enter") { close(); window.open(`/client?company_id=${encodeURIComponent(action.companyId)}`, "_blank", "noopener"); return; }
    if (action.id === "links") { copyLinks(action.companyId); return; }
    if (action.id === "module" && p) {
      close();
      const cat = window.CxConsoleCatalog;
      if (cat) { cat.model.tab = "modulos"; cat.model.builder = null; cat.model.modQuery = action.name; }
      p.setView("catalog", { tab: "modulos" });
      return;
    }
    if (action.id === "package" && p) { close(); p.setView("catalog", { tab: "paquetes", editPackage: action.packageId }); return; }
    if (action.id === "switch" && p) { close(); p.setView("switches", { key: action.key }); }
  }

  // ------------------------------------------------------------ eventos
  function onKey(event) {
    const key = String(event.key || "");
    if ((event.ctrlKey || event.metaKey) && key.toLowerCase() === "k") { event.preventDefault(); if (model.open) close(); else open(); return; }
    if (!model.open) return;
    if (key === "Escape") { event.preventDefault(); close(); return; }
    if (key === "ArrowDown" || key === "ArrowUp") {
      event.preventDefault();
      const n = model.results.length;
      if (n) model.active = (model.active + (key === "ArrowDown" ? 1 : n - 1)) % n;
      draw(true);
      return;
    }
    if (key === "Enter") {
      event.preventDefault();
      const row = model.results[model.active];
      if (row) run(row.actions[event.ctrlKey || event.metaKey ? Math.min(1, row.actions.length - 1) : 0]);
    }
  }

  function onInput(event) {
    if (!model.open || !event.target || !event.target.matches || !event.target.matches("[data-vpp-input]")) return;
    model.query = event.target.value;
    model.active = 0;
    refresh();
  }

  function onClick(event) {
    const t = event.target;
    if (!t || !t.closest) return;
    if (t.closest("[data-vp-search]")) { event.preventDefault(); open(); return; }
    if (!model.open) return;
    const act = t.closest("[data-vpp-act]");
    if (act) { const [i, j] = act.getAttribute("data-vpp-act").split(":").map(Number); run(model.results[i] && model.results[i].actions[j]); return; }
    const row = t.closest("[data-vpp-row]");
    if (row) { const i = Number(row.getAttribute("data-vpp-row")); run(model.results[i] && model.results[i].actions[0]); return; }
    if (t.matches && t.matches("[data-vpp-backdrop]")) close();
  }

  if (typeof document.addEventListener === "function") {
    document.addEventListener("keydown", onKey);
    document.addEventListener("input", onInput);
    document.addEventListener("click", onClick);
  }

  window.CxConsolePalette = { open, close, search, score, buildIndex, run, model, panel };
})();
