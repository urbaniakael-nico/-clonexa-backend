(() => {
  "use strict";
  const form = document.getElementById("loginForm");
  const msg = document.getElementById("loginMessage");
  const email = document.getElementById("email");
  const password = document.getElementById("password");
  const TOKEN_KEY = "clonexa_access_token";

  function setMessage(value, ok=false){
    msg.textContent = value || "";
    msg.style.color = ok ? "#00ff88" : "#fca5a5";
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    setMessage("Validando credenciales...", true);
    try {
      const response = await fetch("/api/v1/auth/login", {
        method: "POST",
        headers: {"Content-Type":"application/json"},
        body: JSON.stringify({email: email.value.trim(), password: password.value})
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || "Credenciales invÃ¡lidas");
      localStorage.setItem(TOKEN_KEY, data.access_token);
      setMessage("Acceso concedido. Redirigiendo...", true);
      const companyId =
        data.company_id ||
        data.companyId ||
        data.company?.id ||
        data.company?.company_id ||
        data.user?.company_id ||
        data.user?.companyId ||
        data.company_user?.company_id ||
        data.company_user?.companyId ||
        data.account?.company_id ||
        data.account?.companyId ||
        "";

      if (!companyId) {
        throw new Error("Login correcto, pero la API no devolvió company_id para abrir el panel cliente.");
      }

      localStorage.setItem("clonexa_company_id", companyId);
      localStorage.setItem("company_id", companyId);
      localStorage.setItem("clonexa_login_payload", JSON.stringify(data));

      window.location.href = `/client?company_id=${encodeURIComponent(companyId)}`;
    } catch (error) {
      setMessage(error.message || "No fue posible iniciar sesiÃ³n");
    }
  });
})();



/* CLONEXA 020A-1 LOGIN SESSION MESSAGE */
(function clonexaLoginSessionMessage() {
  "use strict";

  function showReason() {
    const reason = localStorage.getItem("clonexa_logout_reason");
    if (!reason) return;

    localStorage.removeItem("clonexa_logout_reason");

    const msg = document.getElementById("loginMessage");
    if (msg) {
      msg.textContent = reason;
      msg.classList.add("error");
      return;
    }

    const box = document.createElement("div");
    box.textContent = reason;
    box.style.cssText = "margin:12px auto;padding:10px 14px;border-radius:12px;background:#fff7ed;color:#9a3412;max-width:520px;font-family:system-ui;";
    document.body.prepend(box);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", showReason);
  } else {
    showReason();
  }
})();
