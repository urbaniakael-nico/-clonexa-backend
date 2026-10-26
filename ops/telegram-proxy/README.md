# Proxy de Telegram (Cloudflare Worker)

Solo se usa si Railway no llega bien a `api.telegram.org`. El backend lo usa cuando
existen `TELEGRAM_API_BASE` (URL del Worker) y `TELEGRAM_PROXY_KEY` (cabecera `X-Proxy-Key`).

1. `npx wrangler login` (cuenta gratis de Cloudflare).
2. Desde esta carpeta: `npx wrangler deploy` (crea `clonexa-telegram-proxy.<cuenta>.workers.dev`).
3. `npx wrangler secret put PROXY_KEY` y pega una clave nueva y fuerte (no se guarda en el repo).
4. En Railway (`-clonexa-backend`): `TELEGRAM_API_BASE=https://clonexa-telegram-proxy.<cuenta>.workers.dev`
   y `TELEGRAM_PROXY_KEY=<la misma clave>`.
5. Para volver a la ruta directa: borra las dos variables.

El Worker responde 403 a todo lo que no sea `/bot<token>/<metodo>` o `/file/bot<token>/<ruta>`
con la clave correcta.
