// Biblioteca 3D (consola v2+, solo Admin V2): fuentes recomendadas, subir modelos (GLB/GLTF/FBX/OBJ/ZIP con
// formulario obligatorio y licencia), buscador de Poly Haven (API pública, CC0), revisión con vista previa 3D
// (Aprobar = aparece en el catálogo de todas las empresas), estadísticas del catálogo y Créditos 3D.
import * as THREE from 'three';
import {GLTFLoader} from 'three/addons/loaders/GLTFLoader.js';
import {MeshoptDecoder} from 'three/addons/libs/meshopt_decoder.module.js';

const API = '/admin-v2/api/constructor';
const $ = s => document.querySelector(s);
const esc = s => String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
export const SOURCES = [
  ['Poly Haven', 'https://polyhaven.com/models', 'CC0 · sin atribución obligatoria'],
  ['Kenney', 'https://kenney.nl/assets', 'CC0 · sin atribución obligatoria'],
  ['Quaternius', 'https://quaternius.com', 'CC0 · sin atribución obligatoria'],
  ['Sketchfab', 'https://sketchfab.com/search?features=downloadable&licenses=7c23a1ba438d4306920229c12afcb5f9&licenses=322a749bcfa841b29dff1e8a1bb74b0b&type=models', 'Solo descargables CC0 o CC-BY (guardar la atribución)'],
  ['Mixamo', 'https://www.mixamo.com', 'Personajes y animaciones · fase 2 · solo bucket privado'],
];
const ZONES = [['salon', 'Salón'], ['barra', 'Barra'], ['cocina', 'Cocina'], ['caja', 'Caja'], ['bodega', 'Bodega'], ['oficina', 'Oficina'], ['terraza', 'Terraza'], ['banos', 'Baños'],
  ['pista', 'Pista'], ['produccion', 'Producción'], ['recepcion', 'Recepción']];
let CATS = [];

async function req(url, opts = {}) {
  const r = await fetch(url, {credentials: 'same-origin', ...opts});
  if (r.status === 401) { location.href = '/admin-v2plus/login'; throw new Error('Sesión vencida.'); }
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error((typeof data.detail === 'string' && data.detail) || `Error ${r.status}`);
  return data;
}
const mb = n => `${(Number(n || 0) / 1048576).toFixed(2).replace('.', ',')} MB`;

async function load() {
  $('#libSrc').innerHTML = SOURCES.map(([n, u, l]) => `<a href="${esc(u)}" target="_blank" rel="noopener noreferrer"><b>${esc(n)}</b><small>${esc(l)}</small></a>`).join('');
  $('#libZones').innerHTML = ZONES.map(([k, l]) => `<label><input type="checkbox" name="zonas" value="${k}"> ${esc(l)}</label>`).join('');
  const all = await req(`${API}/catalogo?todos=1`);
  CATS = all.categories; $('#libCat').innerHTML = '<option value="">— Elige —</option>' + CATS.map(c => `<option value="${c.key}">${esc(c.label)}</option>`).join('');
  const rev = all.items.filter(x => x.estado === 'revision' || x.estado === 'fase2');
  $('#revList').innerHTML = rev.map(x => `<article><img src="${esc(x.mini || '')}" alt="" loading="lazy"><div><b>${esc(x.nombre)}</b> · ${esc(x.estado === 'fase2' ? 'Para fase 2 (personaje / esqueleto)' : 'En revisión')}<br>
      <small>${esc(x.categoria)} · ${(x.poligonos || 0).toLocaleString('es-CO')} triángulos · ${esc(fmtSize(x.medidas))} · ${mb(x.bytes)} · ${esc(x.licencia)}${x.autor ? ' · ' + esc(x.autor) : ''}</small><br><small>${esc(x.notas || '')}</small></div>
      <div class="row"><button type="button" data-view="${esc(x.id)}">Ver en 3D</button>${x.estado === 'revision' ? `<button type="button" class="pri" data-ok="${esc(x.id)}">Aprobar</button>` : ''}<button type="button" data-no="${esc(x.id)}">Rechazar</button></div></article>`).join('') || '<p class="cx-note">Nada en revisión.</p>';
  const pub = all.items.filter(x => x.estado === 'publicado');
  const by = {}; pub.forEach(x => { by[x.categoria] = (by[x.categoria] || 0) + 1; });
  $('#catTitle').textContent = `${pub.length} objetos publicados · ${mb(pub.reduce((a, x) => a + (x.bytes || 0), 0))} en archivos`;
  $('#catStats').innerHTML = `<table><tr><th>Categoría</th><th>Objetos</th></tr>${CATS.map(c => `<tr><td>${esc(c.label)}</td><td>${by[c.key] || 0}</td></tr>`).join('')}</table>`;
  const lic = {}; pub.forEach(x => { (lic[x.licencia] = lic[x.licencia] || []).push(x); });
  $('#credits').innerHTML = `<table><tr><th>Objeto</th><th>Licencia</th><th>Fuente</th><th>Autor / atribución</th></tr>${pub.map(x => `<tr><td>${esc(x.nombre)}</td><td>${esc(x.licencia)}</td>
      <td>${/^https:/.test(x.fuente || '') ? `<a href="${esc(x.fuente)}" target="_blank" rel="noopener noreferrer">${esc(x.fuente.replace(/^https:\/\//, ''))}</a>` : esc(x.fuente || '')}</td><td>${esc(x.atribucion || x.autor || '')}</td></tr>`).join('')}</table>
    <p class="cx-note">Resumen: ${Object.entries(lic).map(([k, v]) => `${esc(k)}: ${v.length}`).join(' · ')}. Texturas de paredes y pisos: Poly Haven (CC0, ver docs/oficina/LICENCIAS.md) y patrones dibujados por código. three.js r160 (MIT).</p>`;
}
function fmtSize(m) { return m ? `${m.w} × ${m.d} × ${m.h} m` : '—'; }

$('#libForm').addEventListener('submit', async e => {
  e.preventDefault(); const fd = new FormData(e.target); const msg = $('#libMsg');
  if (!fd.get('licencia')) { msg.textContent = 'Sin licencia no se publica.'; return; }
  const f = fd.get('archivo'); if (f && f.size > 50 * 1048576) { msg.textContent = 'El archivo pasa de 50 MB.'; return; }
  msg.textContent = 'Subiendo y convirtiendo…';
  try { const r = await req(`${API}/biblioteca/subir`, {method: 'POST', body: fd}); msg.textContent = `Listo: ${r.estado === 'fase2' ? 'guardado para la fase 2 (tiene esqueleto)' : 'en revisión'} · ${r.tris.toLocaleString('es-CO')} triángulos${r.warnings.length ? ' · ' + r.warnings.join(' ') : ''}`; e.target.reset(); load(); }
  catch (err) { msg.textContent = 'Rechazado: ' + err.message; }
});
async function search() {
  const q = $('#phQ').value.trim(); $('#phList').innerHTML = '<p class="cx-note">Buscando…</p>';
  try { const r = await req(`${API}/biblioteca/polyhaven?q=${encodeURIComponent(q)}`);
    $('#phList').innerHTML = r.items.map(x => `<article>${/^https:\/\/cdn\.polyhaven\.com\//.test(x.miniatura || '') ? `<img src="${esc(x.miniatura)}" alt="" loading="lazy">` : ''}<b>${esc(x.nombre)}</b><small>${esc((x.categorias || []).join(', '))} · CC0</small>
      <button type="button" data-ph="${esc(x.id)}" data-name="${esc(x.nombre)}">Importar</button></article>`).join('') || '<p class="cx-note">Sin resultados.</p>'; }
  catch (err) { $('#phList').innerHTML = `<p class="cx-note">${esc(err.message)}</p>`; }
}
$('#phGo').addEventListener('click', search); $('#phQ').addEventListener('keydown', e => { if (e.key === 'Enter') search(); });
document.addEventListener('click', async e => {
  const b = e.target.closest('button'); if (!b) return;
  if (b.dataset.ph) {
    const cat = prompt('Categoría (' + CATS.map(c => c.key).join(', ') + ')', 'decoracion'); if (!cat) return;
    const zone = prompt('Zona sugerida (salon, barra, cocina, caja, bodega, oficina, terraza, banos, produccion…)', 'salon'); if (!zone) return;
    const h = prompt('Alto real en metros', '0.9'); if (!h) return;
    b.disabled = true; b.textContent = 'Importando…';
    try { await req(`${API}/biblioteca/polyhaven/${encodeURIComponent(b.dataset.ph)}`, {method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({nombre: b.dataset.name, categoria: cat, zonas: [zone], conectable: 'ninguno', alto: h})}); b.textContent = 'En revisión ✓'; load(); }
    catch (err) { b.disabled = false; b.textContent = 'Importar'; alert(err.message); }
  }
  if (b.dataset.ok || b.dataset.no) { const id = b.dataset.ok || b.dataset.no;
    try { await req(`${API}/biblioteca/revision/${encodeURIComponent(id)}/${b.dataset.ok ? 'aprobar' : 'rechazar'}`, {method: 'POST', headers: {'X-Cx-Audit-Note': 'Biblioteca 3D'}}); load(); } catch (err) { alert(err.message); } }
  if (b.dataset.view) preview(b.dataset.view);
});

// vista previa 3D (girando; arrastra para rotar)
let R3 = null;
async function preview(id) {
  const dlg = $('#libDlg'); dlg.showModal(); $('#libInfo').textContent = 'Cargando…';
  const c = $('#libCanvas'); if (!R3) { R3 = new THREE.WebGLRenderer({canvas: c, antialias: true}); R3.setPixelRatio(Math.min(2, devicePixelRatio)); }
  const S = new THREE.Scene(); S.background = new THREE.Color(0x1b1626); S.add(new THREE.HemisphereLight(0xffffff, 0x333344, 1.4)); const d = new THREE.DirectionalLight(0xffffff, 1.6); d.position.set(3, 5, 4); S.add(d);
  S.add(new THREE.GridHelper(4, 16, 0x6b5b95, 0x2a2538));
  const L = new GLTFLoader(); L.setMeshoptDecoder(MeshoptDecoder);
  try { const g = await L.loadAsync(`/admin-v2/api/oficina/catalogo/${encodeURIComponent(id)}.glb?t=${Date.now()}`); S.add(g.scene);
    const box = new THREE.Box3().setFromObject(g.scene), size = box.getSize(new THREE.Vector3()); const r = Math.max(size.x, size.y, size.z) || 1;
    const C = new THREE.PerspectiveCamera(35, c.width / c.height, .01, 100); let az = .6, drag = null;
    c.onpointerdown = e => { drag = e.clientX; c.setPointerCapture(e.pointerId); }; c.onpointermove = e => { if (drag != null) { az += (e.clientX - drag) * .01; drag = e.clientX; } }; c.onpointerup = () => { drag = null; };
    $('#libInfo').textContent = `Medidas reales: ${size.x.toFixed(2)} × ${size.z.toFixed(2)} × ${size.y.toFixed(2)} m (apoyado en el piso)`;
    const loop = () => { if (!dlg.open) return; if (drag == null) az += .006; C.position.set(Math.sin(az) * r * 2.2, r * 1.1, Math.cos(az) * r * 2.2); C.lookAt(0, size.y / 2, 0); R3.render(S, C); requestAnimationFrame(loop); }; loop(); }
  catch (err) { $('#libInfo').textContent = 'No se pudo abrir: ' + err.message; }
}
if (!window.__CX_BIBLIOTECA_TEST__) load().catch(err => { $('#catTitle').textContent = 'No se pudo cargar: ' + err.message; });
