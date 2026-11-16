// Personajes: Caricatura (por partes, generada por código) y Humano (personas base de Mixamo).
import { THREE, Style, mat, mesh } from './core.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { MeshoptDecoder } from 'three/addons/libs/meshopt_decoder.module.js';
import * as SU from 'three/addons/utils/SkeletonUtils.js';

// ---------- opciones (lo que muestra el editor)
export const OPT = {
  body: [['delgado', 'Delgado'], ['medio', 'Medio'], ['robusto', 'Robusto']],
  skin: ['#ffe0c2', '#f1c27d', '#e0ac69', '#c68642', '#a0673f', '#8d5524', '#6b3e1f', '#4a2a14'],
  eyes: [['redondos', 'Redondos'], ['felices', 'Felices'], ['grandes', 'Grandes']],
  brows: [['normal', 'Normales'], ['gruesas', 'Gruesas'], ['finas', 'Finas']],
  mouth: [['sonrisa', 'Sonrisa'], ['abierta', 'Feliz'], ['seria', 'Seria']],
  hair: [['rapado', 'Rapado'], ['corto', 'Corto'], ['crespo', 'Crespo largo'], ['afro', 'Afro'], ['largo', 'Largo liso'], ['ondulado', 'Ondulado'], ['mono', 'Moño'], ['cola', 'Cola'], ['trenzas', 'Trenzas'], ['calvo', 'Calvo']],
  hairColor: ['#141414', '#3b2414', '#7a4a24', '#e8c26b', '#b4532a', '#9ca3af', '#ffffff', '#8b2fd9', '#f20b6d', '#2563eb', '#16a34a', '#f97316'],
  beard: [['ninguna', 'Sin barba'], ['corta', 'Corta'], ['larga', 'Larga'], ['bigote', 'Bigote'], ['candado', 'Candado']],
  top: [['camiseta', 'Camiseta'], ['camisa', 'Camisa'], ['polo', 'Polo'], ['chaqueta', 'Chaqueta'], ['blazer', 'Blazer'], ['buzo', 'Buzo'], ['chef', 'Chaqueta de chef']],
  bottom: [['jean', 'Jean'], ['pantalon', 'Pantalón'], ['short', 'Short'], ['falda', 'Falda']],
  complete: [['ninguno', 'Ninguno'], ['vestido', 'Vestido'], ['overol', 'Overol']],
  shoes: [['tenis', 'Tenis'], ['zapatos', 'Zapatos'], ['botas', 'Botas'], ['tacones', 'Tacones']],
  acc: [['gorra', 'Gorra'], ['casco', 'Casco'], ['gorro_chef', 'Gorro de chef'], ['diadema', 'Diadema'], ['gafas', 'Gafas'], ['delantal', 'Delantal'], ['chaleco', 'Chaleco reflectivo'], ['reloj', 'Reloj'], ['aretes', 'Aretes']],
  colors: ['#111111', '#ffffff', '#9ca3af', '#1f2937', '#2c4a7c', '#1e3a8a', '#2563eb', '#38bdf8', '#16a34a', '#facc15', '#d59f2a', '#f97316', '#dc2626', '#7f1d1d', '#f20b6d', '#f472b6', '#7c3aed', '#c8a27a', '#5b3a26'],
};
export const HUMAN_BASES = [
  ['Ch22_nonPBR', 'Mujer · casual', 'F'], ['Ch21_nonPBR', 'Mujer · camisa', 'F'], ['Ch07_nonPBR', 'Mujer · traje', 'F'],
  ['Remy', 'Hombre · casual', 'M'], ['Ch42_nonPBR', 'Hombre · camiseta', 'M'], ['Ch01_nonPBR', 'Hombre · urbano', 'M'], ['Ch06_nonPBR', 'Hombre · oscuro', 'M'], ['Ch17_nonPBR', 'Hombre · campo', 'M'],
];
export const HUMAN_ACC = []; // en Humano no se ponen accesorios sueltos (se veían mal): casco y chaleco vienen con la persona base "campo"
export const CLIPS = [['idle', '▶ Quieta'], ['walk', '🚶 Caminar'], ['sit', '🪑 Sentada'], ['work', '🧾 Trabajando'], ['dance', '💃 Bailar']];

export function defaultToon(seed = 0) {
  const r = (a) => a[Math.abs(seed * 7 + a.length) % a.length];
  return { body: 'medio', height: 1, skin: OPT.skin[seed % 8], eyes: 'redondos', brows: 'normal', mouth: 'sonrisa', blush: true, freckles: false,
    hair: OPT.hair[seed % 9][0], hairColor: OPT.hairColor[seed % 6], hairLen: .6, hairVol: .5, beard: 'ninguna', beardColor: '#2b1a10',
    top: 'camiseta', topColor: '#ffffff', innerColor: '#ffffff', bottom: 'jean', bottomColor: '#2c4a7c', complete: 'ninguno', completeColor: '#dc2626',
    shoes: 'tenis', shoesColor: '#f5f5f5', acc: {}, accColor: '#f20b6d' };
}
export function defaultHuman(seed = 0) { return { base: HUMAN_BASES[seed % HUMAN_BASES.length][0], skinTint: '#ffffff', hairColor: '', topColor: '', topStyle: 'original', bottomColor: '', shoesColor: '', beard: 'ninguna', beardColor: '#2b1a10', acc: {}, accColor: '#f20b6d' }; }
export function randomToon() {
  const p = a => a[Math.floor(Math.random() * a.length)];
  const t = defaultToon(Math.floor(Math.random() * 99));
  Object.assign(t, { body: p(OPT.body)[0], skin: p(OPT.skin), eyes: p(OPT.eyes)[0], mouth: p(OPT.mouth)[0], hair: p(OPT.hair)[0], hairColor: p(OPT.hairColor), top: p(OPT.top)[0], topColor: p(OPT.colors), innerColor: p(['#ffffff', '#111111']), bottom: p(OPT.bottom)[0], bottomColor: p(OPT.colors), shoes: p(OPT.shoes)[0], shoesColor: p(OPT.colors), beard: Math.random() < .25 ? p(OPT.beard)[0] : 'ninguna', complete: Math.random() < .15 ? p(['vestido', 'overol']) : 'ninguno', completeColor: p(OPT.colors), acc: Math.random() < .4 ? { [p(OPT.acc)[0]]: true } : {}, hairLen: Math.random(), hairVol: Math.random() });
  return t;
}

// ---------- CARICATURA
const cap = (r, l) => new THREE.CapsuleGeometry(r, l, 8, 16), sph = (r, a = 24, b = 18) => new THREE.SphereGeometry(r, a, b);
export function buildToon(a) {
  const R = new THREE.Group(); const body = new THREE.Group(); R.add(body);
  const sc = { delgado: .85, medio: 1, robusto: 1.22 }[a.body] || 1; body.scale.set(1, a.height || 1, 1);
  const M = c => mat(c);
  const skin = a.skin;
  const full = a.complete && a.complete !== 'ninguno';
  const legC = full && a.complete === 'overol' ? a.completeColor : (a.bottom === 'falda' ? skin : a.bottomColor);
  const shinC = a.bottom === 'short' || a.bottom === 'falda' || (full && a.complete === 'vestido') ? skin : legC;
  // piernas (pivote en la cadera)
  const legs = [-1, 1].map(s => { const p = new THREE.Group(); p.position.set(s * .13 * sc, .62, 0); body.add(p);
    mesh(cap(.115, .2), M(full && a.complete === 'vestido' ? skin : legC), 0, -.15, 0, p);
    mesh(cap(.105, .2), M(shinC), 0, -.38, 0, p);
    const sh = a.shoes, shc = a.shoesColor;
    if (sh === 'botas') { mesh(new THREE.BoxGeometry(.21, .2, .3), M(shc), 0, -.52, .04, p); }
    else if (sh === 'tacones') { mesh(new THREE.BoxGeometry(.17, .07, .27), M(shc), 0, -.59, .05, p); mesh(new THREE.BoxGeometry(.05, .1, .05), M(shc), 0, -.6, -.07, p); }
    else { mesh(new THREE.BoxGeometry(.2, .1, .3), M(sh === 'tenis' ? shc : shc), 0, -.57, .05, p); if (sh === 'tenis') mesh(new THREE.BoxGeometry(.205, .03, .305), M('#ffffff'), 0, -.61, .05, p); }
    return p; });
  // torso (pivote en la cadera)
  const torso = new THREE.Group(); torso.position.set(0, .62, 0); body.add(torso);
  const topC = full ? a.completeColor : (a.top === 'chef' ? '#f8fafc' : a.topColor);
  const t = mesh(cap(.27, .34), M(a.complete === 'overol' ? a.innerColor || '#ffffff' : topC), 0, .48, 0, torso); t.scale.set(sc, 1, sc);
  if (!full) { if (a.bottom === 'falda') mesh(new THREE.CylinderGeometry(.27 * sc, .44 * sc, .45, 24), M(a.bottomColor), 0, .02, 0, torso); else mesh(new THREE.CylinderGeometry(.275 * sc, .275 * sc, .22, 20), M(a.bottomColor), 0, .1, 0, torso); }
  if (a.complete === 'vestido') mesh(new THREE.CylinderGeometry(.27 * sc, .46 * sc, .55, 24), M(a.completeColor), 0, .0, 0, torso);
  if (a.complete === 'overol') { mesh(new THREE.CylinderGeometry(.278 * sc, .278 * sc, .26, 20), M(a.completeColor), 0, .1, 0, torso); mesh(new THREE.BoxGeometry(.38 * sc, .3, .05), M(a.completeColor), 0, .38, .25 * sc, torso); [-1, 1].forEach(s => mesh(new THREE.BoxGeometry(.05, .32, .04), M(a.completeColor), s * .13, .66, .24 * sc, torso)); }
  if (!full) {
    if (a.top === 'chaqueta' || a.top === 'blazer') { mesh(new THREE.CylinderGeometry(.3 * sc, .31 * sc, .55, 24, 1, true, .42, Math.PI * 2 - .84), M(a.topColor), 0, .5, 0, torso); mesh(cap(.268 * sc, .3), M(a.innerColor), 0, .5, .01, torso).scale.set(.6, 1, 1);
      [-1, 1].forEach(s => { const l = mesh(new THREE.BoxGeometry(.06, .34, .04), M(a.topColor), s * .1, .58, .27 * sc, torso); l.rotation.z = s * .25; }); }
    if (a.top === 'camisa' || a.top === 'polo') { mesh(new THREE.TorusGeometry(.12, .03, 8, 20, Math.PI), M(a.top === 'camisa' ? a.innerColor : a.topColor), 0, .82, .05, torso).rotation.x = -.5; for (let i = 0; i < 3; i++) mesh(sph(.015, 6, 4), M('#111'), 0, .68 - i * .12, .27 * sc, torso); }
    if (a.top === 'buzo') { const h = mesh(new THREE.TorusGeometry(.2, .07, 10, 20), M(a.topColor), 0, .82, -.12, torso); h.rotation.x = Math.PI / 2.4; mesh(new THREE.BoxGeometry(.3 * sc, .14, .04), M(a.topColor), 0, .28, .27 * sc, torso); }
    if (a.top === 'chef') { for (let i = 0; i < 4; i++) [-1, 1].forEach(s => mesh(sph(.017, 6, 4), M('#111'), s * .07, .7 - i * .1, .27 * sc, torso)); }
  }
  // brazos (pivote en el hombro)
  const sleeve = full ? (a.complete === 'overol' ? (a.innerColor || '#fff') : a.completeColor) : ((a.top === 'chaqueta' || a.top === 'blazer') ? a.topColor : topC);
  const arms = [-1, 1].map(s => { const p = new THREE.Group(); p.position.set(s * .34 * sc, .76, 0); torso.add(p); p.rotation.z = s * .12;
    const shortS = !full && (a.top === 'camiseta' || a.top === 'polo');
    mesh(cap(.085, .14), M(sleeve), 0, -.12, 0, p); mesh(cap(.08, .16), M(shortS ? skin : sleeve), 0, -.33, 0, p); mesh(sph(.08), M(skin), 0, -.5, 0, p);
    if (s < 0 && a.acc?.reloj) mesh(new THREE.TorusGeometry(.085, .02, 8, 16), M(a.accColor), 0, -.42, 0, p).rotation.x = Math.PI / 2;
    return p; });
  // cabeza
  const head = new THREE.Group(); head.position.set(0, 1.16, 0); torso.add(head);
  mesh(new THREE.CylinderGeometry(.08, .09, .12, 12), M(skin), 0, -.32, 0, head);
  mesh(sph(.34), M(skin), 0, 0, 0, head);
  [-1, 1].forEach(s => mesh(sph(.06), M(skin), s * .33, -.02, 0, head));
  // cara
  const B = c => new THREE.MeshBasicMaterial({ color: c });
  [-1, 1].forEach(s => {
    if (a.eyes === 'felices') { const e = new THREE.Mesh(new THREE.TorusGeometry(.045, .014, 6, 12, Math.PI), B('#111')); e.position.set(s * .11, .01, .32); head.add(e); }
    else { const r = a.eyes === 'grandes' ? .065 : .05; const e = new THREE.Mesh(sph(r, 12, 10), B('#111')); e.scale.set(.8, 1.15, .5); e.position.set(s * .11, .02, .31); head.add(e); const h = new THREE.Mesh(sph(r * .3, 8, 6), B('#fff')); h.position.set(s * .11 + .015, .05, .335); head.add(h); }
    if (a.blush) { const b = new THREE.Mesh(sph(.045, 10, 8), new THREE.MeshBasicMaterial({ color: 0xff8fa3, transparent: true, opacity: .5 })); b.scale.set(1, .6, .3); b.position.set(s * .2, -.08, .29); head.add(b); }
    const bw = { gruesas: [.1, .03], finas: [.09, .01], normal: [.09, .018] }[a.brows || 'normal'];
    const br = new THREE.Mesh(new THREE.BoxGeometry(bw[0], bw[1], .02), B(a.hairColor)); br.position.set(s * .11, .12, .315); br.rotation.z = -s * .12; head.add(br);
  });
  if (a.freckles) for (let i = 0; i < 8; i++) { const f = new THREE.Mesh(sph(.008, 6, 4), B('#7a4a24')); f.position.set((i % 4 - 1.5) * .04 + (i < 4 ? -.15 : .15) * 0 + (i < 4 ? -.14 : .1), -.05 + (i % 2) * .02, .32); head.add(f); }
  if (a.mouth === 'abierta') { const m = new THREE.Mesh(new THREE.CircleGeometry(.05, 16, Math.PI, Math.PI), B('#5a1f1f')); m.position.set(0, -.1, .335); head.add(m); }
  else if (a.mouth === 'seria') { const m = new THREE.Mesh(new THREE.BoxGeometry(.08, .012, .01), B('#5a1f1f')); m.position.set(0, -.12, .33); head.add(m); }
  else { const m = new THREE.Mesh(new THREE.TorusGeometry(.06, .012, 8, 20, Math.PI), B('#5a1f1f')); m.rotation.z = Math.PI; m.position.set(0, -.1, .32); head.add(m); }
  // pelo
  const hc = a.hairColor, H = M(hc), L = .5 + (a.hairLen ?? .6), V = .8 + (a.hairVol ?? .5) * .5, ht = a.hair;
  const capH = () => { const g = new THREE.SphereGeometry(.355, 28, 16, 0, Math.PI * 2, 0, Math.PI * .52); const h = mesh(g, H, 0, .02, -.02, head); h.rotation.x = -.25; return h; };
  const rnd = (i) => ((Math.sin(i * 127.1) * 43758.5453) % 1 + 1) % 1;
  if (ht === 'rapado') { const g = new THREE.SphereGeometry(.345, 28, 16, 0, Math.PI * 2, 0, Math.PI * .45); mesh(g, H, 0, .01, -.02, head).rotation.x = -.3; }
  if (ht === 'corto') { capH(); for (let i = 0; i < 5; i++) mesh(sph(.08 * V), H, -.2 + i * .1, .28, .12 - Math.abs(i - 2) * .03, head); }
  if (ht === 'crespo') { for (let i = 0; i < 60; i++) { const an = rnd(i) * Math.PI * 2, b = rnd(i + 99) * Math.PI * .62, r = .37 + rnd(i + 7) * .05; const y = Math.cos(b) * r, zz = Math.sin(b) * Math.sin(an) * r; if (zz > .18 && y < .18) continue; mesh(sph((.085 + rnd(i + 3) * .04) * V, 10, 8), H, Math.sin(b) * Math.cos(an) * r * 1.15, y, zz - .04, head); }
    for (let i = 0; i < Math.round(30 * L); i++) { const s = i % 2 ? 1 : -1; mesh(sph((.08 + rnd(i + 5) * .03) * V, 10, 8), H, s * (.3 + rnd(i + 11) * .12) * V, -.05 - rnd(i + 13) * .5 * L, -.08 - rnd(i + 17) * .15, head); } }
  if (ht === 'afro') { for (let i = 0; i < 80; i++) { const an = rnd(i) * Math.PI * 2, b = rnd(i + 50) * Math.PI * .6, r = (.44 + rnd(i + 9) * .06) * V; const y = Math.cos(b) * r + .06, zz = Math.sin(b) * Math.sin(an) * r; if (zz > .2 && y < .24) continue; mesh(sph(.09 + rnd(i + 2) * .03, 10, 8), H, Math.sin(b) * Math.cos(an) * r, y, zz - .06, head); } }
  if (ht === 'largo') { capH(); const l = mesh(cap(.3 * V, .5 * L), H, 0, -.2 - .1 * L, -.12, head); l.scale.set(1.05, 1, .5); }
  if (ht === 'ondulado') { capH(); [-1, 1].forEach(s => { for (let i = 0; i < Math.round(3 + 4 * L); i++) mesh(sph(.11 * V, 10, 8), H, s * (.3 + (i % 2) * .05), -.02 - i * .11, -.05, head); }); }
  if (ht === 'mono') { capH(); mesh(sph(.15 * V), H, 0, .32, -.15, head); }
  if (ht === 'cola') { capH(); const tl = mesh(cap(.09 * V, .3 + .3 * L), H, 0, -.1, -.38, head); tl.rotation.x = .35; }
  if (ht === 'trenzas') { capH(); [-1, 1].forEach(s => { for (let i = 0; i < Math.round(4 + 4 * L); i++) mesh(sph(.065 - i * .003, 10, 8), H, s * .32, -.1 - i * .11, .02, head); }); }
  // barba
  const BC = M(a.beardColor || hc);
  if (a.beard === 'corta' || a.beard === 'larga' || a.beard === 'candado') { const g = new THREE.SphereGeometry(.36, 24, 16, Math.PI / 2 - (a.beard === 'candado' ? .5 : 1.1), a.beard === 'candado' ? 1 : 2.2, Math.PI * .5, Math.PI * .42); mesh(g, BC, 0, 0, 0, head); }
  if (a.beard === 'larga') mesh(cap(.16, .2), BC, 0, -.38, .2, head);
  if (a.beard === 'bigote' || a.beard === 'candado') mesh(new THREE.BoxGeometry(.16, .035, .04), BC, 0, -.06, .33, head);
  // accesorios
  const A = a.acc || {}, ac = a.accColor;
  if (A.gafas) [-1, 1].forEach(s => { const g = new THREE.Mesh(new THREE.TorusGeometry(.065, .012, 8, 20), B('#111')); g.position.set(s * .11, .02, .33); head.add(g); });
  if (A.gorra) { mesh(new THREE.SphereGeometry(.37, 28, 16, 0, Math.PI * 2, 0, Math.PI * .5), M(ac), 0, .05, 0, head); mesh(new THREE.BoxGeometry(.4, .03, .25), M(ac), 0, .07, .3, head); }
  if (A.casco) { mesh(new THREE.SphereGeometry(.39, 28, 16, 0, Math.PI * 2, 0, Math.PI * .5), M('#facc15'), 0, .07, 0, head); mesh(new THREE.CylinderGeometry(.46, .46, .03, 28), M('#facc15'), 0, .07, .05, head); }
  if (A.gorro_chef) { mesh(new THREE.CylinderGeometry(.3, .3, .12, 24), M('#ffffff'), 0, .3, 0, head); for (let i = 0; i < 5; i++) mesh(sph(.15), M('#ffffff'), -.18 + i * .09, .45, 0, head); }
  if (A.diadema) { mesh(new THREE.TorusGeometry(.37, .025, 8, 24, Math.PI), M('#222222'), 0, .02, 0, head); [-1, 1].forEach(s => mesh(sph(.08), M('#222222'), s * .36, 0, 0, head)); const mic = mesh(cap(.012, .2), M('#222222'), -.24, -.14, .24, head); mic.rotation.z = 1.1; mic.rotation.y = .6; }
  if (A.aretes) [-1, 1].forEach(s => mesh(sph(.025, 8, 6), M('#facc15'), s * .35, -.09, 0, head));
  if (A.delantal) mesh(new THREE.BoxGeometry(.38 * sc, .55, .03), M(ac), 0, .2, .27 * sc, torso);
  if (A.chaleco) { mesh(new THREE.CylinderGeometry(.3 * sc, .3 * sc, .42, 24), M('#f97316'), 0, .52, 0, torso); [.42, .6].forEach(y => mesh(new THREE.CylinderGeometry(.305 * sc, .305 * sc, .045, 24), M('#e5e7eb'), 0, y, 0, torso)); }
  R.scale.setScalar(.8);
  R.userData.rig = { kind: 'toon', body, legs, arms, torso, head };
  return R;
}
export function animToon(rig, clip, t) {
  const { body, legs, arms, torso, head } = rig;
  body.position.y = 0; body.rotation.set(0, 0, 0); torso.rotation.set(0, 0, 0); head.rotation.set(0, 0, 0);
  legs.forEach(l => l.rotation.set(0, 0, 0)); arms.forEach((a, i) => { a.rotation.set(0, 0, (i ? 1 : -1) * .12); });
  if (clip === 'idle') { torso.rotation.x = Math.sin(t * 1.6) * .02; head.rotation.y = Math.sin(t * .7) * .15; arms.forEach((a, i) => a.rotation.x = Math.sin(t * 1.6 + i) * .04); }
  if (clip === 'walk') { const s = Math.sin(t * 6); legs[0].rotation.x = s * .55; legs[1].rotation.x = -s * .55; arms[0].rotation.x = -s * .5; arms[1].rotation.x = s * .5; body.position.y = Math.abs(Math.cos(t * 6)) * .03; }
  if (clip === 'sit') { body.position.y = -.17; legs.forEach(l => l.rotation.x = -1.5); arms.forEach(a => a.rotation.x = -.45); head.rotation.y = Math.sin(t * .8) * .2; }
  if (clip === 'work') { arms.forEach((a, i) => a.rotation.x = -1.05 + Math.sin(t * 9 + i * 2) * .07); head.rotation.x = .15; }
  if (clip === 'dance') { body.rotation.z = Math.sin(t * 4) * .12; body.position.y = Math.abs(Math.sin(t * 4)) * .06; arms[0].rotation.z = -2.2 + Math.sin(t * 4) * .4; arms[1].rotation.z = 2.2 + Math.sin(t * 4 + 1) * .4; legs[0].rotation.x = Math.sin(t * 4) * .25; legs[1].rotation.x = -Math.sin(t * 4) * .25; head.rotation.z = Math.sin(t * 4) * .15; }
}

// ---------- HUMANO (Mixamo, en Clonexa desde el bucket privado con sesión)
const loader = new GLTFLoader(); loader.setMeshoptDecoder(MeshoptDecoder);
const CH = {}, AN = {};
// Mixamo: NUNCA en el repo. En Clonexa salen del bucket privado con sesión (los mismos de la oficina):
// consola /admin-v2plus/oficina/bar, visor del cliente <ruta firmada>/bar (setAssetBase).
export let ASSET_BASE = '/admin-v2plus/oficina/bar';
export function setAssetBase(b) { ASSET_BASE = b; }
async function loadChar(n) { if (!CH[n]) CH[n] = loader.loadAsync(`${ASSET_BASE}/personajes/${n}.glb`); return CH[n]; }
const ANIM_FILE = { idle: 'Idle', walk: 'Walking', sit: 'Sitting', work: 'Typing', dance: 'Rumba_Dancing', talk: 'Talking' };
async function loadAnim(k) { const f = ANIM_FILE[k]; if (!AN[f]) AN[f] = loader.loadAsync(`${ASSET_BASE}/animaciones/${f}.glb`).then(g => { let hy = 1; g.scene.traverse(o => { if (/Hips$/.test(o.name)) hy = o.position.y; }); return { clip: g.animations[0], hy }; }); return AN[f]; }
const RX = { top: /Shirt|Tops|Suit|Vest/i, bottom: /Pants|Shorts|Bottoms/i, shoes: /Shoes|Sneakers|Heels|Boots/i, hair: /Hair/i, body: /Body/i };
export async function buildHuman(h, clip = 'idle') {
  const gltf = await loadChar(h.base);
  const m = SU.clone(gltf.scene); let chy = 1, pre = '';
  m.traverse(q => { if (/Hips$/.test(q.name) && chy === 1) { chy = q.position.y; pre = q.name.replace(/Hips$/, ''); } });
  m.updateMatrixWorld(true); const bb = new THREE.Box3().setFromObject(m, true); const fem = /Ch07|Ch21|Ch22/.test(h.base);
  m.scale.multiplyScalar((fem ? 1.66 : 1.77) / (bb.max.y - bb.min.y)); m.updateMatrixWorld(true); const b2 = new THREE.Box3().setFromObject(m, true); m.position.y -= b2.min.y;
  const R = new THREE.Group(); R.add(m);
  m.traverse(q => {
    if (!q.isMesh) return; q.castShadow = true; const n = q.name;
    const tint = (col, flat) => { q.material = q.material.clone(); if (flat) { q.material.map = null; q.material.color.set(col); q.material.roughness = .7; } else q.material.color.set(col); q.material.needsUpdate = true; };
    if (RX.hair.test(n) && h.hairColor) tint(h.hairColor, true);
    else if (RX.top.test(n) && h.topColor) tint(h.topColor, h.topStyle === 'liso');
    else if (RX.top.test(n) && h.topStyle === 'liso') tint('#ffffff', false);
    else if (RX.bottom.test(n) && h.bottomColor) tint(h.bottomColor, true);
    else if (RX.shoes.test(n) && h.shoesColor) tint(h.shoesColor, true);
    else if ((RX.body.test(n) || n === m.name) && h.skinTint && h.skinTint !== '#ffffff') tint(h.skinTint, false);
    if (Style.toon() && q.material) { const old = q.material; const tm = new THREE.MeshToonMaterial({ color: old.color, map: old.map, gradientMap: (Style.gradient || null) }); q.material = tm; }
  });
  // accesorios pegados a los huesos
  m.updateMatrixWorld(true);
  const bone = re => { let b = null; m.traverse(o => { if (!b && o.isBone && re.test(o.name)) b = o; }); return b; };
  const attach = (re, obj, pos) => { const b = bone(re); if (!b) return; const ws = new THREE.Vector3(); b.getWorldScale(ws); obj.scale.multiplyScalar(1 / ws.x); obj.position.set(pos[0] / ws.x, pos[1] / ws.x, pos[2] / ws.x); b.add(obj); };
  const A = {}, ac = h.accColor || '#f20b6d', MM = c => new THREE.MeshStandardMaterial({ color: c, roughness: .6 });
  const grp = (...ms) => { const g = new THREE.Group(); ms.forEach(x => g.add(x)); return g; };
  if (A.gorra) attach(/Head$/, grp(new THREE.Mesh(new THREE.SphereGeometry(.105, 24, 12, 0, Math.PI * 2, 0, Math.PI * .5), MM(ac)), (() => { const v = new THREE.Mesh(new THREE.BoxGeometry(.15, .01, .1), MM(ac)); v.position.set(0, .005, .1); return v; })()), [0, .13, .0]);
  if (A.casco) attach(/Head$/, grp(new THREE.Mesh(new THREE.SphereGeometry(.12, 24, 12, 0, Math.PI * 2, 0, Math.PI * .5), MM('#facc15')), new THREE.Mesh(new THREE.CylinderGeometry(.14, .14, .01, 24), MM('#facc15'))), [0, .14, 0]);
  if (A.diadema) attach(/Head$/, grp(new THREE.Mesh(new THREE.TorusGeometry(.1, .008, 8, 24, Math.PI), MM('#111')), ...[-1, 1].map(s => { const e = new THREE.Mesh(new THREE.SphereGeometry(.03, 12, 8), MM('#111')); e.position.set(s * .1, 0, 0); return e; })), [0, .1, .0]);
  if (A.gafas) attach(/Head$/, grp(...[-1, 1].map(s => { const g = new THREE.Mesh(new THREE.TorusGeometry(.022, .004, 8, 16), MM('#111')); g.position.set(s * .033, 0, 0); return g; })), [0, .085, .09]);
  if (A.delantal) attach(/Hips$/, new THREE.Mesh(new THREE.BoxGeometry(.3, .42, .012), MM(ac)), [0, -.16, .12]);
  if (A.chaleco) attach(/Spine2$/, grp(new THREE.Mesh(new THREE.CylinderGeometry(.17, .16, .34, 24, 1, true), new THREE.MeshStandardMaterial({ color: '#f97316', side: THREE.DoubleSide })), (() => { const s = new THREE.Mesh(new THREE.CylinderGeometry(.172, .172, .03, 24, 1, true), new THREE.MeshStandardMaterial({ color: '#e5e7eb', side: THREE.DoubleSide })); s.position.y = -.05; return s; })()), [0, -.02, 0]);
  if (h.beard && h.beard !== 'ninguna') { const g = new THREE.Mesh(new THREE.SphereGeometry(.095, 20, 12, Math.PI / 2 - 1.1, 2.2, Math.PI * .5, Math.PI * .45), MM(h.beardColor || '#2b1a10')); const gg = grp(g); if (h.beard === 'larga') { const l = new THREE.Mesh(new THREE.CapsuleGeometry(.04, .06, 6, 12), MM(h.beardColor)); l.position.set(0, -.1, .06); gg.add(l); } attach(/Head$/, gg, [0, .06, .01]); }
  const mixer = new THREE.AnimationMixer(m);
  R.userData.rig = { kind: 'human', mixer, model: m, pre, chy, current: null };
  await setHumanClip(R, clip);
  return R;
}
export async function setHumanClip(R, clip) {
  const rig = R.userData.rig; if (rig.current === clip) return; rig.current = clip;
  const a = await loadAnim(clip); const k = rig.chy / a.hy; const c = a.clip.clone();
  c.tracks.forEach(t => { t.name = t.name.replace(/^mixamorig\d*/, rig.pre); if (/Hips\.position$/.test(t.name)) { const v = t.values; const x0 = v[0], z0 = v[2]; for (let i = 0; i < v.length; i += 3) { v[i] = x0 * k; v[i + 1] *= k; v[i + 2] = z0 * k; } } });
  rig.mixer.stopAllAction(); rig.mixer.clipAction(c).play();
}

// constructor genérico
export async function buildCharacter(p, style, clip = 'idle') {
  if (style === 'human') { try { return await buildHuman(p.human || defaultHuman(), clip); } catch (e) { console.warn('Humano no cargó, uso caricatura', e); } }
  const g = buildToon(p.toon || defaultToon()); g.userData.clip = clip; return g;
}
export function tickCharacter(g, dt, t) {
  const r = g.userData.rig; if (!r) return;
  if (r.kind === 'toon') animToon(r, g.userData.clip || 'idle', t + (g.userData.phase || 0));
  else r.mixer.update(dt);
}
export async function setClip(g, clip) { if (g.userData.rig?.kind === 'human') await setHumanClip(g, clip); else g.userData.clip = clip; }
