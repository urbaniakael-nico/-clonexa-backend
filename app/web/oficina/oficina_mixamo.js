// Oficina 3D · motor común de los pisos aprobados (Clonexa, Velvet, Asadero El Socio, VOLTAGE). Interno de Clonexa,
// solo Admin V2. Reutiliza lo del bar aprobado: retargeting por prefijo de huesos, escala de cadera, recorte de
// las animaciones sentadas, crossfade, y los personajes/animaciones de Mixamo del bucket PRIVADO (solo con sesión,
// por /admin-v2plus/oficina/bar/...; NUNCA en el repo). Cada piso (oficina_<plantilla>.js) solo arma su escena y
// aplica la copia viva; este módulo pone renderer, cámara, etiquetas, personas, consulta y modo liviano.
import * as THREE from 'three';
import {GLTFLoader} from 'three/addons/loaders/GLTFLoader.js';
import {MeshoptDecoder} from 'three/addons/libs/meshopt_decoder.module.js';
import {RoomEnvironment} from 'three/addons/environments/RoomEnvironment.js';
import {RoundedBoxGeometry} from 'three/addons/geometries/RoundedBoxGeometry.js';
import * as SkeletonUtils from 'three/addons/utils/SkeletonUtils.js';
import {EffectComposer} from 'three/addons/postprocessing/EffectComposer.js';
import {RenderPass} from 'three/addons/postprocessing/RenderPass.js';
import {UnrealBloomPass} from 'three/addons/postprocessing/UnrealBloomPass.js';
import {OutputPass} from 'three/addons/postprocessing/OutputPass.js';
import * as BAR from '/admin-v2plus/oficina/bar_reglas.js';
import * as P from '/admin-v2plus/oficina/pisos_reglas.js';
import {attachGestures} from '/admin-v2plus/oficina/gestos.js';

export {THREE, RoundedBoxGeometry, P};
const RES = '/admin-v2plus/oficina/recursos/';
const MIX = '/admin-v2plus/oficina/bar/';
export const API = '/admin-v2/api/oficina';
const WALK = 1.25;

export function esc(s) { return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'); }

// ------------------------------------------------------------------ túnica y barba (common.js de la referencia aprobada)
const gc = (a, i, k) => (k === 0 ? a.getX(i) : k === 1 ? a.getY(i) : k === 2 ? a.getZ(i) : a.getW(i));
const BAD = /Head|Neck|Hand|Eye|Thumb|Index|Middle|Ring|Pinky/;
// Túnica negra: capa que sigue el esqueleto (sin cabeza ni manos) + falda (solo de pie) + capucha caída;
// lines = líneas moradas del CEO. Devuelve las faldas para ocultarlas al sentarse (no atraviesan la silla).
export function tunic(root, {color = 0x060608, lines = null, hood = true} = {}, track = x => x) {
  root.updateMatrixWorld(true);
  const parts = []; root.traverse(o => { if (o.isSkinnedMesh && !/hair|eye|lash|teeth|tongue|brow/i.test(o.name + ' ' + (o.material && o.material.name))) parts.push(o); });
  const mat = track(new THREE.MeshStandardMaterial({color, roughness: .55, metalness: .15, envMapIntensity: .6, side: THREE.DoubleSide}));
  let hipsBone = null, neckBone = null; const skirts = [];
  parts.forEach(sm => {
    const g = sm.geometry, pos = g.attributes.position, nor = g.attributes.normal, si = g.attributes.skinIndex, sw = g.attributes.skinWeight, bones = sm.skeleton.bones;
    if (!nor || !si || !sw) return;
    bones.forEach(b => { if (/Hips$/.test(b.name)) hipsBone = b; if (/Neck$/.test(b.name)) neckBone = b; });
    g.computeBoundingBox(); const hg = g.boundingBox.max.y - g.boundingBox.min.y || 1; const off = hg * .010;
    const bad = new Uint8Array(pos.count);
    for (let i = 0; i < pos.count; i++) { let mx = -1, bi = 0; for (let k = 0; k < 4; k++) { const w = gc(sw, i, k); if (w > mx) { mx = w; bi = gc(si, i, k); } } bad[i] = BAD.test(bones[bi] ? bones[bi].name : '') ? 1 : 0; }
    const ng = track(g.clone()); const p2 = ng.attributes.position;
    for (let i = 0; i < p2.count; i++) p2.setXYZ(i, p2.getX(i) + nor.getX(i) * off, p2.getY(i) + nor.getY(i) * off, p2.getZ(i) + nor.getZ(i) * off);
    const idx = g.index ? g.index.array : [...Array(pos.count).keys()]; const keep = [];
    for (let t = 0; t < idx.length; t += 3) { const a = idx[t], b = idx[t + 1], c = idx[t + 2]; if (!bad[a] && !bad[b] && !bad[c]) keep.push(a, b, c); }
    ng.setIndex(keep);
    let m = mat;
    if (lines) { m = track(mat.clone()); const bb = g.boundingBox; const cx = (bb.min.x + bb.max.x) / 2, W = bb.max.x - bb.min.x;
      m.onBeforeCompile = sh => { sh.uniforms.uLine = {value: new THREE.Color(lines)}; sh.uniforms.uCx = {value: cx}; sh.uniforms.uW = {value: W}; sh.uniforms.uZ = {value: (bb.min.z + bb.max.z) / 2};
        sh.vertexShader = sh.vertexShader.replace('#include <common>', '#include <common>\nvarying vec3 vOP;').replace('#include <begin_vertex>', '#include <begin_vertex>\nvOP=position;');
        sh.fragmentShader = sh.fragmentShader.replace('#include <common>', '#include <common>\nvarying vec3 vOP;uniform vec3 uLine;uniform float uCx;uniform float uW;uniform float uZ;')
          .replace('#include <emissivemap_fragment>', '#include <emissivemap_fragment>\nfloat dx=abs(abs(vOP.x-uCx)-uW*.06);float ln=(1.0-smoothstep(uW*.006,uW*.012,dx))*step(uZ,vOP.z);totalEmissiveRadiance+=uLine*ln*2.2;diffuseColor.rgb=mix(diffuseColor.rgb,uLine,ln*.6);'); };
      m.customProgramCacheKey = () => 'cx-tunic-lines'; }
    const shell = new THREE.SkinnedMesh(ng, m); shell.bind(sm.skeleton, sm.bindMatrix); shell.castShadow = true; shell.frustumCulled = false; shell.userData.personShadow = true;
    sm.parent.add(shell); shell.position.copy(sm.position); shell.quaternion.copy(sm.quaternion); shell.scale.copy(sm.scale);
  });
  const ws = new THREE.Vector3(); if (hipsBone) hipsBone.getWorldScale(ws); const u = 1 / (ws.y || 1);
  if (hipsBone) { const pts = []; for (let i = 0; i <= 10; i++) { const t = i / 10; pts.push(new THREE.Vector2(.18 + t * .2, -t * .92)); }
    const sk = new THREE.Mesh(track(new THREE.LatheGeometry(pts, 28)), mat); sk.scale.setScalar(u); hipsBone.add(sk); sk.castShadow = true; skirts.push(sk);
    if (lines) { const hem = new THREE.Mesh(track(new THREE.TorusGeometry(.38, .006, 6, 40)), track(new THREE.MeshStandardMaterial({color: 0, emissive: lines, emissiveIntensity: 2.5}))); hem.rotation.x = Math.PI / 2; hem.position.y = -.9; sk.add(hem); } }
  if (hood && neckBone) { const hd = new THREE.Mesh(track(new THREE.SphereGeometry(.15, 20, 12, 0, Math.PI * 2, 0, Math.PI * .55)), mat); hd.scale.set(u * 1.15, u * .7, u * 1.0); hd.position.set(0, .02 * u, -.1 * u); hd.rotation.x = -1.1; neckBone.add(hd); }
  return skirts;
}
// Barba larga + pelo largo (CEO), pegados al hueso de la cabeza. beard=false: solo el pelo.
export function beardHair(root, {color = 0x2b1a10, beard = true} = {}, track = x => x) {
  let head = null; root.traverse(o => { if (o.isBone && /Head$/.test(o.name)) head = o; }); if (!head) return null;
  root.updateMatrixWorld(true); const ws = new THREE.Vector3(); head.getWorldScale(ws); const u = 1 / (ws.y || 1);
  const m = track(new THREE.MeshStandardMaterial({color, roughness: .95, metalness: 0})); const parts = [];
  const add = (geo, x, y, z, sx = 1, sy = 1, sz = 1, rx = 0) => { const k = new THREE.Mesh(track(geo), m); k.position.set(x * u, y * u, z * u); k.scale.set(sx * u, sy * u, sz * u); k.rotation.x = rx; k.castShadow = true; head.add(k); parts.push(k); return k; };
  if (beard) { add(new THREE.SphereGeometry(.09, 22, 14, 0, Math.PI * 2, Math.PI * .6, Math.PI * .4), 0, .078, .022, 1.04, 1.2, 1.12);
    add(new THREE.CapsuleGeometry(.05, .11, 6, 14), 0, -.045, .075, 1.15, 1, .62, -.18); }
  add(new THREE.SphereGeometry(.102, 22, 14, 0, Math.PI * 2, 0, Math.PI * .58), 0, .11, -.005, 1.04, 1.1, 1.1);
  add(new THREE.CapsuleGeometry(.075, .2, 6, 14), 0, -.0, -.06, 1.25, 1, .55, -.12);
  return {material: m, parts};
}

// ------------------------------------------------------------------ piso
export async function openFloor(o, spec) {
  const {R, floor, getJson, log} = o;
  const ui = document.createElement('div'); ui.id = 'realUi'; document.body.appendChild(ui);
  const tagLayer = document.createElement('div'); tagLayer.id = 'barTags'; tagLayer.className = 'pisos ' + (spec.cls || ''); document.body.appendChild(tagLayer);
  ui.innerHTML = `<div class="rbar glass"><button type="button" data-out>← Edificio</button><b>${esc(spec.title)}</b><span class="rchip" data-biz></span>
    <span class="rchip warn hidden" data-warn></span><span class="sp"></span><span class="rchip" data-mb></span><span class="rfps" data-fps>…</span></div>
    <div class="rload" data-load>Cargando el piso…</div>`;
  const $ = s => ui.querySelector(s);
  const warn = t => { const w = $('[data-warn]'); w.textContent = t || ''; w.classList.toggle('hidden', !t); };
  const chip = (t, ok) => { const c = $('[data-biz]'); c.textContent = t; c.className = 'rchip ' + (ok ? 'ok' : 'bad'); };

  const saved = {legacy: R.useLegacyLights, tm: R.toneMapping, exp: R.toneMappingExposure, shadow: R.shadowMap.type, se: R.shadowMap.enabled, pr: R.getPixelRatio()};
  let lite = !!o.lite;
  function rendererMode() {
    R.useLegacyLights = false; R.toneMapping = THREE.ACESFilmicToneMapping; R.toneMappingExposure = spec.exposure || .85;
    R.shadowMap.enabled = true; R.shadowMap.autoUpdate = false; R.shadowMap.type = lite ? THREE.PCFShadowMap : THREE.PCFSoftShadowMap; R.shadowMap.needsUpdate = true; R.setPixelRatio(1);
  }
  rendererMode();
  const disposables = []; const track = x => { disposables.push(x); return x; };
  const S = new THREE.Scene(); S.background = new THREE.Color(spec.bg || 0x07050a);
  const pmrem = new THREE.PMREMGenerator(R); S.environment = track(pmrem.fromScene(new RoomEnvironment(R), .04).texture); pmrem.dispose();
  const {W: RW, D: RD} = spec.room;
  const C = new THREE.PerspectiveCamera(spec.camera.fov, innerWidth / innerHeight, .1, 300);

  // recursos CC0 del repo (texturas) y Mixamo del bucket privado
  let man = {files: {}}; try { man = await getJson(RES + 'manifest.json'); } catch (e) { /* sin texturas: colores planos */ }
  const used = new Set(); const TL = new THREE.TextureLoader();
  const tex = (f, rep = [1, 1], srgb = true) => { const p = `texturas/${f}`; if (!(man.files || {})[p]) return null; used.add(p);
    const t = track(TL.load(RES + p + '?v=' + man.files[p].sha)); t.wrapS = t.wrapT = THREE.RepeatWrapping; t.repeat.set(...rep); if (srgb) t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = lite ? 2 : 8; return t; };
  const L = new GLTFLoader(); L.setMeshoptDecoder(MeshoptDecoder);

  // utilidades de las escenas aprobadas
  const mesh = (g, m, x = 0, y = 0, z = 0, p = S) => { const k = new THREE.Mesh(track(g), m); k.position.set(x, y, z); k.castShadow = k.receiveShadow = true; p.add(k); return k; };
  const flat = (g, m, x, y, z, p = S) => { const k = mesh(g, m, x, y, z, p); k.castShadow = false; return k; };
  const M = (c, x = {}) => track(new THREE.MeshStandardMaterial(Object.assign({color: c, roughness: .6}, x)));
  const glow = (c, i = 3) => track(new THREE.MeshStandardMaterial({color: 0, emissive: c, emissiveIntensity: i}));
  const POINTS = [];
  const point = (c, i, d, x, y, z) => { const l = new THREE.PointLight(c, i, d, 2); l.position.set(x, y, z); S.add(l); POINTS.push([l, i]); l.visible = !lite; return l; };
  // pantalla con textura de canvas que se redibuja solo cuando cambia su modelo (cambios incrementales)
  function canvasScreen(w, h, cw = 1024, ch = 576) {
    const cv = document.createElement('canvas'); cv.width = cw; cv.height = ch; const t = track(new THREE.CanvasTexture(cv)); t.colorSpace = THREE.SRGBColorSpace;
    let key = ''; return {canvas: cv, texture: t, draw(model, fn) { const k = JSON.stringify(model); if (k === key) return; key = k; const x = cv.getContext('2d'); x.clearRect(0, 0, cw, ch); x.textBaseline = 'alphabetic'; x.textAlign = 'left'; fn(x, cw, ch, model); t.needsUpdate = true; }};
  }
  function screen(x, y, z, w, h, cs, ry = 0) { const g = new THREE.Group(); g.position.set(x, y, z); g.rotation.y = ry; S.add(g);
    mesh(new THREE.BoxGeometry(w + .12, h + .12, .08), M(0x050505, {metalness: .6, roughness: .25}), 0, 0, 0, g);
    flat(new THREE.PlaneGeometry(w, h), track(new THREE.MeshBasicMaterial({map: cs.texture, toneMapped: false})), 0, 0, .045, g); return g; }
  const clipText = (s, n) => (String(s).length > n ? String(s).slice(0, n - 1) + '…' : String(s));

  // etiquetas HTML (como las escenas aprobadas)
  const tags = [];
  function tag(obj, html, cls = '', dy = 1.95, fixed = false) { const d = document.createElement('div'); d.className = 'tg ' + cls; d.innerHTML = html; tagLayer.appendChild(d); const t = {obj, d, dy, fixed, html}; tags.push(t); return t; }
  function setTag(t, html, cls) { if (!t) return; if (t.html !== html) { t.d.innerHTML = html; t.html = html; } if (cls != null && t.d.className !== 'tg ' + cls) t.d.className = 'tg ' + cls; }
  function dropTag(t) { if (!t) return; t.d.remove(); const i = tags.indexOf(t); if (i >= 0) tags.splice(i, 1); }
  const at = (x, y, z) => ({position: new THREE.Vector3(x, y, z)});
  const zoneTag = (text, x, z) => tag(at(x, .05, z), esc(text), 'zn', 0, true);
  const v3 = new THREE.Vector3();
  // etiquetas sin taparse: la que choca con otra ya puesta sube hasta quedar libre (P.declutter, regla pura)
  const placed = [];
  function placeTags() {
    placed.length = 0;
    const order = tags.map(t => { if (t.fixed) v3.copy(t.obj.position); else t.obj.getWorldPosition(v3); v3.y += t.dy; v3.project(C); return {t, x: v3.x, y: v3.y, z: v3.z}; })
      .sort((a, b) => (a.t.fixed === b.t.fixed ? b.y - a.y : a.t.fixed ? -1 : 1));   // zonas primero; luego de abajo hacia arriba en pantalla
    for (const {t, x: px, y: py, z} of order) {
      if (z > 1 || t.hidden) { t.d.style.display = 'none'; continue; }
      t.d.style.display = 'flex'; if (!t.w || t.wh !== t.html) { t.w = t.d.offsetWidth; t.h = t.d.offsetHeight; t.wh = t.html; }
      const half = t.w / 2 + 6, x = Math.max(half, Math.min(innerWidth - half, (px * .5 + .5) * innerWidth));
      const y = P.declutter(placed, x, (-py * .5 + .5) * innerHeight, t.w, t.h || 22, !t.fixed);
      t.d.style.left = x.toFixed(1) + 'px'; t.d.style.top = y.toFixed(1) + 'px';
    }
  }
  const dot = cls => `<i class="${esc(cls || 'work')}"></i>`;
  const tagHtml = (cls, text, small) => `${dot(cls)}${esc(text)}${small ? ` <small>· ${esc(small)}</small>` : ''}`;

  // ------------------------------------------------------------------ personas (Mixamo)
  const CH = {}, ANIMS = {}, INFO = {}, CLIP = {}; let mixMan = null, peopleOk = false;
  const avail = new Set();
  async function loadPeople() {
    try { mixMan = await getJson(MIX + 'manifest.json'); } catch (e) { warn('Personajes no disponibles (bucket privado): el piso se ve sin personas'); return; }
    const files = mixMan.files || {};
    const chars = (spec.models || P.CHARACTERS).filter(n => files[`personajes/${n}.glb`]);
    const clips = (spec.clips || P.CLIPS).filter(n => files[`animaciones/${n}.glb`]);
    if (!chars.length || !clips.includes('Idle')) { warn('Personajes no disponibles (bucket privado): el piso se ve sin personas'); return; }
    if (!clips.includes('Typing') && (spec.clips || P.CLIPS).includes('Typing')) warn('Falta la animación Typing en el bucket: quien escribe aparece sentado');
    const get = f => L.loadAsync(MIX + f + '?v=' + files[f].sha.slice(0, 12));
    const [chs, ans] = await Promise.all([Promise.all(chars.map(n => get(`personajes/${n}.glb`))), Promise.all(clips.map(n => get(`animaciones/${n}.glb`)))]);
    chars.forEach((n, i) => { CH[n] = chs[i]; });
    clips.forEach((n, i) => { const g = ans[i]; let hy = 1; g.scene.traverse(x => { if (/Hips$/.test(x.name)) hy = x.position.y; });
      const clip = g.animations[0]; const t0 = P.SIT_CLIPS.includes(n) ? seatedCut(clip) : 0; ANIMS[n] = {clip, hy, trimmed: t0 > 0}; avail.add(n); });
    peopleOk = true;
  }
  function seatedCut(clip) {
    const h = clip.tracks.find(t => /Hips\.position$/.test(t.name)); if (!h) return 0;
    const t0 = BAR.seatedStart(h.times, h.values); if (t0 < .05) return 0;
    clip.tracks.forEach(t => { const n = t.getValueSize(); let i = 0; while (i < t.times.length - 1 && t.times[i] < t0) i++; t.times = t.times.slice(i).map(x => x - t.times[i]); t.values = t.values.slice(i * n); });
    clip.resetDuration(); return t0;
  }
  const modelOk = n => (CH[n] ? n : (P.WOMEN.includes(n) ? P.WOMEN : P.MEN).find(m => CH[m]) || Object.keys(CH)[0]);
  function charInfo(n, tall) {
    const id = n + (tall ? '+' : ''); if (INFO[id]) return INFO[id];
    const m = SkeletonUtils.clone(CH[n].scene); let chy = 1, hips = 'mixamorigHips', found = false;
    m.traverse(x => { if (!found && /Hips$/.test(x.name)) { chy = x.position.y; hips = x.name; found = true; } });
    m.updateMatrixWorld(true); const bb = new THREE.Box3().setFromObject(m, true); const s = P.heightFor(n, tall) / (bb.max.y - bb.min.y);
    m.scale.multiplyScalar(s); m.updateMatrixWorld(true); const bb2 = new THREE.Box3().setFromObject(m, true);
    return (INFO[id] = {chy, hips, scale: s, lift: -bb2.min.y});
  }
  function clipFor(n, name, tall) {
    const id = n + '|' + name + (tall ? '+' : ''); if (CLIP[id]) return CLIP[id];
    const A = ANIMS[name], I = charInfo(n, tall), clip = A.clip.clone(); clip.name = name;
    const plan = BAR.retargetPlan(clip.tracks.map(t => t.name), I.hips, I.chy, A.hy, name, A.trimmed);
    // como las escenas aprobadas: todo en el sitio (la persona se mueve con su grupo); sentadas recortadas: ancladas al asiento
    clip.tracks.forEach((t, i) => { t.name = plan.tracks[i].to; if (plan.tracks[i].hips) t.values = new Float32Array(BAR.scaleHips(t.values, plan.k, !A.trimmed, A.trimmed)); });
    return (CLIP[id] = clip);
  }
  const hitM = track(new THREE.MeshBasicMaterial({visible: false}));
  const PICK = [], people = [];
  const ringGeo = track(new THREE.RingGeometry(.5, .56, 40));
  const RING = {red: track(new THREE.MeshBasicMaterial({color: 0xef4444, transparent: true, opacity: .75, side: THREE.DoubleSide})),
    blue: track(new THREE.MeshBasicMaterial({color: 0x60a5fa, transparent: true, opacity: .7, side: THREE.DoubleSide}))};
  function makePerson(cfg) {
    const n = modelOk(cfg.model); const I = charInfo(n, cfg.tall); const m = SkeletonUtils.clone(CH[n].scene);
    m.scale.multiplyScalar(I.scale); m.position.y = I.lift;
    m.traverse(x => { if (!x.isMesh) return; x.castShadow = !lite; x.receiveShadow = true; x.frustumCulled = false; x.userData.personShadow = true;
      const nm = (x.name + ' ' + ((x.material && x.material.name) || '')).toLowerCase();
      if (cfg.hair && /hair/.test(nm)) { x.material = track(x.material.clone()); x.material.color = new THREE.Color(cfg.hair); }
      else if (cfg.tint && !cfg.tunic && x.material && !/skin|body|eye|hair|teeth|lash|brow/.test(nm)) { x.material = track(x.material.clone()); x.material.color = x.material.color.clone().multiply(new THREE.Color(cfg.tint)); } });
    const g = new THREE.Group(); g.add(m); S.add(g);
    const p = {n, g, m, cfg, mixer: new THREE.AnimationMixer(m), actions: {}, cur: null, path: [], then: null, kind: cfg.kind || 'personal', info: cfg.info || {}, tag: null, skirts: [], ring: null};
    if (cfg.tunic) p.skirts = tunic(m, {lines: cfg.lines || null}, track);
    if (cfg.beard || cfg.longHair) beardHair(m, {color: cfg.beardColor ? new THREE.Color(cfg.beardColor) : 0x2b1a10, beard: !!cfg.beard}, track);
    const hit = new THREE.Mesh(track(new THREE.CylinderGeometry(.32, .32, 1.7, 8)), hitM); hit.position.y = .85; g.add(hit); hit.userData.person = p; PICK.push(hit);
    people.push(p); return p;
  }
  function setRing(p, kind) {
    if (p.ring && (!kind || p.ring.userData.kind !== kind)) { p.g.remove(p.ring); p.ring = null; }
    if (kind && !p.ring) { const r = new THREE.Mesh(ringGeo, RING[kind]); r.rotation.x = -Math.PI / 2; r.position.y = .012; r.userData.kind = kind; p.g.add(r); p.ring = r; }
  }
  function play(p, name, t) {
    if (!p || !peopleOk) return; name = P.clipOr(name, avail); if (p.cur === name) return;
    let a = p.actions[name]; if (!a) a = p.actions[name] = p.mixer.clipAction(clipFor(p.n, name, p.cfg.tall));
    a.reset(); a.enabled = true; a.setEffectiveWeight(1); a.play(); if (t != null) a.time = t * a.getClip().duration;
    if (p.cur && p.actions[p.cur]) p.actions[p.cur].crossFadeTo(a, P.FADE, false);
    p.cur = name; const seated = P.SEATED.test(name); p.skirts.forEach(s => { s.visible = !seated; });
  }
  function dropPerson(p) {
    const i = people.indexOf(p); if (i >= 0) people.splice(i, 1);
    for (let k = PICK.length - 1; k >= 0; k--) if (PICK[k].userData.person === p) PICK.splice(k, 1);
    S.remove(p.g); p.mixer.stopAllAction(); dropTag(p.tag);
  }
  function place(p, [x, z, r], y = 0) { p.g.position.set(x, y, z); if (r != null) p.g.rotation.y = r; }
  function goTo(p, to, then) { p.path = spec.route ? spec.route([p.g.position.x, p.g.position.z], to) : [to]; p.g.position.y = 0; p.then = then || null; play(p, 'Walking'); }
  function sitAt(p, spot, clip, y = 0) { place(p, spot, y); play(p, clip, (people.indexOf(p) * .37) % 1); }   // fase estable por persona (no todos iguales)
  function arrive(p, door, to, then, delay = 0) { place(p, [door[0], door[1], Math.PI]); p.g.visible = false;
    setTimeout(() => { if (!people.includes(p)) return; p.g.visible = true; goTo(p, to, then); }, delay); }
  function leave(p, door, delay = 0) { p.leaving = true; dropTag(p.tag); p.tag = null; setTimeout(() => { if (!people.includes(p)) return; goTo(p, door, () => dropPerson(p)); }, delay); }

  // ------------------------------------------------------------------ cámara (inicial como la escena aprobada) y clics
  const T0 = new THREE.Vector3(...spec.camera.look), P0 = new THREE.Vector3(...spec.camera.pos).sub(T0);
  const cam = {dist: P0.length(), pol: Math.acos(P0.y / P0.length()), az: Math.atan2(P0.x, P0.z), tx: T0.x, tz: T0.z}; const goal = Object.assign({}, cam); const home = Object.assign({}, cam);
  // límites por piso (pisos_reglas.camLimits): la cámara nunca queda detrás de una pared ni bajo el piso
  let LIM = P.camLimits(spec.room, spec.camera); const clampCam = g => P.clampCam(g, LIM);
  const canvas = R.domElement; canvas.style.touchAction = 'none';
  // gestos (oficina_gestos.js): arrastrar gira, pellizco/Ctrl+rueda acerca, rueda horizontal gira; el navegador nunca va "atrás"
  const gestures = attachGestures(canvas, {
    rotate: (dx, dy) => { goal.az -= dx * .005; goal.pol -= dy * .004; clampCam(goal); },
    pan: (dx, dy) => { goal.tx -= dx * .015 * Math.cos(cam.az) + dy * .015 * Math.sin(cam.az); goal.tz += dx * .015 * Math.sin(cam.az) - dy * .015 * Math.cos(cam.az); clampCam(goal); },
    zoom: f => { goal.dist *= f; clampCam(goal); },
    tap: e => { if (e.target === canvas) click(e); },
    reset: () => Object.assign(goal, home)});
  const ray = new THREE.Raycaster(), mv = new THREE.Vector2();
  function click(e) {
    mv.set(e.clientX / innerWidth * 2 - 1, -(e.clientY / innerHeight) * 2 + 1); ray.setFromCamera(mv, C);
    const h = ray.intersectObjects(PICK.filter(x => { let k = x; while (k) { if (k !== x && !k.visible) return false; k = k.parent; } return true; }), false)[0];
    if (!h) return; const ud = h.object.userData;
    if (ud.person) { const p = ud.person; if (p.kind === 'rep') o.onRep && o.onRep(); else o.onPerson && o.onPerson(p.info, p.kind); }
    else if (ud.table && o.onTable) o.onTable(spec.tableInfo ? spec.tableInfo(snap, ud.table) : {label: ud.table});
  }

  // ------------------------------------------------------------------ escena del piso + copia viva
  const api = {THREE, S, C, R, mesh, flat, M, glow, tex, point, canvasScreen, screen, clipText, tag, setTag, dropTag, at, zoneTag, tagHtml, esc, track,
    makePerson, setRing, play, place, goTo, sitAt, arrive, leave, dropPerson, people, PICK, hitM, lite: () => lite, peopleOk: () => peopleOk, warn, chip, floor, o, RoundedBoxGeometry, loader: L};
  const scene = await spec.build(api);
  // paredes del piso (y lo pegado a ellas: logos, pantallas, ventanas): se ocultan si quedan entre la cámara y el centro
  const WALLS = {back: [], front: [], left: [], right: []}; const wb = new THREE.Box3();
  S.updateMatrixWorld(true);
  S.traverse(x => { if (!x.isMesh || x.isSkinnedMesh || x.userData.person || x.userData.personShadow) return; wb.setFromObject(x); if (wb.isEmpty()) return;
    const side = P.wallSide({min: wb.min.toArray(), max: wb.max.toArray()}, spec.room); if (side) WALLS[side].push(x); });
  let hidden = '';
  function cutaway() { const h = P.wallsToHide(C.position.toArray(), spec.room); const k = Object.keys(h).filter(s => h[s]).join(',');
    if (k === hidden) return; hidden = k; for (const [side, list] of Object.entries(WALLS)) list.forEach(m => { m.visible = !h[side]; }); R.shadowMap.needsUpdate = true; }
  let snap = null;
  try { snap = await getJson(spec.liveUrl); } catch (e) { chip('Sin conexión', false); }
  try { await Promise.race([document.fonts.load('800 46px Inter'), new Promise(r => setTimeout(r, 1500))]); } catch (e) { /* fuente del sistema */ }
  $('[data-load]').textContent = 'Cargando las personas…';
  try { await loadPeople(); } catch (e) { warn('Personajes no disponibles: el piso se ve sin personas'); }
  const weight = () => { const st = [...used].reduce((a, f) => a + ((man.files[f] || {}).bytes || 0), 0);
    const mx = peopleOk ? Object.entries((mixMan && mixMan.files) || {}).filter(([f]) => Object.keys(CH).some(n => f === `personajes/${n}.glb`) || [...avail].some(n => f === `animaciones/${n}.glb`)).reduce((a, [, m]) => a + m.bytes, 0) : 0;
    return {static: st, mixamo: mx, total: st + mx}; };
  $('[data-mb]').textContent = `${(weight().total / 1048576).toFixed(1)} MB`;
  function apply(next, first) { const prev = first ? null : snap; snap = next; if (snap) scene.apply(snap, prev, first); R.shadowMap.needsUpdate = true; }
  if (snap) apply(snap, true);
  let composer = null;
  function buildComposer() { if (composer) composer.dispose(); composer = new EffectComposer(R); composer.addPass(new RenderPass(S, C));
    if (!lite) composer.addPass(new UnrealBloomPass(new THREE.Vector2(innerWidth, innerHeight), ...(spec.bloom || [.3, .4, .96]))); composer.addPass(new OutputPass()); }
  buildComposer(); $('[data-load]').remove();
  $('[data-out]').onclick = () => o.onClose && o.onClose();
  log && log(`<b>${esc(spec.title)}</b> · piso aprobado listo (${(weight().total / 1048576).toFixed(1)} MB)`);

  // consulta cada 7 s con rev (solo cambios), pausa si la pestaña no se ve
  let timer = null, dead = false;
  async function poll() {
    if (dead || document.hidden) return;
    try { const r = await getJson(spec.liveUrl + (spec.liveUrl.includes('?') ? '&' : '?') + 'rev=' + encodeURIComponent((snap && snap.rev) || '')); if (!r.same) apply(r, !snap); }
    catch (e) { chip('Sin conexión', false); }
  }
  function schedule() { clearTimeout(timer); if (!dead) timer = setTimeout(async () => { await poll(); schedule(); }, P.LIVE_MS); }
  const onVis = () => { if (document.hidden) clearTimeout(timer); else { poll(); schedule(); } };
  document.addEventListener('visibilitychange', onVis); schedule();

  function setLite(on) { lite = !!on; rendererMode(); S.traverse(x => { if (x.userData.personShadow) x.castShadow = !lite; }); POINTS.forEach(([l]) => { l.visible = !lite; });
    if (scene.key) { scene.key.shadow.mapSize.set(lite ? 1024 : 2048, lite ? 1024 : 2048); if (scene.key.shadow.map) { scene.key.shadow.map.dispose(); scene.key.shadow.map = null; } }
    buildComposer(); resize(); }
  if (lite && scene.key) setLite(true);
  function resize() { C.aspect = innerWidth / innerHeight; C.updateProjectionMatrix(); R.setSize(innerWidth, innerHeight, false); if (composer) composer.setSize(innerWidth, innerHeight); }
  addEventListener('resize', resize); resize();

  const clock = new THREE.Clock(); let frames = 0, fpsT = 0, fpsShown = 0, fpsSamples = 0, frameNo = 0;
  function tick() {
    const dt = Math.min(clock.getDelta(), .05), t = clock.elapsedTime, k = 1 - Math.pow(.003, dt);
    for (const q of ['az', 'pol', 'dist', 'tx', 'tz']) cam[q] += (goal[q] - cam[q]) * k;
    C.position.set(...P.camPos(cam, T0.y)); C.lookAt(cam.tx, T0.y, cam.tz); cutaway();
    for (const p of people) {
      p.mixer.update(dt); if (!p.path.length) continue;
      const [x, z] = p.path[0]; const r = p.g.position; const dx = x - r.x, dz = z - r.z, d = Math.hypot(dx, dz);
      if (d < .04) { r.x = x; r.z = z; p.path.shift(); if (!p.path.length) { const f = p.then; p.then = null; if (f) f(); else play(p, 'Idle'); } }
      else { const sp = Math.min(d, dt * WALK); r.x += dx / d * sp; r.z += dz / d * sp; let dr = Math.atan2(dx, dz) - p.g.rotation.y; dr = Math.atan2(Math.sin(dr), Math.cos(dr)); p.g.rotation.y += dr * Math.min(1, dt * 8); }
    }
    if (scene.tick) scene.tick(t, dt);
    frameNo++; if (frameNo % (lite ? 4 : 3) === 0) R.shadowMap.needsUpdate = true;
    composer.render(); placeTags();
    frames++; fpsT += dt; if (fpsT >= 1) { fpsShown = Math.round(frames / fpsT); frames = 0; fpsT = 0; fpsSamples++; $('[data-fps]').textContent = `${fpsShown} FPS${lite ? ' · liviano' : ''}`;
      if (fpsSamples === 6 && fpsShown < 30 && !lite && o.liteChosen && o.liteChosen() == null) { o.onAutoLite && o.onAutoLite(); } }
  }
  function close() {
    dead = true; clearTimeout(timer); document.removeEventListener('visibilitychange', onVis);
    gestures.detach(); canvas.style.touchAction = ''; removeEventListener('resize', resize);
    people.slice().forEach(dropPerson); if (composer) composer.dispose();
    S.traverse(x => { if (x.geometry) x.geometry.dispose(); if (x.isInstancedMesh) x.dispose(); });
    disposables.forEach(d => { try { d.dispose(); } catch (e) { /* ya liberado */ } });
    ui.remove(); tagLayer.remove();
    R.useLegacyLights = saved.legacy; R.toneMapping = saved.tm; R.toneMappingExposure = saved.exp; R.shadowMap.type = saved.shadow; R.shadowMap.enabled = saved.se; R.setPixelRatio(saved.pr); R.shadowMap.autoUpdate = true; R.shadowMap.needsUpdate = true;
  }
  return {tick, close, setLite, resize, get fps() { return fpsShown; }, get snap() { return snap; }, get scene() { return S; }, get people() { return people.length; },
    get weight() { return weight(); }, get camera() { return C; }, apply: n => apply(n, !snap),
    rebuild() { people.slice().forEach(dropPerson); if (scene.reset) scene.reset(); if (snap) apply(snap, true); },   // el editor cambió un personaje
    view(pos, look) { const t = new THREE.Vector3(...look), d = new THREE.Vector3(...pos).sub(t); Object.assign(goal, {dist: d.length(), pol: Math.acos(d.y / d.length()), az: Math.atan2(d.x, d.z), tx: t.x, tz: t.z}); Object.assign(cam, goal); T0.y = t.y; },
    get cameraState() { return Object.assign({}, cam); }, get limits() { return LIM; }, get hiddenWalls() { return hidden; }, get dragging() { return gestures.dragging; }};
}

// Configuración guardada (editor) de una persona: capas plantilla global -> plantilla de la empresa -> persona.
export function savedFor(o, kind, key, uniform) { try { return (o.rawCfg && o.rawCfg(kind, key, uniform)) || {}; } catch (e) { return {}; } }
