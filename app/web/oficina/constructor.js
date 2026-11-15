// Modo constructor (fase 1) · consola v2+ (solo Admin V2). Plano 2D a escala (canvas) + vista 3D en vivo (iframe con el
// motor de la oficina) + propiedades y "Conectar a" con las entidades reales de ESA empresa. Autoguardado del borrador;
// "Publicar en vivo" crea la versión publicada. Funciona con mouse y táctil (Pointer Events).
import * as R from '/admin-v2plus/oficina/constructor_reglas.js';

const API = '/admin-v2/api/constructor';
const $ = s => document.querySelector(s);
const esc = s => String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
const cid = (new URLSearchParams(location.search).get('empresa') || '').toLowerCase();
const S = {plan: null, items: [], byId: new Map(), sizes: {}, entities: {}, brand: {}, options: {}, history: new R.History(), sel: [], tool: 'select',
  zone: '', q: '', place: null, opening: 'puerta', wallMat: 'pintura', floorMat: 'madera_clara', paint: '#d8cfc4', zoneKind: 'salon',
  status: {version: 1, saving: false, error: ''}, warn: {cruces: [], puertas: [], sin_conectar: [], mesas_sin_objeto: []}, view: null, zoom: 1, pan: [0, 0],
  published: null, history_list: [], usa_plano: false, estilo: 'humano', preview: null, selWall: null, selOpening: null, selFloor: null};

async function req(url, opts = {}) {
  const r = await fetch(url, {credentials: 'same-origin', ...opts, headers: {Accept: 'application/json', ...(opts.body && typeof opts.body === 'string' ? {'Content-Type': 'application/json'} : {}), ...(opts.headers || {})}});
  if (r.status === 401) { location.href = '/admin-v2plus/login'; throw new Error('Sesión vencida.'); }
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error((typeof data.detail === 'string' && data.detail) || `Error ${r.status}`);
  return data;
}

// ------------------------------------------------------------------ carga
async function boot() {
  if (!/^[0-9a-f-]{36}$/.test(cid)) { $('#cxCompany').textContent = 'Abre el constructor desde la ficha de una empresa.'; return; }
  const [st, cat] = await Promise.all([req(`${API}/empresas/${cid}`), req(`${API}/catalogo`)]);
  S.items = cat.items; S.byId = new Map(S.items.map(x => [x.id, x])); S.sizes = R.sizesOf(S.items); S.cats = cat.categories;
  loadState(st);
  $('#cxPeople').href = `/admin-v2plus/oficina?piso=${encodeURIComponent(cid)}&personajes=1`;
  paintLeft(); bindUi(); resize(); openView(); paintProps();
}
function loadState(st) {
  S.plan = st.draft.plano; S.status.version = st.draft.version; S.entities = st.entities; S.brand = st.brand || {}; S.options = st.options;
  S.published = st.published; S.history_list = st.history; S.usa_plano = st.usa_plano; S.estilo = st.estilo_escena; S.warn = st.warnings;
  $('#cxCompany').textContent = `${st.company.name} · ${S.usa_plano ? 'plano en vivo' : 'plano apagado en vivo'}`;
  document.title = `Modo constructor · ${st.company.name}`;
  S.sel = []; status(); fitView();
}

// ------------------------------------------------------------------ panel izquierdo
function paintLeft() {
  const zones = [['', 'Todo'], ...(S.options.zones || []).filter(z => z.key !== 'otra').map(z => [z.key, z.label])];
  $('#cxZones').innerHTML = zones.map(([k, l]) => `<button type="button" data-zone="${k}" class="${S.zone === k ? 'on' : ''}">${esc(l)}</button>`).join('');
  const list = R.filterCatalog(S.items, {zone: S.zone, q: S.q});
  $('#cxGrid').innerHTML = list.map(it => `<button type="button" class="cx-item ${S.place === it.id ? 'on' : ''}" data-item="${esc(it.id)}" draggable="true" title="${esc(it.nombre)} · ${esc(it.licencia || '')}">
      ${it.mini ? `<img src="${esc(it.mini)}" alt="" loading="lazy">` : `<b aria-hidden="true">${esc(it.icono || '▣')}</b>`}${esc(it.nombre)}${it.conectable ? '<small>conectable</small>' : ''}</button>`).join('') || '<p class="cx-note">Nada con ese filtro.</p>';
  $('#cxTpls').innerHTML = (S.options.templates || []).map(t => `<button type="button" data-tpl="${t.key}">${{bar: '🍸', restaurante: '🍽️', taller: '🧵', callcenter: '🎧', bodega: '📦', oficina: '🏢'}[t.key] || ''} ${esc(t.label)}</button>`).join('');
  $('#cxOpenings').innerHTML = (S.options.openings || []).map(o => `<button type="button" data-open="${o.key}" class="${S.opening === o.key ? 'on' : ''}">${esc(o.label)}</button>`).join('');
  $('#cxWalls').innerHTML = (S.options.walls || []).map(o => `<button type="button" data-wallmat="${o.key}" class="${S.wallMat === o.key ? 'on' : ''}">${esc(o.label)}</button>`).join('');
  $('#cxFloors').innerHTML = (S.options.floors || []).map(o => `<button type="button" data-floormat="${o.key}" class="${S.floorMat === o.key ? 'on' : ''}">${esc(o.label)}</button>`).join('');
  $('#cxPaintSw').innerHTML = R.swatches({variantes: ['#d8cfc4', '#f5f5f4', '#9a3b2e', '#3a2418', '#111111', '#1e3a5f']}, S.brand).map(c => `<button type="button" data-paintc="${c}" style="background:${c}" aria-label="Color ${c}"></button>`).join('');
  $('#cxZoneKind').innerHTML = (S.options.zones || []).map(z => `<option value="${z.key}" ${S.zoneKind === z.key ? 'selected' : ''}>${esc(z.label)}</option>`).join('');
  const sala = S.plan.sala; document.querySelectorAll('[data-sala]').forEach(i => { i.value = sala[i.dataset.sala]; });
  $('#cxStyle').innerHTML = (S.options.styles || []).map(s => `<option value="${s.key}" ${S.estilo === s.key ? 'selected' : ''}>${esc(s.label)}</option>`).join('');
  $('#cxPreviewStyle').textContent = `Previsualizar en ${(S.preview || S.estilo) === 'caricatura' ? 'Humano' : 'Caricatura'}`;
}

// ------------------------------------------------------------------ guardado
let saveTimer = null, saving = null;
function change(mutator, {keepSel = false} = {}) {
  S.history.push(S.plan); mutator(S.plan); if (!keepSel) S.sel = S.sel.filter(id => S.plan.objetos.some(o => o.id === id));
  S.warn = R.warnings(S.plan, S.sizes, S.entities); draw(); paintProps(); schedule(); pushView();
}
function schedule() { clearTimeout(saveTimer); S.status.saving = true; status(); saveTimer = setTimeout(save, 900); }
async function save() {
  if (saving) { await saving; }
  const body = JSON.stringify({plano: S.plan});
  saving = req(`${API}/empresas/${cid}/borrador`, {method: 'PUT', body}).then(r => { S.status = {version: r.version, saving: false, error: ''}; S.warn = r.warnings; paintProps(); })
    .catch(e => { S.status.saving = false; S.status.error = e.message; }).finally(() => { saving = null; status(); });
  return saving;
}
function status() { const el = $('#cxStatus'); el.className = 'cx-status' + (S.status.saving ? ' saving' : S.status.error ? ' err' : ''); el.querySelector('span').textContent = R.statusText(S.status);
  document.querySelector('[data-act="undo"]').disabled = !S.history.canUndo; document.querySelector('[data-act="redo"]').disabled = !S.history.canRedo; }
function undo() { const p = S.history.undo(S.plan); if (p) { S.plan = p; afterHistory(); } }
function redo() { const p = S.history.redo(S.plan); if (p) { S.plan = p; afterHistory(); } }
function afterHistory() { S.sel = S.sel.filter(id => S.plan.objetos.some(o => o.id === id)); S.warn = R.warnings(S.plan, S.sizes, S.entities); draw(); paintProps(); schedule(); pushView(); }

// ------------------------------------------------------------------ vista 3D (iframe con el motor de la oficina)
const view = () => $('#cxView');
function openView(style) {
  S.preview = style || null; const st = style || S.estilo;
  view().src = `/admin-v2plus/constructor/vista?empresa=${encodeURIComponent(cid)}&estilo=${st}`;
  $('#cxPreviewStyle').textContent = `Previsualizar en ${st === 'caricatura' ? 'Humano' : 'Caricatura'}`;
}
let viewTimer = null, lastSala = '';
function pushView() {
  clearTimeout(viewTimer);
  viewTimer = setTimeout(() => {
    const sala = JSON.stringify(S.plan.sala); if (lastSala && sala !== lastSala) { lastSala = sala; openView(S.preview); return; } lastSala = sala;
    const used = new Set(S.plan.objetos.map(o => o.asset));
    try { view().contentWindow.postMessage({type: 'cx-plan', payload: {plano: S.plan, catalogo: S.items.filter(x => used.has(x.id))}}, location.origin); } catch (e) { /* aún cargando */ }
  }, 250);
}
addEventListener('message', e => { if (e.origin === location.origin && e.data && e.data.type === 'cx-vista-lista') { lastSala = JSON.stringify(S.plan.sala); pushView(); } });

// ------------------------------------------------------------------ plano 2D
const cv = () => $('#cxPlan'); let ctx = null, DPR = 1;
function resize() { const c = cv(), b = $('#cxPlanBox').getBoundingClientRect(); DPR = Math.min(2, devicePixelRatio || 1); c.width = b.width * DPR; c.height = b.height * DPR; ctx = c.getContext('2d'); fitView(); }
function fitView() { if (!S.plan || !ctx) return; const b = $('#cxPlanBox').getBoundingClientRect(); const f = R.fit(S.plan.sala, b.width, b.height, 46);
  S.view = {k: f.k * S.zoom, ox: f.ox + S.pan[0] - (S.zoom - 1) * S.plan.sala.ancho * f.k / 2, oz: f.oz + S.pan[1] - (S.zoom - 1) * S.plan.sala.fondo * f.k / 2}; draw(); }
const P = (x, z) => R.toPx(S.view, x, z);
const CAT_COLOR = {mesas: '#6b4a8a', barra: '#7c1d4f', cocina: '#475569', caja: '#a16207', pantallas: '#0369a1', luces: '#a16207', decoracion: '#166534', taller: '#4338ca', oficina: '#334155',
  bodega: '#78350f', neveras: '#0e7490', sonido: '#1e1b4b', tienda: '#9d174d', exterior: '#3f6212', banos: '#0f766e'};
let drag = null, hover = null, ghost = null;
function draw() {
  if (!ctx || !S.view) return; const c = cv(); ctx.setTransform(DPR, 0, 0, DPR, 0, 0); const W = c.width / DPR, H = c.height / DPR; ctx.clearRect(0, 0, W, H);
  const v = S.view, sala = S.plan.sala;
  // cuadrícula (1 m y 10 cm con zoom)
  ctx.lineWidth = 1;
  for (const [step, a] of [[.1, .05], [1, .12]]) { if (step * v.k < 6) continue; ctx.strokeStyle = `rgba(255,255,255,${a})`; ctx.beginPath();
    for (let x = 0; x <= sala.ancho + 1e-6; x += step) { const [px] = P(x, 0); ctx.moveTo(px, P(0, 0)[1]); ctx.lineTo(px, P(0, sala.fondo)[1]); }
    for (let z = 0; z <= sala.fondo + 1e-6; z += step) { const [, pz] = P(0, z); ctx.moveTo(P(0, 0)[0], pz); ctx.lineTo(P(sala.ancho, 0)[0], pz); } ctx.stroke(); }
  // pisos y zonas
  for (const f of S.plan.pisos) { ctx.fillStyle = f.color + 'cc'; poly(f.puntos); ctx.fill(); if (S.selFloor === f.id) { ctx.strokeStyle = '#22d3ee'; ctx.lineWidth = 2; ctx.setLineDash([6, 4]); ctx.stroke(); ctx.setLineDash([]); } }
  ctx.font = '700 12px Inter'; ctx.textAlign = 'center';
  for (const z of S.plan.zonas) { const cx = z.puntos.reduce((a, p) => a + p[0], 0) / z.puntos.length, cz = z.puntos.reduce((a, p) => a + p[1], 0) / z.puntos.length;
    ctx.strokeStyle = 'rgba(167,139,250,.35)'; ctx.setLineDash([4, 4]); poly(z.puntos); ctx.stroke(); ctx.setLineDash([]);
    if (S.plan.zonas.length > 1) { ctx.fillStyle = 'rgba(255,255,255,.35)'; const [px, pz] = P(cx, cz); ctx.fillText(z.nombre.toUpperCase(), px, pz); } }
  // objetos (piso -> muebles -> pared/techo)
  const order = {piso: 0, muebles: 1, decoracion: 2, pared: 3, techo: 4}; const cross = new Set(S.warn.cruces.flat()), doors = new Set(S.warn.puertas.map(p => p[0]));
  for (const o of S.plan.objetos.slice().sort((a, b) => order[a.capa] - order[b.capa])) drawObj(o, cross.has(o.id) ? '#ef4444' : doors.has(o.id) ? '#f59e0b' : null);
  // paredes y aberturas
  for (const w of S.plan.paredes) { ctx.strokeStyle = S.selWall === w.id ? '#22d3ee' : w.material === 'vidrio' ? '#7dd3fc' : '#e9e4f0'; ctx.lineWidth = Math.max(3, w.grosor * v.k); ctx.lineCap = 'square';
    ctx.beginPath(); ctx.moveTo(...P(w.x1, w.z1)); ctx.lineTo(...P(w.x2, w.z2)); ctx.stroke(); }
  for (const a of S.plan.aberturas) drawOpening(a);
  // cotas de la sala
  ctx.fillStyle = '#a39fb3'; ctx.font = '600 12px Inter'; ctx.textAlign = 'center';
  const [x0, z0] = P(0, 0), [x1, z1] = P(sala.ancho, sala.fondo); ctx.fillText(R.fmtM(sala.ancho), (x0 + x1) / 2, z0 - 14); ctx.save(); ctx.translate(x0 - 16, (z0 + z1) / 2); ctx.rotate(-Math.PI / 2); ctx.fillText(R.fmtM(sala.fondo), 0, 0); ctx.restore();
  // selección
  for (const id of S.sel) { const o = S.plan.objetos.find(x => x.id === id); if (!o) continue; const pts = R.corners(o, S.sizes).map(([x, z]) => P(x, z));
    ctx.strokeStyle = '#38bdf8'; ctx.lineWidth = 2; ctx.setLineDash([6, 4]); ctx.beginPath(); pts.forEach((p, i) => (i ? ctx.lineTo(...p) : ctx.moveTo(...p))); ctx.closePath(); ctx.stroke(); ctx.setLineDash([]);
    ctx.fillStyle = '#38bdf8'; pts.forEach(p => ctx.fillRect(p[0] - 5, p[1] - 5, 10, 10)); }
  if (S.sel.length === 1) { const h = rotHandle(); if (h) { ctx.beginPath(); ctx.arc(h[0], h[1], 10, 0, 6.3); ctx.fillStyle = '#0ea5e9'; ctx.fill(); ctx.fillStyle = '#fff'; ctx.font = '700 13px Inter'; ctx.fillText('⟳', h[0], h[1] + 5); } }
  // herramientas en curso
  if (drag && drag.kind === 'box') { ctx.strokeStyle = '#38bdf8'; ctx.setLineDash([4, 3]); ctx.strokeRect(drag.px, drag.pz, drag.qx - drag.px, drag.qz - drag.pz); ctx.setLineDash([]); }
  if (drag && (drag.kind === 'rect')) { const [a, b] = P(drag.x, drag.z), [c2, d] = P(drag.x2, drag.z2); ctx.fillStyle = 'rgba(56,189,248,.18)'; ctx.fillRect(a, b, c2 - a, d - b); ctx.strokeStyle = '#38bdf8'; ctx.strokeRect(a, b, c2 - a, d - b); }
  if (S.wallDraft) { ctx.strokeStyle = '#f472b6'; ctx.lineWidth = 3; ctx.beginPath(); ctx.moveTo(...P(S.wallDraft.x, S.wallDraft.z)); ctx.lineTo(...P(S.wallDraft.x2, S.wallDraft.z2)); ctx.stroke();
    label(R.fmtM(Math.hypot(S.wallDraft.x2 - S.wallDraft.x, S.wallDraft.z2 - S.wallDraft.z)), ...P((S.wallDraft.x + S.wallDraft.x2) / 2, (S.wallDraft.z + S.wallDraft.z2) / 2)); }
  if (S.measure) { const m = S.measure; ctx.strokeStyle = '#fde047'; ctx.lineWidth = 2; ctx.setLineDash([5, 4]); ctx.beginPath(); ctx.moveTo(...P(m.x, m.z)); ctx.lineTo(...P(m.x2, m.z2)); ctx.stroke(); ctx.setLineDash([]);
    label(R.fmtM(Math.hypot(m.x2 - m.x, m.z2 - m.z)), ...P((m.x + m.x2) / 2, (m.z + m.z2) / 2)); }
  if (ghost) { const it = S.byId.get(ghost.id); if (it) drawObj({id: '_g', asset: it.id, x: ghost.x, z: ghost.z, rot: 0, escala: 1, capa: it.capa || 'muebles'}, null, .5); }
}
function label(t, x, y) { ctx.font = '700 12px Inter'; const w = ctx.measureText(t).width + 12; ctx.fillStyle = '#111'; ctx.fillRect(x - w / 2, y - 22, w, 18); ctx.fillStyle = '#fde047'; ctx.textAlign = 'center'; ctx.fillText(t, x, y - 9); }
function poly(pts) { ctx.beginPath(); pts.forEach(([x, z], i) => { const [px, pz] = P(x, z); i ? ctx.lineTo(px, pz) : ctx.moveTo(px, pz); }); ctx.closePath(); }
function drawObj(o, bad, alpha = 1) {
  const it = S.byId.get(o.asset) || {}; const [w, d] = R.footprint(o, S.sizes); const [cx, cz] = P(o.x, o.z); const k = S.view.k;
  ctx.save(); ctx.globalAlpha = alpha; ctx.translate(cx, cz); ctx.rotate((o.rot || 0) * Math.PI / 180);
  const col = o.color || (it.variantes || [])[0] || CAT_COLOR[it.categoria] || '#6b7280';
  const round = /table_round|table_high|table_outdoor|table_umbrella|stool|pouf|plant|umbrella|pendant|spot/.test(it.forma || '');
  ctx.fillStyle = it.capa === 'techo' ? 'rgba(250,204,21,.25)' : col + (it.capa === 'piso' ? '88' : 'dd'); ctx.strokeStyle = bad || 'rgba(0,0,0,.6)'; ctx.lineWidth = bad ? 3 : 1.2;
  ctx.beginPath(); if (round) ctx.ellipse(0, 0, w * k / 2, d * k / 2, 0, 0, 6.3); else ctx.rect(-w * k / 2, -d * k / 2, w * k, d * k); ctx.fill(); ctx.stroke();
  if (o.conexion && o.conexion.tipo === 'mesa') { ctx.beginPath(); ctx.arc(0, 0, Math.min(w, d) * k * .28, 0, 6.3); ctx.fillStyle = '#2a1a3a'; ctx.fill(); ctx.lineWidth = 3; ctx.strokeStyle = '#22c55e'; ctx.stroke(); }
  ctx.rotate(-(o.rot || 0) * Math.PI / 180);
  const txt = R.badge(o.conexion) || (w * k > 40 && d * k > 16 ? (o.texto || it.nombre || '').slice(0, 18) : '');
  if (txt) { ctx.fillStyle = '#fff'; ctx.font = `${R.badge(o.conexion) ? 800 : 700} ${R.badge(o.conexion) ? 14 : 11}px Inter`; ctx.textAlign = 'center'; ctx.fillText(txt, 0, 4); }
  ctx.restore();
}
function drawOpening(a) {
  const w = S.plan.paredes.find(x => x.id === a.pared); if (!w) return; const L = R.wallLen(w); const ux = (w.x2 - w.x1) / L, uz = (w.z2 - w.z1) / L;
  const p1 = P(w.x1 + ux * (a.pos - a.ancho / 2), w.z1 + uz * (a.pos - a.ancho / 2)), p2 = P(w.x1 + ux * (a.pos + a.ancho / 2), w.z1 + uz * (a.pos + a.ancho / 2));
  ctx.strokeStyle = '#100e17'; ctx.lineWidth = Math.max(4, w.grosor * S.view.k + 2); ctx.beginPath(); ctx.moveTo(...p1); ctx.lineTo(...p2); ctx.stroke();
  const door = R.DOORS.includes(a.tipo); ctx.strokeStyle = S.selOpening === a.id ? '#22d3ee' : door ? '#a78bfa' : '#7dd3fc'; ctx.lineWidth = 2;
  if (door) { ctx.setLineDash([5, 4]); ctx.beginPath(); const r = a.ancho * S.view.k; const ang = Math.atan2(p2[1] - p1[1], p2[0] - p1[0]); ctx.arc(p1[0], p1[1], r, ang, ang - Math.PI / 2, true); ctx.stroke(); ctx.setLineDash([]); }
  else { ctx.beginPath(); ctx.moveTo(...p1); ctx.lineTo(...p2); ctx.stroke(); }
}
function rotHandle() { const o = S.plan.objetos.find(x => x.id === S.sel[0]); if (!o) return null; const [, d] = R.footprint(o, S.sizes); const a = (o.rot || 0) * Math.PI / 180;
  const off = d / 2 + 18 / S.view.k; return P(o.x + Math.sin(a) * off, o.z - Math.cos(a) * off); }

// ------------------------------------------------------------------ interacción (mouse y táctil)
function pt(e) { const r = cv().getBoundingClientRect(); const px = e.clientX - r.left, pz = e.clientY - r.top; const [x, z] = R.toM(S.view, px, pz); return {px, pz, x, z, free: e.altKey}; }
const pointers = new Map();
function down(e) {
  cv().focus(); cv().setPointerCapture(e.pointerId); pointers.set(e.pointerId, [e.clientX, e.clientY]);
  if (pointers.size === 2) { drag = {kind: 'pinch', d0: dist2(), zoom: S.zoom}; return; }
  const p = pt(e);
  if (e.button === 1 || e.button === 2 || (e.button === 0 && S.space)) { drag = {kind: 'pan', sx: e.clientX, sy: e.clientY, pan: [...S.pan]}; return; }
  if (S.place) { const it = S.byId.get(S.place); if (it) { let id; change(pl => { id = R.addObject(pl, it, R.snap(p.x, p.free), R.snap(p.z, p.free)).id; }); S.sel = [id]; draw(); paintProps(); } if (!e.shiftKey) { S.place = null; paintLeft(); } return; }
  const tool = S.tool;
  if (tool === 'wall') { const x = R.snap(p.x, p.free), z = R.snap(p.z, p.free);
    if (!S.wallDraft) S.wallDraft = {x, z, x2: x, z2: z};
    else { const d = S.wallDraft; change(pl => { R.addWall(pl, d.x, d.z, x, z, {material: S.wallMat, color: S.paint}); }); S.wallDraft = {x, z, x2: x, z2: z}; }
    draw(); return; }
  if (tool === 'opening') { const sz = ((S.options.openings || []).find(o => o.key === S.opening) || {}).size || [.9, 2.1, 0]; let ok = null;
    change(pl => { ok = R.addOpening(pl, p.x, p.z, S.opening, sz); }); if (!ok) toast('Haz clic junto a una pared (y que quepa la abertura).'); return; }
  if (tool === 'floor' || tool === 'zone' || tool === 'measure') { const x = R.snap(p.x, p.free), z = R.snap(p.z, p.free); drag = {kind: tool === 'measure' ? 'measure' : 'rect', x, z, x2: x, z2: z};
    if (tool === 'measure') S.measure = {x, z, x2: x, z2: z}; return; }
  if (tool === 'paint') { paintAt(p); return; }
  // seleccionar
  if (S.sel.length === 1) { const h = rotHandle(); if (h && Math.hypot(h[0] - p.px, h[1] - p.pz) < 14) { S.history.push(S.plan); drag = {kind: 'rotate'}; return; } }
  const id = R.hitObject(S.plan, p.x, p.z, S.sizes);
  if (id) { if (e.shiftKey || e.ctrlKey || e.metaKey) S.sel = S.sel.includes(id) ? S.sel.filter(x => x !== id) : [...S.sel, id]; else if (!S.sel.includes(id)) S.sel = [id];
    S.selWall = S.selOpening = S.selFloor = null;
    S.history.push(S.plan); drag = {kind: 'move', x: p.x, z: p.z, moved: false, start: S.sel.map(i => { const o = S.plan.objetos.find(q => q.id === i); return [i, o.x, o.z]; })}; draw(); paintProps(); return; }
  const op = openingAt(p); if (op) { S.sel = []; S.selOpening = op.id; S.selWall = S.selFloor = null; draw(); paintProps(); return; }
  const nw = R.nearestWall(S.plan, p.x, p.z); if (nw && nw.dist * S.view.k < 8) { S.sel = []; S.selWall = nw.wall.id; S.selOpening = S.selFloor = null; draw(); paintProps(); return; }
  S.selWall = S.selOpening = null; S.selFloor = (S.plan.pisos.slice().reverse().find(f => R.inPoly([p.x, p.z], f.puntos)) || {}).id || null;
  if (!e.shiftKey) S.sel = []; drag = {kind: 'box', px: p.px, pz: p.pz, qx: p.px, qz: p.pz}; draw(); paintProps();
}
function dist2() { const [a, b] = [...pointers.values()]; return Math.hypot(a[0] - b[0], a[1] - b[1]); }
function move(e) {
  if (pointers.has(e.pointerId)) pointers.set(e.pointerId, [e.clientX, e.clientY]);
  const p = pt(e);
  if (S.wallDraft && S.tool === 'wall') { S.wallDraft.x2 = R.snap(p.x, p.free); S.wallDraft.z2 = R.snap(p.z, p.free); draw(); }
  if (!drag) return;
  if (drag.kind === 'pinch' && pointers.size === 2) { S.zoom = Math.max(.4, Math.min(6, drag.zoom * dist2() / drag.d0)); fitView(); return; }
  if (drag.kind === 'pan') { S.pan = [drag.pan[0] + e.clientX - drag.sx, drag.pan[1] + e.clientY - drag.sy]; fitView(); return; }
  if (drag.kind === 'move') { const dx = p.x - drag.x, dz = p.z - drag.z; drag.moved = drag.moved || Math.hypot(dx, dz) * S.view.k > 3;
    for (const [i, x0, z0] of drag.start) { const o = S.plan.objetos.find(q => q.id === i); if (o) { o.x = R.snap(x0 + dx, p.free); o.z = R.snap(z0 + dz, p.free); } }
    S.warn = R.warnings(S.plan, S.sizes, S.entities); draw(); return; }
  if (drag.kind === 'rotate') { const o = S.plan.objetos.find(x => x.id === S.sel[0]); if (o) { let a = Math.atan2(p.x - o.x, -(p.z - o.z)) * 180 / Math.PI; a = p.free ? a : Math.round(a / 15) * 15; o.rot = R.round(((a % 360) + 360) % 360, 1); draw(); paintProps(); } return; }
  if (drag.kind === 'box') { drag.qx = p.px; drag.qz = p.pz; draw(); return; }
  if (drag.kind === 'rect' || drag.kind === 'measure') { drag.x2 = R.snap(p.x, p.free); drag.z2 = R.snap(p.z, p.free); if (drag.kind === 'measure') Object.assign(S.measure, {x2: drag.x2, z2: drag.z2}); draw(); }
}
function up(e) {
  pointers.delete(e.pointerId); const d = drag; drag = null; if (!d) return;
  if (d.kind === 'move') { if (d.moved) { S.history.future = []; afterDrag(); } else S.history.past.pop(); }
  else if (d.kind === 'rotate') afterDrag();
  else if (d.kind === 'box') { const [a, b] = R.toM(S.view, Math.min(d.px, d.qx), Math.min(d.pz, d.qz)), [c2, e2] = R.toM(S.view, Math.max(d.px, d.qx), Math.max(d.pz, d.qz));
    if (Math.abs(d.qx - d.px) > 4) S.sel = [...new Set([...S.sel, ...S.plan.objetos.filter(o => o.x >= a && o.x <= c2 && o.z >= b && o.z <= e2).map(o => o.id)])]; draw(); paintProps(); }
  else if (d.kind === 'rect') { if (S.tool === 'floor') change(pl => { R.addFloor(pl, d.x, d.z, d.x2, d.z2, S.floorMat, S.paint); });
    else { const lab = ((S.options.zones || []).find(z => z.key === S.zoneKind) || {}).label || 'Zona'; change(pl => { R.addZone(pl, d.x, d.z, d.x2, d.z2, S.zoneKind, lab); }); } }
}
function afterDrag() { S.warn = R.warnings(S.plan, S.sizes, S.entities); draw(); paintProps(); schedule(); pushView(); }
function openingAt(p) { for (const a of S.plan.aberturas) { const w = S.plan.paredes.find(x => x.id === a.pared); if (!w) continue; const L = R.wallLen(w); const ux = (w.x2 - w.x1) / L, uz = (w.z2 - w.z1) / L;
  const cx = w.x1 + ux * a.pos, cz = w.z1 + uz * a.pos; if (Math.hypot(p.x - cx, p.z - cz) < a.ancho / 2 + .1) return a; } return null; }
function paintAt(p) {
  const nw = R.nearestWall(S.plan, p.x, p.z);
  if (nw && nw.dist * S.view.k < 10) { change(pl => { const w = pl.paredes.find(x => x.id === nw.wall.id); w.material = S.wallMat; w.color = S.paint; }); return; }
  const f = S.plan.pisos.slice().reverse().find(x => R.inPoly([p.x, p.z], x.puntos));
  if (f) change(pl => { const x = pl.pisos.find(q => q.id === f.id); x.material = S.floorMat; x.color = S.paint; });
}
function finishWall() { S.wallDraft = null; draw(); }
function toast(t) { const el = $('#cxHelp'); el.textContent = t; el.style.color = '#fde68a'; clearTimeout(toast.t); toast.t = setTimeout(() => { el.style.color = ''; el.textContent = HELP; }, 3500); }
const HELP = 'Doble clic: duplicar · R: girar · Supr: borrar · Ctrl+Z: deshacer · Alt: sin cuadrícula · Rueda: zoom';

// ------------------------------------------------------------------ propiedades (derecha)
function paintProps() {
  const box = $('#cxProps'); if (!S.plan) return; const parts = [];
  const sel = S.sel.map(id => S.plan.objetos.find(o => o.id === id)).filter(Boolean);
  if (sel.length === 1) {
    const o = sel[0], it = S.byId.get(o.asset) || {}; const sw = R.swatches(it, S.brand);
    const con = it.conectable; const free = con ? R.freeEntities(S.plan, S.entities, con, o.id) : [];
    parts.push(`<div class="cx-card"><h4>OBJETO SELECCIONADO</h4><h2>${esc(it.nombre || o.asset)}</h2>
      <div class="cx-kv"><span>Posición x · z (m)</span><span style="display:flex;gap:4px"><input type="number" step="0.1" data-p="x" value="${o.x}" aria-label="Posición x"><input type="number" step="0.1" data-p="z" value="${o.z}" aria-label="Posición z"></span>
      <span>Rotación (°)</span><input type="number" step="15" data-p="rot" value="${o.rot}" aria-label="Rotación">
      <span>Escala</span><input type="number" step="0.1" min="0.2" max="5" data-p="escala" value="${o.escala}" aria-label="Escala">
      ${it.forma === 'neon' || (o.conexion && o.conexion.id === 'texto') ? `<span>Texto</span><input type="text" maxlength="40" data-p="texto" value="${esc(o.texto || '')}" aria-label="Texto">` : ''}</div>
      <p style="margin:10px 0 4px;color:var(--mut)">Color (paleta de la marca)</p><div class="cx-sw">${sw.map(c => `<button type="button" data-color="${c}" class="${(o.color || sw[0]) === c ? 'on' : ''}" style="background:${c}" aria-label="Color ${c}"></button>`).join('')}
      <input type="color" data-p="color" value="${o.color || sw[0] || '#888888'}" aria-label="Color libre" style="width:34px;height:28px;border:0;background:none;padding:0"></div>
      <div class="cx-acts"><button type="button" data-do="rot">⟲ Girar</button><button type="button" data-do="dup">⧉ Duplicar</button><button type="button" data-do="del">🗑 Borrar</button></div>
      ${con ? connCard(o, con, free) : ''}</div>`);
  } else if (sel.length > 1) {
    parts.push(`<div class="cx-card"><h4>${sel.length} OBJETOS</h4><h2>Alinear</h2><div class="cx-acts">
      ${[['left', '⇤ Izquierda'], ['centerx', '↔ Centro'], ['right', '⇥ Derecha'], ['top', '⤒ Arriba'], ['centerz', '↕ Medio'], ['bottom', '⤓ Abajo'], ['spreadx', '⇹ Repartir'], ['spreadz', '⇳ Repartir']].map(([k, l]) => `<button type="button" data-align="${k}">${l}</button>`).join('')}
      <button type="button" data-do="rot">⟲ Girar</button><button type="button" data-do="dup">⧉ Duplicar</button><button type="button" data-do="del">🗑 Borrar</button></div></div>`);
  } else if (S.selWall) { const w = S.plan.paredes.find(x => x.id === S.selWall); if (w) parts.push(`<div class="cx-card"><h4>PARED</h4><h2>${esc(R.fmtM(R.wallLen(w)))}</h2><div class="cx-kv">
      <span>Material</span><select data-w="material">${(S.options.walls || []).map(m => `<option value="${m.key}" ${m.key === w.material ? 'selected' : ''}>${esc(m.label)}</option>`).join('')}</select>
      <span>Color</span><input type="color" data-w="color" value="${w.color}"><span>Alto (m)</span><input type="number" step="0.1" data-w="alto" value="${w.alto}"><span>Grosor (m)</span><input type="number" step="0.01" data-w="grosor" value="${w.grosor}"></div>
      <div class="cx-acts"><button type="button" data-do="delwall">🗑 Borrar pared</button></div></div>`); }
  else if (S.selOpening) { const a = S.plan.aberturas.find(x => x.id === S.selOpening); if (a) parts.push(`<div class="cx-card"><h4>PUERTA / VENTANA</h4><div class="cx-kv">
      <span>Tipo</span><select data-a="tipo">${(S.options.openings || []).map(m => `<option value="${m.key}" ${m.key === a.tipo ? 'selected' : ''}>${esc(m.label)}</option>`).join('')}</select>
      <span>Ancho (m)</span><input type="number" step="0.1" data-a="ancho" value="${a.ancho}"><span>Posición (m)</span><input type="number" step="0.1" data-a="pos" value="${a.pos}"></div>
      <div class="cx-acts"><button type="button" data-do="delopen">🗑 Borrar</button></div></div>`); }
  else if (S.selFloor) { const f = S.plan.pisos.find(x => x.id === S.selFloor); if (f) parts.push(`<div class="cx-card"><h4>PISO</h4><div class="cx-kv">
      <span>Material</span><select data-f="material">${(S.options.floors || []).map(m => `<option value="${m.key}" ${m.key === f.material ? 'selected' : ''}>${esc(m.label)}</option>`).join('')}</select>
      <span>Color</span><input type="color" data-f="color" value="${f.color}"></div><div class="cx-acts"><button type="button" data-do="delfloor">🗑 Borrar piso</button></div></div>`); }
  else parts.push(`<div class="cx-card"><h4>PLANO</h4><h2>${esc(R.fmtM(S.plan.sala.ancho))} × ${esc(R.fmtM(S.plan.sala.fondo))}</h2><p style="color:var(--mut);margin:0">${S.plan.objetos.length} objetos · ${S.plan.paredes.length} paredes · ${S.plan.aberturas.length} puertas y ventanas. Toca un objeto para moverlo, girarlo o conectarlo.</p></div>`);
  const w = S.warn; const wl = [];
  if (w.mesas_sin_objeto.length) wl.push(`Mesas reales sin objeto: ${esc(w.mesas_sin_objeto.slice(0, 8).join(', '))}${w.mesas_sin_objeto.length > 8 ? '…' : ''}`);
  if (w.sin_conectar.length) wl.push(`${w.sin_conectar.length} objetos conectables sin conectar`);
  if (w.cruces.length) wl.push(`${w.cruces.length} cruces entre objetos (en rojo)`);
  if (w.puertas.length) wl.push(`${w.puertas.length} objetos tapan una puerta (en naranja)`);
  parts.push(`<div class="cx-card"><h4>AVISOS</h4>${wl.length ? `<ul class="cx-warn" style="margin:6px 0 0;padding-left:18px">${wl.map(x => `<li>${x}</li>`).join('')}</ul>` : '<p style="color:#86efac;margin:6px 0 0">Todo en orden.</p>'}</div>`);
  parts.push(`<div class="cx-card"><h4>EN VIVO</h4><p style="margin:4px 0 8px">${S.published ? `Publicada la versión ${S.published.version}.` : 'Aún no hay versión publicada.'} ${S.usa_plano ? '<b style="color:#86efac">El plano dibuja el piso en vivo.</b>' : '<span style="color:#fde68a">El plano está apagado en vivo para esta empresa (sigue el piso de siempre).</span>'}</p>
    ${S.published ? `<button type="button" class="cx-btn" data-do="toggleLive">${S.usa_plano ? 'Apagar el plano en vivo' : 'Encender el plano en vivo'}</button>` : ''}
    <h4 style="margin-top:12px">HISTORIAL</h4><ul class="cx-hist">${S.history_list.slice(0, 12).map(h => `<li><span>v${h.version} · ${esc((h.created_at || '').slice(0, 16).replace('T', ' '))} · ${h.objetos} obj.</span><button type="button" data-restore="${h.version}">Restaurar</button></li>`).join('') || '<li>Sin versiones publicadas.</li>'}</ul></div>`);
  parts.push(`<div class="cx-card"><b>Se guarda solo</b> <span style="color:var(--mut)">cada cambio, con historial de versiones. "Publicar en vivo" lo pasa al 3D que ve el dueño. El borrador nunca se ve en vivo.</span></div>`);
  box.innerHTML = parts.join('');
}
function connCard(o, tipo, free) {
  const name = {mesa: 'mesa con QR', puesto: 'puesto / máquina', escritorio: 'escritorio / persona', caja: 'caja', pantalla: 'pantalla'}[tipo];
  const now = o.conexion ? `<div class="cx-conn">🔗 <b>Conectada a: ${esc(R.label(S.entities, o.conexion))}</b><br>${tipo === 'mesa' ? 'Cuando la abran con el QR, aparece ocupada en vivo.' : tipo === 'pantalla' ? 'Muestra eso en vivo.' : 'Se mueve con los datos reales.'}</div>`
    : `<div class="cx-conn off">Sin conectar: elige la ${esc(name)} real.</div>`;
  return `${now}<label style="display:block;margin-top:8px;color:var(--mut)">Conectar a<select data-conn="${tipo}"><option value="">— Sin conectar —</option>${free.map(e => `<option value="${esc(e.id)}" ${o.conexion && o.conexion.id === e.id ? 'selected' : ''}>${esc(e.label)}</option>`).join('')}</select></label>`;
}

// ------------------------------------------------------------------ eventos
function bindUi() {
  const c = cv();
  c.addEventListener('pointerdown', down); c.addEventListener('pointermove', move); c.addEventListener('pointerup', up); c.addEventListener('pointercancel', up);
  c.addEventListener('contextmenu', e => e.preventDefault());
  c.addEventListener('dblclick', e => { const p = pt(e); if (S.tool === 'wall') { finishWall(); return; } const id = R.hitObject(S.plan, p.x, p.z, S.sizes); if (id) { let ids; change(pl => { ids = R.duplicate(pl, [id]); }); S.sel = ids; draw(); paintProps(); } });
  c.addEventListener('wheel', e => { e.preventDefault(); S.zoom = Math.max(.4, Math.min(6, S.zoom * (e.deltaY < 0 ? 1.12 : .89))); fitView(); }, {passive: false});
  c.addEventListener('dragover', e => { e.preventDefault(); const p = pt(e); ghost = {id: S.dragItem, x: R.snap(p.x, e.altKey), z: R.snap(p.z, e.altKey)}; draw(); });
  c.addEventListener('dragleave', () => { ghost = null; draw(); });
  c.addEventListener('drop', e => { e.preventDefault(); ghost = null; const it = S.byId.get(e.dataTransfer.getData('text/plain')); if (!it) return; const p = pt(e); let id;
    change(pl => { id = R.addObject(pl, it, R.snap(p.x, e.altKey), R.snap(p.z, e.altKey)).id; }); S.sel = [id]; draw(); paintProps(); });
  addEventListener('resize', resize);
  document.addEventListener('keydown', e => {
    const tag = (e.target.tagName || '').toLowerCase(); if (tag === 'input' || tag === 'select' || tag === 'textarea') return;
    const k = e.key.toLowerCase();
    if ((e.ctrlKey || e.metaKey) && k === 'z') { e.preventDefault(); e.shiftKey ? redo() : undo(); return; }
    if ((e.ctrlKey || e.metaKey) && k === 'y') { e.preventDefault(); redo(); return; }
    if ((e.ctrlKey || e.metaKey) && k === 'd') { e.preventDefault(); if (S.sel.length) { let ids; change(pl => { ids = R.duplicate(pl, S.sel); }); S.sel = ids; draw(); paintProps(); } return; }
    if (k === 'delete' || k === 'backspace' || k === 'supr') { if (S.sel.length) { const ids = S.sel.slice(); change(pl => R.remove(pl, ids)); S.sel = []; } return; }
    if (k === 'r' && S.sel.length) { const ids = S.sel.slice(); change(pl => R.rotate(pl, ids, e.shiftKey ? -45 : 45), {keepSel: true}); return; }
    if (k === 'escape') { finishWall(); S.place = null; S.measure = null; S.sel = []; draw(); paintProps(); paintLeft(); return; }
    if (k === ' ') { S.space = true; return; }
    const arrows = {arrowleft: [-1, 0], arrowright: [1, 0], arrowup: [0, -1], arrowdown: [0, 1]}[k];
    if (arrows && S.sel.length) { e.preventDefault(); const st = e.shiftKey ? .5 : .1; const ids = S.sel.slice(); change(pl => R.moveBy(pl, ids, arrows[0] * st, arrows[1] * st), {keepSel: true}); return; }
    const tool = {v: 'select', w: 'wall', p: 'opening', f: 'floor', t: 'paint', m: 'measure'}[k]; if (tool && !e.ctrlKey && !e.metaKey) setTool(tool);
  });
  document.addEventListener('keyup', e => { if (e.key === ' ') S.space = false; });
  document.addEventListener('click', onClick);
  document.addEventListener('change', onChange);
  document.addEventListener('dragstart', e => { const b = e.target.closest('[data-item]'); if (b) { S.dragItem = b.dataset.item; e.dataTransfer.setData('text/plain', b.dataset.item); e.dataTransfer.effectAllowed = 'copy'; } });
  $('#cxSearch').addEventListener('input', e => { S.q = e.target.value; paintLeft(); });
  $('#cxFile').addEventListener('change', importFile);
  window.addEventListener('beforeunload', e => { if (S.status.saving) { e.preventDefault(); e.returnValue = ''; } });
}
function setTool(t) { S.tool = t; S.wallDraft = null; S.measure = null; document.querySelectorAll('[data-tool]').forEach(b => b.classList.toggle('on', b.dataset.tool === t)); cv().style.cursor = t === 'select' ? 'default' : 'crosshair';
  const help = {wall: 'Paredes: clic a clic; doble clic o Esc termina · Alt: sin cuadrícula', opening: 'Puertas y ventanas: clic junto a una pared (tipo en Construir)', floor: 'Pisos: arrastra un rectángulo (material y color en Construir)',
    paint: 'Pintura: clic en una pared o un piso', measure: 'Medir: arrastra entre dos puntos', zone: 'Zona: arrastra un rectángulo'}[t]; $('#cxHelp').textContent = help || HELP; draw(); }
async function onClick(e) {
  const t = e.target.closest('button,a'); if (!t) return;
  if (t.dataset.tool) { setTool(t.dataset.tool); return; }
  if (t.dataset.tab) { document.querySelectorAll('[data-tab]').forEach(b => b.classList.toggle('on', b === t)); document.querySelectorAll('[data-pane]').forEach(p => { p.hidden = p.dataset.pane !== t.dataset.tab; }); return; }
  if (t.dataset.zone !== undefined) { S.zone = t.dataset.zone; paintLeft(); return; }
  if (t.dataset.item) { S.place = S.place === t.dataset.item ? null : t.dataset.item; setTool('select'); paintLeft(); toast(S.place ? 'Toca el plano para ponerlo (Shift: varios).' : HELP); return; }
  if (t.dataset.open) { S.opening = t.dataset.open; setTool('opening'); paintLeft(); return; }
  if (t.dataset.wallmat) { S.wallMat = t.dataset.wallmat; if (S.tool !== 'wall') setTool('paint'); paintLeft(); return; }
  if (t.dataset.floormat) { S.floorMat = t.dataset.floormat; if (S.tool !== 'floor') setTool('paint'); paintLeft(); return; }
  if (t.dataset.paintc) { S.paint = t.dataset.paintc; $('#cxPaint').value = S.paint; return; }
  if (t.dataset.tpl) { askTemplate(t.dataset.tpl); return; }
  if (t.dataset.color) { const c = t.dataset.color; const ids = S.sel.slice(); change(pl => pl.objetos.filter(o => ids.includes(o.id)).forEach(o => { o.color = c; }), {keepSel: true}); return; }
  if (t.dataset.align) { const ids = S.sel.slice(); change(pl => R.align(pl, ids, t.dataset.align), {keepSel: true}); return; }
  if (t.dataset.restore) { if (await confirmDlg(`¿Restaurar la versión ${t.dataset.restore} en el borrador? El borrador actual se reemplaza (puedes deshacer con otra versión).`)) {
    try { loadState(await req(`${API}/empresas/${cid}/restaurar`, {method: 'POST', body: JSON.stringify({version: Number(t.dataset.restore)})})); draw(); paintProps(); pushView(); } catch (err) { toast(err.message); } } return; }
  const d = t.dataset.do;
  if (d === 'rot') { const ids = S.sel.slice(); change(pl => R.rotate(pl, ids, 45), {keepSel: true}); }
  else if (d === 'dup') { let ids; const sel = S.sel.slice(); change(pl => { ids = R.duplicate(pl, sel); }); S.sel = ids; draw(); paintProps(); }
  else if (d === 'del') { const ids = S.sel.slice(); change(pl => R.remove(pl, ids)); S.sel = []; paintProps(); }
  else if (d === 'delwall') { const id = S.selWall; S.selWall = null; change(pl => R.remove(pl, [id])); }
  else if (d === 'delopen') { const id = S.selOpening; S.selOpening = null; change(pl => R.remove(pl, [id])); }
  else if (d === 'delfloor') { const id = S.selFloor; S.selFloor = null; change(pl => R.remove(pl, [id])); }
  else if (d === 'toggleLive') { try { const r = await req(`${API}/empresas/${cid}/ajustes`, {method: 'PUT', body: JSON.stringify({usa_plano: !S.usa_plano}), headers: {'X-Cx-Audit-Note': 'Plano del constructor en vivo'}}); S.usa_plano = r.usa_plano; paintProps(); } catch (err) { toast(err.message); } }
  const a = t.dataset.act;
  if (a === 'undo') undo(); else if (a === 'redo') redo();
  else if (a === 'export') { await save(); location.href = `${API}/empresas/${cid}/exportar`; }
  else if (a === 'import') $('#cxFile').click();
  else if (a === 'templates') { document.querySelector('[data-tab="objects"]').click(); $('#cxTpls').scrollIntoView({behavior: 'smooth'}); $('#cxTpls').animate([{outline: '2px solid #f20b6d'}, {outline: '2px solid transparent'}], 1200); }
  else if (a === 'publish') publish();
  if (t.id === 'cxPreviewStyle') openView(((S.preview || S.estilo) === 'caricatura') ? 'humano' : 'caricatura');
}
function onChange(e) {
  const t = e.target;
  if (t.id === 'cxPaint') { S.paint = t.value; return; }
  if (t.id === 'cxZoneKind') { S.zoneKind = t.value; return; }
  if (t.id === 'cxStyle') { saveStyle(t.value); return; }
  if (t.dataset.sala) { const v = Number(t.value), k = t.dataset.sala; if (!Number.isFinite(v)) return; change(pl => { pl.sala[k] = R.round(v); }); fitView(); return; }
  if (t.dataset.p) { const k = t.dataset.p, ids = S.sel.slice(); const v = k === 'color' || k === 'texto' ? t.value : Number(t.value); if (k !== 'color' && k !== 'texto' && !Number.isFinite(v)) return;
    change(pl => pl.objetos.filter(o => ids.includes(o.id)).forEach(o => { o[k] = k === 'rot' ? ((v % 360) + 360) % 360 : v; }), {keepSel: true}); return; }
  if (t.dataset.conn !== undefined) { const ids = S.sel.slice(); let res; change(pl => { res = R.connect(pl, ids[0], t.dataset.conn, t.value || null); }, {keepSel: true}); if (res && !res.ok) toast(res.msg); return; }
  if (t.dataset.w) { const id = S.selWall, k = t.dataset.w; change(pl => { const w = pl.paredes.find(x => x.id === id); w[k] = k === 'material' || k === 'color' ? t.value : Number(t.value); }); return; }
  if (t.dataset.a) { const id = S.selOpening, k = t.dataset.a; change(pl => { const a = pl.aberturas.find(x => x.id === id); a[k] = k === 'tipo' ? t.value : Number(t.value);
    if (k === 'tipo') { const o = (S.options.openings || []).find(x => x.key === t.value); if (o) { a.alto = o.size[1]; a.base = o.door ? 0 : o.size[2]; } } }); return; }
  if (t.dataset.f) { const id = S.selFloor, k = t.dataset.f; change(pl => { pl.pisos.find(x => x.id === id)[k] = t.value; }); }
}
async function saveStyle(v) {
  try { const r = await req(`${API}/empresas/${cid}/ajustes`, {method: 'PUT', body: JSON.stringify({estilo_escena: v}), headers: {'X-Cx-Audit-Note': 'Estilo de la escena 3D'}}); S.estilo = r.estilo_escena; openView(); paintLeft(); toast(`Estilo de la empresa: ${v === 'caricatura' ? 'Caricatura' : 'Humano'}`); }
  catch (err) { toast(err.message); }
}
async function askTemplate(key) {
  const lab = ((S.options.templates || []).find(t => t.key === key) || {}).label || key;
  if (!(await confirmDlg(`¿Empezar desde la plantilla ${lab}? El borrador actual se reemplaza (las versiones publicadas no cambian). Las mesas reales se conectan solas.`))) return;
  try { S.history.push(S.plan); const st = await req(`${API}/empresas/${cid}/plantilla`, {method: 'POST', body: JSON.stringify({plantilla: key})}); const h = S.history; loadState(st); S.history = h; draw(); paintProps(); pushView(); paintLeft(); }
  catch (err) { toast(err.message); }
}
async function importFile(e) {
  const f = e.target.files[0]; e.target.value = ''; if (!f) return;
  if (!(await confirmDlg(`¿Cargar "${f.name}" como borrador de esta empresa? Las conexiones no viajan entre empresas: quedará sin conectar.`))) return;
  try { const st = await req(`${API}/empresas/${cid}/importar`, {method: 'POST', body: await f.arrayBuffer(), headers: {'Content-Type': 'application/json'}}); S.history.push(S.plan); const h = S.history; loadState(st); S.history = h; draw(); paintProps(); pushView(); paintLeft(); toast('Plano importado como borrador.'); }
  catch (err) { toast('Archivo rechazado: ' + err.message); }
}
async function publish() {
  await save(); if (S.status.error) { toast('Corrige el error antes de publicar: ' + S.status.error); return; }
  const dlg = $('#cxDlg'); const w = S.warn;
  dlg.innerHTML = `<form method="dialog"><h2 style="margin-top:0">Publicar en vivo</h2><p>Se crea la versión ${S.status.version}. ${w.mesas_sin_objeto.length || w.sin_conectar.length ? `<br><span style="color:#fde68a">Ojo: ${w.mesas_sin_objeto.length} mesas reales sin objeto y ${w.sin_conectar.length} objetos sin conectar.</span>` : ''}</p>
    ${S.usa_plano ? '<p style="color:#86efac">El plano ya está encendido en vivo para esta empresa: el piso cambia al publicar.</p>' : `<label style="display:flex;gap:8px;align-items:flex-start"><input type="checkbox" id="cxOn"> <span>Encender el plano en vivo SOLO para esta empresa (hoy usa su piso de siempre). Sin marcar, la versión queda guardada pero el piso en vivo no cambia.</span></label>`}
    <div class="row"><button value="no">Cancelar</button><button value="si" class="pri">🚀 Publicar</button></div></form>`;
  dlg.showModal();
  dlg.onclose = async () => { if (dlg.returnValue !== 'si') return; const on = S.usa_plano || !!(dlg.querySelector('#cxOn') || {}).checked;
    try { const r = await req(`${API}/empresas/${cid}/publicar`, {method: 'POST', body: JSON.stringify({encender: on}), headers: {'X-Cx-Audit-Note': 'Publicar plano del constructor'}});
      S.published = {version: r.version}; S.history_list = r.history; S.usa_plano = r.usa_plano; S.status.version = r.version + 1; status(); paintProps(); toast(`Versión ${r.version} publicada${r.usa_plano ? ' · ya se ve en vivo' : ''}.`); }
    catch (err) { toast(err.message); } };
}
function confirmDlg(text) {
  return new Promise(res => { const dlg = $('#cxDlg'); dlg.innerHTML = `<form method="dialog"><p>${esc(text)}</p><div class="row"><button value="no">Cancelar</button><button value="si" class="pri">Sí, continuar</button></div></form>`;
    dlg.onclose = () => res(dlg.returnValue === 'si'); dlg.showModal(); });
}

if (!window.__CX_CONSTRUCTOR_TEST__) boot().catch(e => { $('#cxCompany').textContent = 'No se pudo cargar: ' + e.message; });
