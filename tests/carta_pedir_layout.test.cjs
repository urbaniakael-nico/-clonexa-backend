// QR y piezas (058A) en Chrome sin ventana a 390 px, con datos de ejemplo
// (tests/fixtures/carta_pedir_preview.js):
// - Domicilio: carta -> pedido -> datos (nombre, celular, dirección, barrio,
//   referencia, pago contra entrega, nota, autorización de datos con enlace a
//   la política) -> confirmación con resumen y estado. Sin autorización no
//   se envía. El campo anti-robots existe y no se ve.
// - Para llevar: nombre, celular y hora aproximada de recogida.
// - Mesero: sin sesión no abre; con sesión elige SU mesa abierta y agrega por
//   el envío de siempre del mesero (POST /waiter-ordering/orders).
// - Detalle con la galería del plato (las otras fotos, nunca en el video).
// Si no hay Chrome, se salta. CX_CARTA_SHOTS=<carpeta> guarda capturas.
const test = require('node:test');
const assert = require('node:assert/strict');
const http = require('node:http');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { execFile } = require('node:child_process');

const WEB = path.join(__dirname, '..', 'app', 'web');
const MEDIA = path.join(__dirname, 'fixtures', 'menu_video');
const CHROME = [process.env.CHROME_PATH, 'C:/Program Files/Google/Chrome/Application/chrome.exe', '/usr/bin/google-chrome', '/usr/bin/chromium',
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'].find((p) => p && fs.existsSync(p));
const CID = '58a00000-0000-4000-8000-0000000b4a5a';
const TYPES = { '.js': 'application/javascript', '.html': 'text/html', '.webp': 'image/webp', '.mp4': 'video/mp4' };

function media(name) {
  const extra = process.env.CX_CARTA_MEDIA && path.join(process.env.CX_CARTA_MEDIA, name);
  if (extra && fs.existsSync(extra)) return extra;
  const real = path.join(MEDIA, name);
  if (fs.existsSync(real)) return real;
  if (name.endsWith('.mp4')) return path.join(MEDIA, 'd1.mp4');
  if (name.endsWith('-poster.webp')) return path.join(MEDIA, 'd1-poster.webp');
  return path.join(MEDIA, 'd3.webp');
}

function serve() {
  const server = http.createServer((req, res) => {
    const url = new URL(req.url, 'http://x');
    const send = (body, type, status = 200) => { res.writeHead(status, { 'content-type': type }); res.end(body); };
    const inject = (file) => fs.readFileSync(path.join(WEB, file), 'utf8').replace('<script', '<script src="/__fx.js"></script>\n  <script');
    if (url.pathname === '/pedir' || url.pathname === '/carta-mesero') return send(inject('carta_pedir.html'), 'text/html');
    if (url.pathname === '/__fx.js') return send(fs.readFileSync(path.join(__dirname, 'fixtures', 'carta_pedir_preview.js')), TYPES['.js']);
    if (url.pathname.startsWith('/__mv/')) return send(fs.readFileSync(media(path.basename(url.pathname))), TYPES[path.extname(url.pathname)] || 'image/webp');
    if (url.pathname === '/__frames.html') {
      const cases = JSON.parse(url.searchParams.get('c'));
      const frames = cases.map(([k, src]) => `<iframe data-k="${k}" style="width:390px;height:844px;border:0;display:block" src="${src}"></iframe>`);
      return send(`<!doctype html><html><body style="margin:0">${frames.join('')}<pre id="all"></pre><script>
        setTimeout(() => { const out = {}; document.querySelectorAll('iframe').forEach((f) => { const d = f.contentDocument && f.contentDocument.getElementById('layout'); out[f.dataset.k] = d && d.textContent ? JSON.parse(d.textContent) : null; });
          document.getElementById('all').textContent = JSON.stringify(out); }, 9000);</script></body></html>`, 'text/html');
    }
    const file = url.pathname.startsWith('/client-static/') ? path.join(WEB, url.pathname.slice(15)) : null;
    if (file && file.startsWith(WEB) && fs.existsSync(file)) return send(fs.readFileSync(file), TYPES[path.extname(file)] || 'application/octet-stream');
    res.writeHead(404); res.end();
  });
  return new Promise((resolve) => server.listen(0, '127.0.0.1', () => resolve(server)));
}

function chrome(args) {
  return new Promise((resolve, reject) => execFile(CHROME, ['--headless=new', '--disable-gpu', '--no-first-run', ...args],
    { timeout: 200000, maxBuffer: 64 * 1024 * 1024 }, (err, stdout) => (err ? reject(err) : resolve(stdout))));
}

const pedir = (q) => `/pedir?k=enlace-de-prueba-123456&company_id=${CID}${q}`;
const mesero = (q) => `/carta-mesero?company_id=${CID}&k=enlace-mesero-123456${q}`;
const CASES = [
  ['dom-form', pedir('&kind=domicilio&brand=brasa&view=form')], ['dom-done', pedir('&kind=domicilio&brand=brasa&view=done')],
  ['dom-sin-permiso', pedir('&kind=domicilio&brand=azul&view=noconsent')], ['llevar-done', pedir('&kind=llevar&brand=azul&view=done')],
  ['detalle-galeria', pedir('&kind=domicilio&brand=brasa&view=detail')],
  ['mesero', mesero('&mesero=1&brand=brasa')], ['mesero-sin-sesion', mesero('&mesero=1&login=0&brand=brasa')],
];

test('QR y piezas: Domicilio, Para llevar y Mesero a 390 px', { skip: !CHROME && 'Chrome no está instalado en esta máquina', timeout: 300000 }, async () => {
  const server = await serve();
  const base = `http://127.0.0.1:${server.address().port}`;
  const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'cx-carta-pedir-'));
  try {
    const html = await chrome([`--user-data-dir=${profile}`, '--window-size=500,6000', '--virtual-time-budget=20000', '--dump-dom',
      `${base}/__frames.html?c=${encodeURIComponent(JSON.stringify(CASES))}`]);
    const m = html.match(/<pre id="all">([^<]*)<\/pre>/);
    assert.ok(m && m[1], 'sin resultado de la medición');
    const r = JSON.parse(m[1].replace(/&quot;/g, '"').replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>'));
    for (const [k] of CASES) {
      assert.ok(r[k] && !r[k].error, `${k}: ${JSON.stringify(r[k])}`);
      assert.equal(r[k].page_overflow, false, `${k}: se sale de ancho ${JSON.stringify(r[k].overflow_by)}`);
    }
    const form = r['dom-form'];
    assert.ok(form.mounted);
    assert.match(form.form, /Datos de la entrega[\s\S]*Nombre[\s\S]*Celular[\s\S]*Dirección[\s\S]*Barrio[\s\S]*Referencia \(opcional\)[\s\S]*Forma de pago \(contra entrega\)[\s\S]*Efectivo[\s\S]*Transferencia[\s\S]*Nota \(opcional\)[\s\S]*Autorizo el tratamiento de mis datos para gestionar mi pedido\. Política de datos/);
    assert.match(form.form, /Tu pedido[\s\S]*2 × Salmón a la plancha[\s\S]*Bien cocido[\s\S]*El restaurante te confirma el valor del domicilio\.[\s\S]*Pagas al recibir\. No pedimos datos de tarjeta\./);
    assert.equal(form.hp_hidden, true, 'el campo anti-robots no se ve');
    assert.equal(form.calls.length, 0, 'nada se envía hasta llenar los datos');
    const done = r['dom-done'];
    assert.equal(done.calls.length, 1);
    const body = done.calls[0].body;
    assert.match(done.calls[0].path, /^\/carta-links\/public\/enlace-de-prueba-123456\/orders$/);
    assert.deepEqual({ name: body.name, phone: body.phone, address: body.address, barrio: body.barrio, reference: body.reference, payment: body.payment, consent: body.consent, website: body.website },
      { name: 'Laura Gómez', phone: '300 123 4567', address: 'Calle 10 # 5-20', barrio: 'Centro', reference: 'Portería', payment: 'efectivo', consent: true, website: '' });
    assert.deepEqual(body.items, [{ inventory_item_id: 'p3', quantity: 2, observations: 'Bien cocido', quick_notes: [], term: '' }]);
    assert.match(done.done, /¡Pedido recibido![\s\S]*QR-0101[\s\S]*Estado: Recibido[\s\S]*Resumen[\s\S]*El restaurante te confirma el valor del domicilio\.[\s\S]*Entrega en: Calle 10 # 5-20, Centro\. Pago contra entrega \(efectivo\)\./);
    const nope = r['dom-sin-permiso'];
    assert.equal(nope.calls.length, 0, 'sin autorización de datos no se envía');
    assert.match(nope.done, /Marca la casilla de autorización de datos para enviar el pedido\./);
    const llevar = r['llevar-done'];
    assert.match(llevar.form, /Datos para recoger[\s\S]*Hora aproximada de recogida/);
    assert.ok(llevar.calls[0].body.pickup, 'hora de recogida');
    assert.match(llevar.done, /¡Pedido recibido![\s\S]*Recoges hacia las [\s\S]*Pagas al recoger\./);
    assert.doesNotMatch(llevar.form, /Dirección|Autorizo/);
    const det = r['detalle-galeria'];
    assert.equal(det.thumbs, 3, 'la principal y las 2 de la galería');
    assert.match(det.detail_img, /salmon-a-la-plancha-remaster\.webp$/);
    assert.match(det.detail_alt, /foto 3 de 3/);
    const mz = r.mesero;
    assert.ok(mz.mounted, JSON.stringify(mz));
    assert.match(mz.form, /¿A qué mesa\?[\s\S]*Mesa 4[\s\S]*Mesa 7/);
    assert.equal(mz.calls.length, 1);
    assert.match(mz.calls[0].path, new RegExp(`^/companies/${CID}/waiter-ordering/orders$`));
    assert.equal(mz.calls[0].body.table, 'Mesa 4');
    assert.equal(mz.calls[0].auth, 'Bearer token-mesero', 'con la sesión del mesero');
    assert.match(mz.after, /Agregado a la cuenta de Mesa 4\./);
    const out = r['mesero-sin-sesion'];
    assert.equal(out.mounted, false, 'sin sesión no abre');
    assert.match(out.stop, /Inicia sesión en tu panel de mesero[\s\S]*Entrar al panel de mesero/);
    const shots = process.env.CX_CARTA_SHOTS;
    if (shots) {
      fs.mkdirSync(shots, { recursive: true });
      for (const [k, src] of CASES) {
        await chrome([`--user-data-dir=${profile}-${k}`, '--window-size=390,844', '--virtual-time-budget=12000', '--hide-scrollbars', `--screenshot=${path.join(shots, `qr-${k}-390.png`)}`, base + src]);
      }
    }
  } finally {
    server.close();
  }
});
