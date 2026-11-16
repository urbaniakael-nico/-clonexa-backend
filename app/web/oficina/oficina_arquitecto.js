// Oficina 3D · MODO ARQUITECTO: reemplazado por el Modo constructor (fase 1). El botón del piso abre el constructor de
// la empresa; las posiciones guardadas antes (distribucion.piso / distribucion.items) se siguen respetando en los pisos
// sin plano y el constructor las usa para el primer borrador. Reglas puras al final (probadas en node).

// items: [{key, label, get() -> [x, z, giro], set(x, z, giro), pick: [Object3D], turn?: bool, done?()}]
export function attachArchitect(o, ctx) {
  // Desde el Modo constructor (fase 1) "Editar distribución" ya no arrastra objetos aquí: abre el constructor de la
  // empresa (plano 2D a escala + vista 3D), que parte de lo que ya estaba guardado con el modo arquitecto.
  const {ui, cid, esc} = ctx;
  if (!o.architect || !cid || !ui) return {tick() {}, detach() {}, get on() { return false; }};
  const bar = ui.querySelector('.rbar');
  const a = document.createElement('a'); a.className = 'rbtn'; a.href = constructorUrl(cid); a.target = '_blank'; a.rel = 'noopener';
  a.textContent = '🏗 Modo constructor'; a.setAttribute('data-arch-toggle', ''); a.title = esc('Editar distribución en el Modo constructor');
  if (bar) bar.insertBefore(a, bar.querySelector('.sp'));
  if (o.architectOpen) { try { window.open(a.href, '_blank', 'noopener'); } catch (e) { /* bloqueado: queda el botón */ } }
  return {tick() {}, get on() { return false; }, detach() { a.remove(); }};
}
export function constructorUrl(cid) { return '/admin-v2plus/biblioteca3d/constructor?empresa=' + encodeURIComponent(cid); }

// ------------------------------------------------------------------ reglas puras
export function limits(room) { return {x: room.W / 2 - 0.6, z: room.D / 2 - 0.6}; }
export function clampXZ(x, z, lim) { return [Math.max(-lim.x, Math.min(lim.x, x)), Math.max(-lim.z, Math.min(lim.z, z))]; }
export function turn90(r) { const t = (Number(r) || 0) + Math.PI / 2; return Math.atan2(Math.sin(t), Math.cos(t)); }
export function layoutBody(items) {
  const out = {};
  for (const it of items) { const [x, z, r] = it.get(); out[it.key] = [Math.round(x * 100) / 100, Math.round(z * 100) / 100, Math.round((r || 0) * 1000) / 1000]; }
  return {items: out};
}
// Posición guardada de un objeto (arch = snap.arch) o la de la escena aprobada.
export function savedPos(arch, key, def) {
  const v = arch && arch[key];
  if (Array.isArray(v) && v.length === 3 && v.every(n => Number.isFinite(Number(n)))) return v.map(Number);
  return [def[0], def[1], def[2] || 0];
}
// Un punto pegado a un objeto que se movió/giró: base del objeto aprobado -> posición nueva.
export function follow(point, from, to) {
  const dx = point[0] - from[0], dz = point[1] - from[1], a = (to[2] || 0) - (from[2] || 0);
  const c = Math.cos(a), s = Math.sin(a);
  return [to[0] + dx * c + dz * s, to[1] - dx * s + dz * c];
}
