// Personal v2 (interruptor workforce_v2 del modulo workforce). client.js solo
// la monta cuando el interruptor esta encendido; la pantalla de siempre queda
// como respaldo. Mismas funciones y mismos endpoints que la pantalla de
// siempre: agregar, editar todos los campos, guardar, activar, inactivar,
// eliminar (archiva), buscar, filtros, CSV, Historial y Asistencia (estos dos
// por los mismos data-attributes que ya atiende client.js).
// Colores: solo los del tema. Los pares fondo/texto que deben pasar AA
// (titulos de columna, filtro activo, Guardar, Eliminar) se calculan aqui a
// partir de --cx-primary, --cx-text, --cx-bg y --cx-danger: si el par del tema
// no llega a 4.5:1, se oscurece o aclara ese mismo color hasta llegar.
(() => {
  "use strict";

  const h = (v) => String(v ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
  const arr = (v) => (Array.isArray(v) ? v : []);
  const fold = (v) => String(v ?? "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
  const STATUS = { active: "Activo", inactive: "Inactivo", archived: "Archivado" };
  const FILTERS = [["all", "Todos"], ["active", "Activos"], ["inactive", "Inactivos"], ["archived", "Archivados"]];
  const FIELDS = ["full_name", "document_id", "role", "phone", "email", "telegram_user_id", "hire_date", "hourly_rate_regular", "hourly_rate_extra", "deduction_1", "deduction_2", "status"];
  const MONEY = ["hourly_rate_regular", "hourly_rate_extra", "deduction_1", "deduction_2"];
  const CSV_HEAD = ["Nombre", "Documento", "Rol", "Telefono", "Correo", "Telegram ID", "Fecha ingreso", "Hora ordinaria", "Hora extra", "Descuento 1", "Descuento 2", "Estado"];

  // pins: null = CRM VELVET-LAB apagado (el servidor responde 404) y no se muestra nada de PIN.
  // wl: null = interruptor work_locations apagado: no se muestra nada de lugares y el
  // formulario conserva Descuento 2 (todo exactamente como antes).
  const model = { employees: [], filter: "all", query: "", menu: "", modal: null, notice: "", error: "", busy: false, loaded: false, pins: null,
    wl: null, wlFilter: "all", selected: new Set() };
  let ctx = null;
  let bound = false;

  // ------------------------------------------------------------ reglas puras
  function statusOf(e) {
    const s = fold(e && e.status);
    if (s === "archived" || s === "archivado") return "archived";
    if (s === "inactive" || s === "inactivo") return "inactive";
    return "active";
  }

  // roles: [[code, label]] que ofrece la empresa (configuracion o lista de siempre).
  function roleLabel(roles, code) {
    const found = arr(roles).find(([value]) => value === code);
    if (found) return found[1];
    return String(code || "").replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
  }
  function roleEnabled(roles, configured, code) {
    return !configured || arr(roles).some(([value]) => value === code);
  }
  function roleOf(e) { return String((e && (e.role || e.employee_type)) || "operator"); }

  function stats(list) {
    const out = { total: 0, active: 0, inactive: 0, archived: 0 };
    arr(list).forEach((e) => { out.total += 1; out[statusOf(e)] += 1; });
    return out;
  }

  function searchText(e, roles) {
    return fold([e.full_name, e.document_id, roleOf(e), roleLabel(roles, roleOf(e)), e.phone, e.email, e.telegram_user_id, e.hire_date, STATUS[statusOf(e)]].join(" "));
  }

  // 059A Lugares de trabajo (solo con wl): lugar actual de cada empleado.
  // wl = { locations: [{id, name, code, timezone, is_active}], assignments: {employee_id: location_id|null} }
  const WL_NONE = "none";
  function wlPlaceId(wl, e) {
    if (!wl) return null;
    const id = (wl.assignments || {})[String(e && e.id)] || null;
    return id && arr(wl.locations).some((l) => l.id === id) ? id : null;
  }
  function wlPlaceName(wl, e) {
    const id = wlPlaceId(wl, e);
    const loc = id ? arr(wl.locations).find((l) => l.id === id) : null;
    return loc ? loc.name : "Sin asignar";
  }
  function wlFilters(wl) {
    if (!wl) return [];
    return [["all", "Todos"], ...arr(wl.locations).filter((l) => l.is_active).map((l) => [l.id, l.name]), [WL_NONE, "Sin asignar"]];
  }
  function wlMatch(wl, e, wlFilter) {
    if (!wl || !wlFilter || wlFilter === "all") return true;
    const id = wlPlaceId(wl, e);
    return wlFilter === WL_NONE ? !id : id === wlFilter;
  }

  function visible(list, filter, query, roles, wl = null, wlFilter = "all") {
    const q = fold(query).trim();
    return arr(list)
      .filter((e) => filter === "all" || statusOf(e) === filter)
      .filter((e) => wlMatch(wl, e, wlFilter))
      .filter((e) => !q || (searchText(e, roles) + (wl ? " " + fold(wlPlaceName(wl, e)) : "")).includes(q))
      .sort((a, b) => String(a.full_name || "").localeCompare(String(b.full_name || ""), "es", { sensitivity: "base" }));
  }

  function csvText(list, roles, wl = null) {
    const head = wl ? [...CSV_HEAD, "Lugar"] : CSV_HEAD;
    const rows = [head].concat(arr(list).map((e) => {
      const line = [e.full_name, e.document_id, roleLabel(roles, roleOf(e)), e.phone, e.email, e.telegram_user_id, e.hire_date,
        e.hourly_rate_regular, e.hourly_rate_extra, e.deduction_1, e.deduction_2, STATUS[statusOf(e)]];
      return wl ? [...line, wlPlaceName(wl, e)] : line;
    }));
    return rows.map((line) => line.map((v) => `"${String(v ?? "").replace(/"/g, '""')}"`).join(",")).join("\n");
  }

  // Con lugares, Descuento 2 no está en el formulario: se envía el valor ya
  // guardado (o 0 al crear) para que el dato y la nómina no cambien.
  function keepDeduction2(values, original) {
    const kept = original && original.deduction_2 !== undefined && original.deduction_2 !== null ? String(original.deduction_2) : "0";
    return { ...values, deduction_2: kept };
  }

  function assignLabel(count, placeName) {
    const who = count === 1 ? "1 empleado" : `${count} empleados`;
    return placeName === "Sin asignar" ? `Quitar el lugar a ${who}` : `Asignar ${who} a ${placeName}`;
  }

  // Mismo cuerpo que payloadFromPersonalRow de la pantalla de siempre.
  function payloadOf(companyId, values) {
    const payload = { company_id: companyId };
    FIELDS.forEach((key) => {
      let value = values[key];
      if (MONEY.includes(key)) value = value === "" || value === undefined || value === null ? 0 : Number(value);
      payload[key] = value === "" || value === undefined ? null : value;
    });
    payload.employee_type = payload.role || "operator";
    return payload;
  }

  function money(v) {
    if (typeof window !== "undefined" && window.CxLocale && window.CxLocale.foreign() && v !== null && v !== undefined) return window.CxLocale.money(Number(v)); // Fase A
    const n = Number(v || 0);
    return Number.isFinite(n) ? n.toLocaleString("es-CO", { maximumFractionDigits: 2 }) : String(v ?? "");
  }

  // ------------------------------------------------------------ contraste
  function parse(value) {
    const srgb = String(value || "").match(/color\(srgb ([^)]+)\)/);
    if (srgb) {
      const p = srgb[1].split(/[ /]+/).filter(Boolean).map(Number);
      return { r: Math.round(p[0] * 255), g: Math.round(p[1] * 255), b: Math.round(p[2] * 255) };
    }
    const m = String(value || "").match(/rgba?\(([^)]+)\)/);
    if (!m) return null;
    const p = m[1].split(/[ ,/]+/).filter(Boolean).map(Number);
    return { r: p[0], g: p[1], b: p[2] };
  }
  function lum(c) {
    const f = (x) => { x /= 255; return x <= 0.03928 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4; };
    return 0.2126 * f(c.r) + 0.7152 * f(c.g) + 0.0722 * f(c.b);
  }
  function contrast(a, b) {
    const x = lum(a) + 0.05;
    const y = lum(b) + 0.05;
    return Math.max(x, y) / Math.min(x, y);
  }
  function mix(c, toward, t) {
    return { r: Math.round(c.r + (toward.r - c.r) * t), g: Math.round(c.g + (toward.g - c.g) * t), b: Math.round(c.b + (toward.b - c.b) * t) };
  }
  const css = (c) => `rgb(${c.r}, ${c.g}, ${c.b})`;

  // Par fondo/texto AA: el texto es el candidato del tema que mas contrasta; si no
  // llega a la meta, el fondo (color del tema) se oscurece o aclara de a 5 %.
  function pair(bg, candidates, goal = 4.5) {
    const fgs = candidates.filter(Boolean);
    let best = fgs[0];
    fgs.forEach((c) => { if (contrast(bg, c) > contrast(bg, best)) best = c; });
    if (contrast(bg, best) >= goal) return { bg, fg: best };
    const toward = lum(best) > 0.4 ? { r: 0, g: 0, b: 0 } : { r: 255, g: 255, b: 255 };
    for (let t = 0.05; t <= 1.0001; t += 0.05) {
      const next = mix(bg, toward, t);
      if (contrast(next, best) >= goal) return { bg: next, fg: best };
    }
    return { bg: toward, fg: best };
  }

  function themeColor(root, expr) {
    const probe = document.createElement("span");
    probe.style.color = expr;
    probe.style.display = "none";
    root.appendChild(probe);
    const value = parse(getComputedStyle(probe).color);
    probe.remove();
    return value;
  }

  function applyContrast(root) {
    if (!root || typeof getComputedStyle !== "function") return;
    const text = themeColor(root, "var(--cx-text)") || { r: 255, g: 255, b: 255 };
    const bg = themeColor(root, "var(--cx-bg)") || { r: 15, g: 23, b: 42 };
    const primary = themeColor(root, "var(--cx-primary)") || bg;
    const danger = themeColor(root, "var(--cx-danger, #b91c1c)") || primary;
    // Superficie de la tabla y las tarjetas: el fondo del tema, ajustado para que el texto del tema pase con margen (7:1).
    const surface = pair(bg, [text], 7);
    const head = pair(primary, [text, surface.bg]);
    const del = pair(danger, [text, surface.bg]);
    const set = (k, v) => root.style.setProperty(k, v);
    set("--wf-surface", css(surface.bg));
    set("--wf-on-surface", css(surface.fg));
    set("--wf-head-bg", css(head.bg));
    set("--wf-head-fg", css(head.fg));
    set("--wf-danger-bg", css(del.bg));
    set("--wf-danger-fg", css(del.fg));
  }

  // ------------------------------------------------------------ dibujo
  function roles() { return ctx ? arr(ctx.roles()) : []; }
  function configured() { return Boolean(ctx && ctx.configured && ctx.configured()); }

  function roleOptions(selected) {
    const list = roles();
    const options = list.some(([value]) => value === selected) ? list : [...list, [selected, `${roleLabel(list, selected)} (rol no habilitado)`]];
    return options.map(([value, label]) => `<option value="${h(value)}" ${value === selected ? "selected" : ""}>${h(label)}</option>`).join("");
  }

  function rolePill(e) {
    const code = roleOf(e);
    const off = !roleEnabled(roles(), configured(), code);
    return `<span class="wf-role-text">${h(roleLabel(roles(), code))}</span>${off ? ' <span class="wf-pill wf-pill-warn" title="El rol no está habilitado para la empresa; no se cambió">rol no habilitado</span>' : ""}`;
  }

  function statusPill(e) {
    const s = statusOf(e);
    return `<span class="wf-pill wf-pill-${s}">${h(STATUS[s])}</span>`;
  }

  function menu(e) {
    const id = String(e.id || "");
    const s = statusOf(e);
    const open = model.menu === id;
    const items = [`<button type="button" role="menuitem" class="wf-menu-item" data-wf2-edit="${h(id)}">Editar</button>`];
    if (s !== "active") items.push(`<button type="button" role="menuitem" class="wf-menu-item" data-wf2-act="activate" data-id="${h(id)}">Activar</button>`);
    if (s === "active") items.push(`<button type="button" role="menuitem" class="wf-menu-item" data-wf2-act="deactivate" data-id="${h(id)}">Inactivar</button>`);
    // 056F: PIN del CRM VELVET-LAB (solo con el interruptor crm_velvet_lab).
    if (model.pins && s === "active") {
      const has = !!(model.pins[id] && model.pins[id].has_pin);
      items.push(`<button type="button" role="menuitem" class="wf-menu-item" data-wf2-pin="${h(id)}">${has ? "Reiniciar PIN CRM" : "Asignar PIN CRM"}</button>`);
      if (has) items.push(`<button type="button" role="menuitem" class="wf-menu-item" data-wf2-pin-clear="${h(id)}">Quitar PIN CRM</button>`);
    }
    if (s !== "archived") items.push(`<button type="button" role="menuitem" class="wf-menu-item wf-menu-danger" data-wf2-delete="${h(id)}">Eliminar</button>`);
    return `<div class="wf-menu ${open ? "is-open" : ""}">
      <button class="client-btn wf-menu-btn" type="button" aria-haspopup="menu" aria-expanded="${open}" data-wf2-menu="${h(id)}" aria-label="Acciones de ${h(e.full_name || "empleado")}">Acciones <span aria-hidden="true">▾</span></button>
      ${open ? `<div class="wf-menu-list" role="menu">${items.join("")}</div>` : ""}
    </div>`;
  }

  function pinBadge(e) {
    if (!model.pins || statusOf(e) !== "active") return "";
    const has = !!(model.pins[String(e.id)] && model.pins[String(e.id)].has_pin);
    return `<span class="wf-pin ${has ? "is-on" : ""}">${has ? "PIN CRM ✓" : "Sin PIN CRM"}</span>`;
  }

  const dash = (v) => (v === null || v === undefined || String(v).trim() === "" ? '<span class="wf-sub">—</span>' : h(v));

  // Persona: nombre, rol y contacto (teléfono, correo y Telegram juntos); Contrato:
  // ingreso, horas (ordinaria y extra) y descuentos (1 y 2). Cabe a 1280 px sin desplazar.
  const pairLine = (label, value) => `<span class="wf-kv"><span class="wf-sub">${h(label)}</span> ${value}</span>`;

  // 059A: chip del lugar y casilla de selección (solo con lugares).
  function placeChip(e) {
    if (!model.wl) return "";
    const id = wlPlaceId(model.wl, e);
    return `<span class="wf-place ${id ? "" : "is-none"}">${h(wlPlaceName(model.wl, e))}</span>`;
  }
  function pickBox(e) {
    if (!model.wl || !model.wl.can_assign) return "";
    const id = String(e.id || "");
    return `<input type="checkbox" class="wf-pick" data-wf2-pick="${h(id)}" ${model.selected.has(id) ? "checked" : ""} aria-label="Seleccionar a ${h(e.full_name || "empleado")}">`;
  }

  function tableView(list) {
    const wl = Boolean(model.wl);
    const pick = wl && model.wl.can_assign;
    const allOn = pick && list.length > 0 && list.every((e) => model.selected.has(String(e.id)));
    return `<div class="wf-table-wrap wf-scroll"><table class="wf-table${wl ? " wf-has-wl" : ""}">
      <thead>
        <tr><th class="wf-group" colspan="${wl ? 4 : 3}" scope="colgroup">Persona</th><th class="wf-group" colspan="3" scope="colgroup">Contrato</th>
          <th class="wf-th" rowspan="2" scope="col">Estado</th><th class="wf-th" rowspan="2" scope="col">Acciones</th></tr>
        <tr><th class="wf-th" scope="col">${pick ? `<label class="wf-pickhead"><input type="checkbox" class="wf-pick" data-wf2-pick-all ${allOn ? "checked" : ""} aria-label="Seleccionar todos los que se ven"> Nombre</label>` : "Nombre"}</th><th class="wf-th" scope="col">Rol</th>${wl ? '<th class="wf-th" scope="col">Lugar</th>' : ""}<th class="wf-th" scope="col">Documento · teléfono · correo · Telegram ID</th>
          <th class="wf-th" scope="col">Ingreso</th><th class="wf-th wf-num" scope="col">Hora ordinaria · extra</th><th class="wf-th wf-num" scope="col">Descuentos</th></tr>
      </thead>
      <tbody>${list.map((e) => `<tr class="wf-row wf-row-${statusOf(e)}" data-wf2-row="${h(e.id)}">
        <td class="wf-namecell">${pick ? `<label class="wf-pickname">${pickBox(e)}<span class="wf-name">${h(e.full_name || "Sin nombre")}</span></label>` : `<span class="wf-name">${h(e.full_name || "Sin nombre")}</span>`}${pinBadge(e)}</td>
        <td class="wf-role">${rolePill(e)}</td>${wl ? `<td class="wf-placecell">${placeChip(e)}</td>` : ""}
        <td class="wf-contact">${pairLine("Doc.", dash(e.document_id))}${pairLine("Tel.", dash(e.phone))}${pairLine("Correo", `<span class="wf-wrap">${dash(e.email)}</span>`)}${pairLine("Telegram", dash(e.telegram_user_id))}</td>
        <td class="wf-date">${dash(e.hire_date)}</td>
        <td class="wf-num">${pairLine("Ord.", h(money(e.hourly_rate_regular)))}${pairLine("Extra", h(money(e.hourly_rate_extra)))}</td>
        <td class="wf-num">${pairLine("1:", h(money(e.deduction_1)))}${pairLine("2:", h(money(e.deduction_2)))}</td>
        <td>${statusPill(e)}</td>
        <td>${menu(e)}</td>
      </tr>`).join("")}</tbody>
    </table></div>`;
  }

  function cardsView(list) {
    const line = (label, value) => `<div class="wf-card-line"><span class="wf-card-label">${h(label)}</span><span class="wf-card-value">${value}</span></div>`;
    return `<div class="wf-cards">${list.map((e) => `<article class="wf-card wf-row-${statusOf(e)}" data-wf2-card="${h(e.id)}">
      <div class="wf-card-head">${model.wl ? `<label class="wf-card-pick">${pickBox(e)}<span class="wf-name">${h(e.full_name || "Sin nombre")}</span></label>` : `<span class="wf-name">${h(e.full_name || "Sin nombre")}</span>`}${statusPill(e)}</div>
      <div class="wf-card-role">${rolePill(e)}${placeChip(e)}${pinBadge(e)}</div>
      <div class="wf-card-group"><span class="wf-card-title">Persona</span>
        ${line("Documento", dash(e.document_id))}${line("Teléfono", dash(e.phone))}${line("Correo", dash(e.email))}${line("Telegram ID", dash(e.telegram_user_id))}</div>
      <div class="wf-card-group"><span class="wf-card-title">Contrato</span>
        ${line("Ingreso", dash(e.hire_date))}${line("Hora ordinaria", h(money(e.hourly_rate_regular)))}${line("Hora extra", h(money(e.hourly_rate_extra)))}
        ${line("Descuento 1", h(money(e.deduction_1)))}${line("Descuento 2", h(money(e.deduction_2)))}</div>
      <div class="wf-card-actions">${menu(e)}</div>
    </article>`).join("")}</div>`;
  }

  // ------------------------------------------------------------ 059A lugares
  const TIMEZONES = ["America/New_York", "America/Chicago", "America/Denver", "America/Phoenix", "America/Los_Angeles", "America/Anchorage",
    "Pacific/Honolulu", "America/Puerto_Rico", "America/Bogota", "America/Mexico_City", "America/Lima", "America/Santiago", "Europe/Madrid"];

  function placeOptions(selected, { includeInactive = false } = {}) {
    const locs = arr(model.wl && model.wl.locations).filter((l) => l.is_active || includeInactive || l.id === selected);
    return [`<option value="${WL_NONE}" ${!selected ? "selected" : ""}>Sin asignar</option>`]
      .concat(locs.map((l) => `<option value="${h(l.id)}" ${l.id === selected ? "selected" : ""}>${h(l.name)}${l.is_active ? "" : " (desactivado)"}</option>`)).join("");
  }

  function placeSelect(e) {
    const current = e && e.id ? wlPlaceId(model.wl, e) : null;
    const disabled = model.wl.can_assign ? "" : "disabled";
    return `<label class="wf-field"><span>Lugar de trabajo</span><select name="work_location_id" ${disabled}>${placeOptions(current)}</select></label>`;
  }

  function assignModal(md, err) {
    const target = md.target || WL_NONE;
    const loc = arr(model.wl.locations).find((l) => l.id === target);
    const label = assignLabel(md.ids.length, loc ? loc.name : "Sin asignar");
    return `<div class="wf-modal" data-wf2-modal><form class="wf-modal-card" role="dialog" aria-modal="true" aria-labelledby="wf2ModalTitle" data-wf2-assignform>
      <h2 id="wf2ModalTitle">Asignar lugar</h2>
      <p>${md.ids.length === 1 ? "1 empleado seleccionado." : `${md.ids.length} empleados seleccionados.`} Cada traslado queda en el historial con la fecha y quién lo hizo.</p>${err}
      <label class="wf-field"><span>Lugar de trabajo</span><select name="work_location_id" data-wf2-assign-target>${placeOptions(target === WL_NONE ? null : target)}</select></label>
      <div class="wf-modal-actions"><button class="wf-btn-primary" type="submit" ${model.busy ? "disabled" : ""}>${h(label)}</button>
        <button class="client-btn" type="button" data-wf2-close>Cancelar</button></div></form></div>`;
  }

  function placesModal(md, err) {
    const rows = md.rows;
    const tzOptions = (tz) => [...new Set([tz, ...TIMEZONES].filter(Boolean))].map((z) => `<option value="${h(z)}" ${z === tz ? "selected" : ""}>${h(z)}</option>`).join("");
    return `<div class="wf-modal" data-wf2-modal><form class="wf-modal-card wf-places" role="dialog" aria-modal="true" aria-labelledby="wf2ModalTitle" data-wf2-placesform>
      <h2 id="wf2ModalTitle">Administrar lugares</h2>
      <p>Los lugares no se borran: desactívalos y dejan de ofrecerse (el historial los conserva). El orden es el de las secciones del CRM Campo.</p>${err}
      <div class="wf-places-list">${rows.map((r, i) => `<fieldset class="wf-fieldset wf-place-row" data-wf2-place-row="${i}"><legend>${h(r.name || "Lugar nuevo")}</legend><div class="wf-form-grid">
        <label class="wf-field"><span>Nombre</span><input data-wf2-place-field="name" data-i="${i}" value="${h(r.name)}" required minlength="2" maxlength="80" autocomplete="off"></label>
        <label class="wf-field"><span>Estado / sigla</span><input data-wf2-place-field="code" data-i="${i}" value="${h(r.code || "")}" maxlength="8" autocomplete="off"></label>
        <label class="wf-field"><span>Zona horaria</span><select data-wf2-place-field="timezone" data-i="${i}">${tzOptions(r.timezone)}</select></label>
        <label class="wf-field wf-check"><input type="checkbox" data-wf2-place-field="is_active" data-i="${i}" ${r.is_active ? "checked" : ""}><span>Activo</span></label>
      </div><div class="wf-place-move">
        <button class="client-btn" type="button" data-wf2-place-up="${i}" ${i === 0 ? "disabled" : ""} aria-label="Subir ${h(r.name)}">↑ Subir</button>
        <button class="client-btn" type="button" data-wf2-place-down="${i}" ${i === rows.length - 1 ? "disabled" : ""} aria-label="Bajar ${h(r.name)}">↓ Bajar</button>
      </div></fieldset>`).join("")}</div>
      <button class="client-btn" type="button" data-wf2-place-add>+ Agregar lugar</button>
      <div class="wf-modal-actions"><button class="wf-btn-primary" type="submit" ${model.busy ? "disabled" : ""}>Guardar lugares</button>
        <button class="client-btn" type="button" data-wf2-close>Cancelar</button></div></form></div>`;
  }

  function selectionBar() {
    if (!model.wl || !model.wl.can_assign || !model.selected.size) return "";
    const n = model.selected.size;
    return `<div class="wf-selbar" role="region" aria-label="Selección">
      <strong>${n === 1 ? "1 seleccionado" : `${n} seleccionados`}</strong>
      <button class="wf-btn-primary" type="button" data-wf2-assign>Asignar lugar</button>
      <button class="client-btn" type="button" data-wf2-pick-clear>Quitar selección</button>
    </div>`;
  }

  function modalView() {
    const md = model.modal;
    if (!md) return "";
    const err = md.error ? `<div class="wf-alert" role="alert">${h(md.error)}</div>` : "";
    if (md.type === "delete") {
      return `<div class="wf-modal" data-wf2-modal><div class="wf-modal-card" role="dialog" aria-modal="true" aria-labelledby="wf2ModalTitle">
        <h2 id="wf2ModalTitle">Eliminar a ${h(md.name)}</h2>
        <p>Se archiva para auditoría: deja de aparecer en Activos, su historial se conserva y se puede volver a activar.</p>${err}
        <div class="wf-modal-actions"><button class="wf-btn-danger" type="button" data-wf2-delete-go="${h(md.id)}" ${model.busy ? "disabled" : ""}>Eliminar</button>
          <button class="client-btn" type="button" data-wf2-close>Cancelar</button></div></div></div>`;
    }
    if (md.type === "pin") {
      return `<div class="wf-modal" data-wf2-modal><form class="wf-modal-card" role="dialog" aria-modal="true" aria-labelledby="wf2ModalTitle" data-wf2-pinform="${h(md.id)}">
        <h2 id="wf2ModalTitle">PIN CRM de ${h(md.name)}</h2>
        <p>4 dígitos. Lo usa en la tableta del taller (CRM VELVET-LAB). Se guarda cifrado: nadie puede verlo después, solo reiniciarlo.</p>${err}
        <label class="wf-field"><span>PIN nuevo</span><input name="pin" inputmode="numeric" pattern="[0-9]{4}" maxlength="4" minlength="4" autocomplete="off" required></label>
        <div class="wf-modal-actions"><button class="wf-btn-primary" type="submit" ${model.busy ? "disabled" : ""}>Guardar PIN</button>
          <button class="client-btn" type="button" data-wf2-close>Cancelar</button></div></form></div>`;
    }
    if (md.type === "assign") return assignModal(md, err);
    if (md.type === "places") return placesModal(md, err);
    const e = md.employee || {};
    const field = (name, label, attrs = "") => `<label class="wf-field"><span>${h(label)}</span><input name="${name}" value="${h(e[name] ?? "")}" ${attrs}></label>`;
    const role = roleOf(e);
    return `<div class="wf-modal" data-wf2-modal><form class="wf-modal-card" role="dialog" aria-modal="true" aria-labelledby="wf2ModalTitle" data-wf2-form="${h(e.id || "")}">
      <h2 id="wf2ModalTitle">${e.id ? `Editar a ${h(e.full_name || "empleado")}` : "Agregar empleado"}</h2>${err}
      <fieldset class="wf-fieldset"><legend>Persona</legend><div class="wf-form-grid">
        ${field("full_name", "Nombre completo", 'required minlength="2" autocomplete="off"')}
        ${field("document_id", "Documento (opcional)", 'autocomplete="off" maxlength="80"')}
        <label class="wf-field"><span>Rol</span><select name="role" class="wf-role-select">${roleOptions(role)}</select></label>
        ${field("phone", "Teléfono", 'inputmode="tel" autocomplete="off"')}
        ${field("email", "Correo", 'type="email" autocomplete="off"')}
        ${field("telegram_user_id", "Telegram ID", 'inputmode="numeric" autocomplete="off"')}
      </div></fieldset>
      <fieldset class="wf-fieldset"><legend>Contrato</legend><div class="wf-form-grid">
        ${field("hire_date", "Fecha de ingreso", 'placeholder="AAAA-MM-DD" autocomplete="off"')}
        ${field("hourly_rate_regular", "Hora ordinaria", 'type="number" step="0.01" min="0"')}
        ${field("hourly_rate_extra", "Hora extra", 'type="number" step="0.01" min="0"')}
        ${field("deduction_1", "Descuento 1", 'type="number" step="0.01" min="0"')}
        ${model.wl ? placeSelect(e) : field("deduction_2", "Descuento 2", 'type="number" step="0.01" min="0"')}
        <label class="wf-field"><span>Estado</span><select name="status">${Object.entries(STATUS).map(([v, l]) => `<option value="${v}" ${statusOf(e) === v ? "selected" : ""}>${l}</option>`).join("")}</select></label>
      </div></fieldset>
      <div class="wf-modal-actions"><button class="wf-btn-primary" type="submit" ${model.busy ? "disabled" : ""}>Guardar</button>
        <button class="client-btn" type="button" data-wf2-close>Cancelar</button></div>
    </form></div>`;
  }

  function view() {
    const s = stats(model.employees);
    const list = visible(model.employees, model.filter, model.query, roles(), model.wl, model.wlFilter);
    const placeFilters = wlFilters(model.wl);
    return `<div class="wf-root">
      <header class="client-hero wf-head">
        <div class="wf-head-text"><div class="client-eyebrow">Workforce</div><h1 class="client-title">Personal</h1>
          <p class="client-muted">Empleados, roles y contrato que usan el bot, la nómina y la operación.</p></div>
        <div class="wf-head-actions">
          <button class="wf-btn-primary" type="button" data-wf2-add>+ Agregar empleado</button>
          <button class="client-btn" type="button" data-personal-history>Historial</button>
          <button class="client-btn" type="button" data-personal-asistencia>Asistencia</button>
          ${model.wl && model.wl.can_manage ? '<button class="client-btn" type="button" data-wf2-places>Administrar lugares</button>' : ""}
          <button class="client-btn" type="button" data-client-back-dashboard>Volver</button>
        </div>
      </header>
      ${model.notice ? `<div class="wf-notice" role="status">${h(model.notice)}</div>` : ""}
      ${model.error && !model.modal ? `<div class="wf-alert" role="alert">${h(model.error)}</div>` : ""}
      <div class="wf-stats" aria-label="Cifras de personal">
        <div class="wf-stat"><span>Total</span><strong>${s.total}</strong></div>
        <div class="wf-stat"><span>Activos</span><strong>${s.active}</strong></div>
        <div class="wf-stat"><span>Inactivos</span><strong>${s.inactive}</strong></div>
        <div class="wf-stat"><span>Archivados</span><strong>${s.archived}</strong></div>
      </div>
      <section class="client-panel wf-panel">
        <div class="wf-tools">
          <input class="wf-search" type="search" data-wf2-search value="${h(model.query)}" placeholder="Buscar en personal" aria-label="Buscar por nombre, rol, teléfono, correo o Telegram">
          <div class="wf-filters" role="group" aria-label="Filtrar por estado">${FILTERS.map(([k, l]) => `<button type="button" class="wf-filter ${model.filter === k ? "is-active" : ""}" aria-pressed="${model.filter === k}" data-wf2-filter="${k}">${l}</button>`).join("")}</div>
          ${placeFilters.length ? `<div class="wf-filters wf-place-filters" role="group" aria-label="Filtrar por lugar">${placeFilters.map(([k, l]) => `<button type="button" class="wf-filter ${model.wlFilter === k ? "is-active" : ""}" aria-pressed="${model.wlFilter === k}" data-wf2-place-filter="${h(k)}">${h(l)}</button>`).join("")}</div>` : ""}
          <button class="client-btn wf-csv" type="button" data-wf2-csv>Exportar CSV</button>
        </div>
        ${selectionBar()}
        <p class="wf-count">${model.loaded ? `Mostrando ${list.length} de ${s.total}` : "Cargando personal…"}</p>
        ${model.loaded && !list.length ? `<div class="wf-empty">${s.total ? "No hay coincidencias para la búsqueda o el filtro." : "Aún no hay empleados. Usa “+ Agregar empleado”."}</div>` : ""}
        ${list.length ? tableView(list) + cardsView(list) : ""}
      </section>
      ${modalView()}
    </div>`;
  }

  function draw() {
    const host = ctx && ctx.host();
    if (!host) return;
    const active = document.activeElement;
    const keepSearch = active && active.matches && active.matches("[data-wf2-search]");
    const caret = keepSearch ? active.selectionStart : null;
    host.innerHTML = view();
    applyContrast(host.querySelector(".wf-root"));
    if (keepSearch) {
      const again = host.querySelector("[data-wf2-search]");
      if (again) { again.focus(); try { again.setSelectionRange(caret, caret); } catch (_) {} }
    }
    const first = host.querySelector("[data-wf2-modal] input, [data-wf2-modal] button");
    if (model.modal && first && !(active && active.closest && active.closest("[data-wf2-modal]"))) first.focus();
  }

  // ------------------------------------------------------------ datos
  async function loadPins() {
    try {
      const data = await ctx.personalApi(`/crm-lab/companies/${encodeURIComponent(ctx.companyId)}/pins`);
      model.pins = (data && data.pins) || {};
    } catch (_) {
      model.pins = null;
    }
  }

  async function savePin(form) {
    const id = form.getAttribute("data-wf2-pinform");
    const pin = String(form.elements.pin.value || "").trim();
    if (!/^\d{4}$/.test(pin)) { model.modal.error = "El PIN debe tener 4 dígitos."; draw(); return; }
    model.busy = true;
    draw();
    try {
      await ctx.personalApi(`/crm-lab/companies/${encodeURIComponent(ctx.companyId)}/employees/${encodeURIComponent(id)}/pin`, { method: "PUT", body: JSON.stringify({ pin }) });
      model.modal = null;
      model.notice = "PIN CRM guardado.";
      await loadPins();
    } catch (error) {
      if (model.modal) model.modal.error = errorText(error);
    } finally {
      model.busy = false;
      draw();
    }
  }

  async function clearPin(id) {
    model.menu = "";
    try {
      await ctx.personalApi(`/crm-lab/companies/${encodeURIComponent(ctx.companyId)}/employees/${encodeURIComponent(id)}/pin`, { method: "DELETE" });
      model.notice = "PIN CRM quitado.";
      await loadPins();
    } catch (error) {
      model.error = errorText(error);
    }
    draw();
  }

  // 059A: lugares (con sesión: authApi). Solo si client.js dice que el
  // interruptor está encendido; si el servidor no responde, no se muestra nada.
  const wlBase = () => `/work-locations/companies/${encodeURIComponent(ctx.companyId)}`;
  async function loadPlaces() {
    if (!ctx.workLocations || typeof ctx.authApi !== "function") { model.wl = null; return; }
    try {
      const data = await ctx.authApi(wlBase());
      model.wl = { locations: arr(data && data.locations), assignments: (data && data.assignments) || {},
        can_manage: Boolean(data && data.can_manage), can_assign: Boolean(data && data.can_assign) };
      const ok = wlFilters(model.wl).some(([k]) => k === model.wlFilter);
      if (!ok) model.wlFilter = "all";
    } catch (_) {
      model.wl = null;
    }
  }

  async function load() {
    loadPins().then(() => { if (model.loaded) draw(); });
    const places = loadPlaces();
    try {
      const data = await ctx.personalApi(`/employees?company_id=${encodeURIComponent(ctx.companyId)}&include_archived=true`);
      model.employees = arr(data);
      model.error = "";
    } catch (error) {
      model.error = error.message || "No se pudo cargar personal.";
    }
    await places;
    const ids = new Set(model.employees.map((e) => String(e.id)));
    model.selected = new Set([...model.selected].filter((id) => ids.has(id)));
    model.loaded = true;
    draw();
  }

  function errorText(error) {
    const raw = String((error && error.message) || error || "");
    const json = raw.indexOf("{");
    try { const d = JSON.parse(json >= 0 ? raw.slice(json) : raw); return typeof d.detail === "string" ? d.detail : raw; } catch (_) { return raw || "No se pudo guardar."; }
  }

  async function assignPlace(ids, target, source = "personal") {
    return ctx.authApi(`${wlBase()}/assign`, { method: "POST", body: JSON.stringify({ employee_ids: ids, work_location_id: target === WL_NONE ? null : target, source }) });
  }

  async function saveAssign(form) {
    const target = form.elements.work_location_id.value;
    const ids = model.modal.ids.slice();
    model.busy = true;
    draw();
    try {
      const out = await assignPlace(ids, target, "personal_multiple");
      const loc = arr(model.wl.locations).find((l) => l.id === target);
      model.modal = null;
      model.selected = new Set();
      model.notice = `${loc ? `Lugar ${loc.name}` : "Sin asignar"}: ${out && out.changed !== undefined ? out.changed : ids.length} empleado(s) cambiado(s).`;
      await load();
    } catch (error) {
      if (model.modal) model.modal.error = errorText(error);
    } finally {
      model.busy = false;
      draw();
    }
  }

  function placesRows() {
    return arr(model.wl && model.wl.locations).map((l) => ({ id: l.id, name: l.name, code: l.code || "", timezone: l.timezone, is_active: l.is_active }));
  }

  async function savePlaces() {
    const rows = model.modal.rows;
    if (rows.some((r) => String(r.name || "").trim().length < 2)) { model.modal.error = "Cada lugar necesita un nombre."; draw(); return; }
    model.busy = true;
    draw();
    try {
      await ctx.authApi(`${wlBase()}/locations`, { method: "PUT", body: JSON.stringify({ locations: rows }) });
      model.modal = null;
      model.notice = "Lugares guardados.";
      await load();
    } catch (error) {
      if (model.modal) model.modal.error = errorText(error);
    } finally {
      model.busy = false;
      draw();
    }
  }

  async function save(form) {
    const id = form.getAttribute("data-wf2-form");
    const values = {};
    FIELDS.forEach((k) => { const el = form.elements[k]; values[k] = el ? String(el.value).trim() : ""; });
    if (!values.full_name || values.full_name.length < 2) { model.modal.error = "Nombre completo es obligatorio."; draw(); return; }
    const original = model.modal.employee || {};
    const placeEl = model.wl && form.elements.work_location_id;
    const place = placeEl && !placeEl.disabled ? placeEl.value : null;
    model.busy = true;
    draw();
    try {
      const body = JSON.stringify(payloadOf(ctx.companyId, model.wl ? keepDeduction2(values, id ? original : null) : values));
      const saved = await ctx.personalApi(id ? `/employees/${encodeURIComponent(id)}` : "/employees", { method: id ? "PATCH" : "POST", body });
      const savedId = id || (saved && saved.id);
      let placeError = "";
      if (place !== null && savedId) {
        const before = id ? wlPlaceId(model.wl, original) : null;
        const next = place === WL_NONE ? null : place;
        if (before !== next) {
          try { await assignPlace([String(savedId)], place, "personal_form"); } catch (error) { placeError = errorText(error); }
        }
      }
      model.modal = null;
      model.notice = (id ? "Empleado guardado." : "Empleado agregado.") + (placeError ? ` El lugar no se pudo guardar: ${placeError}` : "");
      await load();
    } catch (error) {
      if (model.modal) model.modal.error = errorText(error);
    } finally {
      model.busy = false;
      draw();
    }
  }

  async function act(id, action, notice) {
    model.busy = true;
    try {
      await ctx.personalApi(`/employees/${encodeURIComponent(id)}/${action}`, { method: "POST", body: JSON.stringify({}) });
      model.modal = null;
      model.menu = "";
      model.notice = notice;
      await load();
    } catch (error) {
      if (model.modal) model.modal.error = errorText(error); else model.error = errorText(error);
    } finally {
      model.busy = false;
      draw();
    }
  }

  function exportCsv() {
    const list = visible(model.employees, model.filter, model.query, roles(), model.wl, model.wlFilter);
    const blob = new Blob(["﻿" + csvText(list, roles(), model.wl)], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `clonexa_personal_${new Date().toISOString().slice(0, 10)}.csv`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }

  const byId = (id) => model.employees.find((e) => String(e.id) === String(id)) || null;

  // ------------------------------------------------------------ eventos
  function inside(t) { return ctx && ctx.host() && ctx.host().contains(t); }

  function onClick(event) {
    const t = event.target;
    if (!t || !t.closest || !inside(t)) return;
    const menuBtn = t.closest("[data-wf2-menu]");
    if (menuBtn) { const id = menuBtn.getAttribute("data-wf2-menu"); model.menu = model.menu === id ? "" : id; draw(); return; }
    if (model.menu && !t.closest(".wf-menu-list")) { model.menu = ""; draw(); }
    const filter = t.closest("[data-wf2-filter]");
    if (filter) { model.filter = filter.getAttribute("data-wf2-filter"); draw(); return; }
    if (model.wl && onPlaceClick(t)) return;
    if (t.closest("[data-wf2-csv]")) { exportCsv(); return; }
    if (t.closest("[data-wf2-add]")) { model.notice = ""; model.modal = { type: "edit", employee: { status: "active", role: (roles()[0] || ["operator"])[0] } }; draw(); return; }
    const edit = t.closest("[data-wf2-edit]");
    if (edit) { model.menu = ""; model.notice = ""; model.modal = { type: "edit", employee: { ...byId(edit.getAttribute("data-wf2-edit")) } }; draw(); return; }
    const a = t.closest("[data-wf2-act]");
    if (a) { const action = a.getAttribute("data-wf2-act"); act(a.getAttribute("data-id"), action, action === "activate" ? "Empleado activado." : "Empleado inactivado."); return; }
    const del = t.closest("[data-wf2-delete]");
    if (del) { const e = byId(del.getAttribute("data-wf2-delete")) || {}; model.menu = ""; model.modal = { type: "delete", id: String(e.id || ""), name: e.full_name || "este empleado" }; draw(); return; }
    const pinBtn = t.closest("[data-wf2-pin]");
    if (pinBtn) { const e = byId(pinBtn.getAttribute("data-wf2-pin")) || {}; model.menu = ""; model.notice = ""; model.modal = { type: "pin", id: String(e.id || ""), name: e.full_name || "" }; draw(); return; }
    const pinClear = t.closest("[data-wf2-pin-clear]");
    if (pinClear) { clearPin(pinClear.getAttribute("data-wf2-pin-clear")); return; }
    const go = t.closest("[data-wf2-delete-go]");
    if (go) { act(go.getAttribute("data-wf2-delete-go"), "archive", "Empleado eliminado (archivado para auditoría)."); return; }
    if (t.closest("[data-wf2-close]") || (t.matches && t.matches("[data-wf2-modal]"))) { model.modal = null; draw(); }
  }

  // 059A: selección múltiple, asignar lugar, filtro por lugar y Administrar lugares.
  function onPlaceClick(t) {
    const pf = t.closest("[data-wf2-place-filter]");
    if (pf) { model.wlFilter = pf.getAttribute("data-wf2-place-filter"); draw(); return true; }
    if (t.closest("[data-wf2-pick-clear]")) { model.selected = new Set(); draw(); return true; }
    if (t.closest("[data-wf2-assign]")) {
      model.notice = "";
      model.modal = { type: "assign", ids: [...model.selected], target: (arr(model.wl.locations).find((l) => l.is_active) || {}).id || WL_NONE };
      draw();
      return true;
    }
    if (t.closest("[data-wf2-places]")) { model.notice = ""; model.modal = { type: "places", rows: placesRows() }; draw(); return true; }
    if (model.modal && model.modal.type === "places") {
      const rows = model.modal.rows;
      const up = t.closest("[data-wf2-place-up]");
      const down = t.closest("[data-wf2-place-down]");
      const move = (i, d) => { const j = i + d; if (j < 0 || j >= rows.length) return; [rows[i], rows[j]] = [rows[j], rows[i]]; draw(); };
      if (up) { move(Number(up.getAttribute("data-wf2-place-up")), -1); return true; }
      if (down) { move(Number(down.getAttribute("data-wf2-place-down")), 1); return true; }
      if (t.closest("[data-wf2-place-add]")) {
        rows.push({ id: null, name: "", code: "", timezone: (rows[rows.length - 1] || {}).timezone || "America/New_York", is_active: true });
        draw();
        return true;
      }
    }
    return false;
  }

  function onChange(event) {
    const t = event.target;
    if (!t || !t.matches || !inside(t)) return;
    if (t.matches("[data-wf2-pick]")) {
      const id = t.getAttribute("data-wf2-pick");
      if (t.checked) model.selected.add(id); else model.selected.delete(id);
      draw();
      return;
    }
    if (t.matches("[data-wf2-pick-all]")) {
      const list = visible(model.employees, model.filter, model.query, roles(), model.wl, model.wlFilter);
      list.forEach((e) => { if (t.checked) model.selected.add(String(e.id)); else model.selected.delete(String(e.id)); });
      draw();
      return;
    }
    if (t.matches("[data-wf2-assign-target]") && model.modal && model.modal.type === "assign") { model.modal.target = t.value; draw(); return; }
    if (t.matches("[data-wf2-place-field]") && model.modal && model.modal.type === "places") placeField(t, true);
  }

  function placeField(t, redraw) {
    const row = model.modal.rows[Number(t.getAttribute("data-i"))];
    if (!row) return;
    const key = t.getAttribute("data-wf2-place-field");
    row[key] = key === "is_active" ? t.checked : t.value;
    if (redraw && key !== "name" && key !== "code") draw();
  }

  function onInput(event) {
    const t = event.target;
    if (t && t.matches && inside(t) && t.matches("[data-wf2-place-field]") && model.modal && model.modal.type === "places") { placeField(t, false); return; }
    if (!t || !t.matches || !inside(t) || !t.matches("[data-wf2-search]")) return;
    model.query = t.value;
    draw();
  }

  function onSubmit(event) {
    const form = event.target;
    if (form && form.matches && inside(form) && form.matches("[data-wf2-pinform]")) { event.preventDefault(); savePin(form); return; }
    if (form && form.matches && inside(form) && form.matches("[data-wf2-assignform]")) { event.preventDefault(); saveAssign(form); return; }
    if (form && form.matches && inside(form) && form.matches("[data-wf2-placesform]")) { event.preventDefault(); savePlaces(); return; }
    if (!form || !form.matches || !inside(form) || !form.matches("[data-wf2-form]")) return;
    event.preventDefault();
    save(form);
  }

  function onKey(event) {
    if (event.key !== "Escape" || !ctx || !ctx.host()) return;
    if (model.modal || model.menu) { model.modal = null; model.menu = ""; draw(); }
  }

  async function mount(context) {
    ctx = context;
    model.employees = [];
    model.loaded = false;
    model.modal = null;
    model.menu = "";
    model.notice = "";
    model.error = "";
    model.pins = null;
    model.wl = null;
    model.wlFilter = "all";
    model.selected = new Set();
    if (!bound && typeof document.addEventListener === "function") {
      document.addEventListener("click", onClick);
      document.addEventListener("change", onChange);
      document.addEventListener("input", onInput);
      document.addEventListener("submit", onSubmit);
      document.addEventListener("keydown", onKey);
      bound = true;
    }
    draw();
    await load();
  }

  window.CxWorkforceV2 = { mount, view, model, statusOf, stats, visible, csvText, payloadOf, roleLabel, roleEnabled, pair, contrast, FIELDS, CSV_HEAD,
    wlPlaceId, wlPlaceName, wlFilters, wlMatch, keepDeduction2, assignLabel, WL_NONE };
})();
