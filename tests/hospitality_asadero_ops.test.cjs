// Pendientes de ASADERO (waiter_ordering): turno de la caja (048I) y CRM
// por área / "Operarios activos" (048F).
const { readFileSync } = require('node:fs');
const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const { FakeStorage, boot, flush } = require('./_cashier_boot.cjs');

const client = readFileSync('app/web/client.js', 'utf8').replace(/\r\n/g, '\n');

function fn(name) {
  const start = client.search(new RegExp(`\\n  (?:async )?function ${name}\\(`));
  assert.ok(start >= 0, name);
  const tail = client.slice(start + 3);
  const next = tail.search(/\n  (?:async )?function |\n  let |\n  const |\n  document\./);
  return (next < 0 ? tail : tail.slice(0, next)) + '\n';
}

// ---------------------------------------------------------------- caja ---
function cajaRoutes(state) {
  return (url, options = {}) => {
    const method = options.method || 'GET';
    if (url.includes('/mini-panel-operational-session')) {
      const action = (url.match(/operational-session\/(\w+)/) || [])[1] || 'get';
      state.actions.push(action);
      if (action === 'pause') state.status = 'break';
      if (action === 'resume') state.status = 'active';
      if (action === 'finish') state.status = 'finished';
      return [200, { operational_session: { status: state.status, active_seconds: 3725, break_seconds: 300 } }];
    }
    if (url.includes('/orders?status=active')) return [200, { orders: [] }];
    if (url.includes('/caja/config')) return [200, { direct_sale: false }];
    if (url.includes('/mini-panel-login') && method === 'POST') return [200, { access_token: 'jwt' }];
    return [200, {}];
  };
}

async function settle() {
  for (let i = 0; i < 6; i += 1) await flush();
}

test('la caja abre su turno al entrar y muestra el cronómetro', async () => {
  const shift = { status: 'active', actions: [] };
  const local = new FakeStorage();
  local.setItem('clonexa_cashier_token_c1', 'jwt');
  const b = boot({ local, routes: cajaRoutes(shift) });
  await settle();
  assert.deepEqual(shift.actions, ['get'], 'GET de la sesión operativa = abre/reusa el turno (asistencia)');
  const call = b.calls.find((c) => c.url.includes('/mini-panel-operational-session'));
  assert.match(call.url, /panel_type=caja/);
  assert.match(b.root.innerHTML, /⏱ En turno[\s\S]*data-csh-shift-clock>1:02:05</);
});

test('el cajero puede pausar, retomar y cerrar jornada, y queda registrado', async () => {
  const shift = { status: 'active', actions: [] };
  const local = new FakeStorage();
  local.setItem('clonexa_cashier_token_c1', 'jwt');
  const b = boot({ local, routes: cajaRoutes(shift) });
  b.ctx.window.confirm = () => true;
  await settle();

  b.click('data-csh-shift-toggle');
  assert.match(b.root.innerHTML, /data-csh-shift-pause/);
  b.click('data-csh-shift-pause');
  await settle();
  assert.match(b.root.innerHTML, /⏸ En pausa/);
  assert.match(b.root.innerHTML, /data-csh-shift-resume/);

  b.click('data-csh-shift-resume');
  await settle();
  assert.match(b.root.innerHTML, /⏱ En turno/);

  b.click('data-csh-shift-finish');
  await settle();
  assert.deepEqual(shift.actions, ['get', 'pause', 'resume', 'finish']);
  const posts = b.calls.filter((c) => /operational-session\/(pause|resume|finish)\?panel_type=caja/.test(c.url));
  assert.ok(posts.every((c) => c.options.method === 'POST'));
  assert.equal(local.getItem('clonexa_cashier_token_c1'), null, 'al cerrar jornada cierra la sesión');
  assert.match(b.root.innerHTML, /Jornada cerrada\. Tus horas quedaron registradas\./);
});

// ----------------------------------------------------------------- CRM ---
function crm({ waiterOrdering = true } = {}) {
  const body = { children: [], appendChild(node) { this.children.push(node); } };
  const head = { children: [], appendChild(node) { this.children.push(node); } };
  const ctx = vm.createContext({
    h: (value) => String(value ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])),
    isClientModuleActive: (code) => waiterOrdering && code === 'waiter_ordering',
    state: { company: { timezone: 'America/Bogota' } },
    cxCrmActiveModuleSet018B: () => new Set(['inventory', 'hospitality', 'waiter_ordering']),
    cxCrmNormalizeCode018B: (value) => String(value || '').toLowerCase(),
    CX_CRM_TOP_MODULE_PRIORITY_018B: ['production', 'references', 'gps', 'materials', 'field', 'requests', 'orders', 'inventory', 'stock', 'retail', 'stores', 'hospitality', 'bots', 'payroll'],
    document: {
      body, head,
      getElementById: (id) => [...body.children, ...head.children].find((node) => node.id === id) || null,
      createElement: () => {
        const node = { id: '', innerHTML: '', textContent: '', attrs: {} };
        node.setAttribute = (k, v) => { node.attrs[k] = v; };
        node.addEventListener = () => {};
        node.remove = () => {};
        return node;
      },
    },
    Intl, Date, Number, String, Array, Set, Object, JSON,
  });
  vm.runInContext(`var cxCrmOperators048F = [];\n${['cxCrmTime048F', 'cxCrmHospitalityArea048F', 'cxCrmOperatorsCard048F',
    'cxCrmOpenOperators048F', 'cxHspStockStyles048E', 'crmPickSummaryModules018B'].map(fn).join('\n')}`, ctx);
  return { ctx, body };
}

const person = (area, shift) => ({ snapshotRow: { hospitality: { area, ...shift } } });

test('las tarjetas del CRM muestran el área real: Cocina, Mesas o Caja', () => {
  const { ctx } = crm();
  const card = (p) => JSON.parse(JSON.stringify(ctx.cxCrmHospitalityArea048F(p)));
  assert.deepEqual(card(person('Cocina', { shift_open: true, shift_status: 'active', shift_started_at: '2026-09-24T23:05:00Z' })),
    { code: 'hospitality_area', label: 'Área', value: 'Cocina', meta: 'En turno desde 18:05', tone: 'ok' });
  assert.equal(card(person('Mesas', { shift_open: true, shift_status: 'break', shift_started_at: '2026-09-24T22:00:00Z' })).meta, 'En pausa · turno desde 17:00');
  assert.deepEqual([card(person('Caja', { shift_open: false })).value, card(person('Caja', { shift_open: false })).meta], ['Caja', 'Sin turno abierto']);
  assert.equal(ctx.cxCrmHospitalityArea048F(person('', { shift_open: false })), null, 'sin área conocida: tarjeta de siempre');
  assert.equal(crm({ waiterOrdering: false }).ctx.cxCrmHospitalityArea048F(person('Cocina', {})), null, 'otras empresas sin cambios');
});

test('"Operarios activos" reemplaza a Inventario y cuenta solo turnos abiertos', () => {
  const { ctx, body } = crm();
  assert.deepEqual(JSON.parse(JSON.stringify(ctx.crmPickSummaryModules018B({}))), ['operators_active', 'hospitality']);
  const html = ctx.cxCrmOperatorsCard048F({ summary: {
    operators_active: 2,
    operators_active_list: [
      { name: 'Ana', area: 'Cocina', status: 'active', since: '2026-09-24T22:30:00Z' },
      { name: 'Luis', area: 'Caja', status: 'break', since: '2026-09-24T23:00:00Z' },
    ],
  } });
  assert.match(html, /data-crm-operators-048f>\s*<span>Operarios activos<\/span>\s*<strong>2<\/strong>/);
  ctx.cxCrmOpenOperators048F();
  const sheet = body.children.find((node) => node.id === 'cxCrmOperators048F');
  assert.match(sheet.innerHTML, /Operarios activos \(2\)/);
  assert.match(sheet.innerHTML, /Ana <small>Cocina<\/small><\/span>\s*<b>desde 17:30<\/b>/);
  assert.match(sheet.innerHTML, /Luis <small>Caja<\/small><\/span>\s*<b>En pausa · desde 18:00<\/b>/);
  assert.deepEqual(JSON.parse(JSON.stringify(crm({ waiterOrdering: false }).ctx.crmPickSummaryModules018B({}))), ['inventory', 'hospitality']);
});
