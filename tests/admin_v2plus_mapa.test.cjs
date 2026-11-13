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
  M.model.allZones = true;
  const zt = M.zonesTable(SAMPLE);
  M.model.allZones = false;
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
  assert.equal(map.layers.size, 2, 'al abrir: pines y zonas; calor de visitas y de respuestas apagados; volantes sin prospeccion_visitas');
  M.model.layers.visitas = true; M.model.layers.leads = true;   // se prenden en las casillas
  M.model.data = { ...SAMPLE, ajustes: { prospeccion_visitas: true } };
  const map2 = window.L.map({}, {});
  M._setMap(map2);
  M.drawLayers(window.L);
  assert.equal(map2.layers.size, 5, 'las 5 capas prendidas (con la de volantes)');
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

test('025p canales: ficha con íconos, enlaces seguros y fuente; % por zona', () => {
  const { M } = load();
  M.model.detail = { prospect: { id: 'c', name: 'Taller Marta', status: 'nuevo', channels: {
    instagram: { value: '@tallermarta', url: 'https://www.instagram.com/tallermarta/', source: 'https://tallermarta.co/' },
    whatsapp: { value: '573001112233', url: 'https://wa.me/573001112233', source: 'https://tallermarta.co/contacto' },
    facebook: { value: 'x', url: 'javascript:alert(1)', source: 'google:website' },
    phone: { value: '601 234', url: 'tel:601234', source: 'google:telefono' } } }, history: [] };
  const html = M.detailPanel();
  assert.match(html, /Canales públicos/);
  assert.match(html, /📸/);
  assert.match(html, /href="https:\/\/www\.instagram\.com\/tallermarta\/"/);
  assert.match(html, /href="https:\/\/tallermarta\.co\/" target="_blank" rel="noopener noreferrer">fuente/);
  assert.match(html, /ficha de Google: website/);
  assert.match(html, /nunca escribe en frío/);
  assert.doesNotMatch(html, /javascript:/);
  const zt = M.zonesTable({ zones: [{ id: 1, name: 'Puente Aranda', active: true, prospectos: 4, con_correo: 1, con_redes: 3, con_whatsapp: 1, enviados: 0 }] });
  assert.match(zt, /% Instagram\/Facebook/);
  assert.match(zt, /75%/);
  assert.match(zt, /25%/);
});

test('025p ruta del día, volante PDF y calor por volante', async () => {
  const ROUTE = { zone: { id: 7, slug: 'bogota-puente-aranda', name: 'Puente Aranda', center_lat: 4.615, center_lng: -74.11 }, total_m: 2300,
    route_url: 'https://www.google.com/maps/dir/?api=1&origin=4.6,-74.1', fecha: '2026-11-12',
    stops: [{ id: 's1', name: 'Taller <1>', address: 'Cl 1', nicho: 'Talleres y fábricas', tipo: 'Taller', vigencia: 'por_verificar', desde_anterior_m: 120, maps_url: 'https://www.google.com/maps/search/?api=1&query=x' },
      { id: 's2', name: 'Taller 2', address: 'Cl 2', maps_url: 'javascript:alert(1)', desde_anterior_m: 300 }] };
  const { M, calls, made, window } = load({ responder: (url) => {
    if (url.includes('/route/send')) return { status: 200, body: { ok: true, paradas: 2 } };
    if (url.includes('/route?')) return { status: 200, body: ROUTE };
    if (url.includes('/visited')) return { status: 200, body: { ok: true, mensaje: '✅ Visitado: Taller 2' } };
    return { status: 200, body: SAMPLE };
  } });
  M.model.data = { ...SAMPLE, ajustes: { prospeccion_visitas: true } };
  await M.openRoute(7);
  assert.ok(calls.some((c) => c === 'GET /api/v1/prospecting/admin/route?zone_id=7'));
  const html = M.routePanel();
  assert.match(html, /Ruta del día · Puente Aranda/);
  assert.match(html, /Taller &lt;1&gt;/);
  assert.match(html, /por verificar/);
  assert.match(html, /Abrir la ruta en Google Maps/);
  assert.match(html, /data-vpm-route-send/);
  assert.match(html, /data-vpm-visited="s2"/);
  assert.doesNotMatch(html, /javascript:/);
  assert.doesNotMatch(html, /\sstyle=/);
  assert.equal(M.flyerUrl(7, 'taller'), '/api/v1/prospecting/admin/flyer?zone_id=7&nicho=taller');
  M.model.data = { ...SAMPLE, ajustes: { prospeccion_visitas: true } };
  const vb = M.visitsBar(M.model.data);
  assert.match(vb, /data-vpm-route="1"/);
  assert.match(vb, /data-vpm-flyer="1"/);
  M.model.data = { ...SAMPLE, ajustes: { prospeccion_visitas: true }, heat_flyers: [{ zone: 'Puente Aranda', nicho: 'Talleres', lat: 4.6, lng: -74.1, radius_m: 2500, total: 9, visitantes: 4 }] };
  M._setMap(window.L.map({}, {}));
  M.drawLayers(window.L);
  const fl = made.circles.find((c) => c.args.o.fillColor === '#38bdf8');
  assert.ok(fl && /9 visitas por el QR del volante/.test(fl.tooltip));
});

// ------------------------------------------------------------ ajuste prospeccion_visitas y tabla % por zona compacta
const ZONES3 = { ...SAMPLE, zones: [
  { id: 1, name: 'Kennedy Central', group_name: 'Kennedy', active: true, prospectos: 14, con_correo: 7, con_redes: 3, con_whatsapp: 2, enviados: 10, respondieron: 2, por_verificar: 1, puntaje: 99 },
  { id: 2, name: 'Zona Vacía', group_name: 'Usme', active: true, prospectos: 0, enviados: 0, respondieron: 0, por_verificar: 0, puntaje: 0 },
  { id: 3, name: 'Apagada', active: false, prospectos: 5 },
] };
const clickOn = (sel, attrs) => ({ target: { closest: (s) => (s === sel ? { getAttribute: (k) => attrs[k] } : null) } });

test('ajuste apagado (por defecto): sin Ruta del día ni Volante PDF en el HTML, sin botones ni selector', async () => {
  const { M, calls, window } = load({ responder: () => ({ status: 200, body: ZONES3 }) });
  for (const data of [ZONES3, { ...ZONES3, ajustes: { prospeccion_visitas: false } }]) {
    M.model.data = data;
    M.model.route = { zone_id: 1, data: { zone: { name: 'Kennedy' }, stops: [] } };
    const html = M.pane() + M.zonesTable(data) + M.visitsBar(data) + M.routePanel();
    for (const t of [/Ruta del día/, /Volante/, /data-vpm-route="/, /data-vpm-route-send/, /data-vpm-flyer/, /data-vpm-visit-zone/, /data-vpm-layer="volantes"/, /🗺️/, /🖨️/]) assert.doesNotMatch(html, t, String(t));
    assert.equal(M.visitsOn(), false);
  }
  M.model.route = null;
  // aunque llegue un clic viejo, no llama al servidor ni abre el PDF
  const host = { innerHTML: '', listeners: {}, querySelector: () => null, addEventListener(t, f) { this.listeners[t] = f; } };
  let opened = '';
  window.open = (u) => { opened = u; };
  M.mount(host);
  await new Promise((r) => setTimeout(r, 0));
  M.model.data = ZONES3;
  const before = calls.length;
  await host.listeners.click(clickOn('[data-vpm-route]', { 'data-vpm-route': '1' }));
  await host.listeners.click(clickOn('[data-vpm-flyer]', { 'data-vpm-flyer': '1' }));
  assert.equal(calls.slice(before).filter((c) => /\/route|\/flyer/.test(c)).length, 0);
  assert.equal(opened, '');
});

test('ajuste prendido: vuelven Ruta del día y Volante PDF (fuera de la tabla) y funcionan igual', async () => {
  const ROUTE = { zone: { id: 1, name: 'Kennedy Central' }, total_m: 1000, route_url: 'https://www.google.com/maps/dir/?api=1', stops: [{ id: 's1', name: 'Taller', desde_anterior_m: 10 }] };
  const ON = { ...ZONES3, ajustes: { prospeccion_visitas: true } };
  const { M, calls, window } = load({ responder: (url) => (url.includes('/route?') ? { status: 200, body: ROUTE } : { status: 200, body: ON }) });
  const host = { innerHTML: '', listeners: {}, querySelector: (s) => (s === '[data-vpm-flyer-niche="1"]' ? { value: 'taller' } : null), addEventListener(t, f) { this.listeners[t] = f; } };
  let opened = '';
  window.open = (u) => { opened = u; };
  M.mount(host);
  await new Promise((r) => setTimeout(r, 0));
  await new Promise((r) => setTimeout(r, 0));
  assert.equal(M.visitsOn(), true);
  const html = M.pane();
  for (const t of ['🗺️ Ruta del día', '🖨️ Volante PDF', 'data-vpm-visit-zone', 'data-vpm-flyer-niche="1"', 'data-vpm-layer="volantes"', 'aria-label="Visitas en la calle"']) assert.ok(html.includes(t), t);
  assert.doesNotMatch(M.visitsBar(ON), /Apagada/, 'solo zonas activas');
  assert.doesNotMatch(M.zonesTable(ON), /data-vpm-route|data-vpm-flyer|<button/, 'nada de botones dentro de la tabla');
  await host.listeners.click(clickOn('[data-vpm-route]', { 'data-vpm-route': '1' }));
  await new Promise((r) => setTimeout(r, 0));
  assert.ok(calls.includes('GET /api/v1/prospecting/admin/route?zone_id=1'));
  assert.match(M.routePanel(), /Ruta del día · Kennedy Central/);
  await host.listeners.click(clickOn('[data-vpm-flyer]', { 'data-vpm-flyer': '1' }));
  assert.equal(opened, '/api/v1/prospecting/admin/flyer?zone_id=1&nicho=taller');
});

test('% por zona: oculta zonas en 0 (casilla "ver todas"), columnas pedidas, números a la derecha, sin botones', () => {
  const { M } = load();
  M.model.allZones = false;
  const zt = M.zonesTable(ZONES3);
  assert.match(zt, /Kennedy Central/);
  assert.match(zt, /<small>Kennedy<\/small>/, 'localidad debajo de la zona');
  assert.doesNotMatch(zt, /Zona Vacía/);
  assert.doesNotMatch(zt, /Apagada/);
  assert.match(zt, /data-vpm-all-zones/);
  assert.match(zt, /Ver todas \(1 en 0\)/);
  const heads = [...zt.matchAll(/<th scope="col"[^>]*>([^<]+)<\/th>/g)].map((m) => m[1]);
  assert.deepEqual(heads, ['Zona', 'Prospectos', '% correo', '% Instagram/Facebook', '% WhatsApp publicado', 'Enviados', 'Respuestas', 'Por verificar']);
  const cells = [...zt.matchAll(/<td class="is-num">([^<]*)<\/td>/g)].map((m) => m[1]);
  assert.deepEqual(cells, ['14', '50%', '21.4%', '14.3%', '10', '2', '1']);
  assert.doesNotMatch(zt, /<button|<select|\sstyle=/);
  M.model.allZones = true;
  const all = M.zonesTable(ZONES3);
  assert.match(all, /Zona Vacía/);
  assert.doesNotMatch(all, /Apagada/);
  M.model.allZones = false;
  assert.match(M.zonesTable({ zones: [ZONES3.zones[1]] }), /Ninguna zona tiene prospectos/);
});

test('selects del Mapa comercial: fondo oscuro, letra clara (color-scheme dark, AA) y con nombre', () => {
  const css = readFileSync('app/web/admin_v2plus.css', 'utf8');
  const rule = css.match(/\.vpm select \{([^}]*)\}/);
  assert.ok(rule, 'regla .vpm select');
  assert.match(rule[1], /color-scheme: dark/);
  assert.match(rule[1], /background-color: #140d18/);
  assert.match(rule[1], /color: var\(--vp-text\)/);
  assert.match(css, /\.vpm select option, \.vpm select optgroup \{[^}]*background-color: #140d18; color: var\(--vp-text\)/);
  // contraste #F4ECEC (--vp-text) sobre #140d18 >= 4.5 (AA)
  assert.match(css, /--vp-text: #F4ECEC;/);
  const lum = (hex) => { const c = hex.match(/\w\w/g).map((x) => parseInt(x, 16) / 255).map((v) => (v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4)); return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]; };
  const ratio = (lum('F4ECEC') + 0.05) / (lum('140d18') + 0.05);
  assert.ok(ratio >= 4.5, `contraste ${ratio}`);
  // cada select con nombre: dentro de un <label> o con aria-label; opciones con texto
  const { M } = load();
  M.model.data = { ...ZONES3, ajustes: { prospeccion_visitas: true } };
  const html = M.pane() + M.visitsBar(M.model.data);
  const selects = [...html.matchAll(/<select[^>]*>/g)];
  assert.ok(selects.length >= 8, String(selects.length));
  for (const m of selects) {
    const before = html.slice(0, m.index);
    const inLabel = before.lastIndexOf('<label') > before.lastIndexOf('</label>');
    assert.ok(inLabel || /aria-label=/.test(m[0]), m[0]);
  }
  for (const m of html.matchAll(/<option[^>]*>([^<]*)<\/option>/g)) assert.ok(m[1].trim(), 'opción sin nombre');
});

test('capas de calor apagadas al abrir: casillas sin marcar; pines y zonas siguen prendidos', () => {
  const { M } = load();
  M.model.data = SAMPLE;
  const html = M.pane();
  assert.match(html, /data-vpm-layer="visitas" >/);
  assert.match(html, /data-vpm-layer="leads" >/);
  assert.match(html, /data-vpm-layer="prospectos" checked/);
  assert.match(html, /data-vpm-layer="zonas" checked/);
});
