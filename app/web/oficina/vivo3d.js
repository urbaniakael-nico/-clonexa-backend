// NEGOCIO EN VIVO 3D · visor del cliente (y "Abrir como el cliente" de la consola): SOLO el piso de su empresa, solo
// lectura (sin editor ni modo arquitecto), modo TV (pantalla completa sin controles) y modo liviano según la tarjeta.
// Todo sale de la ruta firmada de SU empresa (ROOT) y exige la cookie del visor: motor, three, recursos y copia viva.
import * as THREE from 'three';

// ===== reglas puras (probadas en tests/vivo3d.test.cjs) =====
const ENGINE = {taller: 'taller.js', restaurante: 'restaurante.js', campo: 'campo.js'};
// Qué motor abre el piso (el mismo que en la Oficina 3D de la consola) o null si aún no tiene piso 3D.
function engineFor(floor) {
  if (!floor) return null;
  if (floor.style === 'bar' && floor.template === 'bar') return {file: 'bar.js', fn: 'openBar'};
  if (floor.style === 'aprobado' && ENGINE[floor.template]) return {file: ENGINE[floor.template], fn: 'open'};
  return null;
}
// Modo liviano: '1' siempre, '0' nunca (lo decide la tarjeta de la consola); automático: celulares y equipos lentos.
function decideLite(mode, env) {
  if (mode === '1') return true;
  if (mode === '0') return false;
  return !!(env.coarse || env.width < 820 || (env.cores && env.cores <= 4) || (env.memory && env.memory <= 4));
}
// Las capas del editor (plantilla global -> plantilla de la empresa -> persona): un "" de arriba no borra lo de abajo.
function mergeRaw(layers) {
  const out = {};
  for (const l of layers || []) if (l) for (const [k, v] of Object.entries(l)) if (v !== '' && v !== null && v !== undefined) out[k] = v;
  return out;
}
// Identificador de esta pantalla (para contar pantallas abiertas): estable mientras la pestaña viva.
function screenId(store, rnd) {
  let id = store && store.getItem('cx3dScreen');
  if (!id || !/^[A-Za-z0-9_-]{8,40}$/.test(id)) { id = Array.from({length: 16}, () => 'abcdefghijkmnpqrstuvwxyz23456789'[Math.floor(rnd() * 32)]).join(''); if (store) store.setItem('cx3dScreen', id); }
  return id;
}
// La copia viva lleva la pantalla (latido); el resto de pedidos no.
function withScreen(url, id) { return /\/vivo(\?|$)/.test(url) ? url + (url.includes('?') ? '&' : '?') + 's=' + encodeURIComponent(id) : url; }
function esc(s) { return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'); }
// ===== fin reglas puras =====

const ROOT = new URL('./', import.meta.url).pathname;
const API = ROOT + 'api';
if (typeof window !== 'undefined' && !window.__CX_VIVO3D_TEST__) start();

async function start() {
  const SCREEN = screenId(window.sessionStorage, Math.random);
  const msg = document.getElementById('v3msg'), load = document.getElementById('load');
  const fail = (t) => { msg.textContent = t; msg.classList.remove('hidden'); if (load) load.remove(); };
  async function getJson(url, opts = {}) {
    const r = await fetch(withScreen(url, SCREEN), Object.assign({credentials: 'same-origin', cache: 'no-store'}, opts));
    if (r.status === 401 || r.status === 403) { fail(r.status === 401 ? 'Tu sesión del visor venció: vuelve a abrirlo desde tu panel.' : 'Negocio en vivo 3D no está disponible para tu usuario.'); throw new Error('Sin acceso'); }
    let data = {}; try { data = await r.json(); } catch (e) { data = {}; }
    if (!r.ok) throw new Error(data.detail || ('Error ' + r.status));
    return data;
  }
  let boot, chars = {items: []};
  try { boot = await getJson(API + '/piso'); } catch (e) { if (msg.classList.contains('hidden')) fail('No se pudo cargar tu negocio. ' + (e.message || '')); return; }
  try { chars = await getJson(API + '/personajes'); } catch (e) { /* sin personajes guardados: los de siempre */ }
  const floor = boot.floor, eng = engineFor(floor);
  document.getElementById('v3name').textContent = floor.name;
  document.title = `${floor.name} · en vivo`;
  if (!boot.tv) document.getElementById('v3tv').remove();
  if (!eng) { fail(`Tu ${boot.noun || 'negocio'} aún no tiene piso 3D. Pronto lo verás aquí.`); return; }

  const env = {coarse: matchMedia('(pointer: coarse)').matches, width: innerWidth, cores: navigator.hardwareConcurrency, memory: navigator.deviceMemory};
  let lite = decideLite(boot.lite, env);
  const R = new THREE.WebGLRenderer({canvas: document.getElementById('c'), antialias: !lite});
  R.setPixelRatio(lite ? 1 : Math.min(devicePixelRatio, 2)); R.setSize(innerWidth, innerHeight, false);
  const SAVED = new Map((chars.items || []).map(it => [(it.company_id || '') + '|' + it.clave, it]));
  const saved = (cid, k) => SAVED.get((cid || '') + '|' + k);
  const cid = floor.company_id;
  const layers = (kind, k, uniform) => kind === 'rep' ? [saved(cid, 'rep')] : [saved(null, 'plantilla:' + uniform), saved(cid, 'plantilla:' + uniform), saved(cid, 'persona:' + k)];
  const info = document.getElementById('v3info');
  const show = html => { info.innerHTML = '<button class="x" type="button" data-close aria-label="Cerrar">✕</button>' + html; info.classList.add('open'); info.querySelector('[data-close]').onclick = () => info.classList.remove('open'); };
  const liteBtn = document.getElementById('v3lite');
  const paintLite = () => { liteBtn.setAttribute('aria-pressed', String(lite)); liteBtn.classList.toggle('pri', lite); };
  let REAL = null;
  try {
    const mod = await import(ROOT + eng.file);
    REAL = await mod[eng.fn]({R, floor, getJson, log: null, lite, liteChosen: () => boot.lite, readonly: true, architect: false, backLabel: '← Volver al panel',
      repName: 'Representante', rawCfg: (kind, k, uniform) => mergeRaw(layers(kind, k, uniform)), charCfg: (kind, k, uniform) => mergeRaw(layers(kind, k, uniform)),
      onClose: () => { location.href = boot.back; },
      onRep: () => show(`<h2>Representante</h2><div class="role">${esc(floor.name)}</div><p>Solo cifras de actividad del día (sin dinero).</p>`),
      onTable: t => show(`<h2>${esc(t.label)}</h2><div class="role">${t.open ? '● QR activo' : 'Libre'}</div><ul>${t.pending ? `<li>${esc(t.pending)} productos pedidos</li>` : '<li>Sin pedidos pendientes</li>'}${t.songs ? `<li>${esc(t.songs)} canciones pedidas</li>` : ''}</ul>`),
      onPerson: (p, kind) => show(`<h2>${esc(p.name || (kind === 'cliente' ? 'Cliente' : '—'))}</h2><div class="role">${esc(p.role || '')}</div>${p.task ? `<ul><li>${esc(p.task)}</li></ul>` : ''}`),
      onAutoLite: () => { if (boot.lite == null && !lite) { lite = true; REAL.setLite(true); paintLite(); } }});
  } catch (e) {
    if (msg.classList.contains('hidden')) fail('No se pudo abrir tu piso 3D. ' + (e.message || ''));
    return;
  }
  if (load) load.remove();
  paintLite();
  if (boot.lite != null) liteBtn.remove(); else liteBtn.onclick = () => { lite = !lite; REAL.setLite(lite); paintLite(); };
  // modo TV: pantalla completa y sin controles (las etiquetas con los datos siguen); salir con Esc o doble toque
  const tvBtn = document.getElementById('v3tv');
  const setTv = on => { document.body.classList.toggle('tv', on); };
  if (tvBtn) tvBtn.onclick = async () => { setTv(true); try { await document.documentElement.requestFullscreen(); } catch (e) { /* sin pantalla completa: igual se ocultan los controles */ } };
  document.addEventListener('fullscreenchange', () => { if (!document.fullscreenElement) setTv(false); });
  addEventListener('dblclick', () => { if (document.body.classList.contains('tv')) { setTv(false); if (document.fullscreenElement) document.exitFullscreen().catch(() => {}); } });
  if (boot.tv && new URLSearchParams(location.search).get('tv') === '1') setTv(true);
  // imagen chica del piso para la tarjeta del panel y de la consola (a lo sumo una cada 10 min; el servidor decide)
  let shot = false;
  setTimeout(() => { shot = true; }, 8000);
  function snapshot() {
    shot = false;
    try { const c = document.createElement('canvas'); c.width = 640; c.height = 360; const x = c.getContext('2d'); const src = R.domElement;
      const k = Math.max(c.width / src.width, c.height / src.height), w = src.width * k, h = src.height * k; x.drawImage(src, (c.width - w) / 2, (c.height - h) / 2, w, h);
      c.toBlob(b => { if (b && b.size < 160 * 1024) fetch(API + '/vista', {method: 'POST', credentials: 'same-origin', headers: {'Content-Type': 'image/jpeg'}, body: b}).catch(() => {}); }, 'image/jpeg', .72);
    } catch (e) { /* sin imagen: la tarjeta muestra el ícono */ }
  }
  // dibujo: pausa con la pestaña oculta (la copia viva también se pausa en el motor)
  function frame() { if (!document.hidden) { REAL.tick(); if (shot) snapshot(); } requestAnimationFrame(frame); }
  requestAnimationFrame(frame);
}
