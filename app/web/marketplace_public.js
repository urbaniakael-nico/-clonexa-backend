(() => {
  "use strict";

  const params = new URLSearchParams(location.search);
  const companyId = String(params.get("company_id") || "").trim();
  const selectedPublication = String(params.get("publication") || "").trim();
  const apiBase = `/api/v1/marketplace/companies/${encodeURIComponent(companyId)}`;
  const tokenKey = `clonexa_marketplace_token:${companyId}`;
  let token = localStorage.getItem(tokenKey) || "";
  let user = null;
  let pendingAction = "";
  let publications = [];
  let currentConversation = "";
  let videoReady = true;

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));
  const h = (value) => String(value ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#039;");
  const money = (value) => new Intl.NumberFormat("es-CO", {style:"currency",currency:"COP",maximumFractionDigits:0}).format(Number(value || 0));
  const errors = {
    marketplace_no_disponible:"Este marketplace no está disponible.", telefono_invalido:"Revisa el número de teléfono.",
    telefono_ya_registrado:"Este teléfono ya tiene una cuenta.", telefono_no_registrado:"No encontramos una cuenta con este teléfono.",
    usuario_no_disponible:"Ese usuario ya está en uso.", codigo_vencido_o_inexistente:"El código venció o no existe. Solicita uno nuevo.",
    codigo_incorrecto:"El código no es correcto.", credenciales_invalidas:"Usuario, teléfono o contraseña incorrectos.",
    cuenta_temporalmente_bloqueada:"Cuenta bloqueada por 15 minutos. Intenta más tarde.", demasiados_codigos_solicitados:"Has solicitado varios códigos. Espera unos minutos.",
    espera_antes_de_solicitar_otro_codigo:"Espera 45 segundos antes de pedir otro código.", mensajeria_no_configurada:"La mensajería aún no está configurada.",
    no_se_pudo_enviar_el_mensaje:"No pudimos enviar el mensaje. Revisa el número e intenta de nuevo.", contrasena_actual_incorrecta:"La contraseña actual no coincide.",
    maximo_5_fotos:"Puedes cargar máximo cinco fotos.", imagen_supera_5mb:"Cada foto debe pesar máximo 5 MB.", video_supera_25mb:"El video debe pesar máximo 25 MB.",
    video_maximo_30_segundos:"El video debe durar máximo 30 segundos.", titulo_requerido:"Escribe un título para el artículo.", selecciona_una_foto:"Selecciona al menos una foto.",
    no_puedes_chatear_contigo:"Esta publicación es tuya. Los mensajes de interesados aparecerán en Mis chats.", chat_no_encontrado:"No encontramos esta conversación."
  };

  async function request(path, options = {}) {
    const isForm = options.body instanceof FormData;
    const headers = {...(options.headers || {})};
    if (!isForm) headers["Content-Type"] = "application/json";
    if (token) headers.Authorization = `Bearer ${token}`;
    const response = await fetch(`${apiBase}${path}`, {...options, headers});
    let payload = {};
    try { payload = await response.json(); } catch {}
    if (!response.ok) throw new Error(errors[payload.detail] || payload.detail || "No pudimos completar la solicitud.");
    return payload;
  }

  function message(element, value, error = false) {
    if (!element) return;
    element.textContent = value || "";
    element.classList.toggle("error", error);
  }
  function toast(value) {
    const el = $("#marketToast");
    el.textContent = value; el.hidden = false;
    clearTimeout(toast.timer); toast.timer = setTimeout(() => { el.hidden = true; }, 4200);
  }
  function setTab(name) {
    $$('[data-auth-panel]').forEach((panel) => { panel.hidden = panel.dataset.authPanel !== name; });
    $$('[data-auth-tab]').forEach((button) => button.classList.toggle("active", button.dataset.authTab === name));
    $("#authTabs").hidden = name === "reset";
    message($("#authMessage"), "");
  }
  function openAuth(action = "") {
    pendingAction = action; setTab("login"); $("#authModal").hidden = false;
    document.body.style.overflow = "hidden";
    setTimeout(() => $("#loginForm input")?.focus(), 20);
  }
  function closeAuth() { $("#authModal").hidden = true; document.body.style.overflow = ""; }
  function closeAccount() { $("#accountModal").hidden = true; document.body.style.overflow = ""; }
  function closeChat() { $("#chatModal").hidden = true; document.body.style.overflow = ""; currentConversation = ""; }
  function updateAccount() {
    $("#accountButton").textContent = user ? user.username : "Ingresar";
    if (!user) return;
    $("#profileName").textContent = user.username;
    $("#profilePhone").textContent = `${user.phone_masked} · registrado`;
    $("#profileAvatar").textContent = (user.username || "V").charAt(0).toUpperCase();
    $("#profileForm [name=username]").value = user.username || "";
  }

  function openPublish() {
    $(".market-hero").hidden = true;
    $("#articulos").hidden = true;
    $("#publicar").hidden = false;
    history.replaceState(null, "", `${location.pathname}?company_id=${encodeURIComponent(companyId)}#publicar`);
    window.scrollTo({top:0,behavior:"smooth"});
  }
  function openCatalog(publicationId = "") {
    $(".market-hero").hidden = false;
    $("#articulos").hidden = false;
    $("#publicar").hidden = true;
    const suffix = publicationId ? `&publication=${encodeURIComponent(publicationId)}` : "";
    history.replaceState(null, "", `${location.pathname}?company_id=${encodeURIComponent(companyId)}${suffix}#articulos`);
    setTimeout(() => {
      const target = publicationId ? document.querySelector(`[data-publication-card="${CSS.escape(publicationId)}"]`) : $("#articulos");
      target?.scrollIntoView({behavior:"smooth",block:"start"});
    }, 30);
  }

  async function completePending() {
    const action = pendingAction; pendingAction = "";
    if (action === "publish") return openPublish();
    if (action.startsWith("chat:")) return openChatForPublication(action.slice(5));
  }

  async function restoreSession() {
    if (!token) return updateAccount();
    try { const data = await request("/auth/me"); user = data.user; }
    catch { token = ""; user = null; localStorage.removeItem(tokenKey); }
    updateAccount();
  }

  async function loadConfig() {
    if (!companyId) {
      $("#marketEmpty").innerHTML = "<h3>Falta identificar la empresa</h3><p>Abre el enlace completo suministrado por la empresa.</p>";
      return;
    }
    try {
      const data = await request("/public");
      const name = data.company?.name || "Marketplace";
      document.title = `${data.marketplace?.title || "Cambios y compras"} · ${name}`;
      $("#companyName").textContent = name;
      $("#registeredUsers").textContent = String(data.marketplace?.registered_users || 0);
    } catch (error) {
      $("#marketEmpty").innerHTML = `<h3>Marketplace no disponible</h3><p>${h(error.message)}</p>`;
    }
  }

  function renderPublications() {
    const query = String($("#marketSearch")?.value || "").trim().toLowerCase();
    const visible = publications.filter((item) => `${item.title} ${item.description} ${item.specifications}`.toLowerCase().includes(query));
    const grid = $("#marketProductGrid");
    grid.innerHTML = visible.map((item) => {
      const image = item.image_urls?.[0] || "";
      const mode = item.offer_mode === "money" ? "Solo venta" : item.offer_mode === "change" ? "Solo cambio" : "Venta o cambio";
      return `<article class="market-product" data-publication-card="${h(item.id)}">
        <div class="market-product-media">${image ? `<img src="${h(image)}" alt="${h(item.title)}" loading="lazy">` : ""}<span class="market-product-badge">${h(mode)}</span></div>
        <div class="market-product-body"><span class="market-product-user">@${h(item.seller?.username || "usuario")}</span><h3>${h(item.title)}</h3>
        <p class="market-product-copy">${h(item.description || item.specifications || "Artículo disponible")}</p><strong class="market-product-price">${money(item.price)}</strong>
        <div class="market-product-actions"><button class="market-btn primary" data-chat-publication="${h(item.id)}" type="button">Chat</button><button class="market-btn ghost" data-copy-publication="${h(item.id)}" type="button">Compartir</button></div></div>
      </article>`;
    }).join("");
    $("#marketEmpty").hidden = publications.length > 0;
    if (publications.length && !visible.length) {
      grid.innerHTML = '<div class="market-empty"><h3>Sin coincidencias</h3><p>Prueba con otra palabra.</p></div>';
    }
    if (selectedPublication) setTimeout(() => document.querySelector(`[data-publication-card="${CSS.escape(selectedPublication)}"]`)?.scrollIntoView({behavior:"smooth",block:"center"}), 120);
  }

  async function loadPublications() {
    if (!companyId) return;
    try { const data = await request("/publications"); publications = data.publications || []; renderPublications(); }
    catch (error) { message($("#publishMessage"), error.message, true); }
  }

  async function openChatForPublication(publicationId) {
    if (!user) return openAuth(`chat:${publicationId}`);
    try {
      const data = await request(`/publications/${encodeURIComponent(publicationId)}/chat`, {method:"POST",body:"{}"});
      currentConversation = data.conversation_id;
      $("#chatModal").hidden = false; document.body.style.overflow = "hidden";
      await loadChats(currentConversation);
    } catch (error) { toast(error.message); }
  }

  async function loadChats(selectId = "") {
    if (!user) return;
    const data = await request("/auth/chats");
    const chats = data.chats || [];
    currentConversation = selectId || currentConversation || chats[0]?.id || "";
    $("#chatList").innerHTML = chats.length ? chats.map((chat) => `<button class="${chat.id === currentConversation ? "active" : ""}" data-chat-id="${h(chat.id)}" type="button"><b>${h(chat.title)}</b><small>${h(chat.other_username)} · ${h(chat.last_message || "Sin mensajes")}</small></button>`).join("") : '<div class="market-chat-empty">Aún no tienes conversaciones.</div>';
    if (currentConversation) await loadMessages(currentConversation);
    else { $("#chatMessages").innerHTML = '<div class="market-chat-empty">Los chats sobre tus artículos aparecerán aquí.</div>'; $("#chatForm").hidden = true; }
  }

  async function loadMessages(conversationId) {
    currentConversation = conversationId;
    const data = await request(`/auth/chats/${encodeURIComponent(conversationId)}/messages`);
    $("#chatTitle").textContent = data.conversation?.title || "Chat";
    $("#chatMessages").innerHTML = (data.messages || []).length ? data.messages.map((item) => `<div class="market-chat-bubble ${String(item.sender_user_id) === String(user?.id) ? "mine" : ""}"><small>${h(item.username)}</small>${h(item.body)}</div>`).join("") : '<div class="market-chat-empty">Inicia la conversación sobre este artículo.</div>';
    $("#chatForm").hidden = false;
    $("#chatMessages").scrollTop = $("#chatMessages").scrollHeight;
    $$('[data-chat-id]').forEach((button) => button.classList.toggle("active", button.dataset.chatId === conversationId));
  }

  $$('[data-auth-action]').forEach((button) => button.addEventListener("click", () => {
    const action = button.dataset.authAction || "";
    if (!user) openAuth(action); else { pendingAction = action; completePending(); }
  }));
  $$('[data-close-modal]').forEach((button) => button.addEventListener("click", closeAuth));
  $$('[data-close-account]').forEach((button) => button.addEventListener("click", closeAccount));
  $$('[data-close-chat]').forEach((button) => button.addEventListener("click", closeChat));
  $$('[data-auth-tab]').forEach((button) => button.addEventListener("click", () => setTab(button.dataset.authTab)));
  $("#backToCatalog").addEventListener("click", () => openCatalog());
  $("#marketSearch").addEventListener("input", renderPublications);
  $("#marketProductGrid").addEventListener("click", async (event) => {
    const chat = event.target.closest("[data-chat-publication]");
    if (chat) return openChatForPublication(chat.dataset.chatPublication || "");
    const copy = event.target.closest("[data-copy-publication]");
    if (copy) {
      const url = `${location.origin}${location.pathname}?company_id=${encodeURIComponent(companyId)}&publication=${encodeURIComponent(copy.dataset.copyPublication || "")}`;
      try { await navigator.clipboard.writeText(url); toast("Enlace de la publicación copiado."); } catch { toast(url); }
    }
  });
  $("#accountButton").addEventListener("click", () => {
    if (!user) return openAuth();
    updateAccount(); $("#accountModal").hidden = false; document.body.style.overflow = "hidden";
  });
  $("#openChatsButton").addEventListener("click", async () => {
    closeAccount(); $("#chatModal").hidden = false; document.body.style.overflow = "hidden";
    try { await loadChats(); } catch (error) { message($("#chatMessage"), error.message, true); }
  });
  $("#chatList").addEventListener("click", async (event) => {
    const button = event.target.closest("[data-chat-id]");
    if (button) await loadMessages(button.dataset.chatId || "");
  });
  $("#chatForm").addEventListener("submit", async (event) => {
    event.preventDefault(); if (!currentConversation) return;
    const input = event.currentTarget.elements.body; const body = String(input.value || "").trim(); if (!body) return;
    const submit = event.currentTarget.querySelector("button"); submit.disabled = true;
    try { await request(`/auth/chats/${encodeURIComponent(currentConversation)}/messages`, {method:"POST",body:JSON.stringify({body})}); input.value = ""; await loadChats(currentConversation); }
    catch (error) { message($("#chatMessage"), error.message, true); } finally { submit.disabled = false; }
  });

  $("#loginForm").addEventListener("submit", async (event) => {
    event.preventDefault(); const form = new FormData(event.currentTarget); const submit = event.currentTarget.querySelector('[type=submit]'); submit.disabled = true;
    try { const data = await request("/auth/login", {method:"POST",body:JSON.stringify(Object.fromEntries(form))}); token = data.access_token; user = data.user; localStorage.setItem(tokenKey, token); updateAccount(); closeAuth(); await completePending(); }
    catch (error) { message($("#authMessage"), error.message, true); } finally { submit.disabled = false; }
  });
  $("#registerForm").addEventListener("submit", async (event) => {
    event.preventDefault(); const form = new FormData(event.currentTarget); const submit = event.currentTarget.querySelector('[type=submit]'); submit.disabled = true;
    try { const data = await request("/auth/register", {method:"POST",body:JSON.stringify(Object.fromEntries(form))}); token = data.access_token; user = data.user; localStorage.setItem(tokenKey, token); updateAccount(); closeAuth(); toast("Cuenta creada. Ya puedes publicar y chatear."); await completePending(); }
    catch (error) { message($("#authMessage"), error.message, true); } finally { submit.disabled = false; }
  });
  $("#profileForm").addEventListener("submit", async (event) => {
    event.preventDefault(); const submit = event.currentTarget.querySelector('[type=submit]'); submit.disabled = true;
    try { const data = await request("/auth/profile", {method:"PATCH",body:JSON.stringify(Object.fromEntries(new FormData(event.currentTarget)))}); user = data.user; updateAccount(); message($("#accountMessage"), "Perfil actualizado."); }
    catch (error) { message($("#accountMessage"), error.message, true); } finally { submit.disabled = false; }
  });
  $("#logoutButton").addEventListener("click", () => { token = ""; user = null; localStorage.removeItem(tokenKey); updateAccount(); closeAccount(); toast("Sesión cerrada."); });

  $("#publicationImages").addEventListener("change", (event) => {
    const files = Array.from(event.target.files || []);
    if (files.length > 5) { event.target.value = ""; $("#imagePreview").innerHTML = ""; return message($("#publishMessage"), "Puedes cargar máximo cinco fotos.", true); }
    if (files.some((file) => file.size > 5 * 1024 * 1024)) { event.target.value = ""; return message($("#publishMessage"), "Cada foto debe pesar máximo 5 MB.", true); }
    $("#imagePreview").innerHTML = files.map((file) => `<img src="${URL.createObjectURL(file)}" alt="Vista previa">`).join("");
    message($("#publishMessage"), files.length ? `${files.length} foto(s) lista(s).` : "");
  });
  $("#publicationVideo").addEventListener("change", (event) => {
    const file = event.target.files?.[0]; const status = $("#videoStatus"); videoReady = true; $("#videoDuration").value = "0";
    if (!file) { status.textContent = "Sin video seleccionado"; status.className = "market-video-status"; return; }
    if (file.size > 25 * 1024 * 1024) { videoReady = false; event.target.value = ""; status.textContent = "El video supera 25 MB."; status.className = "market-video-status error"; return; }
    const probe = document.createElement("video"); probe.preload = "metadata"; probe.src = URL.createObjectURL(file);
    probe.onloadedmetadata = () => { URL.revokeObjectURL(probe.src); const duration = Number(probe.duration || 0); $("#videoDuration").value = duration.toFixed(2); videoReady = duration > 0 && duration <= 30.2; status.textContent = videoReady ? `${file.name} · ${Math.ceil(duration)} segundos` : "El video debe durar máximo 30 segundos."; status.className = `market-video-status ${videoReady ? "ok" : "error"}`; if (!videoReady) event.target.value = ""; };
    probe.onerror = () => { videoReady = false; event.target.value = ""; status.textContent = "No pudimos leer este video."; status.className = "market-video-status error"; };
  });
  $("#publishForm").addEventListener("submit", async (event) => {
    event.preventDefault(); if (!user) return openAuth("publish");
    if (!videoReady) return message($("#publishMessage"), "Revisa el video antes de publicar.", true);
    const submit = event.currentTarget.querySelector('[type=submit]'); submit.disabled = true; submit.textContent = "Publicando...";
    try {
      const data = await request("/publications", {method:"POST",body:new FormData(event.currentTarget)});
      event.currentTarget.reset(); $("#imagePreview").innerHTML = ""; $("#videoStatus").textContent = "Sin video seleccionado";
      await loadPublications(); toast("Artículo publicado. Ya está visible en la app."); openCatalog(data.publication?.id || "");
    } catch (error) { message($("#publishMessage"), error.message, true); }
    finally { submit.disabled = false; submit.textContent = "Publicar ahora"; }
  });

  document.addEventListener("keydown", (event) => { if (event.key === "Escape") { closeAuth(); closeAccount(); closeChat(); } });
  Promise.all([loadConfig(), restoreSession(), loadPublications()]).then(() => {
    if (location.hash === "#publicar" && user) openPublish();
  });
})();
