// Consola v2+ · Empresas. Pruebas de CONTRATO: lo migrado desde Admin V2
// (crear empresa + paquete + dueño, cambiar estado y archivar) usa el MISMO
// endpoint, método y cuerpo que admin_v2.js. Además: pestañas sin cruces,
// filtros de v2, acciones nuevas y escape de nombres.
const { readFileSync } = require('node:fs');
const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');

const source = readFileSync('app/web/admin_v2plus_companies.js', 'utf8');
const v2 = readFileSync('app/web/admin_v2.js', 'utf8').replace(/\r\n/g, '\n');

function load(responder = () => ({ status: 200, body: {} })) {
  const calls = [];
  const fetch = async (url, options = {}) => {
    const call = { url, method: options.method || 'GET', body: options.body ? JSON.parse(options.body) : undefined };
    calls.push(call);
    const { status, body } = responder(call);
    return { status, ok: status >= 200 && status < 300, json: async () => body };
  };
  const ctx = vm.createContext({ window: { location: { href: '' } }, document: {}, fetch, JSON, Object, Array, String, Math, Promise, Error, encodeURIComponent });
  vm.runInContext(source, ctx);
  return { ui: ctx.window.CxConsoleCompanies, calls };
}

const strip = (calls) => calls.map((c) => `${c.method} ${c.url} ${c.body === undefined ? '' : JSON.stringify(c.body)}`.trim());

test('crear empresa: mismo orden, endpoints y cuerpos que createCompany de Admin V2', async () => {
  const { ui, calls } = load((c) => (c.url === '/api/v1/companies' ? { status: 200, body: { id: 'c-1', name: 'Bar' } } : { status: 200, body: {} }));
  const out = await ui.createCompanyFlow({ name: 'Bar Nuevo', slug: 'bar-nuevo', timezone: '', plan: '', package_code: 'restaurante',
    owner_full_name: ' Ana Pérez ', owner_email: ' ANA@BAR.CO ', owner_password: 'Clonexa-bar-x1y2!', kind: 'demo' });
  assert.deepEqual(strip(calls), [
    'POST /api/v1/companies {"name":"Bar Nuevo","slug":"bar-nuevo","timezone":"America/Bogota","plan":"standard"}',
    'POST /api/v1/companies/c-1/activate-package {"package_code":"restaurante","settings":{}}',
    'POST /api/v1/companies/c-1/users {"email":"ana@bar.co","full_name":"Ana Pérez","role":"company_admin","password":"Clonexa-bar-x1y2!","status":"active"}',
  ]);
  assert.equal(out.companyId, 'c-1');
  assert.equal(out.temporaryPassword, 'Clonexa-bar-x1y2!');
});

test('Admin V2 sigue usando exactamente esos cuerpos (si v2 cambia, esta prueba avisa)', () => {
  const create = v2.slice(v2.indexOf('async function createCompany(event)'), v2.indexOf('async function activateCompanyPackage('));
  assert.match(create, /const companyBody = \{\s*name: raw\.name,\s*slug: raw\.slug,\s*timezone: raw\.timezone \|\| "America\/Bogota",\s*plan: raw\.plan \|\| "standard",\s*\};/);
  assert.match(create, /apiPost\(`\$\{API\}\/companies`, companyBody\)/);
  assert.match(create, /apiPost\(`\$\{API\}\/companies\/\$\{companyId\}\/users`, \{\s*email: ownerEmail,\s*full_name: ownerFullName,\s*role: "company_admin",\s*password: ownerPassword,\s*status: "active",\s*\}\)/);
  assert.match(create, /if \(packageCode\) \{[\s\S]*activateCompanyPackage\(companyId, packageCode, false\)/);
  assert.ok(create.indexOf('activateCompanyPackage(companyId') < create.indexOf('/users`'), 'paquete antes que el dueño');
  assert.match(v2, /apiPost\(`\$\{API\}\/companies\/\$\{companyId\}\/activate-package`, \{ package_code: packageCode, settings: \{\} \}\)/);
  const status = v2.slice(v2.indexOf('async function updateCompanyStatus('), v2.indexOf('async function setCompanyStatus('));
  assert.match(status, /apiPatch\(`\$\{API\}\/companies\/\$\{companyId\}\/status`, body\)[\s\S]*apiPatch\(`\$\{API\}\/companies\/\$\{companyId\}`, body\)[\s\S]*apiPut\(`\$\{API\}\/companies\/\$\{companyId\}`, body\)/);
  assert.match(v2, /await setCompanyStatus\(company\.id, "deleted"\);/);
  assert.match(v2, /confirm\.disabled = input\.value !== company\.slug;/);
});

test('sin clave escrita genera una igual que Admin V2; sin dueño no sigue', async () => {
  const { ui, calls } = load((c) => ({ status: 200, body: c.url === '/api/v1/companies' ? { company: { id: 'c-2' } } : {} }));
  const out = await ui.createCompanyFlow({ name: 'X', slug: 'Mi Bar', owner_full_name: 'A', owner_email: 'a@b.co' });
  assert.match(out.temporaryPassword, /^Clonexa-mi-bar-[a-z0-9]{1,4}!$/);
  assert.equal(calls.length, 2, 'sin paquete no se llama activate-package');
  await assert.rejects(ui.createCompanyFlow({ name: 'X', slug: 'x', owner_full_name: '', owner_email: '' }), /Acceso Maestro/);
  await assert.rejects(ui.createCompanyFlow({ name: '', slug: 'x', owner_full_name: 'a', owner_email: 'a@b.co' }), /Nombre y slug/);
});

test('crear como Registrada agrega solo la marca de tipo (nuevo, al final)', async () => {
  const { ui, calls } = load((c) => ({ status: 200, body: c.url === '/api/v1/companies' ? { id: 'c-3' } : {} }));
  await ui.createCompanyFlow({ name: 'R', slug: 'r', owner_full_name: 'A', owner_email: 'a@b.co', owner_password: 'Clave-123!', kind: 'registrada' });
  assert.deepEqual(strip(calls).slice(-1), ['POST /admin-v2/api/companies/c-3/kind {"kind":"registrada","confirm":true}']);
});

test('cambiar estado: PATCH /status y, si falla, el mismo encadenamiento de v2', async () => {
  let { ui, calls } = load();
  await ui.updateCompanyStatus('c-1', 'inactive');
  assert.deepEqual(strip(calls), ['PATCH /api/v1/companies/c-1/status {"status":"inactive"}']);
  ({ ui, calls } = load((c) => ({ status: c.method === 'PUT' ? 200 : 404, body: {} })));
  await ui.updateCompanyStatus('c-1', 'active');
  assert.deepEqual(strip(calls), [
    'PATCH /api/v1/companies/c-1/status {"status":"active"}',
    'PATCH /api/v1/companies/c-1 {"status":"active"}',
    'PUT /api/v1/companies/c-1 {"status":"active"}',
  ]);
});

test('archivar: exige el slug exacto y manda status "deleted" como v2', async () => {
  const { ui, calls } = load();
  const company = { id: 'c-9', slug: 'bar-x', name: 'Bar X' };
  await assert.rejects(ui.archiveCompany(company, 'bar-X'), /slug exacto/);
  assert.equal(calls.length, 0);
  await ui.archiveCompany(company, 'bar-x');
  assert.deepEqual(strip(calls), ['PATCH /api/v1/companies/c-9/status {"status":"deleted"}']);
});

test('acciones nuevas: tipo, clonar y eliminar (simulación y ejecución)', async () => {
  const { ui, calls } = load();
  await ui.changeKind('c 1', 'demo');
  await ui.cloneDemo('c-1', { name: 'D', slug: 'd' });
  await ui.purge('c-1', true);
  await ui.purge('c-1', false, 'Bar X');
  assert.deepEqual(strip(calls), [
    'POST /admin-v2/api/companies/c%201/kind {"kind":"demo","confirm":false}',
    'POST /admin-v2/api/companies/c-1/clone-demo {"name":"D","slug":"d"}',
    'POST /admin-v2/api/companies/c-1/purge {"dry_run":true}',
    'POST /admin-v2/api/companies/c-1/purge {"dry_run":false,"confirm_name":"Bar X"}',
  ]);
});

const COMPANIES = [
  { id: 'r1', name: 'Asadero', slug: 'asadero', status: 'active', settings_json: { kind: 'registrada' } },
  { id: 'r2', name: 'Archivada Reg', slug: 'arch-reg', status: 'archived', settings_json: { kind: 'registrada' } },
  { id: 'd1', name: 'Demo <img src=x onerror=alert(1)>', slug: 'demo-1', status: 'inactive', settings_json: { kind: 'demo' } },
  { id: 'd2', name: 'Demo Vieja', slug: 'demo-vieja', status: 'deleted', settings_json: {} },
  { id: 'd3', name: 'Sin kind en lista', slug: 'sin-kind', status: 'active', settings_json: {} },
];
const OVERVIEW = { companies: [
  { id: 'r1', kind: 'registrada', state: 'conectada', state_reason: '2 usuarios conectados ahora', plan: 'Pro' },
  { id: 'd3', kind: 'registrada', state: 'activa_hoy', state_reason: 'Hoy' },
] };

test('pestañas Registradas y Demos: una empresa nunca aparece en las dos', () => {
  const { ui } = load();
  const reg = ui.visibleCompanies(COMPANIES, OVERVIEW, { tab: 'registrada', filter: 'all' }).map((c) => c.id);
  const demo = ui.visibleCompanies(COMPANIES, OVERVIEW, { tab: 'demo', filter: 'all' }).map((c) => c.id);
  assert.deepEqual(reg, ['r1', 'r2', 'd3'], 'sin kind guardado usa el del overview');
  assert.deepEqual(demo, ['d1', 'd2']);
  assert.equal(reg.filter((id) => demo.includes(id)).length, 0);
  assert.deepEqual({ ...ui.counts(COMPANIES, OVERVIEW) }, { registrada: 3, demo: 2 });
});

test('filtros de Admin V2 (Visibles / Todas / Activas / Inactivas / Archivadas) y buscador', () => {
  const { ui } = load();
  const ids = (filter, query = '') => ui.visibleCompanies(COMPANIES, OVERVIEW, { tab: 'demo', filter, query }).map((c) => c.id).join();
  assert.equal(ids('visible'), 'd1');
  assert.equal(ids('all'), 'd1,d2');
  assert.equal(ids('active'), '');
  assert.equal(ids('inactive'), 'd1');
  assert.equal(ids('archived'), 'd2', '"deleted" cuenta como archivada, igual que v2');
  assert.equal(ui.visibleCompanies(COMPANIES, OVERVIEW, { tab: 'registrada', filter: 'all', query: 'ASAD' }).map((c) => c.id).join(), 'r1');
  assert.equal(ui.visibleCompanies(COMPANIES, OVERVIEW, { tab: 'registrada', filter: 'all', query: 'arch-reg' }).map((c) => c.id).join(), 'r2');
});

test('la tabla lleva el semáforo, escapa nombres y ofrece eliminar solo donde se puede', () => {
  const { ui } = load();
  const html = ui.companiesTable(COMPANIES, OVERVIEW);
  assert.match(html, /vp-dot vp-dot-conectada/);
  assert.match(html, /2 usuarios conectados ahora/);
  assert.doesNotMatch(html, /<img src=x/);
  assert.match(html, /Demo &lt;img src=x onerror=alert\(1\)&gt;/);
  const row = (id) => html.slice(html.indexOf(`data-vpc-row="${id}"`), html.indexOf('</tr>', html.indexOf(`data-vpc-row="${id}"`)));
  assert.doesNotMatch(row('r1'), /data-vpc-purge/, 'registrada activa: no se elimina');
  assert.match(row('r2'), /data-vpc-purge="r2"/, 'registrada archivada: sí');
  assert.match(row('d1'), /data-vpc-purge="d1"/, 'demo en cualquier estado');
  assert.match(row('r1'), /data-vpc-kind="r1" data-kind="demo"/);
  assert.match(row('d1'), /data-vpc-kind="d1" data-kind="registrada"/);
  assert.match(row('r1'), /href="#empresa\/r1"/);
  assert.match(row('r2'), /data-status="active">Reactivar/);
});

test('modales: archivar pide slug, eliminar muestra la simulación y pide el nombre', () => {
  const { ui } = load();
  const company = { id: 'd1', name: 'Demo <b>', slug: 'demo-1' };
  assert.match(ui.modal({ type: 'archive', company }), /Escribe el slug exacto: <b>demo-1<\/b>/);
  const purge = ui.modal({ type: 'purge', company, plan: { total_rows: 12, tables: [{ table: 'hospitality_product_images', rows: 2, images: true }] } });
  assert.match(purge, /<b>12<\/b> filas de 1 tablas/);
  assert.match(purge, /hospitality_product_images<\/b><small>2 fila\(s\) · imágenes/);
  assert.match(purge, /Escribe el nombre exacto: <b>Demo &lt;b&gt;<\/b>/);
  assert.match(ui.modal({ type: 'purge', company, plan: null }), /Simulando/);
});
