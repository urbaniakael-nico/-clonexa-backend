// Consola v2+ · Menú video (solo Admin V2): de la carta en PDF o fotos a la
// carta en video del QR, en 5 pasos: 1. Empresa, 2. Importar (n8n + Claude lee
// la carta; tabla editable, o a mano), 3. Fotos por plato (arrastrar varias,
// emparejadas por nombre de archivo), 4. Remasterizar y clips (antes/después,
// estilos, Rehacer y vista en un celular de muestra), 5. Publicar = combinar.
// Fotos y videos se hacen en el servidor con ffmpeg/Pillow (sin IA).
// Sin estilos en línea (CSP de v2+): todo por clase.
(() => {
  "use strict";

  const API = "/admin-v2/api/menu-video";
  const h = (v) => String(v ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
  const arr = (v) => (Array.isArray(v) ? v : []);
  const enc = encodeURIComponent;
  const STEPS = ["Empresa", "Importar", "Fotos por plato", "Remasterizar y clips", "Publicar"];
  // 058A: estilos de la foto (Camino 2), fondo y velocidad (Camino 1): los mismos del servidor.
  const STYLES = { vida: "Vida", zoom: "Acercamiento", giro: "Giro suave", paneo: "Paneo", brillo: "Brillo", auto: "Automático" };
  const BACKGROUNDS = { desenfocar: "Desenfocar fondo", oscurecer: "Oscurecer fondo", ninguno: "Sin cambios" };
  const SPEEDS = { lento: "Más lento", normal: "Normal", rapido: "Más rápido" };
  const JOB = { en_cola: "En cola", procesando: "Creando…", listo: "Listo", error: "Error", sin_video: "Sin clip", sin_foto: "Sin foto" };
  const FIELDS = [["categoria", "Categoría"], ["subcategoria", "Subcategoría"], ["nombre", "Plato"], ["descripcion", "Descripción"], ["precio", "Precio"], ["opciones", "Opciones"]];

  async function request(url, options = {}) {
    const isForm = typeof FormData !== "undefined" && options.body instanceof FormData;
    const response = await fetch(url, { credentials: "same-origin", ...options,
      headers: { Accept: "application/json", ...(options.body && !isForm ? { "Content-Type": "application/json" } : {}), ...(options.headers || {}) } });
    const data = await response.json().catch(() => ({}));
    if (response.status === 401) { window.location.href = "/admin-v2plus/login"; throw new Error("Sesión vencida."); }
    if (!response.ok) {
      const d = data && data.detail;
      throw new Error((d && typeof d === "object" ? (d.message || JSON.stringify(d)) : d) || `Respuesta ${response.status}`);
    }
    return data;
  }
  const api = {
    health: () => request(`${API}/health`),
    companies: () => request(`${API}/companies`),
    company: (id) => request(`${API}/${enc(id)}`),
    importFiles: (id, form) => request(`${API}/${enc(id)}/imports`, { method: "POST", body: form }),
    imp: (id, iid) => request(`${API}/${enc(id)}/imports/${enc(iid)}`),
    saveTable: (id, iid, table) => request(`${API}/${enc(id)}/imports/${enc(iid)}/table`, { method: "PUT", body: JSON.stringify({ table }) }),
    photos: (id, iid, form) => request(`${API}/${enc(id)}/imports/${enc(iid)}/photos`, { method: "POST", body: form }),
    assign: (id, iid, aid, body) => request(`${API}/${enc(id)}/imports/${enc(iid)}/photos/${enc(aid)}`, { method: "PUT", body: JSON.stringify(body) }),
    process: (id, iid, body) => request(`${API}/${enc(id)}/imports/${enc(iid)}/process`, { method: "POST", body: JSON.stringify(body) }),
    changePhoto: (id, iid, ref, role, file) => { const f = new FormData(); f.append("file", file, file.name); return request(`${API}/${enc(id)}/imports/${enc(iid)}/dish/${enc(ref)}/photo/${enc(role)}`, { method: "POST", body: f }); },
    removePhoto: (id, iid, ref, role) => request(`${API}/${enc(id)}/imports/${enc(iid)}/dish/${enc(ref)}/photo/${enc(role)}`, { method: "DELETE" }),
    restorePhoto: (id, iid, ref, role, body) => request(`${API}/${enc(id)}/imports/${enc(iid)}/dish/${enc(ref)}/photo/${enc(role)}/restore`, { method: "POST", body: JSON.stringify(body) }),
    removeVideo: (id, iid, ref) => request(`${API}/${enc(id)}/imports/${enc(iid)}/dish/${enc(ref)}/video`, { method: "DELETE" }),
    regenerate: (id) => request(`${API}/${enc(id)}/regenerate`, { method: "POST", body: "{}" }),
    options: (id, iid, ref, body) => request(`${API}/${enc(id)}/imports/${enc(iid)}/dish/${enc(ref)}/options`, { method: "POST", body: JSON.stringify(body) }),
    choose: (id, iid, ref, use) => request(`${API}/${enc(id)}/imports/${enc(iid)}/dish/${enc(ref)}/choose`, { method: "POST", body: JSON.stringify({ use_remaster: use }) }),
    plan: (id, iid) => request(`${API}/${enc(id)}/imports/${enc(iid)}/plan`),
    publish: (id, iid) => request(`${API}/${enc(id)}/imports/${enc(iid)}/publish`, { method: "POST", body: "{}" }),
  };

  // ------------------------------------------------------------ estado
  const model = { confirm: null, undo: null, paths: {}, opts: {}, step: 1, companies: null, health: null, companyId: "", data: null, table: null, dirty: false, busy: "", error: "",
    notice: "", plan: null, result: null, preview: "", styles: {}, files: [] };
  let ctx = null;
  let bound = false;
  let timer = null;

  function money(value) {
    if (value === null || value === undefined || value === "") return "—";
    const n = Number(value);
    try { return `$${n.toLocaleString("es-CO", { maximumFractionDigits: 2 })}`; } catch (_) { return `$${n}`; }
  }

  function imp() { return model.data && model.data.import; }
  function dishes() { return arr(model.table && model.table.platos); }
  function media(ref) { return (model.data && model.data.media && model.data.media[ref]) || null; }
  function job(ref) { return (model.data && model.data.jobs && model.data.jobs[ref]) || null; }
  function status(ref) {
    const j = job(ref);
    const m = media(ref);
    if (j && (j.status === "en_cola" || j.status === "procesando")) return j.status;
    if (j && j.status === "error" && (!m || m.status === "error")) return "error";
    return m ? m.status : "sin_foto";
  }
  function busyNow() { return dishes().some((d) => ["en_cola", "procesando"].includes(status(d.ref))) || (imp() && imp().status === "leyendo"); }

  // ------------------------------------------------------------ vistas
  function stepsHtml() {
    return `<ol class="vp-mv-steps" aria-label="Pasos">${STEPS.map((label, i) => {
      const n = i + 1;
      const can = n === 1 || (model.companyId && (n === 2 || (imp() && dishes().length)));
      return `<li><button type="button" class="vp-chip ${model.step === n ? "is-active" : ""}" data-mv-step="${n}" ${can ? "" : "disabled"}>${n}. ${h(label)}</button></li>`;
    }).join("")}</ol>`;
  }

  function companyStep() {
    const list = arr(model.companies);
    const hl = model.health;
    return `
      <section class="vp-panel vp-section">
        <h2>1. Elige la empresa</h2>
        <p class="vp-mv-muted">Solo empresas con el módulo de restaurante (Carta). La carta en video se enciende por empresa en Interruptores (<b>carta_video</b>).</p>
        ${hl ? `<p class="vp-mv-health">ffmpeg <b>${h(hl.ffmpeg || "no instalado")}</b> · Pillow ${h(hl.pillow)} · bucket ${hl.bucket ? "listo" : "sin configurar"} · token de n8n ${hl.token ? "listo" : "falta"}${hl.queue && hl.queue.jobs ? ` · ${h(hl.queue.jobs)} clips en 30 días, promedio ${h(Math.round((hl.queue.avg_total_ms || 0) / 100) / 10)} s y ${h(Math.round((hl.queue.avg_clip_bytes || 0) / 1024))} KB` : ""}</p>` : ""}
        ${model.companies === null ? `<p class="vp-loading">Cargando empresas…</p>` : list.length ? `<div class="vp-mv-companies">${list.map((c) => `
          <button type="button" class="vp-panel vp-mv-company ${c.id === model.companyId ? "is-active" : ""}" data-mv-company="${h(c.id)}">
            <strong>${h(c.name)}</strong>
            <span>${h(c.dishes)} platos · ${c.kind === "demo" ? "Demo" : "Registrada"}</span>
            <span class="vp-mv-pill ${c.carta_video ? "is-on" : ""}">${c.carta_video ? "Carta en video encendida" : "Carta en video apagada"}</span>
            <small>Cupo mensual: ${h(c.quota_new)} nuevos · ${h(c.quota_changes)} cambios</small>
          </button>`).join("")}</div>` : `<div class="vp-empty">Ninguna empresa tiene el módulo Carta.</div>`}
      </section>`;
  }

  function catsHtml() {
    const cats = [...new Set(dishes().map((d) => d.categoria).filter(Boolean))];
    if (!cats.length) return "";
    return `<div class="vp-mv-cats"><span class="vp-mv-muted">Categorías de la importación:</span>${cats.map((c) => {
      const key = `cat|${c}`;
      if (model.confirm && model.confirm.key === key) {
        const n = dishes().filter((d) => d.categoria === c).length;
        return `<span class="vp-mv-confirm" role="alert">¿Quitar ${h(c)} y sus ${h(n)} platos de la importación?
          <button type="button" class="vp-btn vp-btn-sm vp-btn-danger" data-mv-remove-yes>Quitar</button>
          <button type="button" class="vp-btn vp-btn-sm" data-mv-remove-no>Cancelar</button></span>`;
      }
      return `<span class="vp-mv-pill">${h(c)} <button type="button" class="vp-mv-x" data-mv-cat-del="${h(c)}" aria-label="Quitar la categoría ${h(c)}">✕</button></span>`;
    }).join("")}</div>`;
  }

  function tableHtml() {
    const rows = dishes();
    return `
      <div class="vp-table-wrap vp-mv-table-wrap">
        <table class="vp-table vp-table-compact vp-mv-table">
          <thead><tr>${FIELDS.map(([, label]) => `<th scope="col">${h(label)}</th>`).join("")}<th scope="col"><span class="vp-sr">Quitar</span></th></tr></thead>
          <tbody>${rows.map((d, i) => `<tr>${FIELDS.map(([key, label]) => `<td><input class="vp-search vp-mv-cell vp-mv-cell-${key}" aria-label="${h(label)} de la fila ${i + 1}" data-mv-cell="${i}:${key}" value="${h(d[key] ?? "")}" ${key === "precio" ? 'inputmode="decimal"' : ""}></td>`).join("")}
            <td><button type="button" class="vp-btn vp-btn-sm" data-mv-row-del="${i}" aria-label="Quitar ${h(d.nombre)}">✕</button></td></tr>`).join("")}</tbody>
        </table>
      </div>
      ${catsHtml()}
      <div class="vp-head-actions">
        <button type="button" class="vp-btn" data-mv-row-add>+ Agregar plato</button>
        <button type="button" class="vp-btn vp-btn-primary" data-mv-table-save ${model.busy ? "disabled" : ""}>${model.dirty ? "Guardar tabla" : "Tabla guardada"}</button>
        ${rows.length ? `<button type="button" class="vp-btn" data-mv-step="3">Seguir a fotos →</button>` : ""}
      </div>`;
  }

  function importStep() {
    const current = imp();
    const reading = current && current.status === "leyendo";
    const failed = current && current.status === "error";
    return `
      <section class="vp-panel vp-section">
        <h2>2. Importar la carta</h2>
        <form class="vp-mv-import" data-mv-import>
          <label class="vp-mv-drop" data-mv-drop="import">
            <input type="file" name="files" multiple accept="application/pdf,image/jpeg,image/png,image/webp" data-mv-import-files>
            <span><b>Sube el PDF o las fotos de la carta</b> (hasta 10 archivos) o arrástralos aquí.</span>
            ${model.files.length ? `<small>${h(model.files.map((f) => f.name).join(", "))}</small>` : ""}
          </label>
          <label class="vp-field vp-mv-link"><span>…o pega un enlace (https)</span><input class="vp-search" name="link" type="url" placeholder="https://restaurante.com/carta.pdf"></label>
          <div class="vp-head-actions">
            <button class="vp-btn vp-btn-primary" type="submit" ${model.busy ? "disabled" : ""}>Leer la carta</button>
            <button class="vp-btn" type="button" data-mv-manual ${model.busy ? "disabled" : ""}>Llenar a mano</button>
          </div>
        </form>
        ${reading ? `<div class="vp-mv-reading" role="status"><span class="vp-mv-spinner" aria-hidden="true"></span> Leyendo la carta… (Claude por n8n; tarda menos de un minuto)</div>` : ""}
        ${failed ? `<div class="vp-alert vp-alert-warn" role="alert"><strong>No se pudo leer</strong><span>${h(current.error || "")}</span><button class="vp-btn vp-btn-sm" type="button" data-mv-manual>Llenar a mano</button></div>` : ""}
        ${current && !reading ? `<h3 class="vp-mv-sub">Revisa y corrige antes de seguir · ${h(dishes().length)} platos</h3>${tableHtml()}` : ""}
      </section>`;
  }

  function thumb(url, label) {
    return url ? `<img class="vp-mv-thumb" src="${h(url)}" alt="${h(label)}" loading="lazy">` : `<span class="vp-mv-thumb is-empty">${h(label)}</span>`;
  }

  // 058A: 2 caminos por plato. Guía del video (Camino 1) y de la foto (Camino 2).
  const VIDEO_GUIDE = "Pon el plato sobre una base giratoria o camina alrededor, 5 a 10 segundos, celular vertical, buena luz, plato completo en cuadro.";
  function guideHtml(path = "foto") {
    if (path === "video") {
      return `<div class="vp-mv-guide">
        <svg viewBox="0 0 300 92" role="img" aria-label="El plato sobre una base giratoria y el celular vertical dando la vuelta">
          <g fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round">
            <ellipse cx="110" cy="60" rx="46" ry="14"/><ellipse cx="110" cy="54" rx="28" ry="8"/><path d="M60 36q50-26 100 0M152 30l8 6-9 4"/>
            <rect x="210" y="18" width="34" height="60" rx="6"/><circle cx="227" cy="70" r="3"/>
          </g>
          <g fill="currentColor" font-size="11" font-family="inherit" text-anchor="middle"><text x="110" y="88">Base giratoria o alrededor</text><text x="227" y="12">Vertical</text></g>
        </svg>
        <p><b>${h(VIDEO_GUIDE)}</b> MP4 o MOV del celular (incluido el de iPhone), máximo 30 s y 150 MB. Se quita el sonido.</p>
      </div>`;
    }
    return `<div class="vp-mv-guide">
      <svg viewBox="0 0 300 92" role="img" aria-label="Foto principal: el plato completo de frente a 45 grados, con espacio alrededor">
        <g fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round">
          <ellipse cx="150" cy="58" rx="40" ry="15"/><ellipse cx="150" cy="56" rx="23" ry="8"/><path d="M108 14l16 16M118 30h6v-6"/>
          <rect x="92" y="30" width="116" height="48" rx="6" stroke-dasharray="4 4"/>
        </g>
        <g fill="currentColor" font-size="11" font-family="inherit" text-anchor="middle"><text x="150" y="90">Plato completo, a 45°, con aire</text></g>
      </svg>
      <p><b>Una foto principal</b> (la que se anima): plato completo, de frente a 45° y con espacio alrededor. Las demás van a <b>Más fotos (galería)</b> y se ven en el botón Detalle: nunca se mezclan en el video.</p>
    </div>`;
  }

  const ROLE_WORD = { main: "foto principal", gallery: "foto de la galería", source: "el video del plato" };
  const roleWord = (role) => ROLE_WORD[String(role).split(":")[0]] || "foto";

  function confirmHtml(question) {
    return `<div class="vp-mv-confirm" role="alert"><span>${h(question)}</span>
      <button type="button" class="vp-btn vp-btn-sm vp-btn-danger" data-mv-remove-yes>Quitar</button>
      <button type="button" class="vp-btn vp-btn-sm" data-mv-remove-no>Cancelar</button></div>`;
  }

  // Un espacio: Cambiar / Quitar con confirmación en la misma pantalla y Deshacer (10 s).
  function slotHtml(d, role, label, url, opts = {}) {
    const key = `${d.ref}|${role}`;
    const confirming = model.confirm && model.confirm.key === key;
    const undo = model.undo && model.undo.key === key && Date.now() < model.undo.until;
    const isVideo = role === "source";
    const accept = isVideo ? "video/mp4,video/quicktime,.mov,.mp4" : "image/jpeg,image/png,image/webp";
    const has = Boolean(url || opts.has);
    const media = isVideo
      ? (has ? `<span class="vp-mv-thumb is-video">▶ Video subido</span>` : `<span class="vp-mv-thumb is-empty">${h(label)}</span>`)
      : thumb(url, label);
    return `<div class="vp-mv-slot ${has ? "has" : ""}">
      <span class="vp-mv-slot-label">${h(label)}</span>
      ${media}
      ${confirming
        ? confirmHtml(`¿Quitar ${roleWord(role)}?`)
        : `<div class="vp-mv-slot-actions">
            <label class="vp-btn vp-btn-sm vp-mv-file">${has ? "Cambiar" : "Subir"}<input type="file" accept="${accept}" data-mv-change="${h(key)}" aria-label="${has ? "Cambiar" : "Subir"} ${h(roleWord(role))} de ${h(d.nombre)}"></label>
            ${has ? `<button type="button" class="vp-btn vp-btn-sm" data-mv-remove="${h(key)}">Quitar</button>` : ""}
          </div>`}
      ${undo ? `<button type="button" class="vp-btn vp-btn-sm vp-mv-undo" data-mv-undo>Deshacer</button>` : ""}
    </div>`;
  }

  function pathOf(d) {
    const m = media(d.ref) || {};
    return model.paths[d.ref] || m.mode || "foto";
  }

  function slotsHtml(d) {
    const m = media(d.ref) || {};
    const path = pathOf(d);
    const tabs = `<div class="vp-mv-paths" role="group" aria-label="Cómo se hace el video de ${h(d.nombre)}">
      <button type="button" class="vp-chip ${path === "video" ? "is-active" : ""}" data-mv-path="${h(d.ref)}|video" aria-pressed="${path === "video"}">Subir video <small>(recomendado: vista 360)</small></button>
      <button type="button" class="vp-chip ${path === "foto" ? "is-active" : ""}" data-mv-path="${h(d.ref)}|foto" aria-pressed="${path === "foto"}">Subir foto</button></div>`;
    if (path === "video") {
      return `${tabs}<div class="vp-mv-slots">${slotHtml(d, "source", "Video del plato", "", { has: m.has_video_source })}</div>
        <small class="vp-mv-muted">${h(VIDEO_GUIDE)}</small>`;
    }
    const gallery = arr(m.gallery);
    const max = (model.data && model.data.gallery_max) || 6;
    return `${tabs}<div class="vp-mv-slots">${slotHtml(d, "main", "Foto principal", m.main_original_url)}</div>
      <div class="vp-mv-gallery"><span class="vp-mv-slot-label">Más fotos (galería) · se ven en Detalle</span>
        <div class="vp-mv-slots">${gallery.map((g, i) => slotHtml(d, `gallery:${g.id}`, `Foto ${i + 2}`, g.original_url)).join("")}
        ${gallery.length < max ? `<div class="vp-mv-slot"><label class="vp-btn vp-btn-sm vp-mv-file">+ Agregar a la galería<input type="file" multiple accept="image/jpeg,image/png,image/webp" data-mv-change="${h(d.ref)}|gallery" aria-label="Agregar fotos a la galería de ${h(d.nombre)}"></label></div>` : ""}</div></div>`;
  }

  function optionsHtml(d, m) {
    const o = m.options || {};
    const mode = m.mode || "foto";
    const sel = (name, map, value, label) => `<label class="vp-field vp-mv-opt"><span>${h(label)}</span><select class="vp-search" data-mv-opt="${h(d.ref)}|${name}">${Object.entries(map).map(([k, v]) => `<option value="${h(k)}" ${k === value ? "selected" : ""}>${h(v)}</option>`).join("")}</select></label>`;
    const both = m.has_video_source && arr(m.roles).includes("main");
    return `<div class="vp-mv-opts">
      ${both ? sel("mode", { video: "Video del plato", foto: "Foto animada" }, mode, "Camino") : ""}
      ${mode === "foto" ? sel("style", STYLES, o.style || "vida", "Estilo") : ""}
      ${sel("background", BACKGROUNDS, o.background || (mode === "video" ? "desenfocar" : "ninguno"), "Fondo")}
      ${mode === "video" ? `${sel("speed", SPEEDS, o.speed || "normal", "Velocidad")}
        <label class="vp-field vp-mv-opt"><span>Tramo: desde (s)</span><input class="vp-search" type="number" min="0" max="30" step="0.5" data-mv-opt="${h(d.ref)}|start" value="${h(o.start ?? "")}" placeholder="0"></label>
        <label class="vp-field vp-mv-opt"><span>Tramo: duración (s)</span><input class="vp-search" type="number" min="1" max="30" step="0.5" data-mv-opt="${h(d.ref)}|length" value="${h(o.length ?? "")}" placeholder="todo"></label>` : ""}
    </div>`;
  }

  function publishedTag(d) {
    return model.data && model.data.published && model.data.published[d.ref]
      ? `<small class="vp-mv-pub">Publicado: los cambios se ven de inmediato en el QR</small>` : "";
  }

  function photosStep() {
    const photos = arr(model.data && model.data.photos);
    const loose = photos.filter((p) => !p.dish_ref);
    const options = dishes().map((d) => `<option value="${h(d.ref)}">${h(d.nombre)}</option>`).join("");
    return `
      <section class="vp-panel vp-section">
        <h2>3. Fotos por plato</h2>
        <p class="vp-mv-muted">Por plato elige el camino: <b>Subir video</b> (recomendado para la vista 360) o <b>Subir foto</b> (se anima la foto principal). Arrastra varias fotos a la vez: se emparejan por el nombre del archivo (<code>lomo.jpg</code> es la principal; <code>lomo-2.jpg</code> o <code>lomo-perfil.jpg</code> van a la galería). Se guarda siempre la original.</p>
        <div class="vp-mv-guides">${guideHtml("video")}${guideHtml("foto")}</div>
        <label class="vp-mv-drop" data-mv-drop="photos">
          <input type="file" multiple accept="image/jpeg,image/png,image/webp" data-mv-photo-files>
          <span><b>Suelta aquí las fotos</b> o toca para elegirlas.</span>
        </label>
        ${loose.length ? `<div class="vp-mv-loose"><h3 class="vp-mv-sub">Sin plato (${h(loose.length)})</h3>${loose.map((p) => `
          <div class="vp-mv-loose-row">${thumb(p.url, p.source_name || "foto")}<span>${h(p.source_name || "foto")}</span>
            <select class="vp-search" data-mv-assign-ref="${h(p.id)}" aria-label="Plato para ${h(p.source_name || "la foto")}"><option value="">Elige el plato…</option>${options}</select>
            <select class="vp-search" data-mv-assign-role="${h(p.id)}" aria-label="Dónde va la foto"><option value="main">Foto principal</option><option value="gallery">Galería</option></select>
            <button type="button" class="vp-btn vp-btn-sm" data-mv-assign="${h(p.id)}">Asignar</button></div>`).join("")}</div>` : ""}
        <div class="vp-mv-grid vp-mv-grid-wide">${dishes().map((d) => `<article class="vp-panel vp-mv-dish">
            <header><strong>${h(d.nombre)}</strong><small>${h(d.categoria)}${d.subcategoria ? ` › ${h(d.subcategoria)}` : ""}</small>${publishedTag(d)}</header>
            ${slotsHtml(d)}
          </article>`).join("")}</div>
        <div class="vp-head-actions"><button type="button" class="vp-btn vp-btn-primary" data-mv-step="4">Seguir a clips →</button></div>
      </section>`;
  }

  function phoneHtml(ref) {
    const d = dishes().find((x) => x.ref === ref) || dishes().find((x) => media(x.ref) && (media(x.ref).has_photo || media(x.ref).video_url));
    const m = d && media(d.ref);
    if (!d) return `<div class="vp-mv-phone"><div class="vp-mv-phone-screen vp-mv-phone-empty">Sube fotos para ver la vista previa.</div></div>`;
    const visual = m && m.video_url
      ? `<video class="vp-mv-phone-media" src="${h(m.video_url)}" poster="${h(m.poster_url)}" autoplay muted loop playsinline></video>`
      : m && m.photo_url ? `<img class="vp-mv-phone-media vp-mv-kenburns" src="${h(m.photo_url)}" alt="">`
        : `<div class="vp-mv-phone-media vp-mv-phone-card">${h(d.nombre)}</div>`;
    return `<div class="vp-mv-phone" aria-label="Vista previa en el celular: ${h(d.nombre)}">
      <div class="vp-mv-phone-screen">${visual}
        <div class="vp-mv-phone-cats">${[...new Set(dishes().map((x) => x.categoria))].slice(0, 4).map((c) => `<span class="${c === d.categoria ? "is-on" : ""}">${h(c)}</span>`).join("")}</div>
        <div class="vp-mv-phone-info"><strong>${h(d.nombre)}</strong><span>${h(money(d.precio))}</span><b>Agregar +</b></div>
      </div></div>`;
  }

  function clipsStep() {
    const withPhoto = dishes().filter((d) => media(d.ref) && (media(d.ref).has_photo || media(d.ref).has_video_source));
    const preview = model.preview || (withPhoto[0] && withPhoto[0].ref) || "";
    return `
      <section class="vp-panel vp-section">
        <h2>4. Remasterizar y crear clips</h2>
        <p class="vp-mv-muted">Clip de 3 s en bucle, 720×1280, sin sonido, en el servidor y sin IA. <b>Video:</b> estabilizado, luz y color corregidos, fondo a elegir, plato completo arriba de la tarjeta del precio; la vuelta completa cabe en 3 s (velocidad y tramo ajustables). <b>Foto:</b> se anima SOLO la foto principal con un movimiento suave (nunca un pase de fotos); el plato completo siempre visible.</p>
        <div class="vp-head-actions">
          <button type="button" class="vp-btn vp-btn-primary" data-mv-process-all ${withPhoto.length ? "" : "disabled"}>Crear todos (${h(withPhoto.length)})</button>
          <button type="button" class="vp-btn" data-mv-regenerate>Rehacer todos los clips de la empresa</button>
          <button type="button" class="vp-btn" data-mv-step="5">Seguir a publicar →</button>
        </div>
        <div class="vp-mv-studio">
          <div class="vp-mv-grid">${withPhoto.map((d) => {
            const m = media(d.ref);
            const st = status(d.ref);
            const j = job(d.ref);
            const confirmVideo = model.confirm && model.confirm.key === `${d.ref}|video`;
            const isVideo = (m.mode || "foto") === "video";
            return `<article class="vp-panel vp-mv-dish ${preview === d.ref ? "is-active" : ""}">
              <header><strong>${h(d.nombre)}</strong><span class="vp-mv-pill is-${h(st)}">${h(JOB[st] || st)}</span>
                <span class="vp-mv-pill">${isVideo ? "Video del plato" : "Foto animada"}</span>${publishedTag(d)}</header>
              ${isVideo ? "" : `<div class="vp-mv-pair vp-mv-before-after">
                <figure>${thumb(m.main_original_url, "Original")}<figcaption>Antes</figcaption></figure>
                <figure>${thumb(m.main_remaster_url, "Remasterizada")}<figcaption>Después</figcaption></figure>
              </div>`}
              ${slotsHtml(d)}
              ${optionsHtml(d, m)}
              ${j && j.status === "error" ? `<p class="vp-mv-error">${h(j.error)}</p>` : ""}
              ${isVideo ? "" : `<div class="vp-mv-row">
                <label class="vp-check"><input type="checkbox" data-mv-use-remaster="${h(d.ref)}" ${m.use_remaster ? "checked" : ""}> Usar la remasterizada</label>
              </div>`}
              ${confirmVideo
                ? confirmHtml("¿Quitar el video? Queda solo la foto.")
                : `<div class="vp-mv-row">
                    <button type="button" class="vp-btn vp-btn-sm vp-btn-primary" data-mv-process="${h(d.ref)}">${m.video_url ? "Rehacer" : "Crear clip"}</button>
                    ${m.video_url ? `<button type="button" class="vp-btn vp-btn-sm" data-mv-video-remove="${h(d.ref)}">Quitar video</button>` : ""}
                    <button type="button" class="vp-btn vp-btn-sm" data-mv-preview="${h(d.ref)}">Ver en el celular</button>
                  </div>`}
            </article>`;
          }).join("") || `<div class="vp-empty">Primero sube fotos o videos en el paso 3.</div>`}</div>
          <aside class="vp-mv-phone-wrap">${phoneHtml(preview)}<small>Así lo verá el cliente en el QR de la mesa.</small></aside>
        </div>
      </section>`;
  }

  // 057C: "Publicado hoy 3:42 p. m.: 0 nuevos, 1 actualizado" (hora de Bogotá).
  function whenText(iso, now = new Date()) {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return "";
    const opts = { timeZone: "America/Bogota" };
    const day = (x) => x.toLocaleDateString("es-CO", { ...opts, year: "numeric", month: "2-digit", day: "2-digit" });
    const time = d.toLocaleTimeString("es-CO", { ...opts, hour: "numeric", minute: "2-digit" });
    if (day(d) === day(now)) return `hoy ${time}`;
    return `${d.toLocaleDateString("es-CO", { ...opts, day: "numeric", month: "short" })}, ${time}`;
  }

  function lastPublished() {
    const s = imp() && imp().summary;
    return s && s.published_at ? s : null;
  }

  function publishStep() {
    const p = model.plan;
    const done = lastPublished();
    const changes = p ? Number(p.counts.new || 0) + Number(p.counts.updated || 0) : 0;
    return `
      <section class="vp-panel vp-section">
        <h2>5. Publicar en la empresa</h2>
        <p class="vp-mv-muted">Publicar <b>combina</b>, nunca borra: empareja por nombre dentro de la categoría; actualiza precio, descripción, foto y video; los platos nuevos quedan en su Carta con <b>receta pendiente</b> (el QR y los pedidos funcionan igual).</p>
        ${done ? `<div class="vp-mv-done" role="status"><strong>Publicado ${h(whenText(done.published_at))}:</strong> ${h(done.new)} ${done.new === 1 ? "nuevo" : "nuevos"}, ${h(done.updated)} ${done.updated === 1 ? "actualizado" : "actualizados"}, 0 borrados.</div>` : ""}
        ${!p ? `<p class="vp-loading">Calculando…</p>` : `
          <div class="vp-cards vp-mv-sum">
            <div class="vp-panel vp-card vp-card-ok"><span>Platos nuevos</span><strong>${h(p.counts.new)}</strong></div>
            <div class="vp-panel vp-card"><span>Actualizados</span><strong>${h(p.counts.updated)}</strong></div>
            <div class="vp-panel vp-card"><span>Sin cambios</span><strong>${h(p.counts.unchanged)}</strong></div>
            <div class="vp-panel vp-card"><span>Borrados</span><strong>0</strong></div>
          </div>
          <p class="vp-mv-summary">${h(p.counts.new)} platos nuevos, ${h(p.counts.updated)} actualizados, 0 borrados.${arr(p.new_categories).length ? ` Categorías nuevas: ${h(p.new_categories.join(", "))}.` : ""}</p>
          <div class="vp-table-wrap"><table class="vp-table vp-table-compact"><thead><tr><th>Plato</th><th>Categoría</th><th>Precio</th><th>Qué pasa</th></tr></thead><tbody>
            ${[...arr(p.new).map((d) => ({ ...d, what: `Nuevo · receta pendiente${d.media ? " · con video" : ""}` })),
               ...arr(p.updated).map((d) => ({ ...d, what: `Actualiza ${arr(d.changes).join(", ")}` })),
               ...arr(p.unchanged).map((d) => ({ ...d, what: "Sin cambios" }))].map((d) => `<tr><td>${h(d.nombre)}</td><td>${h(d.categoria)}</td><td>${h(money(d.precio))}</td><td>${h(d.what)}</td></tr>`).join("")}
          </tbody></table></div>
          <div class="vp-head-actions">${changes > 0
            ? `<button type="button" class="vp-btn vp-btn-primary" data-mv-publish ${model.busy ? "disabled" : ""}>Publicar en ${h((model.data && model.data.company.name) || "la empresa")}</button>`
            : `<button type="button" class="vp-btn" disabled>No hay cambios para publicar</button>`}</div>`}
      </section>`;
  }

  function view() {
    const company = model.data && model.data.company;
    const body = model.step === 1 ? companyStep() : model.step === 2 ? importStep() : model.step === 3 ? photosStep() : model.step === 4 ? clipsStep() : publishStep();
    return `
      <div class="vp-mv">
        <header class="vp-head">
          <div><p class="vp-eyebrow">CARTA EN VIDEO</p><h1 class="vp-title">Menú video</h1>
            ${company ? `<p class="vp-ficha-meta"><b>${h(company.name)}</b> · ${model.data.carta_video ? "carta en video encendida" : "carta en video apagada (actívala en Interruptores)"} · cupo del cliente ${h(model.data.quota.new.left)}/${h(model.data.quota.new.limit)} nuevos y ${h(model.data.quota.changes.left)}/${h(model.data.quota.changes.limit)} cambios este mes</p>` : ""}
          </div>
        </header>
        ${stepsHtml()}
        ${model.error ? `<div class="vp-alert" role="alert"><strong>No se pudo</strong><span>${h(model.error)}</span></div>` : ""}
        ${model.notice ? `<div class="vp-alert vp-alert-info" role="status"><span>${h(model.notice)}</span></div>` : ""}
        ${model.busy ? `<p class="vp-mv-busy" role="status"><span class="vp-mv-spinner" aria-hidden="true"></span> ${h(model.busy)}</p>` : ""}
        ${body}
      </div>`;
  }

  function draw() {
    const root = ctx && ctx.root && ctx.root();
    if (!root || (ctx.active && !ctx.active())) return;
    root.innerHTML = view();
  }

  // ------------------------------------------------------------ datos
  function applyState(data) {
    model.data = { ...(model.data || {}), ...data };
    const current = imp();
    if (current && (!model.dirty || !model.table)) model.table = JSON.parse(JSON.stringify(current.table_data || { categorias: [], platos: [] }));
    schedule();
  }

  function schedule() {
    if (timer) { clearTimeout(timer); timer = null; }
    if (!busyNow() || !imp()) return;
    timer = setTimeout(async () => {
      timer = null;
      if (!ctx || (ctx.active && !ctx.active()) || !imp()) return;
      try { applyState(await api.imp(model.companyId, imp().id)); draw(); } catch (_) { schedule(); }
    }, 3000);
  }

  async function run(label, fn, notice) {
    model.busy = label;
    model.error = "";
    model.notice = "";
    draw();
    try {
      const out = await fn();
      if (notice) model.notice = notice;
      return out;
    } catch (error) {
      model.error = (error && error.message) || "Algo salió mal.";
      return null;
    } finally {
      model.busy = "";
      draw();
    }
  }

  async function openCompany(id) {
    model.companyId = id;
    model.data = null;
    model.table = null;
    model.dirty = false;
    model.plan = null;
    model.result = null;
    const data = await run("Cargando la empresa…", () => api.company(id));
    if (!data) return;
    applyState(data);
    model.step = imp() && imp().status !== "publicada" ? (dishes().length ? 3 : 2) : 2;
    draw();
  }

  async function saveTable() {
    const data = await run("Guardando la tabla…", () => api.saveTable(model.companyId, imp().id, model.table), "Tabla guardada.");
    if (data) { model.dirty = false; applyState(data); draw(); }
    return data;
  }

  async function uploadPhotos(files) {
    const list = Array.from(files || []).filter((f) => /^image\//.test(f.type || "") || /\.(jpe?g|png|webp)$/i.test(f.name || ""));
    if (!list.length || !imp()) return;
    if (model.dirty && !(await saveTable())) return;
    let ok = 0;
    const bad = [];
    for (let i = 0; i < list.length; i += 6) {
      const form = new FormData();
      list.slice(i, i + 6).forEach((f) => form.append("files", f, f.name));
      const data = await run(`Subiendo fotos ${Math.min(i + 6, list.length)} de ${list.length}…`, () => api.photos(model.companyId, imp().id, form));
      if (!data) return;
      arr(data.results).forEach((r) => (r.ok ? ok += 1 : bad.push(`${r.file}: ${r.error}`)));
      applyState(data);
    }
    model.notice = `${ok} foto${ok === 1 ? "" : "s"} guardada${ok === 1 ? "" : "s"}.${bad.length ? ` No se pudieron usar: ${bad.join(" · ")}` : ""}`;
    draw();
  }

  async function loadPlan() {
    model.plan = null;
    draw();
    if (model.dirty && !(await saveTable())) return;
    const data = await run("Calculando el resumen…", () => api.plan(model.companyId, imp().id));
    if (data) { model.plan = data.plan; draw(); }
  }

  function goStep(n) {
    model.step = n;
    model.error = "";
    model.notice = "";
    if (n === 1 && !model.companies) loadCompanies();
    if (n === 5 && imp()) { loadPlan(); return; }
    draw();
  }

  async function loadCompanies() {
    try {
      const [list, health] = await Promise.all([api.companies(), api.health().catch(() => null)]);
      model.companies = list.companies;
      model.health = health;
    } catch (error) {
      model.companies = [];
      model.error = error.message;
    }
    draw();
  }

  // ------------------------------------------------------------ eventos
  async function onClick(event) {
    const t = event.target;
    if (!t || !t.closest || !t.closest(".vp-mv")) return;
    const step = t.closest("[data-mv-step]");
    if (step && !step.disabled) { goStep(Number(step.getAttribute("data-mv-step"))); return; }
    const company = t.closest("[data-mv-company]");
    if (company) { openCompany(company.getAttribute("data-mv-company")); return; }
    if (t.closest("[data-mv-manual]")) {
      const form = new FormData();
      form.append("manual", "true");
      const data = await run("Creando la tabla…", () => api.importFiles(model.companyId, form));
      if (data) { model.dirty = false; model.table = null; applyState(data); addRow(); draw(); }
      return;
    }
    if (t.closest("[data-mv-row-add]")) { addRow(); draw(); return; }
    const del = t.closest("[data-mv-row-del]");
    if (del) { model.table.platos.splice(Number(del.getAttribute("data-mv-row-del")), 1); model.dirty = true; draw(); return; }
    if (t.closest("[data-mv-table-save]")) { saveTable(); return; }
    const assign = t.closest("[data-mv-assign]");
    if (assign) {
      const id = assign.getAttribute("data-mv-assign");
      const ref = (document.querySelector(`[data-mv-assign-ref="${id}"]`) || {}).value;
      const role = (document.querySelector(`[data-mv-assign-role="${id}"]`) || {}).value || "main";
      if (!ref) { model.error = "Elige el plato."; draw(); return; }
      const data = await run("Asignando…", () => api.assign(model.companyId, imp().id, id, { ref, role }));
      if (data) { applyState(data); draw(); }
      return;
    }
    if (t.closest("[data-mv-process-all]")) {
      const data = await run("Mandando a la cola…", () => api.process(model.companyId, imp().id, { style: "auto" }), "Los clips se están creando: puedes seguir trabajando.");
      if (data) { applyState(data); draw(); }
      return;
    }
    if (t.closest("[data-mv-regenerate]")) {
      const data = await run("Mandando a la cola…", () => api.regenerate(model.companyId));
      if (data) {
        model.notice = `${data.queued} clips de la empresa se rehacen con el proceso nuevo. Los publicados se siguen viendo hasta que el nuevo esté listo (no gasta cupo del cliente).`;
        applyState(await api.imp(model.companyId, imp().id));
        draw();
      }
      return;
    }
    const pathBtn = t.closest("[data-mv-path]");
    if (pathBtn) {
      const [ref, path] = pathBtn.getAttribute("data-mv-path").split("|");
      model.paths[ref] = path;
      const m = media(ref) || {};
      const ready = path === "video" ? m.has_video_source : arr(m.roles).includes("main");
      if (ready && (m.mode || "foto") !== path) {
        const data = await run("Cambiando el camino…", () => api.options(model.companyId, imp().id, ref, { mode: path }), "El clip se rehace con el camino elegido.");
        if (data) applyState(data);
      }
      draw();
      return;
    }
    const removeAsk = t.closest("[data-mv-remove]");
    if (removeAsk) { model.confirm = { key: removeAsk.getAttribute("data-mv-remove") }; draw(); return; }
    const videoAsk = t.closest("[data-mv-video-remove]");
    if (videoAsk) { model.confirm = { key: `${videoAsk.getAttribute("data-mv-video-remove")}|video` }; draw(); return; }
    const catAsk = t.closest("[data-mv-cat-del]");
    if (catAsk) { model.confirm = { key: `cat|${catAsk.getAttribute("data-mv-cat-del")}` }; draw(); return; }
    if (t.closest("[data-mv-remove-no]")) { model.confirm = null; draw(); return; }
    if (t.closest("[data-mv-remove-yes]") && model.confirm) {
      const key = model.confirm.key;
      model.confirm = null;
      if (key.startsWith("cat|")) {
        const cat = key.slice(4);
        model.table.platos = model.table.platos.filter((d) => d.categoria !== cat);
        model.dirty = true;
        draw();
        return;
      }
      const [ref, role] = key.split("|");
      if (role === "video") {
        const data = await run("Quitando el video…", () => api.removeVideo(model.companyId, imp().id, ref), "Video quitado: queda la foto.");
        if (data) { applyState(data); draw(); }
        return;
      }
      const apiRole = role === "source" ? "video" : role;
      const data = await run(role === "source" ? "Quitando el video del plato…" : "Quitando la foto…", () => api.removePhoto(model.companyId, imp().id, ref, apiRole));
      if (data) {
        model.undo = { key, ref, role: apiRole, original: data.undo.original, remaster: data.undo.remaster, index: data.undo.index, until: Date.now() + 10000 };
        setTimeout(() => { if (model.undo && Date.now() >= model.undo.until) { model.undo = null; draw(); } }, 10100);
        model.notice = data.undo.empty ? "Quitada. El plato quedó sin fotos ni video: en el QR se ve su tarjeta de nombre y precio."
          : role.startsWith("gallery") ? "Foto quitada de la galería (el video no cambia)." : "Quitada. El clip se rehace con lo que queda.";
        applyState(data);
        draw();
      }
      return;
    }
    if (t.closest("[data-mv-undo]") && model.undo) {
      const u = model.undo;
      model.undo = null;
      const body = { original: u.original, remaster: u.remaster || "", ...(u.index !== undefined && u.index !== null ? { index: u.index } : {}) };
      const data = await run("Deshaciendo…", () => api.restorePhoto(model.companyId, imp().id, u.ref, u.role, body), "Listo: volvió.");
      if (data) { applyState(data); draw(); }
      return;
    }
    const one = t.closest("[data-mv-process]");
    if (one) {
      const ref = one.getAttribute("data-mv-process");
      // Rehacer con el estilo, fondo, velocidad y tramo elegidos (no gasta cupo)
      const data = await run("Mandando a la cola…", () => api.options(model.companyId, imp().id, ref, model.opts[ref] || {}), "El clip se está rehaciendo: la vista previa se actualiza sola.");
      if (data) { model.preview = ref; delete model.opts[ref]; applyState(data); draw(); }
      return;
    }
    const preview = t.closest("[data-mv-preview]");
    if (preview) { model.preview = preview.getAttribute("data-mv-preview"); draw(); return; }
    if (t.closest("[data-mv-publish]")) {
      const name = (model.data && model.data.company.name) || "la empresa";
      if (typeof window.confirm === "function" && !window.confirm(`¿Publicar en ${name}? Combina con su Carta: no borra nada.`)) return;
      const data = await run("Publicando…", () => api.publish(model.companyId, imp().id));
      if (data) {
        if (ctx && ctx.toast) ctx.toast("Carta publicada.");
        applyState(await api.imp(model.companyId, imp().id)); // el aviso sale de la ÚLTIMA publicación
        model.plan = data.plan || null; // el resumen se recalcula
        if (!model.plan) await loadPlan();
        draw();
      }
    }
  }

  function blankRow() {
    const last = dishes()[dishes().length - 1] || {};
    const ref = window.crypto && window.crypto.randomUUID ? window.crypto.randomUUID() : undefined;
    return { ref, categoria: last.categoria || "", subcategoria: last.subcategoria || "", nombre: "", descripcion: "", precio: "", opciones: "" };
  }

  function addRow() {
    if (!model.table) model.table = { categorias: [], platos: [] };
    model.table.platos.push(blankRow());
    model.dirty = true;
  }

  function onInput(event) {
    const cell = event.target && event.target.closest && event.target.closest("[data-mv-cell]");
    if (!cell) return;
    const [index, key] = cell.getAttribute("data-mv-cell").split(":");
    const row = model.table && model.table.platos[Number(index)];
    if (!row) return;
    row[key] = cell.value;
    if (!model.dirty) {
      model.dirty = true;
      const save = document.querySelector("[data-mv-table-save]");
      if (save) save.textContent = "Guardar tabla";
    }
  }

  async function onChange(event) {
    const t = event.target;
    if (!t || !t.closest || !t.closest(".vp-mv")) return;
    if (t.matches("[data-mv-import-files]")) { model.files = Array.from(t.files || []); draw(); return; }
    if (t.matches("[data-mv-photo-files]")) { uploadPhotos(t.files); return; }
    if (t.matches("[data-mv-change]") && t.files && t.files[0]) {
      const [ref, role] = t.getAttribute("data-mv-change").split("|");
      const files = role === "gallery" ? Array.from(t.files) : [t.files[0]];
      const apiRole = role === "source" ? "video" : role;
      let data = null;
      for (const file of files) {
        data = await run(role === "source" ? "Subiendo el video (puede tardar)…" : "Subiendo la foto…",
          () => api.changePhoto(model.companyId, imp().id, ref, apiRole, file),
          role === "source" ? "Video subido: se está editando (estabilizar, color y fondo)." : role === "gallery" ? "Foto agregada a la galería." : "Foto cambiada: el clip se rehace.");
        if (!data) break;
      }
      if (data) { model.paths[ref] = role === "source" ? "video" : "foto"; applyState(data); draw(); }
      return;
    }
    if (t.matches("[data-mv-opt]")) {
      const [ref, name] = t.getAttribute("data-mv-opt").split("|");
      model.opts[ref] = { ...(model.opts[ref] || {}), [name]: ["start", "length"].includes(name) ? (t.value === "" ? null : Number(t.value)) : t.value };
      return;
    }
    if (t.matches("[data-mv-use-remaster]")) {
      const ref = t.getAttribute("data-mv-use-remaster");
      const data = await run("Cambiando la versión…", () => api.choose(model.companyId, imp().id, ref, t.checked));
      if (data) { model.preview = ref; applyState(data); draw(); }
      return;
    }
    if (t.matches("[data-mv-reassign]")) {
      // reasignar a mano una foto que se emparejó con otro plato
      const body = { ref: t.value, role: t.getAttribute("data-mv-role") || "main" };
      const data = await run("Reasignando…", () => api.assign(model.companyId, imp().id, t.getAttribute("data-mv-reassign"), body));
      if (data) { applyState(data); draw(); }
    }
  }

  async function onSubmit(event) {
    const form = event.target;
    if (!form || !form.matches || !form.matches("[data-mv-import]")) return;
    event.preventDefault();
    const link = String(new FormData(form).get("link") || "").trim();
    if (!model.files.length && !link) { model.error = "Sube el PDF o las fotos de la carta, o pega un enlace."; draw(); return; }
    const body = new FormData();
    model.files.forEach((f) => body.append("files", f, f.name));
    if (link) body.append("link", link);
    const data = await run("Subiendo la carta…", () => api.importFiles(model.companyId, body));
    if (data) { model.files = []; model.dirty = false; model.table = null; applyState(data); draw(); }
  }

  function onDrag(event) {
    const zone = event.target && event.target.closest && event.target.closest("[data-mv-drop]");
    if (!zone) return;
    event.preventDefault();
    zone.classList.toggle("is-over", event.type === "dragover");
    if (event.type !== "drop") return;
    const files = event.dataTransfer && event.dataTransfer.files;
    if (zone.getAttribute("data-mv-drop") === "photos") uploadPhotos(files);
    else { model.files = Array.from(files || []); draw(); }
  }

  window.CxConsoleSections = window.CxConsoleSections || {};
  window.CxConsoleSections.menuvideo = {
    mount(context) {
      ctx = context;
      if (!bound && typeof document.addEventListener === "function") {
        document.addEventListener("click", onClick);
        document.addEventListener("input", onInput);
        document.addEventListener("change", onChange);
        document.addEventListener("submit", onSubmit);
        ["dragover", "dragleave", "drop"].forEach((type) => document.addEventListener(type, onDrag));
        bound = true;
      }
      const p = (context && context.params) || {};
      if (p.company && p.company !== model.companyId) { openCompany(p.company); return; }
      if (!model.companies) loadCompanies();
      draw();
      schedule();
    },
    refreshPulse() {},
  };
  window.CxConsoleMenuVideo = { model, api, view, whenText, slotHtml, slotsHtml, optionsHtml, guideHtml, catsHtml, BACKGROUNDS, SPEEDS, companyStep, importStep, photosStep, clipsStep, publishStep, phoneHtml, tableHtml, STEPS, STYLES };
})();
