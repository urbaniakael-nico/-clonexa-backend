// Vista previa de Conversaciones Nexa para la prueba de diseño: la consola v2+
// real (admin_v2plus.html y sus JS) con fetch simulado. ?open=1 abre una
// conversación. Al final mide desbordes y deja el resultado en <pre id="layout">.
(() => {
  const P = new URLSearchParams(location.search);
  const ID = "7d3b8a6e-1111-4c22-9333-444455556666";
  const json = (b, status = 200) => new Response(JSON.stringify(b), { status, headers: { "content-type": "application/json" } });
  const iso = (min) => new Date(Date.now() - min * 60000).toISOString();
  const long = "Tenemos un restaurante con tres sedes en Bogotá y queremos saber si podemos manejar los pedidos por QR, la cocina, los domicilios y el cierre de caja de todas las sedes desde un mismo lugar sin pagar por cada mesero";
  const items = [
    { id: ID, wa_id: "573001112233", nombre: "Ana María Gómez Restrepo de la Torre", tipo_negocio: "Restaurante de comida a la mesa", ciudad: "Bogotá D.C.", etapa: "demo_agendada", nexa_pausada: true, ultimo: long, ultimo_at: iso(3), nueva: true },
    { id: "b2", wa_id: "573005556677", nombre: null, tipo_negocio: "Bar", ciudad: "Medellín", etapa: "calificado", nexa_pausada: false, ultimo: "¿Tienen juegos en vivo?", ultimo_at: iso(80), nueva: false },
    { id: "c3", wa_id: "13468244098", nombre: "Joe", tipo_negocio: "Call center", ciudad: "Houston", etapa: "pidio_persona", nexa_pausada: false, ultimo: "Can I talk to a person?", ultimo_at: iso(2000), nueva: false },
    { id: "d4", wa_id: "573104445566", nombre: "Taller Hilos", tipo_negocio: null, ciudad: null, etapa: "nuevo", nexa_pausada: false, ultimo: "[audio]", ultimo_at: iso(5000), nueva: true },
    { id: "e5", wa_id: "573117778899", nombre: "Pedro", tipo_negocio: "Tienda o cadena", ciudad: "Cali", etapa: "baja", nexa_pausada: false, ultimo: "baja", ultimo_at: iso(9000), nueva: false },
  ];
  const list = { ok: true, total: 5, nuevas: 2, counts: { nuevo: 1, calificado: 1, demo_agendada: 1, pidio_persona: 1, no_interesado: 0, baja: 1 }, items };
  const detail = {
    ok: true, entregas: { sent: 2, delivered: 2, read: 3, failed: 1 },
    contacto: { id: ID, wa_id: "573001112233", nombre: items[0].nombre, idioma: "es", tipo_negocio: items[0].tipo_negocio, ciudad: "Bogotá D.C.", tamano: "3 sedes, 40 mesas y 25 personas",
      dolor: "pedidos que se pierden entre mesero y cocina, y el cierre de caja de cada sede", correo: "ana.maria.gomez.restrepo@restaurantemuylargo.com.co", etapa: "demo_agendada",
      nexa_pausada: true, demo_at: new Date(Date.now() + 86400000).toISOString(), demo_link: "https://meet.google.com/abc-defg-hij" },
    mensajes: [
      { direccion: "in", tipo: "text", texto: "Hola", opciones: [], creado: iso(30) },
      { direccion: "out", tipo: "list", texto: "Hola, soy Nexa, la asistente virtual con IA de Clonexa. Clonexa conecta pedidos, cocina, caja, inventario, turnos y nómina en un solo sistema. Al continuar aceptas el tratamiento de tus datos para atenderte: https://www.clonexa.com.co/privacidad ¿Qué tipo de negocio tienes?",
        opciones: ["Restaurante", "Bar", "Taller o fábrica", "Tienda o cadena", "Distribuidora", "Call center", "Personal en campo", "Otro"], estado: "read", creado: iso(29) },
      { direccion: "in", tipo: "interactive", texto: "Restaurante", opciones: [], creado: iso(28) },
      { direccion: "in", tipo: "text", texto: long + " https://www.ejemplo-de-enlace-muy-largo-sin-espacios.com/ruta/que/no/se/corta/nunca/porque/no/tiene/espacios", opciones: [], creado: iso(20) },
      { direccion: "out", tipo: "buttons", texto: "¿Te sirve alguno de estos horarios para una demo de 30 minutos?", opciones: ["Jue 29 oct 10:00 am", "Jue 29 oct 3:30 pm", "Vie 30 oct 9:00 am"], estado: "delivered", creado: iso(19) },
      { direccion: "in", tipo: "audio", texto: null, opciones: [], creado: iso(10) },
      { direccion: "out", tipo: "text", texto: "Por ahora leo y escribo en texto.", opciones: [], estado: "failed", error: "131047 Re-engagement message", creado: iso(9) },
    ],
  };
  window.fetch = async (url) => {
    const u = String(url);
    if (u.startsWith("/admin-v2/api/overview")) return json({ ok: true, companies: [], totals: {}, health: {} });
    if (u.startsWith("/admin-v2/api/billing/alerts")) return json({ alerts: [] });
    if (u.startsWith(`/admin-v2/api/nexa-wa/conversations/${ID}`)) return json(detail);
    if (u.startsWith("/admin-v2/api/nexa-wa/conversations")) return json(list);
    return json({});
  };
  if (P.get("open") === "1") { try { history.replaceState(null, "", `${location.pathname}${location.search}#nexa/${ID}`); } catch (_) {} }

  function measure() {
    const root = document.querySelector("[data-nx-root]");
    const out = document.createElement("pre");
    out.id = "layout";
    if (!root) { out.textContent = JSON.stringify({ mounted: false }); document.body.appendChild(out); return; }
    const bad = [];
    root.querySelectorAll("*").forEach((el) => {
      if (/^(INPUT|SELECT|OPTION)$/.test(el.tagName) || el.classList.contains("sr-only")) return;
      if (el.offsetParent === null) return;
      const cs = getComputedStyle(el);
      if (cs.textOverflow === "ellipsis" || /auto|scroll/.test(cs.overflowX + cs.overflowY)) return;
      if (el.scrollWidth > el.clientWidth + 1) bad.push({ tag: el.tagName, cls: String(el.className || ""), text: (el.textContent || "").trim().slice(0, 40), sw: el.scrollWidth, cw: el.clientWidth });
    });
    const shown = (sel) => { const el = root.querySelector(sel); return !!el && el.offsetParent !== null && el.getBoundingClientRect().width > 0; };
    const r = (sel) => { const el = root.querySelector(sel); if (!el) return null; const b = el.getBoundingClientRect(); return { left: Math.round(b.left), right: Math.round(b.right), w: Math.round(b.width) }; };
    out.textContent = JSON.stringify({
      mounted: true, width: window.innerWidth, page_overflow: document.documentElement.scrollWidth > window.innerWidth + 1, bad,
      list: shown("[data-nx-list] .vp-nx-list"), detail: shown(".vp-nx-chat"), back: shown("[data-nx-back]"),
      rows: root.querySelectorAll(".vp-nx-row").length, bubbles: root.querySelectorAll(".vp-nx-msg").length,
      list_box: r("[data-nx-list]"), detail_box: r("[data-nx-detail]"),
      wide: [...document.querySelectorAll("body *")].filter((el) => el.getBoundingClientRect().right > window.innerWidth + 1 && el.offsetParent !== null)
        .slice(0, 6).map((el) => `${el.tagName}.${String(el.className || "").slice(0, 40)} ${Math.round(el.getBoundingClientRect().right)}`),
    });
    document.body.appendChild(out);
  }

  const go = (n = 0) => {
    const plus = window.CxConsolePlus;
    if (!plus) return setTimeout(() => go(n + 1), 100);
    if (P.get("open") !== "1" && plus.state.view !== "nexa") plus.setView("nexa");
    const ready = document.querySelector(P.get("open") === "1" ? ".vp-nx-chat" : ".vp-nx-list");
    if (!ready && n < 60) return setTimeout(() => go(n + 1), 150);
    setTimeout(measure, 600);
  };
  window.addEventListener("load", () => go());
})();
