// Núcleo: estilo (Humano / Caricatura), materiales, texturas y utilidades compartidas.
import * as THREE from 'three';
export {THREE};

export const BRAND = ['#f20b6d', '#7c3aed', '#111111', '#ffffff']; // se reemplaza con loadBrand()
export const PALETTE = ['#111111', '#ffffff', '#9ca3af', '#4b5563', '#7c4a2d', '#5b3a26', '#c8a27a', '#dc2626', '#f97316', '#facc15', '#16a34a', '#2563eb', '#1e3a8a', '#7c3aed', '#f20b6d', '#f472b6'];

// ---------- estilo
export const Style = {
  mode: 'human',
  gradient: null,
  toon() { return this.mode === 'toon'; },
};
function gradientMap() {
  if (!Style.gradient) {
    const t = new THREE.DataTexture(new Uint8Array([110, 110, 110, 255, 185, 185, 185, 255, 255, 255, 255, 255]), 3, 1);
    t.needsUpdate = true; t.minFilter = t.magFilter = THREE.NearestFilter; Style.gradient = t;
  }
  return Style.gradient;
}
export const OUTLINE = new THREE.MeshBasicMaterial({ color: 0x140c1f, side: THREE.BackSide });

// material según estilo
export function mat(color, o = {}) {
  const c = new THREE.Color(color);
  if (Style.toon()) {
    const m = new THREE.MeshToonMaterial({ color: c, gradientMap: gradientMap(), transparent: !!o.transparent, opacity: o.opacity ?? 1 });
    if (o.map) m.map = o.map;
    if (o.emissive) { m.emissive = new THREE.Color(o.emissive); m.emissiveIntensity = (o.emissiveIntensity ?? 1) * 0.6; }
    return m;
  }
  const m = new THREE.MeshStandardMaterial({ color: c, roughness: o.roughness ?? 0.55, metalness: o.metalness ?? 0.05, transparent: !!o.transparent, opacity: o.opacity ?? 1 });
  if (o.map) m.map = o.map;
  if (o.emissive) { m.emissive = new THREE.Color(o.emissive); m.emissiveIntensity = o.emissiveIntensity ?? 1; }
  return m;
}
export function glow(color, i = 2) {
  return new THREE.MeshStandardMaterial({ color: 0x000000, emissive: new THREE.Color(color), emissiveIntensity: Style.toon() ? i * 0.5 : i, toneMapped: false });
}
// malla con sombra y contorno en Caricatura
export function mesh(geo, material, x = 0, y = 0, z = 0, parent, out = true) {
  const k = new THREE.Mesh(geo, material);
  k.position.set(x, y, z); k.castShadow = true; k.receiveShadow = true;
  if (parent) parent.add(k);
  if (Style.toon() && out && !material.transparent && material.toneMapped !== false) {
    const l = new THREE.Mesh(geo, OUTLINE); l.scale.setScalar(1.035); l.userData.outline = true; k.add(l);
  }
  return k;
}

// ---------- texturas por canvas (cacheadas)
const texCache = new Map();
export function canvasTex(key, w, h, draw, repeat) {
  const k = key + '|' + (repeat ? repeat.join(',') : '');
  if (texCache.has(k)) return texCache.get(k);
  const cv = document.createElement('canvas'); cv.width = w; cv.height = h;
  draw(cv.getContext('2d'), w, h);
  const t = new THREE.CanvasTexture(cv); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 4;
  if (repeat) { t.wrapS = t.wrapT = THREE.RepeatWrapping; t.repeat.set(repeat[0], repeat[1]); }
  texCache.set(k, t); return t;
}
const shade = (hex, f) => { const c = new THREE.Color(hex); c.multiplyScalar(f); return '#' + c.getHexString(); };

// Materiales de PARED y PISO (nombre, dibujo). Todos aceptan color.
export const WALLS = {
  pintura: { name: 'Pintura lisa', def: '#e7e2f0' },
  ladrillo: { name: 'Ladrillo', def: '#8a4130' },
  ladrillo_blanco: { name: 'Ladrillo blanco', def: '#e5e1da' },
  concreto: { name: 'Concreto', def: '#8f8f93' },
  madera: { name: 'Madera en listones', def: '#7c4a2d' },
  panel: { name: 'Panel negro brillante', def: '#121016' },
  azulejo: { name: 'Azulejo', def: '#e8f1f5' },
  vidrio: { name: 'Vidrio', def: '#9bd8ff' },
  tapiz: { name: 'Papel tapiz', def: '#6d28d9' },
  piedra: { name: 'Piedra', def: '#77706a' },
};
export const FLOORS = {
  madera_clara: { name: 'Madera clara', def: '#c8a27a' },
  madera_oscura: { name: 'Madera oscura', def: '#5b3a26' },
  baldosa: { name: 'Baldosa blanca', def: '#e8e6e3' },
  ajedrez: { name: 'Ajedrez', def: '#111111' },
  concreto: { name: 'Concreto pulido', def: '#8d8d91' },
  epoxico: { name: 'Epóxico', def: '#5c6670' },
  alfombra: { name: 'Alfombra', def: '#3b2d4f' },
  negro: { name: 'Negro brillante', def: '#141218' },
  deck: { name: 'Deck', def: '#8b5a3c' },
  cesped: { name: 'Césped', def: '#3f8f3f' },
};
function drawWall(kind, col) {
  return (x, w, h) => {
    x.fillStyle = col; x.fillRect(0, 0, w, h);
    const dk = shade(col, 0.7), lt = shade(col, 1.15);
    if (kind === 'ladrillo' || kind === 'ladrillo_blanco') { x.strokeStyle = kind === 'ladrillo' ? dk : shade(col, 0.82); x.lineWidth = 5; for (let r = 0; r < 16; r++) { const y = r * 32; x.beginPath(); x.moveTo(0, y); x.lineTo(w, y); x.stroke(); for (let c = 0; c < 9; c++) { const xx = c * 64 + (r % 2 ? 32 : 0); x.beginPath(); x.moveTo(xx, y); x.lineTo(xx, y + 32); x.stroke(); } } }
    if (kind === 'concreto' || kind === 'piedra') { for (let i = 0; i < 900; i++) { x.fillStyle = Math.random() < .5 ? dk : lt; x.globalAlpha = .12; x.fillRect(Math.random() * w, Math.random() * h, 6, 6); } x.globalAlpha = 1; if (kind === 'piedra') { x.strokeStyle = dk; x.lineWidth = 4; for (let r = 0; r < 8; r++) for (let c = 0; c < 5; c++) x.strokeRect(c * 110 + (r % 2) * 50, r * 64, 100 + (c % 3) * 12, 60); } }
    if (kind === 'madera') { for (let i = 0; i < 16; i++) { x.fillStyle = i % 2 ? dk : lt; x.globalAlpha = .25; x.fillRect(i * 32, 0, 30, h); } x.globalAlpha = 1; x.strokeStyle = shade(col, .55); x.lineWidth = 2; for (let i = 0; i < 16; i++) { x.beginPath(); x.moveTo(i * 32, 0); x.lineTo(i * 32, h); x.stroke(); } }
    if (kind === 'panel') { x.strokeStyle = shade(col, 2.4); x.globalAlpha = .35; x.lineWidth = 3; for (let i = 0; i < 4; i++) { x.beginPath(); x.moveTo(i * 128 + 64, 0); x.lineTo(i * 128 + 64, h); x.stroke(); } x.globalAlpha = 1; }
    if (kind === 'azulejo') { x.strokeStyle = shade(col, .78); x.lineWidth = 4; for (let i = 0; i <= 8; i++) { x.beginPath(); x.moveTo(i * 64, 0); x.lineTo(i * 64, h); x.stroke(); x.beginPath(); x.moveTo(0, i * 64); x.lineTo(w, i * 64); x.stroke(); } }
    if (kind === 'tapiz') { x.fillStyle = lt; for (let r = 0; r < 8; r++) for (let c = 0; c < 8; c++) { x.beginPath(); x.arc(c * 64 + (r % 2) * 32 + 16, r * 64 + 32, 10, 0, 7); x.fill(); } }
  };
}
function drawFloor(kind, col) {
  return (x, w, h) => {
    x.fillStyle = col; x.fillRect(0, 0, w, h);
    const dk = shade(col, 0.72), lt = shade(col, 1.18);
    if (kind.startsWith('madera') || kind === 'deck') { for (let i = 0; i < 8; i++) { x.fillStyle = i % 2 ? dk : lt; x.globalAlpha = .18; x.fillRect(0, i * 64, w, 62); x.globalAlpha = 1; x.strokeStyle = shade(col, .5); x.lineWidth = 3; x.beginPath(); x.moveTo(0, i * 64); x.lineTo(w, i * 64); x.stroke(); for (let c = 0; c < 3; c++) { const xx = ((i * 97 + c * 180) % w); x.beginPath(); x.moveTo(xx, i * 64); x.lineTo(xx, i * 64 + 64); x.stroke(); } } }
    if (kind === 'baldosa') { x.strokeStyle = shade(col, .8); x.lineWidth = 4; for (let i = 0; i <= 4; i++) { x.beginPath(); x.moveTo(i * 128, 0); x.lineTo(i * 128, h); x.stroke(); x.beginPath(); x.moveTo(0, i * 128); x.lineTo(w, i * 128); x.stroke(); } }
    if (kind === 'ajedrez') { for (let r = 0; r < 4; r++) for (let c = 0; c < 4; c++) { x.fillStyle = (r + c) % 2 ? col : '#f2f2f2'; x.fillRect(c * 128, r * 128, 128, 128); } }
    if (kind === 'concreto' || kind === 'epoxico') { for (let i = 0; i < 700; i++) { x.fillStyle = Math.random() < .5 ? dk : lt; x.globalAlpha = kind === 'epoxico' ? .06 : .12; x.fillRect(Math.random() * w, Math.random() * h, 5, 5); } x.globalAlpha = 1; }
    if (kind === 'alfombra') { for (let i = 0; i < 2500; i++) { x.fillStyle = Math.random() < .5 ? dk : lt; x.globalAlpha = .15; x.fillRect(Math.random() * w, Math.random() * h, 2, 2); } x.globalAlpha = 1; }
    if (kind === 'cesped') { for (let i = 0; i < 2500; i++) { x.strokeStyle = Math.random() < .5 ? dk : lt; x.globalAlpha = .4; const a = Math.random() * w, b = Math.random() * h; x.beginPath(); x.moveTo(a, b); x.lineTo(a + 1, b - 6); x.stroke(); } x.globalAlpha = 1; }
  };
}
export function wallMaterial(kind, color, len, hgt) {
  const col = color || WALLS[kind]?.def || '#e7e2f0';
  if (kind === 'vidrio') return Style.toon() ? new THREE.MeshToonMaterial({ color: col, gradientMap: gradientMap(), transparent: true, opacity: .35 }) : new THREE.MeshPhysicalMaterial({ color: col, transparent: true, opacity: .28, roughness: .05, metalness: .1 });
  const tex = kind === 'pintura' ? null : canvasTex('w-' + kind + col, 512, 512, drawWall(kind, col), [Math.max(1, len / 3), Math.max(1, hgt / 3)]);
  const m = mat(kind === 'pintura' ? col : '#ffffff', { map: tex, roughness: kind === 'panel' ? .15 : .85, metalness: kind === 'panel' ? .4 : 0 });
  return m;
}
export function floorMaterial(kind, color, w, d) {
  const col = color || FLOORS[kind]?.def || '#888';
  const tex = canvasTex('f-' + kind + col, 512, 512, drawFloor(kind, col), [w / 2.5, d / 2.5]);
  return mat('#ffffff', { map: tex, roughness: (kind === 'negro' || kind === 'epoxico' || kind === 'baldosa') ? .2 : .7 });
}
// textura de texto (neón, pantallas)
export function textTex(key, w, h, draw) { return canvasTex(key, w, h, draw); }

export function toast(msg, kind = 'ok') {
  let el = document.getElementById('toast');
  if (!el) { el = document.createElement('div'); el.id = 'toast'; document.body.appendChild(el); }
  el.textContent = msg; el.className = 'show ' + kind; clearTimeout(el._t); el._t = setTimeout(() => el.className = '', 2600);
}
export const uid = () => Math.random().toString(36).slice(2, 9);
