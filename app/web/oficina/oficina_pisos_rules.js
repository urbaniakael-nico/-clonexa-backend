// Oficina 3D · pisos aprobados (Clonexa, Velvet, Asadero El Socio, VOLTAGE) · reglas puras, sin three
// (se prueban en tests/oficina_pisos.test.cjs). Fuente de verdad del diseño: las escenas aprobadas
// referencia-pisos/{clonexa,velvet,asadero,voltage}.html (medidas, distribución, cámara y etiquetas).
// REGLA DE ORO: todo lo que se muestra sale de la copia viva (datos reales); si no existe, "—". Lo único
// decorativo es el AMBIENTE (marcado como tal). Nunca dinero en los pisos de clientes.

export const LIVE_MS = 7000;   // copia viva cada 7 s (entre 5 y 10); pausa si la pestaña no se ve
export const FADE = 0.45;
export const NO = '—';
export const show = v => (v === null || v === undefined || v === '' ? NO : String(v));

// ------------------------------------------------------------------ personajes de Mixamo por género
export const MEN = ['Remy', 'Ch01_nonPBR', 'Ch06_nonPBR', 'Ch42_nonPBR', 'Ch17_nonPBR'];
export const WOMEN = ['Ch07_nonPBR', 'Ch21_nonPBR', 'Ch22_nonPBR'];
export const CHARACTERS = [...MEN, ...WOMEN];
export const CLIPS = ['Idle', 'Walking', 'Typing', 'Sitting', 'Talking', 'Drinking', 'Sitting_Drinking', 'Bartending', 'Sitting_Talking', 'Sitting_Laughing'];
export const SIT_CLIPS = ['Sitting', 'Sitting_Drinking', 'Sitting_Talking', 'Sitting_Laughing', 'Typing'];
export const SEATED = /^(Sitting|Typing)/;
// Typing.glb es nuevo en el bucket: mientras no esté, quien escribe aparece sentado (Sitting).
export const CLIP_FALLBACK = {Typing: 'Sitting', Bartending: 'Idle', Sitting_Talking: 'Sitting', Sitting_Laughing: 'Sitting', Drinking: 'Idle'};
export function clipOr(name, available) { let n = name; for (let i = 0; i < 3 && !available.has(n); i++) n = CLIP_FALLBACK[n] || 'Idle'; return n; }

export const genderOf = model => (WOMEN.includes(model) ? 'mujer' : 'hombre');
export function hashOf(s) { let h = 7; for (const ch of String(s)) h = (h * 31 + ch.charCodeAt(0)) >>> 0; return h; }

// Género por defecto según el primer nombre (editable en el editor). Nombres masculinos en "a" y femeninos que no
// terminan en "a" van en las listas; KRISS (Velvet) es hombre.
const MALE_NAMES = new Set(['kriss', 'kris', 'cris', 'luca', 'nicola', 'andrea', 'josua', 'joshua', 'elia', 'garcia', 'borja', 'santi']);
const FEMALE_NAMES = new Set(['isabel', 'raquel', 'carmen', 'pilar', 'luz', 'mar', 'beatriz', 'ines', 'inés', 'esther', 'ruth', 'abigail', 'nicole',
  'michelle', 'karen', 'lizeth', 'yuly', 'yuli', 'sol', 'rocio', 'rocío', 'consuelo', 'mercedes', 'dolores', 'marisol', 'jennifer', 'evelyn', 'ingrid',
  'miriam', 'nataly', 'nathaly', 'sharon', 'astrid', 'maribel', 'leidy', 'ledy', 'heidy', 'deisy', 'daisy', 'yeimy', 'jasmin', 'yasmin', 'lucy', 'mary']);
export function genderFromName(first) {
  const n = String(first || '').trim().split(/\s+/)[0].toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '');
  if (!n) return null;
  if (MALE_NAMES.has(n)) return 'hombre';
  if (FEMALE_NAMES.has(n)) return 'mujer';
  return /a$/.test(n) ? 'mujer' : 'hombre';
}

// Configuración del personaje de una persona: lo guardado en el editor manda; si no, el género por el nombre
// (o estable por la clave cuando la privacidad es "solo cargo") y un personaje estable de ese género.
export function personCfg(key, first, saved = {}, floorDefaults = {}) {
  // sin nombre (privacidad "solo cargo"): el género del personaje del piso (VOLTAGE: técnico con casco) o estable por la clave
  const gender = saved.genero || genderFromName(first) || floorDefaults.genero || (floorDefaults.models ? genderOf(floorDefaults.models[0]) : (hashOf(key) % 3 === 0 ? 'mujer' : 'hombre'));
  const pool = gender === 'mujer' ? WOMEN : MEN;
  const plain = pool.filter(m => m !== 'Ch17_nonPBR');   // Ch17 (casco y chaleco) solo donde el piso lo pide o el editor lo elige
  const cands = (floorDefaults.models || plain).filter(m => pool.includes(m)); const list = cands.length ? cands : plain;
  const model = saved.personaje && pool.includes(saved.personaje) ? saved.personaje : list[hashOf(key) % list.length];
  const tunic = saved.tunica ? saved.tunica === 'si' : !!floorDefaults.tunic;
  return {gender, model, tunic, beard: gender === 'hombre' && saved.barba === 'si', tint: saved.color_ropa || floorDefaults.tint || null,
    hair: saved.color_pelo || null, beardColor: saved.color_barba || saved.color_pelo || null};
}

// ------------------------------------------------------------------ altura y retargeting (igual al bar aprobado)
export const heightFor = (name, tall) => (WOMEN.includes(String(name)) ? 1.65 : (tall ? 1.8 : 1.77));

// Quién entra, quién sale y quién cambia (por la clave estable de cada persona).
export function diffPeople(prevKeys, people) {
  const now = new Set(people.map(p => p.key));
  return {enter: people.filter(p => !prevKeys.has(p.key)).map(p => p.key), leave: [...prevKeys].filter(k => !now.has(k))};
}

// ================================================================== CLONEXA (clonexa.html / clonexa.png)
// Cámara: el encuadre de clonexa.png (algo más cerca que la cámara por defecto de clonexa.html).
export const CLONEXA = {ROOM: {W: 30, D: 20, WALL: 4.2}, CAMERA: {pos: [4.2, 15.5, 22.5], look: [0.5, 0, -1.2], fov: 30},
  ZONES: {direccion: [-10, -6, 8, 6.5, 0xa855f7, 'Dirección', -2.4], juntas: [0, -6, 9, 6.5, 0xf20b6d, 'Sala de juntas', -2.4],
    marketing: [10, -6, 8, 6.5, 0x8b5cf6, 'Marketing', -2.4], ventas: [-10.5, 5.5, 7.5, 7, 0x22c55e, 'Ventas', 9.2],
    bots: [-1.5, 5.5, 8.5, 7, 0x38bdf8, 'Bots y operaciones', 9.2], tesoreria: [5.5, 5.5, 4.5, 7, 0xeab308, 'Tesorería', 9.2],
    lounge: [11, 5.5, 6.5, 7, 0xfb923c, 'Lounge', 9.2]},
  // escritorios de clonexa.html por área [x, z, giro]; los que sobran quedan libres, si faltan se agregan en fila
  DESKS: {marketing: [[7.2, -7.3, .25], [10, -7.8, 0], [12.8, -7.3, -.25], [8.6, -4.6, .12], [11.4, -4.6, -.12]],
    ventas: [[-12.2, 4.2, Math.PI], [-9.2, 4.2, Math.PI], [-12.2, 7.2, Math.PI], [-9.2, 7.2, Math.PI]],
    bots: [[-4.4, 3.9, Math.PI], [-1.5, 3.9, Math.PI], [1.4, 3.9, Math.PI], [-4.4, 6.9, Math.PI], [-1.5, 6.9, Math.PI], [1.4, 6.9, Math.PI]],
    tesoreria: [[5.5, 4.6, Math.PI]]},
  CEO: [-8.6, -5.4, -0.5, 0.16], PRESENTER: [0.4, 0.2, -0.2, 0.12], GUARD: [-3.0, 8.1, Math.PI],
  // lounge: sofás y puestos de pie (clonexa.html)
  LOUNGE: [[9.6, 3.62, Math.PI, 'Sitting_Drinking'], [13.0, 3.62, Math.PI, 'Sitting_Drinking'], [12.2, 7.6, -2.6, 'Drinking'], [10.6, 7.4, 2.4, 'Drinking'],
    [9.0, 3.62, Math.PI, 'Sitting_Drinking'], [13.6, 3.62, Math.PI, 'Sitting_Drinking'], [14.0, 6.6, -1.8, 'Drinking'], [9.4, 6.4, 1.2, 'Drinking']],
};
// Nombre y personaje de cada agente (como clonexa.html); el editor puede renombrarlos y cambiar su personaje.
export const AGENT_NAME = {director: 'Tú · CEO', asistente: 'Nexa Asistente', creativo: 'Director creativo', contenido: 'Nexa Contenido', planb: 'Plan B',
  tiktok: 'Nexa TikTok', analista: 'Analista', ventas: 'Nexa Ventas', correos: 'Nexa Correos', prospecta: 'Prospectora', comunidad: 'Nexa Comunidad',
  mensajero: 'Mensajero VOLTAGE', archivista: 'Archivista', lector: 'Lector de cartas', guardian: 'Guardián', tesoreria: 'Tesorería'};
export const AGENT_MODEL = {director: 'Ch01_nonPBR', asistente: 'Ch07_nonPBR', creativo: 'Remy', contenido: 'Ch22_nonPBR', planb: 'Ch42_nonPBR', tiktok: 'Ch21_nonPBR',
  analista: 'Ch42_nonPBR', ventas: 'Ch07_nonPBR', correos: 'Ch01_nonPBR', prospecta: 'Ch21_nonPBR', comunidad: 'Ch22_nonPBR', mensajero: 'Ch06_nonPBR',
  archivista: 'Ch01_nonPBR', lector: 'Ch07_nonPBR', guardian: 'Ch06_nonPBR', tesoreria: 'Ch21_nonPBR'};
export function agentModel(id) { return AGENT_MODEL[id] || [...MEN, ...WOMEN].filter(m => m !== 'Ch17_nonPBR')[hashOf(id) % 7]; }
// Configuración de un agente: túnica negra siempre en el piso Clonexa (por defecto); el CEO con líneas moradas,
// barba larga y pelo largo (el editor cambia el color o quita la barba).
export function agentCfg(id, saved = {}) {
  const def = agentModel(id); const gender = saved.genero || genderOf(def); const pool = gender === 'mujer' ? WOMEN : MEN;
  const model = saved.personaje && pool.includes(saved.personaje) ? saved.personaje : (pool.includes(def) ? def : pool[hashOf(id) % pool.length]);
  const ceo = id === 'director';
  return {model, gender, tunic: saved.tunica ? saved.tunica === 'si' : true, lines: ceo ? 0xa855f7 : null, beard: gender === 'hombre' && (saved.barba ? saved.barba === 'si' : ceo),
    longHair: ceo, beardColor: saved.color_barba || saved.color_pelo || null, hair: saved.color_pelo || null, tall: ceo, name: saved.nombre || AGENT_NAME[id] || id};
}
// Tesorería: una persona en su escritorio que lee la Facturación (no es un flujo de n8n).
export function treasuryWorker(snap) {
  const t = snap && snap.treasury;
  return {id: 'tesoreria', area: 'tesoreria', state: t ? 'work' : 'nodata', today: [treasuryTag(snap)]};
}
export const ST = {work: 'Trabajando', wait: 'Esperando', err: 'Error', train: 'En entrenamiento', nodata: 'Sin datos', cafe: 'Café'};

// Escritorios de un área: los de clonexa.html y, si hay más trabajadores, otros en filas detrás (sin tabiques).
export function desksFor(area, n) {
  const base = CLONEXA.DESKS[area] || [];
  const out = base.slice(0, Math.max(n, base.length));
  const [cx, cz, w] = CLONEXA.ZONES[area] || [0, 0, 6];
  for (let i = out.length; i < n; i++) { const k = i - base.length; const cols = Math.max(1, Math.floor(w / 2.9)); out.push([cx - (cols - 1) * 1.45 + (k % cols) * 2.9, cz + (area === 'marketing' ? -1.2 : 1.6) + Math.floor(k / cols) * 1.2, area === 'marketing' ? 0 : Math.PI]); }
  return out;
}

// Dónde está y qué hace cada trabajador (agente de n8n o bot de Telegram) según su estado REAL:
// trabajando -> escribe en su escritorio (Typing); esperando -> Lounge (bebe) y vuelve cuando su flujo corre;
// error -> en su escritorio con anillo/etiqueta roja; entrenamiento -> azul; sin datos -> gris, sentado.
export function clonexaPlan(workers) {
  const by = {}; const out = []; let lounge = 0;
  for (const w of workers || []) {
    if (w.id === 'director' || w.id === 'asistente') continue;
    if (w.id === 'guardian') {   // de pie junto a la torre de servidores (clonexa.html)
      const g = CLONEXA.GUARD; out.push({id: w.id, area: 'bots', desk: null, stand: g, lounge: null, clip: w.state === 'work' ? 'Talking' : 'Idle',
        ring: w.state === 'err' ? 'red' : w.state === 'train' ? 'blue' : null, tag: workerTag(w, false)}); continue;
    }
    (by[w.area] = by[w.area] || []).push(w);
  }
  for (const [area, list] of Object.entries(by)) {
    const desks = desksFor(area, list.length);
    list.forEach((w, i) => {
      const desk = desks[i];
      const toLounge = w.state === 'wait' && lounge < CLONEXA.LOUNGE.length;
      const spot = toLounge ? CLONEXA.LOUNGE[lounge++] : null;
      out.push({id: w.id, area, desk, deskIndex: i, lounge: spot, clip: toLounge ? spot[3] : w.state === 'work' ? 'Typing' : 'Sitting',
        ring: w.state === 'err' ? 'red' : w.state === 'train' ? 'blue' : null, tag: workerTag(w, toLounge)});
    });
  }
  return out;
}
export function workerTag(w, inLounge) {
  const first = (w.today || [])[0] || '';
  const task = inLounge ? 'Café · sin trabajo ahora' : w.state === 'err' ? '⚠ Error en la última ejecución' : w.state === 'train' ? 'En entrenamiento'
    : w.state === 'nodata' ? 'Sin datos' : (first || ST[w.state] || '');
  return {cls: inLounge ? 'wait' : w.state, text: task.length > 46 ? task.slice(0, 45) + '…' : task};
}
export function ceoTag(snap) {
  const a = (snap && snap.approvals) || {};
  const parts = [a.pieces == null ? 'piezas —' : `${a.pieces} ${a.pieces === 1 ? 'pieza' : 'piezas'}`,
    a.batch == null ? 'lote —' : a.batch ? '1 lote de correos' : '0 lotes', a.leads == null ? 'leads —' : `${a.leads} leads`];
  return 'Aprobaciones pendientes: ' + parts.join(' · ');
}
export function presenterTag(snap) {
  const n = ((snap && snap.companies) || []).length;
  return n ? `Presentando ${n} ${n === 1 ? 'empresa' : 'empresas'} · hoy` : 'Sin empresas registradas';
}
export const TREASURY_COLOR = {al_dia: '#22c55e', vence: '#f59e0b', vencido: '#ef4444', sin_contrato: '#9ca3af'};
export const HEALTH_COLOR = {ok: '#22c55e', warn: '#f59e0b', bad: '#ef4444', nodata: '#6b7280'};
export function treasuryTag(snap) {
  const t = snap && snap.treasury; if (!t) return 'Facturación: sin datos';
  const ok = t.filter(x => x.state === 'al_dia').length; return `${ok} de ${t.length} al día`;
}

// ================================================================== VELVET · taller (velvet.html / velvet.png)
// Cámara de Velvet: la del PNG aprobado (velvet.png se tomó más cerca que la cámara por defecto de velvet.html).
export const TALLER = {ROOM: {W: 18, D: 12, WALL: 3.4}, CAMERA: {pos: [1.6, 8.6, 11.4], look: [-0.6, 0.9, -1.6], fov: 32},
  CAFE: {x: -6.4, z: 3.6}, CUT: [5.2, -2.5, Math.PI],
  CAFE_SEATS: [[-6.4, 2.58, 0], [-6.4, 3.82, Math.PI], [-4.8, 3.88, 0], [-4.8, 5.12, Math.PI], [-7.2, 5.3, Math.PI / 2], [-5.6, 5.4, -Math.PI / 2]]};
// Máquinas en 2 filas (como velvet.html: 2 x 5); de 11 a 12 personas, 2 x 6.
export function machinePositions(n) {
  const cols = n > 10 ? 6 : 5, step = n > 10 ? 1.75 : 2.1, x0 = n > 10 ? -7.6 : -7.4;
  return Array.from({length: n}, (_, k) => [x0 + (k % cols) * step, -3.6 + Math.floor(k / cols) * 2.6]);
}
// Quién se sienta en qué máquina (estable: una persona conserva su máquina mientras sigue en turno) y quién va al café.
export function assignMachines(prev, people, n) {
  const seat = new Map(); const used = new Set();
  for (const p of people) if (p.status === 'working' && prev.has(p.key) && prev.get(p.key) < n && !used.has(prev.get(p.key))) { seat.set(p.key, prev.get(p.key)); used.add(prev.get(p.key)); }
  for (const p of people) if (p.status === 'working' && !seat.has(p.key)) { let i = 0; while (used.has(i) && i < n) i++; if (i < n) { seat.set(p.key, i); used.add(i); } }
  return {seat, free: Array.from({length: n}, (_, i) => i).filter(i => !used.has(i)), cafe: people.filter(p => p.status === 'paused').map(p => p.key)};
}
export function sewerTag(p) {
  if (p.status === 'paused') return {cls: 'pausa', text: `${p.label}`, small: `En pausa · ${p.paused_min == null ? NO : p.paused_min + ' min'}`};
  return {cls: '', text: p.label, small: `Cosiendo · ${p.reference || NO}`};
}
export function boardModel(b) {
  b = b || {};
  return {lot: show(b.lot), progress: b.made != null && b.meta ? `${b.made} de ${b.meta} prendas` : `${show(b.made)} prendas`, percent: b.percent,
    day: b.day != null ? `día ${b.day} del lote` : `día ${NO}`, kpis: [[show(b.on_shift), 'en turno'], [show(b.paused), 'en pausa'], [show(b.hours), 'horas hoy'], [show(b.week_sum), 'prendas semana']],
    week: b.week || null, sent: b.sent != null ? `${b.sent} enviadas a Bombón esta semana` : `Enviadas a Bombón: ${NO}`,
    next: `Próximo envío a Bombón: ${show(b.next_send)}`, rack: b.to_send != null ? `${b.to_send} listas para Bombón` : `Listo para Bombón · ${NO}`};
}

// ================================================================== ASADERO · restaurante (asadero.html / asadero.png)
export const RESTAURANTE = {ROOM: {W: 18, D: 12, WALL: 3.4}, CAMERA: {pos: [3, 11, 17], look: [0.5, 0.3, -0.8], fov: 32},
  TABLES: [[-3.2, -0.9], [-0.6, -0.9], [2.0, -0.9], [-3.2, 1.9], [-0.6, 1.9], [2.0, 1.9], [-3.2, 4.5], [-0.6, 4.5], [2.0, 4.5], [-5.8, 1.9], [-5.8, 4.5], [-5.8, -0.9], [4.4, 1.9], [4.4, -0.9]],
  SEAT_D: 0.78, KITCHEN: [[-6.6, -4.3], [-4.0, -4.3], [-5.3, -4.3], [-2.8, -4.3]], CASHIER: [6.2, -2.8, Math.PI], WAITER: [3.2, -2.9, -0.7],
  PASS: [-3.6, -3.3], DRIVER: [7.2, 3.6, -2.6], DOOR: [8.2, 5.6], REP: [4.4, 5.0, -0.5]};
export const SEATS = {n: [0, -RESTAURANTE.SEAT_D, 0], s: [0, RESTAURANTE.SEAT_D, Math.PI], w: [-RESTAURANTE.SEAT_D, 0, Math.PI / 2], e: [RESTAURANTE.SEAT_D, 0, -Math.PI / 2]};
export function layoutTables(labels) {
  const pos = RESTAURANTE.TABLES; return {tables: (labels || []).slice(0, pos.length).map((label, i) => ({label, pos: pos[i]})), overflow: Math.max(0, (labels || []).length - pos.length)};
}
export function tableTag(t) { return t.open ? {cls: 'mesa on', text: `${t.label} · QR activo`, dot: true} : {cls: 'mesa off', text: `${t.label} · libre`, dot: false}; }
// AMBIENTE (no son datos): cuántos clientes se sientan en una mesa con QR activo: los registrados (1 a 4); si no, 2 o 3.
export function guestsFor(t) { if (t && t.guests > 0) return Math.min(4, t.guests); return 2 + (hashOf(t && t.label) % 2); }
export function guestCast(label, n) {
  const h = hashOf(label), order = ['n', 'e', 'w', 's'], clips = ['Sitting_Talking', 'Sitting_Laughing', 'Sitting_Drinking', 'Sitting_Talking'];
  const pool = CHARACTERS.filter(m => m !== 'Ch17_nonPBR');   // el casco y chaleco es del domiciliario / técnicos, no de los clientes
  return Array.from({length: n}, (_, i) => ({model: pool[(h + i * 3) % pool.length], side: order[i], clip: clips[(h + i) % 4]}));
}
// Eventos entre dos copias vivas: mesa abierta/cerrada y pedido entregado (-> el mesero lo lleva).
export function diffRestaurante(prev, next) {
  const ev = []; if (!next || !next.ok) return ev; const first = !prev;
  const pt = new Map(((prev && prev.tables) || []).map(t => [t.label, t]));
  for (const t of next.tables || []) { const w = pt.get(t.label);
    if (t.open && !(w && w.open)) ev.push({type: 'mesa_abierta', table: t.label, instant: first});
    if (!t.open && w && w.open) ev.push({type: 'mesa_cerrada', table: t.label}); }
  const po = new Map(((prev && prev.orders) || []).map(o => [o.id, o]));
  for (const o of next.orders || []) { const w = po.get(o.id); if (!first && o.state === 'entregado' && (!w || w.state !== 'entregado')) ev.push({type: 'pedido_entregado', table: o.table}); }
  const pd = new Map(((prev && prev.deliveries) || []).map(d => [d.id, d]));
  for (const d of next.deliveries || []) { const w = pd.get(d.id); if (!first && d.state === 'camino' && (!w || w.state !== 'camino')) ev.push({type: 'domicilio_sale', label: d.label, barrio: d.barrio}); }
  return ev;
}
export function tableInfo(snap, label) {
  const t = ((snap && snap.tables) || []).find(x => x.label === label) || {label, open: false};
  const pending = ((snap && snap.orders) || []).filter(o => o.table === label && o.state !== 'entregado').reduce((a, o) => a + (o.items || 0), 0);
  return {label, open: !!t.open, since: t.since || null, guests: t.guests || null, pending, songs: 0};
}
export const DELIVERY_LABEL = {cocina: ['En cocina', '#f59e0b'], listo: ['Listo', '#a78bfa'], camino: ['En camino', '#38bdf8'], entregado: ['Entregado', '#22c55e']};
export function restStaffSpot(uniform, idx, paused) {
  const R = RESTAURANTE;
  if (paused) return {pos: [7.6 - (idx % 3) * 0.6, -4.8, Math.PI], clip: 'Idle'};
  if (uniform === 'cocina') { const [x, z] = R.KITCHEN[idx % R.KITCHEN.length]; return {pos: [x, z, Math.PI], clip: 'Bartending'}; }
  if (uniform === 'caja') return {pos: [R.CASHIER[0] + idx * .7, R.CASHIER[1], R.CASHIER[2]], clip: 'Talking'};
  if (uniform === 'domiciliario') return {pos: [R.DRIVER[0] + idx * .8, R.DRIVER[1], R.DRIVER[2]], clip: 'Idle'};
  return {pos: [R.WAITER[0] + (idx % 3) * 0.7, R.WAITER[1] + Math.floor(idx / 3) * .7, R.WAITER[2]], clip: 'Idle'};
}
export const UNIFORM_TITLE = {cocina: 'Cocina', caja: 'Caja', mesero: 'Mesero', domiciliario: 'Domiciliario', '': 'Personal'};
export function restStaffTask(p, snap) {
  if (p.paused) return 'En pausa';
  const k = (snap && snap.kitchen) || [];
  if (p.uniform === 'cocina') return k.length ? `${k[0].label} · ${k[0].detail}` : 'Sin comandas';
  if (p.uniform === 'caja') return 'En caja';
  if (p.uniform === 'domiciliario') { const d = ((snap && snap.on_the_way) || [])[0]; return d ? `En camino · ${d.label}${d.barrio ? ' ' + d.barrio : ''}` : 'Esperando domicilio'; }
  const open = ((snap && snap.tables) || []).filter(t => t.open).length; return open ? `Atendiendo ${open} ${open === 1 ? 'mesa' : 'mesas'}` : 'Esperando clientes';
}
export function route(from, to) {   // por el pasillo central (z = 0.5) para no atravesar mesas
  const mid = 0.5, aisleX = [-4.5, -1.9, 0.7, 3.2]; const near = v => aisleX.reduce((a, b) => (Math.abs(b - v) < Math.abs(a - v) ? b : a));
  const ax = near(from[0]), bx = near(to[0]);
  return [[ax, from[1]], [ax, mid], [bx, mid], [bx, to[1]], [to[0], to[1]]].filter((p, i, a) => i === 0 ? Math.hypot(p[0] - from[0], p[1] - from[1]) > .05 : Math.hypot(p[0] - a[i - 1][0], p[1] - a[i - 1][1]) > .05);
}
export function repRestaurante(snap) {
  const k = Object.fromEntries(((snap && snap.kpis) || []).map(([a, b]) => [a, b]));
  return `${show(k['Pedidos del día'])} pedidos · ${show(k['En cocina ahora'])} en cocina · ${show(k['Domicilios del día'])} domicilios · ${show(k['Personal en turno'])} en turno`;
}
export function repTaller(snap) {
  const b = (snap && snap.board) || {}; return `${show(b.on_shift)} en turno · ${show(b.paused)} en pausa · lote ${show(b.lot)}`;
}

// ================================================================== VOLTAGE · campo (voltage.html / voltage.png)
export const CAMPO = {ROOM: {W: 20, D: 13, WALL: 3.6}, CAMERA: {pos: [2, 11, 17], look: [0, 0.3, -0.8], fov: 32}, VISIBLE: 5,
  TECH: [[2.2, -1.1], [4.4, -1.1], [3.0, -3.9], [5.6, -3.9], [6.6, -1.1]], SUPERVISOR: [6.4, 0.8], STORE: [5.6, 2.4], OUTSIDE: [9.0, -5.3], PLUS: [8.6, 4.2], REP: [0.8, 5.2, -0.4]};
// Lado de cada operación: la primera a la izquierda (como Virginia en voltage.html), la segunda a la derecha.
export function sideOf(i) { return i % 2 === 0 ? -1 : 1; }
// Puesto de una persona de la operación: técnicos en los racks (Bartending/Talking), supervisor y almacén en
// su sitio; fuera de perímetro (GPS real) -> fuera de la zona, con aro rojo.
export function campoSpots(op, side) {
  const out = []; let t = 0;
  for (const p of op.people || []) {
    let pos, clip, ry;
    if (p.outside) { pos = [side * CAMPO.OUTSIDE[0] + (out.filter(x => x.outside).length) * side * -0.8, CAMPO.OUTSIDE[1]]; clip = 'Idle'; ry = side > 0 ? -2.4 : 2.4; }
    else if (p.role === 'supervisor') { pos = [side * CAMPO.SUPERVISOR[0], CAMPO.SUPERVISOR[1]]; clip = 'Talking'; ry = side > 0 ? -.6 : .6; }
    else if (p.role === 'almacen') { pos = [side * CAMPO.STORE[0], CAMPO.STORE[1]]; clip = 'Idle'; ry = side > 0 ? -1.2 : 1.2; }
    else { const [x, z] = CAMPO.TECH[t++ % CAMPO.TECH.length]; pos = [side * x, z]; clip = p.paused ? 'Idle' : (t % 4 === 0 ? 'Talking' : 'Bartending'); ry = Math.PI; }
    out.push({key: p.key, pos, clip, ry, outside: !!p.outside, tag: campoTag(op, p)});
  }
  return out;
}
const ROLE_TITLE = {supervisor: 'Supervisor', almacen: 'Almacén', tecnico: 'Técnico'};
export function campoTag(op, p) {
  const who = p.label || ROLE_TITLE[p.role] || 'Técnico';
  return {cls: p.outside ? 'red' : p.paused ? 'pausa' : '', text: `${op.name} · ${who}`, small: p.outside ? '⚠ Fuera de perímetro' : p.paused ? 'En pausa' : ROLE_TITLE[p.role] || 'Técnico'};
}
export function opBoard(op) {
  const cut = op.cut ? `Corte de ${op.cut.kind} ${show(op.cut.at)} · ${op.cut.status === 'enviado' ? 'enviado al grupo ✓' : op.cut.status}` : `Último corte: ${NO}`;
  return {name: op.name, on: `${op.on} / ${show(op.scheduled)}`, missing: show(op.missing), outside: show(op.outside), cut};
}
export function repCampo(snap) {
  const ops = (snap && snap.ops) || []; const out = ops.reduce((a, o) => a + (o.outside || 0), 0);
  return `${show(snap && snap.on_shift)} en turno · ${ops.length ? out : NO} fuera de perímetro`;
}
