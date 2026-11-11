// Oficina 3D · fase 1.5 · reglas puras del piso realista (sin three: se prueban en tests/oficina_real.test.cjs).
// El motor (oficina_real.js) solo dibuja lo que estas reglas deciden.

export const LIVE_MS = 7000;             // copia viva: cada 7 s (entre 5 y 10), pausa si la pestaña no se ve
export const ANIMS = ['quieto', 'caminar', 'sentarse', 'sentado_hablando', 'teclear', 'servir', 'preparar_trago', 'mezclar',
  'brindar', 'bailar', 'cafe', 'telefono'];
export const FADE = 0.35;                // segundos de transición suave (crossfade) entre animaciones

// Nombres de las animaciones de Quaternius (Universal Animation Library, CC0) que sirven para cada estado.
// La primera que exista en el archivo gana; si no hay ninguna, el personaje usa la animación propia (en código).
export const UAL_CLIPS = {
  quieto: [/^idle(_loop)?$/i, /idle/i],
  caminar: [/^walk(_loop)?$/i, /walk/i],
  sentarse: [/sit(ting)?_?(enter|down)/i, /^sit/i],
  sentado_hablando: [/sit(ting)?_?talk/i, /sit(ting)?_?idle/i, /sitting/i],
  teclear: [/typ(e|ing)/i, /keyboard/i, /^interact$/i],
  servir: [/(carry|tray|hold)/i, /walk_formal/i],
  preparar_trago: [/(mix|pour|shake)/i, /^interact$/i],
  mezclar: [/(dj|scratch)/i, /^interact$/i],
  brindar: [/(toast|cheer|drink)/i, /sitting_talk/i],   // sentado: nunca cae a una animación de pie
  bailar: [/danc/i],
  cafe: [/(coffee|sip)/i, /idle_talk/i],
  telefono: [/(phone|call)/i, /idle_talk/i],
};

export function pickClip(names, state) {
  for (const re of UAL_CLIPS[state] || []) {
    const hit = (names || []).find(n => re.test(n));
    if (hit) return hit;
  }
  return null;
}

// Cuántos clientes llegan a una mesa: los que Clonexa tenga registrados; si no, 2 a 4 (siempre los mismos por mesa).
export function guestsFor(table) {
  if (table && Number.isFinite(table.guests) && table.guests > 0) return Math.min(6, table.guests);
  let h = 0;
  for (const ch of String((table && table.label) || '')) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return 2 + (h % 3);
}

// Lo que cambió entre dos copias vivas -> eventos para animar (la primera copia no anima: solo acomoda).
export function diffLive(prev, next) {
  const ev = [];
  if (!next || !next.ok) return ev;
  const first = !prev;
  const P = prev || {tables: [], orders: [], songs: [], staff: {people: []}, game: null};
  const pt = new Map((P.tables || []).map(t => [t.label, t]));
  for (const t of next.tables || []) {
    const was = pt.get(t.label);
    if (!was && first) { if (t.open) ev.push({type: 'mesa_abierta', table: t.label, guests: guestsFor(t), instant: true}); continue; }
    if (t.open && !(was && was.open)) ev.push({type: 'mesa_abierta', table: t.label, guests: guestsFor(t), instant: first});
    if (!t.open && was && was.open) ev.push({type: 'mesa_cerrada', table: t.label});
  }
  const po = new Map((P.orders || []).map(o => [o.id, o]));
  for (const o of next.orders || []) {
    const was = po.get(o.id);
    if (!was) ev.push({type: o.state === 'entregado' ? 'pedido_entregado' : 'pedido_nuevo', order: o.id, table: o.table, items: o.items, instant: first});
    else if (o.state === 'entregado' && was.state !== 'entregado') ev.push({type: 'pedido_entregado', order: o.id, table: o.table, items: o.items});
    else if (o.state === 'preparando' && was.state === 'nuevo') ev.push({type: 'pedido_preparando', order: o.id, table: o.table, items: o.items});
  }
  const ids = new Set((next.orders || []).map(o => o.id));
  for (const o of P.orders || []) if (!ids.has(o.id)) ev.push({type: 'pedido_fuera', order: o.id, table: o.table});
  const ps = new Set((P.songs || []).map(s => s.id));
  const newSongs = (next.songs || []).filter(s => !ps.has(s.id));
  if (newSongs.length && !first) ev.push({type: 'cancion', title: newSongs[0].title});
  if (first && (next.songs || []).length) ev.push({type: 'cancion', title: next.songs[0].title, instant: true});
  const pg = P.game ? P.game.kind + ':' + P.game.state : '';
  const ng = next.game ? next.game.kind + ':' + next.game.state : '';
  if (ng !== pg || first) ev.push(next.game ? {type: 'juego', kind: next.game.kind, label: next.game.label, state: next.game.state} : {type: 'juego_fin'});
  const pp = new Map(((P.staff || {}).people || []).map(p => [p.key, p]));
  const np = new Map(((next.staff || {}).people || []).map(p => [p.key, p]));
  for (const [k, p] of np) {
    const was = pp.get(k);
    if (!was) ev.push({type: 'turno_inicio', key: k, uniform: p.uniform, paused: p.paused, instant: first});
    else if (p.paused && !was.paused) ev.push({type: 'pausa', key: k});
    else if (!p.paused && was.paused) ev.push({type: 'retoma', key: k});
  }
  for (const k of pp.keys()) if (!np.has(k)) ev.push({type: 'turno_fin', key: k});
  return ev;
}

// Evento -> quién se mueve y con qué animación (lo que se ve en el piso).
export function animationFor(e) {
  switch (e.type) {
    case 'mesa_abierta': return {who: 'clientes', path: 'entrada→mesa', anims: ['caminar', 'sentarse', 'sentado_hablando']};
    case 'mesa_cerrada': return {who: 'clientes', path: 'mesa→entrada', anims: ['quieto', 'caminar'], bubble: '👋'};
    case 'pedido_nuevo': return {who: 'barman', anims: ['preparar_trago'], bubble: `🧾 ${e.items} ${e.items === 1 ? 'producto' : 'productos'}`, at: 'mesa'};
    case 'pedido_preparando': return {who: 'barman', anims: ['preparar_trago']};
    case 'pedido_entregado': return {who: 'mesero', path: 'barra→mesa→barra', anims: ['servir', 'caminar', 'quieto'], then: {who: 'clientes', anims: ['brindar', 'sentado_hablando']}};
    case 'cancion': return {who: 'dj', anims: ['mezclar'], bubble: `♪ ${e.title}`};
    case 'juego': return {who: 'pantalla', screen: e.kind};
    case 'juego_fin': return {who: 'pantalla', screen: 'marca'};
    case 'turno_inicio': return {who: 'personal', path: 'entrada→puesto', anims: ['caminar', e.paused ? 'cafe' : 'quieto']};
    case 'pausa': return {who: 'personal', path: 'puesto→personal', anims: ['caminar', 'cafe']};
    case 'retoma': return {who: 'personal', path: 'personal→puesto', anims: ['caminar', 'quieto']};
    case 'turno_fin': return {who: 'personal', path: 'puesto→entrada', anims: ['caminar']};
    default: return null;
  }
}

// Animación de trabajo de cada cargo cuando está en su puesto.
export function workAnim(uniform, paused) {
  if (paused) return 'cafe';
  return {barman: 'preparar_trago', dj: 'mezclar', caja: 'teclear', mesero: 'quieto', cocina: 'preparar_trago'}[uniform] || 'quieto';
}

// Cámara casa de muñecas: qué paredes se ocultan según de dónde mira la cámara (la del frente siempre).
// az = 0 mira desde el frente (z positivo). Una pared lateral se oculta si la cámara está de su lado.
export function hiddenWalls(az) {
  const s = Math.sin(az);
  const out = ['frente'];
  if (s > 0.35) out.push('derecha');
  if (s < -0.35) out.push('izquierda');
  if (Math.cos(az) < -0.2) out.push('fondo');
  return out;
}

// Límites de la cámara para no atravesar paredes: el centro queda dentro del salón y la cámara afuera, del lado abierto.
export function clampCamera(cam, room) {
  const W = room.W, D = room.D;
  const out = Object.assign({}, cam);
  out.az = Math.max(-1.15, Math.min(1.15, cam.az));
  out.pol = Math.max(0.42, Math.min(1.22, cam.pol));
  const maxD = Math.max(W, D) * 1.55;
  out.dist = Math.max(6, Math.min(maxD, cam.dist));
  out.tx = Math.max(-W / 2 + 1, Math.min(W / 2 - 1, cam.tx || 0));
  out.tz = Math.max(-D / 2 + 1, Math.min(D / 2 - 1, cam.tz || 0));
  return out;
}

// La distancia que llena la pantalla con el piso (según el ancho visible y el campo de visión).
export function fitDistance(room, fovDeg, aspect) {
  const half = (fovDeg * Math.PI / 180) / 2;
  const byH = (room.D * 0.75) / Math.tan(half);
  const byW = (room.W * 0.62) / (Math.tan(half) * Math.max(0.4, aspect));
  return Math.max(byH, byW);
}

// Texto corto del representante (solo actividad, nunca dinero).
export function repSummary(snap) {
  if (!snap || !snap.ok) return 'Sin datos de la copia viva.';
  const k = Object.fromEntries((snap.kpis || []).map(([a, b]) => [a, b]));
  const open = (snap.tables || []).filter(t => t.open).length;
  const bits = [`${open} ${open === 1 ? 'mesa abierta' : 'mesas abiertas'}`, `${k['Pedidos a barra'] ?? '—'} pedidos a barra`,
    `${k['Canciones pedidas'] ?? '—'} canciones`, `${k['Personal en turno'] ?? '—'} en turno`];
  const lead = snap.business && !snap.business.open ? (snap.business.activity_off_hours ? 'Fuera de horario pero con movimiento: ' : 'Cerrado por ahora. ') : 'Hoy va así: ';
  return lead + bits.join(' · ') + (snap.game ? ` · 🎮 ${snap.game.label} en pantalla` : '');
}

// Lo que dice la pantalla grande.
export function screenLines(snap) {
  if (snap && snap.game) return [snap.game.label, snap.game.state === 'playing' ? 'jugando ahora' : 'inscripciones abiertas'];
  const s = snap && snap.songs && snap.songs[0];
  return s ? ['♪ Sonando', s.title] : ['', ''];
}

// Modo arquitecto: lo que se manda a guardar (solo posiciones, redondeadas).
export function layoutBody(items) {
  const out = {};
  for (const [k, v] of Object.entries(items || {})) out[k] = [Math.round(v[0] * 100) / 100, Math.round(v[1] * 100) / 100, Math.round(v[2] * 1000) / 1000];
  return {items: out};
}

// Ruta simple por los pasillos: primero al pasillo central (z del pasillo), luego en x y luego en z.
export function aislePath(from, to, aisleZ) {
  return [[from[0], aisleZ], [to[0], aisleZ], [to[0], to[1]]];
}
