// Juegos en vivo · pantalla del bar (TV o proyector, 16:9). Solo lectura con el
// token secreto ?t= (el admin lo regenera). Sin login ni botones.
// Escenas: espera, ruleta (gira ~6 s y cae en el número que el servidor ya
// guardó), registro (QR grande y nombres entrando), en juego (ranking con
// ▲▼ que se reacomoda) y podio con confeti. Consulta cada 1 s solo mientras
// hay algo activo; si no, cada 5 s. Respeta prefers-reduced-motion.
(() => {
  "use strict";

  const h = (v) => String(v ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
  const arr = (v) => (Array.isArray(v) ? v : []);
  const fill = (s, vars) => (vars ? String(s).replace(/\{(\w+)\}/g, (m, k) => (vars[k] !== undefined ? String(vars[k]) : m)) : String(s));
  const T = (s, vars) => (typeof window !== "undefined" && window.CxI18n && typeof window.CxI18n.t === "function" ? window.CxI18n.t(s, vars) : fill(s, vars));
  const KIND = { memory: "Memoria relámpago", trivia: "Trivia Máquina del tiempo", differences: "7 diferencias" };
  const REVEAL_AFTER_MS = 8000;
  const SPIN_MS = 6000;
  const WHEEL_MAX_SEGMENTS = 120;

  // ------------------------------------------------------------ ruleta (puro: se prueba en node)
  const ease = (p) => 1 - Math.pow(1 - Math.min(1, Math.max(0, p)), 3);

  // Ángulo final: varias vueltas completas y el centro del segmento del número bajo la flecha (arriba).
  function rouletteTarget(min, max, target, turns = 6) {
    const size = max - min + 1;
    const seg = 360 / size;
    return turns * 360 + (360 - ((target - min) + 0.5) * seg);
  }

  // Número bajo la flecha para una rotación dada de la rueda.
  function numberAt(angle, min, max) {
    const size = max - min + 1;
    const seg = 360 / size;
    const under = (((360 - (angle % 360)) % 360) + 360) % 360;
    return min + Math.min(size - 1, Math.floor(under / seg));
  }

  function rouletteFrame(p, min, max, target) {
    const final = rouletteTarget(min, max, target);
    const angle = final * ease(p);
    return { angle, number: p >= 1 ? target : numberAt(angle, min, max) };
  }

  // Flechas del ranking: ▲ subió, ▼ bajó (frente a la consulta anterior).
  function arrows(prev, ranking) {
    const out = {};
    for (const r of arr(ranking)) {
      const before = prev[r.id];
      out[r.id] = before === undefined || before === r.rank ? "" : before > r.rank ? "up" : "down";
    }
    return out;
  }

  // ------------------------------------------------------------ estado
  const P = new URLSearchParams(typeof location !== "undefined" ? location.search : "");
  const TOKEN = P.get("t") || "";
  const API = "/api/v1/loyalty-games/screen";
  const view = { scene: "", data: null, offset: 0, prevRanks: {}, shownNames: new Set(), lastDraw: "", spinning: null, timer: null, tick: null, denied: false };
  const reduced = () => typeof window !== "undefined" && window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const $ = (id) => document.getElementById(id);
  const serverNow = () => Date.now() + view.offset;

  function brandVars(b) {
    const root = document.documentElement;
    if (!b) return;
    root.style.setProperty("--lgx-accent", b.primary || "#7c3aed");
    root.style.setProperty("--lgx-accent-2", b.secondary || "#f59e0b");
    if (window.CxI18n && window.CxI18n.setLanguage && b.language && b.language !== "es") window.CxI18n.setLanguage(b.language);
  }

  function brandHead(b, small = false) {
    const logo = b && b.logo_url ? `<img class="lgx-logo" src="${h(b.logo_url)}" alt="">` : "";
    return `<header class="lgx-top${small ? " is-small" : ""}">${logo}<div><p class="lgx-company">${h((b && b.name) || "")}</p><p class="lgx-kicker">🎮 ${h(T("Juegos en vivo"))}</p></div></header>`;
  }

  // Resultado y tiempo (castigos incluidos): "5/7 · 01:42", "8/10 · 02:31", "7 parejas · 01:12".
  function fmtTime(ms) {
    if (ms === null || ms === undefined || ms === "") return "";
    const s2 = Math.max(0, Math.round(Number(ms) / 1000));
    return `${String(Math.floor(s2 / 60)).padStart(2, "0")}:${String(s2 % 60).padStart(2, "0")}`;
  }
  function resultLabel(kind, score, goal, ms) {
    const n = Number(score) || 0;
    const main = kind === "memory" ? T(n === 1 ? "{n} pareja" : "{n} parejas", { n }) : `${n}/${goal || "?"}`;
    const t = fmtTime(ms);
    return t ? `${main} · ${t}` : main;
  }

  function sceneKey(d) {
    if (d.focus === "roulette" && d.roulette) return `roulette:${d.roulette.id}`;
    if (d.focus === "round" && d.round) return `round:${d.round.id}:${d.round.status}`;
    return "idle";
  }

  // ------------------------------------------------------------ escenas
  function idle(d) {
    return `${brandHead(d.brand)}<section class="lgx-idle"><p class="lgx-huge">${h(T("Muy pronto empieza el próximo juego"))}</p>
      <p class="lgx-sub">${h(T("Ruleta · Memoria relámpago · Trivia"))}</p></section>`;
  }

  function wheelSvg(min, max) {
    const size = max - min + 1;
    const segs = Math.min(size, WHEEL_MAX_SEGMENTS);
    const label = size <= 60 ? 1 : Math.ceil(size / 30);
    const seg = 360 / size;
    let out = "";
    for (let i = 0; i < segs; i += 1) {
      const n = size <= WHEEL_MAX_SEGMENTS ? i : Math.floor((i * size) / segs);
      const a0 = (n * seg - 90) * Math.PI / 180;
      const a1 = ((size <= WHEEL_MAX_SEGMENTS ? n + 1 : Math.floor(((i + 1) * size) / segs)) * seg - 90) * Math.PI / 180;
      const x0 = 50 + 48 * Math.cos(a0), y0 = 50 + 48 * Math.sin(a0), x1 = 50 + 48 * Math.cos(a1), y1 = 50 + 48 * Math.sin(a1);
      const large = a1 - a0 > Math.PI ? 1 : 0;
      out += `<path d="M50 50 L${x0.toFixed(3)} ${y0.toFixed(3)} A48 48 0 ${large} 1 ${x1.toFixed(3)} ${y1.toFixed(3)} Z" class="lgx-seg is-${i % 2 ? "b" : "a"}"/>`;
      if (size <= WHEEL_MAX_SEGMENTS && n % label === 0) {
        const mid = (n + 0.5) * seg;
        out += `<text x="50" y="7.5" class="lgx-segtext" transform="rotate(${mid.toFixed(3)} 50 50)">${min + n}</text>`;
      }
    }
    return `<svg viewBox="0 0 100 100" class="lgx-wheel" aria-hidden="true"><g id="lgxWheelG">${out}</g><circle cx="50" cy="50" r="13" class="lgx-hub"/></svg>`;
  }

  function roulette(d) {
    const r = d.roulette;
    return `${brandHead(d.brand, true)}<section class="lgx-roulette">
      <div class="lgx-wheelbox"><div class="lgx-pointer" aria-hidden="true">▼</div>${wheelSvg(r.range_min, r.range_max)}<div class="lgx-center"><b id="lgxNumber">${h(r.number)}</b></div></div>
      <div class="lgx-side"><p class="lgx-kicker">🎡 ${h(T("Ruleta de la rifa"))} · ${h(`${r.range_min}–${r.range_max}`)}</p>
        <p class="lgx-bignum" id="lgxBig" aria-label="${h(T("Número"))}">${h(r.number)}</p>
        ${r.prize ? `<p class="lgx-prize">🎁 ${h(r.prize)}</p>` : ""}
        <p class="lgx-sub">${h(T("Sacados esta noche"))}</p><p class="lgx-drawn" id="lgxDrawn">${arr(r.drawn).map((n) => `<span>${h(n)}</span>`).join("")}</p></div></section>`;
  }

  // Desempate de una polla (Retos para las mesas): solo juegan las mesas empatadas.
  function tiebreakLine(r) {
    const tb = r && r.tiebreak;
    if (!tb) return "";
    return `<p class="lgx-tiebreak">⚖️ ${h(T("Desempate de la polla {teams}", { teams: tb.teams }))}</p><p class="lgx-sub">${h(T("Solo las mesas empatadas: {list}", { list: (tb.tables || []).join(", ") }))}</p>`;
  }

  function registration(d) {
    const r = d.round;
    return `${brandHead(d.brand, true)}<section class="lgx-reg">
      <div class="lgx-qrbox"><img class="lgx-qr" alt="${h(T("Código QR para jugar"))}" src="${API}/${encodeURIComponent(TOKEN)}/qr.svg?r=${encodeURIComponent(r.id)}"><p class="lgx-huge">${h(T("Escanea y juega"))}</p></div>
      <div class="lgx-side"><p class="lgx-kicker">${h(T(KIND[r.kind] || r.kind))}</p>${tiebreakLine(r)}${r.prize ? `<p class="lgx-prize">🎁 ${h(r.prize)}</p>` : ""}
        <p class="lgx-count"><b id="lgxCount">${h(r.count)}</b> <span>${h(T("inscritos"))}</span></p><ul class="lgx-names" id="lgxNames"></ul></div></section>`;
  }

  const img = (r, w) => `${API}/${encodeURIComponent(TOKEN)}/image/${w}.png?r=${encodeURIComponent(r.id)}`;

  function playing(d) {
    const r = d.round;
    const thumbs = r.kind === "differences"
      ? `<div class="lgx-thumbs" aria-hidden="true"><img src="${img(r, "a")}" alt=""><img src="${img(r, "b")}" alt=""></div>` : "";
    return `${brandHead(d.brand, true)}<section class="lgx-live${r.kind === "differences" ? " is-diff" : ""}"><div class="lgx-livehead"><p class="lgx-kicker">${h(T(KIND[r.kind] || r.kind))}</p>${r.tiebreak ? `<p class="lgx-tiebreak">⚖️ ${h(T("Desempate de la polla {teams}", { teams: r.tiebreak.teams }))}</p>` : ""}
        <p class="lgx-clock" id="lgxClock">--:--</p>${r.prize ? `<p class="lgx-prize">🎁 ${h(r.prize)}</p>` : ""}${thumbs}</div>
      <ol class="lgx-rank" id="lgxRank"></ol></section>`;
  }

  function podium(d) {
    const r = d.round;
    const by = {};
    arr(r.podium).forEach((p) => { by[p.place] = p; });
    const step = (n) => `<div class="lgx-step is-${n}">${by[n] ? `<p class="lgx-pname">${h(by[n].name)}</p>${by[n].score !== undefined ? `<p class="lgx-pscore">${h(resultLabel(r.kind, by[n].score, r.goal, by[n].ms))}</p>` : ""}` : `<p class="lgx-pname is-empty">—</p>`}<div class="lgx-block"><b>${n}</b></div></div>`;
    const confetti = reduced() ? "" : `<div class="lgx-confetti" aria-hidden="true">${Array.from({ length: 70 }, (_, i) => `<i style="--x:${(i * 37) % 100};--d:${(i % 10) * 0.18}s;--c:${i % 3}"></i>`).join("")}</div>`;
    return `${brandHead(d.brand, true)}<section class="lgx-podium" id="lgxPodium">${confetti}<p class="lgx-kicker">${h(T(KIND[r.kind] || r.kind))} · ${h(T("Resultados"))}</p>
      ${arr(r.podium).length ? `<div class="lgx-steps">${step(2)}${step(1)}${step(3)}</div>` : `<p class="lgx-huge">${h(T("Esta ronda no tuvo ganadores"))}</p>`}
      ${r.prize ? `<p class="lgx-prize">🎁 ${h(r.prize)}</p>` : ""}<p class="lgx-claim">${h(T((d.texts && d.texts.claim) || "Reclama con tu documento"))}</p></section>
      ${r.kind === "differences" ? reveal(r) : ""}`;
  }

  // 7 diferencias: despues del podio se revelan las 7 con un circulo animado en las dos imagenes.
  function reveal(r) {
    const circles = arr(r.zones).map((z, i) => `<circle cx="${z.x * 1000}" cy="${z.y * 750}" r="${Math.max(22, z.r * 1000)}" style="--i:${i}"/>`).join("");
    const pane = (w) => `<figure class="lgx-reveal-img"><img src="${img(r, w)}" alt=""><svg viewBox="0 0 1000 750" preserveAspectRatio="none" aria-hidden="true">${circles}</svg>
      <figcaption>${w.toUpperCase()}</figcaption></figure>`;
    return `<section class="lgx-reveal" id="lgxReveal" hidden><p class="lgx-kicker">🔍 ${h(T("Las 7 diferencias"))}</p><div class="lgx-reveal-pair">${pane("a")}${pane("b")}</div></section>`;
  }

  function scheduleReveal(r) {
    if (!r || r.kind !== "differences" || r.status !== "closed") return;
    const closed = r.closed_at ? new Date(r.closed_at).getTime() : serverNow();
    const wait = Math.max(0, REVEAL_AFTER_MS - (serverNow() - closed));
    setTimeout(() => {
      const pod = $("lgxPodium"), rev = $("lgxReveal");
      if (!pod || !rev) return;
      pod.hidden = true;
      rev.hidden = false;
    }, wait);
  }

  // ------------------------------------------------------------ actualizaciones dentro de la escena
  function updateNames(r) {
    const list = $("lgxNames");
    if (!list) return;
    const current = new Set(arr(r.players).map((p) => p.id));
    list.querySelectorAll("[data-id]").forEach((li) => { if (!current.has(li.getAttribute("data-id"))) li.remove(); });
    for (const p of arr(r.players)) {
      if (list.querySelector(`[data-id="${CSS.escape(p.id)}"]`)) continue;
      const li = document.createElement("li");
      li.setAttribute("data-id", p.id);
      li.textContent = p.name;
      if (view.shownNames.has(p.id) || reduced()) li.className = "is-static";
      view.shownNames.add(p.id);
      list.prepend(li);
    }
    const c = $("lgxCount");
    if (c) c.textContent = String(r.count);
  }

  function updateRanking(r) {
    const list = $("lgxRank");
    if (!list) return;
    const top = arr(r.ranking).slice(0, 10);
    const marks = arrows(view.prevRanks, top);
    const before = {};
    list.querySelectorAll("[data-id]").forEach((li) => { before[li.getAttribute("data-id")] = li.getBoundingClientRect().top; });
    list.innerHTML = top.map((p) => `<li data-id="${h(p.id)}" class="${p.rank <= 3 ? `is-top is-${p.rank}` : ""}"><b class="lgx-pos">${h(p.rank)}</b><span class="lgx-who">${h(p.name)}</span>
      <span class="lgx-arrow is-${marks[p.id] || "same"}" aria-hidden="true">${marks[p.id] === "up" ? "▲" : marks[p.id] === "down" ? "▼" : ""}</span><em>${h(resultLabel(r.kind, p.score, r.goal, p.ms))}${p.done ? " ✓" : ""}</em></li>`).join("")
      || `<li class="lgx-empty">${h(T("Esperando las primeras jugadas…"))}</li>`;
    if (!reduced()) {
      list.querySelectorAll("[data-id]").forEach((li) => {
        const old = before[li.getAttribute("data-id")];
        if (old === undefined) return;
        const dy = old - li.getBoundingClientRect().top;
        if (!dy) return;
        li.animate([{ transform: `translateY(${dy}px)` }, { transform: "translateY(0)" }], { duration: 550, easing: "cubic-bezier(.2,.8,.2,1)" });
      });
    }
    view.prevRanks = Object.fromEntries(top.map((p) => [p.id, p.rank]));
  }

  function updateClock(r) {
    const el = $("lgxClock");
    if (!el || !r || !r.ends_at) return;
    const s = Math.max(0, Math.ceil((new Date(r.ends_at).getTime() - serverNow()) / 1000));
    el.textContent = `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
    el.classList.toggle("is-ending", s <= 10);
  }

  function animateSpin(r) {
    const g = $("lgxWheelG");
    const num = $("lgxNumber");
    const big = $("lgxBig");
    const elapsed = serverNow() - new Date(r.spun_at).getTime();
    const show = (frame, done) => {
      if (g) g.setAttribute("transform", `rotate(${frame.angle.toFixed(2)} 50 50)`);
      if (num) num.textContent = String(frame.number);
      if (big) { big.textContent = done ? String(r.number) : "…"; big.classList.toggle("is-landed", done); }
    };
    if (reduced() || elapsed >= SPIN_MS) { show(rouletteFrame(1, r.range_min, r.range_max, r.number), true); return; }
    const start = performance.now() - Math.max(0, elapsed);
    const step = (t) => {
      const p = Math.min(1, (t - start) / SPIN_MS);
      show(rouletteFrame(p, r.range_min, r.range_max, r.number), p >= 1);
      if (p < 1 && $("lgxWheelG")) view.spinning = requestAnimationFrame(step);
    };
    view.spinning = requestAnimationFrame(step);
  }

  function paint(d) {
    const stage = $("lgxScreen");
    const key = sceneKey(d);
    if (key !== view.scene) {
      if (view.spinning) cancelAnimationFrame(view.spinning);
      view.scene = key;
      view.prevRanks = {};
      stage.className = `lgx-stage is-${key.split(":")[0]}${d.round ? ` is-${d.round.status}` : ""}`;
      stage.innerHTML = key === "idle" ? idle(d) : key.startsWith("roulette") ? roulette(d) : d.round.status === "registration" ? registration(d)
        : d.round.status === "playing" ? playing(d) : d.round.status === "closed" ? podium(d) : idle(d);
      if (key.startsWith("roulette")) animateSpin(d.roulette);
      if (d.round && key.startsWith("round")) scheduleReveal(d.round);
    }
    if (d.round && key.startsWith("round")) {
      if (d.round.status === "registration") updateNames(d.round);
      if (d.round.status === "playing") { updateRanking(d.round); updateClock(d.round); }
    }
  }

  async function poll() {
    let next = 5000;
    try {
      const res = await fetch(`${API}/${encodeURIComponent(TOKEN)}/state`, { cache: "no-store" });
      if (res.status === 403 || res.status === 404) {
        view.denied = true;
        $("lgxScreen").innerHTML = `<section class="lgx-idle"><p class="lgx-huge">${h(T("Esta pantalla no está autorizada"))}</p><p class="lgx-sub">${h(T("Pide el enlace nuevo en Fidelización › Juegos en vivo."))}</p></section>`;
        return;
      }
      const d = await res.json();
      view.offset = new Date(d.now).getTime() - Date.now();
      view.data = d;
      brandVars(d.brand);
      paint(d);
      const recentSpin = d.focus === "roulette" && d.roulette && serverNow() - new Date(d.roulette.spun_at).getTime() < 20000;
      next = d.active || recentSpin ? 1000 : 5000;
    } catch (_) {
      next = 3000;
    }
    view.timer = setTimeout(poll, next);
  }

  function start() {
    if (!$("lgxScreen")) return;
    view.tick = setInterval(() => { if (view.data && view.data.round && view.data.round.status === "playing") updateClock(view.data.round); }, 250);
    poll();
  }

  if (typeof window !== "undefined") {
    window.CxLoyaltyGamesScreen = { rouletteFrame, rouletteTarget, numberAt, arrows, sceneKey, ease, resultLabel, fmtTime };
    if (typeof document !== "undefined" && document.addEventListener) document.addEventListener("DOMContentLoaded", start);
  }
})();
