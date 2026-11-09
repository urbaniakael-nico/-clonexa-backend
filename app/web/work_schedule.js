// Horario de la semana por operación (interruptor work_schedule del módulo workforce, 071A).
// client.js solo carga este archivo con el interruptor encendido (hoy solo VOLTAGE); sin el
// interruptor, o si este archivo no carga, CRM Campo sigue igual.
// - En CRM Campo, al frente de cada operación: "Horario de la semana" con el horario de hoy y un
//   botón para verlo (cualquiera con acceso) o editarlo (solo dueño / admin; el servidor lo valida).
// - Por persona: chip rojo "Fuera de horario" y, si hay más de un horario, "Horario 2".
// - Editor: Horario 1, 2…; días, entrada, salida y almuerzo de referencia en la hora local de la
//   operación; un día puntual distinto (Libre u otra hora); "+ Agregar horario"; semana anterior /
//   siguiente (una semana sin cambios copia la anterior); horario de cada persona.
// Datos: GET/PUT /work-schedule/companies/{id}/locations/{lugar}?week=AAAA-MM-DD y
// PUT /work-schedule/companies/{id}/employees/{persona}.
(() => {
  "use strict";

  const h = (v) => String(v ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
  const arr = (v) => (Array.isArray(v) ? v : []);
  const DAY_SHORT = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"];
  const DAY_NAMES = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"];
  const ZONES = { "America/New_York": "ET", "America/Chicago": "CT", "America/Denver": "MT", "America/Los_Angeles": "PT" };
  const MAX_SLOTS = 6;

  const model = { open: false, loc: null, data: null, slots: [], busy: false, error: "", saved: "", people: {} };
  let ctx = null;
  let bound = false;

  // ------------------------------------------------------------ reglas puras
  function addDays(iso, n) {
    const d = new Date(`${iso}T00:00:00Z`);
    d.setUTCDate(d.getUTCDate() + n);
    return d.toISOString().slice(0, 10);
  }

  function clock(value) {
    const m = /^(\d{1,2}):(\d{2})$/.exec(String(value || ""));
    if (!m) return "—";
    const hour = Number(m[1]);
    return `${hour % 12 || 12}:${m[2]} ${hour < 12 ? "a. m." : "p. m."}`;
  }

  const MONTHS = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];
  function dayLabel(iso) {
    const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(iso || ""));
    return m ? `${Number(m[3])} ${MONTHS[Number(m[2]) - 1]}` : "";
  }

  function weekLabel(start) { return `Semana del ${dayLabel(start)} al ${dayLabel(addDays(start, 6))}`; }

  const zoneLabel = (tz) => ZONES[tz] || String(tz || "");

  function copy(value) { return JSON.parse(JSON.stringify(value)); }

  function newSlot(slots) {
    const base = arr(slots)[0] || { start: "07:00", end: "17:00", lunch_start: "12:00", lunch_end: "13:00" };
    return { slot: arr(slots).length + 1, name: `Horario ${arr(slots).length + 1}`, days: [0, 1, 2, 3, 4],
      start: base.start, end: base.end, lunch_start: base.lunch_start || "", lunch_end: base.lunch_end || "", overrides: {} };
  }

  // normal (sigue sus días) | off (libre ese día) | custom (otra hora ese día)
  function dayMode(slot, iso) {
    const o = (slot.overrides || {})[iso];
    if (!o) return "normal";
    return o.off ? "off" : "custom";
  }

  function planOf(slot, iso, weekday) {
    const o = (slot.overrides || {})[iso];
    if (o) return o.off ? { off: true } : { off: false, start: o.start, end: o.end, special: true };
    return arr(slot.days).includes(weekday) ? { off: false, start: slot.start, end: slot.end } : { off: true };
  }

  function bodyOf(weekStart, slots) {
    return { week_start: weekStart, slots: arr(slots).map((s, i) => ({ slot: i + 1, days: arr(s.days).slice().sort((a, b) => a - b), start: s.start, end: s.end,
      lunch_start: s.lunch_start || null, lunch_end: s.lunch_end || null, overrides: copy(s.overrides || {}) })) };
  }

  function sourceNote(data) {
    if (!data || !data.configured) return "Esta operación aún no tiene horario: el bot no le pregunta a nadie hasta que lo guardes.";
    if (data.source === "copied") return `Copiado de la ${weekLabel(data.copied_from).toLowerCase()}. Si lo cambias, el cambio queda solo para esta semana y las siguientes.`;
    return `Guardado para esta semana${data.updated_by ? ` por ${data.updated_by}` : ""}.`;
  }

  // ------------------------------------------------------------ CRM Campo
  function canEdit() { return Boolean(ctx && typeof ctx.canEdit === "function" ? ctx.canEdit() : ctx && ctx.canEdit); }

  function sectionExtra(group) {
    const sc = group && group.schedule;
    if (!sc) return "";
    const slots = arr(sc.slots);
    const today = sc.configured ? slots.map((s) => `${slots.length > 1 ? `${s.name}: ` : "Hoy: "}${s.today}`).join(" · ") : "Sin horario configurado";
    const label = canEdit() ? (sc.configured ? "Editar horario" : "Configurar horario") : "Ver horario";
    return `<div class="cxws-bar"><span class="cxws-title">Horario de la semana</span><span class="cxws-today">${h(today)}</span>
      <button type="button" class="client-btn cxws-open" data-cxws-open="${h(group.key)}" aria-label="${h(label)} de ${h(group.name)}">${h(label)}</button></div>`;
  }

  function rowExtra(row) {
    const sc = row && row.schedule;
    if (!sc) return "";
    return `${sc.out_of_schedule ? '<span class="cxws-chip is-late">Fuera de horario</span>' : ""}${sc.slot_name ? `<span class="cxws-chip">${h(sc.slot_name)}</span>` : ""}`;
  }

  // ------------------------------------------------------------ editor
  function dayTable(slot, i, start, edit) {
    return `<table class="cxws-table"><caption class="cxws-sr">Días de ${h(slot.name)}</caption><tbody>${[0, 1, 2, 3, 4, 5, 6].map((wd) => {
      const iso = addDays(start, wd);
      const plan = planOf(slot, iso, wd);
      const mode = dayMode(slot, iso);
      const label = plan.off ? "Libre" : `${clock(plan.start)} – ${clock(plan.end)}`;
      if (!edit) return `<tr class="${mode !== "normal" ? "is-special" : ""}"><th scope="row">${h(DAY_NAMES[wd])} ${h(dayLabel(iso))}</th><td>${h(label)}${mode !== "normal" ? ' <small>(día puntual)</small>' : ""}</td></tr>`;
      const o = (slot.overrides || {})[iso] || {};
      return `<tr class="${mode !== "normal" ? "is-special" : ""}"><th scope="row">${h(DAY_NAMES[wd])} ${h(dayLabel(iso))}</th>
        <td><select name="mode-${i}-${iso}" data-cxws-mode aria-label="${h(DAY_NAMES[wd])} ${h(dayLabel(iso))}">
          <option value="normal" ${mode === "normal" ? "selected" : ""}>Como siempre${mode === "normal" ? ` (${h(label)})` : ""}</option>
          <option value="off" ${mode === "off" ? "selected" : ""}>Libre este día</option>
          <option value="custom" ${mode === "custom" ? "selected" : ""}>Otra hora este día</option></select></td>
        <td>${mode === "custom" ? `<span class="cxws-pair"><input type="time" name="ostart-${i}-${iso}" value="${h(o.start || slot.start)}" aria-label="Entrada"> – <input type="time" name="oend-${i}-${iso}" value="${h(o.end || slot.end)}" aria-label="Salida"></span>` : ""}</td></tr>`;
    }).join("")}</tbody></table>`;
  }

  function slotView(slot, i, start, edit) {
    const dis = edit ? "" : "disabled";
    const days = DAY_SHORT.map((d, wd) => `<label class="cxws-day"><input type="checkbox" name="days-${i}" value="${wd}" ${arr(slot.days).includes(wd) ? "checked" : ""} ${dis}> ${h(d)}</label>`).join("");
    const time = (name, label, value) => `<label class="cxws-field"><span>${h(label)}</span><input type="time" name="${name}-${i}" value="${h(value || "")}" ${dis}></label>`;
    return `<fieldset class="cxws-slot" data-cxws-slot="${i}"><legend>${h(slot.name || `Horario ${i + 1}`)}</legend>
      <div class="cxws-days" role="group" aria-label="Días de ${h(slot.name)}">${days}</div>
      <div class="cxws-grid">${time("start", "Entrada", slot.start)}${time("end", "Salida", slot.end)}${time("lunch_start", "Almuerzo desde", slot.lunch_start)}${time("lunch_end", "Almuerzo hasta", slot.lunch_end)}</div>
      <p class="cxws-hint">El almuerzo es solo de referencia: se descuenta únicamente la pausa que la persona marca (Pausa / Retomar).</p>
      ${dayTable(slot, i, start, edit)}
      ${edit && i > 0 ? `<button type="button" class="client-btn" data-cxws-remove="${i}">Quitar ${h(slot.name)}</button>` : ""}
    </fieldset>`;
  }

  function peopleView(data, edit) {
    const saved = arr(data && data.slots);
    if (saved.length < 2 || !arr(data.people).length) return "";
    const options = (current) => saved.map((s) => `<option value="${h(s.slot)}" ${Number(current) === Number(s.slot) ? "selected" : ""}>${h(s.name)}</option>`).join("");
    return `<section class="cxws-people" aria-labelledby="cxwsPeople"><h3 id="cxwsPeople">Horario de cada persona</h3>
      <p class="cxws-hint">Por defecto todos están en Horario 1. Cada persona se evalúa con su horario.</p>
      <ul>${arr(data.people).map((p) => `<li><span>${h(p.name || "Colaborador")}</span>
        <select data-cxws-person="${h(p.id)}" aria-label="Horario de ${h(p.name)}" ${edit ? "" : "disabled"}>${options(p.slot)}</select>
        ${model.people[p.id] ? `<small role="status">${h(model.people[p.id])}</small>` : ""}</li>`).join("")}</ul></section>`;
  }

  function modalView() {
    if (!model.open) return "";
    const data = model.data;
    const loc = model.loc || {};
    const edit = Boolean(data && data.can_edit);
    const head = `<div class="cxws-head"><h2 id="cxwsTitle">Horario de la semana · ${h(loc.name || "")}</h2><button type="button" class="client-btn" data-cxws-close>Cerrar</button></div>`;
    if (!data) return `<div class="cxws-modal" data-cxws-modal><div class="cxws-card" role="dialog" aria-modal="true" aria-labelledby="cxwsTitle">${head}
      <p>${model.error ? h(model.error) : "Cargando horario…"}</p></div></div>`;
    const start = data.week_start;
    return `<div class="cxws-modal" data-cxws-modal><div class="cxws-card" role="dialog" aria-modal="true" aria-labelledby="cxwsTitle">${head}
      <div class="cxws-week"><button type="button" class="client-btn" data-cxws-week="-7">‹ Semana anterior</button><strong>${h(weekLabel(start))}</strong>
        <button type="button" class="client-btn" data-cxws-week="7">Semana siguiente ›</button></div>
      <p class="cxws-note">${h(sourceNote(data))} Horas en la hora local de ${h(loc.name || "la operación")} (${h(zoneLabel(loc.timezone || (data.location || {}).timezone))}).</p>
      ${model.error ? `<div class="cxws-alert" role="alert">${h(model.error)}</div>` : ""}
      ${model.saved ? `<div class="cxws-saved" role="status">${h(model.saved)}</div>` : ""}
      <form data-cxws-form>${model.slots.map((s, i) => slotView(s, i, start, edit)).join("")}
        ${edit ? `<div class="cxws-actions">${model.slots.length < MAX_SLOTS ? '<button type="button" class="client-btn" data-cxws-add>+ Agregar horario</button>' : ""}
          <button type="submit" class="client-btn cxws-primary" ${model.busy ? "disabled" : ""}>${model.busy ? "Guardando…" : "Guardar esta semana"}</button></div>` : '<p class="cxws-hint">Solo el dueño o el administrador cambia el horario.</p>'}
      </form>
      ${peopleView(data, edit)}
    </div></div>`;
  }

  function slotRoot() {
    let el = document.getElementById("cxwsModalHost");
    if (!el && document.body) {
      el = document.createElement("div");
      el.id = "cxwsModalHost";
      document.body.appendChild(el);
    }
    return el;
  }

  function draw() {
    const el = slotRoot();
    if (!el) return;
    el.innerHTML = modalView();
    if (model.open && !(document.activeElement && document.activeElement.closest && document.activeElement.closest("[data-cxws-modal]"))) {
      const close = el.querySelector("[data-cxws-close]");
      if (close) close.focus();
    }
  }

  // Lo escrito en el formulario -> model.slots (antes de redibujar o guardar).
  function collect() {
    const form = document.querySelector("[data-cxws-form]");
    if (!form || !model.data || !model.data.can_edit) return;
    const start = model.data.week_start;
    const val = (name) => { const el = form.elements[name]; return el ? String(el.value || "") : ""; };
    model.slots = model.slots.map((slot, i) => {
      const days = [...form.querySelectorAll(`input[name="days-${i}"]`)].filter((c) => c.checked).map((c) => Number(c.value));
      const out = { ...slot, days, start: val(`start-${i}`), end: val(`end-${i}`), lunch_start: val(`lunch_start-${i}`), lunch_end: val(`lunch_end-${i}`), overrides: {} };
      for (let wd = 0; wd < 7; wd += 1) {
        const iso = addDays(start, wd);
        const mode = val(`mode-${i}-${iso}`);
        if (mode === "off") out.overrides[iso] = { off: true };
        if (mode === "custom") out.overrides[iso] = { start: val(`ostart-${i}-${iso}`) || out.start, end: val(`oend-${i}-${iso}`) || out.end };
      }
      return out;
    });
  }

  function errorText(error) {
    const raw = String((error && error.message) || error || "");
    const i = raw.indexOf("{");
    try { const d = JSON.parse(i >= 0 ? raw.slice(i) : raw); return typeof d.detail === "string" ? d.detail : raw; } catch (_) { return raw || "No se pudo completar."; }
  }

  const base = () => `/work-schedule/companies/${encodeURIComponent(ctx.companyId)}`;

  function take(data) {
    model.data = data;
    model.slots = copy(arr(data && data.slots)).map((s) => { delete s.days_view; return s; });
    if (data && data.location) model.loc = { ...(model.loc || {}), ...data.location };
  }

  async function load(week) {
    model.error = "";
    try {
      const q = week ? `?week=${encodeURIComponent(week)}` : "";
      take(await ctx.api(`${base()}/locations/${encodeURIComponent(model.loc.id)}${q}`));
    } catch (error) {
      model.error = errorText(error);
    }
    draw();
  }

  async function open(loc) {
    model.open = true;
    model.loc = loc;
    model.data = null;
    model.saved = "";
    model.people = {};
    draw();
    await load(null);
  }

  function close() {
    model.open = false;
    model.data = null;
    draw();
  }

  async function save() {
    collect();
    model.busy = true;
    model.error = "";
    model.saved = "";
    draw();
    try {
      take(await ctx.api(`${base()}/locations/${encodeURIComponent(model.loc.id)}`, { method: "PUT", body: JSON.stringify(bodyOf(model.data.week_start, model.slots)) }));
      model.saved = `Horario guardado para la ${weekLabel(model.data.week_start).toLowerCase()}. Las semanas siguientes lo copian solas.`;
      if (ctx && typeof ctx.onSaved === "function") ctx.onSaved();
    } catch (error) {
      model.error = errorText(error);
    } finally {
      model.busy = false;
      draw();
    }
  }

  async function savePerson(id, slot) {
    model.people[id] = "Guardando…";
    draw();
    try {
      await ctx.api(`${base()}/employees/${encodeURIComponent(id)}`, { method: "PUT", body: JSON.stringify({ slot: Number(slot) }) });
      const p = arr(model.data && model.data.people).find((x) => x.id === id);
      if (p) p.slot = Number(slot);
      model.people[id] = "Guardado";
      if (ctx && typeof ctx.onSaved === "function") ctx.onSaved();
    } catch (error) {
      model.people[id] = errorText(error);
    }
    draw();
  }

  // ------------------------------------------------------------ eventos
  function placeOf(key) {
    const board = ctx && typeof ctx.board === "function" ? ctx.board() : null;
    const group = arr(board && board.groups).find((g) => String(g.key) === String(key));
    return group ? { id: group.key, name: group.name, timezone: group.timezone } : { id: key, name: "", timezone: "" };
  }

  function onClick(event) {
    const t = event.target;
    if (!t || !t.closest || !ctx) return;
    const opener = t.closest("[data-cxws-open]");
    if (opener) { open(placeOf(opener.getAttribute("data-cxws-open"))); return; }
    if (!t.closest("[data-cxws-modal]")) return;
    if (t.closest("[data-cxws-close]") || (t.matches && t.matches("[data-cxws-modal]"))) { close(); return; }
    const week = t.closest("[data-cxws-week]");
    if (week && model.data) { load(addDays(model.data.week_start, Number(week.getAttribute("data-cxws-week")))); return; }
    if (t.closest("[data-cxws-add]") && model.slots.length < MAX_SLOTS) { collect(); model.slots.push(newSlot(model.slots)); draw(); return; }
    const remove = t.closest("[data-cxws-remove]");
    if (remove) {
      collect();
      model.slots.splice(Number(remove.getAttribute("data-cxws-remove")), 1);
      model.slots = model.slots.map((s, i) => ({ ...s, slot: i + 1, name: `Horario ${i + 1}` }));
      draw();
    }
  }

  function onChange(event) {
    const t = event.target;
    if (!t || !t.closest || !t.closest("[data-cxws-modal]")) return;
    if (t.matches("[data-cxws-mode]")) { collect(); draw(); return; }
    if (t.matches("[data-cxws-person]")) savePerson(t.getAttribute("data-cxws-person"), t.value);
  }

  function onSubmit(event) {
    const f = event.target;
    if (!f || typeof f.matches !== "function" || !f.matches("[data-cxws-form]")) return;
    event.preventDefault();
    save();
  }

  function onKey(event) { if (event.key === "Escape" && model.open) close(); }

  function attach(context) {
    ctx = context;
    if (!bound && typeof document.addEventListener === "function") {
      document.addEventListener("click", onClick);
      document.addEventListener("change", onChange);
      document.addEventListener("submit", onSubmit);
      document.addEventListener("keydown", onKey);
      bound = true;
    }
  }

  window.CxWorkSchedule = { attach, sectionExtra, rowExtra, open, close, model, modalView, collect, bodyOf, planOf, dayMode, newSlot, addDays, clock, weekLabel, sourceNote,
    zoneLabel, onClick, onChange, onSubmit, _ctx: (c) => { ctx = c; } };
})();
