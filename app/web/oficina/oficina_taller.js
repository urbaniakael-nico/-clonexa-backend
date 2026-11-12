// Oficina 3D · piso aprobado VELVET · taller de costura (velvet.html / velvet.png). Interno de Clonexa, solo Admin V2.
// Datos REALES (copia viva /pisos/{id}/vivo, plantilla taller): quien abre turno cose en su máquina (Typing) con
// "Nombre · Cosiendo · <referencia>"; pausa -> café con "En pausa · N min"; cierra turno -> se va. Tablero de
// producción con el lote activo, prendas de la meta, día del lote, turno/pausa, horas, semana y Bombón.
// Lo que Clonexa no tiene: "—". Nunca dinero.
import {openFloor, THREE, P, API, esc, savedFor} from '/admin-v2plus/oficina/mixamo.js';

export function open(o) {
  const T = P.TALLER, {W: RW, D: RD, WALL: WH} = T.ROOM, PINK = 0xdb2777;
  return openFloor(o, {title: o.floor.name, room: T.ROOM, camera: T.CAMERA, exposure: .8, bloom: [.25, .4, .98], cls: 'taller',
    liveUrl: `${API}/pisos/${o.floor.company_id}/vivo`, models: P.CHARACTERS, clips: ['Idle', 'Walking', 'Typing', 'Sitting', 'Sitting_Drinking', 'Sitting_Talking', 'Talking'],
    async build(A) {
      const {mesh, flat, M, glow, tex, RoundedBoxGeometry: RB, S} = A;
      // taller: piso de concreto claro, paredes claras con franja de la marca, ventanales
      const fl = flat(new THREE.PlaneGeometry(RW, RD), M(0xcfcac6, {map: tex('piso_diff.webp', [5, 4]), normalMap: tex('piso_nor_gl.webp', [5, 4], false), roughness: .55})); fl.rotation.x = -Math.PI / 2;
      const wall = M(0xcfc6cb, {roughness: .9}); mesh(new THREE.BoxGeometry(RW, WH, .2), wall, 0, WH / 2, -RD / 2 - .1); mesh(new THREE.BoxGeometry(.2, WH, RD), wall, -RW / 2 - .1, WH / 2, 0);
      const brand = new THREE.Color((o.floor.brand && o.floor.brand.uniform) || PINK);
      mesh(new THREE.BoxGeometry(RW, .18, .04), M(brand, {roughness: .5}), 0, 1.0, -RD / 2 + .01); mesh(new THREE.BoxGeometry(.04, .18, RD), M(brand, {roughness: .5}), -RW / 2 + .01, 1.0, 0);
      flat(new THREE.BoxGeometry(RW + .4, .25, RD + .4), M(0x0d0a10, {metalness: .5, roughness: .4}), 0, -.13, 0); flat(new THREE.BoxGeometry(RW + .42, .04, .04), glow(0xec4899, 3), 0, -.02, RD / 2 + .2);
      for (let i = 0; i < 4; i++) { const x = -6 + i * 4; flat(new THREE.PlaneGeometry(2.6, 1.3), new THREE.MeshBasicMaterial({color: 0x9fb8d8}), x, 2.35, -RD / 2 + .02); mesh(new THREE.BoxGeometry(2.7, .06, .06), M(0x222222), x, 1.68, -RD / 2 + .04); mesh(new THREE.BoxGeometry(.05, 1.3, .05), M(0x222222), x, 2.35, -RD / 2 + .04); }
      // máquinas de coser (una por persona que puede trabajar en producción, de 6 a 12)
      const tableTop = M(0x7a5a3e, {roughness: .5}), iron = M(0x1c1c20, {metalness: .7, roughness: .35}), machineM = M(0xece6dc, {roughness: .35});
      const lampOn = glow(0x4ade80, 5), lampOff = M(0x333333), seatM = M(0x3a2a35);
      const CLOTH = [0xf9a8d4, 0xc4b5fd, 0xfecaca, 0xfde68a].map(c => M(c, {side: THREE.DoubleSide, roughness: .95})), SPOOL = [0xec4899, 0x8b5cf6, 0xf59e0b, 0x22c55e].map(c => M(c));
      const machinesG = new THREE.Group(); S.add(machinesG); let MACH = [];
      function buildMachines(n) {
        while (machinesG.children.length) machinesG.remove(machinesG.children[0]); MACH.forEach(m => A.dropTag(m.tag));
        A.archItems.splice(0, A.archItems.length);
        MACH = P.machinePositions(n).map((p0, k) => {
          const [x, z, r] = A.archPos('maquina:' + k, p0);
          const g = new THREE.Group(); g.position.set(x, 0, z); g.rotation.y = r; machinesG.add(g);
          mesh(new RB(1.25, .05, .7, 2, .02), tableTop, 0, .75, 0, g); [[-.56, -.28], [.56, -.28], [-.56, .28], [.56, .28]].forEach(([a, b]) => mesh(new THREE.BoxGeometry(.04, .75, .04), iron, a, .375, b, g)); mesh(new THREE.BoxGeometry(1.1, .03, .03), iron, 0, .15, .28, g);
          mesh(new RB(.58, .15, .24, 2, .05), machineM, .06, .85, -.05, g); mesh(new RB(.16, .36, .22, 2, .05), machineM, .28, 1.05, -.05, g); mesh(new RB(.52, .14, .2, 2, .06), machineM, .07, 1.25, -.05, g);
          mesh(new THREE.CylinderGeometry(.06, .06, .035, 20), iron, .38, 1.06, .08, g).rotation.x = Math.PI / 2; mesh(new THREE.CylinderGeometry(.008, .008, .16, 6), iron, -.14, 1.1, -.05, g);
          mesh(new THREE.CylinderGeometry(.03, .03, .06, 12), SPOOL[k % 4], .26, 1.36, -.05, g);
          const cloth = mesh(new THREE.PlaneGeometry(.55, .42), CLOTH[k % 4], -.18, .78, .05, g); cloth.rotation.x = -Math.PI / 2; cloth.rotation.z = .2;
          const lamp = mesh(new THREE.SphereGeometry(.03, 10, 8), lampOff, -.2, 1.2, .06, g);
          const c = new THREE.Group(); c.position.set(0, 0, .68); g.add(c); mesh(new RB(.42, .05, .4, 2, .02), seatM, 0, .46, 0, c); mesh(new RB(.4, .4, .04, 2, .02), seatM, 0, .72, .18, c);
          [[-.18, -.16], [.18, -.16], [-.18, .16], [.18, .16]].forEach(([a, b]) => mesh(new THREE.CylinderGeometry(.012, .012, .46, 6), iron, a, .23, b, c));
          const at = A.at(x, .8, z), m = {x, z, r, lamp, tag: A.tag(at, '<span class="off">Máquina libre</span>', 'mesa off', .1, true)};
          const hit = new THREE.Mesh(A.track(new THREE.BoxGeometry(1.3, 1.4, 1.4)), A.hitM); hit.position.set(0, .7, .3); g.add(hit);
          A.archItems.push({key: 'maquina:' + k, label: 'máquinas', pick: [hit], turn: true, get: () => [m.x, m.z, m.r],
            set: (nx, nz, nr) => { m.x = nx; m.z = nz; m.r = nr; g.position.set(nx, 0, nz); g.rotation.y = nr; at.position.set(nx, .8, nz); }});
          return m;
        });
        R.shadowMap.needsUpdate = true;
      }
      const R = A.R;
      A.zoneTag('Producción', -3.2, -.3);
      // corte y lotes
      mesh(new RB(3.6, .08, 1.6, 2, .03), M(0xe8e2d6, {roughness: .6}), 5.4, .88, -3.6); mesh(new THREE.BoxGeometry(3.4, .84, 1.4), M(0x5b4636), 5.4, .42, -3.6);
      for (let i = 0; i < 4; i++) { const r = mesh(new THREE.CylinderGeometry(.13, .13, 1.5, 20), M([0xf472b6, 0xc084fc, 0xfda4af, 0xfde68a][i], {roughness: .95}), 4.1 + i * .85, 1.06, -3.6); r.rotation.z = Math.PI / 2; }
      mesh(new THREE.BoxGeometry(.6, .01, .02), M(0x888888), 6.6, .93, -3.2); A.zoneTag('Corte', 5.4, -1.9);
      const shelf = M(0x3a3a40, {metalness: .6, roughness: .4});
      for (let s = 0; s < 3; s++) { mesh(new THREE.BoxGeometry(4.2, .05, .6), shelf, 5.6, .4 + s * .75, -5.55);
        for (let i = 0; i < 6; i++) { const c = [0xf9a8d4, 0xddd6fe, 0xfecaca, 0xfde68a, 0xbbf7d0, 0xbfdbfe][(i + s) % 6]; if ((i + s) % 3) mesh(new RB(.5, .38, .45, 2, .04), M(0xc8a27a, {roughness: .9}), 3.8 + i * .7, .62 + s * .75, -5.55); else { const r = mesh(new THREE.CylinderGeometry(.16, .16, .5, 16), M(c, {roughness: .95}), 3.8 + i * .7, .6 + s * .75, -5.55); r.rotation.z = Math.PI / 2; } } }
      [3.5, 7.7].forEach(x => mesh(new THREE.BoxGeometry(.05, 2.2, .6), shelf, x, 1.1, -5.55));
      // percheros "Listo para Bombón"
      for (let i = 0; i < 2; i++) { const x = 4.3 + i * 2.2, z = -.6; mesh(new THREE.CylinderGeometry(.015, .015, 1.6, 8), iron, x - .8, .8, z); mesh(new THREE.CylinderGeometry(.015, .015, 1.6, 8), iron, x + .8, .8, z); mesh(new THREE.CylinderGeometry(.012, .012, 1.6, 8), iron, x, 1.6, z).rotation.z = Math.PI / 2;
        for (let k = 0; k < 7; k++) { const p = mesh(new THREE.BoxGeometry(.06, .75, .42), M([0xdb2777, 0xbe185d, 0xf9a8d4, 0x9d174d][k % 4], {roughness: .9}), x - .65 + k * .21, 1.18, z); p.rotation.y = .15; } }
      const rackTag = A.tag(A.at(5.4, .05, .6), 'Listo para Bombón', 'zn', 0, true);
      // tablero de producción
      const board = A.canvasScreen(4.15, 2.33, 1280, 720); A.screen(-3.2, 2.15, -RD / 2 + .08, 4.15, 2.33, board);
      // café (pausas)
      const {x: cafeX, z: cafeZ} = T.CAFE;
      const rugC = flat(new THREE.PlaneGeometry(4.2, 3.4), M(0x6b2a4a, {roughness: .95}), cafeX, .012, cafeZ); rugC.rotation.x = -Math.PI / 2;
      mesh(new RB(2.2, .95, .6, 2, .05), M(0x3a2a35), -RW / 2 + .5, .48, cafeZ + .2).rotation.y = Math.PI / 2; mesh(new RB(.4, .5, .35, 2, .04), M(0xc0c0c4, {metalness: .9, roughness: .2}), -RW / 2 + .5, 1.2, cafeZ - .3);
      const cafeChair = M(brand, {roughness: .6});
      [[cafeX, cafeZ - .4], [cafeX + 1.6, cafeZ + .9]].forEach(([x, z]) => { mesh(new THREE.CylinderGeometry(.45, .45, .04, 28), M(0xf4f1ea, {roughness: .3}), x, .74, z); mesh(new THREE.CylinderGeometry(.04, .04, .72, 10), iron, x, .36, z);
        A.point(0xffc08a, 1.2, 3, x, 2.3, z); flat(new THREE.SphereGeometry(.06, 10, 8), glow(0xffc27a, 5), x, 2.35, z);
        [[0, -.62, 0], [0, .62, Math.PI]].forEach(([a, b, r]) => { const c = new THREE.Group(); c.position.set(x + a, 0, z + b); c.rotation.y = r; S.add(c); mesh(new RB(.42, .05, .4, 2, .02), cafeChair, 0, .46, 0, c); mesh(new RB(.4, .4, .04, 2, .02), cafeChair, 0, .72, .18, c);
          [[-.18, -.16], [.18, -.16], [-.18, .16], [.18, .16]].forEach(([u, v]) => mesh(new THREE.CylinderGeometry(.012, .012, .46, 6), iron, u, .23, v, c)); }); });
      A.zoneTag('Café · pausas', cafeX + .5, cafeZ + 1.9);
      // AMBIENTE (decorativo): plantas
      [[8.3, 4.8], [-8.3, -0.4]].forEach(([x, z], j) => { const g = new THREE.Group(); g.position.set(x, 0, z); S.add(g); mesh(new THREE.CylinderGeometry(.3, .24, .55, 20), M(0xf4f1ea), 0, .28, 0, g);
        for (let i = 0; i < 8; i++) { const l = mesh(new THREE.SphereGeometry(.2 + ((i * 37 + j) % 10) / 100, 10, 8), M(0x2f7a46, {roughness: .8}), (((i * 13) % 10) / 10 - .5) * .4, .75 + ((i * 29) % 10) / 16, (((i * 7) % 10) / 10 - .5) * .4, g); l.scale.y = 1.4; } });
      // luces (día de taller, como la aprobada)
      S.add(new THREE.AmbientLight(0xfff4f8, .45)); S.add(new THREE.HemisphereLight(0xffffff, 0x4a3a40, .3));
      const key = new THREE.DirectionalLight(0xfff6ee, 1.5); key.position.set(5, 12, 8); key.castShadow = true; key.shadow.mapSize.set(2048, 2048); Object.assign(key.shadow.camera, {left: -11, right: 11, top: 8, bottom: -8}); key.shadow.camera.updateProjectionMatrix(); key.shadow.bias = -.0005; S.add(key);
      for (let r = 0; r < 2; r++) { flat(new THREE.BoxGeometry(10.4, .05, .12), glow(0xfff2e0, 2.5), -3.2, 2.7, -3.4 + r * 2.6); A.point(0xfff0e0, 2.2, 6, -3.2, 2.5, -3.4 + r * 2.6); }

      const PEOPLE = new Map(); let seats = new Map(); let nMach = 0; let rep = null;
      const door = [8.2, 5.4];
      function drawBoard(snap) {
        const m = P.boardModel(snap.board); const cut = A.clipText;
        board.draw(m, (x, w, h) => {
          const g = x.createLinearGradient(0, 0, w, h); g.addColorStop(0, '#1d0f1c'); g.addColorStop(1, '#2d0a1f'); x.fillStyle = g; x.fillRect(0, 0, w, h);
          x.fillStyle = '#fff'; x.font = '800 48px Inter,sans-serif'; x.fillText(cut(`${o.floor.name} · Producción de hoy`, 34), 36, 66); x.fillStyle = '#ec4899'; x.fillRect(36, 86, w - 72, 3);
          x.fillStyle = '#f9a8d4'; x.font = '700 28px Inter,sans-serif'; x.fillText('LOTE ACTIVO', 36, 140); x.fillStyle = '#fff'; x.font = '800 46px Inter,sans-serif'; x.fillText(cut(m.lot, 40), 36, 194);
          x.fillStyle = '#cbbfd6'; x.font = '500 30px Inter,sans-serif'; x.fillText(`${m.progress} · ${m.day}`, 36, 236);
          x.fillStyle = 'rgba(255,255,255,.12)'; x.fillRect(36, 256, w * .55, 22); if (m.percent != null) { x.fillStyle = '#22c55e'; x.fillRect(36, 256, w * .55 * Math.min(1, m.percent / 100), 22); }
          x.fillStyle = '#fff'; x.font = '800 30px Inter,sans-serif'; x.fillText(m.percent != null ? `${m.percent} %` : P.NO, w * .55 + 52, 277);
          const C = ['#22c55e', '#f59e0b', '#a78bfa', '#ec4899'];
          m.kpis.forEach(([v, t], i) => { const X = 36 + i * ((w - 72) / 4); x.fillStyle = 'rgba(255,255,255,.06)'; x.fillRect(X, 320, (w - 72) / 4 - 16, 150); x.fillStyle = C[i]; x.font = '800 54px Inter,sans-serif'; x.fillText(v, X + 20, 395); x.fillStyle = '#cbbfd6'; x.font = '500 26px Inter,sans-serif'; x.fillText(t, X + 20, 440); });
          x.fillStyle = '#f9a8d4'; x.font = '700 26px Inter,sans-serif'; x.fillText('PRODUCCIÓN DE LA SEMANA', 36, 520);
          if (!m.week) { x.fillStyle = '#cbbfd6'; x.font = '500 26px Inter,sans-serif'; x.fillText('sin datos', 36, 600); }
          else { const max = Math.max(1, ...m.week.map(d => d.n || 0)); m.week.forEach((d, i) => { const X = 36 + i * 82, v = d.n || 0, hh = 140 * v / max; x.fillStyle = d.n ? '#ec4899' : 'rgba(255,255,255,.1)'; x.fillRect(X, h - 40 - hh, 56, hh + 4); x.fillStyle = '#cbbfd6'; x.font = '500 20px Inter,sans-serif'; x.fillText(d.d, X + 20, h - 12); if (d.n) { x.fillStyle = '#fff'; x.fillText(String(d.n), X + 14, h - 48 - hh); } }); }
          x.fillStyle = '#fff'; x.font = '700 26px Inter,sans-serif'; x.fillText(m.sent, w * .5, 560); x.fillText(m.next, w * .5, 610);
        });
        A.setTag(rackTag, esc(m.rack), 'zn');
      }
      function cfgFor(p) { return P.personCfg(p.key, p.first, savedFor(o, 'staff', p.key, p.uniform || 'costura'), {}); }
      function machineSpot(i) { const m = MACH[i], r = m.r || 0; return [m.x + Math.sin(r) * .66, m.z + Math.cos(r) * .66, Math.PI + r]; }
      function cafeSpot(i) { return T.CAFE_SEATS[i % T.CAFE_SEATS.length]; }
      function apply(snap, prev, first) {
        if (snap.machines !== nMach) { nMach = snap.machines; buildMachines(nMach); seats = new Map(); }
        drawBoard(snap);
        A.chip(`${snap.board && snap.board.on_shift != null ? snap.board.on_shift : P.NO} en turno`, true);
        if (!A.peopleOk()) return;
        const people = snap.people || [];
        const prevSeat = new Map([...PEOPLE.entries()].filter(([, s]) => s.where === 'maq').map(([k, s]) => [k, s.idx]));
        const plan = P.assignMachines(prevSeat, people, nMach); seats = plan.seat;
        const seen = new Set(); let cafeI = 0;
        for (const p of people) {
          seen.add(p.key);
          const where = p.status === 'paused' ? 'cafe' : plan.seat.has(p.key) ? 'maq' : 'pie';
          const idx = where === 'maq' ? plan.seat.get(p.key) : where === 'cafe' ? cafeI++ : 0;
          const spot = where === 'maq' ? machineSpot(idx) : where === 'cafe' ? cafeSpot(idx) : [T.CUT[0] - 1.2 - idx * .6, T.CUT[1], Math.PI];
          const clip = where === 'maq' ? 'Typing' : where === 'cafe' ? 'Sitting_Drinking' : 'Idle';
          const tg = P.sewerTag(p);
          let s = PEOPLE.get(p.key);
          if (!s) {
            const per = A.makePerson({...cfgFor(p), kind: 'personal', info: {name: p.label, role: o.floor.name, task: tg.small}});
            s = {p: per, where, idx}; PEOPLE.set(p.key, s); per.tag = A.tag(per.g, '', '', 1.5);
            if (first) A.sitAt(per, spot, clip); else A.arrive(per, door, [spot[0], spot[1]], () => A.sitAt(per, spot, clip));
          } else if (s.where !== where || s.idx !== idx) {
            s.where = where; s.idx = idx; A.goTo(s.p, [spot[0], spot[1]], () => A.sitAt(s.p, spot, clip));
          }
          s.p.info = {name: p.label, role: o.floor.name, task: tg.small};
          A.setTag(s.p.tag, A.tagHtml(tg.cls === 'pausa' ? 'wait' : 'work', tg.text, tg.small), tg.cls);
          s.p.tag.dy = where === 'maq' || where === 'cafe' ? 1.5 : 1.95;
        }
        for (const [k, s] of PEOPLE) if (!seen.has(k)) { PEOPLE.delete(k); A.leave(s.p, door); }
        MACH.forEach((m, i) => { const busy = [...plan.seat.values()].includes(i); m.lamp.material = busy ? lampOn : lampOff; m.tag.hidden = busy; });
        if (!rep) { rep = A.makePerson({...P.repCfg(savedFor(o, 'rep', 'rep')), kind: 'rep', info: {name: 'Representante', role: o.floor.name}}); A.sitAt(rep, [7.4, 4.0, -.5], 'Talking'); rep.tag = A.tag(rep.g, '', 'rep', 1.95); }
        A.setTag(rep.tag, A.tagHtml('rep', 'Representante', P.repTaller(snap)), 'rep');
      }
      return {apply, key, reset() { PEOPLE.clear(); rep = null; }};
    }});
}
