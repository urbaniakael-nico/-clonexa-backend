// Entrada a la Consola v2+: apenas abre pide la huella (si este acceso tiene
// huellas registradas y el navegador lo permite); "Entrar con clave" queda
// siempre como alternativa. Cualquiera de las dos abre la misma sesión.
(() => {
  "use strict";

  const body = document.body;
  const W = window.CxWebAuthn;
  const box = document.querySelector("[data-vp-passkey-box]");
  const form = document.querySelector("[data-vp-password-form]");
  const status = document.querySelector("[data-vp-passkey-status]");
  const errorBox = document.querySelector("[data-vp-login-error]");
  const usePasskey = document.querySelector("[data-vp-use-passkey]");
  const noPasskeyHint = document.querySelector("[data-vp-no-passkey]");
  const hasPasskeys = body.getAttribute("data-has-passkeys") === "true";
  const canPasskey = hasPasskeys && W && W.supported();
  let busy = false;

  function showError(message) {
    if (!errorBox) return;
    errorBox.textContent = message || "";
    errorBox.hidden = !message;
  }

  function mode(which) {
    const passkey = which === "passkey" && canPasskey;
    if (box) box.hidden = !passkey;
    if (form) form.hidden = passkey;
    if (usePasskey) usePasskey.hidden = !canPasskey;
    if (noPasskeyHint) noPasskeyHint.hidden = hasPasskeys;
    if (!passkey) {
      const email = document.getElementById("email");
      if (email && typeof email.focus === "function") email.focus();
    }
  }

  async function post(url, payload) {
    const response = await fetch(url, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(payload || {}),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || "No se pudo entrar con la huella.");
    return data;
  }

  async function passkeyLogin() {
    if (busy || !canPasskey) return;
    busy = true;
    showError("");
    if (status) status.textContent = "Esperando tu huella…";
    try {
      const start = await post("/admin-v2plus/api/passkey/login/options");
      const credential = await navigator.credentials.get({ publicKey: W.requestOptions(start.options) });
      const done = await post("/admin-v2plus/api/passkey/login/verify", { credential: W.credentialJson(credential) });
      if (status) status.textContent = "Listo. Entrando…";
      window.location.href = done.redirect || "/admin-v2plus";
    } catch (error) {
      showError(error && error.name ? W.friendlyError(error) : (error && error.message) || "No se pudo entrar con la huella.");
      if (status) status.textContent = "Puedes volver a intentarlo o entrar con tu clave.";
    } finally {
      busy = false;
    }
  }

  document.addEventListener("click", (event) => {
    const target = event.target;
    if (!target || !target.closest) return;
    if (target.closest("[data-vp-passkey-start]")) passkeyLogin();
    else if (target.closest("[data-vp-use-password]")) mode("password");
    else if (target.closest("[data-vp-use-passkey]")) { mode("passkey"); passkeyLogin(); }
  });

  // Con un error de clave, se queda en el formulario de clave.
  const hadError = errorBox && !errorBox.hidden && String(errorBox.textContent || "").trim();
  if (canPasskey && !hadError) {
    mode("passkey");
    passkeyLogin();
  } else {
    mode("password");
  }

  window.CxConsoleLogin = { passkeyLogin, mode, canPasskey };
})();
