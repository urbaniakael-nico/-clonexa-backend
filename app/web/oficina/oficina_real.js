// Oficina 3D · fase 1.5 · motor del piso REALISTA (interno de Clonexa, solo Admin V2).
// Se carga solo al abrir un piso con estilo "realista" (hoy solo The Time Machine): carga por piso.
// - Ambiente HDRI (Poly Haven, CC0), sombras suaves, oclusión ambiental (GTAO), brillo (bloom) y mapeo AgX.
// - Materiales PBR con texturas CC0 y muebles glTF reales comprimidos con meshopt (texturas WebP).
// - Personas con esqueleto y animaciones con transición suave (crossfade). Si están los personajes CC0 de
//   Quaternius en recursos/personajes/, se usan esos; si no, los de respaldo hechos en código.
// - Cámara casa de muñecas, copia viva cada 7 s (pausa si la pestaña no se ve) y modo arquitecto.
// Reglas puras en oficina_real_rules.js. Solo actividad: nunca dinero.
import * as THREE from 'three';
import {GLTFLoader} from 'three/addons/loaders/GLTFLoader.js';
import {MeshoptDecoder} from 'three/addons/libs/meshopt_decoder.module.js';
import {RGBELoader} from 'three/addons/loaders/RGBELoader.js';
import {EffectComposer} from 'three/addons/postprocessing/EffectComposer.js';
import {RenderPass} from 'three/addons/postprocessing/RenderPass.js';
import {GTAOPass} from 'three/addons/postprocessing/GTAOPass.js';
import {UnrealBloomPass} from 'three/addons/postprocessing/UnrealBloomPass.js';
import {OutputPass} from 'three/addons/postprocessing/OutputPass.js';
import * as SkeletonUtils from 'three/addons/utils/SkeletonUtils.js';
import {mergeGeometries} from 'three/addons/utils/BufferGeometryUtils.js';
import * as RULES from '/admin-v2plus/oficina/real_reglas.js';

const RES = '/admin-v2plus/oficina/recursos/';
const API = '/admin-v2/api/oficina';
const WALL_H = 4.2;
const SPEED = 1.35;

function esc(s) {
  return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

export async function openReal(o) {
  const {R, floor, getJson, log} = o;
  const cid = floor.company_id;
  const ui = document.createElement('div'); ui.id = 'realUi'; document.body.appendChild(ui);
  const tagLayer = document.createElement('div'); tagLayer.id = 'realTags'; document.body.appendChild(tagLayer);
  ui.innerHTML = `<div class="rbar glass"><button type="button" data-out>← Edificio</button><b>${esc(floor.name)}</b><span class="rchip" data-biz></span>
    <span class="rchip warn hidden" data-warn></span><span class="sp"></span><button type="button" data-arch>🏗 Modo arquitecto</button><span class="rfps" data-fps>…</span></div>
    <div class="rarch glass hidden" data-archbar><b>Modo arquitecto</b><span>Arrastra mesas, barra, DJ, pantalla, caja, entrada o zona de personal.</span>
    <button type="button" data-rot>↻ Girar</button><button type="button" class="pri" data-save>💾 Guardar</button><button type="button" data-auto>Acomodar automático</button><button type="button" data-archx>Salir</button></div>
    <div class="rload" data-load>Cargando el piso realista…</div>`;
  const $ = s => ui.querySelector(s);

  // ------------------------------------------------------------- renderer (se restaura al salir)
  const saved = {legacy: R.useLegacyLights, tm: R.toneMapping, exp: R.toneMappingExposure, shadow: R.shadowMap.type, se: R.shadowMap.enabled, pr: R.getPixelRatio()};
  let lite = !!o.lite;
  function rendererMode() {
    R.useLegacyLights = false; R.toneMapping = THREE.AgXToneMapping; R.toneMappingExposure = 1.05;
    R.shadowMap.enabled = true; R.shadowMap.autoUpdate = false; R.shadowMap.type = lite ? THREE.BasicShadowMap : THREE.PCFSoftShadowMap; R.shadowMap.needsUpdate = true;
    R.setPixelRatio(lite ? 1 : Math.min(devicePixelRatio, 1.25));
  }
  rendererMode();

  const S = new THREE.Scene();
  const C = new THREE.PerspectiveCamera(40, innerWidth / innerHeight, .1, 300);
  const disposables = [];
  const track = x => { disposables.push(x); return x; };

  // ------------------------------------------------------------- recursos
  const man = await getJson(RES + 'manifest.json');
  const has = f => !!(man.files && man.files[f]);
  const url = f => RES + f + '?v=' + ((man.files[f] || {}).sha || '1');
  const gltf = new GLTFLoader(); gltf.setMeshoptDecoder(MeshoptDecoder);
  const texL = new THREE.TextureLoader();
  const loadModel = k => has(`modelos/${k}.glb`) ? gltf.loadAsync(url(`modelos/${k}.glb`)).then(g => g.scene).catch(() => null) : Promise.resolve(null);
  const MODELS = {};
  const PEOPLE = {};
  const modelKeys = ['taburete', 'mesa', 'silla', 'sofa', 'botellas', 'lampara', 'planta', 'caja', 'barril'];
  const personKeys = Object.keys(man.files || {}).filter(f => /^personajes\/.+\.glb$/.test(f));
  const hdr = has('hdri/warm_bar_1k.hdr') ? new RGBELoader().loadAsync(url('hdri/warm_bar_1k.hdr')).catch(() => null) : Promise.resolve(null);
  const [envTex] = await Promise.all([hdr, ...modelKeys.map(k => loadModel(k).then(m => { MODELS[k] = m; })),
    ...personKeys.map(f => gltf.loadAsync(url(f)).then(g => { PEOPLE[f.split('/')[1].replace('.glb', '')] = g; }).catch(() => null))]);
  if (envTex) { const pm = new THREE.PMREMGenerator(R); S.environment = track(pm.fromEquirectangular(envTex).texture); envTex.dispose(); pm.dispose(); }

  const TEX = {};
  function tex(key, map, rep) {
    const f = `texturas/${key}_${map}.webp`;
    if (!has(f)) return null;
    const t = track(texL.load(url(f)));
    t.wrapS = t.wrapT = THREE.RepeatWrapping; t.repeat.set(rep[0], rep[1]); t.anisotropy = lite ? 1 : 8;
    if (map === 'diff') t.colorSpace = THREE.SRGBColorSpace;
    return t;
  }
  function pbr(key, opts = {}) {
    const rep = opts.rep || [1, 1];
    const id = key + rep.join('x') + (opts.color || '');
    if (TEX[id]) return TEX[id];
    const arm = tex(key, 'arm', rep);
    const m = new THREE.MeshStandardMaterial({color: opts.color || 0xffffff, map: tex(key, 'diff', rep), normalMap: lite ? null : tex(key, 'nor_gl', rep),
      aoMap: arm, roughnessMap: arm, metalnessMap: opts.metal ? arm : null, roughness: opts.rough ?? 1, metalness: opts.metal ? 1 : 0, envMapIntensity: opts.env ?? .7});
    return (TEX[id] = track(m));
  }
  const mat = (c, x = {}) => track(new THREE.MeshStandardMaterial(Object.assign({color: c, roughness: .6, metalness: 0, envMapIntensity: .7}, x)));
  const glow = (c, i = 2.4) => track(new THREE.MeshStandardMaterial({color: 0x000000, emissive: new THREE.Color(c), emissiveIntensity: i, roughness: 1}));

  // ------------------------------------------------------------- marca de la empresa
  let snap = await getJson(`${API}/pisos/${cid}/vivo`);
  let brand = snap.brand || floor.brand || {};
  const B = {accent: brand.accent || '#b08d57', accent2: brand.accent2 || '#3b4b5a', primary: (brand.colors || {}).primary || '#b08d57',
    secondary: (brand.colors || {}).secondary || '#3b4b5a', bg: brand.screen_bg || '#141519', text: brand.screen_text || '#ffffff'};
  const accentMat = glow(B.accent, 2.6), accent2Mat = glow(B.accent2, 1.6);
  const carpetMat = pbr('tela', {rep: [3, 3], color: new THREE.Color(B.primary).lerp(new THREE.Color('#1a1418'), .35)});
  const upholstery = new THREE.Color(B.primary).lerp(new THREE.Color('#222'), .25);
  let logoTex = null;
  function loadLogo() {
    if (!brand.logo_url) return;
    texL.load(brand.logo_url, t => { t.colorSpace = THREE.SRGBColorSpace; logoTex = track(t); logoMeshes.forEach(m => { m.material.map = t; m.material.emissiveMap = t; m.material.needsUpdate = true; m.visible = true; }); });
  }
  const logoMeshes = [];
  if (brand.warning) { $('[data-warn]').textContent = brand.warning; $('[data-warn]').classList.remove('hidden'); }

  // ------------------------------------------------------------- salón
  S.background = new THREE.Color(new THREE.Color(B.bg).lerp(new THREE.Color('#050406'), .7));
  const hemi = new THREE.HemisphereLight(0xffe2c4, 0x1a1016, .35); S.add(hemi);
  const key = new THREE.DirectionalLight(0xffe7cf, 1.6); key.castShadow = true; key.shadow.mapSize.set(lite ? 512 : 1024, lite ? 512 : 1024);
  key.shadow.bias = -.0005; key.shadow.normalBias = .02; S.add(key); S.add(key.target);
  const ROOM = new THREE.Group(); S.add(ROOM);
  const WALLS = {fondo: [], izquierda: [], derecha: [], frente: []};
  const OBJ = new THREE.Group(); S.add(OBJ);
  const PICK = [];
  const layoutGroups = new Map();
  let room = snap.layout.room;
  const lamps = [], anims = [];

  function shadowAll(g, cast = true) { g.traverse(x => { if (x.isMesh) { x.castShadow = cast; x.receiveShadow = true; if (x.material && 'envMapIntensity' in x.material) x.material.envMapIntensity = .7; } }); return g; }
  function clone(k) { const m = MODELS[k]; return m ? shadowAll(m.clone(true)) : null; }
  function boxMesh(w, h, d, m, x, y, z, p) { const k = new THREE.Mesh(track(new THREE.BoxGeometry(w, h, d)), m); k.position.set(x, y, z); k.castShadow = k.receiveShadow = true; p.add(k); return k; }
  function cyl(rt, rb, h, m, x, y, z, p, seg = 24) { const k = new THREE.Mesh(track(new THREE.CylinderGeometry(rt, rb, h, seg)), m); k.position.set(x, y, z); k.castShadow = k.receiveShadow = true; p.add(k); return k; }
  function canvasTex(w, h, draw) { const c = document.createElement('canvas'); c.width = w; c.height = h; draw(c.getContext('2d'), w, h); const t = track(new THREE.CanvasTexture(c)); t.colorSpace = THREE.SRGBColorSpace; t.userData.canvas = c; return t; }
  function label(text, w = 512, h = 128, fg = '#fff', bg = 'rgba(0,0,0,0)', size = 64) {
    return canvasTex(w, h, (x) => { x.fillStyle = bg; x.fillRect(0, 0, w, h); x.fillStyle = fg; x.font = `800 ${size}px Inter, system-ui, sans-serif`; x.textAlign = 'center'; x.textBaseline = 'middle'; x.fillText(String(text).slice(0, 28), w / 2, h / 2); });
  }

  function buildRoom() {
    while (ROOM.children.length) ROOM.remove(ROOM.children[0]);
    Object.values(WALLS).forEach(l => l.length = 0); logoMeshes.length = 0;
    const {W, D} = room;
    const fl = new THREE.Mesh(track(new THREE.PlaneGeometry(W, D)), pbr('piso', {rep: [W / 2.2, D / 2.2], rough: 1})); fl.rotation.x = -Math.PI / 2; fl.receiveShadow = true; ROOM.add(fl);
    const wallM = pbr('pared', {rep: [W / 3, WALL_H / 3]}), sideM = pbr('pared', {rep: [D / 3, WALL_H / 3]});
    WALLS.fondo.push(boxMesh(W + .5, WALL_H, .25, wallM, 0, WALL_H / 2, -D / 2 - .125, ROOM));
    WALLS.izquierda.push(boxMesh(.25, WALL_H, D, sideM, -W / 2 - .125, WALL_H / 2, 0, ROOM));
    WALLS.derecha.push(boxMesh(.25, WALL_H, D, sideM, W / 2 + .125, WALL_H / 2, 0, ROOM));
    // frente: zócalo bajo y columnas (se ocultan cuando tapan)
    WALLS.frente.push(boxMesh(W + .5, .35, .25, wallM, 0, .175, D / 2 + .125, ROOM));
    for (const x of [-W / 2, -W / 6, W / 6, W / 2]) WALLS.frente.push(boxMesh(.45, WALL_H, .45, pbr('concreto', {rep: [1, 3]}), x, WALL_H / 2, D / 2 + .1, ROOM));
    // pared de acento (izquierda) con el LOGO grande y neón de la marca
    const acc = boxMesh(.06, WALL_H - .6, D * .62, mat(new THREE.Color(B.primary).lerp(new THREE.Color('#0b0a0c'), .55), {roughness: .85}), -W / 2 + .04, WALL_H / 2, 0, ROOM);
    WALLS.izquierda.push(acc);
    const lm = new THREE.Mesh(track(new THREE.PlaneGeometry(Math.min(5.2, D * .5), Math.min(5.2, D * .5) * .5)),
      track(new THREE.MeshStandardMaterial({color: 0xffffff, transparent: true, emissive: 0xffffff, emissiveIntensity: .9, roughness: .5})));
    lm.position.set(-W / 2 + .09, WALL_H * .58, 0); lm.rotation.y = Math.PI / 2; lm.visible = false; ROOM.add(lm); logoMeshes.push(lm); WALLS.izquierda.push(lm);
    [[0, WALL_H - .32, D * .62, .05], [0, .32, D * .62, .05]].forEach(([, y, len]) => WALLS.izquierda.push(boxMesh(.05, .05, len, accentMat, -W / 2 + .1, y, 0, ROOM)));
    WALLS.fondo.push(boxMesh(W, .05, .05, accentMat, 0, WALL_H - .25, -D / 2 + .05, ROOM));
    // alfombra de la marca (lounge) y pista
    const rug = new THREE.Mesh(track(new THREE.PlaneGeometry(6, 4)), carpetMat); rug.rotation.x = -Math.PI / 2; rug.position.set(-W / 2 + 4.2, .012, D / 2 - 3.2); rug.receiveShadow = true; ROOM.add(rug);
    if (logoTex) loadLogoNow();
    key.position.set(W * .3, 14, D * .55); key.target.position.set(0, 0, 0);
    Object.assign(key.shadow.camera, {left: -W / 1.6, right: W / 1.6, top: D / 1.4, bottom: -D / 1.4, near: 1, far: 40}); key.shadow.camera.updateProjectionMatrix();
  }
  function loadLogoNow() { logoMeshes.forEach(m => { m.material.map = logoTex; m.material.emissiveMap = logoTex; m.material.needsUpdate = true; m.visible = true; }); }

  // ------------------------------------------------------------- objetos del piso (cada uno movible en modo arquitecto)
  function place(keyName, build) {
    let g = layoutGroups.get(keyName);
    if (!g) { g = new THREE.Group(); g.userData.layoutKey = keyName; build(g); mergeStatic(g); OBJ.add(g); layoutGroups.set(keyName, g); g.traverse(x => { if (x.isMesh) { x.userData.layout = g; PICK.push(x); } }); }
    const v = snap.layout.items[keyName]; if (v) { g.position.set(v[0], 0, v[1]); g.rotation.y = v[2]; }
    return g;
  }
  // Rendimiento: las mallas fijas de cada objeto se funden por material (una llamada de dibujo por material).
  const ATTRS = ['position', 'normal', 'uv'];
  function bake(o, m) {
    let geo = o.geometry.index ? o.geometry.toNonIndexed() : o.geometry.clone();
    for (const k of Object.keys(geo.attributes)) if (!ATTRS.includes(k)) geo.deleteAttribute(k);
    if (!geo.attributes.normal) geo.computeVertexNormals();
    if (!geo.attributes.uv) geo.setAttribute('uv', new THREE.Float32BufferAttribute(new Float32Array(geo.attributes.position.count * 2), 2));
    geo.morphAttributes = {}; geo.applyMatrix4(m); return geo;
  }
  function mergeStatic(g) {
    g.updateMatrixWorld(true);
    const inv = new THREE.Matrix4().copy(g.matrixWorld).invert(), buckets = new Map();
    g.traverse(o => { if (!o.isMesh || o.isSkinnedMesh || o.isInstancedMesh || o.userData.keep || Array.isArray(o.material)) return;
      const k = o.material.uuid + '|' + o.castShadow; if (!buckets.has(k)) buckets.set(k, []); buckets.get(k).push(o); });
    for (const list of buckets.values()) {
      if (list.length < 2) continue;
      const merged = mergeGeometries(list.map(o => bake(o, new THREE.Matrix4().multiplyMatrices(inv, o.matrixWorld))));
      if (!merged) continue;
      const m = new THREE.Mesh(track(merged), list[0].material); m.castShadow = list[0].castShadow; m.receiveShadow = true; g.add(m);
      list.forEach(o => o.parent && o.parent.remove(o));
    }
  }
  const SPOT = {};  // puestos en coordenadas locales de cada objeto
  function world(g, local) { const v = new THREE.Vector3(local[0], 0, local[1]).applyMatrix4(g.matrixWorld); return [v.x, v.z, g.rotation.y + (local[2] || 0)]; }

  function buildBar(g) {
    const wood = pbr('madera', {rep: [4, 1]}), top = mat('#121014', {roughness: .18, metalness: .2}), metal = pbr('metal', {rep: [3, 1], metal: true, rough: .5});
    boxMesh(9, 1.05, .8, wood, 0, .525, 0, g); boxMesh(9.2, .07, 1.05, top, 0, 1.08, .05, g); boxMesh(9.1, .05, .05, metal, 0, .2, .42, g);
    boxMesh(9, .04, .03, accentMat, 0, .06, .41, g);
    for (let i = 0; i < 6; i++) { const s = clone('taburete'); if (s) { s.position.set(-3.75 + i * 1.5, 0, 1.0); s.rotation.y = Math.PI; g.add(s); } }
    // contrabarra con botellas y luz de fondo
    boxMesh(9, 2.8, .45, wood, 0, 1.4, -1.55, g); const back = boxMesh(8.6, 1.9, .02, accent2Mat, 0, 2.0, -1.31, g); back.castShadow = false;
    for (let s = 0; s < 3; s++) { boxMesh(8.6, .04, .4, metal, 0, 1.25 + s * .62, -1.25, g); }
    const b = MODELS.botellas;
    if (b) { const bb = new THREE.Box3().setFromObject(b); const wB = bb.max.x - bb.min.x || 1; const n = lite ? 3 : 5;
      for (let s = 0; s < 3; s++) for (let i = 0; i < n; i++) { const c = clone('botellas'); c.traverse(x => { if (x.isMesh) x.castShadow = false; }); c.scale.setScalar(Math.min(1, .9 / wB)); c.position.set(-3.9 + i * (7.8 / (n - 1)), 1.27 + s * .62, -1.25); g.add(c); } }
    boxMesh(9, .9, .55, wood, 0, .45, -.95, g);   // mesa de trabajo del barman
    const sp = new THREE.SpotLight(0xffd6a8, 30, 9, .75, .6, 1.4); sp.position.set(0, 3.9, .4); sp.target.position.set(0, 1, .2); sp.castShadow = false;
    sp.shadow.mapSize.set(1024, 1024); g.add(sp); g.add(sp.target);
    SPOT.barra = [[-2.6, -.55, Math.PI], [0, -.55, Math.PI], [2.6, -.55, Math.PI]].map(p => [p[0], p[1], 0]);
    SPOT.pickup = [4.2, .9, 0];
  }
  function buildCaja(g) {
    boxMesh(1.6, 1.05, .7, pbr('madera', {rep: [1, 1]}), 0, .525, 0, g); const c = clone('caja'); if (c) { c.position.set(0, 1.05, 0); c.rotation.y = 0; g.add(c); }
    SPOT.caja = [[0, -.75, 0]];
  }
  function buildDj(g) {
    const dark = mat('#141216', {roughness: .35, metalness: .3});
    boxMesh(2.6, 1.05, .9, dark, 0, .525, 0, g); const front = boxMesh(2.5, .7, .02, accentMat, 0, .55, .46, g); front.castShadow = false;
    const decks = [];
    for (const x of [-.75, .75]) { cyl(.21, .21, .04, mat('#0a0a0a', {roughness: .25}), x, 1.08, 0, g); const v = cyl(.18, .18, .01, mat('#1b1b1b', {roughness: .15, metalness: .4}), x, 1.11, 0, g, 32); v.userData.keep = true; decks.push(v); }
    boxMesh(.5, .06, .4, mat('#202024', {metalness: .6, roughness: .3}), 0, 1.09, 0, g); boxMesh(.4, .02, .3, glow(B.accent2, 2), 0, 1.125, 0, g);
    for (const x of [-1.75, 1.75]) { boxMesh(.7, 1.6, .6, pbr('tela', {rep: [1, 2], color: '#2a2a2e'}), x, .8, 0, g); cyl(.22, .22, .03, mat('#111', {roughness: .3}), x, 1.05, .31, g).rotation.x = Math.PI / 2; }
    const beams = [B.accent, B.accent2].map((c, i) => { const s = new THREE.SpotLight(new THREE.Color(c), lite ? 0 : 25, 14, .35, .5, 1.2); s.position.set(i ? 1.2 : -1.2, 3.9, .5); g.add(s); g.add(s.target); return s; });
    anims.push(t => { decks.forEach(d => { d.rotation.y = t * 3.5; }); beams.forEach((s, i) => { s.target.position.set(Math.sin(t * .7 + i * 2) * 4, 0, 3 + Math.cos(t * .5 + i) * 2.5); }); });
    SPOT.dj = [[0, -.8, 0]];
  }
  let screenTex = null, screenMode = 'marca';
  function buildScreen(g) {
    boxMesh(4.4, 2.6, .1, mat('#08080a', {roughness: .25, metalness: .5}), 0, 2.35, 0, g);
    screenTex = canvasTex(1024, 576, () => {});
    const m = new THREE.Mesh(track(new THREE.PlaneGeometry(4.2, 2.36)), track(new THREE.MeshStandardMaterial({color: 0x000000, emissive: 0xffffff, emissiveMap: screenTex, emissiveIntensity: 1.25, roughness: .4})));
    m.position.set(0, 2.35, .06); g.add(m); drawScreen(0);
  }
  function drawScreen(t) {
    const c = screenTex.userData.canvas, x = c.getContext('2d'), w = c.width, h = c.height;
    x.fillStyle = B.bg; x.fillRect(0, 0, w, h);
    const gr = x.createLinearGradient(0, 0, w, h); gr.addColorStop(0, B.primary + '55'); gr.addColorStop(1, B.secondary + '33'); x.fillStyle = gr; x.fillRect(0, 0, w, h);
    x.fillStyle = B.text; x.textAlign = 'center'; x.textBaseline = 'middle';
    const g = snap.game;
    if (g && g.kind === 'roulette') {
      const cx = w / 2, cy = h / 2 + 20, r = 190, n = 12;
      for (let i = 0; i < n; i++) { x.beginPath(); x.moveTo(cx, cy); x.arc(cx, cy, r, t * 2 + i * 2 * Math.PI / n, t * 2 + (i + 1) * 2 * Math.PI / n); x.fillStyle = i % 2 ? B.primary : B.secondary; x.fill(); }
      x.fillStyle = B.text; x.beginPath(); x.moveTo(cx, cy - r - 24); x.lineTo(cx - 16, cy - r - 52); x.lineTo(cx + 16, cy - r - 52); x.fill();
      x.font = '800 48px Inter, sans-serif'; x.fillText('Ruleta', w / 2, 44);
    } else if (g && g.kind === 'trivia') {
      x.font = '900 220px Inter, sans-serif'; x.globalAlpha = .85 + .15 * Math.sin(t * 4); x.fillText('?', w / 2, h / 2 + 10); x.globalAlpha = 1;
      x.font = '800 52px Inter, sans-serif'; x.fillText('Trivia', w / 2, 60);
    } else if (g && g.kind === 'memory') {
      for (let i = 0; i < 4; i++) for (let j = 0; j < 3; j++) { const flip = Math.sin(t * 2 + i + j * 2) > .4; x.fillStyle = flip ? B.text : B.primary; x.fillRect(232 + i * 145, 130 + j * 135, 120, 115); }
      x.fillStyle = B.text; x.font = '800 52px Inter, sans-serif'; x.fillText('Memoria', w / 2, 60);
    } else {
      const lines = RULES.screenLines(snap);
      x.font = '900 86px Inter, sans-serif'; x.fillText(lines[0] || floor.name, w / 2, h / 2 - 50);
      x.font = '600 46px Inter, sans-serif'; x.fillText(String(lines[1] || 'Bienvenidos').slice(0, 34), w / 2, h / 2 + 50);
    }
    if (g) { x.font = '600 34px Inter, sans-serif'; x.fillText(g.state === 'playing' ? 'Jugando ahora' : 'Inscríbete con el QR', w / 2, h - 46); }
    screenTex.needsUpdate = true;
  }
  let doorSign = null;
  function buildEntrance(g) {
    const metal = pbr('metal', {rep: [1, 2], metal: true, rough: .45});
    boxMesh(.18, 3, .3, metal, -1.1, 1.5, 0, g); boxMesh(.18, 3, .3, metal, 1.1, 1.5, 0, g); boxMesh(2.4, .25, .32, metal, 0, 3.05, 0, g);
    doorSign = label('Entrada', 512, 128, B.text, B.bg, 60);
    const s = new THREE.Mesh(track(new THREE.PlaneGeometry(2.2, .55)), track(new THREE.MeshStandardMaterial({color: 0x000000, emissive: 0xffffff, emissiveMap: doorSign, emissiveIntensity: 1.1})));
    s.position.set(0, 3.5, .05); g.add(s);
    const b = clone('barril'); if (b) { b.position.set(-1.9, 0, -.4); g.add(b); }
    SPOT.entrada = [0, -.4, Math.PI]; SPOT.rep = [-1.6, -1.1, Math.PI * .85];
  }
  function buildStaffZone(g) {
    const t = clone('mesa'); if (t) { t.scale.setScalar(.8); g.add(t); }
    boxMesh(.5, 1.1, .45, mat('#1d1d20', {metalness: .6, roughness: .3}), 1.4, .55, -.6, g); boxMesh(.3, .25, .3, mat('#c9c9cf', {metalness: .9, roughness: .2}), 1.4, 1.22, -.6, g);
    const s = clone('sofa'); if (s) { s.position.set(-.2, 0, 1.7); s.rotation.y = Math.PI; tint(s, upholstery); g.add(s); }
    const p = clone('planta'); if (p && !lite) { p.position.set(-1.6, 0, -.8); g.add(p); }
    const sign = new THREE.Mesh(track(new THREE.PlaneGeometry(1.6, .4)), track(new THREE.MeshBasicMaterial({map: label('Personal', 512, 128, '#fff', 'rgba(0,0,0,.55)', 56), transparent: true})));
    sign.position.set(0, 2.2, -.9); g.add(sign);
    SPOT.personal = [[-.9, .5, Math.PI / 2], [.9, .5, -Math.PI / 2], [0, -.9, 0]];
  }
  function tint(model, color) { model.traverse(x => { if (x.isMesh && x.material) { x.material = x.material.clone(); track(x.material); if (x.material.color) x.material.color.lerp(color, .65); } }); }
  const TABLES = new Map();
  function buildTable(g, labelText) {
    const t = clone('mesa'); if (t) g.add(t); else boxMesh(1.1, .76, 1.1, pbr('madera'), 0, .38, 0, g);
    const seats = [];
    [[0, .95, Math.PI], [0, -.95, 0], [.95, 0, -Math.PI / 2], [-.95, 0, Math.PI / 2]].forEach(([x, z, r]) => {
      const c = clone('silla'); if (c) { c.position.set(x, 0, z); c.rotation.y = r + Math.PI; g.add(c); } seats.push([x * .92, z * .92, r]); });
    const plate = new THREE.Sprite(track(new THREE.SpriteMaterial({map: label(labelText, 512, 128, '#fff', 'rgba(10,8,12,.72)', 58), depthWrite: false})));
    plate.scale.set(1.3, .32, 1); plate.position.set(0, 1.55, 0); g.add(plate);
    if (MODELS.lampara) { const l = clone('lampara'); l.traverse(x => { if (x.isMesh) x.castShadow = false; }); const bb = new THREE.Box3().setFromObject(l); l.position.set(0, WALL_H - (bb.max.y - bb.min.y) - .05, 0); g.add(l);
      // solo unas pocas luces puntuales reales (cada luz cuesta en todo el piso); las demas lamparas brillan por su bombillo
      if (lamps.length < (lite ? 2 : 4) && TABLES.size % 3 === 0) { const pl = new THREE.PointLight(0xffc98a, lite ? 6 : 9, 6, 1.5); pl.position.set(0, WALL_H - (bb.max.y - bb.min.y) - .2, 0); g.add(pl); lamps.push(pl); }
      const bulb = new THREE.Mesh(track(new THREE.SphereGeometry(.06, 10, 8)), glow('#ffcf8a', 3)); bulb.position.set(0, WALL_H - (bb.max.y - bb.min.y) - .12, 0); g.add(bulb); }
    TABLES.set(labelText, {g, seats, guests: [], label: labelText, pending: 0});
  }
  function buildLayout() {
    buildRoom();
    place('barra', buildBar); place('caja', buildCaja); place('dj', buildDj); place('pantalla', buildScreen); place('entrada', buildEntrance); place('personal', buildStaffZone);
    syncTables();
    // decoración fija
    const p1 = clone('planta'); if (p1 && !lite) { p1.position.set(room.W / 2 - .8, 0, -room.D / 2 + 4.6); ROOM.add(p1); }
  }
  function syncTables() {
    const want = new Set(Object.keys(snap.layout.items).filter(k => k.startsWith('mesa:')).map(k => k.slice(5)));
    for (const [lbl, t] of TABLES) if (!want.has(lbl)) { t.guests.forEach(dropPerson); OBJ.remove(t.g); layoutGroups.delete('mesa:' + lbl); TABLES.delete(lbl); }
    for (const lbl of want) place('mesa:' + lbl, g => buildTable(g, lbl));
    for (const [k, g] of layoutGroups) { const v = snap.layout.items[k]; if (v && !arch.on) { g.position.set(v[0], 0, v[1]); g.rotation.y = v[2]; } }
    OBJ.updateMatrixWorld(true);
  }

  // ------------------------------------------------------------- personas (esqueleto + animaciones con crossfade)
  const people = [];
  const SKIN = ['#f2cfb3', '#dcab86', '#b07a55', '#7d4f34'];
  const CLIPS = proceduralClips();
  function proceduralClips() {
    const Q = new THREE.Quaternion(), E = new THREE.Euler();
    const q = (x, y = 0, z = 0) => { E.set(x, y, z); Q.setFromEuler(E); return [Q.x, Q.y, Q.z, Q.w]; };
    const SEAT = {legL: [-1.45, 0, 0], legR: [-1.45, 0, 0], shinL: [1.45, 0, 0], shinR: [1.45, 0, 0]};
    function clip(name, dur, keys, opts = {}) {
      // keys: {bone: [[t, [x,y,z]], ...]} ; opts.hips: [[t, y]] ; opts.base: pose fija
      const tracks = [];
      const bones = new Set([...Object.keys(keys), ...Object.keys(opts.base || {})]);
      for (const b of bones) {
        const k = keys[b] || [[0, opts.base[b]], [dur, opts.base[b]]];
        tracks.push(new THREE.QuaternionKeyframeTrack(b + '.quaternion', k.map(x => x[0]), k.flatMap(x => q(...x[1]))));
      }
      if (opts.hips) tracks.push(new THREE.VectorKeyframeTrack('hips.position', opts.hips.map(x => x[0]), opts.hips.flatMap(x => [0, x[1], 0])));
      return new THREE.AnimationClip(name, dur, tracks);
    }
    const rest = {armL: [0, 0, .12], armR: [0, 0, -.12], foreL: [-.15, 0, 0], foreR: [-.15, 0, 0]};
    const seated = Object.assign({}, SEAT, {foreL: [-.9, 0, 0], foreR: [-.9, 0, 0], armL: [-.35, 0, .1], armR: [-.35, 0, -.1]});
    const walkLeg = (a) => [[0, [a, 0, 0]], [.5, [-a, 0, 0]], [1, [a, 0, 0]]];
    const out = {
      quieto: clip('quieto', 3, {chest: [[0, [0, 0, 0]], [1.5, [.03, 0, 0]], [3, [0, 0, 0]]], head: [[0, [0, 0, 0]], [1.5, [.04, .08, 0]], [3, [0, 0, 0]]]}, {base: rest, hips: [[0, .95], [3, .95]]}),
      caminar: clip('caminar', 1, {legL: walkLeg(.5), legR: walkLeg(-.5), shinL: [[0, [.1, 0, 0]], [.25, [.7, 0, 0]], [.5, [.1, 0, 0]], [1, [.1, 0, 0]]],
        shinR: [[0, [.1, 0, 0]], [.5, [.1, 0, 0]], [.75, [.7, 0, 0]], [1, [.1, 0, 0]]], armL: walkLeg(-.4).map(([t, v]) => [t, [v[0], 0, .1]]), armR: walkLeg(.4).map(([t, v]) => [t, [v[0], 0, -.1]])},
      {base: {foreL: [-.3, 0, 0], foreR: [-.3, 0, 0]}, hips: [[0, .95], [.25, .92], [.5, .95], [.75, .92], [1, .95]]}),
      sentarse: clip('sentarse', .8, {legL: [[0, [0, 0, 0]], [.8, SEAT.legL]], legR: [[0, [0, 0, 0]], [.8, SEAT.legR]], shinL: [[0, [0, 0, 0]], [.8, SEAT.shinL]], shinR: [[0, [0, 0, 0]], [.8, SEAT.shinR]]},
        {base: rest, hips: [[0, .95], [.8, .52]]}),
      sentado_hablando: clip('sentado_hablando', 3, {armR: [[0, [-.35, 0, -.1]], [.8, [-.9, .3, -.3]], [1.6, [-.35, 0, -.1]], [3, [-.35, 0, -.1]]], head: [[0, [0, 0, 0]], [.7, [.1, .25, 0]], [1.8, [-.05, -.2, 0]], [3, [0, 0, 0]]]},
        {base: seated, hips: [[0, .52], [3, .52]]}),
      teclear: clip('teclear', .6, {foreL: [[0, [-1.3, 0, 0]], [.3, [-1.2, 0, 0]], [.6, [-1.3, 0, 0]]], foreR: [[0, [-1.2, 0, 0]], [.3, [-1.3, 0, 0]], [.6, [-1.2, 0, 0]]], head: [[0, [.25, 0, 0]], [.6, [.25, 0, 0]]]},
        {base: {armL: [-.3, 0, .15], armR: [-.3, 0, -.15]}, hips: [[0, .95], [.6, .95]]}),
      servir: clip('servir', 1, {legL: walkLeg(.45), legR: walkLeg(-.45), armL: walkLeg(-.3).map(([t, v]) => [t, [v[0], 0, .1]])},
        {base: {armR: [-.4, 0, -.25], foreR: [-1.55, 0, 0], foreL: [-.3, 0, 0]}, hips: [[0, .95], [.25, .92], [.5, .95], [.75, .92], [1, .95]]}),
      preparar_trago: clip('preparar_trago', .7, {armR: [[0, [-.9, 0, -.2]], [.35, [-1.5, 0, -.2]], [.7, [-.9, 0, -.2]]], armL: [[0, [-.6, 0, .3]], [.35, [-.4, 0, .3]], [.7, [-.6, 0, .3]]], head: [[0, [.15, 0, 0]], [.7, [.15, 0, 0]]]},
        {base: {foreR: [-1.2, 0, 0], foreL: [-1.3, 0, 0]}, hips: [[0, .95], [.7, .95]]}),
      mezclar: clip('mezclar', .5, {foreR: [[0, [-1.2, .3, 0]], [.25, [-1.2, -.3, 0]], [.5, [-1.2, .3, 0]]], head: [[0, [.1, 0, 0]], [.25, [.3, 0, 0]], [.5, [.1, 0, 0]]], armL: [[0, [-.2, 0, .2]], [.25, [-1.2, 0, .5]], [.5, [-.2, 0, .2]]]},
        {base: {armR: [-.7, 0, -.15], foreL: [-.6, 0, 0]}, hips: [[0, .95], [.25, .93], [.5, .95]]}),
      brindar: clip('brindar', 2, {armR: [[0, [-.35, 0, -.1]], [.6, [-2.4, 0, -.2]], [1.2, [-2.4, 0, -.2]], [2, [-.35, 0, -.1]]]}, {base: seated, hips: [[0, .52], [2, .52]]}),
      bailar: clip('bailar', 1, {armL: [[0, [-2.6, 0, .4]], [.5, [-.4, 0, .6]], [1, [-2.6, 0, .4]]], armR: [[0, [-.4, 0, -.6]], [.5, [-2.6, 0, -.4]], [1, [-.4, 0, -.6]]],
        spine: [[0, [0, 0, .12]], [.5, [0, 0, -.12]], [1, [0, 0, .12]]], legL: [[0, [-.2, 0, 0]], [.5, [.1, 0, 0]], [1, [-.2, 0, 0]]]}, {hips: [[0, .95], [.25, .88], [.5, .95], [.75, .88], [1, .95]]}),
      cafe: clip('cafe', 3, {armR: [[0, [-.3, 0, -.1]], [1, [-.3, 0, -.1]], [1.5, [-.9, 0, -.4]], [2.1, [-.9, 0, -.4]], [2.6, [-.3, 0, -.1]], [3, [-.3, 0, -.1]]],
        foreR: [[0, [-1.3, 0, 0]], [1.5, [-2.2, 0, 0]], [2.1, [-2.2, 0, 0]], [3, [-1.3, 0, 0]]]}, {base: {armL: [0, 0, .12], foreL: [-.15, 0, 0]}, hips: [[0, .95], [3, .95]]}),
      telefono: clip('telefono', 2, {head: [[0, [0, 0, .15]], [1, [.05, .1, .2]], [2, [0, 0, .15]]]}, {base: {armR: [-.6, 0, -.7], foreR: [-2.3, 0, 0], armL: [0, 0, .12], foreL: [-.2, 0, 0]}, hips: [[0, .95], [2, .95]]}),
    };
    return out;
  }
  const BODY = {medio: [1, 1], delgado: [.9, 1.01], robusto: [1.16, .99], alto: [1, 1.08]};
  function makeRig(cfg) {
    const root = new THREE.Group();
    const skin = track(new THREE.MeshPhysicalMaterial({color: cfg.skin || SKIN[0], roughness: .55, sheen: .3, sheenColor: new THREE.Color('#ffd9c4')}));
    const shirt = track(new THREE.MeshStandardMaterial({color: cfg.color || '#333', roughness: .82, normalMap: lite ? null : (pbr('tela').normalMap || null)}));
    const pants = mat(cfg.legs || '#22202b', {roughness: .85}), shoe = mat('#141216', {roughness: .4}), hairM = mat(cfg.hair || '#2b1b12', {roughness: .75});
    const [sx, sy] = BODY[cfg.body] || BODY.medio;
    root.scale.set(1, sy, 1);
    const bone = (name, parent, x, y, z) => { const b = new THREE.Bone(); b.name = name; b.position.set(x, y, z); parent.add(b); return b; };
    const seg = (parent, r, len, m, y0 = 0, sz = 1) => { const k = new THREE.Mesh(track(new THREE.CapsuleGeometry(r, len, 3, 9)), m); k.position.y = y0 - len / 2 - r * .3; k.scale.z = sz; k.castShadow = true; parent.add(k); return k; };
    const hips = bone('hips', root, 0, .95, 0);
    const pelvis = new THREE.Mesh(track(new THREE.CapsuleGeometry(.14 * sx, .12, 4, 12)), pants); pelvis.rotation.z = Math.PI / 2; pelvis.scale.z = .75; pelvis.castShadow = true; hips.add(pelvis);
    const spine = bone('spine', hips, 0, .08, 0), chest = bone('chest', spine, 0, .22, 0);
    const torso = new THREE.Mesh(track(new THREE.CapsuleGeometry(.155 * sx, .32, 3, 12)), shirt); torso.position.y = .05; torso.scale.z = .68; torso.castShadow = true; chest.add(torso);
    const neck = bone('neck', chest, 0, .26, 0); const nk = new THREE.Mesh(track(new THREE.CylinderGeometry(.045, .05, .1, 10)), skin); nk.position.y = .03; neck.add(nk);
    const head = bone('head', neck, 0, .1, 0);
    const skull = new THREE.Mesh(track(new THREE.SphereGeometry(.105, 18, 12)), skin); skull.scale.set(.95, 1.2, 1.05); skull.position.y = .08; skull.castShadow = true; head.add(skull);
    const nose = new THREE.Mesh(track(new THREE.SphereGeometry(.018, 8, 6)), skin); nose.position.set(0, .07, .105); head.add(nose);
    [-.038, .038].forEach(x => { const e = new THREE.Mesh(track(new THREE.SphereGeometry(.012, 8, 6)), mat('#1c140f', {roughness: .2})); e.position.set(x, .1, .093); head.add(e);
      const ear = new THREE.Mesh(track(new THREE.SphereGeometry(.024, 8, 6)), skin); ear.position.set(x > 0 ? .1 : -.1, .08, 0); ear.scale.z = .5; head.add(ear); });
    hair(head, cfg.hairStyle || 'corto', hairM);
    const arm = (side) => { const s = side === 'L' ? 1 : -1; const sh = bone('arm' + side, chest, s * .2 * sx, .2, 0); seg(sh, .048, .22, shirt);
      const fo = bone('fore' + side, sh, 0, -.3, 0); seg(fo, .04, .2, skin); const hand = bone('hand' + side, fo, 0, -.27, 0); const hm = new THREE.Mesh(track(new THREE.SphereGeometry(.04, 10, 8)), skin); hm.scale.set(.8, 1.1, .5); hand.add(hm); return hand; };
    const handL = arm('L'), handR = arm('R');
    const leg = (side) => { const s = side === 'L' ? 1 : -1; const up = bone('leg' + side, hips, s * .09 * sx, -.04, 0); seg(up, .065 * Math.max(1, sx * .95), .34, pants);
      const sh = bone('shin' + side, up, 0, -.43, 0); seg(sh, .052, .34, pants); const f = new THREE.Mesh(track(new THREE.BoxGeometry(.1, .07, .24)), shoe); f.position.set(0, -.46, .05); f.castShadow = true; sh.add(f); };
    leg('L'); leg('R');
    accessory(cfg, {head, chest, hips}, skin);
    toSkinned(root, hips);
    // utilería en la mano derecha (bandeja, taza, teléfono, copa)
    const props = {};
    props.servir = new THREE.Group(); boxMesh(.42, .02, .3, mat('#b9b9be', {metalness: .9, roughness: .25}), 0, -.02, .12, props.servir); cyl(.035, .03, .14, mat('#ffffff', {transparent: true, opacity: .55, roughness: .05}), -.08, .06, .12, props.servir);
    props.cafe = new THREE.Group(); cyl(.04, .035, .09, mat('#f2efe9', {roughness: .3}), 0, 0, .05, props.cafe);
    props.telefono = new THREE.Group(); boxMesh(.035, .14, .015, mat('#0b0b0d', {metalness: .5, roughness: .2}), 0, .02, .04, props.telefono);
    props.brindar = new THREE.Group(); cyl(.035, .025, .16, mat('#ffffff', {transparent: true, opacity: .5, roughness: .05}), 0, .05, .05, props.brindar);
    Object.values(props).forEach(p => { p.visible = false; handR.add(p); });
    return {root, props, height: 1.75 * sy};
  }
  // Esqueleto real: cada pieza queda pegada a su hueso (peso 1) y todo el cuerpo se dibuja con una malla por material.
  function toSkinned(root, hips) {
    root.updateMatrixWorld(true);
    const bones = []; hips.traverse(b => { if (b.isBone) bones.push(b); });
    const inv = new THREE.Matrix4().copy(root.matrixWorld).invert(), buckets = new Map();
    bones.forEach((b, bi) => {
      b.children.filter(c => c.isMesh).forEach(m => {
        m.updateMatrixWorld(true);
        const geo = bake(m, new THREE.Matrix4().multiplyMatrices(inv, m.matrixWorld)); const n = geo.attributes.position.count;
        const idx = new Uint16Array(n * 4), w = new Float32Array(n * 4); for (let i = 0; i < n; i++) { idx[i * 4] = bi; w[i * 4] = 1; }
        geo.setAttribute('skinIndex', new THREE.Uint16BufferAttribute(idx, 4)); geo.setAttribute('skinWeight', new THREE.Float32BufferAttribute(w, 4));
        const k = m.material.uuid; if (!buckets.has(k)) buckets.set(k, {mat: m.material, geos: []}); buckets.get(k).geos.push(geo); b.remove(m);
      });
    });
    const skel = new THREE.Skeleton(bones);
    for (const {mat: mm, geos} of buckets.values()) {
      const sm = new THREE.SkinnedMesh(track(mergeGeometries(geos)), mm); sm.castShadow = !lite; sm.userData.personShadow = true; sm.frustumCulled = false; root.add(sm);
      sm.updateMatrixWorld(true); sm.bind(skel, sm.matrixWorld.clone());
    }
  }
  function hair(head, style, m) {
    if (style === 'calvo') return;
    const cap = new THREE.Mesh(track(new THREE.SphereGeometry(.112, 16, 9, 0, Math.PI * 2, 0, Math.PI * (style === 'rapado' ? .42 : .55))), m);
    cap.scale.set(.98, 1.22, 1.08); cap.position.set(0, .085, -.008); cap.castShadow = true; head.add(cap);
    if (style === 'largo') { const b = new THREE.Mesh(track(new THREE.CapsuleGeometry(.1, .2, 4, 10)), m); b.position.set(0, -.02, -.06); b.scale.set(1, 1, .5); head.add(b); }
    if (style === 'recogido') { const b = new THREE.Mesh(track(new THREE.SphereGeometry(.055, 12, 10)), m); b.position.set(0, .2, -.09); head.add(b); }
    if (style === 'rizado') for (let i = 0; i < 14; i++) { const a = i / 14 * Math.PI * 2; const b = new THREE.Mesh(track(new THREE.SphereGeometry(.04, 8, 6)), m); b.position.set(Math.cos(a) * .1, .15 + Math.sin(i * 1.7) * .03, Math.sin(a) * .1); head.add(b); }
  }
  function accessory(cfg, B2, skin) {
    const A = cfg.acc, am = mat(cfg.accColor || '#222', {roughness: .4, metalness: .2});
    if (A === 'delantal') boxMesh(.3, .55, .02, mat('#f4f1ea', {roughness: .9}), 0, -.2, .11, B2.chest);
    if (A === 'corbata') boxMesh(.045, .24, .015, mat(cfg.accColor || '#b91c1c'), 0, .1, .108, B2.chest);
    if (A === 'chaleco') { const v = new THREE.Mesh(track(new THREE.CapsuleGeometry(.162, .26, 4, 12)), mat(cfg.accColor || '#111', {roughness: .7})); v.position.y = .03; v.scale.z = .72; B2.chest.add(v); }
    if (A === 'gorra') { const c = new THREE.Mesh(track(new THREE.SphereGeometry(.118, 18, 10, 0, Math.PI * 2, 0, Math.PI / 2)), am); c.position.y = .13; B2.head.add(c); boxMesh(.16, .015, .12, am, 0, .14, .12, B2.head); }
    if (A === 'casco') { const c = new THREE.Mesh(track(new THREE.SphereGeometry(.13, 18, 10, 0, Math.PI * 2, 0, Math.PI / 2)), mat(cfg.accColor || '#f59e0b', {roughness: .35})); c.position.y = .12; B2.head.add(c); }
    if (A === 'audifonos') { const r = new THREE.Mesh(track(new THREE.TorusGeometry(.125, .012, 6, 24, Math.PI)), am); r.position.y = .1; B2.head.add(r); [-1, 1].forEach(k => cyl(.035, .035, .03, am, k * .118, .08, 0, B2.head).rotation.z = Math.PI / 2); }
    if (A === 'gafas') [-1, 1].forEach(k => { const l = new THREE.Mesh(track(new THREE.TorusGeometry(.026, .005, 6, 14)), mat('#0d0d0d', {metalness: .7})); l.position.set(k * .038, .1, .1); B2.head.add(l); });
  }
  // Personajes CC0 de Quaternius (Universal Base Characters + Universal Animation Library, mismo esqueleto de 65 huesos).
  // Ropa con los colores de la marca: el traje (zonas oscuras de la textura) se tiñe con cfg.color; la piel no cambia.
  const CLIP_CACHE = {};
  let FIT = null;
  function uniformTint(m, color) {
    const tint = new THREE.Color(color);
    m.onBeforeCompile = sh => {
      sh.uniforms.uTint = {value: tint};
      sh.fragmentShader = 'uniform vec3 uTint;\n' + sh.fragmentShader.replace('#include <map_fragment>', `#include <map_fragment>
        float cxL = dot(diffuseColor.rgb, vec3(.299, .587, .114));
        float cxM = 1.0 - smoothstep(.035, .11, cxL);
        diffuseColor.rgb = mix(diffuseColor.rgb, uTint * (.45 + cxL * 6.0), cxM * .85);`);
    };
    m.customProgramCacheKey = () => 'cx-tint';
  }
  function rigFromModel(cfg) {
    const k = cfg.sex === 'f' && PEOPLE.superhero_female ? 'superhero_female' : PEOPLE.superhero_male ? 'superhero_male' : (PEOPLE.superhero_female ? 'superhero_female' : null);
    if (!k || !PEOPLE.animaciones) return null;
    if (!FIT) { const bb = new THREE.Box3().setFromObject(PEOPLE[k].scene); FIT = 1.75 / Math.max(.1, bb.max.y - bb.min.y); }
    const inner = SkeletonUtils.clone(PEOPLE[k].scene);
    const [sx, sy] = BODY[cfg.body] || BODY.medio;
    inner.scale.set(FIT * sx, FIT * sy, FIT * sx);
    inner.traverse(x => { if (!x.isMesh) return; x.castShadow = !lite; x.userData.personShadow = true; x.frustumCulled = false;
      x.material = track(x.material.clone()); const n = (x.material.name || '').toLowerCase();
      if (/hair/.test(n)) x.material.color.set(new THREE.Color(cfg.hair || '#2b1b12').lerp(new THREE.Color('#ffffff'), .35));
      else if (/superhero|body|suit/.test(n)) uniformTint(x.material, cfg.color || '#333'); });
    const root = new THREE.Group(); root.add(inner);
    if (!CLIP_CACHE.done) {
      const names = PEOPLE.animaciones.animations.map(a => a.name);
      RULES.ANIMS.forEach(st => { const n = RULES.pickClip(names, st) || RULES.pickClip(names, 'quieto'); if (n) CLIP_CACHE[st] = PEOPLE.animaciones.animations.find(a => a.name === n); });
      CLIP_CACHE.done = true;
    }
    const clips = Object.fromEntries(RULES.ANIMS.filter(st => CLIP_CACHE[st]).map(st => [st, CLIP_CACHE[st]]));
    return {root, props: {}, height: 1.75 * sy, clips};
  }
  function makePerson(cfg, kind) {
    let rig = null;
    try { rig = rigFromModel(cfg); } catch (e) { rig = null; }
    const own = !rig;
    if (!rig) rig = makeRig(cfg);
    const p = {kind, cfg, root: rig.root, props: rig.props, height: rig.height, mixer: new THREE.AnimationMixer(rig.root), actions: {}, cur: null, path: [], then: null, info: {}};
    const clips = own ? CLIPS : rig.clips;
    RULES.ANIMS.forEach(n => { if (clips[n]) { const a = p.mixer.clipAction(clips[n]); if (n === 'sentarse') { a.setLoop(THREE.LoopOnce, 1); a.clampWhenFinished = true; } p.actions[n] = a; } });
    p.mixer.addEventListener('finished', e => { if (e.action === p.actions.sentarse) play(p, 'sentado_hablando'); });
    p.root.traverse(x => { if (x.isMesh) { x.userData.person = p; PICK.push(x); } });
    S.add(p.root); people.push(p); play(p, 'quieto');
    return p;
  }
  function play(p, name) {
    if (p.cur === name || !p.actions[name]) return;
    const next = p.actions[name]; next.reset(); next.enabled = true; next.setEffectiveWeight(1); next.play();
    if (p.cur && p.actions[p.cur]) p.actions[p.cur].crossFadeTo(next, RULES.FADE, false);
    p.cur = name; Object.entries(p.props).forEach(([k, g]) => { g.visible = k === name; });
  }
  function dropPerson(p) {
    const i = people.indexOf(p); if (i >= 0) people.splice(i, 1);
    for (let k = PICK.length - 1; k >= 0; k--) if (PICK[k].userData.person === p) PICK.splice(k, 1);
    S.remove(p.root); p.mixer.stopAllAction(); if (p.tag) p.tag.remove();
  }
  function goTo(p, pts, anim, then) { p.path = pts.slice(); p.walkAnim = anim || 'caminar'; p.then = then || null; play(p, p.walkAnim); }
  const aisle = () => (snap.layout.items.barra ? snap.layout.items.barra[1] + 2.4 : 0);
  function route(p, to) { const f = [p.root.position.x, p.root.position.z]; return RULES.aislePath(f, to, aisle()); }
  function seatAt(p, spot, anim) { p.root.position.set(spot[0], 0, spot[1]); p.root.rotation.y = spot[2]; play(p, anim); }

  // ------------------------------------------------------------- copia viva: clientes, personal y representante
  const STAFF = new Map();
  const entrance = () => world(layoutGroups.get('entrada'), SPOT.entrada);
  function guestCfg(seed) { const h = [...String(seed)].reduce((a, c) => (a * 31 + c.charCodeAt(0)) >>> 0, 7);
    const shirts = ['#2f3e46', '#6b2737', '#334155', '#7c5c3b', '#1f4e5f', '#4a3f6b', '#5c5c5c', '#8a6d3b'];
    return {color: shirts[h % shirts.length], legs: ['#1f2937', '#2b2b30', '#3b3a36'][h % 3], skin: SKIN[(h >> 3) % 4], hair: ['#111', '#3b2414', '#6b4423', '#9a8478'][(h >> 5) % 4],
      hairStyle: ['corto', 'largo', 'rizado', 'recogido', 'rapado'][(h >> 7) % 5], body: ['medio', 'delgado', 'robusto', 'alto'][(h >> 9) % 4], acc: 'none', sex: (h >> 11) % 2 ? 'f' : 'm'}; }
  function tableOpen(lbl, n, instant) {
    const t = TABLES.get(lbl); if (!t || t.guests.length) return;
    for (let i = 0; i < n; i++) {
      const p = makePerson(guestCfg(lbl + i), 'cliente'); t.guests.push(p); p.info = {name: 'Cliente', role: lbl};
      const spot = i < 4 ? world(t.g, t.seats[i]) : world(t.g, [(i - 4.5) * .7, 1.5, Math.PI]);
      const end = () => { p.root.rotation.y = spot[2]; if (i < 4) play(p, 'sentarse'); else play(p, 'quieto'); };
      if (instant) { p.root.position.set(spot[0], 0, spot[1]); end(); if (i < 4) play(p, 'sentado_hablando'); }
      else { const e = entrance(); p.root.position.set(e[0] + (i % 2) * .5, 0, e[1] - Math.floor(i / 2) * .5); setTimeout(() => goTo(p, route(p, spot), 'caminar', end), i * 600); }
    }
  }
  function tableClose(lbl) {
    const t = TABLES.get(lbl); if (!t) return;
    const leaving = t.guests.splice(0);
    leaving.forEach((p, i) => { play(p, 'quieto'); setTimeout(() => { const e = entrance(); goTo(p, route(p, [e[0], e[1] + 1.5]), 'caminar', () => dropPerson(p)); }, 500 + i * 400); });
  }
  function staffCfg(person) {
    const u = person.uniform || 'mesero';
    const base = {barman: {color: '#141414', legs: '#141414', acc: 'chaleco', accColor: B.primary}, mesero: {color: B.primary, legs: '#1d1d22', acc: 'corbata', accColor: B.secondary},
      dj: {color: B.secondary, legs: '#141414', acc: 'audifonos', accColor: B.accent}, caja: {color: B.primary, legs: '#222', acc: 'none'}, cocina: {color: '#f4f1ea', legs: '#222', acc: 'delantal'}}[u] || {color: B.primary, legs: '#222'};
    const h = [...person.key].reduce((a, c) => (a * 31 + c.charCodeAt(0)) >>> 0, 3);
    const def = Object.assign({skin: SKIN[h % 4], hair: ['#111', '#3b2414', '#6b4423'][h % 3], hairStyle: ['corto', 'recogido', 'rapado', 'largo'][h % 4], body: 'medio', sex: /a$/i.test(String(person.role || '')) ? 'f' : (h % 2 ? 'f' : 'm')}, base);
    return Object.assign(def, (o.charCfg && o.charCfg('persona', person.key, u)) || {});
  }
  function stationFor(person, idx) {
    const u = person.uniform;
    const pick = (g, list) => world(layoutGroups.get(g), list[idx % list.length]);
    if (person.paused) return pick('personal', SPOT.personal);
    if (u === 'barman') return pick('barra', SPOT.barra);
    if (u === 'dj') return pick('dj', SPOT.dj);
    if (u === 'caja') return pick('caja', SPOT.caja);
    const b = layoutGroups.get('barra'); const v = world(b, [SPOT.pickup[0] + (idx % 3) * .7, SPOT.pickup[1] + .3, 0]); return [v[0], v[1], Math.PI];
  }
  function syncStaff(list, instant) {
    const seen = new Set();
    const counters = {};
    (list || []).forEach(person => {
      seen.add(person.key);
      const slot = (person.paused ? 'pausa' : person.uniform || 'mesero'); const idx = counters[slot] = (counters[slot] ?? -1) + 1;
      let s = STAFF.get(person.key);
      const spot = stationFor(person, idx);
      if (!s) {
        const p = makePerson(staffCfg(person), 'personal'); s = {p, data: person, spot}; STAFF.set(person.key, s);
        const arrive = () => { p.root.rotation.y = spot[2]; play(p, RULES.workAnim(person.uniform, person.paused)); };
        if (instant) { seatAt(p, spot, RULES.workAnim(person.uniform, person.paused)); } else { const e = entrance(); p.root.position.set(e[0], 0, e[1]); goTo(p, route(p, spot), 'caminar', arrive); }
      } else if (s.data.paused !== person.paused || Math.hypot(s.spot[0] - spot[0], s.spot[1] - spot[1]) > .3) {
        s.spot = spot; goTo(s.p, route(s.p, spot), 'caminar', () => { s.p.root.rotation.y = spot[2]; play(s.p, RULES.workAnim(person.uniform, person.paused)); });
      }
      s.data = person; s.p.info = {name: person.label, role: person.role, task: person.task};
    });
    for (const [k, s] of STAFF) if (!seen.has(k)) { STAFF.delete(k); const e = entrance(); goTo(s.p, route(s.p, [e[0], e[1] + 1.5]), 'caminar', () => dropPerson(s.p)); }
  }
  function staffBy(uniform) { return [...STAFF.values()].filter(s => s.data.uniform === uniform && !s.data.paused); }
  function deliver(ev) {
    const w = staffBy('mesero')[0] || staffBy('')[0]; const t = TABLES.get(ev.table); if (!w || !t || w.busy) return;
    w.busy = true; const pick = world(layoutGroups.get('barra'), SPOT.pickup); const dest = world(t.g, [0, 1.25, Math.PI]);
    goTo(w.p, route(w.p, pick), 'caminar', () => { goTo(w.p, route(w.p, dest), 'servir', () => { w.p.root.rotation.y = dest[2]; play(w.p, 'quieto');
      t.guests.slice(0, 2).forEach(g => { play(g, 'brindar'); setTimeout(() => play(g, 'sentado_hablando'), 2100); });
      setTimeout(() => { goTo(w.p, route(w.p, w.spot || stationFor(w.data, 0)), 'caminar', () => { w.busy = false; play(w.p, 'quieto'); }); }, 1600); }); });
  }
  let rep = null;
  function buildRep() {
    const cfg = Object.assign({color: B.primary, legs: '#18181b', skin: SKIN[1], hair: '#111', hairStyle: 'recogido', body: 'medio', acc: 'none', sex: 'f'}, (o.charCfg && o.charCfg('rep', cid)) || {});
    rep = makePerson(cfg, 'rep'); rep.info = {name: (o.repName || 'Representante'), role: 'Representante de ' + floor.name};
    const s = world(layoutGroups.get('entrada'), SPOT.rep); seatAt(rep, s, 'quieto');
  }

  // ------------------------------------------------------------- globos (HTML sobre la escena)
  const bubbles = new Map();
  function bubble(keyName, html, cls = '') {
    let el = bubbles.get(keyName);
    if (!el) { el = document.createElement('div'); el.className = 'rb ' + cls; tagLayer.appendChild(el); bubbles.set(keyName, el); }
    if (el._h !== html) { el.innerHTML = html; el._h = html; }
    el.className = 'rb ' + cls; return el;
  }
  function dropBubble(keyName) { const el = bubbles.get(keyName); if (el) { el.remove(); bubbles.delete(keyName); } }
  const anchors = new Map();   // globo -> función que devuelve la posición en el mundo
  let songUntil = 0, songTitle = '';
  function refreshBubbles() {
    const live = new Set();
    for (const [k, s] of STAFF) { const key2 = 'st:' + k; live.add(key2); bubble(key2, `<b>${esc(s.data.label)}</b><span>${esc(s.data.task || '')}</span>`, s.data.paused ? 'pausa' : 'staff');
      anchors.set(key2, () => s.p.root.position.clone().add(new THREE.Vector3(0, s.p.height + .45, 0))); }
    const pend = {};
    (snap.orders || []).filter(x => x.state !== 'entregado').forEach(x => { pend[x.table] = (pend[x.table] || 0) + x.items; });
    for (const [lbl, t] of TABLES) if (pend[lbl]) { const key2 = 'mesa:' + lbl; live.add(key2); bubble(key2, `🧾 ${pend[lbl]} ${pend[lbl] === 1 ? 'producto' : 'productos'}`, 'pedido');
      anchors.set(key2, () => new THREE.Vector3().setFromMatrixPosition(t.g.matrixWorld).add(new THREE.Vector3(0, 2.05, 0))); }
    if (performance.now() < songUntil) { live.add('dj'); bubble('dj', `♪ ${esc(songTitle)}`, 'nota'); anchors.set('dj', () => new THREE.Vector3().setFromMatrixPosition(layoutGroups.get('dj').matrixWorld).add(new THREE.Vector3(0, 2.6, 0))); }
    if (repSay && performance.now() < repSay.until) { live.add('rep'); bubble('rep', esc(repSay.text), 'rep'); anchors.set('rep', () => rep.root.position.clone().add(new THREE.Vector3(0, rep.height + .5, 0))); }
    for (const k of [...bubbles.keys()]) if (!live.has(k)) { dropBubble(k); anchors.delete(k); }
  }
  const v3 = new THREE.Vector3();
  function placeBubbles() {
    for (const [k, el] of bubbles) { const f = anchors.get(k); if (!f) continue; v3.copy(f()).project(C);
      if (v3.z > 1) { el.style.display = 'none'; continue; } el.style.display = 'flex'; el.style.left = (v3.x * .5 + .5) * innerWidth + 'px'; el.style.top = (-v3.y * .5 + .5) * innerHeight + 'px'; }
  }
  let repSay = null;

  // ------------------------------------------------------------- aplicar una copia viva
  function applyBusiness() {
    const b = snap.business || {};
    const low = b.lights === 'low';
    key.intensity = low ? .25 : 1.6; hemi.intensity = low ? .12 : .35; lamps.forEach(l => { l.intensity = low ? 1 : (lite ? 6 : 9); });
    accentMat.emissiveIntensity = low ? .6 : 2.6;
    const chip = $('[data-biz]'); chip.textContent = b.open ? `Abierto · ${b.hours}` : (b.activity_off_hours ? `Fuera de horario con actividad · ${b.hours}` : (b.sign || 'Cerrado'));
    chip.className = 'rchip ' + (b.open ? 'ok' : 'bad');
    if (doorSign) { const c = doorSign.userData.canvas, x = c.getContext('2d'); x.fillStyle = b.open || b.activity_off_hours ? B.bg : '#2a0b0b'; x.fillRect(0, 0, c.width, c.height);
      x.fillStyle = b.open || b.activity_off_hours ? B.text : '#ff6b6b'; x.font = '800 54px Inter, sans-serif'; x.textAlign = 'center'; x.textBaseline = 'middle';
      x.fillText(b.open || b.activity_off_hours ? 'Entrada' : (b.sign || 'Cerrado'), c.width / 2, c.height / 2); doorSign.needsUpdate = true; }
  }
  function applySnap(next, first) {
    const prev = first ? null : snap;
    const roomChanged = JSON.stringify(next.layout.room) !== JSON.stringify(room);
    snap = next;
    if (next.brand && JSON.stringify(next.brand) !== JSON.stringify(brand)) { const logoChanged = next.brand.logo_url !== brand.logo_url; brand = next.brand; restyle(); if (logoChanged) loadLogo(); }
    if (roomChanged) { room = next.layout.room; buildRoom(); }
    syncTables();
    const events = RULES.diffLive(prev, next);
    events.forEach(e => {
      if (e.type === 'mesa_abierta') tableOpen(e.table, e.guests, e.instant);
      else if (e.type === 'mesa_cerrada') tableClose(e.table);
      else if (e.type === 'pedido_nuevo' && !e.instant) { const b = staffBy('barman')[0]; if (b) play(b.p, 'preparar_trago'); log(`<b>${esc(floor.name)}</b> · pedido nuevo en ${esc(e.table)} (${e.items} ${e.items === 1 ? 'producto' : 'productos'})`); }
      else if (e.type === 'pedido_entregado' && !e.instant) deliver(e);
      else if (e.type === 'cancion') { songTitle = e.title; songUntil = performance.now() + (e.instant ? 15000 : 30000); const d = staffBy('dj')[0]; if (d) play(d.p, 'mezclar'); }
      else if (e.type === 'juego' || e.type === 'juego_fin') screenMode = e.type === 'juego' ? e.kind : 'marca';
    });
    // conciliación: lo que diga la copia viva manda aunque se haya perdido un evento
    for (const t of next.tables) { const T = TABLES.get(t.label); if (!T) continue; if (t.open && !T.guests.length) tableOpen(t.label, RULES.guestsFor(t), true); if (!t.open && T.guests.length) tableClose(t.label); }
    syncStaff((next.staff || {}).people, first);
    applyBusiness(); refreshBubbles(); drawScreen(clock.elapsedTime);
  }
  function restyle() {
    B.accent = brand.accent || B.accent; B.accent2 = brand.accent2 || B.accent2; B.primary = (brand.colors || {}).primary || B.primary; B.secondary = (brand.colors || {}).secondary || B.secondary;
    B.bg = brand.screen_bg || B.bg; B.text = brand.screen_text || B.text;
    accentMat.emissive.set(B.accent); accent2Mat.emissive.set(B.accent2); carpetMat.color.set(new THREE.Color(B.primary).lerp(new THREE.Color('#1a1418'), .35));
    const w = $('[data-warn]'); w.textContent = brand.warning || ''; w.classList.toggle('hidden', !brand.warning);
  }

  // ------------------------------------------------------------- posproceso y modo liviano
  let composer = null, gtao = null, bloom = null;
  function buildComposer() {
    if (composer) { composer.dispose(); composer = null; }
    composer = new EffectComposer(R); composer.addPass(new RenderPass(S, C));
    // liviano: sin oclusión ni brillo (solo render + salida, que en estos equipos es más rápido que dibujar directo al lienzo)
    if (lite) { composer.addPass(new OutputPass()); return; }
    gtao = new GTAOPass(S, C, innerWidth, innerHeight); gtao.output = GTAOPass.OUTPUT.Default;
    gtao.updateGtaoMaterial({radius: .45, distanceFallOff: 1, thickness: 1, samples: 8}); gtao.updatePdMaterial({lumaPhi: 10, depthPhi: 2, normalPhi: 3, radius: 4, rings: 2, samples: 8}); composer.addPass(gtao);
    bloom = new UnrealBloomPass(new THREE.Vector2(innerWidth / 2, innerHeight / 2), .55, .45, .85); composer.addPass(bloom);
    composer.addPass(new OutputPass());
  }
  function setLite(on) { lite = !!on; rendererMode(); S.traverse(x => { if (x.userData.personShadow) x.castShadow = !lite; }); lamps.forEach(l => { l.intensity = lite ? 6 : 9; }); key.shadow.mapSize.set(lite ? 512 : 1024, lite ? 512 : 1024); if (key.shadow.map) { key.shadow.map.dispose(); key.shadow.map = null; } buildComposer(); resize(); }

  // ------------------------------------------------------------- cámara casa de muñecas
  const cam = {az: .42, pol: .92, dist: 20, tx: 0, tz: .5}, goal = Object.assign({}, cam);
  function fit() { goal.dist = RULES.fitDistance(room, C.fov, innerWidth / innerHeight); Object.assign(goal, RULES.clampCamera(goal, room)); }
  const canvas = R.domElement;
  let drag = null; const touches = new Map();
  const onDown = e => { if (arch.on && pickLayout(e)) return; drag = {x: e.clientX, y: e.clientY, m: 0, pan: e.button === 2 || e.shiftKey}; touches.set(e.pointerId, [e.clientX, e.clientY]); };
  const onMove = e => {
    if (arch.drag) { dragLayout(e); return; }
    if (touches.size === 2 && touches.has(e.pointerId)) { const [a, b] = [...touches.values()]; const d0 = Math.hypot(a[0] - b[0], a[1] - b[1]); touches.set(e.pointerId, [e.clientX, e.clientY]);
      const [c, d] = [...touches.values()]; const d1 = Math.hypot(c[0] - d[0], c[1] - d[1]); if (d0 > 0) goal.dist *= d0 / d1; Object.assign(goal, RULES.clampCamera(goal, room)); return; }
    if (!drag) return; const dx = e.clientX - drag.x, dy = e.clientY - drag.y; drag.m += Math.abs(dx) + Math.abs(dy); drag.x = e.clientX; drag.y = e.clientY;
    if (drag.pan) { goal.tx -= dx * .02 * Math.cos(cam.az) + dy * .02 * Math.sin(cam.az); goal.tz += dx * .02 * Math.sin(cam.az) - dy * .02 * Math.cos(cam.az); }
    else { goal.az -= dx * .005; goal.pol -= dy * .004; }
    Object.assign(goal, RULES.clampCamera(goal, room));
  };
  const onUp = e => { touches.delete(e.pointerId); if (arch.drag) { arch.drag = null; return; } if (drag && drag.m < 6 && e.target === canvas) click(e); drag = null; };
  const onWheel = e => { e.preventDefault(); goal.dist *= 1 + Math.sign(e.deltaY) * .08; Object.assign(goal, RULES.clampCamera(goal, room)); };
  const onCtx = e => e.preventDefault();
  canvas.addEventListener('pointerdown', onDown); addEventListener('pointermove', onMove); addEventListener('pointerup', onUp); canvas.addEventListener('wheel', onWheel, {passive: false}); canvas.addEventListener('contextmenu', onCtx);
  const ray = new THREE.Raycaster(), mv = new THREE.Vector2();
  function hit(e, list) { mv.set(e.clientX / innerWidth * 2 - 1, -(e.clientY / innerHeight) * 2 + 1); ray.setFromCamera(mv, C); return ray.intersectObjects(list.filter(x => { let k = x; while (k) { if (!k.visible) return false; k = k.parent; } return true; }), false)[0]; }
  function click(e) {
    const h = hit(e, PICK); if (!h) return;
    const p = h.object.userData.person;
    if (p && p.kind === 'rep') { repSay = {text: RULES.repSummary(snap), until: performance.now() + 9000}; refreshBubbles(); o.onRep && o.onRep(snap); return; }
    if (p) { o.onPerson && o.onPerson(p.info, p.kind); return; }
  }

  // ------------------------------------------------------------- modo arquitecto
  const arch = {on: false, sel: null, drag: null, dirty: false};
  const plane = new THREE.Plane(new THREE.Vector3(0, 1, 0), 0), pt = new THREE.Vector3();
  const selBox = new THREE.BoxHelper(new THREE.Object3D(), new THREE.Color(B.accent)); selBox.visible = false; S.add(selBox);
  function pickLayout(e) { const h = hit(e, PICK.filter(x => x.userData.layout)); if (!h) return false; arch.sel = h.object.userData.layout; selBox.setFromObject(arch.sel); selBox.visible = true;
    ray.ray.intersectPlane(plane, pt); arch.drag = {dx: arch.sel.position.x - pt.x, dz: arch.sel.position.z - pt.z}; return true; }
  function dragLayout(e) { mv.set(e.clientX / innerWidth * 2 - 1, -(e.clientY / innerHeight) * 2 + 1); ray.setFromCamera(mv, C); if (!ray.ray.intersectPlane(plane, pt)) return;
    const g = arch.sel; g.position.x = Math.max(-room.W / 2, Math.min(room.W / 2, pt.x + arch.drag.dx)); g.position.z = Math.max(-room.D / 2, Math.min(room.D / 2, pt.z + arch.drag.dz)); selBox.setFromObject(g); arch.dirty = true; }
  function setArch(on) { arch.on = on; $('[data-archbar]').classList.toggle('hidden', !on); selBox.visible = false; arch.sel = null;
    if (!on && arch.dirty) { arch.dirty = false; syncTables(); } }
  $('[data-arch]').onclick = () => setArch(!arch.on);
  $('[data-archx]').onclick = () => setArch(false);
  $('[data-rot]').onclick = () => { if (!arch.sel) return; arch.sel.rotation.y += Math.PI / 4; selBox.setFromObject(arch.sel); arch.dirty = true; };
  $('[data-save]').onclick = async () => {
    const items = {}; for (const [k, g] of layoutGroups) items[k] = [g.position.x, g.position.z, g.rotation.y];
    try { const r = await getJson(`${API}/pisos/${cid}/distribucion`, {method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(RULES.layoutBody(items))});
      snap.layout = r.layout; arch.dirty = false; OBJ.updateMatrixWorld(true); restation(); log(`<b>${esc(floor.name)}</b> · distribución guardada`); }
    catch (err) { log(`<b>${esc(floor.name)}</b> · no se guardó la distribución: ${esc(err.message)}`, 'error'); }
  };
  $('[data-auto]').onclick = async () => {
    try { const r = await getJson(`${API}/pisos/${cid}/distribucion`, {method: 'DELETE'}); snap.layout = r.layout; arch.dirty = false; setArch(false); syncTables(); restation(); log(`<b>${esc(floor.name)}</b> · acomodado automático`); }
    catch (err) { log(`<b>${esc(floor.name)}</b> · ${esc(err.message)}`, 'error'); }
  };
  function restation() {
    for (const t of TABLES.values()) t.guests.forEach((p, i) => { const s = i < 4 ? world(t.g, t.seats[i]) : world(t.g, [(i - 4.5) * .7, 1.5, Math.PI]); p.root.position.set(s[0], 0, s[1]); p.root.rotation.y = s[2]; });
    const list = [...STAFF.values()].map(s => s.data); STAFF.forEach(s => { s.spot = [Infinity, Infinity, 0]; }); syncStaff(list, false);
    if (rep) seatAt(rep, world(layoutGroups.get('entrada'), SPOT.rep), 'quieto');
  }

  // ------------------------------------------------------------- consulta (cada 7 s, pausa si la pestaña no se ve)
  let timer = null, closed = false;
  async function poll() {
    if (closed || document.hidden) return;
    try { const r = await getJson(`${API}/pisos/${cid}/vivo?rev=${encodeURIComponent(snap.rev || '')}`); if (!r.same) applySnap(r, false); }
    catch (e) { const chip = $('[data-biz]'); chip.textContent = 'Sin conexión'; chip.className = 'rchip bad'; }
  }
  function schedule() { clearTimeout(timer); if (!closed) timer = setTimeout(async () => { await poll(); schedule(); }, RULES.LIVE_MS); }
  const onVis = () => { if (document.hidden) clearTimeout(timer); else { poll(); schedule(); } };
  document.addEventListener('visibilitychange', onVis);

  // ------------------------------------------------------------- arranque
  const clock = new THREE.Clock();
  buildLayout(); OBJ.updateMatrixWorld(true); loadLogo(); buildRep();
  applySnap(snap, true); buildComposer(); fit(); Object.assign(cam, goal);
  $('[data-load]').remove(); schedule();
  $('[data-out]').onclick = () => o.onClose && o.onClose();
  let frames = 0, fpsT = 0, fpsShown = 0, fpsSamples = 0, lastScreen = 0, frameNo = 0;
  function resize() { C.aspect = innerWidth / innerHeight; C.updateProjectionMatrix(); R.setSize(innerWidth, innerHeight, false); if (composer) composer.setSize(innerWidth, innerHeight); }
  addEventListener('resize', resize); resize();

  function tick() {
    const dt = Math.min(clock.getDelta(), .05), t = clock.elapsedTime, k = 1 - Math.pow(.003, dt);
    cam.az += (goal.az - cam.az) * k; cam.pol += (goal.pol - cam.pol) * k; cam.dist += (goal.dist - cam.dist) * k; cam.tx += (goal.tx - cam.tx) * k; cam.tz += (goal.tz - cam.tz) * k;
    C.position.set(cam.tx + cam.dist * Math.sin(cam.pol) * Math.sin(cam.az), cam.dist * Math.cos(cam.pol), cam.tz + cam.dist * Math.sin(cam.pol) * Math.cos(cam.az)); C.lookAt(cam.tx, .8, cam.tz);
    const hidden = new Set(RULES.hiddenWalls(cam.az)); Object.entries(WALLS).forEach(([n, list]) => list.forEach(m => { m.visible = !hidden.has(n); }));
    for (const p of people) {
      p.mixer.update(dt);
      if (p.path.length) { const [x, z] = p.path[0]; const r = p.root.position; const dx = x - r.x, dz = z - r.z, d = Math.hypot(dx, dz);
        if (d < .05) { r.x = x; r.z = z; p.path.shift(); if (!p.path.length) { const f = p.then; p.then = null; if (f) f(); else play(p, 'quieto'); } }
        else { const sp = Math.min(d, dt * SPEED); r.x += dx / d * sp; r.z += dz / d * sp; const want = Math.atan2(dx, dz); let dr = want - p.root.rotation.y; dr = Math.atan2(Math.sin(dr), Math.cos(dr)); p.root.rotation.y += dr * Math.min(1, dt * 8); } }
    }
    anims.forEach(f => f(t));
    if (snap.game && t - lastScreen > .12) { lastScreen = t; drawScreen(t); }
    frameNo++; if (frameNo % (lite ? 4 : 2) === 0) R.shadowMap.needsUpdate = true;
    if (composer) composer.render(); else R.render(S, C);
    placeBubbles();
    frames++; fpsT += dt; if (fpsT >= 1) { fpsShown = Math.round(frames / fpsT); frames = 0; fpsT = 0; fpsSamples++; $('[data-fps]').textContent = `${fpsShown} FPS${lite ? ' · liviano' : ''}`;
      if (fpsSamples === 6 && fpsShown < 30 && !lite && o.liteChosen() == null) { o.onAutoLite && o.onAutoLite(); } }
  }

  function close() {
    closed = true; clearTimeout(timer); document.removeEventListener('visibilitychange', onVis);
    canvas.removeEventListener('pointerdown', onDown); removeEventListener('pointermove', onMove); removeEventListener('pointerup', onUp); canvas.removeEventListener('wheel', onWheel); canvas.removeEventListener('contextmenu', onCtx); removeEventListener('resize', resize);
    people.slice().forEach(dropPerson); if (composer) composer.dispose();
    S.traverse(x => { if (x.geometry) x.geometry.dispose(); });
    disposables.forEach(d => { try { d.dispose(); } catch (e) { /* ya liberado */ } });
    ui.remove(); tagLayer.remove();
    R.useLegacyLights = saved.legacy; R.toneMapping = saved.tm; R.toneMappingExposure = saved.exp; R.shadowMap.type = saved.shadow; R.shadowMap.enabled = saved.se; R.setPixelRatio(saved.pr); R.shadowMap.autoUpdate = true; R.shadowMap.needsUpdate = true;
  }
  return {tick, close, setLite, resize, get fps() { return fpsShown; }, get snap() { return snap; }, get scene() { return S; }};
}
