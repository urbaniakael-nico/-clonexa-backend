// Oficina 3D · bar aprobado (The Time Machine) · reglas puras, sin three (se prueban en tests/oficina_bar.test.cjs).
// Fuente de verdad del diseño: la escena aprobada bar.html (bar5.png): medidas, distribución, cámara y lógica de
// animación. El motor (oficina_bar.js) solo dibuja lo que estas reglas deciden. Solo actividad: nunca dinero.

export const LIVE_MS = 7000;   // copia viva cada 7 s (entre 5 y 10); pausa si la pestaña no se ve
export const FADE = 0.45;      // transición suave (crossfade) entre animaciones, en segundos

// ------------------------------------------------------------------ medidas de bar.html (metros)
export const ROOM = {W: 16, D: 11, WALL: 3.4};
export const BAR = {x: -5.6, z0: -4.3, z1: 2.7, h: 1.08, stools: 9};
export const BACKBAR_X = -ROOM.W / 2 + 0.25;
export const CAMERA = {pos: [3, 9.5, 15.5], look: [1, 0.6, -0.5], fov: 32};
// 10 mesas de bar.html; si The Time Machine tiene más mesas configuradas, caen en estos puestos libres.
export const TABLE_POS = [[-2.6, -3.0], [0, -3.0], [-2.6, -0.4], [0, -0.4], [2.6, -0.4], [-2.6, 2.2], [0, 2.2], [2.6, 2.2], [5.2, 2.2], [5.2, 4.4],
  [2.6, 4.4], [-2.6, 4.4], [5.2, -0.4], [0, 4.4]];
export const SEAT_D = 0.8;
export const SEATS = {n: [0, -SEAT_D, 0], s: [0, SEAT_D, Math.PI], w: [-SEAT_D, 0, Math.PI / 2], e: [SEAT_D, 0, -Math.PI / 2]};
export const SEAT_ORDER = ['n', 'e', 'w', 's'];
export const DANCE = {x0: 3.0, z0: -4.3, cols: 4, rows: 3};
export const DANCERS = [[3.6, -3.6, 0.3], [4.4, -3.2, -0.8], [5.3, -3.9, -0.3], [4.0, -4.4, 0.6]];
export const DJ = {booth: [6.9, -4.6], spot: [6.9, -5.2, 0]};
export const ENTRANCE = [6.9, 5.3];
export const REP = [6.6, 4.4, -0.6];
export const STANDERS = [[-3.6, 4.4, 1.0, 'Talking'], [-2.9, 4.6, -2.2, 'Drinking']];
export const LOGO = {x: -1.3, y: 2.15, w: 3.0, h: 1.53};
export const SCREEN = {x: 3.6, y: 2.15, w: 3.15, h: 1.77};

export const stoolZ = i => BAR.z0 + 0.4 + i * ((BAR.z1 - BAR.z0) - 0.8) / (BAR.stools - 1);

// ------------------------------------------------------------------ personajes de Mixamo
export const CHARACTERS = ['Remy', 'Ch01_nonPBR', 'Ch06_nonPBR', 'Ch07_nonPBR', 'Ch21_nonPBR', 'Ch22_nonPBR', 'Ch42_nonPBR'];
export const CLIPS = ['Idle', 'Walking', 'Bartending', 'Sitting', 'Sitting_Drinking', 'Sitting_Talking', 'Sitting_Laughing', 'Sitting_Clap',
  'Rumba_Dancing', 'Silly_Dancing', 'Talking', 'Waving', 'Drinking'];
export const SIT_CLIPS = ['Sitting_Talking', 'Sitting_Drinking', 'Sitting_Laughing', 'Sitting_Clap', 'Sitting'];
export const IN_PLACE = new Set(['Walking', 'Rumba_Dancing', 'Silly_Dancing', 'Talking', 'Drinking']);
export const WOMEN = /^(Ch07|Ch21|Ch22)/;
export const CLIENTS = ['Remy', 'Ch42_nonPBR', 'Ch21_nonPBR', 'Ch22_nonPBR', 'Ch07_nonPBR', 'Ch01_nonPBR', 'Ch06_nonPBR'];
// Quién es quién (como en bar.html): barman Ch01 / bartender Ch22, mesero Ch01, DJ Ch06 (buzo y audífonos), representante Ch07 (traje).
export const STAFF_MODEL = {barman: ['Ch01_nonPBR', 'Ch22_nonPBR'], mesero: ['Ch01_nonPBR', 'Ch42_nonPBR'], dj: ['Ch06_nonPBR'], caja: ['Ch21_nonPBR'],
  cocina: ['Remy'], '': ['Ch01_nonPBR']};
export const REP_MODEL = 'Ch07_nonPBR';
// Selector de género del editor (Hombre / Mujer y su personaje) para el personal; sin nada guardado, el de siempre.
export function staffModel(def, saved, key) {
  const pool = saved && saved.genero === 'mujer' ? CHARACTERS.filter(n => WOMEN.test(n)) : saved && saved.genero === 'hombre' ? CHARACTERS.filter(n => !WOMEN.test(n)) : null;
  if (saved && saved.personaje && CHARACTERS.includes(saved.personaje) && (!pool || pool.includes(saved.personaje))) return saved.personaje;
  if (!pool || pool.includes(def)) return def;
  return pool[hashOf(key || '') % pool.length];
}
// Ropa alegre de los clientes (solo la camisa/blusa: la piel nunca se toca).
export const HAPPY = ['#ff4d6d', '#ffb703', '#2ec4b6', '#8338ec', '#3a86ff', '#fb5607', '#06d6a0', '#ff006e', '#f15bb5', '#00bbf9'];
export const STAFF_BLACK = '#141416';

// Altura real medida con la caja precisa en reposo: hombres 1,78 m, mujeres 1,66 m.
export function heightFor(name) { return WOMEN.test(String(name)) ? 1.66 : 1.78; }

// Prefijo de los huesos del personaje (mixamorig, mixamorig12, ...): three quita los ":" del nombre.
export function bonePrefix(hipsName) { return String(hipsName || '').replace(/Hips$/, '') || 'mixamorig'; }

// Una pista de la animación ("mixamorig:Hips.position" o "mixamorigHips.quaternion") con el prefijo del personaje.
export function retargetName(trackName, prefix) { return String(trackName).replace(/^mixamorig\d*:?/, prefix); }

// Escala de la cadera: altura de cadera en reposo del personaje / altura de cadera de la animación.
export function hipScale(charHipY, animHipY) {
  const a = Number(animHipY), c = Number(charHipY);
  return a > 0 && c > 0 ? c / a : 1;
}

// Hips.position escalada; "en el sitio" (caminar, bailar, ...) deja X/Z fijos en el primer cuadro: sin deriva.
// anchor: la cadera queda sobre el asiento (X/Z relativos al primer cuadro) para las animaciones sentadas recortadas.
export function scaleHips(values, k, inPlace, anchor) {
  const v = Array.from(values), x0 = v[0], z0 = v[2];
  for (let i = 0; i < v.length; i += 3) {
    v[i] = anchor ? (v[i] - x0) * k : (inPlace ? x0 : v[i]) * k; v[i + 1] *= k; v[i + 2] = anchor ? (v[i + 2] - z0) * k : (inPlace ? z0 : v[i + 2]) * k;
  }
  return v;
}

// Algunas animaciones "sentadas" de Mixamo empiezan de pie, caminan y se sientan (Sitting_Drinking: 4,3 s de pie y
// 2,6 m de recorrido). En el bar la persona ya está en su silla: se usa solo la parte sentada (desde que la cadera
// baja a su altura de sentado). times = tiempos de la pista Hips.position, values = sus valores x,y,z.
export function seatedStart(times, values) {
  let minY = Infinity; for (let i = 1; i < values.length; i += 3) minY = Math.min(minY, values[i]);
  for (let i = 0; i < times.length; i++) if (values[i * 3 + 1] <= minY + 0.06) return times[i];
  return 0;
}

// Plan de retargeting de una animación para un personaje: nombre nuevo de cada pista y qué pista se escala.
export function retargetPlan(trackNames, hipsName, charHipY, animHipY, clipName, trimmed = false) {
  const prefix = bonePrefix(hipsName);
  return {prefix, k: hipScale(charHipY, animHipY), inPlace: IN_PLACE.has(clipName), anchor: !!trimmed,
    tracks: trackNames.map(n => ({from: n, to: retargetName(n, prefix), hips: /Hips\.position$/.test(n)}))};
}

// ------------------------------------------------------------------ mesas y puestos de barra (configuración real)
const isBarSeat = l => /^(barra|bar)(\s|$|·|:|#|-)/i.test(String(l || '').trim());

// Mesas reales -> puestos de bar.html (en orden). Puestos de barra de Clonexa ("Barra 3") -> los 9 taburetes.
export function layoutTables(labels) {
  const tables = [], stools = {}; let overflow = 0, nextStool = 0;
  for (const label of labels || []) {
    if (isBarSeat(label)) {
      const n = parseInt(String(label).replace(/\D+/g, ' ').trim().split(' ')[0], 10);
      const idx = Number.isFinite(n) && n >= 1 && n <= BAR.stools && !Object.values(stools).includes(n - 1) ? n - 1 : nextStool;
      if (idx < BAR.stools) { stools[label] = idx; nextStool = Math.max(nextStool, idx + 1); } else overflow++;
      continue;
    }
    if (tables.length < TABLE_POS.length) tables.push({label, pos: TABLE_POS[tables.length]}); else overflow++;
  }
  return {tables, stools, overflow};
}

// Etiqueta de la mesa: "● Mesa N · QR activo" (verde) o "Mesa N · libre" (gris).
export function tableTag(label, open) {
  return open ? {cls: 'mesa on', text: `${label} · QR activo`, dot: true} : {cls: 'mesa off', text: `${label} · libre`, dot: false};
}

// Clientes que llegan al abrirse una mesa: los registrados en Clonexa (1 a 4 sillas); si no, 2 o 3 (siempre los mismos).
export function guestsFor(table) {
  if (table && Number.isFinite(table.guests) && table.guests > 0) return Math.max(1, Math.min(4, table.guests));
  let h = 0; for (const ch of String((table && table.label) || '')) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return 2 + (h % 2);
}

export function hashOf(s) { let h = 7; for (const ch of String(s)) h = (h * 31 + ch.charCodeAt(0)) >>> 0; return h; }

// Quién se sienta y cómo (personaje, animación sentada, color de la ropa), estable por mesa.
export function guestCast(label, n) {
  const h = hashOf(label);
  return Array.from({length: n}, (_, i) => ({model: CLIENTS[(h + i * 3) % CLIENTS.length], clip: SIT_CLIPS[(h + i) % 4],
    tint: HAPPY[(h + i * 7) % HAPPY.length], side: SEAT_ORDER[i % 4], t: ((h >> (i + 2)) % 100) / 100}));
}

// ------------------------------------------------------------------ estado del bar
export function isClosed(snap) {
  const b = (snap && snap.business) || {};
  return !b.open && !b.activity_off_hours;
}
export function activeTables(snap) { return ((snap && snap.tables) || []).filter(t => t.open).length; }

// AMBIENTE (no son datos): bailarines en la pista solo con el bar abierto y mesas activas: 1 por cada 2, máximo 4.
export function dancersFor(snap) { return isClosed(snap) ? 0 : Math.min(DANCERS.length, Math.floor(activeTables(snap) / 2)); }
// AMBIENTE (no son datos): clientes en los taburetes y de pie conversando, para que el bar abierto se vea vivo.
// Solo con el bar abierto y mesas activas; nunca reemplazan un dato (los puestos de barra reales mandan).
export function ambientFor(snap) {
  const a = isClosed(snap) ? 0 : activeTables(snap);
  return {stools: a >= 2 ? Math.min(3, a - 1) : 0, standers: a >= 3 ? STANDERS.length : 0};
}
export const AMBIENT_STOOLS = [2, 3, 6];

// Puesto de cada cargo (posición y animación de trabajo). Pausa -> se aparta con Idle.
export function staffSpot(uniform, idx, paused) {
  if (paused) return {pos: [-7.1 + (idx % 3) * 0.6, 4.6, Math.PI * 0.75], clip: 'Idle'};
  if (uniform === 'barman') return {pos: [[BAR.x - 0.75, -2.6], [BAR.x - 0.75, 1.0], [BAR.x - 0.75, -0.8]][idx % 3].concat([Math.PI / 2]), clip: 'Bartending'};
  if (uniform === 'dj') return {pos: DJ.spot, clip: 'Silly_Dancing'};
  if (uniform === 'caja') return {pos: [BAR.x - 0.75, 2.3, Math.PI / 2], clip: 'Idle'};
  if (uniform === 'cocina') return {pos: [BAR.x - 0.75, -3.8, Math.PI / 2], clip: 'Idle'};
  return {pos: [BAR.x + 1.3 + (idx % 3) * 0.6, 3.4, -Math.PI * 0.6], clip: 'Idle'};   // mesero: al final de la barra (recoge pedidos)
}
// El barman trabaja (Bartending) si hay pedidos por preparar; si no, espera (Idle).
export function barmanClip(task) { return /^Preparando/.test(String(task || '')) ? 'Bartending' : 'Idle'; }

export function staffTitle(p) {
  const r = String((p && p.role) || '').trim();
  return r || {barman: 'Barman', mesero: 'Mesero', dj: 'DJ', caja: 'Caja', cocina: 'Cocina'}[(p && p.uniform) || ''] || 'Personal';
}

// Globo del representante: solo cifras de actividad, nunca dinero.
export function repBubble(snap) {
  const k = Object.fromEntries(((snap && snap.kpis) || []).map(([a, b]) => [a, b]));
  const open = activeTables(snap);
  const songs = k['Canciones pedidas'] ?? (((snap && snap.songs) || []).length);
  const staff = k['Personal en turno'] ?? ((snap && snap.staff && snap.staff.count) ?? '—');
  return [`${open} ${open === 1 ? 'mesa abierta' : 'mesas abiertas'}`, `${k['Pedidos a barra'] ?? '—'} pedidos`, `${songs} canciones`, `${staff} en turno`].join(' · ');
}

// Pantalla "Canciones pedidas": lo que suena (con barra de avance) y las siguientes 3; vacía o bar cerrado.
export const SONG_SECONDS = 210;   // duración típica (Clonexa no guarda la duración): la barra avanza hasta 95 %
export function screenModel(snap, nowMs) {
  if (isClosed(snap)) return {mode: 'cerrado', sign: (snap.business && snap.business.sign) || 'Cerrado · abre 18:00'};
  const s = (snap && snap.song_screen) || {now: null, queue: []};
  if (!s.now && !(s.queue || []).length) return {mode: 'vacio', text: 'Pide tu canción desde el QR de tu mesa'};
  let progress = 0;
  if (s.now && s.now.since) { const t0 = Date.parse(s.now.since); if (Number.isFinite(t0)) progress = Math.max(0, Math.min(0.95, (nowMs - t0) / 1000 / SONG_SECONDS)); }
  return {mode: 'lista', now: s.now ? {title: s.now.title, from: s.now.table ? `Pedida desde la ${s.now.table}` : 'Pedida desde el QR', progress} : null,
    queue: (s.queue || []).slice(0, 3).map((q, i) => ({n: String(i + 2), title: q.title, from: q.table || 'QR'}))};
}
export function nowPlaying(snap) {
  const s = snap && snap.song_screen;
  if (s && s.now) return s.now.title;
  return null;
}

// Lo que cambió entre dos copias vivas (la primera no anima: solo acomoda).
export function diffBar(prev, next) {
  const ev = [];
  if (!next || !next.ok) return ev;
  const first = !prev;
  const pt = new Map(((prev && prev.tables) || []).map(t => [t.label, t]));
  for (const t of next.tables || []) {
    const was = pt.get(t.label);
    if (t.open && !(was && was.open)) ev.push({type: 'mesa_abierta', table: t.label, guests: guestsFor(t), instant: first});
    if (!t.open && was && was.open) ev.push({type: 'mesa_cerrada', table: t.label});
  }
  const po = new Map(((prev && prev.orders) || []).map(o => [o.id, o]));
  for (const o of next.orders || []) {
    const was = po.get(o.id);
    if (!first && o.state === 'entregado' && (!was || was.state !== 'entregado')) ev.push({type: 'pedido_entregado', table: o.table, items: o.items});
  }
  return ev;
}

// Ruta por los pasillos entre mesas (sin atravesar mesas): al pasillo vertical más cercano, por el pasillo
// horizontal más cercano al destino, al pasillo vertical del destino y al destino.
export const AISLE_X = [-4.1, -1.3, 1.3, 3.9, 6.6];
export const AISLE_Z = [-1.7, 0.9, 3.3, 5.1];
const nearest = (list, v) => list.reduce((a, b) => (Math.abs(b - v) < Math.abs(a - v) ? b : a));
const behindBar = p => p[0] < BAR.x - 0.2 && p[1] < BAR.z1 + 0.3;
const BAR_GATE = [BAR.x - 0.75, BAR.z1 + 0.6];   // se entra detrás de la barra por su extremo (no se atraviesa)
export function route(from, to) {
  if (behindBar(to) && !behindBar(from)) return route(from, [-4.1, BAR_GATE[1]]).concat([BAR_GATE, [to[0], BAR_GATE[1]], [to[0], to[1]]]);
  if (behindBar(from) && !behindBar(to)) return [[from[0], BAR_GATE[1]], BAR_GATE, [-4.1, BAR_GATE[1]]].concat(route([-4.1, BAR_GATE[1]], to));
  if (behindBar(from) && behindBar(to)) return [[to[0], to[1]]];
  const ax0 = nearest(AISLE_X, from[0]), az = nearest(AISLE_Z, to[1]), ax1 = nearest(AISLE_X, to[0]);
  const pts = [[ax0, from[1]], [ax0, az], [ax1, az], [ax1, to[1]], [to[0], to[1]]];
  const out = [];
  for (const p of pts) { const last = out[out.length - 1] || from; if (Math.hypot(p[0] - last[0], p[1] - last[1]) > 0.05) out.push(p); }
  return out;
}

// Clic dentro del piso: persona -> su ficha; mesa -> su estado; nada más (nunca cambia de piso).
export function clickTarget(ud) {
  if (ud && ud.person) return {type: 'persona'};
  if (ud && ud.table) return {type: 'mesa', label: ud.table};
  return {type: 'nada'};
}
export function tableInfo(snap, label) {
  const t = ((snap && snap.tables) || []).find(x => x.label === label) || {label, open: false};
  const pend = ((snap && snap.orders) || []).filter(o => o.table === label && o.state !== 'entregado').reduce((a, o) => a + (o.items || 0), 0);
  const songs = ((snap && snap.songs) || []).filter(s => s.table === label).length;
  return {label, open: !!t.open, since: t.since || null, guests: t.guests || null, pending: pend, songs};
}
