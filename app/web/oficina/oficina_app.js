// Oficina 3D · Consola v2+ (interno de Clonexa, solo Admin V2).
// Diseño: docs/oficina/maqueta-v2.html (edificio negro con neón y logo, ascensor, pisos, personajes
// Lego / Anime / 3D, editor, elenco, etiquetas y actividad en vivo).
// Fase 1.5: los pisos con estilo "realista" (interruptor por empresa; hoy solo The Time Machine) abren el motor
// realista (oficina_real.js, se carga solo al entrar a ese piso) con la marca de la empresa y su copia viva.
// El editor ya no carga imágenes ni modelos: una imagen plana pierde la animación.
// Aquí los datos son REALES: GET /admin-v2/api/oficina/estado cada 30 s (pausa si la pestaña no se ve).
// Three.js sale del propio backend (three@0.160.0, copia local fija), sin CDN.
import * as THREE from 'three';
import {RoomEnvironment} from 'three/addons/environments/RoomEnvironment.js';
import {RoundedBoxGeometry} from 'three/addons/geometries/RoundedBoxGeometry.js';
import {genderFromName} from '/admin-v2plus/oficina/pisos_reglas.js';
import {attachGestures} from '/admin-v2plus/oficina/gestos.js';

// ===== reglas puras (probadas en tests/oficina_app.test.cjs) =====
const API = '/admin-v2/api/oficina';
const POLL_MS = 30000;
const FLOOR_STEP = 5.6;
const ST = {work: {c: '#22c55e', t: 'Trabajando'}, wait: {c: '#f59e0b', t: 'Esperando'}, cafe: {c: '#f59e0b', t: 'En la cafetería'},
  err: {c: '#ef4444', t: 'Error'}, train: {c: '#60a5fa', t: 'En entrenamiento'}, nodata: {c: '#6b7280', t: 'Sin datos'}};
const STYLE_LABEL = {lego: 'Lego', anime: 'Anime', real: '3D'};
const BODY_LABEL = {medio: 'Medio', delgado: 'Delgado', robusto: 'Robusto', alto: 'Alto'};
const HAIR_LABEL = {corto: 'Corto', largo: 'Largo', rizado: 'Rizado', recogido: 'Recogido', rapado: 'Rapado', calvo: 'Sin pelo'};
const ACC_LABEL = {none: 'Ninguno', delantal: 'Delantal', gorra: 'Gorra', casco: 'Casco', audifonos: 'Audífonos', gafas: 'Gafas', chaleco: 'Chaleco', corbata: 'Corbata'};
const SERVER_FIELDS = {nombre: 'name', rol: 'zone', tarea: 'role', estilo: 'style', color_ropa: 'color', color_pantalon: 'legs',
  color_pelo: 'hair', color_piel: 'skin', accesorio: 'acc', color_accesorio: 'accColor', cuerpo: 'body', peinado: 'hairStyle',
  genero: 'gender', personaje: 'model', tunica: 'tunic', barba: 'beard', color_barba: 'beardColor'};
// Pisos aprobados: personajes de Mixamo por género (el editor elige cuál).
const MIXAMO = {hombre: ['Remy', 'Ch01_nonPBR', 'Ch06_nonPBR', 'Ch42_nonPBR', 'Ch17_nonPBR'], mujer: ['Ch07_nonPBR', 'Ch21_nonPBR', 'Ch22_nonPBR']};
const MIXAMO_LABEL = {Remy: 'Remy · camisa', Ch01_nonPBR: 'Hombre casual (Ch01)', Ch06_nonPBR: 'Buzo y audífonos (Ch06)', Ch42_nonPBR: 'Hombre (Ch42)', Ch17_nonPBR: 'Técnico con casco (Ch17)',
  Ch07_nonPBR: 'Mujer de traje (Ch07)', Ch21_nonPBR: 'Mujer (Ch21)', Ch22_nonPBR: 'Mujer (Ch22)'};
// Motor de cada piso aprobado (uno por plantilla).
const AGENT_MODEL_DEF = {director: 'Ch01_nonPBR', asistente: 'Ch07_nonPBR', creativo: 'Remy', contenido: 'Ch22_nonPBR', planb: 'Ch42_nonPBR', tiktok: 'Ch21_nonPBR',
  analista: 'Ch42_nonPBR', ventas: 'Ch07_nonPBR', correos: 'Ch01_nonPBR', prospecta: 'Ch21_nonPBR', comunidad: 'Ch22_nonPBR', mensajero: 'Ch06_nonPBR',
  archivista: 'Ch01_nonPBR', lector: 'Ch07_nonPBR', guardian: 'Ch06_nonPBR'};
const APPROVED_MODULE = {taller: '/admin-v2plus/oficina/taller.js', restaurante: '/admin-v2plus/oficina/restaurante.js', campo: '/admin-v2plus/oficina/campo.js'};

function esc(s) {
  return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

// Modo liviano: lo que el dueño eligió manda; si no eligió, se activa solo en celulares o equipos lentos.
function decideLite(saved, env) {
  if (saved === '1') return true;
  if (saved === '0') return false;
  return !!(env.coarse || env.width < 820 || (env.cores && env.cores <= 4) || (env.memory && env.memory <= 4));
}

// Lo guardado en el servidor (nombres en español) -> campos del personaje (los de la maqueta).
function fromServer(item) {
  const out = {};
  if (!item) return out;
  for (const [k, v] of Object.entries(SERVER_FIELDS)) {
    if (item[k] !== undefined && item[k] !== null && item[k] !== '') out[v] = item[k];
  }
  if (out.style && !STYLE_LABEL[out.style]) delete out.style;  // "imagen" y "modelo" ya no se usan
  if (out.acc && !ACC_LABEL[out.acc]) delete out.acc;
  return out;
}

function toServer(patch) {
  const back = Object.fromEntries(Object.entries(SERVER_FIELDS).map(([k, v]) => [v, k]));
  const out = {};
  for (const [k, v] of Object.entries(patch)) {
    if (back[k]) out[back[k]] = v;
  }
  return out;
}

function mergeCfg(def, layers) {
  return Object.assign({}, def, ...layers.map(fromServer));
}

// Quién entra y quién sale del piso (por clave estable de la persona).
function staffDiff(currentKeys, people) {
  const now = new Set(people.map(p => p.key));
  const had = new Set(currentKeys);
  return {add: people.filter(p => !had.has(p.key)), remove: [...had].filter(k => !now.has(k))};
}

// Altura de cada piso: recepción abajo, los pisos de clientes en el orden del ascensor (el primero
// queda arriba) y CLONEXA encima de todos.
function floorYs(count) {
  const base = 0.45 + FLOOR_STEP;
  return {floors: Array.from({length: count}, (_, i) => base + (count - 1 - i) * FLOOR_STEP), clonexa: base + count * FLOOR_STEP};
}

// Puesto de cada persona: primero los de su uniforme, luego cualquier puesto libre.
function assignSeats(people, stations) {
  const used = new Set();
  const take = list => {
    for (let i = 0; i < (list || []).length; i++) {
      const id = JSON.stringify(list[i]);
      if (!used.has(id)) { used.add(id); return list[i]; }
    }
    return null;
  };
  return people.map(p => ({person: p, seat: take(stations[p.uniform]) || take(stations.any)})).filter(x => x.seat);
}

function reorder(list, from, to) {
  const out = list.slice();
  const [item] = out.splice(from, 1);
  out.splice(to, 0, item);
  return out;
}

function agentVisualState(state) {
  return ST[state] ? state : 'nodata';
}

// Un piso abre el motor realista solo si su empresa tiene el interruptor encendido (estilo "realista" o "bar":
// el bar aprobado de The Time Machine, oficina_bar.js).
function isRealFloor(f) {
  return !!(f && (f.style === 'realista' || f.style === 'bar' || (f.style === 'aprobado' && APPROVED_MODULE[f.template])));
}
// Con un piso abierto, el clic y el arrastre son del piso: nunca cambian de piso ni mueven el edificio.
function buildingInputAllowed(realOpen) {
  return !realOpen;
}
// Género por defecto del editor: la MISMA regla que usan los pisos (oficina_pisos_rules.genderFromName), así lo
// que dice el editor es lo que se ve en el piso. Editable.
function guessGender(name) {
  return genderFromName(name) || 'hombre';
}
// Capas del editor (plantilla global -> plantilla de la empresa -> persona) -> lo que reciben los pisos aprobados.
// El servidor devuelve todas las columnas ("" si no se tocaron): un "" de arriba NO borra lo de abajo.
function mergeRaw(layers) {
  const out = {};
  for (const l of layers || []) if (l) for (const [k, v] of Object.entries(l)) if (v !== '' && v !== null && v !== undefined) out[k] = v;
  return out;
}
// Cola de guardado POR personaje (clave + empresa): cambiar de persona antes de que se guarde la anterior ya no
// pierde su cambio (antes había una sola cola y el cambio de la primera persona nunca llegaba al servidor).
function queueSave(queue, key, base, patch) {
  const cur = queue.get(key) || Object.assign({}, base);
  Object.assign(cur, patch); queue.set(key, cur);
  return cur;
}
const LOOK_FIELDS = ['genero', 'personaje', 'tunica', 'barba', 'color_barba', 'color_pelo', 'color_ropa', 'nombre'];
function changesLook(body) { return LOOK_FIELDS.some(k => k in (body || {})); }
// ===== fin reglas puras =====

if (typeof window !== 'undefined' && !window.__CX_OFICINA_TEST__) start();

async function start() {
  const loadEl = document.getElementById('load');
  let first;
  try {
    first = await getJson(API + '/estado');
  } catch (e) {
    loadEl.textContent = 'No se pudo cargar la oficina. ' + (e.message || '');
    return;
  }
  let saved = {items: []};
  try { saved = await getJson(API + '/personajes'); } catch (e) { /* el editor dirá que no hay datos */ }
  main(first, saved);
}

async function getJson(url, opts = {}) {
  const r = await fetch(url, Object.assign({credentials: 'same-origin', cache: 'no-store'}, opts));
  if (r.status === 401) { location.href = '/admin-v2plus/login'; throw new Error('Sesión vencida'); }
  let data = {};
  try { data = await r.json(); } catch (e) { data = {}; }
  if (!r.ok) throw new Error(data.detail || ('Error ' + r.status));
  return data;
}

function main(DATA, SAVED_IN) {
  // ---------------------------------------------------------------- render y escena
  const env = {coarse: matchMedia('(pointer: coarse)').matches, width: innerWidth, cores: navigator.hardwareConcurrency, memory: navigator.deviceMemory};
  let lite = decideLite(localStorage.getItem('cxOfiLite'), env);
  const canvas = document.getElementById('c');
  const R = new THREE.WebGLRenderer({canvas, antialias: !lite});
  R.setPixelRatio(lite ? 1 : Math.min(devicePixelRatio, 2)); R.useLegacyLights = true; R.toneMapping = THREE.ACESFilmicToneMapping; R.toneMappingExposure = 1.15;
  R.shadowMap.enabled = !lite; R.shadowMap.type = THREE.PCFSoftShadowMap;
  const S = new THREE.Scene(); S.fog = new THREE.Fog(0x08060c, 140, 380);
  const pm = new THREE.PMREMGenerator(R); S.environment = pm.fromScene(new RoomEnvironment(R), .04).texture;
  const C = new THREE.PerspectiveCamera(42, 1, .1, 900);
  {const g = document.createElement('canvas'); g.width = 2; g.height = 512; const x = g.getContext('2d'); const gr = x.createLinearGradient(0, 0, 0, 512);
    gr.addColorStop(0, '#05040a'); gr.addColorStop(.55, '#120a1c'); gr.addColorStop(.8, '#2a1022'); gr.addColorStop(1, '#08060c'); x.fillStyle = gr; x.fillRect(0, 0, 2, 512);
    const t = new THREE.CanvasTexture(g); t.colorSpace = THREE.SRGBColorSpace; S.background = t;}
  S.add(new THREE.HemisphereLight(0xefe6ff, 0x1a1218, .6));
  const sun = new THREE.DirectionalLight(0xfff1e6, .9); sun.position.set(45, 90, 60); sun.castShadow = !lite; sun.shadow.mapSize.set(2048, 2048); sun.shadow.bias = -.0004;
  Object.assign(sun.shadow.camera, {left: -45, right: 45, top: 45, bottom: -45, near: 1, far: 260}); S.add(sun); S.add(sun.target);
  const M = (c, o = {}) => new THREE.MeshStandardMaterial(Object.assign({color: c, roughness: .7, metalness: .05, envMapIntensity: .55}, o));
  function mesh(geo, m, x = 0, y = 0, z = 0, p) { const k = new THREE.Mesh(geo, m); k.position.set(x, y, z); k.castShadow = k.receiveShadow = true; (p || S).add(k); return k; }
  const box = (w, h, d, m, x, y, z, p) => mesh(new THREE.BoxGeometry(w, h, d), m, x, y, z, p);
  const rbox = (w, h, d, m, x, y, z, p, r = .04) => mesh(new RoundedBoxGeometry(w, h, d, lite ? 1 : 3, Math.min(r, w / 2.1, h / 2.1, d / 2.1)), m, x, y, z, p);
  const cyl = (rt, rb, h, m, x, y, z, p, seg = 20) => mesh(new THREE.CylinderGeometry(rt, rb, h, lite ? Math.min(seg, 12) : seg), m, x, y, z, p);
  const sph = (r, m, x, y, z, p, ws = 20, hs = 16) => mesh(new THREE.SphereGeometry(r, ws, hs), m, x, y, z, p);
  const cap = (r, l, m, x, y, z, p) => mesh(new THREE.CapsuleGeometry(r, l, 6, 14), m, x, y, z, p);
  function canvasTex(w, h, draw, rep = [1, 1]) { const c = document.createElement('canvas'); c.width = w; c.height = h; draw(c.getContext('2d'), w, h); const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; t.wrapS = t.wrapT = THREE.RepeatWrapping; t.repeat.set(rep[0], rep[1]); t.anisotropy = 8; t.userData.canvas = c; t.userData.draw = draw; return t; }
  function drawText(lines, {w = 768, h = 256, bg = 'rgba(0,0,0,0)', fg = '#fff', size = 64, sub = '#c9bccf'} = {}) {
    return (x) => { x.clearRect(0, 0, w, h); x.fillStyle = bg; x.fillRect(0, 0, w, h); x.textAlign = 'center'; x.textBaseline = 'middle'; const L = [].concat(lines);
      L.forEach((l, i) => { x.fillStyle = i ? sub : fg; x.font = `${i ? 500 : 800} ${i ? size * .55 : size}px Inter, system-ui, sans-serif`; x.fillText(String(l).slice(0, 48), w / 2, h / 2 + (i - (L.length - 1) / 2) * size * 1.05); }); };
  }
  function textTex(lines, o = {}) { const w = o.w || 768, h = o.h || 256; return canvasTex(w, h, drawText(lines, o)); }
  function retext(tex, lines, o) { const c = tex.userData.canvas; drawText(lines, Object.assign({w: c.width, h: c.height}, o))(c.getContext('2d')); tex.needsUpdate = true; }
  const rnd = (s => () => { s |= 0; s = s + 0x6D2B79F5 | 0; let t = Math.imul(s ^ s >>> 15, 1 | s); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; })(11);
  const TX = {
    madera: canvasTex(512, 512, (x, w) => { for (let i = 0; i < 8; i++) { const v = 36 + rnd() * 10; x.fillStyle = `hsl(26,38%,${v}%)`; x.fillRect(0, i * 64, w, 64); for (let k = 0; k < 40; k++) { x.strokeStyle = `rgba(0,0,0,${.05 + rnd() * .08})`; x.beginPath(); const y = i * 64 + rnd() * 64; x.moveTo(0, y); x.bezierCurveTo(w * .3, y + rnd() * 6 - 3, w * .6, y + rnd() * 6 - 3, w, y); x.stroke(); } x.fillStyle = 'rgba(0,0,0,.25)'; x.fillRect(0, i * 64, w, 1); } }, [6, 4]),
    concreto: canvasTex(512, 512, (x, w, h) => { x.fillStyle = '#8d8a90'; x.fillRect(0, 0, w, h); for (let i = 0; i < 9000; i++) { x.fillStyle = `rgba(${rnd() > .5 ? 255 : 0},${rnd() > .5 ? 255 : 0},${rnd() > .5 ? 255 : 0},.04)`; x.fillRect(rnd() * w, rnd() * h, 2, 2); } x.strokeStyle = 'rgba(0,0,0,.18)'; x.strokeRect(0, 0, w, h); }, [5, 4]),
    terracota: canvasTex(512, 512, (x) => { for (let i = 0; i < 8; i++) for (let j = 0; j < 8; j++) { x.fillStyle = `hsl(${14 + rnd() * 6},45%,${30 + rnd() * 8}%)`; x.fillRect(i * 64 + 1, j * 64 + 1, 62, 62); } }, [5, 4]),
    negro: canvasTex(512, 512, (x, w, h) => { x.fillStyle = '#121016'; x.fillRect(0, 0, w, h); for (let i = 0; i < 8; i++) for (let j = 0; j < 8; j++) { x.fillStyle = `rgba(255,255,255,${.015 + rnd() * .02})`; x.fillRect(i * 64 + 2, j * 64 + 2, 60, 60); } }, [6, 4]),
    tecnico: canvasTex(512, 512, (x, w, h) => { x.fillStyle = '#5b616b'; x.fillRect(0, 0, w, h); for (let i = 0; i < 4; i++) for (let j = 0; j < 4; j++) { x.fillStyle = '#6d737d'; x.fillRect(i * 128 + 3, j * 128 + 3, 122, 122); for (let k = 0; k < 30; k++) { x.fillStyle = 'rgba(0,0,0,.25)'; x.fillRect(i * 128 + 12 + (k % 6) * 18, j * 128 + 12 + Math.floor(k / 6) * 20, 6, 6); } } }, [8, 5]),
    alfombra: canvasTex(256, 256, (x, w, h) => { x.fillStyle = '#3a3540'; x.fillRect(0, 0, w, h); for (let i = 0; i < 6000; i++) { x.fillStyle = `rgba(255,255,255,${rnd() * .04})`; x.fillRect(rnd() * w, rnd() * h, 1, 1); } }, [4, 4]),
    adoquin: canvasTex(512, 512, (x, w, h) => { x.fillStyle = '#1d1b20'; x.fillRect(0, 0, w, h); for (let i = 0; i < 16; i++) for (let j = 0; j < 16; j++) { x.fillStyle = `hsl(270,6%,${11 + rnd() * 5}%)`; x.fillRect(i * 32 + 1 + (j % 2) * 16, j * 32 + 1, 30, 30); } }, [30, 30]),
  };
  const ST_LOGO = new THREE.TextureLoader().load('/admin-v2plus/oficina/logo-simbolo.png'); ST_LOGO.colorSpace = THREE.SRGBColorSpace;
  const WM_LOGO = new THREE.TextureLoader().load('/admin-v2plus/oficina/logo-nombre.png'); WM_LOGO.colorSpace = THREE.SRGBColorSpace;

  // ---------------------------------------------------------------- fachada
  const THEMES = {negro: {glass: 0x07070a, op: .86, metal: .9, rough: .06, frame: 0x0d0d10, slab: 0x111014}, azul: {glass: 0x16324a, op: .55, metal: .6, rough: .05, frame: 0x1d2a36, slab: 0x1b2026}, blanco: {glass: 0xdfe7ee, op: .35, metal: .2, rough: .1, frame: 0xf4f1ec, slab: 0xe7e2da}};
  const facadeGlass = new THREE.MeshPhysicalMaterial({color: THEMES.negro.glass, metalness: .9, roughness: .06, transparent: true, opacity: .86, envMapIntensity: 1.4, clearcoat: 1, depthWrite: false});
  const frameMat = M(0x0d0d10, {metalness: .8, roughness: .3, envMapIntensity: 1});
  const slabMat = M(0x111014, {roughness: .5, metalness: .4});
  const neonMat = new THREE.MeshBasicMaterial({color: 0xf20b6d});
  function applyTheme(k) { const t = THEMES[k] || THEMES.negro; facadeGlass.color.set(t.glass); facadeGlass.opacity = t.op; facadeGlass.metalness = t.metal; facadeGlass.roughness = t.rough; frameMat.color.set(t.frame); slabMat.color.set(t.slab); }
  const themeEl = document.getElementById('theme'), accentEl = document.getElementById('accent');
  themeEl.value = localStorage.getItem('cxOfiTheme') || 'negro'; applyTheme(themeEl.value);
  accentEl.value = localStorage.getItem('cxOfiAccent') || '#f20b6d'; neonMat.color.set(accentEl.value);
  themeEl.onchange = e => { applyTheme(e.target.value); localStorage.setItem('cxOfiTheme', e.target.value); };
  accentEl.oninput = e => { neonMat.color.set(e.target.value); localStorage.setItem('cxOfiAccent', e.target.value); };

  // ---------------------------------------------------------------- exterior (la ciudad no sale en modo liviano)
  const CITY = new THREE.Group(); S.add(CITY);
  {const g = mesh(new THREE.PlaneGeometry(700, 700), M(0x0b0a0e, {map: TX.adoquin, roughness: .9})); g.rotation.x = -Math.PI / 2; g.castShadow = false;
    const road = mesh(new THREE.PlaneGeometry(700, 14), M(0x0c0c0f, {roughness: .95}), 0, .02, 40); road.rotation.x = -Math.PI / 2;
    for (let i = -30; i < 30; i++) { const l = mesh(new THREE.PlaneGeometry(4, .3), new THREE.MeshBasicMaterial({color: 0x888888}), i * 10, .03, 40); l.rotation.x = -Math.PI / 2; }
    for (let i = -6; i <= 6; i++) { if (Math.abs(i) < 1) continue; const x = i * 7.5; cyl(.08, .1, 6, M(0x222226, {metalness: .8}), x, 3, 31, CITY, 8); sph(.35, new THREE.MeshBasicMaterial({color: 0xffd9a8}), x, 6.1, 31, CITY); }
    for (let i = 0; i < 14; i++) { const x = -48 + i * 7.4, z = i % 2 ? -26 : 28; if (Math.abs(x) < 24 && z > 0) continue; cyl(.18, .25, 2.2, M(0x3b2a20), x, 1.1, z, CITY, 8); const f = mesh(new THREE.IcosahedronGeometry(1.7, 1), M(0x1f5a35, {flatShading: true, roughness: .9}), x, 3.4, z, CITY); f.scale.y = 1.2; }
    for (let i = 0; i < 90; i++) { const a = rnd() * Math.PI * 2, r = 100 + rnd() * 150, h = 12 + rnd() * 55; const bm = M(0x0e0c12, {roughness: .4, metalness: .6}); const b = box(8 + rnd() * 10, h, 8 + rnd() * 10, bm, Math.cos(a) * r, h / 2, Math.sin(a) * r, CITY); b.castShadow = false;
      const wt = canvasTex(64, 256, (x, w, hh) => { x.fillStyle = '#0b0a0f'; x.fillRect(0, 0, w, hh); for (let yy = 0; yy < hh; yy += 10) for (let xx = 0; xx < w; xx += 10) { if (rnd() > .72) { x.fillStyle = rnd() > .8 ? '#ff7aa8' : '#ffd49a'; x.globalAlpha = .4 + rnd() * .5; x.fillRect(xx + 2, yy + 2, 5, 6); x.globalAlpha = 1; } } }); bm.emissive = new THREE.Color(0xffffff); bm.emissiveMap = wt; bm.emissiveIntensity = .55; }}
  CITY.visible = !lite;

  // ---------------------------------------------------------------- personajes
  const CHARS = [], PICK = [];
  const SKIN = ['#f2cfb3', '#dcab86', '#b07a55', '#7d4f34'];
  const SAVED = new Map();
  const savedKey = (cid, clave) => `${cid || ''}|${clave}`;
  (SAVED_IN.items || []).forEach(it => SAVED.set(savedKey(it.company_id, it.clave), it));
  function layersOf(ch) {
    if (ch.kind === 'agent') return [SAVED.get(savedKey(null, 'agente:' + ch.id))];
    if (ch.kind === 'rep') return [SAVED.get(savedKey(ch.floor.cid, 'rep'))];
    if (ch.kind === 'staff') { const u = ch.def.uniform; return [SAVED.get(savedKey(null, 'plantilla:' + u)), SAVED.get(savedKey(ch.floor.cid, 'plantilla:' + u)), SAVED.get(savedKey(ch.floor.cid, 'persona:' + ch.id))]; }
    return [];
  }
  function arm(g, x, y, len, r, m, hand) { const p = new THREE.Group(); p.position.set(x, y, 0); g.add(p); cap(r, len, m, 0, -len / 2 - r * .5, 0, p); sph(r * 1.05, hand, 0, -len - r * 1.2, 0, p, 10, 8); return p; }
  function buildBody(ch) {
    const g = ch.body; while (g.children.length) g.remove(g.children[0]);
    const c = mergeCfg(ch.def, layersOf(ch).filter(Boolean)); if (ch.kind !== 'agent') { c.name = ch.def.name; } ch.cfg = c; ch.armL = ch.armR = null;
    if (c.hairStyle === 'largo' || (c.gender === 'mujer' && (!c.hairStyle || c.hairStyle === 'corto'))) c.long = true;   // el género del editor también se ve en el edificio
    const mb = M(c.color, {roughness: .8}), ms = M(c.style === 'lego' ? '#ffd34d' : c.skin, {roughness: .6}), mh = M(c.hair, {roughness: .9}), ml = M(c.legs || '#22202b', {roughness: .85}), shoe = M('#141216', {roughness: .5});
    let headY = 1.6, hr = .15, front = .15;
    if (c.style === 'lego') { [-.11, .11].forEach(x => { rbox(.2, .5, .26, ml, x, .25, 0, g, .03); }); rbox(.48, .12, .28, ml, 0, .55, 0, g, .03);
      const t = new THREE.Mesh(new THREE.CylinderGeometry(.22, .29, .55, 4, 1), mb); t.rotation.y = Math.PI / 4; t.position.y = .88; t.scale.z = .62; t.castShadow = true; g.add(t);
      ch.armL = arm(g, -.31, 1.1, .32, .075, mb, ms); ch.armR = arm(g, .31, 1.1, .32, .075, mb, ms);
      cyl(.2, .2, .34, ms, 0, 1.37, 0, g, 24); cyl(.11, .11, .08, ms, 0, 1.58, 0, g); headY = 1.37; hr = .2; front = .2;
      if (c.hair !== 'none') cyl(.215, .215, .16, mh, 0, 1.52, -.01, g, 24);
      [-.07, .07].forEach(x => sph(.022, M('#111'), x, 1.4, .195, g, 8, 6)); const sm = new THREE.Mesh(new THREE.TorusGeometry(.06, .012, 6, 12, Math.PI), M('#111')); sm.rotation.z = Math.PI; sm.position.set(0, 1.32, .198); g.add(sm); }
    else if (c.style !== 'real') { [-.1, .1].forEach(x => { cap(.08, .28, ml, x, .24, 0, g); rbox(.15, .08, .24, shoe, x, .04, .04, g, .03); });
      cap(.2, .26, mb, 0, .66, 0, g).scale.z = .8; ch.armL = arm(g, -.25, .86, .24, .06, mb, ms); ch.armR = arm(g, .25, .86, .24, .06, mb, ms);
      cyl(.06, .06, .1, ms, 0, .98, 0, g); sph(.32, ms, 0, 1.26, 0, g, 28, 22); headY = 1.26; hr = .32; front = .3;
      if (c.hair !== 'none') { const h = new THREE.Mesh(new THREE.SphereGeometry(.335, 28, 16, 0, Math.PI * 2, 0, Math.PI * .55), mh); h.position.set(0, 1.29, -.01); h.castShadow = true; g.add(h);
        for (let i = -2; i <= 2; i++) { const b = new THREE.Mesh(new THREE.ConeGeometry(.07, .2, 8), mh); b.position.set(i * .09, 1.47, .25); b.rotation.x = Math.PI * .82; g.add(b); }
        const back = sph(.3, mh, 0, 1.2, -.1, g); back.scale.set(1.05, 1.1, .8); }
      [-.12, .12].forEach(x => { const w = sph(.075, M('#ffffff', {roughness: .3}), x, 1.25, .27, g, 14, 10); w.scale.set(.8, 1.15, .4); const p = sph(.048, M('#1a1024', {roughness: .2}), x, 1.24, .3, g, 12, 8); p.scale.set(.8, 1.1, .4); sph(.016, new THREE.MeshBasicMaterial({color: '#fff'}), x + .02, 1.27, .315, g, 6, 4); const bl = sph(.04, M('#ff8fa3', {transparent: true, opacity: .55}), x * 1.45, 1.14, .26, g, 8, 6); bl.scale.z = .3; });
      const mo = new THREE.Mesh(new THREE.TorusGeometry(.04, .01, 6, 12, Math.PI), M('#7a2d3a')); mo.rotation.z = Math.PI; mo.position.set(0, 1.11, .305); g.add(mo); }
    else { [-.1, .1].forEach(x => { cap(.075, .62, ml, x, .44, 0, g); rbox(.13, .08, .27, shoe, x, .04, .05, g, .035); });
      rbox(.34, .2, .22, ml, 0, .84, 0, g, .08); const t = cap(.19, .34, mb, 0, 1.17, 0, g); t.scale.z = .68;
      rbox(.42, .1, .24, mb, 0, 1.36, 0, g, .05); ch.armL = arm(g, -.25, 1.37, .5, .062, mb, ms); ch.armR = arm(g, .25, 1.37, .5, .062, mb, ms);
      cyl(.055, .065, .12, ms, 0, 1.46, 0, g, 14); const h = sph(.13, ms, 0, 1.62, 0, g, 28, 22); h.scale.set(1, 1.18, 1.08); headY = 1.62; hr = .14; front = .14;
      sph(.035, ms, 0, 1.59, .14, g, 10, 8); [-.045, .045].forEach(x => { sph(.016, M('#2a1a12', {roughness: .2}), x, 1.645, .125, g, 8, 6); const ear = sph(.03, ms, x > 0 ? .13 : -.13, 1.62, 0, g, 8, 6); ear.scale.z = .6; });
      if (c.hair !== 'none') { const hh = new THREE.Mesh(new THREE.SphereGeometry(.142, 28, 14, 0, Math.PI * 2, 0, Math.PI * .52), mh); hh.scale.set(1, 1.18, 1.12); hh.position.set(0, 1.645, -.012); hh.castShadow = true; g.add(hh); if (c.long) { const lh = cap(.12, .25, mh, 0, 1.5, -.07, g); lh.scale.z = .6; } } }
    const am = M(c.accColor || '#222', {roughness: .4, metalness: .2}); const A = c.acc; const real = c.style === 'real';
    {
      if (A === 'audifonos') { const r = new THREE.Mesh(new THREE.TorusGeometry(hr * 1.08, .022, 8, 28, Math.PI), am); r.position.y = headY + (c.style === 'lego' ? .05 : hr * .2); g.add(r); [-1, 1].forEach(k => { const p = cyl(.055, .055, .05, am, k * hr * 1.05, headY, 0, g, 14); p.rotation.z = Math.PI / 2; }); }
      if (A === 'casco') { const r = new THREE.Mesh(new THREE.SphereGeometry(hr * 1.18, 24, 12, 0, Math.PI * 2, 0, Math.PI / 2), M(c.accColor || '#f59e0b', {roughness: .35})); r.position.y = headY + hr * .35; r.castShadow = true; g.add(r); cyl(hr * 1.35, hr * 1.35, .02, M(c.accColor || '#f59e0b'), 0, headY + hr * .35, 0, g, 24); }
      if (A === 'gorra') { const r = new THREE.Mesh(new THREE.SphereGeometry(hr * 1.08, 24, 12, 0, Math.PI * 2, 0, Math.PI / 2), am); r.position.y = headY + hr * .3; g.add(r); rbox(hr * 1.3, .02, hr * 1.1, am, 0, headY + hr * .32, hr * 1.05, g, .01); }
      if (A === 'gafas') { const gm = M('#0d0d0d', {metalness: .7, roughness: .2}); [-1, 1].forEach(k => { const l = new THREE.Mesh(new THREE.TorusGeometry(hr * .28, hr * .05, 6, 16), gm); l.position.set(k * hr * .38, headY + hr * .1, front + .01); g.add(l); }); rbox(hr * .3, hr * .05, hr * .05, gm, 0, headY + hr * .1, front + .01, g, .005); }
      if (A === 'chaleco') { const v = cap(real ? .2 : .21, real ? .3 : .24, M('#ff7a1a', {roughness: .6, emissive: 0x2a0e00}), 0, real ? 1.18 : c.style === 'lego' ? .88 : .67, 0, g); v.scale.set(1.04, 1, real ? .74 : .85); rbox(.44, .035, .02, M('#e5e7eb', {emissive: 0x555555}), 0, real ? 1.1 : .7, real ? .15 : .18, g, .01); }
      if (A === 'delantal') rbox(.34, .48, .02, M('#f4f1ea'), 0, real ? .98 : c.style === 'lego' ? .72 : .56, c.style === 'anime' ? .18 : c.style === 'lego' ? .17 : .14, g, .01);
      if (A === 'corbata') rbox(.05, .26, .02, M(c.accColor || '#b91c1c'), 0, real ? 1.22 : .9, real ? .135 : .17, g, .01);
    }
    g.traverse(o => { if (o.isMesh) { o.userData.ch = ch; PICK.push(o); } }); ch.tagH = headY + .5;
  }
  function rebuild(ch) { for (let i = PICK.length - 1; i >= 0; i--) if (PICK[i].userData.ch === ch) PICK.splice(i, 1); buildBody(ch); }
  function addChar(p, def, kind, seat) {
    const root = new THREE.Group(); const body = new THREE.Group(); root.add(body);
    const ring = new THREE.Mesh(new THREE.RingGeometry(.36, .46, 32), new THREE.MeshBasicMaterial({color: '#22c55e', transparent: true, opacity: .9, side: THREE.DoubleSide, depthWrite: false})); ring.rotation.x = -Math.PI / 2; ring.position.y = .03; root.add(ring);
    const ch = {id: def.id, kind, def: Object.assign({style: 'anime', color: '#f20b6d', skin: SKIN[0], hair: '#2b1b12', acc: 'none'}, def), root, body, ring, floor: p, state: 'work', path: [], home: seat, t: rnd() * 10};
    buildBody(ch); root.position.set(seat[0], 0, seat[1]); root.rotation.y = seat[2] || 0; p.g.add(root); CHARS.push(ch); paint(ch); return ch;
  }
  function removeChar(ch) {
    const i = CHARS.indexOf(ch); if (i >= 0) CHARS.splice(i, 1);
    for (let k = PICK.length - 1; k >= 0; k--) if (PICK[k].userData.ch === ch) PICK.splice(k, 1);
    if (ch.root.parent) ch.root.parent.remove(ch.root);
    const el = tagEls.get(ch); if (el) { el.remove(); tagEls.delete(ch); }
    if (ch.cafe) ch.cafe.used = null;
  }
  function paint(ch) {
    const col = ch.kind === 'rep' ? '#fbbf24' : ch.kind === 'staff' ? (ch.paused ? ST.wait.c : ST.work.c) : ST[agentVisualState(ch.state)].c;
    ch.ring.material.color.set(col);
  }
  function setState(ch, s) { ch.state = agentVisualState(s); paint(ch); }
  function walkTo(ch, x, z, then) { const p = ch.root.position; const cz = ch.floor.corr; ch.path = [[p.x, cz], [x, cz], [x, z]]; ch.then = then; }

  // ---------------------------------------------------------------- mobiliario
  const W_DESK = M('#d9d4cc', {roughness: .45}), W_DARK = M('#2a2730', {roughness: .5, metalness: .3}), CHROME = M('#c8c8cc', {metalness: .95, roughness: .2, envMapIntensity: 1});
  function chair(g, x, z, r = 0, col = '#1f1c24') { const c = new THREE.Group(); c.position.set(x, 0, z); c.rotation.y = r; g.add(c); const cm = M(col, {roughness: .85}); rbox(.5, .08, .48, cm, 0, .48, 0, c, .04); rbox(.48, .55, .07, cm, 0, .8, -.22, c, .035); cyl(.03, .03, .38, CHROME, 0, .28, 0, c, 8); for (let i = 0; i < 5; i++) { const a = i / 5 * Math.PI * 2; const l = rbox(.3, .03, .04, CHROME, Math.cos(a) * .14, .06, Math.sin(a) * .14, c, .01); l.rotation.y = -a; } return c; }
  function desk(p, x, z, r = 0, scr = '#3b82f6') { const g = new THREE.Group(); g.position.set(x, 0, z); g.rotation.y = r; p.g.add(g);
    rbox(1.7, .05, .8, W_DESK, 0, .75, 0, g, .02); [[-.8, -.36], [.8, -.36], [-.8, .36], [.8, .36]].forEach(([a, b]) => rbox(.05, .75, .05, W_DARK, a, .375, b, g, .015));
    rbox(.85, .5, .035, M('#0b0b0d', {roughness: .3, metalness: .4}), 0, 1.12, -.24, g, .02); mesh(new THREE.PlaneGeometry(.8, .45), new THREE.MeshBasicMaterial({color: scr}), 0, 1.12, -.22, g);
    rbox(.06, .3, .06, W_DARK, 0, .9, -.26, g, .02); rbox(.42, .02, .14, M('#e5e5e5'), -.05, .785, .08, g, .008); rbox(.08, .02, .12, M('#e5e5e5'), .3, .785, .1, g, .01);
    cyl(.04, .035, .09, M(['#f20b6d', '#fff', '#111'][Math.floor(rnd() * 3)]), .6, .82, .15, g, 12); chair(g, 0, .78, Math.PI); return g; }
  const seatOf = (x, z, r = 0) => [x + Math.sin(r) * .62, z + Math.cos(r) * .62, r + Math.PI];
  function plant(p, x, z, s = 1) { if (lite && s < 1.25) return; const g = new THREE.Group(); g.position.set(x, 0, z); g.scale.setScalar(s); p.g.add(g); cyl(.22, .17, .42, M('#e7e3dc', {roughness: .4}), 0, .21, 0, g, 18); for (let i = 0; i < 7; i++) { const l = sph(.2 + rnd() * .12, M('#2d7a46', {roughness: .8}), (rnd() - .5) * .35, .6 + rnd() * .55, (rnd() - .5) * .35, g, 10, 8); l.scale.y = 1.3; } }
  function rug(p, x1, z1, x2, z2, col) { const m = mesh(new THREE.PlaneGeometry(x2 - x1, z2 - z1), M(col, {map: TX.alfombra, roughness: 1}), (x1 + x2) / 2, .015, (z1 + z2) / 2, p.g); m.rotation.x = -Math.PI / 2; m.castShadow = false; return m; }
  function zoneLabel(p, txt, x, z, w = 7) { const m = mesh(new THREE.PlaneGeometry(w, w / 4), new THREE.MeshBasicMaterial({map: textTex([txt], {w: 768, h: 192, fg: 'rgba(255,255,255,.75)', size: 96}), transparent: true, depthWrite: false}), x, .03, z, p.g); m.rotation.x = -Math.PI / 2; m.castShadow = false; return m; }
  function glassWall(p, x, z, w, d, h = 2.6) { const m = new THREE.MeshPhysicalMaterial({color: 0xcfe3ff, transparent: true, opacity: .14, roughness: .05, metalness: .1, depthWrite: false}); mesh(new THREE.BoxGeometry(w, h, d), m, x, h / 2, z, p.g).castShadow = false; rbox(w > d ? w : .06, .05, w > d ? .06 : d, frameMat, x, h, z, p.g, .01); }
  function screenWall(p, x, z, w, h, tx, r = 0, y0 = .9) { const g = new THREE.Group(); g.position.set(x, y0, z); g.rotation.y = r; p.g.add(g); rbox(w + .12, h + .12, .06, M('#0b0b0d', {metalness: .5, roughness: .3}), 0, h / 2, 0, g, .03); mesh(new THREE.PlaneGeometry(w, h), new THREE.MeshBasicMaterial({map: tx, toneMapped: false}), 0, h / 2, .035, g); return g; }
  function pendant(p, x, z, y, col = 0xffd9a8) { if (lite) return; cyl(.005, .005, 1, M('#111'), x, y + .5, z, p.g, 4); mesh(new THREE.ConeGeometry(.22, .22, 20, 1, true), M('#111', {side: THREE.DoubleSide, metalness: .6}), x, y, z, p.g); sph(.07, new THREE.MeshBasicMaterial({color: col}), x, y - .08, z, p.g, 10, 8); }
  function sofa(p, x, z, r = 0, col = '#3b2f4a') { const g = new THREE.Group(); g.position.set(x, 0, z); g.rotation.y = r; p.g.add(g); const m = M(col, {roughness: .95}); rbox(2, .35, .85, m, 0, .3, 0, g, .1); rbox(2, .55, .22, m, 0, .6, -.32, g, .1); rbox(.22, .45, .85, m, -.95, .45, 0, g, .08); rbox(.22, .45, .85, m, .95, .45, 0, g, .08); }
  function roundTable(p, x, z, r = .75, top = '#e9e4ef') { cyl(r, r, .05, M(top, {roughness: .35}), x, .76, z, p.g, 28); cyl(.05, .05, .74, CHROME, x, .38, z, p.g, 10); cyl(.3, .32, .03, CHROME, x, .015, z, p.g, 20); }

  // ---------------------------------------------------------------- pisos
  const FLOORS = []; const H = 5.2;
  function neonEdge(w, d, y, p) { [[0, -d / 2, w, .06], [0, d / 2, w, .06], [-w / 2, 0, .06, d], [w / 2, 0, .06, d]].forEach(([x, z, a, b]) => { const k = box(a, .07, b, neonMat, x, y, z, p); k.castShadow = false; }); }
  function makeFloor(o) {
    const p = Object.assign({corr: 0, anim: []}, o); p.g = new THREE.Group(); p.g.position.y = p.y; S.add(p.g); const h = p.H || H; p.h = h;
    const slab = rbox(p.W + .8, .45, p.D + .8, slabMat, 0, -.225, 0, p.g, .05); slab.userData.floor = p; PICK.push(slab);
    neonEdge(p.W + .84, p.D + .84, -.03, p.g);
    const fl = mesh(new THREE.PlaneGeometry(p.W, p.D), M(p.floorCol || '#ffffff', {map: p.tex || TX.madera, roughness: p.rough ?? .55, envMapIntensity: .6}), 0, .01, 0, p.g); fl.rotation.x = -Math.PI / 2; fl.castShadow = false;
    p.front = []; p.shell = [];
    const fh = h - .45; [[0, -p.D / 2, p.W, .04, 0], [0, p.D / 2, p.W, .04, 1], [-p.W / 2, 0, .04, p.D, 0], [p.W / 2, 0, .04, p.D, 0]].forEach(([x, z, w, d, f]) => { const b = new THREE.Mesh(new THREE.BoxGeometry(w, fh, d), facadeGlass); b.position.set(x, fh / 2, z); p.g.add(b); (f ? p.front : p.shell).push(b); });
    for (let i = -p.W / 2; i <= p.W / 2 + .01; i += 2.5) { const a = box(.1, fh, .22, frameMat, i, fh / 2, p.D / 2 + .08, p.g), b = box(.1, fh, .22, frameMat, i, fh / 2, -p.D / 2 - .08, p.g); p.front.push(a); p.shell.push(b); }
    for (let i = -p.D / 2; i <= p.D / 2 + .01; i += 2.5) { p.shell.push(box(.22, fh, .1, frameMat, -p.W / 2 - .08, fh / 2, i, p.g), box(.22, fh, .1, frameMat, p.W / 2 + .08, fh / 2, i, p.g)); }
    p.ceil = box(p.W, .1, p.D, M('#141217'), 0, fh + .05, 0, p.g); p.ceil.castShadow = false;
    for (let i = 0; i < 5; i++) for (let j = 0; j < 3; j++) { const l = box(p.W / 9, .03, .9, new THREE.MeshBasicMaterial({color: p.light || 0xfff4e6}), -p.W / 2 + p.W / 10 + i * p.W / 5, fh - .02, -p.D / 3 + j * p.D / 3, p.g); l.castShadow = false; p.front.push(l); }
    rbox(3, fh, .6, M('#1a181d', {metalness: .5, roughness: .35}), 0, fh / 2, p.D / 2 - .5, p.g, .04); rbox(1.6, 2.4, .04, CHROME, 0, 1.2, p.D / 2 - .82, p.g, .01);
    p.door = [0, p.D / 2 - 1.4];
    FLOORS.push(p); return p;
  }
  function dropFloor(p) {
    CHARS.filter(c => c.floor === p).forEach(removeChar);
    for (let k = PICK.length - 1; k >= 0; k--) { let o = PICK[k]; let inside = false; while (o) { if (o === p.g) { inside = true; break; } o = o.parent; } if (inside) PICK.splice(k, 1); }
    S.remove(p.g); const i = FLOORS.indexOf(p); if (i >= 0) FLOORS.splice(i, 1);
    const el = flEls.get(p); if (el) { el.remove(); flEls.delete(p); }
  }

  // --- Recepción
  const lobby = makeFloor({key: 'lobby', name: 'Recepción', sub: 'Entrada del edificio', y: .45, W: 36, D: 24, H: 5.6, tex: TX.negro, rough: .15, corr: 2});
  rbox(7, 1.1, 1.3, M('#0f0d12', {metalness: .6, roughness: .25}), 0, .55, -4, lobby.g, .1); box(7.04, .04, 1.34, neonMat, 0, 1.1, -4, lobby.g);
  {const m = mesh(new THREE.PlaneGeometry(4.6, 1), new THREE.MeshBasicMaterial({map: WM_LOGO, transparent: true, toneMapped: false}), 0, 3.2, -11.85, lobby.g); m.castShadow = false; rbox(10, 4.4, .2, M('#0c0b0e', {roughness: .3, metalness: .5}), 0, 2.6, -11.95, lobby.g, .04);}
  plant(lobby, -15, -9, 1.6); plant(lobby, 15, -9, 1.6); plant(lobby, -15, 8, 1.3); plant(lobby, 15, 8, 1.3); sofa(lobby, -9, 4, Math.PI / 2, '#2a2530'); sofa(lobby, 9, 4, -Math.PI / 2, '#2a2530');
  {rbox(14, .3, 5, M('#0b0a0d', {metalness: .7, roughness: .25}), 0, 4.4, 15, S, .05); box(14.04, .05, 5.04, neonMat, 0, 4.25, 15); [-6.5, 6.5].forEach(x => cyl(.15, .15, 4.3, CHROME, x, 2.15, 17.2, S, 12));
    const t = mesh(new THREE.PlaneGeometry(7, 1.5), new THREE.MeshBasicMaterial({map: WM_LOGO, transparent: true, toneMapped: false}), 0, 4.4, 17.52); t.castShadow = false;}

  // --- plantillas de piso de clientes (mobiliario + puestos para el personal)
  const TPL = {};
  const TPL_OPTS = {taller: {tex: TX.concreto, floorCol: '#cfc9c4'}, restaurante: {tex: TX.terracota}, bar: {tex: TX.negro, rough: .12, light: 0xc4a6ff},
    campo: {tex: TX.tecnico, light: 0xe6f4ff}, general: {tex: TX.madera}};
  TPL.taller = (p) => {
    zoneLabel(p, 'Producción', -6, 1.5); zoneLabel(p, 'Corte', 12, 1.5, 5); zoneLabel(p, 'Lotes', -11, 4, 5);
    const seats = [];
    for (let r = 0; r < 2; r++) for (let i = 0; i < 5; i++) { const x = -14 + i * 4.4, z = -7.5 + r * 4.4; const g = new THREE.Group(); g.position.set(x, 0, z); p.g.add(g);
      rbox(1.3, .05, .75, M('#c7b8a3', {roughness: .5}), 0, .74, 0, g, .02); [[-.58, -.3], [.58, -.3], [-.58, .3], [.58, .3]].forEach(([a, b]) => box(.04, .74, .04, W_DARK, a, .37, b, g));
      const mw = M('#f4f2ee', {roughness: .35}); rbox(.62, .16, .26, mw, .05, .85, 0, g, .05); rbox(.16, .38, .24, mw, .3, 1.05, 0, g, .05); rbox(.56, .15, .22, mw, .08, 1.26, 0, g, .06); cyl(.012, .012, .18, CHROME, -.15, 1.1, 0, g, 6); cyl(.06, .06, .04, M('#111'), .38, 1.05, .13, g, 14);
      cyl(.03, .03, .06, M(['#ec4899', '#8b5cf6', '#f59e0b', '#22c55e'][i % 4]), .25, 1.37, 0, g, 10);
      const cloth = mesh(new THREE.PlaneGeometry(.5, .4), M(['#f9a8d4', '#c4b5fd', '#fecaca', '#fde68a'][(i + r) % 4], {side: THREE.DoubleSide, roughness: .9}), -.25, .775, .05, g); cloth.rotation.x = -Math.PI / 2;
      chair(g, 0, .72, Math.PI, '#3b2f3a'); seats.push([x, z + .72, Math.PI]); }
    rbox(6, .9, 2.2, M('#e9e2d6'), 12, .45, -6, p.g, .04); for (let i = 0; i < 5; i++) rbox(.9, .04, .6, M(['#f472b6', '#c084fc', '#fda4af', '#e9d5ff', '#fbcfe8'][i], {roughness: .95}), 9.6 + i * 1.2, .92, -6, p.g, .01);
    for (let i = 0; i < 3; i++) { const x = 6 + i * 2.2; cyl(.025, .025, 1.6, CHROME, x, .8, -2, p.g, 6); sph(.18, M('#e7e3dc'), x, 1.65, -2, p.g, 12, 10); cap(.16, .5, M(['#f9a8d4', '#ddd6fe', '#fecaca'][i], {roughness: .9}), x, 1.1, -2, p.g); }
    for (let i = 0; i < 6; i++) rbox(1.4, 1.2, 1, M(['#a78bfa', '#f9a8d4', '#fcd34d', '#86efac', '#93c5fd', '#fca5a5'][i], {roughness: .9}), -15 + i * 1.8, .6, 9.5, p.g, .05);
    p.screen = textTex(['Lote activo', 'cargando…'], {w: 768, h: 336, size: 60, bg: '#1a1220'}); screenWall(p, 12, -10.85, 5.5, 2.4, p.screen); plant(p, 16, 9.5, 1.3);
    p.screenLines = f => { const k = Object.fromEntries((f.kpis || []).map(([a, b]) => [a, b])); return [k['Lote activo'] && k['Lote activo'] !== '—' ? 'Lote ' + k['Lote activo'] : 'Sin lote activo', `${k['Avance del lote'] || '—'} · ${k['Personas en turno'] || '—'} en turno`]; };
    return {rep: [2, 9.2, Math.PI], repDef: {color: '#db2777', hair: '#111', acc: 'gafas', long: true}, stations: {costura: seats, any: seats.concat([[10, -4.4, Math.PI], [12, -4.4, Math.PI], [14, -4.4, Math.PI]])}};
  };
  TPL.restaurante = (p) => {
    zoneLabel(p, 'Cocina', -10, -1, 5); zoneLabel(p, 'Salón', 7, -1, 5); zoneLabel(p, 'Caja y domicilios', 10, 2.5, 7);
    rbox(5, 1, 1.5, M('#1e1e20', {metalness: .7, roughness: .35}), -10, .5, -8, p.g, .04); const coals = box(4.6, .06, 1.1, new THREE.MeshBasicMaterial({color: '#ff5a1f'}), -10, 1.02, -8, p.g); coals.castShadow = false;
    for (let i = 0; i < 6; i++) { const sk = cyl(.06, .06, .5, M('#7c2d12', {roughness: .6}), -12 + i * .8, 1.1, -8, p.g, 8); sk.rotation.z = Math.PI / 2; }
    rbox(5, 1.6, .5, M('#3a3a3e', {metalness: .6}), -10, 2.8, -10.6, p.g, .04);
    const fire = new THREE.PointLight(0xff6a2a, 1.4, 9); fire.position.set(-10, 2, -8); p.g.add(fire);
    rbox(6, .95, 1.1, M('#b8b8bd', {metalness: .85, roughness: .25}), -10, .475, -3.6, p.g, .03);
    for (let i = 0; i < 3; i++) for (let j = 0; j < 2; j++) { const x = 1 + i * 5, z = -8 + j * 4.5; rbox(1.8, .06, 1.1, M('#7c4a2a', {roughness: .5}), x, .76, z, p.g, .02); box(.08, .74, .08, W_DARK, x, .37, z, p.g); [[-1.15, 0, Math.PI / 2], [1.15, 0, -Math.PI / 2]].forEach(([a, b, r]) => { const c = new THREE.Group(); c.position.set(x + a, 0, z + b); c.rotation.y = r; p.g.add(c); rbox(.45, .06, .45, M('#5b3a26'), 0, .46, 0, c, .02); rbox(.45, .5, .05, M('#5b3a26'), 0, .72, -.2, c, .02); }); pendant(p, x, z, 2.6); }
    rbox(4, 1.1, 1, M('#e9e4dc'), 10, .55, 5.5, p.g, .06);
    {const mo = new THREE.Group(); mo.position.set(14, 0, 8.5); mo.rotation.y = Math.PI / 2; p.g.add(mo); rbox(1.5, .35, .36, M('#dc2626', {metalness: .4, roughness: .35}), 0, .62, 0, mo, .12); [-.6, .6].forEach(x => { const w = new THREE.Mesh(new THREE.TorusGeometry(.28, .08, 10, 20), M('#111')); w.position.set(x, .32, 0); mo.add(w); }); rbox(.5, .5, .5, M('#f59e0b'), -.45, 1.05, 0, mo, .04);}
    p.screen = textTex(['Comandas en cocina', 'cargando…'], {w: 768, h: 308, size: 56, bg: '#20140c'}); screenWall(p, -3, -10.85, 5.5, 2.2, p.screen);
    p.screenLines = f => { const k = Object.fromEntries((f.kpis || []).map(([a, b]) => [a, b])); return [`En cocina ahora: ${k['En cocina ahora'] ?? '—'}`, `${k['Pedidos del día'] ?? '—'} pedidos · ${k['Domicilios del día'] ?? '—'} domicilios hoy`]; };
    p.anim.push(t => { coals.material.color.setHSL(.04 + Math.sin(t * 5) * .01, 1, .5 + Math.sin(t * 7) * .05); fire.intensity = 1.2 + Math.sin(t * 9) * .3; });
    const mesero = [[3.5, -4, 0], [8.5, -6, 0], [13.5, -4, 0], [3.5, .5, 0], [8.5, .5, 0], [13.5, .5, 0]];
    return {rep: [7, 6, Math.PI], repDef: {color: '#ea580c', hair: '#222', acc: 'gorra', accColor: '#111'},
      stations: {cocina: [[-11.5, -6.7, Math.PI], [-8, -6.7, Math.PI], [-12, -2.5, Math.PI], [-9.5, -2.5, Math.PI], [-7, -2.5, Math.PI]], mesero, caja: [[10, 4.4, 0], [11.5, 4.4, 0]],
        domiciliario: [[12.6, 8.5, Math.PI / 2], [11.2, 9.4, Math.PI / 2], [12.6, 10, Math.PI / 2]], any: mesero.concat([[5, 3, 0], [2, 3, 0]])}};
  };
  TPL.bar = (p) => {
    rbox(12, 1.12, 1.1, M('#2a1a12', {roughness: .45}), -8.5, .56, -6, p.g, .05); rbox(12.4, .06, 1.4, M('#0a0a0a', {metalness: .6, roughness: .12}), -8.5, 1.15, -6, p.g, .02); box(12.2, .04, .04, neonMat, -8.5, .25, -5.42, p.g);
    for (let i = 0; i < 5; i++) { const st = new THREE.Group(); st.position.set(-13 + i * 2.2, 0, -4.6); p.g.add(st); cyl(.22, .22, .06, M('#111', {metalness: .5}), 0, .78, 0, st, 16); cyl(.03, .03, .78, CHROME, 0, .39, 0, st, 8); }
    for (let s = 0; s < 3; s++) { rbox(12, .05, .4, M('#2a1a12'), -8.5, 1.7 + s * .6, -10.6, p.g, .01); for (let i = 0; i < (lite ? 8 : 16); i++) { const c = ['#22c55e', '#f59e0b', '#ef4444', '#60a5fa', '#e879f9', '#fde68a'][(i + s) % 6]; cyl(.07, .08, .38, M(c, {transparent: true, opacity: .8, roughness: .1, metalness: .1, emissive: c, emissiveIntensity: .25}), -14 + i * (lite ? 1.46 : .73), 1.92 + s * .6, -10.6, p.g, 10); } }
    const tiles = []; for (let i = 0; i < 5; i++) for (let j = 0; j < 4; j++) { const t = box(1.9, .04, 1.9, new THREE.MeshBasicMaterial({color: '#7c3aed'}), 3 + i * 2, .04, -9 + j * 2, p.g); t.castShadow = false; tiles.push(t); }
    rbox(3, 1.15, 1.1, M('#0d0d0f', {metalness: .5}), 14, .58, -8, p.g, .05); box(2.6, .04, .8, new THREE.MeshBasicMaterial({color: '#e879f9'}), 14, 1.17, -8, p.g); [13.3, 14.7].forEach(x => cyl(.25, .25, .05, M('#222'), x, 1.2, -8, p.g, 24));
    for (let i = 0; i < 4; i++) { const x = -12 + i * 7, z = 7; cyl(.65, .65, .05, M('#1a1a1d', {metalness: .5, roughness: .2}), x, 1, z, p.g, 24); cyl(.05, .05, 1, CHROME, x, .5, z, p.g, 8); pendant(p, x, z, 3, 0xe9d5ff); sofa(p, x, z + 1.6, Math.PI, '#4c1d95'); }
    p.screen = textTex(['Canciones pedidas', 'cargando…'], {w: 900, h: 388, size: 72, bg: '#24104a'}); screenWall(p, 8, -10.85, 6.5, 2.8, p.screen);
    p.screenLines = f => { const k = Object.fromEntries((f.kpis || []).map(([a, b]) => [a, b])); return [`🎵 ${k['Canciones pedidas'] ?? '—'} canciones pedidas`, `${k['Mesas abiertas'] ?? '—'} mesas abiertas · ${k['Pedidos a barra'] ?? '—'} pedidos`]; };
    const disco = new THREE.PointLight(0xe879f9, 1.3, 14); disco.position.set(7, 3.5, -6); p.g.add(disco); const ball = sph(.4, M('#ddd', {metalness: 1, roughness: .05, envMapIntensity: 2}), 7, 3.9, -6, p.g, 20, 14);
    p.anim.push(t => { tiles.forEach((tl, i) => tl.material.color.setHSL((t * .15 + i * .07) % 1, .8, .42)); disco.intensity = 1.1 + Math.sin(t * 6) * .4; ball.rotation.y = t * .6; });
    const barman = [[-11, -7.4, 0], [-6, -7.4, 0], [-8.5, -7.4, 0], [-3.5, -7.4, 0], [-13.5, -7.4, 0]], mesero = [[-9, 4.6, 0], [-2, 4.6, 0], [5, 4.6, 0], [12, 4.6, 0]];
    return {rep: [2, 9.2, Math.PI], repDef: {color: '#7c3aed', hair: '#111', acc: 'audifonos', accColor: '#e879f9'},
      stations: {barman, dj: [[14, -9.2, 0]], mesero, caja: [[-1.2, -6, -Math.PI / 2]], cocina: [[-13.5, -9.3, 0]], any: barman.concat(mesero)}};
  };
  TPL.campo = (p, f) => {
    const ops = (f.staff && f.staff.ops && f.staff.ops.length ? f.staff.ops.map(o => o.name) : (f.kpis[0] && /·/.test(f.kpis[0][0]) ? f.kpis[0][0].split('·')[1].split('/').map(s => s.trim()) : [])).slice(0, 2);
    while (ops.length < 2) ops.push(ops.length ? 'Otra operación' : 'Operación');
    p.ops = ops; p.signs = {};
    [-1, 1].forEach((side, k) => {
      zoneLabel(p, ops[k], side * 9, 6.5, 7);
      for (let i = 0; i < 4; i++) { const x = side * (3 + i * 3.4), z = -7.5; rbox(1.1, 2.6, 1.1, M('#141418', {metalness: .6, roughness: .3}), x, 1.3, z, p.g, .03); mesh(new THREE.PlaneGeometry(.95, 2.4), M('#0c0c10', {metalness: .7, roughness: .15, transparent: true, opacity: .85}), x, 1.3, z + .56, p.g); for (let q = 0; q < (lite ? 4 : 10); q++) { const led = box(.04, .04, .02, new THREE.MeshBasicMaterial({color: q % 3 ? '#22c55e' : '#38bdf8'}), x - .35 + (q % 5) * .17, .4 + Math.floor(q / 5) * 1.8 + (q % 2) * .2, z + .57, p.g); led.castShadow = false; } }
      rbox(13, .08, .4, M('#f59e0b', {metalness: .4}), side * 8.6, 2.9, -7.5, p.g, .02);
      const scr = textTex([ops[k], 'cargando…'], {w: 800, h: 306, size: 58, bg: side < 0 ? '#0d1d15' : '#0d1820'}); screenWall(p, side * 9, 10.85, 6, 2.3, scr, Math.PI);
      const sign = textTex(['+0', 'en turno'], {w: 512, h: 192, size: 84, bg: '#0b1a12', fg: '#22c55e'}); const sg = screenWall(p, side * 11.5, -1.6, 3.2, 1.2, sign, side > 0 ? -Math.PI / 2 : Math.PI / 2, 1);
      p.signs[ops[k]] = {screen: scr, sign, group: sg, side};
    });
    desk(p, 0, 4, 0, '#22c55e'); for (let i = 0; i < 4; i++) rbox(.6, .5, .4, M('#c2410c'), -15 + i * .7, .25, 9.6, p.g, .03);
    const st = {any: []};
    ops.forEach((name, k) => { const side = k ? 1 : -1; st['op:' + name] = Array.from({length: 5}, (_, i) => [side * (3.5 + (i % 3) * 3.4), -4 + Math.floor(i / 3) * 2.6, Math.PI]); });
    return {rep: seatOf(0, 4), repDef: {color: '#16a34a', hair: '#222', acc: 'chaleco', style: 'real'}, stations: st};
  };
  TPL.general = (p) => {
    zoneLabel(p, 'Oficina', -4, 1.2, 6); const seats = [];
    for (let r = 0; r < 2; r++) for (let i = 0; i < 5; i++) { const x = -12 + i * 5, z = -8 + r * 5; desk(p, x, z, 0, '#38bdf8'); seats.push(seatOf(x, z)); }
    sofa(p, 10, 7, Math.PI, '#2a2530'); plant(p, -15, 8, 1.3); plant(p, 15, -9, 1.3);
    p.screen = textTex(['Oficina', 'cargando…'], {w: 768, h: 308, size: 56, bg: '#141a24'}); screenWall(p, 8, -10.85, 5.5, 2.2, p.screen);
    p.screenLines = f => [`${(f.staff && f.staff.total) ?? '—'} personas en turno`, `Última actividad ${f.last_activity || ''}`];
    return {rep: [2, 6, Math.PI], repDef: {color: '#0ea5e9', hair: '#222', acc: 'gafas'}, stations: {any: seats}};
  };

  // ---------------------------------------------------------------- piso CLONEXA (doble altura)
  const cx = makeFloor({key: 'clonexa', name: 'CLONEXA', sub: 'Piso principal · agentes de IA', y: floorYs(0).clonexa, W: 46, D: 30, H: 6.6, tex: TX.madera, floorCol: '#ffffff', corr: 0});
  rug(cx, -22, -14, -9.5, -2.5, '#4a2a3a'); rug(cx, -8.5, -14, 6.5, -2.5, '#2f2a44'); rug(cx, 7.5, -14, 22, -2.5, '#23324a'); rug(cx, -22, 2.5, -5.5, 14, '#24363c');
  zoneLabel(cx, 'Gerencia', -15.5, -1.2); zoneLabel(cx, 'Marketing', -1, -1.2); zoneLabel(cx, 'Ventas', 15, -1.2, 6); zoneLabel(cx, 'Operaciones', -13.5, 1.6); zoneLabel(cx, 'Cafetería', 14, 1.6, 6);
  glassWall(cx, -9, -8.5, .06, 12); glassWall(cx, 7, -8.5, .06, 12); glassWall(cx, -5, 8.5, .06, 12); glassWall(cx, 5, 8.5, .06, 12);
  desk(cx, -19, -9, 0, '#f20b6d'); rbox(5, .07, 2.2, M('#1b1820', {metalness: .5, roughness: .15}), -13, .76, -7, cx.g, .03); cyl(.12, .25, .74, CHROME, -13, .37, -7, cx.g, 12);
  [[-14.6, -8.4, 0], [-13, -8.4, 0], [-11.4, -8.4, 0], [-14.6, -5.6, Math.PI], [-11.4, -5.6, Math.PI]].forEach(([x, z, r]) => chair(cx.g, x, z, r, '#3a2030'));
  const approvalsTex = textTex(['Sala de aprobaciones', 'cargando…'], {w: 768, h: 338, size: 56, bg: '#2a0f22'}); screenWall(cx, -13, -14.85, 5, 2.2, approvalsTex); plant(cx, -21.5, -13.5, 1.3);
  {const m = mesh(new THREE.PlaneGeometry(1.4, 2.24), new THREE.MeshBasicMaterial({map: ST_LOGO, toneMapped: false}), -21.9, 2.2, -8, cx.g); m.rotation.y = Math.PI / 2;}
  [[-6, -10], [-2, -10], [2, -10], [-6, -5], [-2, -5]].forEach(([x, z]) => desk(cx, x, z, 0, '#a855f7'));
  const calendarTex = textTex(['Calendario de contenido', 'cargando…'], {w: 768, h: 338, size: 52, bg: '#1c1238'}); screenWall(cx, 1, -14.85, 5, 2.2, calendarTex);
  [[10, -10], [14, -10], [10, -5], [14, -5]].forEach(([x, z]) => desk(cx, x, z, 0, '#22c55e'));
  screenWall(cx, 19, -14.85, 5.6, 2.4, canvasTex(768, 330, (x) => { x.fillStyle = '#0b1611'; x.fillRect(0, 0, 768, 330); x.strokeStyle = '#1f3b2c'; x.lineWidth = 2; for (let i = 0; i < 26; i++) { x.beginPath(); x.moveTo(rnd() * 768, 0); x.lineTo(rnd() * 768, 330); x.stroke(); } const g = x.createRadialGradient(330, 190, 0, 330, 190, 150); g.addColorStop(0, 'rgba(242,11,109,.85)'); g.addColorStop(1, 'rgba(242,11,109,0)'); x.fillStyle = g; x.fillRect(0, 0, 768, 330); x.fillStyle = '#fff'; x.font = '800 34px Inter, system-ui'; x.fillText('Mapa comercial', 20, 44); }));
  [[-20, 6], [-16, 6], [-12, 6], [-20, 11], [-16, 11]].forEach(([x, z]) => desk(cx, x, z, Math.PI, '#38bdf8'));
  for (let i = 0; i < 3; i++) { rbox(1, 2.6, 1, M('#121216', {metalness: .6, roughness: .3}), -7.5, 1.3, 4.2 + i * 1.3, cx.g, .03); for (let k = 0; k < 6; k++) { const l = box(.02, .04, .04, new THREE.MeshBasicMaterial({color: k % 2 ? '#f20b6d' : '#38bdf8'}), -6.99, .5 + k * .35, 4 + i * 1.3 + (k % 3) * .15, cx.g); l.castShadow = false; } }
  rbox(5, 1.05, 1, M('#2a1d16', {roughness: .4}), 15, .525, 13.6, cx.g, .05); rbox(5.1, .05, 1.1, M('#e9e4dc', {roughness: .25}), 15, 1.08, 13.6, cx.g, .02); rbox(.5, .6, .45, CHROME, 13.4, 1.4, 13.6, cx.g, .05);
  const cafeSpots = []; [[9, 5.5], [15, 5.5], [20.5, 6], [9, 10], [15, 10]].forEach(([x, z]) => { roundTable(cx, x, z, .7); pendant(cx, x, z, 3.4); [[1.05, 0, -Math.PI / 2], [-1.05, 0, Math.PI / 2]].forEach(([a, b, r]) => { chair(cx.g, x + a, z + b, r, '#5b4636'); cafeSpots.push([x + a * .7, z, r]); }); });
  sofa(cx, 20.5, 10.5, -Math.PI / 2, '#4c1d95'); plant(cx, 22, 3, 1.3); plant(cx, -22, 14, 1.3); plant(cx, 6, -13.5); plant(cx, 22, -13.5, 1.3);
  const crown = new THREE.Group(); S.add(crown);
  rbox(cx.W + .8, .5, cx.D + .8, M('#0b0a0d', {metalness: .7, roughness: .3}), 0, .25, 0, crown, .06); neonEdge(cx.W + .84, cx.D + .84, .5, crown); for (let i = 0; i < 4; i++) { rbox(3, 1.4, 2.2, M('#1a191d', {metalness: .6, roughness: .4}), -14 + i * 5, 1.2, -8, crown, .08); cyl(.7, .7, .15, M('#2a292e', {metalness: .7}), -14 + i * 5, 1.98, -8, crown, 20); }
  {const hp = mesh(new THREE.CircleGeometry(5, 40), M('#141317', {roughness: .6}), 12, .52, -4, crown); hp.rotation.x = -Math.PI / 2; const hl = mesh(new THREE.RingGeometry(4.3, 4.5, 48), neonMat, 12, .53, -4, crown); hl.rotation.x = -Math.PI / 2;}
  rbox(16, 4.2, .5, M('#09080b', {metalness: .7, roughness: .25}), 0, 2.6, cx.D / 2 - 1, crown, .08);
  {const m = mesh(new THREE.PlaneGeometry(13, 2.7), new THREE.MeshBasicMaterial({map: WM_LOGO, transparent: true, toneMapped: false}), 0, 2.6, cx.D / 2 - .73, crown); m.castShadow = false;}
  {const m = mesh(new THREE.PlaneGeometry(2.4, 3.84), new THREE.MeshBasicMaterial({map: ST_LOGO, toneMapped: false}), -cx.W / 2 - .45, -6, cx.D / 2 - 6, crown); m.rotation.y = -Math.PI / 2;}

  // agentes de Clonexa (diseño de la maqueta; lo guardado en el editor manda)
  const A = [
    {id: 'director', name: 'Tú · Director', role: 'Apruebas todo desde Telegram', zone: 'Gerencia', seat: seatOf(-19, -9), style: 'real', color: '#16161c', legs: '#16161c', hair: '#1b120c', skin: SKIN[1], acc: 'corbata', accColor: '#f20b6d'},
    {id: 'asistente', name: 'Nexa Asistente', role: 'Asistente de gerencia · bot de comandos', zone: 'Gerencia', seat: [-13, -4.9, Math.PI], style: 'anime', color: '#f20b6d', hair: '#3b1d14', skin: SKIN[0], acc: 'audifonos', accColor: '#f4f4f5'},
    {id: 'creativo', name: 'Director creativo', role: 'Paquete semanal de contenido', zone: 'Marketing', seat: seatOf(-6, -10), style: 'anime', color: '#7c3aed', hair: '#111', skin: SKIN[2], acc: 'gafas'},
    {id: 'contenido', name: 'Nexa Contenido', role: 'Vista previa 6 p. m. · publica L/M/V 12 m.', zone: 'Marketing', seat: seatOf(-2, -10), style: 'anime', color: '#ec4899', hair: '#6b3a1f', skin: SKIN[0]},
    {id: 'planb', name: 'Plan B', role: 'Arma un anuncio si falta contenido', zone: 'Marketing', seat: seatOf(2, -10), style: 'anime', color: '#f59e0b', hair: '#222', skin: SKIN[3], acc: 'gorra', accColor: '#f20b6d'},
    {id: 'tiktok', name: 'Nexa TikTok', role: 'Publicará en TikTok', zone: 'Marketing', seat: seatOf(-6, -5), style: 'anime', color: '#06b6d4', hair: '#111', skin: SKIN[1], acc: 'audifonos', accColor: '#e879f9'},
    {id: 'analista', name: 'Analista', role: 'Reporte de crecimiento semanal', zone: 'Marketing', seat: seatOf(-2, -5), style: 'real', color: '#334155', hair: '#7c4a1e', skin: SKIN[0], acc: 'gafas'},
    {id: 'ventas', name: 'Nexa Ventas', role: 'WhatsApp · responde a quien escribe', zone: 'Ventas', seat: seatOf(10, -10), style: 'anime', color: '#16a34a', hair: '#2b1b12', skin: SKIN[1], acc: 'audifonos', accColor: '#111'},
    {id: 'correos', name: 'Nexa Correos', role: 'Lee la bandeja y marca respuestas', zone: 'Ventas', seat: seatOf(14, -10), style: 'anime', color: '#0ea5e9', hair: '#5b3a1f', skin: SKIN[0]},
    {id: 'prospecta', name: 'Prospectora', role: 'Busca negocios por zona', zone: 'Ventas', seat: seatOf(10, -5), style: 'anime', color: '#84cc16', hair: '#111', skin: SKIN[2], acc: 'gorra', accColor: '#111'},
    {id: 'comunidad', name: 'Nexa Comunidad', role: 'Responde "DEMO" en comentarios', zone: 'Ventas', seat: seatOf(14, -5), style: 'anime', color: '#e11d48', hair: '#c2410c', skin: SKIN[0]},
    {id: 'mensajero', name: 'Mensajero VOLTAGE', role: 'Cortes de entrada y salida por WhatsApp', zone: 'Operaciones', seat: seatOf(-20, 6, Math.PI), style: 'real', color: '#15803d', hair: '#222', skin: SKIN[1], acc: 'chaleco'},
    {id: 'archivista', name: 'Archivista', role: 'Guarda los timesheets en Drive', zone: 'Operaciones', seat: seatOf(-16, 6, Math.PI), style: 'real', color: '#475569', hair: '#9ca3af', skin: SKIN[0], acc: 'gafas'},
    {id: 'lector', name: 'Lector de cartas', role: 'Lee PDFs y arma la carta video', zone: 'Operaciones', seat: seatOf(-12, 6, Math.PI), style: 'anime', color: '#d97706', hair: '#3b1d14', skin: SKIN[1], acc: 'delantal'},
    {id: 'guardian', name: 'Guardián', role: 'Avisa si un flujo falla', zone: 'Operaciones', seat: seatOf(-20, 11, Math.PI), style: 'real', color: '#1e293b', hair: '#111', skin: SKIN[3], acc: 'casco', accColor: '#ef4444'},
  ];
  const AG = {}; A.forEach(d => { const c = addChar(cx, d, 'agent', d.seat); c.state = 'nodata'; paint(c); AG[d.id] = c; });
  function applyNames() { A.forEach(d => { const s = fromServer(SAVED.get(savedKey(null, 'agente:' + d.id))); ['name', 'role', 'zone'].forEach(k => { AG[d.id].def[k] = s[k] || d[k]; }); }); }
  applyNames();

  // uniformes (8 plantillas)
  const UNI = {costura: {style: 'anime', color: '#f472b6', hair: '#2b1b12'}, cocina: {style: 'anime', color: '#f4f1ea', acc: 'delantal'}, mesero: {style: 'anime', color: '#111827', acc: 'corbata', accColor: '#b91c1c'},
    caja: {style: 'anime', color: '#0ea5e9'}, domiciliario: {style: 'anime', color: '#dc2626', acc: 'casco', accColor: '#dc2626'}, barman: {style: 'anime', color: '#111111', acc: 'none'},
    dj: {style: 'anime', color: '#4c1d95', acc: 'audifonos', accColor: '#e879f9'}, tecnico: {style: 'real', color: '#1f2937', acc: 'chaleco', accColor: '#f8fafc'}, '': {style: 'anime', color: '#64748b'}};

  // ---------------------------------------------------------------- pisos de clientes: crear, mover, actualizar
  const BY_CID = new Map();
  function buildClientFloor(f, y) {
    const p = makeFloor(Object.assign({key: f.company_id, cid: f.company_id, name: f.name, sub: f.template_label, y, W: 34, D: 22, corr: 1, template: f.template}, TPL_OPTS[f.template] || TPL_OPTS.general));
    const out = (TPL[f.template] || TPL.general)(p, f);
    p.stations = out.stations; p.data = f;
    if (f.template !== 'campo') { p.extraTex = textTex(['+0', 'en turno'], {w: 512, h: 192, size: 84, bg: '#0b1a12', fg: '#22c55e'}); p.extraSign = screenWall(p, -2.6, p.D / 2 - .85, 2.2, .9, p.extraTex, Math.PI, 1.6); p.extraSign.visible = false; }
    if (isRealFloor(f)) facadeBrand(p, f);
    p.rep = addChar(p, Object.assign({id: 'rep-' + f.company_id, name: 'Rep. ' + f.name, role: 'Representante de ' + f.name, zone: 'Representante', rep: true, style: 'anime'}, out.repDef), 'rep', out.rep);
    repNames(p);
    p.staff = new Map();
    BY_CID.set(f.company_id, p);
    return p;
  }
  function seatFor(p, person) {
    const used = new Set([...p.staff.values()].map(c => JSON.stringify(c.home)));
    const st = p.template === 'campo' ? {[person.uniform]: p.stations['op:' + person.op] || [], any: []} : p.stations;
    const lists = [st[person.uniform] || [], st.any || []];
    for (const l of lists) for (const s of l) if (!used.has(JSON.stringify(s))) return s;
    return null;
  }
  function syncStaff(p, f) {
    const people = (f.staff && f.staff.visible) || [];
    const visibleNow = p.template === 'campo' ? people.filter(x => p.ops.includes(x.op)) : people;
    const diff = staffDiff([...p.staff.keys()], visibleNow);
    diff.remove.forEach(k => { const c = p.staff.get(k); p.staff.delete(k); c.leaving = true; walkTo(c, p.door[0], p.door[1], () => removeChar(c)); });
    diff.add.forEach(person => {
      const seat = seatFor(p, person); if (!seat) return;
      const c = addChar(p, Object.assign({}, UNI[person.uniform] || UNI[''], {id: person.key, name: person.label, role: person.role, zone: of_uniform(person.uniform), uniform: person.uniform, group: 'plantilla',
        hair: ['#111', '#5b2a14', '#2b1b12', '#7c2d12'][person.key.charCodeAt(0) % 4], skin: SKIN[person.key.charCodeAt(1) % 4]}), 'staff', [p.door[0], p.door[1], Math.PI]);
      c.home = seat; c.root.position.set(p.door[0], 0, p.door[1]); walkTo(c, seat[0], seat[1], () => { c.root.rotation.y = seat[2]; });
      p.staff.set(person.key, c);
    });
    visibleNow.forEach(person => { const c = p.staff.get(person.key); if (c) { c.paused = !!person.paused; c.def.name = person.label + (person.paused ? ' ⏸' : ''); paint(c); } });
    const extra = (f.staff && f.staff.extra) || 0;
    if (p.template === 'campo') {
      (f.staff.ops || []).forEach(o => { const s = p.signs[o.name]; if (s) { retext(s.sign, [`+${o.extra}`, `en turno en ${o.name}`], {size: 84, bg: '#0b1a12', fg: '#22c55e'}); s.group.visible = o.extra > 0; retext(s.screen, [`${o.name} · ${o.total} en turno`, `${Math.min(o.total, 5)} a la vista`], {size: 58, bg: s.side < 0 ? '#0d1d15' : '#0d1820'}); } });
      p.ops.forEach(name => { if (!(f.staff.ops || []).some(o => o.name === name)) { const s = p.signs[name]; s.group.visible = false; retext(s.screen, [`${name} · 0 en turno`, 'nadie con turno abierto'], {size: 58, bg: s.side < 0 ? '#0d1d15' : '#0d1820'}); } });
    } else if (p.extraSign) { p.extraSign.visible = extra > 0; if (extra) retext(p.extraTex, [`+${extra}`, 'en turno'], {size: 84, bg: '#0b1a12', fg: '#22c55e'}); }
    if (p.screen && p.screenLines) retext(p.screen, p.screenLines(f), {size: p.template === 'bar' ? 72 : 56, bg: {taller: '#1a1220', restaurante: '#20140c', bar: '#24104a', general: '#141a24'}[p.template] || '#141a24'});
  }
  // Piso realista en el edificio: el logo de la empresa en su fachada y el neón con su color.
  function facadeBrand(p, f) {
    const b = f.brand || {};
    const neon = new THREE.MeshBasicMaterial({color: b.accent || '#b08d57'});
    p.g.children.filter(k => k.material === neonMat).forEach(k => { k.material = neon; });
    p.brandNeon = neon;
    const sign = mesh(new THREE.PlaneGeometry(6, 1.6), new THREE.MeshBasicMaterial({map: textTex([f.name], {w: 1024, h: 272, size: 120, fg: b.accent || '#ffffff', bg: 'rgba(0,0,0,.55)'}), transparent: true, toneMapped: false}), 4.5, p.h - 1.4, p.D / 2 + .32, p.g);
    sign.castShadow = false; p.front.push(sign);
    if (b.logo_url) {
      const t = new THREE.TextureLoader().load(b.logo_url); t.colorSpace = THREE.SRGBColorSpace;
      const lm = mesh(new THREE.PlaneGeometry(3, 1.5), new THREE.MeshBasicMaterial({map: t, transparent: true, toneMapped: false}), -4.5, p.h - 1.4, p.D / 2 + .32, p.g);
      lm.castShadow = false; p.front.push(lm);
    }
  }
  function repNames(p) { const s = fromServer(SAVED.get(savedKey(p.cid, 'rep'))); p.rep.def.name = s.name || 'Rep. ' + p.name; p.rep.def.role = s.role || 'Representante de ' + p.name; }
  function of_uniform(u) { return ((DATA.uniforms || []).find(x => x.key === u) || {}).label || 'Personal'; }
  function layout(floors) {
    const ys = floorYs(floors.length);
    const wanted = new Set(floors.map(f => f.company_id));
    [...BY_CID.entries()].forEach(([cid, p]) => { if (!wanted.has(cid)) { dropFloor(p); BY_CID.delete(cid); } });
    floors.forEach((f, i) => {
      let p = BY_CID.get(f.company_id);
      if (p && (p.template !== f.template || isRealFloor(p.data) !== isRealFloor(f) || (isRealFloor(f) && JSON.stringify(p.data.brand) !== JSON.stringify(f.brand)))) { dropFloor(p); BY_CID.delete(f.company_id); p = null; }
      if (!p) p = buildClientFloor(f, ys.floors[i]);
      p.y = ys.floors[i]; p.g.position.y = p.y; p.name = f.name; p.sub = f.template_label; p.data = f; p.order = i;
      syncStaff(p, f);
    });
    cx.y = ys.clonexa; cx.g.position.y = cx.y; crown.position.y = cx.y + cx.h;
    const top = cx.y + cx.h;
    home.tgt.set(0, top / 2, 0); home.dist = 70 + top * 1.6;
    FLOORS.sort((a, b) => b.y - a.y);
    renderElevator(floors);
    FLOORS.forEach(p => { if (!flEls.get(p)) { const d = document.createElement('div'); d.className = 'fl'; d.onclick = () => setFocus(p); tags.appendChild(d); flEls.set(p, d); } const d = flEls.get(p); d.innerHTML = `${esc(p.name)}<small>${esc(p.sub)}</small>`; });
    if (focus && !FLOORS.includes(focus)) setFocus(null); else if (focus) setFocus(focus, true);
  }

  // ---------------------------------------------------------------- cámara
  const home = {tgt: new THREE.Vector3(0, 17, 0), dist: 120};
  const cam = {az: -.6, pol: 1.12, dist: 120, tgt: new THREE.Vector3(0, 17, 0)}, goal = {az: -.6, pol: 1.12, dist: 120, tgt: new THREE.Vector3(0, 17, 0)}; let focus = null;
  let REAL = null, realFor = null, realBusy = false;
  async function enterReal(p) {
    if (realBusy || (REAL && realFor === p)) return;
    leaveReal(); realBusy = true; realFor = p; hideInfo();
    document.body.classList.add('real-on');
    try {
      const isLobby = p === lobby, isCx = p === cx || isLobby, isBar = !isCx && p.data && p.data.style === 'bar', approved = !isCx && p.data && p.data.style === 'aprobado' && APPROVED_MODULE[p.data.template];
      // planta baja: Recepción con Nexa (interruptor oficina_ajustes.piso_recepcion, 025n)
      const mod = isLobby ? await import('/admin-v2plus/oficina/recepcion.js') : isCx ? await import('/admin-v2plus/oficina/clonexa.js') : approved ? await import(approved) : isBar ? await import('/admin-v2plus/oficina/bar.js') : await import('/admin-v2plus/oficina/real.js');
      if (realFor !== p) return;
      const layers = (kind, k, uniform) => kind === 'rep' ? [SAVED.get(savedKey(p.cid, 'rep'))] : kind === 'agent' ? [SAVED.get(savedKey(null, 'agente:' + k))]
        : [SAVED.get(savedKey(null, 'plantilla:' + uniform)), SAVED.get(savedKey(p.cid, 'plantilla:' + uniform)), SAVED.get(savedKey(p.cid, 'persona:' + k))];
      const openFn = isCx || approved ? mod.open : isBar ? mod.openBar : mod.openReal;
      REAL = await openFn({R, floor: isLobby ? {company_id: null, name: 'Recepción', template: 'recepcion'} : isCx ? {company_id: null, name: 'CLONEXA', template: 'clonexa'} : p.data, getJson, log, lite, liteChosen: () => localStorage.getItem('cxOfiLite'),
        repName: p.rep && p.rep.def.name,
        charCfg: (kind, k, uniform) => fromServerCfg(layers(kind, k, uniform)),
        rawCfg: (kind, k, uniform) => mergeRaw(layers(kind, k, uniform)),
        onClose: () => setFocus(null), onRep: () => showRep(p), onTable: t => showTable(t, p),
        onPerson: (info, kind) => kind === 'visitante' ? showVisitor(info) : (isCx && !isLobby && info && info.id && AG[info.id]) ? showChar(AG[info.id]) : showPerson(info, kind, p),
        onAutoLite: () => setLite(true, 'modo liviano activado (este equipo va lento en el piso realista)')});
      log(`<b>${esc(p.name)}</b> · piso realista abierto`);
    } catch (e) {
      log(`<b>${esc(p.name)}</b> · no se pudo abrir el piso realista: ${esc(e.message)}`, 'error'); leaveReal(); realFor = null;
    } finally { realBusy = false; }
  }
  function leaveReal() {
    if (REAL) { REAL.close(); REAL = null; }
    realFor = null; document.body.classList.remove('real-on'); resize();
  }
  function fromServerCfg(layers) { return Object.assign({}, ...layers.filter(Boolean).map(fromServer)); }
  function showTable(t, p) {
    const since = t.since ? new Date(t.since).toLocaleTimeString('es-CO', {hour: '2-digit', minute: '2-digit'}) : null;
    openInfo(`<h2>${esc(t.label)}</h2><div class="role">${t.open ? '● QR activo' : 'Libre'} · ${esc(p.name)}</div>
      <ul>${t.open ? `<li>Abierta${since ? ' desde las ' + esc(since) : ''}</li>` : '<li>Sin QR activo</li>'}${t.guests ? `<li>${esc(t.guests)} personas registradas</li>` : ''}
      <li>${t.pending ? esc(t.pending) + (t.pending === 1 ? ' producto pedido' : ' productos pedidos') + (p.data && p.data.template === 'restaurante' ? ' en preparación' : ' a la barra') : 'Sin pedidos pendientes'}</li>${t.songs ? `<li>${esc(t.songs)} canciones pedidas</li>` : ''}</ul>
      <div class="src">Solo actividad (sin dinero ni datos de los clientes).</div>`, 'mesa:' + t.label);
  }
  // Recepción: tocar un visitante abre su conversación en Conversaciones Nexa (o el prospecto en el Mapa comercial).
  function showVisitor(info) {
    const link = info && typeof info.link === 'string' && /^\/admin-v2plus#(nexa|mapa)\/[0-9a-fA-F-]{36}$/.test(info.link) ? info.link : null;
    if (link) { window.open(link, '_blank', 'noopener'); return; }
    openInfo(`<h2>${esc(info.name || 'Interesado')}</h2><div class="role">Recepción</div>${info.task ? `<ul><li>${esc(info.task)}</li></ul>` : ''}
      <div class="src">Interesado real de hoy (sin datos personales). Este canal no tiene conversación en la consola.</div>`);
  }
  function showPerson(info, kind, p) {
    openInfo(`<h2>${esc(info.name || 'Cliente')}</h2><div class="role">${esc(info.role || '')} · ${esc(p.name)}</div>${info.task ? `<ul><li>${esc(info.task)}</li></ul>` : ''}
      <div class="src">${kind === 'cliente' ? 'Cliente anónimo (Clonexa no muestra datos de los clientes).' : 'Personal en turno (privacidad del piso).'}</div>`);
  }
  const cxApproved = () => DATA && DATA.clonexa_style === 'aprobado';
  const rcApproved = () => DATA && DATA.reception_style === 'aprobado';
  function setFocus(p, keepCamera) {
    if (p && (isRealFloor(p.data) || (p === cx && cxApproved()) || (p === lobby && rcApproved()))) { focus = p; document.querySelectorAll('#floors button').forEach(b => b.classList.toggle('on', b.dataset.k === p.key)); enterReal(p); return; }
    if (REAL || realFor) leaveReal();
    focus = p; document.querySelectorAll('#floors button').forEach(b => b.classList.toggle('on', !!p && b.dataset.k === p.key));
    FLOORS.forEach(f => { f.g.visible = !(p && f.y > p.y + .1); const on = p === f; f.ceil.visible = !on; f.front.forEach(o => o.visible = !on); f.shell.forEach(o => o.visible = !on || !o.material || o.material !== facadeGlass); }); crown.visible = !p;
    if (keepCamera) return;
    if (p) { goal.tgt.set(0, p.y + .6, 1.5); goal.dist = p.key === 'clonexa' ? 38 : 30; goal.pol = .8; goal.az = -.32; } else { goal.tgt.copy(home.tgt); goal.dist = home.dist; goal.pol = 1.12; goal.az = -.6; }
    if (p) { if (p.key === 'clonexa') showFloorInfo(); else if (p.rep) showRep(p); else hideInfo(); } else hideInfo();
  }
  // gestos del edificio (oficina_gestos.js): arrastrar gira, pellizco/rueda acerca; Chrome ya no hace "atrás". Con un piso abierto, el piso manda.
  const gestures = attachGestures(canvas, {
    rotate: (dx, dy) => { if (!buildingInputAllowed(REAL || realFor)) return; goal.az -= dx * .005; goal.pol = Math.max(.2, Math.min(1.48, goal.pol - dy * .004)); },
    zoom: f => { if (!buildingInputAllowed(REAL || realFor)) return; goal.dist = Math.max(8, Math.min(260, goal.dist * f)); },
    tap: e => { if (e.target === canvas && buildingInputAllowed(REAL || realFor)) click(e); }});
  const drag = {get on() { return gestures.dragging; }};
  const ray = new THREE.Raycaster(), mv = new THREE.Vector2(); const vis = o => { while (o) { if (!o.visible) return false; o = o.parent; } return true; };
  function click(e) { mv.set(e.clientX / innerWidth * 2 - 1, -(e.clientY / innerHeight) * 2 + 1); ray.setFromCamera(mv, C); const hit = ray.intersectObjects(PICK.filter(vis), false)[0]; if (!hit) return;
    const ch = hit.object.userData.ch; if (ch) { if (focus !== ch.floor) setFocus(ch.floor); ch.kind === 'rep' ? showRep(ch.floor) : showChar(ch); } else if (hit.object.userData.floor) setFocus(hit.object.userData.floor); }

  // ---------------------------------------------------------------- ascensor (arrastrar para ordenar)
  const fEl = document.getElementById('floors');
  function renderElevator(floors) {
    fEl.innerHTML = '';
    const n = floors.length;
    const item = (p, label, draggable, idx) => { const b = document.createElement('button'); b.type = 'button'; b.dataset.k = p.key; const warn = p.data && p.data.needs_template ? '<small class="warn">⚠ Elige su plantilla</small>' : '';
      b.innerHTML = `<span class="n">${label}</span><span>${esc(p.name)}<small>${esc(p.sub)}</small>${warn}</span>`; b.onclick = () => setFocus(p);
      if (draggable) { b.draggable = true; b.dataset.i = idx; b.addEventListener('dragstart', ev => { b.classList.add('drag'); ev.dataTransfer.setData('text/plain', String(idx)); ev.dataTransfer.effectAllowed = 'move'; });
        b.addEventListener('dragend', () => b.classList.remove('drag')); b.addEventListener('dragover', ev => { ev.preventDefault(); b.classList.add('over'); }); b.addEventListener('dragleave', () => b.classList.remove('over'));
        b.addEventListener('drop', ev => { ev.preventDefault(); b.classList.remove('over'); const from = +ev.dataTransfer.getData('text/plain'); if (from !== idx) moveFloor(from, idx); }); }
      fEl.appendChild(b); };
    item(cx, 'P' + (n + 1), false);
    floors.forEach((f, i) => item(BY_CID.get(f.company_id), 'P' + (n - i), true, i));
    item(lobby, 'PB', false);
  }
  async function moveFloor(from, to) {
    const ids = reorder(DATA.floors.map(f => f.company_id), from, to);
    DATA.floors = reorder(DATA.floors, from, to); layout(DATA.floors);
    try { await getJson(API + '/pisos/orden', {method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({company_ids: ids})}); log('<b>Oficina</b> · orden de pisos guardado'); }
    catch (e) { log('<b>Oficina</b> · no se guardó el orden: ' + esc(e.message), 'error'); poll(); }
  }
  document.getElementById('btnOut').onclick = () => setFocus(null);

  // ---------------------------------------------------------------- paneles
  const info = document.getElementById('info'); const hideInfo = () => info.classList.remove('open');
  const stHtml = (state, label) => `<span class="st"><span class="dot st-${state}"></span>${esc(label || (ST[state] || ST.nodata).t)}</span>`;
  let infoKind = '';
  function openInfo(html, kind = '') { infoKind = kind; info.innerHTML = '<button class="x" type="button" data-close>✕</button>' + html; info.classList.add('open'); info.querySelector('[data-close]').onclick = hideInfo; }
  function agentData(id) { return (DATA.agents || []).find(a => a.id === id) || {}; }
  function showChar(ch) {
    const d = ch.def;
    if (ch.kind === 'staff') {
      openInfo(`<h2>${esc(d.name)}</h2><div class="role">${esc(d.role)} · ${esc(ch.floor.name)}</div>${stHtml(ch.paused ? 'wait' : 'work', ch.paused ? 'En pausa ⏸' : 'En turno')}<ul><li>Uniforme: ${esc(of_uniform(d.uniform))}</li></ul><div class="src">Fuente real: turno abierto en Clonexa. Sale de la oficina cuando cierra su turno.</div><div class="row"><button type="button" data-edit>✏️ Editar este personaje</button></div>`);
      info.querySelector('[data-edit]').onclick = () => openEd(ch); return;
    }
    const a = agentData(ch.id);
    const last = a.last_run && a.last_run.at ? `<div class="src">Última ejecución: ${esc(new Date(a.last_run.at).toLocaleString('es-CO'))} · ${a.last_run.status === 'success' ? 'bien' : esc(a.last_run.status)}</div>` : '';
    openInfo(`<h2>${esc(d.name)}</h2><div class="role">${esc(d.role || '')}${d.zone ? ' · ' + esc(d.zone) : ''}</div>${stHtml(ch.state === 'cafe' ? 'wait' : ch.state, ch.state === 'cafe' ? ST.cafe.t : null)}<ul>${(a.today || ['Sin datos']).map(t => `<li>${esc(t)}</li>`).join('')}</ul><div class="src">Fuente real: ${esc(a.source || '')}</div>${last}<div class="row"><button type="button" data-edit>✏️ Editar personaje</button></div>`);
    info.querySelector('[data-edit]').onclick = () => openEd(ch);
  }
  function showRep(p) {
    const f = p.data || {};
    const tplOpts = (DATA.templates || []).map(t => `<option value="${t.key}" ${t.key === f.template ? 'selected' : ''}>${esc(t.label)}</option>`).join('');
    openInfo(`<h2>${esc(f.name)}</h2><div class="role">${esc(p.rep.def.name)} · te cuenta cómo va la empresa</div>${stHtml('rep', 'Representante')}
      ${f.needs_template ? '<div class="alert">No se pudo deducir el tipo de empresa: elige su plantilla.</div>' : ''}
      <div class="kpis">${(f.kpis || []).map(([k, v]) => `<div class="kpi"><b>${esc(v)}</b><span>${esc(k)}</span></div>`).join('')}</div>
      <ul>${(f.lines || []).map(t => `<li>${esc(t)}</li>`).join('')}<li>Última actividad ${esc(f.last_activity || '')}</li><li>${f.staff && f.staff.total != null ? esc(f.staff.total) + ' personas con turno abierto' : 'Turnos: sin datos'}</li></ul>
      <div class="row">Plantilla <select data-tpl>${tplOpts}</select></div>
      ${APPROVED_MODULE[f.template] ? `<div class="row">Estilo del piso <select data-style><option value="clasico" ${f.style !== 'aprobado' ? 'selected' : ''}>Clásico</option><option value="aprobado" ${f.style === 'aprobado' ? 'selected' : ''}>Piso aprobado (copia viva)</option></select></div>` : ''}
      ${f.template === 'bar' ? `<div class="row">Estilo del piso <select data-style><option value="clasico" ${!isRealFloor(f) ? 'selected' : ''}>Clásico</option><option value="realista" ${f.style === 'realista' ? 'selected' : ''}>Realista (copia viva)</option><option value="bar" ${f.style === 'bar' ? 'selected' : ''}>Bar aprobado (copia viva)</option></select></div>` : ''}
      ${f.brand && f.brand.warning ? `<div class="alert">${esc(f.brand.warning)}</div>` : ''}
      <div class="row">Personal <select data-priv><option value="nombre" ${f.privacy !== 'cargo' ? 'selected' : ''}>Nombre + inicial y cargo</option><option value="cargo" ${f.privacy === 'cargo' ? 'selected' : ''}>Solo el cargo</option></select></div>
      <div class="src">Solo actividad (sin dinero). Fuente: turnos, pedidos y registros de ${esc(f.name)} en Clonexa.</div><div class="row"><button type="button" data-edit>✏️ Editar representante</button></div>`, 'rep:' + f.company_id);
    info.querySelector('[data-edit]').onclick = () => openEd(p.rep);
    info.querySelector('[data-tpl]').onchange = e => saveFloor(f.company_id, {plantilla: e.target.value});
    info.querySelector('[data-priv]').onchange = e => saveFloor(f.company_id, {privacidad: e.target.value});
    const st = info.querySelector('[data-style]'); if (st) st.onchange = e => saveFloor(f.company_id, {estilo: e.target.value});
  }
  async function saveFloor(cid, body) {
    try { await getJson(API + '/pisos/' + cid, {method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)}); log('<b>Oficina</b> · piso actualizado'); await poll(); const p = BY_CID.get(cid); if (p) setFocus(p); }
    catch (e) { log('<b>Oficina</b> · no se guardó: ' + esc(e.message), 'error'); }
  }
  function showFloorInfo() {
    const ag = CHARS.filter(c => c.floor === cx); const n = s => ag.filter(c => c.state === s).length; const ap = DATA.approvals || {};
    const pieces = ap.pieces == null ? '<li>Piezas: sin datos de la hoja</li>' : (ap.pieces.length ? ap.pieces.slice(0, 5).map(x => `<li>🎬 ${esc(x.fecha)} · ${esc(x.formato || '')} ${esc(x.tema || '')}</li>`).join('') : '<li>No hay piezas en "Listo para aprobar"</li>');
    const batch = !ap.batch_known ? '<li>Lote de correos: sin datos</li>' : ap.batch ? `<li>✉️ Lote de hoy: ${esc(ap.batch.items)} negocios esperan tu ✅ en Telegram</li>` : '<li>Sin lote de correos pendiente</li>';
    const leads = !ap.replied_known ? '<li>Leads: sin datos</li>' : ap.replied.length ? ap.replied.map(x => `<li>💬 Respondió: ${esc(x)}</li>`).join('') : '<li>Ningún lead por atender</li>';
    const cal = DATA.calendar; const ideas = DATA.ideas;
    openInfo(`<h2>CLONEXA · piso principal</h2><div class="role">${ag.length} personajes: tú y ${ag.length - 1} agentes de IA</div>
      ${DATA.n8n && !DATA.n8n.ok ? `<div class="alert">n8n no responde: los agentes quedan en gris "sin datos". ${esc(DATA.n8n.error || '')}</div>` : ''}
      <div class="kpis"><div class="kpi"><b>${n('work')}</b><span>Trabajando</span></div><div class="kpi"><b>${n('wait') + n('cafe')}</b><span>Esperando / café</span></div><div class="kpi"><b>${n('err')}</b><span>Con error</span></div><div class="kpi"><b>${n('train')}</b><span>En entrenamiento</span></div></div>
      <h4>SALA DE APROBACIONES · HOY</h4><ul>${pieces}${batch}${leads}</ul>
      ${cal ? `<h4>CALENDARIO</h4><ul><li>${esc(cal.ready)} listo para aprobar · ${esc(cal.approved)} aprobado</li>${cal.next ? `<li>Próxima publicación: ${esc(cal.next.fecha)} · ${esc(cal.next.formato || '')} ${esc(cal.next.tema || '')}</li>` : ''}</ul>` : ''}
      ${ideas ? `<h4>IDEAS</h4><ul><li>${esc(ideas.pending)} temas pendientes</li>${ideas.items.map(t => `<li>💡 ${esc(t)}</li>`).join('')}</ul>` : ''}
      <div class="src">Toca un personaje para ver qué hizo hoy y de qué flujo real sale.</div>`, 'clonexa');
  }
  const feedL = document.getElementById('feedL');
  let SERVER_FEED = []; const LOCAL_FEED = [];
  function log(h, kind) { LOCAL_FEED.unshift({at: new Date().toISOString(), text: h, kind: kind || 'local'}); LOCAL_FEED.splice(8); renderFeed(); }
  function renderFeed(items) {
    if (items) SERVER_FEED = items;
    const all = SERVER_FEED.concat(LOCAL_FEED).sort((a, b) => String(b.at).localeCompare(String(a.at))).slice(0, 7);
    feedL.innerHTML = '';
    all.forEach(e => { const d = document.createElement('div'); if (e.kind === 'error') d.className = 'error'; const t = e.at ? new Date(e.at).toTimeString().slice(0, 5) : ''; d.innerHTML = `<span class="t">${t}</span> ${e.text}`; feedL.appendChild(d); });
    if (!all.length) feedL.innerHTML = '<div>Sin eventos en las últimas 24 h.</div>';
  }

  // ---------------------------------------------------------------- etiquetas
  const tags = document.getElementById('tags'); const tagEls = new Map(), flEls = new Map();
  const v3 = new THREE.Vector3();
  function updTags() {
    CHARS.forEach(ch => { let el = tagEls.get(ch); const show = focus && ch.floor === focus; if (!show) { if (el) el.style.display = 'none'; return; }
      if (!el) { el = document.createElement('div'); el.className = 'tg' + (ch.kind === 'rep' ? ' rep' : ''); tags.appendChild(el); tagEls.set(ch, el); }
      ch.root.getWorldPosition(v3); v3.y += ch.tagH; v3.project(C); if (v3.z > 1) { el.style.display = 'none'; return; } el.style.display = 'flex'; el.style.left = (v3.x * .5 + .5) * innerWidth + 'px'; el.style.top = (-v3.y * .5 + .5) * innerHeight + 'px';
      const cls = ch.kind === 'rep' ? 'rep' : ch.kind === 'staff' ? (ch.paused ? 'wait' : 'work') : agentVisualState(ch.state);
      const html = `<i class="st-${cls}"></i>${esc(ch.def.name)}`; if (el._h !== html) { el.innerHTML = html; el._h = html; } });
    FLOORS.forEach(p => { const el = flEls.get(p); if (!el) return; if (focus) { el.style.display = 'none'; return; } v3.set(p.W / 2 + 1.2, p.y + p.h / 2, p.D / 2); v3.project(C); el.style.display = 'block'; el.style.left = (v3.x * .5 + .5) * innerWidth + 'px'; el.style.top = (-v3.y * .5 + .5) * innerHeight + 'px'; });
  }

  // ---------------------------------------------------------------- estados reales de los agentes
  function toCafe(c) { if (c.cafe) return; const s = cafeSpots.find(s => !s.used); if (!s) return; s.used = c; c.cafe = s; walkTo(c, s[0], s[1], () => { c.root.rotation.y = s[2]; }); }
  function back(c) { if (c.cafe) { c.cafe.used = null; c.cafe = null; walkTo(c, c.home[0], c.home[1], () => { c.root.rotation.y = c.home[2]; }); } }
  const prevState = {};
  function applyAgents(list) {
    (list || []).forEach(a => { const c = AG[a.id]; if (!c) return; const s = agentVisualState(a.state);
      if (!booting && prevState[a.id] && prevState[a.id] !== s) { if (s === 'err') log(`<b>${esc(c.def.name)}</b> · ⚠️ la última ejecución falló`, 'error'); else if (s === 'work' && prevState[a.id] !== 'work') log(`<b>${esc(c.def.name)}</b> · volvió a trabajar`); }
      prevState[a.id] = s; setState(c, s); if (s === 'wait' && !c.def.human) toCafe(c); else back(c); if (s === 'wait') c.state = c.cafe ? 'cafe' : 'wait'; });
    const ap = DATA.approvals || {};
    retext(approvalsTex, ['Sala de aprobaciones', `${ap.pieces_count == null ? '—' : ap.pieces_count} piezas · ${ap.batch ? '1 lote' : '0 lotes'} · ${ap.replied_known ? ap.replied.length : '—'} leads`], {size: 56, bg: '#2a0f22'});
    const cal = DATA.calendar;
    retext(calendarTex, ['Calendario de contenido', cal && cal.next ? `Próxima: ${cal.next.fecha} · ${cal.next.formato || ''}` : (cal ? 'Sin próximas publicaciones' : 'Sin datos de la hoja')], {size: 52, bg: '#1c1238'});
  }
  const liveTag = document.getElementById('liveTag');
  function applyData(d) {
    DATA = d;
    liveTag.textContent = d.n8n && d.n8n.ok ? 'Datos en vivo' : 'En vivo · n8n sin datos';
    liveTag.className = 'tag ' + (d.n8n && d.n8n.ok ? 'ok' : 'bad');
    layout(d.floors || []); applyAgents(d.agents); renderFeed(d.feed);
    if (info.classList.contains('open')) { if (infoKind === 'clonexa') showFloorInfo(); else if (infoKind.startsWith('rep:') && BY_CID.get(infoKind.slice(4)) && !info.contains(document.activeElement)) showRep(BY_CID.get(infoKind.slice(4))); }
  }

  // ---------------------------------------------------------------- consulta cada 30 s (pausa si la pestaña no se ve)
  let timer = null;
  async function poll() {
    if (document.hidden) return;
    try { applyData(await getJson(API + '/estado')); } catch (e) { liveTag.textContent = 'Sin conexión'; liveTag.className = 'tag bad'; }
  }
  function schedule() { clearTimeout(timer); timer = setTimeout(async () => { await poll(); schedule(); }, POLL_MS); }
  document.addEventListener('visibilitychange', () => { if (document.hidden) clearTimeout(timer); else { poll(); schedule(); } });

  // ---------------------------------------------------------------- modo liviano
  const liteEl = document.getElementById('lite');
  function setLite(on, why) {
    lite = on; if (REAL) REAL.setLite(on); liteEl.checked = on; CITY.visible = !on; R.shadowMap.enabled = !on; sun.castShadow = !on; R.setPixelRatio(on ? 1 : Math.min(devicePixelRatio, 2));
    S.traverse(o => { if (o.material) { (Array.isArray(o.material) ? o.material : [o.material]).forEach(m => { m.needsUpdate = true; }); } }); resize();
    if (why) log('<b>Oficina</b> · ' + why);
  }
  liteEl.checked = lite; liteEl.onchange = () => { localStorage.setItem('cxOfiLite', liteEl.checked ? '1' : '0'); setLite(liteEl.checked); };

  // ---------------------------------------------------------------- editor de personajes
  const ed = document.getElementById('ed'), edList = document.getElementById('edList'), edForm = document.getElementById('edForm');
  const tabEd = document.getElementById('tabEd'), tabCast = document.getElementById('tabCast'), paneEd = document.getElementById('paneEd'), paneCast = document.getElementById('paneCast');
  document.getElementById('btnEd').onclick = () => openEd(); document.getElementById('edClose').onclick = () => ed.classList.remove('open');
  tabEd.onclick = () => { tabEd.classList.add('on'); tabCast.classList.remove('on'); paneEd.classList.remove('hidden'); paneCast.classList.add('hidden'); };
  tabCast.onclick = () => { tabCast.classList.add('on'); tabEd.classList.remove('on'); paneEd.classList.add('hidden'); paneCast.classList.remove('hidden'); castHtml(); };
  function castHtml() {
    const c = DATA.cast || {};
    const by = (c.by_floor || []).map(x => `${esc(x.name)} ${x.on_shift == null ? '(sin datos)' : esc(x.on_shift)}`).join(' · ');
    const rows = [
      ['Piso CLONEXA · agentes de IA', c.agents, A.map(a => AG[a.id].def.name).join(', '), 'Diseño único cada uno'],
      ['Representantes', c.reps, (DATA.floors || []).map(f => f.name).join(', ') || 'Ninguna empresa registrada', '1 por cada empresa registrada (las nuevas aparecen solas)'],
      ['Personal de clientes (plantillas)', `${c.templates} plantillas`, (DATA.uniforms || []).map(u => u.label).join(', '), 'Cada persona usa la plantilla de su cargo; puedes cambiar la plantilla o un personaje puntual'],
      ['Personas en turno ahora', c.on_shift, by || '—', 'Aparecen al iniciar turno y salen al cerrarlo (VOLTAGE: máx. 5 por operación + "+N")'],
    ];
    paneCast.innerHTML = `<table><tr><th>GRUPO</th><th>CUÁNTOS</th><th>QUIÉNES</th><th>CÓMO SE HACEN</th></tr>${rows.map(r => `<tr><td><b>${esc(r[0])}</b></td><td><b>${esc(r[1])}</b></td><td>${esc(r[2])}</td><td>${esc(r[3])}</td></tr>`).join('')}</table>`;
  }
  // Una "entrada" del editor: qué se guarda (clave + empresa) y a quién se le ve el cambio.
  function entries() {
    const out = [['CLONEXA', A.map(a => ({label: AG[a.id].def.name, sub: 'CLONEXA', clave: 'agente:' + a.id, cid: null, chars: () => [AG[a.id]], def: a, kind: 'agent'}))]];
    out.push(['REPRESENTANTES', [...BY_CID.values()].map(p => ({label: p.rep.def.name, sub: p.name, clave: 'rep', cid: p.cid, chars: () => [p.rep], def: p.rep.def, kind: 'rep'}))]);
    out.push(['PLANTILLAS DE PERSONAL', (DATA.uniforms || []).map(u => ({label: u.label, sub: 'Todas las empresas', clave: 'plantilla:' + u.key, cid: null, uniform: u.key,
      chars: () => CHARS.filter(c => c.kind === 'staff' && c.def.uniform === u.key), def: UNI[u.key], kind: 'plantilla'}))]);
    const staff = CHARS.filter(c => c.kind === 'staff' && !c.leaving);
    out.push(['PERSONAS EN TURNO AHORA', staff.map(c => ({label: c.def.name, sub: c.floor.name, clave: 'persona:' + c.id, cid: c.floor.cid, chars: () => [c], def: c.def, kind: 'persona'}))]);
    return out;
  }
  let current = null;
  function openEd(ch) {
    ed.classList.add('open'); tabEd.onclick(); edList.innerHTML = ''; let first = null, mine = null;
    getJson(API + '/personajes').then(r => { (r.items || []).forEach(it => SAVED.set(savedKey(it.company_id, it.clave), it)); }).catch(() => {});
    entries().forEach(([t, list]) => { const h = document.createElement('h4'); h.textContent = `${t} · ${list.length}`; edList.appendChild(h);
      list.forEach(en => { const b = document.createElement('button'); b.type = 'button'; const cfg = mergeCfg(en.def || {}, [SAVED.get(savedKey(en.cid, en.clave))].filter(Boolean));
        b.innerHTML = `<span>${esc(en.label)}<br><small>${esc(en.sub)}</small></span><small>${BODY_LABEL[cfg.body] || STYLE_LABEL[cfg.style] || 'Anime'}</small>`; b.onclick = () => sel(en, b); edList.appendChild(b);
        if (!first) first = [en, b]; if (ch && !mine && en.kind !== 'plantilla' && en.chars().includes(ch)) mine = [en, b]; }); });
    if (mine || first) sel(...(mine || first));
  }
  const PENDING = new Map(), TIMERS = new Map(); let rebuildT = null;
  function sel(en, b) {
    current = en; edList.querySelectorAll('button').forEach(x => x.classList.toggle('on', x === b));
    const saved = SAVED.get(savedKey(en.cid, en.clave)); const v = mergeCfg(Object.assign({style: 'anime', color: '#f20b6d', skin: SKIN[0], hair: '#2b1b12', acc: 'none'}, en.def || {}), [saved].filter(Boolean));
    const named = en.kind === 'agent' || en.kind === 'rep';
    const roles = ['Gerencia', 'Marketing', 'Ventas', 'Operaciones', 'Representante', 'Producción', 'Barra', 'Cocina', 'Salón', 'Campo'];
    edForm.innerHTML = `${named ? `<label class="full">Nombre<input name="name" maxlength="80" value="${esc(v.name || '')}"></label>` : `<div class="note full">${en.kind === 'plantilla' ? 'Plantilla de uniforme: la usan todas las personas con este cargo (en todas las empresas).' : 'Personaje puntual: solo cambia a esta persona. Su nombre sale de Clonexa con la privacidad del piso.'}</div>`}
      ${named ? `<label>Rol / sección<select name="zone">${roles.map(r => `<option ${r === v.zone ? 'selected' : ''}>${r}</option>`).join('')}</select></label><label>Tarea<input name="role" maxlength="120" value="${esc(v.role || '')}"></label>` : ''}
      <label>Cuerpo<select name="body">${Object.entries(BODY_LABEL).map(([k, t]) => `<option value="${k}" ${k === (v.body || 'medio') ? 'selected' : ''}>${t}</option>`).join('')}</select></label>
      <label>Peinado<select name="hairStyle">${Object.entries(HAIR_LABEL).map(([k, t]) => `<option value="${k}" ${k === (v.hairStyle || 'corto') ? 'selected' : ''}>${t}</option>`).join('')}</select></label>
      ${mixamoFields(en, v)}
      <label>Ropa<input type="color" name="color" value="${esc(v.color || '#f20b6d')}"></label><label>Pantalón<input type="color" name="legs" value="${esc(v.legs || '#22202b')}"></label>
      <label>Color de pelo<input type="color" name="hair" value="${esc(v.hair === 'none' ? '#000000' : (v.hair || '#2b1b12'))}"></label>
      <label>Tono de piel<select name="skin">${SKIN.map((s, i) => `<option value="${s}" ${s === v.skin ? 'selected' : ''}>Tono ${i + 1}</option>`).join('')}</select></label>
      <label>Accesorio<select name="acc">${Object.entries(ACC_LABEL).map(([a, t]) => `<option value="${a}" ${a === (v.acc || 'none') ? 'selected' : ''}>${t}</option>`).join('')}</select></label>
      <label>Color del accesorio<input type="color" name="accColor" value="${esc(v.accColor || '#222222')}"></label>
      ${brandSwatches(en)}
      <div class="msg" data-msg></div>
      <div class="note legal">Usa solo personajes propios o con permiso. Los personajes de películas o cómics (Batman, etc.) tienen dueño y no se pueden usar.</div>`;
    const msg = edForm.querySelector('[data-msg]');
    const say = (t, bad) => { msg.textContent = t; msg.className = 'msg' + (bad ? ' bad' : ''); };
    edForm.onsubmit = e => { e.preventDefault(); };
    edForm.querySelectorAll('input,select').forEach(x => x.oninput = () => { const o = {}; o[x.name] = x.value; change(en, o, say); if (x.name === 'name') b.querySelector('span').firstChild.textContent = x.value; });
    const gSel = edForm.querySelector('[name=gender]'); if (gSel) gSel.oninput = () => { change(en, {gender: gSel.value, model: '', ...(gSel.value === 'mujer' ? {beard: 'no'} : {})}, say); sel(en, b); };
    edForm.querySelectorAll('[data-sw]').forEach(x => { x.firstChild.style.background = x.dataset.c; }); edForm.querySelectorAll('[data-sw]').forEach(x => x.onclick = () => { change(en, {[x.dataset.sw]: x.dataset.c}, say); sel(en, b); });
  }
  // Pisos aprobados (Mixamo): género Hombre / Mujer, su personaje, túnica, barba (solo hombres) y su color.
  function mixamoFields(en, v) {
    const isAgent = en.kind === 'agent';
    const gender = v.gender || (isAgent ? (/(Ch07|Ch21|Ch22)/.test(AGENT_MODEL_DEF[en.def && en.def.id] || '') ? 'mujer' : 'hombre') : guessGender(en.label));
    const opt = (val, label, cur) => `<option value="${esc(val)}" ${val === (cur || '') ? 'selected' : ''}>${esc(label)}</option>`;
    return `<div class="note full">Pisos aprobados (personajes de Mixamo)${isAgent ? ' · piso Clonexa: túnica negra' : ''}</div>
      <label>Género<select name="gender">${opt('hombre', 'Hombre', gender)}${opt('mujer', 'Mujer', gender)}</select></label>
      <label>Personaje<select name="model">${opt('', 'Automático', v.model)}${MIXAMO[gender].map(m => opt(m, MIXAMO_LABEL[m], v.model)).join('')}</select></label>
      <label>Túnica<select name="tunic">${opt('', isAgent ? 'Sí (piso Clonexa)' : 'Automática', v.tunic)}${opt('si', 'Sí', v.tunic)}${opt('no', 'No', v.tunic)}</select></label>
      ${gender === 'hombre' ? `<label>Barba<select name="beard">${opt('', en.def && en.def.id === 'director' ? 'Sí (CEO)' : 'No', v.beard)}${opt('si', 'Sí', v.beard)}${opt('no', 'No', v.beard)}</select></label>
      <label>Color de barba<input type="color" name="beardColor" value="${esc(v.beardColor || '#2b1a10')}"></label>` : ''}`;
  }
  // Ropa según cargo y colores de la empresa: atajos con la paleta del Estudio de marca del piso.
  function brandSwatches(en) {
    const p = en.cid ? BY_CID.get(en.cid) : null; const c = p && p.data && p.data.brand && p.data.brand.colors;
    if (!c) return '';
    const sw = (field, label) => `<div class="sw full">${label}${['primary', 'secondary', 'surface', 'text'].map(k => `<button type="button" data-sw="${field}" data-c="${esc(c[k])}" title="${esc(k)}"><i class="c-${esc(k)}"></i></button>`).join('')}</div>`;
    return sw('color', 'Ropa con la marca') + sw('accColor', 'Accesorio con la marca');
  }
  function change(en, o, say) {
    const k = savedKey(en.cid, en.clave); const cur = Object.assign({}, SAVED.get(k) || {clave: en.clave, company_id: en.cid});
    Object.assign(cur, toServer(o)); SAVED.set(k, cur);
    if (en.kind === 'agent') applyNames();
    if (en.kind === 'rep') { const p = BY_CID.get(en.cid); if (p) repNames(p); }
    en.chars().forEach(rebuild);
    const patch = toServer(o);
    queueSave(PENDING, k, {clave: en.clave, company_id: en.cid}, patch);
    if (REAL && REAL.rebuild && changesLook(patch)) { clearTimeout(rebuildT); rebuildT = setTimeout(() => REAL && REAL.rebuild && REAL.rebuild(), 120); }   // el piso abierto cambia al instante (antes de guardar)
    clearTimeout(TIMERS.get(k)); TIMERS.set(k, setTimeout(async () => { const body = PENDING.get(k); PENDING.delete(k); TIMERS.delete(k); if (!body) return;
      try { const r = await getJson(API + '/personajes', {method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)}); SAVED.set(savedKey(r.item.company_id, r.item.clave), Object.assign({}, r.item, PENDING.get(k) || {})); say('Guardado ✓'); }
      catch (err) { say('No se guardó: ' + err.message, true); } }, 600));
  }

  // ---------------------------------------------------------------- bucle
  const clock = new THREE.Clock(); let frames = 0, fpsT = 0, fpsDone = false;
  function resize() { R.setSize(innerWidth, innerHeight, false); C.aspect = innerWidth / innerHeight; C.updateProjectionMatrix(); } addEventListener('resize', resize); resize();
  function tick() {
    const dt = Math.min(clock.getDelta(), .05), t = clock.elapsedTime; const k = 1 - Math.pow(.002, dt);
    if (!fpsDone) { frames++; fpsT += dt; if (fpsT > 5) { fpsDone = true; if (frames / fpsT < 28 && !lite && localStorage.getItem('cxOfiLite') == null) setLite(true, 'modo liviano activado (este equipo va lento)'); } }
    cam.az += (goal.az - cam.az) * k; cam.pol += (goal.pol - cam.pol) * k; cam.dist += (goal.dist - cam.dist) * k; cam.tgt.lerp(goal.tgt, k); if (!focus && !drag.on) goal.az += dt * .035;
    C.position.set(cam.tgt.x + cam.dist * Math.sin(cam.pol) * Math.sin(cam.az), cam.tgt.y + cam.dist * Math.cos(cam.pol), cam.tgt.z + cam.dist * Math.sin(cam.pol) * Math.cos(cam.az)); C.lookAt(cam.tgt);
    sun.position.set(cam.tgt.x + 45, cam.tgt.y + 90, cam.tgt.z + 60); sun.target.position.copy(cam.tgt);
    CHARS.forEach(ch => { ch.t += dt; const r = ch.root;
      if (ch.path.length) { const [x, z] = ch.path[0]; const dx = x - r.position.x, dz = z - r.position.z, d = Math.hypot(dx, dz);
        if (d < .06) { r.position.x = x; r.position.z = z; ch.path.shift(); if (!ch.path.length && ch.then) { const f = ch.then; ch.then = null; f(); } } else { const sp = Math.min(d, dt * 2.6); r.position.x += dx / d * sp; r.position.z += dz / d * sp; r.rotation.y = Math.atan2(dx, dz); }
        ch.body.position.y = Math.abs(Math.sin(ch.t * 9)) * .05; if (ch.armL) { ch.armL.rotation.x = Math.sin(ch.t * 9) * .5; ch.armR.rotation.x = -Math.sin(ch.t * 9) * .5; } }
      else { ch.body.position.y = Math.sin(ch.t * 2) * .012; if (ch.armL) { const w = ch.kind === 'staff' ? !ch.paused : ch.state === 'work'; ch.armL.rotation.x = w ? -.9 + Math.sin(ch.t * 13) * .12 : Math.sin(ch.t * 1.5) * .04; ch.armR.rotation.x = w ? -.9 + Math.sin(ch.t * 13 + 1.7) * .12 : -Math.sin(ch.t * 1.5) * .04; } }
      ch.ring.material.opacity = ch.state === 'err' && ch.kind === 'agent' ? .5 + .5 * Math.sin(t * 10) : .9; });
    FLOORS.forEach(p => p.anim && p.g.visible && p.anim.forEach(f => f(t)));
    if (REAL) REAL.tick(); else { R.render(S, C); updTags(); }
    requestAnimationFrame(tick);
  }
  let booting = true;
  applyData(DATA); booting = false;
  goal.tgt.copy(home.tgt); goal.dist = home.dist; cam.tgt.copy(home.tgt); cam.dist = home.dist;
  setFocus(null); tick(); schedule(); document.getElementById('load').remove();
  if (location.hash !== '#edificio') setTimeout(() => { if (!focus) setFocus(cx); }, 3500);
}
