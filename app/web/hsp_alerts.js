// Alerts shared by the cocina, caja and mesero panels (waiter_ordering):
// a distinct sound per kind of alert, vibration where the device allows it,
// and an on-screen card that stays until the person closes it.
//
// Browsers block audio until the user interacts with the page, so the audio
// is unlocked on the first tap/key anywhere (a small banner asks for that
// tap while it is still locked). Each panel has its own mute button, stored
// per panel in localStorage. Sounds are synthesized with Web Audio: no
// files to download or store.
(() => {
  "use strict";

  // Distinct melody per alert kind: [frequency Hz, duration s] notes.
  const SOUNDS = {
    new_order: [[660, 0.14], [880, 0.14], [660, 0.14], [880, 0.24]],  // cocina: pedido nuevo
    ready: [[988, 0.12], [1319, 0.12], [1568, 0.28]],                // mesero: pedido listo
    new_sale: [[523, 0.16], [784, 0.32]],                             // caja: venta nueva
    to_charge: [[880, 0.16], [659, 0.16], [523, 0.34]],               // caja: lista para cobrar
  };
  const VIBRATION = {
    new_order: [300, 120, 300],
    ready: [200, 100, 200, 100, 200],
    new_sale: [250],
    to_charge: [150, 80, 150],
  };

  function h(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  // Ids that appeared since the previous poll. `previous` null = first load:
  // everything already on screen is known, nothing is announced.
  function newIds(previous, currentIds) {
    if (!previous) return [];
    return currentIds.filter((id) => !previous.has(id));
  }

  function create(panel) {
    const muteKey = `clonexa_alerts_muted_${panel}`;
    let audioCtx = null;
    let unlocked = false;
    let alertSeq = 0;

    function storeGet(key) {
      try { return window.localStorage.getItem(key); } catch (_) { return null; }
    }

    function storeSet(key, value) {
      try { window.localStorage.setItem(key, value); } catch (_) {}
    }

    function isMuted() {
      return storeGet(muteKey) === "1";
    }

    function ensureContext() {
      if (audioCtx) return audioCtx;
      const Ctor = window.AudioContext || window.webkitAudioContext;
      if (!Ctor) return null;
      try { audioCtx = new Ctor(); } catch (_) { audioCtx = null; }
      return audioCtx;
    }

    function unlock() {
      const ctx = ensureContext();
      if (ctx && ctx.state === "suspended" && ctx.resume) ctx.resume().catch(() => {});
      unlocked = true;
      renderControls();
    }

    function playNotes(kind) {
      const ctx = ensureContext();
      const notes = SOUNDS[kind] || SOUNDS.new_order;
      if (!ctx || !unlocked) return false;
      let at = ctx.currentTime + 0.02;
      notes.forEach(([freq, duration]) => {
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.type = "sine";
        osc.frequency.value = freq;
        gain.gain.setValueAtTime(0.0001, at);
        gain.gain.exponentialRampToValueAtTime(0.35, at + 0.02);
        gain.gain.exponentialRampToValueAtTime(0.0001, at + duration);
        osc.connect(gain);
        gain.connect(ctx.destination);
        osc.start(at);
        osc.stop(at + duration + 0.02);
        at += duration + 0.05;
      });
      return true;
    }

    function stackEl() {
      let el = document.getElementById("cxAlertStack");
      if (!el) {
        el = document.createElement("div");
        el.id = "cxAlertStack";
        el.className = "cx-alert-stack";
        el.setAttribute("role", "alertdialog");
        document.body.appendChild(el);
      }
      return el;
    }

    // Sound + vibration + a card that stays until closed. Returns the card.
    function notify({ kind, title, message, onClose }) {
      const muted = isMuted();
      if (!muted) {
        playNotes(kind);
        try { if (navigator.vibrate) navigator.vibrate(VIBRATION[kind] || [200]); } catch (_) {}
      }
      alertSeq += 1;
      const card = document.createElement("div");
      card.className = `cx-alert cx-alert-${kind}`;
      card.setAttribute("data-cx-alert", String(alertSeq));
      card.innerHTML = `
        <div class="cx-alert-text">
          <strong>${h(title)}</strong>
          ${message ? `<span>${h(message)}</span>` : ""}
        </div>
        <button type="button" class="cx-alert-close" data-cx-alert-close>Entendido</button>`;
      const close = () => {
        card.remove();
        if (typeof onClose === "function") onClose();
      };
      const closeBtn = card.querySelector("[data-cx-alert-close]");
      if (closeBtn) closeBtn.addEventListener("click", close);
      card.closeAlert = close;
      stackEl().appendChild(card);
      return card;
    }

    function renderControls() {
      let bar = document.getElementById("cxAlertControls");
      if (!bar) {
        bar = document.createElement("div");
        bar.id = "cxAlertControls";
        bar.className = "cx-alert-controls";
        document.body.appendChild(bar);
      }
      const muted = isMuted();
      bar.innerHTML = `
        ${!unlocked && !muted ? `<span class="cx-alert-unlock">🔈 Toca la pantalla para activar el sonido de los avisos</span>` : ""}
        <button type="button" class="cx-alert-mute" data-cx-alert-mute aria-pressed="${muted ? "true" : "false"}" title="${muted ? "Activar sonido" : "Silenciar avisos"}">${muted ? "🔕 Silenciado" : "🔔 Sonido"}</button>`;
    }

    function toggleMute() {
      storeSet(muteKey, isMuted() ? "0" : "1");
      renderControls();
    }

    function install() {
      injectStyles();
      const first = () => {
        unlock();
        document.removeEventListener("pointerdown", first, true);
        document.removeEventListener("keydown", first, true);
        document.removeEventListener("touchstart", first, true);
      };
      document.addEventListener("pointerdown", first, true);
      document.addEventListener("keydown", first, true);
      document.addEventListener("touchstart", first, true);
      document.addEventListener("click", (event) => {
        const target = event.target;
        if (target && target.closest && target.closest("[data-cx-alert-mute]")) toggleMute();
      });
      renderControls();
    }

    return {
      install,
      notify,
      isMuted,
      toggleMute,
      unlock,
      isUnlocked: () => unlocked,
      sounds: SOUNDS,
    };
  }

  const STYLES = `
    .cx-alert-stack{position:fixed;top:12px;left:50%;transform:translateX(-50%);width:min(560px,calc(100% - 24px));z-index:90;display:grid;gap:10px}
    .cx-alert{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:16px 18px;border-radius:18px;color:#fff;box-shadow:0 18px 40px rgba(0,0,0,.5);animation:cxAlertIn .18s ease-out;border:2px solid rgba(255,255,255,.25)}
    @keyframes cxAlertIn{from{transform:translateY(-10px);opacity:0}to{transform:none;opacity:1}}
    .cx-alert-new_order{background:#1d4ed8}
    .cx-alert-ready{background:#15803d}
    .cx-alert-new_sale{background:#7c3aed}
    .cx-alert-to_charge{background:#b45309}
    .cx-alert-text{display:grid;gap:2px}
    .cx-alert-text strong{font-size:19px;font-weight:1000}
    .cx-alert-text span{font-size:14px;font-weight:700;opacity:.92}
    .cx-alert-close{min-height:44px;padding:0 16px;border-radius:12px;border:none;background:rgba(0,0,0,.28);color:#fff;font-weight:900;font-size:15px;cursor:pointer;flex:none}
    .cx-alert-controls{position:fixed;right:12px;bottom:84px;z-index:55;display:flex;align-items:center;gap:8px;flex-wrap:wrap;justify-content:flex-end;max-width:calc(100% - 24px)}
    .cx-alert-mute{min-height:38px;padding:0 12px;border-radius:999px;border:1px solid rgba(255,255,255,.18);background:rgba(10,8,20,.85);color:#fff;font-weight:900;font-size:13px;cursor:pointer}
    .cx-alert-unlock{padding:8px 12px;border-radius:999px;background:rgba(245,158,11,.9);color:#1a1206;font-size:12px;font-weight:900}
  `;

  function injectStyles() {
    if (document.getElementById("cxAlertStyles")) return;
    const style = document.createElement("style");
    style.id = "cxAlertStyles";
    style.textContent = STYLES;
    document.head.appendChild(style);
  }

  window.CxAlerts = { create, newIds, SOUNDS, VIBRATION };
})();
