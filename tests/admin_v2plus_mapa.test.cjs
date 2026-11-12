// Consola v2+ · Landing → Mapa comercial (Leaflet + OpenStreetMap, solo Admin V2).
const { readFileSync } = require('node:fs');
const { createHash } = require('node:crypto');
const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');

const MAPA = readFileSync('app/web/admin_v2plus_mapa.js', 'utf8');
const ADMIN = readFileSync('app/web/admin_v2plus_admin.js', 'utf8');

function fakeL() {
  const made = { maps: [], markers: [], circles: [], polygons: [], groups: [], tiles: [] };
  const layer = (kind, args) => {
    const l = { kind, args, tooltip: '', handlers: {}, bindTooltip(t) { this.tooltip = t; return this; }, on(e, f) { this.handlers[e] = f; return this; } };
    return l;
  };
  const L = {
    map(el, opts) {
      const m = { el, opts, layers: new Set(), view: null, handlers: {}, attributionControl: { setPrefix(p) { m.prefix = p; } },
        on(e, f) { this.handlers[e] = f; }, hasLayer(g) { return this.layers.has(g); }, setView(c, z) { this.view = [c, z]; }, fitBounds(b) { this.view = ['fit', b]; }, remove() {} };
      made.maps.push(m);
      return m;
    },
    latLngBounds(b) { return { b, pad: () => ({ b }) }; },
    tileLayer(url, o) { const t = { url, o, addTo(m) { made.tiles.push(this); return this; } }; return t; },
    layerGroup() {
      const g = { items: [], addLayer(x) { this.items.push(x); return this; }, addTo(m) { m.layers.add(this); this.map = m; return this; }, remove() { if (this.map) this.map.layers.delete(this); } };
      made.groups.push(g);
      return g;
    },
    circleMarker(c, o) { const l = layer('marker', { c, o }); made.markers.push(l); return l; },
    circle(c, o) { const l = layer('circle', { c, o }); made.circles.push(l); return l; },
    polygon(p, o) { const l = layer('polygon', { p, o }); made.polygons.push(l); return l; },
  };
  return { L, made };
}

function el(attrs = {}) {
  const children = {};
  const node = {
    innerHTML: '', listeners: {}, attrs,
    querySelector(sel) { if (!children[sel]) children[sel] = el(); return children[sel]; },
    addEventListener(type, fn) { this.listeners[type] = fn; },
    getAttribute(k) { return attrs[k]; },
  };
  return node;
}

function load({ responder, withL = true } = {}) {
  const calls = [];
  const { L, made } = fakeL();
  const fetch = async (url, options = {}) => {
    calls.push(`${options.method || 'GET'} ${url}${options.body ? ` ${options.body}` : ''}`);
    const { status, body } = (responder || (() => ({ status: 200, body: SAMPLE })))(url, options);
    return { status, ok: status >= 200 && status < 300, json: async () => body };
  };
  const window = { location: { href: '' }, L: withL ? L : undefined };
  const document = { head: { appendChild() {} }, createElement: () => ({ setAttribute() {} }), querySelector: () => null, addEventListener() {} };
  const ctx = vm.createContext({ window, document, fetch, JSON, Object, Array, String, Math, Number, Promise, Error, Date, Set, Map, URLSearchParams, encodeURIComponent, FormData: class {} });
  vm.runInContext(MAPA, ctx);
  return { M: window.CxConsoleMapa, calls, made, window };
}

const SAMPLE = {
  cards: { prospectos: 14, con_correo: 2, enviados: 10, abrieron: 3, respondieron: 1, demos: 1, clientes: 0 },
  zones: [
    { id: 1, slug: 'kennedy-central', name: 'Kennedy Central', group_name: 'Kennedy', kind: 'circle', center_lat: 4.62, center_lng: -74.15, radius_m: 750, active: true, prospectos: 14, enviados: 10, abrieron: 3, respondieron: 1, demos: 1, clientes: 0, puntaje: 99 },
    { id: 2, slug: 'poli', name: 'Polígono <x>', group_name: '', kind: 'polygon', polygon: [[4.6, -74.1], [4.7, -74.1], [4.7, -74.0]], center_lat: 4.6, center_lng: -74.1, radius_m: 700, active: true, prospectos: 0, enviados: 0, abrieron: 0, respondieron: 0, demos: 0, clientes: 0, puntaje: 0 },
  ],
  pins: [
    { id: 'a', name: 'Panadería <b>La Espiga</b>', business_type: 'panaderia', tipo: 'Panadería', status: 'abrio', lat: 4.621, lng: -74.152, email: 'p•••@laespiga.com.co' },
    { id: 'b', name: 'Bar Uno', business_type: 'bar', tipo: 'Bar', status: 'baja', lat: 4.622, lng: -74.151, email: '' },
  ],
  heat_visits: [{ city: 'Bogotá', region: 'Bogota D.C.', country: 'CO', lat: 4.61, lng: -74.08, total: 20 }, { city: 'Medellín', region: '', lat: 6.24, lng: -75.57, total: 5 }],
  heat_leads: [{ lat: 4.621, lng: -74.152, total: 1 }],
};

test('URL del mapa con filtros (zona, tipo, estado, fechas)', () => {
  const { M } = load();
  assert.equal(M.mapUrl({}), '/api/v1/prospecting/admin/map');
  assert.equal(M.mapUrl({ zone_id: '1', tipo: 'bar', estado: 'respondio', desde: '2026-11-01', hasta: '2026-11-10' }),
    '/api/v1/prospecting/admin/map?zone_id=1&tipo=bar&estado=respondio&desde=2026-11-01&hasta=2026-11-10');
});

test('tarjetas: prospectos, correos, aperturas, respuestas, demos y clientes con %', () => {
  const { M } = load();
  const html = M.cards(SAMPLE);
  for (const t of ['Prospectos', 'Correos enviados', 'Abrieron la landing', 'Respondieron', 'Demos', 'Clientes', '30%', '10%', '2 con correo']) assert.match(html, new RegExp(t));
  const zt = M.zonesTable(SAMPLE);
  assert.match(zt, /% por zona/);
  assert.match(zt, /Polígono &lt;x&gt;/);
  assert.doesNotMatch(zt, /<x>/);
});

test('pane: filtros, capas, leyenda, atribución OSM y DB-IP; sin estilos en línea', () => {
  const { M } = load();
  M.model.data = SAMPLE;
  const html = M.pane();
  for (const t of ['name="zone_id"', 'name="tipo"', 'name="estado"', 'name="desde"', 'name="hasta"', 'data-vpm-layer="prospectos"', 'data-vpm-layer="visitas"',
    'data-vpm-layer="leads"', 'data-vpm-layer="zonas"', 'OpenStreetMap', 'IP Geolocation by DB-IP', 'precisión de ciudad', 'data-vpm-jump="colombia"']) assert.ok(html.includes(t), t);
  assert.doesNotMatch(html, /\sstyle=/);
  assert.doesNotMatch(html, /\son[a-z]+=/);
});

test('ficha: correo completo (solo Admin V2), historial, Google Maps solo https', () => {
  const { M } = load();
  M.model.detail = { prospect: { id: 'a', name: 'La <i>Espiga</i>', status: 'respondio', tipo: 'Panadería', email: 'pedidos@laespiga.com.co', code: 'K7M2QD',
    maps_url: 'https://www.google.com/maps/search/?api=1&query=La%20Espiga&query_place_id=place-0', website: 'javascript:alert(1)', email_source_url: 'https://laespiga.com.co/contacto' },
    history: [{ kind: 'inicial', channel: 'email', status: 'enviado', subject: 'La Espiga: tu carta', sent_at: '2026-11-10T13:00:00Z' }, { kind: 'respuesta', channel: 'email', status: 'registrado', created_at: '2026-11-10T15:00:00Z' }] };
  const html = M.detailPanel();
  assert.match(html, /pedidos@laespiga\.com\.co/);
  assert.match(html, /Abrir en Google Maps/);
  assert.match(html, /query_place_id=place-0/);
  assert.match(html, /De dónde salió el correo/);
  assert.doesNotMatch(html, /javascript:/);
  assert.match(html, /La &lt;i&gt;Espiga&lt;\/i&gt;/);
  assert.match(html, /Correo inicial/);
  assert.match(html, /Respondió/);
  assert.match(html, /target="_blank" rel="noopener noreferrer"/);
});

test('capas: un pin por prospecto con color de su estado; calor de visitas por ciudad; zonas con puntaje', () => {
  const { M, made, window } = load();
  M.model.data = SAMPLE;
  const map = window.L.map({}, {});
  M._setMap(map);
  M.drawLayers(window.L);
  assert.equal(made.markers.length, 2);
  assert.equal(made.markers[0].args.o.fillColor, M.STATUS.abrio[1]);
  assert.equal(made.markers[1].args.o.fillColor, M.STATUS.baja[1]);
  assert.match(made.markers[0].tooltip, /Panadería &lt;b&gt;La Espiga&lt;\/b&gt;/);
  assert.match(made.markers[0].tooltip, /p•••@laespiga\.com\.co/);
  const heat = made.circles.filter((c) => c.args.o.fillColor === '#ff2d6f' && c.args.o.stroke === false);
  assert.equal(heat.length, 2);
  assert.ok(heat[0].args.o.radius > heat[1].args.o.radius, 'más visitas, círculo más grande');
  assert.match(heat[0].tooltip, /Bogotá, Bogota D\.C\.: 20 visitas/);
  assert.equal(made.polygons.length, 1);
  assert.match(made.circles.find((c) => c.args.o.dashArray).tooltip, /puntaje 99/);
  assert.equal(map.layers.size, 4, 'las 4 capas prendidas');
});

test('montar: abre en Bogotá, límites de Colombia y carga el mapa del servidor', async () => {
  const { M, made, calls } = load();
  const host = el();
  M.mount(host);
  await new Promise((r) => setTimeout(r, 0));
  await new Promise((r) => setTimeout(r, 0));
  assert.equal(made.maps.length, 1);
  assert.deepEqual(Array.from(made.maps[0].opts.center), [4.628, -74.142]);
  assert.equal(made.maps[0].opts.zoom, 13);
  assert.match(made.tiles[0].url, /^https:\/\/tile\.openstreetmap\.org\//);
  assert.match(made.tiles[0].o.attribution, /OpenStreetMap/);
  assert.ok(calls.includes('GET /api/v1/prospecting/admin/map'));
  assert.ok(host.listeners.click && host.listeners.submit && host.listeners.change);
  // tocar el mapa con "Nueva zona" abierto llena latitud y longitud
  M.model.newZone = { radius_m: 700 };
  made.maps[0].handlers.click({ latlng: { lat: 4.6123456, lng: -74.1234567 } });
  assert.equal(M.model.newZone.center_lat, 4.61235);
  assert.equal(M.model.newZone.center_lng, -74.12346);
});

test('sin sesión: 401 lleva al ingreso de v2+', async () => {
  const { M, window } = load({ responder: () => ({ status: 401, body: {} }) });
  await assert.rejects(M.api.map({}));
  assert.equal(window.location.href, '/admin-v2plus/login');
});

test('Landing tiene la pestaña Mapa comercial y monta el módulo', () => {
  assert.match(ADMIN, /\["mapa", "Mapa comercial"\]/);
  assert.match(ADMIN, /data-vpm-host/);
  assert.match(ADMIN, /window\.CxConsoleMapa\.mount/);
  const html = readFileSync('app/web/admin_v2plus.html', 'utf8');
  assert.match(html, /<script src="\/admin-v2plus-mapa\.js"><\/script>\s*<script src="\/admin-v2plus-admin\.js"><\/script>/);
});

test('Leaflet local sin cambios (SRI oficial 1.9.4) y con su ruta', () => {
  const sri = (f) => `sha256-${createHash('sha256').update(readFileSync(f)).digest('base64')}`;
  assert.equal(sri('app/web/vendor/leaflet-1.9.4.js'), 'sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=');
  assert.equal(sri('app/web/vendor/leaflet-1.9.4.css'), 'sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=');
  const routes = readFileSync('app/web/admin_v2plus_routes.py', 'utf8');
  assert.match(routes, /"\/admin-v2plus-leaflet\.js"/);
  assert.match(routes, /"\/admin-v2plus-leaflet\.css"/);
  assert.match(routes, /"\/admin-v2plus-mapa\.js"/);
});

test('025p nichos: filtro, tabla por nicho, color e ícono por nicho', () => {
  const { M, made, window } = load();
  assert.equal(M.mapUrl({ nicho: 'taller', tipo: 'fabrica' }), '/api/v1/prospecting/admin/map?nicho=taller&tipo=fabrica');
  const data = { ...SAMPLE, niches: [{ key: 'taller', label: 'Talleres y fábricas', icon: '🧵', page: '/talleres-y-fabricas', priority: 1, prospectos: 15, enviados: 4, abrieron: 1, respondieron: 1, demos: 0, clientes: 0, puntaje: 28 },
    { key: 'tienda', label: 'Tiendas <y> minimercados', icon: '🛒', page: '', priority: 2, prospectos: 0, enviados: 0, abrieron: 0, respondieron: 0, demos: 0, clientes: 0, puntaje: 0 }] };
  const nt = M.nichesTable(data);
  assert.match(nt, /% por nicho/);
  assert.match(nt, /\/talleres-y-fabricas/);
  assert.match(nt, /sin página propia/);
  assert.match(nt, /Tiendas &lt;y&gt; minimercados/);
  assert.match(nt, /25%/);
  M.model.data = data;
  const html = M.pane();
  assert.ok(html.includes('name="nicho"') && html.includes('data-vpm-color'));
  assert.doesNotMatch(html, /\sstyle=/);
  assert.equal(M.pinColor({ status: 'baja', niche: 'campo' }), '#ef4444');
  M.model.colorBy = 'nicho';
  assert.equal(M.pinColor({ status: 'baja', niche: 'campo' }), '#22c55e');
  assert.equal(M.pinColor({ status: 'nuevo' }), '#f59e0b', 'sin nicho = restaurantes');
  M._setMap({ layers: new Set(), hasLayer() { return false; } });
  M.model.data = { ...SAMPLE, pins: [{ id: 'x', name: 'Eléctricos <b>', business_type: 'electrico', niche: 'campo', tipo: 'Contratista eléctrico', status: 'nuevo', lat: 4.6, lng: -74.1 }] };
  M.drawLayers(window.L);
  const mk = made.markers[made.markers.length - 1];
  assert.equal(mk.args.o.fillColor, '#22c55e');
  assert.match(mk.tooltip, /🦺 Eléctricos &lt;b&gt; · Empresas de campo/);
  M.model.colorBy = 'estado';
});

test('025p vigencia: filtro, ficha "por verificar" y pin atenuado', () => {
  const { M, made, window } = load();
  assert.equal(M.mapUrl({ vigencia: 'por_verificar' }), '/api/v1/prospecting/admin/map?vigencia=por_verificar');
  M.model.data = SAMPLE;
  assert.ok(M.pane().includes('name="vigencia"'));
  M.model.detail = { prospect: { id: 'v', name: 'Taller', status: 'nuevo', vigencia: 'por_verificar', vigencia_reason: 'sin actividad visible en 12 meses <x>' }, history: [] };
  const html = M.detailPanel();
  assert.match(html, /Por verificar/);
  assert.match(html, /solo a la ruta de visitas/);
  assert.match(html, /&lt;x&gt;/);
  M._setMap({ layers: new Set(), hasLayer() { return false; } });
  M.model.data = { ...SAMPLE, pins: [{ id: 'v', name: 'T', business_type: 'taller', niche: 'taller', status: 'nuevo', vigencia: 'por_verificar', lat: 4.6, lng: -74.1 }] };
  M.drawLayers(window.L);
  const mk = made.markers[made.markers.length - 1];
  assert.equal(mk.args.o.fillOpacity, 0.4);
  assert.match(mk.tooltip, /por verificar/);
});
