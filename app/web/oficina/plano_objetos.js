// Modo constructor · OBJETOS CLONEXA generados por código (0 bytes de descarga) + materiales de pared y piso +
// puertas y ventanas, en los DOS estilos de escena: "humano" (PBR, sombras suaves, texturas CC0 de Poly Haven del repo)
// y "caricatura" (toon de 3 tonos, contorno oscuro, colores más vivos). El mismo plano se dibuja igual en los dos:
// cambia solo el material. Cada objeto se arma UNA vez por (modelo, color, variante) y se aplana por material para
// dibujarlo con instancias (rendimiento con 150+ objetos). Interno de Clonexa; lo usa oficina_plano.js.
import * as THREE from 'three';
import {mergeGeometries} from 'three/addons/utils/BufferGeometryUtils.js';
import {RoundedBoxGeometry} from 'three/addons/geometries/RoundedBoxGeometry.js';

// ------------------------------------------------------------------ reglas puras (probadas en node)
export function hexOf(c, def = '#888888') { return /^#[0-9a-f]{6}$/i.test(String(c || '')) ? String(c).toLowerCase() : def; }
export function shade(hex, k) {   // k < 1 oscurece, > 1 aclara
  const n = parseInt(hexOf(hex).slice(1), 16), f = v => Math.max(0, Math.min(255, Math.round(k >= 1 ? v + (255 - v) * (k - 1) : v * k)));
  return '#' + [f(n >> 16 & 255), f(n >> 8 & 255), f(n & 255)].map(v => v.toString(16).padStart(2, '0')).join('');
}
export function vivid(hex) {   // caricatura: un poco más saturado y claro
  const n = parseInt(hexOf(hex).slice(1), 16); let r = (n >> 16 & 255) / 255, g = (n >> 8 & 255) / 255, b = (n & 255) / 255;
  const mx = Math.max(r, g, b), mn = Math.min(r, g, b), l = (mx + mn) / 2; const s = 1.25, add = .04;
  [r, g, b] = [r, g, b].map(v => Math.max(0, Math.min(1, l + (v - l) * s + add)));
  return '#' + [r, g, b].map(v => Math.round(v * 255).toString(16).padStart(2, '0')).join('');
}
export const UNIQUE = new Set(['neon', 'logo', 'tv_wall', 'tv_stand', 'projector']);
export const LIGHTS = {pendant: [0xffd9a0, 1.6, 5, 2.0], spot: [0xffffff, 1.4, 5, 2.4], sconce: [0xffc98a, .8, 3, 1.8], floor_lamp: [0xffe0b0, 1, 4, 1.5],
  led_strip: [null, .6, 3, .1], neon: [null, 1.2, 4, .3], track_light: [0xffffff, 1.2, 6, 2.6], led_floor: [null, .8, 5, .1]};
// Clave de instancia: mismo modelo + color + variante + texto se dibujan juntos.
export function instKey(o, item) { return [o.asset, hexOf(o.color || (item && item.variantes && item.variantes[0]), ''), o.variante || '', o.texto || ''].join('|'); }
// 3D: el plano usa metros con origen arriba a la izquierda; la escena va centrada.
export function toScene(x, z, sala) { return [x - sala.ancho / 2, z - sala.fondo / 2]; }
export function rotY(deg) { return -(Number(deg) || 0) * Math.PI / 180; }

// ------------------------------------------------------------------ materiales
export function createLibrary({tex = () => null, toon = false, lite = false, track = x => x} = {}) {
  const cache = new Map();
  const grad = (() => { const d = new Uint8Array([70, 150, 255]); const t = new THREE.DataTexture(d, 3, 1, THREE.RedFormat); t.minFilter = t.magFilter = THREE.NearestFilter; t.needsUpdate = true; return track(t); })();
  function M(key, make) { if (!cache.has(key)) cache.set(key, track(make())); return cache.get(key); }
  function base(color, o = {}) {
    const hex = toon ? vivid(color) : hexOf(color);
    const key = `${toon}|${hex}|${JSON.stringify(o, (k, v) => (v && v.isTexture ? v.uuid : v))}`;
    return M(key, () => {
      if (o.glow) return new THREE.MeshBasicMaterial({color: hex, toneMapped: false});
      if (toon) { const m = new THREE.MeshToonMaterial({color: hex, gradientMap: grad, map: o.map || null, transparent: !!o.glass, opacity: o.glass ? .35 : 1});
        if (o.glass) m.userData.noOutline = true; return m; }
      return new THREE.MeshStandardMaterial({color: hex, map: o.map || null, roughness: o.glass ? .05 : o.rough ?? .6, metalness: o.metal ?? 0,
        transparent: !!o.glass, opacity: o.glass ? .3 : 1, envMapIntensity: o.env ?? 1, side: o.double ? THREE.DoubleSide : THREE.FrontSide});
    });
  }
  const glow = c => { const m = base(c, {glow: true}); m.userData.noOutline = true; return m; };
  const pal = color => ({c: base(color), c2: base(shade(color, .62)), c3: base(shade(color, 1.35)), k: base('#16161a', {rough: .4}), s: base('#b8b8bd', {metal: .85, rough: .3}),
    w: base('#f2f2ee'), g: base('#a9d6f5', {glass: true}), wood: base('#8a5a36', {map: tex('madera_diff.webp')}), dark: base('#2a2a2e'), red: base('#dc2626'),
    green: base('#22a35a'), leaf: base('#2f7a46', {rough: .8}), soil: base('#4a2c1d'), screen: base('#0b1220', {rough: .2}), glow, col: x => base(x)});

  // ---------------------------------------------------------------- piezas
  function K(group, color) {
    const p = pal(color);
    const add = (geo, m, x, y, z, ry = 0, rx = 0, rz = 0) => { const k = new THREE.Mesh(geo, m); k.position.set(x, y, z); k.rotation.set(rx, ry, rz); k.castShadow = k.receiveShadow = !lite; group.add(k); return k; };
    return Object.assign(p, {
      group,
      box: (w, h, d, x = 0, y = 0, z = 0, m = p.c, ry = 0) => add(new THREE.BoxGeometry(w, h, d), m, x, y + h / 2, z, ry),
      rbox: (w, h, d, x = 0, y = 0, z = 0, m = p.c, r = .04) => add(new RoundedBoxGeometry(w, h, d, 2, Math.min(r, w / 2, h / 2, d / 2)), m, x, y + h / 2, z),
      cyl: (r, h, x = 0, y = 0, z = 0, m = p.c, seg = 16, r2 = null) => add(new THREE.CylinderGeometry(r, r2 ?? r, h, seg), m, x, y + h / 2, z),
      sph: (r, x = 0, y = 0, z = 0, m = p.c, sy = 1) => { const k = add(new THREE.SphereGeometry(r, 14, 10), m, x, y, z); k.scale.y = sy; return k; },
      cone: (r, h, x = 0, y = 0, z = 0, m = p.c, seg = 16, open = false) => add(new THREE.ConeGeometry(r, h, seg, 1, open), m, x, y + h / 2, z),
      torus: (R, r, x = 0, y = 0, z = 0, m = p.c, rx = Math.PI / 2) => add(new THREE.TorusGeometry(R, r, 8, 24), m, x, y, z, 0, rx),
      plane: (w, h, x, y, z, m, ry = 0) => add(new THREE.PlaneGeometry(w, h), m, x, y, z, ry),
    });
  }
  const chair = (k, x, z, ry, m = k.c, leg = k.k) => { const g = new THREE.Group(); g.position.set(x, 0, z); g.rotation.y = ry; k.group.add(g);
    const kk = K(g, '#000'); kk.rbox(.44, .05, .42, 0, .44, 0, m, .02); kk.rbox(.42, .42, .05, 0, .49, -.19, m, .02);
    [[-.18, -.17], [.18, -.17], [-.18, .17], [.18, .17]].forEach(([u, v]) => kk.cyl(.016, .44, u, 0, v, leg, 6)); };
  const stool = (k, x, z, m = k.c, h = .76) => { k.cyl(.19, .06, x, h - .06, z, m, 18); k.cyl(.025, h - .06, x, 0, z, k.s, 8); k.torus(.15, .012, x, .3, z, k.s); k.cyl(.2, .02, x, 0, z, k.s, 18); };
  const bottles = (k, x0, y, z, n, w) => { const cols = ['#16a34a', '#b45309', '#1d4ed8', '#dc2626', '#f5f5f5', '#a855f7']; for (let i = 0; i < n; i++) { const x = x0 + (i + .5) * w / n; k.cyl(.035, .24, x, y, z, base(cols[i % cols.length], {rough: .15}), 8); k.cyl(.012, .07, x, y + .24, z, k.k, 6); } };
  const screen = (k, w, h, y, z = 0) => { k.box(w + .08, h + .08, .06, 0, y - .04, z, k.k); const s = k.plane(w, h, 0, y + h / 2, z + .035, k.screen); s.userData.screen = true; return s; };
  const plantOn = (k, x, y, z, s = 1, pot = k.c) => { k.cyl(.22 * s, .4 * s, x, y, z, pot, 14, .17 * s); for (let i = 0; i < 7; i++) k.sph((.17 + (i % 3) * .03) * s, x + Math.sin(i * 2.4) * .14 * s, y + (.6 + (i % 4) * .14) * s, z + Math.cos(i * 2.4) * .14 * s, k.leaf, 1.3); };
  const tableSeats = (k, top, legs, seats, W, D, h = .75) => { top(); legs(); seats.forEach(([x, z, r]) => chair(k, x, z, r)); };

  // Cada forma recibe (k, W, D, H, item, o): W ancho (x), D fondo (z), H alto. Frente hacia +z.
  const F = {
    // ---------- barra y sonido
    bar_straight: (k, W, D, H) => { k.box(W, H - .05, D * .8, 0, 0, .05, k.c); k.box(W + .1, .05, D, 0, H - .05, 0, k.wood); k.box(W, .06, .04, 0, .12, D * .45, k.glow('#a855f7')); },
    bar_l: (k, W, D, H) => { k.box(W, H - .05, .7, 0, 0, D / 2 - .35, k.c); k.box(.7, H - .05, D - .7, -W / 2 + .35, 0, -.35, k.c); k.box(W + .1, .05, .8, 0, H - .05, D / 2 - .35, k.wood); k.box(.8, .05, D - .7, -W / 2 + .35, H - .05, -.35, k.wood); },
    bar_island: (k, W, D, H) => { k.rbox(W, H - .05, D, 0, 0, 0, k.c, .1); k.rbox(W + .2, .05, D + .2, 0, H - .05, 0, k.wood, .06); bottles(k, -W / 4, H, 0, 6, W / 2); },
    backbar: (k, W, D, H) => { k.box(W, .9, D, 0, 0, 0, k.c); k.box(W, H - .9, .06, 0, .9, -D / 2 + .03, k.c2); for (let r = 0; r < 3; r++) { k.box(W, .03, D * .7, 0, 1.15 + r * .38, -D * .1, k.wood); bottles(k, -W / 2, 1.18 + r * .38, -D * .1, Math.round(W * 6), W); } k.box(W, .03, .03, 0, H - .1, 0, k.glow('#f59e0b')); },
    stool: (k, W, D, H) => stool(k, 0, 0, k.c, H),
    beer_tap: (k, W, D, H) => { k.box(W, .08, D, 0, 0, 0, k.s); [-.18, 0, .18].forEach(x => { k.cyl(.02, H - .1, x, .08, 0, k.s, 8); k.box(.04, .12, .04, x, H - .14, .04, k.k); }); },
    dj_booth: (k, W, D, H) => { k.box(W, H, D, 0, 0, 0, k.c); k.box(W, .04, .04, 0, H * .55, D / 2, k.glow('#ec4899')); k.box(W * .9, .05, D * .7, 0, H, 0, k.k); [-.5, .5].forEach(x => k.cyl(.16, .03, x * W / 2, H + .05, 0, k.s, 20)); k.box(.4, .04, .25, 0, H + .05, 0, k.dark); },
    led_floor: (k, W, D, H, it, o) => { const n = Math.max(2, Math.round(W)); const cols = [o.color || '#ec4899', '#22d3ee', '#a855f7', '#f59e0b'];
      for (let i = 0; i < n; i++) for (let j = 0; j < n; j++) k.box(W / n - .03, H, D / n - .03, -W / 2 + (i + .5) * W / n, 0, -D / 2 + (j + .5) * D / n, k.glow(shade(cols[(i + j * 2) % cols.length], .75))); },
    speaker: (k, W, D, H) => { k.box(W, H, D, 0, 0, 0, k.c); [H * .3, H * .7].forEach(y => k.cyl(W * .32, .02, 0, y, D / 2, k.dark, 20).rotation.x = Math.PI / 2); },
    speaker_wall: (k, W, D, H) => { k.box(W, H, D, 0, 0, 0, k.c); k.cyl(W * .3, .02, 0, H * .5, D / 2, k.dark, 16).rotation.x = Math.PI / 2; },
    console: (k, W, D, H) => { k.box(W, H - .1, D, 0, 0, 0, k.k); k.box(W, .1, D, 0, H - .1, 0, k.dark); for (let i = 0; i < 8; i++) k.box(.03, .02, .2, -W / 2 + .1 + i * .1, H, 0, k.s); },
    mic: (k, W, D, H) => { k.cyl(.12, .02, 0, 0, 0, k.c, 16); k.cyl(.012, H - .15, 0, 0, 0, k.c, 6); k.sph(.04, 0, H - .1, .05, k.k, 1.4); },
    // ---------- neveras
    fridge_glass: (k, W, D, H) => { k.box(W, H, D, 0, 0, 0, k.c); k.box(W * .86, H * .78, .02, 0, H * .15, D / 2 + .005, k.g); for (let r = 0; r < 4; r++) bottles(k, -W * .4, H * .17 + r * H * .19, D * .2, 6, W * .8); k.box(W, H * .1, .02, 0, H * .9, D / 2 + .01, k.glow('#e0f2fe')); },
    fridge_glass2: (k, W, D, H) => { [-1, 1].forEach(s => { const g = new THREE.Group(); g.position.x = s * W / 4; k.group.add(g); F.fridge_glass(Object.assign(K(g, '#000'), {c: k.c, g: k.g}), W / 2, D, H); }); },
    fridge_steel: (k, W, D, H) => { k.box(W, H, D, 0, 0, 0, k.s); k.box(.02, H * .9, .02, 0, H * .05, D / 2, k.dark); [-.1, .1].forEach(x => k.box(.03, .5, .04, x, H * .45, D / 2 + .02, k.k)); },
    fridge: (k, W, D, H) => { k.rbox(W, H, D, 0, 0, 0, k.c, .05); k.box(W, .01, .01, 0, H * .62, D / 2, k.dark); k.box(.03, .35, .04, W * .38, H * .68, D / 2 + .02, k.s); k.box(.03, .35, .04, W * .38, H * .3, D / 2 + .02, k.s); },
    freezer: (k, W, D, H) => { k.rbox(W, H, D, 0, 0, 0, k.c, .05); k.box(W * .9, .02, D * .8, 0, H, 0, k.g); },
    dessert_case: (k, W, D, H) => { k.box(W, H * .55, D, 0, 0, 0, k.c); k.box(W, H * .45, D, 0, H * .55, 0, k.g); for (let i = 0; i < 4; i++) { k.cyl(.11, .08, -W / 2 + .25 + i * W / 4.2, H * .6, 0, base('#f9a8d4'), 12); k.cyl(.11, .08, -W / 2 + .25 + i * W / 4.2, H * .78, 0, base('#fde68a'), 12); } },
    // ---------- mesas y asientos
    table_round: (k, W, D, H) => { k.cyl(.48, .05, 0, H - .05, 0, k.c, 28); k.cyl(.05, H - .05, 0, 0, 0, k.k, 10); k.cyl(.25, .03, 0, 0, 0, k.k, 18); [[0, -.72, 0], [0, .72, Math.PI], [-.72, 0, Math.PI / 2], [.72, 0, -Math.PI / 2]].forEach(([x, z, r]) => chair(k, x, z, r, k.c2)); },
    table_square: (k, W, D, H) => { k.rbox(1.0, .05, 1.0, 0, H - .05, 0, k.c, .02); [[-.42, -.42], [.42, -.42], [-.42, .42], [.42, .42]].forEach(([x, z]) => k.box(.05, H - .05, .05, x, 0, z, k.k)); [[0, -.75, 0], [0, .75, Math.PI], [-.75, 0, Math.PI / 2], [.75, 0, -Math.PI / 2]].forEach(([x, z, r]) => chair(k, x, z, r, k.c2)); },
    table_two: (k, W, D, H) => { k.rbox(.7, .05, .7, 0, H - .05, 0, k.c, .02); k.cyl(.04, H - .05, 0, 0, 0, k.k, 8); chair(k, -.6, 0, Math.PI / 2, k.c2); chair(k, .6, 0, -Math.PI / 2, k.c2); },
    table_six: (k, W, D, H) => { k.rbox(1.9, .05, .95, 0, H - .05, 0, k.c, .02); [[-.85, -.4], [.85, -.4], [-.85, .4], [.85, .4]].forEach(([x, z]) => k.box(.05, H - .05, .05, x, 0, z, k.k)); [-.6, 0, .6].forEach(x => { chair(k, x, -.75, 0, k.c2); chair(k, x, .75, Math.PI, k.c2); }); },
    table_high: (k, W, D, H) => { k.cyl(.35, .04, 0, H - .04, 0, k.c, 24); k.cyl(.035, H - .04, 0, 0, 0, k.s, 8); k.cyl(.22, .02, 0, 0, 0, k.s, 18); [[0, -.55], [0, .55]].forEach(([x, z]) => stool(k, x, z, k.c2, .76)); },
    booth: (k, W, D, H) => { k.rbox(1.1, .05, .7, 0, .72, 0, k.wood, .02); k.cyl(.05, .72, 0, 0, 0, k.k, 8); [-1, 1].forEach(s => { k.rbox(W * .95, .45, .5, 0, 0, s * .65, k.c, .05); k.rbox(W * .95, H - .45, .15, 0, .45, s * (.65 + .2), k.c2, .05); }); },
    table_coffee: (k, W, D, H) => { k.rbox(W, .05, D, 0, H - .05, 0, k.c, .02); k.box(W * .9, .03, D * .8, 0, .1, 0, k.c2); [[-1, -1], [1, -1], [-1, 1], [1, 1]].forEach(([a, b]) => k.cyl(.02, H - .05, a * (W / 2 - .05), 0, b * (D / 2 - .05), k.k, 6)); },
    chair: (k) => chair(k, 0, 0, 0, k.c),
    bench: (k, W, D, H) => { k.rbox(W, .06, D, 0, H - .06, 0, k.c, .02); [-1, 1].forEach(s => k.box(.06, H - .06, D * .8, s * (W / 2 - .1), 0, 0, k.k)); },
    bench_back: (k, W, D, H) => { k.rbox(W, .1, D * .8, 0, .42, .05, k.c, .03); k.rbox(W, H - .52, .1, 0, .52, -D / 2 + .05, k.c2, .03); [-1, 1].forEach(s => k.box(.06, .42, D * .7, s * (W / 2 - .1), 0, 0, k.k)); },
    sofa: (k, W, D, H) => { k.rbox(W, .42, D, 0, .05, 0, k.c, .08); k.rbox(W, H - .3, .22, 0, .3, -D / 2 + .11, k.c2, .08); [-1, 1].forEach(s => k.rbox(.2, .62, D, s * (W / 2 - .1), .05, 0, k.c2, .06)); k.box(W * .95, .05, D * .9, 0, 0, 0, k.k); },
    armchair: (k, W, D, H) => F.sofa(k, W, D, H),
    pouf: (k, W, D, H) => k.cyl(W / 2, H, 0, 0, 0, k.c, 20),
    office_chair: (k, W, D, H) => { k.rbox(.5, .08, .48, 0, .45, 0, k.c, .03); k.rbox(.46, .55, .07, 0, .5, -.22, k.c, .04); k.cyl(.03, .4, 0, .05, 0, k.s, 8); for (let i = 0; i < 5; i++) { const a = i * 1.256; k.box(.3, .03, .04, Math.sin(a) * .15, .04, Math.cos(a) * .15, k.k, a + Math.PI / 2); } },
    // ---------- pantallas
    tv_wall: (k, W, D, H) => { screen(k, W, H, 1.3 - H / 2 + .4, -D / 2 + .05); },
    tv_stand: (k, W, D, H) => { k.box(.5, .04, .4, 0, 0, 0, k.k); k.cyl(.03, H - .75, 0, 0, 0, k.c, 8); screen(k, W, .72, H - .74, 0); },
    projector: (k, W, D, H) => { k.box(W, .08, .1, 0, 2.6 - H * .1, -D / 2 + .05, k.k); const s = k.plane(W, H, 0, 2.55 - H / 2, -D / 2 + .08, k.w); s.userData.screen = true; },
    // ---------- cocina
    stove: (k, W, D, H) => { k.box(W, H, D, 0, 0, 0, k.c); k.box(W, .03, D, 0, H, 0, k.k); [[-.25, -.18], [.25, -.18], [-.25, .18], [.25, .18]].forEach(([x, z]) => k.torus(.11, .015, x * W, H + .04, z, k.dark)); k.box(W * .8, .4, .02, 0, .2, D / 2 + .005, k.dark); },
    grill: (k, W, D, H) => { k.box(W, H - .1, D, 0, 0, 0, k.c); k.box(W * .9, .03, D * .8, 0, H - .08, 0, k.glow('#ff5a1f')); for (let i = 0; i < 9; i++) k.box(.02, .02, D * .8, -W * .43 + i * W * .107, H - .03, 0, k.dark); },
    fryer: (k, W, D, H) => { k.box(W, H, D, 0, 0, 0, k.c); k.box(W * .7, .02, D * .6, 0, H, 0, base('#a16207', {rough: .2})); k.box(W * .3, .05, D * .7, 0, H + .15, 0, k.s); },
    oven: (k, W, D, H) => { k.box(W, H, D, 0, 0, 0, k.c); [.35, .95].forEach(y => { k.box(W * .8, .45, .02, 0, y, D / 2, k.dark); k.box(W * .5, .2, .021, 0, y + .12, D / 2, k.glow('#fb923c')); }); },
    wood_oven: (k, W, D, H) => { k.box(W, .9, D, 0, 0, 0, k.c2); k.sph(W * .45, 0, .9, 0, k.c, .9); k.box(.5, .35, .1, 0, .95, W * .42, k.glow('#ff5a1f')); k.cyl(.12, .8, 0, 1.5, -.2, k.c2, 10); },
    hood: (k, W, D, H, it) => { const y = 2.0; k.box(W, .25, D, 0, y, 0, k.c); k.cone(Math.min(W, D) * .6, .35, 0, y + .25, 0, k.c, 4); k.box(.4, .8, .4, 0, y + .5, 0, k.c); },
    counter: (k, W, D, H) => { k.box(W, H - .04, D, 0, 0, 0, k.c); k.box(W, .04, D, 0, H - .04, 0, k.s); k.box(W * .9, .02, D * .8, 0, .25, 0, k.c2); },
    sink: (k, W, D, H) => { F.counter(k, W, D, H); k.box(W * .4, .02, D * .6, -W * .2, H, 0, k.dark); k.cyl(.015, .3, -W * .2, H, -D * .35, k.s, 8); },
    pass: (k, W, D, H) => { k.box(W, 1.0, D, 0, 0, 0, k.c); k.box(W, .04, D, 0, 1.0, 0, k.s); k.box(W, .04, D * .8, 0, H - .04, 0, k.s); [-1, 1].forEach(s => k.box(.04, H - 1.0, .04, s * W / 2, 1.0, 0, k.s)); k.box(W * .9, .02, .05, 0, H - .1, 0, k.glow('#fbbf24')); for (let i = 0; i < 3; i++) k.cyl(.12, .02, -W / 3 + i * W / 3, 1.04, 0, k.w, 16); },
    pot_shelf: (k, W, D, H) => { F.shelf(k, W, D, H); for (let i = 0; i < 3; i++) k.cyl(.14, .2, -W / 3 + i * W / 3, .45, 0, k.s, 14); },
    // ---------- caja
    register: (k, W, D, H) => { k.box(W, H - .05, D, 0, 0, 0, k.c); k.box(W + .05, .05, D + .05, 0, H - .05, 0, k.wood); k.box(.35, .25, .3, -W * .25, H, 0, k.k); k.box(.32, .2, .02, -W * .25, H + .25, -.05, k.screen); k.box(.1, .02, .16, W * .2, H, 0, k.k); },
    card_terminal: (k, W, D, H) => { k.rbox(W, H, D, 0, 0, 0, k.c, .02); k.box(W * .8, .005, D * .4, 0, H, -D * .2, k.screen); },
    shop_counter: (k, W, D, H) => { k.box(W, H - .05, D, 0, 0, 0, k.c); k.box(W + .06, .05, D + .06, 0, H - .05, 0, k.c3); k.box(W * .9, .03, .03, 0, .1, D / 2, k.glow('#e0f2fe')); },
    // ---------- taller
    sewing: (k, W, D, H) => { k.box(W, .04, D, 0, .74, 0, k.wood); [[-1, -1], [1, -1], [-1, 1], [1, 1]].forEach(([a, b]) => k.box(.04, .74, .04, a * (W / 2 - .05), 0, b * (D / 2 - .05), k.k)); k.box(.42, .12, .2, 0, .78, 0, k.c); k.box(.1, .25, .18, .16, .9, 0, k.c); k.box(.4, .1, .18, 0, 1.12, 0, k.c); k.box(.04, .12, .04, -.17, 1.0, 0, k.s); k.cyl(.05, .04, .2, 1.22, 0, base('#db2777'), 10); chair(k, 0, .65, Math.PI, k.dark); },
    overlock: (k, W, D, H) => { F.sewing(k, W, D, H); k.box(.25, .2, .2, .2, .78, 0, base('#1d4ed8')); },
    iron: (k, W, D, H) => { k.rbox(W, .08, D * .6, 0, .9, 0, k.w, .03); k.box(.1, .9, .1, 0, 0, 0, k.s); k.box(W * .6, .06, D, 0, 0, 0, k.s); k.rbox(.25, .1, .14, W * .2, .98, 0, k.c, .03); },
    cut_table: (k, W, D, H) => { k.box(W, .05, D, 0, H - .05, 0, k.c); [[-1, -1], [1, -1], [-1, 1], [1, 1]].forEach(([a, b]) => k.box(.06, H - .05, .06, a * (W / 2 - .1), 0, b * (D / 2 - .1), k.k)); k.box(W * .7, .01, D * .6, 0, H, 0, base('#93c5fd')); k.box(W * .9, .02, D * .9, 0, .2, 0, k.c2); },
    fabric_rolls: (k, W, D, H, it, o) => { const cols = [o.color || '#db2777', '#1d4ed8', '#16a34a', '#f59e0b', '#a855f7', '#e5e7eb']; for (let i = 0; i < 6; i++) { const r = k.cyl(.13, D * .9, -W / 2 + .2 + (i % 3) * W / 3.2, .13 + Math.floor(i / 3) * .27 + H * .3, 0, base(cols[i]), 14); r.rotation.x = Math.PI / 2; } k.box(W, .04, D, 0, H * .3 - .04, 0, k.k); },
    garment_rack: (k, W, D, H, it, o) => { [-1, 1].forEach(s => k.box(.04, H, .04, s * W / 2, 0, 0, k.s)); k.cyl(.015, W, 0, H - .05, 0, k.s, 6).rotation.z = Math.PI / 2; k.box(W, .03, D, 0, .05, 0, k.s); const cols = [o.color || '#7c3aed', '#db2777', '#0f766e', '#f59e0b']; for (let i = 0; i < 8; i++) k.box(.06, H * .5, D * .8, -W / 2 + .15 + i * (W - .3) / 7, H * .42, 0, base(cols[i % 4])); },
    mannequin: (k, W, D, H) => { k.cyl(.15, .03, 0, 0, 0, k.k, 14); k.cyl(.015, H * .5, 0, 0, 0, k.k, 6); k.cyl(.15, H * .3, 0, H * .48, 0, k.c, 14, .12); k.sph(.09, 0, H * .87, 0, k.c); },
    lot_shelf: (k, W, D, H) => { F.shelf(k, W, D, H); for (let r = 0; r < 4; r++) for (let i = 0; i < 3; i++) k.box(W / 4, .2, D * .8, -W / 3 + i * W / 3, .08 + r * H / 4.2, 0, base(['#b58a5a', '#93c5fd', '#fca5a5', '#86efac'][(r + i) % 4])); },
    cart: (k, W, D, H) => { k.box(W, .05, D, 0, .25, 0, k.c); k.box(W, H - .3, .03, 0, .3, -D / 2, k.c); [[-1, -1], [1, -1], [-1, 1], [1, 1]].forEach(([a, b]) => k.cyl(.06, .03, a * (W / 2 - .08), .02, b * (D / 2 - .08), k.k, 10).rotation.z = Math.PI / 2); k.box(W * .8, .3, D * .7, 0, .3, 0, base('#b58a5a')); },
    // ---------- oficina
    desk_pc: (k, W, D, H) => { k.box(W, .04, D, 0, .72, 0, k.c); [-1, 1].forEach(s => k.box(.04, .72, D * .9, s * (W / 2 - .03), 0, 0, k.k)); k.box(.5, .32, .03, 0, .82, -D / 2 + .15, k.k); k.box(.47, .28, .005, 0, .84, -D / 2 + .17, k.screen); k.box(.06, .08, .06, 0, .74, -D / 2 + .15, k.k); k.box(.42, .02, .14, 0, .76, .05, k.dark); },
    desk_row: (k, W, D, H) => { F.desk_pc(k, W, D, H); k.box(W, .5, .04, 0, .76, -D / 2 + .02, base('#94a3b8')); k.torus(.08, .012, .35, .8, .1, k.k, 0); },
    partition: (k, W, D, H) => { k.rbox(W, H, D, 0, 0, 0, k.c, .02); },
    meeting: (k, W, D, H) => { k.rbox(W * .75, .05, D * .5, 0, .72, 0, k.c, .04); k.box(.1, .72, D * .3, 0, 0, 0, k.k); for (let i = 0; i < 3; i++) { const x = -W * .28 + i * W * .28; chair(k, x, -D * .4, 0, k.dark); chair(k, x, D * .4, Math.PI, k.dark); } },
    whiteboard: (k, W, D, H) => { k.box(W + .06, H + .06, D, 0, 1.0 - .03, 0, base('#94a3b8', {metal: .5})); k.plane(W, H, 0, 1.0 + H / 2, D / 2 + .005, k.c); },
    reception: (k, W, D, H) => { k.rbox(W, H, D * .5, 0, 0, D * .2, k.c, .06); k.box(W, .04, D * .7, 0, .74, -D * .1, k.c2); k.box(W * .9, .03, .03, 0, .2, D * .46, k.glow('#a855f7')); k.box(.45, .3, .03, -W * .25, .78, -D * .25, k.k); },
    water: (k, W, D, H) => { k.box(W, H * .7, D, 0, 0, 0, k.c); k.cyl(W * .38, H * .3, 0, H * .7, 0, base('#7dd3fc', {glass: true}), 14); },
    printer: (k, W, D, H) => { k.rbox(W, H, D, 0, 0, 0, k.c, .03); k.box(W * .7, .01, D * .5, 0, H, 0, k.w); },
    file_cabinet: (k, W, D, H) => { k.box(W, H, D, 0, 0, 0, k.c); for (let i = 0; i < 4; i++) k.box(.15, .02, .02, 0, .2 + i * H / 4, D / 2 + .01, k.k); },
    // ---------- tienda
    gondola: (k, W, D, H) => { k.box(W, .1, D, 0, 0, 0, k.c2); k.box(W, H, .05, 0, 0, 0, k.c); for (let r = 0; r < 4; r++) [-1, 1].forEach(s => { k.box(W, .03, D / 2 - .05, 0, .2 + r * H / 4.2, s * D / 4, k.c); for (let i = 0; i < Math.round(W * 4); i++) k.box(.12, .18, .12, -W / 2 + .1 + i * .25, .23 + r * H / 4.2, s * D / 4, base(['#dc2626', '#f59e0b', '#16a34a', '#1d4ed8', '#f5f5f5'][(i + r) % 5])); }); },
    wall_display: (k, W, D, H) => { k.box(W, H, .05, 0, 0, -D / 2 + .025, k.c); for (let r = 0; r < 5; r++) { k.box(W, .03, D, 0, .3 + r * H / 5.5, 0, k.c2); for (let i = 0; i < Math.round(W * 4); i++) k.cyl(.04, .16, -W / 2 + .12 + i * .25, .33 + r * H / 5.5, 0, base(['#f472b6', '#38bdf8', '#facc15', '#a3e635'][(i + r) % 4]), 8); } },
    baskets: (k, W, D, H) => { for (let i = 0; i < 4; i++) k.box(W, .13, D, 0, i * .14, 0, k.c); },
    // ---------- bodega
    rack: (k, W, D, H, it, o) => { [[-1, -1], [1, -1], [-1, 1], [1, 1]].forEach(([a, b]) => k.box(.05, H, .05, a * (W / 2 - .03), 0, b * (D / 2 - .03), k.c)); for (let r = 0; r < 4; r++) { k.box(W, .03, D, 0, .1 + r * H / 4, 0, k.s); k.box(W * .4, .3, D * .8, -W * .22, .13 + r * H / 4, 0, base('#b58a5a')); k.box(W * .3, .22, D * .7, W * .2, .13 + r * H / 4, 0, base('#d6b48a')); } },
    rack_tall: (k, W, D, H) => { [-1, 0, 1].forEach(a => [-1, 1].forEach(b => k.box(.08, H, .08, a * (W / 2 - .05), 0, b * (D / 2 - .05), k.c))); for (let r = 0; r < 3; r++) { k.box(W, .08, .06, 0, 1.2 + r * 1.4, -D / 2 + .05, base('#f97316')); k.box(W, .08, .06, 0, 1.2 + r * 1.4, D / 2 - .05, base('#f97316')); [-.6, .6].forEach(x => { k.box(1.1, .14, 1.0, x * W / 2.4, 1.28 + r * 1.4, 0, base('#b58a5a')); k.box(1.0, .8, .9, x * W / 2.4, 1.42 + r * 1.4, 0, base('#d6b48a')); }); } },
    pallet: (k, W, D, H) => { k.box(W, .14, D, 0, 0, 0, k.c); [[-.25, -.2], [.25, -.2], [-.25, .25], [.25, .25]].forEach(([x, z]) => k.box(W * .45, .4, D * .45, x * W, .14, z * D, base('#d6b48a'))); k.box(W * .45, .38, D * .45, -.12, .54, 0, base('#c9a273')); },
    boxes: (k, W, D, H) => { k.box(W * .55, H * .5, D * .6, -W * .2, 0, 0, k.c); k.box(W * .4, H * .4, D * .5, W * .28, 0, .1, base(shade('#b58a5a', 1.15))); k.box(W * .45, H * .45, D * .5, -W * .15, H * .5, 0, base(shade('#b58a5a', .9))); },
    forklift: (k, W, D, H) => { k.rbox(W, .9, D * .6, 0, .2, .2, k.c, .1); k.box(W * .9, .05, D * .35, 0, 2.0, .3, k.k); [-1, 1].forEach(s => k.box(.05, 1.9, .05, s * W * .4, .9, .45, k.k)); k.rbox(.5, .35, .4, 0, 1.0, .1, k.k, .05); [-1, 1].forEach(s => k.box(.05, 2.1, .08, s * W * .35, 0, -D / 2 + .2, k.dark)); [-1, 1].forEach(s => k.box(.12, .05, 1.0, s * .25, .05, -D / 2 - .2, k.s)); [[-1, .8], [1, .8], [-1, -.3], [1, -.3]].forEach(([a, z]) => k.cyl(.2, .14, a * W / 2, .2, z, k.k, 14).rotation.z = Math.PI / 2); },
    lockers: (k, W, D, H) => { k.box(W, H, D, 0, 0, 0, k.c); for (let i = 1; i < 4; i++) k.box(.01, H, .01, -W / 2 + i * W / 4, 0, D / 2, k.k); for (let i = 0; i < 4; i++) k.box(.04, .1, .02, -W / 2 + (i + .7) * W / 4, H * .55, D / 2 + .01, k.s); },
    tools: (k, W, D, H) => { k.box(W, H, .03, 0, 1.0, -D / 2 + .015, base('#64748b')); for (let i = 0; i < 6; i++) { k.box(.04, .35, .03, -W / 2 + .2 + i * W / 6.5, 1.3, 0, base(['#dc2626', '#f59e0b', '#1d4ed8'][i % 3])); k.box(.12, .06, .04, -W / 2 + .2 + i * W / 6.5, 1.62, 0, k.s); } },
    cones: (k, W, D, H, it, o) => { [-.25, .25].forEach(x => { k.cone(.15, H, x, 0, 0, k.c, 14); k.box(.32, .03, .32, x, 0, 0, k.k); k.cyl(.1, .06, x, H * .5, 0, k.w, 14); }); },
    shelf: (k, W, D, H) => { [-1, 1].forEach(s => k.box(.04, H, D, s * (W / 2 - .02), 0, 0, k.c)); for (let r = 0; r < 5; r++) k.box(W, .03, D, 0, r * H / 4.6, 0, k.c); k.box(W, H, .02, 0, 0, -D / 2 + .01, k.c2); },
    bins: (k, W, D, H, it, o) => { [o.color || '#16a34a', '#1d4ed8', '#9ca3af'].forEach((c, i) => k.rbox(W / 3.2, H, D, -W / 3 + i * W / 3, 0, 0, base(c), .04)); },
    // ---------- luces
    pendant: (k, W, D, H) => { const y = 2.2; k.cyl(.005, .9, 0, y + .3, 0, k.k, 4); k.cone(W * .45, .25, 0, y + .05, 0, k.c, 18, true).material = base(k.c.color ? '#' + k.c.color.getHexString() : '#111111', {double: true}); k.sph(.06, 0, y + .05, 0, k.glow('#ffe7b0')); },
    spot: (k, W, D, H) => { k.cyl(.03, .25, 0, 2.6, 0, k.c, 8); k.cyl(.08, .18, 0, 2.45, 0, k.c, 12, .1); k.cyl(.07, .01, 0, 2.44, 0, k.glow('#fff7e6'), 12); },
    led_strip: (k, W, D, H, it, o) => { k.box(W, .03, .03, 0, 2.6, -D / 2 + .02, k.glow(o.color || '#ec4899')); },
    sconce: (k, W, D, H) => { k.box(.08, .2, .04, 0, 1.8, -D / 2 + .02, k.c); k.cone(.1, .18, 0, 1.85, -D / 2 + .1, k.glow('#ffd9a0'), 12, true); },
    floor_lamp: (k, W, D, H) => { k.cyl(.16, .03, 0, 0, 0, k.c, 16); k.cyl(.015, H - .3, 0, 0, 0, k.c, 6); k.cyl(.12, .3, 0, H - .3, 0, base('#f5e6c8'), 16, .18); },
    track_light: (k, W, D, H) => { k.box(W, .04, .06, 0, 2.9, 0, k.c); for (let i = 0; i < 4; i++) { const x = -W / 2 + (i + .5) * W / 4; k.cyl(.05, .14, x, 2.74, 0, k.c, 10); k.cyl(.045, .01, x, 2.73, 0, k.glow('#fff7e6'), 10); } },
    neon: (k, W, D, H) => { k.box(W, H, .02, 0, 1.9, -D / 2 + .01, base('#0b0b10', {rough: .3})); },
    // ---------- decoración
    logo: (k, W, D, H) => { k.box(W, H, .04, 0, 1.6, -D / 2 + .02, k.c); },
    plant: (k, W, D, H) => { k.cyl(W * .3, H * .3, 0, 0, 0, k.c, 16, W * .24); for (let i = 0; i < 9; i++) k.sph(W * (.22 + (i % 3) * .05), Math.sin(i * 2.4) * W * .2, H * (.42 + (i % 4) * .14), Math.cos(i * 2.4) * W * .2, k.leaf, 1.4); },
    plant_small: (k, W, D, H) => plantOn(k, 0, 0, 0, .7, k.c),
    palm: (k, W, D, H) => { k.cyl(.3, .45, 0, 0, 0, k.c, 16, .25); k.cyl(.05, H - .9, 0, .45, 0, base('#8a5a36'), 8, .07); for (let i = 0; i < 7; i++) { const l = k.box(.18, .02, .9, Math.sin(i * .9) * .35, H - .35, Math.cos(i * .9) * .35, k.leaf); l.rotation.set(-.5 * Math.cos(i * .9), i * .9, .5 * Math.sin(i * .9)); } },
    frame: (k, W, D, H) => { k.box(W, H, .04, 0, 1.5, -D / 2 + .02, k.wood); k.plane(W * .86, H * .8, 0, 1.5 + H / 2, -D / 2 + .045, k.c); },
    rug: (k, W, D, H) => { k.box(W, .015, D, 0, 0, 0, k.c); k.box(W * .8, .016, D * .7, 0, 0, 0, k.c2); },
    clock: (k, W, D, H) => { const c = k.cyl(W / 2, .04, 0, 2.2, -D / 2 + .02, k.c, 24); c.rotation.x = Math.PI / 2; const f = k.cyl(W / 2 - .03, .01, 0, 2.2, -D / 2 + .045, k.w, 24); f.rotation.x = Math.PI / 2; k.box(.02, W * .3, .01, 0, 2.2 + .02, -D / 2 + .05, k.k); },
    mirror: (k, W, D, H) => { k.box(W, H, .03, 0, 1.0, -D / 2 + .015, k.c); k.plane(W * .9, H * .92, 0, 1.0 + H / 2, -D / 2 + .035, base('#dbeafe', {metal: 1, rough: .02})); },
    wall_shelf: (k, W, D, H) => { k.box(W, .03, D, 0, 1.5, 0, k.c); plantOn(k, -W / 3, 1.53, 0, .4, k.w); k.box(.2, .25, .15, W / 4, 1.53, 0, base('#b45309')); },
    screen_divider: (k, W, D, H) => { for (let i = 0; i < 3; i++) k.box(W / 3 - .02, H, D, -W / 3 + i * W / 3, 0, (i % 2) * .08, k.c); },
    // ---------- exterior
    umbrella: (k, W, D, H) => { k.cyl(.025, H - .1, 0, 0, 0, k.w, 8); k.cone(W / 2, .5, 0, H - .5, 0, k.c, 16); k.cyl(.25, .08, 0, 0, 0, k.k, 14); },
    table_outdoor: (k, W, D, H) => { k.cyl(.45, .04, 0, H - .04, 0, k.c, 24); k.cyl(.035, H - .04, 0, 0, 0, k.c, 8); [[0, -.7, 0], [0, .7, Math.PI], [-.7, 0, Math.PI / 2], [.7, 0, -Math.PI / 2]].forEach(([x, z, r]) => chair(k, x, z, r, k.c, k.c2)); },
    table_umbrella: (k, W, D, H) => { F.table_outdoor(Object.assign({}, k, {c: k.w, c2: k.dark}), W, D, .75); F.umbrella(k, 2.2, 2.2, H); },
    planter: (k, W, D, H) => { k.box(W, H * .5, D, 0, 0, 0, k.c); for (let i = 0; i < 5; i++) k.sph(D * .55, -W / 2 + (i + .5) * W / 5, H * .62, 0, k.leaf, 1.2); },
    moto: (k, W, D, H) => { k.rbox(.34, .34, 1.5, 0, .45, 0, k.c, .12); [-.6, .6].forEach(z => { const t = k.torus(.27, .08, 0, .3, z, k.k, 0); t.rotation.y = Math.PI / 2; }); k.rbox(.46, .46, .46, 0, .82, -.45, base('#f97316'), .04); k.cyl(.02, .5, 0, .8, .55, k.s, 6); },
    bike_rack: (k, W, D, H) => { for (let i = 0; i < 5; i++) { const t = k.torus(.3, .02, -W / 2 + .2 + i * (W - .4) / 4, .3, 0, k.c, 0); t.rotation.y = Math.PI / 2; } },
    fence: (k, W, D, H) => { k.box(W, .05, .05, 0, H - .05, 0, k.c); k.box(W, .05, .05, 0, H * .4, 0, k.c); for (let i = 0; i <= Math.round(W * 4); i++) k.box(.03, H, .03, -W / 2 + i * W / Math.round(W * 4), 0, 0, k.c); },
    // ---------- baños
    toilet: (k, W, D, H) => { k.rbox(W * .8, .4, D * .6, 0, 0, .05, k.c, .08); k.rbox(W, .38, .2, 0, .4, -D / 2 + .1, k.c, .05); k.cyl(W * .45, .04, 0, .4, .1, k.c, 18); },
    washbasin: (k, W, D, H) => { k.cyl(.07, H - .15, 0, 0, -D * .2, k.c, 10); k.rbox(W, .15, D, 0, H - .15, 0, k.c, .05); k.cyl(.015, .2, 0, H, -D / 2 + .05, k.s, 8); },
    urinal: (k, W, D, H) => { k.rbox(W, H, D, 0, .5, 0, k.c, .1); },
    stall: (k, W, D, H) => { [-1, 1].forEach(s => k.box(.03, H - .2, D, s * W / 2, .2, 0, k.c)); k.box(W, H - .2, .03, 0, .2, D / 2, k.c2); F.toilet(k, .4, .7, .8); },
    hand_dryer: (k, W, D, H) => { k.rbox(W, H, D, 0, 1.2, -D / 2 + D / 2, k.c, .05); },
  };
  F.glb = () => {};

  function buildProto(item, o) {
    const g = new THREE.Group();
    const color = o.color || (item.variantes && item.variantes[0]) || '#8a8a8a';
    const m = item.medidas || {w: 1, d: 1, h: 1};
    const fn = F[item.forma];
    if (fn) fn(K(g, color), m.w, m.d, m.h, item, o);
    else K(g, color).box(m.w, m.h, m.d, 0, 0, 0);
    return g;
  }
  // Aplana un objeto en (geometria fusionada, material) por material: pocas llamadas de dibujo por modelo.
  function flatten(group) {
    group.updateMatrixWorld(true);
    const by = new Map();
    group.traverse(x => { if (!x.isMesh || x.userData.screen) return; const g = x.geometry.index ? x.geometry.toNonIndexed() : x.geometry.clone(); g.applyMatrix4(x.matrixWorld);
      for (const k of Object.keys(g.attributes)) if (!['position', 'normal', 'uv'].includes(k)) g.deleteAttribute(k);
      if (!g.attributes.uv) g.setAttribute('uv', new THREE.BufferAttribute(new Float32Array(g.attributes.position.count * 2), 2));
      const list = by.get(x.material) || []; list.push(g); by.set(x.material, list); });
    const parts = [];
    for (const [mat, list] of by) { const geo = list.length > 1 ? mergeGeometries(list, false) : list[0]; if (geo) parts.push({geo: track(geo), mat}); }
    return parts;
  }
  return {F, buildProto, flatten, base, glow, pal, K, toon, grad};
}

// ------------------------------------------------------------------ texturas por código (sin licencia: dibujadas aquí)
const TEX = new Map();
export function patternCanvas(kind, size = 512) {
  const c = document.createElement('canvas'); c.width = c.height = size; const x = c.getContext('2d'); const s = size;
  const noise = (a, n = 1600) => { for (let i = 0; i < n; i++) { x.fillStyle = `rgba(0,0,0,${Math.random() * a})`; x.fillRect(Math.random() * s, Math.random() * s, 2 + Math.random() * 3, 2 + Math.random() * 3); } };
  x.fillStyle = '#fff'; x.fillRect(0, 0, s, s);
  if (kind === 'ladrillo_blanco') { x.fillStyle = '#d8d4cf'; for (let r = 0; r < 8; r++) { x.fillRect(0, r * s / 8 - 3, s, 6); for (let i = 0; i < 4; i++) x.fillRect(((i + (r % 2) * .5) * s / 4) % s - 3, r * s / 8, 6, s / 8); } noise(.06); }
  else if (kind === 'listones' || kind === 'deck') { const n = kind === 'deck' ? 6 : 10; for (let i = 0; i < n; i++) { x.fillStyle = `hsl(28,30%,${78 + (i * 37 % 15)}%)`; x.fillRect(i * s / n, 0, s / n, s); x.fillStyle = 'rgba(0,0,0,.35)'; x.fillRect(i * s / n, 0, 3, s); } noise(.05, 900); }
  else if (kind === 'azulejo' || kind === 'baldosa_blanca') { const n = kind === 'azulejo' ? 8 : 4; x.fillStyle = '#cfcfcf'; for (let i = 0; i <= n; i++) { x.fillRect(i * s / n - 2, 0, 4, s); x.fillRect(0, i * s / n - 2, s, 4); } }
  else if (kind === 'ajedrez') { for (let i = 0; i < 4; i++) for (let j = 0; j < 4; j++) { x.fillStyle = (i + j) % 2 ? '#222' : '#f4f4f4'; x.fillRect(i * s / 4, j * s / 4, s / 4, s / 4); } }
  else if (kind === 'papel_tapiz') { for (let i = 0; i < 8; i++) { x.fillStyle = i % 2 ? '#f2f2f2' : '#e1e1e1'; x.fillRect(i * s / 8, 0, s / 8, s); } x.fillStyle = 'rgba(0,0,0,.12)'; for (let i = 0; i < 8; i++) for (let j = 0; j < 8; j++) { x.beginPath(); x.arc((i + .5) * s / 8, (j + .5) * s / 8 + (i % 2) * s / 16, s / 40, 0, 6.3); x.fill(); } }
  else if (kind === 'piedra') { for (let i = 0; i < 70; i++) { x.fillStyle = `hsl(30,6%,${55 + Math.random() * 35}%)`; x.beginPath(); x.ellipse(Math.random() * s, Math.random() * s, 20 + Math.random() * 40, 15 + Math.random() * 30, Math.random() * 3, 0, 6.3); x.fill(); x.strokeStyle = 'rgba(0,0,0,.35)'; x.lineWidth = 3; x.stroke(); } }
  else if (kind === 'cesped') { x.fillStyle = '#7bbf5a'; x.fillRect(0, 0, s, s); for (let i = 0; i < 5000; i++) { x.fillStyle = `hsl(${95 + Math.random() * 20},45%,${30 + Math.random() * 25}%)`; x.fillRect(Math.random() * s, Math.random() * s, 1.5, 4); } }
  else if (kind === 'alfombra') { noise(.12, 9000); }
  else noise(.05);
  return c;
}
function patternTex(kind) {
  if (!TEX.has(kind)) { const t = new THREE.CanvasTexture(patternCanvas(kind)); t.wrapS = t.wrapT = THREE.RepeatWrapping; t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 4; TEX.set(kind, t); }
  return TEX.get(kind);
}
// Material de pared / piso: tipo + color (cualquier color; el color tiñe la textura). Repetición en metros.
export const WALL_MAT = {pintura: {}, ladrillo: {file: 'pared_diff.webp', tile: 2}, ladrillo_blanco: {pat: 'ladrillo_blanco', tile: 1.6}, concreto: {file: 'concreto_diff.webp', tile: 3},
  listones: {pat: 'listones', tile: 1.4}, panel_negro: {rough: .12, metal: .3}, azulejo: {pat: 'azulejo', tile: 1.2, rough: .2}, vidrio: {glass: true},
  papel_tapiz: {pat: 'papel_tapiz', tile: 1.2}, piedra: {pat: 'piedra', tile: 1.8, rough: .9}};
export const FLOOR_MAT = {madera_clara: {file: 'madera_diff.webp', tile: 2}, madera_oscura: {file: 'piso_diff.webp', tile: 2}, baldosa_blanca: {pat: 'baldosa_blanca', tile: 1.2, rough: .25},
  ajedrez: {pat: 'ajedrez', tile: 1.2, rough: .25}, concreto_pulido: {file: 'concreto_diff.webp', tile: 4, rough: .3}, epoxico: {rough: .15}, alfombra: {pat: 'alfombra', tile: 1, rough: 1},
  negro_brillante: {rough: .08, metal: .2}, deck: {pat: 'deck', tile: 1.6}, cesped: {pat: 'cesped', tile: 2, rough: 1}};
export function surfaceMaterial(lib, kind, color, table, tex, repX = 1, repY = 1) {
  const def = table[kind] || {};
  let map = null;
  if (def.file) { const t = tex(def.file); if (t) map = t; }
  else if (def.pat) map = patternTex(def.pat);
  if (map) { map = map.clone(); map.needsUpdate = true; map.wrapS = map.wrapT = THREE.RepeatWrapping; map.repeat.set(repX / (def.tile || 1), repY / (def.tile || 1)); }
  const hex = hexOf(color, '#cccccc');
  if (lib.toon) { const m = new THREE.MeshToonMaterial({color: vivid(hex), gradientMap: lib.grad, map, transparent: !!def.glass, opacity: def.glass ? .3 : 1}); m.userData.noOutline = true; return m; }
  return new THREE.MeshStandardMaterial({color: hex, map, roughness: def.glass ? .05 : def.rough ?? .8, metalness: def.metal ?? 0, transparent: !!def.glass, opacity: def.glass ? .28 : 1});
}

// ------------------------------------------------------------------ personaje CARICATURA (por partes; el editor completo llega en la fase 2)
export function toonPerson(lib, cfg = {}) {
  const g = new THREE.Group(); const k = lib.K(g, cfg.ropa || '#7c3aed');
  const skin = lib.base(cfg.piel || '#e0ac69'), hair = lib.base(cfg.pelo || '#2b1a10'), pants = lib.base(cfg.pantalon || '#1f2937');
  const legs = new THREE.Group(); g.add(legs); const kl = lib.K(legs, '#000');
  [-.09, .09].forEach(x => { kl.cyl(.075, .5, x, 0, 0, pants, 10); kl.rbox(.13, .07, .2, x, 0, .04, lib.base('#111111'), .03); });
  const body = new THREE.Group(); body.position.y = .5; g.add(body); const kb = lib.K(body, cfg.ropa || '#7c3aed');
  kb.rbox(.36, .5, .24, 0, 0, 0, kb.c, .1);
  [-1, 1].forEach(s => { kb.cyl(.06, .42, s * .23, .06, 0, kb.c, 10); kb.sph(.055, s * .23, .06, 0, skin); });
  kb.sph(.17, 0, .72, 0, skin); kb.sph(.18, 0, .8, -.02, hair, .75);
  [-.06, .06].forEach(x => kb.sph(.025, x, .74, .15, lib.base('#111111')));
  return {g, sit(on) { legs.rotation.x = on ? -Math.PI / 2 : 0; legs.position.set(0, on ? .45 : 0, on ? .02 : 0); body.position.y = on ? .45 : .5; },
    tick(t, i = 0) { body.position.y += Math.sin(t * 2 + i) * .0015; body.rotation.z = Math.sin(t * 1.3 + i) * .03; }};
}
