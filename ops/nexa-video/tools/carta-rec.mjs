// Graba la carta QR real (modo video) de la demo Brasa & Maiz en un celular a 2x (780x1688)
// con el screencast de Chrome (CDP) y arma un mp4 a 30 fps con los tiempos reales de cada cuadro.
// Uso: node tools/carta-rec.mjs <url-del-qr> <carpeta-salida> <ffmpeg>
// (necesita playwright; se corrio desde la carpeta de herramientas de captura de la landing)
import { chromium } from "playwright";
import fs from "node:fs";
import path from "node:path";
import { execFileSync } from "node:child_process";

const [url, outDir, ffmpeg] = process.argv.slice(2);
const frames = path.join(outDir, "frames");
fs.rmSync(frames, { recursive: true, force: true });
fs.mkdirSync(frames, { recursive: true });
const browser = await chromium.launch({ channel: "chrome" });
const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true, locale: "es-CO" });
const page = await ctx.newPage();
await page.goto(url, { waitUntil: "networkidle" });
await page.waitForTimeout(1200);
await page.click("[data-cxa-video]");
await page.waitForTimeout(800);
const cdp = await ctx.newCDPSession(page);
const list = [];
cdp.on("Page.screencastFrame", async (f) => {
  const file = path.join(frames, `f${String(list.length).padStart(5, "0")}.jpg`);
  fs.writeFileSync(file, Buffer.from(f.data, "base64"));
  list.push({ file, t: f.metadata.timestamp });
  await cdp.send("Page.screencastFrameAck", { sessionId: f.sessionId }).catch(() => {});
});
await cdp.send("Page.startScreencast", { format: "jpeg", quality: 92, maxWidth: 780, maxHeight: 1688, everyNthFrame: 1 });
await page.waitForTimeout(9000);
await cdp.send("Page.stopScreencast");
await ctx.close();
await browser.close();
// concat con la duracion real de cada cuadro
const lines = [];
list.forEach((f, i) => {
  const d = i < list.length - 1 ? Math.max(0.001, list[i + 1].t - f.t) : 0.04;
  lines.push(`file '${f.file.replace(/\\/g, "/")}'`, `duration ${d.toFixed(4)}`);
});
lines.push(`file '${list.at(-1).file.replace(/\\/g, "/")}'`);
const txt = path.join(outDir, "frames.txt");
fs.writeFileSync(txt, lines.join("\n"));
const out = path.join(outDir, "carta-video-hd.mp4");
execFileSync(ffmpeg, ["-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", txt, "-vf", "fps=30,scale=780:1688:force_original_aspect_ratio=decrease,pad=780:1688:(ow-iw)/2:(oh-ih)/2,format=yuv420p",
  "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-movflags", "+faststart", out]);
console.log(`cuadros: ${list.length}, salida: ${out}`);
