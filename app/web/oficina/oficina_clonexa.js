// Oficina 3D · piso aprobado CLONEXA · futurista, grande y abierto (clonexa.html / clonexa.png). Interno, solo Admin V2.
// Datos REALES (GET /admin-v2/api/oficina/clonexa/vivo): cada agente de n8n y cada bot de Telegram de las empresas es
// un trabajador con túnica negra en su área: escribe (Typing) cuando su flujo trabaja, espera sentado, va al Lounge
// cuando no tiene trabajo y vuelve cuando su flujo corre; error = anillo/etiqueta roja; entrenamiento = azul. Un flujo
// o bot nuevo aparece solo en su área. CEO con túnica de líneas moradas, barba y pelo largo, con las aprobaciones reales.
// Pantallas: Estadísticas de las empresas · hoy (las cifras de los representantes), Tesorería (estado de cobro sin
// montos, de Facturación), calendario de contenido y mapa comercial (lista real de prospección).
import {openFloor, THREE, P, API, esc, savedFor} from '/admin-v2plus/oficina/mixamo.js';

export function open(o) {
  const CX = P.CLONEXA, {W: RW, D: RD, WALL: WH} = CX.ROOM, X0 = CX.ROOM.X0 || 0, XL = X0 - RW / 2, XR = X0 + RW / 2;
  return openFloor(o, {title: 'CLONEXA · piso principal', room: CX.ROOM, camera: CX.CAMERA, exposure: .85, bloom: [.4, .4, .97], bg: 0x04030a, cls: 'clonexa',
    liveUrl: `${API}/clonexa/vivo`, models: P.CHARACTERS.filter(n => n !== 'Ch17_nonPBR'),
    clips: ['Idle', 'Walking', 'Typing', 'Sitting', 'Talking', 'Drinking', 'Sitting_Drinking'],
    async build(A) {
      const {mesh, flat, M, glow, RoundedBoxGeometry: RB, S, track} = A;
      const fl = flat(new THREE.PlaneGeometry(RW, RD), track(new THREE.MeshPhysicalMaterial({color: 0x2a2733, roughness: .18, metalness: .2, clearcoat: 1, clearcoatRoughness: .05})), X0, 0, 0); fl.rotation.x = -Math.PI / 2;
      const gridM = glow(0x8b5cf6, .5);
      for (let x = XL + 3; x < XR; x += 3) { const l = flat(new THREE.PlaneGeometry(.025, RD), gridM, x, .004, 0); l.rotation.x = -Math.PI / 2; }
      for (let z = -RD / 2 + 3; z < RD / 2; z += 3) { const l = flat(new THREE.PlaneGeometry(RW, .025), gridM, X0, .004, z); l.rotation.x = -Math.PI / 2; }
      const wallM = track(new THREE.MeshPhysicalMaterial({color: 0x07060b, roughness: .08, metalness: .6, clearcoat: 1}));
      mesh(new THREE.BoxGeometry(RW, WH, .2), wallM, X0, WH / 2, -RD / 2 - .1); mesh(new THREE.BoxGeometry(.2, WH, RD), wallM, XL - .1, WH / 2, 0);
      const stripM = glow(0x8b5cf6, 1.6), neonM = glow(0xf20b6d, 3);
      for (let i = XL + 1.5; i < XR; i += 3) flat(new THREE.BoxGeometry(.04, WH - .4, .04), stripM, i, WH / 2, -RD / 2 + .02);
      for (let i = -RD / 2 + 1.5; i < RD / 2; i += 3) flat(new THREE.BoxGeometry(.04, WH - .4, .04), stripM, XL + .02, WH / 2, i);
      flat(new THREE.BoxGeometry(RW, .05, .05), neonM, X0, WH - .1, -RD / 2 + .03); flat(new THREE.BoxGeometry(.05, .05, RD), neonM, XL + .03, WH - .1, 0);
      flat(new THREE.BoxGeometry(RW + .6, .35, RD + .6), M(0x0a090e, {metalness: .7, roughness: .25}), X0, -.18, 0);
      flat(new THREE.BoxGeometry(RW + .62, .04, .04), glow(0xf20b6d, 4), X0, -.02, RD / 2 + .3); flat(new THREE.BoxGeometry(.04, .04, RD + .62), glow(0xf20b6d, 4), XR + .3, -.02, 0);
      // áreas sin tabiques: línea de luz de su color y su nombre
      for (const [key, [x, z, w, d, col, name, tz]] of Object.entries(CX.ZONES)) {
        const g = new THREE.Group(); g.position.set(x, .006, z); S.add(g); const m = glow(col, 1.4);
        [[0, -d / 2, w, .05], [0, d / 2, w, .05], [-w / 2, 0, .05, d], [w / 2, 0, .05, d]].forEach(([a, b, ww, dd]) => { const k = flat(new THREE.PlaneGeometry(ww, dd), m, a, 0, b, g); k.rotation.x = -Math.PI / 2; });
        A.zoneTag(name, key === 'ventas' ? -10.5 : x, tz);
      }
      A.zoneTag('Núcleo IA', 0, 1.9);
      const holoFrame = track(new THREE.MeshBasicMaterial({color: 0xd8b4fe, toneMapped: false, side: THREE.DoubleSide}));
      function holo(x, y, z, w, h, cs, ry = 0, parent = S) { const g = new THREE.Group(); g.position.set(x, y, z); g.rotation.y = ry; parent.add(g);
        flat(new THREE.PlaneGeometry(w, h), track(new THREE.MeshBasicMaterial({map: cs.texture, transparent: true, opacity: .92, toneMapped: false, side: THREE.DoubleSide})), 0, 0, 0, g);
        [[0, h / 2, w, .012], [0, -h / 2, w, .012], [-w / 2, 0, .012, h], [w / 2, 0, .012, h]].forEach(([a, b, ww, hh]) => flat(new THREE.PlaneGeometry(ww, hh), holoFrame, a, b, .002, g)); return g; }
      // pantalla de un escritorio: nombre del trabajador y lo que hizo hoy (líneas reales; sin datos -> "Sin datos")
      const COL = {work: '#22c55e', wait: '#f59e0b', err: '#ef4444', train: '#60a5fa', nodata: '#6b7280'};
      function drawDesk(cs, name, state, lines) { cs.draw({name, state, lines}, (x, w, h, m) => {
        x.fillStyle = 'rgba(16,8,30,.82)'; x.fillRect(0, 0, w, h); x.fillStyle = COL[m.state] || COL.nodata; x.fillRect(0, 0, w, 6);
        x.fillStyle = '#fff'; x.font = '700 30px Inter,sans-serif'; x.fillText(A.clipText(m.name, 26), 20, 48);
        (m.lines.length ? m.lines : ['Sin datos']).slice(0, 5).forEach((t, i) => { x.fillStyle = 'rgba(255,255,255,.1)'; x.fillRect(20, 72 + i * 44, w - 40, 34); x.fillStyle = '#e9e3f0'; x.font = '500 20px Inter,sans-serif'; x.fillText(A.clipText(t, 44), 30, 96 + i * 44); }); }); }
      const white = M(0xa8a5b2, {roughness: .55, metalness: .1}), black = M(0x0c0b10, {roughness: .3, metalness: .7}), edge = {};
      const desksG = new THREE.Group(); S.add(desksG); let DESKS = {}, deskKey = '';
      function buildDesks(counts) {
        const k = JSON.stringify(counts); if (k === deskKey) return; deskKey = k;
        while (desksG.children.length) desksG.remove(desksG.children[0]); DESKS = {};
        for (const [area, n] of Object.entries(counts)) {
          const col = CX.ZONES[area][4]; edge[col] = edge[col] || glow(col, 3);
          DESKS[area] = P.desksFor(area, n).map(([x, z, ry]) => { const g = new THREE.Group(); g.position.set(x, 0, z); g.rotation.y = ry; desksG.add(g);
            mesh(new RB(1.7, .06, .85, 3, .03), white, 0, .75, 0, g); flat(new THREE.BoxGeometry(1.6, .015, .015), edge[col], 0, .725, .42, g);
            mesh(new RB(.08, .72, .7, 2, .03), black, -.78, .36, 0, g); mesh(new RB(.08, .72, .7, 2, .03), black, .78, .36, 0, g);
            const cs = A.canvasScreen(.95, .56, 512, 300); holo(0, 1.25, -.28, .95, .56, cs, 0, g);
            const c = new THREE.Group(); c.position.set(0, 0, .75); g.add(c); mesh(new RB(.5, .08, .48, 2, .03), white, 0, .47, 0, c); mesh(new RB(.48, .6, .07, 2, .03), white, 0, .8, .22, c);
            mesh(new THREE.CylinderGeometry(.03, .03, .4, 8), black, 0, .25, 0, c); mesh(new THREE.CylinderGeometry(.26, .28, .03, 20), black, 0, .03, 0, c);
            return {x, z, ry, cs}; });
        }
        A.R.shadowMap.needsUpdate = true;
      }
      const TL = new THREE.TextureLoader();
      const sym = track(TL.load('/admin-v2plus/oficina/logo-simbolo.png')); sym.colorSpace = THREE.SRGBColorSpace;
      const wm = track(TL.load('/admin-v2plus/oficina/logo-nombre.png')); wm.colorSpace = THREE.SRGBColorSpace;
      // Dirección: tarima, escritorio de vidrio negro, gran símbolo, pantallas Aprobaciones y Empresas en vivo
      mesh(new RB(7.4, .16, 5.8, 3, .05), M(0x111016, {metalness: .6, roughness: .2}), -10, .08, -6.3); flat(new THREE.BoxGeometry(7.42, .02, .02), glow(0xa855f7, 4), -10, .16, -3.4);
      mesh(new RB(2.8, .07, 1.1, 3, .03), track(new THREE.MeshPhysicalMaterial({color: 0x0a0a10, roughness: .05, metalness: .3, clearcoat: 1})), -10, .92, -7.0);
      mesh(new RB(.12, .76, 1.0, 2, .04), M(0xf4f2f7), -11.3, .54, -7.0); mesh(new RB(.12, .76, 1.0, 2, .04), M(0xf4f2f7), -8.7, .54, -7.0);
      const apScreen = A.canvasScreen(1.1, .62, 512, 300), liveScreen = A.canvasScreen(1.1, .62, 512, 300);
      holo(-10.6, 1.5, -7.35, 1.1, .62, apScreen); holo(-9.4, 1.5, -7.35, 1.1, .62, liveScreen);
      flat(new THREE.PlaneGeometry(1.6, 2.56), track(new THREE.MeshBasicMaterial({map: sym, toneMapped: false, transparent: true})), -10, 2.35, -RD / 2 + .04);
      { const c = new THREE.Group(); c.position.set(-10, .16, -6.1); S.add(c); mesh(new RB(.7, .12, .65, 3, .05), M(0x1b1426), 0, .5, 0, c); mesh(new RB(.7, 1.0, .12, 3, .05), M(0x1b1426), 0, 1.0, .3, c); mesh(new THREE.CylinderGeometry(.3, .32, .04, 24), black, 0, .03, 0, c); }
      // Sala de juntas: cubo de vidrio, mesa ovalada y pantalla "Estadísticas de las empresas · hoy"
      const glassM = track(new THREE.MeshBasicMaterial({color: 0xe9d5ff, transparent: true, opacity: .07, depthWrite: false, side: THREE.DoubleSide}));
      [[0, -2.95, 8.6, .02], [-4.3, -6, .02, 6.1], [4.3, -6, .02, 6.1]].forEach(([x, z, w, d]) => { flat(new THREE.BoxGeometry(w, 2.8, d), glassM, x, 1.4, z); flat(new THREE.BoxGeometry(w > d ? w : .03, .03, w > d ? .03 : d), glow(0xf20b6d, 2.5), x, 2.8, z); });
      const tbl = mesh(new THREE.CylinderGeometry(1, 1, .06, 48), white, 0, .76, -6.2); tbl.scale.set(2.4, 1, .85); mesh(new THREE.CylinderGeometry(.25, .4, .72, 24), black, 0, .37, -6.2);
      const juntaChair = M(0x1b1426);
      for (let i = 0; i < 5; i++) for (const s of [-1, 1]) { const a = (i - 2) * .42; const x = Math.sin(a) * 2.9, z = -6.2 + s * 1.35; const c = new THREE.Group(); c.position.set(x * .95, 0, z); c.rotation.y = s > 0 ? 0 : Math.PI; S.add(c);
        mesh(new RB(.5, .08, .48, 2, .03), juntaChair, 0, .47, 0, c); mesh(new RB(.48, .62, .07, 2, .03), juntaChair, 0, .82, .22, c); mesh(new THREE.CylinderGeometry(.03, .03, .4, 8), black, 0, .25, 0, c); }
      const stats = A.canvasScreen(4.95, 2.32, 1280, 600); A.screen(0, 2.1, -RD / 2 + .08, 4.95, 2.32, stats);
      // Marketing: calendario de contenido real
      const calScreen = A.canvasScreen(3.0, 1.4, 1024, 480); holo(13.9, 2.3, -RD / 2 + .3, 3.0, 1.4, calScreen, -.15);
      // Núcleo IA: plataforma circular con holograma del símbolo de Clonexa
      mesh(new THREE.CylinderGeometry(2.2, 2.3, .12, 64), M(0x0d0b14, {metalness: .7, roughness: .15}), 0, .06, .4); flat(new THREE.TorusGeometry(2.2, .03, 8, 96), glow(0xf20b6d, 4), 0, .13, .4).rotation.x = Math.PI / 2;
      flat(new THREE.TorusGeometry(1.3, .02, 8, 96), glow(0xa855f7, 3), 0, .14, .4).rotation.x = Math.PI / 2;
      const holoSym = flat(new THREE.PlaneGeometry(1.15, 1.84), track(new THREE.MeshBasicMaterial({map: sym, transparent: true, opacity: .95, toneMapped: false, side: THREE.DoubleSide})), 0, 2.0, .4); holoSym.rotation.y = -.35;
      flat(new THREE.CylinderGeometry(.9, 1.25, 2.6, 48, 1, true), track(new THREE.MeshBasicMaterial({color: 0xa855f7, transparent: true, opacity: .07, side: THREE.DoubleSide, depthWrite: false})), 0, 1.4, .4);
      const wmP = flat(new THREE.PlaneGeometry(2.6, .54), track(new THREE.MeshBasicMaterial({map: wm, transparent: true, toneMapped: false, side: THREE.DoubleSide})), 0, .75, 1.9); wmP.rotation.x = -.4;
      // Ventas: mapa comercial (lista real de prospección)
      const mapScreen = A.canvasScreen(4.2, 2.0, 1024, 488); holo(XL + .3, 2.2, 5.6, 4.2, 2.0, mapScreen, Math.PI / 2);
      // Bots y operaciones: torre de servidores
      for (let i = 0; i < 4; i++) { const x = -4.6 + i * 1.0; mesh(new RB(.85, 2.6, .9, 2, .04), M(0x08080b, {metalness: .7, roughness: .25}), x, 1.3, 8.75);
        for (let k = 0; k < 10; k++) flat(new THREE.BoxGeometry(.6, .02, .02), glow(k % 3 ? 0x38bdf8 : 0xa855f7, 3), x, .4 + k * .22, 8.29); }
      // Tesorería: estado de cobro por empresa (sin montos)
      const tesScreen = A.canvasScreen(2.6, 1.3, 1024, 512); holo(5.5, 2.0, 7.9, 2.6, 1.3, tesScreen, 0);
      // Lounge
      mesh(new RB(4.2, 1.05, .8, 3, .06), M(0x111016, {metalness: .5, roughness: .25}), 11.5, .53, 8.9); flat(new THREE.BoxGeometry(4.22, .02, .02), glow(0xfb923c, 3), 11.5, 1.06, 8.5);
      const sofaM = M(0x5e5868, {roughness: .85});
      [[9.6, 3.4], [13.0, 3.4]].forEach(([x, z]) => { const g = new THREE.Group(); g.position.set(x, 0, z); S.add(g); mesh(new RB(2.2, .4, .9, 3, .12), sofaM, 0, .25, 0, g); mesh(new RB(2.2, .5, .22, 3, .1), sofaM, 0, .6, -.35, g); });
      [[9.6, 4.9], [13.0, 4.9]].forEach(([x, z]) => { mesh(new THREE.CylinderGeometry(.55, .55, .04, 32), white, x, .45, z); mesh(new THREE.CylinderGeometry(.06, .06, .43, 12), black, x, .22, z); });
      [[8.4, 8.6], [14.4, 2.6], [-14, -2], [14.2, -2.5]].forEach(([x, z], j) => { const g = new THREE.Group(); g.position.set(x, 0, z); S.add(g); mesh(new THREE.CylinderGeometry(.32, .26, .6, 20), white, 0, .3, 0, g);
        for (let i = 0; i < 9; i++) { const l = mesh(new THREE.SphereGeometry(.22 + ((i * 37 + j) % 10) / 100, 10, 8), M(0x2f7a46, {roughness: .8}), (((i * 13 + j) % 10) / 10 - .5) * .45, .8 + ((i * 29) % 10) / 14, (((i * 7 + j) % 10) / 10 - .5) * .45, g); l.scale.y = 1.4; } });
      // Innovación (nexus.html): escritorio blanco de NEXUS con dos pantallas holográficas, radar sobre pedestal,
      // pantalla grande "NEXUS · Radar de innovación" y tablero "Backlog" en la pared del fondo. Todo con datos REALES.
      const IN = CX.INNOVACION, CY = 0x22d3ee, [DX, DZ] = IN.DESK, [RX, RZ] = IN.RADAR;
      const radarScreen = A.canvasScreen(IN.SCREEN[2], IN.SCREEN[3], 1400, 620), boardScreen = A.canvasScreen(IN.BOARD[2], IN.BOARD[3], 560, 560);
      const bigG = A.screen(IN.SCREEN[0], IN.SCREEN[1], -RD / 2 + .1, IN.SCREEN[2], IN.SCREEN[3], radarScreen);
      const boardG = A.screen(IN.BOARD[0], IN.BOARD[1], -RD / 2 + .1, IN.BOARD[2], IN.BOARD[3], boardScreen);
      [[bigG, IN.SCREEN[2], IN.SCREEN[3]], [boardG, IN.BOARD[2], IN.BOARD[3]]].forEach(([g, w, h]) => {   // tocar la pantalla abre el Radar
        const hit = flat(new THREE.PlaneGeometry(w, h), A.hitM, 0, 0, .06, g); hit.userData.link = P.RADAR_LINK; A.PICK.push(hit); });
      mesh(new RB(2.0, .06, .9, 3, .03), white, DX, .75, DZ); flat(new THREE.BoxGeometry(1.9, .015, .015), glow(CY, 3), DX, .725, DZ + .45);
      mesh(new RB(.08, .72, .75, 2, .03), black, DX - .95, .36, DZ); mesh(new RB(.08, .72, .75, 2, .03), black, DX + .95, .36, DZ);
      const holoL = A.canvasScreen(.9, .53, 512, 300), holoR = A.canvasScreen(.9, .53, 512, 300);
      holo(DX - 1.25, 1.25, DZ - .25, .9, .53, holoL, .75); holo(DX + 1.25, 1.25, DZ - .25, .9, .53, holoR, -.75);
      { const c = new THREE.Group(); c.position.set(DX, 0, DZ - .72); c.rotation.y = Math.PI; S.add(c); mesh(new RB(.5, .08, .48, 2, .03), white, 0, .47, 0, c);
        mesh(new RB(.48, .6, .07, 2, .03), white, 0, .8, .22, c); mesh(new THREE.CylinderGeometry(.03, .03, .4, 8), black, 0, .25, 0, c); mesh(new THREE.CylinderGeometry(.26, .28, .03, 20), black, 0, .03, 0, c); }
      mesh(new THREE.CylinderGeometry(.6, .7, .5, 40), M(0x0c0b10, {metalness: .7, roughness: .25}), RX, .25, RZ);
      flat(new THREE.TorusGeometry(.62, .02, 8, 60), glow(CY, 4), RX, .5, RZ).rotation.x = Math.PI / 2;
      const radarTex = A.canvasScreen(1.7, 1.7, 512, 512), radarDiscs = [];
      for (let i = 0; i < 2; i++) { const d = flat(new THREE.CircleGeometry(.85, 48), track(new THREE.MeshBasicMaterial({map: radarTex.texture, transparent: true, opacity: i ? .35 : .9, toneMapped: false, side: THREE.DoubleSide, depthWrite: false})), RX, 1.15 + i * .35, RZ); d.rotation.x = -Math.PI / 2; radarDiscs.push(d); }
      flat(new THREE.CylinderGeometry(.85, .55, .7, 48, 1, true), track(new THREE.MeshBasicMaterial({color: CY, transparent: true, opacity: .07, toneMapped: false, side: THREE.DoubleSide, depthWrite: false})), RX, .85, RZ);
      const radarPt = new THREE.Group(); radarPt.position.set(RX, 1.6, RZ); S.add(radarPt); const radarTagEl = A.tag(radarPt, '', 'nx', .3);
      [[16.6, -8.9], [25.2, -3.4]].forEach(([x, z], j) => { const g = new THREE.Group(); g.position.set(x, 0, z); S.add(g); mesh(new THREE.CylinderGeometry(.3, .24, .55, 20), white, 0, .28, 0, g);
        for (let i = 0; i < 8; i++) { const l = mesh(new THREE.SphereGeometry(.2 + ((i * 31 + j) % 10) / 100, 10, 8), M(0x2f7a46, {roughness: .8}), (((i * 13 + j) % 10) / 10 - .5) * .4, .75 + ((i * 29) % 10) / 16, (((i * 7 + j) % 10) / 10 - .5) * .4, g); l.scale.y = 1.4; } });
      A.point(CY, 2.5 * .55, 6, RX, 2.6, RZ); A.point(0xa855f7, 1.6 * .55, 6, DX, 2.6, DZ);

      function drawRadar(radar) {
        const top = (radar && radar.top) || [], counts = (radar && radar.counts) || null;
        radarScreen.draw(top, (x, w, h) => { const g = x.createLinearGradient(0, 0, w, h); g.addColorStop(0, '#04141a'); g.addColorStop(1, '#140826'); x.fillStyle = g; x.fillRect(0, 0, w, h);
          x.fillStyle = '#fff'; x.font = '800 46px Inter,sans-serif'; x.fillText('NEXUS · Radar de innovación', 32, 64); x.fillStyle = '#22d3ee'; x.font = '600 26px Inter,sans-serif';
          x.fillText('Ideas del último informe · por puntaje', 32, 102); x.fillRect(32, 118, w - 64, 3);
          if (!top.length) { x.fillStyle = '#cbd5e1'; x.font = '500 34px Inter,sans-serif'; x.fillText('Sin ideas aún', 32, 200); return; }
          top.slice(0, 3).forEach((it, i) => { const y = 140 + i * 118; x.fillStyle = 'rgba(255,255,255,.06)'; x.fillRect(32, y, w - 64, 100); x.fillStyle = P.RADAR_LEVEL_COLOR[it.impacto] || '#22d3ee'; x.fillRect(32, y, 8, 100);
            x.fillStyle = '#fff'; x.font = '800 32px Inter,sans-serif'; x.fillText(A.clipText(it.titulo, 52), 58, y + 44); x.fillStyle = '#cbd5e1'; x.font = '500 26px Inter,sans-serif';
            x.fillText(`Impacto ${it.impacto} · Esfuerzo ${it.esfuerzo}${it.fecha_limite ? ` · cierra ${it.fecha_limite}` : ''} · ${it.puntaje} pts`, 58, y + 82);
            x.fillStyle = 'rgba(34,211,238,.18)'; x.fillRect(w - 300, y + 30, 240, 44); x.fillStyle = '#67e8f9'; x.font = '700 24px Inter,sans-serif'; x.fillText(A.clipText(it.estado_label || it.estado, 16), w - 284, y + 60); }); });
        boardScreen.draw(counts, (x, w, h) => { x.fillStyle = '#0b0814'; x.fillRect(0, 0, w, h); x.fillStyle = '#fff'; x.font = '800 40px Inter,sans-serif'; x.fillText('Backlog', 30, 60); x.fillStyle = '#22d3ee'; x.fillRect(30, 78, w - 60, 3);
          if (!counts) { x.fillStyle = '#cbd5e1'; x.font = '500 30px Inter,sans-serif'; x.fillText('Sin datos', 30, 150); return; }
          P.RADAR_COUNTS.forEach(([k, l, col], i) => { const y = 130 + i * 86; x.fillStyle = col; x.beginPath(); x.arc(46, y - 12, 10, 0, 7); x.fill(); x.fillStyle = '#e2e8f0'; x.font = '600 34px Inter,sans-serif'; x.fillText(l, 70, y);
            x.fillStyle = col; x.font = '800 40px Inter,sans-serif'; x.fillText(String(counts[k] || 0), w - 80, y); }); });
        const st = P.nexusState(radar), n = Math.min(12, (radar && radar.nuevas) || 0);
        radarTex.draw([n, st.cls], (x, w) => { const c = w / 2; x.strokeStyle = 'rgba(34,211,238,.9)'; x.lineWidth = 4; [.95, .7, .45, .2].forEach(r => { x.beginPath(); x.arc(c, c, c * r, 0, 7); x.stroke(); });
          x.beginPath(); x.moveTo(c, 0); x.lineTo(c, w); x.moveTo(0, c); x.lineTo(w, c); x.stroke(); const g = x.createLinearGradient(c, c, c + c * .9, c - c * .6); g.addColorStop(0, 'rgba(34,211,238,.7)'); g.addColorStop(1, 'rgba(34,211,238,0)');
          x.fillStyle = g; x.beginPath(); x.moveTo(c, c); x.arc(c, c, c * .95, -1.1, -.3); x.fill();
          for (let i = 0; i < n; i++) { const a = i * 2.39996, r = c * (.25 + ((i * 37) % 60) / 100); x.fillStyle = '#f0abfc'; x.beginPath(); x.arc(c + Math.cos(a) * r, c + Math.sin(a) * r, 12, 0, 7); x.fill(); } });
        holoL.draw(st.cls, (x, w, h) => { x.fillStyle = 'rgba(4,20,26,.85)'; x.fillRect(0, 0, w, h); x.fillStyle = '#22d3ee'; x.fillRect(0, 0, w, 6); x.fillStyle = '#fff'; x.font = '700 30px Inter,sans-serif';
          x.fillText(st.cls === 'work' ? 'Buscando fuentes' : st.cls === 'err' ? 'Último informe falló' : 'Esperando', 20, 48);
          for (let i = 0; i < 5; i++) { x.fillStyle = 'rgba(255,255,255,.1)'; x.fillRect(20, 72 + i * 40, w - 40, 26); if (st.cls === 'work') { x.fillStyle = '#22d3ee'; x.fillRect(20, 72 + i * 40, (w - 40) * (.3 + ((i * 37) % 60) / 100), 26); } } });
        holoR.draw(top.map(t => t.puntaje), (x, w, h) => { x.fillStyle = 'rgba(4,20,26,.85)'; x.fillRect(0, 0, w, h); x.fillStyle = '#22d3ee'; x.fillRect(0, 0, w, 6); x.fillStyle = '#fff'; x.font = '700 30px Inter,sans-serif'; x.fillText('Puntaje de ideas', 20, 48);
          if (!top.length) { x.fillStyle = '#cbd5e1'; x.font = '500 24px Inter,sans-serif'; x.fillText('Sin ideas aún', 20, 110); return; }
          top.slice(0, 5).forEach((t, i) => { x.fillStyle = 'rgba(255,255,255,.1)'; x.fillRect(20, 72 + i * 40, w - 40, 26); x.fillStyle = '#22d3ee'; x.fillRect(20, 72 + i * 40, (w - 40) * Math.max(.05, (t.puntaje || 0) / 100), 26); }); });
        A.setTag(radarTagEl, A.tagHtml('nx', 'Radar', P.radarTag(radar)), 'nx');
      }

      // luces (la versión aprobada, la más baja)
      S.add(new THREE.AmbientLight(0xf2eefc, .4)); S.add(new THREE.HemisphereLight(0xffffff, 0x2a2040, .3));
      const key = new THREE.DirectionalLight(0xffffff, 1.2); key.position.set(8, 18, 12); key.castShadow = true; key.shadow.mapSize.set(2048, 2048); Object.assign(key.shadow.camera, {left: -17, right: 17, top: 12, bottom: -12}); key.shadow.camera.updateProjectionMatrix(); key.shadow.bias = -.0005; S.add(key);
      [[0, .4, 0xa855f7, 6], [-10, -6, 0xa855f7, 4], [0, -6, 0xf20b6d, 4], [10, -6, 0x8b5cf6, 4], [-10.5, 5.5, 0x22c55e, 3], [-1.5, 5.5, 0x38bdf8, 3], [11, 5.5, 0xfb923c, 1.6]].forEach(([x, z, c, i]) => A.point(c, i * .55, 8, x, 3.2, z));

      function drawScreens(snap) {
        apScreen.draw(snap.approvals, (x, w, h) => { const a = snap.approvals || {}; x.fillStyle = 'rgba(16,8,30,.85)'; x.fillRect(0, 0, w, h); x.fillStyle = '#a855f7'; x.fillRect(0, 0, w, 6);
          x.fillStyle = '#fff'; x.font = '700 30px Inter,sans-serif'; x.fillText('Aprobaciones', 20, 48);
          [['Piezas por aprobar', a.pieces], ['Lote de correos', a.batch == null ? null : a.batch ? 'por aprobar' : 'ninguno'], ['Leads que respondieron', a.leads]].forEach(([t, v], i) => {
            x.fillStyle = 'rgba(255,255,255,.08)'; x.fillRect(20, 76 + i * 70, w - 40, 56); x.fillStyle = '#e9e3f0'; x.font = '500 22px Inter,sans-serif'; x.fillText(t, 34, 112 + i * 70); x.fillStyle = '#fff'; x.font = '800 26px Inter,sans-serif'; x.fillText(P.show(v), w - 150, 112 + i * 70); }); });
        const comps = snap.companies || [];
        liveScreen.draw(comps.map(c => [c.name, c.health]), (x, w, h) => { x.fillStyle = 'rgba(16,8,30,.85)'; x.fillRect(0, 0, w, h); x.fillStyle = '#f20b6d'; x.fillRect(0, 0, w, 6);
          x.fillStyle = '#fff'; x.font = '700 30px Inter,sans-serif'; x.fillText(`Empresas · en vivo · ${comps.length}`, 20, 48);
          comps.slice(0, 5).forEach((c, i) => { x.fillStyle = P.HEALTH_COLOR[c.health] || '#6b7280'; x.beginPath(); x.arc(34, 92 + i * 44, 9, 0, 7); x.fill(); x.fillStyle = '#e9e3f0'; x.font = '600 24px Inter,sans-serif'; x.fillText(A.clipText(c.name, 28), 54, 100 + i * 44); }); });
        stats.draw(comps, (x, w, h) => { const g = x.createLinearGradient(0, 0, w, h); g.addColorStop(0, '#12061f'); g.addColorStop(1, '#26071f'); x.fillStyle = g; x.fillRect(0, 0, w, h);
          x.fillStyle = '#fff'; x.font = '800 46px Inter,sans-serif'; x.fillText('Estadísticas de las empresas · hoy', 36, 64); x.fillStyle = '#f20b6d'; x.fillRect(36, 84, w - 72, 3);
          if (!comps.length) { x.fillStyle = '#cbbfd6'; x.font = '500 32px Inter,sans-serif'; x.fillText('Sin empresas registradas', 36, 180); return; }
          const cols = 2, rows = Math.min(3, Math.ceil(comps.length / cols)), ch = (h - 130) / rows - 16, accent = ['#ec4899', '#f97316', '#a855f7', '#22c55e', '#38bdf8', '#eab308'];
          comps.slice(0, cols * rows).forEach((c, i) => { const X = 36 + (i % cols) * ((w - 90) / 2 + 18), Y = 112 + Math.floor(i / cols) * (ch + 16), cw = (w - 90) / 2, col = accent[i % accent.length];
            x.fillStyle = 'rgba(255,255,255,.06)'; x.fillRect(X, Y, cw, ch); x.fillStyle = col; x.fillRect(X, Y, 8, ch);
            x.fillStyle = '#fff'; x.font = '800 32px Inter,sans-serif'; x.fillText(A.clipText(c.name, 22), X + 28, Y + 44); x.fillStyle = '#cbbfd6'; x.font = '500 22px Inter,sans-serif'; x.fillText(c.label || '', X + 28, Y + 74);
            (c.kpis || []).slice(0, 2).forEach(([k, v], j) => { x.fillStyle = j ? col : '#fff'; x.font = `800 ${rows > 2 ? 30 : 38}px Inter,sans-serif`; x.fillText(P.show(v), X + 28 + j * cw / 2, Y + ch - 34); x.fillStyle = '#cbbfd6'; x.font = '500 18px Inter,sans-serif'; x.fillText(A.clipText(k, 24), X + 28 + j * cw / 2, Y + ch - 10); });
            x.fillStyle = P.HEALTH_COLOR[c.health] || '#6b7280'; x.beginPath(); x.arc(X + cw - 30, Y + 30, 9, 0, 7); x.fill(); });
          if (comps.length > cols * rows) { x.fillStyle = '#cbbfd6'; x.font = '500 22px Inter,sans-serif'; x.fillText(`+${comps.length - cols * rows} empresas más`, w - 260, h - 14); } });
        tesScreen.draw(snap.treasury, (x, w, h, t) => { x.fillStyle = 'rgba(30,22,4,.88)'; x.fillRect(0, 0, w, h); x.fillStyle = '#fff'; x.font = '800 44px Inter,sans-serif'; x.fillText('Tesorería · cobro de cada empresa', 30, 64);
          if (!t) { x.fillStyle = '#cbbfd6'; x.font = '500 32px Inter,sans-serif'; x.fillText('Facturación: sin datos', 30, 170); return; }
          t.slice(0, 4).forEach((c, i) => { x.fillStyle = 'rgba(255,255,255,.08)'; x.fillRect(30, 100 + i * 100, w - 60, 84); x.fillStyle = '#fff'; x.font = '700 32px Inter,sans-serif'; x.fillText(A.clipText(c.name, 22), 56, 154 + i * 100);
            x.fillStyle = P.TREASURY_COLOR[c.state] || '#9ca3af'; x.fillText(c.text, w - 330, 154 + i * 100); }); });
        calScreen.draw(snap.calendar, (x, w, h, cal) => { x.fillStyle = 'rgba(20,10,40,.85)'; x.fillRect(0, 0, w, h); x.fillStyle = '#fff'; x.font = '800 40px Inter,sans-serif'; x.fillText('Calendario de contenido', 30, 60);
          if (!cal) { x.fillStyle = '#cbbfd6'; x.font = '500 30px Inter,sans-serif'; x.fillText('Sin datos de la hoja', 30, 150); return; }
          if (!cal.length) { x.fillStyle = '#cbbfd6'; x.font = '500 30px Inter,sans-serif'; x.fillText(snap.next && snap.next.fecha ? `Próxima: ${snap.next.fecha} · ${snap.next.formato || ''}` : 'Nada por aprobar', 30, 150); return; }
          cal.forEach((c, i) => { x.fillStyle = 'rgba(255,255,255,.08)'; x.fillRect(30, 90 + i * 92, w - 60, 76); x.fillStyle = '#f59e0b'; x.fillRect(30, 90 + i * 92, 8, 76);
            x.fillStyle = '#fff'; x.font = '600 28px Inter,sans-serif'; x.fillText(A.clipText(`${c.fecha} · ${c.formato || ''} ${c.tema || ''} · ${c.estado}`, 52), 56, 138 + i * 92); }); });
        mapScreen.draw(snap.map, (x, w, h, m) => { x.fillStyle = 'rgba(4,20,14,.88)'; x.fillRect(0, 0, w, h); x.strokeStyle = 'rgba(34,197,94,.18)'; x.lineWidth = 2;
          for (let i = 1; i < 8; i++) { x.beginPath(); x.moveTo(i * w / 8, 70); x.lineTo(i * w / 8, h); x.stroke(); x.beginPath(); x.moveTo(0, 70 + i * (h - 70) / 8); x.lineTo(w, 70 + i * (h - 70) / 8); x.stroke(); }
          x.fillStyle = '#fff'; x.font = '800 36px Inter,sans-serif';
          if (!m) { x.fillText('Mapa comercial', 30, 52); x.fillStyle = '#cbbfd6'; x.font = '500 28px Inter,sans-serif'; x.fillText('sin datos', 30, 150); return; }
          x.fillText(A.clipText(`Mapa comercial · ${m.zones.length ? m.zones.join(' · ') : 'sin zonas'} · ${m.count}`, 46), 30, 52);
          const C = {respondio: '#22c55e', contactado: '#f59e0b', nuevo: '#60a5fa'};
          m.points.forEach(([px, py, k]) => { x.fillStyle = C[k] || '#60a5fa'; x.beginPath(); x.arc(40 + px * (w - 80), 90 + py * (h - 120), 6, 0, 7); x.fill(); }); });
      }
      const WK = new Map(); let ceo = null, nx = null, nexus = null;
      // NEXUS: Typing cuando el Radar investiga, Sitting cuando espera, rojo si el último informe falló. Tocarlo abre el Radar.
      function applyNexus(snap) {
        const radar = snap.radar || null, st = P.nexusState(radar);
        drawRadar(radar);
        if (!A.peopleOk()) return;
        const info = {name: 'NEXUS', role: 'Innovación · Radar', task: st.text, link: P.RADAR_LINK, id: 'nexus'};
        if (!nexus) { const cfg = P.agentCfg('nexus', savedFor(o, 'agent', 'nexus')); nexus = A.makePerson({...cfg, kind: 'nexus', info});
          A.sitAt(nexus, CX.INNOVACION.SEAT, st.clip, 0); nexus.tag = A.tag(nexus.g, '', 'nx', 1.55); nexus.clip = st.clip; }
        else if (nexus.clip !== st.clip) { nexus.clip = st.clip; A.play(nexus, st.clip); }
        nexus.info = info; A.setRing(nexus, st.ring);
        A.setTag(nexus.tag, A.tagHtml(st.cls, 'NEXUS · Radar', st.text), st.ring === 'red' ? 'red' : 'nx');
      }
      const deskSeat = d => [d.x + Math.sin(d.ry) * .7, d.z + Math.cos(d.ry) * .7, d.ry + Math.PI];
      function workerName(w) { const s = savedFor(o, 'agent', w.id); return w.name || (s && s.nombre) || P.AGENT_NAME[w.id] || w.id; }
      function apply(snap, prev, first) {
        const workers = (snap.workers || []).concat([P.treasuryWorker(snap)]);
        A.chip(snap.n8n_ok ? 'n8n en vivo' : 'n8n sin datos', !!snap.n8n_ok);
        const plan = P.clonexaPlan(workers); const counts = {};
        for (const pl of plan) if (pl.desk) counts[pl.area] = Math.max(counts[pl.area] || 0, pl.deskIndex + 1);
        for (const a of Object.keys(CX.DESKS)) counts[a] = Math.max(counts[a] || 0, CX.DESKS[a].length);
        buildDesks(counts); drawScreens(snap); applyNexus(snap);
        const byId = new Map(workers.map(w => [w.id, w]));
        for (const pl of plan) { const w = byId.get(pl.id); if (pl.desk) { const d = DESKS[pl.area][pl.deskIndex]; if (d) drawDesk(d.cs, workerName(w), w.state, w.today || []); } }
        if (!A.peopleOk()) return;
        const seen = new Set();
        for (const pl of plan) {
          const w = byId.get(pl.id); seen.add(pl.id);
          const d = pl.desk ? DESKS[pl.area][pl.deskIndex] : null;
          const home = d ? deskSeat(d) : pl.stand;
          const spot = pl.lounge || home; const y = pl.lounge && /^Sitting/.test(pl.clip) ? -.05 : 0;
          let s = WK.get(pl.id);
          if (!s) { const cfg = P.agentCfg(pl.id, w.bot || w.extra ? {} : savedFor(o, 'agent', pl.id)); const per = A.makePerson({...cfg, kind: 'agente', info: {name: workerName(w), role: P.CLONEXA.ZONES[pl.area][5], task: (w.today || [])[0] || ''}});
            per.tag = A.tag(per.g, '', '', 1.5); s = {p: per, at: spot, clip: pl.clip}; WK.set(pl.id, s); A.sitAt(s.p, spot, pl.clip, y); }
          else if (Math.hypot(s.at[0] - spot[0], s.at[1] - spot[1]) > .3) { s.at = spot; s.clip = pl.clip; A.goTo(s.p, [spot[0], spot[1]], () => A.sitAt(s.p, spot, pl.clip, y)); }
          else if (s.clip !== pl.clip && !s.p.path.length) { s.clip = pl.clip; A.play(s.p, pl.clip); }
          A.setRing(s.p, pl.lounge ? null : pl.ring);
          s.p.info = {name: workerName(w), role: P.CLONEXA.ZONES[pl.area][5], task: (w.today || []).join(' · '), id: w.id};
          s.p.tag.dy = pl.lounge ? (y ? 1.55 : 2.0) : pl.stand ? 2.0 : 1.5;
          A.setTag(s.p.tag, A.tagHtml(pl.tag.cls, workerName(w), pl.tag.text), pl.ring === 'red' ? 'red' : pl.ring === 'blue' ? 'blue' : '');
        }
        for (const [k, s] of WK) if (!seen.has(k)) { WK.delete(k); A.dropPerson(s.p); }
        // CEO y Nexa Asistente presentando junto a la pantalla de estadísticas
        if (!ceo) { const cfg = P.agentCfg('director', savedFor(o, 'agent', 'director')); ceo = A.makePerson({...cfg, kind: 'agente', info: {name: cfg.name, role: 'Dirección'}});
          const [x, z, r, y] = CX.CEO; A.sitAt(ceo, [x, z, r], 'Talking', y); ceo.tag = A.tag(ceo.g, '', 'ceo', 2.1); }
        ceo.info = {name: P.agentCfg('director', savedFor(o, 'agent', 'director')).name, role: 'Dirección', task: P.ceoTag(snap), id: 'director'};
        A.setTag(ceo.tag, A.tagHtml('ceo', ceo.info.name, P.ceoTag(snap)), 'ceo');
        const asis = byId.get('asistente');
        if (!nx) { const cfg = P.agentCfg('asistente', savedFor(o, 'agent', 'asistente')); nx = A.makePerson({...cfg, kind: 'agente', info: {name: cfg.name, role: 'Sala de juntas'}});
          const [x, z, r, y] = CX.PRESENTER; A.sitAt(nx, [x, z, r], 'Talking', y); nx.tag = A.tag(nx.g, '', '', 2.05); }
        nx.info = {name: P.agentCfg('asistente', savedFor(o, 'agent', 'asistente')).name, role: 'Sala de juntas', task: (asis && asis.today || []).join(' · '), id: 'asistente'};
        A.setRing(nx, asis && asis.state === 'err' ? 'red' : null);
        A.setTag(nx.tag, A.tagHtml(asis ? asis.state : 'nodata', nx.info.name, P.presenterTag(snap)), asis && asis.state === 'err' ? 'red' : '');
      }
      function tick(t) { holoSym.rotation.y = -.35 + Math.sin(t * .4) * .25; radarDiscs[0].rotation.z = -t * .9; radarDiscs[1].rotation.z = t * .5; }
      return {apply, tick, key, reset() { WK.clear(); ceo = null; nx = null; nexus = null; }};
    }});
}
