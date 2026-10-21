// Consola v2+ · Landing → pestañas Visitas (igual que antes) y Redes sociales
// (cifras de Nexa que manda n8n, embudo a la landing, publicaciones y enlaces).
const { readFileSync } = require('node:fs');
const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');

const SRC = ['admin_v2plus_companies.js', 'admin_v2plus_ficha.js', 'admin_v2plus_company.js', 'admin_v2plus_catalog.js', 'admin_v2plus_admin.js', 'admin_v2plus_switches.js']
  .map((f) => readFileSync(`app/web/${f}`, 'utf8'));
const LANDING = JSON.parse(readFileSync('tests/fixtures/landing_visitas_data.json', 'utf8'));

function load(responder = () => ({ status: 200, body: {} })) {
  const calls = [];
  const handlers = {};
  const fetch = async (url, options = {}) => {
    calls.push(`${options.method || 'GET'} ${url}`);
    const { status, body } = responder(url);
    return { status, ok: status >= 200 && status < 300, json: async () => body };
  };
  const window = { location: { href: '', origin: 'https://clonexa.app' } };
  const document = { addEventListener: (type, fn) => { handlers[type] = fn; } };
  const ctx = vm.createContext({ window, document, fetch, JSON, Object, Array, String, Math, Number, Promise, Error, Date, Map, Set, URLSearchParams, encodeURIComponent, decodeURIComponent });
  SRC.forEach((s) => vm.runInContext(s, ctx));
  return { adm: window.CxConsoleAdmin, sections: window.CxConsoleSections, calls, handlers };
}

// Un elemento falso para los clics: closest(selector) con data-*.
const el = (attr, value) => ({ closest: (sel) => (sel === `[${attr}]` ? { getAttribute: () => value } : null) });
const tick = () => new Promise((r) => setTimeout(r, 0));

function series(days, pick) {
  const out = [];
  for (let i = 0; i < days; i += 1) {
    const d = new Date(Date.UTC(2026, 8, 22 + i)).toISOString().slice(0, 10);
    out.push({ date: d, ...pick(i) });
  }
  return out;
}

function sample() {
  const net = (network, label, extra) => ({ network, label, has_data: false, followers: null, followers_change: null, views: 0, engagements: 0, posts: 0, series: series(30, () => ({ followers: null, views: null })), ...extra });
  return {
    ok: true, days: 30, start: '2026-09-22', end: '2026-10-21',
    networks: [
      net('instagram', 'Instagram', { has_data: true, followers: 1530, followers_change: 42, views: 2100, engagements: 180, posts: 4, series: series(30, (i) => ({ followers: 1488 + i, views: 70 })) }),
      net('facebook', 'Facebook', { has_data: true, followers: 800, followers_change: -3, views: 900, engagements: 20, posts: 4, series: series(30, (i) => ({ followers: 803 - (i % 4), views: 30 })) }),
      net('youtube', 'YouTube', { has_data: true, followers: 210, followers_change: 0, views: 640, engagements: 31, posts: 4 }),
      net('linkedin', 'LinkedIn'),
      net('tiktok', 'TikTok'),
    ],
    posts: [
      { network: 'instagram', label: 'Instagram', published_at: '2026-10-20T15:00:00+00:00', tema: 'Turnos <b>sin</b> papel', views: 820, likes: 61, comments: 7, shares: 4, url: 'https://instagram.com/p/abc', utm_campaign: 'nexa-2026-s43' },
      { network: 'youtube', label: 'YouTube', published_at: '2026-10-13T15:00:00+00:00', tema: 'Caja en 3 minutos', views: 300, likes: 20, comments: 2, shares: 1, url: 'javascript:alert(1)', utm_campaign: 'nexa-2026-s42' },
    ],
    funnel: { social_views: 3640, landing_visits: 91, unique_visitors: 70 },
    landing_by_network: [{ network: 'instagram', label: 'Instagram', visits: 60, unique_visitors: 44 }],
    landing_by_campaign: [{ campaign: 'nexa-2026-s43', visits: 50, unique_visitors: 40 }],
  };
}

test('URL del resumen de redes: solo days', () => {
  const { adm } = load();
  assert.equal(adm.consoleApi.socialUrl('7'), '/api/v1/social-metrics/summary?days=7');
  assert.equal(adm.consoleApi.socialUrl(), '/api/v1/social-metrics/summary?days=30');
});

test('Fuentes: los dominios de una red se suman con su nombre; lo demás no cambia', () => {
  const { adm } = load();
  const rows = adm.groupSources([
    { label: 'directo', total: 30 }, { label: 'm.facebook.com', total: 4 }, { label: 'www.facebook.com', total: 3 }, { label: 'facebook', total: 2 },
    { label: 'l.instagram.com', total: 2 }, { label: 'instagram', total: 1 }, { label: 'google.com', total: 5 }, { label: 'lnkd.in', total: 1 }, { label: 'youtu.be', total: 1 },
  ]);
  assert.deepEqual(JSON.parse(JSON.stringify(rows)), [
    { label: 'directo', total: 30 }, { label: 'Facebook', total: 9 }, { label: 'google.com', total: 5 }, { label: 'Instagram', total: 3 },
    { label: 'LinkedIn', total: 1 }, { label: 'YouTube', total: 1 },
  ]);
});

test('mismo criterio de red que el servidor (social_metrics.network_of)', () => {
  const { adm } = load();
  const cases = [['instagram', 'instagram'], ['Facebook', 'facebook'], ['m.facebook.com', 'facebook'], ['www.facebook.com', 'facebook'], ['l.facebook.com', 'facebook'],
    ['youtu.be', 'youtube'], ['www.youtube.com', 'youtube'], ['lnkd.in', 'linkedin'], ['www.linkedin.com', 'linkedin'], ['www.tiktok.com', 'tiktok'],
    ['directo', null], ['google.com', null], ['notinstagram.com', null], ['instagram.com.evil.co', null]];
  for (const [source, expected] of cases) {
    const net = adm.socialNetworkOf(source);
    assert.equal(net ? net.key : null, expected, source);
  }
});

test('pestaña Visitas: el mismo HTML de antes (solo se agregan las pestañas)', () => {
  const { adm } = load();
  adm.model.landing.data = LANDING;
  const html = adm.landingView();
  assert.match(html, /data-vpx-landing-tab="visitas"[^>]*>Visitas<[\s\S]*data-vpx-landing-tab="redes"[^>]*>Redes sociales</);
  assert.match(html, /class="vp-chip is-active" type="button" role="tab" aria-selected="true" data-vpx-landing-tab="visitas"/);
  const before = readFileSync('tests/fixtures/landing_visitas_before.html', 'utf8');
  const withoutTabs = html.replace(/\s*<nav class="vp-chips" role="tablist">[\s\S]*?<\/nav>\s*/, '');
  const norm = (s) => s.replace(/\s+/g, ' ').replace(/> </g, '><').trim();
  assert.equal(norm(withoutTabs), norm(before));
});

test('pestaña Redes sociales con datos: tarjetas, embudo, gráficos, tabla y enlaces', () => {
  const { adm } = load();
  adm.model.landing.tab = 'redes';
  adm.model.social.data = sample();
  const html = adm.landingView();
  assert.match(html, /vp-soc-net is-instagram"><header><svg class="vp-soc-icon"[\s\S]*?<b>Instagram<\/b>[\s\S]*?<strong>1\.530<\/strong><span class="vp-soc-delta is-up">▲ 42<\/span>/);
  assert.match(html, /is-facebook[\s\S]*?<span class="vp-soc-delta is-down">▼ 3<\/span>/);
  assert.match(html, /is-youtube[\s\S]*?<span class="vp-soc-delta ">= 0<\/span>/);
  assert.match(html, /<dt>Vistas<\/dt><dd>2\.100<\/dd><\/div><div><dt>Interacciones<\/dt><dd>180<\/dd><\/div><div><dt>Publicaciones<\/dt><dd>4<\/dd>/);
  assert.match(html, /vp-soc-net is-linkedin is-empty[\s\S]*?Aún sin datos/);
  assert.match(html, /vp-soc-net is-tiktok is-empty[\s\S]*?Pendiente de aprobación/);
  assert.match(html, /Vistas en redes<\/span><strong>3\.640<\/strong>[\s\S]*Visitas a la landing desde redes<\/span><strong>91<\/strong><small>2,5 % de las vistas[\s\S]*Visitantes únicos<\/span><strong>70<\/strong>/);
  assert.match(html, /Vistas por semana[\s\S]*<rect class="vp-soc-mark is-instagram"/);
  assert.match(html, /Seguidores[\s\S]*<polyline class="vp-soc-line is-instagram"/);
  assert.match(html, /Turnos &lt;b&gt;sin&lt;\/b&gt; papel/, 'el tema se escapa');
  assert.match(html, /href="https:\/\/instagram\.com\/p\/abc" target="_blank" rel="noopener noreferrer">Ver</);
  assert.doesNotMatch(html, /javascript:alert/, 'solo enlaces http(s)');
  assert.match(html, /nexa-2026-s43<\/b><span class="vp-mono">50 · 40 únicos/);
  for (const n of ['instagram', 'facebook', 'youtube', 'linkedin', 'tiktok']) {
    assert.ok(html.includes(`data-vpx-copy="https://clonexa-landing-production.up.railway.app/?utm_source=${n}&amp;utm_medium=social&amp;utm_campaign=nexa-bio"`), n);
  }
  assert.doesNotMatch(html, /\sstyle=/);
  adm.model.social.query = 'caja';
  const filtered = adm.landingView();
  assert.match(filtered, /Caja en 3 minutos/);
  assert.doesNotMatch(filtered, /Turnos &lt;b&gt;/);
  adm.model.social.query = 'zzz';
  assert.match(adm.landingView(), /Ninguna publicación coincide/);
});

test('pestaña Redes sociales sin datos: estados vacíos y los enlaces igual', () => {
  const { adm } = load();
  adm.model.landing.tab = 'redes';
  const empty = sample();
  empty.networks = empty.networks.map((n) => ({ ...n, has_data: false, followers: null, followers_change: null, views: 0, engagements: 0, posts: 0, series: n.series.map((p) => ({ date: p.date, followers: null, views: null })) }));
  Object.assign(empty, { posts: [], funnel: { social_views: 0, landing_visits: 0, unique_visitors: 0 }, landing_by_network: [], landing_by_campaign: [] });
  adm.model.social.data = empty;
  const html = adm.landingView();
  assert.equal((html.match(/Aún sin datos/g) || []).length, 4);
  assert.match(html, /Pendiente de aprobación/);
  assert.match(html, /Aún sin vistas diarias/);
  assert.match(html, /Aún sin seguidores registrados/);
  assert.match(html, /Aún no hay publicaciones en este periodo/);
  assert.match(html, /Ninguna visita desde redes todavía/);
  assert.match(html, /Visitas a la landing desde redes<\/span><strong>0<\/strong><small>— de las vistas/);
  assert.match(html, /Enlaces con etiqueta/);
  adm.model.social.data = null;
  adm.model.social.error = 'admin_v2_session_required';
  const failed = adm.landingView();
  assert.match(failed, /vp-alert[\s\S]*admin_v2_session_required/);
  assert.match(failed, /Enlaces con etiqueta/);
});

test('vistas por semana: bloques de 7 días que terminan hoy; 7 días = por día', () => {
  const { adm } = load();
  const nets = sample().networks;
  const weeks = adm.viewBuckets(nets, 30);
  assert.equal(weeks.length, 5);
  assert.deepEqual(Array.from(weeks, (w) => w.total), [200, 700, 700, 700, 700]);
  assert.equal(weeks[4].label, '15/10');
  const short = nets.map((n) => ({ ...n, series: n.series.slice(-7) }));
  assert.equal(adm.viewBuckets(short, 7).length, 7);
});

test('cambiar de pestaña carga el resumen una vez; el periodo vuelve a pedirlo', async () => {
  const env = load((url) => ({ status: 200, body: url.includes('social-metrics') ? sample() : LANDING }));
  const root = { innerHTML: '', querySelector: () => null, querySelectorAll: () => [] };
  env.sections.landing.mount({ root: () => root, active: () => true, overview: () => null, toast: () => {}, params: {} });
  await tick();
  assert.deepEqual(env.calls, ['GET /api/v1/landing-analytics/summary?days=30&limit=40'], 'Visitas carga lo mismo que antes');
  await env.handlers.click({ target: el('data-vpx-landing-tab', 'redes') });
  await tick();
  assert.equal(env.calls[1], 'GET /api/v1/social-metrics/summary?days=30');
  assert.match(root.innerHTML, /Embudo/);
  await env.handlers.click({ target: el('data-vpx-landing-tab', 'visitas') });
  await env.handlers.click({ target: el('data-vpx-landing-tab', 'redes') });
  await tick();
  assert.equal(env.calls.length, 2, 'ya cargado: no vuelve a pedir');
  await env.handlers.click({ target: el('data-vpx-social-days', '90') });
  await tick();
  assert.equal(env.calls[2], 'GET /api/v1/social-metrics/summary?days=90');
  assert.match(root.innerHTML, /aria-pressed="true" data-vpx-social-days="90"/);
});
