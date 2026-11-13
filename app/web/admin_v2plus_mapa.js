// Consola v2+ · Landing → Mapa comercial (interno de Clonexa, solo Admin V2).
// Mapa de Colombia con Leaflet + OpenStreetMap (abre en Bogotá): prospectos por
// estado, zonas de calor de visitas a la landing (por ciudad, DB-IP) y de
// respuestas, y zonas de prospección con su puntaje. Filtros por zona, tipo,
// estado y fechas; ficha del negocio con historial y "Abrir en Google Maps".
// Leaflet se carga solo al abrir esta pestaña (/admin-v2plus-leaflet.js, copia
// local de Leaflet 1.9.4: la CSP de v2+ solo permite scripts propios).
// Sin estilos en línea: todo por clase; los colores del mapa van como opciones
// de Leaflet (atributos SVG). Todo el texto se escapa.
(() => {
  "use strict";

  const API = "/api/v1/prospecting/admin";
  const h = (v) => String(v ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
  const arr = (v) => (Array.isArray(v) ? v : []);
  const enc = encodeURIComponent;
  const BOGOTA = [4.6280, -74.1420];
  const COLOMBIA = [[-4.3, -79.1], [12.6, -66.8]];
  const STATUS = {
    nuevo: ["Nuevo", "#9aa4b2"], contactado: ["Contactado", "#3b82f6"], abrio: ["Abrió la landing", "#f59e0b"],
    respondio: ["Respondió", "#a855f7"], demo: ["Demo", "#ec4899"], cliente: ["Cliente", "#22c55e"], baja: ["Baja", "#ef4444"],
  };
  const TYPES = { restaurante: "Restaurante", comidas_rapidas: "Comidas rápidas", cafe: "Café", panaderia: "Panadería", bar: "Bar", taller: "Taller de confección",
    fabrica: "Fábrica pequeña", electrico: "Contratista eléctrico", telecom: "Telecomunicaciones", construccion: "Construcción", instalador: "Instaladores",
    aseo: "Aseo", vigilancia: "Vigilancia", transporte: "Transporte y logística", tienda: "Tienda / minimercado" };
  // nicho -> [etiqueta, icono, color] (los mismos de app/services/prospecting_niches.py)
  const NICHES = { restaurante: ["Restaurantes y comidas", "🍽️", "#f59e0b"], taller: ["Talleres y fábricas", "🧵", "#ff2d6f"],
    campo: ["Empresas de campo", "🦺", "#22c55e"], transporte: ["Transporte y logística", "🚚", "#3b82f6"], tienda: ["Tiendas y minimercados", "🛒", "#14b8a6"],
    bar: ["Bares", "🍸", "#a855f7"] };
  const EMPTY_FILTERS = () => ({ zone_id: "", nicho: "", tipo: "", estado: "", vigencia: "", desde: "", hasta: "" });
  // canales publicos (de la ficha de Google y de la web del negocio): [icono, nombre]
  const CHANNELS = { email: ["✉️", "Correo"], instagram: ["📸", "Instagram"], facebook: ["📘", "Facebook"], tiktok: ["🎵", "TikTok"],
    whatsapp: ["🟢", "WhatsApp publicado"], web: ["🌐", "Web"], phone: ["📞", "Teléfono"] };
  const chanIcons = (keys) => arr(keys).filter((k) => CHANNELS[k]).map((k) => CHANNELS[k][0]).join("");
  const VIGENCIA = { activo: "Activo", por_verificar: "Por verificar", sin_dato: "Sin dato aún" };
  const KINDS = { inicial: "Correo inicial", seguimiento: "Seguimiento", respuesta: "Respondió", baja: "Baja", apertura: "Abrió la landing",
    whatsapp_entrada: "Escribió por WhatsApp", demo: "Demo", cliente: "Cliente", prueba: "Prueba" };
  const LAYERS = [["prospectos", "Prospectos"], ["visitas", "Calor: visitas a la landing"], ["leads", "Calor: respuestas y leads"],
    ["volantes", "Calor: visitas por volante"], ["zonas", "Zonas de prospección"]];
  const FLYER_NICHES = ["restaurante", "bar", "taller", "campo", "tienda", "transporte"];

  async function request(url, options = {}) {
    const response = await fetch(url, { credentials: "same-origin", ...options,
      headers: { Accept: "application/json", ...(options.body ? { "Content-Type": "application/json" } : {}), ...(options.headers || {}) } });
    const data = await response.json().catch(() => ({}));
    if (response.status === 401) { window.location.href = "/admin-v2plus/login"; throw new Error("Sesión vencida."); }
    if (!response.ok) throw new Error((data && typeof data.detail === "string" && data.detail) || `Respuesta ${response.status}`);
    return data;
  }

  function mapUrl(f = {}) {
    const p = new URLSearchParams();
    if (f.zone_id) p.set("zone_id", f.zone_id);
    if (f.nicho) p.set("nicho", f.nicho);
    if (f.tipo) p.set("tipo", f.tipo);
    if (f.estado) p.set("estado", f.estado);
    if (f.vigencia) p.set("vigencia", f.vigencia);
    if (f.desde) p.set("desde", f.desde);
    if (f.hasta) p.set("hasta", f.hasta);
    const qs = p.toString();
    return `${API}/map${qs ? `?${qs}` : ""}`;
  }
  const api = {
    map: (f) => request(mapUrl(f)),
    detail: (id) => request(`${API}/prospects/${enc(id)}`),
    status: (id, estado) => request(`${API}/prospects/${enc(id)}/status`, { method: "POST", body: JSON.stringify({ estado }) }),
    createZone: (z) => request(`${API}/zones`, { method: "POST", body: JSON.stringify(z) }),
    route: (zoneId, nicho) => request(`${API}/route?zone_id=${enc(zoneId)}${nicho ? `&nicho=${enc(nicho)}` : ""}`),
    routeSend: (zoneId, nicho) => request(`${API}/route/send`, { method: "POST", body: JSON.stringify({ zone_id: Number(zoneId), nicho: nicho || "" }) }),
    visited: (id) => request(`${API}/prospects/${enc(id)}/visited`, { method: "POST", body: "{}" }),
  };
  const flyerUrl = (zoneId, nicho) => `${API}/flyer?zone_id=${enc(zoneId)}&nicho=${enc(nicho)}`;

  // ------------------------------------------------------------ estado
  const model = {
    filters: EMPTY_FILTERS(), colorBy: "estado",
    layers: { prospectos: true, visitas: true, leads: true, volantes: true, zonas: true }, route: null,
    data: null, error: "", loading: false, detail: null, detailError: "", confirm: "", newZone: null, notice: "",
  };
  let host = null;
  let map = null;
  let groups = null;

  // ------------------------------------------------------------ utilidades
  const pct = (a, b) => (b ? `${Math.round((1000 * a) / b) / 10}%` : "—");
  const num = (v) => Number(v || 0).toLocaleString("es-CO");
  function fecha(iso) {
    if (!iso) return "—";
    try { return new Date(iso).toLocaleString("es-CO", { timeZone: "America/Bogota", day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" }); } catch (_) { return String(iso).slice(0, 16); }
  }
  const safeUrl = (u) => (/^https:\/\//i.test(String(u || "")) ? String(u) : "");
  function zoneColor(score, max) {
    const t = max ? Math.min(1, score / max) : 0;
    return t > 0.66 ? "#ff2d6f" : t > 0.33 ? "#f59e0b" : "#9d17ff";
  }
  function heatStyle(total, max, base, span, color) {
    const t = max ? Math.sqrt(total / max) : 0;
    return { radius: base + span * t, stroke: false, fillColor: color, fillOpacity: 0.14 + 0.42 * t, interactive: true };
  }

  // ------------------------------------------------------------ vistas (HTML)
  function cards(d) {
    const c = (d && d.cards) || {};
    const items = [["Prospectos", c.prospectos, `${num(c.con_correo)} con correo · ${num(c.por_verificar)} por verificar`], ["Correos enviados", c.enviados, ""],
      ["Abrieron la landing", c.abrieron, pct(c.abrieron || 0, c.enviados || 0)], ["Respondieron", c.respondieron, pct(c.respondieron || 0, c.enviados || 0)],
      ["Demos", c.demos, ""], ["Clientes", c.clientes, ""]];
    return `<section class="vp-cards vpm-cards">${items.map(([l, v, s]) => `<div class="vp-panel vp-card"><span>${h(l)}</span><strong>${h(num(v))}</strong>${s ? `<small>${h(s)}</small>` : ""}</div>`).join("")}</section>`;
  }

  const chanCells = (z) => `<td>${h(pct(z.con_correo || 0, z.prospectos || 0))}</td><td>${h(pct(z.con_redes || 0, z.prospectos || 0))}</td><td>${h(pct(z.con_whatsapp || 0, z.prospectos || 0))}</td>`;

  function channelsList(p) {
    const ch = (p && p.channels) || {};
    const keys = Object.keys(CHANNELS).filter((k) => ch[k] && typeof ch[k] === "object" && ch[k].value);
    if (!keys.length) return `<p class="vp-login-hint">Sin canales públicos encontrados.</p>`;
    const link = (u) => (/^(https:\/\/|mailto:|tel:)/i.test(String(u || "")) ? String(u) : "");
    const src = (s) => (/^https:\/\//i.test(String(s || "")) ? `<a href="${h(s)}" target="_blank" rel="noopener noreferrer">fuente</a>` : h(String(s || "").replace("google:", "ficha de Google: ")));
    return `<ul class="vpm-channels">${keys.map((k) => { const c = ch[k]; const u = link(c.url);
      return `<li><span aria-hidden="true">${h(CHANNELS[k][0])}</span><b>${h(CHANNELS[k][1])}</b> ${u ? `<a href="${h(u)}" target="_blank" rel="noopener noreferrer">${h(c.value)}</a>` : h(c.value)}<small>${src(c.source)}</small></li>`; }).join("")}</ul>
      ${ch.whatsapp ? `<p class="vp-login-hint">El WhatsApp publicado solo se muestra: Nexa nunca escribe en frío.</p>` : ""}`;
  }

  function zonesTable(d) {
    const zs = arr(d && d.zones).filter((z) => z.active !== false);
    if (!zs.length) return "";
    return `<section class="vp-panel vp-section"><h2>% por zona</h2><div class="vpm-table-wrap"><table class="vpm-table">
      <thead><tr><th>Zona</th><th>Prospectos</th><th>% correo</th><th>% IG/FB</th><th>% WhatsApp publicado</th><th>Enviados</th><th>% abrió</th><th>% respondió</th><th>Demos</th><th>Clientes</th><th>Puntaje</th></tr></thead>
      <tbody>${zs.map((z) => `<tr><td><button class="vp-btn vp-btn-sm vp-btn-link" type="button" data-vpm-zone="${h(z.id)}">${h(z.name)}</button><small>${h(z.group_name || "")}</small>
        <span class="vpm-zone-tools"><button class="vp-btn vp-btn-sm" type="button" data-vpm-route="${h(z.id)}">🗺️ Ruta del día</button>
        <select data-vpm-flyer-niche="${h(z.id)}" aria-label="Nicho del volante">${FLYER_NICHES.map((k) => `<option value="${h(k)}">${h((NICHES[k] || [k])[0])}</option>`).join("")}</select>
        <button class="vp-btn vp-btn-sm" type="button" data-vpm-flyer="${h(z.id)}">🖨️ Volante PDF</button></span></td>
        <td>${h(num(z.prospectos))}</td>${chanCells(z)}<td>${h(num(z.enviados))}</td><td>${h(pct(z.abrieron, z.enviados))}</td><td>${h(pct(z.respondieron, z.enviados))}</td>
        <td>${h(num(z.demos))}</td><td>${h(num(z.clientes))}</td><td class="vp-mono">${h(num(z.puntaje))}</td></tr>`).join("")}</tbody></table></div>
      <p class="vp-login-hint">Puntaje = prospectos ×1 + correos ×2 + aperturas ×5 + respuestas ×10 + demos ×20 + clientes ×40.</p></section>`;
  }

  function filtersForm(d) {
    const f = model.filters;
    const opt = (v, l, cur) => `<option value="${h(v)}" ${String(cur) === String(v) ? "selected" : ""}>${h(l)}</option>`;
    const zs = arr(d && d.zones);
    return `<form class="vp-panel vp-section vp-form-grid vpm-filters" data-vpm-filters>
      <label class="vp-field">Zona<select name="zone_id">${opt("", "Todas", f.zone_id)}${zs.map((z) => opt(z.id, z.name, f.zone_id)).join("")}</select></label>
      <label class="vp-field">Nicho<select name="nicho">${opt("", "Todos", f.nicho)}${Object.entries(NICHES).map(([k, [l, i]]) => opt(k, `${i} ${l}`, f.nicho)).join("")}</select></label>
      <label class="vp-field">Tipo de negocio<select name="tipo">${opt("", "Todos", f.tipo)}${Object.entries(TYPES).map(([k, l]) => opt(k, l, f.tipo)).join("")}</select></label>
      <label class="vp-field">Estado<select name="estado">${opt("", "Todos", f.estado)}${Object.entries(STATUS).map(([k, [l]]) => opt(k, l, f.estado)).join("")}</select></label>
      <label class="vp-field">Vigencia<select name="vigencia">${opt("", "Todas", f.vigencia)}${Object.entries(VIGENCIA).map(([k, l]) => opt(k, l, f.vigencia)).join("")}</select></label>
      <label class="vp-field">Desde<input type="date" name="desde" value="${h(f.desde)}"></label>
      <label class="vp-field">Hasta<input type="date" name="hasta" value="${h(f.hasta)}"></label>
      <div class="vp-actions"><button class="vp-btn vp-btn-primary" type="submit">Filtrar</button><button class="vp-btn" type="button" data-vpm-reset>Limpiar</button></div>
    </form>`;
  }

  function layerToggles() {
    return `<div class="vpm-layers" role="group" aria-label="Capas del mapa">${LAYERS.map(([k, l]) => `<label class="vpm-layer"><input type="checkbox" data-vpm-layer="${k}" ${model.layers[k] ? "checked" : ""}> ${h(l)}</label>`).join("")}
      <label class="vpm-layer">Color de los pines <select data-vpm-color><option value="estado" ${model.colorBy === "estado" ? "selected" : ""}>por estado</option><option value="nicho" ${model.colorBy === "nicho" ? "selected" : ""}>por nicho</option></select></label>
      <span class="vpm-jump"><button class="vp-btn vp-btn-sm" type="button" data-vpm-jump="bogota">Bogotá</button><button class="vp-btn vp-btn-sm" type="button" data-vpm-jump="colombia">Colombia</button>
      <button class="vp-btn vp-btn-sm" type="button" data-vpm-new-zone>＋ Zona</button></span></div>`;
  }

  function legend() {
    if (model.colorBy === "nicho") return `<ul class="vpm-legend">${Object.entries(NICHES).map(([k, [l, i]]) => `<li><span class="vpm-dot is-n-${k}" aria-hidden="true"></span>${h(i)} ${h(l)}</li>`).join("")}</ul>`;
    return `<ul class="vpm-legend">${Object.entries(STATUS).map(([k, [l]]) => `<li><span class="vpm-dot is-${k}" aria-hidden="true"></span>${h(l)}</li>`).join("")}</ul>`;
  }
  const nicheOf = (p) => (p && (p.niche || "")) || "restaurante";
  function pinColor(p) {
    if (model.colorBy === "nicho") return (NICHES[nicheOf(p)] || NICHES.restaurante)[2];
    return (STATUS[p.status] || [p.status, "#9aa4b2"])[1];
  }

  function nichesTable(d) {
    const ns = arr(d && d.niches);
    if (!ns.length) return "";
    return `<section class="vp-panel vp-section"><h2>% por nicho</h2><div class="vpm-table-wrap"><table class="vpm-table">
      <thead><tr><th>Nicho</th><th>Prospectos</th><th>% correo</th><th>% IG/FB</th><th>% WhatsApp publicado</th><th>Enviados</th><th>% abrió</th><th>% respondió</th><th>Demos</th><th>Clientes</th><th>Puntaje</th></tr></thead>
      <tbody>${ns.map((n) => `<tr><td><button class="vp-btn vp-btn-sm vp-btn-link" type="button" data-vpm-niche="${h(n.key)}">${h(n.icon || "")} ${h(n.label)}</button><small>${n.page ? h(n.page) : "sin página propia (usa la principal)"} · prioridad ${h(n.priority || 1)}</small></td>
        <td>${h(num(n.prospectos))}</td>${chanCells(n)}<td>${h(num(n.enviados))}</td><td>${h(pct(n.abrieron, n.enviados))}</td><td>${h(pct(n.respondieron, n.enviados))}</td>
        <td>${h(num(n.demos))}</td><td>${h(num(n.clientes))}</td><td class="vp-mono">${h(num(n.puntaje))}</td></tr>`).join("")}</tbody></table></div></section>`;
  }

  function newZoneForm() {
    const z = model.newZone;
    if (!z) return "";
    return `<form class="vp-panel vp-section vp-form-grid vpm-newzone" data-vpm-zone-form>
      <p class="vp-login-hint">Toca el mapa para elegir el centro de la zona.</p>
      <label class="vp-field">Nombre<input name="name" required minlength="2" maxlength="120" value="${h(z.name || "")}"></label>
      <label class="vp-field">Grupo (localidad)<input name="group_name" maxlength="120" value="${h(z.group_name || "")}"></label>
      <label class="vp-field">Ciudad<input name="city" maxlength="80" value="${h(z.city || "Bogotá")}"></label>
      <label class="vp-field">Latitud<input name="center_lat" inputmode="decimal" required value="${h(z.center_lat ?? "")}" data-vpm-lat></label>
      <label class="vp-field">Longitud<input name="center_lng" inputmode="decimal" required value="${h(z.center_lng ?? "")}" data-vpm-lng></label>
      <label class="vp-field">Radio (m)<input name="radius_m" type="number" min="150" max="5000" value="${h(z.radius_m || 700)}"></label>
      ${z.error ? `<div class="vp-alert" role="alert"><span>${h(z.error)}</span></div>` : ""}
      <div class="vp-actions"><button class="vp-btn vp-btn-primary" type="submit">Guardar zona</button><button class="vp-btn" type="button" data-vpm-zone-cancel>Cancelar</button></div>
    </form>`;
  }

  function detailPanel() {
    if (model.detailError) return `<aside class="vp-panel vp-section vpm-detail"><div class="vp-alert" role="alert"><span>${h(model.detailError)}</span></div></aside>`;
    const d = model.detail;
    if (!d) return `<aside class="vp-panel vp-section vpm-detail"><p class="vp-login-hint">Toca un pin para ver la ficha del negocio.</p>${legend()}</aside>`;
    const p = d.prospect || {};
    const [label] = STATUS[p.status] || [p.status];
    const row = (k, v) => (v ? `<li><span>${h(k)}</span><b>${h(v)}</b></li>` : "");
    const web = safeUrl(p.website);
    const src = safeUrl(p.email_source_url);
    const maps = safeUrl(p.maps_url);
    const confirm = model.confirm === p.id;
    return `<aside class="vp-panel vp-section vpm-detail" data-vpm-detail="${h(p.id)}">
      <div class="vp-row-between"><h2>${h(p.name)}</h2><button class="vp-btn vp-btn-sm" type="button" data-vpm-close aria-label="Cerrar ficha">✕</button></div>
      <p><span class="vpm-dot is-${h(p.status)}" aria-hidden="true"></span> ${h(label)} · ${h(p.tipo || TYPES[p.business_type] || "")}${p.nicho ? ` · ${h(p.nicho)}` : ""}</p>
      <p class="vpm-vig is-${h(p.vigencia || "sin_dato")}"><b>${h(VIGENCIA[p.vigencia] || VIGENCIA.sin_dato)}</b>${p.vigencia_reason ? ` · ${h(p.vigencia_reason)}` : ""}${p.vigencia === "por_verificar" ? " · no entra a correo ni a la cola asistida: solo a la ruta de visitas" : ""}</p>
      <ul class="vpm-facts">${row("Zona", [p.zone_name, p.zone_group].filter(Boolean).join(" · "))}${row("Dirección", p.address)}${row("Teléfono", p.phone)}
        ${row("Correo", p.email)}${row("Código", p.code)}${row("Correos enviados", String(p.contact_count ?? 0))}
        ${row("Primer contacto", p.first_contacted_at && fecha(p.first_contacted_at))}${row("Abrió la landing", p.opened_at && fecha(p.opened_at))}
        ${row("Respondió", p.replied_at && fecha(p.replied_at))}${row("Consentimiento WhatsApp", p.wa_consent_at && fecha(p.wa_consent_at))}
        ${row("Baja", p.unsubscribed_at && fecha(p.unsubscribed_at))}</ul>
      <div class="vp-actions">${maps ? `<a class="vp-btn vp-btn-primary" href="${h(maps)}" target="_blank" rel="noopener noreferrer">Abrir en Google Maps</a>` : ""}
        ${web ? `<a class="vp-btn" href="${h(web)}" target="_blank" rel="noopener noreferrer">Web</a>` : ""}
        ${src ? `<a class="vp-btn" href="${h(src)}" target="_blank" rel="noopener noreferrer">De dónde salió el correo</a>` : ""}</div>
      ${p.status === "baja" ? "" : `<div class="vp-actions">
        <button class="vp-btn vp-btn-sm" type="button" data-vpm-status="demo">Marcar demo</button>
        <button class="vp-btn vp-btn-sm" type="button" data-vpm-status="cliente">Marcar cliente</button>
        <button class="vp-btn vp-btn-sm ${confirm ? "vp-btn-danger" : ""}" type="button" data-vpm-status="baja">${confirm ? "Confirmar baja permanente" : "Dar de baja"}</button></div>`}
      <h3>Canales públicos</h3>${channelsList(p)}
      <h3>Historial de contactos</h3>
      <ul class="vp-actions-list vpm-history">${arr(d.history).map((x) => `<li class="vp-action"><b>${h(KINDS[x.kind] || x.kind)}</b>
        <small>${h(fecha(x.sent_at || x.created_at))} · ${h(x.channel)} · ${h(x.status)}${x.subject ? ` · ${h(x.subject)}` : ""}${x.detail && x.detail.motivo ? ` · ${h(x.detail.motivo)}` : ""}</small></li>`).join("") || `<li class="vp-empty">Sin contactos todavía.</li>`}</ul>
    </aside>`;
  }

  function routePanel() {
    const r = model.route;
    if (!r) return "";
    const d = r.data;
    const zone = d ? d.zone.name : "";
    const stops = arr(d && d.stops);
    return `<section class="vp-panel vp-section vpm-route" data-vpm-route-panel>
      <div class="vp-row-between"><h2>🗺️ Ruta del día${zone ? ` · ${h(zone)}` : ""}</h2><button class="vp-btn vp-btn-sm" type="button" data-vpm-route-close aria-label="Cerrar ruta">✕</button></div>
      ${r.error ? `<div class="vp-alert" role="alert"><span>${h(r.error)}</span></div>` : ""}
      ${r.notice ? `<div class="vp-alert is-ok" role="status"><span>${h(r.notice)}</span></div>` : ""}
      ${!d ? `<p class="vp-loading">Armando la ruta…</p>` : !stops.length ? `<p class="vp-empty">No hay negocios para visitar en esta zona (sin baja, sin contacto esta semana y sin visita en 30 días).</p>` : `
      <p class="vp-login-hint">${h(stops.length)} negocios ordenados por cercanía desde el centro de la zona, ~${h(Math.round(Number(d.total_m || 0) / 100) / 10)} km a pie. Incluye los "por verificar". Visitas de lunes a viernes, 8:00 a 17:00.</p>
      <div class="vp-actions">${safeUrl(d.route_url) ? `<a class="vp-btn vp-btn-primary" href="${h(d.route_url)}" target="_blank" rel="noopener noreferrer">Abrir la ruta en Google Maps</a>` : ""}
        <button class="vp-btn" type="button" data-vpm-route-send>📨 Enviar a Telegram</button></div>
      <ol class="vpm-stops">${stops.map((x) => `<li><b>${h(x.name)}</b>${x.vigencia === "por_verificar" ? ` <small class="vpm-tag">por verificar</small>` : ""}
        <small>${h(x.nicho || "")} · ${h(x.tipo || "")} · ${h(x.address || "")} · ${h(x.desde_anterior_m)} m</small>
        <span class="vp-actions">${safeUrl(x.maps_url) ? `<a class="vp-btn vp-btn-sm" href="${h(x.maps_url)}" target="_blank" rel="noopener noreferrer">Abrir en Google Maps</a>` : ""}
        ${x.visitado ? `<span class="vpm-tag is-ok">✅ Visitado</span>` : `<button class="vp-btn vp-btn-sm" type="button" data-vpm-visited="${h(x.id)}">✅ Visitado</button>`}</span></li>`).join("")}</ol>`}
    </section>`;
  }

  function pane() {
    const d = model.data;
    return `<div class="vpm" data-vpm-root>
      ${model.notice ? `<div class="vp-alert is-ok" role="status"><span>${h(model.notice)}</span></div>` : ""}
      ${model.error ? `<div class="vp-alert" role="alert"><span>${h(model.error)}</span></div>` : ""}
      <div data-vpm-cards>${d ? cards(d) : `<p class="vp-loading">Cargando el mapa comercial…</p>`}</div>
      <div data-vpm-filters-host>${filtersForm(d)}</div>
      <div data-vpm-newzone-host>${newZoneForm()}</div>
      <div data-vpm-route-host>${routePanel()}</div>
      <section class="vp-panel vp-section vpm-mapbox">${layerToggles()}
        <div class="vpm-grid"><div class="vpm-map" data-vpm-canvas role="region" aria-label="Mapa comercial de Colombia"></div><div data-vpm-detail-host>${detailPanel()}</div></div>
        <p class="vpm-attrib">Mapa © <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">OpenStreetMap</a> ·
          Ubicación de visitas: <a href="https://db-ip.com" target="_blank" rel="noopener noreferrer">IP Geolocation by DB-IP</a> (precisión de ciudad, no de barrio).
          Las aperturas con código de prospecto sí son exactas.</p></section>
      <div data-vpm-zones>${d ? zonesTable(d) : ""}</div>
      <div data-vpm-niches>${d ? nichesTable(d) : ""}</div>
    </div>`;
  }

  // ------------------------------------------------------------ Leaflet
  let leafletPromise = null;
  function ensureLeaflet() {
    if (window.L && window.L.map) return Promise.resolve(window.L);
    if (leafletPromise) return leafletPromise;
    leafletPromise = new Promise((resolve, reject) => {
      if (!document.querySelector || !document.querySelector("link[data-vpm-leaflet]")) {
        const css = document.createElement("link");
        css.rel = "stylesheet"; css.href = "/admin-v2plus-leaflet.css"; css.setAttribute("data-vpm-leaflet", "1");
        document.head.appendChild(css);
      }
      const s = document.createElement("script");
      s.src = "/admin-v2plus-leaflet.js";
      s.onload = () => (window.L ? resolve(window.L) : reject(new Error("Leaflet no cargó")));
      s.onerror = () => { leafletPromise = null; reject(new Error("No se pudo cargar el mapa.")); };
      document.head.appendChild(s);
    });
    return leafletPromise;
  }

  function createMap(L, canvas) {
    const m = L.map(canvas, { center: BOGOTA, zoom: 13, minZoom: 5, maxBounds: L.latLngBounds(COLOMBIA).pad(0.25), attributionControl: true });
    m.attributionControl.setPrefix('<a href="https://leafletjs.com" target="_blank" rel="noopener noreferrer">Leaflet</a>');
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 19,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">OpenStreetMap</a>' }).addTo(m);
    m.on("click", (e) => {
      if (!model.newZone || !e || !e.latlng) return;
      model.newZone.center_lat = Number(e.latlng.lat.toFixed(5));
      model.newZone.center_lng = Number(e.latlng.lng.toFixed(5));
      paint("newzone");
    });
    return m;
  }

  function drawLayers(L) {
    if (!map || !L) return;
    if (groups) Object.values(groups).forEach((g) => g.remove());
    groups = { zonas: L.layerGroup(), visitas: L.layerGroup(), leads: L.layerGroup(), volantes: L.layerGroup(), prospectos: L.layerGroup() };
    const d = model.data || {};
    const zs = arr(d.zones).filter((z) => z.active !== false);
    const maxScore = Math.max(0, ...zs.map((z) => Number(z.puntaje || 0)));
    zs.forEach((z) => {
      const color = zoneColor(Number(z.puntaje || 0), maxScore);
      const opts = { color, weight: 2, dashArray: "6 6", fillColor: color, fillOpacity: 0.06 };
      const shape = z.kind === "polygon" && arr(z.polygon).length >= 3 ? L.polygon(z.polygon, opts) : L.circle([z.center_lat, z.center_lng], { ...opts, radius: z.radius_m });
      shape.bindTooltip(`${h(z.name)} · puntaje ${h(num(z.puntaje))} · ${h(num(z.prospectos))} prospectos · ${h(num(z.enviados))} correos · ${h(num(z.abrieron))} aperturas · ${h(num(z.respondieron))} respuestas · ${h(num(z.demos))} demos · ${h(num(z.clientes))} clientes`, { sticky: true });
      groups.zonas.addLayer(shape);
    });
    const hv = arr(d.heat_visits).filter((v) => v.lat != null && v.lng != null);
    const maxV = Math.max(0, ...hv.map((v) => Number(v.total || 0)));
    hv.forEach((v) => {
      groups.visitas.addLayer(L.circle([v.lat, v.lng], heatStyle(Number(v.total || 0), maxV, 2500, 9000, "#ff2d6f"))
        .bindTooltip(`${h(v.city)}${v.region ? `, ${h(v.region)}` : ""}: ${h(num(v.total))} visitas a la landing (aprox. por ciudad)`, { sticky: true }));
    });
    const hl = arr(d.heat_leads);
    const maxL = Math.max(0, ...hl.map((v) => Number(v.total || 0)));
    hl.forEach((v) => {
      groups.leads.addLayer(L.circle([v.lat, v.lng], heatStyle(Number(v.total || 0), maxL, 180, 420, "#22c55e"))
        .bindTooltip(`${h(num(v.total))} respuesta(s) o lead(s)`, { sticky: true }));
    });
    const hf = arr(d.heat_flyers).filter((v) => v.lat != null && v.lng != null);
    const maxF = Math.max(0, ...hf.map((v) => Number(v.total || 0)));
    hf.forEach((v) => {
      groups.volantes.addLayer(L.circle([v.lat, v.lng], heatStyle(Number(v.total || 0), maxF, Math.max(200, Number(v.radius_m || 600) * 0.5), Number(v.radius_m || 600), "#38bdf8"))
        .bindTooltip(`🖨️ ${h(v.zone)} · ${h(v.nicho || v.niche || "")}: ${h(num(v.total))} visitas por el QR del volante (${h(num(v.visitantes))} personas)`, { sticky: true }));
    });
    arr(d.pins).forEach((p) => {
      const [label] = STATUS[p.status] || [p.status];
      const [nl, icon] = NICHES[nicheOf(p)] || NICHES.restaurante;
      const mk = (L.divIcon && L.marker)
        ? L.marker([p.lat, p.lng], { icon: L.divIcon({ className: `vpm-pin is-${model.colorBy === "nicho" ? `n-${nicheOf(p)}` : h(p.status)}${p.vigencia === "por_verificar" ? " is-verify" : ""}`, html: h(icon), iconSize: [24, 24] }), keyboard: false })
        : L.circleMarker([p.lat, p.lng], { radius: 7, color: "#0b0710", weight: 1.5, fillColor: pinColor(p), fillOpacity: p.vigencia === "por_verificar" ? 0.4 : 0.95,
          dashArray: p.vigencia === "por_verificar" ? "2 3" : null });
      const ci = chanIcons(p.canales);
      mk.bindTooltip(`${h(icon)} ${h(p.name)}${ci ? ` ${h(ci)}` : ""} · ${h(nl)} · ${h(p.tipo || TYPES[p.business_type] || "")} · ${h(label)}${p.vigencia === "por_verificar" ? " · por verificar (solo visita)" : ""}${p.email ? ` · ${h(p.email)}` : ""}`);
      mk.on("click", () => openDetail(p.id));
      groups.prospectos.addLayer(mk);
    });
    Object.entries(groups).forEach(([k, g]) => { if (model.layers[k]) g.addTo(map); });
  }

  function syncLayers() {
    if (!map || !groups) return;
    Object.entries(groups).forEach(([k, g]) => {
      const on = map.hasLayer(g);
      if (model.layers[k] && !on) g.addTo(map);
      if (!model.layers[k] && on) g.remove();
    });
  }

  // ------------------------------------------------------------ pintar por partes (el mapa no se recrea)
  function paint(part) {
    if (!host || !host.querySelector) return;
    const set = (sel, html) => { const el = host.querySelector(sel); if (el) el.innerHTML = html; };
    if (!part || part === "data") {
      set("[data-vpm-cards]", model.data ? cards(model.data) : (model.error ? "" : `<p class="vp-loading">Cargando el mapa comercial…</p>`));
      set("[data-vpm-filters-host]", filtersForm(model.data));
      set("[data-vpm-zones]", model.data ? zonesTable(model.data) : "");
      set("[data-vpm-niches]", model.data ? nichesTable(model.data) : "");
    }
    if (!part || part === "detail" || part === "data") set("[data-vpm-detail-host]", detailPanel());
    if (!part || part === "newzone") set("[data-vpm-newzone-host]", newZoneForm());
    if (!part || part === "route") set("[data-vpm-route-host]", routePanel());
  }

  async function load() {
    model.loading = true;
    try { model.data = await api.map(model.filters); model.error = ""; } catch (error) { model.error = error.message; }
    model.loading = false;
    paint("data");
    if (window.L && map) drawLayers(window.L);
  }

  async function openRoute(zoneId) {
    model.route = { zone_id: zoneId, nicho: model.filters.nicho || "", data: null, error: "", notice: "" };
    paint("route");
    try { model.route.data = await api.route(zoneId, model.route.nicho); } catch (error) { model.route.error = error.message; }
    paint("route");
  }

  async function openDetail(id) {
    model.confirm = "";
    model.detailError = "";
    try { model.detail = await api.detail(id); } catch (error) { model.detail = null; model.detailError = error.message; }
    paint("detail");
  }

  // ------------------------------------------------------------ eventos (solo dentro del host)
  async function onClick(event) {
    const t = event.target;
    if (!t || !t.closest) return;
    const jump = t.closest("[data-vpm-jump]");
    if (jump && map) { if (jump.getAttribute("data-vpm-jump") === "colombia") map.fitBounds(COLOMBIA); else map.setView(BOGOTA, 13); return; }
    if (t.closest("[data-vpm-reset]")) { model.filters = EMPTY_FILTERS(); load(); return; }
    if (t.closest("[data-vpm-close]")) { model.detail = null; model.detailError = ""; paint("detail"); return; }
    if (t.closest("[data-vpm-new-zone]")) { model.newZone = model.newZone ? null : { radius_m: 700, city: "Bogotá" }; paint("newzone"); return; }
    if (t.closest("[data-vpm-zone-cancel]")) { model.newZone = null; paint("newzone"); return; }
    const rb = t.closest("[data-vpm-route]");
    if (rb) { openRoute(rb.getAttribute("data-vpm-route")); return; }
    if (t.closest("[data-vpm-route-close]")) { model.route = null; paint("route"); return; }
    if (t.closest("[data-vpm-route-send]") && model.route) {
      try { const r = await api.routeSend(model.route.zone_id, model.route.nicho); model.route.notice = r.ok ? `Ruta enviada a Telegram (${r.paradas} negocios).` : "No hay negocios para enviar."; model.route.error = ""; }
      catch (error) { model.route.error = error.message === "telegram_no_disponible" ? "Telegram no respondió: intenta de nuevo." : error.message; }
      paint("route"); return;
    }
    const vb = t.closest("[data-vpm-visited]");
    if (vb && model.route && model.route.data) {
      const id = vb.getAttribute("data-vpm-visited");
      try { const r = await api.visited(id); model.route.notice = r.mensaje || ""; model.route.error = r.ok ? "" : (r.mensaje || "");
        if (r.ok) arr(model.route.data.stops).forEach((x) => { if (x.id === id) x.visitado = true; }); }
      catch (error) { model.route.error = error.message; }
      paint("route"); return;
    }
    const fb = t.closest("[data-vpm-flyer]");
    if (fb) {
      const zid = fb.getAttribute("data-vpm-flyer");
      const sel = host.querySelector && host.querySelector(`[data-vpm-flyer-niche="${zid}"]`);
      const nicho = (sel && sel.value) || "restaurante";
      if (window.open) window.open(flyerUrl(zid, nicho), "_blank", "noopener");
      return;
    }
    const nb = t.closest("[data-vpm-niche]");
    if (nb) { model.filters = { ...model.filters, nicho: nb.getAttribute("data-vpm-niche") || "" }; load(); return; }
    const zb = t.closest("[data-vpm-zone]");
    if (zb) {
      const z = arr(model.data && model.data.zones).find((x) => String(x.id) === zb.getAttribute("data-vpm-zone"));
      if (z && map) map.setView([z.center_lat, z.center_lng], 15);
      return;
    }
    const st = t.closest("[data-vpm-status]");
    if (st && model.detail && model.detail.prospect) {
      const estado = st.getAttribute("data-vpm-status");
      const id = model.detail.prospect.id;
      if (estado === "baja" && model.confirm !== id) { model.confirm = id; paint("detail"); return; }
      try { await api.status(id, estado); model.notice = estado === "baja" ? "Negocio dado de baja (lista de exclusión permanente)." : `Marcado como ${STATUS[estado][0].toLowerCase()}.`; }
      catch (error) { model.detailError = error.message; }
      await openDetail(id);
      load();
    }
  }

  function onChange(event) {
    const t = event.target;
    if (t && t.matches && t.matches("[data-vpm-color]")) { model.colorBy = t.value === "nicho" ? "nicho" : "estado"; paint("detail"); if (window.L && map) drawLayers(window.L); return; }
    if (!t || !t.matches || !t.matches("[data-vpm-layer]")) return;
    model.layers[t.getAttribute("data-vpm-layer")] = Boolean(t.checked);
    syncLayers();
  }

  async function onSubmit(event) {
    const form = event.target;
    if (!form || !form.matches) return;
    if (form.matches("[data-vpm-filters]")) {
      event.preventDefault();
      const d = new FormData(form);
      model.filters = { zone_id: String(d.get("zone_id") || ""), nicho: String(d.get("nicho") || ""), tipo: String(d.get("tipo") || ""), estado: String(d.get("estado") || ""), vigencia: String(d.get("vigencia") || ""),
        desde: String(d.get("desde") || ""), hasta: String(d.get("hasta") || "") };
      load();
      return;
    }
    if (form.matches("[data-vpm-zone-form]")) {
      event.preventDefault();
      const d = new FormData(form);
      const z = { name: String(d.get("name") || "").trim(), group_name: String(d.get("group_name") || "").trim(), city: String(d.get("city") || "Bogotá").trim(),
        center_lat: Number(String(d.get("center_lat") || "").replace(",", ".")), center_lng: Number(String(d.get("center_lng") || "").replace(",", ".")),
        radius_m: Number(d.get("radius_m") || 700) };
      if (!Number.isFinite(z.center_lat) || !Number.isFinite(z.center_lng)) { model.newZone = { ...z, error: "Toca el mapa o escribe la latitud y longitud." }; paint("newzone"); return; }
      try { await api.createZone(z); model.newZone = null; model.notice = `Zona "${z.name}" agregada: Nexa la empieza a prospectar en la próxima corrida.`; }
      catch (error) { model.newZone = { ...z, error: error.message === "zona_repetida" ? "Ya existe una zona con ese nombre." : error.message }; }
      paint("newzone");
      load();
    }
  }

  // ------------------------------------------------------------ montar
  function mount(el) {
    if (!el) return;
    if (el === host && el.querySelector && el.querySelector("[data-vpm-root]")) return;
    host = el;
    host.innerHTML = pane();
    if (host.addEventListener) {
      host.addEventListener("click", onClick);
      host.addEventListener("change", onChange);
      host.addEventListener("submit", onSubmit);
    }
    if (map) { try { map.remove(); } catch (_) {} map = null; groups = null; }
    ensureLeaflet().then((L) => {
      const canvas = host.querySelector && host.querySelector("[data-vpm-canvas]");
      if (!canvas) return;
      map = createMap(L, canvas);
      drawLayers(L);
    }).catch((error) => { model.error = error.message; paint("data"); });
    load();
    if (model.openId) { const id = model.openId; model.openId = ""; openDetail(id); }   // #mapa/{prospecto}
  }

  window.CxConsoleMapa = { routePanel, openRoute, flyerUrl, CHANNELS, channelsList, VIGENCIA, model, api, mapUrl, pane, cards, zonesTable, nichesTable, filtersForm, detailPanel, mount, drawLayers, heatStyle, zoneColor, pinColor, STATUS, TYPES, NICHES,
    _setMap: (m) => { map = m; } };
})();
