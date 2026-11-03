#!/usr/bin/env bash
# Render final: HyperFrames (SDR) -> H.264 High + AAC, -14 LUFS / -1 dBTP, faststart, ~21 MB en 30 s; portada jpg.
# Uso (desde ops/nexa-video): bash tools/final.sh <proyecto> <carpeta-salida> <nombre> [segundo-portada]
set -euo pipefail
cd "$(dirname "$0")/.."
export PATH="$PWD/work/bin:$PATH"
P="$1"; OUT="$2"; NAME="$3"; COVER="${4:-2.0}"
mkdir -p "$OUT" work
(cd "$P" && npx hyperframes render -o ../work/render.mp4 -f 30 -q delivery -w 2 --sdr --quiet)
M=$(ffmpeg -hide_banner -nostats -i work/render.mp4 -af loudnorm=I=-14:TP=-1:LRA=11:print_format=json -f null - 2>&1 | sed -n '/^{/,/^}/p')
g() { echo "$M" | node -e "console.log(JSON.parse(require('fs').readFileSync(0))['$1'])"; }
AF="loudnorm=I=-14:TP=-1:LRA=11:measured_I=$(g input_i):measured_TP=$(g input_tp):measured_LRA=$(g input_lra):measured_thresh=$(g input_thresh):offset=$(g target_offset):linear=true,aresample=48000"
V="-pix_fmt yuv420p -c:v libx264 -preset slow -profile:v high -r 30 -b:v 5500k -color_primaries bt709 -color_trc bt709 -colorspace bt709"
(cd work && ffmpeg -v error -y -i render.mp4 $V -pass 1 -passlogfile x264 -an -f null NUL \
  && ffmpeg -v error -y -i render.mp4 $V -maxrate 8000k -bufsize 11000k -pass 2 -passlogfile x264 \
       -af "$AF" -c:a aac -b:a 160k -ar 48000 -movflags +faststart "$OUT/$NAME.mp4" && rm -f x264*)
ffmpeg -v error -y -ss "$COVER" -i "$OUT/$NAME.mp4" -frames:v 1 -q:v 2 "$OUT/$NAME.jpg"
ffprobe -v error -show_entries stream=codec_name,profile,width,height,r_frame_rate:format=duration,size -of compact "$OUT/$NAME.mp4"
ffmpeg -hide_banner -nostats -i "$OUT/$NAME.mp4" -af ebur128=peak=true -f null - 2>&1 | grep -E "^\s+(I|Peak):" | tail -2
