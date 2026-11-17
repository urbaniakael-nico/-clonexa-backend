// Consola v2+ · Publicar en TikTok: reglas de las Content Sharing Guidelines en la pantalla.
const { readFileSync } = require('node:fs');
const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');

const SRC = readFileSync('app/web/admin_v2plus_tiktok.js', 'utf8');
const MAIN = readFileSync('app/web/admin_v2plus.js', 'utf8');

function load() {
  const window = { location: { href: '' } };
  const document = { addEventListener: () => {} };
  const ctx = vm.createContext({ window, document, fetch: async () => ({ status: 200, ok: true, json: async () => ({}) }), JSON, Object, Array, String,
    Math, Number, Promise, Error, Date, Boolean, encodeURIComponent, setInterval, clearInterval, FormData: class {} });
  vm.runInContext(SRC, ctx);
  return window.CxConsoleTikTok;
}

const CREATOR = { avatar: 'https://p16.tiktokcdn.com/a.jpg', nickname: 'Clonexa', username: 'clonexxa', max_video_post_duration_sec: 60,
  privacy_level_options: ['PUBLIC_TO_EVERYONE', 'MUTUAL_FOLLOW_FRIENDS', 'SELF_ONLY'], comment_disabled: false, duet_disabled: true, stitch_disabled: false };

function ready(tt, extra = {}) {
  return Object.assign(tt.fresh(), { status: { configurado: true, conectada: true, auditada: false }, creator: { ...CREATOR },
    pieces: [{ id: 'p1', tema: 'Bumerán bar', duracion: 6, origen: 'subida', caption: '' }, { id: 'p2', tema: 'Largo', duracion: 95, origen: 'calendario' }],
    piece: 'p1' }, extra);
}

test('creator_info visible: avatar y nickname de la cuenta que recibe el post', () => {
  const tt = load();
  const html = tt.account(ready(tt));
  assert.match(html, /src="https:\/\/p16\.tiktokcdn\.com\/a\.jpg"/);
  assert.match(html, /<b>Clonexa<\/b>/);
  assert.match(html, /@clonexxa/);
});

test('privacidad: solo privacy_level_options y SIN valor por defecto', () => {
  const tt = load();
  const m = ready(tt);
  const html = tt.form(m);
  assert.match(html, /<option value="" selected disabled>Elige una opción<\/option>/);
  assert.equal((html.match(/<option value="[A-Z_]+"/g) || []).length, 3);
  assert.doesNotMatch(html, /FOLLOWER_OF_CREATOR/);
  assert.equal(tt.blocker(m), 'Elige quién puede ver la publicación.');
  assert.match(html, /data-tt-publish disabled/);
  assert.match(html, /Hasta que TikTok apruebe la auditoría, las publicaciones quedan privadas\./);
});

test('interacciones: sin marcar por defecto y en gris si la cuenta las tiene apagadas', () => {
  const tt = load();
  const m = ready(tt);
  const html = tt.form(m);
  assert.match(html, /<input type="checkbox" data-tt-allow="comment"  >/);
  assert.match(html, /is-disabled"><input type="checkbox" data-tt-allow="duet"  disabled> Duet/);
  assert.match(html, /<input type="checkbox" data-tt-allow="stitch"  >/);
  m.allow.duet = true; m.allow.comment = true;
  const p = tt.payload(Object.assign(m, { privacy: 'SELF_ONLY' }));
  assert.equal(p.allow_duet, false);   // apagado por la cuenta: nunca va en true
  assert.equal(p.allow_comment, true);
  assert.equal(p.allow_stitch, false);
});

test('divulgacion comercial: etiquetas, privado deshabilitado con Branded content y boton bloqueado sin opcion', () => {
  const tt = load();
  const m = ready(tt, { privacy: 'PUBLIC_TO_EVERYONE' });
  assert.equal(tt.blocker(m), '');
  assert.match(tt.form(m), /By posting, you agree to TikTok&#039;s <a href="https:\/\/www\.tiktok\.com\/legal\/page\/global\/music-usage-confirmation\/en" target="_blank" rel="noopener noreferrer">Music Usage Confirmation<\/a>/);
  m.disclosure = true;
  assert.equal(tt.blocker(m), 'You need to indicate if your content promotes yourself, a third party, or both.');
  m.yourBrand = true;
  assert.equal(tt.disclosureLabel(m), "Your photo/video will be labeled as 'Promotional content'");
  assert.equal(tt.declaration(m).text, "By posting, you agree to TikTok's Music Usage Confirmation");
  m.branded = true;
  assert.equal(tt.disclosureLabel(m), "Your photo/video will be labeled as 'Paid partnership'");
  assert.equal(tt.declaration(m).text, "By posting, you agree to TikTok's Branded Content Policy and Music Usage Confirmation");
  assert.deepEqual(JSON.parse(JSON.stringify(tt.declaration(m).links.map((l) => l[1]))), ['https://www.tiktok.com/legal/page/global/bc-policy/en', 'https://www.tiktok.com/legal/page/global/music-usage-confirmation/en']);
  const priv = tt.privacyOptions(m).find((o) => o.value === 'SELF_ONLY');
  assert.equal(priv.disabled, true);
  assert.equal(priv.note, 'Branded content visibility cannot be set to private.');
  assert.match(tt.form(m), /value="SELF_ONLY"  disabled>Solo yo \(privado\) — Branded content visibility cannot be set to private\./);
  m.privacy = 'SELF_ONLY';
  assert.equal(tt.blocker(m), 'Branded content visibility cannot be set to private.');
  const p = tt.payload(Object.assign(m, { privacy: 'PUBLIC_TO_EVERYONE' }));
  assert.equal(p.branded_content, true); assert.equal(p.your_brand, true);
});

test('interruptor de divulgacion apagado por defecto', () => {
  const tt = load();
  const html = tt.form(ready(tt));
  assert.match(html, /<input type="checkbox" role="switch" data-tt-disclosure >/);
  assert.doesNotMatch(html, /data-tt-brand/);
});

test('duracion mayor a la permitida y error de creator_info bloquean', () => {
  const tt = load();
  const m = ready(tt, { piece: 'p2', privacy: 'SELF_ONLY' });
  assert.match(tt.blocker(m), /dura 95 s y esta cuenta permite máximo 60 s/);
  const bad = ready(tt, { creator: null, creatorError: 'TikTok no deja publicar ahora en esta cuenta. Intenta más tarde.', privacy: 'SELF_ONLY' });
  assert.equal(tt.blocker(bad), 'TikTok no deja publicar ahora en esta cuenta. Intenta más tarde.');
});

test('despues de publicar: aviso de procesamiento, estado y enlace al post', () => {
  const tt = load();
  const m = ready(tt, { current: { id: 'x', estado: 'PROCESANDO', modo: 'directo' } });
  assert.match(tt.current(m), /Puede tardar unos minutos en procesarse y aparecer en tu perfil\./);
  assert.match(tt.current(m), /⏳ Procesando/);
  m.current = { id: 'x', estado: 'PUBLICADO', modo: 'directo', post_id: '7400000000000000001' };
  assert.match(tt.current(m), /href="https:\/\/www\.tiktok\.com\/@clonexxa\/video\/7400000000000000001"/);
  m.current = { id: 'x', estado: 'FALLO', modo: 'directo', motivo: 'file_format_check_failed' };
  assert.match(tt.current(m), /❌ Falló<\/b> · file_format_check_failed/);
});

test('sin cuenta conectada: boton Conectar TikTok; sin variables: dice cuales crear', () => {
  const tt = load();
  assert.match(tt.account(Object.assign(tt.fresh(), { status: { configurado: true, conectada: false } })), /data-tt-connect/);
  const html = tt.account(Object.assign(tt.fresh(), { status: { configurado: false } }));
  assert.match(html, /TIKTOK_CLIENT_KEY/); assert.match(html, /TIKTOK_CLIENT_SECRET/);
});

test('rutas de la consola: #tiktok=<pieza> desde Telegram y la vuelta de TikTok', () => {
  const window = { location: { hash: '' } };
  const ctx = vm.createContext({ window, document: { getElementById: () => null }, JSON, Object, Array, String, Math, Number, Promise, Error, Date });
  vm.runInContext(MAIN, ctx);
  const f = window.CxConsolePlus.tiktokFromHash;
  assert.deepEqual({ ...f('#tiktok=0b6d5f7e-1111-4222-8333-944445555666') }, { piece: '0b6d5f7e-1111-4222-8333-944445555666', conectada: false, error: '' });
  assert.deepEqual({ ...f('#tiktok?conectada=1') }, { piece: '', conectada: true, error: '' });
  assert.deepEqual({ ...f('#tiktok?error=estado') }, { piece: '', conectada: false, error: 'estado' });
  assert.equal(f('#cola'), null);
  assert.equal(window.CxConsolePlus.VIEWS.tiktok, 'Publicar en TikTok');
});
