// Escribe la composicion HyperFrames (index.html + compositions/*.html) a partir de guion.json.
// Uso: node tools/build.mjs <proyecto> [--borrador]
//   --borrador: sin audios de HeyGen; tiempos estimados y Nexa de muestra (mudo) para revisar el diseno.
// Tiempos: bloque 1 = video de Nexa que abre; luego la narracion (TTS) con una escena por frase; al final
// Nexa cierra y entra el logo. Los subtitulos salen de los tiempos por palabra de cada audio.
import fs from "node:fs";
import path from "node:path";
import { execFileSync } from "node:child_process";

const [dir, ...flags] = process.argv.slice(2);
const draft = flags.includes("--borrador");
const P = (...p) => path.join(dir, ...p);
const g = JSON.parse(fs.readFileSync(P("guion.json"), "utf8"));
const M = g.marca;
const W = 1080, H = 1920;
const FFPROBE = path.resolve(dir, "..", "work", "bin", "ffprobe.exe");
const r3 = (n) => Math.round(n * 1000) / 1000;
const esc = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

function duration(rel) {
  const out = execFileSync(FFPROBE, ["-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", P(rel)]).toString();
  return Number(out.trim());
}
const split = (t) => t.split(/\s+/).filter(Boolean);
// Palabras [{text,start,end}] de un audio; en borrador se estiman (0,3 s por palabra).
function words(rel, text, offset = 0.15) {
  if (!draft) return JSON.parse(fs.readFileSync(P(rel), "utf8"));
  return split(text).map((w, i) => ({ text: w, start: r3(offset + i * 0.3), end: r3(offset + i * 0.3 + 0.27) }));
}

// ---------------------------------------------------------------- tiempos
const sample = "assets/nexa/muestra.mp4";
const abre = { ...g.nexa.abre, src: draft ? sample : g.nexa.abre.video };
const cierra = { ...g.nexa.cierra, src: draft ? sample : g.nexa.cierra.video };
abre.words = words(abre.palabras, abre.texto);
cierra.words = words(cierra.palabras, cierra.texto);
abre.len = draft ? r3(abre.words.at(-1).end + 0.45) : duration(abre.src);
cierra.len = draft ? r3(cierra.words.at(-1).end + 0.45) : duration(cierra.src);

// Una TTS por frase: cada escena dura lo que su frase (la tarjeta entra y luego habla Nexa).
const LEAD = 0.3, TAIL = 0.45;
let cursor = abre.len;
const frases = g.narracion.frases.map((f) => {
  const ws = words(f.palabras, f.texto, 0.05);
  if (ws.length !== split(f.texto).length) console.warn(`aviso: ${f.bloque} tiene ${ws.length} palabras en la TTS y ${split(f.texto).length} en el guion`);
  const start = r3(cursor);
  const at = r3(start + LEAD);
  const len = draft ? r3(ws.at(-1).end + 0.2) : duration(f.audio);
  const end = r3(at + Math.max(ws.at(-1).end + TAIL, len));
  cursor = end;
  return { ...f, words: ws, start, at, len, end };
});
const starts = frases.map((f) => f.start);
const ends = frases.map((f) => f.end);
const cierreStart = r3(cursor);
const logoStart = r3(cierreStart + cierra.words.at(-1).end + 0.35);
const total = r3(Math.max(cierreStart + cierra.len, logoStart + 2.4));
const OVER = 0.5; // la tarjeta nueva entra encima de la anterior

// ---------------------------------------------------------------- estilos comunes
const cardCss = `
  .card{position:absolute;left:36px;top:150px;width:${W - 72}px;height:${H - 300}px;border-radius:56px;overflow:hidden;
    background:#000;box-shadow:0 40px 90px rgba(0,0,0,.55),0 0 0 2px rgba(255,255,255,.06)}
  .zoom{position:absolute;inset:0}
  .zoom video{position:absolute;left:0;top:0;width:100%;height:100%;object-fit:cover}
  .cx{position:absolute;border-radius:30px;padding:14px;background:rgba(255,255,255,.84);
    backdrop-filter:blur(18px);-webkit-backdrop-filter:blur(18px);border:1.5px solid rgba(255,255,255,.75);
    box-shadow:0 26px 60px rgba(25,5,15,.38),0 4px 14px rgba(25,5,15,.18)}
  .cx-tag{display:flex;align-items:center;gap:12px;margin:2px 6px 12px;font:800 27px/1 ${M.fuente},sans-serif;color:${M.tinta};letter-spacing:-.01em}
  .cx-dot{width:16px;height:16px;border-radius:50%;background:linear-gradient(135deg,${M.degradado[0]},${M.degradado[1]})}
  .cx img{display:block;width:100%;border-radius:18px}
  .phone{position:absolute;border-radius:58px;padding:13px;background:#111;
    box-shadow:0 30px 70px rgba(25,5,15,.5),0 0 0 2px rgba(255,255,255,.18) inset}
  .phone video{display:block;width:100%;border-radius:46px}
  .phone .cx-tag{position:absolute;left:50%;transform:translateX(-50%);top:-74px;white-space:nowrap;margin:0;padding:14px 22px;border-radius:999px;
    background:rgba(255,255,255,.9);box-shadow:0 12px 30px rgba(25,5,15,.3)}`;

function cardHtml(id, c) {
  const tag = c.etiqueta ? `<div class="cx-tag"><span class="cx-dot"></span>${esc(c.etiqueta)}</div>` : "";
  if (c.tipo === "telefono") {
    const h = Math.round((c.w - 26) * (1688 / 780));
    return `<div id="${id}" class="phone" style="left:${c.x}px;top:${c.y}px;width:${c.w}px">${tag.replace('class="cx-tag"', `id="${id}-tag" class="cx-tag"`)}
      <video id="${id}-v" class="clip" src="${c.src}" muted playsinline data-start="${c.inicio}" data-duration="${c.dur}" style="height:${h}px"></video></div>`;
  }
  return `<div id="${id}" class="cx" style="left:${c.x}px;top:${c.y}px;width:${c.w}px">${tag}<img src="${c.src}" alt=""></div>`;
}

// ---------------------------------------------------------------- escena (tarjeta con video + tarjetas de Clonexa)
function sceneFile(id, len, clips, cards, opts = {}) {
  let t = 0;
  const vids = clips.map((c, i) => {
    const d = i === clips.length - 1 ? r3(len - t) : r3(len * (c.parte || 1 / clips.length));
    const v = { ...c, id: `${id}-v${i}`, start: r3(t), dur: d };
    t = r3(t + d);
    return v;
  });
  const cs = cards.map((c, i) => {
    const clip = vids[c.clip || 0];
    const inicio = r3(clip.start + c.entra);
    const fin = c.hasta !== undefined ? Math.min(len, clip.start + c.hasta) : c.clip !== undefined && c.clip < vids.length - 1 ? vids[c.clip].start + vids[c.clip].dur : len;
    return { ...c, cid: `${id}-${c.id}`, inicio, dur: r3(fin - inicio), fin: r3(fin) };
  });
  const sound = opts.audio ? `data-has-audio="true"` : "muted";
  const tweens = [];
  if (opts.enter !== false) tweens.push(`tl.fromTo("#${id}-card",{y:140,scale:.9,opacity:0,rotation:-1.2},{y:0,scale:1,opacity:1,rotation:0,duration:.6,ease:"power3.out"},0);`);
  // zoom lento tipo camara (max 6 %) en cada clip
  for (const v of vids) tweens.push(`tl.fromTo("#${v.id}-z",{scale:1},{scale:1.06,duration:${v.dur},ease:"none"},${v.start});`);
  for (const c of cs) {
    tweens.push(`tl.fromTo("#${c.cid}",{opacity:0,scale:.55,y:50},{opacity:1,scale:1,y:0,duration:.6,ease:"back.out(1.9)"},${c.inicio});`);
    if (c.fin < len) tweens.push(`tl.to("#${c.cid}",{opacity:0,scale:.92,duration:.2,ease:"power2.in"},${r3(c.fin - 0.2)});`);
  }
  if (opts.extra) tweens.push(opts.extra);
  return `<template>
  <style>
    #root{position:absolute;inset:0}
    ${cardCss}
    ${opts.css || ""}
  </style>
  <div id="root" data-composition-id="${id}" data-width="${W}" data-height="${H}">
    <div id="${id}-card" class="card">
      ${vids.map((v) => `<div id="${v.id}-z" class="zoom"><video id="${v.id}" class="clip" src="${v.src}" ${sound} playsinline data-start="${v.start}" data-duration="${v.dur}"${v.mediaStart ? ` data-media-start="${v.mediaStart}"` : ""}></video></div>`).join("\n      ")}
    </div>
    ${cs.map((c) => cardHtml(c.cid, c)).join("\n    ")}
    ${opts.html || ""}
  </div>
  <script>
    const tl = gsap.timeline({ paused: true });
    ${tweens.join("\n    ")}
    window.__timelines["${id}"] = tl;
  </script>
</template>
`;
}

// ---------------------------------------------------------------- subtitulos
function captionsFile(all) {
  // grupos de 2 a 4 palabras; se corta en puntuacion
  const groups = [];
  let cur = [];
  for (const w of all) {
    cur.push(w);
    const brk = /[.,?!:;]$/.test(w.text) || cur.length >= 4 || (cur.length >= 3 && w.text.length > 7);
    if (brk) { groups.push(cur); cur = []; }
  }
  if (cur.length) groups.push(cur);
  const tw = [];
  const html = groups.map((gr, gi) => {
    const gs = r3(Math.max(0.12, gr[0].start - 0.08));
    const next = groups[gi + 1];
    const ge = r3(next ? Math.min(gr.at(-1).end + 0.35, next[0].start - 0.08) : gr.at(-1).end + 0.4);
    tw.push(`tl.fromTo("#cap${gi}",{opacity:0,y:18},{opacity:1,y:0,duration:.14,ease:"power2.out"},${gs});`);
    tw.push(`tl.to("#cap${gi}",{opacity:0,duration:.1,ease:"power2.in"},${r3(Math.max(gs + 0.15, ge - 0.1))});`);
    tw.push(`tl.set("#cap${gi}",{visibility:"hidden"},${ge});`);
    gr.forEach((w, wi) => {
      tw.push(`tl.set("#cap${gi}w${wi}",{color:"${M.acento}"},${r3(w.start)});`);
      tw.push(`tl.fromTo("#cap${gi}w${wi}",{scale:1},{scale:1.1,duration:.09,ease:"power2.out"},${r3(w.start)});`);
      tw.push(`tl.to("#cap${gi}w${wi}",{scale:1,color:"#ffffff",duration:.1},${r3(Math.max(w.start + 0.1, w.end))});`);
    });
    return `<div id="cap${gi}" class="cap"><span class="capbox">${gr.map((w, wi) => `<span id="cap${gi}w${wi}" class="w">${esc(w.text)}</span>`).join("")}</span></div>`;
  }).join("\n    ");
  return `<template>
  <style>
    #root{position:absolute;inset:0;pointer-events:none}
    .cap{position:absolute;left:60px;right:60px;top:1165px;text-align:center;opacity:0;overflow:visible}
    .capbox{display:inline-block;padding:16px 30px 20px;border-radius:28px;background:rgba(10,7,16,.62);
      font:900 66px/1.12 ${M.fuente},sans-serif;color:#fff;letter-spacing:-.015em;text-shadow:0 3px 12px rgba(0,0,0,.35)}
    .w{display:inline-block;margin:0 .2em;transform-origin:50% 70%}
  </style>
  <div id="root" data-composition-id="captions" data-width="${W}" data-height="${H}">
    ${html}
  </div>
  <script>
    const tl = gsap.timeline({ paused: true });
    ${tw.join("\n    ")}
    window.__timelines["captions"] = tl;
  </script>
</template>
`;
}

// ---------------------------------------------------------------- armar
fs.mkdirSync(P("compositions"), { recursive: true });
const hosts = [];
const host = (id, start, dur, z, kind = "graphics") => hosts.push(
  `<div id="${id}" data-composition-id="${id}" data-composition-src="compositions/${id}.html" data-start="${r3(start)}" data-duration="${r3(dur)}" data-track-index="${hosts.length + 1}" data-track-kind="${kind}" data-width="${W}" data-height="${H}" style="z-index:${z}"></div>`);

// 1) Nexa abre: su cara desde el cuadro 0 (sin animacion de entrada)
const abreLen = r3(abre.len + OVER);
fs.writeFileSync(P("compositions", "nexa-abre.html"), sceneFile("nexa-abre", abreLen, [{ src: abre.src }], [], { enter: false, audio: !draft }));
host("nexa-abre", 0, abreLen, 1);

// 2-5) escenas con la voz de Nexa
frases.forEach((f, i) => {
  const e = g.escenas[f.bloque];
  const len = r3(ends[i] - starts[i] + OVER);
  fs.writeFileSync(P("compositions", `${f.bloque}.html`), sceneFile(f.bloque, len, e.clips, e.tarjetas || []));
  host(f.bloque, starts[i], len, 2 + i);
});

// 6) Nexa cierra + "Comenta DEMO" + logo y web
const demoAt = cierra.words.find((w) => /^DEMO/i.test(w.text))?.start ?? 0.4;
const lg = r3(logoStart - cierreStart);
const cierraLen = r3(total - cierreStart);
const endCss = `
  .demo{position:absolute;left:0;right:0;top:300px;text-align:center}
  .demo span{display:inline-block;padding:22px 40px;border-radius:999px;font:900 60px/1 ${M.fuente},sans-serif;color:#fff;
    background:linear-gradient(135deg,${M.degradado[0]},${M.degradado[1]});box-shadow:0 20px 50px rgba(255,46,147,.45)}
  .endcard{position:absolute;inset:0;background:radial-gradient(120% 70% at 50% 40%,${M.fondo2},${M.fondo});opacity:0}
  .endlogo{position:absolute;left:150px;width:780px;top:760px}
  .endweb{position:absolute;left:0;right:0;top:960px;text-align:center;font:800 58px/1 ${M.fuente},sans-serif;color:${M.texto};letter-spacing:-.01em}
  .endline{position:absolute;left:390px;width:300px;top:1060px;height:8px;border-radius:8px;background:linear-gradient(90deg,${M.degradado[0]},${M.degradado[1]})}`;
const endHtml = `<div id="nexa-cierra-demo" class="demo"><span id="nexa-cierra-demo-pill">💬 Comenta DEMO</span></div>
    <div id="nexa-cierra-end" class="endcard"><img id="nexa-cierra-logo" class="endlogo" src="${M.logo}" alt="Clonexa">
      <div id="nexa-cierra-web" class="endweb">${esc(M.web)}</div><div id="nexa-cierra-line" class="endline"></div></div>`;
const endTw = [
  `tl.fromTo("#nexa-cierra-demo-pill",{opacity:0,scale:.5},{opacity:1,scale:1,duration:.5,ease:"back.out(2.2)"},${r3(demoAt)});`,
  `tl.to("#nexa-cierra-demo-pill",{opacity:0,scale:.9,duration:.2},${r3(lg - 0.25)});`,
  `tl.to("#nexa-cierra-end",{opacity:1,duration:.4,ease:"power2.out"},${lg});`,
  `tl.fromTo("#nexa-cierra-logo",{opacity:0,y:40,scale:.92},{opacity:1,y:0,scale:1,duration:.6,ease:"back.out(1.6)"},${r3(lg + 0.15)});`,
  `tl.fromTo("#nexa-cierra-web",{opacity:0,y:24},{opacity:1,y:0,duration:.45,ease:"power3.out"},${r3(lg + 0.45)});`,
  `tl.fromTo("#nexa-cierra-line",{scaleX:0},{scaleX:1,duration:.5,ease:"power3.out"},${r3(lg + 0.6)});`,
].join("\n    ");
fs.writeFileSync(P("compositions", "nexa-cierra.html"),
  sceneFile("nexa-cierra", cierraLen, [{ src: cierra.src }], [], { audio: !draft, css: endCss, html: endHtml, extra: endTw }));
host("nexa-cierra", cierreStart, cierraLen, 10);

// subtitulos con tiempos absolutos
const allWords = [
  ...abre.words,
  ...frases.flatMap((f) => f.words.map((w) => ({ ...w, start: r3(f.at + w.start), end: r3(f.at + w.end) }))),
  ...cierra.words.map((w) => ({ ...w, start: r3(cierreStart + w.start), end: r3(cierreStart + w.end) })),
].filter((w) => w.start < logoStart - 0.1);
fs.writeFileSync(P("compositions", "captions.html"), captionsFile(allWords));
host("captions", 0, total, 20, "captions");

// audio: narracion y musica (Nexa trae su sonido en el video)
const vol = g.musica.volumen ?? 0.12;
const audio = [
  ...frases.map((f, i) => `<audio id="voz-${f.bloque}" class="clip" src="${f.audio}" data-start="${f.at}" data-duration="${r3(f.len)}" data-track-index="${30 + i}" data-volume="1"></audio>`),
  `<audio id="musica" class="clip" src="${g.musica.src}" data-start="0" data-duration="${total}" data-track-index="40" data-volume="${vol}" data-fade-out="1.2"></audio>`,
].filter(Boolean).join("\n      ");

fs.writeFileSync(P("index.html"), `<!doctype html>
<html lang="es" data-resolution="portrait">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=${W}, height=${H}" />
    <title>${esc(g.titulo)}</title>
    <script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
    <style>
      * { margin: 0; padding: 0; box-sizing: border-box; }
      html, body { margin: 0; width: ${W}px; height: ${H}px; overflow: hidden; background: ${M.fondo}; }
      #root { position: relative; width: 100%; height: 100%; font-family: ${M.fuente}, sans-serif; }
      #bg { position: absolute; inset: 0; background: radial-gradient(90% 60% at 50% 35%, ${M.fondo2}, ${M.fondo}); }
    </style>
  </head>
  <body>
    <!-- Generado por tools/build.mjs desde guion.json${draft ? " (BORRADOR: tiempos estimados, Nexa de muestra)" : ""} -->
    <div id="root" data-composition-id="main" data-start="0" data-duration="${total}" data-width="${W}" data-height="${H}">
      <div id="bg"></div>
      ${hosts.join("\n      ")}
      ${audio}
    </div>
    <script>
      const tl = gsap.timeline({ paused: true });
      window.__timelines["main"] = tl;
    </script>
  </body>
</html>
`);
console.log(JSON.stringify({ draft, total, abre: abre.len, starts, ends, cierreStart, logoStart }, null, 1));
