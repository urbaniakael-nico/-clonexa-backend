// HeyGen para los videos de Nexa (API v3). La key se lee de un archivo FUERA del repo y nunca se imprime.
//   node tools/heygen.mjs quota
//   node tools/heygen.mjs tts "<texto>" <salida.wav> <palabras.json> [modelo]   -> tambien <salida>.meta.json
//   node tools/heygen.mjs avatar <audio.meta.json> <salida.mp4>                 -> Avatar IV de Nexa con ese audio
import fs from "node:fs";

const KEY_FILE = process.env.HEYGEN_KEY_FILE || "C:/Users/valef/Desktop/nexa-secret/heygen.key";
const NEXA = { avatar_id: "e2e5dbd302844e8892f9ca447042640d", voice_id: "145ee9caa9a344d9bf61ddd3d95de7b1" };
const API = "https://api.heygen.com";
const key = fs.readFileSync(KEY_FILE, "utf8").trim();
const H = { "X-Api-Key": key, Accept: "application/json", "Content-Type": "application/json" };
const [cmd, ...args] = process.argv.slice(2);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function call(method, url, body, tries = 5) {
  for (let i = 0; ; i++) {
    const res = await fetch(API + url, { method, headers: H, body: body ? JSON.stringify(body) : undefined });
    const text = await res.text();
    if (res.status === 429 && i < tries) {
      const wait = Number(res.headers.get("retry-after")) || 2 ** (i + 2);
      console.log(`429, espero ${wait} s`);
      await sleep(wait * 1000);
      continue;
    }
    if (!res.ok) throw new Error(`HTTP ${res.status} ${url.replace(/\?.*/, "")}: ${text.slice(0, 600)}`);
    return { json: JSON.parse(text), headers: res.headers };
  }
}
async function download(url, out) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`descarga HTTP ${res.status}`);
  fs.writeFileSync(out, Buffer.from(await res.arrayBuffer()));
}
// caracteres con tiempo -> palabras (se corta en espacios)
function wordsFromChars(chars) {
  const out = [];
  let cur = null;
  for (const c of chars) {
    if (/\s/.test(c.text)) { if (cur) out.push(cur); cur = null; continue; }
    if (!cur) cur = { text: "", start: c.start_time, end: c.end_time };
    cur.text += c.text;
    cur.end = c.end_time;
  }
  if (cur) out.push(cur);
  return out.map((w) => ({ text: w.text, start: Math.round(w.start * 1000) / 1000, end: Math.round(w.end * 1000) / 1000 }));
}

if (cmd === "quota") {
  const me = (await call("GET", "/v3/users/me")).json.data;
  const q = await call("GET", "/v2/user/remaining_quota").then((r) => r.json.data).catch(() => null);
  console.log(JSON.stringify({ wallet_usd: me.wallet?.remaining_balance, auto_reload: me.wallet?.auto_reload, quota: q }, null, 1));
} else if (cmd === "tts") {
  const [text, out, wordsOut, model = "heygen-voice-1-turbo-free"] = args;
  const body = { model, voice_id: NEXA.voice_id, text, language: "es", with_timestamps: true };
  const { json, headers } = await call("POST", "/v3/models/audio/tts", body);
  const d = json.data;
  await download(d.audio_url, out);
  const words = wordsFromChars(d.original_characters || []);
  fs.writeFileSync(wordsOut, JSON.stringify(words, null, 1));
  fs.writeFileSync(out.replace(/\.\w+$/, ".meta.json"), JSON.stringify({
    model, text, audio_url: d.audio_url, duration: d.duration, request_id: headers.get("x-request-id"), language: headers.get("content-language"),
  }, null, 1));
  console.log(`ok ${out} · ${d.duration} s · ${words.length} palabras · modelo ${model} · idioma ${headers.get("content-language")}`);
} else if (cmd === "avatar") {
  const [metaFile, out] = args;
  const meta = JSON.parse(fs.readFileSync(metaFile, "utf8"));
  const body = { type: "avatar", avatar_id: NEXA.avatar_id, audio_url: meta.audio_url, aspect_ratio: "9:16", resolution: "720p", title: `Nexa prueba · ${meta.text.slice(0, 40)}` };
  const id = (await call("POST", "/v3/videos", body)).json.data.video_id;
  console.log("video_id", id);
  for (let i = 0; i < 180; i++) {
    await sleep(10000);
    const v = (await call("GET", `/v3/videos/${id}`)).json.data;
    if (v.status === "completed") {
      await download(v.video_url, out);
      fs.writeFileSync(out.replace(/\.\w+$/, ".video.json"), JSON.stringify({ video_id: id, duration: v.duration ?? null }, null, 1));
      console.log(`ok ${out} · ${v.duration ?? "?"} s`);
      break;
    }
    if (v.status === "failed") throw new Error(`HeyGen fallo: ${v.failure_message || JSON.stringify(v.error || v)}`);
    if (i % 3 === 0) console.log("estado:", v.status);
  }
} else {
  console.log("uso: quota | tts | avatar");
}
