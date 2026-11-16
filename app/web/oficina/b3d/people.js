// EDITOR DE PERSONAJES · prototipo funcional aprobado (Caricatura y Humano, misma interfaz), integrado a Clonexa:
// el equipo es el Personal real de la empresa y cada personaje se guarda en el servidor (store.js).
import { THREE, Style, BRAND } from './core.js';
import { Store, toast, uid, company, loadBrand, link, state } from './store.js';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { OPT, HUMAN_BASES, HUMAN_ACC, CLIPS, buildCharacter, tickCharacter, setClip, defaultToon, defaultHuman, randomToon } from './char.js';
import { loadTeam, saveTeam, loadUniforms, saveUniforms, AREAS } from './team.js';

const $ = s => document.querySelector(s);
loadBrand(); Style.mode = Store.get('style', 'human');
document.querySelectorAll('.cxEmp').forEach(e => e.textContent = company().name);
let team = loadTeam(), uniforms = loadUniforms(), filter = 'Todos';
let cur = null, tab = 'pelo', clip = 'idle', model = null, dirty = false;

// ---------- miniaturas
const TR = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true }); TR.outputColorSpace = THREE.SRGBColorSpace; TR.toneMapping = THREE.ACESFilmicToneMapping;
const cache = {};
function tscene() { const s = new THREE.Scene(); s.background = new THREE.Color(0x1d1430); s.add(new THREE.AmbientLight(0xffffff, .95)); const k = new THREE.DirectionalLight(0xffffff, 1.6); k.position.set(2, 4, 4); s.add(k); const r = new THREE.DirectionalLight(0xf20b6d, .5); r.position.set(-3, 2, -2); s.add(r); return s; }
async function thumb(p, framing = 'full', w = 240, h = 260) {
  const key = Style.mode + framing + JSON.stringify(Style.mode === 'human' ? p.human : p.toon); if (cache[key]) return cache[key];
  const s = tscene(); const g = await buildCharacter(p, Style.mode, 'idle'); s.add(g); tickCharacter(g, .016, .3);
  const c = new THREE.PerspectiveCamera(28, w / h, .05, 50);
  if (framing === 'full') { c.position.set(0, 1.0, 4.3); c.lookAt(0, .9, 0); }
  if (framing === 'head') { const y = Style.mode === 'human' ? 1.58 : 1.47; c.position.set(Style.mode === 'human' ? .25 : .45, y + .08, Style.mode === 'human' ? 1.05 : 1.35); c.lookAt(0, y - .02, 0); }
  if (framing === 'top') { const y = Style.mode === 'human' ? 1.25 : .95; c.position.set(0, y, 1.9); c.lookAt(0, y - .05, 0); }
  if (framing === 'legs') { const y = Style.mode === 'human' ? .55 : .42; c.position.set(0, y, 2.2); c.lookAt(0, y - .02, 0); }
  if (framing === 'feet') { c.position.set(0, .3, 1.5); c.lookAt(0, .1, 0); }
  TR.setSize(w, h); TR.render(s, c); const u = TR.domElement.toDataURL('image/jpeg', .85); cache[key] = u; return u;
}

// ---------- lista del equipo
function renderTeam() {
  $('#team').classList.remove('hide'); $('#edit').classList.add('hide'); $('#stySel').value = Style.mode;
  const areas = ['Todos', ...AREAS.filter(a => team.some(t => t.area === a))]; const pend = team.filter(t => !t.custom).length;
  $('#flt').innerHTML = areas.map(a => `<button class="pill ${a === filter ? 'on' : ''}" data-f="${a}">${a}${a === 'Todos' ? ' ' + team.length : ''}</button>`).join('') + (pend ? `<button class="pill ${filter === 'pend' ? 'on' : ''}" data-f="pend">Sin personalizar ${pend}</button>` : '');
  $('#flt').querySelectorAll('button').forEach(b => b.onclick = () => { filter = b.dataset.f; renderTeam(); });
  const list = team.filter(t => filter === 'Todos' || (filter === 'pend' ? !t.custom : t.area === filter));
  const G = $('#grid'); G.innerHTML = '';
  list.forEach(async p => { const c = document.createElement('div'); c.className = 'sc'; c.innerHTML = `<div class="av"><img></div><b>${p.name}</b><small>${p.role} · ${p.shift}</small><span class="chip ${p.custom ? 'live' : 'draft'}">${p.custom ? '✓ Listo' : 'Sin personalizar'}</span>`; c.onclick = () => openEdit(p.id); G.appendChild(c); c.querySelector('img').src = await thumb(p); });
  const n = document.createElement('div'); n.className = 'new'; n.innerHTML = '<div class="p">＋</div>Nuevo personaje<small style="font-weight:500;color:#7d7590">o ligarlo a alguien del personal</small>'; n.onclick = newPerson; G.appendChild(n);
  const U = $('#uni'); U.innerHTML = uniforms.map(u => { const d = Style.mode === 'human' ? [u.human.topColor, u.human.bottomColor, u.human.accColor] : [u.toon.topColor, u.toon.bottomColor, u.toon.accColor]; return `<div class="uc"><div class="dots">${d.filter(Boolean).map(c => `<i style="background:${c}"></i>`).join('')}</div><div><b>${u.name}</b><small>${u.desc} · ${team.filter(t => t.uniform === u.id).length} personas</small></div><div class="acts"><button data-ap="${u.id}">Aplicar a ${u.name}</button><button data-del="${u.id}">🗑</button></div></div>`; }).join('') + `<div class="uc" style="border-style:dashed;justify-content:center;cursor:pointer" id="newU"><b>＋ Nuevo uniforme</b></div>`;
  U.querySelectorAll('[data-ap]').forEach(b => b.onclick = () => applyUniform(b.dataset.ap));
  U.querySelectorAll('[data-del]').forEach(b => b.onclick = () => { if (!confirm('¿Borrar este uniforme?')) return; uniforms = uniforms.filter(u => u.id !== b.dataset.del); saveUniforms(uniforms); renderTeam(); });
  $('#newU').onclick = () => toast('Abre a alguien, vístelo y toca "Guardar como uniforme"');
}
function applyUniform(id) {
  const u = uniforms.find(x => x.id === id); const areaMap = { Barra: 'Barra', Caja: 'Caja', Cocina: 'Cocina', 'Salón': 'Salón' }; const area = areaMap[u.name] || u.name; let n = 0;
  team.forEach(t => { if (t.area === area) { Object.assign(t.toon, u.toon); Object.assign(t.human, u.human); t.uniform = u.id; t.custom = true; n++; } });
  saveTeam(team); renderTeam(); toast(n ? `Uniforme "${u.name}" aplicado a ${n} persona${n > 1 ? 's' : ''}` : `Nadie del equipo está en el área ${area}`, n ? 'ok' : 'err');
}
const pid = () => [...crypto.getRandomValues(new Uint8Array(6))].map(b => b.toString(16).padStart(2, '0')).join('');
function newPerson() { const p = { id: pid(), name: 'Nueva persona', role: 'Mesero/a', area: 'Salón', shift: 'Turno noche', custom: false, toon: randomToon(), human: defaultHuman(team.length) }; team.push(p); saveTeam(team); openEdit(p.id); }
$('#stySel').onchange = e => { Style.mode = e.target.value; Store.set('style', Style.mode); renderTeam(); toast('Estilo de la empresa: ' + (Style.mode === 'toon' ? 'Caricatura' : 'Humano')); };
$('#newBtn').onclick = newPerson;
$('#rndAll').onclick = () => { const p = team.find(t => !t.custom) || team[0]; p.toon = randomToon(); p.human.base = HUMAN_BASES[Math.floor(Math.random() * HUMAN_BASES.length)][0]; p.human.topColor = OPT.colors[Math.floor(Math.random() * OPT.colors.length)]; p.human.topStyle = 'liso'; p.custom = true; saveTeam(team); renderTeam(); toast(p.name + ': personaje al azar'); };

// ---------- editor 3D
const cv = $('#cv'); const R = new THREE.WebGLRenderer({ canvas: cv, antialias: true }); R.setPixelRatio(Math.min(devicePixelRatio, 2)); R.outputColorSpace = THREE.SRGBColorSpace; R.toneMapping = THREE.ACESFilmicToneMapping; R.shadowMap.enabled = true;
const scene = new THREE.Scene(); scene.background = new THREE.Color(0x0d0816);
const cam = new THREE.PerspectiveCamera(30, 1, .05, 50); cam.position.set(0, 1.1, 4.6);
const ctr = new OrbitControls(cam, cv); ctr.target.set(0, .85, 0); ctr.enablePan = false; ctr.minDistance = 1.4; ctr.maxDistance = 7; ctr.maxPolarAngle = 1.75; ctr.enableDamping = true;
scene.add(new THREE.AmbientLight(0xffffff, .8)); const k = new THREE.DirectionalLight(0xffffff, 1.7); k.position.set(2, 5, 4); k.castShadow = true; k.shadow.bias = -.0008; k.shadow.normalBias = .03; scene.add(k); const rim = new THREE.DirectionalLight(0xf20b6d, 1.0); rim.position.set(-3, 2, -3); scene.add(rim);
const disc = new THREE.Mesh(new THREE.CylinderGeometry(.8, .85, .06, 48), new THREE.MeshStandardMaterial({ color: 0x2a2140 })); disc.position.y = -.03; disc.receiveShadow = true; scene.add(disc);
const ring = new THREE.Mesh(new THREE.TorusGeometry(.83, .012, 8, 64), new THREE.MeshBasicMaterial({ color: 0xf20b6d })); ring.rotation.x = Math.PI / 2; scene.add(ring);
const holder = new THREE.Group(); scene.add(holder);
function resize() { const r = cv.getBoundingClientRect(); if (!r.width) return; R.setSize(r.width, r.height, false); cam.aspect = r.width / r.height; cam.updateProjectionMatrix(); }
addEventListener('resize', resize);
let buildTok = 0;
async function rebuild() { const tok = ++buildTok; const g = await buildCharacter(cur, Style.mode, clip); if (tok !== buildTok) return; holder.clear(); g.userData.phase = 0; holder.add(g); model = g; g.traverse(q => { if (q.isMesh) q.castShadow = true; }); }
const clock = new THREE.Clock();
(function loop() { requestAnimationFrame(loop); if ($('#edit').classList.contains('hide')) return; const dt = Math.min(clock.getDelta(), .05); ctr.update(); if (model) tickCharacter(model, dt, clock.elapsedTime); R.render(scene, cam); })();
$('#rl').onclick = () => holder.rotation.y -= Math.PI / 4; $('#rr').onclick = () => holder.rotation.y += Math.PI / 4;

// ---------- categorías
const TABS_TOON = [['cuerpo', '🧍', 'Cuerpo'], ['cara', '🙂', 'Cara'], ['pelo', '💇', 'Pelo'], ['barba', '🧔', 'Barba'], ['arriba', '👕', 'Arriba'], ['abajo', '👖', 'Abajo'], ['completo', '👗', 'Completo'], ['zapatos', '👟', 'Zapatos'], ['acc', '🧢', 'Accesorios'], ['uniforme', '🏷️', 'Uniforme']];
const TABS_HUM = [['persona', '🧍', 'Persona'], ['cara', '🙂', 'Piel'], ['pelo', '💇', 'Pelo'], ['barba', '🧔', 'Barba'], ['arriba', '👕', 'Arriba'], ['abajo', '👖', 'Abajo'], ['zapatos', '👟', 'Zapatos'], ['uniforme', '🏷️', 'Uniforme']];
function openEdit(id) {
  cur = team.find(t => t.id === id); if (!cur) return; dirty = false;
  $('#team').classList.add('hide'); $('#edit').classList.remove('hide'); $('#esub').textContent = company().name + ' · ' + (Style.mode === 'toon' ? 'Caricatura' : 'Humano');
  $('#nmIn').value = cur.name; $('#roleIn').innerHTML = AREAS.map(a => `<option ${a === cur.area ? 'selected' : ''}>${a}</option>`).join('');
  const tabs = Style.mode === 'toon' ? TABS_TOON : TABS_HUM; if (!tabs.some(t => t[0] === tab)) tab = tabs[0][0];
  $('#ic').innerHTML = tabs.map(([k, e, n]) => `<button data-t="${k}" class="${k === tab ? 'sel' : ''}">${e}<small>${n}</small></button>`).join('');
  $('#ic').querySelectorAll('button').forEach(b => b.onclick = () => { tab = b.dataset.t; $('#ic').querySelectorAll('button').forEach(x => x.classList.toggle('sel', x === b)); renderPanel(); });
  $('#act').innerHTML = CLIPS.map(([k, n]) => `<button data-c="${k}" class="${k === clip ? 'sel' : ''}">${n}</button>`).join('');
  $('#act').querySelectorAll('button').forEach(b => b.onclick = async () => { clip = b.dataset.c; $('#act').querySelectorAll('button').forEach(x => x.classList.toggle('sel', x === b)); if (model) await setClip(model, clip); });
  holder.rotation.y = 0; requestAnimationFrame(() => { resize(); }); rebuild(); renderPanel(); history.replaceState(null, '', link('personajes?id=' + id));
}
$('#nmIn').oninput = () => { cur.name = $('#nmIn').value; dirty = true; }; $('#roleIn').onchange = () => { cur.area = $('#roleIn').value; dirty = true; };
function set(path, val, rebuildIt = true) { if (val === 'true') val = true; else if (val === 'false') val = false; const t = Style.mode === 'toon' ? cur.toon : cur.human; t[path] = val; dirty = true; cur.custom = true; if (rebuildIt) rebuild(); renderPanel(); }
function setAcc(k) { const t = Style.mode === 'toon' ? cur.toon : cur.human; t.acc = { ...(t.acc || {}) }; t.acc[k] = !t.acc[k]; dirty = true; rebuild(); renderPanel(); }
function colors(key, list, curv) { return `<div class="cw">${list.map(c => `<button data-k="${key}" data-c="${c}" style="background:${c}" class="${(curv || '').toLowerCase() === c.toLowerCase() ? 's' : ''}"></button>`).join('')}<input type="color" data-k="${key}" value="${/^#/.test(curv || '') ? curv : '#ffffff'}" title="Otro color"></div>`; }
async function optGrid(key, opts, curv, framing, mk) {
  const P = $('#og-' + key); if (!P) return; P.innerHTML = '';
  for (const [v, n] of opts) { const b = document.createElement('button'); b.className = 'o' + (v === curv ? ' sel' : ''); b.innerHTML = `<img><span>${n}</span>`; b.onclick = () => set(key, v); P.appendChild(b);
    const probe = JSON.parse(JSON.stringify(cur)); mk(probe, v); thumb(probe, framing, 200, 150).then(u => b.querySelector('img').src = u); }
}
function renderPanel() {
  const P = $('#pan'); const toon = Style.mode === 'toon'; const a = toon ? cur.toon : cur.human; let h = '';
  const wire = () => { P.querySelectorAll('.cw button').forEach(b => b.onclick = () => set(b.dataset.k, b.dataset.c)); P.querySelectorAll('.cw input[type=color]').forEach(i => i.onchange = () => set(i.dataset.k, i.value)); P.querySelectorAll('[data-tg]').forEach(b => b.onclick = () => set(b.dataset.tg, b.dataset.v)); P.querySelectorAll('[data-acc]').forEach(b => b.onclick = () => setAcc(b.dataset.acc)); P.querySelectorAll('input[type=range]').forEach(r => { r.oninput = () => { a[r.dataset.k] = +r.value; dirty = true; cur.custom = true; clearTimeout(r._t); r._t = setTimeout(rebuild, 60); }; }); };
  const tg = (key, opts) => `<div class="tg">${opts.map(([v, n]) => `<button data-tg="${key}" data-v="${v}" class="${a[key] === v ? 'sel' : ''}">${n}</button>`).join('')}</div>`;
  if (toon) {
    if (tab === 'cuerpo') h = `<div class="ey">Cuerpo</div><h2>Contextura y piel</h2>${tg('body', OPT.body)}<div class="sl">Estatura <input type="range" data-k="height" min=".85" max="1.15" step=".01" value="${a.height || 1}"></div><div class="sec ey">Tono de piel</div>${colors('skin', OPT.skin, a.skin)}`;
    if (tab === 'cara') h = `<div class="ey">Cara</div><h2>Ojos, cejas y boca</h2><div class="sec ey">Ojos</div>${tg('eyes', OPT.eyes)}<div class="sec ey">Cejas</div>${tg('brows', OPT.brows)}<div class="sec ey">Boca</div>${tg('mouth', OPT.mouth)}<div class="sec ey">Detalles</div><div class="tg"><button data-tg="blush" data-v="${!a.blush}" class="${a.blush ? 'sel' : ''}">Mejillas rosadas</button><button data-tg="freckles" data-v="${!a.freckles}" class="${a.freckles ? 'sel' : ''}">Pecas</button></div>`;
    if (tab === 'pelo') h = `<div class="ey">Pelo</div><h2>Elige el peinado</h2><div class="og" id="og-hair"></div><div class="sl">Largo <input type="range" data-k="hairLen" min="0" max="1" step=".05" value="${a.hairLen ?? .6}"></div><div class="sl">Volumen <input type="range" data-k="hairVol" min="0" max="1" step=".05" value="${a.hairVol ?? .5}"></div><div class="sec ey">Color</div>${colors('hairColor', OPT.hairColor, a.hairColor)}`;
    if (tab === 'barba') h = `<div class="ey">Barba</div><h2>Tipo y color</h2><div class="og" id="og-beard"></div><div class="sec ey">Color</div>${colors('beardColor', OPT.hairColor, a.beardColor)}`;
    if (tab === 'arriba') h = `<div class="ey">Arriba</div><h2>Elige la prenda</h2><div class="og" id="og-top"></div><div class="sec ey">Color de la prenda</div>${colors('topColor', OPT.colors, a.topColor)}<div class="sec ey">Debajo (camisa interior / cuello)</div>${colors('innerColor', ['#ffffff', '#111111', '#f20b6d', '#7c3aed', '#9ca3af', '#93c5fd'], a.innerColor)}<div class="sec ey">Colores de la marca</div>${colors('topColor', BRAND, a.topColor)}${a.complete !== 'ninguno' ? '<div class="note">⚠ Tiene un completo (vestido/overol) puesto: quítalo en "Completo" para ver esta prenda.</div>' : ''}`;
    if (tab === 'abajo') h = `<div class="ey">Abajo</div><h2>Pantalón, short o falda</h2><div class="og" id="og-bottom"></div><div class="sec ey">Color</div>${colors('bottomColor', OPT.colors, a.bottomColor)}`;
    if (tab === 'completo') h = `<div class="ey">Completo</div><h2>Vestido u overol</h2><div class="og" id="og-complete"></div><div class="sec ey">Color</div>${colors('completeColor', OPT.colors, a.completeColor)}`;
    if (tab === 'zapatos') h = `<div class="ey">Zapatos</div><h2>Calzado</h2><div class="og" id="og-shoes"></div><div class="sec ey">Color</div>${colors('shoesColor', OPT.colors, a.shoesColor)}`;
    if (tab === 'acc') h = `<div class="ey">Accesorios</div><h2>Puedes ponerle varios</h2><div class="og" id="og-acc"></div><div class="sec ey">Color (gorra, delantal, reloj)</div>${colors('accColor', [...BRAND, ...OPT.colors.slice(0, 10)], a.accColor)}`;
  } else {
    if (tab === 'persona') h = `<div class="ey">Persona base</div><h2>Elige la persona</h2><div class="og" id="og-base"></div><div class="note">En estilo Humano cada persona base trae su cuerpo, cara y ropa. Encima le cambias colores, accesorios y uniforme.</div>`;
    if (tab === 'cara') h = `<div class="ey">Piel</div><h2>Tono</h2>${colors('skinTint', ['#ffffff', '#ffe6d0', '#f0c8a8', '#d8a47f', '#b8835c', '#8f5f3d'], a.skinTint)}<div class="note">Ajusta el tono sobre la piel original de la persona.</div>`;
    if (tab === 'pelo') h = `<div class="ey">Pelo</div><h2>Color del pelo</h2>${colors('hairColor', OPT.hairColor, a.hairColor)}<div class="tg sec"><button data-tg="hairColor" data-v="">Color original</button></div><div class="note">El peinado viene con cada persona base: para otro peinado, elige otra persona en "Persona". Algunas personas no tienen pelo separado y el color no cambia.</div>`;
    if (tab === 'barba') h = `<div class="ey">Barba</div><h2>Tipo y color</h2><div class="tg">${OPT.beard.filter(b => b[0] !== 'bigote' && b[0] !== 'candado').map(([v, n]) => `<button data-tg="beard" data-v="${v}" class="${a.beard === v ? 'sel' : ''}">${n}</button>`).join('')}</div><div class="sec ey">Color</div>${colors('beardColor', OPT.hairColor, a.beardColor)}`;
    if (tab === 'arriba') h = `<div class="ey">Arriba</div><h2>Prenda de arriba</h2><div class="tg"><button data-tg="topStyle" data-v="original" class="${a.topStyle !== 'liso' ? 'sel' : ''}">Original (con estampado)</button><button data-tg="topStyle" data-v="liso" class="${a.topStyle === 'liso' ? 'sel' : ''}">Lisa de un color</button></div><div class="sec ey">Color de la prenda</div>${colors('topColor', OPT.colors, a.topColor)}<div class="sec ey">Colores de la marca</div>${colors('topColor', BRAND, a.topColor)}<div class="tg sec"><button data-tg="topColor" data-v="">Color original</button></div><div class="note">Para otro tipo de prenda (traje, chaleco, camisa) elige otra persona base en "Persona".</div>`;
    if (tab === 'abajo') h = `<div class="ey">Abajo</div><h2>Color del pantalón</h2>${colors('bottomColor', OPT.colors, a.bottomColor)}<div class="tg sec"><button data-tg="bottomColor" data-v="">Color original</button></div>`;
    if (tab === 'zapatos') h = `<div class="ey">Zapatos</div><h2>Color</h2>${colors('shoesColor', OPT.colors, a.shoesColor)}<div class="tg sec"><button data-tg="shoesColor" data-v="">Color original</button></div>`;
    if (tab === 'acc') h = `<div class="ey">Accesorios</div><h2>Puedes ponerle varios</h2><div class="tg">${HUMAN_ACC.map(k => `<button data-acc="${k}" class="${a.acc?.[k] ? 'sel' : ''}">${OPT.acc.find(x => x[0] === k)[1]}</button>`).join('')}</div><div class="sec ey">Color (gorra, delantal)</div>${colors('accColor', [...BRAND, ...OPT.colors.slice(0, 10)], a.accColor)}`;
  }
  if (tab === 'uniforme') h = `<div class="ey">Uniforme</div><h2>Uniformes de la empresa</h2><div class="tg">${uniforms.map(u => `<button data-uni="${u.id}" class="${cur.uniform === u.id ? 'sel' : ''}">${u.name}</button>`).join('')}<button data-uni="">Sin uniforme</button></div><div class="note">El uniforme cambia solo la ropa y los accesorios; el pelo y la cara se quedan. Para crear uno: viste a esta persona y toca "🏷 Guardar como uniforme".</div>`;
  P.innerHTML = h; wire();
  P.querySelectorAll('[data-uni]').forEach(b => b.onclick = () => { const u = uniforms.find(x => x.id === b.dataset.uni); cur.uniform = u ? u.id : null; if (u) { Object.assign(cur.toon, u.toon); Object.assign(cur.human, u.human); } dirty = true; cur.custom = true; rebuild(); renderPanel(); });
  // cuadrículas con miniaturas reales
  if (toon) {
    if (tab === 'pelo') optGrid('hair', OPT.hair, a.hair, 'head', (p, v) => p.toon.hair = v);
    if (tab === 'barba') optGrid('beard', OPT.beard, a.beard, 'head', (p, v) => { p.toon.beard = v; p.toon.hair = 'rapado'; });
    if (tab === 'arriba') optGrid('top', OPT.top, a.top, 'top', (p, v) => { p.toon.top = v; p.toon.complete = 'ninguno'; p.toon.acc = {}; });
    if (tab === 'abajo') optGrid('bottom', OPT.bottom, a.bottom, 'legs', (p, v) => { p.toon.bottom = v; p.toon.complete = 'ninguno'; });
    if (tab === 'completo') optGrid('complete', OPT.complete, a.complete, 'full', (p, v) => p.toon.complete = v);
    if (tab === 'zapatos') optGrid('shoes', OPT.shoes, a.shoes, 'feet', (p, v) => p.toon.shoes = v);
    if (tab === 'acc') { const G = $('#og-acc'); OPT.acc.forEach(([k, n]) => { const b = document.createElement('button'); b.className = 'o' + (a.acc?.[k] ? ' sel' : ''); b.innerHTML = `<img><span>${a.acc?.[k] ? '✓ ' : ''}${n}</span>`; b.onclick = () => setAcc(k); G.appendChild(b); const probe = JSON.parse(JSON.stringify(cur)); probe.toon.acc = { [k]: true }; thumb(probe, ['delantal', 'chaleco', 'reloj'].includes(k) ? 'top' : 'head', 200, 150).then(u => b.querySelector('img').src = u); }); }
  } else if (tab === 'persona') {
    const G = $('#og-base'); HUMAN_BASES.forEach(([k, n]) => { const b = document.createElement('button'); b.className = 'o' + (a.base === k ? ' sel' : ''); b.innerHTML = `<img><span>${n}</span>`; b.onclick = () => set('base', k); G.appendChild(b); const probe = JSON.parse(JSON.stringify(cur)); probe.human = { ...defaultHuman(), base: k }; thumb(probe, 'full', 200, 220).then(u => b.querySelector('img').src = u); });
  }
}
$('#back').onclick = () => { if (dirty && !confirm('Hay cambios sin guardar. ¿Salir igual?')) return; team = loadTeam(); history.replaceState(null, '', link('personajes')); renderTeam(); };
$('#save').onclick = () => { const all = loadTeam(); const i = all.findIndex(t => t.id === cur.id); if (i >= 0) all[i] = cur; else all.push(cur); team = all; saveTeam(team); dirty = false; Object.keys(cache).forEach(k => delete cache[k]); toast('Personaje guardado ✓'); };
$('#rnd').onclick = () => { if (Style.mode === 'toon') cur.toon = { ...randomToon() }; else { cur.human.base = HUMAN_BASES[Math.floor(Math.random() * HUMAN_BASES.length)][0]; cur.human.topColor = OPT.colors[Math.floor(Math.random() * OPT.colors.length)]; cur.human.topStyle = 'liso'; cur.human.bottomColor = OPT.colors[Math.floor(Math.random() * OPT.colors.length)]; } dirty = true; cur.custom = true; rebuild(); renderPanel(); };
$('#saveU').onclick = () => { const name = prompt('Nombre del uniforme (ej. Barra, Cocina, Salón):', cur.area); if (!name) return; const t = cur.toon, h = cur.human; const u = { id: 'u-' + uid(), name, desc: 'Creado desde ' + cur.name, toon: { top: t.top, topColor: t.topColor, innerColor: t.innerColor, bottom: t.bottom, bottomColor: t.bottomColor, complete: t.complete, completeColor: t.completeColor, shoes: t.shoes, shoesColor: t.shoesColor, acc: { ...(t.acc || {}) }, accColor: t.accColor }, human: { topColor: h.topColor, topStyle: h.topStyle, bottomColor: h.bottomColor, shoesColor: h.shoesColor, acc: { ...(h.acc || {}) }, accColor: h.accColor } }; uniforms.push(u); saveUniforms(uniforms); cur.uniform = u.id; toast('Uniforme "' + name + '" creado'); };
$('#copy').onclick = () => { const L = $('#copyL'); L.innerHTML = team.filter(t => t.id !== cur.id).map(t => `<button class="pill" data-id="${t.id}">${t.name} · ${t.role}</button>`).join(''); L.querySelectorAll('button').forEach(b => b.onclick = () => { const t = team.find(x => x.id === b.dataset.id); const keep = $('#copyKeep').checked; const KT = ['skin', 'hair', 'hairColor', 'hairLen', 'hairVol', 'eyes', 'brows', 'mouth', 'blush', 'freckles', 'beard', 'beardColor', 'body', 'height']; const nt = JSON.parse(JSON.stringify(cur.toon)), nh = JSON.parse(JSON.stringify(cur.human)); if (keep) { KT.forEach(k => nt[k] = t.toon[k]); nh.base = t.human.base; nh.hairColor = t.human.hairColor; nh.beard = t.human.beard; nh.skinTint = t.human.skinTint; } t.toon = nt; t.human = nh; t.custom = true; saveTeam(team); $('#copyM').classList.remove('show'); toast('Look copiado a ' + t.name); }); $('#copyM').classList.add('show'); };

// arranque
const qid = new URLSearchParams(location.search).get('id');
if (qid && team.find(t => t.id === qid)) openEdit(qid); else renderTeam();
window.__px = { openEdit, get cur() { return cur; }, set tab(v) { tab = v; renderPanel(); } };
