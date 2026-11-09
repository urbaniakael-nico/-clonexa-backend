// Turnos abiertos y "Cerrar turno" (interruptor open_shift_alert del modulo
// workforce). client.js solo lo monta con el interruptor encendido, arriba de CRM
// Campo y de Personal; sin el interruptor, o si este archivo no carga, esas
// pantallas siguen igual. Solo muestra los turnos que pasan el limite de la empresa
// (alert_hours, lo manda el servidor); sin ninguno no dibuja nada. Los turnos normales se ven solo en la
// vista por lugar, sin boton de cerrar (060D).
// Datos: GET /open-shifts/companies/{id}; cerrar: POST .../employees/{id}/close con
// la hora real de salida (en la hora del LUGAR de la persona) y una nota obligatoria.
// Nunca cierra solo: solo cuando el supervisor / direccion / dueno lo confirma.
// 071A (interruptor work_schedule; el servidor manda schedule_mode): TODOS los turnos abiertos, con
// chip rojo "Fuera de horario", salida programada y Cerrar turno con hora por defecto (la programada
// si ya paso, si no la actual), motivo obligatorio y doble confirmacion.
(() => {
  "use strict";

  const h = (v) => String(v ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
  const arr = (v) => (Array.isArray(v) ? v : []);
  const NOTE_MIN = 5;
  const REFRESH_MS = 60000;
  const STATUS = { working: "Trabajando", on_break: "En pausa" };

  const model = { data: null, open: null, error: "", saved: "", busy: false, confirm: null };
  let ctx = null;
  let bound = false;
  let refresh = null;

  // ------------------------------------------------------------ reglas puras
  function tzOffsetMinutes(tz, date) {
    const parts = new Intl.DateTimeFormat("en-US", { timeZone: tz, hourCycle: "h23", year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" })
      .formatToParts(date).reduce((o, p) => { o[p.type] = p.value; return o; }, {});
    const asUtc = Date.UTC(Number(parts.year), Number(parts.month) - 1, Number(parts.day), Number(parts.hour) % 24, Number(parts.minute));
    return Math.round((asUtc - Math.floor(date.getTime() / 60000) * 60000) / 60000);
  }

  // "2026-11-02T18:30" en la zona `tz` -> ISO UTC ("...Z"), o "" si no es valido.
  function zonedToUtcIso(local, tz) {
    const m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})$/.exec(String(local || "").trim());
    if (!m) return "";
    const guess = Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3]), Number(m[4]), Number(m[5]));
    let at = guess - tzOffsetMinutes(tz, new Date(guess)) * 60000;
    at = guess - tzOffsetMinutes(tz, new Date(at)) * 60000;
    return new Date(at).toISOString().replace(".000Z", "Z");
  }

  // Instante -> "2026-11-02T18:30" en la zona `tz` (valor del campo de fecha y hora).
  function utcToZonedInput(iso, tz) {
    const date = new Date(iso);
    if (Number.isNaN(date.getTime())) return "";
    const local = new Date(date.getTime() + tzOffsetMinutes(tz, date) * 60000);
    return local.toISOString().slice(0, 16);
  }

  function localLabel(iso, tz) {
    const date = new Date(iso);
    if (Number.isNaN(date.getTime())) return "—";
    return new Intl.DateTimeFormat("es-CO", { timeZone: tz, day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).format(date);
  }

  function hoursLabel(hours) {
    const total = Math.max(0, Math.round(Number(hours || 0) * 60));
    return `${Math.floor(total / 60)} h ${String(total % 60).padStart(2, "0")} min`;
  }

  // Lo mismo que valida el servidor, para avisar antes de enviar.
  function validate(form, shift, now) {
    const endIso = zonedToUtcIso(form.end_local, shift.timezone);
    if (!endIso) return { ok: false, field: "end_at", message: "Indica la hora real de salida." };
    const end = new Date(endIso).getTime();
    if (shift.shift_started_at && end <= new Date(shift.shift_started_at).getTime()) {
      return { ok: false, field: "end_at", message: "La salida debe ser después del inicio del turno." };
    }
    if (end > (now || Date.now()) + 2 * 60000) return { ok: false, field: "end_at", message: "La salida no puede estar en el futuro." };
    const note = String(form.note || "").replace(/\s+/g, " ").trim();
    if (note.length < NOTE_MIN) return { ok: false, field: "note", message: `La nota es obligatoria (mínimo ${NOTE_MIN} caracteres).` };
    return { ok: true, body: { end_at: endIso, note } };
  }

  // ------------------------------------------------------------ vista
  const limitOf = (data) => Number(data && data.alert_hours) || 0;
  const longShifts = (data) => (limitOf(data) > 0 ? arr(data && data.shifts).filter((s) => Number(s.hours_open || 0) >= limitOf(data)) : []);

  function rowView(s, data) {
    const place = s.work_location_name || "Sin lugar asignado";
    const open = model.open === s.employee_id;
    const form = open ? `
      <form class="cxos-form" data-cxos-form="${h(s.employee_id)}">
        <label>Hora real de salida <small>(hora de ${h(place)})</small>
          <input type="datetime-local" name="end_local" required value="${h(utcToZonedInput(new Date().toISOString(), s.timezone))}">
        </label>
        <label>Nota (obligatoria)
          <textarea name="note" rows="2" required minlength="${NOTE_MIN}" maxlength="500" placeholder="Ej: olvidó finalizar, salió a las 6 pm según el supervisor"></textarea>
        </label>
        ${model.error ? `<p class="cxos-error" role="alert">${h(model.error)}</p>` : ""}
        <div class="cxos-actions">
          <button type="submit" class="client-btn" ${model.busy ? "disabled" : ""}>Cerrar turno</button>
          <button type="button" class="client-btn" data-cxos-cancel>Cancelar</button>
        </div>
      </form>` : "";
    return `<li class="cxos-row is-long">
      <div class="cxos-main">
        <strong>${h(s.employee_name || "Colaborador")}</strong>
        <span>${h(place)} · ${h(STATUS[s.status] || s.status)}</span>
        <span>Inicio ${h(localLabel(s.shift_started_at, s.timezone))} · <b>${h(hoursLabel(s.hours_open))}</b> abierto</span>
      </div>
      ${data.can_close && !open ? `<button type="button" class="client-btn" data-cxos-open="${h(s.employee_id)}">Cerrar turno</button>` : ""}
      ${form}
    </li>`;
  }

  // ------------------------------------------------------------ 071A: modo horario
  const DETAIL_MIN = 5;
  const REASONS = [["olvido", "Olvidó finalizar"], ["salida_real", "Salida real confirmada"], ["otro", "Otro"]];

  function reasonsOf(data) {
    const list = arr(data && data.reasons).map((r) => [r.code, r.label]);
    return list.length ? list : REASONS;
  }

  // Lo mismo que valida el servidor en modo horario: hora, motivo y detalle para "Otro".
  function validateSchedule(form, shift, now) {
    const base = validate({ end_local: form.end_local, note: "motivo" }, shift, now);
    if (!base.ok) return base;
    const code = String(form.reason_code || "");
    if (!REASONS.some(([k]) => k === code)) return { ok: false, field: "reason_code", message: "Elige el motivo del cierre." };
    const detail = String(form.reason_detail || "").replace(/\s+/g, " ").trim();
    if (code === "otro" && detail.length < DETAIL_MIN) return { ok: false, field: "reason_detail", message: `Escribe el detalle del motivo (mínimo ${DETAIL_MIN} caracteres).` };
    return { ok: true, body: { end_at: base.body.end_at, reason_code: code, reason_detail: detail, confirmed: true } };
  }

  function scheduleForm(s, data) {
    const place = s.work_location_name || "Sin lugar asignado";
    const end = s.default_end_at || new Date().toISOString();
    const options = reasonsOf(data).map(([k, l]) => `<option value="${h(k)}">${h(l)}</option>`).join("");
    return `<form class="cxos-form" data-cxos-form="${h(s.employee_id)}">
        <label>Hora de salida <small>(hora de ${h(place)}${s.scheduled_end_at ? " · por defecto la salida programada" : " · por defecto la hora actual"})</small>
          <input type="datetime-local" name="end_local" required value="${h(utcToZonedInput(end, s.timezone))}">
        </label>
        <label>Motivo (obligatorio)
          <select name="reason_code" required><option value="">Elige el motivo</option>${options}</select>
        </label>
        <label>Detalle <small>(obligatorio si el motivo es Otro)</small>
          <textarea name="reason_detail" rows="2" maxlength="500" placeholder="Ej: el supervisor confirmó que salió a las 5 pm"></textarea>
        </label>
        ${model.error ? `<p class="cxos-error" role="alert">${h(model.error)}</p>` : ""}
        <div class="cxos-actions">
          <button type="submit" class="client-btn" ${model.busy ? "disabled" : ""}>Continuar</button>
          <button type="button" class="client-btn" data-cxos-cancel>Cancelar</button>
        </div>
      </form>`;
  }

  function confirmBox(s) {
    const c = model.confirm;
    const reason = (REASONS.find(([k]) => k === c.body.reason_code) || ["", ""])[1];
    return `<div class="cxos-form cxos-confirm" role="alertdialog" aria-labelledby="cxosConfirm-${h(s.employee_id)}">
        <p id="cxosConfirm-${h(s.employee_id)}"><b>¿Cerrar el turno de ${h(s.employee_name || "la persona")}?</b><br>
          Salida: <b>${h(localLabel(c.body.end_at, s.timezone))}</b> (hora de ${h(s.work_location_name || "su lugar")}) · Motivo: <b>${h(reason)}</b>${c.body.reason_detail ? ` · ${h(c.body.reason_detail)}` : ""}</p>
        <label class="cxos-check"><input type="checkbox" data-cxos-check ${c.checked ? "checked" : ""}> Confirmo que esta es la hora de salida y queda en la auditoría</label>
        ${model.error ? `<p class="cxos-error" role="alert">${h(model.error)}</p>` : ""}
        <div class="cxos-actions">
          <button type="button" class="client-btn cxos-danger" data-cxos-yes ${c.checked && !model.busy ? "" : "disabled"}>${model.busy ? "Guardando…" : "Sí, cerrar turno"}</button>
          <button type="button" class="client-btn" data-cxos-cancel>Cancelar</button>
        </div>
      </div>`;
  }

  function scheduleRow(s, data) {
    const place = s.work_location_name || "Sin lugar asignado";
    const open = model.open === s.employee_id;
    const chips = [
      s.out_of_schedule ? '<span class="cxos-chip is-late">Fuera de horario</span>' : "",
      s.over_limit ? `<span class="cxos-chip">Más de ${h(String(limitOf(data)))} h</span>` : "",
      s.slot_name ? `<span class="cxos-chip is-soft">${h(s.slot_name)}</span>` : "",
    ].join("");
    const body = open ? (model.confirm && model.confirm.id === s.employee_id ? confirmBox(s) : scheduleForm(s, data)) : "";
    return `<li class="cxos-row ${s.out_of_schedule ? "is-late" : ""} ${s.over_limit ? "is-long" : ""}" data-cxos-row="${h(s.employee_id)}">
      <div class="cxos-main">
        <strong>${h(s.employee_name || "Colaborador")} ${chips}</strong>
        <span>${h(place)} · ${h(STATUS[s.status] || s.status)}</span>
        <span>Inicio ${h(localLabel(s.shift_started_at, s.timezone))} · <b>${h(hoursLabel(s.hours_open))}</b> abierto${s.scheduled_end_at ? ` · Salida programada ${h(localLabel(s.scheduled_end_at, s.timezone))}` : ""}</span>
        ${s.reason ? `<span>Sigue trabajando: ${h(s.reason)}</span>` : ""}
      </div>
      ${data.can_close && !open ? `<button type="button" class="client-btn" data-cxos-open="${h(s.employee_id)}">Cerrar turno</button>` : ""}
      ${body}
    </li>`;
  }

  // Los Fuera de horario primero, luego los mas viejos.
  function scheduleShifts(data) {
    return arr(data && data.shifts).slice().sort((a, b) => (Number(Boolean(b.out_of_schedule)) - Number(Boolean(a.out_of_schedule)))
      || String(a.shift_started_at).localeCompare(String(b.shift_started_at)));
  }

  function scheduleView(data) {
    const shifts = scheduleShifts(data);
    const saved = model.saved ? `<p class="cxos-saved" role="status">${h(model.saved)}</p>` : "";
    if (!shifts.length) return saved ? `<section class="cxos-root">${saved}</section>` : "";
    const late = shifts.filter((s) => s.out_of_schedule).length;
    return `<section class="cxos-root" aria-label="Turnos abiertos">
      <div class="cxos-head"><h3>Turnos abiertos (${shifts.length})</h3>${late ? `<span class="cxos-badge is-late">Fuera de horario: ${late}</span>` : ""}</div>
      ${saved}
      <ul class="cxos-list">${shifts.map((s) => scheduleRow(s, data)).join("")}</ul>
    </section>`;
  }

  function view(data) {
    if (!data) return "";
    if (data.schedule_mode) return scheduleView(data);
    const shifts = longShifts(data);
    const saved = model.saved ? `<p class="cxos-saved" role="status">${h(model.saved)}</p>` : "";
    if (!shifts.length) return saved ? `<section class="cxos-root">${saved}</section>` : "";
    const title = `Turnos de más de ${h(String(limitOf(data)))} h`;
    return `<section class="cxos-root" aria-label="${title}">
      <div class="cxos-head"><h3>${title} (${shifts.length})</h3></div>
      ${saved}
      <ul class="cxos-list">${shifts.map((s) => rowView(s, data)).join("")}</ul>
    </section>`;
  }

  // ------------------------------------------------------------ eventos
  const host = () => (ctx && typeof ctx.host === "function" ? ctx.host() : null);

  function draw() {
    const el = host();
    if (el) el.innerHTML = view(model.data);
  }

  async function load() {
    try {
      model.data = await ctx.api(`/open-shifts/companies/${encodeURIComponent(ctx.companyId)}`);
      return true;
    } catch (_) {
      model.data = null;
      return false;
    }
  }

  function shiftOf(id) {
    const list = model.data && model.data.schedule_mode ? arr(model.data.shifts) : longShifts(model.data);
    return list.find((s) => s.employee_id === id) || null;
  }

  async function onClick(event) {
    const t = event.target;
    if (!t || typeof t.closest !== "function" || !host() || !host().contains(t)) return;
    const open = t.closest("[data-cxos-open]");
    if (open) { model.open = open.getAttribute("data-cxos-open"); model.error = ""; model.saved = ""; model.confirm = null; draw(); return; }
    if (t.closest("[data-cxos-cancel]")) { model.open = null; model.error = ""; model.confirm = null; draw(); return; }
    if (t.closest("[data-cxos-check]") && model.confirm) { model.confirm.checked = Boolean(t.checked); draw(); return; }
    if (t.closest("[data-cxos-yes]") && model.confirm && model.confirm.checked) { await closeConfirmed(); }
  }

  async function closeConfirmed() {
    const c = model.confirm;
    const shift = c && shiftOf(c.id);
    if (!shift || model.busy) return;
    model.busy = true;
    draw();
    try {
      const done = await ctx.api(`/open-shifts/companies/${encodeURIComponent(ctx.companyId)}/employees/${encodeURIComponent(c.id)}/close`,
        { method: "POST", body: JSON.stringify(c.body) });
      model.open = null;
      model.confirm = null;
      model.error = "";
      model.saved = `Turno de ${shift.employee_name || "la persona"} cerrado a las ${localLabel(c.body.end_at, shift.timezone)}. Quedó en la auditoría${done && done.notified ? " y se le avisó por el bot" : ""}.`;
      await load();
    } catch (error) {
      const raw = String((error && error.message) || "");
      const m = /"detail"\s*:\s*"([^"]+)"/.exec(raw);
      model.error = m ? m[1] : "No se pudo cerrar el turno. Intenta de nuevo.";
    } finally {
      model.busy = false;
      draw();
    }
  }

  async function submit(id, form) {
    const shift = shiftOf(id);
    if (!shift || model.busy) return;
    const check = validate(form, shift);
    if (!check.ok) { model.error = check.message; draw(); return; }
    model.busy = true;
    try {
      await ctx.api(`/open-shifts/companies/${encodeURIComponent(ctx.companyId)}/employees/${encodeURIComponent(id)}/close`,
        { method: "POST", body: JSON.stringify(check.body) });
      model.open = null;
      model.error = "";
      model.saved = `Turno de ${shift.employee_name || "la persona"} cerrado. Quedó en la auditoría.`;
      await load();
    } catch (error) {
      const raw = String((error && error.message) || "");
      const m = /"detail"\s*:\s*"([^"]+)"/.exec(raw);
      model.error = m ? m[1] : "No se pudo cerrar el turno. Intenta de nuevo.";
    } finally {
      model.busy = false;
      draw();
    }
  }

  function onSubmit(event) {
    const f = event.target;
    if (!f || typeof f.getAttribute !== "function" || !f.getAttribute("data-cxos-form")) return;
    event.preventDefault();
    const id = f.getAttribute("data-cxos-form");
    if (model.data && model.data.schedule_mode) {  // 071A: primer paso; el segundo confirma
      const shift = shiftOf(id);
      if (!shift) return;
      const check = validateSchedule({ end_local: f.elements.end_local.value, reason_code: f.elements.reason_code.value,
        reason_detail: f.elements.reason_detail.value }, shift);
      if (!check.ok) { model.error = check.message; draw(); return; }
      model.error = "";
      model.confirm = { id, body: check.body, checked: false };
      draw();
      return;
    }
    submit(id, { end_local: f.elements.end_local.value, note: f.elements.note.value });
  }

  function stop() { if (refresh) clearInterval(refresh); refresh = null; }

  async function mount(context) {
    stop();
    ctx = context;
    model.data = null;
    model.open = null;
    model.error = "";
    model.saved = "";
    model.confirm = null;
    if (!bound && typeof document.addEventListener === "function") {
      document.addEventListener("click", onClick);
      document.addEventListener("submit", onSubmit);
      bound = true;
    }
    const ok = await load();
    draw();
    refresh = setInterval(async () => { if (!host()) { stop(); return; } if (model.open) return; await load(); draw(); }, REFRESH_MS);
    return ok;
  }

  window.CxOpenShifts = { mount, view, longShifts, model, validate, validateSchedule, scheduleShifts, zonedToUtcIso, utcToZonedInput, localLabel, hoursLabel, tzOffsetMinutes, submit,
    _ctx: (c) => { ctx = c; }, onClick, onSubmit };
})();
