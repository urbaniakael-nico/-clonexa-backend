// 064C: recorre la flecha atrás/adelante en Chrome real, con popstate de verdad. Sin red: datos
// inventados. Deja cada paso en <pre id="steps">. window.__boot prueba que la página no se recargó.
(() => {
  const OP = { id: "op", name: "Alabama", code: "AL", timezone: "America/Chicago", abbr: "CT", accent: 1, slug: "alabama", local_time: "12:00", local_date: "2026-11-05" };
  window.__CX_LIDER__ = { ok: true, name: "Alabama", slug: "alabama", accent: 1, abbr: "CT", timezone: "America/Chicago", brand: {} };
  window.__boot = `b${Math.random()}`;
  const boot = window.__boot;
  const json = (b, status = 200) => new Response(JSON.stringify(b), { status, headers: { "content-type": "application/json" } });
  const real = window.fetch.bind(window);
  let logouts = 0;
  window.fetch = async (url, opts) => {
    const u = String(url);
    if (u.includes("/mini-panel-login")) return json({ access_token: "tok" });
    if (u.includes("/auth/logout")) { logouts += 1; return json({ ok: true }); }
    if (u.includes("/inicio")) return json({ ok: true, company: "VOLTAGE", me: { name: "Alma", role: "Supervisor" }, operation: OP, crm: { total: 1, working: 1, on_break: 0, no_shift: 0, to_confirm: 0 }, reports: { hours_minutes: 60, alerts: 0, notes_today: 0 } });
    if (u.includes("/crm")) return json({ ok: true, operation: OP, counts: { total: 1, working: 1, on_break: 0, no_shift: 0, to_confirm: 0 }, people: [{ id: "a", name: "Ana", role: "Operario", state: "working", minutes: 5, last_mark: null }] });
    if (u.includes("/reportes")) {
      const fix = await (await real("/__fix.json")).json();
      fix.operations = fix.operations.filter((o) => o.name === "Alabama").map((o) => ({ ...o, color: 1 }));
      fix.scope = { limited: true };
      return json(fix);
    }
    return real(url, opts);
  };

  const steps = [];
  const q = (s) => document.querySelector(s);
  const pause = (ms) => new Promise((r) => setTimeout(r, ms));
  function snapshot(name) {
    const on = q(".lo-nav .is-on");
    steps.push({ name, same_page: window.__boot === boot, screen: q("[data-lo-login]") ? "login" : on ? on.getAttribute("data-lo-tab") : "?", person_open: Boolean(q(".rb-detail") || q(".lo-sheet")), confirm: Boolean(q(".lo-dialog")),
      preset: (q('[data-rb-preset].is-on') || {}).getAttribute ? q('[data-rb-preset].is-on').getAttribute("data-rb-preset") : "", logouts,
      token: sessionStorage.getItem(window.CxLiderOperacion.TOKEN_KEY) || "", state: (history.state || {}).screen || "", overflow: document.documentElement.scrollWidth > innerWidth + 1, width: innerWidth });
  }
  const back = async (name) => { history.back(); await pause(350); snapshot(name); };
  const forward = async (name) => { history.forward(); await pause(350); snapshot(name); };
  const click = async (sel, name) => { q(sel).click(); await pause(350); if (name) snapshot(name); };
  async function until(sel) { for (let i = 0; i < 60 && !q(sel); i += 1) await pause(100); }

  async function run() {
    sessionStorage.removeItem(window.CxLiderOperacion.TOKEN_KEY);
    await pause(200);
    snapshot("login");
    const form = q("[data-lo-login]");
    form.elements.namedItem("username").value = "alma";
    form.elements.namedItem("password").value = "clave";
    form.requestSubmit();
    await until(".lo-module");
    snapshot("entro");
    await back("atras en inicio tras entrar");
    await click("[data-lo-exit-no]", "no");
    await back("atras otra vez");
    await back("atras con la pregunta abierta");
    await click("[data-lo-exit-no]", "no otra vez");
    await click('.lo-nav [data-lo-tab="crm"]', "crm");
    await until(".lo-person");
    await click('.lo-nav [data-lo-tab="reportes"]');
    await until(".rb-row");
    await click('[data-rb-preset="month"]');
    await until(".rb-row");
    snapshot("reportes mes");
    await click(".rb-who", "persona");
    await back("atras cierra persona");
    await forward("adelante abre persona");
    await back("atras cierra persona 2");
    await back("atras a crm");
    await forward("adelante a reportes");
    await until(".rb-row");
    await pause(300);
    snapshot("reportes conserva mes");
    await back("atras a crm 2");
    await click("[data-lo-person]", "detalle");
    await back("atras cierra detalle");
    await forward("adelante abre detalle");
    await click("[data-lo-detail-close]", "cerrar detalle");
    await back("atras a inicio");
    await back("atras pregunta");
    await click("[data-lo-exit-no]");
    await forward("adelante en inicio no rompe");
    await click('.lo-nav [data-lo-tab="crm"]');
    await until(".lo-person");
    await click('.lo-nav [data-lo-tab="inicio"]', "barra a inicio");
    await back("atras tras barra a inicio");
    await click("[data-lo-exit-yes]", "si salir");
    await back("atras tras salir");
    const out = document.createElement("pre");
    out.id = "steps";
    out.textContent = JSON.stringify(steps);
    document.body.appendChild(out);
  }
  window.addEventListener("load", () => setTimeout(() => run().catch((e) => {
    const out = document.createElement("pre");
    out.id = "steps";
    out.textContent = JSON.stringify([...steps, { name: "ERROR", error: String(e) }]);
    document.body.appendChild(out);
  }), 200));
})();
