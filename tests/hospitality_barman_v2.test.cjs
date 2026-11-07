// Panel Barman v2 (barman_music_layout, solo The Time Machine) en el portal real
// con Chrome sin ventana: 10 mesas activas, 9 cuentas de barra y 2 mesas libres.
// Música fija al bajar, tarjetas compactas sin huecos (5 por fila a 1600, 4 a
// 1280, 3 en tablet), "+" rápido, panel flotante con pago obligatorio y cierre,
// filtros, buscador, llegada en vivo, botón de música en tablet vertical y otra
// empresa sin cambios. No guarda capturas: todo son medidas. Sin Chrome, se salta.
const test = require('node:test');
const assert = require('node:assert/strict');
const http = require('node:http');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { execFile } = require('node:child_process');

const ROOT = path.resolve(__dirname, '..');
const WEB = path.join(ROOT, 'app', 'web');
const CHROME = [process.env.CHROME_PATH, 'C:/Program Files/Google/Chrome/Application/chrome.exe', 'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
  '/usr/bin/google-chrome', '/usr/bin/chromium', '/usr/bin/chromium-browser', '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'].find((p) => p && fs.existsSync(p));
const CID = '21a3065e-0000-4000-8000-00000000c0de';
// El caso sin alerta visual usa otra empresa: la preferencia vive en localStorage
// por empresa y los iframes comparten origen.
const CID_SIN_ALERTA = '21a3065e-0000-4000-8000-00000000a1e0';
const TYPES = { '.js': 'application/javascript', '.css': 'text/css', '.html': 'text/html' };
// [clave, ancho, alto, parámetros]
const CASES = [
  ['layout-1600', 1600, 900, '&on=1&sc=layout&songs=40'],
  ['layout-1280', 1280, 900, '&on=1&sc=layout&songs=40'],
  ['add-1280', 1280, 1000, '&on=1&sc=add'],
  ['panel-1280', 1280, 1000, '&on=1&sc=panel'],
  ['panel-1600', 1600, 1000, '&on=1&sc=panel'],
  ['live-1280', 1280, 1000, '&on=1&sc=live'],
  ['filters-1280', 1280, 1000, '&on=1&sc=filters'],
  ['tablet-1024', 1024, 768, '&on=1&sc=tablet'],
  ['tablet-768', 768, 1024, '&on=1&sc=tablet'],
  ['song-1280', 1280, 900, '&on=1&sc=song'],
  ['song-sin-alerta-1280', 1280, 900, '&on=1&sc=song&visual=off'],
  ['off-1280', 1280, 1000, '&sc=off'],
];

function serve() {
  const server = http.createServer((req, res) => {
    const url = new URL(req.url, 'http://x');
    const send = (body, type) => { res.writeHead(200, { 'content-type': type }); res.end(body); };
    if (url.pathname === '/client.html') {
      return send(fs.readFileSync(path.join(WEB, 'client.html'), 'utf8').replace('<link rel="stylesheet"', '<script src="/__preview.js"></script>\n  <link rel="stylesheet"'), 'text/html');
    }
    if (url.pathname === '/__preview.js') return send(fs.readFileSync(path.join(__dirname, 'fixtures', 'barman_v2_preview.js')), TYPES['.js']);
    if (url.pathname === '/__frames.html') {
      const frames = CASES.map(([k, w, hgt, q]) => `<iframe data-k="${k}" style="width:${w}px;height:${hgt}px;border:0;display:block" src="/client.html?company_id=${q.includes('visual=off') ? CID_SIN_ALERTA : CID}${q}"></iframe>`);
      return send(`<!doctype html><html><body style="margin:0">${frames.join('')}<pre id="all"></pre><script>
        const read = () => { const out = {}; document.querySelectorAll('iframe').forEach((f) => { const d = f.contentDocument && f.contentDocument.getElementById('layout'); out[f.dataset.k] = d ? JSON.parse(d.textContent) : null; }); return out; };
        setTimeout(() => { document.getElementById('all').textContent = JSON.stringify(read()); }, 60000);</script></body></html>`, 'text/html');
    }
    const file = url.pathname.startsWith('/client-static/') ? path.join(WEB, url.pathname.slice('/client-static/'.length)) : null;
    if (file && file.startsWith(WEB) && fs.existsSync(file) && fs.statSync(file).isFile()) return send(fs.readFileSync(file), TYPES[path.extname(file)] || 'application/octet-stream');
    res.writeHead(404); res.end();
  });
  return new Promise((resolve) => server.listen(0, '127.0.0.1', () => resolve(server)));
}

function chrome(args) {
  return new Promise((resolve, reject) => {
    execFile(CHROME, ['--headless=new', '--disable-gpu', '--no-first-run', ...args], { timeout: 240000, maxBuffer: 64 * 1024 * 1024 }, (err, stdout) => (err ? reject(err) : resolve(stdout)));
  });
}

const money = (n) => new RegExp(`^\\$\\s?${n.toLocaleString('es-CO').replace(/\./g, '\\.')}$`);

test('Panel Barman v2: música fija, tarjetas compactas, "+" rápido y panel flotante; otra empresa igual',
  { skip: !CHROME && 'Chrome no está instalado en esta máquina', timeout: 400000 }, async () => {
    const server = await serve();
    const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'cx-barman-v2-'));
    const base = `http://127.0.0.1:${server.address().port}`;
    try {
      const html = await chrome([`--user-data-dir=${profile}`, '--window-size=1700,1400', '--virtual-time-budget=90000', '--dump-dom', `${base}/__frames.html`]);
      const m = html.match(/<pre id="all">([^<]*)<\/pre>/);
      assert.ok(m && m[1], 'sin resultado de la medición');
      const r = JSON.parse(m[1].replace(/&quot;/g, '"').replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&nbsp;/g, ' '));
      if (process.env.CX_BARMAN_DUMP) fs.writeFileSync(process.env.CX_BARMAN_DUMP, JSON.stringify(r, null, 1));
      for (const [k] of CASES) assert.ok(r[k] && r[k].mounted, `${k}: no se montó ${r[k] && r[k].error}`);

      // Sección En curso y cuadrícula sin huecos.
      for (const [k, perRow] of [['layout-1600', 5], ['layout-1280', 4]]) {
        const x = r[k];
        assert.match(x.title, /^Mesas y barra abiertas \(19\) · Total abierto \$\s?[\d.]+$/, k);
        assert.deepEqual(x.filters, ['Todas 19', 'Mesas 10', 'Barra 9', 'Pedido nuevo 2'], k);
        assert.equal(x.tables.length, 10, k);
        assert.equal(x.bars.length, 9, k);
        assert.deepEqual(x.free, ['Mesa 11', 'Mesa 12'], k);
        assert.deepEqual(x.tables.slice(0, 2), ['Mesa 8', 'Mesa 3'], `${k}: pedidos nuevos primero (el más antiguo primero)`);
        assert.equal(x.first_badge, 'PEDIDO NUEVO', k);
        assert.ok(x.table_rows.every((n, i) => n === perRow || i === x.table_rows.length - 1), `${k}: ${perRow} por fila (${x.table_rows})`);
        assert.equal(x.table_rows[0], perRow, `${k}: ${perRow} mesas por fila`);
        assert.equal(x.bar_rows[0], perRow, `${k}: ${perRow} cuentas por fila`);
        assert.equal(x.heights.length, 1, `${k}: todas del mismo alto (${x.heights})`);
        assert.match(x.mesa5, /^6 productos · ⏱ \d+:\d{2}(:\d{2})?$/, k);
        assert.equal(x.page_overflow, false, `${k}: la página no se sale de ancho`);
        assert.deepEqual(x.clipped, [], `${k}: nada recortado en las tarjetas`);
        assert.equal(x.total_overflow, 0, `${k}: el total cabe en la tarjeta`);
        assert.deepEqual(x.small_buttons, [], `${k}: botones de al menos 40 px`);
        // Música a la derecha y pegada a la pantalla al bajar hasta el final.
        assert.equal(x.music_btn_visible, false, k);
        assert.equal(x.queue_visible, true, k);
        assert.ok(x.queue_before.left > x.live.right, `${k}: música a la derecha`);
        assert.ok(x.scrolled > 300, `${k}: la página sí baja (${x.scrolled})`);
        assert.ok(x.queue_after.top >= 0 && x.queue_after.bottom <= x.vh, `${k}: la música sigue a la vista al bajar (${JSON.stringify(x.queue_after)})`);
        assert.ok(x.queue_after.h >= 300, `${k}: con alto útil`);
        assert.ok(x.fold_after.bottom <= x.vh + 2, `${k}: se llega hasta los cierres`);
        assert.equal(x.list_scrolls, true, `${k}: muchas canciones se desplazan dentro del panel`);
        assert.deepEqual(x.copy_buttons, ['Copiar'], k);
        assert.equal(x.song_count, '40', k);
        assert.match(x.fold_title, /^Mesas cerradas hoy \(6\) · Total \$\s?210\.000$/, `${k}: cierres como ya quedaron`);
      }

      // "+" rápido.
      const a = r['add-1280'];
      assert.equal(a.pop_open, true);
      assert.equal(a.pop_near, true, 'pegado a la tarjeta');
      assert.equal(a.qty_default, '1');
      assert.deepEqual(a.calls_add, ['POST /orders/a5/items'], 'Enter agrega al pedido de la Mesa 5');
      assert.equal(a.add_body.items[0].name, 'Águila');
      assert.equal(a.add_body.items[0].quantity, 2);
      assert.equal(a.pop_closed, true);
      assert.equal(a.toast, 'Agregado: 2 × Águila a Mesa 5');
      assert.match(a.before, money(75500));
      assert.match(a.after, money(87500), 'la tarjeta actualiza su total');
      assert.equal(a.esc_closed, true);
      assert.deepEqual(a.esc_calls, [], 'Esc no envía nada');
      assert.equal(a.bad_open, true);
      assert.match(a.bad_msg, /Elige un producto/);
      assert.deepEqual(a.bad_calls, []);
      assert.match(a.bar_calls[0], /^POST \/bar-accounts\/b\d\/items$/);
      assert.equal(a.bar_calls.length, 1);
      assert.match(a.bar_before, money(11000));
      assert.match(a.bar_after, money(17000));
      assert.equal(a.bar_toast, 'Agregado: 1 × Águila a Laura');
      assert.deepEqual(a.pending_calls.slice(0, 1), ['POST /orders'], 'mesa sin entregados: pedido de mesa como hoy');
      assert.equal(a.pending_body.source, 'table_manual');
      assert.equal(a.pending_body.table, 'Mesa 3');

      // Panel flotante.
      for (const k of ['panel-1280', 'panel-1600']) {
        const p = r[k];
        assert.equal(p.panel_open, true, k);
        assert.equal(p.panel_title, 'Mesa 5', k);
        assert.equal(p.panel_kind, 'Mesa abierta', k);
        assert.ok(p.panel.right <= p.queue.left, `${k}: no tapa la música`);
        assert.ok(p.panel.left >= 0, k);
        assert.ok(p.panel_lines.length >= 2, `${k}: productos con cantidad y precio`);
        assert.equal(p.panel_has_add, true, k);
        assert.equal(p.close_disabled, true, `${k}: sin pago no se puede cerrar`);
        assert.equal(p.panels, 1, `${k}: un solo panel`);
        assert.equal(p.replaced_title, 'Mesa 6', k);
        assert.deepEqual(p.panel_add_calls, ['POST /orders/a5/items'], `${k}: agregar desde el panel`);
        assert.equal(p.panel_after_add, 'Mesa 5', `${k}: sigue abierto tras agregar`);
        assert.equal(p.close_enabled, true, k);
        assert.equal(p.cash_visible, true, `${k}: efectivo pide dinero recibido`);
        assert.deepEqual(p.close_calls, ['POST /orders/a5/close-table'], k);
        assert.deepEqual(p.close_body, { payment_method: 'cash' }, k);
        assert.equal(p.panel_gone, true, `${k}: al cerrar la mesa el panel se va`);
        assert.equal(p.close_toast, 'Mesa cerrada.', k);
        assert.ok(!p.tables_after.includes('Mesa 5'), k);
        assert.equal(p.bar_title, 'Andrés', k);
        assert.equal(p.bar_kind, 'Cuenta de barra', k);
        assert.deepEqual(p.bar_no_pay_calls, [], `${k}: la cuenta sin pago no se cierra`);
        assert.match(p.bar_no_pay_msg, /Selecciona efectivo, transferencia o tarjeta/, k);
        assert.equal(p.bar_close_calls.length, 1, k);
        assert.match(p.bar_close_calls[0], /^POST \/orders\/b\d\/close-table$/, k);
        assert.deepEqual(p.bar_close_body, { payment_method: 'transfer' }, k);
        assert.equal(p.bar_panel_gone, true, k);
        assert.ok(!p.bars_after.includes('Andrés'), k);
        assert.equal(p.x_closed, true, `${k}: ✕ cierra`);
        assert.equal(p.esc_closed, true, `${k}: Esc cierra`);
        assert.equal(p.free_title, 'Mesa 11', k);
        assert.equal(p.free_kind, 'Mesa libre', k);
        assert.equal(p.free_calls[0], 'POST /orders', `${k}: la mesa libre recibe su primer producto`);
        assert.equal(p.free_body.table, 'Mesa 11', k);
        assert.equal(p.free_panel_kind, 'Mesa abierta', `${k}: el panel sigue abierto con la mesa ya activa`);
        assert.equal(p.free_now_active, true, k);
      }

      // En vivo: el panel no se cierra ni pierde lo escrito.
      const l = r['live-1280'];
      assert.equal(l.open_while_typing, true);
      assert.equal(l.value_kept, 'pok');
      assert.equal(l.open_after, true);
      assert.equal(l.title_after, 'Mesa 7');
      assert.equal(l.mesa2_badge, 'PEDIDO NUEVO', 'el pedido que llegó se ve en su tarjeta');
      assert.ok(l.first_tables.includes('Mesa 2'), 'y sube con los pedidos nuevos');

      // Filtros y buscador (sin mayúsculas ni tildes).
      const f = r['filters-1280'];
      assert.deepEqual(f.bar_groups, ['bar']);
      assert.equal(f.bar_cards, 9);
      assert.deepEqual(f.tables_groups, ['tables', 'free']);
      assert.deepEqual(f.new_groups, ['tables']);
      assert.deepEqual(f.new_cards, ['Mesa 8', 'Mesa 3']);
      assert.equal(f.new_pressed, 'true');
      assert.deepEqual(f.jose, ['José Barra']);
      assert.deepEqual(f.monica, ['Mónica']);
      assert.deepEqual(f.mesa1.slice().sort(), ['Mesa 1', 'Mesa 10']);
      assert.deepEqual(f.mesa1_free, ['Mesa 11', 'Mesa 12']);
      assert.match(f.none_text, /Nada coincide con «nadie»/);
      assert.equal(f.form_hidden, true);
      assert.equal(f.form_open, true, '+ Cuenta de barra abre el formulario de siempre');
      assert.deepEqual(f.create_calls, ['POST /bar-accounts']);

      // Tablet: 3 por fila; en vertical la música es un botón con contador.
      for (const k of ['tablet-1024', 'tablet-768']) {
        const t = r[k];
        assert.equal(t.btn_visible, true, k);
        assert.equal(t.btn_text, 'Música (6)'.replace('Música', '🎵 Música'), k);
        assert.ok(t.btn.h >= 44, k);
        assert.equal(t.queue_hidden, true, k);
        assert.equal(t.table_rows[0], 3, `${k}: 3 por fila (${t.table_rows})`);
        assert.equal(t.page_overflow, false, k);
        assert.equal(t.queue_shown, true, k);
        assert.ok(t.queue.h > 200, k);
        assert.ok(t.copy > 0, k);
        assert.equal(t.queue_closed, true, `${k}: Esc cierra la música`);
        assert.equal(t.small_buttons, 0, k);
      }

      // Canción nueva: borde rojo y contador, respetando Alerta visual.
      const s = r['song-1280'];
      assert.equal(s.before, false);
      assert.equal(s.count_before, '6');
      assert.equal(s.after, true);
      assert.equal(s.count_after, '7');
      assert.equal(s.item_marked, true);
      assert.equal(s.cleared, true, 'al tocar la música se da por vista');
      const so = r['song-sin-alerta-1280'];
      assert.equal(so.after, false, 'con Alerta visual OFF no se marca');
      assert.equal(so.count_after, '7', 'el contador sí se actualiza');

      // Otra empresa con el panel barman: el de siempre.
      const o = r['off-1280'];
      assert.equal(o.v2, false);
      assert.equal(o.music_btn, false);
      assert.equal(o.bar_cards_classic, 9);
      assert.ok(o.table_cards_classic >= 10);
    } finally {
      server.close();
      try { fs.rmSync(profile, { recursive: true, force: true }); } catch (_) {}
    }
  });
