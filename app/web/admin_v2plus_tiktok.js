// Consola v2+ · Publicar en TikTok (solo Admin V2). Cumple las Content Sharing Guidelines de TikTok:
// creator_info al abrir (avatar y nickname de la cuenta; el avatar no se guarda), privacidad SOLO de
// privacy_level_options y sin valor por defecto, interacciones sin marcar (y en gris si la cuenta las tiene
// apagadas), divulgacion de contenido comercial, declaracion legal que cambia sola, duracion maxima, y nada se
// envia a TikTok hasta tocar Publicar o Enviar como borrador. El servidor valida las mismas reglas.
// Sin estilos en linea (CSP de v2+): todo por clase. Todo escapado.
(() => {
  "use strict";

  const API = "/api/v1/tiktok/admin";
  const h = (v) => String(v ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
  const arr = (v) => (Array.isArray(v) ? v : []);
  const MAX_CAPTION = 2200;
  const PRIVATE = "SELF_ONLY";
  const LEGAL = {
    music: "https://www.tiktok.com/legal/page/global/music-usage-confirmation/en",
    branded: "https://www.tiktok.com/legal/page/global/bc-policy/en",
  };
  // Nombres de privacidad (las opciones salen SIEMPRE de privacy_level_options).
  const PRIVACY_LABEL = {
    PUBLIC_TO_EVERYONE: "Todos (público)", MUTUAL_FOLLOW_FRIENDS: "Amigos (seguidores mutuos)",
    FOLLOWER_OF_CREATOR: "Seguidores", SELF_ONLY: "Solo yo (privado)",
  };
  const STATE_LABEL = { PROCESANDO: "⏳ Procesando", PUBLICADO: "✅ Publicado", FALLO: "❌ Falló", EN_BANDEJA: "📥 En la bandeja de TikTok" };
  const POLL_MS = 5000;

  async function request(url, options = {}) {
    const response = await fetch(url, { credentials: "same-origin", ...options,
      headers: { Accept: "application/json", ...(options.body && typeof options.body === "string" ? { "Content-Type": "application/json" } : {}), ...(options.headers || {}) } });
    const data = await response.json().catch(() => ({}));
    if (response.status === 401) { window.location.href = "/admin-v2plus/login"; throw new Error("Sesión vencida."); }
    if (!response.ok) {
      const d = data && data.detail;
      const err = new Error((d && d.mensaje) || (typeof d === "string" && d) || `Respuesta ${response.status}`);
      err.code = (d && d.codigo) || "";
      throw err;
    }
    return data;
  }
  const api = {
    estado: () => request(`${API}/estado`),
    creator: () => request(`${API}/creator`),
    piezas: () => request(`${API}/piezas`),
    publicaciones: () => request(`${API}/publicaciones`),
    conectar: () => request(`${API}/conectar`, { method: "POST" }),
    desconectar: () => request(`${API}/desconectar`, { method: "POST" }),
    publicar: (body) => request(`${API}/publicar`, { method: "POST", body: JSON.stringify(body) }),
    borrador: (pieza) => request(`${API}/borrador`, { method: "POST", body: JSON.stringify({ pieza }) }),
    estadoPublicacion: (id) => request(`${API}/publicaciones/${encodeURIComponent(id)}/estado`),
    subir: (file, caption) => { const f = new FormData(); f.append("file", file); f.append("caption", caption || ""); f.append("tema", file.name || "Video subido");
      return request(`${API}/subir`, { method: "POST", body: f }); },
  };

  function fresh() {
    return { status: null, creator: null, creatorError: "", pieces: [], posts: [], piece: "", caption: "", privacy: "",
      allow: { comment: false, duet: false, stitch: false }, disclosure: false, yourBrand: false, branded: false,
      busy: "", notice: "", error: "", current: null, confirmDisconnect: false };
  }
  const model = fresh();
  let ctx = null;
  let bound = false;
  let poll = null;

  // ------------------------------------------------------------ reglas (puras, las mismas del servidor)
  function selectedPiece(m = model) { return arr(m.pieces).find((p) => p.id === m.piece) || null; }

  function privacyOptions(m = model) {
    const options = arr(m.creator && m.creator.privacy_level_options);
    return options.map((value) => ({ value, label: PRIVACY_LABEL[value] || value,
      disabled: value === PRIVATE && m.disclosure && m.branded,   // Branded content no puede ser privado
      note: value === PRIVATE && m.disclosure && m.branded ? "Branded content visibility cannot be set to private." : "" }));
  }

  function disclosureLabel(m = model) {
    if (!m.disclosure) return "";
    if (m.branded) return "Your photo/video will be labeled as 'Paid partnership'";
    if (m.yourBrand) return "Your photo/video will be labeled as 'Promotional content'";
    return "";
  }

  function declaration(m = model) {
    if (m.disclosure && m.branded) {
      return { text: "By posting, you agree to TikTok's Branded Content Policy and Music Usage Confirmation",
        links: [["Branded Content Policy", LEGAL.branded], ["Music Usage Confirmation", LEGAL.music]] };
    }
    return { text: "By posting, you agree to TikTok's Music Usage Confirmation", links: [["Music Usage Confirmation", LEGAL.music]] };
  }

  // Motivo por el que NO se puede publicar ("" = se puede).
  function blocker(m = model) {
    if (!m.status || !m.status.conectada) return "Conecta la cuenta de TikTok.";
    if (m.creatorError) return m.creatorError;
    if (!m.creator) return "Consultando la cuenta de TikTok…";
    const piece = selectedPiece(m);
    if (!piece) return "Elige una pieza o sube un video.";
    const max = Number(m.creator.max_video_post_duration_sec || 0);
    if (max && piece.duracion && piece.duracion > max + 0.5) return `El video dura ${Math.round(piece.duracion)} s y esta cuenta permite máximo ${max} s.`;
    if (String(m.caption || "").length > MAX_CAPTION) return `El texto tiene más de ${MAX_CAPTION} caracteres.`;
    if (m.disclosure && !m.yourBrand && !m.branded) return "You need to indicate if your content promotes yourself, a third party, or both.";
    if (!m.privacy) return "Elige quién puede ver la publicación.";
    const opt = privacyOptions(m).find((o) => o.value === m.privacy);
    if (!opt || opt.disabled) return opt && opt.note ? opt.note : "Elige quién puede ver la publicación.";
    return "";
  }

  // Cuerpo que se manda al servidor (las casillas deshabilitadas por la cuenta nunca van en true).
  function payload(m = model) {
    const c = m.creator || {};
    return { pieza: m.piece, caption: m.caption, privacy_level: m.privacy,
      allow_comment: m.allow.comment && !c.comment_disabled, allow_duet: m.allow.duet && !c.duet_disabled, allow_stitch: m.allow.stitch && !c.stitch_disabled,
      disclosure: m.disclosure, your_brand: m.disclosure && m.yourBrand, branded_content: m.disclosure && m.branded };
  }

  // ------------------------------------------------------------ vistas
  function header() {
    return `<header class="vp-head"><div><p class="vp-eyebrow">REDES · NEXA</p><h1 class="vp-title">Publicar en TikTok</h1></div></header>`;
  }

  function account(m = model) {
    const s = m.status || {};
    if (!s.configurado) {
      return `<section class="vp-panel vp-section vp-tt-account" data-tt-account><p><b>Falta configurar la app de TikTok.</b> Crea en Railway (servicio del backend)
        las variables <code>TIKTOK_CLIENT_KEY</code> y <code>TIKTOK_CLIENT_SECRET</code> con las claves de Production de "Clonexa Nexa".</p></section>`;
    }
    if (!s.conectada) {
      return `<section class="vp-panel vp-section vp-tt-account" data-tt-account><p>La cuenta de TikTok no está conectada.</p>
        <button class="vp-btn vp-btn-primary" type="button" data-tt-connect ${m.busy === "connect" ? "disabled" : ""}>Conectar TikTok</button></section>`;
    }
    const c = m.creator;
    const who = c ? `<img class="vp-tt-avatar" src="${h(c.avatar)}" alt="" referrerpolicy="no-referrer" width="48" height="48">
        <div><b>${h(c.nickname)}</b>${c.username ? `<small>@${h(c.username)}</small>` : ""}<small>Esta es la cuenta que recibirá la publicación.</small></div>`
      : `<div>${m.creatorError ? `<b>${h(m.creatorError)}</b>` : "Consultando la cuenta de TikTok…"}</div>`;
    return `<section class="vp-panel vp-section vp-tt-account" data-tt-account><div class="vp-tt-who">${who}</div>
      <div class="vp-tt-account-actions">${m.confirmDisconnect
        ? `<button class="vp-btn vp-btn-danger" type="button" data-tt-disconnect="go">Confirmar: desconectar y borrar el acceso</button>`
        : `<button class="vp-btn vp-btn-sm" type="button" data-tt-disconnect="ask">Desconectar</button>`}</div></section>`;
  }

  function pieceList(m = model) {
    const rows = arr(m.pieces);
    const items = rows.map((p) => `<label class="vp-tt-piece ${m.piece === p.id ? "is-active" : ""}"><input type="radio" name="tt-piece" value="${h(p.id)}" data-tt-piece ${m.piece === p.id ? "checked" : ""}>
        <span><b>${h(p.tema || "Video")}</b><small>${h(p.fecha || "")}${p.duracion ? ` · ${h(Math.round(p.duracion))} s` : ""} · ${p.origen === "calendario" ? "calendario" : "subido"}</small></span></label>`).join("");
    return `<fieldset class="vp-tt-pieces"><legend>Contenido</legend>${items || `<p class="vp-empty">Todavía no hay piezas. Usa «Publicar en TikTok» en la vista previa de Telegram o sube un mp4.</p>`}
      <label class="vp-btn vp-btn-sm vp-tt-upload">⬆ Subir un mp4<input type="file" accept="video/mp4" data-tt-upload hidden></label></fieldset>`;
  }

  function preview(m = model) {
    const p = selectedPiece(m);
    if (!p) return "";
    const max = Number((m.creator && m.creator.max_video_post_duration_sec) || 0);
    const long = max && p.duracion && p.duracion > max + 0.5;
    return `<div class="vp-tt-preview"><video class="vp-tt-video" src="${API}/piezas/${h(p.id)}/video" controls playsinline preload="metadata"></video>
      ${long ? `<p class="vp-alert" role="alert">El video dura ${h(Math.round(p.duracion))} s y esta cuenta permite máximo ${h(max)} s: no se puede publicar.</p>` : ""}</div>`;
  }

  function form(m = model) {
    const c = m.creator || {};
    const opts = privacyOptions(m);
    const onlyPrivate = !(m.status && m.status.auditada);
    const check = (key, label, off) => `<label class="vp-tt-check ${off ? "is-disabled" : ""}"><input type="checkbox" data-tt-allow="${key}" ${m.allow[key] && !off ? "checked" : ""} ${off ? "disabled" : ""}> ${h(label)}</label>`;
    const decl = declaration(m);
    let declHtml = h(decl.text);
    decl.links.forEach(([label, url]) => { declHtml = declHtml.replace(h(label), `<a href="${h(url)}" target="_blank" rel="noopener noreferrer">${h(label)}</a>`); });
    const stop = blocker(m);
    const len = String(m.caption || "").length;
    return `<div class="vp-tt-form">
      <label class="vp-tt-field"><span>Título / texto <small data-tt-count>${h(len)} / ${MAX_CAPTION}</small></span>
        <textarea data-tt-caption maxlength="${MAX_CAPTION}" rows="5">${h(m.caption)}</textarea></label>
      <label class="vp-tt-field"><span>¿Quién puede ver este video?</span>
        <select data-tt-privacy required><option value="" ${m.privacy ? "" : "selected"} disabled>Elige una opción</option>
          ${opts.map((o) => `<option value="${h(o.value)}" ${m.privacy === o.value ? "selected" : ""} ${o.disabled ? "disabled" : ""}>${h(o.label)}${o.note ? ` — ${h(o.note)}` : ""}</option>`).join("")}
        </select>${onlyPrivate ? `<small class="vp-tt-note">Hasta que TikTok apruebe la auditoría, las publicaciones quedan privadas.</small>` : ""}</label>
      <fieldset class="vp-tt-group"><legend>Allow users to</legend>
        ${check("comment", "Allow Comment", c.comment_disabled)}${check("duet", "Duet", c.duet_disabled)}${check("stitch", "Stitch", c.stitch_disabled)}</fieldset>
      <fieldset class="vp-tt-group"><legend>Content disclosure</legend>
        <label class="vp-tt-check"><input type="checkbox" role="switch" data-tt-disclosure ${m.disclosure ? "checked" : ""}> Disclose video content</label>
        ${m.disclosure ? `<p class="vp-tt-help">Turn on to disclose that this video promotes goods or services in exchange for something of value. Your video could promote yourself, a third party, or both.</p>
          <label class="vp-tt-check"><input type="checkbox" data-tt-brand="your" ${m.yourBrand ? "checked" : ""}> Your brand <small>You are promoting yourself or your own business.</small></label>
          <label class="vp-tt-check"><input type="checkbox" data-tt-brand="branded" ${m.branded ? "checked" : ""}> Branded content <small>You are promoting another brand or a third party.</small></label>
          ${disclosureLabel(m) ? `<p class="vp-tt-label" data-tt-label>${h(disclosureLabel(m))}</p>` : ""}` : ""}
      </fieldset>
      <p class="vp-tt-declaration" data-tt-declaration>${declHtml}</p>
      ${stop && m.status && m.status.conectada ? `<p class="vp-tt-blocker" data-tt-blocker>${h(stop)}</p>` : ""}
      <div class="vp-tt-actions">
        <button class="vp-btn vp-btn-primary" type="button" data-tt-publish ${stop || m.busy ? "disabled" : ""}>Publicar</button>
        <button class="vp-btn" type="button" data-tt-draft ${!selectedPiece(m) || !(m.status && m.status.conectada) || m.busy ? "disabled" : ""}>Enviar como borrador a la app</button>
      </div></div>`;
  }

  function current(m = model) {
    const p = m.current;
    if (!p) return "";
    const user = m.creator && m.creator.username;
    const link = p.estado === "PUBLICADO" && p.post_id && user ? `https://www.tiktok.com/@${encodeURIComponent(user)}/video/${encodeURIComponent(p.post_id)}` : "";
    return `<section class="vp-panel vp-section vp-tt-status" role="status" data-tt-status>
      <p>${p.modo === "borrador" ? "Enviado a la bandeja de TikTok: ábrelo en la app para terminar de publicarlo." : "Puede tardar unos minutos en procesarse y aparecer en tu perfil."}</p>
      <p class="vp-tt-state"><b>${h(STATE_LABEL[p.estado] || p.estado)}</b>${p.estado === "FALLO" && p.motivo ? ` · ${h(p.motivo)}` : ""}</p>
      ${link ? `<p><a class="vp-btn" href="${h(link)}" target="_blank" rel="noopener noreferrer">Ver la publicación en TikTok</a></p>` : ""}</section>`;
  }

  function registry(m = model) {
    const rows = arr(m.posts);
    if (!rows.length) return "";
    return `<section class="vp-panel vp-section"><h2 class="vp-tt-h2">Registro</h2><table class="vp-table vp-tt-log"><thead><tr><th>Fecha</th><th>Pieza</th><th>Modo</th><th>Estado</th><th>publish_id</th><th>post_id</th></tr></thead><tbody>
      ${rows.map((p) => `<tr><td>${h(String(p.fecha || "").slice(0, 16).replace("T", " "))}</td><td>${h(p.tema)}</td><td>${h(p.modo)}</td><td>${h(STATE_LABEL[p.estado] || p.estado)}</td><td>${h(p.publish_id)}</td><td>${h(p.post_id)}</td></tr>`).join("")}
      </tbody></table></section>`;
  }

  function view(m = model) {
    const msgs = `${m.notice ? `<p class="vp-ok-text" role="status">${h(m.notice)}</p>` : ""}${m.error ? `<div class="vp-alert" role="alert"><span>${h(m.error)}</span></div>` : ""}`;
    if (!m.status) return `${header()}${msgs}<p class="vp-loading">Cargando…</p>`;
    const editor = m.status.conectada ? `<section class="vp-panel vp-section vp-tt-editor">${pieceList(m)}${preview(m)}${form(m)}</section>` : "";
    return `<div class="vp-tt">${header()}${msgs}${account(m)}${current(m)}${editor}${registry(m)}</div>`;
  }

  function root() { return (ctx && ctx.root && ctx.root()) || null; }
  const active = () => ctx && (!ctx.active || ctx.active());
  function draw() { const r = root(); if (r && active()) r.innerHTML = view(); }

  // ------------------------------------------------------------ datos
  async function load() {
    try { model.status = await api.estado(); } catch (e) { model.error = e.message; draw(); return; }
    if (model.status.conectada) {
      try {
        const [creator, pieces, posts] = await Promise.all([api.creator().catch((e) => { throw e; }), api.piezas(), api.publicaciones()]);
        model.creator = creator; model.creatorError = "";
        model.pieces = arr(pieces.piezas); model.posts = arr(posts.publicaciones);
      } catch (e) {
        model.creator = null; model.creatorError = e.message || "No se pudo consultar la cuenta de TikTok.";
        try { model.pieces = arr((await api.piezas()).piezas); model.posts = arr((await api.publicaciones()).publicaciones); } catch (_) {}
      }
      const p = selectedPiece();
      if (p && !model.caption) model.caption = p.caption || "";
    }
    draw();
  }

  function stopPoll() { if (poll) { clearInterval(poll); poll = null; } }
  function startPoll(id) {
    stopPoll();
    poll = setInterval(async () => {
      if (!active()) { stopPoll(); return; }
      try {
        model.current = await api.estadoPublicacion(id);
        if (["PUBLICADO", "FALLO", "EN_BANDEJA"].includes(model.current.estado) && (model.current.estado !== "PUBLICADO" || model.current.post_id)) {
          stopPoll(); model.posts = arr((await api.publicaciones()).publicaciones);
        }
      } catch (e) { model.error = e.message; stopPoll(); }
      draw();
    }, POLL_MS);
  }

  async function run(kind, fn) {
    model.busy = kind; model.error = ""; model.notice = ""; draw();
    try { await fn(); } catch (e) { model.error = e.message; }
    model.busy = ""; draw();
  }

  // ------------------------------------------------------------ eventos
  async function onClick(event) {
    if (!active()) return;
    const t = event.target;
    if (!t || !t.closest) return;
    if (t.closest("[data-tt-connect]")) {
      await run("connect", async () => { const r = await api.conectar(); window.location.href = r.url; });
      return;
    }
    const disc = t.closest("[data-tt-disconnect]");
    if (disc) {
      if (disc.getAttribute("data-tt-disconnect") === "ask") { model.confirmDisconnect = true; draw(); return; }
      await run("disconnect", async () => { await api.desconectar(); Object.assign(model, fresh()); model.notice = "Cuenta desconectada y acceso borrado."; await load(); });
      return;
    }
    if (t.closest("[data-tt-publish]")) {
      if (blocker()) return;
      await run("publish", async () => {
        const r = await api.publicar(payload());
        model.current = { id: r.id, estado: r.estado, modo: "directo", post_id: "" };
        startPoll(r.id);
      });
      return;
    }
    if (t.closest("[data-tt-draft]")) {
      await run("draft", async () => {
        const r = await api.borrador(model.piece);
        model.current = { id: r.id, estado: r.estado, modo: "borrador", post_id: "" };
        startPoll(r.id);
      });
    }
  }

  function onChange(event) {
    if (!active()) return;
    const t = event.target;
    if (!t || !t.closest) return;
    if (t.closest("[data-tt-piece]")) {
      model.piece = t.value; const p = selectedPiece(); model.caption = (p && p.caption) || ""; model.current = null; draw(); return;
    }
    if (t.closest("[data-tt-privacy]")) { model.privacy = t.value; draw(); return; }
    const allow = t.closest("[data-tt-allow]");
    if (allow) { model.allow[allow.getAttribute("data-tt-allow")] = Boolean(t.checked); draw(); return; }
    if (t.closest("[data-tt-disclosure]")) { model.disclosure = Boolean(t.checked); if (!model.disclosure) { model.yourBrand = false; model.branded = false; } draw(); return; }
    const brand = t.closest("[data-tt-brand]");
    if (brand) {
      if (brand.getAttribute("data-tt-brand") === "your") model.yourBrand = Boolean(t.checked);
      else { model.branded = Boolean(t.checked); if (model.branded && model.privacy === PRIVATE) model.privacy = ""; }
      draw(); return;
    }
    if (t.closest("[data-tt-upload]") && t.files && t.files[0]) {
      const file = t.files[0];
      run("upload", async () => {
        const r = await api.subir(file, "");
        model.pieces = [r.pieza, ...model.pieces]; model.piece = r.pieza.id; model.caption = ""; model.notice = "Video subido. Revísalo antes de publicar.";
      });
    }
  }

  function onInput(event) {
    if (!active()) return;
    const t = event.target;
    if (t && t.closest && t.closest("[data-tt-caption]")) {
      model.caption = t.value;
      const r = root();
      const count = r && r.querySelector && r.querySelector("[data-tt-count]");
      if (count) count.textContent = `${model.caption.length} / ${MAX_CAPTION}`;   // sin redibujar: no se pierde el cursor
      const btn = r && r.querySelector && r.querySelector("[data-tt-publish]");
      if (btn) btn.disabled = Boolean(blocker() || model.busy);
    }
  }

  window.CxConsoleSections = window.CxConsoleSections || {};
  window.CxConsoleSections.tiktok = {
    mount(context) {
      ctx = context;
      if (!bound && typeof document.addEventListener === "function") {
        document.addEventListener("click", onClick); document.addEventListener("change", onChange); document.addEventListener("input", onInput); bound = true;
      }
      const params = (context && context.params) || {};
      model.notice = params.conectada ? "Cuenta conectada." : "";
      model.error = params.error === "estado" ? "El enlace de conexión venció o ya se usó. Vuelve a tocar «Conectar TikTok»."
        : params.error === "cancelado" ? "Se canceló la conexión con TikTok." : params.error ? "TikTok no entregó el acceso. Intenta conectar de nuevo." : "";
      if (params.piece) { model.piece = params.piece; model.caption = ""; }
      model.creator = null;   // creator_info SIEMPRE al abrir la pantalla
      draw(); load();
    },
  };
  window.CxConsoleTikTok = { model, fresh, api, view, form, account, current, registry, privacyOptions, declaration, disclosureLabel, blocker, payload, selectedPiece, load, onClick, onChange, onInput, LEGAL };
})();
