// Oficina 3D y "Negocio en vivo 3D" · piso dibujado por el PLANO PUBLICADO de la Biblioteca 3D. Usa la MISMA función que
// el editor (b3d/room.js buildRoom + b3d/char.js buildCharacter), en el estilo de la empresa (Humano o Caricatura), sobre
// el motor común de los pisos (oficina_mixamo.openFloor: renderer, cámara, gestos, etiquetas, copia viva cada 7 s).
// Los objetos CONECTADOS se mueven con los datos reales: mesa con QR (bombillo + clientes sentados), puesto/máquina con su
// operaria, escritorio con su agente, caja con quien cobra, nevera con el inventario y pantallas con su contenido real.
// Las personas del plano aparecen cuando abren turno; su animación sale del dato real (en pausa -> sentada, en su puesto
// -> trabajando). Sin nombres en el plano: cada persona va por su huella (la misma de la copia viva).
import {openFloor, THREE, P, API, esc} from '/admin-v2plus/oficina/mixamo.js';
import {Style} from '/admin-v2plus/oficina/b3d/core.js';
import {buildRoom} from '/admin-v2plus/oficina/b3d/room.js';
import {byId, registerModels} from '/admin-v2plus/oficina/b3d/catalog.js';
import {buildCharacter, tickCharacter, setAssetBase, defaultToon, defaultHuman} from '/admin-v2plus/oficina/b3d/char.js';

// ===== reglas puras (tests/plano_motor.test.cjs) =====
export function cameraFor(room) {   // la misma vista inicial del editor (fitView)
  const m = Math.max(room.w, room.d);
  return {pos: [room.w * .15, m * .82, room.d * 1.0 + 2], look: [0, 0, -.3], fov: 45};
}
export function connKind(conn) { const m = /^([a-z]+):/.exec(conn || ''); return m ? m[1] : ''; }
export function connId(conn) { return String(conn || '').replace(/^[a-z]+:/, ''); }
const rad = deg => (Number(deg) || 0) * Math.PI / 180;
function local(o, dx, dz) { const r = rad(o.rot), c = Math.cos(r), s = Math.sin(r); return [o.x + dx * c + dz * s, o.z - dx * s + dz * c]; }
// Puesto de la persona en un objeto conectado (coordenadas del plano = de la escena).
export function seatOf(o, def, kind) {
  const d = (def && def.d) || .7;
  const off = kind === 'caja' ? [0, -d / 2 - .45] : kind === 'puesto' ? [0, d / 2 + .35] : [0, d / 2 + .3];
  const [x, z] = local(o, off[0], off[1]);
  return [x, z, rad(o.rot) + (kind === 'caja' ? 0 : Math.PI)];
}
// Asientos alrededor de una mesa conectada (según el modelo del catálogo).
export function tableSeats(o, def) {
  const id = o.item, w = ((def && def.w) || 1.6) / 2, d = ((def && def.d) || 1.6) / 2;
  const base = id === 'mesa_2' ? [[0, -d + .25, 0], [0, d - .25, Math.PI]]
    : id === 'mesa_alta' ? [[0, -.55, 0], [0, .55, Math.PI]]
    : id === 'mesa_larga' ? [[-.75, -d + .2, 0], [0, -d + .2, 0], [.75, -d + .2, 0], [-.75, d - .2, Math.PI], [0, d - .2, Math.PI], [.75, d - .2, Math.PI]]
    : [[0, -d + .2, 0], [0, d - .2, Math.PI], [-w + .2, 0, Math.PI / 2], [w - .2, 0, -Math.PI / 2]];
  return base.map(([a, b, r]) => { const [x, z] = local(o, a, b); return [x, z, r + rad(o.rot)]; });
}
// Animación desde el dato real: en pausa -> sentada; en su puesto/escritorio -> trabajando; si no, la del plano.
export function liveClip(planClip, paused, atStation) {
  if (paused) return 'sit';
  if (atStation) return 'work';
  return planClip || 'idle';
}
export function staffPeople(snap) {
  if (!snap) return [];
  if (Array.isArray(snap.people)) return snap.people.map(p => ({...p, uniform: p.uniform || 'taller', paused: p.status === 'paused'}));
  return ((snap.staff || {}).people || []).slice();
}
const SCREEN_KIND = {'Canciones pedidas': 'canciones', 'Comandas en cocina': 'comandas', 'Domicilios': 'domicilios', 'Tablero de producción': 'produccion', 'Logo de la empresa': 'logo'};
export function screenKind(o) {   // conectada: su dato real; si no, lo que se eligió en "¿Qué muestra la pantalla?" (Partido / TV = imagen fija)
  if (connKind(o.conn) === 'pantalla') return connId(o.conn);
  return SCREEN_KIND[o.screen || (o.item === 'tv_pedestal' ? 'Canciones pedidas' : o.item === 'tablero' ? 'Tablero de producción' : 'Partido / TV')] || null;
}
export function screenModel(kind, snap) {
  const s = snap || {};
  if (kind === 'canciones') return {title: 'Canciones pedidas', rows: (s.songs || []).slice(0, 5).map(x => x.title || x.label || String(x)), empty: 'Sin canciones pedidas'};
  if (kind === 'comandas') return {title: `Comandas en cocina · ${s.kitchen_count ?? (s.kitchen || []).length ?? 0}`, rows: (s.kitchen || []).slice(0, 5).map(k => `${k.label}${k.minutes != null ? ' · ' + k.minutes + ' min' : ''}`), empty: 'Sin comandas'};
  if (kind === 'domicilios') return {title: 'Domicilios', rows: (s.deliveries || []).slice(0, 5).map(d => `${d.label}${d.barrio ? ' · ' + d.barrio : ''}`), empty: 'Sin domicilios hoy'};
  if (kind === 'produccion') { const b = s.board || {}; return {title: b.lot ? `Lote ${b.lot}` : 'Producción', rows: [b.made != null ? `Hechas ${b.made}${b.meta ? ' de ' + b.meta : ''}` : 'Sin lote en proceso', `En turno ${b.on_shift ?? '—'} · pausa ${b.paused ?? '—'}`, b.hours ? `Horas ${b.hours}` : ''].filter(Boolean), empty: ''}; }
  if (kind === 'turno') { const pp = staffPeople(s); return {title: `Personal en turno · ${pp.length}`, rows: pp.slice(0, 6).map(p => p.label), empty: 'Nadie en turno'}; }
  return {title: '', rows: [], empty: '', logo: true};
}
// Nevera conectada: qué tan llena se ve (0..1) según el inventario real de esa categoría (productos sobre su mínimo).
export function inventoryLevel(snap, conn) {
  const inv = ((snap || {}).inventory || {})[connId(conn)];
  if (!inv || !inv.items) return 1;
  return Math.max(0, Math.min(1, (inv.items - inv.low) / inv.items));
}
// Personaje de una persona: el que se guardó en el editor (por su huella) sobre el personaje por defecto del prototipo.
export function lookFor(key, looks) {
  let h = 0; for (const ch of String(key || '')) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  const saved = (looks || {})[key] || {};
  return {toon: {...defaultToon(h % 97), ...(saved.toon || {})}, human: {...defaultHuman(h % 97), ...(saved.human || {})}};
}
// ===== fin reglas puras =====

const ROOT = new URL('./', import.meta.url).pathname;

export async function open(o) {
  const cid = o.floor.company_id;
  const pay = o.planPayload || await o.getJson(`${API}/pisos/${cid}/plano`);
  const plan0 = pay.plano, room = {W: plan0.room.w, D: plan0.room.d, WALL: plan0.room.h};
  const toon = (o.styleOverride || pay.estilo) === 'caricatura';
  Style.mode = toon ? 'toon' : 'human';
  setAssetBase(ROOT + 'bar');          // Mixamo del bucket privado: consola o ruta firmada del visor
  registerModels(pay.catalogo || []);
  return openFloor(o, {title: o.floor.name, room, camera: cameraFor(plan0.room), exposure: toon ? 1.05 : 1.0, bloom: [0, 0, 1], cls: 'plano' + (toon ? ' toon' : ''),
    bg: toon ? 0x2a1f3d : 0x07050a, liveUrl: o.liveUrl || `${API}/pisos/${cid}/vivo`, ownPeople: true, tableInfo: (snap, label) => P.tableInfo(snap, label),
    async build(A) {
      const {S, R} = A;
      S.environment = null;   // como el editor: solo las luces del plano
      let plan = plan0, looks = pay.looks || {}, G = null, key = null;
      const CHARS = new Set(), TABLES = new Map(), SPOTS = {puesto: new Map(), escritorio: new Map(), caja: []}, SCREENS = [], FRIDGES = [];
      const stats = {objects: 0, people: 0};
      const bulbOn = A.track(new THREE.MeshStandardMaterial({color: 0x000000, emissive: new THREE.Color('#4ade80'), emissiveIntensity: 2.5, toneMapped: false}));
      const bulbOff = A.track(new THREE.MeshStandardMaterial({color: 0x2a2a2a}));
      const sc0 = document.createElement('canvas'); sc0.width = sc0.height = 128;
      { const x = sc0.getContext('2d'); const g = x.createRadialGradient(64, 64, 0, 64, 64, 64); g.addColorStop(0, 'rgba(74,222,128,1)'); g.addColorStop(1, 'rgba(74,222,128,0)'); x.fillStyle = g; x.fillRect(0, 0, 128, 128); }
      const softM = A.track(new THREE.MeshBasicMaterial({map: A.track(new THREE.CanvasTexture(sc0)), transparent: true, opacity: .28, depthWrite: false, blending: THREE.AdditiveBlending}));

      async function character(look, clip, x, z, ry, phase = 0) {
        const g = await buildCharacter(look, Style.mode, clip); g.position.set(x, 0, z); g.rotation.y = ry || 0; g.userData.phase = phase;
        g.traverse(q => { if (q.isMesh) { q.castShadow = !A.lite(); q.userData.person = true; } }); S.add(g); CHARS.add(g); stats.people = CHARS.size; return g;
      }
      function drop(g) { if (!g) return; S.remove(g); CHARS.delete(g); stats.people = CHARS.size; }
      const groupOf = id => G && G.userData.objs.children.find(g => g.userData.objId === id);

      function buildPlan() {
        G = buildRoom(plan); S.add(G); key = G.children.find(x => x.isDirectionalLight) || null;
        G.traverse(x => { if (x.isMesh && x.userData.surface && x.userData.surface.type === 'floor') x.userData.ownCut = true; });
        stats.objects = (plan.objects || []).length;
        for (const ob of plan.objects || []) {
          const def = byId[ob.item]; if (!def) continue; const g = groupOf(ob.id); const kind = connKind(ob.conn);
          if ((def.props || []).includes('screen')) {
            const sk = screenKind(ob); const scr = g && [...g.children].reverse().find(x => x.isMesh && x.material && x.material.isMeshBasicMaterial && x.material.map && x.geometry.type === 'PlaneGeometry');
            if (sk && scr) { const cs = A.canvasScreen(1, 1, 1024, 576); scr.material = A.track(new THREE.MeshBasicMaterial({map: cs.texture, toneMapped: false})); SCREENS.push({cs, kind: sk, ob}); }
          }
          if (kind === 'mesa') {
            const label = connId(ob.conn); const t = new THREE.Group(); t.position.set(ob.x, 0, ob.z); S.add(t);
            const bulb = new THREE.Mesh(new THREE.SphereGeometry(.07, 10, 8), bulbOff); bulb.position.y = 2.45; t.add(bulb);
            const cord = new THREE.Mesh(new THREE.CylinderGeometry(.004, .004, .7, 4), bulbOff); cord.position.y = 2.85; t.add(cord);
            const soft = new THREE.Mesh(new THREE.CircleGeometry(1.2, 32), softM); soft.rotation.x = -Math.PI / 2; soft.position.y = .02; soft.visible = false; t.add(soft);
            const hit = new THREE.Mesh(new THREE.CylinderGeometry(.8, .8, 1, 10), A.hitM); hit.position.y = .5; hit.userData.table = label; t.add(hit); A.PICK.push(hit);
            t.traverse(x => { x.userData.ownCut = true; });
            TABLES.set(label, {ob, def, holder: t, bulb, soft, guests: [], tag: A.tag(A.at(ob.x, .8, ob.z), '', 'mesa off', .12, true)});
          } else if (kind === 'puesto' || kind === 'escritorio') SPOTS[kind].set(ob.conn, seatOf(ob, def, kind));
          else if (kind === 'caja') SPOTS.caja.push(seatOf(ob, def, 'caja'));
          else if (kind === 'inv' && g) { const bottles = []; g.traverse(x => { if (x.isMesh && x.geometry.type === 'CylinderGeometry' && x.geometry.parameters.radiusTop < .04) bottles.push(x); }); FRIDGES.push({ob, bottles}); }
        }
        R.shadowMap.needsUpdate = true;
      }
      function clear() {
        for (const T of TABLES.values()) { A.dropTag(T.tag); T.guests.splice(0).forEach(drop); S.remove(T.holder); }
        for (const s of STAFF.values()) { drop(s.g); A.dropTag(s.tag); }
        STAFF.clear(); TABLES.clear(); SPOTS.puesto.clear(); SPOTS.escritorio.clear(); SPOTS.caja.length = 0; SCREENS.length = 0; FRIDGES.length = 0;
        for (let i = A.PICK.length - 1; i >= 0; i--) if (A.PICK[i].userData.table) A.PICK.splice(i, 1);
        if (G) S.remove(G); G = null;
      }
      // ---------------------------------------------------------- personal en turno
      const STAFF = new Map();
      function staffSpot(p, idx, used) {
        const pp = (plan.people || []).find(x => x.pid === p.key);
        const desk = SPOTS.escritorio.get('emp:' + p.key);
        if (desk) return {spot: desk, clip: liveClip(pp && pp.clip, p.paused, true)};
        if (pp) return {spot: [pp.x, pp.z, rad(pp.rot)], clip: liveClip(pp.clip, p.paused, false)};
        if (!p.paused && (p.uniform === 'taller' || p.uniform === 'costura' || p.uniform === 'operaria' || p.uniform === 'cocina')) {
          const free = [...SPOTS.puesto.entries()].sort((a, b) => parseInt(connId(a[0])) - parseInt(connId(b[0]))).find(([k]) => !used.has(k));
          if (free) { used.add(free[0]); return {spot: free[1], clip: 'work'}; }
        }
        if (/caj/.test(p.uniform || '') && SPOTS.caja.length && !used.has('caja')) { used.add('caja'); return {spot: SPOTS.caja[0], clip: liveClip('idle', p.paused, false)}; }
        return {spot: [-room.W / 2 + 1.2 + (idx % 8) * .9, room.D / 2 - 1.1 - Math.floor(idx / 8) * .9, Math.PI], clip: liveClip('idle', p.paused, false)};
      }
      function drawScreen(scr, snap) {
        const m = screenModel(scr.kind, snap); const brand = (A.floor && A.floor.brand) || {};
        scr.cs.draw({m, n: A.floor && A.floor.name}, (x, w, h) => {
          x.fillStyle = toon ? '#1b1035' : '#0b0f1c'; x.fillRect(0, 0, w, h);
          if (m.logo) { x.fillStyle = (brand.colors && brand.colors.primary) || brand.primary || '#f20b6d'; x.font = 'italic 800 110px Georgia,serif'; x.textAlign = 'center'; x.fillText(A.clipText((A.floor && A.floor.name) || 'Clonexa', 18), w / 2, h / 2 + 36); return; }
          x.fillStyle = '#fff'; x.font = '800 54px Inter,sans-serif'; x.fillText(A.clipText(m.title, 30), 36, 80);
          if (!m.rows.length) { x.fillStyle = '#cbbfd6'; x.font = '500 40px Inter,sans-serif'; x.fillText(m.empty, 36, 180); return; }
          m.rows.forEach((r, i) => { x.fillStyle = 'rgba(255,255,255,.08)'; x.fillRect(30, 110 + i * 88, w - 60, 74); x.fillStyle = '#fff'; x.font = '600 40px Inter,sans-serif'; x.fillText(A.clipText(r, 40), 52, 160 + i * 88); });
        });
      }
      let lastSnap = null, gen = 0;
      function apply(snap) {
        lastSnap = snap; const my = gen;
        const tables = new Map((snap.tables || []).map(t => [t.label, t]));
        let open = 0;
        for (const [label, T] of TABLES) {
          const t = tables.get(label); const on = !!(t && t.open); if (on) open++;
          T.bulb.material = on ? bulbOn : bulbOff; T.soft.visible = on;
          const tt = P.tableTag(t || {label, open: false}); A.setTag(T.tag, `${tt.dot ? '<b class="dot">●</b> ' : ''}${esc(tt.text)}`, tt.cls);
          if (on && !T.guests.length) {
            const seats = tableSeats(T.ob, T.def); const n = Math.max(1, Math.min(seats.length, P.guestsFor(t)));
            T.guests.push(null);   // reservado mientras cargan
            Promise.all(seats.slice(0, n).map((s, i) => character(lookFor(label + ':' + i, {}), 'sit', s[0], s[1], s[2], i))).then(gs => {
              T.guests.splice(0, T.guests.length, ...gs); if (gen !== my || !T.soft.visible) { T.guests.splice(0).forEach(drop); } });
          }
          if (!on && T.guests.length) T.guests.splice(0).forEach(drop);
        }
        A.chip(TABLES.size ? `${open} mesas con QR activo` : `${staffPeople(snap).length} en turno`, true);
        const used = new Set(), seen = new Set(); let idx = 0;
        for (const p of staffPeople(snap)) {
          seen.add(p.key); const {spot, clip} = staffSpot(p, idx++, used); let s = STAFF.get(p.key);
          if (!s || Math.hypot(s.spot[0] - spot[0], s.spot[1] - spot[1]) > .2 || s.clip !== clip) {
            if (s) { drop(s.g); A.dropTag(s.tag); }
            s = {spot, clip, g: null, tag: null}; STAFF.set(p.key, s);
            const ss = s; character(lookFor(p.key, looks), clip, spot[0], spot[1], spot[2], idx).then(g => {
              if (STAFF.get(p.key) !== ss || gen !== my) { drop(g); return; } ss.g = g; ss.tag = A.tag(g, ss.html || '', ss.cls || '', toon ? 1.45 : 1.95); });
          }
          s.html = A.tagHtml(p.paused ? 'wait' : 'work', p.label, p.reference || p.role || ''); s.cls = p.paused ? 'pausa' : '';
          if (s.tag) A.setTag(s.tag, s.html, s.cls);
        }
        for (const [k, s] of STAFF) if (!seen.has(k)) { drop(s.g); A.dropTag(s.tag); STAFF.delete(k); }
        for (const scr of SCREENS) drawScreen(scr, snap);
        for (const f of FRIDGES) { const lv = inventoryLevel(snap, f.ob.conn); const n = Math.round(f.bottles.length * lv); f.bottles.forEach((b, i) => { b.visible = i < n; }); }
        R.shadowMap.needsUpdate = true;
      }
      async function setPlan(next) {
        gen++; clear(); plan = next.plano; looks = next.looks || looks; if (next.catalogo) registerModels(next.catalogo);
        buildPlan(); if (lastSnap) apply(lastSnap);
      }
      buildPlan();
      return {apply, get key() { return key; }, setPlan, stats,
        tick(t, dt) { for (const g of CHARS) tickCharacter(g, dt || .016, t); },
        reset() { STAFF.forEach(s => { drop(s.g); A.dropTag(s.tag); }); STAFF.clear(); TABLES.forEach(T => { T.guests.splice(0).forEach(drop); }); }};
    }});
}
