// MODO CONSTRUCTOR · prototipo funcional aprobado, integrado a Clonexa: mismo front, guardado por la API de planos por
// empresa (store.js), conexiones con las entidades REALES de la empresa y Biblioteca con la conversión del servidor.
import { THREE, Style, BRAND, PALETTE, WALLS, FLOORS, wallMaterial, floorMaterial } from './core.js';
import { Store, toast, uid, company, loadBrand, link, api, companyPath, flush, entities, connLabel, state } from './store.js';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { CATS, ITEMS, byId, buildItem, CONN, SCREENS, registerModels } from './catalog.js';
import { buildRoom, OPENINGS, collisions, footprint, INNER_KINDS, innerLen } from './room.js';
import { TEMPLATES, blankPlan } from './templates.js';
import { buildCharacter, tickCharacter, setClip, CLIPS } from './char.js';
import { loadTeam } from './team.js';

const $ = s => document.querySelector(s), $$ = s => [...document.querySelectorAll(s)];
loadBrand(); Style.mode = Store.get('style', 'human');
document.querySelectorAll('.cxEmp').forEach(e => e.textContent = company().name);
let designs = Store.get('designs', []);
let D = null;               // diseño abierto
let plan = null;            // plano en edición
let mode = 'amueblar', cat = 'barra', sel = null; // sel: {kind:'obj'|'person'|'open', id}
let drawWall = null, wallStart = null, wallPrev = null; // muros interiores
let paintTab = 'paredes', paintMat = { wall: 'ladrillo', floor: 'madera_oscura' }, paintColor = null, pendingOpening = null, allWalls = false;
const team = loadTeam();

// ================= render principal
const cv = $('#cv');
const R = new THREE.WebGLRenderer({ canvas: cv, antialias: true });
R.setPixelRatio(Math.min(devicePixelRatio, 2)); R.shadowMap.enabled = true; R.shadowMap.type = THREE.PCFSoftShadowMap;
R.toneMapping = THREE.ACESFilmicToneMapping; R.toneMappingExposure = 1.0; R.outputColorSpace = THREE.SRGBColorSpace;
const scene = new THREE.Scene(); const cam = new THREE.PerspectiveCamera(45, 1, .1, 200);
const ctr = new OrbitControls(cam, cv); ctr.enableDamping = true; ctr.maxPolarAngle = 1.38; ctr.minDistance = 3; ctr.maxDistance = 45;
ctr.mouseButtons = { LEFT: THREE.MOUSE.ROTATE, MIDDLE: THREE.MOUSE.DOLLY, RIGHT: THREE.MOUSE.PAN };
let shell = null; const objG = new THREE.Group(), peopleG = new THREE.Group(); scene.add(objG, peopleG);
const objMap = new Map(), peopleMap = new Map();
const selBox = new THREE.Box3Helper(new THREE.Box3(), 0x38bdf8); selBox.visible = false; scene.add(selBox);
const colBoxes = new THREE.Group(); scene.add(colBoxes);
function resize() { const w = innerWidth, h = innerHeight; R.setSize(w, h, false); cam.aspect = w / h; cam.updateProjectionMatrix(); }
addEventListener('resize', resize);

// ================= miniaturas (render aparte)
const TR = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true, alpha: false }); TR.setSize(240, 190); TR.outputColorSpace = THREE.SRGBColorSpace; TR.toneMapping = THREE.ACESFilmicToneMapping; TR.shadowMap.enabled = true;
const thumbCache = {};
function thumbScene() { const s = new THREE.Scene(); s.background = new THREE.Color(Style.toon() ? 0x2a1f3d : 0x1a1424); s.add(new THREE.AmbientLight(0xffffff, .9)); s.add(new THREE.HemisphereLight(0xffffff, 0x2a2040, .5)); const k = new THREE.DirectionalLight(0xffffff, 1.6); k.position.set(3, 6, 5); s.add(k); return s; }
function itemThumb(id) {
  const key = Style.mode + id; if (thumbCache[key]) return thumbCache[key];
  const md = byId[id]; if (md?.thumb) return md.thumb;
  if (md?.model && !md.ready) { md.whenReady(() => { delete thumbCache[key]; if (mode === 'amueblar' && !$('#editor').classList.contains('hide')) renderDock(); if ($('#lib').classList.contains('show')) renderLib(); }); }
  const s = thumbScene(); const g = buildItem({ item: id }); s.add(g);
  const b = new THREE.Box3().setFromObject(g); const c = b.getCenter(new THREE.Vector3()); const z = b.getSize(new THREE.Vector3()); const r = Math.max(z.x, z.y, z.z, .6);
  const c2 = new THREE.PerspectiveCamera(32, 240 / 190, .05, 100); c2.position.set(c.x + r * 1.05, c.y + r * .85, c.z + r * 1.5); c2.lookAt(c);
  TR.setSize(240, 190); TR.render(s, c2); const u = TR.domElement.toDataURL('image/jpeg', .85); thumbCache[key] = u; return u;
}
function planThumb(p, w = 480, h = 270) {
  TR.setSize(w, h); const s = new THREE.Scene(); s.background = new THREE.Color(Style.toon() ? 0x2a1f3d : 0x0c0910); s.add(buildRoom(p));
  const c2 = new THREE.PerspectiveCamera(42, w / h, .1, 200); const m = Math.max(p.room.w, p.room.d); c2.position.set(p.room.w * .12, m * .78, p.room.d * .95); c2.lookAt(0, 0, -.4);
  TR.render(s, c2); const u = TR.domElement.toDataURL('image/jpeg', .8); TR.setSize(240, 190); return u;
}
async function personThumb(p) {
  const key = Style.mode + JSON.stringify(Style.mode === 'human' ? p.human : p.toon); if (thumbCache[key]) return thumbCache[key];
  const s = thumbScene(); const g = await buildCharacter(p, Style.mode, 'idle'); s.add(g); tickCharacter(g, .01, 0);
  const c2 = new THREE.PerspectiveCamera(30, 240 / 200, .05, 50); c2.position.set(0, 1.2, 4.2); c2.lookAt(0, .95, 0);
  TR.setSize(240, 200); TR.render(s, c2); const u = TR.domElement.toDataURL('image/jpeg', .85); TR.setSize(240, 190); thumbCache[key] = u; return u;
}

// ================= pantalla de inicio
function renderStart() {
  $('#start').classList.remove('hide'); $('#editor').classList.add('hide');
  const sp = $('#styPick'); sp.innerHTML = '';
  [['human', 'Humano'], ['toon', 'Caricatura']].forEach(([k, n]) => { const prev = Style.mode; Style.mode = k; const u = planThumb(TEMPLATES.bar.make(), 160, 100); Style.mode = prev;
    const b = document.createElement('button'); b.className = k === Style.mode ? 'sel' : ''; b.innerHTML = `<img src="${u}"><span>${n}</span>`; b.onclick = () => { Style.mode = k; Store.set('style', k); renderStart(); }; sp.appendChild(b); });
  const tp = $('#tpls'); tp.innerHTML = '';
  Object.entries(TEMPLATES).forEach(([k, t]) => { const p = t.make(); const card = document.createElement('div'); card.className = 'tc'; card.innerHTML = `<div class="im"><img src="${planThumb(p)}"><span class="use">Usar plantilla</span></div><b>${t.icon} ${t.name}</b><small>${t.desc}</small>`; card.onclick = () => newDesign(t.make(), t.name); tp.appendChild(card); });
  const bl = document.createElement('div'); bl.className = 'blank'; bl.innerHTML = `<div class="big">✏️</div><b style="font-size:18px">Desde cero</b><small style="color:#a39cb0">Pon las medidas de tu local (m)</small><div style="display:flex;gap:8px;align-items:center"><input type="number" id="bw" value="14" min="4" max="40"> × <input type="number" id="bd" value="10" min="4" max="40"></div><button class="pill pk" id="bgo">Empezar</button>`; tp.appendChild(bl);
  $('#bgo').onclick = () => newDesign(blankPlan(+$('#bw').value || 14, +$('#bd').value || 10), 'Mi local');
  const mine = $('#mine'); mine.innerHTML = ''; $('#mineWrap').classList.toggle('hide', !designs.length);
  designs.slice().sort((a, b) => b.updated - a.updated).forEach(d => { const el = document.createElement('div'); el.className = 'dc'; el.innerHTML = `<img src="${d.thumb || ''}"><div><b>${d.name}</b><small>Versión ${d.version || 0} · ${new Date(d.updated).toLocaleString('es-CO')}</small><span class="chip ${d.live ? 'live' : 'draft'}">${d.live ? '● En vivo' : 'Borrador'}</span></div><button class="x" title="Borrar">🗑</button>`;
    el.onclick = e => { if (e.target.classList.contains('x')) { if (confirm('¿Borrar el diseño "' + d.name + '"?')) { designs = designs.filter(x => x.id !== d.id); Store.set('designs', designs); renderStart(); } return; } openDesign(d.id); }; mine.appendChild(el); });
}
// "Mesa 3", "Caja principal", "Puesto 5"... de las plantillas -> la entidad real de ESA empresa del mismo tipo (por número o la
// siguiente libre). Si la empresa no tiene esa entidad, el objeto queda sin conectar (aparece en "Sin conectar").
function realConns(p) {
  const ents = entities(), used = new Set();
  (p.objects || []).forEach(o => {
    const kind = byId[o.item]?.conn; const ph = o.conn; o.conn = ''; if (!kind || !ph) return;
    const list = ents[kind] || []; const n = parseInt((String(ph).match(/(\d+)\s*$/) || [])[1], 10);
    let e = Number.isFinite(n) ? list[n - 1] : null; if (e && used.has(e.id)) e = null;
    if (!e && !Number.isFinite(n)) e = list.find(x => !used.has(x.id));
    if (e) { o.conn = e.id; used.add(e.id); }
  });
  (p.objects || []).forEach(o => { if (!o.conn) delete o.conn; });
  return p;
}
function newDesign(p, name) { realConns(p); (p.objects || []).forEach(o => { if (o.item === 'neon') { o.text = company().neon; o.color = BRAND[0]; } }); const d = { id: uid(), name, plan: p, version: 0, live: false, versions: [], updated: Date.now() }; designs.push(d); Store.set('designs', designs); openDesign(d.id); }
function importFile(f) { const r = new FileReader(); r.onload = async () => { try { const res = await api(companyPath() + '/importar', { method: 'POST', body: r.result, headers: { 'Content-Type': 'application/json' } }); const p = res.plan; newDesign(p, (p.name || 'Importado') + ' (importado)'); toast('Plano importado'); } catch (e) { toast(e.message || 'Ese archivo no es un plano válido de Clonexa', 'err'); } }; r.readAsText(f); }
$('#impFile').onchange = e => e.target.files[0] && importFile(e.target.files[0]);
$('#impFile2').onchange = e => { $('#menu').classList.remove('show'); e.target.files[0] && importFile(e.target.files[0]); };

// ================= abrir diseño
const hist = { u: [], r: [] };
function openDesign(id) {
  D = designs.find(d => d.id === id); plan = JSON.parse(JSON.stringify(D.plan)); plan.people = plan.people || []; plan.inner = plan.inner || [];
  hist.u = [JSON.stringify(plan)]; hist.r = []; sel = null;
  $('#start').classList.add('hide'); $('#editor').classList.remove('hide'); $('#nameIn').value = D.name; $('#styleSel').value = Style.mode;
  resize(); rebuildAll(); fitView(); setMode('amueblar'); cv.focus();
}
function fitView() { const m = Math.max(plan.room.w, plan.room.d); cam.position.set(plan.room.w * .15, m * .82, plan.room.d * 1.0 + 2); ctr.target.set(0, 0, -.3); ctr.update(); }
function rebuildShell() { if (shell) scene.remove(shell); shell = buildRoom({ ...plan, objects: [] }, { allWalls }); scene.add(shell); scene.background = new THREE.Color(Style.toon() ? 0x2a1f3d : 0x07050a); R.toneMappingExposure = Style.toon() ? 1.05 : 1.0; }
function objGroup(o) { const g = buildItem(o); g.position.set(o.x, 0, o.z); g.rotation.y = (o.rot || 0) * Math.PI / 180; g.traverse(q => { if (q.isMesh) q.userData.objId = o.id; }); if (byId[o.item]?.light && !Style.toon()) { const L = new THREE.PointLight(o.color2 || '#ffd28a', 2.0, 5, 2); L.position.set(0, 2.1, 0); g.add(L); } return g; }
function addObj(o) { const g = objGroup(o); objMap.set(o.id, g); objG.add(g); }
function refreshObj(o) { const old = objMap.get(o.id); if (old) objG.remove(old); addObj(o); }
async function addPerson(pp) { const p = team.find(t => t.id === pp.pid); if (!p) return; const g = await buildCharacter(p, Style.mode, pp.clip || 'idle'); g.position.set(pp.x, 0, pp.z); g.rotation.y = (pp.rot || 0) * Math.PI / 180; g.userData.phase = Math.random() * 5; g.traverse(q => { if (q.isMesh) q.userData.personId = pp.id; }); const old = peopleMap.get(pp.id); if (old) peopleG.remove(old); peopleMap.set(pp.id, g); peopleG.add(g); }
function rebuildAll() { rebuildShell(); objG.clear(); objMap.clear(); plan.objects.forEach(addObj); peopleG.clear(); peopleMap.clear(); plan.people.forEach(addPerson); afterChange(false); }

// ================= cambios, historial y guardado
let saveT = null;
function afterChange(push = true) {
  if (push) { hist.u.push(JSON.stringify(plan)); if (hist.u.length > 80) hist.u.shift(); hist.r = []; }
  $('#tUndo').disabled = hist.u.length < 2; $('#tRedo').disabled = !hist.r.length;
  // choques
  colBoxes.clear(); const col = collisions(plan); col.forEach(id => { const g = objMap.get(id); if (g) { const h = new THREE.Box3Helper(new THREE.Box3().setFromObject(g), 0xef4444); colBoxes.add(h); } });
  drawMap(); updateSel(); if (mode === 'conectar' || mode === 'construir' || mode === 'personajes') renderDock();
  $('#saveSt').textContent = '● guardando…'; $('#saveSt').style.color = '#fde68a';
  clearTimeout(saveT); saveT = setTimeout(save, 500);
}
function save() { D.plan = JSON.parse(JSON.stringify(plan)); D.name = $('#nameIn').value || D.name; D.updated = Date.now(); try { D.thumb = planThumb(plan, 320, 180); } catch (e) { } Store.set('designs', designs); $('#saveSt').textContent = '● guardado'; $('#saveSt').style.color = '#86efac'; }
function undo() { if (hist.u.length < 2) return; hist.r.push(hist.u.pop()); plan = JSON.parse(hist.u[hist.u.length - 1]); sel = null; rebuildAll(); }
function redo() { if (!hist.r.length) return; const s = hist.r.pop(); hist.u.push(s); plan = JSON.parse(s); sel = null; rebuildAll(); }
$('#nameIn').oninput = () => { clearTimeout(saveT); saveT = setTimeout(save, 500); };

// ================= modos y dock
const HINT = {
  construir: 'Muros: elige el tipo y toca dos puntos del piso (inicio y fin) · Alt = ángulo libre · Esc cancela · toca un muro para cambiarlo, ponerle puerta o borrarlo · puertas/ventanas: elige una y toca una pared del borde',
  amueblar: 'Arrastra del catálogo al local (o tócalo y aparece en el centro) · arrastra para mover · <b>R</b> girar · <b>Supr</b> borrar · Alt = sin cuadrícula',
  pintar: 'Elige material y color, y toca una pared o el piso para pintarlo',
  personajes: 'Pon a tu equipo en el local y elige qué está haciendo · el aspecto se cambia en el Editor de personajes',
  conectar: 'Toca una mesa, puesto, caja o pantalla y elige con qué dato real se conecta',
};
function setMode(m) { mode = m; pendingOpening = null; drawWall = null; wallStart = null; clearWallPrev(); if (m === 'pintar' || (m === 'construir' && sel?.kind !== 'open' && sel?.kind !== 'inner') || (m !== 'construir' && (sel?.kind === 'inner' || sel?.kind === 'open')) || (m === 'personajes' && sel?.kind === 'obj')) { sel = null; renderProp(); } $$('#modes button').forEach(b => b.classList.toggle('sel', b.dataset.m === m)); $('#hint').innerHTML = HINT[m]; renderDock(); updateSel(); }
$$('#modes button').forEach(b => b.onclick = () => setMode(b.dataset.m));
function renderDock() {
  const dk = $('#dock');
  if (mode === 'amueblar') {
    dk.innerHTML = `<div class="cats">${CATS.map(([k, n]) => `<button data-c="${k}" class="${k === cat ? 'sel' : ''}">${n}</button>`).join('')}</div><div class="strip" id="strip"></div>`;
    dk.querySelectorAll('.cats button').forEach(b => b.onclick = () => { cat = b.dataset.c; renderDock(); });
    const st = $('#strip'); ITEMS.filter(i => i.cat === cat).forEach(i => { const b = document.createElement('button'); b.className = 'it'; b.dataset.id = i.id; b.innerHTML = `<img src="${itemThumb(i.id)}"><span>${i.name}</span>`; b.onpointerdown = e => startDockDrag(e, i.id); st.appendChild(b); });
  }
  if (mode === 'pintar') {
    const list = paintTab === 'paredes' ? WALLS : FLOORS; const cur = paintTab === 'paredes' ? paintMat.wall : paintMat.floor;
    dk.innerHTML = `<div class="cats"><button data-t="paredes" class="${paintTab === 'paredes' ? 'sel' : ''}">🧱 Paredes</button><button data-t="piso" class="${paintTab === 'piso' ? 'sel' : ''}">▦ Piso</button><span style="flex:1"></span>${paintTab === 'paredes' ? '<button id="allW">Aplicar a todas las paredes</button>' : '<button id="applyF">Aplicar al piso</button>'}</div>
      <div class="row" style="margin-bottom:10px"><b style="font-size:13px">Color:</b><div class="sw" id="pcol"></div><input type="color" id="pcus" value="${paintColor || '#ffffff'}" title="Otro color" style="width:38px;height:30px;padding:0;border-radius:8px"><button class="pill" id="pdef" style="padding:6px 10px">Color original</button></div><div class="mats" id="mats"></div>`;
    dk.querySelectorAll('.cats button[data-t]').forEach(b => b.onclick = () => { paintTab = b.dataset.t; renderDock(); });
    const pc = $('#pcol'); [...BRAND, ...PALETTE.slice(0, 12)].forEach(c => { const b = document.createElement('button'); b.style.background = c; b.className = c === paintColor ? 's' : ''; b.onclick = () => { paintColor = c; renderDock(); }; pc.appendChild(b); });
    $('#pcus').oninput = e => { paintColor = e.target.value; }; $('#pdef').onclick = () => { paintColor = null; renderDock(); };
    const ms = $('#mats'); Object.entries(list).forEach(([k, v]) => { const b = document.createElement('button'); b.className = 'mt' + (k === cur ? ' sel' : ''); const c = document.createElement('canvas'); c.width = 104; c.height = 62; const x = c.getContext('2d'); const m = paintTab === 'paredes' ? wallMaterial(k, paintColor || v.def, 3, 3) : floorMaterial(k, paintColor || v.def, 2.5, 2.5); if (m.map && m.map.image) x.drawImage(m.map.image, 0, 0, 104, 62); else { x.fillStyle = paintColor || v.def; x.fillRect(0, 0, 104, 62); } b.appendChild(c); b.insertAdjacentHTML('beforeend', `<span>${v.name}</span>`); b.onclick = () => { if (paintTab === 'paredes') paintMat.wall = k; else paintMat.floor = k; renderDock(); }; ms.appendChild(b); });
    const aw = $('#allW'); if (aw) aw.onclick = () => { ['n', 's', 'e', 'w'].forEach(k => plan.walls[k] = { mat: paintMat.wall, color: paintColor || WALLS[paintMat.wall].def }); rebuildShell(); afterChange(); toast('Paredes pintadas'); };
    const af = $('#applyF'); if (af) af.onclick = () => { plan.floor = { mat: paintMat.floor, color: paintColor || FLOORS[paintMat.floor].def }; rebuildShell(); afterChange(); toast('Piso cambiado'); };
  }
  if (mode === 'construir') {
    dk.innerHTML = `<div class="row" style="margin-bottom:10px"><b>Local:</b><label>Ancho <input type="range" id="rw" min="6" max="30" step=".5" value="${plan.room.w}"> <span id="rwv">${plan.room.w} m</span></label><label>Fondo <input type="range" id="rd" min="5" max="24" step=".5" value="${plan.room.d}"> <span id="rdv">${plan.room.d} m</span></label><label>Alto <input type="range" id="rh" min="2.6" max="6" step=".1" value="${plan.room.h}"> <span id="rhv">${plan.room.h} m</span></label><label><input type="checkbox" id="aw" ${allWalls ? 'checked' : ''}> Ver paredes del frente</label></div>
      <div class="ey" style="margin-bottom:6px">Muros y divisiones · elige y toca dos puntos del piso</div><div class="strip" id="inw" style="margin-bottom:10px"></div>
      <div class="ey" style="margin-bottom:6px">Puertas y ventanas (paredes del borde) · elige una y toca la pared</div><div class="strip" id="opn"></div>`;
    const upd = () => { plan.room.w = +$('#rw').value; plan.room.d = +$('#rd').value; plan.room.h = +$('#rh').value; $('#rwv').textContent = plan.room.w + ' m'; $('#rdv').textContent = plan.room.d + ' m'; $('#rhv').textContent = plan.room.h + ' m'; clampAll(); rebuildShell(); plan.objects.forEach(o => { const g = objMap.get(o.id); if (g) g.position.set(o.x, 0, o.z); }); drawMap(); };
    ['#rw', '#rd', '#rh'].forEach(s => { $(s).oninput = upd; $(s).onchange = () => afterChange(); });
    $('#aw').onchange = e => { allWalls = e.target.checked; rebuildShell(); };
    const iwc = $('#inw'); Object.entries(INNER_KINDS).forEach(([k, v]) => { const b = document.createElement('button'); b.className = 'it' + (drawWall === k ? ' sel' : ''); b.style.cursor = 'pointer'; b.innerHTML = `<div style="height:70px;display:flex;align-items:center;justify-content:center"><svg width="70" height="54" viewBox="0 0 70 54"><rect x="6" y="${k === 'media' ? 26 : 6}" width="58" height="${k === 'media' ? 24 : 44}" rx="3" fill="${k === 'vidrio' ? '#9bd8ff88' : '#e7e2f0'}" stroke="${k === 'vidrio' ? '#38bdf8' : '#8a4130'}" stroke-width="3"/>${k === 'alto' ? '<path d="M6 20H64M6 35H64M25 6V20M45 20V35M25 35V50" stroke="#8a4130" stroke-width="2"/>' : ''}</svg></div><span>${v.name}</span>`; b.onclick = () => { drawWall = drawWall === k ? null : k; pendingOpening = null; wallStart = null; clearWallPrev(); renderDock(); $('#hint').innerHTML = drawWall ? `Toca el <b>inicio</b> del ${v.name.toLowerCase()} en el piso` : HINT.construir; }; iwc.appendChild(b); });
    const op = $('#opn'); Object.entries(OPENINGS).forEach(([k, v]) => { const b = document.createElement('button'); b.className = 'it' + (pendingOpening === k ? ' sel' : ''); b.style.cursor = 'pointer'; b.innerHTML = `<div style="height:70px;display:flex;align-items:center;justify-content:center;font-size:36px">${k.startsWith('ventan') || k === 'vitrina' ? '🪟' : k === 'cortina' ? '🏪' : '🚪'}</div><span>${v.name}</span>`; b.onclick = () => { pendingOpening = pendingOpening === k ? null : k; drawWall = null; wallStart = null; clearWallPrev(); renderDock(); $('#hint').innerHTML = pendingOpening ? `Ahora toca una pared para poner: <b>${v.name}</b>` : HINT.construir; }; op.appendChild(b); });
  }
  if (mode === 'personajes') {
    dk.innerHTML = `<div class="row" style="margin-bottom:8px"><div class="ey">Tu equipo · toca para ponerlo en el local</div><a class="pill" href="${link('personajes')}" style="margin-left:auto">✏️ Editor de personajes</a></div><div class="team" id="teamS"></div>`;
    const ts = $('#teamS'); team.forEach(async p => { const b = document.createElement('button'); b.className = 'tm'; const placed = plan.people.filter(x => x.pid === p.id).length; b.innerHTML = `<img><span>${p.name}<br><small style="color:#a39cb0">${p.role}${placed ? ' · en el local' : ''}</small></span>`; b.onclick = () => placePerson(p); ts.appendChild(b); b.querySelector('img').src = await personThumb(p); });
  }
  if (mode === 'conectar') {
    const conns = plan.objects.filter(o => byId[o.item]?.conn); const used = new Set(conns.map(o => o.conn).filter(Boolean));
    const sinObj = Object.values(entities()).flatMap(l => l.filter(e => !used.has(e.id)).slice(0, 4).map(e => e.label));
    dk.innerHTML = `<div class="row"><div><div class="ey">Objetos conectables</div><b style="font-size:20px">${conns.filter(o => o.conn).length} de ${conns.length}</b> conectados</div>
      <div style="flex:1;min-width:260px"><div class="ey">Sin conectar</div><div style="display:flex;gap:6px;flex-wrap:wrap;margin-top:4px">${conns.filter(o => !o.conn).map(o => `<button class="pill" data-id="${o.id}">⚠ ${byId[o.item].name}</button>`).join('') || '<span style="color:#86efac">Todo conectado ✓</span>'}</div></div>
      <div style="flex:1;min-width:260px"><div class="ey">Datos reales libres</div><div style="color:#cbc5d6;font-size:13px;margin-top:4px">${sinObj.slice(0, 10).join(' · ')}</div></div></div>`;
    dk.querySelectorAll('button[data-id]').forEach(b => b.onclick = () => select({ kind: 'obj', id: b.dataset.id }, true));
  }
}

// ================= colocar / arrastrar desde el dock
let ghost = null, ghostId = null, dockStart = null;
function startDockDrag(e, id) { e.preventDefault(); dockStart = { x: e.clientX, y: e.clientY, id }; ghostId = id; addEventListener('pointermove', dockMove); addEventListener('pointerup', dockUp, { once: true }); }
function dockMove(e) {
  if (!dockStart) return; if (!ghost && Math.hypot(e.clientX - dockStart.x, e.clientY - dockStart.y) < 8) return;
  if (!ghost) { ghost = buildItem({ item: ghostId }); ghost.traverse(q => { if (q.isMesh) { q.material = q.material.clone(); q.material.transparent = true; q.material.opacity = .6; } }); scene.add(ghost); }
  const p = floorPoint(e.clientX, e.clientY); if (p) { const s = snapPos(ghostId, p.x, p.z, e.altKey); ghost.position.set(s.x, 0, s.z); ghost.rotation.y = (s.rot ?? 0) * Math.PI / 180; ghost.visible = true; } else ghost.visible = false;
}
function dockUp(e) {
  removeEventListener('pointermove', dockMove); const id = ghostId;
  if (ghost) { const vis = ghost.visible; const pos = ghost.position.clone(), rot = ghost.rotation.y * 180 / Math.PI; scene.remove(ghost); ghost = null; if (vis && e.target === cv) placeItem(id, pos.x, pos.z, rot); }
  else placeItem(id, ctr.target.x, ctr.target.z, null);
  dockStart = null; ghostId = null;
}
function placeItem(id, x, z, rot) { const s = snapPos(id, x, z, false); const o = { id: uid(), item: id, x: s.x, z: s.z, rot: rot ?? s.rot ?? 0 }; const def = byId[id]; if (def.props?.includes('text')) o.text = 'Tu texto'; plan.objects.push(o); addObj(o); select({ kind: 'obj', id: o.id }); afterChange(); toast(def.name + ' agregado'); }
function placePerson(p) { const n = plan.people.length; const pp = { id: uid(), pid: p.id, x: clamp(ctr.target.x + ((n % 4) - 1.5) * 1.0, -plan.room.w / 2 + .5, plan.room.w / 2 - .5), z: clamp(ctr.target.z + (Math.floor(n / 4) % 3) * 1.0 + .6, -plan.room.d / 2 + .5, plan.room.d / 2 - .5), rot: 0, clip: 'idle' }; plan.people.push(pp); addPerson(pp).then(() => { select({ kind: 'person', id: pp.id }); }); afterChange(); toast(p.name + ' está en el local'); }

// ================= geometría de interacción
const ray = new THREE.Raycaster(), mouse = new THREE.Vector2(), floorPlane = new THREE.Plane(new THREE.Vector3(0, 1, 0), 0);
function setMouse(x, y) { const r = cv.getBoundingClientRect(); mouse.set(((x - r.left) / r.width) * 2 - 1, -((y - r.top) / r.height) * 2 + 1); ray.setFromCamera(mouse, cam); }
function floorPoint(x, y) { setMouse(x, y); const p = new THREE.Vector3(); return ray.ray.intersectPlane(floorPlane, p) ? p : null; }
function clamp(v, a, b) { return Math.max(a, Math.min(b, v)); }
function snapPos(id, x, z, free) {
  const def = byId[id]; const { w, d } = plan.room; let rot = null;
  if (!free) { x = Math.round(x * 10) / 10; z = Math.round(z * 10) / 10; }
  if (def?.wall) { const dn = z + d / 2, dw = x + w / 2, ds = d / 2 - z, de = w / 2 - x; const m = Math.min(dn, dw, ds, de); if (m === dn) { z = -d / 2 + .12; rot = 0; } else if (m === dw) { x = -w / 2 + .12; rot = 90; } else if (m === de) { x = w / 2 - .12; rot = -90; } else { z = d / 2 - .12; rot = 180; } }
  const hw = (def?.w || .5) / 2 * .5; x = clamp(x, -w / 2 + hw, w / 2 - hw); z = clamp(z, -d / 2 + hw, d / 2 - hw); return { x, z, rot };
}
function clampAll() { plan.objects.forEach(o => { const s = snapPos(o.item, o.x, o.z, true); o.x = s.x; o.z = s.z; if (s.rot != null && byId[o.item]?.wall) o.rot = s.rot; }); }

// ================= puntero sobre el lienzo
let drag = null;
cv.addEventListener('pointerdown', e => {
  if (e.button !== 0) return; setMouse(e.clientX, e.clientY);
  if (mode === 'construir' && drawWall) { const p = floorPoint(e.clientX, e.clientY); if (!p) return; const q = wallSnap(p, e.altKey); if (!wallStart) { wallStart = q; $('#hint').innerHTML = 'Ahora toca el <b>final</b> del muro (Esc cancela)'; } else { if (Math.hypot(q.x - wallStart.x, q.z - wallStart.z) > .3) { const iw = { id: uid(), x1: wallStart.x, z1: wallStart.z, x2: q.x, z2: q.z, kind: drawWall, mat: drawWall === 'vidrio' ? 'vidrio' : 'pintura', color: drawWall === 'vidrio' ? '#bfe6ff' : '#e7e2f0' }; plan.inner.push(iw); rebuildShell(); afterChange(); toast(INNER_KINDS[drawWall].name + ' de ' + innerLen(iw).toFixed(1) + ' m'); wallStart = q; $('#hint').innerHTML = 'Sigue tocando para encadenar muros · <b>Esc</b> o el botón del muro para terminar'; } } return; }
  const targets = (mode === 'pintar' || (mode === 'construir' && pendingOpening)) ? [shell] : [objG, peopleG, shell];
  const hits = ray.intersectObjects(targets, true).filter(h => h.object.visible && !h.object.userData.outline);
  const h = hits[0]; if (!h) { select(null); return; }
  const ud = h.object.userData;
  if (mode === 'pintar') { const surf = findSurface(h.object); if (surf) { paintSurface(surf); e.preventDefault(); } return; }
  if (mode === 'construir') { if (pendingOpening) { const surf = findSurface(h.object); if (surf?.type === 'wall') { addOpening(surf.key, h.point); } return; } const oid = findUp(h.object, 'openId'); if (oid) { select({ kind: 'open', id: oid }); return; } const iid = findUp(h.object, 'innerId'); if (iid) { select({ kind: 'inner', id: iid }); beginDrag(e, 'inner', iid); return; } }
  if (ud.objId && mode !== 'personajes') { select({ kind: 'obj', id: ud.objId }); if (mode === 'amueblar' || mode === 'conectar') beginDrag(e, 'obj', ud.objId); return; }
  if (ud.personId) { select({ kind: 'person', id: ud.personId }); beginDrag(e, 'person', ud.personId); return; }
  select(null);
});
function findUp(o, key) { while (o) { if (o.userData[key]) return o.userData[key]; o = o.parent; } return null; }
function findSurface(o) { while (o) { if (o.userData.surface) return o.userData.surface; o = o.parent; } return null; }
function beginDrag(e, kind, id) { const p = floorPoint(e.clientX, e.clientY); if (kind === 'inner') { const w = plan.inner.find(o => o.id === id); if (!p || !w) return; drag = { kind, id, p0: p.clone(), w0: { ...w }, moved: false }; ctr.enabled = false; cv.setPointerCapture(e.pointerId); return; } const rec = kind === 'obj' ? plan.objects.find(o => o.id === id) : plan.people.find(o => o.id === id); if (!p || !rec) return; drag = { kind, id, dx: rec.x - p.x, dz: rec.z - p.z, moved: false }; ctr.enabled = false; cv.setPointerCapture(e.pointerId); }
cv.addEventListener('pointermove', e => {
  if (mode === 'construir' && drawWall && wallStart) { const p = floorPoint(e.clientX, e.clientY); if (p) showWallPrev(wallStart, wallSnap(p, e.altKey)); }
  if (drag?.kind === 'inner') { const p = floorPoint(e.clientX, e.clientY); if (!p) return; const dx = Math.round((p.x - drag.p0.x) * 10) / 10, dz = Math.round((p.z - drag.p0.z) * 10) / 10; const w = plan.inner.find(o => o.id === drag.id); Object.assign(w, { x1: drag.w0.x1 + dx, x2: drag.w0.x2 + dx, z1: drag.w0.z1 + dz, z2: drag.w0.z2 + dz }); drag.moved = true; rebuildShell(); updateSel(); drawMap(); return; }
  if (!drag) return; const p = floorPoint(e.clientX, e.clientY); if (!p) return; drag.moved = true;
  if (drag.kind === 'obj') { const o = plan.objects.find(x => x.id === drag.id); const s = snapPos(o.item, p.x + drag.dx, p.z + drag.dz, e.altKey); o.x = s.x; o.z = s.z; if (s.rot != null) o.rot = s.rot; const g = objMap.get(o.id); g.position.set(o.x, 0, o.z); g.rotation.y = o.rot * Math.PI / 180; }
  else { const o = plan.people.find(x => x.id === drag.id); o.x = clamp(p.x + drag.dx, -plan.room.w / 2 + .3, plan.room.w / 2 - .3); o.z = clamp(p.z + drag.dz, -plan.room.d / 2 + .3, plan.room.d / 2 - .3); peopleMap.get(o.id)?.position.set(o.x, 0, o.z); }
  updateSel(); drawMap();
});
cv.addEventListener('pointerup', e => { if (drag) { const m = drag.moved; drag = null; ctr.enabled = true; if (m) afterChange(); } });

// ================= muros interiores
function wallSnap(p, free) { const { w, d } = plan.room; let x = Math.max(-w / 2, Math.min(w / 2, p.x)), z = Math.max(-d / 2, Math.min(d / 2, p.z)); if (!free) { x = Math.round(x * 10) / 10; z = Math.round(z * 10) / 10; if (wallStart) { const dx = Math.abs(x - wallStart.x), dz = Math.abs(z - wallStart.z); if (dx > dz * 2.4) z = wallStart.z; else if (dz > dx * 2.4) x = wallStart.x; } } return { x, z }; }
function clearWallPrev() { if (wallPrev) { scene.remove(wallPrev); wallPrev = null; } }
function showWallPrev(a, b) { clearWallPrev(); const L = Math.hypot(b.x - a.x, b.z - a.z); if (L < .05) return; const H = drawWall === 'media' ? 1.1 : plan.room.h; wallPrev = new THREE.Mesh(new THREE.BoxGeometry(L, H, .12), new THREE.MeshBasicMaterial({ color: 0x38bdf8, transparent: true, opacity: .45 })); wallPrev.position.set((a.x + b.x) / 2, H / 2, (a.z + b.z) / 2); wallPrev.rotation.y = -Math.atan2(b.z - a.z, b.x - a.x); scene.add(wallPrev); $('#hint').innerHTML = `Largo: <b>${L.toFixed(1)} m</b> · toca para terminar este muro · Alt = ángulo libre · Esc cancela`; }
addEventListener('keydown', e => { if (e.key === 'Escape' && drawWall) { drawWall = null; wallStart = null; clearWallPrev(); renderDock(); $('#hint').innerHTML = HINT.construir; } });

// ================= pintar / aberturas
function paintSurface(s) {
  if (s.type === 'inner') { if (paintTab !== 'paredes') { paintTab = 'paredes'; renderDock(); toast('Cambié a Paredes: elige el material y vuelve a tocar el muro'); return; } const iw = plan.inner.find(x => x.id === s.id); if (iw) { if (iw.kind === 'vidrio') { iw.color = paintColor || '#bfe6ff'; } else { iw.mat = paintMat.wall === 'vidrio' ? 'pintura' : paintMat.wall; iw.color = paintColor || WALLS[iw.mat].def; } rebuildShell(); afterChange(); toast('Muro pintado'); } return; }
  if (s.type === 'wall' && paintTab !== 'paredes') { paintTab = 'paredes'; renderDock(); toast('Cambié a Paredes: elige el material y vuelve a tocar la pared'); return; }
  if (s.type === 'floor' && paintTab !== 'piso') { paintTab = 'piso'; renderDock(); toast('Cambié a Piso: elige el material y vuelve a tocar el piso'); return; }
  if (s.type === 'wall') { plan.walls[s.key] = { mat: paintMat.wall, color: paintColor || WALLS[paintMat.wall].def }; toast('Pared pintada: ' + WALLS[paintMat.wall].name); }
  else { plan.floor = { mat: paintMat.floor, color: paintColor || FLOORS[paintMat.floor].def }; toast('Piso: ' + FLOORS[paintMat.floor].name); }
  rebuildShell(); afterChange();
}
function addOpening(wall, pt) { const { w, d } = plan.room; const along = (wall === 'n' || wall === 's') ? (pt.x + w / 2) / w : (pt.z + d / 2) / d; const o = { id: uid(), wall, pos: clamp(along, .08, .92), type: pendingOpening }; plan.openings.push(o); pendingOpening = null; rebuildShell(); select({ kind: 'open', id: o.id }); afterChange(); renderDock(); $('#hint').innerHTML = HINT.construir; toast(OPENINGS[o.type].name + ' agregada'); }

// ================= selección y panel derecho
function select(s, focus) {
  sel = s; if (s?.kind === 'obj' && focus) { const o = plan.objects.find(x => x.id === s.id); if (o) { ctr.target.set(o.x, 0, o.z); ctr.update(); } }
  updateSel(); renderProp();
}
function selObject() { if (!sel) return null; if (sel.kind === 'obj') return objMap.get(sel.id); if (sel.kind === 'person') return peopleMap.get(sel.id); if (sel.kind === 'open') return shell?.children.find(c => c.userData.openId === sel.id); if (sel.kind === 'inner') return shell?.children.find(c => c.userData.innerId === sel.id); return null; }
function updateSel() { const g = selObject(); if (!g) { selBox.visible = false; $('#handles').classList.add('hide'); return; } selBox.box.setFromObject(g); selBox.visible = true; $('#handles').classList.toggle('hide', sel.kind === 'open' || sel.kind === 'inner'); }
function renderProp() {
  const P = $('#prop'); if (!sel) { P.classList.add('hide'); return; } P.classList.remove('hide');
  if (sel.kind === 'obj') {
    const o = plan.objects.find(x => x.id === sel.id); if (!o) { P.classList.add('hide'); return; } const def = byId[o.item];
    const cols = (k, cur) => `<div class="sw">${[...BRAND, ...PALETTE].map(c => `<button data-k="${k}" data-c="${c}" style="background:${c}" class="${(cur || '').toLowerCase() === c ? 's' : ''}"></button>`).join('')}<input type="color" data-k="${k}" value="${cur || def.colors[0]}" style="width:28px;height:28px;padding:0;border-radius:8px"></div>`;
    let h = `<div class="ey">Seleccionado</div><h3>${def.name}</h3><div style="font-size:12px;color:#a39cb0">${def.w} × ${def.d} m · x ${o.x.toFixed(1)} · z ${o.z.toFixed(1)} · ${Math.round(o.rot || 0)}°</div>`;
    h += `<div class="lbl">Color principal</div>${cols('color', o.color || def.colors[0])}`;
    if (def.colors.length > 1) h += `<div class="lbl">Color secundario</div>${cols('color2', o.color2 || def.colors[1])}`;
    if (def.props?.includes('text')) h += `<div class="lbl">Texto del letrero</div><input type="text" id="pText" value="${o.text || ''}" maxlength="18" style="width:100%">`;
    if (def.props?.includes('screen')) h += `<div class="lbl">¿Qué muestra la pantalla?</div><select id="pScreen" style="width:100%">${SCREENS.map(s => `<option ${s === (o.screen || '') ? 'selected' : ''}>${s}</option>`).join('')}</select>`;
    if (def.props?.includes('products')) h += `<div class="lbl">Productos que se ven</div><div style="display:flex;gap:6px;flex-wrap:wrap">${['Gaseosas', 'Cervezas', 'Agua', 'Variado'].map(p => `<button class="pill ${p === (o.products || 'Variado') ? 'on' : ''}" data-prod="${p}" style="padding:5px 9px;font-size:12px">${p}</button>`).join('')}</div>`;
    h += `<div class="lbl">Girar</div><div class="btns"><button data-r="-90">↺ 90°</button><button data-r="-45">↺ 45°</button><button data-r="45">↻ 45°</button><button data-r="90">↻ 90°</button></div><div class="btns" style="margin-top:6px"><button id="pDup">⧉ Duplicar</button><button id="pDel">🗑 Borrar</button></div>`;
    if (def.conn) { const opts = entities()[def.conn] || []; h += `<div class="link">🔗 <b>Conectar a: ${CONN[def.conn]}</b><select id="pConn"><option value="">— Sin conectar —</option>${opts.map(n => { const usedBy = plan.objects.find(x => x.conn === n.id && x.id !== o.id); return `<option value="${esc(n.id)}" ${o.conn === n.id ? 'selected' : ''} ${usedBy ? 'disabled' : ''}>${esc(n.label)}${usedBy ? ' (ya usado)' : ''}</option>`; }).join('')}</select><small>${o.conn ? 'En vivo se mueve con este dato real' : 'Aún no se mueve con datos reales'}</small></div>`; }
    if (collisions(plan).has(o.id)) h += `<div class="warn">⚠ Se cruza con otro objeto</div>`;
    P.innerHTML = h;
    P.querySelectorAll('.sw button').forEach(b => b.onclick = () => { o[b.dataset.k] = b.dataset.c; refreshObj(o); afterChange(); renderProp(); });
    P.querySelectorAll('.sw input[type=color]').forEach(i => i.onchange = () => { o[i.dataset.k] = i.value; refreshObj(o); afterChange(); renderProp(); });
    P.querySelectorAll('[data-r]').forEach(b => b.onclick = () => rotateSel(+b.dataset.r));
    P.querySelectorAll('[data-prod]').forEach(b => b.onclick = () => { o.products = b.dataset.prod; refreshObj(o); afterChange(); renderProp(); });
    const pt = $('#pText'); if (pt) pt.oninput = () => { o.text = pt.value; refreshObj(o); afterChange(); };
    const ps = $('#pScreen'); if (ps) ps.onchange = () => { o.screen = ps.value; refreshObj(o); afterChange(); };
    const pc = $('#pConn'); if (pc) pc.onchange = () => { o.conn = pc.value; if (!o.conn) delete o.conn; afterChange(); renderProp(); toast(o.conn ? 'Conectado a ' + connLabel(o.conn) : 'Desconectado'); };
    $('#pDup').onclick = dupSel; $('#pDel').onclick = delSel;
  }
  if (sel.kind === 'person') {
    const pp = plan.people.find(x => x.id === sel.id); const p = team.find(t => t.id === pp?.pid); if (!pp || !p) { P.classList.add('hide'); return; }
    P.innerHTML = `<div class="ey">Persona</div><h3>${p.name}</h3><div style="font-size:12px;color:#a39cb0">${p.role} · ${p.area}</div><div class="lbl">¿Qué está haciendo?</div><div style="display:flex;gap:6px;flex-wrap:wrap">${CLIPS.map(([k, n]) => `<button class="pill ${pp.clip === k ? 'on' : ''}" data-clip="${k}" style="padding:6px 9px;font-size:12px">${n}</button>`).join('')}</div>
      <div class="lbl">Girar</div><div class="btns"><button data-r="-45">↺ 45°</button><button data-r="45">↻ 45°</button><button data-r="180">↻ 180°</button></div><div class="btns" style="margin-top:6px"><button id="pEdit">✏️ Editar personaje</button><button id="pDel">🗑 Quitar</button></div>
      <div style="font-size:12px;color:#a39cb0;margin-top:10px">En vivo aparece cuando abre turno y hace lo que diga su dato real.</div>`;
    P.querySelectorAll('[data-clip]').forEach(b => b.onclick = async () => { pp.clip = b.dataset.clip; await setClip(peopleMap.get(pp.id), pp.clip); afterChange(); renderProp(); });
    P.querySelectorAll('[data-r]').forEach(b => b.onclick = () => rotateSel(+b.dataset.r));
    $('#pEdit').onclick = () => location.href = link('personajes?id=' + p.id); $('#pDel').onclick = delSel;
  }
  if (sel.kind === 'inner') {
    const iw = plan.inner.find(x => x.id === sel.id); if (!iw) { P.classList.add('hide'); return; } const L = innerLen(iw);
    P.innerHTML = `<div class="ey">Muro interior</div><h3>${INNER_KINDS[iw.kind].name}</h3><div style="font-size:12px;color:#a39cb0">Largo ${L.toFixed(1)} m · arrastra para moverlo</div>
      <div class="lbl">Tipo</div><div style="display:flex;gap:6px;flex-wrap:wrap">${Object.entries(INNER_KINDS).map(([k, v]) => `<button class="pill ${iw.kind === k ? 'on' : ''}" data-kind="${k}" style="padding:6px 9px;font-size:12px">${v.name}</button>`).join('')}</div>
      <div class="lbl">Largo (m)</div><input type="range" id="iL" min=".5" max="${Math.max(plan.room.w, plan.room.d)}" step=".1" value="${L.toFixed(1)}" style="width:100%">
      ${iw.kind === 'media' ? `<div class="lbl">Alto (m)</div><input type="range" id="iH" min=".6" max="1.8" step=".05" value="${iw.h || 1.1}" style="width:100%">` : ''}
      ${iw.kind !== 'vidrio' ? `<div class="lbl">Material</div><select id="iM" style="width:100%">${Object.entries(WALLS).filter(([k]) => k !== 'vidrio').map(([k, v]) => `<option value="${k}" ${k === (iw.mat || 'pintura') ? 'selected' : ''}>${v.name}</option>`).join('')}</select>` : ''}
      <div class="lbl">Color</div><div class="sw">${[...BRAND, ...PALETTE.slice(0, 12)].map(c => `<button data-c="${c}" style="background:${c}" class="${(iw.color || '') === c ? 's' : ''}"></button>`).join('')}<input type="color" id="iC" value="${iw.color || '#e7e2f0'}" style="width:28px;height:28px;padding:0;border-radius:8px"></div>
      <div class="lbl">Puerta en este muro</div><div style="display:flex;gap:6px;flex-wrap:wrap">${[['', 'Sin puerta'], ['hueco', 'Hueco'], ['puerta', 'Puerta'], ['vidrio', 'Puerta de vidrio']].map(([k, n]) => `<button class="pill ${(iw.door?.type || '') === k ? 'on' : ''}" data-door="${k}" style="padding:6px 9px;font-size:12px">${n}</button>`).join('')}</div>
      ${iw.door ? `<div class="lbl">Posición de la puerta</div><input type="range" id="iDP" min="0" max="1" step=".02" value="${iw.door.pos ?? .5}" style="width:100%"><div class="lbl">Ancho de la puerta (m)</div><input type="range" id="iDW" min=".7" max="${Math.max(.8, Math.min(3, L - .2)).toFixed(1)}" step=".1" value="${iw.door.width || .9}" style="width:100%">` : ''}
      <div class="btns" style="margin-top:10px"><button id="iRot">⟲ Girar 90°</button><button id="iDup">⧉ Duplicar</button><button id="pDel">🗑 Borrar</button></div>`;
    const re = () => { rebuildShell(); updateSel(); drawMap(); };
    P.querySelectorAll('[data-kind]').forEach(b => b.onclick = () => { iw.kind = b.dataset.kind; if (iw.kind === 'vidrio') iw.color = '#bfe6ff'; else if (iw.mat === 'vidrio' || !iw.mat) iw.mat = 'pintura'; re(); afterChange(); renderProp(); });
    $('#iL').oninput = e => { const nl = +e.target.value, a = Math.atan2(iw.z2 - iw.z1, iw.x2 - iw.x1); const cx = (iw.x1 + iw.x2) / 2, cz = (iw.z1 + iw.z2) / 2; iw.x1 = cx - Math.cos(a) * nl / 2; iw.x2 = cx + Math.cos(a) * nl / 2; iw.z1 = cz - Math.sin(a) * nl / 2; iw.z2 = cz + Math.sin(a) * nl / 2; re(); }; $('#iL').onchange = () => { afterChange(); renderProp(); };
    const ih = $('#iH'); if (ih) { ih.oninput = e => { iw.h = +e.target.value; re(); }; ih.onchange = () => afterChange(); }
    const im = $('#iM'); if (im) im.onchange = e => { iw.mat = e.target.value; iw.color = WALLS[iw.mat].def; re(); afterChange(); renderProp(); };
    P.querySelectorAll('.sw button').forEach(b => b.onclick = () => { iw.color = b.dataset.c; re(); afterChange(); renderProp(); });
    $('#iC').onchange = e => { iw.color = e.target.value; re(); afterChange(); renderProp(); };
    P.querySelectorAll('[data-door]').forEach(b => b.onclick = () => { iw.door = b.dataset.door ? { pos: iw.door?.pos ?? .5, width: iw.door?.width || .9, type: b.dataset.door } : null; re(); afterChange(); renderProp(); });
    const dp = $('#iDP'); if (dp) { dp.oninput = e => { iw.door.pos = +e.target.value; re(); }; dp.onchange = () => afterChange(); }
    const dw = $('#iDW'); if (dw) { dw.oninput = e => { iw.door.width = +e.target.value; re(); }; dw.onchange = () => afterChange(); }
    $('#iRot').onclick = () => { const cx = (iw.x1 + iw.x2) / 2, cz = (iw.z1 + iw.z2) / 2; const r = (x, z) => ({ x: cx - (z - cz), z: cz + (x - cx) }); const a = r(iw.x1, iw.z1), b = r(iw.x2, iw.z2); Object.assign(iw, { x1: a.x, z1: a.z, x2: b.x, z2: b.z }); re(); afterChange(); renderProp(); };
    $('#iDup').onclick = () => { const n = { ...iw, id: uid(), x1: iw.x1 + .6, x2: iw.x2 + .6, z1: iw.z1 + .6, z2: iw.z2 + .6, door: iw.door ? { ...iw.door } : null }; plan.inner.push(n); re(); select({ kind: 'inner', id: n.id }); afterChange(); toast('Muro duplicado'); };
    $('#pDel').onclick = delSel;
  }
  if (sel.kind === 'open') {
    const o = plan.openings.find(x => x.id === sel.id); if (!o) { P.classList.add('hide'); return; }
    P.innerHTML = `<div class="ey">Puerta / ventana</div><h3>${OPENINGS[o.type].name}</h3><div class="lbl">Tipo</div><select id="oType" style="width:100%">${Object.entries(OPENINGS).map(([k, v]) => `<option value="${k}" ${k === o.type ? 'selected' : ''}>${v.name}</option>`).join('')}</select>
      <div class="lbl">Posición en la pared</div><input type="range" id="oPos" min=".05" max=".95" step=".01" value="${o.pos}" style="width:100%"><div class="lbl">Ancho (m)</div><input type="range" id="oW" min=".7" max="4" step=".1" value="${o.width || OPENINGS[o.type].w}" style="width:100%">
      <div class="lbl">Color</div><div class="sw">${['#5b3a26', '#111111', '#ffffff', '#7f1d1d', '#1e3a8a', '#f20b6d', '#9ca3af'].map(c => `<button data-c="${c}" style="background:${c}" class="${o.color === c ? 's' : ''}"></button>`).join('')}</div><div class="btns" style="margin-top:10px"><button id="pDel">🗑 Borrar</button></div>`;
    $('#oType').onchange = e => { o.type = e.target.value; delete o.width; rebuildShell(); afterChange(); renderProp(); };
    $('#oPos').oninput = e => { o.pos = +e.target.value; rebuildShell(); updateSel(); }; $('#oPos').onchange = () => afterChange();
    $('#oW').oninput = e => { o.width = +e.target.value; rebuildShell(); updateSel(); }; $('#oW').onchange = () => afterChange();
    P.querySelectorAll('.sw button').forEach(b => b.onclick = () => { o.color = b.dataset.c; rebuildShell(); afterChange(); renderProp(); });
    $('#pDel').onclick = delSel;
  }
}
function rotateSel(deg) {
  if (!sel) return; if (sel.kind === 'inner') { $('#iRot')?.click(); return; } if (sel.kind === 'obj') { const o = plan.objects.find(x => x.id === sel.id); o.rot = ((o.rot || 0) + deg + 360) % 360; objMap.get(o.id).rotation.y = o.rot * Math.PI / 180; }
  if (sel.kind === 'person') { const o = plan.people.find(x => x.id === sel.id); o.rot = ((o.rot || 0) + deg + 360) % 360; peopleMap.get(o.id).rotation.y = o.rot * Math.PI / 180; }
  afterChange(); renderProp();
}
function dupSel() { if (sel?.kind !== 'obj') return; const o = plan.objects.find(x => x.id === sel.id); const n = { ...o, id: uid(), x: o.x + .8, z: o.z + .8 }; delete n.conn; const s = snapPos(n.item, n.x, n.z, false); n.x = s.x; n.z = s.z; plan.objects.push(n); addObj(n); select({ kind: 'obj', id: n.id }); afterChange(); toast('Duplicado'); }
function delSel() {
  if (!sel) return;
  if (sel.kind === 'obj') { plan.objects = plan.objects.filter(x => x.id !== sel.id); objG.remove(objMap.get(sel.id)); objMap.delete(sel.id); }
  if (sel.kind === 'person') { plan.people = plan.people.filter(x => x.id !== sel.id); peopleG.remove(peopleMap.get(sel.id)); peopleMap.delete(sel.id); }
  if (sel.kind === 'open') { plan.openings = plan.openings.filter(x => x.id !== sel.id); rebuildShell(); }
  if (sel.kind === 'inner') { plan.inner = plan.inner.filter(x => x.id !== sel.id); rebuildShell(); }
  sel = null; renderProp(); afterChange(); toast('Borrado');
}
$('#tRot').onclick = () => rotateSel(45); $('#tDup').onclick = dupSel; $('#tDel').onclick = delSel; $('#tUndo').onclick = undo; $('#tRedo').onclick = redo; $('#tView').onclick = fitView;
$('#tWalls').onclick = () => { allWalls = !allWalls; rebuildShell(); };
$('#hRot').onclick = () => rotateSel(45); $('#hDup').onclick = dupSel; $('#hDel').onclick = delSel;
addEventListener('keydown', e => {
  if ($('#editor').classList.contains('hide') || /INPUT|SELECT|TEXTAREA/.test(document.activeElement?.tagName)) return;
  if (e.key === 'r' || e.key === 'R') rotateSel(45);
  if (e.key === 'Delete' || e.key === 'Backspace') delSel();
  if (e.key === 'Escape') select(null);
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'z') { e.preventDefault(); undo(); }
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'y') { e.preventDefault(); redo(); }
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'd') { e.preventDefault(); dupSel(); }
});

// ================= estilo, publicar, menú
$('#styleSel').onchange = e => { Style.mode = e.target.value; Store.set('style', Style.mode); rebuildAll(); renderDock(); renderProp(); toast('Estilo de la empresa: ' + (Style.mode === 'toon' ? 'Caricatura' : 'Humano')); };
$('#pubBtn').onclick = async () => { clearTimeout(saveT); save(); const b = $('#pubBtn'); b.disabled = true; try { await flush(); const r = await api(companyPath() + '/disenos/' + encodeURIComponent(D.id) + '/publicar', { method: 'POST', body: '{}' }); D.version = r.version; D.live = true; designs.forEach(d => { if (d.id !== D.id) d.live = false; }); toast('Versión ' + D.version + ' publicada en vivo 🚀'); } catch (e) { toast('No se pudo publicar: ' + e.message, 'err'); } finally { b.disabled = false; } };
$('#menuBtn').onclick = () => $('#menu').classList.add('show'); $('#mClose').onclick = () => $('#menu').classList.remove('show');
$('#mHome').onclick = () => { save(); $('#menu').classList.remove('show'); renderStart(); };
$('#mPeople').onclick = () => location.href = link('personajes');
$('#mExport').onclick = () => { const b = new Blob([JSON.stringify({ ...plan, name: D.name }, null, 1)], { type: 'application/json' }); const a = document.createElement('a'); a.href = URL.createObjectURL(b); a.download = (D.name || 'plano').replace(/\W+/g, '-') + '.clonexa.json'; a.click(); toast('Plano exportado'); };
$('#mVersions').onclick = async () => { $('#menu').classList.remove('show'); const L = $('#verList'); L.innerHTML = '<p style="color:#a39cb0">Cargando…</p>'; $('#versions').classList.add('show'); try { await flush(); D.versions = (await api(companyPath() + '/disenos/' + encodeURIComponent(D.id) + '/versiones')).items; } catch (e) { L.innerHTML = `<p style="color:#fecaca">${esc(e.message)}</p>`; return; } L.innerHTML = (D.versions || []).map(v => `<div class="dc"><div><b>Versión ${v.n}</b><small>${new Date(v.date).toLocaleString('es-CO')}${v.n === D.version ? ' · en vivo' : ''}</small></div><button class="pill" data-v="${v.n}" style="margin-left:auto">Restaurar</button></div>`).join('') || '<p style="color:#a39cb0">Aún no hay versiones publicadas. "Publicar en vivo" crea una.</p>'; L.querySelectorAll('[data-v]').forEach(b => b.onclick = async () => { const v = D.versions.find(x => x.n === +b.dataset.v); try { const r = await api(companyPath() + '/disenos/' + encodeURIComponent(D.id) + '/versiones/' + v.n); plan = r.plan; plan.people = plan.people || []; rebuildAll(); afterChange(); $('#versions').classList.remove('show'); toast('Versión ' + v.n + ' restaurada como borrador'); } catch (e) { toast(e.message, 'err'); } }); };

// ================= mapa
const mapC = $('#map'), mx = mapC.getContext('2d');
function drawMap() {
  if (!plan) return; const { w, d } = plan.room; const W = mapC.width, H = mapC.height, s = Math.min((W - 20) / w, (H - 20) / d), ox = W / 2, oz = H / 2;
  mx.fillStyle = '#0b0911'; mx.fillRect(0, 0, W, H); mx.fillStyle = plan.floor.color || '#555'; mx.fillRect(ox - w / 2 * s, oz - d / 2 * s, w * s, d * s); mx.strokeStyle = '#e7e2f0'; mx.lineWidth = 3; mx.strokeRect(ox - w / 2 * s, oz - d / 2 * s, w * s, d * s);
  const col = collisions(plan);
  plan.objects.forEach(o => { const f = footprint(o); if (!f) return; mx.fillStyle = sel?.id === o.id ? '#38bdf8' : col.has(o.id) ? '#ef4444' : f.flat ? 'rgba(242,11,109,.35)' : (o.color || byId[o.item].colors[0]); mx.globalAlpha = .9; mx.fillRect(ox + f.x0 * s, oz + f.z0 * s, (f.x1 - f.x0) * s, (f.z1 - f.z0) * s); mx.globalAlpha = 1; mx.strokeStyle = '#000a'; mx.lineWidth = 1; mx.strokeRect(ox + f.x0 * s, oz + f.z0 * s, (f.x1 - f.x0) * s, (f.z1 - f.z0) * s); });
  (plan.inner || []).forEach(iw => { mx.strokeStyle = sel?.id === iw.id ? '#38bdf8' : iw.kind === 'vidrio' ? '#7dd3fc' : '#e7e2f0'; mx.lineWidth = iw.kind === 'media' ? 2 : 4; mx.beginPath(); mx.moveTo(ox + iw.x1 * s, oz + iw.z1 * s); mx.lineTo(ox + iw.x2 * s, oz + iw.z2 * s); mx.stroke(); });
  plan.people.forEach(p => { mx.fillStyle = '#facc15'; mx.beginPath(); mx.arc(ox + p.x * s, oz + p.z * s, 4, 0, 7); mx.fill(); });
  mx.strokeStyle = '#38bdf8'; mx.setLineDash([4, 3]); mx.beginPath(); mx.arc(ox + ctr.target.x * s, oz + ctr.target.z * s, 10, 0, 7); mx.stroke(); mx.setLineDash([]);
  mapC._s = { s, ox, oz };
}
mapC.onclick = e => { const r = mapC.getBoundingClientRect(); const { s, ox, oz } = mapC._s; const x = ((e.clientX - r.left) / r.width * mapC.width - ox) / s, z = ((e.clientY - r.top) / r.height * mapC.height - oz) / s; const d = new THREE.Vector3(x, 0, z).sub(ctr.target); ctr.target.add(d); cam.position.add(d); ctr.update(); drawMap(); };

// ================= biblioteca (carpetas) y subir modelo GLB
let libCat = 'barra', wiz = { step: 1, scene: null, url: '' };
const custom = () => ITEMS.filter(i => i.model);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
function renderLib() {
  const q = ($('#libQ').value || '').toLowerCase();
  $('#folders').innerHTML = CATS.map(([k, n]) => `<button class="fd ${k === libCat && !q ? 'sel' : ''}" data-c="${k}">${n}<small>${ITEMS.filter(i => i.cat === k).length} objetos</small></button>`).join('');
  $('#folders').querySelectorAll('.fd').forEach(b => b.onclick = () => { libCat = b.dataset.c; $('#libQ').value = ''; renderLib(); });
  const list = q ? ITEMS.filter(i => i.name.toLowerCase().includes(q)) : ITEMS.filter(i => i.cat === libCat);
  $('#libItems').innerHTML = '';
  const rev = (state().review || []).filter(x => !q || x.name.toLowerCase().includes(q));
  if (rev.length) { const h = document.createElement('div'); h.style.gridColumn = '1/-1'; h.innerHTML = `<div class="ey" style="margin:4px 0 8px">En revisión · apruébalo para que entre al catálogo</div><div class="items" style="margin-top:0">${rev.map(x => `<div class="it" style="cursor:default"><img src="${esc(x.mini || '')}"><span>${esc(x.name)}<br><small style="color:#a39cb0">${esc(x.license)}</small></span><div class="btns" style="padding:0 6px 6px"><button data-ok="${esc(x.id)}">✓ Aprobar</button><button data-no="${esc(x.id)}">✕</button></div></div>`).join('')}</div>`; $('#libItems').appendChild(h);
    h.querySelectorAll('[data-ok],[data-no]').forEach(b => b.onclick = async () => { const id = b.dataset.ok || b.dataset.no; try { const r = await api('/biblioteca/' + encodeURIComponent(id) + '/' + (b.dataset.ok ? 'aprobar' : 'rechazar'), { method: 'POST', body: '{}' }); state().review = r.review; state().catalog = r.catalog; registerModels(r.catalog); renderLib(); toast(b.dataset.ok ? 'Aprobado: ya está en el catálogo' : 'Rechazado'); } catch (e) { toast(e.message, 'err'); } }); }
  list.forEach(i => { const b = document.createElement('button'); b.className = 'it'; b.innerHTML = `<img src="${itemThumb(i.id)}"><span>${i.name}</span>`; b.onclick = () => { $('#lib').classList.remove('show'); if ($('#editor').classList.contains('hide')) { toast('Abre o crea un diseño para usarlo'); return; } cat = i.cat; setMode('amueblar'); placeItem(i.id, ctr.target.x, ctr.target.z, null); }; $('#libItems').appendChild(b); });
}
$('#libBtn').onclick = () => { $('#lib').classList.add('show'); renderLib(); }; $('#libQ').oninput = renderLib;
$('#credLink').onclick = e => { e.preventDefault(); const c = $('#creds'); c.classList.toggle('hide'); const cu = custom(); c.innerHTML = `<b>Créditos 3D</b><br>${ITEMS.length - cu.length} objetos propios de Clonexa (hechos por código)${cu.length ? '<br>' + cu.map(c => `${esc(c.name)} · ${esc(c.license)}${c.author ? ' · ' + esc(c.author) : ''} · ${esc(c.source || 'sin fuente')}`).join('<br>') : ''}<br>Personajes y animaciones: Mixamo (Adobe), uso dentro de Clonexa; three.js (MIT).`; };
function wizShow() { [1, 2, 3].forEach(n => { $('#w' + n).classList.toggle('hide', wiz.step !== n); $('#st' + n).classList.toggle('sel', wiz.step === n); }); $('#wNext').textContent = wiz.step === 3 ? '✓ Agregar a la biblioteca' : 'Siguiente →'; }
$('#upBtn').onclick = () => { $('#upWiz').classList.remove('hide'); wiz = { step: 1, scene: null, file: null }; $('#glbIn').value = ''; $('#w1prev').innerHTML = ''; $('#wCat').innerHTML = CATS.map(([k, n]) => `<option value="${k}">${n}</option>`).join(''); $('#wCat').value = libCat; wizShow(); };
$('#glbIn').onchange = async e => { const f = e.target.files[0]; if (!f) return; if (!/\.(glb|fbx|obj|zip)$/i.test(f.name)) { toast('Sube un modelo .glb, .fbx, .obj o .zip', 'err'); return; } if (f.size > 50 * 1024 * 1024) { toast('El archivo pasa de 50 MB', 'err'); return; } wiz.file = f; wiz.scene = null; $('#wName').value = f.name.replace(/\.(glb|fbx|obj|zip)$/i, '').slice(0, 60);
  if (/\.glb$/i.test(f.name)) { try { const url = URL.createObjectURL(f); const g = await new GLTFLoader().loadAsync(url); URL.revokeObjectURL(url); wiz.scene = g.scene; const sz = new THREE.Box3().setFromObject(g.scene).getSize(new THREE.Vector3()); if (sz.y > .05 && sz.y < 15) $('#wH').value = sz.y.toFixed(2); } catch (er) { /* el servidor lo revisa igual */ } }
  $('#w1prev').innerHTML = `<span class="chip live">✓ ${wiz.scene ? 'Modelo leído' : 'Archivo listo (se convierte en el servidor)'}: ${esc(f.name)}</span>`; };
$('#wBack').onclick = () => { if (wiz.step > 1) { wiz.step--; wizShow(); } };
$('#wNext').onclick = () => {
  if (wiz.step === 1) { if (!wiz.file) { toast('Primero sube un archivo .glb, .fbx, .obj o .zip', 'err'); return; } wiz.step = 2; return wizShow(); }
  if (wiz.step === 2) { if (!$('#wName').value) { toast('Ponle nombre', 'err'); return; } wiz.step = 3; return wizShow(); }
  if (!$('#wLic').value) { toast('Sin licencia no se puede publicar', 'err'); return; }
  if (!$('#wSrc').value && $('#wLic').value !== 'Propia') { toast('Escribe la URL de la fuente (https://…)', 'err'); return; }
  const lic = { 'CC0': 'cc0', 'CC-BY (con atribución)': 'ccby', 'Propia': 'propia' }[$('#wLic').value];
  const fd = new FormData(); fd.append('archivo', wiz.file); fd.append('nombre', $('#wName').value); fd.append('categoria', $('#wCat').value); fd.append('alto', $('#wH').value || '1');
  fd.append('licencia', lic); fd.append('fuente', $('#wSrc').value); if (lic === 'ccby') fd.append('atribucion', $('#wName').value + ' · ' + $('#wSrc').value);
  const nb = $('#wNext'); nb.disabled = true; nb.textContent = 'Convirtiendo…';
  api('/biblioteca/subir', { method: 'POST', body: fd }).then(r => { state().review = r.review; state().catalog = r.catalog; registerModels(r.catalog); libCat = $('#wCat').value; $('#upWiz').classList.add('hide'); renderLib(); toast(r.estado === 'revision' ? '"' + $('#wName').value + '" quedó en revisión: apruébalo para usarlo' : 'Modelo con esqueleto: queda para personajes'); })
    .catch(e => toast(e.message, 'err')).finally(() => { nb.disabled = false; wizShow(); });
};

// ================= bucle
const clock = new THREE.Clock(); let mapT = 0;
function loop() {
  requestAnimationFrame(loop); if ($('#editor').classList.contains('hide')) return;
  const dt = Math.min(clock.getDelta(), .05), t = clock.elapsedTime; ctr.update();
  peopleG.children.forEach(g => tickCharacter(g, dt, t));
  // manijas y etiquetas
  const g = selObject(); if (g && sel.kind !== 'open' && sel.kind !== 'inner') { const b = new THREE.Box3().setFromObject(g); const p = new THREE.Vector3((b.min.x + b.max.x) / 2, b.max.y + .15, (b.min.z + b.max.z) / 2).project(cam); const H = $('#handles'); H.style.left = ((p.x + 1) / 2 * innerWidth) + 'px'; H.style.top = ((1 - p.y) / 2 * innerHeight - 6) + 'px'; selBox.box.copy(b); }
  const L = $('#labels'); if (mode === 'conectar') { const items = plan.objects.filter(o => byId[o.item]?.conn); if (L.children.length !== items.length) { L.innerHTML = items.map(() => '<div class="badge"></div>').join(''); } items.forEach((o, i) => { const gg = objMap.get(o.id); if (!gg) return; const b = new THREE.Box3().setFromObject(gg); const p = new THREE.Vector3(o.x, b.max.y + .2, o.z).project(cam); const el = L.children[i]; el.className = 'badge ' + (o.conn ? 'ok' : 'no'); el.textContent = o.conn ? '🔗 ' + connLabel(o.conn) : '⚠ sin conectar'; el.style.left = ((p.x + 1) / 2 * innerWidth) + 'px'; el.style.top = ((1 - p.y) / 2 * innerHeight) + 'px'; el.style.display = p.z < 1 ? '' : 'none'; }); } else if (L.children.length) L.innerHTML = '';
  if (t - mapT > .25) { mapT = t; drawMap(); }
  R.render(scene, cam);
}
loop();
// arranque: ?d=<id> abre un diseño; si no, inicio
const qd = new URLSearchParams(location.search).get('d');
if (qd && designs.find(d => d.id === qd)) openDesign(qd); else renderStart();
if (new URLSearchParams(location.search).get('lib')) { $('#lib').classList.add('show'); renderLib(); if (new URLSearchParams(location.search).get('lib') === 'up') $('#upBtn').click(); }
window.__cx = { get plan() { return plan; }, setMode, placeItem, select, openDesign, designs: () => designs,
  // medición (pruebas y FPS): n cuadros completos con gl.finish -> ms por cuadro
  bench(n = 20) { const gl = R.getContext(); R.render(scene, cam); gl.finish(); const t0 = performance.now(); for (let i = 0; i < n; i++) { ctr.update(); peopleG.children.forEach(g => tickCharacter(g, .016, i * .016)); R.render(scene, cam); } gl.finish(); return { ms: +((performance.now() - t0) / n).toFixed(2), objects: plan ? plan.objects.length : 0, people: peopleG.children.length }; } };
