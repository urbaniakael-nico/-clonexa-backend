// SECURITY (2026-09-24): agente de WhatsApp. Ejecuta las funciones reales
// del puente (bridge.mjs) y del panel de Bots (client.js, 048M).
const { readFileSync } = require('node:fs');
const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');

const bridge = readFileSync('app/services/whatsapp_bridge/bridge.mjs', 'utf8').replace(/\r\n/g, '\n');
const client = readFileSync('app/web/client.js', 'utf8').replace(/\r\n/g, '\n');

function topLevelFn(source, name) {
  const start = source.search(new RegExp(`\\n(?:async )?function ${name}\\(`));
  assert.ok(start >= 0, name);
  const tail = source.slice(start + 1);
  const end = tail.indexOf('\n}\n');
  return tail.slice(0, end + 3);
}

function clientFn(name) {
  const start = client.search(new RegExp(`\\n  (?:async )?function ${name}\\(`));
  assert.ok(start >= 0, name);
  const tail = client.slice(start + 3);
  const next = tail.search(/\n  (?:async )?function |\n  let |\n  const |\n  document\./);
  return (next < 0 ? tail : tail.slice(0, next)) + '\n';
}

const bridgeCtx = vm.createContext({ String });
vm.runInContext(
  ['normalizePhone', 'phoneFromJid', 'splitSessionKey', 'otherLineKey', 'senderPhone']
    .map((name) => topLevelFn(bridge, name)).join('\n'),
  bridgeCtx,
);

test('puente: cada número tiene una sola línea (interno o clientes)', () => {
  const cid = '7625872c-f941-4479-a27b-f8443be953c5';
  assert.deepEqual({ ...bridgeCtx.splitSessionKey(cid) }, { companyId: cid, line: 'interno' });
  assert.deepEqual({ ...bridgeCtx.splitSessionKey(`${cid}--clientes`) }, { companyId: cid, line: 'clientes' });
  assert.equal(bridgeCtx.otherLineKey(cid), `${cid}--clientes`);
  assert.equal(bridgeCtx.otherLineKey(`${cid}--clientes`), cid);
  assert.match(bridge, /other\?\.connectedPhone && other\.connectedPhone === session\.connectedPhone/);
});

test('puente: el remitente @lid nunca se confunde con un teléfono', () => {
  assert.equal(bridgeCtx.senderPhone({ key: { remoteJid: '573001234567@s.whatsapp.net' } }), '573001234567');
  assert.equal(bridgeCtx.senderPhone({ key: { remoteJid: '123456789012345@lid', senderPn: '573001234567@s.whatsapp.net' } }), '573001234567');
  assert.equal(bridgeCtx.senderPhone({ key: { remoteJid: '123456789012345@lid' } }), '');
});

test('puente: lo que el dueño escribe en chats ajenos ya no es una orden', () => {
  assert.doesNotMatch(bridge, /looksLikeAgentPrompt/);
  assert.match(bridge, /if \(fromMe && \(splitSessionKey\(companyId\)\.line !== "interno" \|\| !isSelfChat\)\) continue;/);
  assert.match(bridge, /is_self_chat: !!isSelfChat,\n    from_me: !!message\.key\?\.fromMe,/);
  assert.match(bridge, /const location = isCustomerLine\(sessionKey\) \? extractLocation\(message\) : null;/, 'ubicaciones solo en la línea de clientes');
  assert.match(bridge, /if \(line !== "interno"\) return;/, 'la línea de clientes no manda bienvenida del agente');
});

function panel() {
  const ctx = vm.createContext({
    h: (value) => String(value ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])),
    state: { companyId: 'c1' },
    String, Array,
  });
  vm.runInContext(clientFn('cxBotWaAccessPanel048M'), ctx);
  return ctx;
}

test('portal: "Puede consultar por WhatsApp" apagado por defecto, por persona', () => {
  const html = panel().cxBotWaAccessPanel048M({
    employees: [
      { employee_id: 'e1', name: 'Ana', phone: '573001234567', enabled: true, stale: false },
      { employee_id: 'e2', name: 'Luis', phone: '573009998877', enabled: false, stale: false },
      { employee_id: 'e3', name: 'Sin Tel', phone: '', enabled: false, stale: false },
      { employee_id: 'e4', name: 'Cambió', phone: '573110000000', enabled: false, stale: true },
    ],
  });
  assert.match(html, /Puede consultar por WhatsApp/);
  assert.match(html, /A cualquier otro numero no le responde nada/);
  assert.match(html, /data-bot-wa-access-048m="e1" checked /);
  assert.match(html, /data-bot-wa-access-048m="e2"  >/);
  assert.match(html, /data-bot-wa-access-048m="e3"  disabled>[\s\S]*Sin telefono en Workforce/);
  assert.match(html, /data-bot-wa-access-048m="e4"[\s\S]*El telefono cambio despues del permiso/);
  assert.match(panel().cxBotWaAccessPanel048M({ employees: [] }), /No hay personal activo en Workforce/);
});

test('portal: aviso de número dedicado y el agente se presenta como línea interna', () => {
  assert.match(client, /automatizar WhatsApp Web no esta permitido por WhatsApp y el numero puede ser suspendido\. Usa un numero dedicado/);
  assert.match(client, /<div class="client-eyebrow">Numero interno<\/div>/);
  assert.match(client, /Nunca atiende clientes\./);
  assert.match(client, /\$\{cxBotWaAccessPanel048M\(waAccess \|\| \{\}\)\}/);
  assert.match(client, /whatsapp-web\/access\/\$\{encodeURIComponent\(employeeId\)\}`, \{\n        method: "PUT"/);
});
