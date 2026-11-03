# Nexa + escenas (videos verticales con HyperFrames)

Videos de 30 s en vertical (1080x1920 a 30 fps). Nexa abre y cierra con su cara (HeyGen Avatar IV). En medio van escenas reales de Pexels, cada una como tarjeta, con tarjetas de pantallas **reales** de Clonexa, la voz de Nexa (TTS de HeyGen) y subtítulos palabra por palabra.

- Herramienta: [HyperFrames](https://github.com/heygen-com/hyperframes), licencia Apache-2.0. Versión fija `hyperframes@0.8.155`.
- FFmpeg: `ffmpeg-static` y `ffprobe-static`, copiados a `work/bin/` (`work/` está en `.gitignore`).
- Sin secretos en el repo: `tools/heygen.mjs` lee la key de HeyGen de `C:/Users/valef/Desktop/nexa-secret/heygen.key` (fuera del repo) y nunca la imprime.

## Pasos (proyecto `restaurante/`)

```bash
cd ops/nexa-video
npm ci
mkdir -p work/bin && cp node_modules/ffmpeg-static/ffmpeg.exe node_modules/ffprobe-static/bin/win32/x64/ffprobe.exe work/bin/
export PATH="$PWD/work/bin:$PATH"

# 1. Material: escenas verticales y recortes de pantallas reales (editar tiempos y recortes en el script)
bash tools/prep-restaurante.sh

# 2. Voz y Nexa (HeyGen)
# la key de HeyGen va en C:/Users/valef/Desktop/nexa-secret/heygen.key (fuera del repo)
node tools/heygen.mjs quota
node tools/heygen.mjs tts "<frase de apertura>" restaurante/assets/nexa/abre.wav restaurante/assets/nexa/abre.words.json
node tools/heygen.mjs tts "<frase de cierre>"   restaurante/assets/nexa/cierra.wav restaurante/assets/nexa/cierra.words.json
node tools/heygen.mjs tts "<frase de cada escena>" restaurante/assets/voz/<escena>.wav restaurante/assets/voz/<escena>.words.json   # una por escena
node tools/heygen.mjs avatar restaurante/assets/nexa/abre.meta.json   restaurante/assets/nexa/abre.mp4
node tools/heygen.mjs avatar restaurante/assets/nexa/cierra.meta.json restaurante/assets/nexa/cierra.mp4

# 3. Composición, revisión y entrega (render SDR -> H.264 + AAC, -14 LUFS, faststart, portada)
node tools/build.mjs restaurante            # --borrador: sin HeyGen, con tiempos estimados
(cd restaurante && npx hyperframes check && npx hyperframes snapshot --frames 9)
bash tools/final.sh restaurante "C:/Users/valef/OneDrive/Desktop/nexa-escenas/_pruebas" nexa-restaurante-v1 2.0
```

## Cómo se arma (`tools/build.mjs`)

Todo sale de `guion.json`: textos, escenas, tarjetas (posición `x`/`y`/`w`, segundo en que entra `entra`) y marca.

- **Bloque 1:** el video de Nexa que abre, desde el cuadro 0.
- **Bloques 2 a 5:** una escena por frase, cada una con su propia TTS. La tarjeta entra 0,3 s antes de que Nexa hable y la escena dura lo que dura su frase.
- **Bloque 6:** Nexa cierra, aparece "Comenta DEMO" y después el logo con la web.
- **Escenas:** cada una es una tarjeta con esquinas redondeadas que entra encima de la anterior y tiene un zoom lento de máximo 6 %. Las tarjetas de Clonexa entran con rebote, sombra y vidrio.
- **Subtítulos:** grupos de 2 a 4 palabras. La palabra que suena se pinta del color de la marca, con los tiempos de cada audio.
- **Música:** se mezcla en la composición. El volumen se calcula para quedar 18 dB por debajo de la voz (`musica.volumen` en `guion.json`).

Para otro guion: copia `restaurante/` y cambia `guion.json`, las escenas y las pantallas.
