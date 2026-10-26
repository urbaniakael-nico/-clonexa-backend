// Proxy de Telegram (ops/telegram-proxy/worker.js): solo /bot<token>/<metodo> y
// /file/bot<token>/<ruta>, solo con la cabecera X-Proxy-Key correcta; lo demas 403.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const { pathToFileURL } = require('node:url');

test('el proxy reenvia solo rutas de bot con la clave y rechaza lo demas', async () => {
  const worker = (await import(pathToFileURL(path.resolve('ops/telegram-proxy/worker.js')).href)).default;
  const upstream = [];
  const realFetch = globalThis.fetch;
  globalThis.fetch = async (url, options) => { upstream.push({ url, method: options.method }); return new Response('{"ok":true}', { status: 200 }); };
  try {
    const call = (p, key, method = 'GET') => worker.fetch(new Request(`https://proxy.dev${p}`, { method, headers: key ? { 'X-Proxy-Key': key } : {} }), { PROXY_KEY: 'clave-fuerte' }).then((r) => r.status);
    assert.equal(await call('/bot123:AB-c_d/getMe', 'clave-fuerte'), 200);
    assert.equal(await call('/bot123:AB-c_d/sendMessage?x=1', 'clave-fuerte', 'POST'), 200);
    assert.equal(await call('/file/bot123:AB/photos/a.jpg', 'clave-fuerte'), 200);
    assert.equal(await call('/bot123:AB/getMe', 'otra'), 403);
    assert.equal(await call('/bot123:AB/getMe'), 403);
    assert.equal(await call('/', 'clave-fuerte'), 403);
    assert.equal(await call('/admin', 'clave-fuerte'), 403);
    assert.equal(await call('/bot123:AB/getMe', 'clave-fuerte', 'DELETE'), 403);
    assert.deepEqual(upstream.map((u) => `${u.method} ${u.url}`), [
      'GET https://api.telegram.org/bot123:AB-c_d/getMe',
      'POST https://api.telegram.org/bot123:AB-c_d/sendMessage?x=1',
      'GET https://api.telegram.org/file/bot123:AB/photos/a.jpg',
    ]);
    const noKey = await worker.fetch(new Request('https://proxy.dev/bot1:A/getMe', { headers: { 'X-Proxy-Key': '' } }), {});
    assert.equal(noKey.status, 403, 'sin PROXY_KEY configurada no reenvia nada');
  } finally {
    globalThis.fetch = realFetch;
  }
});
