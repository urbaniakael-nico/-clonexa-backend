// Oficina 3D · BAR APROBADO (estilo "bar", hoy solo The Time Machine; interno de Clonexa, solo Admin V2).
// Reproduce la escena aprobada bar.html / bar5.png (medidas, distribución, luces, materiales, cámara y etiquetas) y
// la conecta a la copia viva del bar (/pisos/{id}/vivo cada 7 s). Reglas puras en oficina_bar_rules.js.
// Personajes y animaciones de Mixamo: NUNCA en el repo; llegan del bucket privado por /admin-v2plus/oficina/bar/...
// (solo con sesión). Solo actividad: nunca dinero.
import * as THREE from 'three';
import {GLTFLoader} from 'three/addons/loaders/GLTFLoader.js';
import {MeshoptDecoder} from 'three/addons/libs/meshopt_decoder.module.js';
import {RGBELoader} from 'three/addons/loaders/RGBELoader.js';
import * as SkeletonUtils from 'three/addons/utils/SkeletonUtils.js';
import {EffectComposer} from 'three/addons/postprocessing/EffectComposer.js';
import {RenderPass} from 'three/addons/postprocessing/RenderPass.js';
import {UnrealBloomPass} from 'three/addons/postprocessing/UnrealBloomPass.js';
import {OutputPass} from 'three/addons/postprocessing/OutputPass.js';
import * as RULES from '/admin-v2plus/oficina/bar_reglas.js';
import * as PR from '/admin-v2plus/oficina/pisos_reglas.js';
import {attachGestures} from '/admin-v2plus/oficina/gestos.js';
import {attachArchitect, savedPos, follow} from '/admin-v2plus/oficina/arquitecto.js';

// Las rutas salen del propio origen del motor: en la consola /admin-v2plus/oficina/; en el visor del cliente (Negocio en
// vivo 3D) la ruta firmada de SU empresa (/panel/negocio-en-vivo/r/<empresa>/<firma>/), que exige su sesion.
const ROOT = new URL('./', import.meta.url).pathname;
const VIEWER = ROOT.startsWith('/panel/');
const RES = ROOT + 'recursos/';
const MIX = ROOT + 'bar/';
const API = VIEWER ? ROOT + 'api' : '/admin-v2/api/oficina';
const WALK = 1.25;   // m/s
const {W: RW, D: RD, WALL: WH} = RULES.ROOM;

function esc(s) {
  return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

export async function openBar(o) {
  const {R, floor, getJson, log} = o;
  const cid = floor.company_id;
  const ui = document.createElement('div'); ui.id = 'realUi'; document.body.appendChild(ui);
  const tagLayer = document.createElement('div'); tagLayer.id = 'barTags'; document.body.appendChild(tagLayer);
  ui.innerHTML = `<div class="rbar glass"><button type="button" data-out>${esc(o.backLabel || '← Edificio')}</button><b>${esc(floor.name)}</b><span class="rchip" data-biz></span>
    <span class="rchip warn hidden" data-warn></span><span class="sp"></span><span class="rchip" data-mb></span><span class="rfps" data-fps>…</span></div>
    <div class="rload" data-load>Cargando el bar…</div>`;
  const $ = s => ui.querySelector(s);
  const warn = t => { const w = $('[data-warn]'); w.textContent = t || ''; w.classList.toggle('hidden', !t); };

  // ------------------------------------------------------------- renderer (se restaura al salir)
  const saved = {legacy: R.useLegacyLights, tm: R.toneMapping, exp: R.toneMappingExposure, shadow: R.shadowMap.type, se: R.shadowMap.enabled, pr: R.getPixelRatio()};
  let lite = !!o.lite;
  function rendererMode() {
    R.useLegacyLights = false; R.toneMapping = THREE.ACESFilmicToneMapping; R.toneMappingExposure = 1.0;
    R.shadowMap.enabled = true; R.shadowMap.autoUpdate = false; R.shadowMap.type = lite ? THREE.PCFShadowMap : THREE.PCFSoftShadowMap; R.shadowMap.needsUpdate = true;
    R.setPixelRatio(1);   // como bar.html (la vista aprobada se dibujó a 1:1)
  }
  rendererMode();
  const S = new THREE.Scene(); S.background = new THREE.Color(0x07050a);
  const C = new THREE.PerspectiveCamera(RULES.CAMERA.fov, innerWidth / innerHeight, .1, 200);
  const disposables = []; const track = x => { disposables.push(x); return x; };

  // ------------------------------------------------------------- recursos (CC0 del repo + Mixamo del bucket privado)
  const man = await getJson(RES + 'manifest.json');
  const has = f => !!(man.files && man.files[f]);
  const url = f => RES + f + '?v=' + ((man.files[f] || {}).sha || '1');
  const L = new GLTFLoader(); L.setMeshoptDecoder(MeshoptDecoder);
  const TL = new THREE.TextureLoader();
  const used = new Set();
  const loadModel = k => { const f = `modelos/${k}.glb`; if (!has(f)) return Promise.resolve(null); used.add(f); return L.loadAsync(url(f)).then(g => g.scene).catch(() => null); };
  const tex = (f, rep = [1, 1], srgb = true) => { const p = `texturas/${f}`; if (!has(p)) return null; used.add(p);
    const t = track(TL.load(url(p))); t.wrapS = t.wrapT = THREE.RepeatWrapping; t.repeat.set(...rep); if (srgb) t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = lite ? 2 : 8; return t; };
  let mixMan = null;
  const mixP = getJson(MIX + 'manifest.json').then(m => (mixMan = m)).catch(() => null);
  const hdrP = has('hdri/warm_bar_1k.hdr') ? (used.add('hdri/warm_bar_1k.hdr'), new RGBELoader().loadAsync(url('hdri/warm_bar_1k.hdr')).catch(() => null)) : Promise.resolve(null);
  const [hdr, mesa, taburete, botellas, planta] = await Promise.all([hdrP, ...['mesa', 'taburete', 'botellas', 'planta'].map(loadModel)]);
  if (hdr) { hdr.mapping = THREE.EquirectangularReflectionMapping; S.environment = track(hdr); }
  // bar.html pide 0,35, pero three r160 no tiene environmentIntensity: la vista aprobada (bar5.png) se dibujó con el HDRI a 1,0.

  let snap = await getJson(`${API}/pisos/${cid}/vivo`);
  const brandAccent = new THREE.Color((snap.brand && snap.brand.accent) || '#f20b6d');
  const ARCH = snap.arch || {};   // modo arquitecto: posiciones guardadas (mesas, cabina, pista, plantas)
  const ARCH_ITEMS = [];

  // ------------------------------------------------------------- utilidades de bar.html
  const mesh = (g, m, x = 0, y = 0, z = 0, p = S) => { const k = new THREE.Mesh(track(g), m); k.position.set(x, y, z); k.castShadow = k.receiveShadow = true; p.add(k); return k; };
  const M = (c, x = {}) => track(new THREE.MeshStandardMaterial(Object.assign({color: c, roughness: .6}, x)));
  const glow = (c, i = 3) => track(new THREE.MeshStandardMaterial({color: 0x000000, emissive: c, emissiveIntensity: i}));
  function fit(obj, h) { obj.updateMatrixWorld(true); const b = new THREE.Box3().setFromObject(obj); obj.scale.multiplyScalar(h / (b.max.y - b.min.y)); obj.updateMatrixWorld(true);
    const b2 = new THREE.Box3().setFromObject(obj); obj.position.y -= b2.min.y; return obj; }
  function shadows(obj) { obj.traverse(m => { if (m.isMesh) m.castShadow = m.receiveShadow = true; }); return obj; }
  const NEON = [];   // materiales que bajan con el bar cerrado: [material, intensidad abierta]
  const neon = (c, i) => { const m = glow(c, i); NEON.push([m, i]); return m; };

  // ------------------------------------------------------------- sala 16 x 11 m (casa de muñecas: sin techo ni pared frontal)
  const floorM = M(0xffffff, {map: tex('madera_diff.webp', [6, 4]), normalMap: tex('madera_nor_gl.webp', [6, 4], false), roughness: .35, metalness: .05});
  const fl = mesh(new THREE.PlaneGeometry(RW, RD), floorM); fl.rotation.x = -Math.PI / 2; fl.castShadow = false;
  mesh(new THREE.BoxGeometry(RW, WH, .2), M(0xc9b6a8, {map: tex('pared_diff.webp', [5, 1.2]), normalMap: tex('pared_nor_gl.webp', [5, 1.2], false), roughness: .9}), 0, WH / 2, -RD / 2 - .1);
  mesh(new THREE.BoxGeometry(.2, WH, RD), M(0xc9b6a8, {map: tex('pared_diff.webp', [3.5, 1.2]), normalMap: tex('pared_nor_gl.webp', [3.5, 1.2], false), roughness: .9}), -RW / 2 - .1, WH / 2, 0);
  mesh(new THREE.BoxGeometry(.2, WH, RD), M(0x1a1420, {roughness: .8}), RW / 2 + .1, WH / 2, 0);
  mesh(new THREE.BoxGeometry(RW, .12, .06), M(0x1a1118), 0, .06, -RD / 2 + .03);
  mesh(new THREE.BoxGeometry(RW + .4, .25, RD + .4), M(0x0d0a10, {roughness: .4, metalness: .5}), 0, -.13, 0).castShadow = false;
  mesh(new THREE.BoxGeometry(RW + .42, .04, .04), neon(0xd946ef, 4), 0, -.02, RD / 2 + .2);

  // ------------------------------------------------------------- barra (pared izquierda): 7 m, 1,08 m, neón rosado, contrabarra
  const {x: barX, z0: barZ0, z1: barZ1} = RULES.BAR; const barLen = barZ1 - barZ0, barZc = (barZ0 + barZ1) / 2, bbX = RULES.BACKBAR_X;
  const wood = M(0x3a2216, {map: tex('madera_diff.webp', [2, 1]), roughness: .45});
  mesh(new THREE.BoxGeometry(.65, 1.05, barLen), wood, barX, .525, barZc);
  mesh(new THREE.BoxGeometry(.85, .06, barLen + .15), M(0x111014, {roughness: .15, metalness: .6}), barX, 1.08, barZc);
  mesh(new THREE.BoxGeometry(.02, .05, barLen), neon(0xf20b6d, 6), barX + .335, .18, barZc);
  mesh(new THREE.BoxGeometry(.06, .05, barLen), M(0xb08d57, {metalness: 1, roughness: .3}), barX + .36, .32, barZc);
  mesh(new THREE.BoxGeometry(.45, .95, barLen), M(0x24160f, {roughness: .5}), bbX, .475, barZc);
  const shelfM = M(0x1a1a1f, {metalness: .5, roughness: .2}), stripM = neon(0xf5b971, 5);
  for (let s = 0; s < 3; s++) { mesh(new THREE.BoxGeometry(.32, .04, barLen), shelfM, bbX + .05, 1.45 + s * .48, barZc); mesh(new THREE.BoxGeometry(.02, .02, barLen), stripM, bbX + .2, 1.47 + s * .48, barZc); }
  mesh(new THREE.BoxGeometry(.04, 1.6, barLen), neon(0x7c3aed, .9), bbX - .18, 2.0, barZc);
  if (taburete) for (let i = 0; i < RULES.BAR.stools; i++) { const t = fit(taburete.clone(), .78); t.position.x = barX + .75; t.position.z = RULES.stoolZ(i); shadows(t); S.add(t); }
  if (botellas) for (let s = 0; s < 3; s++) for (let i = 0; i < 7; i++) { const b = fit(botellas.clone(), .36); b.position.set(bbX + .05, 1.47 + s * .48, barZ0 + .4 + i * .95); b.rotation.y = i; S.add(b); }

  // ------------------------------------------------------------- mesas redondas (0,76 m) con 4 sillas modernas y lámpara colgante
  const sc0 = document.createElement('canvas'); sc0.width = sc0.height = 256;
  { const x = sc0.getContext('2d'); const g = x.createRadialGradient(128, 128, 0, 128, 128, 128); g.addColorStop(0, 'rgba(74,222,128,1)'); g.addColorStop(.6, 'rgba(74,222,128,.35)'); g.addColorStop(1, 'rgba(74,222,128,0)'); x.fillStyle = g; x.fillRect(0, 0, 256, 256); }
  const SOFT = track(new THREE.CanvasTexture(sc0));
  const softM = track(new THREE.MeshBasicMaterial({map: SOFT, transparent: true, opacity: .22, depthWrite: false, blending: THREE.AdditiveBlending}));
  const chairSeat = M(0x6b3f26, {map: tex('madera_diff.webp', [1, 1]), roughness: .5}), chairMetal = M(0x111114, {metalness: .8, roughness: .35});
  const bulbOn = glow(0x4ade80, 3.5), bulbOff = M(0x2a2a2a, {roughness: .3}), cordM = M(0x111), shadeM = M(0x111, {side: THREE.DoubleSide, metalness: .6});
  const hitM = track(new THREE.MeshBasicMaterial({visible: false}));
  const PICK = [];
  const TABLES = new Map();   // label -> {g, x, z, bulb, soft, tag, guests, stool}
  const tablesG = new THREE.Group(); S.add(tablesG);
  // Rendimiento: las sillas (4 por mesa, 8 piezas cada una) se dibujan con mallas instanciadas: mismo aspecto, 4 llamadas.
  let chairParts = [];
  function buildChairs(spots) {
    chairParts.forEach(m => { tablesG.remove(m); m.dispose(); }); chairParts = [];
    const parts = [[new THREE.BoxGeometry(.42, .04, .42), chairSeat, [[0, .46, 0]]], [new THREE.BoxGeometry(.42, .32, .03), chairSeat, [[0, .72, -.2]]],
      [new THREE.CylinderGeometry(.013, .013, .46, 8), chairMetal, [[-.19, .23, -.19], [.19, .23, -.19], [-.19, .23, .19], [.19, .23, .19]]],
      [new THREE.CylinderGeometry(.012, .012, .36, 8), chairMetal, [[-.19, .64, -.2], [.19, .64, -.2]]]];
    const g = new THREE.Object3D(), k = new THREE.Object3D();
    for (const [geo, m, offs] of parts) {
      const im = new THREE.InstancedMesh(track(geo), m, spots.length * offs.length); im.castShadow = im.receiveShadow = true; let n = 0;
      for (const [x, z, r] of spots) { g.position.set(x, 0, z); g.rotation.set(0, r, 0); g.updateMatrix();
        for (const off of offs) { k.position.set(...off); k.updateMatrix(); im.setMatrixAt(n++, new THREE.Matrix4().multiplyMatrices(g.matrix, k.matrix)); } }
      im.instanceMatrix.needsUpdate = true; tablesG.add(im); chairParts.push(im);
    }
  }
  const LAMP_LIGHTS = [];
  function lampPool() {   // luces verdes reales de las mesas activas (en liviano solo brillan el bombillo y el sombreado)
    LAMP_LIGHTS.forEach(l => S.remove(l)); LAMP_LIGHTS.length = 0;
    for (let i = 0; i < (lite ? 0 : 6); i++) { const pl = new THREE.PointLight(0x9dffc4, 0, 3.2, 2); pl.position.set(0, -10, 0); S.add(pl); LAMP_LIGHTS.push(pl); }
  }
  let layout = {tables: [], stools: {}, overflow: 0}, layoutKey = '';
  const CHAIR_OFFS = [[0, -.78, 0], [0, .78, Math.PI], [-.78, 0, Math.PI / 2], [.78, 0, -Math.PI / 2]];
  function chairSpots() { const out = []; for (const t of TABLES.values()) if (t.stool == null) CHAIR_OFFS.forEach(([dx, dz, r]) => out.push([t.x + dx, t.z + dz, r])); return out; }
  function buildTables() {
    const labels = (snap.tables || []).map(t => t.label);
    const key = labels.join('|'); if (key === layoutKey) return; layoutKey = key;
    for (const t of TABLES.values()) { t.guests.splice(0).forEach(dropPerson); dropTag(t.tag); }
    TABLES.clear(); while (tablesG.children.length) tablesG.remove(tablesG.children[0]); chairParts = [];
    for (let i = PICK.length - 1; i >= 0; i--) if (PICK[i].userData.table) PICK.splice(i, 1);
    layout = RULES.layoutTables(labels);
    ARCH_ITEMS.splice(0, ARCH_ITEMS.length, ...ARCH_ITEMS.filter(it => !it.key.startsWith('mesa:')));
    for (const {label, pos: p0} of layout.tables) {
      const [x, z] = savedPos(ARCH, 'mesa:' + label, p0);
      const g = new THREE.Group(); g.position.set(x, 0, z); tablesG.add(g);
      if (mesa) { const t = fit(mesa.clone(), .76); shadows(t);
        const bb = new THREE.Box3().setFromObject(t); const w = bb.max.x - bb.min.x; if (w > 1.1 || w < .6) { const k = .85 / w; t.scale.x *= k; t.scale.z *= k; } g.add(t); }
      mesh(new THREE.CylinderGeometry(.005, .005, .9, 4), cordM, 0, 2.95, 0, g); mesh(new THREE.ConeGeometry(.2, .18, 20, 1, true), shadeM, 0, 2.5, 0, g);
      const bulb = mesh(new THREE.SphereGeometry(.065, 12, 10), bulbOff, 0, 2.42, 0, g);
      const soft = new THREE.Mesh(track(new THREE.CircleGeometry(1.15, 48)), softM); soft.rotation.x = -Math.PI / 2; soft.position.set(0, .013, 0); soft.visible = false; g.add(soft);
      const hit = new THREE.Mesh(track(new THREE.CylinderGeometry(.75, .75, 1, 12)), hitM); hit.position.set(0, .5, 0); hit.userData.table = label; g.add(hit); PICK.push(hit);
      const tagAt = new THREE.Vector3(x, .76, z);
      const tg = tag({position: tagAt}, '', 'mesa off', .15, true);
      const T = {g, x, z, bulb, soft, tag: tg, guests: [], seats: {}};
      const seatsAt = () => { T.seats = Object.fromEntries(Object.entries(RULES.SEATS).map(([k, [dx, dz, r]]) => [k, [T.x + dx, T.z + dz, r]])); };
      seatsAt(); TABLES.set(label, T);
      ARCH_ITEMS.push({key: 'mesa:' + label, label: 'mesas', pick: [hit], get: () => [T.x, T.z, 0],
        set: (nx, nz) => { T.x = nx; T.z = nz; g.position.set(nx, 0, nz); tagAt.set(nx, .76, nz); seatsAt(); }, done: () => buildChairs(chairSpots())});
    }
    for (const [label, idx] of Object.entries(layout.stools)) TABLES.set(label, {stool: idx, guests: [], x: barX + .78, z: RULES.stoolZ(idx), seats: {n: [barX + .78, RULES.stoolZ(idx), -Math.PI / 2]}});
    buildChairs(chairSpots());
    if (layout.overflow) warn(`${layout.overflow} mesas sin puesto en el plano`);
    R.shadowMap.needsUpdate = true;
  }

  // ------------------------------------------------------------- pista LED 4 x 3, cabina de DJ, logo y pantalla
  const tiles = [];
  const PISTA0 = [4.5, -3.3, 0], PISTA = savedPos(ARCH, 'pista', PISTA0);
  const pistaG = new THREE.Group(); pistaG.position.set(PISTA[0], 0, PISTA[1]); pistaG.rotation.y = PISTA[2]; S.add(pistaG);
  for (let i = 0; i < 4; i++) for (let j = 0; j < 3; j++) { const t = mesh(new THREE.BoxGeometry(.95, .03, .95), neon(new THREE.Color().setHSL((i * 3 + j) / 12 * .25 + .75, 1, .5), 1.6), 3.0 + i - PISTA0[0], .016, -4.3 + j - PISTA0[1], pistaG); t.castShadow = false; tiles.push(t); }
  const pistaHit = new THREE.Mesh(track(new THREE.BoxGeometry(4, .1, 3)), hitM); pistaG.add(pistaHit);
  ARCH_ITEMS.push({key: 'pista', label: 'pista', pick: [pistaHit], turn: true, get: () => [pistaG.position.x, pistaG.position.z, pistaG.rotation.y],
    set: (x, z, r) => { pistaG.position.set(x, 0, z); pistaG.rotation.y = r; PISTA[0] = x; PISTA[1] = z; PISTA[2] = r; }});
  const DJ0 = [RULES.DJ.booth[0], RULES.DJ.booth[1], 0], DJP = savedPos(ARCH, 'dj', DJ0);
  const dj = new THREE.Group(); dj.position.set(DJP[0], 0, DJP[1]); dj.rotation.y = DJP[2]; S.add(dj);
  const djHit = new THREE.Mesh(track(new THREE.BoxGeometry(3.2, 1.4, 1)), hitM); djHit.position.y = .7; dj.add(djHit);
  ARCH_ITEMS.push({key: 'dj', label: 'cabina del DJ', pick: [djHit], turn: true, get: () => [dj.position.x, dj.position.z, dj.rotation.y],
    set: (x, z, r) => { dj.position.set(x, 0, z); dj.rotation.y = r; DJP[0] = x; DJP[1] = z; DJP[2] = r; }});
  // puestos que siguen a lo que se movió (DJ detrás de su cabina, bailarines en la pista)
  const movedSpot = (pos, from, to) => { const [x, z] = follow(pos, from, to); return [x, z, (pos[2] || 0) + (to[2] - from[2])]; };
  const spotOf = (uniform, idx, paused) => { const sp = RULES.staffSpot(uniform, idx, paused); if (uniform === 'dj' && !paused) sp.pos = movedSpot(sp.pos, DJ0, DJP); return sp; };
  mesh(new THREE.BoxGeometry(1.8, 1.05, .75), M(0x101014, {roughness: .3, metalness: .4}), 0, .525, 0, dj);
  mesh(new THREE.BoxGeometry(1.82, .05, .06), neon(0xe879f9, 6), 0, .9, .39, dj);
  const platters = [-.45, .45].map(x => mesh(new THREE.CylinderGeometry(.16, .16, .03, 24), M(0x222), x, 1.07, 0, dj));
  mesh(new THREE.BoxGeometry(.4, .05, .3), M(0x333), 0, 1.07, 0, dj);
  [-1.25, 1.25].forEach(x => { mesh(new THREE.BoxGeometry(.5, 1.4, .5), M(0x18181b), x, .7, 0, dj); mesh(new THREE.CylinderGeometry(.16, .16, .02, 24), M(0x333), x, 1.0, .26, dj).rotation.x = Math.PI / 2; });
  // pared del fondo: logo (resolución original del Estudio de marca / logo del panel) con marco y neón rosado
  const LG = RULES.LOGO;
  mesh(new THREE.BoxGeometry(3.2, 1.7, .06), M(0x140c08), LG.x, LG.y, -RD / 2 + .05);
  const logoM = track(new THREE.MeshStandardMaterial({color: 0xffffff, emissive: 0xffffff, emissiveIntensity: .32}));
  const logoMesh = mesh(new THREE.PlaneGeometry(LG.w, LG.h), logoM, LG.x, LG.y, -RD / 2 + .09); logoMesh.castShadow = false; logoMesh.visible = false;
  const pinkBar = neon(0xf20b6d, 5);
  mesh(new THREE.BoxGeometry(3.3, .04, .04), pinkBar, LG.x, 1.28, -RD / 2 + .1); mesh(new THREE.BoxGeometry(3.3, .04, .04), pinkBar, LG.x, 3.02, -RD / 2 + .1);
  let logoImg = null;
  function setLogo(img, t) {
    const a = img.width / img.height, box = LG.w / LG.h;
    logoMesh.scale.set(a > box ? 1 : a / box, a > box ? box / a : 1, 1);
    t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 8; logoM.map = t; logoM.emissiveMap = t; logoM.needsUpdate = true; logoMesh.visible = true;
  }
  const logoUrl = snap.brand && snap.brand.logo_url;
  if (logoUrl) TL.load(logoUrl, t => { track(t); logoImg = t.image; setLogo(t.image, t); drawScreen(); }, undefined, () => nameLogo());
  else nameLogo();
  function nameLogo() {   // sin logo en el Estudio de marca: el nombre del bar en neón (nunca una captura)
    const c = document.createElement('canvas'); c.width = 1024; c.height = 522; const x = c.getContext('2d');
    x.fillStyle = '#140c08'; x.fillRect(0, 0, c.width, c.height); x.fillStyle = '#ffd6e7'; x.shadowColor = '#f20b6d'; x.shadowBlur = 30;
    x.font = '900 110px Inter, sans-serif'; x.textAlign = 'center'; x.textBaseline = 'middle'; x.fillText(String(floor.name).slice(0, 18), 512, 261);
    const t = track(new THREE.CanvasTexture(c)); setLogo(c, t); warn('Sin logo en el Estudio de marca: se muestra el nombre');
  }
  // pantalla grande "Canciones pedidas"
  const sc = document.createElement('canvas'); sc.width = 1280; sc.height = 720;
  const st = track(new THREE.CanvasTexture(sc)); st.colorSpace = THREE.SRGBColorSpace;
  const SC = RULES.SCREEN;
  mesh(new THREE.BoxGeometry(3.3, 1.9, .08), M(0x050505, {metalness: .6, roughness: .3}), SC.x, SC.y, -RD / 2 + .06);
  const screenM = track(new THREE.MeshBasicMaterial({map: st, toneMapped: false}));
  mesh(new THREE.PlaneGeometry(SC.w, SC.h), screenM, SC.x, SC.y, -RD / 2 + .11).castShadow = false;
  let screenKey = '';
  function drawScreen(force) {
    const m = RULES.screenModel(snap, Date.now());
    const key = JSON.stringify(m) + (logoImg ? 1 : 0); if (!force && key === screenKey) return; screenKey = key;
    const x = sc.getContext('2d');
    const g = x.createLinearGradient(0, 0, 1280, 720); g.addColorStop(0, '#1b0b2e'); g.addColorStop(1, '#3b0a2a'); x.fillStyle = g; x.fillRect(0, 0, 1280, 720);
    if (logoImg) { const a = logoImg.width / logoImg.height; const w = Math.min(236, 120 * a), h = w / a; x.drawImage(logoImg, 40 + (236 - w) / 2, 30 + (120 - h) / 2, w, h); }
    x.textAlign = 'left'; x.textBaseline = 'alphabetic';
    x.fillStyle = '#fff'; x.font = '800 64px Inter,sans-serif'; x.fillText('♫ Canciones pedidas', 310, 105);
    x.fillStyle = '#f20b6d'; x.fillRect(40, 175, 1200, 4);
    const clip = (s, n) => (String(s).length > n ? String(s).slice(0, n - 1) + '…' : String(s));
    if (m.mode === 'cerrado' || m.mode === 'vacio') {
      x.textAlign = 'center'; x.fillStyle = m.mode === 'cerrado' ? '#fca5a5' : '#fff'; x.font = '800 64px Inter,sans-serif';
      x.fillText(m.mode === 'cerrado' ? m.sign : 'Pide tu canción', 640, 400);
      if (m.mode === 'vacio') { x.fillStyle = '#cbbfd6'; x.font = '500 40px Inter,sans-serif'; x.fillText('desde el QR de tu mesa', 640, 470); }
    } else {
      if (m.now) {
        x.fillStyle = '#22c55e'; x.font = '700 30px Inter,sans-serif'; x.fillText('SONANDO AHORA', 60, 240);
        x.fillStyle = '#fff'; x.font = '800 54px Inter,sans-serif'; x.fillText(clip(m.now.title, 38), 60, 305);
        x.fillStyle = '#cbbfd6'; x.font = '500 34px Inter,sans-serif'; x.fillText(clip(m.now.from, 48), 60, 355);
        x.fillStyle = 'rgba(255,255,255,.12)'; x.fillRect(60, 380, 1160, 8); x.fillStyle = '#22c55e'; x.fillRect(60, 380, Math.round(1160 * m.now.progress), 8);
      } else { x.fillStyle = '#cbbfd6'; x.font = '600 40px Inter,sans-serif'; x.fillText('La próxima canción empieza pronto', 60, 300); }
      x.fillStyle = '#a78bfa'; x.font = '700 30px Inter,sans-serif'; x.fillText('EN COLA', 60, 450);
      if (!m.queue.length) { x.fillStyle = '#cbbfd6'; x.font = '500 30px Inter,sans-serif'; x.fillText('Pide tu canción desde el QR de tu mesa', 85, 510); }
      m.queue.forEach((q, i) => { const y = 510 + i * 70; x.fillStyle = 'rgba(255,255,255,.07)'; x.fillRect(60, y - 45, 1160, 58);
        x.fillStyle = '#f20b6d'; x.font = '800 34px Inter,sans-serif'; x.fillText(q.n, 85, y); x.fillStyle = '#fff'; x.fillText(clip(q.title, 40), 140, y);
        x.fillStyle = '#cbbfd6'; x.font = '500 30px Inter,sans-serif'; x.fillText(clip(q.from, 18), 940, y); });
    }
    st.needsUpdate = true;
  }
  if (planta) [[7.4, 4.9], [-7.4, 4.9], [7.4, -.8]].forEach((p0, i) => { const [px, pz] = savedPos(ARCH, 'planta:' + i, p0); const p = fit(planta.clone(), 1.4); p.position.x = px; p.position.z = pz; shadows(p); S.add(p);
    ARCH_ITEMS.push({key: 'planta:' + i, label: 'plantas', pick: [p], get: () => [p.position.x, p.position.z, 0], set: (x, z) => { p.position.x = x; p.position.z = z; }}); });

  // ------------------------------------------------------------- luces (igual a bar.html)
  const amb = new THREE.AmbientLight(0x2a1838, .6); S.add(amb);
  const key = new THREE.DirectionalLight(0xffe2c4, .9); key.position.set(4, 10, 6); key.castShadow = true;
  key.shadow.mapSize.set(lite ? 1024 : 2048, lite ? 1024 : 2048); Object.assign(key.shadow.camera, {left: -10, right: 10, top: 8, bottom: -8}); key.shadow.camera.updateProjectionMatrix(); key.shadow.bias = -.0005; S.add(key);
  const POINTS = [[0xa855f7, 8, 9, [4.5, 2.8, -3.6]], [0xf20b6d, 6, 8, [-1.3, 2.6, -4.2]], [0xffb36b, 6, 7, [-5.4, 2.6, -.8]], [0xffb36b, 4, 6, [-5.4, 2.6, 2.2]], [0x8b5cf6, 3, 5, [3.6, 2.1, -4.6]]]
    .map(([c, i, d, p]) => { const l = new THREE.PointLight(c, i, d, 2); l.position.set(...p); S.add(l); return [l, i]; });
  lampPool();

  // ------------------------------------------------------------- etiquetas HTML (como bar.html)
  const tags = [];
  function tag(obj, html, cls = '', dy = 2.05, fixed = false) { const d = document.createElement('div'); d.className = 'tg ' + cls; d.innerHTML = html; tagLayer.appendChild(d); const t = {obj, d, dy, fixed, html}; tags.push(t); return t; }
  function setTag(t, html, cls) { if (!t) return; if (t.html !== html) { t.d.innerHTML = html; t.html = html; } if (cls != null && t.d.className !== 'tg ' + cls) t.d.className = 'tg ' + cls; }
  function dropTag(t) { if (!t) return; t.d.remove(); const i = tags.indexOf(t); if (i >= 0) tags.splice(i, 1); }
  const v3 = new THREE.Vector3();
  function placeTags() {
    for (const t of tags) {
      if (t.fixed) v3.copy(t.obj.position); else t.obj.getWorldPosition(v3);
      v3.y += t.dy; v3.project(C);
      if (v3.z > 1 || t.hidden) { t.d.style.display = 'none'; continue; }
      t.d.style.display = 'flex'; if (!t.w || t.wh !== t.html) { t.w = t.d.offsetWidth; t.wh = t.html; }   // ancho medido solo cuando cambia el texto
      const half = t.w / 2 + 6, x = Math.max(half, Math.min(innerWidth - half, (v3.x * .5 + .5) * innerWidth));
      t.d.style.left = x.toFixed(1) + 'px'; t.d.style.top = ((-v3.y * .5 + .5) * innerHeight).toFixed(1) + 'px';
    }
  }

  // ------------------------------------------------------------- personajes de Mixamo (retargeting por prefijo y escala de cadera)
  const CH = {}, ANIMS = {}, INFO = {}, CLIP = {};
  let peopleOk = false;
  async function loadPeople() {
    await mixP;
    const files = (mixMan && mixMan.files) || {};
    const need = [...RULES.CHARACTERS.map(n => `personajes/${n}.glb`), ...RULES.CLIPS.map(n => `animaciones/${n}.glb`)];
    if (!need.every(f => files[f])) { warn('Personajes del bar no disponibles (bucket privado): el piso se ve sin personas'); return; }
    const get = f => L.loadAsync(MIX + f + '?v=' + files[f].sha.slice(0, 12));
    const [chs, ans] = await Promise.all([Promise.all(RULES.CHARACTERS.map(n => get(`personajes/${n}.glb`))), Promise.all(RULES.CLIPS.map(n => get(`animaciones/${n}.glb`)))]);
    RULES.CHARACTERS.forEach((n, i) => { CH[n] = chs[i]; });
    RULES.CLIPS.forEach((n, i) => { const g = ans[i]; let hy = 1; g.scene.traverse(x => { if (/Hips$/.test(x.name)) hy = x.position.y; });
      const clip = g.animations[0]; const t0 = RULES.SIT_CLIPS.includes(n) ? seatedCut(clip) : 0; ANIMS[n] = {clip, hy, trimmed: t0 > 0}; });
    peopleOk = true;
  }
  function seatedCut(clip) {   // solo la parte sentada (ver RULES.seatedStart); devuelve desde qué segundo se cortó
    const h = clip.tracks.find(t => /Hips\.position$/.test(t.name)); if (!h) return 0;
    const t0 = RULES.seatedStart(h.times, h.values); if (t0 < .05) return 0;
    clip.tracks.forEach(t => { const n = t.getValueSize(); let i = 0; while (i < t.times.length - 1 && t.times[i] < t0) i++;
      t.times = t.times.slice(i).map(x => x - t.times[i]); t.values = t.values.slice(i * n); });
    clip.resetDuration(); return t0;
  }
  function charInfo(n) {   // prefijo, cadera en reposo y escala real (caja precisa en reposo), una vez por personaje
    if (INFO[n]) return INFO[n];
    const m = SkeletonUtils.clone(CH[n].scene); let chy = 1, hips = 'mixamorigHips', found = false;
    m.traverse(x => { if (!found && /Hips$/.test(x.name)) { chy = x.position.y; hips = x.name; found = true; } });
    m.updateMatrixWorld(true); const bb = new THREE.Box3().setFromObject(m, true); const s = RULES.heightFor(n) / (bb.max.y - bb.min.y);
    m.scale.multiplyScalar(s); m.updateMatrixWorld(true); const bb2 = new THREE.Box3().setFromObject(m, true);
    return (INFO[n] = {chy, hips, scale: s, lift: -bb2.min.y});
  }
  function clipFor(n, name) {
    const id = n + '|' + name; if (CLIP[id]) return CLIP[id];
    const A = ANIMS[name], I = charInfo(n), clip = A.clip.clone(); clip.name = name;
    const plan = RULES.retargetPlan(clip.tracks.map(t => t.name), I.hips, I.chy, A.hy, name, A.trimmed);
    clip.tracks.forEach((t, i) => { t.name = plan.tracks[i].to; if (plan.tracks[i].hips) t.values = new Float32Array(RULES.scaleHips(t.values, plan.k, plan.inPlace, plan.anchor)); });
    return (CLIP[id] = clip);
  }
  const TINTS = [];
  function tintMat(src, color, amount = .88) {   // tiñe la ropa conservando el sombreado de la tela (la piel está en otras mallas)
    const m = track(src.clone()); const u = {value: new THREE.Color(color)}; TINTS.push(m);
    m.onBeforeCompile = sh => { sh.uniforms.uTint = u; sh.fragmentShader = 'uniform vec3 uTint;\n' + sh.fragmentShader.replace('#include <map_fragment>', `#include <map_fragment>
      float cxL = dot(diffuseColor.rgb, vec3(.299, .587, .114));
      diffuseColor.rgb = mix(diffuseColor.rgb, uTint * (.3 + cxL * 1.25), ${amount.toFixed(2)});`); };
    m.customProgramCacheKey = () => 'cx-bar-tint-' + amount.toFixed(2); return m;
  }
  const people = [];
  function makePerson(n, opts = {}) {
    const I = charInfo(n); const m = SkeletonUtils.clone(CH[n].scene);
    m.scale.multiplyScalar(I.scale); m.position.y = I.lift;
    m.traverse(x => { if (!x.isMesh) return; x.castShadow = !lite; x.receiveShadow = true; x.frustumCulled = false; x.userData.personShadow = true;
      const nm = x.name;
      if (opts.staff && /(Shirt|Tops|Pants|Bottoms|Shorts|Suit|Vest)/i.test(nm)) x.material = tintMat(x.material, RULES.STAFF_BLACK, .92);
      else if (opts.staff && /(Sneakers|Shoes|Boots)/i.test(nm)) x.material = tintMat(x.material, '#' + brandAccent.getHexString(), .8);
      else if (opts.tint && /(Shirt|Tops)$/i.test(nm)) x.material = tintMat(x.material, opts.tint); });
    const g = new THREE.Group(); g.add(m); S.add(g);
    if (opts.staff) {   // detalle del color de la marca en el pecho del uniforme negro
      let chest = null; m.traverse(x => { if (!chest && /Spine2$/.test(x.name)) chest = x; });
      if (chest) { m.updateMatrixWorld(true); const ws = chest.getWorldScale(new THREE.Vector3()).x || 1; const b = new THREE.Mesh(track(new THREE.BoxGeometry(.12, .07, .015)), badgeM);
        b.scale.setScalar(1 / ws); b.position.set(.07 / ws, .1 / ws, .13 / ws); chest.add(b); }
    }
    const hit = new THREE.Mesh(track(new THREE.CylinderGeometry(.32, .32, RULES.heightFor(n), 8)), hitM); hit.position.y = RULES.heightFor(n) / 2; g.add(hit);
    const p = {n, g, m, mixer: new THREE.AnimationMixer(m), actions: {}, cur: null, path: [], then: null, kind: opts.kind || 'cliente', info: opts.info || {name: 'Cliente', role: ''}, tag: null};
    hit.userData.person = p; PICK.push(hit); people.push(p);
    return p;
  }
  const badgeM = glow(brandAccent, 2.2);
  function play(p, name, t) {
    if (!p || !ANIMS[name] || p.cur === name) return;
    let a = p.actions[name]; if (!a) a = p.actions[name] = p.mixer.clipAction(clipFor(p.n, name));
    a.reset(); a.enabled = true; a.setEffectiveWeight(1); a.play(); if (t != null) a.time = t * a.getClip().duration;
    if (p.cur && p.actions[p.cur]) p.actions[p.cur].crossFadeTo(a, RULES.FADE, false);
    p.cur = name;
  }
  function dropPerson(p) {
    const i = people.indexOf(p); if (i >= 0) people.splice(i, 1);
    for (let k = PICK.length - 1; k >= 0; k--) if (PICK[k].userData.person === p) PICK.splice(k, 1);
    S.remove(p.g); p.mixer.stopAllAction(); dropTag(p.tag);
  }
  function place(p, [x, z, r], y = 0) { p.g.position.set(x, y, z); p.g.rotation.y = r; }
  function goTo(p, to, then) { p.path = RULES.route([p.g.position.x, p.g.position.z], to); p.g.position.y = 0; p.then = then || null; play(p, 'Walking'); }
  function arriveFromDoor(p, to, then, delay = 0) { place(p, [RULES.ENTRANCE[0], RULES.ENTRANCE[1], Math.PI]); p.g.visible = false;
    setTimeout(() => { if (!people.includes(p)) return; p.g.visible = true; goTo(p, to, then); }, delay); }
  function leave(p, delay = 0) { p.leaving = true; setTimeout(() => { if (!people.includes(p)) return; play(p, 'Idle'); setTimeout(() => goTo(p, RULES.ENTRANCE, () => dropPerson(p)), 450); }, delay); }

  // ------------------------------------------------------------- copia viva -> escena
  let closed = false;
  function sitAt(p, seat, clip, y = 0) { place(p, seat, y); play(p, clip, Math.random()); }
  function tableOpen(label, n, instant) {
    const t = TABLES.get(label); if (!t || t.guests.length || closed || !peopleOk) return;
    const cast = RULES.guestCast(label, t.stool != null ? 1 : n);
    cast.forEach((c, i) => {
      const p = makePerson(c.model, {tint: c.tint, info: {name: 'Cliente', role: label}}); t.guests.push(p);
      const seat = t.stool != null ? t.seats.n : t.seats[c.side]; const y = t.stool != null ? .3 : 0; const clip = t.stool != null ? 'Sitting_Drinking' : c.clip;
      if (instant) sitAt(p, seat, clip, y);
      else arriveFromDoor(p, [seat[0], seat[1]], () => { sitAt(p, seat, clip, y); }, i * 700);
    });
  }
  function tableClose(label) { const t = TABLES.get(label); if (!t) return; t.guests.splice(0).forEach((p, i) => leave(p, 300 + i * 450)); }
  function paintTables() {
    let li = 0;
    for (const s of snap.tables || []) {
      const t = TABLES.get(s.label); if (!t || t.stool != null) continue;
      const on = !!s.open && !closed;
      t.bulb.material = on ? bulbOn : bulbOff; t.soft.visible = on;
      const tt = RULES.tableTag(s.label, on);
      setTag(t.tag, `${tt.dot ? '<b class="dot">●</b> ' : ''}${esc(tt.text)}`, tt.cls);
      if (on && li < LAMP_LIGHTS.length) { const l = LAMP_LIGHTS[li++]; l.position.set(t.x, 2.3, t.z); l.intensity = 1.1; }
    }
    for (; li < LAMP_LIGHTS.length; li++) { LAMP_LIGHTS[li].intensity = 0; LAMP_LIGHTS[li].position.set(0, -10, 0); }
  }
  // AMBIENTE (no son datos): bailarines, clientes en taburetes y de pie. Solo con el bar abierto y mesas activas.
  const AMB = {dancers: [], stools: [], standers: []};
  function syncAmbient(instant) {
    if (!peopleOk) return;
    const want = {dancers: RULES.dancersFor(snap), ...RULES.ambientFor(snap)};
    const realStools = new Set(Object.values(layout.stools));
    const sets = {
      dancers: i => { const [x, z, r] = movedSpot(RULES.DANCERS[i], PISTA0, PISTA); return {model: ['Ch22_nonPBR', 'Remy', 'Ch21_nonPBR', 'Ch42_nonPBR'][i], clip: i === 2 ? 'Silly_Dancing' : 'Rumba_Dancing', seat: [x, z, r], y: 0, tint: RULES.HAPPY[i * 3]}; },
      stools: i => { const idx = RULES.AMBIENT_STOOLS[i]; return realStools.has(idx) ? null : {model: ['Ch42_nonPBR', 'Ch21_nonPBR', 'Remy'][i], clip: ['Sitting_Drinking', 'Sitting_Talking', 'Sitting_Laughing'][i], seat: [barX + .78, RULES.stoolZ(idx), -Math.PI / 2], y: .3, tint: RULES.HAPPY[i * 4 + 1]}; },
      standers: i => { const [x, z, r, clip] = RULES.STANDERS[i]; return {model: ['Ch06_nonPBR', 'Ch22_nonPBR'][i], clip, seat: [x, z, r], y: 0, tint: RULES.HAPPY[i + 5]}; },
    };
    for (const k of Object.keys(AMB)) {
      const list = AMB[k];
      while (list.length > want[k]) { const p = list.pop(); if (p) leave(p); }
      for (let i = list.length; i < want[k]; i++) { const c = sets[k](i); if (!c) { list.push(null); continue; }
        const p = makePerson(c.model, {tint: c.tint, info: {name: 'Cliente', role: 'Ambiente del bar'}}); list.push(p);
        if (instant) sitAt(p, c.seat, c.clip, c.y); else arriveFromDoor(p, [c.seat[0], c.seat[1]], () => sitAt(p, c.seat, c.clip, c.y), i * 900); }
    }
  }
  // personal en turno: en su puesto; pausa -> se aparta con Idle; cierra turno -> se va
  const STAFF = new Map();
  function staffTagHtml(s) {
    const p = s.data; let task = p.task || '';
    if (s.busy) task = `Llevando pedido · ${s.busy}`;
    if (p.uniform === 'dj' && !closed) { const now = RULES.nowPlaying(snap); if (now) task = `Sonando: ${now}`; }
    return `<i></i>${esc(RULES.staffTitle(p))} <small>· ${esc(task)}</small>`;
  }
  function syncStaff(list, instant) {
    if (!peopleOk) return;
    const seen = new Set(), counters = {};
    for (const person of list || []) {
      seen.add(person.key);
      const slot = person.paused ? 'pausa' : (person.uniform || ''); const idx = counters[slot] = (counters[slot] ?? -1) + 1;
      const spot = spotOf(person.uniform, idx, person.paused);
      const clip = person.uniform === 'barman' && !person.paused ? RULES.barmanClip(person.task, performance.now() / 1000, person.key) : spot.clip;
      let s = STAFF.get(person.key);
      if (!s) {
        const models = RULES.STAFF_MODEL[person.uniform] || RULES.STAFF_MODEL[''];
        const n = RULES.staffModel(models[idx % models.length], (o.rawCfg && o.rawCfg('staff', person.key, person.uniform)) || {}, person.key);   // género del editor
        const p = makePerson(n, {staff: person.uniform !== 'dj', kind: 'personal', info: {name: person.label, role: person.role, task: person.task}});
        s = {p, data: person, spot: spot.pos, clip}; STAFF.set(person.key, s);
        p.tag = tag(p.g, '', '', person.uniform === 'dj' ? 2.15 : 2.05);
        if (instant) sitAt(p, spot.pos, clip); else arriveFromDoor(p, [spot.pos[0], spot.pos[1]], () => sitAt(p, spot.pos, clip));
      } else if (!s.busy && (s.data.paused !== person.paused || Math.hypot(s.spot[0] - spot.pos[0], s.spot[1] - spot.pos[1]) > .3)) {
        s.spot = spot.pos; s.clip = clip; goTo(s.p, [spot.pos[0], spot.pos[1]], () => sitAt(s.p, spot.pos, clip));
      } else if (!s.busy && !s.p.path.length && s.clip !== clip) { s.clip = clip; play(s.p, clip); }
      s.data = person; s.p.info = {name: person.label, role: person.role, task: person.task};
      setTag(s.p.tag, staffTagHtml(s), person.paused ? 'pausa' : '');
    }
    for (const [k, s] of STAFF) if (!seen.has(k)) { STAFF.delete(k); dropTag(s.p.tag); s.p.tag = null; leave(s.p); }
  }
  function deliver(ev) {   // pedido entregado: el mesero lo recoge en la barra y camina a la mesa
    const s = [...STAFF.values()].find(x => (x.data.uniform === 'mesero' || x.data.uniform === '') && !x.data.paused && !x.busy);
    const t = TABLES.get(ev.table); if (!s || !t) return;
    s.busy = ev.table; setTag(s.p.tag, staffTagHtml(s));
    const dest = t.stool != null ? [barX + 1.4, t.z] : [t.x, t.z + 1.25];
    goTo(s.p, [barX + 1.3, 3.2], () => goTo(s.p, dest, () => { s.p.g.rotation.y = Math.PI; play(s.p, 'Idle');
      setTimeout(() => goTo(s.p, [s.spot[0], s.spot[1]], () => { s.busy = null; sitAt(s.p, s.spot, s.clip); setTag(s.p.tag, staffTagHtml(s)); }), 1800); }));
  }
  // representante en la entrada (traje), saluda de vez en cuando; globo con cifras de actividad (sin dinero)
  let rep = null, repWave = 0;
  function buildRep() {
    if (!peopleOk || rep) return;
    rep = makePerson(RULES.staffModel(RULES.REP_MODEL, (o.rawCfg && o.rawCfg('rep', 'rep')) || {}, 'rep'), {kind: 'rep', info: {name: o.repName || 'Representante', role: 'Representante de ' + floor.name}});
    sitAt(rep, RULES.REP, 'Waving'); rep.tag = tag(rep.g, '', 'rep');
  }
  function lights() {
    const k = closed ? .3 : 1;
    amb.intensity = closed ? .3 : .6; key.intensity = closed ? .25 : .9;
    POINTS.forEach(([l, i]) => { l.intensity = i * k; }); NEON.forEach(([m, i]) => { m.emissiveIntensity = i * (closed ? .25 : 1); });
    logoM.emissiveIntensity = closed ? .12 : .32;
  }
  function applySnap(next, first) {
    const prev = first ? null : snap; snap = next;
    const wasClosed = closed; closed = RULES.isClosed(snap);
    const b = snap.business || {};
    const chip = $('[data-biz]'); chip.textContent = b.open ? `Abierto · ${b.hours}` : (b.activity_off_hours ? `Fuera de horario con actividad · ${b.hours}` : (b.sign || 'Cerrado'));
    chip.className = 'rchip ' + (b.open ? 'ok' : 'bad');
    buildTables();
    if (closed && !wasClosed) for (const lbl of TABLES.keys()) tableClose(lbl);
    for (const e of RULES.diffBar(prev, snap)) {
      if (e.type === 'mesa_abierta') tableOpen(e.table, e.guests, e.instant);
      else if (e.type === 'mesa_cerrada') tableClose(e.table);
      else if (e.type === 'pedido_entregado') deliver(e);
    }
    // conciliación: lo que diga la copia viva manda aunque se haya perdido un evento
    for (const t of snap.tables || []) { const T = TABLES.get(t.label); if (!T) continue;
      if (t.open && !closed && !T.guests.length) tableOpen(t.label, RULES.guestsFor(t), first);
      if ((!t.open || closed) && T.guests.length) tableClose(t.label); }
    paintTables(); lights(); syncStaff((snap.staff || {}).people, first); syncAmbient(first); buildRep();
    if (rep) setTag(rep.tag, `<i></i>Representante <small>· ${esc(RULES.repBubble(snap))}</small>`, 'rep');
    djTag(); drawScreen(); R.shadowMap.needsUpdate = true;
  }
  let boothTag = null;
  function djTag() {   // sin DJ en turno pero con canción sonando: el globo queda sobre la cabina
    const hasDj = [...STAFF.values()].some(s => s.data.uniform === 'dj');
    const now = RULES.nowPlaying(snap);
    if (!hasDj && now && !closed) { if (!boothTag) boothTag = tag({position: new THREE.Vector3(DJP[0], 1.1, DJP[1])}, '', '', 1.0, true);
      setTag(boothTag, `<i></i>Cabina <small>· Sonando: ${esc(now)}</small>`); }
    else if (boothTag) { dropTag(boothTag); boothTag = null; }
  }

  // ------------------------------------------------------------- composición: brillo suave (fuerza 0,4, umbral 0,92)
  let composer = null;
  function buildComposer() {
    if (composer) composer.dispose();
    composer = new EffectComposer(R); composer.addPass(new RenderPass(S, C));
    if (!lite) composer.addPass(new UnrealBloomPass(new THREE.Vector2(innerWidth, innerHeight), .4, .45, .92));
    composer.addPass(new OutputPass());
  }
  function setLite(on) {
    lite = !!on; rendererMode(); S.traverse(x => { if (x.userData.personShadow) x.castShadow = !lite; });
    key.shadow.mapSize.set(lite ? 1024 : 2048, lite ? 1024 : 2048); if (key.shadow.map) { key.shadow.map.dispose(); key.shadow.map = null; }
    lampPool(); paintTables(); buildComposer(); resize();
  }

  // ------------------------------------------------------------- cámara (inicial como bar.html) y clics
  const T0 = new THREE.Vector3(...RULES.CAMERA.look), P0 = new THREE.Vector3(...RULES.CAMERA.pos).sub(T0);
  const cam = {dist: P0.length(), pol: Math.acos(P0.y / P0.length()), az: Math.atan2(P0.x, P0.z), tx: T0.x, tz: T0.z}; const goal = Object.assign({}, cam); const home = Object.assign({}, cam);
  // límites del bar (pisos_reglas.camLimits, giro hasta 1.0 como antes) y gestos sin "atrás" del navegador (oficina_gestos.js)
  const LIM = Object.assign(PR.camLimits(RULES.ROOM, RULES.CAMERA), {azMin: -1.0, azMax: 1.0}); const clampCam = g => PR.clampCam(g, LIM);
  const canvas = R.domElement; canvas.style.touchAction = 'none';
  let arch = {on: false, tick() {}, detach() {}};   // modo arquitecto (solo consola): se arma al final
  const gestures = attachGestures(canvas, {
    rotate: (dx, dy) => { goal.az -= dx * .005; goal.pol -= dy * .004; clampCam(goal); },
    pan: (dx, dy) => { goal.tx -= dx * .015 * Math.cos(cam.az) + dy * .015 * Math.sin(cam.az); goal.tz += dx * .015 * Math.sin(cam.az) - dy * .015 * Math.cos(cam.az); clampCam(goal); },
    zoom: f => { goal.dist *= f; clampCam(goal); },
    tap: e => { if (e.target === canvas && !arch.on) click(e); },
    reset: () => Object.assign(goal, home)});
  // paredes entre la cámara y el centro: se ocultan (las del bar se marcan al armarlo)
  const WALLS = {back: [], front: [], left: [], right: []}; let hidden = null;
  { const wb = new THREE.Box3(); S.updateMatrixWorld(true); S.traverse(x => { if (!x.isMesh || x.isSkinnedMesh || x.userData.person || x.userData.personShadow) return; wb.setFromObject(x); if (wb.isEmpty()) return;
    const side = PR.wallSide({min: wb.min.toArray(), max: wb.max.toArray()}, RULES.ROOM); if (side) WALLS[side].push(x); }); }
  function cutaway() { const h = PR.wallsToHide(C.position.toArray(), RULES.ROOM); const k = Object.keys(h).filter(q => h[q]).join(',');
    if (k === hidden) return; hidden = k; for (const [side, list] of Object.entries(WALLS)) list.forEach(m => { m.visible = !h[side]; }); R.shadowMap.needsUpdate = true; }
  const ray = new THREE.Raycaster(), mv = new THREE.Vector2();
  function click(e) {   // dentro del piso: persona -> su ficha; mesa -> su estado. Nunca cambia de piso.
    mv.set(e.clientX / innerWidth * 2 - 1, -(e.clientY / innerHeight) * 2 + 1); ray.setFromCamera(mv, C);
    const h = ray.intersectObjects(PICK.filter(x => { let k = x; while (k) { if (k !== x && !k.visible) return false; k = k.parent; } return true; }), false)[0];
    const target = RULES.clickTarget(h && h.object.userData);
    if (target.type === 'persona') { const p = h.object.userData.person; if (p.kind === 'rep') o.onRep && o.onRep(snap); else o.onPerson && o.onPerson(p.info, p.kind); }
    else if (target.type === 'mesa') o.onTable && o.onTable(RULES.tableInfo(snap, target.label));
  }

  // ------------------------------------------------------------- consulta (cada 7 s, pausa si la pestaña no se ve)
  let timer = null, dead = false;
  async function poll() {
    if (dead || document.hidden) return;
    try { const r = await getJson(`${API}/pisos/${cid}/vivo?rev=${encodeURIComponent(snap.rev || '')}`); if (!r.same) applySnap(r, false); }
    catch (e) { const chip = $('[data-biz]'); chip.textContent = 'Sin conexión'; chip.className = 'rchip bad'; }
  }
  function schedule() { clearTimeout(timer); if (!dead) timer = setTimeout(async () => { await poll(); schedule(); }, RULES.LIVE_MS); }
  const onVis = () => { if (document.hidden) clearTimeout(timer); else { poll(); schedule(); } };
  document.addEventListener('visibilitychange', onVis);

  // ------------------------------------------------------------- arranque
  try { await Promise.race([document.fonts.load('800 64px Inter'), new Promise(r => setTimeout(r, 1500))]); } catch (e) { /* fuente del sistema */ }
  $('[data-load]').textContent = 'Cargando las personas del bar…';
  try { await loadPeople(); } catch (e) { warn('Personajes del bar no disponibles: el piso se ve sin personas'); }
  const weight = () => { const st = [...used].reduce((a, f) => a + ((man.files[f] || {}).bytes || 0), 0);
    const mx = Object.entries((mixMan && mixMan.files) || {}).filter(([f]) => RULES.CHARACTERS.some(n => f === `personajes/${n}.glb`) || RULES.CLIPS.some(n => f === `animaciones/${n}.glb`)).reduce((a, [, m]) => a + m.bytes, 0);
    return {static: st, mixamo: peopleOk ? mx : 0, total: st + (peopleOk ? mx : 0)}; };
  const wt = weight(); $('[data-mb]').textContent = `${(wt.total / 1048576).toFixed(1)} MB`;
  applySnap(snap, true); buildComposer();
  $('[data-load]').remove(); schedule();
  $('[data-out]').onclick = () => o.onClose && o.onClose();
  arch = attachArchitect(o, {THREE, S, C, R, ui, room: RULES.ROOM, items: ARCH_ITEMS, cid, getJson, api: API, esc});
  log && log(`<b>${esc(floor.name)}</b> · bar listo (${(wt.total / 1048576).toFixed(1)} MB)`);
  function resize() { C.aspect = innerWidth / innerHeight; C.updateProjectionMatrix(); R.setSize(innerWidth, innerHeight, false); if (composer) composer.setSize(innerWidth, innerHeight); }
  addEventListener('resize', resize); resize();

  const clock = new THREE.Clock();
  let frames = 0, fpsT = 0, fpsShown = 0, fpsSamples = 0, frameNo = 0, lastScreen = 0, barmanSwap = 0;
  function tick() {
    const dt = Math.min(clock.getDelta(), .05), t = clock.elapsedTime, k = 1 - Math.pow(.003, dt);
    for (const q of ['az', 'pol', 'dist', 'tx', 'tz']) cam[q] += (goal[q] - cam[q]) * k;
    C.position.set(...PR.camPos(cam, T0.y));
    C.lookAt(cam.tx, T0.y, cam.tz); cutaway();
    for (const p of people) {
      p.mixer.update(dt);
      if (!p.path.length) continue;
      const [x, z] = p.path[0]; const r = p.g.position; const dx = x - r.x, dz = z - r.z, d = Math.hypot(dx, dz);
      if (d < .04) { r.x = x; r.z = z; p.path.shift(); if (!p.path.length) { const f = p.then; p.then = null; if (f) f(); else play(p, 'Idle'); } }
      else { const sp = Math.min(d, dt * WALK); r.x += dx / d * sp; r.z += dz / d * sp; let dr = Math.atan2(dx, dz) - p.g.rotation.y; dr = Math.atan2(Math.sin(dr), Math.cos(dr)); p.g.rotation.y += dr * Math.min(1, dt * 8); }
    }
    if (t - barmanSwap > 1) { barmanSwap = t;   // barra sin pedidos: el barman alterna Idle / Talking en su puesto
      for (const s of STAFF.values()) { if (s.data.uniform !== 'barman' || s.data.paused || s.busy || s.p.path.length) continue;
        const c = RULES.barmanClip(s.data.task, performance.now() / 1000, s.data.key); if (c !== s.clip) { s.clip = c; play(s.p, c); } } }
    if (rep && !rep.path.length && t - repWave > 10) { repWave = t; play(rep, 'Waving'); setTimeout(() => { if (rep && people.includes(rep)) play(rep, 'Idle'); }, 3200); }
    if (!closed) platters.forEach(m => { m.rotation.y = t * 3.5; });
    if (t - lastScreen > 2) { lastScreen = t; drawScreen(); }
    frameNo++; if (frameNo % (lite ? 4 : 3) === 0) R.shadowMap.needsUpdate = true;
    arch.tick(); composer.render(); placeTags();
    frames++; fpsT += dt; if (fpsT >= 1) { fpsShown = Math.round(frames / fpsT); frames = 0; fpsT = 0; fpsSamples++; $('[data-fps]').textContent = `${fpsShown} FPS${lite ? ' · liviano' : ''}`;
      if (fpsSamples === 6 && fpsShown < 30 && !lite && o.liteChosen && o.liteChosen() == null) { o.onAutoLite && o.onAutoLite(); } }
  }

  function close() {
    arch.detach(); dead = true; clearTimeout(timer); document.removeEventListener('visibilitychange', onVis);
    gestures.detach(); canvas.style.touchAction = ''; removeEventListener('resize', resize);
    people.slice().forEach(dropPerson); if (composer) composer.dispose();
    S.traverse(x => { if (x.geometry) x.geometry.dispose(); if (x.isInstancedMesh) x.dispose(); });
    disposables.forEach(d => { try { d.dispose(); } catch (e) { /* ya liberado */ } });
    ui.remove(); tagLayer.remove();
    R.useLegacyLights = saved.legacy; R.toneMapping = saved.tm; R.toneMappingExposure = saved.exp; R.shadowMap.type = saved.shadow; R.shadowMap.enabled = saved.se; R.setPixelRatio(saved.pr); R.shadowMap.autoUpdate = true; R.shadowMap.needsUpdate = true;
  }
  return {tick, close, setLite, resize, get fps() { return fpsShown; }, get snap() { return snap; }, get scene() { return S; }, get people() { return people.length; },
    get weight() { return weight(); }, get camera() { return C; }, apply: n => applySnap(n, false),
    rebuild() {   // el editor cambió un personaje (género, personaje, túnica...): el personal y el representante se rehacen en vivo
      for (const [, s] of STAFF) { dropTag(s.p.tag); s.p.tag = null; dropPerson(s.p); } STAFF.clear(); if (rep) { dropPerson(rep); rep = null; }
      if (snap) { syncStaff((snap.staff || {}).people, true); buildRep(); } },
    view(pos, look) { const t = new THREE.Vector3(...look), d = new THREE.Vector3(...pos).sub(t);   // mover la cámara (pruebas y recorridos)
      Object.assign(goal, {dist: d.length(), pol: Math.acos(d.y / d.length()), az: Math.atan2(d.x, d.z), tx: t.x, tz: t.z}); Object.assign(cam, goal); T0.y = t.y; }};
}
