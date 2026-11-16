// BIBLIOTECA 3D (inicio) · prototipo aprobado integrado a Clonexa: empresa real, su Estudio de marca (solo lectura),
// estilo y entradas a Diseño del local, Personajes, Catálogo y Subir modelo. "Aplicar Estudio de marca a todo" usa
// las mismas reglas del prototipo en el servidor (queda como cambio del borrador: se restaura en "Versiones").
import { Style } from './core.js';
import { COMPANIES, company, setCompany, Store, toast, loadBrand, BRAND, api, companyPath, link, state } from './store.js';
import { TEMPLATES } from './templates.js';
import { loadTeam } from './team.js';
const $ = s => document.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
function render() {
  loadBrand(); Style.mode = Store.get('style', 'human'); const c = company();
  $('#ec').innerHTML = COMPANIES.map(x => `<button data-id="${esc(x.id)}" class="${x.id === c.id ? 'sel' : ''}"><span style="display:flex;gap:3px">${x.brand.slice(0, 3).map(b => `<i style="background:${esc(b)}"></i>`).join('')}</span>${esc(x.name)}</button>`).join('');
  $('#ec').querySelectorAll('button').forEach(b => b.onclick = async () => { try { await setCompany(b.dataset.id); render(); toast('Empresa: ' + company().name); } catch (e) { toast(e.message, 'err'); } });
  $('#sty').innerHTML = [['human', '🧍 Humano'], ['toon', '🙂 Caricatura']].map(([k, n]) => `<button data-s="${k}" class="${k === Style.mode ? 'sel' : ''}">${n}</button>`).join('');
  $('#sty').querySelectorAll('button').forEach(b => b.onclick = () => { Store.set('style', b.dataset.s); render(); toast('Estilo: ' + (b.dataset.s === 'toon' ? 'Caricatura' : 'Humano')); });
  $('#br').innerHTML = BRAND.map((col, i) => `<input type="color" data-i="${i}" value="${esc(col)}" title="${['Principal', 'Secundario', 'Oscuro', 'Claro'][i]}" disabled>`).join('') + '<small>Principal · Secundario · Oscuro · Claro</small>';
  $('#brEdit').href = '/admin-v2plus#empresa/' + encodeURIComponent(c.id);
  const ds = Store.get('designs', []); const live = ds.find(d => d.live);
  $('#stat').innerHTML = `<span>🏗️ ${ds.length} diseño${ds.length === 1 ? '' : 's'}</span><span>${live ? '● En vivo: ' + esc(live.name) + ' v' + live.version : '○ Sin plano en vivo'}</span><span>🧍 ${loadTeam().length} personas</span><span>Plantilla sugerida: ${TEMPLATES[c.kind]?.icon || ''} ${TEMPLATES[c.kind]?.name || ''}</span>`;
  const last = ds.slice().sort((a, b) => b.updated - a.updated)[0]; $('#imD').innerHTML = last?.thumb ? `<img src="${esc(last.thumb)}">` : '🏗️';
  document.querySelectorAll('a[data-to]').forEach(a => a.href = link(a.dataset.to));
}
$('#apply').onclick = async () => {
  const b = $('#apply'); b.disabled = true;
  try {
    const r = await api(companyPath() + '/aplicar-marca', { method: 'POST', body: '{}' });
    await setCompany(company().id); render(); toast(`Marca aplicada: ${r.objects} objetos y ${r.uniforms} uniformes`);
  } catch (e) { toast('No se pudo aplicar: ' + e.message, 'err'); } finally { b.disabled = false; }
};
if (!state().designs && !COMPANIES.length) toast('No hay empresas registradas', 'err');
render();
