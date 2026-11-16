// Catálogo del constructor: objetos de negocio hechos por código (sirven en Humano y Caricatura).
// En Clonexa, además de estos, entran los modelos 3D aprobados en la Biblioteca.
import { THREE, mat, glow, mesh, textTex } from './core.js';
import { RoundedBoxGeometry as RB } from 'three/addons/geometries/RoundedBoxGeometry.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { MeshoptDecoder } from 'three/addons/libs/meshopt_decoder.module.js';

const box = (w, h, d) => new THREE.BoxGeometry(w, h, d);
const rb = (w, h, d, r = .03) => new RB(w, h, d, 2, r);
const cyl = (rt, rb_, h, s = 20) => new THREE.CylinderGeometry(rt, rb_, h, s);
const sph = (r) => new THREE.SphereGeometry(r, 14, 10);

export const CATS = [
  ['barra', '🍸 Barra'], ['neveras', '🧊 Neveras'], ['mesas', '🪑 Mesas y sillas'], ['pantallas', '📺 Pantallas'], ['sonido', '🔊 Sonido'],
  ['luces', '💡 Luces'], ['cocina', '🍳 Cocina'], ['caja', '💵 Caja'], ['deco', '🪴 Decoración'], ['taller', '🧵 Taller'],
  ['oficina', '💻 Oficina'], ['bodega', '📦 Bodega'], ['banos', '🚻 Baños'],
];
export const CONN = { mesa: 'Mesa con QR', puesto: 'Puesto / máquina', escritorio: 'Escritorio / agente', caja: 'Caja', pantalla: 'Pantalla viva', inventario: 'Inventario', sonido: 'Canciones pedidas' };
export const SCREENS = ['Logo de la empresa', 'Canciones pedidas', 'Comandas en cocina', 'Domicilios', 'Tablero de producción', 'Partido / TV'];

function chair(g, c, x = 0, z = 0, ry = 0) { const q = new THREE.Group(); q.position.set(x, 0, z); q.rotation.y = ry; g.add(q); mesh(rb(.42, .06, .42, .02), mat(c), 0, .46, 0, q); mesh(rb(.42, .5, .06, .02), mat(c), 0, .74, -.19, q); [[-.17, -.17], [.17, -.17], [-.17, .17], [.17, .17]].forEach(([a, b]) => mesh(cyl(.018, .018, .44, 6), mat('#222'), a, .22, b, q)); return q; }
function screenTex(kind, color) {
  return textTex('scr-' + kind + color, 512, 288, (x, w, h) => {
    const g = x.createLinearGradient(0, 0, w, h); g.addColorStop(0, '#14081f'); g.addColorStop(1, '#26071a'); x.fillStyle = g; x.fillRect(0, 0, w, h);
    x.fillStyle = '#fff'; x.font = '800 30px Arial';
    if (kind === 'Partido / TV') { const q = x.createLinearGradient(0, 0, w, h); q.addColorStop(0, '#14532d'); q.addColorStop(1, '#16a34a'); x.fillStyle = q; x.fillRect(0, 0, w, h); x.strokeStyle = '#fff'; x.lineWidth = 4; x.strokeRect(24, 24, w - 48, h - 48); x.beginPath(); x.moveTo(w / 2, 24); x.lineTo(w / 2, h - 24); x.stroke(); x.beginPath(); x.arc(w / 2, h / 2, 40, 0, 7); x.stroke(); return; }
    if (kind === 'Logo de la empresa') { x.font = 'italic 800 64px Georgia'; x.textAlign = 'center'; x.fillStyle = color || '#f20b6d'; x.fillText('Tu marca', w / 2, h / 2 + 20); return; }
    x.fillText(kind, 24, 46); x.fillStyle = color || '#f20b6d'; x.fillRect(24, 60, w - 48, 4);
    for (let i = 0; i < 4; i++) { x.fillStyle = 'rgba(255,255,255,.08)'; x.fillRect(24, 80 + i * 48, w - 48, 40); x.fillStyle = ['#22c55e', '#f59e0b', '#38bdf8', '#a855f7'][i]; x.fillRect(24, 80 + i * 48, 6, 40); x.fillStyle = '#ddd'; x.font = '600 20px Arial'; x.fillText(['Mesa 4 · 2 ítems', 'Mesa 7 · 1 ítem', 'Barra · 3 ítems', 'Mesa 2 · 4 ítems'][i], 42, 106 + i * 48); }
  });
}
function neonTex(text, color) {
  return textTex('neon-' + text + color, 768, 256, (x, w, h) => { x.clearRect(0, 0, w, h); x.font = 'italic 700 110px Georgia'; x.textAlign = 'center'; x.shadowColor = color; x.shadowBlur = 30; x.fillStyle = '#ffe4f1'; x.fillText(text || 'Tu texto', w / 2, h / 2 + 38); x.shadowBlur = 0; x.lineWidth = 3; x.strokeStyle = color; x.strokeText(text || 'Tu texto', w / 2, h / 2 + 38); });
}

const I = [];
const add = (id, name, cat, w, d, colors, build, extra = {}) => I.push({ id, name, cat, w, d, colors, build, ...extra });

// ---------------- BARRA
add('barra_recta', 'Barra recta', 'barra', 2.4, .75, ['#1a1418', '#5b3a26', '#f20b6d'], (g, o) => { mesh(rb(2.4, 1.05, .7, .05), mat(o.color), 0, .53, 0, g); mesh(box(2.5, .06, .78), mat(o.color2), 0, 1.08, 0, g); mesh(box(2.4, .05, .05), glow(o.color3, 3), 0, .1, .37, g, false); });
add('barra_l', 'Barra en L', 'barra', 2.6, 2.6, ['#1a1418', '#5b3a26', '#f20b6d'], (g, o) => { mesh(rb(2.6, 1.05, .7, .05), mat(o.color), 0, .53, -.95, g); mesh(rb(.7, 1.05, 2.6, .05), mat(o.color), -.95, .53, 0, g); mesh(box(2.7, .06, .78), mat(o.color2), 0, 1.08, -.95, g); mesh(box(.78, .06, 2.7), mat(o.color2), -.95, 1.08, 0, g); mesh(box(2.6, .05, .05), glow(o.color3, 3), 0, .1, -.58, g, false); });
add('isla', 'Isla de barra', 'barra', 2.2, 1.2, ['#1a1418', '#c8a27a'], (g, o) => { mesh(rb(2.2, 1.0, 1.1, .06), mat(o.color), 0, .5, 0, g); mesh(rb(2.4, .06, 1.3, .03), mat(o.color2), 0, 1.03, 0, g); });
add('contrabarra', 'Contrabarra con botellas', 'barra', 2.4, .4, ['#241a22', '#7c3aed'], (g, o) => { mesh(box(2.4, 2.2, .35), mat(o.color), 0, 1.1, 0, g); for (let s = 0; s < 3; s++) { mesh(box(2.3, .03, .3), glow(o.color2, 1.2), 0, .78 + s * .55, .02, g, false); for (let i = 0; i < 10; i++) mesh(cyl(.035, .045, .26, 8), mat(['#15803d', '#b45309', '#7c2d12', '#e5e7eb', '#1d4ed8'][(i + s) % 5], { roughness: .1 }), -1.05 + i * .23, .93 + s * .55, .06, g); } }, { h: 2.2 });
add('taburete', 'Taburete', 'barra', .45, .45, ['#9a5b36', '#222222'], (g, o) => { mesh(cyl(.2, .2, .06), mat(o.color), 0, .78, 0, g); mesh(cyl(.03, .03, .75, 8), mat(o.color2), 0, .4, 0, g); mesh(new THREE.TorusGeometry(.16, .015, 8, 20), mat(o.color2), 0, .3, 0, g).rotation.x = Math.PI / 2; mesh(cyl(.18, .18, .03), mat(o.color2), 0, .015, 0, g); });
add('taburete_alto', 'Taburete con espaldar', 'barra', .5, .5, ['#3b2d4f', '#222222'], (g, o) => { mesh(rb(.42, .07, .42), mat(o.color), 0, .8, 0, g); mesh(rb(.42, .4, .05), mat(o.color), 0, 1.02, -.19, g); [[-.15, -.15], [.15, -.15], [-.15, .15], [.15, .15]].forEach(([a, b]) => mesh(cyl(.02, .02, .78, 6), mat(o.color2), a, .39, b, g)); });
// ---------------- NEVERAS
function fridge(g, o, w = .9, doors = 1) { mesh(rb(w, 2, .7, .04), mat(o.color, { metalness: .3, roughness: .35 }), 0, 1, 0, g); for (let d = 0; d < doors; d++) { const dx = doors === 1 ? 0 : (d - .5) * w / 2; const gl = mesh(new THREE.PlaneGeometry(w / doors - .12, 1.75), new THREE.MeshStandardMaterial({ color: 0x9bd8ff, emissive: 0x2a6a9a, emissiveIntensity: .25, transparent: true, opacity: .55 }), dx, 1.02, .36, g, false); gl.castShadow = false; } const P = { 'Gaseosas': ['#dc2626', '#16a34a', '#facc15', '#f97316'], 'Cervezas': ['#b45309', '#facc15', '#7c2d12', '#16a34a'], 'Agua': ['#93c5fd', '#e0f2fe', '#60a5fa', '#bfdbfe'], 'Variado': ['#dc2626', '#facc15', '#16a34a', '#2563eb'] }[o.products || 'Variado']; const n = Math.round(w / .11) - 2; for (let s = 0; s < 4; s++) for (let i = 0; i < n; i++) mesh(cyl(.035, .035, .22, 8), mat(P[s]), -w / 2 + .15 + i * .11, .38 + s * .42, .18, g, false); }
add('nevera_bebidas', 'Nevera de bebidas', 'neveras', .9, .7, ['#9ca3af'], (g, o) => fridge(g, o), { conn: 'inventario', props: ['products'], h: 2 });
add('nevera_doble', 'Nevera de bebidas doble', 'neveras', 1.5, .7, ['#111111'], (g, o) => fridge(g, o, 1.5, 2), { conn: 'inventario', props: ['products'], h: 2 });
add('nevera_industrial', 'Nevera industrial', 'neveras', 1.3, .75, ['#c0c4cc'], (g, o) => { mesh(rb(1.3, 2.05, .75, .04), mat(o.color, { metalness: .6, roughness: .3 }), 0, 1.02, 0, g); [-.33, .33].forEach(x => { mesh(box(.6, 1.9, .02), mat('#d1d5db', { metalness: .6, roughness: .25 }), x, 1.02, .38, g); mesh(box(.03, .5, .04), mat('#555'), x + (x < 0 ? .25 : -.25), 1.1, .41, g); }); }, { h: 2 });
add('congelador', 'Congelador horizontal', 'neveras', 1.4, .7, ['#f1f5f9'], (g, o) => { mesh(rb(1.4, .85, .7, .04), mat(o.color), 0, .43, 0, g); mesh(box(1.32, .03, .62), new THREE.MeshStandardMaterial({ color: 0x9bd8ff, transparent: true, opacity: .5 }), 0, .87, 0, g, false); });
// ---------------- MESAS Y SILLAS
add('mesa_redonda', 'Mesa redonda · 4 sillas', 'mesas', 2, 2, ['#7c4a2d', '#3b2d4f'], (g, o) => { mesh(cyl(.55, .55, .05, 28), mat(o.color), 0, .75, 0, g); mesh(cyl(.05, .05, .72, 8), mat('#222'), 0, .37, 0, g); mesh(cyl(.25, .25, .03), mat('#222'), 0, .015, 0, g); for (let a = 0; a < 4; a++) { const cx = Math.cos(a * Math.PI / 2 + .78) * .85, cz = Math.sin(a * Math.PI / 2 + .78) * .85; chair(g, o.color2, cx, cz, Math.atan2(-cx, -cz)); } }, { conn: 'mesa' });
add('mesa_cuadrada', 'Mesa cuadrada · 4 sillas', 'mesas', 1.9, 1.9, ['#c8a27a', '#111111'], (g, o) => { mesh(rb(1, .05, 1), mat(o.color), 0, .75, 0, g); [[-.42, -.42], [.42, -.42], [-.42, .42], [.42, .42]].forEach(([a, b]) => mesh(box(.05, .72, .05), mat('#222'), a, .37, b, g)); [[0, -.8, 0], [0, .8, Math.PI], [-.8, 0, Math.PI / 2], [.8, 0, -Math.PI / 2]].forEach(([a, b, r]) => chair(g, o.color2, a, b, r)); }, { conn: 'mesa' });
add('mesa_2', 'Mesa para 2', 'mesas', .8, 1.6, ['#7c4a2d', '#3b2d4f'], (g, o) => { mesh(rb(.7, .05, .7), mat(o.color), 0, .75, 0, g); mesh(cyl(.04, .04, .72, 8), mat('#222'), 0, .37, 0, g); chair(g, o.color2, 0, -.6, 0); chair(g, o.color2, 0, .6, Math.PI); }, { conn: 'mesa' });
add('mesa_larga', 'Mesa larga · 6 sillas', 'mesas', 2.4, 1.9, ['#5b3a26', '#111111'], (g, o) => { mesh(rb(2.1, .06, .9), mat(o.color), 0, .75, 0, g); [[-1, -.4], [1, -.4], [-1, .4], [1, .4]].forEach(([a, b]) => mesh(box(.06, .72, .06), mat('#222'), a, .37, b, g)); [-.7, 0, .7].forEach(x => { chair(g, o.color2, x, -.75, 0); chair(g, o.color2, x, .75, Math.PI); }); }, { conn: 'mesa' });
add('mesa_alta', 'Mesa alta', 'mesas', .8, .8, ['#111111', '#555555'], (g, o) => { mesh(cyl(.35, .35, .04, 24), mat(o.color), 0, 1.05, 0, g); mesh(cyl(.04, .04, 1.05, 8), mat(o.color2), 0, .52, 0, g); mesh(cyl(.25, .25, .03), mat(o.color2), 0, .015, 0, g); }, { conn: 'mesa' });
add('silla', 'Silla', 'mesas', .5, .5, ['#3b2d4f'], (g, o) => chair(g, o.color));
add('butaca', 'Mesa con butacas', 'mesas', 1.6, 2.2, ['#7f1d1d', '#5b3a26'], (g, o) => { [-1, 1].forEach(s => { mesh(rb(1.4, .45, .55, .08), mat(o.color), 0, .23, s * .8, g); mesh(rb(1.4, .7, .15, .06), mat(o.color), 0, .75, s * 1.0, g); }); mesh(rb(1.2, .05, .8), mat(o.color2), 0, .75, 0, g); mesh(box(.08, .72, .08), mat('#222'), 0, .37, 0, g); }, { conn: 'mesa' });
add('sofa', 'Sofá lounge', 'mesas', 2.2, .95, ['#6d28d9'], (g, o) => { const c2 = new THREE.Color(o.color).multiplyScalar(.85); mesh(rb(2, .45, .9, .12), mat(o.color), 0, .3, 0, g); mesh(rb(2, .6, .25, .1), mat(c2), 0, .7, -.35, g); [-1, 1].forEach(s => mesh(rb(.2, .55, .9, .08), mat(c2), s * 1.0, .4, 0, g)); });
add('mesa_centro', 'Mesa de centro', 'mesas', 1, .6, ['#3a3346'], (g, o) => { mesh(rb(1, .06, .55), mat(o.color), 0, .42, 0, g); mesh(rb(.9, .38, .45), mat('#222'), 0, .2, 0, g); });
add('puff', 'Puff', 'mesas', .5, .5, ['#f20b6d'], (g, o) => mesh(new RB(.5, .42, .5, 3, .15), mat(o.color), 0, .21, 0, g));
// ---------------- PANTALLAS
add('tv_pared', 'TV de pared', 'pantallas', 1.8, .2, ['#0b0b0b'], (g, o) => { mesh(box(1.8, 1.05, .08), mat(o.color), 0, 1.9, 0, g); mesh(new THREE.PlaneGeometry(1.7, .95), new THREE.MeshBasicMaterial({ map: screenTex(o.screen || 'Partido / TV', o.color2), toneMapped: false }), 0, 1.9, .045, g, false); }, { conn: 'pantalla', props: ['screen'], wall: true, colors2: ['#f20b6d'] });
add('tv_pedestal', 'TV con pedestal', 'pantallas', 1, .6, ['#0b0b0b'], (g, o) => { mesh(box(1.4, .82, .07), mat(o.color), 0, 1.45, 0, g); mesh(new THREE.PlaneGeometry(1.32, .74), new THREE.MeshBasicMaterial({ map: screenTex(o.screen || 'Canciones pedidas', '#f20b6d'), toneMapped: false }), 0, 1.45, .04, g, false); mesh(cyl(.04, .04, 1.05, 8), mat('#333'), 0, .53, 0, g); mesh(cyl(.32, .32, .04), mat('#222'), 0, .02, 0, g); }, { conn: 'pantalla', props: ['screen'] });
add('tablero', 'Tablero grande', 'pantallas', 3.2, .2, ['#050505'], (g, o) => { mesh(box(3.2, 1.6, .1), mat(o.color), 0, 2.0, 0, g); mesh(new THREE.PlaneGeometry(3.05, 1.45), new THREE.MeshBasicMaterial({ map: screenTex(o.screen || 'Tablero de producción', '#a855f7'), toneMapped: false }), 0, 2.0, .055, g, false); }, { conn: 'pantalla', props: ['screen'], wall: true });
// ---------------- SONIDO
add('cabina_dj', 'Cabina DJ', 'sonido', 1.8, .75, ['#1e1b2e', '#a855f7'], (g, o) => { mesh(rb(1.8, 1, .7, .05), mat(o.color), 0, .5, 0, g); mesh(box(1.8, .04, .04), glow(o.color2, 3), 0, 1.0, .36, g, false); [-.5, .5].forEach(x => mesh(cyl(.18, .18, .04, 24), mat('#333'), x, 1.03, 0, g)); mesh(box(.5, .05, .3), mat('#111'), 0, 1.03, 0, g); }, { conn: 'sonido' });
add('parlante', 'Parlante', 'sonido', .6, .55, ['#111111'], (g, o) => { mesh(rb(.6, 1.6, .55, .04), mat(o.color), 0, .8, 0, g); [[1.15, .12], [.55, .2]].forEach(([y, r]) => { const c = mesh(cyl(r, r, .04, 24), mat('#3a3a3a'), 0, y, .28, g); c.rotation.x = Math.PI / 2; }); });
add('pista_led', 'Pista LED', 'sonido', 3, 2.4, ['#f20b6d', '#a855f7', '#22d3ee'], (g, o) => { const cs = [o.color, o.color2, o.color3]; for (let i = 0; i < 4; i++) for (let j = 0; j < 3; j++) { const t = mesh(new THREE.PlaneGeometry(.72, .76), glow(cs[(i + j) % 3], 1.2), -1.125 + i * .75, .006, -.8 + j * .8, g, false); t.rotation.x = -Math.PI / 2; t.castShadow = false; } }, { flat: true });
// ---------------- LUCES
add('lampara', 'Lámpara colgante', 'luces', .6, .6, ['#111111', '#ffd28a'], (g, o) => { mesh(cyl(.008, .008, 1.1, 6), mat('#222'), 0, 2.95, 0, g, false); mesh(new THREE.ConeGeometry(.3, .28, 20, 1, true), mat(o.color), 0, 2.35, 0, g); mesh(sph(.09), glow(o.color2, 4), 0, 2.25, 0, g, false); }, { light: true, hang: true });
add('foco', 'Lámpara de pie', 'luces', .5, .5, ['#e5e7eb', '#ffd28a'], (g, o) => { mesh(cyl(.02, .02, 1.6, 6), mat('#222'), 0, .8, 0, g); mesh(cyl(.18, .22, .03), mat('#222'), 0, .02, 0, g); mesh(new THREE.ConeGeometry(.22, .3, 20, 1, true), mat(o.color), 0, 1.7, 0, g); mesh(sph(.07), glow(o.color2, 3), 0, 1.62, 0, g, false); }, { light: true });
add('tira_led', 'Tira LED', 'luces', 2.4, .1, ['#a855f7'], (g, o) => mesh(box(2.4, .04, .04), glow(o.color, 3), 0, .08, 0, g, false), { flat: true });
add('neon', 'Letrero neón', 'luces', 2, .2, ['#ff2d95'], (g, o) => { mesh(box(2, .85, .05), mat('#120a10'), 0, 2.2, 0, g); mesh(new THREE.PlaneGeometry(1.9, .75), new THREE.MeshBasicMaterial({ map: neonTex(o.text, o.color), transparent: true, toneMapped: false }), 0, 2.2, .03, g, false); }, { props: ['text'], wall: true, light: false });
// ---------------- COCINA
add('estufa', 'Estufa', 'cocina', 1, .7, ['#c0c4cc'], (g, o) => { mesh(rb(1, .9, .7), mat(o.color, { metalness: .6, roughness: .3 }), 0, .45, 0, g); for (let i = 0; i < 4; i++) mesh(cyl(.12, .12, .03), mat('#111'), (i % 2 - .5) * .45, .92, (Math.floor(i / 2) - .5) * .32, g); mesh(box(.8, .4, .02), mat('#222'), 0, .45, .36, g); }, { conn: 'puesto' });
add('parrilla', 'Parrilla', 'cocina', 1.2, .8, ['#1f1f24', '#f97316'], (g, o) => { mesh(rb(1.2, .85, .8), mat(o.color), 0, .43, 0, g); for (let i = 0; i < 8; i++) mesh(box(1.05, .02, .02), mat('#555'), 0, .88, -.3 + i * .085, g); mesh(box(1.0, .02, .6), glow(o.color2, 1.5), 0, .86, 0, g, false); }, { conn: 'puesto' });
add('freidora', 'Freidora', 'cocina', .6, .7, ['#c0c4cc'], (g, o) => { mesh(rb(.6, .9, .7), mat(o.color, { metalness: .6, roughness: .3 }), 0, .45, 0, g); [-.13, .13].forEach(x => mesh(box(.2, .05, .4), mat('#facc15'), x, .92, 0, g)); });
add('horno', 'Horno', 'cocina', .9, .75, ['#2b2b30'], (g, o) => { mesh(rb(.9, 1.5, .75), mat(o.color, { metalness: .5 }), 0, .75, 0, g); mesh(box(.7, .5, .02), new THREE.MeshStandardMaterial({ color: 0x111, emissive: 0xf97316, emissiveIntensity: .3 }), 0, .9, .38, g, false); });
add('campana', 'Campana extractora', 'cocina', 1.4, .8, ['#c0c4cc'], (g, o) => { mesh(new THREE.CylinderGeometry(.25, .9, .5, 4, 1), mat(o.color, { metalness: .6 }), 0, 2.4, 0, g).rotation.y = Math.PI / 4; mesh(box(.4, .7, .4), mat(o.color, { metalness: .6 }), 0, 3.0, 0, g); }, { wall: true });
add('meson', 'Mesón', 'cocina', 1.6, .7, ['#c0c4cc', '#e5e7eb'], (g, o) => { mesh(rb(1.6, .88, .7), mat(o.color, { metalness: .5 }), 0, .44, 0, g); mesh(box(1.65, .04, .75), mat(o.color2), 0, .9, 0, g); });
add('lavaplatos', 'Lavaplatos', 'cocina', 1.2, .7, ['#c0c4cc'], (g, o) => { mesh(rb(1.2, .88, .7), mat(o.color, { metalness: .5 }), 0, .44, 0, g); mesh(box(.5, .05, .4), mat('#222'), -.2, .89, 0, g); mesh(cyl(.02, .02, .35, 6), mat('#ddd'), .2, 1.05, -.2, g); });
add('pase', 'Pase de platos', 'cocina', 1.8, .5, ['#9ca3af'], (g, o) => { mesh(box(1.8, .05, .5), mat(o.color, { metalness: .5 }), 0, 1.2, 0, g); [-.85, .85].forEach(x => mesh(box(.05, 1.2, .5), mat(o.color), x, .6, 0, g)); mesh(box(1.7, .03, .4), glow('#f59e0b', .8), 0, 1.55, 0, g, false); for (let i = 0; i < 3; i++) mesh(cyl(.13, .1, .03), mat('#fff'), -.5 + i * .5, 1.24, 0, g); });
// ---------------- CAJA
add('caja', 'Caja registradora', 'caja', 1.2, .6, ['#2a2433', '#22c55e'], (g, o) => { mesh(rb(1.2, .95, .55), mat(o.color), 0, .48, 0, g); mesh(rb(.45, .28, .32), mat('#111'), -.2, 1.1, 0, g); mesh(new THREE.PlaneGeometry(.32, .18), glow(o.color2, 1), -.2, 1.27, -.05, g, false).rotation.x = -.4; mesh(rb(.12, .05, .2), mat('#333'), .35, .99, 0, g); }, { conn: 'caja' });
add('mostrador', 'Mostrador', 'caja', 2, .7, ['#111111', '#c8a27a'], (g, o) => { mesh(rb(2, 1.05, .65, .05), mat(o.color), 0, .53, 0, g); mesh(box(2.05, .05, .7), mat(o.color2), 0, 1.07, 0, g); });
// ---------------- DECORACIÓN
add('planta', 'Planta', 'deco', .6, .6, ['#2f7a46', '#d1d5db'], (g, o) => { mesh(cyl(.28, .22, .5, 16), mat(o.color2), 0, .25, 0, g); for (let i = 0; i < 8; i++) { const l = mesh(sph(.18 + ((i * 37) % 10) / 100), mat(o.color), ((i * 13) % 7 - 3) * .06, .75 + ((i * 29) % 10) / 20, ((i * 17) % 7 - 3) * .06, g); l.scale.y = 1.4; } });
add('planta_alta', 'Planta alta', 'deco', .6, .6, ['#3f9a5a', '#111111'], (g, o) => { mesh(cyl(.25, .2, .55, 16), mat(o.color2), 0, .27, 0, g); mesh(cyl(.03, .04, 1.3, 6), mat('#5b3a26'), 0, 1.1, 0, g); for (let i = 0; i < 10; i++) { const l = mesh(sph(.16), mat(o.color), Math.cos(i) * .3, 1.4 + (i % 4) * .18, Math.sin(i) * .3, g); l.scale.set(1.4, .6, .8); } });
add('cuadro', 'Cuadro', 'deco', 1, .1, ['#f472b6', '#111111'], (g, o) => { mesh(box(1, .7, .04), mat(o.color2), 0, 1.7, 0, g); mesh(new THREE.PlaneGeometry(.88, .58), mat(o.color), 0, 1.7, .025, g); }, { wall: true });
add('tapete', 'Tapete', 'deco', 2.4, 1.6, ['#7c3aed'], (g, o) => { const t = mesh(new THREE.PlaneGeometry(2.4, 1.6), mat(o.color), 0, .006, 0, g, false); t.rotation.x = -Math.PI / 2; t.castShadow = false; }, { flat: true });
add('reloj', 'Reloj de pared', 'deco', .5, .1, ['#ffffff', '#111111'], (g, o) => { const c = mesh(cyl(.25, .25, .05, 28), mat(o.color), 0, 2.2, 0, g); c.rotation.x = Math.PI / 2; mesh(box(.02, .16, .01), mat(o.color2), 0, 2.26, .03, g); mesh(box(.12, .02, .01), mat(o.color2), .05, 2.2, .03, g); }, { wall: true });
add('espejo', 'Espejo', 'deco', .8, .1, ['#c0c4cc'], (g, o) => { mesh(box(.8, 1.4, .04), mat(o.color), 0, 1.4, 0, g); mesh(new THREE.PlaneGeometry(.7, 1.3), new THREE.MeshStandardMaterial({ color: 0xdbeafe, metalness: 1, roughness: .05 }), 0, 1.4, .025, g, false); }, { wall: true });
add('jardinera', 'Jardinera', 'deco', 1.6, .5, ['#3f8f3f', '#5b3a26'], (g, o) => { mesh(rb(1.6, .5, .45), mat(o.color2), 0, .25, 0, g); for (let i = 0; i < 7; i++) mesh(sph(.18), mat(o.color), -.6 + i * .2, .55, 0, g); });
// ---------------- TALLER
add('maquina_plana', 'Máquina de coser plana', 'taller', 1.2, 1.3, ['#f5f5f5', '#d6c3a5'], (g, o) => { mesh(rb(1.1, .05, .6), mat(o.color2), 0, .75, 0, g); [-.5, .5].forEach(x => mesh(box(.04, .73, .55), mat('#333'), x, .37, 0, g)); mesh(rb(.5, .25, .18, .04), mat(o.color), 0, .9, 0, g); mesh(rb(.12, .3, .16, .04), mat(o.color), .2, 1.0, 0, g); mesh(rb(.4, .08, .16, .03), mat(o.color), 0, 1.12, 0, g); chair(g, '#3b2d4f', 0, .7, Math.PI); }, { conn: 'puesto' });
add('fileteadora', 'Fileteadora', 'taller', 1.1, 1.3, ['#e5e7eb', '#c8a27a'], (g, o) => { mesh(rb(1, .05, .6), mat(o.color2), 0, .75, 0, g); [-.45, .45].forEach(x => mesh(box(.04, .73, .55), mat('#333'), x, .37, 0, g)); mesh(rb(.35, .32, .3, .05), mat(o.color), 0, .93, 0, g); chair(g, '#3b2d4f', 0, .7, Math.PI); }, { conn: 'puesto' });
add('mesa_corte', 'Mesa de corte', 'taller', 2.6, 1.3, ['#e9dcc5', '#4b5563'], (g, o) => { mesh(rb(2.6, .06, 1.2), mat(o.color), 0, .9, 0, g); [[-1.2, -.5], [1.2, -.5], [-1.2, .5], [1.2, .5]].forEach(([a, b]) => mesh(box(.06, .88, .06), mat(o.color2), a, .45, b, g)); mesh(cyl(.08, .08, 1.0, 12), mat('#f472b6'), .4, 1.0, 0, g).rotation.z = Math.PI / 2; }, { conn: 'puesto' });
add('rollos', 'Rollos de tela', 'taller', 1.2, .6, ['#f472b6', '#38bdf8', '#facc15'], (g, o) => { const cs = [o.color, o.color2, o.color3, '#a855f7', '#22c55e']; for (let i = 0; i < 5; i++) { const r = mesh(cyl(.12, .12, 1.0, 14), mat(cs[i]), -.48 + i * .24, .5, 0, g); } });
add('perchero', 'Perchero', 'taller', 1.4, .5, ['#9ca3af', '#f472b6'], (g, o) => { [-.65, .65].forEach(x => mesh(cyl(.02, .02, 1.6, 6), mat(o.color), x, .8, 0, g)); mesh(cyl(.02, .02, 1.3, 6), mat(o.color), 0, 1.6, 0, g).rotation.z = Math.PI / 2; for (let i = 0; i < 6; i++) mesh(box(.04, .7, .4), mat([o.color2, '#7c3aed', '#fff', '#111'][i % 4]), -.5 + i * .2, 1.2, 0, g); });
add('maniqui', 'Maniquí', 'taller', .5, .5, ['#e5e1da'], (g, o) => { mesh(cyl(.04, .04, 1.0, 8), mat('#333'), 0, .5, 0, g); mesh(cyl(.2, .18, .03), mat('#333'), 0, .02, 0, g); mesh(new THREE.CapsuleGeometry(.17, .45, 8, 16), mat(o.color), 0, 1.3, 0, g); });
add('estante_lotes', 'Estantería de lotes', 'taller', 1.8, .5, ['#4b5563', '#c8a27a'], (g, o) => { [-.85, .85].forEach(x => mesh(box(.05, 2, .45), mat(o.color), x, 1, 0, g)); for (let s = 0; s < 4; s++) { mesh(box(1.75, .03, .45), mat(o.color), 0, .3 + s * .5, 0, g); for (let i = 0; i < 3; i++) mesh(rb(.45, .3, .35), mat(o.color2), -.55 + i * .55, .47 + s * .5, 0, g); } }, { h: 2 });
// ---------------- OFICINA
add('escritorio', 'Escritorio con computador', 'oficina', 1.4, 1.4, ['#e5e3ea', '#1f1d29'], (g, o) => { mesh(rb(1.4, .05, .7), mat(o.color), 0, .74, 0, g); [-.66, .66].forEach(x => mesh(box(.05, .72, .65), mat('#222'), x, .36, 0, g)); mesh(box(.6, .36, .03), mat('#111'), 0, 1.02, -.15, g); mesh(new THREE.PlaneGeometry(.56, .32), glow('#38bdf8', .8), 0, 1.02, -.133, g, false); mesh(box(.4, .02, .14), mat('#222'), 0, .77, .1, g); const c = new THREE.Group(); c.position.set(0, 0, .62); g.add(c); mesh(rb(.48, .07, .46), mat(o.color2), 0, .48, 0, c); mesh(rb(.46, .6, .07), mat(o.color2), 0, .8, .2, c); mesh(cyl(.03, .03, .4, 8), mat('#222'), 0, .25, 0, c); }, { conn: 'escritorio' });
add('silla_ergo', 'Silla ergonómica', 'oficina', .6, .6, ['#1f1d29'], (g, o) => { mesh(rb(.5, .08, .48), mat(o.color), 0, .48, 0, g); mesh(rb(.48, .65, .08), mat(o.color), 0, .85, -.2, g); mesh(cyl(.03, .03, .4, 8), mat('#222'), 0, .25, 0, g); mesh(cyl(.28, .3, .03), mat('#222'), 0, .03, 0, g); });
add('division', 'División de escritorio', 'oficina', 1.5, .1, ['#7c3aed'], (g, o) => mesh(box(1.5, .5, .04), mat(o.color, { transparent: true, opacity: .6 }), 0, 1.0, 0, g, false));
add('mesa_juntas', 'Mesa de juntas', 'oficina', 3.2, 2, ['#121016', '#e5e3ea'], (g, o) => { mesh(new RB(2.8, .06, 1.2, 3, .3), mat(o.color, { roughness: .15 }), 0, .75, 0, g); mesh(box(.3, .72, .6), mat('#222'), 0, .37, 0, g); [-1, 0, 1].forEach(x => { chair(g, o.color2, x, -.85, 0); chair(g, o.color2, x, .85, Math.PI); }); });
add('archivador', 'Archivador', 'oficina', .5, .6, ['#9ca3af'], (g, o) => { mesh(rb(.5, 1.3, .6), mat(o.color, { metalness: .4 }), 0, .65, 0, g); for (let i = 0; i < 4; i++) mesh(box(.15, .03, .02), mat('#333'), 0, .3 + i * .3, .31, g); });
// ---------------- BODEGA
add('rack', 'Rack metálico', 'bodega', 2, .8, ['#2563eb', '#f97316'], (g, o) => { [[-.95, -.35], [.95, -.35], [-.95, .35], [.95, .35]].forEach(([a, b]) => mesh(box(.06, 2.4, .06), mat(o.color), a, 1.2, b, g)); for (let s = 0; s < 3; s++) { mesh(box(2, .06, .8), mat(o.color2), 0, .4 + s * .8, 0, g); for (let i = 0; i < 3; i++) mesh(rb(.5, .4, .55), mat('#c8a27a'), -.6 + i * .6, .64 + s * .8, 0, g); } }, { h: 2.4 });
add('estiba', 'Estiba con cajas', 'bodega', 1.2, 1, ['#c8a27a', '#8b5a3c'], (g, o) => { mesh(box(1.2, .14, 1), mat(o.color2), 0, .07, 0, g); for (let i = 0; i < 6; i++) mesh(rb(.55, .4, .45), mat(o.color), (i % 2 - .5) * .58, .35 + Math.floor(i / 4) * .42, (Math.floor(i / 2) % 2 - .5) * .48, g); });
add('casilleros', 'Casilleros', 'bodega', 1.5, .5, ['#4b5563'], (g, o) => { mesh(box(1.5, 1.9, .5), mat(o.color, { metalness: .4 }), 0, .95, 0, g); for (let i = 0; i < 5; i++) mesh(box(.02, 1.8, .02), mat('#111'), -.6 + i * .3, .95, .26, g); });
add('conos', 'Conos', 'bodega', .8, .5, ['#f97316'], (g, o) => { [-.25, .25].forEach(x => { mesh(new THREE.ConeGeometry(.15, .5, 16), mat(o.color), x, .25, 0, g); mesh(cyl(.11, .12, .05, 16), mat('#fff'), x, .25, 0, g); }); });
// ---------------- BAÑOS
add('sanitario', 'Sanitario', 'banos', .5, .7, ['#f8fafc'], (g, o) => { mesh(new RB(.4, .4, .55, 3, .15), mat(o.color), 0, .2, 0, g); mesh(rb(.42, .45, .18), mat(o.color), 0, .6, -.25, g); });
add('lavamanos', 'Lavamanos', 'banos', .6, .45, ['#f8fafc'], (g, o) => { mesh(cyl(.08, .1, .8, 12), mat(o.color), 0, .4, 0, g); mesh(new RB(.55, .15, .42, 3, .06), mat(o.color), 0, .85, 0, g); });

export const ITEMS = I;
export const byId = Object.fromEntries(I.map(x => [x.id, x]));
export function buildItem(o) {
  const def = byId[o.item]; const g = new THREE.Group();
  if (!def) return g;
  const cols = def.colors;
  def.build(g, { color: o.color || cols[0], color2: o.color2 || cols[1] || cols[0], color3: o.color3 || cols[2] || cols[0], text: o.text, screen: o.screen, products: o.products });
  g.userData.item = o; return g;
}

// ---------------- MODELOS 3D DE LA BIBLIOTECA (Clonexa): los 9 de Poly Haven (CC0) y los subidos y aprobados.
// Entran al catálogo en su carpeta. El GLB se baja una vez (sesión) y se clona; mientras llega se ve una caja.
const glbLoader = new GLTFLoader(); glbLoader.setMeshoptDecoder(MeshoptDecoder);
const GLB = new Map();
function loadModel(def) {
  if (GLB.has(def.id)) return GLB.get(def.id);
  const p = glbLoader.loadAsync(def.glb).then(g => {
    const src = g.scene; const b = new THREE.Box3().setFromObject(src); const c = b.getCenter(new THREE.Vector3());
    src.position.set(-c.x, -b.min.y, -c.z); src.traverse(q => { if (q.isMesh) { q.castShadow = true; q.receiveShadow = true; } });
    const holder = new THREE.Group(); holder.add(src); def.ready = true;
    def.pending.splice(0).forEach(g2 => fill(g2, holder)); def.waiters.splice(0).forEach(fn => { try { fn(); } catch (e) { } }); return holder;
  }).catch(() => null);
  GLB.set(def.id, p); return p;
}
function fill(g, holder) { g.children.filter(k => k.userData.placeholder).forEach(k => g.remove(k)); const c = holder.clone(true); c.traverse(q => { if (q.isMesh) q.userData.objId = g.userData.item?.id; }); g.add(c); }
export function registerModels(list) {
  for (const m of list || []) {
    if (byId[m.id]) continue;
    const def = { id: m.id, name: m.name, cat: CATS.some(c => c[0] === m.cat) ? m.cat : 'deco', w: Math.max(.3, +m.w || .6), d: Math.max(.3, +m.d || .6), colors: ['#ffffff'],
      glb: m.url, thumb: m.mini || '', license: m.license || '', source: m.source || '', author: m.author || '', model: true, pending: [], waiters: [], ready: false };
    if (m.conn) def.conn = m.conn;
    def.build = (g) => {
      const ph = mesh(box(def.w * .9, Math.max(.2, +m.h || .6), def.d * .9), mat('#9ca3af', { transparent: true, opacity: .45 }), 0, Math.max(.2, +m.h || .6) / 2, 0, g, false); ph.userData.placeholder = true;
      if (def.ready) GLB.get(def.id).then(h => h && fill(g, h)); else { def.pending.push(g); loadModel(def); }
    };
    def.whenReady = fn => { if (def.ready) fn(); else { def.waiters.push(fn); loadModel(def); } };
    I.push(def); byId[def.id] = def;
  }
}
