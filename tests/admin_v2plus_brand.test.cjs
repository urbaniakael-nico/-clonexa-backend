// Consola v2+ · Estudio de marca (Fase 4): editor. Seleccionar una pieza desde
// la vista previa, editar un degradado, armar un fondo por capas, paleta desde
// el logo (aplicar y deshacer), restablecer, guardia de lectura y la vista.
const { readFileSync } = require('node:fs');
const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');

const source = readFileSync('app/web/admin_v2plus_brand.js', 'utf8');
const plain = (v) => JSON.parse(JSON.stringify(v));
const REGISTRY = JSON.parse(readFileSync('app/web/brand_registry.json', 'utf8'));

function load(responder = () => ({ status: 200, body: {} })) {
  const calls = [];
  const fetch = async (url, options = {}) => {
    calls.push({ url, method: options.method || 'GET', body: typeof options.body === 'string' ? JSON.parse(options.body || '{}') : options.body });
    const { status, body } = responder({ url, options });
    return { status, ok: status >= 200 && status < 300, json: async () => body };
  };
  const listeners = {};
  const window = { location: { origin: 'https://clonexa.app', href: '' }, addEventListener: (t, f) => { listeners[`w:${t}`] = f; } };
  const document = { addEventListener: (t, f) => { listeners[t] = f; }, head: null, createElement: () => ({ style: {} }) };
  const ctx = vm.createContext({ window, document, fetch, JSON, Object, Array, String, Number, Math, Promise, Error, Map, Set, setTimeout: (f) => f(), clearTimeout: () => {}, encodeURIComponent, CSS: { escape: (s) => s }, FormData: class {} });
  vm.runInContext(source, ctx);
  return { S: window.CxBrandStudio, sections: window.CxConsoleSections, calls, listeners, window };
}

function tokens() {
  return {
    theme: { colors: { primary: '#e3122f', secondary: '#9d17ff', background: '#0b0507', surface: '#1a1214', text: '#f4eef0', text_muted: '#a99da0', success: '#22c55e', warning: '#f59e0b', danger: '#ef4444' },
      font: { family: 'Manrope', size: 15, heading_weight: 700 }, radius: 16, shadow: 45, glow: 35, logo: null },
    backgrounds: { general: { base: { kind: 'solid', color: '#0b0507' }, image: null, veil: null }, ingreso: { inherit: true }, mesero: { inherit: true }, cocina: { inherit: true }, caja: { inherit: true } },
    components: { boton_principal: { fill: { kind: 'solid', color: '#e3122f' } } },
    pieces: { 'caja.cobrar': { fill: { kind: 'solid', color: '#00ff00' }, text: { color: '#111111' } } },
  };
}

test('tocar una pieza en la vista previa la selecciona; un componente o el fondo también', () => {
  const { S } = load();
  assert.deepEqual(plain(S.selectFromPreview({ piece: 'caja.cobrar' }, 'caja')), { kind: 'piece', key: 'caja.cobrar' });
  assert.deepEqual(plain(S.selectFromPreview({ component: 'tarjeta' }, 'caja')), { kind: 'component', key: 'tarjeta' });
  assert.deepEqual(plain(S.selectFromPreview({ background: 'mesero' }, 'mesero')), { kind: 'background', key: 'mesero' });
});

test('el mensaje "select" del iframe cambia la selección solo si viene de ese iframe y del mismo origen', () => {
  const { S } = load();
  const frameWin = {};
  const root = { querySelector: (s) => (s === '[data-vpb-frame]' ? { contentWindow: frameWin } : null), querySelectorAll: () => [] };
  S._ctx({ active: () => false, root: () => root });
  S.model.sel = { kind: 'theme', key: 'colors' };
  S.onMessage({ source: {}, origin: 'https://clonexa.app', data: { type: 'select', target: { piece: 'mesero.enviar_pedido' } } });
  assert.equal(S.model.sel.kind, 'theme', 'de otra ventana: se ignora');
  S.onMessage({ source: frameWin, origin: 'https://evil.example', data: { type: 'select', target: { piece: 'mesero.enviar_pedido' } } });
  assert.equal(S.model.sel.kind, 'theme', 'de otro origen: se ignora');
  S.onMessage({ source: frameWin, origin: 'https://clonexa.app', data: { type: 'select', target: { piece: 'mesero.enviar_pedido' } } });
  assert.deepEqual(plain(S.model.sel), { kind: 'piece', key: 'mesero.enviar_pedido' });
});

test('editor de degradado: tipo, ángulo con rango, 2 o 3 paradas ordenadas, color solo hex', () => {
  const { S } = load();
  let g = S.editGradient(null, {});
  assert.equal(g.stops.length, 2);
  g = S.editGradient(g, { addStop: true });
  assert.equal(g.stops.length, 3);
  assert.equal(S.editGradient(g, { addStop: true }).stops.length, 3, 'máximo 3');
  g = S.editGradient(g, { angle: 999, type: 'radial' });
  assert.equal(g.angle, 360);
  assert.equal(g.type, 'radial');
  g = S.editGradient(g, { stop: { index: 0, color: 'url(javascript:x)' } });
  assert.notEqual(g.stops[0].color, 'url(javascript:x)', 'solo hex');
  g = S.editGradient(g, { stop: { index: 0, color: '#ABCDEF', at: 90 } });
  assert.deepEqual(plain(g.stops.map((s) => s.at)), [50, 90, 100], 'ordenadas');
  assert.equal(S.editGradient(g, { removeStop: 1 }).stops.length, 2);
  assert.equal(S.editGradient(S.editGradient(null, {}), { removeStop: 0 }).stops.length, 2, 'mínimo 2');
  assert.match(S.gradientCss(g), /^radial-gradient\(circle at center,/);
});

test('fondo por capas: base, imagen y velo; heredar y restablecer', () => {
  const { S } = load();
  let t = tokens();
  t = S.setBackgroundLayer(t, 'caja', 'base', { kind: 'gradient', gradient: S.editGradient(null, {}) });
  t = S.setBackgroundLayer(t, 'caja', 'image', { id: '11111111-2222-3333-4444-555555555555', mode: 'watermark', size: 30, position: 'bottom right', opacity: 40 });
  t = S.setBackgroundLayer(t, 'caja', 'veil', { gradient: S.editGradient(null, {}), darken: 30, blur: 6, opacity: 50 });
  const bg = t.backgrounds.caja;
  assert.equal(bg.inherit, undefined);
  assert.equal(bg.base.kind, 'gradient');
  assert.equal(bg.image.mode, 'watermark');
  assert.equal(bg.veil.blur, 6);
  assert.deepEqual(plain(tokens().backgrounds.caja), { inherit: true }, 'no muta el original');
  t = S.setBackgroundLayer(t, 'caja', 'veil', null);
  assert.equal(t.backgrounds.caja.veil, null);
  t = S.resetSelection(t, { kind: 'background', key: 'caja' });
  assert.deepEqual(plain(t.backgrounds.caja), { inherit: true });
  t = S.setInherit(t, 'mesero', false);
  assert.deepEqual(plain(t.backgrounds.mesero), plain(tokens().backgrounds.general), 'arranca desde el general');
});

test('colores desde el logo: se aplican con un clic y se deshacen', () => {
  const { S } = load();
  const before = tokens();
  const proposal = { primary: '#123456', secondary: '#654321', background: '#ffffff', surface: '#f0f0f0', text: '#111111', text_muted: '#555555', success: '#22c55e', warning: '#f59e0b', danger: 'rojo' };
  const { tokens: after, undo } = S.applyPalette(before, proposal);
  assert.equal(after.theme.colors.primary, '#123456');
  assert.equal(after.theme.colors.danger, '#ef4444', 'lo que no es hex no entra');
  assert.deepEqual(plain(after.backgrounds.general.base), { kind: 'solid', color: '#ffffff' }, 'el fondo general toma el fondo propuesto');
  const undone = S.undoPalette(after, undo);
  assert.deepEqual(plain(undone.theme.colors), plain(before.theme.colors));
  assert.deepEqual(plain(undone.backgrounds.general.base), plain(before.backgrounds.general.base), 'deshacer también restaura el fondo');
});

test('las rutas de las piezas respetan el punto de su clave', () => {
  const { S } = load();
  const t = S.setPath(tokens(), 'pieces.caja.cobrar.hover.glow', 60);
  assert.equal(t.pieces['caja.cobrar'].hover.glow, 60);
  assert.equal(t.pieces.caja, undefined, 'no crea pieces.caja');
  assert.equal(S.getPath(t, 'pieces.caja.cobrar.fill.color'), '#00ff00');
  assert.equal(S.setPath(t, 'pieces.caja.cobrar.fill', undefined).pieces['caja.cobrar'].fill, undefined);
});

test('restablecer una pieza o un componente a lo heredado', () => {
  const { S } = load();
  const t = tokens();
  assert.equal(S.resetSelection(t, { kind: 'piece', key: 'caja.cobrar' }).pieces['caja.cobrar'], undefined);
  assert.equal(S.resetSelection(t, { kind: 'component', key: 'boton_principal' }).components.boton_principal, undefined);
  assert.ok(t.pieces['caja.cobrar'], 'no muta el original');
});

test('guardia de lectura: avisa por debajo de AA y "Corregir" lo arregla', () => {
  const { S } = load();
  const t = tokens();
  t.theme.colors.text = '#222222';
  t.pieces['caja.cobrar'] = { fill: { kind: 'solid', color: '#00ff00' }, text: { color: '#33ff33' } };
  const issues = S.contrastIssues(t, REGISTRY);
  const ids = issues.map((i) => i.id);
  assert.ok(ids.includes('text-general'));
  assert.ok(ids.includes('piece-caja.cobrar'));
  assert.match(issues.find((i) => i.id === 'piece-caja.cobrar').label, /Cobrar/);
  let fixed = t;
  for (const id of ['text-general', 'piece-caja.cobrar']) fixed = S.applyFix(fixed, S.contrastIssues(fixed, REGISTRY).find((i) => i.id === id));
  const left = S.contrastIssues(fixed, REGISTRY).map((i) => i.id);
  assert.ok(!left.includes('text-general') && !left.includes('piece-caja.cobrar'));
  // con imagen y velo: primero ajusta el velo
  const v = tokens();
  v.theme.colors.text = '#333333';
  v.backgrounds.general = { base: { kind: 'solid', color: '#000000' }, image: { id: '11111111-2222-3333-4444-555555555555', mode: 'cover' },
    veil: { gradient: { type: 'linear', angle: 180, stops: [{ color: '#000000', at: 0 }, { color: '#000000', at: 100 }] }, darken: 0, blur: 0, opacity: 20 } };
  const issue = S.contrastIssues(v, REGISTRY).find((i) => i.id === 'text-general');
  const out = S.applyFix(v, issue);
  assert.ok(out.backgrounds.general.veil.opacity >= 85 && out.backgrounds.general.veil.darken >= 55);
});

test('vista: elegir empresa, tres columnas, árbol con piezas, iframe del mismo origen y sin style=""', async () => {
  const draft = tokens();
  const { S, sections } = load(({ url }) => ({ status: 200, body: url.endsWith('/templates') ? { templates: [] } : {
    company: { id: 'c1', name: 'ASADERO EL SOCIO', kind: 'registrada' }, draft: { version: 2, tokens: draft }, published: { version: 1 }, history: [{ version: 2, status: 'draft' }, { version: 1, status: 'published' }],
    registry: REGISTRY, fonts: ['Inter', 'Manrope'], storage: { configured: true, used_bytes: 0, quota_bytes: 26214400 }, images: [] } }));
  let html = '';
  const root = { get innerHTML() { return html; }, set innerHTML(v) { html = v; }, querySelector: () => null, querySelectorAll: () => [] };
  const ov = { companies: [{ id: 'c1', name: 'ASADERO EL SOCIO', kind: 'registrada', status: 'active' }, { id: 'v', name: 'Vieja', status: 'archived' }] };
  sections.brand.mount({ root: () => root, active: () => true, overview: () => ov, toast: () => {}, params: {} });
  assert.match(html, /Elige la empresa/);
  assert.match(html, /data-vpb-pick="c1"/);
  assert.doesNotMatch(html, /Vieja/, 'sin archivadas');
  sections.brand.mount({ root: () => root, active: () => true, overview: () => ov, toast: () => {}, params: { companyId: 'c1' } });
  await new Promise((r) => setImmediate(r));
  await new Promise((r) => setImmediate(r));
  assert.match(html, /class="vp-brand-layout"/);
  assert.match(html, /Marca general<\/h3><p class="vp-brand-note">Aplica a todas las pantallas\.[\s\S]*Esta pantalla · Panel principal<\/h3>[\s\S]*Tipos de pieza<\/h3><p class="vp-brand-note">Aplica a todos los de ese tipo/);
  assert.doesNotMatch(html, /<h3>Fondos<\/h3>|<h3>Piezas<\/h3>/, 'ya no hay listas con todas las pantallas');
  for (const p of REGISTRY.pieces.filter((x) => x.screen === 'portal_dashboard')) assert.ok(html.includes(`data-vpb-sel="piece|${p.key}"`), p.key);
  assert.ok(!html.includes('data-vpb-sel="piece|caja.cobrar"'), 'piezas de otra pantalla no aparecen');
  assert.match(html, /<iframe class="vp-brand-frame" data-vpb-frame title="Vista previa: Panel principal" src="\/admin-v2\/brand-preview\/c1\?screen=portal_dashboard">/, 'abre en el panel principal');
  assert.match(html, /Celular[\s\S]*Tableta[\s\S]*Pantalla grande/);
  assert.match(html, /Guardar borrador[\s\S]*Publicar/);
  assert.match(html, /publicada la versión 1/);
  assert.doesNotMatch(html, /\sstyle="/);
  S.model.sel = { kind: 'piece', key: 'caja.cobrar' };
  S.draw(false);
  assert.match(html, /Cobrar \(método de pago\)/);
  assert.match(html, /Normal[\s\S]*Cursor encima[\s\S]*Presionado/);
  assert.match(html, /Restablecer a lo heredado/);
  S.model.sel = { kind: 'background', key: 'caja' };
  S.model.tokens.backgrounds.caja = { own: true };
  S.draw(false);
  assert.match(html, /Fondo de esta pantalla · Caja[\s\S]*data-vpb-usegeneral="caja"[\s\S]*Usar el fondo general[\s\S]*Su fondo de siempre \(como hoy\)[\s\S]*Personalizado/);
  S.model.sel = { kind: 'background', key: 'portal_dashboard' };
  S.draw(false);
  assert.match(html, /data-vpb-usegeneral="portal_dashboard" checked[\s\S]*Estás editando el <b>fondo general<\/b>/, 'con el interruptor encendido se edita el fondo general');
  assert.doesNotMatch(html, /Su fondo de siempre/, 'el panel principal no tiene fondo propio de panel');
});

test('una sola lista de pantallas: las pestañas, en orden y con separador entre familias', async () => {
  const draft = tokens();
  const available = { screens: ['caja', 'mesero', 'portal_modulo', 'portal_ingreso', 'portal_dashboard'] };
  const { S, sections } = load(() => ({ status: 200, body: {
    company: { id: 'a1', name: 'ASADERO', kind: 'registrada' }, draft: { version: 1, tokens: draft }, published: null, history: [],
    available, registry: REGISTRY, fonts: ['Inter'], storage: { configured: true, used_bytes: 0, quota_bytes: 1 }, images: [] } }));
  let html = '';
  const root = { get innerHTML() { return html; }, set innerHTML(v) { html = v; }, querySelector: () => null, querySelectorAll: () => [] };
  sections.brand.mount({ root: () => root, active: () => true, overview: () => ({ companies: [] }), toast: () => {}, params: { companyId: 'a1' } });
  await new Promise((r) => setImmediate(r));
  await new Promise((r) => setImmediate(r));
  const tabs = [...html.matchAll(/data-vpb-screen="([a-z_]+)">([^<]+)</g)].map((m) => `${m[1]}:${m[2]}`);
  assert.deepEqual(tabs, ['portal_dashboard:Panel principal', 'portal_ingreso:Ingreso', 'portal_modulo:Vista de módulo', 'mesero:Mesero', 'caja:Caja'], 'una sola vez cada pantalla, Panel principal primero');
  assert.equal((html.match(/data-vpb-screen="/g) || []).length, 5, 'ninguna pantalla repetida en otro lado');
  assert.equal((html.match(/vp-brand-tab-sep/g) || []).length, 1, 'separador entre el portal y el restaurante');
  assert.match(html, /Toca cualquier parte del panel para editarla\./);
  assert.ok(html.includes('data-vpb-sel="background|portal_dashboard"') && !html.includes('data-vpb-sel="background|caja"'), 'un solo fondo: el de la pantalla elegida');
  assert.equal(S.model.screen, 'portal_dashboard', 'la pantalla inicial es el Panel principal');
  assert.equal(S.model.size, 'desktop', 'el panel principal en pantalla grande');
  // Botones: Cambiar empresa | Más (Plantillas, Copiar, Historial) | Compartir, Guardar, Publicar
  assert.match(html, /vp-brand-actions-left">[\s\S]*Cambiar empresa[\s\S]*<summary class="vp-btn">Más ▾<\/summary>[\s\S]*Plantillas[\s\S]*Copiar de otra empresa[\s\S]*Historial[\s\S]*vp-brand-actions-right">[\s\S]*Compartir vista previa[\s\S]*Guardar borrador[\s\S]*Publicar/);
  // Cada elemento del panel izquierdo trae su descripción de una línea.
  const nodes = [...html.matchAll(/<button type="button" class="vp-brand-node[^"]*" data-vpb-sel="[^"]+">\s*<b>[^<]+(?:<span[^>]*><\/span>)?<\/b><small>([^<]+)<\/small>/g)];
  assert.ok(nodes.length >= 15 && nodes.every((m) => m[1].trim().length > 10), 'descripción en cada elemento');
});

test('el bloque "Esta pantalla" cambia con la pestaña; el tamaño también', async () => {
  const draft = tokens();
  const available = { screens: ['portal_dashboard', 'portal_ingreso', 'portal_modulo', 'mesero', 'caja'] };
  const { S, sections } = load(() => ({ status: 200, body: {
    company: { id: 'a1', name: 'ASADERO', kind: 'registrada' }, draft: { version: 1, tokens: draft }, published: null, history: [],
    available, registry: REGISTRY, fonts: ['Inter'], storage: { configured: true, used_bytes: 0, quota_bytes: 1 }, images: [] } }));
  let html = '';
  const root = { get innerHTML() { return html; }, set innerHTML(v) { html = v; }, querySelector: () => null, querySelectorAll: () => [] };
  sections.brand.mount({ root: () => root, active: () => true, overview: () => ({ companies: [] }), toast: () => {}, params: { companyId: 'a1' } });
  await new Promise((r) => setImmediate(r));
  await new Promise((r) => setImmediate(r));
  S.model.sel = { kind: 'piece', key: 'portal.menu' };
  S.setScreen('mesero');
  assert.match(html, /Esta pantalla · Mesero<\/h3>/);
  assert.ok(html.includes('data-vpb-sel="piece|mesero.enviar_pedido"') && !html.includes('data-vpb-sel="piece|portal.menu"'), 'piezas del mesero, no del portal');
  assert.deepEqual(plain(S.model.sel), { kind: 'background', key: 'mesero' }, 'lo elegido pasa al fondo de la nueva pantalla');
  assert.equal(S.model.size, 'phone', 'el mesero en celular');
  assert.match(html, /src="\/admin-v2\/brand-preview\/a1\?screen=mesero"/);
  S.setScreen('portal_modulo');
  assert.match(html, /Esta pantalla · Vista de módulo<\/h3>/);
  assert.ok(html.includes('data-vpb-sel="piece|portal.barra_lateral"') && !html.includes('data-vpb-sel="piece|portal.servicio"'), 'la vista de módulo trae sus piezas');
  assert.equal(S.model.size, 'desktop');
  // Aviso de lectura compacto que se despliega al tocarlo.
  S.model.tokens.theme.colors.text = '#222222';
  S.model.guardOpen = false;
  S.draw(false);
  assert.match(html, /data-vpb-guard>⚠ \d+ avisos? de lectura<\/button>/);
  assert.doesNotMatch(html, /data-vpb-fix=/, 'cerrado no ocupa espacio');
  S.model.guardOpen = true;
  S.draw(false);
  assert.match(html, /data-vpb-fix="text-general"/);
});

test('una empresa sin waiter_ordering (Velvet) no ve pantallas de restaurante en el estudio', async () => {
  const draft = tokens();
  const available = { screens: ['portal_dashboard', 'portal_modulo', 'portal_ingreso'], mini_types: [], segments: {} };
  const { S, sections } = load(() => ({ status: 200, body: {
    company: { id: 'v1', name: 'Velvet', kind: 'registrada' }, draft: { version: 1, tokens: draft }, published: null, history: [{ version: 1, status: 'draft' }],
    available, registry: REGISTRY, fonts: ['Inter'], storage: { configured: true, used_bytes: 0, quota_bytes: 1 }, images: [] } }));
  let html = '';
  const root = { get innerHTML() { return html; }, set innerHTML(v) { html = v; }, querySelector: () => null, querySelectorAll: () => [] };
  sections.brand.mount({ root: () => root, active: () => true, overview: () => ({ companies: [] }), toast: () => {}, params: { companyId: 'v1' } });
  await new Promise((r) => setImmediate(r));
  await new Promise((r) => setImmediate(r));
  assert.match(html, /data-vpb-screen="portal_dashboard"[\s\S]*data-vpb-screen="portal_ingreso"[\s\S]*data-vpb-screen="portal_modulo"/);
  for (const k of ['ingreso', 'mesero', 'cocina', 'caja', 'mini_ingreso', 'mini_panel']) {
    assert.ok(!html.includes(`data-vpb-screen="${k}"`), `sin pantalla ${k}`);
    assert.ok(!html.includes(`data-vpb-sel="background|${k}"`), `sin fondo ${k}`);
  }
  assert.doesNotMatch(html, /Panel Caja|data-vpb-sel="piece\|caja\./, 'nada de la caja');
  assert.match(html, /data-vpb-sel="piece\|portal\.barra_lateral"/);
  assert.doesNotMatch(html, /Alcance de la marca/, 'sin paneles no hay alcance que elegir');
  assert.deepEqual(plain(S.screensFor({ registry: REGISTRY, available: { screens: ['caja', 'portal_dashboard'] } }).map((x) => x.key)), ['portal_dashboard', 'caja'], 'primero el panel principal');
});

test('modo de fondo: heredar, propio del panel o personalizado', () => {
  const { S } = load();
  let t = tokens();
  t = S.setBgMode(t, 'caja', 'own');
  assert.deepEqual(plain(t.backgrounds.caja), { own: true });
  t = S.setBgMode(t, 'caja', 'custom');
  assert.equal(t.backgrounds.caja.base.kind, 'solid');
  t.backgrounds.general.base = { kind: 'preset' };
  t = S.setBgMode(t, 'mesero', 'custom');
  assert.deepEqual(plain(t.backgrounds.mesero.base), { kind: 'solid', color: '#0b0507' }, 'el estilo del panel principal no se copia a un panel');
  t = S.setBgMode(t, 'caja', 'inherit');
  assert.deepEqual(plain(t.backgrounds.caja), { inherit: true });
  t = S.setBackgroundLayer(S.setBgMode(t, 'cocina', 'own'), 'cocina', 'veil', null);
  assert.equal(t.backgrounds.cocina.own, undefined, 'editar una capa sale del fondo propio');
});
