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
      if (!response.ok) throw new Error(data.detail || "Credenciales inválidas");
      localStorage.setItem(TOKEN_KEY, data.access_token);
      setMessage("Acceso concedido. Redirigiendo...", true);
      window.location.href = "/client";
    } catch (error) {
      setMessage(error.message || "No fue posible iniciar sesión");
    }
  });
})();
