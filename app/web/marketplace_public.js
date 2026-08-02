(() => {
  "use strict";

  const params = new URLSearchParams(location.search);
  const companyId = String(params.get("company_id") || "").trim();
  const selectedPublication = String(params.get("publication") || "").trim();
  const selectedProfile = String(params.get("profile") || "").trim();
  const apiBase = `/api/v1/marketplace/companies/${encodeURIComponent(companyId)}`;
  const tokenKey = `clonexa_marketplace_token:${companyId}`;
  let token = localStorage.getItem(tokenKey) || "";
  let user = null;
  let pendingAction = "";
  let publications = [];
  let currentConversation = "";
  let videoReady = true;
  let activeCategory = "todos";
  let editingPublicationId = "";
  let currentProfileId = "";
  let myPublications = [];
  const categoryDefs = [
    ["tecnologia", "Tecnología", ["tecnologia","celular","telefono","iphone","android","tablet","ipad","portatil","laptop","computador","pc","monitor","televisor","audifono","parlante","camara","playstation","play 4","play 5","ps4","ps5","xbox","nintendo","switch","consola"]],
    ["juegos_consola", "Juegos de consola", ["videojuego","juego ps","juego xbox","juego nintendo","fifa","ea fc","eafc","gta","call of duty","mario","pokemon","zelda","fortnite","minecraft"]],
    ["accesorios", "Accesorios", ["accesorio","bolso","cartera","gafas","collar","pulsera","anillo","cinturon","maletin","mochila"]],
    ["gorras", "Gorras", ["gorra","cachucha","sombrero","visera"]],
    ["tenis", "Tenis", ["tenis","sneaker","zapatilla","zapato","calzado","botas"]],
    ["ropa", "Ropa", ["ropa","camisa","camiseta","pantalon","jean","vestido","chaqueta","hoodie","buzo","falda","short"]],
    ["herramientas", "Herramientas", ["herramienta","taladro","martillo","destornillador","llave inglesa","pulidora","sierra","multimetro"]],
    ["relojes", "Relojes", ["reloj","smartwatch","watch","cronografo"]],
    ["artesanias", "Artesanías", ["artesania","hecho a mano","tejido","macrame","ceramica","manualidad"]],
    ["otros", "Otros", []],
  ];
  const categoryLabels = Object.fromEntries(categoryDefs.map(([key, label]) => [key, label]));
  const companyField = document.querySelector("#publishCompanyId");
  if (companyField) companyField.value = companyId;

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));
  const h = (value) => String(value ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#039;");
  const money = (value) => new Intl.NumberFormat("es-CO", {style:"currency",currency:"COP",maximumFractionDigits:0}).format(Number(value || 0));
  const normalizedWords = (value) => String(value || "").toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/\s+/g, " ");
  function suggestCategory(...values) {
    const content = normalizedWords(values.join(" "));
    const tokens = new Set(content.split(" "));
    let best = "otros"; let bestScore = 0;
    categoryDefs.forEach(([key, , keywords]) => {
      const score = keywords.reduce((total, keyword) => total + ((keyword.length > 3 ? content.includes(keyword) : tokens.has(keyword)) ? (keyword.includes(" ") ? 2 : 1) : 0), 0);
      if (score > bestScore) { best = key; bestScore = score; }
    });
    return best;
  }
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
    no_puedes_chatear_contigo:"Esta publicación es tuya. Los mensajes de interesados aparecerán en Mis chats.", chat_no_encontrado:"No encontramos esta conversación.",
    perfil_no_encontrado:"No encontramos este perfil.", no_puedes_calificarte:"No puedes calificar tu propio perfil.", publicacion_no_encontrada:"No encontramos esta publicación o no te pertenece.", categoria_invalida:"Selecciona una categoría válida."
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
    $("#profileForm [name=bio]").value = user.bio || "";
  }

  function setPublishMode(item = null) {
    const form = $("#publishForm");
    editingPublicationId = item?.id || "";
    form.elements.title.value = item?.title || "";
    form.elements.price.value = item?.price || "";
    form.elements.offer_mode.value = item?.offer_mode || "both";
    form.elements.category.value = item?.category || "auto";
    form.elements.description.value = item?.description || "";
    form.elements.specifications.value = item?.specifications || "";
    $("#publicationImages").required = !editingPublicationId;
    $("#publicationImages").closest("label").hidden = !!editingPublicationId;
    $("#publicationVideo").closest("label").hidden = !!editingPublicationId;
    $("#imagePreview").hidden = !!editingPublicationId;
    $("#videoStatus").hidden = !!editingPublicationId;
    $("#publishEyebrow").textContent = editingPublicationId ? "Editar publicación" : "Nueva publicación";
    $("#publishTitle").textContent = editingPublicationId ? "Actualiza tu artículo." : "Muéstralo como se merece.";
    $("#publishCopy").textContent = editingPublicationId ? "Las fotos actuales se conservan; aquí puedes cambiar la información, precio y categoría." : "Completa la información y el artículo aparecerá inmediatamente en la app.";
    $("#cancelEditPublication").hidden = !editingPublicationId;
    form.querySelector('[type="submit"]').textContent = editingPublicationId ? "Guardar cambios" : "Publicar ahora";
    updateCategoryHint();
  }

  function openPublish(item = null) {
    setPublishMode(item);
    $(".market-hero").hidden = true;
    $("#articulos").hidden = true;
    $("#profileView").hidden = true;
    $("#publicar").hidden = false;
    history.replaceState(null, "", `${location.pathname}?company_id=${encodeURIComponent(companyId)}#publicar`);
    window.scrollTo({top:0,behavior:"smooth"});
  }
  function openCatalog(publicationId = "") {
    $(".market-hero").hidden = false;
    $("#articulos").hidden = false;
    $("#profileView").hidden = true;
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
    if (action.startsWith("review:")) return openProfile(action.slice(7));
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

  function renderCategoryChips() {
    const counts = publications.reduce((result, item) => { const key = item.category || "otros"; result[key] = (result[key] || 0) + 1; return result; }, {});
    $("#marketCategoryChips").innerHTML = `<button class="${activeCategory === "todos" ? "active" : ""}" data-market-category="todos" type="button">Todos <small>${publications.length}</small></button>${categoryDefs.map(([key, label]) => `<button class="${activeCategory === key ? "active" : ""}" data-market-category="${h(key)}" type="button">${h(label)} <small>${counts[key] || 0}</small></button>`).join("")}`;
  }

  function publicationCard(item) {
    const image = item.image_urls?.[0] || "";
    const mode = item.offer_mode === "money" ? "Solo venta" : item.offer_mode === "change" ? "Solo cambio" : "Venta o cambio";
    return `<article class="market-product" data-publication-card="${h(item.id)}">
      <div class="market-product-media">${image ? `<img src="${h(image)}" alt="${h(item.title)}" loading="lazy">` : ""}<span class="market-product-badge">${h(mode)}</span></div>
      <div class="market-product-body"><span class="market-product-category">${h(item.category_label || categoryLabels[item.category] || "Otros")}</span><button class="market-product-user" data-profile-user="${h(item.seller?.id || "")}" type="button">@${h(item.seller?.username || "usuario")}</button><h3>${h(item.title)}</h3>
      <p class="market-product-copy">${h(item.description || item.specifications || "Artículo disponible")}</p><strong class="market-product-price">${money(item.price)}</strong>
      <div class="market-product-actions"><button class="market-btn primary" data-chat-publication="${h(item.id)}" type="button">Chat</button><button class="market-btn ghost" data-copy-publication="${h(item.id)}" type="button">Compartir</button></div></div>
    </article>`;
  }

  function renderPublications() {
    const query = String($("#marketSearch")?.value || "").trim().toLowerCase();
    const visible = publications.filter((item) => (activeCategory === "todos" || (item.category || "otros") === activeCategory) && `${item.title} ${item.description} ${item.specifications} ${item.category_label || ""}`.toLowerCase().includes(query));
    const grid = $("#marketProductGrid");
    renderCategoryChips();
    const keys = activeCategory === "todos" ? categoryDefs.map(([key]) => key) : [activeCategory];
    grid.innerHTML = keys.map((key) => {
      const items = visible.filter((item) => (item.category || "otros") === key);
      if (!items.length) return "";
      return `<section class="market-category-section" data-category-section="${h(key)}"><div class="market-category-head"><div><span class="market-eyebrow">Categoría</span><h3>${h(categoryLabels[key] || "Otros")}</h3></div><span>${items.length} artículo${items.length === 1 ? "" : "s"}</span></div><div class="market-product-grid">${items.map(publicationCard).join("")}</div></section>`;
    }).join("");
    $("#marketEmpty").hidden = publications.length > 0;
    if (publications.length && !visible.length) {
      grid.innerHTML = '<div class="market-empty"><h3>Sin coincidencias</h3><p>Prueba con otra palabra o categoría.</p></div>';
    }
    if (selectedPublication) setTimeout(() => document.querySelector(`[data-publication-card="${CSS.escape(selectedPublication)}"]`)?.scrollIntoView({behavior:"smooth",block:"center"}), 120);
  }

  async function loadPublications() {
    if (!companyId) return;
    try { const data = await request("/publications"); publications = data.publications || []; renderPublications(); }
    catch (error) { message($("#publishMessage"), error.message, true); }
  }

  async function loadMyPublications() {
    if (!user) { myPublications = []; $("#myPublicationsList").innerHTML = ""; return; }
    const data = await request("/auth/publications");
    myPublications = data.publications || [];
    $("#myPublicationsList").innerHTML = myPublications.length ? myPublications.map((item) => `<article><div><strong>${h(item.title)}</strong><small>${h(item.category_label || "Otros")} · ${money(item.price)}</small></div><button class="market-btn ghost" data-edit-publication="${h(item.id)}" type="button">Editar</button></article>`).join("") : '<small>Aún no tienes publicaciones.</small>';
  }

  async function openProfile(profileUserId) {
    if (!profileUserId) return;
    currentProfileId = profileUserId;
    closeAccount();
    $(".market-hero").hidden = true;
    $("#articulos").hidden = true;
    $("#publicar").hidden = true;
    $("#profileView").hidden = false;
    history.replaceState(null, "", `${location.pathname}?company_id=${encodeURIComponent(companyId)}&profile=${encodeURIComponent(profileUserId)}#perfil`);
    window.scrollTo({top:0,behavior:"smooth"});
    try {
      const data = await request(`/profiles/${encodeURIComponent(profileUserId)}`);
      const profile = data.profile || {};
      $("#publicProfileAvatar").textContent = (profile.username || "V").charAt(0).toUpperCase();
      $("#publicProfileName").textContent = profile.username || "Usuario";
      $("#publicProfileBio").textContent = profile.bio || "Miembro de la comunidad de cambios y compras.";
      $("#publicProfileRating").textContent = profile.review_count ? `${Number(profile.rating || 0).toFixed(1)} ★` : "Nuevo";
      $("#publicProfileReviewCount").textContent = profile.review_count ? `${profile.review_count} calificación${profile.review_count === 1 ? "" : "es"}` : "Sin calificaciones todavía";
      $("#publicProfilePublicationCount").textContent = `${(data.publications || []).length} artículo${(data.publications || []).length === 1 ? "" : "s"}`;
      $("#publicProfilePublications").innerHTML = (data.publications || []).length ? data.publications.map(publicationCard).join("") : '<div class="market-empty"><h3>Sin publicaciones activas</h3><p>Este usuario todavía no tiene artículos visibles.</p></div>';
      $("#publicProfileReviews").innerHTML = (data.reviews || []).length ? data.reviews.map((review) => `<article><div><button data-profile-user="${h(review.reviewer_user_id)}" type="button">@${h(review.reviewer_username)}</button><span>${"★".repeat(Number(review.rating || 0))}${"☆".repeat(5 - Number(review.rating || 0))}</span></div><p>${h(review.comment)}</p></article>`).join("") : '<div class="market-review-empty">Aún no hay comentarios. Sé la primera persona en calificar.</div>';
      $("#reviewForm").hidden = String(user?.id || "") === String(profileUserId);
      $("#shareProfileButton").dataset.profileUrl = profile.public_url || location.href;
      document.title = `${profile.username || "Perfil"} · Cambios y compras`;
    } catch (error) {
      $("#publicProfilePublications").innerHTML = `<div class="market-empty"><h3>Perfil no disponible</h3><p>${h(error.message)}</p></div>`;
    }
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
  $("#backFromProfile").addEventListener("click", () => openCatalog());
  $("#marketSearch").addEventListener("input", renderPublications);
  $("#marketCategoryChips").addEventListener("click", (event) => {
    const button = event.target.closest("[data-market-category]");
    if (!button) return;
    activeCategory = button.dataset.marketCategory || "todos";
    renderPublications();
  });
  function updateCategoryHint() {
    const form = $("#publishForm");
    const selected = $("#publicationCategory").value;
    const suggested = suggestCategory(form.elements.title.value, form.elements.description.value, form.elements.specifications.value);
    $("#categoryHint").textContent = selected === "auto" ? `Sugerencia inteligente: ${categoryLabels[suggested]}. Puedes cambiarla si lo prefieres.` : `Se guardará en ${categoryLabels[selected] || "Otros"}.`;
  }
  ["title", "description", "specifications"].forEach((name) => $("#publishForm").elements[name].addEventListener("input", updateCategoryHint));
  $("#publicationCategory").addEventListener("change", updateCategoryHint);
  $("#marketProductGrid").addEventListener("click", async (event) => {
    const profile = event.target.closest("[data-profile-user]");
    if (profile) return openProfile(profile.dataset.profileUser || "");
    const chat = event.target.closest("[data-chat-publication]");
    if (chat) return openChatForPublication(chat.dataset.chatPublication || "");
    const copy = event.target.closest("[data-copy-publication]");
    if (copy) {
      const url = `${location.origin}${location.pathname}?company_id=${encodeURIComponent(companyId)}&publication=${encodeURIComponent(copy.dataset.copyPublication || "")}`;
      try { await navigator.clipboard.writeText(url); toast("Enlace de la publicación copiado."); } catch { toast(url); }
    }
  });
  $("#publicProfilePublications").addEventListener("click", async (event) => {
    const profile = event.target.closest("[data-profile-user]");
    if (profile) return openProfile(profile.dataset.profileUser || "");
    const chat = event.target.closest("[data-chat-publication]");
    if (chat) return openChatForPublication(chat.dataset.chatPublication || "");
    const copy = event.target.closest("[data-copy-publication]");
    if (copy) {
      const url = `${location.origin}${location.pathname}?company_id=${encodeURIComponent(companyId)}&publication=${encodeURIComponent(copy.dataset.copyPublication || "")}`;
      try { await navigator.clipboard.writeText(url); toast("Enlace de la publicación copiado."); } catch { toast(url); }
    }
  });
  $("#publicProfileReviews").addEventListener("click", (event) => {
    const profile = event.target.closest("[data-profile-user]");
    if (profile) openProfile(profile.dataset.profileUser || "");
  });
  $("#accountButton").addEventListener("click", () => {
    if (!user) return openAuth();
    updateAccount(); $("#accountModal").hidden = false; document.body.style.overflow = "hidden";
    loadMyPublications().catch((error) => message($("#accountMessage"), error.message, true));
  });
  $("#openPublicProfileButton").addEventListener("click", () => user && openProfile(user.id));
  $("#myPublicationsList").addEventListener("click", (event) => {
    const button = event.target.closest("[data-edit-publication]");
    if (!button) return;
    const item = myPublications.find((publication) => String(publication.id) === String(button.dataset.editPublication));
    if (item) { closeAccount(); openPublish(item); }
  });
  $("#cancelEditPublication").addEventListener("click", () => { setPublishMode(); openCatalog(); });
  $("#shareProfileButton").addEventListener("click", async (event) => {
    const url = event.currentTarget.dataset.profileUrl || location.href;
    try { await navigator.clipboard.writeText(url); toast("Enlace del perfil copiado."); } catch { toast(url); }
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
  $("#reviewForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!user) return openAuth(`review:${currentProfileId}`);
    const formElement = event.currentTarget;
    const submit = formElement.querySelector('[type="submit"]'); submit.disabled = true;
    try {
      await request(`/profiles/${encodeURIComponent(currentProfileId)}/reviews`, {method:"POST",body:JSON.stringify(Object.fromEntries(new FormData(formElement)))});
      formElement.reset(); toast("Tu calificación quedó publicada."); await openProfile(currentProfileId);
    } catch (error) { message($("#reviewMessage"), error.message, true); }
    finally { submit.disabled = false; }
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
    const formElement = event.currentTarget;
    const submit = formElement.querySelector('[type=submit]'); submit.disabled = true; submit.textContent = "Publicando...";
    try {
      const formData = new FormData(formElement);
      const wasEditing = editingPublicationId;
      const data = wasEditing
        ? await request(`/publications/${encodeURIComponent(wasEditing)}`, {method:"PATCH",body:JSON.stringify({title:formData.get("title"),price:Number(formData.get("price") || 0),offer_mode:formData.get("offer_mode"),category:formData.get("category"),description:formData.get("description"),specifications:formData.get("specifications")})})
        : await request("/publications", {method:"POST",body:formData});
      formElement.reset(); $("#imagePreview").innerHTML = ""; $("#videoStatus").textContent = "Sin video seleccionado";
      setPublishMode(); await loadPublications(); toast(wasEditing ? "Publicación actualizada." : "Artículo publicado. Ya está visible en la app."); openCatalog(data.publication?.id || "");
    } catch (error) { message($("#publishMessage"), error.message, true); }
    finally { submit.disabled = false; submit.textContent = editingPublicationId ? "Guardar cambios" : "Publicar ahora"; }
  });

  document.addEventListener("keydown", (event) => { if (event.key === "Escape") { closeAuth(); closeAccount(); closeChat(); } });
  Promise.all([loadConfig(), restoreSession(), loadPublications()]).then(() => {
    if (selectedProfile) openProfile(selectedProfile);
    else if (location.hash === "#publicar" && user) openPublish();
  });
})();
