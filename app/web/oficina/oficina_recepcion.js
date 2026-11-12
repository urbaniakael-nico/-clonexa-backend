// Oficina 3D · RECEPCIÓN con Nexa (diseño aprobado recepcion.html / recepcion.png). Interno de Clonexa, solo Admin V2.
// Planta baja: piso oscuro brillante, muro con el logo de Clonexa y neón, mostrador negro con luz morada/rosada,
// sala de espera con sofás, plantas y la pantalla "Recepción · interesados de hoy".
// NEXA recepcionista detrás del mostrador (mujer, túnica negra con líneas ROSADAS): Talking cuando atiende, Idle si no.
// Visitantes = interesados REALES de hoy (copia viva /recepcion/vivo): WhatsApp, Leads DEMO, correos y prospectos,
// demos agendadas. Nunca teléfono, correo ni nombre de la persona (el servidor ni los manda). Sin interesados:
// solo Nexa y "Sin visitas hoy". Ningún dato de ejemplo en este archivo.
import {openFloor, THREE, P, API} from '/admin-v2plus/oficina/mixamo.js';

const LOGO = '/admin-v2plus/oficina/logo-nombre.png';

export function open(o) {
  const RC = P.RECEPCION, {W: RW, D: RD, WALL: WH} = RC.ROOM;
  return openFloor(o, {title: 'Recepción', room: RC.ROOM, camera: RC.CAMERA, exposure: .85, bloom: [.35, .4, .95], cls: 'recepcion', bg: 0x050407,
    liveUrl: `${API}/recepcion/vivo`, models: P.RC_MODELS, clips: ['Idle', 'Walking', 'Sitting', 'Talking'],
    async build(A) {
      const {mesh, flat, M, glow, track, S, RoundedBoxGeometry: RB} = A;
      // piso oscuro brillante con líneas moradas
      const fl = flat(new THREE.PlaneGeometry(RW, RD), track(new THREE.MeshPhysicalMaterial({color: 0x221f28, roughness: .15, metalness: .2, clearcoat: 1}))); fl.rotation.x = -Math.PI / 2;
      for (let x = -RW / 2 + 2; x < RW / 2; x += 2) { const l = flat(new THREE.PlaneGeometry(.02, RD), glow(0x8b5cf6, .4), x, .004, 0); l.rotation.x = -Math.PI / 2; }
      // muros negros brillantes con neón morado vertical
      const wallM = track(new THREE.MeshPhysicalMaterial({color: 0x07060b, roughness: .1, metalness: .6, clearcoat: 1}));
      mesh(new THREE.BoxGeometry(RW, WH, .2), wallM, 0, WH / 2, -RD / 2 - .1); mesh(new THREE.BoxGeometry(.2, WH, RD), wallM, -RW / 2 - .1, WH / 2, 0);
      for (let i = -RW / 2 + 1.5; i < RW / 2; i += 3) flat(new THREE.BoxGeometry(.04, WH - .4, .04), glow(0x8b5cf6, 1.4), i, WH / 2, -RD / 2 + .02);
      flat(new THREE.BoxGeometry(RW + .4, .25, RD + .4), M(0x0a090e, {metalness: .6, roughness: .3}), 0, -.13, 0); flat(new THREE.BoxGeometry(RW + .42, .04, .04), glow(0xf20b6d, 4), 0, -.02, RD / 2 + .2);
      // muro del logo de Clonexa con neón rosado
      const logo = track(new THREE.TextureLoader().load(LOGO)); logo.colorSpace = THREE.SRGBColorSpace;
      flat(new THREE.PlaneGeometry(5.6, 1.15), track(new THREE.MeshBasicMaterial({map: logo, transparent: true, toneMapped: false})), 0, 2.7, -RD / 2 + .05);
      flat(new THREE.BoxGeometry(6.2, .04, .04), glow(0xf20b6d, 4), 0, 2.0, -RD / 2 + .05);
      // mostrador negro con luz morada (arriba) y rosada (abajo)
      mesh(new RB(4.2, .95, .7, 3, .12), track(new THREE.MeshPhysicalMaterial({color: 0x0c0b10, roughness: .15, metalness: .6, clearcoat: 1})), 0, .475, -3.25);
      flat(new THREE.BoxGeometry(4.25, .03, .03), glow(0xa855f7, 3.5), 0, 1.06, -2.9); flat(new THREE.BoxGeometry(4.25, .03, .03), glow(0xf20b6d, 3.5), 0, .08, -2.9);
      // pantalla "Recepción · interesados de hoy" (se redibuja solo si cambia)
      const scr = A.canvasScreen(4.2, 1.9, 1280, 580); A.screen(-5.6, 2.2, -RD / 2 + .08, 4.2, 1.9, scr);
      // sala de espera: dos sofás y mesa
      const sofa = (x, z, r) => { const g = new THREE.Group(); g.position.set(x, 0, z); g.rotation.y = r; S.add(g); const m = M(0x4a4256, {roughness: .85});
        mesh(new RB(2.2, .42, .85, 3, .12), m, 0, .26, 0, g); mesh(new RB(2.2, .5, .2, 3, .1), m, 0, .62, -.34, g); };
      sofa(4.6, -.6, -Math.PI / 2); sofa(4.6, 2.4, -Math.PI / 2);
      mesh(new THREE.CylinderGeometry(.5, .5, .04, 28), M(0xa8a5b2, {roughness: .4}), 3.4, .42, .9); mesh(new THREE.CylinderGeometry(.06, .06, .4, 12), M(0x111111), 3.4, .21, .9);
      A.zoneTag('Recepción', 0, -.6); A.zoneTag('Sala de espera', 4.2, 4.4); A.zoneTag('Entrada', -3.6, 5.2);
      // plantas (hojas en posiciones fijas: nada al azar)
      const LEAF = [[-.12, .95, .08, .26], [.14, 1.1, -.1, .24], [0, 1.3, .12, .28], [-.18, 1.25, -.12, .22], [.16, .88, .14, .25], [-.05, 1.45, -.02, .26], [.1, 1.4, .06, .23], [-.15, 1.05, .16, .24], [.04, .82, -.18, .27]];
      const leafM = M(0x2f7a46, {roughness: .8}), potM = M(0xa8a5b2);
      for (const [x, z] of [[-8, -5], [8, -5], [8, 5], [-8, 1]]) { const g = new THREE.Group(); g.position.set(x, 0, z); S.add(g); mesh(new THREE.CylinderGeometry(.32, .26, .6, 20), potM, 0, .3, 0, g);
        for (const [lx, ly, lz, r] of LEAF) { const l = mesh(new THREE.SphereGeometry(r, 10, 8), leafM, lx, ly, lz, g); l.scale.y = 1.4; } }
      // luces (como la referencia)
      S.add(new THREE.AmbientLight(0xf2eefc, .45)); S.add(new THREE.HemisphereLight(0xffffff, 0x2a2040, .3));
      const key = new THREE.DirectionalLight(0xffffff, 1.2); key.position.set(6, 14, 9); key.castShadow = true; key.shadow.mapSize.set(2048, 2048);
      Object.assign(key.shadow.camera, {left: -11, right: 11, top: 8, bottom: -8}); key.shadow.camera.updateProjectionMatrix(); key.shadow.bias = -.0005; S.add(key);
      for (const [x, z, c, i] of [[0, -3, 0xa855f7, 3], [4.4, 1, 0xf59e0b, 1.5], [-5.6, -4, 0xf20b6d, 2]]) A.point(c, i, 7, x, 3, z);

      function drawScreen(snap) {
        const m = P.receptionScreen(snap);
        scr.draw(m, (x, w, h) => {
          const g = x.createLinearGradient(0, 0, w, h); g.addColorStop(0, '#14081f'); g.addColorStop(1, '#260720'); x.fillStyle = g; x.fillRect(0, 0, w, h);
          x.fillStyle = '#fff'; x.font = '800 46px Inter,sans-serif'; x.fillText(m.title, 32, 64);
          if (m.more) { x.textAlign = 'right'; x.fillStyle = '#f9a8d4'; x.font = '800 34px Inter,sans-serif'; x.fillText(`+${m.more}`, w - 32, 62); x.textAlign = 'left'; }
          x.fillStyle = '#f20b6d'; x.fillRect(32, 84, w - 64, 3);
          if (m.empty) { x.fillStyle = '#cbbfd6'; x.font = '700 40px Inter,sans-serif'; x.textAlign = 'center'; x.fillText('Sin visitas hoy', w / 2, h / 2 + 30); x.textAlign = 'left'; return; }
          m.rows.forEach((r, i) => { const y = 100 + i * 78;
            x.fillStyle = 'rgba(255,255,255,.06)'; x.fillRect(32, y, w - 64, 70); x.fillStyle = r.color; x.fillRect(32, y, 8, 70);
            x.fillStyle = '#fff'; x.font = '800 28px Inter,sans-serif'; x.fillText(A.clipText(r.a, 40), 58, y + 31);
            x.fillStyle = '#cbbfd6'; x.font = '500 22px Inter,sans-serif'; x.fillText(A.clipText(r.b, 52), 58, y + 60);
            x.fillStyle = r.color; x.font = '700 24px Inter,sans-serif'; x.textAlign = 'right'; x.fillText(A.clipText(r.state, 30), w - 52, y + 45); x.textAlign = 'left'; });
        });
      }

      // ------------------------------------------------------------ personas: Nexa y los visitantes reales
      let nexa = null; const V = new Map();
      function ensureNexa(snap) {
        const n = P.nexaTag(snap);
        if (!nexa) { nexa = A.makePerson({model: 'Ch07_nonPBR', gender: 'mujer', tunic: true, lines: 0xf20b6d, kind: 'nexa', info: {name: 'Nexa', role: 'Recepción'}});
          A.sitAt(nexa, RC.NEXA, n.clip); nexa.tag = A.tag(nexa.g, '', 'nx', 2.0); }
        A.play(nexa, n.clip); nexa.info = {name: 'Nexa', role: 'Recepción', task: n.small};
        A.setTag(nexa.tag, A.tagHtml(n.cls, n.text, n.small), 'nx');
      }
      function apply(snap, prev, first) {
        drawScreen(snap);
        A.chip(snap.empty ? 'Sin visitas hoy' : `${snap.interesados} ${snap.interesados === 1 ? 'interesado' : 'interesados'} hoy`, true);
        if (!A.peopleOk()) return;
        ensureNexa(snap);
        const visitors = snap.visitors || []; const plan = P.receptionPlan(visitors); const byId = new Map(visitors.map(v => [v.id, v]));
        const seen = new Set();
        for (const pl of plan) {
          const v = byId.get(pl.id); seen.add(pl.id); const t = P.receptionTag(v);
          const info = {name: t.head, role: 'Recepción', task: t.small, link: P.visitorLink(v)};
          let s = V.get(pl.id);
          const settle = per => A.sitAt(per, pl.spot, pl.clip);
          if (!s) {
            const per = A.makePerson({model: P.visitorModel(pl.id), kind: 'visitante', info});
            s = {p: per, spot: pl.spot, clip: pl.clip}; V.set(pl.id, s); per.tag = A.tag(per.g, '', '', 2.05);
            if (first && !pl.arrive) settle(per); else A.arrive(per, RC.DOOR, [pl.spot[0], pl.spot[1]], () => settle(per));
          } else if (s.spot !== pl.spot || s.clip !== pl.clip) {
            s.spot = pl.spot; s.clip = pl.clip; A.goTo(s.p, [pl.spot[0], pl.spot[1]], () => settle(s.p));
          }
          s.p.info = info;
          A.setTag(s.p.tag, A.tagHtml(t.cls, t.head, t.small), t.cls); s.p.tag.dy = pl.dy;
        }
        for (const [k, s] of V) if (!seen.has(k)) { V.delete(k); A.leave(s.p, RC.DOOR); }
      }
      return {apply, key, reset() { V.clear(); nexa = null; }};
    }});
}

