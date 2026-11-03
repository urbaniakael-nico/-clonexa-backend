#!/usr/bin/env bash
# Prepara los recursos del video "restaurante" (escenas verticales y tarjetas con pantallas reales).
# Uso (desde ops/nexa-video): bash tools/prep-restaurante.sh
# Necesita: work/bin/ffmpeg.exe (ffmpeg-static), las escenas en OneDrive y las capturas de la landing.
set -euo pipefail
cd "$(dirname "$0")/.."
export PATH="$PWD/work/bin:$PATH"
S="C:/Users/valef/OneDrive/Desktop/nexa-escenas"
CAP="C:/Users/valef/Desktop/clonexa-landing/public/capturas"
A="restaurante/assets"
mkdir -p "$A/escenas" "$A/pantallas" "$A/marca"

# Escena vertical 1080x1920 a 30 fps, sin audio. $1 entrada, $2 inicio, $3 duracion, $4 filtro de recorte, $5 salida
scene() {
  # setparams + etiquetas bt709: todo sale SDR (cocina 4 viene en HLG y pondria el render en HDR, que pierde las tarjetas)
  ffmpeg -v error -y -ss "$2" -t "$3" -i "$1" -an \
    -vf "$4,scale=1080:1920:flags=lanczos,fps=30,format=yuv420p,setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709" \
    -color_primaries bt709 -color_trc bt709 -colorspace bt709 -c:v libx264 -preset slow -crf 20 -movflags +faststart "$5"
  echo "escena $5"
}
scene "$S/salon/salon 3.mp4"   10.0 7 "crop=2160:3840:0:0"        "$A/escenas/salon.mp4"
scene "$S/cocina/cocina 4.mp4"  9.4 7 "crop=2160:3840:0:0"        "$A/escenas/cocina.mp4"
scene "$S/bodega/bodega 2.mp4"  0.0 6 "crop=810:1440:1180:0"      "$A/escenas/bodega.mp4"
scene "$S/caja/caja.mp4"        5.4 6.8 "crop=1215:2160:1540:0"     "$A/escenas/caja.mp4"
# dueno 1 no se usa: el celular muestra una calculadora y los papeles estan en ruso (pantalla y texto ajenos)

# Carta QR en video (grabacion real de la demo Brasa & Maiz con tools/carta-rec.mjs) -> mp4 780x1688
cp work/carta/carta-video-hd.mp4 "$A/pantallas/carta-video.mp4"
echo "carta-video"

# Tarjetas: recortes de pantallas reales (coordenadas en px de cada captura)
crop() { ffmpeg -v error -y -i "$1" -vf "crop=$2" -frames:v 1 "$3"; echo "tarjeta $3"; }
crop "$CAP/rest-cocina.webp" "1600:500:0:105"   "$A/pantallas/cocina.png"
crop "$CAP/hero-caja.webp"   "965:145:20:95"    "$A/pantallas/caja-kpis.png"
crop "$CAP/rest-cierre.webp" "752:432:424:150"  "$A/pantallas/cierre.png"
INV=work/inventario-tabla.png
crop "$INV" "1236:138:0:70"   "$A/pantallas/inv-lomo.png"
crop "$INV" "1236:138:0:208"  "$A/pantallas/inv-pollo.png"
crop "$INV" "1236:138:0:346"  "$A/pantallas/inv-papa.png"

cp "C:/Users/valef/Desktop/clonexa-landing/public/brand/clonexa-logo.svg" "$A/marca/clonexa-logo.svg"
cp "$S/musica/kornevmusic-upbeat-happy-corporate-487426.mp3" "$A/musica.mp3"
echo listo
