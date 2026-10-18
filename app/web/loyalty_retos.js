// Retos para las mesas (interruptor loyalty_retos_v2 del módulo loyalty).
// Reemplaza "Sorteos de consumo" solo en las empresas con el interruptor:
// - Paso 1 "¿Qué quieres lanzar?": consumo, polla o concurso, cada uno con CÓMO SE GANA.
//   Máximo uno activo por tipo (el servidor responde 409).
// - Asistente Qué → Cuándo → Revisar y publicar, con atajos de hora en la zona y la
//   jornada del bar, validación del orden de las fechas y vista del QR de la mesa.
// - "En curso": línea de tiempo, cuenta regresiva, participantes, ranking o conteo
//   y el botón de LO QUE FALTA. Historial con ganador y estado del premio.
// Datos en /loyalty-retos/companies/{id}/...; las mesas siguen con su QR de siempre.
(() => {
  "use strict";

  const h = (v) => String(v ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
  const arr = (v) => (Array.isArray(v) ? v : []);
  const fill = (s, vars) => (vars ? String(s).replace(/\{(\w+)\}/g, (m, k) => (vars[k] !== undefined ? String(vars[k]) : m)) : String(s));
  const T = (s, vars) => (typeof window !== "undefined" && window.CxI18n && typeof window.CxI18n.t === "function" ? window.CxI18n.t(s, vars) : fill(s, vars));

  const TYPES = { consumption: "Reto de consumo", score_pool: "Polla de marcador", vote_poll: "Concurso o votación" };
  const ICONS = { consumption: "🏆", score_pool: "⚽", vote_poll: "🎤" };
  const HOW = {
    consumption: "Gana la mesa con más consumo registrado en el torneo. Automático.",
    score_pool: "Gana quien acierte el marcador exacto.",
    vote_poll: "Gana según el tipo: más votos, respuesta correcta o el que elija el bar.",
  };
  const BUSY = { consumption: "Ya hay un reto de consumo en curso", score_pool: "Ya hay una polla en curso", vote_poll: "Ya hay un concurso en curso" };
  const MODES = { registration: "Inscripción simple", yes_no: "Sí / No", true_false: "Verdadero / Falso", participants: "Votación (hasta 5 opciones)" };
  const MODE_HOW = {
    registration: "Las mesas se inscriben (ej. karaoke) y al cerrar el bar elige al ganador.",
    yes_no: "Se sortea un ganador entre las mesas que acierten la respuesta correcta.",
    true_false: "Se sortea un ganador entre las mesas que acierten la respuesta correcta.",
    participants: "Gana la opción con más votos. Si empatan, el bar elige entre las empatadas.",
  };
  const ANSWERS = { yes: "Sí", no: "No", true: "Verdadero", false: "Falso" };
  const STAGES = { registration: "Inscripción", playing: "En juego", result: "Resultado" };
  const GAMES = { memory: "Memoria relámpago", trivia: "Trivia Máquina del tiempo", differences: "7 diferencias" };
  const ROUND = { registration: "Registro abierto", playing: "En juego", closed: "Cerrada", cancelled: "Cancelada" };
  const SOURCES = { consumption: "Mayor consumo", exact: "Marcador exacto", votes: "Más votos", draw: "Sorteo entre los aciertos", bar: "Lo eligió el bar", tiebreak: "Desempate con Juego en vivo" };
  const OUTCOMES = { winner: "Con ganador", no_winner: "Sin ganador", tie: "Empate", pick: "El bar elige" };
  const ERRORS = {
    ya_hay_uno_activo_de_este_tipo: "Ya hay uno activo de este tipo: termínalo antes de publicar otro.",
    premio_requerido: "Escribe el premio.",
    equipos_requeridos: "Escribe los dos equipos.",
    equipos_iguales: "Los dos equipos deben ser distintos.",
    pregunta_requerida: "Escribe la pregunta.",
    opciones_de_2_a_5: "La votación lleva de 2 a 5 opciones.",
    opciones_repetidas: "Las opciones no se pueden repetir.",
    respuesta_correcta_requerida: "Marca la respuesta correcta.",
    inscripcion_en_el_pasado: "El cierre de inscripción ya pasó.",
    inicio_antes_de_inscripcion: "El torneo debe empezar cuando cierra la inscripción o después.",
    cierre_antes_de_inicio: "El torneo debe cerrar después de empezar.",
    cierre_en_el_pasado: "La hora de cierre ya pasó.",
    pronosticos_en_el_pasado: "La hora de pronósticos ya pasó.",
    fecha_muy_lejana: "La fecha está demasiado lejos (máximo 45 días).",
    fecha_invalida: "Revisa la fecha y la hora.",
    pronosticos_abiertos: "Los pronósticos siguen abiertos hasta el inicio del partido.",
    el_reto_ya_tiene_resultado: "Este reto ya tiene resultado.",
    marcador_invalido: "El marcador va de 0 a 99.",
    no_hay_que_elegir: "Este reto ya no espera que el bar elija.",
    opcion_no_valida: "Esa opción no está en la lista.",
    hay_un_desempate_en_curso: "Hay un desempate en curso: ciérralo en Juegos en vivo.",
    juegos_en_vivo_no_activo: "Juegos en vivo no está activo: elige el ganador.",
    ya_hay_una_ronda_activa: "Ya hay una ronda de Juegos en vivo abierta: ciérrala primero.",
    la_polla_no_esta_empatada: "La polla no está empatada.",
    falta_respuesta_correcta: "Indica cuál era la respuesta correcta.",
    no_hay_premio_pendiente: "Este premio ya se entregó.",
    documento_invalido: "Documento inválido.",
    datos_purgados: "Los datos del desempate ya se purgaron (30 días).",
    juego_invalido: "Escoge memoria, trivia o 7 diferencias.",
    tipo_invalido: "Escoge qué quieres lanzar.",
    el_reto_ya_termino: "Este reto ya terminó.",
    pronosticos_ya_cerrados: "Los pronósticos ya están cerrados.",
  };
  // Diálogo de confirmación dentro de la página (nunca ventanas del navegador).
  const CONFIRM_TITLES = { close: "Terminar ahora", cancel: "Cancelar y reiniciar", score: "Poner marcador final", pick: "Elegir ganador", tiebreak: "Desempatar con Juego en vivo" };
  const CONFIRM_BODY = {
    close_consumption: "Se cierra el torneo en este momento y gana la mesa con más consumo con los pedidos hasta ahora.",
    close_score_pool: "Se cierran los pronósticos ya. Después pones el marcador final.",
    close_vote_poll: "Se cierra ya y se aplica la regla de ganador del concurso.",
    cancel: "Se anula sin ganador, deja de verse en el QR de las mesas y queda en el historial como Cancelado. Luego puedes lanzar otro del mismo tipo.",
    score: "Se guarda el marcador y se calculan los aciertos exactos.",
    pick: "Esa opción queda como ganadora y el premio pasa a pendiente.",
    tiebreak: "Se abre una ronda de Juegos en vivo solo para las mesas empatadas.",
  };
  const PRIZE_EXAMPLES = ["1/4 de ron", "Botella de aguardiente", "Ronda de shots", "Consumo de $50.000"];
  const DEFAULTS = {
    consumption: { title: "Reto de consumo", description: "¿Se animan? La mesa con más consumo registrado dentro del tiempo gana el premio." },
    score_pool: { title: "Polla de marcador", description: "Adivina el marcador exacto y participa por el premio." },
    vote_poll: { title: "Concurso", description: "" },
  };
  const TOURNAMENT_HOURS = 3;

  const model = { st: null, tab: "main", wizard: null, error: "", info: "", busy: "", denied: "", confirm: "", forms: {}, loading: false };
  let ctx = null;
  let bound = false;
  let timer = null;
  let ticker = null;

  // ------------------------------------------------------------ hora de la empresa
  const zone = () => (model.st && model.st.timezone) || "America/Bogota";
  const locale = () => (window.CxI18n && window.CxI18n.locale ? window.CxI18n.locale() : "es-CO");
  const nowMs = () => Date.now() + (model.offset || 0);

  // Partes de un instante en la zona tz: {y, m, d, hh, mm}.
  function partsIn(ms, tz) {
    const f = new Intl.DateTimeFormat("en-US", { timeZone: tz, year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23" });
    const p = {};
    f.formatToParts(new Date(ms)).forEach((x) => { p[x.type] = x.value; });
    return { y: Number(p.year), m: Number(p.month), d: Number(p.day), hh: Number(p.hour) % 24, mm: Number(p.minute) };
  }

  // Hora "de pared" en tz → instante UTC (ms). Dos pasadas cubren los cambios de horario.
  function zonedToUtc(y, m, d, hh, mm, tz) {
    const want = Date.UTC(y, m - 1, d, hh, mm);
    let guess = want;
    for (let i = 0; i < 2; i += 1) {
      const p = partsIn(guess, tz);
      guess += want - Date.UTC(p.y, p.m - 1, p.d, p.hh, p.mm);
    }
    return guess;
  }

  const pad = (n) => String(n).padStart(2, "0");
  function toInput(ms, tz) {
    if (!Number.isFinite(ms)) return "";
    const p = partsIn(ms, tz);
    return `${p.y}-${pad(p.m)}-${pad(p.d)}T${pad(p.hh)}:${pad(p.mm)}`;
  }
  function fromInput(value, tz) {
    const m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/.exec(String(value || ""));
    return m ? zonedToUtc(+m[1], +m[2], +m[3], +m[4], +m[5], tz) : NaN;
  }

  function clockMinutes(text) {
    const m = /^(\d{1,2}):(\d{2})/.exec(String(text || ""));
    return m ? Number(m[1]) * 60 + Number(m[2]) : null;
  }

  // Día de la jornada del bar: con jornada nocturna (18:00-04:00), la 01:00 sigue siendo "hoy".
  function businessDate(ms, tz, bd) {
    const p = partsIn(ms, tz);
    const close = bd && bd.overnight ? clockMinutes(bd.close) : null;
    let day = Date.UTC(p.y, p.m - 1, p.d);
    if (close !== null && p.hh * 60 + p.mm < close) day -= 86400000;
    const d = new Date(day);
    return { y: d.getUTCFullYear(), m: d.getUTCMonth() + 1, d: d.getUTCDate() };
  }

  function insideJornada(ms, tz, bd) {
    if (!bd) return true;
    const o = clockMinutes(bd.open);
    const c = clockMinutes(bd.close);
    if (o === null || c === null) return true;
    const p = partsIn(ms, tz);
    const t = p.hh * 60 + p.mm;
    return bd.overnight ? (t >= o || t <= c) : (t >= o && t <= c);
  }

  function fmt(iso) {
    if (!iso && iso !== 0) return "—";
    try {
      return new Intl.DateTimeFormat(locale(), { weekday: "short", day: "numeric", month: "short", hour: "numeric", minute: "2-digit", timeZone: zone() }).format(new Date(iso));
    } catch (_) { return String(iso); }
  }
  function fmtClock(text) {
    const m = clockMinutes(text);
    if (m === null) return text || "";
    try { return new Intl.DateTimeFormat(locale(), { hour: "numeric", minute: "2-digit", timeZone: "UTC" }).format(new Date(Date.UTC(2026, 0, 1, Math.floor(m / 60), m % 60))); } catch (_) { return text; }
  }

  function countdown(iso) {
    if (!iso) return "";
    const s = Math.max(0, Math.round((new Date(iso).getTime() - nowMs()) / 1000));
    const d = Math.floor(s / 86400);
    const hh = Math.floor((s % 86400) / 3600);
    const mm = Math.floor((s % 3600) / 60);
    const ss = s % 60;
    if (d) return `${d} d ${hh} h`;
    return hh ? `${hh}:${pad(mm)}:${pad(ss)}` : `${mm}:${pad(ss)}`;
  }

  // ------------------------------------------------------------ atajos y validación del "Cuándo"
  const roundUp5 = (ms) => Math.ceil(ms / 300000) * 300000;
  function presetTime(preset, now, tz, bd) {
    if (preset === "1h") return roundUp5(now + 3600000);
    const day = businessDate(now, tz, bd);
    const base = zonedToUtc(day.y, day.m, day.d, 20, 0, tz);
    return preset === "tomorrow" ? zonedToUtc(day.y, day.m, day.d + 1, 20, 0, tz) : base;
  }

  // Las horas del reto según el tipo a partir de la hora principal del atajo.
  function whenFromMain(type, mainMs, tz) {
    if (type === "consumption") {
      return { registration_ends_at: toInput(mainMs, tz), starts_at: toInput(mainMs, tz), ends_at: toInput(mainMs + TOURNAMENT_HOURS * 3600000, tz) };
    }
    return type === "score_pool" ? { predictions_close_at: toInput(mainMs, tz) } : { ends_at: toInput(mainMs, tz) };
  }

  const WHEN_FIELDS = {
    consumption: [["registration_ends_at", "Cierre de inscripción"], ["starts_at", "Inicio del torneo"], ["ends_at", "Cierre del torneo"]],
    score_pool: [["predictions_close_at", "Pronósticos hasta (inicio del partido)"]],
    vote_poll: [["ends_at", "Cierre"]],
  };

  function checkWhen(type, when, now, tz, bd) {
    const ms = {};
    const errors = [];
    const warnings = [];
    for (const [key, label] of WHEN_FIELDS[type]) {
      ms[key] = fromInput(when[key], tz);
      if (!Number.isFinite(ms[key])) errors.push(T("Falta: {f}", { f: T(label) }));
    }
    if (errors.length) return { errors, warnings, ms };
    if (type === "consumption") {
      if (ms.registration_ends_at <= now) errors.push(T(ERRORS.inscripcion_en_el_pasado));
      if (ms.starts_at < ms.registration_ends_at) errors.push(T(ERRORS.inicio_antes_de_inscripcion));
      if (ms.ends_at <= ms.starts_at) errors.push(T(ERRORS.cierre_antes_de_inicio));
    } else {
      const key = WHEN_FIELDS[type][0][0];
      if (ms[key] <= now) errors.push(T(type === "score_pool" ? ERRORS.pronosticos_en_el_pasado : ERRORS.cierre_en_el_pasado));
    }
    const outside = [];
    for (const [key, label] of WHEN_FIELDS[type]) {
      if (ms[key] > now + 45 * 86400000) errors.push(T(ERRORS.fecha_muy_lejana));
      if (bd && !insideJornada(ms[key], tz, bd)) outside.push(T(label));
    }
    if (outside.length) warnings.push(T("Fuera de la jornada del bar: {f}.", { f: outside.join(", ") }));
    return { errors: [...new Set(errors)], warnings, ms };
  }

  // ------------------------------------------------------------ datos
  const base = () => `${ctx.apiBase}/loyalty-retos/companies/${encodeURIComponent(ctx.companyId)}`;
  const headers = (json) => { const t = ctx.token(); return { ...(t ? { Authorization: `Bearer ${t}` } : {}), ...(json ? { "Content-Type": "application/json" } : {}) }; };
  function errText(code) { return T(ERRORS[code] || code || "No se pudo completar la acción."); }

  async function call(path, method = "GET", body = undefined) {
    const res = await fetch(`${base()}${path}`, { method, headers: headers(body !== undefined), body: body !== undefined ? JSON.stringify(body) : undefined });
    let data = null;
    try { data = await res.json(); } catch (_) {}
    if (!res.ok) {
      const err = new Error(errText(data && typeof data.detail === "string" ? data.detail : ""));
      err.status = res.status;
      throw err;
    }
    return data;
  }

  async function loadState(first = false) {
    if (first) { model.loading = true; draw(); }
    try {
      model.st = await call("/state");
      model.offset = new Date(model.st.now).getTime() - Date.now();
      model.denied = "";
    } catch (error) {
      if (error.status === 401 || error.status === 403) model.denied = T("Retos para las mesas no está disponible para tu usuario.");
      else model.error = error.message;
    } finally { model.loading = false; }
    if (!inputsBusy()) draw();
  }

  function schedule() {
    if (timer) clearTimeout(timer);
    timer = setTimeout(async () => {
      if (!ctx || !document.querySelector("[data-rt-root]")) { timer = null; return; }
      if (!model.busy && model.tab === "main") await loadState();
      schedule();
    }, anyActive() ? 4000 : 15000);
  }
  const anyActive = () => !!(model.st && Object.values(model.st.active || {}).some(Boolean));

  function tick() {
    if (ticker) clearInterval(ticker);
    ticker = setInterval(() => {
      if (!ctx || !document.querySelector("[data-rt-root]")) { clearInterval(ticker); ticker = null; return; }
      document.querySelectorAll("[data-rt-count]").forEach((el) => { el.textContent = countdown(el.getAttribute("data-rt-count")); });
    }, 1000);
  }

  async function act(kind, fn) {
    model.busy = kind; model.error = ""; model.info = ""; draw();
    try { await fn(); } catch (error) { model.error = error.message || T("No se pudo completar la acción."); }
    finally { model.busy = ""; model.confirm = ""; draw(); }
  }

  // ------------------------------------------------------------ vistas: encabezado y paso 1
  function head() {
    const games = model.st && model.st.games_on;
    return `<header class="client-hero rt-head"><div class="rt-head-text"><p class="client-eyebrow">${h(T("Módulo Fidelización"))}</p>
        <h1 class="client-title">${h(T("Retos para las mesas"))}</h1>
        <p class="rt-lead">${h(T("Lanza un reto, sigue en vivo cómo va y entrega el premio al ganador. Las mesas participan desde su QR."))}</p></div>
      <div class="client-actions rt-head-actions"><button class="client-btn" type="button" data-client-back-dashboard>${h(T("Dashboard"))}</button>
        ${games ? `<button class="client-btn" type="button" data-rt-games>🎮 ${h(T("Juegos en vivo"))}</button>` : ""}
        <button class="client-btn${model.tab === "history" ? " is-on" : ""}" type="button" data-rt-tab="${model.tab === "history" ? "main" : "history"}" aria-pressed="${model.tab === "history"}">${h(T("Historial"))}</button></div></header>`;
  }

  function typeCards() {
    const active = (model.st && model.st.active) || {};
    return `<section class="client-panel rt-card" aria-labelledby="rtPick"><h2 class="rt-h" id="rtPick">${h(T("¿Qué quieres lanzar?"))}</h2>
      <div class="rt-types">${Object.keys(TYPES).map((t) => {
        const busy = active[t];
        return `<article class="rt-type${busy ? " is-busy" : ""}"><span class="rt-type-icon" aria-hidden="true">${ICONS[t]}</span>
          <div class="rt-type-body"><h3>${h(T(TYPES[t]))}</h3><p>${h(T(HOW[t]))}</p>
          ${busy ? `<p class="rt-type-busy" role="status">${h(T(BUSY[t]))}: <b>${h(busy.title)}</b></p>` : ""}</div>
          ${busy ? `<button type="button" class="rt-btn" data-rt-goto="${h(busy.id)}">${h(T("Ver el que está en curso"))}</button>`
            : `<button type="button" class="client-btn rt-btn is-primary" data-rt-new="${t}">${h(T("Lanzar"))}</button>`}</article>`;
      }).join("")}</div></section>`;
  }

  // ------------------------------------------------------------ asistente
  function newWizard(type) {
    const tz = zone();
    const bd = model.st && model.st.business_day;
    const main = presetTime("1h", nowMs(), tz, bd);
    const def = DEFAULTS[type];
    return { type, step: 1, errors: [], data: { title: T(def.title), description: def.description ? T(def.description) : "", prize: "", team_a: "", team_b: "", vote_mode: "registration", options: ["", "", ""], secret_answer: "" },
      preset: "1h", when: whenFromMain(type, main, tz) };
  }

  function stepper(step) {
    const names = ["Qué", "Cuándo", "Revisar y publicar"];
    return `<ol class="rt-steps">${names.map((n, i) => `<li class="${i + 1 === step ? "is-on" : i + 1 < step ? "is-done" : ""}" ${i + 1 === step ? 'aria-current="step"' : ""}><b>${i + 1}</b><span>${h(T(n))}</span></li>`).join("")}</ol>`;
  }

  function field(label, input, hint = "") {
    return `<label class="rt-field"><span>${h(T(label))}</span>${input}${hint ? `<small>${h(T(hint))}</small>` : ""}</label>`;
  }

  function stepWhat(w) {
    const d = w.data;
    const own = w.type === "score_pool"
      ? `<div class="rt-vs">${field("Equipo 1", `<input data-rt-w="team_a" maxlength="120" value="${h(d.team_a)}" placeholder="${h(T("Ej: Colombia"))}">`)}<b aria-hidden="true">VS</b>${field("Equipo 2", `<input data-rt-w="team_b" maxlength="120" value="${h(d.team_b)}" placeholder="${h(T("Ej: Argentina"))}">`)}</div>`
      : w.type === "vote_poll" ? voteFields(d) : "";
    return `${field("Título", `<input data-rt-w="title" maxlength="160" value="${h(d.title)}">`)}
      <div class="rt-field"><label for="rtPrize">${h(T("Premio"))}</label><input id="rtPrize" data-rt-w="prize" maxlength="220" value="${h(d.prize)}" placeholder="${h(T("Ej: 1/4 de ron"))}">
        <div class="rt-chips" role="group" aria-label="${h(T("Ejemplos de premio"))}">${PRIZE_EXAMPLES.map((p) => `<button type="button" class="rt-chip" data-rt-prize="${h(p)}">${h(T(p))}</button>`).join("")}</div></div>
      ${own}
      ${w.type !== "vote_poll" ? field("Texto que verán las mesas", `<textarea data-rt-w="description" maxlength="700" rows="2">${h(d.description)}</textarea>`) : ""}`;
  }

  function voteFields(d) {
    const mode = d.vote_mode;
    const secret = mode === "yes_no" ? ["yes", "no"] : mode === "true_false" ? ["true", "false"] : null;
    return `<fieldset class="rt-modes"><legend>${h(T("Tipo de concurso"))}</legend>${Object.keys(MODES).map((m) => `<label class="rt-mode${mode === m ? " is-on" : ""}">
        <input type="radio" name="rtMode" value="${m}" data-rt-mode ${mode === m ? "checked" : ""}><span><b>${h(T(MODES[m]))}</b><small>${h(T(MODE_HOW[m]))}</small></span></label>`).join("")}</fieldset>
      ${field(mode === "registration" ? "¿A qué se inscriben?" : "La pregunta", `<textarea data-rt-w="description" maxlength="700" rows="2" placeholder="${h(T(mode === "registration" ? "Ej: Inscríbete al karaoke de las 10" : mode === "participants" ? "Ej: ¿Quién cantó mejor?" : "Ej: ¿Colombia gana el partido?"))}">${h(d.description)}</textarea>`)}
      ${mode === "participants" ? `<div class="rt-field"><span>${h(T("Opciones (hasta 5)"))}</span><div class="rt-options">${d.options.map((o, i) => `<div class="rt-option"><input data-rt-opt="${i}" maxlength="120" value="${h(o)}" aria-label="${h(T("Opción {n}", { n: i + 1 }))}" placeholder="${h(T("Opción {n}", { n: i + 1 }))}">${d.options.length > 2 ? `<button type="button" class="rt-btn is-small" data-rt-opt-del="${i}" aria-label="${h(T("Quitar opción {n}", { n: i + 1 }))}">✕</button>` : ""}</div>`).join("")}</div>
        ${d.options.length < 5 ? `<button type="button" class="rt-btn is-small" data-rt-opt-add>+ ${h(T("Opción"))}</button>` : ""}</div>` : ""}
      ${secret ? `<fieldset class="rt-secret"><legend>🔒 ${h(T("Respuesta correcta (secreta: las mesas no la ven)"))}</legend>${secret.map((k) => `<label class="rt-mode is-inline${d.secret_answer === k ? " is-on" : ""}"><input type="radio" name="rtSecret" value="${k}" data-rt-secret ${d.secret_answer === k ? "checked" : ""}><b>${h(T(ANSWERS[k]))}</b></label>`).join("")}</fieldset>` : ""}`;
  }

  function stepWhen(w) {
    const tz = zone();
    const bd = model.st && model.st.business_day;
    const now = nowMs();
    const tonight = presetTime("tonight", now, tz, bd);
    const presets = [["1h", "En 1 hora"], ["tonight", "Hoy 8:00 p. m."], ["tomorrow", "Mañana"], ["custom", "Personalizado"]];
    const check = checkWhen(w.type, w.when, now, tz, bd);
    const main = w.type === "consumption" ? "Inicio del torneo (cierra la inscripción)" : WHEN_FIELDS[w.type][0][1];
    const fields = w.preset === "custom"
      ? WHEN_FIELDS[w.type].map(([k, label]) => field(label, `<input type="datetime-local" data-rt-when="${k}" value="${h(w.when[k] || "")}">`)).join("")
      : `<ul class="rt-times">${WHEN_FIELDS[w.type].map(([k, label]) => `<li><span>${h(T(label))}</span><b>${h(fmt(fromInput(w.when[k], tz)))}</b></li>`).join("")}</ul>`;
    return `<p class="rt-muted">${h(T("Elige {m}.", { m: T(main).toLowerCase() }))}${w.type === "consumption" ? ` ${h(T("El torneo dura {n} horas; cámbialo en Personalizado.", { n: TOURNAMENT_HOURS }))}` : ""}</p>
      <div class="rt-chips is-presets" role="group" aria-label="${h(T("Atajos"))}">${presets.map(([k, l]) => `<button type="button" class="rt-chip${w.preset === k ? " is-on" : ""}" data-rt-preset="${k}" aria-pressed="${w.preset === k}" ${k === "tonight" && tonight <= now ? "disabled" : ""}>${h(T(l))}</button>`).join("")}</div>
      ${fields}
      <p class="rt-zone">🕒 ${h(T("Horas de {z}", { z: tz }))}${bd ? ` · ${h(T("Jornada del bar: {a} a {b}", { a: fmtClock(bd.open), b: fmtClock(bd.close) }))}` : ""}</p>
      ${check.errors.length ? `<ul class="rt-alert" role="alert">${check.errors.map((e) => `<li>${h(e)}</li>`).join("")}</ul>` : ""}
      ${check.warnings.length ? `<ul class="rt-alert is-warn" role="status">${check.warnings.map((e) => `<li>${h(e)}</li>`).join("")}</ul>` : ""}`;
  }

  function summaryRows(w) {
    const d = w.data;
    const tz = zone();
    const rows = [["Tipo", T(TYPES[w.type])], ["Título", d.title], ["Premio", d.prize || "—"], ["Cómo se gana", T(w.type === "vote_poll" ? MODE_HOW[d.vote_mode] : HOW[w.type])]];
    if (w.type === "score_pool") rows.push(["Partido", `${d.team_a} vs ${d.team_b}`]);
    if (w.type === "vote_poll") {
      rows.push(["Tipo de concurso", T(MODES[d.vote_mode])], [d.vote_mode === "registration" ? "Inscripción" : "Pregunta", d.description || "—"]);
      if (d.vote_mode === "participants") rows.push(["Opciones", d.options.filter((o) => o.trim()).join(" · ")]);
      if (d.secret_answer) rows.push(["Respuesta correcta", `🔒 ${T(ANSWERS[d.secret_answer])}`]);
    }
    WHEN_FIELDS[w.type].forEach(([k, label]) => rows.push([label, fmt(fromInput(w.when[k], tz))]));
    return `<dl class="rt-summary">${rows.map(([k, v]) => `<div><dt>${h(T(k))}</dt><dd>${h(v)}</dd></div>`).join("")}</dl>`;
  }

  // Maqueta del celular: así se verá en el QR de la mesa (sin la respuesta secreta).
  function phone(w) {
    const d = w.data;
    const tz = zone();
    let body = "";
    if (w.type === "consumption") {
      body = `<p class="rt-ph-k">${h(T("Sorteo activo"))}</p><p class="rt-ph-t">${h(d.title)}</p><p class="rt-ph-m">${h(d.description)}</p>
        <p class="rt-ph-prize"><span>${h(T("Premio"))}</span><b>${h(d.prize || T("Por definir"))}</b></p>
        <p class="rt-ph-row"><span>${h(T("Inscripción cierra"))}</span><b>${h(fmt(fromInput(w.when.registration_ends_at, tz)))}</b></p>
        <span class="rt-ph-input">${h(T("Nombre del equipo"))}</span><span class="rt-ph-btn">${h(T("Sí, participar"))}</span>`;
    } else if (w.type === "score_pool") {
      body = `<p class="rt-ph-k">${h(T("Polla activa"))}</p><p class="rt-ph-t">${h(d.title)}</p>
        <p class="rt-ph-prize"><span>${h(T("Premio"))}</span><b>${h(d.prize || T("Por definir"))}</b></p>
        <div class="rt-ph-score"><span>${h(d.team_a || T("Equipo 1"))}<i>0</i></span><span>${h(d.team_b || T("Equipo 2"))}<i>0</i></span></div>
        <p class="rt-ph-row"><span>${h(T("Pronósticos hasta"))}</span><b>${h(fmt(fromInput(w.when.predictions_close_at, tz)))}</b></p>
        <span class="rt-ph-btn">${h(T("Enviar marcador"))}</span>`;
    } else {
      const opts = d.vote_mode === "participants" ? d.options.filter((o) => o.trim()) : d.vote_mode === "yes_no" ? [T("Sí"), T("No")] : d.vote_mode === "true_false" ? [T("Verdadero"), T("Falso")] : [];
      body = `<p class="rt-ph-k">${h(T(MODES[d.vote_mode]))}</p><p class="rt-ph-t">${h(d.title)}</p><p class="rt-ph-m">${h(d.description)}</p>
        <p class="rt-ph-prize"><span>${h(T("Premio"))}</span><b>${h(d.prize || T("Por definir"))}</b></p>
        ${opts.map((o) => `<span class="rt-ph-opt">${h(o)}<i aria-hidden="true"></i></span>`).join("")}
        <span class="rt-ph-btn">${h(T(d.vote_mode === "registration" ? "Inscribirme" : "Enviar respuesta"))}</span>`;
    }
    return `<figure class="rt-phone" aria-label="${h(T("Así se verá en el QR de la mesa"))}"><div class="rt-phone-screen">${body}</div><figcaption>${h(T("Así se verá en el QR de la mesa"))}</figcaption></figure>`;
  }

  function wizardView() {
    const w = model.wizard;
    const body = w.step === 1 ? stepWhat(w) : w.step === 2 ? stepWhen(w) : `<div class="rt-review">${summaryRows(w)}${phone(w)}</div>`;
    return `<section class="client-panel rt-card rt-wizard" aria-labelledby="rtWizTitle"><header class="rt-wiz-head"><h2 class="rt-h" id="rtWizTitle">${ICONS[w.type]} ${h(T(TYPES[w.type]))}</h2>
        <button type="button" class="rt-btn is-small" data-rt-cancel>${h(T("Cancelar"))}</button></header>
      ${stepper(w.step)}
      <div class="rt-wiz-body">${body}</div>
      ${w.errors.length ? `<ul class="rt-alert" role="alert">${w.errors.map((e) => `<li>${h(e)}</li>`).join("")}</ul>` : ""}
      <footer class="rt-wiz-foot">${w.step > 1 ? `<button type="button" class="rt-btn" data-rt-back>← ${h(T("Atrás"))}</button>` : "<span></span>"}
        ${w.step < 3 ? `<button type="button" class="client-btn rt-btn is-primary" data-rt-next>${h(T("Siguiente"))} →</button>`
          : `<button type="button" class="client-btn rt-btn is-primary" data-rt-publish ${model.busy ? "disabled" : ""}>${h(T("Publicar"))}</button>`}</footer></section>`;
  }

  function validateWhat(w) {
    const d = w.data;
    const out = [];
    if (!String(d.prize || "").trim()) out.push(T(ERRORS.premio_requerido));
    if (w.type === "score_pool") {
      if (!d.team_a.trim() || !d.team_b.trim()) out.push(T(ERRORS.equipos_requeridos));
      else if (d.team_a.trim().toLowerCase() === d.team_b.trim().toLowerCase()) out.push(T(ERRORS.equipos_iguales));
    }
    if (w.type === "vote_poll") {
      if (d.vote_mode !== "registration" && !String(d.description || "").trim()) out.push(T(ERRORS.pregunta_requerida));
      if (d.vote_mode === "participants") {
        const opts = d.options.map((o) => o.trim()).filter(Boolean);
        if (opts.length < 2) out.push(T(ERRORS.opciones_de_2_a_5));
        else if (new Set(opts.map((o) => o.toLowerCase())).size !== opts.length) out.push(T(ERRORS.opciones_repetidas));
      }
      if ((d.vote_mode === "yes_no" || d.vote_mode === "true_false") && !d.secret_answer) out.push(T(ERRORS.respuesta_correcta_requerida));
    }
    return out;
  }

  function payloadOf(w) {
    const d = w.data;
    const tz = zone();
    const iso = (k) => new Date(fromInput(w.when[k], tz)).toISOString();
    const out = { type: w.type, title: d.title, prize: d.prize, description: d.description };
    if (w.type === "consumption") Object.assign(out, { registration_ends_at: iso("registration_ends_at"), starts_at: iso("starts_at"), ends_at: iso("ends_at") });
    if (w.type === "score_pool") Object.assign(out, { team_a: d.team_a, team_b: d.team_b, predictions_close_at: iso("predictions_close_at") });
    if (w.type === "vote_poll") {
      Object.assign(out, { vote_mode: d.vote_mode, ends_at: iso("ends_at") });
      if (d.vote_mode === "participants") out.options = d.options.map((o) => o.trim()).filter(Boolean);
      if (d.secret_answer && (d.vote_mode === "yes_no" || d.vote_mode === "true_false")) out.secret_answer = d.secret_answer;
    }
    return out;
  }

  // ------------------------------------------------------------ en curso
  function timeline(r) {
    const order = ["registration", "playing", "result"];
    const at = order.indexOf(r.stage);
    const labels = r.campaign_type === "vote_poll" ? { registration: r.vote_mode === "registration" ? "Inscripción" : "Votación", playing: "En juego", result: "Resultado" } : STAGES;
    const steps = r.campaign_type === "vote_poll" ? ["registration", "result"] : order;
    return `<ol class="rt-line" aria-label="${h(T("Etapa"))}">${steps.map((s) => {
      const i = order.indexOf(s);
      return `<li class="${i === at ? "is-on" : i < at ? "is-done" : ""}" ${i === at ? 'aria-current="step"' : ""}>${h(T(labels[s]))}</li>`;
    }).join("")}</ol>`;
  }

  function winnerText(wn) {
    if (!wn) return "";
    if (wn.kind === "option") return wn.label;
    const who = wn.player_name ? `${wn.player_name} · ` : "";
    return `${who}${wn.team_name || wn.label || ""}${wn.table_number && wn.table_number !== wn.team_name ? ` (${wn.table_number})` : ""}`;
  }

  function liveBoard(r) {
    if (r.campaign_type === "consumption") {
      const rows = arr(r.leaderboard).slice(0, 5);
      return rows.length ? `<ol class="rt-rank">${rows.map((x) => `<li><b>${h(x.rank)}</b><span>${h(x.team_name)}<small>${h(x.table_number)} · ${h(T("{n} pedido(s)", { n: x.orders_count }))}</small></span><em>${h(money(x.total))}</em></li>`).join("")}</ol>`
        : `<p class="rt-muted">${h(T("Aún no hay mesas inscritas."))}</p>`;
    }
    if (r.campaign_type === "score_pool") {
      const preds = arr(r.predictions);
      if (!preds.length) return `<p class="rt-muted">${h(T("Aún no hay pronósticos."))}</p>`;
      const counts = {};
      preds.forEach((p) => { const k = `${p.score_a} - ${p.score_b}`; counts[k] = (counts[k] || 0) + 1; });
      const top = Object.entries(counts).sort((a, b) => b[1] - a[1]).slice(0, 6);
      return `<p class="rt-sub">${h(T("Marcadores más pronosticados"))}</p><ul class="rt-tally">${top.map(([k, n]) => `<li><b>${h(k)}</b><span>${h(T("{n} mesa(s)", { n }))}</span></li>`).join("")}</ul>`;
    }
    if (r.vote_mode === "registration") {
      const votes = arr(r.votes);
      return votes.length ? `<ul class="rt-tally is-list">${votes.slice(0, 12).map((v) => `<li><b>${h(v.voter_name || v.table_number)}</b><span>${h(v.table_number)}</span></li>`).join("")}</ul>` : `<p class="rt-muted">${h(T("Aún no hay inscritos."))}</p>`;
    }
    const results = arr(r.results);
    return results.length ? `<ul class="rt-bars">${results.map((x) => `<li><span>${h(x.label)}${r.secret_answer_key === x.key ? ` <i class="rt-lock" title="${h(T("Respuesta correcta"))}">🔒 ${h(T("correcta"))}</i>` : ""}</span><b>${h(x.count)}</b><i class="rt-bar"><i style="width:${Math.min(100, Math.max(0, Number(x.percent || 0)))}%"></i></i></li>`).join("")}</ul>` : "";
  }

  function money(v) {
    try { return new Intl.NumberFormat(locale(), { style: "currency", currency: (model.st && model.st.currency) || "COP", maximumFractionDigits: 0 }).format(Number(v || 0)); } catch (_) { return String(v); }
  }

  function form(id) { return model.forms[id] || (model.forms[id] = { score_a: "", score_b: "", pick: "", kind: "memory", answer: "", doc: "" }); }

  function confirmBtn(r, action, label, secondary = false) {
    return `<button type="button" class="${secondary ? "" : "client-btn "}rt-btn${secondary ? "" : " is-primary"}" data-rt-ask="${h(`${r.id}:${action}`)}" ${model.busy ? "disabled" : ""}>${action === "cancel" ? "↺ " : ""}${h(T(label))}</button>`;
  }

  function findReto(id) {
    return Object.values((model.st && model.st.active) || {}).find((r) => r && r.id === id) || null;
  }

  function confirmDialog() {
    if (!model.confirm) return "";
    const [id, action] = model.confirm.split(":");
    const r = findReto(id);
    if (!r || !CONFIRM_TITLES[action]) return "";
    const body = CONFIRM_BODY[action === "close" ? `close_${r.campaign_type}` : action];
    return `<div class="rt-dialog-back" data-rt-dialog><div class="rt-dialog client-panel" role="dialog" aria-modal="true" aria-labelledby="rtDlgT" aria-describedby="rtDlgB">
      <h2 class="rt-h" id="rtDlgT">${h(T(CONFIRM_TITLES[action]))}</h2><p class="rt-dlg-reto">${ICONS[r.campaign_type]} ${h(r.title)}</p><p id="rtDlgB">${h(T(body))}</p>
      <div class="rt-confirm"><button type="button" class="client-btn rt-btn is-primary" data-rt-do="${h(action)}" data-rt-id="${h(id)}" ${model.busy ? "disabled" : ""}>${h(T("Sí, {a}", { a: T(CONFIRM_TITLES[action]).toLowerCase() }))}</button>
        <button type="button" class="rt-btn" data-rt-unconfirm>${h(T("Volver"))}</button></div></div></div>`;
  }

  function choices(r) {
    const res = r.result || {};
    if (r.campaign_type === "score_pool") return arr(res.matches).map((m) => ({ key: m.table_key, label: `${m.team_name} (${m.table_number})` }));
    if (r.result_status === "tie") return arr(res.tied).map((o) => ({ key: o.key, label: `${o.label} · ${T("{n} voto(s)", { n: o.votes })}` }));
    return arr(r.votes).map((v) => ({ key: v.table_key, label: `${v.voter_name || v.table_number} (${v.table_number})` }));
  }

  function nextStep(r) {
    const f = form(r.id);
    const out = [];
    const legacySecret = r.campaign_type === "vote_poll" && (r.vote_mode === "yes_no" || r.vote_mode === "true_false") && !r.secret_answer_key;
    if (arr(r.actions).includes("close_now")) {
      const label = "Terminar ahora";
      out.push(`${legacySecret ? `<label class="rt-field is-inline"><span>${h(T("¿Cuál era la respuesta correcta?"))}</span><select data-rt-f="answer" data-rt-id="${h(r.id)}"><option value="">—</option>${(r.vote_mode === "yes_no" ? ["yes", "no"] : ["true", "false"]).map((k) => `<option value="${k}" ${f.answer === k ? "selected" : ""}>${h(T(ANSWERS[k]))}</option>`).join("")}</select></label>` : ""}
        ${confirmBtn(r, "close", label)}`);
    }
    if (arr(r.actions).includes("set_score")) {
      out.push(`<div class="rt-score-form"><label class="rt-field is-num"><span>${h(r.team_a)}</span><input type="number" min="0" max="99" inputmode="numeric" data-rt-f="score_a" data-rt-id="${h(r.id)}" value="${h(f.score_a)}"></label>
        <b aria-hidden="true">-</b><label class="rt-field is-num"><span>${h(r.team_b)}</span><input type="number" min="0" max="99" inputmode="numeric" data-rt-f="score_b" data-rt-id="${h(r.id)}" value="${h(f.score_b)}"></label>
        ${confirmBtn(r, "score", "Poner marcador final")}</div>`);
    }
    if (arr(r.actions).includes("tiebreak") && r.result_status === "tie") {
      const tb = r.tiebreak;
      const liveRound = tb && (tb.status === "registration" || tb.status === "playing");
      if (liveRound) {
        out.push(`<p class="rt-note" role="status">🎮 ${h(T("Desempate en Juegos en vivo: {g} · {s} · {n} inscrito(s)", { g: T(GAMES[tb.kind] || tb.kind), s: T(ROUND[tb.status] || tb.status), n: tb.players }))}</p>
          <button type="button" class="client-btn rt-btn is-primary" data-rt-games>${h(T("Abrir Juegos en vivo"))}</button>`);
      } else if (model.st && model.st.games_on) {
        out.push(`${tb && tb.status ? `<p class="rt-note">${h(T("La ronda de desempate terminó sin ganador. Abre otra o elige el ganador."))}</p>` : ""}
          <div class="rt-row"><label class="rt-field is-inline"><span>${h(T("Juego"))}</span><select data-rt-f="kind" data-rt-id="${h(r.id)}">${Object.keys(GAMES).map((k) => `<option value="${k}" ${f.kind === k ? "selected" : ""}>${h(T(GAMES[k]))}</option>`).join("")}</select></label>
          ${confirmBtn(r, "tiebreak", "Desempatar con Juego en vivo")}</div>`);
      }
    }
    if (arr(r.actions).includes("pick_winner")) {
      const list = choices(r);
      const tb = r.tiebreak;
      if (!(tb && (tb.status === "registration" || tb.status === "playing"))) {
        out.push(`<fieldset class="rt-pick"><legend>${h(T(r.campaign_type === "score_pool" && model.st && model.st.games_on ? "O elige el ganador" : "Elegir ganador"))}</legend>
          ${list.map((c) => `<label class="rt-mode is-inline${f.pick === c.key ? " is-on" : ""}"><input type="radio" name="rtPick-${h(r.id)}" value="${h(c.key)}" data-rt-f="pick" data-rt-id="${h(r.id)}" ${f.pick === c.key ? "checked" : ""}><b>${h(c.label)}</b></label>`).join("") || `<p class="rt-muted">${h(T("No hay entre quién elegir."))}</p>`}
          ${list.length ? confirmBtn(r, "pick", "Elegir ganador") : ""}</fieldset>`);
      }
    }
    if (arr(r.actions).includes("cancel")) out.push(`<div class="rt-cancel-row">${confirmBtn(r, "cancel", "Cancelar y reiniciar", true)}</div>`);
    return out.join("");
  }

  function resultLine(r) {
    const res = r.result || {};
    if (r.campaign_type === "score_pool" && r.final_score) {
      return `<p class="rt-final">${h(T("Marcador final"))}: <b>${h(r.team_a)} ${h(r.final_score.score_a)} - ${h(r.final_score.score_b)} ${h(r.team_b)}</b></p>
        ${r.result_status === "tie" ? `<p class="rt-note">⚖️ ${h(T("Empate: {n} mesas acertaron el marcador exacto.", { n: arr(res.matches).length }))} ${h(arr(res.matches).map((m) => m.table_number).join(", "))}</p>` : ""}`;
    }
    if (r.result_status === "tie") return `<p class="rt-note">⚖️ ${h(T("Empate en votos: el bar elige entre las empatadas."))}</p>`;
    if (r.result_status === "pick") return `<p class="rt-note">${h(T("Inscripción cerrada: elige al ganador de la lista."))}</p>`;
    return "";
  }

  function retoCard(r) {
    const left = r.deadline ? `<p class="rt-count"><span>${h(T(r.deadline_label))}</span><b data-rt-count="${h(r.deadline)}">${h(countdown(r.deadline))}</b></p>` : "";
    const sub = r.campaign_type === "score_pool" ? `${r.team_a} vs ${r.team_b}` : r.campaign_type === "vote_poll" ? T(MODES[r.vote_mode] || "Concurso") : T(HOW.consumption);
    return `<article class="client-panel rt-card rt-live" id="rt-${h(r.id)}" data-rt-live="${h(r.id)}"><header class="rt-live-head"><span class="rt-type-icon" aria-hidden="true">${ICONS[r.campaign_type]}</span>
        <div><h3>${h(r.title)}</h3><p class="rt-muted">${h(sub)}</p></div><p class="rt-prize">🎁 ${h(r.prize || T("Por definir"))}</p></header>
      ${timeline(r)}
      <div class="rt-live-meta">${left}<p class="rt-count"><span>${h(T("Participantes"))}</span><b>${h(r.participants)}</b></p></div>
      ${r.campaign_type === "vote_poll" && r.description ? `<p class="rt-q">${h(r.description)}</p>` : ""}
      ${resultLine(r)}
      ${liveBoard(r)}
      <div class="rt-next">${nextStep(r) || (r.campaign_type === "score_pool" && r.stage === "registration" ? `<p class="rt-muted">${h(T("Cuando empiece el partido se cierran los pronósticos y podrás poner el marcador final."))}</p>` : "")}</div></article>`;
  }

  function prizeBox(item) {
    const f = form(item.id);
    const needsDoc = item.winner && item.winner.source === "tiebreak";
    return `<div class="rt-prize-act">${needsDoc ? `<label class="rt-field is-inline"><span>${h(T("Documento del ganador"))}</span><input data-rt-f="doc" data-rt-id="${h(item.id)}" inputmode="numeric" autocomplete="off" maxlength="20" value="${h(f.doc)}"></label>` : ""}
      <button type="button" class="client-btn rt-btn is-primary is-small" data-rt-deliver="${h(item.id)}" ${model.busy ? "disabled" : ""}>${h(T(needsDoc ? "Validar y entregar" : "Marcar entregado"))}</button></div>`;
  }

  function pendingPrizes() {
    const list = arr(model.st && model.st.history).filter((x) => x.prize_status === "pending");
    if (!list.length) return "";
    return `<section class="client-panel rt-card rt-pending" aria-labelledby="rtPend"><h2 class="rt-h" id="rtPend">🎁 ${h(T("Premios por entregar"))}</h2>
      <ul class="rt-hist">${list.map((x) => `<li><div><b>${h(winnerText(x.winner))}</b><small>${h(x.title)} · ${h(x.prize)}</small></div>${prizeBox(x)}</li>`).join("")}</ul></section>`;
  }

  function liveColumn() {
    const active = Object.values((model.st && model.st.active) || {}).filter(Boolean);
    return `<section class="rt-col" aria-labelledby="rtLive"><h2 class="rt-h rt-col-h" id="rtLive">${h(T("En curso"))}</h2>
      ${active.length ? active.map(retoCard).join("") : `<div class="client-panel rt-card"><p class="rt-muted">${h(T("No hay retos en curso. Lanza uno y aparecerá aquí."))}</p></div>`}
      ${pendingPrizes()}</section>`;
  }

  function historyView() {
    const list = arr(model.st && model.st.history);
    return `<section class="client-panel rt-card" aria-labelledby="rtHist"><h2 class="rt-h" id="rtHist">${h(T("Historial"))}</h2>
      ${list.length ? `<ul class="rt-hist is-full">${list.map((x) => `<li><span class="rt-type-icon" aria-hidden="true">${ICONS[x.type] || "•"}</span>
        <div class="rt-hist-main"><b>${h(x.title)}</b><small>${h(fmt(x.closed_at))}${x.type === "score_pool" ? ` · ${h(x.team_a)} vs ${h(x.team_b)}` : ""}${x.final_score ? ` · ${h(x.final_score.score_a)} - ${h(x.final_score.score_b)}` : ""}</small>
          <small>${h(T("Premio"))}: ${h(x.prize || "—")}</small></div>
        <div class="rt-hist-win">${x.status === "cancelled" ? `<b>↺ ${h(T("Cancelado"))}</b><small>${h(fmt(x.closed_at))}${x.closed_by ? ` · ${h(x.closed_by)}` : ""}</small>`
          : x.winner ? `<b>🏆 ${h(winnerText(x.winner))}</b><small>${h(T(SOURCES[x.source] || ""))}</small>` : `<b>${h(T(x.result_status ? OUTCOMES[x.result_status] || "" : "Sin resultado registrado"))}</b>`}</div>
        <div class="rt-hist-prize">${x.prize_status === "delivered" ? `<i class="rt-chip-ok">✓ ${h(T("Entregado"))}</i><small>${h(fmt(x.prize_delivered_at))} · ${h(x.prize_delivered_by)}</small>`
          : x.prize_status === "pending" ? `<i class="rt-chip-pend">${h(T("Pendiente"))}</i>${prizeBox(x)}` : "<small>—</small>"}</div></li>`).join("")}</ul>`
        : `<p class="rt-muted">${h(T("Aún no hay retos cerrados."))}</p>`}</section>`;
  }

  function view() {
    if (model.denied) return `<div class="rt-root" data-rt-root>${head()}<section class="client-panel rt-card"><p class="rt-denied">${h(model.denied)}</p></section></div>`;
    const notices = `${model.error ? `<div class="rt-notice" role="alert">${h(model.error)}</div>` : ""}${model.info ? `<div class="rt-notice is-ok" role="status">${h(model.info)}</div>` : ""}`;
    if (!model.st) return `<div class="rt-root" data-rt-root>${head()}${notices}<section class="client-panel rt-card"><p class="rt-muted">${h(T("Cargando…"))}</p></section></div>`;
    const body = model.tab === "history" ? historyView()
      : `<div class="rt-layout"><div class="rt-col">${model.wizard ? wizardView() : typeCards()}</div>${liveColumn()}</div>`;
    return `<div class="rt-root" data-rt-root>${head()}${notices}${body}${confirmDialog()}</div>`;
  }

  function draw() {
    if (!ctx) return;
    const host = ctx.host();
    if (host) host.innerHTML = view();
  }

  // El sondeo no repinta mientras alguien escribe: lo escrito vive en el modelo.
  function inputsBusy() {
    const el = typeof document !== "undefined" ? document.activeElement : null;
    return !!(el && el.closest && el.closest("[data-rt-root]") && /^(INPUT|SELECT|TEXTAREA)$/.test(el.tagName));
  }

  // ------------------------------------------------------------ eventos
  function go(step) {
    const w = model.wizard;
    if (step > w.step) {
      const errors = w.step === 1 ? validateWhat(w) : w.step === 2 ? checkWhen(w.type, w.when, nowMs(), zone(), model.st.business_day).errors : [];
      if (errors.length) { w.errors = errors; draw(); return; }
    }
    w.errors = [];
    w.step = Math.max(1, Math.min(3, step));
    draw();
  }

  function onClick(event) {
    const t = event.target;
    if (!ctx || !t || !t.closest || !t.closest("[data-rt-root]")) return;
    const attr = (a) => { const el = t.closest(`[${a}]`); return el ? el.getAttribute(a) : null; };
    let v;
    if (t.closest("[data-rt-games]")) { stop(); if (ctx.openGames) ctx.openGames(); return; }
    if ((v = attr("data-rt-tab"))) { model.tab = v; model.error = ""; model.info = ""; draw(); return; }
    if ((v = attr("data-rt-new"))) { model.wizard = newWizard(v); model.error = ""; model.info = ""; draw(); return; }
    if ((v = attr("data-rt-goto"))) { const el = document.getElementById(`rt-${v}`); if (el && el.scrollIntoView) el.scrollIntoView({ behavior: "smooth", block: "start" }); if (el && el.focus) { el.setAttribute("tabindex", "-1"); el.focus(); } return; }
    if (t.closest("[data-rt-cancel]")) { model.wizard = null; draw(); return; }
    if (t.closest("[data-rt-back]")) { go(model.wizard.step - 1); return; }
    if (t.closest("[data-rt-next]")) { go(model.wizard.step + 1); return; }
    if ((v = attr("data-rt-prize")) !== null) { model.wizard.data.prize = v; draw(); return; }
    if ((v = attr("data-rt-preset"))) {
      const w = model.wizard;
      w.preset = v;
      if (v !== "custom") w.when = whenFromMain(w.type, presetTime(v, nowMs(), zone(), model.st.business_day), zone());
      draw();
      return;
    }
    if (t.closest("[data-rt-opt-add]")) { if (model.wizard.data.options.length < 5) model.wizard.data.options.push(""); draw(); return; }
    if ((v = attr("data-rt-opt-del")) !== null) { model.wizard.data.options.splice(Number(v), 1); draw(); return; }
    if (t.closest("[data-rt-publish]")) {
      const w = model.wizard;
      const errors = [...validateWhat(w), ...checkWhen(w.type, w.when, nowMs(), zone(), model.st.business_day).errors];
      if (errors.length) { w.errors = errors; draw(); return; }
      act("publish", async () => {
        await call("/retos", "POST", payloadOf(w));
        model.wizard = null;
        model.info = T("Publicado: ya aparece en el QR de las mesas.");
        await loadState();
      });
      return;
    }
    if ((v = attr("data-rt-ask"))) { model.confirm = v; draw(); return; }
    if (t.closest("[data-rt-unconfirm]") || (t.hasAttribute && t.hasAttribute("data-rt-dialog"))) { model.confirm = ""; draw(); return; }
    if ((v = attr("data-rt-do"))) {
      const id = attr("data-rt-id");
      const f = form(id);
      const paths = {
        close: ["/close", f.answer ? { answer_key: f.answer } : {}],
        score: ["/score", { score_a: f.score_a === "" ? null : Number(f.score_a), score_b: f.score_b === "" ? null : Number(f.score_b) }],
        pick: ["/winner", { key: f.pick }],
        tiebreak: ["/tiebreak", { kind: f.kind || "memory" }],
        cancel: ["/cancel", {}],
      };
      const r = findReto(id);
      const [path, body] = paths[v];
      act(v, async () => {
        await call(`/retos/${encodeURIComponent(id)}${path}`, "POST", body);
        model.info = v === "tiebreak" ? T("Desempate abierto: inícialo en Juegos en vivo cuando estén las mesas.")
          : v === "cancel" ? T("Cancelado: ya no se ve en el QR y puedes lanzar otro.")
          : v === "close" && r && r.campaign_type === "score_pool" ? T("Pronósticos cerrados: ya puedes poner el marcador final.") : T("Listo.");
        await loadState();
      });
      return;
    }
    if ((v = attr("data-rt-deliver"))) {
      const f = form(v);
      const body = f.doc ? { document: f.doc } : {};
      f.doc = "";
      act("deliver", async () => {
        const res = await call(`/retos/${encodeURIComponent(v)}/prize`, "POST", body);
        model.info = res.match ? T("Premio entregado.") : "";
        if (!res.match) model.error = T("✗ El documento no coincide con el del ganador.");
        await loadState();
      });
    }
  }

  function onInput(event) {
    const t = event.target;
    if (!ctx || !t || !t.closest || !t.closest("[data-rt-root]")) return;
    const w = model.wizard;
    let v;
    if (w && (v = t.getAttribute("data-rt-w"))) { w.data[v] = t.value; return; }
    if (w && (v = t.getAttribute("data-rt-opt")) !== null) { w.data.options[Number(v)] = t.value; return; }
    if (w && (v = t.getAttribute("data-rt-when"))) { w.when[v] = t.value; return; }
    if ((v = t.getAttribute("data-rt-f"))) { form(t.getAttribute("data-rt-id"))[v] = t.value; }
  }

  function onChange(event) {
    onInput(event);
    const t = event.target;
    if (!ctx || !t || !t.closest || !t.closest("[data-rt-root]")) return;
    const w = model.wizard;
    if (w && t.hasAttribute("data-rt-mode")) { w.data.vote_mode = t.value; w.data.secret_answer = ""; draw(); return; }
    if (w && t.hasAttribute("data-rt-secret")) { w.data.secret_answer = t.value; draw(); return; }
    if (w && t.hasAttribute("data-rt-when")) { draw(); return; }  // revalida el orden de las fechas
    if (t.getAttribute("data-rt-f") === "pick") draw();
  }

  function onKey(event) {
    if (event.key === "Escape" && model.confirm && ctx) { model.confirm = ""; draw(); }
  }

  function stop() {
    if (timer) clearTimeout(timer);
    if (ticker) clearInterval(ticker);
    timer = null;
    ticker = null;
  }

  async function mount(context) {
    ctx = context;
    if (!bound && typeof document.addEventListener === "function") {
      document.addEventListener("click", onClick);
      document.addEventListener("change", onChange);
      document.addEventListener("input", onInput);
      document.addEventListener("keydown", onKey);
      bound = true;
    }
    Object.assign(model, { st: null, tab: "main", wizard: null, error: "", info: "", busy: "", denied: "", confirm: "", forms: {}, loading: false });
    draw();
    await loadState(true);
    schedule();
    tick();
  }

  window.CxLoyaltyRetos = { mount, model, view, zonedToUtc, toInput, fromInput, businessDate, presetTime, whenFromMain, checkWhen, insideJornada, payloadOf, validateWhat, newWizard, countdown, winnerText };
})();
