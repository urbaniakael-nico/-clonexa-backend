// Juegos en vivo · página del jugador (se abre con el QR de la ronda, ?r=).
// Inscripción: nombre (20), documento y la casilla obligatoria de datos
// (Ley 1581); el documento viaja al servidor y allí solo se guarda su HMAC.
// Memoria: el servidor revela la cara de cada carta solo al voltearla.
// Trivia: 10 s por pregunta con barra; si no responde, pasa sola.
// Consulta cada 1 s solo mientras la ronda está activa. Pensada para 375 px.
(() => {
  "use strict";

  const h = (v) => String(v ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
  const fill = (s, vars) => (vars ? String(s).replace(/\{(\w+)\}/g, (m, k) => (vars[k] !== undefined ? String(vars[k]) : m)) : String(s));
  const T = (s, vars) => (typeof window !== "undefined" && window.CxI18n && typeof window.CxI18n.t === "function" ? window.CxI18n.t(s, vars) : fill(s, vars));
  const KIND = { memory: "Memoria relámpago", trivia: "Trivia Máquina del tiempo" };
  const ERRORS = {
    documento_invalido: "Revisa tu documento (de 5 a 15 letras o números).",
    nombre_requerido: "Escribe tu nombre.",
    consentimiento_requerido: "Debes autorizar el tratamiento de tus datos para jugar.",
    documento_ya_juega: "Ese documento ya está inscrito en esta ronda.",
    registro_cerrado: "El registro de esta ronda ya cerró.",
    demasiadas_peticiones: "Vas muy rápido: espera un momento.",
    ronda_no_encontrada: "Esta ronda no existe o ya no está disponible.",
    ronda_no_en_juego: "La ronda no está en juego.",
    fuera_de_tiempo: "Se acabó el tiempo de esa pregunta.",
  };

  const P = new URLSearchParams(typeof location !== "undefined" ? location.search : "");
  const ROUND = P.get("r") || "";
  const API = `/api/v1/loyalty-games/play/${encodeURIComponent(ROUND)}`;
  const KEY = `cxlg:${ROUND.slice(0, 48)}`;
  const st = { info: null, me: null, token: "", error: "", busy: false, board: {}, lock: false, question: null, feedback: null, timer: null, qtimer: null, form: { name: "", doc: "", consent: false } };
  const $ = (id) => document.getElementById(id);

  function store(get, value) {
    try {
      if (get) return window.localStorage.getItem(KEY) || "";
      window.localStorage.setItem(KEY, value);
    } catch (_) {}
    return "";
  }

  async function call(path, method = "GET", body = undefined) {
    const res = await fetch(`${API}${path}`, {
      method, cache: "no-store",
      headers: { ...(st.token ? { "X-Player-Token": st.token } : {}), ...(body !== undefined ? { "Content-Type": "application/json" } : {}) },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
    let data = null;
    try { data = await res.json(); } catch (_) {}
    if (!res.ok) {
      const code = data && typeof data.detail === "string" ? data.detail : "";
      const err = new Error(T(ERRORS[code] || "No se pudo completar. Intenta de nuevo."));
      err.code = code;
      err.status = res.status;
      throw err;
    }
    return data;
  }

  // ------------------------------------------------------------ vistas
  function top() {
    const b = (st.info && st.info.brand) || {};
    const logo = b.logo_url ? `<img class="lgx-logo" src="${h(b.logo_url)}" alt="">` : "";
    return `<header class="lgx-top is-phone">${logo}<div><p class="lgx-company">${h(b.name || "")}</p><p class="lgx-kicker">${h(T(KIND[st.info && st.info.kind] || "Juegos en vivo"))}</p></div></header>
      ${st.info && st.info.prize ? `<p class="lgx-prize is-phone">🎁 ${h(st.info.prize)}</p>` : ""}`;
  }

  function joinForm() {
    const consent = (st.info.texts && st.info.texts.consent) || "Autorizo el tratamiento de mis datos para este concurso";
    return `<form class="lgx-card lgx-form" data-lgx-join novalidate>
      <label>${h(T("Tu nombre (se verá en la pantalla)"))}<input name="name" maxlength="20" autocomplete="nickname" required value="${h(st.form.name)}"></label>
      <label>${h(T("Documento"))}<input name="doc" inputmode="numeric" autocomplete="off" maxlength="15" required value="${h(st.form.doc)}"><small>${h(T("Solo para validar si ganas. No se muestra a nadie."))}</small></label>
      <label class="lgx-consent"><input type="checkbox" name="consent" ${st.form.consent ? "checked" : ""} required><span>${h(T(consent))} ${h(T("(Ley 1581)"))}</span></label>
      <button type="submit" class="lgx-btn" ${st.busy ? "disabled" : ""}>${h(T("Inscribirme"))}</button></form>`;
  }

  function waiting() {
    return `<section class="lgx-card lgx-wait"><p class="lgx-big">✅ ${h(T("¡Listo, {name}!", { name: st.me.name }))}</p><p>${h(T("Mira tu nombre en la pantalla. El juego empieza cuando el barman lo inicie."))}</p><div class="lgx-dots" aria-hidden="true"><i></i><i></i><i></i></div></section>`;
  }

  function countdown() {
    const ends = st.me && st.me.ends_at ? new Date(st.me.ends_at).getTime() : 0;
    const s = Math.max(0, Math.ceil((ends - (Date.now() + (st.offset || 0))) / 1000));
    return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
  }

  function memory() {
    const m = (st.me && st.me.memory) || { size: 10, faces: {}, matched: [], pairs: 0, total_pairs: 5 };
    const faces = { ...m.faces, ...st.board };
    return `<section class="lgx-card"><div class="lgx-hud"><span>${h(T("Parejas {n} de {t}", { n: m.pairs, t: m.total_pairs }))}</span><b class="lgx-timer" id="lgxTimer">${countdown()}</b></div>
      <div class="lgx-cards">${Array.from({ length: m.size }, (_, i) => {
        const face = faces[String(i)];
        const done = m.matched.includes(i);
        return `<button type="button" class="lgx-card3d${face ? " is-up" : ""}${done ? " is-done" : ""}" data-lgx-flip="${i}" ${done || st.lock ? "disabled" : ""} aria-label="${h(face ? face : T("Carta {n}", { n: i + 1 }))}">
          <span class="lgx-back" aria-hidden="true">?</span><span class="lgx-face" aria-hidden="true">${h(face || "")}</span></button>`;
      }).join("")}</div>${m.pairs >= m.total_pairs ? `<p class="lgx-big">🏁 ${h(T("¡Completaste el tablero!"))}</p>` : ""}</section>`;
  }

  function trivia() {
    const q = st.question;
    if (!q) return `<section class="lgx-card"><p>${h(T("Cargando…"))}</p></section>`;
    if (q.done) return `<section class="lgx-card lgx-wait"><p class="lgx-big">🏁 ${h(T("¡Terminaste! {n} aciertos", { n: q.correct }))}</p><p>${h(T("Espera el resultado en la pantalla."))}</p></section>`;
    const fb = st.feedback;
    return `<section class="lgx-card"><div class="lgx-hud"><span>${h(T("Pregunta {a} de {t}", { a: Math.min(q.total, q.answered + 1), t: q.total }))}${q.lap > 1 ? ` · ${h(T("vuelta {n}", { n: q.lap }))}` : ""}</span><b class="lgx-timer" id="lgxTimer">${countdown()}</b></div>
      <div class="lgx-bar" aria-hidden="true"><i style="animation-duration:${Math.max(0, q.question.remaining_ms)}ms"></i></div>
      <p class="lgx-q">${h(q.question.text)}</p>
      <div class="lgx-opts">${q.question.options.map((o, i) => `<button type="button" class="lgx-opt${fb && fb.choice === i ? (fb.ok ? " is-ok" : " is-bad") : ""}" data-lgx-answer="${i}" ${fb || st.busy ? "disabled" : ""}>${h(o)}</button>`).join("")}</div></section>`;
  }

  function result() {
    const r = st.me.result || {};
    if (r.result === "lost") return `<section class="lgx-card lgx-end is-lost"><p class="lgx-big">⌛ ${h(T("Se acabó el tiempo, perdiste"))}</p><p>${h(T("Te quedaron preguntas sin contestar."))}</p></section>`;
    if (r.result === "ranked" && r.place && r.place <= 3) {
      return `<section class="lgx-card lgx-end is-win"><p class="lgx-big">🏆 ${h(T("¡Quedaste en el puesto {n}!", { n: r.place }))}</p><p>${h(T((st.info.texts && st.info.texts.claim) || "Reclama con tu documento"))}</p></section>`;
    }
    if (r.result === "ranked") return `<section class="lgx-card lgx-end"><p class="lgx-big">${h(T("Quedaste en el puesto {n}", { n: r.place }))}</p><p>${h(T("¡Gracias por jugar!"))}</p></section>`;
    return `<section class="lgx-card lgx-end"><p class="lgx-big">${h(T("¡Gracias por jugar!"))}</p></section>`;
  }

  function body() {
    if (!st.info) return st.error ? `<section class="lgx-card"><p class="lgx-big">${h(st.error)}</p></section>` : `<section class="lgx-card"><p>${h(T("Cargando…"))}</p></section>`;
    const status = st.me ? st.me.status : st.info.status;
    if (!st.me) return status === "registration" ? joinForm() : `<section class="lgx-card"><p class="lgx-big">${h(T("El registro de esta ronda ya cerró."))}</p></section>`;
    if (status === "registration") return waiting();
    if (status === "playing") return st.info.kind === "memory" ? memory() : trivia();
    if (status === "closed") return result();
    return `<section class="lgx-card"><p class="lgx-big">${h(T("Esta ronda se canceló."))}</p></section>`;
  }

  function draw() {
    const root = $("lgxPlay");
    if (!root) return;
    root.innerHTML = `${top()}${st.error && st.info ? `<p class="lgx-error" role="alert">${h(st.error)}</p>` : ""}${body()}`;
  }

  // ------------------------------------------------------------ juego
  async function refreshMe() {
    if (!st.token) return;
    try {
      st.me = await call("/me");
      st.offset = new Date(st.me.now).getTime() - Date.now();
    } catch (error) {
      if (error.status === 403) { st.token = ""; st.me = null; }
    }
  }

  async function loadQuestion() {
    try { st.question = await call("/question", "POST"); st.feedback = null; } catch (error) { if (error.code !== "ronda_no_en_juego") st.error = error.message; }
    draw();
    armQuestionTimer();
  }

  function armQuestionTimer() {
    if (st.qtimer) clearTimeout(st.qtimer);
    const q = st.question;
    if (!q || q.done || !q.question) return;
    // Si no responde en sus 10 s, pasa sola a la siguiente (el servidor la deja pendiente).
    st.qtimer = setTimeout(loadQuestion, Math.max(0, q.question.remaining_ms) + 1200);
  }

  async function loop() {
    if (!st.token) {
      // Aun no inscrito: solo mira si cambio el estado de la ronda (nunca repinta el formulario a mitad de escribir).
      try {
        const info = await call("");
        if (info.status !== st.info.status) { st.info = info; draw(); }
      } catch (_) {}
      st.timer = setTimeout(loop, 3000);
      return;
    }
    const before = st.me && st.me.status;
    await refreshMe();
    const now = st.me ? st.me.status : st.info && st.info.status;
    if (st.info && st.me && st.info.kind === "trivia" && now === "playing" && (before !== "playing" || !st.question)) await loadQuestion();
    if (before !== now || !st.me || now !== "playing" || st.info.kind === "memory") {
      if (!(st.info && st.info.kind === "memory" && st.lock)) draw();
    } else {
      const t = $("lgxTimer");
      if (t) t.textContent = countdown();
    }
    const active = !st.me || ["registration", "playing"].includes(now);
    st.timer = setTimeout(loop, active ? 1000 : 15000);
  }

  async function flip(i) {
    if (st.lock) return;
    try {
      const res = await call("/flip", "POST", { index: i });
      Object.assign(st.board, res.faces);
      if (res.match === false) {
        st.lock = true;
        draw();
        await new Promise((r) => setTimeout(r, 900));
        st.board = {};
        st.lock = false;
      } else if (res.match === true) {
        st.board = {};
      }
      await refreshMe();
    } catch (error) {
      st.error = error.message;
    }
    draw();
  }

  async function answer(i) {
    const q = st.question;
    if (!q || !q.question || st.feedback) return;
    st.busy = true;
    try {
      const res = await call("/answer", "POST", { question_id: q.question.id, choice: i });
      st.feedback = { choice: i, ok: res.ok };
    } catch (error) {
      st.feedback = { choice: i, ok: false };
      if (error.code !== "fuera_de_tiempo") st.error = error.message;
    }
    st.busy = false;
    draw();
    setTimeout(loadQuestion, 700);
  }

  async function join(form) {
    const el = (n) => form.elements.namedItem(n);
    st.form = { name: el("name").value, doc: el("doc").value, consent: el("consent").checked };
    if (!st.form.consent) { st.error = T(ERRORS.consentimiento_requerido); draw(); return; }
    st.busy = true; st.error = ""; draw();
    try {
      const res = await call("/join", "POST", { name: st.form.name, document: st.form.doc, consent: true });
      st.token = res.player_token;
      store(false, st.token);
      st.form.doc = "";
      await refreshMe();
      if (!st.timer) loop();
    } catch (error) {
      st.error = error.message;
    }
    st.busy = false;
    draw();
  }

  async function start() {
    if (!$("lgxPlay")) return;
    document.addEventListener("click", (e) => {
      const f = e.target.closest && e.target.closest("[data-lgx-flip]");
      if (f) { flip(Number(f.getAttribute("data-lgx-flip"))); return; }
      const a = e.target.closest && e.target.closest("[data-lgx-answer]");
      if (a) answer(Number(a.getAttribute("data-lgx-answer")));
    });
    document.addEventListener("input", (e) => {
      const f = e.target.form;
      if (f && f.hasAttribute("data-lgx-join")) st.form = { name: f.elements.namedItem("name").value, doc: f.elements.namedItem("doc").value, consent: f.elements.namedItem("consent").checked };
    });
    document.addEventListener("submit", (e) => {
      const f = e.target.closest && e.target.closest("[data-lgx-join]");
      if (f) { e.preventDefault(); join(f); }
    });
    try {
      st.info = await call("");
      if (st.info.brand) {
        document.documentElement.style.setProperty("--lgx-accent", st.info.brand.primary || "#7c3aed");
        document.documentElement.style.setProperty("--lgx-accent-2", st.info.brand.secondary || "#f59e0b");
        if (window.CxI18n && st.info.brand.language && st.info.brand.language !== "es") window.CxI18n.setLanguage(st.info.brand.language);
      }
    } catch (error) {
      st.error = error.message;
      draw();
      return;
    }
    st.token = store(true);
    draw();
    loop();
  }

  if (typeof window !== "undefined") {
    window.CxLoyaltyGamesPlay = { st, body, ERRORS };
    if (typeof document !== "undefined" && document.addEventListener) document.addEventListener("DOMContentLoaded", start);
  }
})();
