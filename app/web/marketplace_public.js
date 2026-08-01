(() => {
  "use strict";
  const params = new URLSearchParams(location.search);
  const companyId = String(params.get("company_id") || "").trim();
  const apiBase = `/api/v1/marketplace/companies/${encodeURIComponent(companyId)}`;
  const tokenKey = `clonexa_marketplace_token:${companyId}`;
  let token = localStorage.getItem(tokenKey) || "";
  let user = null;
  let pendingAction = "";
  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));
  const errors = {marketplace_no_disponible:"Este marketplace no está disponible.",telefono_invalido:"Revisa el número de teléfono.",telefono_ya_registrado:"Este teléfono ya tiene una cuenta.",telefono_no_registrado:"No encontramos una cuenta con este teléfono.",usuario_no_disponible:"Ese usuario ya está en uso.",codigo_vencido_o_inexistente:"El código venció o no existe. Solicita uno nuevo.",codigo_incorrecto:"El código no es correcto.",credenciales_invalidas:"Usuario, teléfono o contraseña incorrectos.",cuenta_temporalmente_bloqueada:"Cuenta bloqueada por 15 minutos. Intenta más tarde.",demasiados_codigos_solicitados:"Has solicitado varios códigos. Espera unos minutos.",espera_antes_de_solicitar_otro_codigo:"Espera 45 segundos antes de pedir otro código.",mensajeria_no_configurada:"La mensajería aún no está configurada.",no_se_pudo_enviar_el_mensaje:"No pudimos enviar el mensaje. Revisa el número e intenta de nuevo.",contrasena_actual_incorrecta:"La contraseña actual no coincide."};

  async function request(path, options = {}) {
    const headers = {"Content-Type":"application/json", ...(options.headers || {})};
    if (token) headers.Authorization = `Bearer ${token}`;
    const response = await fetch(`${apiBase}${path}`, {...options, headers});
    let payload = {};
    try { payload = await response.json(); } catch {}
    if (!response.ok) throw new Error(errors[payload.detail] || payload.detail || "No pudimos completar la solicitud.");
    return payload;
  }
  function message(element, value, error = false) { element.textContent = value || ""; element.classList.toggle("error", error); }
  function toast(value) { const el = $("#marketToast"); el.textContent = value; el.hidden = false; clearTimeout(toast.timer); toast.timer = setTimeout(() => { el.hidden = true; }, 4200); }
  function setTab(name) {
    $$('[data-auth-panel]').forEach((panel) => { panel.hidden = panel.dataset.authPanel !== name; });
    $$('[data-auth-tab]').forEach((button) => button.classList.toggle("active", button.dataset.authTab === name));
    $("#authTabs").hidden = name === "reset";
    message($("#authMessage"), "");
  }
  function openAuth(action = "") { pendingAction = action; setTab("login"); $("#authModal").hidden = false; document.body.style.overflow = "hidden"; setTimeout(() => $("#loginForm input")?.focus(), 20); }
  function closeAuth() { $("#authModal").hidden = true; document.body.style.overflow = ""; }
  function closeAccount() { $("#accountModal").hidden = true; document.body.style.overflow = ""; }
  function updateAccount() {
    $("#accountButton").textContent = user ? user.username : "Ingresar";
    if (!user) return;
    $("#profileName").textContent = user.username;
    $("#profilePhone").textContent = `${user.phone_masked} · verificado`;
    $("#profileAvatar").textContent = (user.username || "V").charAt(0).toUpperCase();
    $("#profileForm [name=username]").value = user.username || "";
  }
  function completePending() { const action = pendingAction; pendingAction = ""; if (action === "publish") toast("Tu cuenta está lista. En el siguiente módulo podrás cargar fotos, video y publicar el artículo."); else if (action === "offer") toast("Cuenta verificada. Ya puedes ofertar cuando haya artículos publicados."); }
  async function restoreSession() {
    if (!token) return updateAccount();
    try { const data = await request("/auth/me"); user = data.user; } catch { token = ""; user = null; localStorage.removeItem(tokenKey); }
    updateAccount();
  }
  async function loadConfig() {
    if (!companyId) { $("#marketEmpty").innerHTML = "<h3>Falta identificar la empresa</h3><p>Abre el enlace completo suministrado por la empresa.</p>"; return; }
    try {
      const data = await request("/public");
      const name = data.company?.name || "Marketplace";
      document.title = `${data.marketplace?.title || "Cambios y compras"} · ${name}`;
      $("#companyName").textContent = name;
      $("#registeredUsers").textContent = String(data.marketplace?.registered_users || 0);
    } catch (error) { $("#marketEmpty").innerHTML = `<h3>Marketplace no disponible</h3><p>${error.message}</p>`; }
  }
  $$('[data-auth-action]').forEach((button) => button.addEventListener("click", () => { const action = button.dataset.authAction || ""; if (!user) openAuth(action); else { pendingAction = action; completePending(); } }));
  $$('[data-close-modal]').forEach((button) => button.addEventListener("click", closeAuth));
  $$('[data-close-account]').forEach((button) => button.addEventListener("click", closeAccount));
  $$('[data-auth-tab]').forEach((button) => button.addEventListener("click", () => setTab(button.dataset.authTab)));
  $("#accountButton").addEventListener("click", () => { if (!user) return openAuth(); updateAccount(); $("#accountModal").hidden = false; document.body.style.overflow = "hidden"; });
  $$('[data-send-code]').forEach((button) => button.addEventListener("click", async () => {
    const purpose = button.dataset.sendCode;
    const form = purpose === "reset" ? $("#resetForm") : $("#registerForm");
    const phone = new FormData(form).get("phone");
    if (!phone) return message($("#authMessage"), "Escribe primero tu teléfono.", true);
    button.disabled = true; button.textContent = "Enviando...";
    try { const data = await request("/auth/verification/request", {method:"POST",body:JSON.stringify({phone,purpose})}); message($("#authMessage"), `Código enviado a ${data.phone_masked}.`); let seconds = 45; const timer = setInterval(() => { seconds -= 1; button.textContent = seconds > 0 ? `Reenviar en ${seconds}s` : "Enviar código"; if (seconds <= 0) { clearInterval(timer); button.disabled = false; } }, 1000); } catch (error) { message($("#authMessage"), error.message, true); button.disabled = false; button.textContent = "Enviar código"; }
  }));
  $("#loginForm").addEventListener("submit", async (event) => { event.preventDefault(); const form = new FormData(event.currentTarget); const submit = event.currentTarget.querySelector('[type=submit]'); submit.disabled = true; try { const data = await request("/auth/login", {method:"POST",body:JSON.stringify(Object.fromEntries(form))}); token = data.access_token; user = data.user; localStorage.setItem(tokenKey, token); updateAccount(); closeAuth(); completePending(); } catch (error) { message($("#authMessage"), error.message, true); } finally { submit.disabled = false; } });
  $("#registerForm").addEventListener("submit", async (event) => { event.preventDefault(); const form = new FormData(event.currentTarget); const submit = event.currentTarget.querySelector('[type=submit]'); submit.disabled = true; try { const data = await request("/auth/register", {method:"POST",body:JSON.stringify(Object.fromEntries(form))}); token = data.access_token; user = data.user; localStorage.setItem(tokenKey, token); updateAccount(); closeAuth(); toast("Cuenta creada y teléfono verificado."); completePending(); } catch (error) { message($("#authMessage"), error.message, true); } finally { submit.disabled = false; } });
  $("#resetForm").addEventListener("submit", async (event) => { event.preventDefault(); const submit = event.currentTarget.querySelector('[type=submit]'); submit.disabled = true; try { await request("/auth/password-reset", {method:"POST",body:JSON.stringify(Object.fromEntries(new FormData(event.currentTarget)))}); setTab("login"); message($("#authMessage"), "Contraseña actualizada. Ya puedes ingresar."); } catch (error) { message($("#authMessage"), error.message, true); } finally { submit.disabled = false; } });
  $("#profileForm").addEventListener("submit", async (event) => { event.preventDefault(); const submit = event.currentTarget.querySelector('[type=submit]'); submit.disabled = true; try { const data = await request("/auth/profile", {method:"PATCH",body:JSON.stringify(Object.fromEntries(new FormData(event.currentTarget)))}); user = data.user; updateAccount(); message($("#accountMessage"), "Perfil actualizado."); } catch (error) { message($("#accountMessage"), error.message, true); } finally { submit.disabled = false; } });
  $("#logoutButton").addEventListener("click", () => { token = ""; user = null; localStorage.removeItem(tokenKey); updateAccount(); closeAccount(); toast("Sesión cerrada."); });
  document.addEventListener("keydown", (event) => { if (event.key === "Escape") { closeAuth(); closeAccount(); } });
  loadConfig(); restoreSession();
})();
