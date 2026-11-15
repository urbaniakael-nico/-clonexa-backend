// Modo constructor · REGLAS PURAS del editor (sin DOM ni three; probadas en tests/constructor.test.cjs). Las mismas
// reglas de avisos que el servidor (app/services/constructor_plano.py: warnings) para que lo que se ve en el plano
// sea lo que guarda la base.
export const STEP = 0.1;
export const DOORS = ['puerta', 'puerta_doble', 'puerta_vidrio', 'corrediza', 'cortina_metalica', 'vaiven'];
export const round = (v, n = 2) => Math.round(v * 10 ** n) / 10 ** n;
// Ajuste a 10 cm (Alt = libre, 1 mm).
export function snap(v, free = false, step = STEP) { return free ? round(v, 3) : round(Math.round(v / step) * step, 2); }
export const clone = x => JSON.parse(JSON.stringify(x));
export function norm(s) { return String(s || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().trim(); }

// ------------------------------------------------------------------ deshacer / rehacer
export class History {
  constructor(limit = 120) { this.limit = limit; this.past = []; this.future = []; }
  push(state) { this.past.push(JSON.stringify(state)); if (this.past.length > this.limit) this.past.shift(); this.future = []; }
  undo(cur) { if (!this.past.length) return null; this.future.push(JSON.stringify(cur)); return JSON.parse(this.past.pop()); }
  redo(cur) { if (!this.future.length) return null; this.past.push(JSON.stringify(cur)); return JSON.parse(this.future.pop()); }
  get canUndo() { return this.past.length > 0; }
  get canRedo() { return this.future.length > 0; }
}

// ------------------------------------------------------------------ ids y objetos
export function nextId(plan, prefix) {
  const used = new Set([...(plan.objetos || []), ...(plan.paredes || []), ...(plan.aberturas || []), ...(plan.pisos || []), ...(plan.zonas || [])].map(x => x.id));
  let i = 1; while (used.has(prefix + i)) i++; return prefix + i;
}
export function addObject(plan, item, x, z, extra = {}) {
  const o = {id: nextId(plan, 'o'), asset: item.id, x: round(x), z: round(z), rot: 0, escala: 1, color: null, variante: null,
    capa: item.capa || 'muebles', conexion: null, texto: item.forma === 'neon' ? 'Abierto' : null, ...extra};
  plan.objetos.push(o); return o;
}
export function duplicate(plan, ids, dx = .5, dz = .5) {
  const out = [];
  for (const id of ids) { const o = plan.objetos.find(x => x.id === id); if (!o) continue;
    const c = {...clone(o), id: nextId(plan, 'o'), x: round(o.x + dx), z: round(o.z + dz), conexion: null}; plan.objetos.push(c); out.push(c.id); }
  return out;
}
export function remove(plan, ids) {
  const set = new Set(ids);
  plan.objetos = plan.objetos.filter(o => !set.has(o.id));
  plan.aberturas = plan.aberturas.filter(a => !set.has(a.id) && !set.has(a.pared));
  plan.paredes = plan.paredes.filter(w => !set.has(w.id));
  plan.pisos = plan.pisos.filter(f => !set.has(f.id));
  plan.zonas = plan.zonas.filter(z => !set.has(z.id));
}
export function rotate(plan, ids, deg) { for (const o of plan.objetos) if (ids.includes(o.id)) o.rot = ((round(o.rot + deg, 1) % 360) + 360) % 360; }
export function moveBy(plan, ids, dx, dz) { for (const o of plan.objetos) if (ids.includes(o.id)) { o.x = round(o.x + dx, 3); o.z = round(o.z + dz, 3); } }
// Alinear selección: left|right|centerx|top|bottom|centerz|spreadx|spreadz
export function align(plan, ids, how) {
  const L = plan.objetos.filter(o => ids.includes(o.id)); if (L.length < 2) return;
  const xs = L.map(o => o.x), zs = L.map(o => o.z);
  if (how === 'left') L.forEach(o => { o.x = Math.min(...xs); });
  else if (how === 'right') L.forEach(o => { o.x = Math.max(...xs); });
  else if (how === 'centerx') { const c = round(xs.reduce((a, b) => a + b, 0) / L.length); L.forEach(o => { o.x = c; }); }
  else if (how === 'top') L.forEach(o => { o.z = Math.min(...zs); });
  else if (how === 'bottom') L.forEach(o => { o.z = Math.max(...zs); });
  else if (how === 'centerz') { const c = round(zs.reduce((a, b) => a + b, 0) / L.length); L.forEach(o => { o.z = c; }); }
  else if (how === 'spreadx' || how === 'spreadz') { const k = how === 'spreadx' ? 'x' : 'z'; L.sort((a, b) => a[k] - b[k]); const a = L[0][k], b = L[L.length - 1][k];
    L.forEach((o, i) => { o[k] = round(a + (b - a) * i / (L.length - 1)); }); }
}

// ------------------------------------------------------------------ geometría y avisos (misma regla que el servidor)
export function footprint(o, sizes) { const s = sizes[o.asset] || {w: .6, d: .6}; const k = Number(o.escala) || 1; return [(s.w || .6) * k, (s.d || .6) * k]; }
export function corners(o, sizes) {
  const [w, d] = footprint(o, sizes); const a = (o.rot || 0) * Math.PI / 180, c = Math.cos(a), s = Math.sin(a);
  return [[-w / 2, -d / 2], [w / 2, -d / 2], [w / 2, d / 2], [-w / 2, d / 2]].map(([dx, dz]) => [o.x + dx * c - dz * s, o.z + dx * s + dz * c]);
}
export function overlap(a, b) {
  for (const poly of [a, b]) for (let i = 0; i < 4; i++) {
    const [x1, z1] = poly[i], [x2, z2] = poly[(i + 1) % 4]; const nx = z2 - z1, nz = x1 - x2;
    const pa = a.map(([x, z]) => nx * x + nz * z), pb = b.map(([x, z]) => nx * x + nz * z);
    if (Math.max(...pa) <= Math.min(...pb) + 1e-6 || Math.max(...pb) <= Math.min(...pa) + 1e-6) return false;
  }
  return true;
}
export function wallLen(w) { return Math.hypot(w.x2 - w.x1, w.z2 - w.z1); }
export function doorBox(plan, op, depth = .9) {
  const w = plan.paredes.find(x => x.id === op.pared); if (!w || !DOORS.includes(op.tipo)) return null;
  const L = wallLen(w) || 1, ux = (w.x2 - w.x1) / L, uz = (w.z2 - w.z1) / L, cx = w.x1 + ux * op.pos, cz = w.z1 + uz * op.pos, hw = op.ancho / 2, nx = -uz, nz = ux;
  return [[cx - ux * hw - nx * depth, cz - uz * hw - nz * depth], [cx + ux * hw - nx * depth, cz + uz * hw - nz * depth], [cx + ux * hw + nx * depth, cz + uz * hw + nz * depth], [cx - ux * hw + nx * depth, cz - uz * hw + nz * depth]];
}
export function warnings(plan, sizes, entities) {
  const solid = plan.objetos.filter(o => (o.capa || 'muebles') === 'muebles');
  const box = new Map(solid.map(o => [o.id, corners(o, sizes)]));
  const cruces = [], puertas = [];
  for (let i = 0; i < solid.length; i++) for (let j = i + 1; j < solid.length; j++) if (overlap(box.get(solid[i].id), box.get(solid[j].id))) cruces.push([solid[i].id, solid[j].id]);
  for (const op of plan.aberturas) { const b = doorBox(plan, op); if (b) for (const o of solid) if (overlap(box.get(o.id), b)) puertas.push([o.id, op.id]); }
  const sin_conectar = plan.objetos.filter(o => (sizes[o.asset] || {}).conectable && !o.conexion).map(o => o.id);
  const linked = new Set(plan.objetos.filter(o => o.conexion).map(o => o.conexion.tipo + ':' + o.conexion.id));
  const mesas_sin_objeto = ((entities || {}).mesa || []).filter(e => !linked.has('mesa:' + e.id)).map(e => e.label);
  return {cruces: cruces.slice(0, 50), puertas: puertas.slice(0, 50), sin_conectar, mesas_sin_objeto};
}
export function hitObject(plan, x, z, sizes) {
  const order = ['techo', 'pared', 'decoracion', 'muebles', 'piso'];
  const L = plan.objetos.slice().sort((a, b) => order.indexOf(a.capa) - order.indexOf(b.capa));
  return (L.find(o => inPoly([x, z], corners(o, sizes))) || {}).id || null;
}
export function inPoly([x, z], pts) {
  let ins = false;
  for (let i = 0, j = pts.length - 1; i < pts.length; j = i++) { const [xi, zi] = pts[i], [xj, zj] = pts[j]; if ((zi > z) !== (zj > z) && x < (xj - xi) * (z - zi) / (zj - zi) + xi) ins = !ins; }
  return ins;
}
// Pared más cercana a un punto: {wall, pos (m desde su inicio), dist}
export function nearestWall(plan, x, z) {
  let best = null;
  for (const w of plan.paredes) { const L = wallLen(w); if (!L) continue; const ux = (w.x2 - w.x1) / L, uz = (w.z2 - w.z1) / L;
    const t = Math.max(0, Math.min(L, (x - w.x1) * ux + (z - w.z1) * uz)); const px = w.x1 + ux * t, pz = w.z1 + uz * t; const d = Math.hypot(x - px, z - pz);
    if (!best || d < best.dist) best = {wall: w, pos: round(t), dist: d}; }
  return best;
}
// Puerta/ventana pegada a la pared: se centra dentro de la pared.
export function addOpening(plan, x, z, tipo, size, maxDist = .8) {
  const nw = nearestWall(plan, x, z); if (!nw || nw.dist > maxDist) return null;
  const [ancho, alto, base] = size; const L = wallLen(nw.wall); if (L < ancho + .1) return null;
  const pos = Math.max(ancho / 2, Math.min(L - ancho / 2, snap(nw.pos)));
  const a = {id: nextId(plan, 'a'), pared: nw.wall.id, tipo, pos: round(pos), ancho, alto, base: DOORS.includes(tipo) ? 0 : base};
  plan.aberturas.push(a); return a;
}
export function addWall(plan, x1, z1, x2, z2, look = {}) {
  if (Math.hypot(x2 - x1, z2 - z1) < .1) return null;
  const w = {id: nextId(plan, 'w'), x1, z1, x2, z2, grosor: look.grosor || .15, alto: look.alto || plan.sala.alto, color: look.color || '#d8cfc4', material: look.material || 'pintura'};
  plan.paredes.push(w); return w;
}
export function addFloor(plan, x1, z1, x2, z2, material, color) {
  const [a, b] = [Math.min(x1, x2), Math.max(x1, x2)], [c, d] = [Math.min(z1, z2), Math.max(z1, z2)]; if (b - a < .2 || d - c < .2) return null;
  const f = {id: nextId(plan, 'p'), zona: null, puntos: [[a, c], [b, c], [b, d], [a, d]], material, color}; plan.pisos.push(f); return f;
}
export function addZone(plan, x1, z1, x2, z2, tipo, nombre) {
  const [a, b] = [Math.min(x1, x2), Math.max(x1, x2)], [c, d] = [Math.min(z1, z2), Math.max(z1, z2)]; if (b - a < .3 || d - c < .3) return null;
  const zn = {id: nextId(plan, 'z'), nombre, tipo, puntos: [[a, c], [b, c], [b, d], [a, d]]}; plan.zonas.push(zn); return zn;
}

// ------------------------------------------------------------------ conexiones (una entidad real -> un solo objeto)
export function usedBy(plan, tipo, id) { const o = plan.objetos.find(x => x.conexion && x.conexion.tipo === tipo && x.conexion.id === id); return o ? o.id : null; }
export function connect(plan, objId, tipo, id) {
  const o = plan.objetos.find(x => x.id === objId); if (!o) return {ok: false, msg: 'Objeto no encontrado.'};
  if (id == null) { o.conexion = null; return {ok: true}; }
  const other = usedBy(plan, tipo, id);
  if (other && other !== objId) return {ok: false, msg: `Ya está conectada a otro objeto (${other}).`};
  o.conexion = {tipo, id}; return {ok: true};
}
export function freeEntities(plan, entities, tipo, objId) {
  return ((entities || {})[tipo] || []).filter(e => { const u = usedBy(plan, tipo, e.id); return !u || u === objId; });
}
export function label(entities, con) {
  if (!con) return ''; const e = ((entities || {})[con.tipo] || []).find(x => x.id === con.id); return e ? e.label : con.id;
}
// Número corto que se dibuja sobre la mesa conectada ("Mesa 4" -> "4").
export function badge(con) { if (!con || con.tipo !== 'mesa') return ''; const m = String(con.id).match(/(\d+)\s*$/); return m ? m[1] : String(con.id).slice(0, 3); }

// ------------------------------------------------------------------ catálogo
export function filterCatalog(items, {zone = '', q = '', category = ''} = {}) {
  const w = norm(q).split(/\s+/).filter(Boolean);
  return items.filter(it => (!zone || (it.zonas || []).includes(zone)) && (!category || it.categoria === category)
    && w.every(t => norm(`${it.nombre} ${it.categoria} ${(it.zonas || []).join(' ')}`).includes(t)));
}
export function sizesOf(items) { const out = {}; for (const it of items) out[it.id] = {...(it.medidas || {}), conectable: it.conectable || null, forma: it.forma}; return out; }
export function swatches(item, brand) {
  const b = brand || {}; const out = [...(item && item.variantes || [])];
  for (const c of [b.primary, b.secondary, b.accent, b.background, b.text]) if (/^#[0-9a-f]{6}$/i.test(c || '') && !out.includes(c.toLowerCase())) out.push(c.toLowerCase());
  return out.slice(0, 10);
}

// ------------------------------------------------------------------ vista 2D (metros <-> pixeles)
export function fit(sala, w, h, pad = 40) { const k = Math.min((w - pad * 2) / sala.ancho, (h - pad * 2) / sala.fondo); return {k, ox: (w - sala.ancho * k) / 2, oz: (h - sala.fondo * k) / 2}; }
export function toPx(v, x, z) { return [v.ox + x * v.k, v.oz + z * v.k]; }
export function toM(v, px, pz) { return [(px - v.ox) / v.k, (pz - v.oz) / v.k]; }
export function fmtM(v) { return `${round(v, 1).toFixed(1).replace('.', ',')} m`; }
export function statusText(st) { return st.saving ? 'Guardando…' : st.error ? `Sin guardar · ${st.error}` : `Versión ${st.version} · guardado`; }
