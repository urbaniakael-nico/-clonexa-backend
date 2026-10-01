// Conversión entre el JSON del servidor (base64url) y las llaves de acceso
// del navegador (WebAuthn). La usan la entrada con huella y el registro de
// la huella en la Consola v2+. La huella nunca sale del equipo.
(() => {
  "use strict";

  function toBuffer(value) {
    const base64 = String(value || "").replace(/-/g, "+").replace(/_/g, "/");
    const padded = base64 + "===".slice((base64.length + 3) % 4);
    const bytes = atob(padded);
    const out = new Uint8Array(bytes.length);
    for (let i = 0; i < bytes.length; i += 1) out[i] = bytes.charCodeAt(i);
    return out.buffer;
  }

  function toBase64url(buffer) {
    const bytes = new Uint8Array(buffer);
    let text = "";
    for (let i = 0; i < bytes.length; i += 1) text += String.fromCharCode(bytes[i]);
    return btoa(text).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  }

  function creationOptions(json) {
    return {
      ...json,
      challenge: toBuffer(json.challenge),
      user: { ...json.user, id: toBuffer(json.user.id) },
      excludeCredentials: (json.excludeCredentials || []).map((c) => ({ ...c, id: toBuffer(c.id) })),
    };
  }

  function requestOptions(json) {
    return {
      ...json,
      challenge: toBuffer(json.challenge),
      allowCredentials: (json.allowCredentials || []).map((c) => ({ ...c, id: toBuffer(c.id) })),
    };
  }

  function credentialJson(credential) {
    const r = credential.response;
    const response = { clientDataJSON: toBase64url(r.clientDataJSON) };
    if (r.attestationObject) {
      response.attestationObject = toBase64url(r.attestationObject);
      if (typeof r.getTransports === "function") response.transports = r.getTransports();
    }
    if (r.authenticatorData) response.authenticatorData = toBase64url(r.authenticatorData);
    if (r.signature) response.signature = toBase64url(r.signature);
    if (r.userHandle) response.userHandle = toBase64url(r.userHandle);
    return {
      id: credential.id,
      rawId: toBase64url(credential.rawId),
      type: credential.type,
      response,
      clientExtensionResults: typeof credential.getClientExtensionResults === "function" ? credential.getClientExtensionResults() : {},
      authenticatorAttachment: credential.authenticatorAttachment || null,
    };
  }

  function supported() {
    return typeof window !== "undefined" && Boolean(window.PublicKeyCredential && navigator.credentials);
  }

  function friendlyError(error) {
    const name = error && error.name;
    if (name === "NotAllowedError") return "Se canceló o se agotó el tiempo. Vuelve a intentarlo o entra con tu clave.";
    if (name === "InvalidStateError") return "Este equipo ya tiene la huella registrada.";
    if (name === "SecurityError") return "La huella solo funciona en el dominio seguro de la consola (https).";
    return (error && error.message) || "No se pudo usar la huella.";
  }

  window.CxWebAuthn = { toBuffer, toBase64url, creationOptions, requestOptions, credentialJson, supported, friendlyError };
})();
