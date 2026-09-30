// 049W: selector de cantidad libre, EL MISMO en los cuatro sitios donde se
// toma un pedido (mesero, caja, link de domicilios y QR de mesa). Solo con el
// interruptor quantity_picker del modulo waiter_ordering.
//
//   [ − ] [ 6 ] [ ＋ ]   [1/8] [1/4] [1/2] [3/4]
//   Vas a cobrar $273.000 · 6 1/2
//
// El entero se escribe o se sube con + y −; la fraccion (opcional) se suma al
// entero. Las fracciones solo salen en productos que se venden por porciones;
// los demas solo tienen el entero. El total es precio x cantidad (6,5 veces).
(() => {
  "use strict";

  const FRACTIONS = [["1/8", 0.125], ["1/4", 0.25], ["1/2", 0.5], ["3/4", 0.75]];
  const MAX_WHOLE = 99;

  function esc(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  function pesos(value) {
    return `$${Math.round(Number(value) || 0).toLocaleString("es-CO")}`;
  }

  function fractionValue(label) {
    const found = FRACTIONS.find(([l]) => l === label);
    return found ? found[1] : 0;
  }

  function clampWhole(value) {
    const n = Math.floor(Number(String(value ?? "").replace(/[^0-9]/g, "")) || 0);
    return Math.max(0, Math.min(MAX_WHOLE, n));
  }

  // 6.5 -> { whole: 6, fraction: "1/2" }; una parte que no es de la lista se redondea al entero.
  function split(quantity) {
    const q = Math.max(0, Number(quantity) || 0);
    const whole = Math.floor(q + 1e-9);
    const rest = q - whole;
    const found = FRACTIONS.find(([, v]) => Math.abs(v - rest) < 1e-6);
    return { whole: Math.min(MAX_WHOLE, whole), fraction: found ? found[0] : "" };
  }

  function quantityOf(whole, fraction) {
    return clampWhole(whole) + fractionValue(fraction);
  }

  // "6 1/2", "1/2", "3"
  function label(quantity) {
    const { whole, fraction } = split(quantity);
    if (!fraction) return String(whole);
    return whole ? `${whole} ${fraction}` : fraction;
  }

  function totalText(price, quantity, verb) {
    if (!(quantity > 0)) return "Elige la cantidad";
    return `${verb} ${pesos(Number(price || 0) * quantity)} · ${label(quantity)}`;
  }

  // opts: { price, portions, quantity, verb }
  function html(opts = {}) {
    const start = split(opts.quantity || 1);
    const verb = opts.verb || "Vas a cobrar";
    const q = quantityOf(start.whole, opts.portions ? start.fraction : "");
    return `
      <div class="cxq" data-cxq>
        <span class="cxq-caption">Cantidad</span>
        <div class="cxq-row">
          <div class="cxq-whole">
            <button type="button" class="cxq-step" data-cxq-step="-1" aria-label="Uno menos">−</button>
            <input class="cxq-input" data-cxq-whole type="text" inputmode="numeric" pattern="[0-9]*" autocomplete="off" aria-label="Cantidad entera" value="${esc(start.whole)}">
            <button type="button" class="cxq-step" data-cxq-step="1" aria-label="Uno más">＋</button>
          </div>
          ${opts.portions ? `
            <div class="cxq-fracs" role="group" aria-label="Fracción">
              ${FRACTIONS.map(([l]) => `<button type="button" class="cxq-frac ${l === start.fraction ? "is-on" : ""}" data-cxq-frac="${l}" aria-pressed="${l === start.fraction ? "true" : "false"}">＋${l}</button>`).join("")}
            </div>` : ""}
        </div>
        <p class="cxq-total" data-cxq-total aria-live="polite">${esc(totalText(opts.price, q, verb))}</p>
      </div>`;
  }

  // Conecta los botones dentro de `container`. Devuelve { quantity() }.
  function mount(container, opts = {}) {
    const found = container.querySelector ? container.querySelector("[data-cxq]") : null;
    const box = found && found.querySelector ? found : container;
    const one = (selector) => (box.querySelector ? box.querySelector(selector) : null);
    const input = one("[data-cxq-whole]");
    const totalNode = one("[data-cxq-total]");
    // Cada boton por su selector exacto (sirve igual en el navegador y en las pruebas).
    const steps = ["-1", "1"].map((d) => [d, one(`[data-cxq-step="${d}"]`)]).filter(([, b]) => b);
    const fracs = opts.portions ? FRACTIONS.map(([l]) => [l, one(`[data-cxq-frac="${l}"]`)]).filter(([, b]) => b) : [];
    const verb = opts.verb || "Vas a cobrar";
    const start = split(opts.quantity || 1);
    const state = { whole: start.whole, fraction: opts.portions ? start.fraction : "" };

    const current = () => quantityOf(state.whole, state.fraction);
    const paint = (fromTyping) => {
      if (!fromTyping && input) input.value = String(state.whole);
      if (totalNode) totalNode.textContent = totalText(opts.price, current(), verb);
      fracs.forEach(([l, btn]) => {
        const on = l === state.fraction;
        if (btn.classList) btn.classList.toggle("is-on", on);
        if (btn.setAttribute) btn.setAttribute("aria-pressed", on ? "true" : "false");
      });
      if (typeof opts.onChange === "function") opts.onChange(current());
    };

    steps.forEach(([delta, btn]) => {
      btn.addEventListener("click", () => {
        const next = clampWhole(state.whole + Number(delta));
        // sin fraccion nunca baja de 1; con fraccion puede quedar en 0 (1/2 sola)
        state.whole = state.fraction ? next : Math.max(1, next);
        paint(false);
      });
    });
    fracs.forEach(([pick, btn]) => {
      btn.addEventListener("click", () => {
        state.fraction = state.fraction === pick ? "" : pick;
        if (!state.fraction && state.whole < 1) state.whole = 1;
        paint(false);
      });
    });
    if (input) {
      input.addEventListener("input", () => {
        state.whole = clampWhole(input.value);
        paint(true);
      });
      input.addEventListener("blur", () => {
        if (!state.fraction && state.whole < 1) state.whole = 1;
        paint(false);
      });
    }
    paint(false);
    return { quantity: current, label: () => label(current()) };
  }

  const STYLES = `
    .cxq{display:grid;gap:10px}
    .cxq-caption{font-size:13px;font-weight:800;color:#c9c3e6}
    .cxq-row{display:flex;flex-wrap:wrap;align-items:center;gap:10px}
    .cxq-whole{display:flex;align-items:center;gap:6px}
    .cxq-step{width:52px;height:52px;border-radius:14px;border:1px solid rgba(255,255,255,.16);background:rgba(255,255,255,.06);color:#fff;font-size:24px;font-weight:900;cursor:pointer}
    .cxq-input{width:78px;height:52px;border-radius:14px;border:1px solid rgba(255,255,255,.16);background:rgba(3,7,18,.6);color:#fff;font:inherit;font-size:26px;font-weight:900;text-align:center}
    .cxq-fracs{display:flex;flex-wrap:wrap;gap:6px}
    .cxq-frac{min-width:58px;height:52px;padding:0 10px;border-radius:14px;border:1px solid rgba(255,255,255,.16);background:rgba(255,255,255,.05);color:#fff;font:inherit;font-size:16px;font-weight:900;cursor:pointer}
    .cxq-frac.is-on{border-color:transparent;background:linear-gradient(135deg,#ff7a18,#ff2d95);color:#fff}
    .cxq-total{margin:0;padding:10px 12px;border-radius:12px;background:rgba(255,209,102,.1);color:#ffd166;font-size:16px;font-weight:900}
  `;

  function injectStyles() {
    if (!document.head || (document.getElementById && document.getElementById("cxQtyStyles049W"))) return;
    const style = document.createElement("style");
    style.id = "cxQtyStyles049W";
    style.textContent = STYLES;
    document.head.appendChild(style);
  }

  window.CxQtyPicker = { FRACTIONS, split, quantityOf, label, totalText, html, mount, injectStyles, STYLES };
})();
