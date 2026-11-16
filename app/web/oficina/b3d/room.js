// Construye la escena 3D a partir del PLANO (JSON). Misma función para el editor, la oficina y "Negocio en vivo 3D".
import { THREE, Style, mat, glow, mesh, wallMaterial, floorMaterial } from './core.js';
import { buildItem, byId } from './catalog.js';

export const OPENINGS = {
  puerta: { name: 'Puerta sencilla', w: .95, h: 2.1 }, puerta_doble: { name: 'Puerta doble', w: 1.7, h: 2.1 }, puerta_vidrio: { name: 'Puerta de vidrio', w: 1.0, h: 2.2 },
  corrediza: { name: 'Corrediza', w: 1.8, h: 2.2 }, cortina: { name: 'Cortina metálica', w: 2.6, h: 2.6 }, vaiven: { name: 'Vaivén de cocina', w: .9, h: 1.9 },
  ventana: { name: 'Ventana', w: 1.2, h: 1.0, y: 1.1 }, ventanal: { name: 'Ventanal', w: 2.6, h: 1.6, y: .8 }, vitrina: { name: 'Vitrina de local', w: 3.0, h: 2.2, y: .1 },
};

export function buildRoom(plan, opts = {}) {
  const G = new THREE.Group(); const { w, d, h } = plan.room;
  // piso
  const fm = floorMaterial(plan.floor.mat, plan.floor.color, w, d);
  const fl = new THREE.Mesh(new THREE.PlaneGeometry(w, d), fm); fl.rotation.x = -Math.PI / 2; fl.receiveShadow = true; fl.userData.surface = { type: 'floor' }; G.add(fl);
  // zócalo exterior
  const base = new THREE.Mesh(new THREE.BoxGeometry(w + .4, .25, d + .4), mat('#0c0a10', { roughness: .4 })); base.position.y = -.13; G.add(base);
  // paredes: n (fondo) y w (izquierda) completas; s y e bajas para ver adentro (vista casa de muñecas)
  const T = .18, full = opts.allWalls;
  const walls = { n: { len: w, pos: [0, 0, -d / 2 - T / 2], rot: 0 }, s: { len: w, pos: [0, 0, d / 2 + T / 2], rot: Math.PI }, w: { len: d, pos: [-w / 2 - T / 2, 0, 0], rot: Math.PI / 2 }, e: { len: d, pos: [w / 2 + T / 2, 0, 0], rot: -Math.PI / 2 } };
  for (const [k, W] of Object.entries(walls)) {
    const conf = plan.walls[k] || plan.walls.n; const low = !full && (k === 's' || k === 'e'); const hh = low ? .3 : h;
    const m = new THREE.Mesh(new THREE.BoxGeometry(W.len + (k === 'n' || k === 's' ? 2 * T : 0), hh, T), wallMaterial(conf.mat, conf.color, W.len, hh));
    m.position.set(W.pos[0], hh / 2, W.pos[2]); m.rotation.y = W.rot; m.castShadow = !low; m.receiveShadow = true; m.userData.surface = { type: 'wall', key: k }; G.add(m);
    if (Style.toon()) { const e = new THREE.LineSegments(new THREE.EdgesGeometry(m.geometry), new THREE.LineBasicMaterial({ color: 0x140c1f })); m.add(e); }
  }
  // aberturas
  (plan.openings || []).forEach(o => G.add(buildOpening(plan, o)));
  // muros interiores (divisiones)
  (plan.inner || []).forEach(iw => G.add(buildInner(iw, h)));
  // objetos
  const objs = new THREE.Group(); G.add(objs);
  let lights = 0;
  (plan.objects || []).forEach(o => {
    const g = buildItem(o); g.position.set(o.x, 0, o.z); g.rotation.y = (o.rot || 0) * Math.PI / 180; g.userData.objId = o.id;
    g.traverse(q => { if (q.isMesh) q.userData.objId = o.id; });
    if (byId[o.item]?.light && !Style.toon() && lights < 8) { const L = new THREE.PointLight(o.color2 || '#ffd28a', 2.2, 5, 2); L.position.set(0, 2.1, 0); g.add(L); lights++; }
    objs.add(g);
  });
  G.userData.objs = objs;
  // luces
  G.add(new THREE.AmbientLight(0xfff4e8, Style.toon() ? 1.0 : .45));
  G.add(new THREE.HemisphereLight(0xffffff, 0x2a2040, Style.toon() ? .45 : .35));
  const key = new THREE.DirectionalLight(0xfff0dd, Style.toon() ? 1.3 : 1.25); key.position.set(w * .35, 12, d * .6); key.castShadow = true; key.shadow.mapSize.set(2048, 2048);
  const s = Math.max(w, d) * .7; Object.assign(key.shadow.camera, { left: -s, right: s, top: s, bottom: -s, far: 40 }); key.shadow.bias = -.0006; key.shadow.normalBias = .03; G.add(key);
  return G;
}

function buildOpening(plan, o) {
  const { w, d } = plan.room; const T = .18, def = OPENINGS[o.type] || OPENINGS.puerta; const ow = o.width || def.w, oh = def.h, y0 = def.y || 0;
  const g = new THREE.Group(); g.userData.openId = o.id;
  const along = (o.wall === 'n' || o.wall === 's') ? w : d; const p = (o.pos - .5) * along;
  if (o.wall === 'n') { g.position.set(p, 0, -d / 2 + .01); }
  if (o.wall === 's') { g.position.set(p, 0, d / 2 - .01); g.rotation.y = Math.PI; }
  if (o.wall === 'w') { g.position.set(-w / 2 + .01, 0, p); g.rotation.y = Math.PI / 2; }
  if (o.wall === 'e') { g.position.set(w / 2 - .01, 0, p); g.rotation.y = -Math.PI / 2; }
  const frame = mat('#1b1622', { roughness: .4 });
  const fr = (a, b, c, x, y) => { const k = mesh(new THREE.BoxGeometry(a, b, c), frame, x, y, .03, g); k.userData.openId = o.id; return k; };
  fr(ow + .12, .08, .08, 0, y0 + oh + .04); fr(.08, oh, .08, -ow / 2 - .02, y0 + oh / 2); fr(.08, oh, .08, ow / 2 + .02, y0 + oh / 2); if (y0 > 0) fr(ow + .12, .06, .1, 0, y0 - .03);
  let panel;
  if (['ventana', 'ventanal', 'vitrina', 'puerta_vidrio', 'corrediza'].includes(o.type)) panel = new THREE.MeshStandardMaterial({ color: 0xbfe6ff, emissive: 0x2a5a7a, emissiveIntensity: .35, transparent: true, opacity: .55, roughness: .05 });
  else if (o.type === 'cortina') panel = mat('#9ca3af', { metalness: .6, roughness: .35 });
  else panel = mat(o.color || '#5b3a26');
  const pm = new THREE.Mesh(new THREE.PlaneGeometry(ow, oh), panel); pm.position.set(0, y0 + oh / 2, .02); pm.userData.openId = o.id; g.add(pm);
  if (o.type === 'cortina') for (let i = 0; i < 12; i++) { const l = new THREE.Mesh(new THREE.PlaneGeometry(ow, .02), mat('#6b7280')); l.position.set(0, .2 + i * .2, .025); g.add(l); }
  if (o.type === 'puerta_doble' || o.type === 'corrediza') { const l = new THREE.Mesh(new THREE.PlaneGeometry(.03, oh), mat('#111')); l.position.set(0, oh / 2, .025); g.add(l); }
  if (['puerta', 'puerta_doble', 'vaiven'].includes(o.type)) mesh(new THREE.SphereGeometry(.04, 10, 8), mat('#d1d5db', { metalness: .8 }), ow / 2 - .12, 1.0, .06, g);
  return g;
}

// huella (para choques y mapa)
export function footprint(o) {
  const def = byId[o.item]; if (!def) return null; const r = (o.rot || 0) * Math.PI / 180; const c = Math.abs(Math.cos(r)), s = Math.abs(Math.sin(r));
  const w = def.w * c + def.d * s, d = def.w * s + def.d * c; return { x0: o.x - w / 2, x1: o.x + w / 2, z0: o.z - d / 2, z1: o.z + d / 2, flat: def.flat || def.hang, wall: def.wall };
}
export function collisions(plan) {
  const out = new Set(); const fs = plan.objects.map(o => [o, footprint(o)]).filter(x => x[1] && !x[1].flat && !x[1].wall);
  for (let i = 0; i < fs.length; i++) for (let j = i + 1; j < fs.length; j++) { const a = fs[i][1], b = fs[j][1]; if (a.x0 < b.x1 - .05 && a.x1 > b.x0 + .05 && a.z0 < b.z1 - .05 && a.z1 > b.z0 + .05) { out.add(fs[i][0].id); out.add(fs[j][0].id); } }
  return out;
}

// ---------- MUROS INTERIORES: {id,x1,z1,x2,z2,kind:'alto'|'media'|'vidrio', h, t, mat, color, door:{pos,width,type:'hueco'|'puerta'|'vidrio'}}
export const INNER_KINDS = { alto: { name: 'Muro completo', h: null }, media: { name: 'Media pared', h: 1.1 }, vidrio: { name: 'Muro de vidrio', h: null } };
export function innerLen(iw) { return Math.hypot(iw.x2 - iw.x1, iw.z2 - iw.z1); }
export function buildInner(iw, roomH = 3.4) {
  const g = new THREE.Group(); g.userData.innerId = iw.id;
  const L = innerLen(iw); if (L < .05) return g;
  const H = iw.kind === 'media' ? (iw.h || 1.1) : (iw.h || roomH), T = iw.t || .12;
  g.position.set((iw.x1 + iw.x2) / 2, 0, (iw.z1 + iw.z2) / 2); g.rotation.y = -Math.atan2(iw.z2 - iw.z1, iw.x2 - iw.x1);
  const glass = iw.kind === 'vidrio';
  const M = glass ? (Style.toon() ? new THREE.MeshToonMaterial({ color: iw.color || '#9bd8ff', transparent: true, opacity: .35 }) : new THREE.MeshPhysicalMaterial({ color: iw.color || '#bfe6ff', transparent: true, opacity: .3, roughness: .05 })) : wallMaterial(iw.mat || 'pintura', iw.color, L, H);
  const seg = (a, b, y0, y1) => { if (b - a < .02 || y1 - y0 < .02) return; const m = new THREE.Mesh(new THREE.BoxGeometry(b - a, y1 - y0, T), M); m.position.set((a + b) / 2 - L / 2, (y0 + y1) / 2, 0); m.castShadow = !glass; m.receiveShadow = true; m.userData.surface = { type: 'inner', id: iw.id }; m.userData.innerId = iw.id; g.add(m); if (Style.toon() && !glass) { const e = new THREE.LineSegments(new THREE.EdgesGeometry(m.geometry), new THREE.LineBasicMaterial({ color: 0x140c1f })); m.add(e); } };
  if (glass) { const fr = mat('#1b1622', { roughness: .4 }); [[0, H - .03], [0, .03]].forEach(([_, y]) => { const b = new THREE.Mesh(new THREE.BoxGeometry(L, .06, T + .02), fr); b.position.set(0, y, 0); b.userData.innerId = iw.id; b.userData.surface = { type: 'inner', id: iw.id }; g.add(b); }); }
  const d = iw.door;
  if (d && L > (d.width || .9) + .2) {
    const dw = d.width || .9, c = clamp01(d.pos ?? .5) * (L - dw) + dw / 2, dh = Math.min(2.1, H);
    seg(0, c - dw / 2, 0, H); seg(c + dw / 2, L, 0, H); if (H > dh + .05) seg(c - dw / 2, c + dw / 2, dh, H);
    if (d.type !== 'hueco') { const pm = d.type === 'vidrio' ? new THREE.MeshStandardMaterial({ color: 0xbfe6ff, transparent: true, opacity: .5 }) : mat(d.color || '#5b3a26'); const p = new THREE.Mesh(new THREE.BoxGeometry(dw - .04, dh - .02, .04), pm); p.position.set(c - L / 2, dh / 2, 0); p.userData.innerId = iw.id; g.add(p); }
    const fr = mat('#1b1622'); [[c - dw / 2, 0], [c + dw / 2, 0]].forEach(([x]) => { const f = new THREE.Mesh(new THREE.BoxGeometry(.05, dh, T + .02), fr); f.position.set(x - L / 2, dh / 2, 0); f.userData.innerId = iw.id; g.add(f); });
  } else seg(0, L, 0, H);
  return g;
}
const clamp01 = v => Math.max(0, Math.min(1, v));
