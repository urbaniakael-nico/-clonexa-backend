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
const logger = Pino({ level: process.env.WHATSAPP_BRIDGE_LOG_LEVEL || "warn" });
const sessions = new Map();

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
    };
  }
  return {
    ok: true,
    configured: true,
    status: session.status || "connecting",
    qr_data_url: session.qrDataUrl || "",
    connected_phone: session.connectedPhone || "",
    last_error: session.lastError || "",
    updated_at: session.updatedAt || "",
  };
}

async function removeAuth(companyId) {
  const dir = path.join(AUTH_ROOT, companyId);
  await fs.rm(dir, { recursive: true, force: true }).catch(() => {});
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
    updatedAt: new Date().toISOString(),
    intentionalClose: false,
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
