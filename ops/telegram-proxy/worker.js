// Proxy minimo hacia la API de Telegram (Cloudflare Worker).
// Solo reenvia /bot<token>/<metodo> y /file/bot<token>/<ruta> a api.telegram.org,
// exige la cabecera X-Proxy-Key igual al secreto PROXY_KEY (wrangler secret put PROXY_KEY)
// y rechaza todo lo demas con 403. No guarda ni registra nada.
const UPSTREAM = "https://api.telegram.org";
const ALLOWED_PATH = /^\/(?:bot\d+:[A-Za-z0-9_-]+\/[A-Za-z0-9_]+|file\/bot\d+:[A-Za-z0-9_-]+\/[A-Za-z0-9_./-]+)$/;

function safeEqual(a, b) {
  if (typeof a !== "string" || typeof b !== "string" || a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i += 1) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const key = request.headers.get("X-Proxy-Key") || "";
    if (!env.PROXY_KEY || !safeEqual(key, env.PROXY_KEY) || !ALLOWED_PATH.test(url.pathname) || url.pathname.includes("..")) {
      return new Response("Forbidden", { status: 403 });
    }
    if (!["GET", "POST"].includes(request.method)) {
      return new Response("Forbidden", { status: 403 });
    }
    const headers = new Headers();
    const contentType = request.headers.get("Content-Type");
    if (contentType) headers.set("Content-Type", contentType);
    const upstream = await fetch(UPSTREAM + url.pathname + url.search, {
      method: request.method,
      headers,
      body: request.method === "POST" ? request.body : undefined,
    });
    return new Response(upstream.body, { status: upstream.status, headers: upstream.headers });
  },
};
