import http from "node:http";
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

import makeWASocket, {
  DisconnectReason,
  fetchLatestBaileysVersion,
  useMultiFileAuthState,
} from "baileys";
import Pino from "pino";
import QRCode from "qrcode";

const PORT = Number(process.env.WHATSAPP_BRIDGE_PORT || 3219);
const AUTH_ROOT = process.env.WHATSAPP_AUTH_DIR || "/tmp/clonexa-whatsapp-auth";
const INBOUND_URL = String(process.env.WHATSAPP_INBOUND_URL || "").trim();
const INBOUND_SECRET = String(process.env.WHATSAPP_INBOUND_SECRET || "").trim();
const logger = Pino({ level: process.env.WHATSAPP_BRIDGE_LOG_LEVEL || "warn" });
const sessions = new Map();
const processedInboundIds = new Set();
const sentOutboundIds = new Set();

function cleanCompanyId(value = "") {
  return String(value || "").replace(/[^a-zA-Z0-9_-]/g, "").slice(0, 90);
}

function normalizePhone(value = "") {
  let phone = String(value || "").replace(/\D/g, "");
  if (phone.startsWith("00")) phone = phone.slice(2);
  if (phone.length === 10 && phone.startsWith("3")) phone = `57${phone}`;
  return phone;
}

function phoneFromJid(value = "") {
  const user = String(value || "").split("@")[0].split(":")[0];
  return normalizePhone(user);
}

function rememberInboundId(id = "") {
  const key = String(id || "").trim();
  if (!key) return false;
  if (processedInboundIds.has(key)) return true;
  processedInboundIds.add(key);
  if (processedInboundIds.size > 500) {
    const first = processedInboundIds.values().next().value;
    processedInboundIds.delete(first);
  }
  return false;
}

function rememberOutboundId(id = "") {
  const key = String(id || "").trim();
  if (!key) return;
  sentOutboundIds.add(key);
  if (sentOutboundIds.size > 500) {
    const first = sentOutboundIds.values().next().value;
    sentOutboundIds.delete(first);
  }
}

function isOutboundId(id = "") {
  const key = String(id || "").trim();
  return !!key && sentOutboundIds.has(key);
}

function extractMessageText(message = {}) {
  const content = message.message || {};
  return String(
    content.conversation ||
      content.extendedTextMessage?.text ||
      content.imageMessage?.caption ||
      content.videoMessage?.caption ||
      content.documentMessage?.caption ||
      ""
  ).trim();
}

function normalizeText(value = "") {
  return String(value || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .trim();
}

function looksLikeAgentPrompt(text = "") {
  const normalized = normalizeText(text);
  if (!normalized) return false;
  return [
    "clonexa",
    "crm",
    "nomina",
    "corte",
    "conexion",
    "conexiones",
    "tiempo",
    "tiempos",
    "estado",
    "estados",
    "modulo",
    "modulos",
    "produccion",
    "avance",
    "cierre",
    "cierres",
    "cotizacion",
    "cuenta de cobro",
    "pedido",
    "pedidos",
    "stock",
    "dame",
    "consulta",
    "necesito",
  ].some((token) => normalized.includes(token));
}

async function postInboundPayload(payload) {
  if (!INBOUND_URL) return { ok: false, detail: "WHATSAPP_INBOUND_URL not configured." };
  const response = await fetch(INBOUND_URL, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      ...(INBOUND_SECRET ? { "x-clonexa-whatsapp-secret": INBOUND_SECRET } : {}),
    },
    body: JSON.stringify(payload),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    return { ok: false, status: response.status, detail: data?.detail || "Inbound callback failed." };
  }
  return data;
}

async function postInboundMessage(companyId, message, textOverride = "") {
  const remoteJid = String(message.key?.remoteJid || "");
  const text = String(textOverride || extractMessageText(message) || "").trim();
  if (!remoteJid || !text) return { ok: true, ignored: true };
  const payload = {
    company_id: companyId,
    from_jid: remoteJid,
    from_phone: phoneFromJid(remoteJid),
    push_name: message.pushName || "",
    message_id: message.key?.id || "",
    text,
    timestamp: message.messageTimestamp || null,
  };
  return postInboundPayload(payload);
}

async function sendAgentWelcome(companyId, session, sock) {
  if (session.welcomeSent || !session.connectedPhone) return;
  const jid = `${session.connectedPhone}@s.whatsapp.net`;
  const result = await postInboundPayload({
    company_id: companyId,
    event_type: "connected",
    from_jid: jid,
    from_phone: session.connectedPhone,
    text: "__clonexa_whatsapp_connected__",
  });
  const reply = String(result?.reply || "").trim();
  if (!reply) return;
  const sent = await sock.sendMessage(jid, { text: reply });
  rememberOutboundId(`${companyId}:${jid}:${sent?.key?.id || ""}`);
  session.welcomeSent = true;
}

function sessionPublic(companyId) {
  const session = sessions.get(companyId);
  if (!session) {
    return {
      ok: true,
      configured: false,
      status: "not_linked",
      qr_data_url: "",
      connected_phone: "",
      last_error: "",
      last_inbound_at: "",
      last_inbound_from: "",
      last_inbound_text: "",
      last_reply_at: "",
      last_inbound_error: "",
    };
  }
  return {
    ok: true,
    configured: true,
    status: session.status || "connecting",
    qr_data_url: session.qrDataUrl || "",
    connected_phone: session.connectedPhone || "",
    last_error: session.lastError || "",
    last_inbound_at: session.lastInboundAt || "",
    last_inbound_from: session.lastInboundFrom || "",
    last_inbound_text: session.lastInboundText || "",
    last_reply_at: session.lastReplyAt || "",
    last_inbound_error: session.lastInboundError || "",
    updated_at: session.updatedAt || "",
  };
}

async function removeAuth(companyId) {
  const dir = path.join(AUTH_ROOT, companyId);
  await fs.rm(dir, { recursive: true, force: true }).catch(() => {});
}

async function hasAuth(companyId) {
  try {
    const dir = path.join(AUTH_ROOT, companyId);
    const entries = await fs.readdir(dir);
    return entries.length > 0;
  } catch {
    return false;
  }
}

async function startSession(companyId) {
  const existing = sessions.get(companyId);
  if (existing?.sock && ["connecting", "qr", "connected"].includes(existing.status)) {
    return sessionPublic(companyId);
  }

  const dir = path.join(AUTH_ROOT, companyId);
  await fs.mkdir(dir, { recursive: true });
  const { state, saveCreds } = await useMultiFileAuthState(dir);
  const { version } = await fetchLatestBaileysVersion();
  const session = {
    sock: null,
    status: "connecting",
    qrDataUrl: "",
    connectedPhone: "",
    lastError: "",
    lastInboundAt: "",
    lastInboundFrom: "",
    lastInboundText: "",
    lastReplyAt: "",
    lastInboundError: "",
    updatedAt: new Date().toISOString(),
    intentionalClose: false,
    welcomeSent: false,
  };
  sessions.set(companyId, session);

  const sock = makeWASocket({
    auth: state,
    browser: ["CLONEXA ShopLink", "Chrome", "1.0.0"],
    logger,
    printQRInTerminal: false,
    version,
  });
  session.sock = sock;
  sock.ev.on("creds.update", saveCreds);
  sock.ev.on("messages.upsert", async (event) => {
    const messages = Array.isArray(event?.messages) ? event.messages : [];
    for (const message of messages) {
      const remoteJid = String(message?.key?.remoteJid || "");
      if (!remoteJid) continue;
      if (remoteJid.endsWith("@g.us") || remoteJid === "status@broadcast") continue;
      const messageId = message?.key?.id || "";
      if (isOutboundId(`${companyId}:${remoteJid}:${messageId}`)) continue;
      const fromMe = !!message?.key?.fromMe;
      const remotePhone = phoneFromJid(remoteJid);
      const text = extractMessageText(message);
      const isSelfChat = !!session.connectedPhone && remotePhone === normalizePhone(session.connectedPhone);
      if (fromMe && !isSelfChat && !looksLikeAgentPrompt(text)) continue;
      if (rememberInboundId(`${companyId}:${remoteJid}:${messageId}`)) continue;
      try {
        session.lastInboundAt = new Date().toISOString();
        session.lastInboundFrom = remotePhone || remoteJid;
        session.lastInboundText = text.slice(0, 160);
        session.lastInboundError = "";
        const result = await postInboundMessage(companyId, message, text);
        const reply = String(result?.reply || "").trim();
        if (reply) {
          const sent = await sock.sendMessage(remoteJid, { text: reply });
          rememberOutboundId(`${companyId}:${remoteJid}:${sent?.key?.id || ""}`);
          session.lastReplyAt = new Date().toISOString();
        }
      } catch (error) {
        session.lastInboundError = error.message || String(error);
        logger.error({ err: error, companyId, remoteJid }, "whatsapp inbound failed");
      }
    }
  });
  sock.ev.on("connection.update", async (update) => {
    session.updatedAt = new Date().toISOString();
    if (update.qr) {
      session.status = "qr";
      session.qrDataUrl = await QRCode.toDataURL(update.qr, { margin: 1, width: 280 });
      session.lastError = "";
    }
    if (update.connection === "open") {
      session.status = "connected";
      session.qrDataUrl = "";
      session.connectedPhone = phoneFromJid(sock.user?.id || sock.user?.jid || "");
      session.lastError = "";
      await sendAgentWelcome(companyId, session, sock).catch((error) => {
        logger.error({ err: error, companyId }, "whatsapp welcome failed");
      });
    }
    if (update.connection === "close") {
      const statusCode = update.lastDisconnect?.error?.output?.statusCode;
      const loggedOut = statusCode === DisconnectReason.loggedOut;
      session.sock = null;
      session.status = loggedOut ? "not_linked" : "disconnected";
      session.lastError = update.lastDisconnect?.error?.message || "";
      if (loggedOut || session.intentionalClose) {
        await removeAuth(companyId);
        session.qrDataUrl = "";
        return;
      }
    }
  });
  return sessionPublic(companyId);
}

async function logoutSession(companyId) {
  const session = sessions.get(companyId);
  if (session?.sock) {
    session.intentionalClose = true;
    await session.sock.logout().catch(() => {});
    if (typeof session.sock.end === "function") {
      await session.sock.end().catch(() => {});
    }
  }
  sessions.delete(companyId);
  await removeAuth(companyId);
  return sessionPublic(companyId);
}

async function sendMessage(companyId, to, message) {
  const phone = normalizePhone(to);
  if (!phone) {
    return { ok: false, status: "missing_phone", detail: "Destino WhatsApp requerido." };
  }
  const text = String(message || "").trim();
  if (!text) {
    return { ok: false, status: "missing_message", detail: "Mensaje requerido." };
  }
  let session = sessions.get(companyId);
  if (!session || !session.sock) {
    await startSession(companyId);
    session = sessions.get(companyId);
  }
  if (!session?.sock || session.status !== "connected") {
    return { ok: false, status: session?.status || "not_linked", detail: "WhatsApp no esta vinculado." };
  }
  const exists = await session.sock.onWhatsApp(phone).catch(() => null);
  const target = Array.isArray(exists)
    ? exists.find((item) => item?.exists)?.jid || ""
    : "";
  if (Array.isArray(exists) && !target) {
    return {
      ok: false,
      status: "not_on_whatsapp",
      to: phone,
      detail: "El numero destino no aparece activo en WhatsApp.",
    };
  }
  const jid = target || `${phone}@s.whatsapp.net`;
  const sent = await session.sock.sendMessage(jid, { text });
  rememberOutboundId(`${companyId}:${jid}:${sent?.key?.id || ""}`);
  return { ok: true, status: "sent", to: phone, jid, message_id: sent?.key?.id || "" };
}

async function readJson(req) {
  const chunks = [];
  for await (const chunk of req) chunks.push(chunk);
  const raw = Buffer.concat(chunks).toString("utf8");
  if (!raw) return {};
  return JSON.parse(raw);
}

function sendJson(res, statusCode, payload) {
  const body = JSON.stringify(payload);
  res.writeHead(statusCode, {
    "content-type": "application/json; charset=utf-8",
    "content-length": Buffer.byteLength(body),
  });
  res.end(body);
}

function routeParts(url = "") {
  return new URL(url, `http://127.0.0.1:${PORT}`).pathname.split("/").filter(Boolean);
}

const server = http.createServer(async (req, res) => {
  try {
    const parts = routeParts(req.url);
    if (req.method === "GET" && parts[0] === "health") {
      return sendJson(res, 200, { ok: true, service: "clonexa-whatsapp-bridge" });
    }
    if (parts[0] !== "sessions" || !parts[1]) {
      return sendJson(res, 404, { ok: false, detail: "Ruta no encontrada." });
    }
    const companyId = cleanCompanyId(parts[1]);
    if (!companyId) {
      return sendJson(res, 422, { ok: false, detail: "Empresa invalida." });
    }
    if (req.method === "GET" && parts.length === 2) {
      const existing = sessions.get(companyId);
      if ((!existing || existing.status === "disconnected") && await hasAuth(companyId)) {
        return sendJson(res, 200, await startSession(companyId));
      }
      return sendJson(res, 200, sessionPublic(companyId));
    }
    if (req.method === "POST" && parts[2] === "start") {
      return sendJson(res, 200, await startSession(companyId));
    }
    if (req.method === "POST" && parts[2] === "logout") {
      return sendJson(res, 200, await logoutSession(companyId));
    }
    if (req.method === "POST" && parts[2] === "send") {
      const payload = await readJson(req);
      const sent = await sendMessage(companyId, payload.to, payload.message);
      return sendJson(res, sent.ok ? 200 : 409, sent);
    }
    return sendJson(res, 404, { ok: false, detail: "Ruta no encontrada." });
  } catch (error) {
    logger.error({ err: error }, "bridge request failed");
    return sendJson(res, 500, { ok: false, status: "bridge_error", detail: error.message || String(error) });
  }
});

await fs.mkdir(AUTH_ROOT, { recursive: true });
server.listen(PORT, "127.0.0.1", () => {
  logger.info({ port: PORT }, "CLONEXA WhatsApp bridge listening");
});
