// Menu kit shared by the mesero and caja panels (waiter_ordering): the SAME
// category grid, product grid, product sheet (fraction buttons only for
// products that allow portions, whole-unit selector otherwise, cooking
// term, quick notes, observations) and cart-line math. Moved out of
// hsp_waiter.js so the caja reuses it instead of duplicating it. Exposed as
// window.CxMenuKit; both panels load this file before their own script.
(() => {
  "use strict";

  const TERM_STOPS = ["Crudo", "Medio", "3/4", "Bien cocinado"];

  // ---------------------------------------------------------------------
  // Emoji por categoria / producto (switch menu_emojis). Tabla de
  // correspondencia: la primera palabra del nombre (sin tildes, singular o
  // plural) contra estas palabras. Para ampliar, agrega una fila. Una foto
  // subida en Admin V2 siempre reemplaza al emoji.
  // ---------------------------------------------------------------------
  const MENU_EMOJIS = [
    [["pollo", "alita", "ala", "pechuga", "muslo", "broaster"], "🍗"],
    [["carne", "res", "churrasco", "costilla", "asado", "lomo", "punta", "sobrebarriga", "bife", "filete", "chuleta", "parrilla", "parrillada", "picada", "chuzo"], "🥩"],
    [["cerdo", "lechona", "tocino", "chicharron", "panceta", "bondiola"], "🥓"],
    [["hamburguesa", "burger"], "🍔"],
    [["perro", "hotdog", "salchicha", "chorizo", "salchipapa"], "🌭"],
    [["papa", "francesa", "yuca", "patacon", "platano", "maduro"], "🍟"],
    [["arepa"], "🫓"],
    [["empanada"], "🥟"],
    [["arroz", "paella"], "🍚"],
    [["sopa", "caldo", "sancocho", "consome", "crema", "ajiaco", "mondongo"], "🍲"],
    [["pescado", "mojarra", "trucha", "tilapia", "bagre", "salmon", "robalo", "marisco", "camaron"], "🐟"],
    [["ensalada", "verdura"], "🥗"],
    [["pizza"], "🍕"],
    [["taco", "burrito", "quesadilla"], "🌮"],
    [["sandwich", "sanduche", "emparedado"], "🥪"],
    [["huevo", "desayuno", "calentado"], "🍳"],
    [["pan", "pandebono", "almojabana", "bunuelo"], "🥖"],
    [["postre", "torta", "pastel", "tres", "brownie", "flan", "cheesecake", "gelatina"], "🍰"],
    [["helado", "malteada", "sundae"], "🍨"],
    [["cerveza", "pola", "michelada", "aguila", "poker", "club", "corona", "costena", "costenita"], "🍺"],
    [["vino", "sangria"], "🍷"],
    [["aguardiente", "ron", "whisky", "tequila", "vodka", "licor", "coctel", "shot", "trago"], "🥃"],
    [["cafe", "tinto", "capuchino", "aromatica", "te", "chocolate"], "☕"],
    [["gaseosa", "bebida", "refresco", "soda", "jugo", "limonada", "agua", "cola", "coca", "pepsi", "postobon", "colombiana", "sprite", "hit", "natural"], "🥤"],
  ];
  const DEFAULT_MENU_EMOJI = "🍽️";
  // Carta de bar (pantalla QR con qr_bar_menu): iconos más específicos para
  // lo que vende un bar. Solo se consulta con { bar: true }, antes de la
  // tabla general, así el panel mesero de las otras empresas no cambia.
  const BAR_MENU_EMOJIS = [
    [["aguardiente", "antioqueno", "nectar", "blanco"], "🍶"],
    [["ron", "medellin", "caldas", "bacardi", "whisky", "whiskey", "buchanans", "chivas", "old", "tequila", "brandy"], "🥃"],
    [["vodka", "ginebra", "gin", "martini"], "🍸"],
    [["coctel", "coctail", "mojito", "margarita", "pina", "daiquiri", "cuba"], "🍹"],
    [["champana", "champagne", "espumoso"], "🍾"],
    [["agua", "hielo"], "💧"],
    [["energizante", "redbull", "vive", "monster", "speed"], "⚡"],
    [["jugo", "limonada", "natural"], "🧃"],
    [["cigarrillo", "cigarro", "cigarrillos", "tabaco", "marlboro", "lucky", "boston", "belmont", "pielroja", "vape", "vaper"], "🚬"],
    [["snack", "snacks", "pasaboca", "pasabocas", "mani", "papita", "papitas", "chito", "chitos", "dorito", "doritos", "tostacos", "detodito", "crispeta", "crispetas"], "🍿"],
    [["dulce", "dulces", "chicle", "chicles", "confite", "confites", "chocolatina", "bombon"], "🍬"],
  ];

  // .replace(/x/g) instead of .replaceAll: replaceAll throws on the older
  // Android WebViews some phones still run.
  function h(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  function money(value) {
    const number = Number(value || 0);
    try {
      return new Intl.NumberFormat("es-CO", { style: "currency", currency: "COP", maximumFractionDigits: 0 }).format(number);
    } catch (_) {
      return `$${Math.round(number).toLocaleString("es-CO")}`;
    }
  }

  function menuEmoji(text, opts = {}) {
    const first = String(text || "")
      .normalize("NFD")
      .replace(/[̀-ͯ]/g, "")
      .toLowerCase()
      .replace(/[^a-z0-9ñ\s]/g, " ")
      .trim()
      .split(/\s+/)[0] || "";
    if (!first) return DEFAULT_MENU_EMOJI;
    const candidates = [first, first.replace(/es$/, ""), first.replace(/s$/, "")];
    const tables = opts.bar ? [...BAR_MENU_EMOJIS, ...MENU_EMOJIS] : MENU_EMOJIS;
    for (const [words, emoji] of tables) {
      if (candidates.some((word) => words.includes(word))) return emoji;
    }
    return DEFAULT_MENU_EMOJI;
  }

  // Photo (Admin V2) > emoji (switch on) > nothing, like before the switch.
  function tileArt(kind, item, opts = {}) {
    const companyId = opts.companyId || "";
    if (item.has_image) {
      const path = kind === "category"
        ? `categories/${encodeURIComponent(item.key)}/image`
        : `products/${encodeURIComponent(item.image_item_id || item.id)}/image`;
      return { type: "image", url: `/api/v1/companies/${encodeURIComponent(companyId)}/waiter-ordering/${path}` };
    }
    if (opts.emojis) return { type: "emoji", emoji: menuEmoji(kind === "category" ? item.label || item.key : item.name, opts) };
    return kind === "category" ? { type: "emoji", emoji: DEFAULT_MENU_EMOJI } : { type: "none" };
  }

  // Table labels already come as "Mesa 11" from the QR tables; only a bare
  // number gets the word added -- never "Mesa Mesa 11".
  function tableTitle(label) {
    const clean = String(label ?? "").trim();
    if (!clean) return "Mesa";
    return /^mesa\b/i.test(clean) ? clean : `Mesa ${clean}`;
  }

  // "1/4" -> 0.25, "2" -> 2, "Medio" -> 0.5, "Familiar" -> null. Twin of
  // waiter_ordering._portion_label_fraction on the server.
  function portionFraction(label) {
    const words = { entero: "1", entera: "1", completo: "1", completa: "1", unidad: "1", medio: "1/2", media: "1/2", mitad: "1/2", cuarto: "1/4" };
    const first = String(label || "").trim().toLowerCase().split(/\s+/)[0] || "";
    const raw = (words[first] || first).replace(",", ".");
    if (!raw) return null;
    let value;
    if (raw.includes("/")) {
      const [num, den] = raw.split("/");
      value = Number(num) / Number(den);
    } else {
      value = Number(raw);
    }
    return Number.isFinite(value) && value > 0 ? value : null;
  }

  // Buttons shown in the sheet: the configured fractions (price and
  // availability straight from the server's menu preview), plus -- for an
  // Admin V2 portion group -- any portion that isn't one of those fractions
  // (e.g. "Familiar"), so nothing configured becomes unreachable.
  function quantityChoices(product) {
    const choices = (product.quantity_options || []).map((option) => ({
      label: option.label,
      price: option.price,
      available: option.available !== false && option.price !== null && option.price !== undefined,
      fraction: option.label,
      inventory_item_id: product.quantity_ref_id || product.id,
    }));
    if (product.is_portioned) {
      const buttonValues = choices.map((c) => portionFraction(c.label));
      (product.portions || []).forEach((portion) => {
        const value = portionFraction(portion.label);
        if (value !== null && buttonValues.some((v) => v !== null && Math.abs(v - value) < 1e-9)) return;
        choices.push({
          label: portion.label,
          price: portion.price,
          available: true,
          fraction: "",
          inventory_item_id: portion.inventory_item_id,
        });
      });
    }
    return choices;
  }

  function defaultChoiceIndex(choices, prefill) {
    if (prefill) {
      const same = choices.findIndex((c) => c.available && c.label === (prefill.fraction || prefill.portion_label));
      if (same >= 0) return same;
    }
    const whole = choices.findIndex((c) => c.available && portionFraction(c.label) === 1);
    if (whole >= 0) return whole;
    return choices.findIndex((c) => c.available);
  }

  function choiceCartLine(product, choice, common) {
    return {
      inventory_item_id: choice.inventory_item_id,
      menu_product_id: product.id,
      name: product.name,
      unit_price: Number(choice.price || 0),
      quantity: 1,
      fraction: choice.fraction || "",
      quantity_label: choice.label,
      portion_label: choice.fraction ? "" : choice.label,
      ...common,
    };
  }

  // Whole units only, 1..99 (a product without portions is never sold as a
  // fraction; the server rejects it too).
  function stepQuantity(current, delta) {
    const value = Math.round(Number(current) || 1) + Number(delta || 0);
    return Math.max(1, Math.min(99, value));
  }

  function orderItemPayload(item) {
    const payload = {
      inventory_item_id: item.inventory_item_id,
      quantity: item.quantity,
      observations: item.observations,
      quick_notes: item.quick_notes,
      term: item.term || "",
    };
    // The server re-resolves item + price from the fraction; the price the
    // user saw is only a preview of that same calculation.
    if (item.fraction) payload.fraction = item.fraction;
    return payload;
  }

  function cartTotal(lines) {
    return (lines || []).reduce((sum, item) => sum + Number(item.unit_price || 0) * Number(item.quantity || 0), 0);
  }

  function cartLineLabel(item) {
    if (item.quantity_label) return `${h(item.quantity_label)} · ${h(item.name)}`;
    return `${h(item.quantity)} x ${h(item.name)}`;
  }

  function findMenuProduct(menu, productId) {
    for (const category of menu || []) {
      const product = (category.products || []).find((item) => item.id === productId);
      if (product) return { product, category };
    }
    return null;
  }

  // ---------------------------------------------------------------------
  // Grids. `attr` is the data-* attribute each panel's click handler reads
  // (data-wtr-cat / data-csh-cat...), so both panels keep their own routing.
  // ---------------------------------------------------------------------
  function categoryGridHtml(menu, opts = {}) {
    const attr = opts.attr || "data-wtr-cat";
    return `
      <div class="wtr-grid-cat">
        ${(menu || []).map((cat) => {
          const art = tileArt("category", cat, opts);
          return `
            <button class="wtr-cat-tile" type="button" ${attr}="${h(cat.key)}">
              ${art.type === "image"
                ? `<div class="wtr-cat-img" style="background-image:url('${art.url}')"></div>`
                : `<div class="wtr-cat-img wtr-emoji">${art.emoji}</div>`}
              <span>${h(cat.label)}</span>
            </button>`;
        }).join("") || `<div class="wtr-empty">Sin categorías todavía.</div>`}
      </div>`;
  }

  function productGridHtml(products, opts = {}) {
    const attr = opts.attr || "data-wtr-product";
    return `
      <div class="wtr-grid-prod">
        ${(products || []).map((product) => {
          const art = tileArt("product", product, opts);
          return `
            <button class="wtr-prod-tile" type="button" ${attr}="${h(product.id)}">
              ${art.type === "image" ? `<div class="wtr-prod-img" style="background-image:url('${art.url}')"></div>` : ""}
              ${art.type === "emoji" ? `<div class="wtr-prod-emoji">${art.emoji}</div>` : ""}
              <span>${h(product.name)}</span>
              ${product.is_portioned
                ? `<strong>Elegir porción</strong>`
                : `<strong>${h(money(product.price))}</strong>`}
            </button>`;
        }).join("") || `<div class="wtr-empty">Sin productos en esta categoría.</div>`}
      </div>`;
  }

  // How a tap on a product opens: the fraction sheet (quantity buttons on
  // and the product allows portions), the Admin V2 portion list, or the
  // plain product sheet.
  function productOpenMode(product, quantityButtons) {
    if ((quantityButtons || []).length && Array.isArray(product.quantity_options)) return "sheet";
    if (product.is_portioned) return "portions";
    return "sheet";
  }

  // ---------------------------------------------------------------------
  // Sheets
  // ---------------------------------------------------------------------
  function openPortionSheet(group, onPick) {
    const sheet = document.createElement("div");
    sheet.className = "wtr-sheet-backdrop";
    sheet.innerHTML = `
      <div class="wtr-sheet">
        <h2>${h(group.name)}</h2>
        <div class="wtr-portion-grid">
          ${(group.portions || []).map((portion, i) => `
            <button type="button" class="wtr-portion-btn" data-portion-index="${i}">
              <span>${h(portion.label)}</span>
              <strong>${h(money(portion.price))}</strong>
            </button>`).join("")}
        </div>
        <div class="wtr-sheet-actions">
          <button type="button" class="wtr-btn" data-sheet-cancel>Cancelar</button>
        </div>
      </div>`;
    document.body.appendChild(sheet);
    sheet.querySelector("[data-sheet-cancel]").addEventListener("click", () => sheet.remove());
    sheet.querySelectorAll("[data-portion-index]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const portion = group.portions[Number(btn.getAttribute("data-portion-index"))];
        sheet.remove();
        onPick({ id: portion.inventory_item_id, name: `${group.name} ${portion.label}`, price: portion.price }, portion.label);
      });
    });
    return sheet;
  }

  // opts: { product, category, portionLabel, prefill, quantityButtons,
  //         addLabel, onAdd(line) }
  function openItemSheet(opts) {
    const { product, category, portionLabel, prefill } = opts;
    const quantityButtons = opts.quantityButtons || [];
    const requiresTerm = Boolean(category && category.requires_term);
    const quickOptions = (category && category.quick_notes) || [];
    const initialTermIndex = requiresTerm && prefill && prefill.term
      ? Math.max(0, TERM_STOPS.indexOf(prefill.term))
      : 0;
    const choices = quantityButtons.length && Array.isArray(product.quantity_options) ? quantityChoices(product) : null;
    let choiceIndex = choices ? defaultChoiceIndex(choices, prefill) : -1;
    // Products sold by the unit (no "Permite porciones": carne, gaseosa...)
    // get a simple 1, 2, 3 selector with the price, never fractions.
    const unitStepper = !choices && quantityButtons.length > 0;
    let stepQty = stepQuantity(prefill ? Number(prefill.quantity || 1) : 1, 0);

    const sheet = document.createElement("div");
    sheet.className = "wtr-sheet-backdrop";
    sheet.innerHTML = `
      <div class="wtr-sheet">
        <h2>${h(product.name)}</h2>
        ${choices ? `
          <div class="wtr-qty-block">
            <span class="wtr-term-caption">Cantidad</span>
            <div class="wtr-qty-grid">
              ${choices.map((choice, i) => `
                <button type="button" class="wtr-qty-btn ${i === choiceIndex ? "is-active" : ""}" data-qty-index="${i}" ${choice.available ? "" : "disabled"}>
                  <span>${h(choice.label)}</span>
                  <strong>${choice.available ? h(money(choice.price)) : "Sin precio"}</strong>
                </button>`).join("")}
            </div>
            <div class="wtr-qty-preview">Vas a cobrar <strong id="wtrQtyPrice">${choiceIndex >= 0 ? h(money(choices[choiceIndex].price)) : "—"}</strong></div>
          </div>` : `
        ${unitStepper ? `
          <div class="wtr-qty-block">
            <span class="wtr-term-caption">Cantidad</span>
            <div class="wtr-stepper">
              <button type="button" class="wtr-step-btn" data-qty-step="-1" aria-label="Menos">−</button>
              <strong id="wtrStepQty">${stepQty}</strong>
              <button type="button" class="wtr-step-btn" data-qty-step="1" aria-label="Más">+</button>
            </div>
            <div class="wtr-qty-preview">Vas a cobrar <strong id="wtrQtyPrice">${h(money(Number(product.price || 0) * stepQty))}</strong></div>
          </div>` : `
        <label>Cantidad<input id="wtrSheetQty" type="number" min="1" step="1" value="${prefill ? Number(prefill.quantity || 1) : 1}" /></label>`}`}
        ${requiresTerm ? `
          <div class="wtr-term-block">
            <span class="wtr-term-caption">Término de cocción</span>
            <input id="wtrSheetTerm" type="range" min="0" max="${TERM_STOPS.length - 1}" step="1" value="${initialTermIndex}" />
            <div class="wtr-term-labels" id="wtrTermLabels">
              ${TERM_STOPS.map((t, i) => `<span class="${i === initialTermIndex ? "is-active" : ""}" data-term-label="${i}">${h(t)}</span>`).join("")}
            </div>
          </div>` : ""}
        ${quickOptions.length ? `
          <div class="wtr-quick-notes">
            ${quickOptions.map((note, i) => `<button type="button" class="wtr-quick-note ${prefill && (prefill.quick_notes || []).includes(note) ? "is-active" : ""}" data-note-index="${i}">${h(note)}</button>`).join("")}
          </div>` : ""}
        <label>Observaciones<textarea id="wtrSheetObs" rows="2" placeholder="Ej: sin sal, bien asado...">${h(prefill ? prefill.observations || "" : "")}</textarea></label>
        <div class="wtr-sheet-actions">
          <button type="button" class="wtr-btn" data-sheet-cancel>Cancelar</button>
          <button type="button" class="wtr-btn wtr-btn-primary" data-sheet-add>${prefill ? "Guardar cambios" : h(opts.addLabel || "Agregar al pedido")}</button>
        </div>
      </div>`;
    document.body.appendChild(sheet);

    const selectedNotes = new Set(prefill ? prefill.quick_notes || [] : []);
    sheet.querySelectorAll("[data-note-index]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const idx = Number(btn.getAttribute("data-note-index"));
        const note = quickOptions[idx];
        if (selectedNotes.has(note)) { selectedNotes.delete(note); btn.classList.remove("is-active"); }
        else { selectedNotes.add(note); btn.classList.add("is-active"); }
      });
    });

    const termInput = sheet.querySelector("#wtrSheetTerm");
    if (termInput) {
      termInput.addEventListener("input", () => {
        const idx = Number(termInput.value);
        sheet.querySelectorAll("[data-term-label]").forEach((el) => {
          el.classList.toggle("is-active", Number(el.getAttribute("data-term-label")) === idx);
        });
      });
    }

    const addButton = sheet.querySelector("[data-sheet-add]");
    if (unitStepper) {
      sheet.querySelectorAll("[data-qty-step]").forEach((btn) => {
        btn.addEventListener("click", () => {
          stepQty = stepQuantity(stepQty, Number(btn.getAttribute("data-qty-step")));
          sheet.querySelector("#wtrStepQty").textContent = String(stepQty);
          sheet.querySelector("#wtrQtyPrice").textContent = money(Number(product.price || 0) * stepQty);
        });
      });
    }
    if (choices) {
      addButton.disabled = choiceIndex < 0;
      sheet.querySelectorAll("[data-qty-index]").forEach((btn) => {
        btn.addEventListener("click", () => {
          if (btn.disabled) return;
          choiceIndex = Number(btn.getAttribute("data-qty-index"));
          sheet.querySelectorAll("[data-qty-index]").forEach((el) => el.classList.toggle("is-active", el === btn));
          sheet.querySelector("#wtrQtyPrice").textContent = money(choices[choiceIndex].price);
          addButton.disabled = false;
        });
      });
    }

    sheet.querySelector("[data-sheet-cancel]").addEventListener("click", () => sheet.remove());
    addButton.addEventListener("click", () => {
      const obs = String(sheet.querySelector("#wtrSheetObs").value || "");
      const term = requiresTerm ? TERM_STOPS[Number(sheet.querySelector("#wtrSheetTerm").value || 0)] : "";
      const common = { term, observations: obs, quick_notes: Array.from(selectedNotes) };
      if (choices) {
        if (choiceIndex < 0) return;
        sheet.remove();
        opts.onAdd(choiceCartLine(product, choices[choiceIndex], common));
        return;
      }
      const qty = unitStepper
        ? stepQty
        : stepQuantity(Number(sheet.querySelector("#wtrSheetQty").value || 1), 0);
      sheet.remove();
      opts.onAdd({
        inventory_item_id: product.id,
        menu_product_id: opts.menuProductId || undefined,
        name: product.name,
        unit_price: product.price,
        quantity: qty,
        portion_label: portionLabel || "",
        ...common,
      });
    });
    return sheet;
  }

  // ---------------------------------------------------------------------
  // Styles of the shared pieces (injected once per page).
  // ---------------------------------------------------------------------
  const STYLES = `
    .wtr-btn{min-height:52px;border-radius:16px;border:1px solid rgba(255,255,255,.14);background:rgba(255,255,255,.06);color:#fff;font-size:16px;font-weight:900;cursor:pointer}
    .wtr-btn-primary{border:none;background:linear-gradient(135deg,#ff7a18,#ff2d95 55%,#a855f7);width:100%}
    .wtr-btn-primary:disabled{opacity:.6}
    .wtr-empty{padding:20px;color:#8f8aa8;text-align:center}
    .wtr-grid-cat{display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:14px;padding:16px}
    .wtr-cat-tile{display:grid;gap:8px;border-radius:20px;border:1px solid rgba(255,255,255,.14);background:rgba(255,255,255,.05);color:#fff;padding:0 0 12px;overflow:hidden;cursor:pointer}
    .wtr-cat-img{height:100px;display:grid;place-items:center;font-size:34px;background-size:cover;background-position:center;background-color:rgba(255,255,255,.06)}
    .wtr-cat-tile span{font-size:15px;font-weight:900}
    .wtr-grid-prod{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:12px;padding:16px}
    .wtr-prod-tile{min-height:76px;display:grid;gap:6px;align-content:center;border-radius:18px;border:1px solid rgba(255,255,255,.14);background:rgba(255,255,255,.05);color:#fff;padding:12px;text-align:left;overflow:hidden;cursor:pointer}
    .wtr-prod-img{height:70px;margin:-12px -12px 4px;background-size:cover;background-position:center}
    .wtr-cat-img.wtr-emoji{font-size:56px;line-height:1}
    .wtr-prod-emoji{font-size:40px;line-height:1}
    .wtr-prod-tile strong{color:#ffd166}
    .wtr-sheet-backdrop{position:fixed;inset:0;background:rgba(0,0,0,.6);display:grid;align-items:end;z-index:60}
    .wtr-sheet{background:#120e20;color:#f5f3ff;border-radius:24px 24px 0 0;padding:22px;display:grid;gap:14px;max-height:90vh;overflow:auto;width:100%;max-width:720px;margin:0 auto}
    .wtr-sheet h2{margin:0}
    .wtr-sheet label{display:grid;gap:6px;font-size:13px;font-weight:800;color:#c9c3e6}
    .wtr-sheet input,.wtr-sheet textarea{padding:12px;border-radius:12px;border:1px solid rgba(255,255,255,.16);background:rgba(3,7,18,.6);color:#fff;font:inherit}
    .wtr-sheet-status{color:#fecaca;font-size:13px;font-weight:800;min-height:16px}
    .wtr-quick-notes{display:flex;flex-wrap:wrap;gap:8px}
    .wtr-quick-note{padding:8px 12px;border-radius:999px;border:1px solid rgba(255,255,255,.18);background:rgba(255,255,255,.05);color:#fff;font-size:12px;font-weight:800}
    .wtr-quick-note.is-active{background:linear-gradient(135deg,#ff7a18,#ff2d95);border-color:transparent}
    .wtr-term-block{display:grid;gap:8px}
    .wtr-term-caption{font-size:13px;font-weight:800;color:#c9c3e6}
    .wtr-term-block input[type=range]{width:100%}
    .wtr-term-labels{display:flex;justify-content:space-between;font-size:11px;color:#8f8aa8;font-weight:800}
    .wtr-term-labels span.is-active{color:#ffd166}
    .wtr-sheet-actions{display:flex;gap:10px}
    .wtr-sheet-actions .wtr-btn{flex:1}
    .wtr-portion-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(120px,1fr));gap:10px}
    .wtr-portion-btn{display:grid;gap:4px;padding:14px;border-radius:16px;border:1px solid rgba(255,255,255,.16);background:rgba(255,255,255,.05);color:#fff;font-weight:900}
    .wtr-portion-btn strong{color:#ffd166}
    .wtr-qty-block{display:grid;gap:8px}
    .wtr-qty-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(88px,1fr));gap:8px}
    .wtr-qty-btn{display:grid;gap:4px;justify-items:center;padding:12px 6px;border-radius:16px;border:1px solid rgba(255,255,255,.16);background:rgba(255,255,255,.05);color:#fff;font-weight:900;cursor:pointer}
    .wtr-qty-btn span{font-size:20px}
    .wtr-qty-btn strong{font-size:12px;color:#ffd166}
    .wtr-qty-btn.is-active{background:linear-gradient(135deg,#ff7a18,#ff2d95);border-color:transparent}
    .wtr-qty-btn.is-active strong{color:#fff}
    .wtr-qty-btn:disabled{opacity:.35;cursor:not-allowed}
    .wtr-stepper{display:flex;align-items:center;justify-content:center;gap:18px}
    .wtr-step-btn{width:56px;height:56px;border-radius:16px;border:1px solid rgba(255,255,255,.16);background:rgba(255,255,255,.06);color:#fff;font-size:28px;font-weight:900;cursor:pointer}
    .wtr-stepper strong{min-width:48px;text-align:center;font-size:30px;font-weight:1000}
    .wtr-qty-preview{display:flex;justify-content:space-between;align-items:center;padding:10px 12px;border-radius:12px;background:rgba(255,209,102,.1);font-size:13px;font-weight:800;color:#c9c3e6}
    .wtr-qty-preview strong{font-size:20px;color:#ffd166}
  `;

  function injectStyles() {
    if (document.getElementById("cxMenuKitStyles")) return;
    const style = document.createElement("style");
    style.id = "cxMenuKitStyles";
    style.textContent = STYLES;
    document.head.appendChild(style);
  }

  window.CxMenuKit = {
    TERM_STOPS,
    MENU_EMOJIS,
    BAR_MENU_EMOJIS,
    DEFAULT_MENU_EMOJI,
    h,
    money,
    menuEmoji,
    tileArt,
    tableTitle,
    portionFraction,
    quantityChoices,
    defaultChoiceIndex,
    choiceCartLine,
    stepQuantity,
    orderItemPayload,
    cartTotal,
    cartLineLabel,
    findMenuProduct,
    categoryGridHtml,
    productGridHtml,
    productOpenMode,
    openPortionSheet,
    openItemSheet,
    injectStyles,
  };
})();
