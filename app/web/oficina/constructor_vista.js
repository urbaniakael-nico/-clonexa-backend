// Vista 3D EN VIVO del Modo constructor (iframe dentro del constructor). El MISMO motor de la oficina
// (oficina_plano.js sobre oficina_mixamo.openFloor) con el BORRADOR: el constructor le manda cada cambio por
// postMessage (mismo origen) y la escena se redibuja al instante; los datos reales de la empresa llegan por la copia
// viva (?plano=1: aunque el plano aún no esté publicado). ?estilo=humano|caricatura previsualiza el otro estilo.
import * as THREE from 'three';

const q = new URLSearchParams(location.search);
const cid = (q.get('empresa') || '').toLowerCase();
const estilo = q.get('estilo') === 'caricatura' ? 'caricatura' : (q.get('estilo') === 'humano' ? 'humano' : null);
const msg = document.getElementById('cxvMsg');
async function getJson(url, opts = {}) {
  const r = await fetch(url, {credentials: 'same-origin', cache: 'no-store', ...opts});
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail || 'Error ' + r.status);
  return data;
}
let REAL = null, busy = Promise.resolve();
async function start() {
  const pay = await getJson(`/admin-v2/api/oficina/pisos/${cid}/plano?borrador=1`);
  const R = new THREE.WebGLRenderer({canvas: document.getElementById('c'), antialias: true});
  R.setPixelRatio(Math.min(devicePixelRatio, 2)); R.setSize(innerWidth, innerHeight, false);
  const mod = await import('/admin-v2plus/oficina/plano.js');
  REAL = await mod.open({R, floor: {company_id: cid, name: pay.name || 'Empresa', brand: pay.brand || null}, getJson, log: null, lite: false, liteChosen: () => '0',
    planPayload: pay, styleOverride: estilo, liveUrl: `/admin-v2/api/oficina/pisos/${cid}/vivo?plano=1`, architect: false, readonly: true,
    rawCfg: () => ({}), charCfg: () => ({}), onClose() {}, onTable() {}, onPerson() {}, onRep() {}});
  msg.textContent = '';
  // medición de rendimiento (ms por cuadro con gl.finish; la pestaña de fondo limita requestAnimationFrame)
  const bench = (n = 120) => { const gl = R.getContext(); for (let i = 0; i < 10; i++) REAL.tick(); gl.finish(); const t0 = performance.now();
    for (let i = 0; i < n; i++) { REAL.tick(); gl.finish(); } const ms = (performance.now() - t0) / n; return {ms: Math.round(ms * 100) / 100, fps: Math.round(1000 / ms), calls: R.info.render.calls, tris: R.info.render.triangles}; };
  window.__cxVista = {get fps() { return REAL.fps; }, get stats() { return REAL.floorScene && REAL.floorScene.stats; }, get scene() { return REAL.scene; }, bench};
  const loop = () => { if (!document.hidden) REAL.tick(); requestAnimationFrame(loop); }; requestAnimationFrame(loop);
  parent.postMessage({type: 'cx-vista-lista'}, location.origin);
}
addEventListener('message', e => {
  if (e.origin !== location.origin || !e.data || e.data.type !== 'cx-plan' || !REAL || !REAL.floorScene) return;
  busy = busy.then(() => REAL.floorScene.setPlan(e.data.payload)).catch(err => { msg.textContent = 'No se pudo dibujar: ' + err.message; });
});
if (/^[0-9a-f-]{36}$/.test(cid)) start().catch(e => { msg.textContent = 'No se pudo abrir la vista 3D: ' + e.message; });
else msg.textContent = 'Falta la empresa.';
