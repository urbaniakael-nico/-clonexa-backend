// Printable "CUENTA DE COBRO" shared by the caja panel (Imprimir cuenta) and
// the portal's document configuration (preview). It only renders what the
// server built (sale_document.build_sale_document): title, "NO ES FACTURA
// DE VENTA", numbers and totals all come from the server, so the preview and
// the printed document can't drift apart. 80 mm wide, ready for the future
// thermal printer phase; today it opens the browser's print dialog.
(() => {
  "use strict";

  function h(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  function pesos(value) {
    const n = Math.round(Number(value || 0));
    try {
      return `$${n.toLocaleString("es-CO")}`;
    } catch (_) {
      return `$${n}`;
    }
  }

  function dateLabel(iso) {
    const date = new Date(iso || "");
    if (Number.isNaN(date.getTime())) return "";
    try {
      return date.toLocaleString("es-CO", { timeZone: "America/Bogota", dateStyle: "short", timeStyle: "short" });
    } catch (_) {
      return date.toISOString().slice(0, 16).replace("T", " ");
    }
  }

  function safeLogo(url) {
    const clean = String(url || "").trim();
    return /^(https:\/\/|\/)/.test(clean) ? clean : "";
  }

  // The document body (no <html>): used inside the print frame and in the
  // portal preview.
  function documentBody(doc) {
    const d = doc || {};
    const issuer = d.issuer || {};
    const logo = safeLogo(issuer.logo_url);
    const iva = Number(d.iva || 0);
    return `
      <div class="cxdoc">
        ${logo ? `<img class="cxdoc-logo" src="${h(logo)}" alt="">` : ""}
        <div class="cxdoc-issuer">
          ${issuer.trade_name ? `<strong>${h(issuer.trade_name)}</strong>` : ""}
          ${issuer.legal_name ? `<div>${h(issuer.legal_name)}</div>` : ""}
          ${issuer.nit ? `<div>NIT ${h(issuer.nit)}</div>` : ""}
          ${issuer.regime ? `<div>${h(issuer.regime)}</div>` : ""}
          ${issuer.address ? `<div>${h(issuer.address)}</div>` : ""}
          ${issuer.phone ? `<div>Tel. ${h(issuer.phone)}</div>` : ""}
        </div>
        <h1 class="cxdoc-title">${h(d.title || "CUENTA DE COBRO")}</h1>
        <div class="cxdoc-not-invoice">${h(d.not_invoice_notice || "NO ES FACTURA DE VENTA")}</div>
        ${d.dian_pending_notice ? `<div class="cxdoc-dian">${h(d.dian_pending_notice)}</div>` : ""}
        <div class="cxdoc-meta">
          <div><span>${h(d.number_label || "Consecutivo interno")}</span><strong>${h(d.number || "")}</strong></div>
          ${d.issued_at ? `<div><span>Fecha</span><strong>${h(dateLabel(d.issued_at))}</strong></div>` : ""}
          ${d.table ? `<div><span>Mesa / venta</span><strong>${h(d.table)}</strong></div>` : ""}
          ${d.waiter ? `<div><span>Atendió</span><strong>${h(d.waiter)}</strong></div>` : ""}
        </div>
        <table class="cxdoc-lines">
          <thead><tr><th>Cant.</th><th>Producto</th><th>Valor</th></tr></thead>
          <tbody>
            ${(d.lines || []).map((line) => `
              <tr>
                <td>${h(line.qty)}</td>
                <td>${h(line.name)}${line.term ? ` <small>(${h(line.term)})</small>` : ""}${line.observations ? `<div class="cxdoc-obs">${h(line.observations)}</div>` : ""}</td>
                <td>${h(pesos(line.subtotal))}</td>
              </tr>`).join("")}
          </tbody>
        </table>
        <div class="cxdoc-totals">
          ${iva > 0 ? `
            <div><span>Subtotal</span><strong>${h(pesos(d.subtotal))}</strong></div>
            <div><span>IVA ${h(d.iva_percent)}%${d.prices_include_iva ? " (incluido)" : ""}</span><strong>${h(pesos(iva))}</strong></div>` : ""}
          <div class="cxdoc-total"><span>TOTAL</span><strong>${h(pesos(d.total))}</strong></div>
          ${d.payment_label ? `<div><span>Pago</span><strong>${h(d.payment_label)}</strong></div>` : ""}
        </div>
        ${d.withholdings ? `<div class="cxdoc-note">${h(d.withholdings)}</div>` : ""}
        ${d.resolution ? `<div class="cxdoc-note">${h(d.resolution)}</div>` : ""}
        ${d.footer ? `<div class="cxdoc-footer">${h(d.footer)}</div>` : ""}
        <div class="cxdoc-not-invoice cxdoc-not-invoice-end">${h(d.not_invoice_notice || "NO ES FACTURA DE VENTA")}</div>
      </div>`;
  }

  const STYLES = `
    .cxdoc{width:72mm;margin:0 auto;padding:2mm 0;font-family:ui-monospace,Menlo,Consolas,monospace;font-size:11.5px;line-height:1.35;color:#000;background:#fff}
    .cxdoc-logo{display:block;max-width:40mm;max-height:22mm;margin:0 auto 2mm;object-fit:contain}
    .cxdoc-issuer{text-align:center}
    .cxdoc-issuer strong{font-size:14px}
    .cxdoc-title{margin:3mm 0 1mm;font-size:15px;text-align:center;letter-spacing:.06em}
    .cxdoc-not-invoice{text-align:center;font-weight:900;border:1.5px solid #000;padding:1mm;letter-spacing:.04em}
    .cxdoc-not-invoice-end{margin-top:3mm}
    .cxdoc-dian{margin-top:2mm;font-size:10px;border:1px dashed #000;padding:1mm}
    .cxdoc-meta{margin:2mm 0;border-top:1px dashed #000;border-bottom:1px dashed #000;padding:1mm 0}
    .cxdoc-meta div,.cxdoc-totals div{display:flex;justify-content:space-between;gap:2mm}
    .cxdoc-lines{width:100%;border-collapse:collapse}
    .cxdoc-lines th{text-align:left;border-bottom:1px solid #000;font-size:10.5px}
    .cxdoc-lines td{vertical-align:top;padding:.6mm 0}
    .cxdoc-lines td:first-child{width:9mm;white-space:nowrap}
    .cxdoc-lines td:last-child,.cxdoc-lines th:last-child{text-align:right;white-space:nowrap}
    .cxdoc-obs{font-size:10px}
    .cxdoc-totals{margin-top:1.5mm;border-top:1px solid #000;padding-top:1mm}
    .cxdoc-total{font-size:14px;font-weight:900}
    .cxdoc-note,.cxdoc-footer{margin-top:2mm;font-size:10px;text-align:center;white-space:pre-line}
  `;

  function documentHtml(doc) {
    return `<!doctype html><html lang="es"><head><meta charset="utf-8"><title>${h((doc && doc.number) || "Cuenta de cobro")}</title>
<style>@page{size:80mm auto;margin:3mm}html,body{margin:0;background:#fff}${STYLES}</style></head>
<body>${documentBody(doc)}</body></html>`;
  }

  // Prints through a hidden iframe (no pop-up to be blocked). The browser's
  // own dialog lets the cashier pick the printer until the thermal-printer
  // phase connects one directly.
  function printDocument(doc) {
    const frame = document.createElement("iframe");
    frame.setAttribute("aria-hidden", "true");
    frame.style.position = "fixed";
    frame.style.right = "0";
    frame.style.bottom = "0";
    frame.style.width = "0";
    frame.style.height = "0";
    frame.style.border = "0";
    document.body.appendChild(frame);
    const win = frame.contentWindow;
    win.document.open();
    win.document.write(documentHtml(doc));
    win.document.close();
    const go = () => {
      try {
        win.focus();
        win.print();
      } finally {
        window.setTimeout(() => frame.remove(), 1000);
      }
    };
    if (win.document.readyState === "complete") window.setTimeout(go, 50);
    else frame.onload = go;
    return frame;
  }

  window.CxSaleDocument = { documentBody, documentHtml, printDocument, STYLES };
})();
