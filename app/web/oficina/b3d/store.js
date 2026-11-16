// Biblioteca 3D: guardado POR EMPRESA (API del backend). Solo las pantallas de la consola lo usan: el motor en vivo no.
import { BRAND, toast, uid } from './core.js';
import { registerModels } from './catalog.js';
import { defaultToon, defaultHuman } from './char.js';
export { toast, uid, BRAND };
// ---------- guardado POR EMPRESA en el backend de Clonexa (en el prototipo era localStorage)
// Empresas = lista real de la consola + su Estudio de marca. Diseños, estilo, equipo y uniformes viven en la API
// /admin-v2/api/b3d (sesión de Admin V2; 401 sin sesión). Store guarda en memoria y sincroniza en segundo plano.
export const API_BASE = '/admin-v2/api/b3d';
export const PAGES = '/admin-v2plus/biblioteca3d';
export async function api(path, opts = {}) {
  const json = opts.body && typeof opts.body === 'string';
  const r = await fetch(API_BASE + path, { credentials: 'same-origin', ...opts, headers: { Accept: 'application/json', ...(json ? { 'Content-Type': 'application/json' } : {}), ...(opts.headers || {}) } });
  if (r.status === 401) { location.href = '/admin-v2plus/login'; throw new Error('Sesión vencida'); }
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error((data && typeof data.detail === 'string' && data.detail) || ('Respuesta ' + r.status));
  return data;
}
export const COMPANIES = [];
let CID = new URLSearchParams(location.search).get('empresa') || sessionStorage.getItem('cx_b3d_empresa') || '';
let STATE = { designs: [], team: [], uniforms: [], style: 'human', entities: {}, areas: [], catalog: [], review: [] };
const synced = { designs: new Map(), team: new Map(), uniforms: '', style: '' };
const thumbAt = new Map();
async function loadState() {
  if (!CID) return;
  STATE = await api('/empresas/' + encodeURIComponent(CID));
  // cada persona arranca con el personaje por defecto del prototipo y encima lo que tenga guardado
  STATE.team.forEach((p, i) => { p.toon = { ...defaultToon(i), ...(p.toon || {}) }; p.human = { ...defaultHuman(i), ...(p.human || {}) }; });
  STATE.designs.forEach(d => { d.versions = d.versions || []; });
  synced.designs = new Map(STATE.designs.map(d => [d.id, designBody(d)]));
  synced.team = new Map(STATE.team.map(p => [p.id, personBody(p)]));
  synced.uniforms = JSON.stringify(STATE.uniforms); synced.style = STATE.style;
  registerModels(STATE.catalog || []);
}
try {
  const r = await api('/empresas'); COMPANIES.splice(0, COMPANIES.length, ...r.items);
  if (!COMPANIES.some(c => c.id === CID)) CID = (COMPANIES[0] || {}).id || '';
  if (CID) { sessionStorage.setItem('cx_b3d_empresa', CID); await loadState(); }
} catch (e) { setTimeout(() => toast('No se pudo cargar: ' + e.message, 'err'), 50); }
export function company() { return COMPANIES.find(c => c.id === CID) || COMPANIES[0] || { id: '', name: '—', kind: 'oficina', brand: [...BRAND], neon: '' }; }
export async function setCompany(id) {
  CID = id; sessionStorage.setItem('cx_b3d_empresa', id);
  const u = new URL(location.href); u.searchParams.set('empresa', id); history.replaceState(null, '', u);
  await loadState(); keepCompanyInLinks();
}
// los enlaces entre pantallas llevan la empresa (parámetro + sesión)
export function link(path) { const u = new URL(path, location.href); if (CID) u.searchParams.set('empresa', CID); return u.pathname + u.search; }
function keepCompanyInLinks() {
  document.querySelectorAll('a[href]').forEach(a => {
    const h = a.getAttribute('href'); if (!/^(constructor|personajes|index|\.\/|\/admin-v2plus\/biblioteca3d)/.test(h)) return;
    a.setAttribute('href', link(h.replace(/^index\.html/, './').replace(/\.html/, '')));
  });
}
if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', keepCompanyInLinks); else keepCompanyInLinks();
export const state = () => STATE;

// cola por clave: los guardados de un mismo diseño/persona salen en orden
const queue = new Map();
function chain(key, fn) { const p = (queue.get(key) || Promise.resolve()).then(fn); queue.set(key, p.catch(() => { })); return p; }
export function flush() { return Promise.all([...queue.values()]); }
const fail = e => toast('No se pudo guardar: ' + e.message, 'err');
const base = () => '/empresas/' + encodeURIComponent(CID);
export const companyPath = base;
function designBody(d) { return JSON.stringify({ name: d.name, plan: d.plan }); }
function personBody(p) { return JSON.stringify({ name: p.name, area: p.area, role: p.role, shift: p.shift, toon: p.toon, human: p.human, uniform: p.uniform || null, custom: !!p.custom }); }
function syncDesigns(list) {
  const ids = new Set(list.map(d => d.id));
  for (const id of [...synced.designs.keys()]) if (!ids.has(id)) { synced.designs.delete(id); chain('d' + id, () => api(`${base()}/disenos/${encodeURIComponent(id)}`, { method: 'DELETE' })).catch(fail); }
  for (const d of list) {
    const body = designBody(d), now = Date.now();
    const sendThumb = typeof d.thumb === 'string' && d.thumb.startsWith('data:image/jpeg') && now - (thumbAt.get(d.id) || 0) > 15000;
    if (synced.designs.get(d.id) === body && !sendThumb) continue;
    synced.designs.set(d.id, body); if (sendThumb) thumbAt.set(d.id, now);
    const thumb = sendThumb ? d.thumb : null;
    chain('d' + d.id, () => api(`${base()}/disenos/${encodeURIComponent(d.id)}`, { method: 'PUT', body: JSON.stringify({ name: d.name, plan: d.plan, thumb }) })
      .then(r => { if (r.thumb && d.thumb === thumb) d.thumb = r.thumb; })).catch(e => { synced.designs.delete(d.id); fail(e); });
  }
}
function syncTeam(list) {
  for (const p of list) {
    const body = personBody(p); if (synced.team.get(p.id) === body) continue; synced.team.set(p.id, body);
    chain('p' + p.id, () => api(`${base()}/equipo/${encodeURIComponent(p.id)}`, { method: 'PUT', body })).catch(e => { synced.team.delete(p.id); fail(e); });
  }
}
function syncUniforms(list) {
  const body = JSON.stringify(list); if (synced.uniforms === body) return; synced.uniforms = body;
  chain('u', () => api(`${base()}/uniformes`, { method: 'PUT', body: JSON.stringify({ items: list }) })).catch(e => { synced.uniforms = ''; fail(e); });
}
export const Store = {   // todo queda guardado POR EMPRESA
  get(k, d) {
    // copias, como leer de localStorage en el prototipo: lo que no se guarda (Store.set) no cambia nada
    if (k === 'designs') return structuredClone(STATE.designs); if (k === 'team') return structuredClone(STATE.team); if (k === 'uniforms') return structuredClone(STATE.uniforms);
    if (k === 'style') return STATE.style || d; if (k === 'brand') return company().brand || d; return d;
  },
  set(k, v) {
    if (!CID) return;
    if (k === 'designs') { STATE.designs = v; syncDesigns(v); }
    if (k === 'team') { STATE.team = structuredClone(v); syncTeam(STATE.team); }
    if (k === 'uniforms') { STATE.uniforms = structuredClone(v); syncUniforms(STATE.uniforms); }
    if (k === 'style' && v !== synced.style) { STATE.style = v; synced.style = v; chain('s', () => api(`${base()}/estilo`, { method: 'PUT', body: JSON.stringify({ style: v }) })).catch(fail); }
    // la marca no se guarda aquí: sale del Estudio de marca (solo lectura en la Biblioteca 3D)
  },
};
// paleta de marca de la empresa activa (Estudio de marca)
export function loadBrand() { const b = Store.get('brand', company().brand); BRAND.splice(0, BRAND.length, ...b); return BRAND; }
// entidades reales de ESA empresa (Conectar): {mesa: [{id, label}], ...}
export function entities() { return STATE.entities || {}; }
export function connLabel(id) { for (const l of Object.values(STATE.entities || {})) { const e = l.find(x => x.id === id); if (e) return e.label; } return id || ''; }
// modelos 3D aprobados de la Biblioteca (Poly Haven CC0 y subidos): entran al catálogo en su carpeta
export function libraryModels() { return STATE.catalog || []; }
// botones "Cerrar" de las ventanas (la CSP de la consola no admite onclick en el HTML)
document.addEventListener('click', e => { const b = e.target.closest && e.target.closest('[data-close]'); if (b) b.closest('.modal')?.classList.remove('show'); });
