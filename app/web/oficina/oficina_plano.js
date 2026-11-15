// Oficina 3D · piso dibujado por el PLANO del Modo constructor (fase 1). Interno de Clonexa: en la consola (Oficina 3D
// y la vista 3D del constructor) y en el visor del cliente (Negocio en vivo 3D) solo con la versión PUBLICADA.
// Reutiliza el motor común (oficina_mixamo.openFloor: renderer, cámara, gestos, etiquetas, personas de Mixamo, copia
// viva cada 7 s). Las paredes, pisos, puertas y objetos salen del plano (plano_objetos.js); los objetos CONECTADOS se
// mueven con los datos reales: mesa con QR activo (bombillo verde + clientes), puesto/máquina con su operaria,
// escritorio con su persona, caja con el cajero y pantallas vivas (canciones, comandas, domicilios, producción, turno).
// Estilo por empresa: "humano" (Mixamo, PBR) o "caricatura" (toon + contorno + personaje por partes).
import {openFloor, THREE, P, API, esc, savedFor} from '/admin-v2plus/oficina/mixamo.js';
import * as O from '/admin-v2plus/oficina/plano_objetos.js';

// ===== reglas puras (tests/plano_motor.test.cjs) =====
export function cameraFor(room) {
  const m = Math.max(room.W, room.D);
  return {pos: [room.W * .12, m * .78 + 2, room.D / 2 + m * .62 + 2], look: [0, .4, 0], fov: 34};
}
// Partes macizas de una pared con aberturas: [{a, b, y0, y1}] a lo largo de la pared (metros desde su inicio).
export function wallPieces(L, H, openings) {
  const ops = (openings || []).map(o => ({a: Math.max(0, o.pos - o.ancho / 2), b: Math.min(L, o.pos + o.ancho / 2), y0: o.base || 0, y1: Math.min(H, (o.base || 0) + o.alto)}))
    .filter(o => o.b > o.a).sort((p, q) => p.a - q.a);
  const out = []; let x = 0;
  for (const o of ops) {
    if (o.a > x + .001) out.push({a: x, b: o.a, y0: 0, y1: H});
    if (o.y0 > .001) out.push({a: o.a, b: o.b, y0: 0, y1: o.y0});
    if (o.y1 < H - .001) out.push({a: o.a, b: o.b, y0: o.y1, y1: H});
    x = Math.max(x, o.b);
  }
  if (x < L - .001) out.push({a: x, b: L, y0: 0, y1: H});
  return out;
}
// Normal hacia afuera de una pared (lejos del centro de la sala): para ocultar la que queda entre la cámara y el salón.
export function outward(w, sala) {
  const L = Math.hypot(w.x2 - w.x1, w.z2 - w.z1) || 1, ux = (w.x2 - w.x1) / L, uz = (w.z2 - w.z1) / L;
  let nx = -uz, nz = ux; const mx = (w.x1 + w.x2) / 2 - sala.ancho / 2, mz = (w.z1 + w.z2) / 2 - sala.fondo / 2;
  if (nx * mx + nz * mz < 0) { nx = -nx; nz = -nz; }
  return [nx, nz];
}
// Puesto (asiento de la persona) de un objeto conectado, en coordenadas de escena.
export function seatOf(o, sala, item, kind) {
  const [x, z] = O.toScene(o.x, o.z, sala), r = O.rotY(o.rot), d = (item && item.medidas && item.medidas.d) || .7;
  const off = kind === 'caja' ? [0, -d / 2 - .45] : kind === 'puesto' ? [0, .62] : [0, d / 2 + .3];
  const c = Math.cos(r), s = Math.sin(r);
  return [x + off[0] * c + off[1] * s, z - off[0] * s + off[1] * c, r + (kind === 'caja' ? 0 : Math.PI)];
}
// Asientos alrededor de una mesa conectada (cuántos según el modelo).
export function tableSeats(o, sala, item) {
  const [x, z] = O.toScene(o.x, o.z, sala), r = O.rotY(o.rot), f = item && item.forma;
  const base = f === 'table_two' ? [[-.6, 0, -Math.PI / 2], [.6, 0, Math.PI / 2]] : f === 'table_six' ? [[-.6, -.75, 0], [0, -.75, 0], [.6, -.75, 0], [-.6, .75, Math.PI], [0, .75, Math.PI], [.6, .75, Math.PI]]
    : f === 'table_high' ? [[0, -.55, 0], [0, .55, Math.PI]] : f === 'booth' ? [[-.3, -.6, 0], [.3, -.6, 0], [-.3, .6, Math.PI], [.3, .6, Math.PI]]
    : [[0, -.72, 0], [0, .72, Math.PI], [-.72, 0, Math.PI / 2], [.72, 0, -Math.PI / 2]];
  const c = Math.cos(r), s = Math.sin(r);
  return base.map(([a, b, rr]) => [x + a * c + b * s, z - a * s + b * c, rr + r]);
}
export function staffPeople(snap) {
  if (!snap) return [];
  if (Array.isArray(snap.people)) return snap.people.map(p => ({...p, uniform: p.uniform || 'taller', paused: p.status === 'paused'}));
  return ((snap.staff || {}).people || []).slice();
}
export function screenModel(kind, snap, o) {
  const s = snap || {};
  if (kind === 'canciones') return {title: 'Canciones pedidas', rows: (s.songs || []).slice(0, 5).map(x => x.title || x.label || String(x)), empty: 'Sin canciones pedidas'};
  if (kind === 'comandas') return {title: `Comandas en cocina · ${s.kitchen_count ?? (s.kitchen || []).length ?? 0}`, rows: (s.kitchen || []).slice(0, 5).map(k => `${k.label}${k.minutes != null ? ' · ' + k.minutes + ' min' : ''}`), empty: 'Sin comandas'};
  if (kind === 'domicilios') return {title: 'Domicilios', rows: (s.deliveries || []).slice(0, 5).map(d => `${d.label}${d.barrio ? ' · ' + d.barrio : ''}`), empty: 'Sin domicilios hoy'};
  if (kind === 'produccion') { const b = s.board || {}; return {title: b.lot ? `Lote ${b.lot}` : 'Producción', rows: [b.made != null ? `Hechas ${b.made}${b.meta ? ' de ' + b.meta : ''}` : 'Sin lote en proceso', `En turno ${b.on_shift ?? '—'} · pausa ${b.paused ?? '—'}`, b.hours ? `Horas ${b.hours}` : ''].filter(Boolean), empty: ''}; }
  if (kind === 'turno') { const pp = staffPeople(s); return {title: `Personal en turno · ${pp.length}`, rows: pp.slice(0, 6).map(p => p.label), empty: 'Nadie en turno'}; }
  if (kind === 'texto') return {title: (o && o.texto) || '', rows: [], empty: ''};
  return {title: '', rows: [], empty: '', logo: true};
}
// ===== fin reglas puras =====

export async function open(o) {
  const cid = o.floor.company_id;
  const pay = o.planPayload || await o.getJson(`${API}/pisos/${cid}/plano`);
  const sala = pay.plano.sala, room = {W: sala.ancho, D: sala.fondo, WALL: sala.alto};
  const toon = (o.styleOverride || pay.estilo) === 'caricatura';
  const camera = cameraFor(room);
  return openFloor(o, {title: o.floor.name, room, camera, exposure: toon ? 1.0 : .85, bloom: toon ? [.25, .3, .98] : [.3, .4, .96], cls: 'plano' + (toon ? ' toon' : ''),
    bg: toon ? 0x241a3a : 0x07050a, liveUrl: o.liveUrl || `${API}/pisos/${cid}/vivo`, route: (a, b) => [b], models: P.CHARACTERS,
    tableInfo: (snap, label) => P.tableInfo(snap, label),
    clips: ['Idle', 'Walking', 'Typing', 'Bartending', 'Talking', 'Sitting', 'Sitting_Talking', 'Sitting_Drinking', 'Sitting_Laughing'],
    async build(A) {
      const {S, C} = A;
      const texCache = new Map();
      const tex = f => { if (!texCache.has(f)) texCache.set(f, A.tex(f, [1, 1])); return texCache.get(f); };
      const lib = O.createLibrary({tex, toon, lite: A.lite(), track: A.track});
      const outlineMat = A.track(new THREE.MeshBasicMaterial({color: 0x15101c, side: THREE.BackSide}));
      outlineMat.onBeforeCompile = sh => { sh.vertexShader = sh.vertexShader.replace('#include <begin_vertex>', '#include <begin_vertex>\ntransformed += normalize(normal) * 0.022;'); };
      // luces
      S.add(new THREE.AmbientLight(0xfff4ea, toon ? .85 : .38)); S.add(new THREE.HemisphereLight(0xfff4e6, 0x30202a, toon ? .45 : .32));
      const key = new THREE.DirectionalLight(0xffefe0, toon ? 1.15 : 1.35); key.position.set(room.W * .25, 14, room.D * .4); key.castShadow = true;
      key.shadow.mapSize.set(2048, 2048); Object.assign(key.shadow.camera, {left: -room.W / 2 - 1, right: room.W / 2 + 1, top: room.D / 2 + 1, bottom: -room.D / 2 - 1, far: 40});
      key.shadow.camera.updateProjectionMatrix(); key.shadow.bias = -.0005; S.add(key);
      const root = new THREE.Group(); S.add(root);
      let plan = pay.plano, items = new Map((pay.catalogo || []).map(x => [x.id, x]));
      const protoCache = new Map(), glbCache = new Map(), lights = [];
      const WALLS = [], SCREENS = new Map(), TABLES = new Map(), SPOTS = {puesto: new Map(), escritorio: new Map(), caja: []};
      const stats = {objects: 0, instanced: 0, drawGroups: 0, glb: 0};

      async function glbParts(item) {
        if (glbCache.has(item.id)) return glbCache.get(item.id);
        const p = (async () => { const g = await A.loader.loadAsync(item.url); const scene = g.scene;
          if (toon) scene.traverse(x => { if (x.isMesh) { const om = x.material; x.material = lib.base('#' + (om.color ? om.color.getHexString() : 'cccccc'), {map: om.map || null}); } });
          return lib.flatten(scene); })().catch(() => null);
        glbCache.set(item.id, p); return p;
      }
      function partsFor(item, ob) {
        const k = O.instKey(ob, item);
        if (!protoCache.has(k)) protoCache.set(k, lib.flatten(lib.buildProto(item, ob)));
        return protoCache.get(k);
      }
      function matrixOf(ob, y = 0) {
        const [x, z] = O.toScene(ob.x, ob.z, sala); const m = new THREE.Matrix4();
        m.compose(new THREE.Vector3(x, ob.y ?? y, z), new THREE.Quaternion().setFromEuler(new THREE.Euler(0, O.rotY(ob.rot), 0)), new THREE.Vector3(ob.escala || 1, ob.escala || 1, ob.escala || 1));
        return m;
      }
      function instanced(parts, list, parent) {
        for (const {geo, mat} of parts) {
          const im = new THREE.InstancedMesh(geo, mat, list.length); list.forEach((ob, i) => im.setMatrixAt(i, matrixOf(ob)));
          im.castShadow = !A.lite() && !mat.transparent; im.receiveShadow = true; im.userData.ownCut = true; parent.add(im); stats.drawGroups++;
          if (toon && !mat.userData.noOutline) { const ol = new THREE.InstancedMesh(geo, outlineMat, list.length); list.forEach((ob, i) => ol.setMatrixAt(i, matrixOf(ob))); ol.userData.ownCut = true; parent.add(ol); stats.drawGroups++; }
        }
      }
      function clear() {
        for (const t of TABLES.values()) { A.dropTag(t.tag); t.guests.splice(0).forEach(g => g.drop()); }
        TABLES.clear(); SPOTS.puesto.clear(); SPOTS.escritorio.clear(); SPOTS.caja.length = 0; SCREENS.clear(); WALLS.length = 0;
        lights.splice(0).forEach(l => S.remove(l));
        root.traverse(x => { if (x.isInstancedMesh) x.dispose(); });
        while (root.children.length) root.remove(root.children[0]);
        for (let i = A.PICK.length - 1; i >= 0; i--) if (A.PICK[i].userData.table) A.PICK.splice(i, 1);
      }
      // ---------------------------------------------------------- piso, paredes, aberturas
      function buildShell() {
        const base = new THREE.Mesh(new THREE.PlaneGeometry(room.W + .3, room.D + .3), O.surfaceMaterial(lib, 'concreto_pulido', '#6b6b70', O.FLOOR_MAT, tex, room.W, room.D));
        base.rotation.x = -Math.PI / 2; base.receiveShadow = true; base.userData.ownCut = true; root.add(base);
        (plan.pisos || []).forEach((f, i) => {
          const sh = new THREE.Shape(f.puntos.map(([x, z]) => { const [a, b] = O.toScene(x, z, sala); return new THREE.Vector2(a, -b); }));
          const m = new THREE.Mesh(new THREE.ShapeGeometry(sh), O.surfaceMaterial(lib, f.material, f.color, O.FLOOR_MAT, tex, 1, 1));
          m.rotation.x = -Math.PI / 2; m.position.y = .003 + i * .0007; m.receiveShadow = true; m.userData.ownCut = true; root.add(m);
        });
        const byWall = new Map(); (plan.aberturas || []).forEach(a => { const l = byWall.get(a.pared) || []; l.push(a); byWall.set(a.pared, l); });
        for (const w of plan.paredes || []) {
          const L = Math.hypot(w.x2 - w.x1, w.z2 - w.z1); const ang = Math.atan2(w.z2 - w.z1, w.x2 - w.x1); const [sx, sz] = O.toScene(w.x1, w.z1, sala);
          const [nx, nz] = outward(w, sala); const g = new THREE.Group(); g.position.set(sx, 0, sz); g.rotation.y = -ang; root.add(g);
          for (const pc of wallPieces(L, w.alto, byWall.get(w.id))) {
            const len = pc.b - pc.a, h = pc.y1 - pc.y0; if (len < .01 || h < .01) continue;
            const m = new THREE.Mesh(new THREE.BoxGeometry(len, h, w.grosor), O.surfaceMaterial(lib, w.material, w.color, O.WALL_MAT, tex, len, h));
            m.position.set(pc.a + len / 2, pc.y0 + h / 2, 0); m.castShadow = m.receiveShadow = true; m.userData.ownCut = true; g.add(m);
            if (toon && w.material !== 'vidrio') { const e = new THREE.Mesh(m.geometry, outlineMat); e.position.copy(m.position); e.userData.ownCut = true; g.add(e); }
          }
          for (const a of byWall.get(w.id) || []) opening(g, a, w);
          const mid = O.toScene((w.x1 + w.x2) / 2, (w.z1 + w.z2) / 2, sala); WALLS.push({g, cx: mid[0], cz: mid[1], nx, nz});
        }
      }
      function opening(g, a, w) {
        const k = lib.K(g, a.tipo === 'cortina_metalica' ? '#8a8f98' : '#5b3a26'); const x0 = a.pos, t = w.grosor;
        const frame = (y0, h) => { k.box(a.ancho + .08, .06, t + .04, x0, y0 + h, 0, k.k); [-1, 1].forEach(s => k.box(.05, h, t + .04, x0 + s * (a.ancho / 2 + .02), y0, 0, k.k)); };
        const leaf = (cx, w2, h, m, open = 0) => { const p = new THREE.Group(); p.position.set(cx - w2 / 2, 0, 0); g.add(p); const kk = lib.K(p, '#000'); const b = kk.box(w2, h, .045, w2 / 2, 0, 0, m); p.rotation.y = open; return b; };
        if (a.tipo === 'puerta') { frame(0, a.alto); leaf(x0, a.ancho, a.alto, k.c, -.5); }
        else if (a.tipo === 'puerta_doble') { frame(0, a.alto); leaf(x0 - a.ancho / 4, a.ancho / 2, a.alto, k.c, -.35); leaf(x0 + a.ancho / 4, a.ancho / 2, a.alto, k.c, .35).position.x -= a.ancho / 2 - .02; }
        else if (a.tipo === 'puerta_vidrio') { frame(0, a.alto); leaf(x0, a.ancho, a.alto, k.g, -.3); }
        else if (a.tipo === 'corrediza') { frame(0, a.alto); k.box(a.ancho / 2, a.alto, .03, x0 + a.ancho / 4, 0, .03, k.g); }
        else if (a.tipo === 'cortina_metalica') { frame(0, a.alto); k.box(a.ancho, .35, t + .1, x0, a.alto - .35, 0, k.c); for (let i = 0; i < 4; i++) k.box(a.ancho, .02, .02, x0, a.alto - .3 + i * .07, t / 2 + .05, k.c2); }
        else if (a.tipo === 'vaiven') { frame(0, a.alto); [-1, 1].forEach(s => k.box(a.ancho / 2 - .02, a.alto * .55, .04, x0 + s * a.ancho / 4, a.alto * .25, 0, k.s)); }
        else { frame(a.base, a.alto); k.box(.04, .04, t + .08, x0, a.base - .04, 0, k.k); const gl = new THREE.Mesh(new THREE.PlaneGeometry(a.ancho, a.alto), k.g); gl.position.set(x0, a.base + a.alto / 2, 0); g.add(gl);
          if (a.tipo === 'ventanal' || a.tipo === 'vitrina') for (let i = 1; i < Math.round(a.ancho / 1.2); i++) k.box(.03, a.alto, t, x0 - a.ancho / 2 + i * a.ancho / Math.round(a.ancho / 1.2), a.base, 0, k.k); }
        g.children.forEach(x => { x.userData.ownCut = true; });
      }
      // ---------------------------------------------------------- objetos (instancias por modelo+color+variante)
      function textTexture(text, color, w = 1024, h = 320, font = '800 150px "Brush Script MT", cursive') {
        const cv = document.createElement('canvas'); cv.width = w; cv.height = h; const x = cv.getContext('2d');
        x.font = font; x.textAlign = 'center'; x.textBaseline = 'middle'; x.shadowColor = color; x.shadowBlur = 28; x.fillStyle = O.shade(color, 1.4);
        let size = 150; while (x.measureText(text).width > w * .92 && size > 40) { size -= 10; x.font = font.replace(/\d+px/, size + 'px'); }
        x.fillText(text, w / 2, h / 2); x.fillText(text, w / 2, h / 2);
        const t = A.track(new THREE.CanvasTexture(cv)); t.colorSpace = THREE.SRGBColorSpace; return t;
      }
      function uniqueObject(ob, item) {
        const g = lib.buildProto(item, ob); const holder = new THREE.Group(); holder.applyMatrix4(matrixOf(ob)); holder.add(g); root.add(holder);
        g.traverse(x => { if (x.isMesh) { x.userData.ownCut = true; x.castShadow = !A.lite(); } });
        const m = item.medidas || {};
        if (item.forma === 'neon') {
          const col = ob.color || (item.variantes || [])[0] || '#ec4899';
          const pl = new THREE.Mesh(new THREE.PlaneGeometry(m.w, m.h), A.track(new THREE.MeshBasicMaterial({map: textTexture(ob.texto || 'Clonexa', col), transparent: true, toneMapped: false})));
          pl.position.set(0, 1.9 + m.h / 2, -m.d / 2 + .03); holder.add(pl);
        } else if (item.forma === 'logo') {
          const brand = (A.floor && A.floor.brand) || {}; const pl = new THREE.Mesh(new THREE.PlaneGeometry(m.w * .9, m.h * .85), A.track(new THREE.MeshBasicMaterial({transparent: true, toneMapped: false,
            map: textTexture(A.floor.name || 'Logo', brand.primary || '#f20b6d', 1024, 512, '900 120px Inter, sans-serif')})));
          pl.position.set(0, 1.6 + m.h / 2, -m.d / 2 + .045); holder.add(pl);
          if (brand.logo_url) new THREE.TextureLoader().load(brand.logo_url, t => { t.colorSpace = THREE.SRGBColorSpace; pl.material.map = A.track(t); pl.material.needsUpdate = true; }, undefined, () => {});
        }
        g.traverse(x => { if (x.isMesh && x.userData.screen) { const cs = A.canvasScreen(1, 1, 1024, 576); x.material = A.track(new THREE.MeshBasicMaterial({map: cs.texture, toneMapped: false}));
          SCREENS.set(ob.id, {cs, kind: (ob.conexion && ob.conexion.tipo === 'pantalla' && ob.conexion.id) || 'logo', ob}); } });
        if (toon) g.traverse(x => { if (x.isMesh && !x.userData.screen && !(x.material.userData || {}).noOutline) { const e = new THREE.Mesh(x.geometry, outlineMat); e.position.copy(x.position); e.rotation.copy(x.rotation); e.scale.copy(x.scale); e.userData.ownCut = true; x.parent.add(e); } });
        return holder;
      }
      async function buildObjects() {
        const groups = new Map(), glbs = new Map();
        stats.objects = (plan.objetos || []).length; stats.instanced = 0;
        for (const ob of plan.objetos || []) {
          const item = items.get(ob.asset); if (!item) continue;
          if (item.forma === 'glb') { const l = glbs.get(item.id) || []; l.push(ob); glbs.set(item.id, l); }
          else if (O.UNIQUE.has(item.forma)) uniqueObject(ob, item);
          else { const k = O.instKey(ob, item); const g = groups.get(k) || {item, list: []}; g.list.push(ob); groups.set(k, g); }
          const L = O.LIGHTS[item.forma];
          if (L && !A.lite() && !toon && lights.length < 10) { const [x, z] = O.toScene(ob.x, ob.z, sala); const l = new THREE.PointLight(L[0] ?? new THREE.Color(ob.color || (item.variantes || [])[0] || '#ffffff'), L[1], L[2], 2); l.position.set(x, L[3], z); S.add(l); lights.push(l); }
          connect(ob, item);
        }
        for (const {item, list} of groups.values()) { instanced(partsFor(item, list[0]), list, root); stats.instanced += list.length; }
        for (const [id, list] of glbs) {   // carga diferida: caja provisional mientras llega el GLB
          const item = items.get(id); const box = lib.flatten(lib.buildProto({...item, forma: 'none'}, {color: '#9ca3af'})); const tmp = new THREE.Group(); root.add(tmp); instanced(box, list, tmp);
          glbParts(item).then(parts => { if (!parts || !root.children.includes(tmp)) return; root.remove(tmp); tmp.traverse(x => { if (x.isInstancedMesh) x.dispose(); }); instanced(parts, list, root); stats.glb++; R.shadowMap.needsUpdate = true; });
        }
      }
      const R = A.R;
      // ---------------------------------------------------------- conexiones con lo real
      const bulbOn = lib.glow('#4ade80'), bulbOff = lib.base('#2a2a2a');
      const sc0 = document.createElement('canvas'); sc0.width = sc0.height = 128;
      { const x = sc0.getContext('2d'); const g = x.createRadialGradient(64, 64, 0, 64, 64, 64); g.addColorStop(0, 'rgba(74,222,128,1)'); g.addColorStop(1, 'rgba(74,222,128,0)'); x.fillStyle = g; x.fillRect(0, 0, 128, 128); }
      const softM = A.track(new THREE.MeshBasicMaterial({map: A.track(new THREE.CanvasTexture(sc0)), transparent: true, opacity: .28, depthWrite: false, blending: THREE.AdditiveBlending}));
      function connect(ob, item) {
        const con = ob.conexion; if (!con) return;
        if (con.tipo === 'mesa') {
          const [x, z] = O.toScene(ob.x, ob.z, sala); const g = new THREE.Group(); g.position.set(x, 0, z); root.add(g);
          const bulb = new THREE.Mesh(new THREE.SphereGeometry(.07, 10, 8), bulbOff); bulb.position.y = 2.45; g.add(bulb);
          const cord = new THREE.Mesh(new THREE.CylinderGeometry(.004, .004, .7, 4), lib.base('#111111')); cord.position.y = 2.85; g.add(cord);
          const soft = new THREE.Mesh(new THREE.CircleGeometry(1.2, 32), softM); soft.rotation.x = -Math.PI / 2; soft.position.y = .02; soft.visible = false; g.add(soft);
          const hit = new THREE.Mesh(new THREE.CylinderGeometry(.8, .8, 1, 10), A.hitM); hit.position.y = .5; hit.userData.table = con.id; g.add(hit); A.PICK.push(hit);
          TABLES.set(con.id, {ob, item, bulb, soft, guests: [], tag: A.tag(A.at(x, .8, z), '', 'mesa off', .12, true)});
        } else if (con.tipo === 'puesto' || con.tipo === 'escritorio') SPOTS[con.tipo].set(con.id, seatOf(ob, sala, item, con.tipo));
        else if (con.tipo === 'caja') SPOTS.caja.push(seatOf(ob, sala, item, 'caja'));
      }
      // ---------------------------------------------------------- personas (Mixamo en Humano; por partes en Caricatura o sin Mixamo)
      const TOON = [];
      function person(cfg, spot, clip, kind, info) {
        if (!toon && A.peopleOk()) { const p = A.makePerson({...cfg, kind, info}); A.sitAt(p, spot, clip); return {g: p.g, drop: () => A.dropPerson(p), p}; }
        const h = P.hashOf(cfg.key || info.name || ''); const tp = O.toonPerson(lib, {ropa: cfg.color || ['#7c3aed', '#dc2626', '#0ea5e9', '#f59e0b', '#16a34a'][h % 5],
          piel: ['#f1c27d', '#e0ac69', '#c68642', '#8d5524'][h % 4], pelo: ['#2b1a10', '#111111', '#a16207', '#7c2d12'][(h >> 3) % 4]});
        tp.sit(P.SEATED.test(clip)); tp.g.position.set(spot[0], 0, spot[1]); tp.g.rotation.y = spot[2] || 0; S.add(tp.g);
        if (toon) tp.g.traverse(x => { if (x.isMesh) { const e = new THREE.Mesh(x.geometry, outlineMat); e.position.copy(x.position); e.scale.copy(x.scale); x.parent.add(e); } });
        TOON.push(tp); return {g: tp.g, drop: () => { S.remove(tp.g); const i = TOON.indexOf(tp); if (i >= 0) TOON.splice(i, 1); }};
      }
      const STAFF = new Map();
      function staffSpot(p, idx, used) {
        if (SPOTS.escritorio.has(p.key)) return [SPOTS.escritorio.get(p.key), 'Typing'];
        if (p.uniform === 'taller' || p.uniform === 'costura' || p.uniform === 'operaria') { if (p.paused) return [[-room.W / 2 + 1 + idx * .7, room.D / 2 - 1, Math.PI], 'Idle'];
          const free = [...SPOTS.puesto.entries()].sort((a, b) => parseInt(a[0].split('-')[1]) - parseInt(b[0].split('-')[1])).find(([k]) => !used.has(k)); if (free) { used.add(free[0]); return [free[1], 'Typing']; } }
        if (/caj/.test(p.uniform || '') && SPOTS.caja.length && !used.has('caja')) { used.add('caja'); return [SPOTS.caja[0], 'Idle']; }
        return [[-room.W / 2 + 1.2 + (idx % 8) * .9, room.D / 2 - 1.1 - Math.floor(idx / 8) * .9, Math.PI], 'Idle'];
      }
      function drawScreen(scr, snap) {
        const m = screenModel(scr.kind, snap, scr.ob); const brand = (A.floor && A.floor.brand) || {};
        scr.cs.draw({m, n: A.floor && A.floor.name}, (x, w, h) => {
          x.fillStyle = toon ? '#1b1035' : '#0b0f1c'; x.fillRect(0, 0, w, h);
          if (m.logo) { x.fillStyle = brand.primary || '#f20b6d'; x.font = '900 96px Inter,sans-serif'; x.textAlign = 'center'; x.fillText(A.clipText((A.floor && A.floor.name) || 'Clonexa', 18), w / 2, h / 2 + 30); return; }
          x.fillStyle = '#fff'; x.font = '800 54px Inter,sans-serif'; x.fillText(A.clipText(m.title, 30), 36, 80);
          if (!m.rows.length) { x.fillStyle = '#cbbfd6'; x.font = '500 40px Inter,sans-serif'; x.fillText(m.empty, 36, 180); return; }
          m.rows.forEach((r, i) => { x.fillStyle = 'rgba(255,255,255,.08)'; x.fillRect(30, 110 + i * 88, w - 60, 74); x.fillStyle = '#fff'; x.font = '600 40px Inter,sans-serif'; x.fillText(A.clipText(r, 40), 52, 160 + i * 88); });
        });
      }
      let lastSnap = null;
      function apply(snap, prev, first) {
        lastSnap = snap;
        const tables = new Map((snap.tables || []).map(t => [t.label, t]));
        let open = 0;
        for (const [label, T] of TABLES) {
          const t = tables.get(label); const on = !!(t && t.open); if (on) open++;
          T.bulb.material = on ? bulbOn : bulbOff; T.soft.visible = on;
          const tt = P.tableTag(t || {label, open: false}); A.setTag(T.tag, `${tt.dot ? '<b class="dot">●</b> ' : ''}${esc(tt.text)}`, tt.cls);
          if (on && !T.guests.length) { const seats = tableSeats(T.ob, sala, T.item); P.guestCast(label, Math.min(seats.length, P.guestsFor(t))).forEach((c, i) => {
            const s = seats[i % seats.length]; T.guests.push(person({model: c.model, key: label + i}, s, c.clip, 'cliente', {name: 'Cliente', role: label})); }); }
          if (!on && T.guests.length) T.guests.splice(0).forEach(g => g.drop());
        }
        A.chip(TABLES.size ? `${open} mesas con QR activo` : `${staffPeople(snap).length} en turno`, true);
        const used = new Set(), seen = new Set(); let idx = 0;
        for (const p of staffPeople(snap)) {
          seen.add(p.key); const [spot, clip] = staffSpot(p, idx++, used); let s = STAFF.get(p.key);
          if (!s || Math.hypot(s.spot[0] - spot[0], s.spot[1] - spot[1]) > .2) { if (s) s.h.drop();
            const cfg = P.personCfg(p.key, p.first, savedFor(o, 'staff', p.key, p.uniform)); s = {h: person({...cfg, key: p.key}, spot, clip, 'personal', {name: p.label, role: p.role}), spot};
            s.tag = A.tag(s.h.g, '', '', toon ? 1.45 : 1.95); STAFF.set(p.key, s); }
          A.setTag(s.tag, A.tagHtml(p.paused ? 'wait' : 'work', p.label, p.reference || p.role || ''), p.paused ? 'pausa' : '');
        }
        for (const [k, s] of STAFF) if (!seen.has(k)) { s.h.drop(); A.dropTag(s.tag); STAFF.delete(k); }
        for (const scr of SCREENS.values()) drawScreen(scr, snap);
      }
      function cut() {
        for (const w of WALLS) { const v = (C.position.x - w.cx) * w.nx + (C.position.z - w.cz) * w.nz; w.g.visible = v < 1.5; }
      }
      async function setPlan(next) {
        const reStaff = [...STAFF.values()]; reStaff.forEach(s => { s.h.drop(); A.dropTag(s.tag); }); STAFF.clear();
        clear(); plan = next.plano; if (next.catalogo) items = new Map(next.catalogo.map(x => [x.id, x]));
        buildShell(); await buildObjects(); if (lastSnap) apply(lastSnap, null, true); R.shadowMap.needsUpdate = true;
      }
      buildShell(); await buildObjects();
      return {apply, key, setPlan, stats, tick(t) { cut(); TOON.forEach((p, i) => p.tick(t, i)); },
        reset() { STAFF.forEach(s => { s.h.drop(); A.dropTag(s.tag); }); STAFF.clear(); TABLES.forEach(T => { T.guests.splice(0).forEach(g => g.drop()); }); }};
    }});
}
