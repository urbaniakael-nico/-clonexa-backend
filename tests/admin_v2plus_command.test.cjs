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
  totals: { companies: 5, operating_today: 1, no_operation_today: 1, dormant: 1, at_risk: 1, inactive: 1, sales_today_total: 1234500, open_sessions: 3 },
  companies: [
    { id: 'a1', name: 'Asadero El Socio', slug: 'asadero', plan: 'Restaurante Pro', modules_enabled: 11, sales_today_total: 1234500,
      state: 'operando', state_reason: '42 venta(s) hoy', last_real_signal_at: '2026-10-01T04:25:00Z' },
    { id: 'v1', name: 'Vieja Tienda', slug: 'vieja', plan: 'starter', modules_enabled: 3, sales_today_total: 0,
      state: 'dormida', state_reason: 'Hace 61 días', last_real_signal_at: '2026-08-01T12:00:00Z' },
    { id: 'r1', name: 'Riesgosa <b>SAS</b>', slug: 'riesgosa', plan: 'starter', modules_enabled: 11, sales_today_total: 0,
      state: 'riesgo', state_reason: 'Inactiva con 11 módulos', last_real_signal_at: null },
    { id: 'i1', name: 'Quieta', slug: 'quieta', plan: 'starter', modules_enabled: 0, sales_today_total: 0,
      state: 'inactiva', state_reason: 'Inactiva sin módulos', last_real_signal_at: null },
    { id: 's1', name: 'Semana Activa', slug: 'semana', plan: 'starter', modules_enabled: 5, sales_today_total: 0,
      state: 'sin_operacion_hoy', state_reason: 'Última señal hace 3 días', last_real_signal_at: '2026-09-28T04:30:00Z' },
  ],
};

test('el Centro de mando pinta encabezado, tarjetas, tabla y acciones', () => {
  const ui = load();
  const out = ui.commandCenter(OVERVIEW, 'todas', { now: NOW });
  assert.match(out, /SISTEMA OPERATIVO EMPRESARIAL · NÚCLEO CLONEXA/);
  assert.match(out, /<h1 class="vp-title">Centro de mando<\/h1>/);
  assert.match(out, /Buscar u ordenar…<\/span><span class="vp-kbd">Ctrl K/);
  assert.match(out, /href="\/admin-v2">\+ Nueva empresa/);
  // 5 tarjetas
  for (const label of ['Ventas hoy', 'Operando hoy', 'Dormidas', 'En riesgo', 'Sesiones abiertas']) assert.match(out, new RegExp(label));
  assert.match(out, /\$1\.234\.500/);
  // tabla
  assert.match(out, /Asadero El Socio<\/b><small>asadero/);
  assert.match(out, /vp-initials" aria-hidden="true">AE</);
  assert.match(out, /vp-dot vp-dot-operando/);
  assert.match(out, /42 venta\(s\) hoy/);
  assert.match(out, /Hace 5 min/);
  assert.match(out, /href="\/admin-v2\?company_id=a1">Ficha/);
  assert.match(out, /href="\/client\?company_id=a1" target="_blank"[^>]*>Entrar como empresa/);
  // banda crítica y "Requiere acción"
  assert.match(out, /ACCESO MAESTRO SIN BCRYPT/);
  const actions = out.slice(out.indexOf('data-vp-actions'));
  assert.match(actions, /Acceso maestro sin bcrypt/);
  assert.match(actions, /Inactiva con 11 módulos/);
  assert.match(actions, /Dormida · Hace 61 días/);
  // nunca HTML sin escapar
  assert.doesNotMatch(out, /Riesgosa <b>SAS<\/b>/);
  assert.match(out, /Riesgosa &lt;b&gt;SAS&lt;\/b&gt;/);
});

test('los filtros muestran solo su estado y cada chip lleva su conteo', () => {
  const ui = load();
  const chips = ui.chips(OVERVIEW, 'riesgo');
  assert.match(chips, /data-vp-filter="todas"[^>]*>Todas<b>5<\/b>/);
  assert.match(chips, /data-vp-filter="sin_operacion_hoy"[^>]*>Sin operación hoy<b>1<\/b>/);
  assert.match(chips, /data-vp-filter="inactiva"[^>]*>Inactivas<b>1<\/b>/);
  assert.match(chips, /data-vp-filter="operando"[^>]*>Operando<b>1<\/b>/);
  assert.match(chips, /class="vp-chip is-active" type="button" data-vp-filter="riesgo" aria-pressed="true">En riesgo<b>1<\/b>/);
  const only = ui.table(OVERVIEW, 'riesgo', NOW);
  assert.match(only, /Riesgosa/);
  assert.doesNotMatch(only, /Asadero|Vieja|Quieta|Semana/);
  assert.equal(ui.filtered(OVERVIEW, 'dormida').map((c) => c.id).join(), 'v1');
  assert.equal(ui.filtered(OVERVIEW, 'todas').length, 5);
  // La activa sin operación hoy no se mezcla con las inactivas.
  assert.equal(ui.filtered(OVERVIEW, 'sin_operacion_hoy').map((c) => c.id).join(), 's1');
  assert.equal(ui.filtered(OVERVIEW, 'inactiva').map((c) => c.id).join(), 'i1');
  const row = ui.table(OVERVIEW, 'sin_operacion_hoy', NOW);
  assert.match(row, /vp-dot vp-dot-sin_operacion_hoy/);
  assert.match(row, /<b>Sin operación hoy<\/b>/);
  assert.match(row, /Última señal hace 3 días/);
  assert.doesNotMatch(row, /<b>Inactiva<\/b>/);
});

test('estados vacíos: sin empresas y sin coincidencias en el filtro', () => {
  const ui = load();
  const none = ui.commandCenter({ totals: {}, companies: [], master_access_mode: 'bcrypt' }, 'todas', { now: NOW });
  assert.match(none, /Aún no hay empresas activas en Clonexa/);
  assert.doesNotMatch(none, /ACCESO MAESTRO SIN BCRYPT/, 'con bcrypt no hay banda');
  assert.match(none, /Nada pendiente/);
  const noMatch = ui.table({ companies: [OVERVIEW.companies[0]] }, 'dormida', NOW);
  assert.match(noMatch, /Ninguna empresa en este estado/);
});

test('las secciones que aún no existen dicen "Próximamente"', () => {
  const ui = load();
  assert.match(ui.soon('billing'), /Facturación<\/h2><p>Próximamente/);
});

test('HTML y tema: menú completo, logo idéntico a Admin V2 y colores Catedral', () => {
  for (const item of ['Centro de mando', 'Empresas', 'Interruptores', 'Accesos y sesiones', 'Catálogo', 'Facturación', 'Salud y seguridad', 'Auditoría', 'Landing']) {
    assert.match(html, new RegExp(`>${item}</button>`));
  }
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
