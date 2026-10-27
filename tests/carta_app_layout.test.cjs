// Carta QR nueva (057C) en Chrome sin ventana a 390 px: /carta-qr y /ordenar
// reales con datos de ejemplo (tests/fixtures/carta_app_preview.js).
// - Dos marcas (oscura cálida y clara azul): cada una con sus colores y AA.
// - Inicio: "Lo más pedido", categorías SIEMPRE con imagen (o la portada de su
//   primer plato), nunca el ícono genérico; sin desbordes.
// - Video: un plato por pantalla, video muted/playsinline/loop/autoplay/
//   preload=metadata con portada; solo el visible y el siguiente cargan; video
//   roto -> su portada; con carta_video apagado, fotos.
// - Lista: foto >= 88 px, título arriba y alineado a la izquierda.
// - Pedido: término obligatorio + nota rápida + nota por plato -> el MISMO
//   POST /hospitality/companies/{id}/orders con term/note/quick_notes.
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
const CID = '57c00000-0000-4000-8000-0000000b4a5a';
const TYPES = { '.js': 'application/javascript', '.html': 'text/html', '.webp': 'image/webp', '.mp4': 'video/mp4', '.css': 'text/css' };

function media(name) {
  if (name.startsWith('no-existe')) return null;
  const extra = process.env.CX_CARTA_MEDIA && path.join(process.env.CX_CARTA_MEDIA, name); // capturas con medios reales
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
    if (url.pathname === '/carta-qr') return send(inject('carta_qr.html'), 'text/html');
    if (url.pathname === '/ordenar') return send(inject('hospitality_order.html'), 'text/html');
    if (url.pathname === '/domicilio') return send(inject('domicilio.html'), 'text/html');
    if (url.pathname === '/__fx.js') return send(fs.readFileSync(path.join(__dirname, 'fixtures', 'carta_app_preview.js')), TYPES['.js']);
    if (url.pathname.startsWith('/__mv/')) {
      const file = media(path.basename(url.pathname));
      if (!file) return send('', 'text/plain', 404);
      return send(fs.readFileSync(file), TYPES[path.extname(file)]);
    }
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
  return new Promise((resolve, reject) => execFile(CHROME, ['--headless=new', '--disable-gpu', '--no-first-run', '--autoplay-policy=no-user-gesture-required', ...args],
    { timeout: 200000, maxBuffer: 64 * 1024 * 1024 }, (err, stdout) => (err ? reject(err) : resolve(stdout))));
}

const qr = (q) => `/carta-qr?t=token-de-prueba-123456789&company_id=${CID}${q}`;
const mesa = (q) => `/ordenar?company_id=${CID}&mesa=Mesa%204${q}`;
const CASES = [
  ['home-brasa', qr('&brand=brasa')], ['home-azul', qr('&brand=azul')], ['video-brasa', qr('&brand=brasa&view=video')],
  ['video-roto', qr('&brand=brasa&view=video&broken=1')], ['video-apagado', qr('&brand=azul&view=video&video=0')], ['lista-azul', qr('&brand=azul&view=list')],
  ['lista-foto-rota', qr('&brand=brasa&view=list&brokenphoto=1')],
  ['detalle', mesa('&brand=brasa&view=detail')], ['video-mesa', mesa('&brand=azul&view=video')], ['pedido-mesa', mesa('&brand=brasa&view=cart&send=1')],
  ['domicilio', `/domicilio?c=${CID}&s=codigo-de-prueba-123&company_id=${CID}&brand=azul&view=cart&send=1`],
];

test('carta QR nueva: marca y AA, categorías con imagen, video, lista y pedido por el mismo envío',
  { skip: !CHROME && 'Chrome no está instalado en esta máquina', timeout: 300000 }, async () => {
    const server = await serve();
    const base = `http://127.0.0.1:${server.address().port}`;
    const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'cx-carta-app-'));
    try {
      const html = await chrome([`--user-data-dir=${profile}`, '--window-size=500,7000', '--virtual-time-budget=20000', '--dump-dom',
        `${base}/__frames.html?c=${encodeURIComponent(JSON.stringify(CASES))}`]);
      const m = html.match(/<pre id="all">([^<]*)<\/pre>/);
      assert.ok(m && m[1], 'sin resultado de la medición');
      const r = JSON.parse(m[1].replace(/&quot;/g, '"').replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>'));
      for (const [k] of CASES) { assert.ok(r[k] && r[k].mounted, `${k}: la carta nueva no se montó (${JSON.stringify(r[k])})`); assert.equal(r[k].page_overflow, false, `${k}: se sale de ancho ${JSON.stringify(r[k].overflow_by)}`); }
      for (const k of ['home-brasa', 'home-azul']) {
        const x = r[k];
        assert.match(x.text, k.endsWith('brasa') ? /Brasa & Maíz/ : /Mar Azul/);
        assert.match(x.text, /Busca un plato|Lo más pedido/);
        assert.equal(x.top, 4, 'Lo más pedido');
        assert.deepEqual(x.cats.map((c) => c.label), ['ENTRADAS', 'FUERTES', 'BEBIDAS', 'POSTRES']);
        assert.ok(x.cats.every((c) => c.img), 'cada categoría con su imagen (o la portada de su primer plato)');
        for (const [name, value] of Object.entries(x.ratios)) if (value !== null) assert.ok(value >= 4.5, `${k}: ${name} contraste ${value}`);
        assert.ok(x.palette.text >= 4.5 && x.palette.button >= 4.5);
      }
      assert.notDeepEqual(r['home-brasa'].ratios, r['home-azul'].ratios, 'cada empresa con sus colores');
      const v = r['video-brasa'];
      assert.equal(v.slides, 9);
      assert.equal(v.video_attrs, true, 'muted playsinline loop autoplay preload=metadata con portada');
      assert.deepEqual(v.video_src.slice(0, 3), [true, true, false], 'solo el visible y el siguiente');
      assert.equal(v.vcard_visible, true);
      assert.ok(v.ratios.vcard >= 4.5, `tarjeta del plato ${v.ratios.vcard}`);
      assert.match(v.text, /Ceviche de pescado[\s\S]*\$ 24\.000/);
      assert.doesNotMatch(v.text, /Agregar|Término/, 'carta impresa: se ve, no se pide');
      assert.match(r['video-mesa'].text, /Lomo a la parrilla[\s\S]*Término \(obligatorio\)[\s\S]*Agregar/, 'en la mesa se pide desde el video');
      assert.ok(r['video-mesa'].ratios.primary >= 4.5, `botón Agregar ${r['video-mesa'].ratios.primary}`);
      assert.equal(r['video-roto'].slide0, 'IMG', 'video roto -> su portada, nunca un hueco');
      assert.ok(!r['video-apagado'].video_src.length && r['video-apagado'].slide0 === 'IMG', 'sin carta_video: fotos');
      const l = r['lista-azul'];
      assert.ok(l.list_img >= 88, `foto de la lista ${l.list_img}px`);
      assert.ok(l.list_title_top <= 16 && ['start', 'left'].includes(l.list_title_align), 'título arriba y a la izquierda');
      // 057D: fotos de la lista: las visibles cargan de inmediato y ninguna queda en blanco
      assert.ok(l.list_imgs.length >= 3);
      assert.ok(l.list_imgs.slice(0, 3).every((i) => i.eager), 'las primeras sin carga diferida');
      assert.ok(l.list_imgs.filter((i) => i.visible).every((i) => i.loaded), `fotos visibles cargadas ${JSON.stringify(l.list_imgs)}`);
      assert.ok(l.list_imgs.every((i) => i.bg.startsWith('linear-gradient')), 'mientras carga: color de la marca');
      const rota = r['lista-foto-rota'].list_imgs.find((i) => i.broken);
      assert.ok(rota && rota.bg.startsWith('linear-gradient'), 'foto que falla: el color de la marca, nunca un hueco');
      assert.match(r.detalle.sheet, /300 gr de lomo[\s\S]*Término \(obligatorio\)[\s\S]*Preferencias \(opcional\)[\s\S]*Sin sal/);
      assert.doesNotMatch(JSON.stringify(r), /calor|Me gusta|estrellas/i, 'nada inventado');
      const order = r['pedido-mesa'].orders;
      assert.equal(order.length, 1, 'un solo pedido por el envío de siempre');
      assert.match(order[0].path, new RegExp(`/hospitality/companies/${CID}/orders$`));
      assert.equal(order[0].body.table, 'Mesa 4');
      assert.equal(order[0].body.source, 'qr');
      const lomo = order[0].body.items.find((i) => i.inventory_item_id === 'p1');
      assert.deepEqual({ term: lomo.term, note: lomo.note, quick_notes: lomo.quick_notes, quantity: lomo.quantity, unit_price: lomo.unit_price },
        { term: '3/4', note: 'Bien caliente', quick_notes: ['Salsa aparte'], quantity: 1, unit_price: 46000 });
      const salmon = order[0].body.items.find((i) => i.inventory_item_id === 'p3');
      assert.ok(salmon && !('term' in salmon) && !('note' in salmon), 'sin opciones, la línea va igual que antes');
      assert.match(r['pedido-mesa'].sheet, /Tu pedido llegó a cocina: QR-21. Queda en la cuenta de la mesa./);
      const dom = r.domicilio;
      assert.equal(dom.app_hidden, true, 'domicilio: "Continuar con la entrega" abre el checkout de siempre');
      assert.match(dom.dom, /Tu pedido[\s\S]*Lomo a la parrilla[\s\S]*Bien caliente[\s\S]*Salmón a la plancha[\s\S]*Entrega/);
      assert.equal(dom.orders.length, 0, 'domicilio no envía nada hasta su checkout');
      const shots = process.env.CX_CARTA_SHOTS;
      if (shots) {
        fs.mkdirSync(shots, { recursive: true });
        for (const [k, src] of CASES) {
          await chrome([`--user-data-dir=${profile}-${k}`, '--window-size=390,844', '--virtual-time-budget=8000', '--hide-scrollbars', `--screenshot=${path.join(shots, `${k}-390.png`)}`, base + src]);
        }
        for (const k of ['home-brasa', 'home-azul']) {
          const src = CASES.find((c) => c[0] === k)[1];
          await chrome([`--user-data-dir=${profile}-${k}-w`, '--window-size=1280,900', '--virtual-time-budget=8000', '--hide-scrollbars', `--screenshot=${path.join(shots, `${k}-1280.png`)}`, base + src]);
        }
      }
    } finally {
      server.close();
    }
  });
