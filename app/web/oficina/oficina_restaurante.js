// Oficina 3D · piso aprobado ASADERO EL SOCIO · restaurante (asadero.html / asadero.png). Interno de Clonexa, solo Admin V2.
// Datos REALES (copia viva, plantilla restaurante): mesas reales del Asadero (QR activo: bombillito verde + sombreado
// + etiqueta, como el bar; libre: apagada), platos en las mesas con pedidos abiertos, "Comandas en cocina" con su
// tiempo, Domicilios (en cocina / en camino / entregado, barrio si existe), mesero "Llevando pedido · Mesa N" al
// entregarse un pedido real, domiciliario que sale en la moto, caja y cocina con su personal en turno.
// AMBIENTE (decorativo, marcado): los clientes sentados en las mesas con QR activo. Nunca dinero.
import {openFloor, THREE, P, API, esc, savedFor} from '/admin-v2plus/oficina/mixamo.js';

export function open(o) {
  const RT = P.RESTAURANTE, {W: RW, D: RD, WALL: WH} = RT.ROOM, ORANGE = 0xea580c;
  return openFloor(o, {title: o.floor.name, room: RT.ROOM, camera: RT.CAMERA, exposure: .85, bloom: [.3, .4, .96], cls: 'restaurante',
    liveUrl: `${API}/pisos/${o.floor.company_id}/vivo`, route: P.route, models: P.CHARACTERS,
    tableInfo: (snap, label) => P.tableInfo(snap, label),
    clips: ['Idle', 'Walking', 'Bartending', 'Talking', 'Sitting', 'Sitting_Talking', 'Sitting_Drinking', 'Sitting_Laughing'],
    async build(A) {
      const {mesh, flat, M, glow, tex, RoundedBoxGeometry: RB, S} = A;
      const fl = flat(new THREE.PlaneGeometry(RW, RD), M(0xb8653f, {roughness: .7})); fl.rotation.x = -Math.PI / 2;
      const grout = M(0x6b3520);
      for (let i = -RW / 2; i <= RW / 2; i += .6) { const l = flat(new THREE.PlaneGeometry(.015, RD), grout, i, .002, 0); l.rotation.x = -Math.PI / 2; }
      for (let i = -RD / 2; i <= RD / 2; i += .6) { const l = flat(new THREE.PlaneGeometry(RW, .015), grout, 0, .002, i); l.rotation.x = -Math.PI / 2; }
      mesh(new THREE.BoxGeometry(RW, WH, .2), M(0xb9a090, {map: tex('pared_diff.webp', [5, 1.2]), normalMap: tex('pared_nor_gl.webp', [5, 1.2], false), roughness: .9}), 0, WH / 2, -RD / 2 - .1);
      mesh(new THREE.BoxGeometry(.2, WH, RD), M(0xd8c8b8, {roughness: .9}), -RW / 2 - .1, WH / 2, 0);
      mesh(new THREE.BoxGeometry(RW, 1.0, .04), M(0x5b3a26, {map: tex('madera_diff.webp', [6, 1])}), 0, .5, -RD / 2 + .01);
      flat(new THREE.BoxGeometry(RW + .4, .25, RD + .4), M(0x0d0a10, {metalness: .5, roughness: .4}), 0, -.13, 0); flat(new THREE.BoxGeometry(RW + .42, .04, .04), glow(0xf97316, 3), 0, -.02, RD / 2 + .2);
      // cocina abierta con parrilla encendida
      const steel = M(0xb8b8bd, {metalness: .9, roughness: .25});
      mesh(new THREE.BoxGeometry(6.6, .95, .8), steel, -5.0, .475, -5.0); mesh(new THREE.BoxGeometry(2.6, .08, .7), M(0x111111, {metalness: .6}), -6.4, .98, -5.0);
      flat(new THREE.BoxGeometry(2.4, .04, .55), glow(0xff5a1f, 4), -6.4, 1.0, -5.0);
      for (let i = 0; i < 7; i++) { const m = mesh(new THREE.CylinderGeometry(.05, .05, .45, 8), M(0x7c2d12, {roughness: .6}), -7.4 + i * .33, 1.07, -5.0); m.rotation.z = Math.PI / 2; }
      mesh(new THREE.BoxGeometry(3.0, 1.0, 1.0), M(0x2a2a2e, {metalness: .7, roughness: .35}), -6.4, 2.8, -5.2);
      const fire = A.point(0xff6a2a, 6, 5, -6.4, 1.7, -4.6);
      // pase con platos
      mesh(new THREE.BoxGeometry(6.6, .06, .5), M(0x3a2418, {map: tex('madera_diff.webp', [2, 1])}), -5.0, 1.2, -3.9); mesh(new THREE.BoxGeometry(6.6, 1.2, .08), M(0x6b4a33), -5.0, .6, -3.7);
      const plateM = M(0xffffff), foodM = M(0x8b4513, {roughness: .8}), foodM2 = M(0xa0522d, {roughness: .8});
      const passG = new THREE.Group(); S.add(passG);
      const kitchenScreen = A.canvasScreen(3.0, 1.25, 1024, 560); A.screen(-2.0, 2.2, -RD / 2 + .07, 3.0, 1.25, kitchenScreen);
      A.zoneTag('Cocina y parrilla', -5, -2.9);
      // salón: mesas reales (configuración del Asadero)
      const wood = M(0x8a5a36, {map: tex('madera_diff.webp', [1, 1]), roughness: .45}), chairM = M(0x5b3a26), legM = M(0x222222), shadeM = M(0x2a1a10, {side: THREE.DoubleSide});
      const bulbOn = glow(0x4ade80, 3.5), bulbOff = M(0x2a2a2a);
      const sc0 = document.createElement('canvas'); sc0.width = sc0.height = 256;
      { const x = sc0.getContext('2d'); const g = x.createRadialGradient(128, 128, 0, 128, 128, 128); g.addColorStop(0, 'rgba(74,222,128,1)'); g.addColorStop(.6, 'rgba(74,222,128,.35)'); g.addColorStop(1, 'rgba(74,222,128,0)'); x.fillStyle = g; x.fillRect(0, 0, 256, 256); }
      const softM = A.track(new THREE.MeshBasicMaterial({map: A.track(new THREE.CanvasTexture(sc0)), transparent: true, opacity: .2, depthWrite: false, blending: THREE.AdditiveBlending}));
      const tablesG = new THREE.Group(); S.add(tablesG); const TABLES = new Map(); let layoutKey = '';
      const LAMPS = []; for (let i = 0; i < 6; i++) LAMPS.push(A.point(0x9dffc4, 0, 3, 0, -10, 0));
      function buildTables(labels) {
        const k = labels.join('|'); if (k === layoutKey) return; layoutKey = k;
        for (const t of TABLES.values()) { A.dropTag(t.tag); t.guests.splice(0).forEach(A.dropPerson); }
        TABLES.clear(); while (tablesG.children.length) tablesG.remove(tablesG.children[0]);
        for (let i = A.PICK.length - 1; i >= 0; i--) if (A.PICK[i].userData.table) A.PICK.splice(i, 1);
        const lay = P.layoutTables(labels);
        for (const {label, pos: [x, z]} of lay.tables) {
          mesh(new RB(1.1, .06, 1.1, 2, .02), wood, x, .75, z, tablesG); mesh(new THREE.CylinderGeometry(.05, .06, .73, 10), legM, x, .37, z, tablesG);
          [[0, -.75, 0], [0, .75, Math.PI], [-.75, 0, Math.PI / 2], [.75, 0, -Math.PI / 2]].forEach(([a, b, r]) => { const c = new THREE.Group(); c.position.set(x + a, 0, z + b); c.rotation.y = r; tablesG.add(c);
            mesh(new RB(.44, .05, .42, 2, .02), chairM, 0, .46, 0, c); mesh(new RB(.42, .42, .04, 2, .02), chairM, 0, .72, .19, c); [[-.19, -.17], [.19, -.17], [-.19, .17], [.19, .17]].forEach(([u, v]) => mesh(new THREE.CylinderGeometry(.015, .015, .46, 6), legM, u, .23, v, c)); });
          mesh(new THREE.CylinderGeometry(.005, .005, .8, 4), legM, x, 2.95, z, tablesG); mesh(new THREE.ConeGeometry(.2, .18, 20, 1, true), shadeM, x, 2.55, z, tablesG);
          const bulb = mesh(new THREE.SphereGeometry(.06, 10, 8), bulbOff, x, 2.47, z, tablesG);
          const soft = new THREE.Mesh(A.track(new THREE.CircleGeometry(1.2, 40)), softM); soft.rotation.x = -Math.PI / 2; soft.position.set(x, .013, z); soft.visible = false; tablesG.add(soft);
          const plates = new THREE.Group(); tablesG.add(plates);
          [0, 1].forEach(j => { mesh(new THREE.CylinderGeometry(.13, .13, .02, 20), plateM, x - .2 + j * .4, .79, z, plates); mesh(new THREE.SphereGeometry(.06, 10, 8), foodM2, x - .2 + j * .4, .82, z, plates); }); plates.visible = false;
          const hit = new THREE.Mesh(A.track(new THREE.CylinderGeometry(.75, .75, 1, 12)), A.hitM); hit.position.set(x, .5, z); hit.userData.table = label; tablesG.add(hit); A.PICK.push(hit);
          TABLES.set(label, {x, z, bulb, soft, plates, guests: [], tag: A.tag(A.at(x, .78, z), '', 'mesa off', .12, true)});
        }
        if (lay.overflow) A.warn(`${lay.overflow} mesas sin puesto en el plano`);
      }
      A.zoneTag('Salón', -.6, 6.2);
      // caja y domicilios
      mesh(new RB(2.6, 1.05, .8, 2, .04), M(0x3a2418, {map: tex('madera_diff.webp', [2, 1])}), 6.2, .52, -2.0); mesh(new THREE.BoxGeometry(2.62, .04, .82), M(0x1a1a1a, {metalness: .5, roughness: .2}), 6.2, 1.06, -2.0);
      mesh(new THREE.BoxGeometry(.4, .3, .3), M(0x222222), 5.6, 1.24, -2.0); mesh(new THREE.BoxGeometry(.35, .02, .25), M(0x111111), 6.5, 1.09, -2.0);
      const delScreen = A.canvasScreen(2.6, 1.15, 1024, 500); A.screen(6.2, 2.3, -RD / 2 + .07, 2.6, 1.15, delScreen);
      const motos = [[6.6, 2.6], [7.9, 2.6]].map(([x, z]) => { const g = new THREE.Group(); g.position.set(x, 0, z); g.rotation.y = Math.PI / 2; S.add(g);
        mesh(new RB(1.5, .34, .34, 2, .12), M(0xdc2626, {metalness: .4, roughness: .35}), 0, .62, 0, g); [-.6, .6].forEach(u => mesh(new THREE.TorusGeometry(.27, .08, 10, 20), M(0x111111), u, .3, 0, g));
        mesh(new RB(.46, .46, .46, 2, .04), M(ORANGE), -.45, 1.04, 0, g); mesh(new THREE.CylinderGeometry(.02, .02, .5, 6), M(0xcccccc, {metalness: .9}), .55, .95, 0, g); return {g, x0: x, z0: z}; });
      A.zoneTag('Caja y domicilios', 6.6, 4.6);
      [[8.4, -5.2], [-8.4, 5.4]].forEach(([x, z], j) => { const g = new THREE.Group(); g.position.set(x, 0, z); S.add(g); mesh(new THREE.CylinderGeometry(.3, .24, .55, 20), M(0x8a4a2a), 0, .28, 0, g);
        for (let i = 0; i < 8; i++) { const l = mesh(new THREE.SphereGeometry(.2 + ((i * 37 + j) % 10) / 100, 10, 8), M(0x2f7a46, {roughness: .8}), (((i * 13) % 10) / 10 - .5) * .4, .75 + ((i * 29) % 10) / 16, (((i * 7) % 10) / 10 - .5) * .4, g); l.scale.y = 1.4; } });
      S.add(new THREE.AmbientLight(0xfff1e6, .45)); S.add(new THREE.HemisphereLight(0xfff4e6, 0x3a2418, .3));
      const key = new THREE.DirectionalLight(0xffefe0, 1.4); key.position.set(5, 12, 8); key.castShadow = true; key.shadow.mapSize.set(2048, 2048); Object.assign(key.shadow.camera, {left: -11, right: 11, top: 8, bottom: -8}); key.shadow.camera.updateProjectionMatrix(); key.shadow.bias = -.0005; S.add(key);

      function drawKitchen(snap) {
        const items = (snap.kitchen || []).slice(0, 4).map(k => ({l: k.label, d: k.detail, m: k.minutes, kind: k.kind}));
        kitchenScreen.draw({items, n: snap.kitchen_count, known: snap.known && snap.known.orders}, (x, w, h, m) => {
          x.fillStyle = '#1c0f07'; x.fillRect(0, 0, w, h); x.fillStyle = '#fff'; x.font = '800 44px Inter,sans-serif'; x.fillText(`Comandas en cocina · ${m.known === false ? P.NO : m.n || 0}`, 30, 62);
          if (m.known === false) { x.fillStyle = '#cbbfd6'; x.font = '500 32px Inter,sans-serif'; x.fillText('sin datos', 30, 160); return; }
          if (!m.items.length) { x.fillStyle = '#cbbfd6'; x.font = '500 32px Inter,sans-serif'; x.fillText('Sin comandas en cocina', 30, 160); }
          m.items.forEach((k, i) => { const c = k.m == null ? '#9ca3af' : k.m >= 15 ? '#ef4444' : k.m >= 8 ? '#f59e0b' : '#22c55e';
            x.fillStyle = 'rgba(255,255,255,.07)'; x.fillRect(30, 96 + i * 112, w - 60, 96); x.fillStyle = c; x.fillRect(30, 96 + i * 112, 8, 96);
            x.fillStyle = '#fff'; x.font = '800 34px Inter,sans-serif'; x.fillText(A.clipText(k.l, 28), 56, 140 + i * 112); x.fillStyle = '#cbbfd6'; x.font = '500 28px Inter,sans-serif'; x.fillText(k.d, 56, 176 + i * 112);
            x.fillStyle = c; x.font = '800 32px Inter,sans-serif'; x.fillText(k.m == null ? P.NO : `${k.m} min`, w - 190, 150 + i * 112); });
        });
        // platos en el pase (uno por comanda, hasta 3)
        while (passG.children.length) passG.remove(passG.children[0]);
        for (let i = 0; i < Math.min(3, (snap.kitchen || []).length); i++) { mesh(new THREE.CylinderGeometry(.13, .13, .02, 20), plateM, -6.2 + i * 1.1, 1.24, -3.9, passG); mesh(new THREE.SphereGeometry(.07, 10, 8), foodM, -6.2 + i * 1.1, 1.28, -3.9, passG); }
      }
      function drawDeliveries(snap) {
        const items = (snap.deliveries || []).slice(0, 3).map(d => ({l: d.label, b: d.barrio, s: d.state}));
        delScreen.draw({items, known: snap.known && snap.known.orders}, (x, w, h, m) => {
          x.fillStyle = '#071722'; x.fillRect(0, 0, w, h); x.fillStyle = '#fff'; x.font = '800 44px Inter,sans-serif'; x.fillText('Domicilios', 30, 62);
          if (m.known === false || !m.items.length) { x.fillStyle = '#cbbfd6'; x.font = '500 32px Inter,sans-serif'; x.fillText(m.known === false ? 'sin datos' : 'Sin domicilios hoy', 30, 160); return; }
          m.items.forEach((d, i) => { const [t, c] = P.DELIVERY_LABEL[d.s] || [d.s, '#9ca3af']; x.fillStyle = 'rgba(255,255,255,.07)'; x.fillRect(30, 96 + i * 130, w - 60, 110);
            x.fillStyle = '#fff'; x.font = '800 36px Inter,sans-serif'; x.fillText(A.clipText(d.l + (d.b ? ' · ' + d.b : ''), 30), 56, 165 + i * 130); x.fillStyle = c; x.font = '700 32px Inter,sans-serif'; x.fillText(t, w - 260, 165 + i * 130); });
        });
      }
      const STAFF = new Map(); let rep = null, moto = null;
      function cfgFor(p) { return P.personCfg(p.key, p.first, savedFor(o, 'staff', p.key, p.uniform), p.uniform === 'domiciliario' ? {models: ['Ch17_nonPBR']} : {}); }
      function tableOpen(label, t, instant) {
        const T = TABLES.get(label); if (!T || T.guests.length || !A.peopleOk()) return;
        // AMBIENTE: clientes anónimos (Clonexa no guarda quiénes son); cantidad = invitados registrados o 2-3
        P.guestCast(label, P.guestsFor(t)).forEach((c, i) => { const [dx, dz, r] = P.SEATS[c.side]; const seat = [T.x + dx, T.z + dz, r];
          const per = A.makePerson({model: c.model, kind: 'cliente', info: {name: 'Cliente', role: label}}); T.guests.push(per);
          if (instant) A.sitAt(per, seat, c.clip); else A.arrive(per, RT.DOOR, [seat[0], seat[1]], () => A.sitAt(per, seat, c.clip), i * 700); });
      }
      function tableClose(label) { const T = TABLES.get(label); if (!T) return; T.guests.splice(0).forEach((g, i) => A.leave(g, RT.DOOR, 300 + i * 400)); }
      function deliver(ev) {
        const s = [...STAFF.values()].find(x => x.data.uniform === 'mesero' && !x.data.paused && !x.busy); const T = TABLES.get(ev.table); if (!s || !T) return;
        s.busy = ev.table; A.setTag(s.p.tag, A.tagHtml('work', s.data.label, `Llevando pedido · ${ev.table}`), '');
        A.goTo(s.p, RT.PASS, () => A.goTo(s.p, [T.x, T.z + 1.1], () => { s.p.g.rotation.y = Math.PI; A.play(s.p, 'Idle');
          setTimeout(() => A.goTo(s.p, [s.spot[0], s.spot[1]], () => { s.busy = null; A.sitAt(s.p, s.spot, s.clip); }), 1800); }));
      }
      function rideOut(ev) {   // domicilio real que sale: el domiciliario se va en la moto
        const m = motos[0]; if (moto) return; const d = [...STAFF.values()].find(x => x.data.uniform === 'domiciliario' && !x.data.paused);
        moto = {t: 0, m}; if (d) { d.busy = 'moto'; d.p.g.visible = false; A.setTag(d.p.tag, A.tagHtml('blue', d.data.label, `Saliendo · ${ev.label}${ev.barrio ? ' ' + ev.barrio : ''}`), ''); moto.d = d; }
      }
      function apply(snap, prev, first) {
        buildTables((snap.tables || []).map(t => t.label));
        drawKitchen(snap); drawDeliveries(snap);
        A.chip(`${(snap.tables || []).filter(t => t.open).length} mesas con QR activo`, true);
        let li = 0;
        for (const t of snap.tables || []) { const T = TABLES.get(t.label); if (!T) continue;
          T.bulb.material = t.open ? bulbOn : bulbOff; T.soft.visible = t.open; T.plates.visible = t.plates > 0;
          const tt = P.tableTag(t); A.setTag(T.tag, `${tt.dot ? '<b class="dot">●</b> ' : ''}${esc(tt.text)}`, tt.cls);
          if (t.open && li < LAMPS.length) { LAMPS[li].position.set(T.x, 2.3, T.z); LAMPS[li].intensity = 1; li++; } }
        for (; li < LAMPS.length; li++) { LAMPS[li].intensity = 0; LAMPS[li].position.set(0, -10, 0); }
        if (!A.peopleOk()) return;
        for (const e of P.diffRestaurante(prev, snap)) {
          if (e.type === 'mesa_abierta') tableOpen(e.table, (snap.tables || []).find(t => t.label === e.table), e.instant);
          else if (e.type === 'mesa_cerrada') tableClose(e.table);
          else if (e.type === 'pedido_entregado') deliver(e);
          else if (e.type === 'domicilio_sale') rideOut(e);
        }
        for (const t of snap.tables || []) { const T = TABLES.get(t.label); if (!T) continue; if (t.open && !T.guests.length) tableOpen(t.label, t, first); if (!t.open && T.guests.length) tableClose(t.label); }
        const seen = new Set(), counters = {};
        for (const p of (snap.staff || {}).people || []) {
          seen.add(p.key); const slot = p.paused ? 'pausa' : p.uniform; const idx = counters[slot] = (counters[slot] ?? -1) + 1;
          const sp = P.restStaffSpot(p.uniform, idx, p.paused); let s = STAFF.get(p.key);
          if (!s) { const per = A.makePerson({...cfgFor(p), kind: 'personal', info: {name: p.label, role: p.role}});
            s = {p: per, data: p, spot: sp.pos, clip: sp.clip}; STAFF.set(p.key, s); per.tag = A.tag(per.g, '', '', 1.95);
            if (first) A.sitAt(per, sp.pos, sp.clip); else A.arrive(per, RT.DOOR, [sp.pos[0], sp.pos[1]], () => A.sitAt(per, sp.pos, sp.clip)); }
          else if (!s.busy && (s.data.paused !== p.paused || Math.hypot(s.spot[0] - sp.pos[0], s.spot[1] - sp.pos[1]) > .3)) { s.spot = sp.pos; s.clip = sp.clip; A.goTo(s.p, [sp.pos[0], sp.pos[1]], () => A.sitAt(s.p, sp.pos, sp.clip)); }
          s.data = p; s.p.info = {name: p.label, role: p.role, task: P.restStaffTask(p, snap)};
          if (!s.busy) A.setTag(s.p.tag, A.tagHtml(p.paused ? 'wait' : 'work', p.label, P.restStaffTask(p, snap)), p.paused ? 'pausa' : '');
        }
        for (const [k, s] of STAFF) if (!seen.has(k)) { STAFF.delete(k); A.leave(s.p, RT.DOOR); }
        if (!rep) { rep = A.makePerson({...P.repCfg(savedFor(o, 'rep', 'rep')), kind: 'rep', info: {name: 'Representante', role: o.floor.name}}); A.sitAt(rep, RT.REP, 'Talking'); rep.tag = A.tag(rep.g, '', 'rep', 1.95); }
        A.setTag(rep.tag, A.tagHtml('rep', 'Representante', P.repRestaurante(snap)), 'rep');
      }
      function tick(t, dt) {
        fire.intensity = 5.4 + Math.sin(t * 9) * .5 + Math.sin(t * 23) * .3;
        if (moto) { moto.t += dt; const g = moto.m.g; g.position.z = moto.m.z0 + moto.t * 2.2;
          if (moto.t > 4) { g.position.z = moto.m.z0; if (moto.d) { moto.d.busy = null; moto.d.p.g.visible = true; } moto = null; } }
      }
      return {apply, tick, key, reset() { STAFF.clear(); TABLES.forEach(T => { T.guests.length = 0; }); rep = null; layoutKey = ''; }};
    }});
}
