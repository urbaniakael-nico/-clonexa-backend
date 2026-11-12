// Oficina 3D · piso aprobado VOLTAGE · operación en campo (voltage.html / voltage.png). Interno de Clonexa, solo Admin V2.
// Datos REALES (copia viva, plantilla campo): sitio de centro de datos dividido por operación (Virginia ET |
// Alabama CT, por la franja amarilla). Técnicos con turno abierto (máximo 5 por operación) en los racks, letrero
// "+N en turno" con el resto; supervisor y almacén según su cargo; fuera de perímetro (GPS real) -> aro rojo +
// "⚠ Fuera de perímetro". Tablero por operación: en turno / programado, sin conectar (Horario de la semana; sin
// horario guardado "—"), fuera de perímetro y el último corte de entrada/salida enviado al grupo.
import {openFloor, THREE, P, API, esc, savedFor} from '/admin-v2plus/oficina/mixamo.js';

export function open(o) {
  const CP = P.CAMPO, {W: RW, D: RD, WALL: WH} = CP.ROOM;
  return openFloor(o, {title: o.floor.name, room: CP.ROOM, camera: CP.CAMERA, exposure: .85, bloom: [.3, .4, .96], cls: 'campo',
    liveUrl: `${API}/pisos/${o.floor.company_id}/vivo`, models: [...P.MEN, ...P.WOMEN], clips: ['Idle', 'Walking', 'Bartending', 'Talking'],
    async build(A) {
      const {mesh, flat, M, glow, RoundedBoxGeometry: RB, S} = A;
      const fl = flat(new THREE.PlaneGeometry(RW, RD), M(0x8a9098, {roughness: .6})); fl.rotation.x = -Math.PI / 2;
      const grid = M(0x555b63);
      for (let i = -RW / 2; i <= RW / 2; i += .6) { const l = flat(new THREE.PlaneGeometry(.02, RD), grid, i, .002, 0); l.rotation.x = -Math.PI / 2; }
      for (let i = -RD / 2; i <= RD / 2; i += .6) { const l = flat(new THREE.PlaneGeometry(RW, .02), grid, 0, .002, i); l.rotation.x = -Math.PI / 2; }
      const wallM = M(0x2a2e34, {roughness: .8}); mesh(new THREE.BoxGeometry(RW, WH, .2), wallM, 0, WH / 2, -RD / 2 - .1); mesh(new THREE.BoxGeometry(.2, WH, RD), wallM, -RW / 2 - .1, WH / 2, 0);
      flat(new THREE.BoxGeometry(RW + .4, .25, RD + .4), M(0x0d0a10, {metalness: .5, roughness: .4}), 0, -.13, 0); flat(new THREE.BoxGeometry(RW + .42, .04, .04), glow(0x22c55e, 3), 0, -.02, RD / 2 + .2);
      const div = flat(new THREE.PlaneGeometry(.12, RD), M(0xfacc15, {roughness: .5}), 0, .006, 0); div.rotation.x = -Math.PI / 2;
      // racks en filas con luces (instanciados: mismo aspecto, pocas llamadas)
      const rackM = M(0x111317, {metalness: .7, roughness: .3}); const spots = [];
      for (const side of [-1, 1]) for (let i = 0; i < 5; i++) { spots.push([side * (1.8 + i * .75), -4.6]); spots.push([side * (1.8 + i * .75), -1.8]); }
      const rackIM = new THREE.InstancedMesh(A.track(new RB(.7, 2.2, 1.0, 2, .03)), rackM, spots.length); rackIM.castShadow = rackIM.receiveShadow = true;
      const ledG = A.track(new THREE.BoxGeometry(.5, .02, .02)); const ledA = new THREE.InstancedMesh(ledG, glow(0x22c55e, 2.5), spots.length * 6), ledB = new THREE.InstancedMesh(ledG, glow(0x38bdf8, 2.5), spots.length * 3);
      const mm = new THREE.Matrix4(); let na = 0, nb = 0;
      spots.forEach(([x, z], j) => { mm.makeTranslation(x, 1.1, z); rackIM.setMatrixAt(j, mm); for (let k = 0; k < 9; k++) { mm.makeTranslation(x, .35 + k * .2, z + .51); if (k % 3) ledA.setMatrixAt(na++, mm); else ledB.setMatrixAt(nb++, mm); } });
      S.add(rackIM, ledA, ledB);
      for (const side of [-1, 1]) { mesh(new THREE.BoxGeometry(4.2, .08, .35), M(0xfacc15, {metalness: .4}), side * 3.3, 2.45, -4.6); mesh(new THREE.BoxGeometry(4.2, .08, .35), M(0xfacc15, {metalness: .4}), side * 3.3, 2.45, -1.8); }
      for (const [x, z] of [[-7.6, 1.6], [7.6, 1.6]]) { mesh(new RB(1.1, .6, .7, 2, .04), M(0x3f4650, {metalness: .5}), x, .55, z); for (let i = 0; i < 3; i++) mesh(new THREE.CylinderGeometry(.18, .18, .22, 20), M(0x1d4ed8), x - .35 + i * .35, .96, z).rotation.x = Math.PI / 2; }
      mesh(new RB(1.6, .06, .8, 2, .02), M(0xd6d3d1), 0, .75, 4.4); mesh(new THREE.BoxGeometry(1.5, .72, .7), M(0x3f4650), 0, .37, 4.4);
      // tableros por operación y letreros +N
      const boards = [A.canvasScreen(3.6, 1.34, 1024, 380), A.canvasScreen(3.6, 1.34, 1024, 380)];
      A.screen(-4.6, 2.4, -RD / 2 + .08, 3.6, 1.34, boards[0]); A.screen(4.6, 2.4, -RD / 2 + .08, 3.6, 1.34, boards[1]);
      const plus = [A.canvasScreen(1.6, .8, 512, 256), A.canvasScreen(1.6, .8, 512, 256)];
      const plusG = [A.screen(-CP.PLUS[0], 1.6, CP.PLUS[1], 1.6, .8, plus[0]), A.screen(CP.PLUS[0], 1.6, CP.PLUS[1], 1.6, .8, plus[1])];
      const zones = [A.zoneTag('—', -5, 5.4), A.zoneTag('—', 5, 5.4)];
      S.add(new THREE.AmbientLight(0xeef6ff, .5)); S.add(new THREE.HemisphereLight(0xffffff, 0x20262e, .35));
      const key = new THREE.DirectionalLight(0xf2f7ff, 1.4); key.position.set(5, 12, 8); key.castShadow = true; key.shadow.mapSize.set(2048, 2048); Object.assign(key.shadow.camera, {left: -12, right: 12, top: 9, bottom: -9}); key.shadow.camera.updateProjectionMatrix(); key.shadow.bias = -.0005; S.add(key);
      for (const x of [-6, -2, 2, 6]) flat(new THREE.BoxGeometry(2.8, .05, .18), glow(0xf2f7ff, 2), x, 3.3, -3.2);

      function drawBoard(i, op) {
        const b = op ? P.opBoard(op) : null; const col = i ? '#38bdf8' : '#22c55e';
        boards[i].draw(b, (x, w, h, m) => {
          x.fillStyle = '#0b1410'; x.fillRect(0, 0, w, h); x.fillStyle = col; x.fillRect(0, 0, w, 8);
          if (!m) { x.fillStyle = '#9ca3af'; x.font = '700 40px Inter,sans-serif'; x.fillText('Sin operación', 30, 200); return; }
          x.fillStyle = '#fff'; x.font = '800 52px Inter,sans-serif'; x.fillText(A.clipText(m.name, 22), 30, 78);
          [[m.on, 'en turno', '#22c55e'], [m.missing, 'sin conectar', '#f59e0b'], [m.outside, 'fuera de perímetro', '#ef4444']].forEach(([v, t, c], j) => { const X = 30 + j * ((w - 60) / 3);
            x.fillStyle = 'rgba(255,255,255,.06)'; x.fillRect(X, 110, (w - 60) / 3 - 16, 170); x.fillStyle = c; x.font = '800 60px Inter,sans-serif'; x.fillText(v, X + 20, 200); x.fillStyle = '#cbd5e1'; x.font = '500 26px Inter,sans-serif'; x.fillText(t, X + 20, 250); });
          x.fillStyle = '#fff'; x.font = '700 30px Inter,sans-serif'; x.fillText(A.clipText(m.cut, 56), 30, 340);
        });
        plusG[i].visible = !!(op && op.extra);
        plus[i].draw(op ? {n: op.extra, name: op.name} : null, (x, w, h, m) => { x.fillStyle = '#062014'; x.fillRect(0, 0, w, h); if (!m) return;
          x.fillStyle = '#22c55e'; x.font = '800 120px Inter,sans-serif'; x.fillText('+' + m.n, 30, 140); x.fillStyle = '#d1fae5'; x.font = '600 40px Inter,sans-serif'; x.fillText(A.clipText('en turno · ' + m.name, 20), 30, 210); });
        A.setTag(zones[i], esc(op ? `${op.name}${op.tz ? ' (' + tzShort(op.tz) + ')' : ''}` : '—'), 'zn');
      }
      const tzShort = tz => ({'America/New_York': 'ET', 'America/Chicago': 'CT', 'America/Denver': 'MT', 'America/Los_Angeles': 'PT', 'America/Bogota': 'COT'}[tz] || tz);
      const CREW = new Map(); let rep = null; const door = [0, 6.2];
      function apply(snap, prev, first) {
        const ops = (snap.ops || []).slice(0, 2); drawBoard(0, ops[0]); drawBoard(1, ops[1]);
        A.chip(`${snap.on_shift == null ? P.NO : snap.on_shift} en turno`, true);
        if ((snap.ops || []).length > 2) A.warn(`${snap.ops.length - 2} operaciones más sin espacio en el plano`);
        if (!A.peopleOk()) return;
        const seen = new Set();
        ops.forEach((op, i) => { const side = P.sideOf(i);
          for (const s of P.campoSpots(op, side)) {
            seen.add(s.key); const person = op.people.find(p => p.key === s.key);
            let c = CREW.get(s.key);
            if (!c) { const cfg = P.personCfg(s.key, person.first, savedFor(o, 'staff', s.key, 'tecnico'), {models: ['Ch17_nonPBR']});
              const per = A.makePerson({...cfg, kind: 'personal', info: {name: person.label, role: op.name}}); per.tag = A.tag(per.g, '', '', 1.95);
              c = {p: per, pos: s.pos}; CREW.set(s.key, c);
              if (first) A.sitAt(per, [...s.pos, s.ry], s.clip); else A.arrive(per, door, s.pos, () => A.sitAt(per, [...s.pos, s.ry], s.clip)); }
            else if (Math.hypot(c.pos[0] - s.pos[0], c.pos[1] - s.pos[1]) > .3) { c.pos = s.pos; A.goTo(c.p, s.pos, () => A.sitAt(c.p, [...s.pos, s.ry], s.clip)); }
            else if (!c.p.path.length) A.play(c.p, s.clip);
            A.setRing(c.p, s.outside ? 'red' : null);
            c.p.info = {name: person.label, role: op.name, task: s.tag.small};
            A.setTag(c.p.tag, A.tagHtml(s.outside ? 'err' : s.tag.cls === 'pausa' ? 'wait' : 'work', s.tag.text, s.tag.small), s.tag.cls);
          } });
        for (const [k, c] of CREW) if (!seen.has(k)) { CREW.delete(k); A.setRing(c.p, null); A.leave(c.p, door); }
        if (!rep) { rep = A.makePerson({model: 'Ch07_nonPBR', kind: 'rep', info: {name: 'Representante', role: o.floor.name}}); A.sitAt(rep, CP.REP, 'Talking'); rep.tag = A.tag(rep.g, '', 'rep', 1.95); }
        A.setTag(rep.tag, A.tagHtml('rep', 'Representante', P.repCampo(snap)), 'rep');
      }
      return {apply, key, reset() { CREW.clear(); rep = null; }};
    }});
}
