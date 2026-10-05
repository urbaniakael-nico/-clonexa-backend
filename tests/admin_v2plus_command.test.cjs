// Consola v2+ · Centro de mando: render con un overview de ejemplo, filtros
// por estado, estado vacío, banda del acceso maestro y "Requiere acción".
const { readFileSync } = require('node:fs');
const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');

const source = readFileSync('app/web/admin_v2plus.js', 'utf8');
const html = readFileSync('app/web/admin_v2plus.html', 'utf8').replace(/\r\n/g, '\n');
const css = readFileSync('app/web/admin_v2plus.css', 'utf8').replace(/\r\n/g, '\n');

function load() {
  const ctx = vm.createContext({ window: {}, document: {}, Date, Math, Number, String, Array, encodeURIComponent });
  vm.runInContext(source, ctx);
  return ctx.window.CxConsolePlus;
}

const NOW = Date.parse('2026-10-01T04:30:00Z');
const OVERVIEW = {
  ok: true, generated_at: '2026-10-01T04:30:00Z', master_access_mode: 'sha256_legacy',
  totals: { registered: 6, registered_active: 4, connected_now: 1, users_connected_now: 3, logins_today: 7, dormant: 1, at_risk: 1, open_sessions: 3,
    states: { conectada: 1, activa_hoy: 1, sin_actividad_hoy: 1, dormida: 1, riesgo: 1, inactiva: 1 } },
  health: { database: { used_mb: 236.4, limit_mb: 500, used_pct: 47.3, warn: false }, demo_companies: 1, deploy: { commit: 'abc' } },
  companies: [
    { id: 'a1', kind: 'registrada', name: 'Asadero El Socio', slug: 'asadero', plan: 'Restaurante Pro', modules_enabled: 11, open_sessions: 3, sales_today_total: 1234500,
      state: 'conectada', state_reason: '3 usuarios conectados ahora', last_real_signal_at: '2026-10-01T04:25:00Z' },
    { id: 't1', kind: 'registrada', name: 'Taller Produce', slug: 'taller', plan: 'starter', modules_enabled: 4, open_sessions: 0,
      state: 'activa_hoy', state_reason: 'Última señal hoy a las 18:10', last_real_signal_at: '2026-09-30T23:10:00Z' },
    { id: 'v1', kind: 'registrada', name: 'Vieja Tienda', slug: 'vieja', plan: 'starter', modules_enabled: 3, open_sessions: 0,
      state: 'dormida', state_reason: 'Hace 61 días', last_real_signal_at: '2026-08-01T12:00:00Z' },
    { id: 'r1', kind: 'registrada', name: 'Riesgosa <b>SAS</b>', slug: 'riesgosa', plan: 'starter', modules_enabled: 11, open_sessions: 0,
      state: 'riesgo', state_reason: 'Inactiva con 11 módulos', last_real_signal_at: null },
    { id: 'i1', kind: 'registrada', name: 'Quieta', slug: 'quieta', plan: 'starter', modules_enabled: 0, open_sessions: 0,
      state: 'inactiva', state_reason: 'Inactiva sin módulos', last_real_signal_at: null },
    { id: 's1', kind: 'registrada', name: 'Semana Activa', slug: 'semana', plan: 'starter', modules_enabled: 5, open_sessions: 0,
      state: 'sin_actividad_hoy', state_reason: 'Última señal hace 3 días', last_real_signal_at: '2026-09-28T04:30:00Z' },
    { id: 'd1', kind: 'demo', name: 'Demo Bar', slug: 'demo-bar', plan: 'starter', modules_enabled: 9, open_sessions: 1,
      state: 'dormida', state_reason: 'Hace 90 días', last_real_signal_at: null },
  ],
};

test('el Centro de mando pinta conexión y salud, nunca ventas', () => {
  const ui = load();
  const out = ui.commandCenter(OVERVIEW, 'todas', { now: NOW });
  assert.match(out, /SISTEMA OPERATIVO EMPRESARIAL · NÚCLEO CLONEXA/);
  assert.match(out, /<h1 class="vp-title">Centro de mando<\/h1>/);
  assert.match(out, /Buscar u ordenar…<\/span><span class="vp-kbd">Ctrl K/);
  const cards = ui.cards(OVERVIEW);
  for (const [label, value] of [['Conectadas ahora', '1'], ['Usuarios conectados', '3'], ['Ingresos hoy', '7'], ['Dormidas', '1'], ['En riesgo', '1'], ['Base de datos', '236\\.4 MB']]) {
    assert.match(cards, new RegExp(`<span>${label}</span><strong>${value}</strong>`), label);
  }
  assert.match(cards, /de 500 MB · 47\.3%/);
  assert.doesNotMatch(out, /Ventas|\$1\.234\.500|1234500/, 'sin ventas en el Centro de mando');
  assert.match(out, /<th>Empresa<\/th><th>Estado<\/th><th>Plan<\/th><th>Módulos<\/th><th>Sesiones abiertas<\/th><th>Última conexión<\/th>/);
  assert.match(out, /Asadero El Socio<\/b><small>asadero/);
  assert.match(out, /vp-dot vp-dot-conectada/);
  assert.match(out, /3 usuarios conectados ahora/);
  assert.match(out, /Hace 5 min/);
  assert.match(out, /href="\/client\?company_id=a1" target="_blank"[^>]*>Entrar como empresa/);
  assert.doesNotMatch(out, /Demo Bar/, 'las demos no aparecen sin "Ver demos"');
  assert.match(out, /data-vp-show-demos\s*>/);
  assert.match(out, /ACCESO MAESTRO SIN BCRYPT/);
  const actions = out.slice(out.indexOf('data-vp-actions'));
  assert.match(actions, /Acceso maestro sin bcrypt/);
  assert.match(actions, /Inactiva con 11 módulos/);
  assert.match(actions, /Dormida · Hace 61 días/);
  assert.doesNotMatch(actions, /Demo Bar/);
  assert.doesNotMatch(actions, /Base de datos por encima/);
  assert.doesNotMatch(out, /Riesgosa <b>SAS<\/b>/);
  assert.match(out, /Riesgosa &lt;b&gt;SAS&lt;\/b&gt;/);
});

test('base de datos por encima del 80 %: aviso en la tarjeta y en "Requiere acción"', () => {
  const ui = load();
  const hot = { ...OVERVIEW, master_access_mode: 'bcrypt', health: { ...OVERVIEW.health, database: { used_mb: 412, limit_mb: 500, used_pct: 82.4, warn: true } } };
  const out = ui.commandCenter(hot, 'todas', { now: NOW });
  assert.match(ui.cards(hot), /data-vp-db-warn role="alert"><span>Base de datos<\/span><strong>412 MB<\/strong><small>de 500 MB · 82\.4% · ⚠ libera espacio/);
  assert.match(out.slice(out.indexOf('data-vp-actions')), /Base de datos por encima del 80 %/);
  assert.doesNotMatch(out, /ACCESO MAESTRO SIN BCRYPT/);
  const unknown = { ...OVERVIEW, health: { database: { used_mb: null, limit_mb: 500 } } };
  assert.match(ui.cards(unknown), /<span>Base de datos<\/span><strong>—<\/strong><small>Sin dato/);
});

test('"Ver demos" suma las demos a la tabla y a los chips', () => {
  const ui = load();
  assert.equal(ui.filtered(OVERVIEW, 'todas').length, 6);
  assert.equal(ui.filtered(OVERVIEW, 'todas', true).length, 7);
  assert.match(ui.chips(OVERVIEW, 'dormida'), /data-vp-filter="dormida" aria-pressed="true">Dormidas<b>1<\/b>/);
  assert.match(ui.chips(OVERVIEW, 'dormida', true), /data-vp-filter="dormida" aria-pressed="true">Dormidas<b>2<\/b>/);
  assert.match(ui.chips(OVERVIEW, 'todas', true), /data-vp-show-demos checked/);
  const withDemos = ui.commandCenter(OVERVIEW, 'todas', { now: NOW, showDemos: true });
  assert.match(withDemos, /Demo Bar<\/b><small>demo-bar · demo/);
});

test('los filtros muestran solo su estado y cada chip lleva su conteo', () => {
  const ui = load();
  const chips = ui.chips(OVERVIEW, 'riesgo');
  assert.match(chips, /data-vp-filter="todas"[^>]*>Todas<b>6<\/b>/);
  for (const [key, label] of [['conectada', 'Conectadas'], ['activa_hoy', 'Activas hoy'], ['sin_actividad_hoy', 'Sin actividad hoy'], ['inactiva', 'Inactivas']]) {
    assert.match(chips, new RegExp(`data-vp-filter="${key}"[^>]*>${label}<b>1</b>`), key);
  }
  assert.match(chips, /class="vp-chip is-active" type="button" data-vp-filter="riesgo" aria-pressed="true">En riesgo<b>1<\/b>/);
  const only = ui.table(OVERVIEW, 'riesgo', NOW);
  assert.match(only, /Riesgosa/);
  assert.doesNotMatch(only, /Asadero|Vieja|Quieta|Semana|Taller/);
  assert.equal(ui.filtered(OVERVIEW, 'sin_actividad_hoy').map((c) => c.id).join(), 's1');
  assert.equal(ui.filtered(OVERVIEW, 'inactiva').map((c) => c.id).join(), 'i1');
  const row = ui.table(OVERVIEW, 'sin_actividad_hoy', NOW);
  assert.match(row, /vp-dot vp-dot-sin_actividad_hoy/);
  assert.match(row, /<b>Sin actividad hoy<\/b>/);
  assert.match(row, /Última señal hace 3 días/);
  assert.doesNotMatch(row, /<b>Inactiva<\/b>/);
  assert.match(ui.table(OVERVIEW, 'activa_hoy', NOW), /vp-dot vp-dot-activa_hoy/);
});

test('estados vacíos: sin empresas y sin coincidencias en el filtro', () => {
  const ui = load();
  const none = ui.commandCenter({ totals: {}, companies: [], master_access_mode: 'bcrypt' }, 'todas', { now: NOW });
  assert.match(none, /Aún no hay empresas registradas activas en Clonexa/);
  assert.doesNotMatch(none, /ACCESO MAESTRO SIN BCRYPT/, 'con bcrypt no hay banda');
  assert.match(none, /Nada pendiente/);
  const noMatch = ui.table({ companies: [OVERVIEW.companies[0]] }, 'dormida', NOW);
  assert.match(noMatch, /Ninguna empresa en este estado/);
});

test('una sección sin archivo propio cae en "Próximamente" (hoy ninguna: Estudio de marca tiene admin_v2plus_brand.js)', () => {
  const ui = load();
  assert.match(ui.soon('brand'), /Estudio de marca<\/h2><p>Próximamente/);
});

test('HTML y tema: menú completo, logo idéntico a Admin V2 y colores Catedral', () => {
  // Menú final (Fase 3), en este orden exacto y sin Facturación.
  const order = ['Centro de mando', 'Empresas', 'Catálogo', 'Interruptores', 'Estudio de marca', 'Accesos y sesiones', 'Salud y seguridad', 'Facturación', 'Landing'];
  const nav = [...html.matchAll(/data-vp-view="[a-z]+">([^<]+)<\/button>/g)].map((m) => m[1]);
  assert.deepEqual(nav, order);
  assert.match(html, /data-vp-view="billing">Facturación<\/button>/, 'Facturación ocupa el lugar de Auditoría');
  assert.match(html, /<script src="\/admin-v2plus-billing\.js"><\/script>/);
  assert.match(html, /Volver a Admin V2/);
  assert.match(html, /class="cx-logo-fallback" aria-hidden="true">CX</);
  assert.match(html, /class="cx-brand-title">CLONEXA</);
  const v2css = readFileSync('app/web/admin_v2.css', 'utf8').replace(/\r\n/g, '\n');
  const block = (text, sel) => text.slice(text.indexOf(`${sel} {`), text.indexOf('}', text.indexOf(`${sel} {`)) + 1);
  for (const sel of ['.cx-brand', '.cx-logo-wrap', '.cx-logo-img', '.cx-logo-fallback', '.cx-brand-title', '.cx-brand-subtitle']) {
    assert.equal(block(css, sel), block(v2css, sel), `${sel} igual al de Admin V2`);
  }
  assert.match(css, /url\("\/admin-v2-assets\/consola-fondo\.jpg"\)/);
  assert.match(css, /background-attachment: fixed/);
  assert.match(css, /rgba\(3,1,2,\.55\) 0%, rgba\(3,1,2,\.1\) 45%, transparent 70%/);
  assert.match(css, /radial-gradient\(ellipse 45% 60% at 82% 55%, rgba\(200,14,42,\.22\), transparent 70%\)/);
  assert.match(css, /grid-template-columns: 264px/);
  assert.match(css, /border-right: 1px solid rgba\(227, 18, 47, \.3\)/);
  for (const color of ['#050204', '#F4ECEC', '#A8969A', '#E3122F', '#A80B24', '#9D17FF', '#B84DFF', '#4ADE9A', '#F0B44C', '#FF2D4A', '#5E4C51']) {
    assert.ok(css.includes(color), color);
  }
  assert.match(html, /family=Chakra\+Petch/); assert.match(html, /family=Cinzel:wght@900/); assert.match(html, /family=JetBrains\+Mono/);
  assert.match(css, /min-height: 44px/);
});
