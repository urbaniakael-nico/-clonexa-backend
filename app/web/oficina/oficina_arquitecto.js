// Oficina 3D · MODO ARQUITECTO de los pisos aprobados (bar de Mixamo, taller, restaurante): solo en la consola
// (Admin V2), nunca en el visor del cliente. Arrastrar mesas, máquinas, cabina, pista o plantas sobre el piso, girarlas,
// guardar (PUT /pisos/{id}/distribucion) o "Acomodar automático" (DELETE). Al guardar, el piso se vuelve a abrir con
// las posiciones nuevas (puestos, sillas y rutas salen de ellas). Reglas puras al final (probadas en node).

// items: [{key, label, get() -> [x, z, giro], set(x, z, giro), pick: [Object3D], turn?: bool, done?()}]
export function attachArchitect(o, ctx) {
  const {THREE, C, R, ui, room, items, cid, getJson, api, esc} = ctx;
  if (!o.architect || !items.length) return {tick() {}, detach() {}, get on() { return false; }};
  const bar = ui.querySelector('.rbar');
  const btn = document.createElement('button'); btn.type = 'button'; btn.textContent = '🏗 Modo arquitecto'; btn.setAttribute('data-arch-toggle', '');
  bar.insertBefore(btn, bar.querySelector('.sp'));
  const panel = document.createElement('div'); panel.className = 'rarch glass hidden'; ui.appendChild(panel);
  panel.innerHTML = `<b>Modo arquitecto</b><span data-arch-say>Arrastra ${esc(items.map(i => i.label).filter((v, i, a) => a.indexOf(v) === i).join(', '))}.</span>
    <button type="button" data-arch-turn disabled>↻ Girar 90°</button><button type="button" class="pri" data-arch-save>Guardar</button>
    <button type="button" data-arch-auto>Acomodar automático</button><button type="button" data-arch-exit>Salir</button>`;
  const say = t => { panel.querySelector('[data-arch-say]').textContent = t; };
  const canvas = R.domElement, ray = new THREE.Raycaster(), mv = new THREE.Vector2(), plane = new THREE.Plane(new THREE.Vector3(0, 1, 0), 0), hit = new THREE.Vector3();
  const lim = limits(room);
  let on = false, sel = null, drag = null, dirty = false, helper = null;
  const toNdc = e => { const r = canvas.getBoundingClientRect(); mv.set((e.clientX - r.left) / r.width * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1); ray.setFromCamera(mv, C); };
  function pickAt(e) {
    toNdc(e);
    const all = []; items.forEach(it => it.pick.forEach(p => { p.userData.__arch = it; all.push(p); }));
    const h = ray.intersectObjects(all, true)[0]; if (!h) return null;
    let k = h.object; while (k && !k.userData.__arch) k = k.parent; return k ? k.userData.__arch : null;
  }
  function select(it) {
    sel = it; panel.querySelector('[data-arch-turn]').disabled = !(it && it.turn);
    if (helper) { helper.parent && helper.parent.remove(helper); helper = null; }
    if (it) { helper = new THREE.BoxHelper(it.pick[0], 0xfbbf24); ctx.S.add(helper); say(`${it.label} · ${it.key.replace(/^\w+:/, '')}: arrastra para mover`); }
  }
  function down(e) {
    if (!on || e.button > 0) return;
    const it = pickAt(e); if (!it) return;
    e.stopImmediatePropagation(); e.preventDefault(); select(it);
    if (!ray.ray.intersectPlane(plane, hit)) return;
    const [x, z] = it.get(); drag = {it, dx: x - hit.x, dz: z - hit.z, id: e.pointerId};
    try { canvas.setPointerCapture(e.pointerId); } catch (_) { /* sin captura */ }
  }
  function move(e) {
    if (!drag || e.pointerId !== drag.id) return;
    e.stopImmediatePropagation(); toNdc(e); if (!ray.ray.intersectPlane(plane, hit)) return;
    const [, , r] = drag.it.get(); const [x, z] = clampXZ(hit.x + drag.dx, hit.z + drag.dz, lim);
    drag.it.set(x, z, r); dirty = true; R.shadowMap.needsUpdate = true;
  }
  function up(e) {
    if (!drag || e.pointerId !== drag.id) return;
    e.stopImmediatePropagation(); const it = drag.it; drag = null; if (it.done) it.done(); R.shadowMap.needsUpdate = true;
  }
  canvas.addEventListener('pointerdown', down, true); canvas.addEventListener('pointermove', move, true); canvas.addEventListener('pointerup', up, true);
  function setOn(v) { on = v; panel.classList.toggle('hidden', !on); btn.classList.toggle('pri', on); if (!on) select(null); document.body.classList.toggle('arch-on', on); }
  btn.onclick = () => setOn(!on);
  panel.querySelector('[data-arch-exit]').onclick = () => { if (dirty && !confirmLeave()) return; setOn(false); if (dirty) o.onReload && o.onReload(); };
  panel.querySelector('[data-arch-turn]').onclick = () => { if (!sel || !sel.turn) return; const [x, z, r] = sel.get(); sel.set(x, z, turn90(r)); if (sel.done) sel.done(); dirty = true; R.shadowMap.needsUpdate = true; };
  panel.querySelector('[data-arch-save]').onclick = async () => {
    say('Guardando…');
    try { await getJson(`${api}/pisos/${cid}/distribucion`, {method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(layoutBody(items))});
      dirty = false; say('Guardado ✓'); o.onReload && o.onReload(); }
    catch (err) { say('No se pudo guardar: ' + (err.message || '')); }
  };
  panel.querySelector('[data-arch-auto]').onclick = async () => {
    say('Acomodando…');
    try { await getJson(`${api}/pisos/${cid}/distribucion`, {method: 'DELETE'}); dirty = false; o.onReload && o.onReload(); }
    catch (err) { say('No se pudo acomodar: ' + (err.message || '')); }
  };
  function confirmLeave() { say('Hay cambios sin guardar: pulsa Guardar o vuelve a pulsar Salir para descartarlos.'); const was = panel.dataset.warned === '1'; panel.dataset.warned = '1'; return was; }
  if (o.architectOpen) setOn(true);
  return {tick() { if (helper && sel) helper.update(); }, get on() { return on; },
    detach() { canvas.removeEventListener('pointerdown', down, true); canvas.removeEventListener('pointermove', move, true); canvas.removeEventListener('pointerup', up, true);
      if (helper && helper.parent) helper.parent.remove(helper); document.body.classList.remove('arch-on'); }};
}

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
