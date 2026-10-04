# Seguridad de base · Consola v2+ Fase 2 (commit 2)

Afecta a **todas las empresas**. Nada de esto bloquea una petición válida.

## 1. Cabeceras de seguridad (`app/core/security_headers.py`)

Middleware ASGI puro registrado en `app/main.py`. Solo agrega cabeceras al empezar la
respuesta; si algo falla al armarlas, la respuesta sale igual que antes. Si una ruta ya puso
su propia cabecera, se respeta.

| Cabecera | Dónde |
|---|---|
| `X-Content-Type-Options: nosniff` | todas las respuestas |
| `Referrer-Policy: strict-origin-when-cross-origin` | todas las respuestas |
| `X-Frame-Options: SAMEORIGIN` | todas **excepto `/webapp/...`** |
| `Content-Security-Policy` | **solo `/admin-v2plus*`** |

### Páginas que se incrustan en un iframe (verificado)

- **WebApp de Telegram `/webapp/materials` → EXCLUIDA de `X-Frame-Options`.** El bot la abre
  como `web_app` (`bots.py`, `_materials_webapp_url`). En Telegram para celular y escritorio
  abre en su propio visor, pero **Telegram Web (web.telegram.org) la abre dentro de un iframe
  de otro origen**: con `SAMEORIGIN` quedaría en blanco.
- Ninguna otra página de Clonexa se incrusta en un iframe de otro sitio. Los iframes propios
  (vista previa de la cuenta en `client.js`, impresión en `hsp_cashier.js`, `sale_document.js`,
  planilla de Sanidad, soportes en `mini_panel.js`) usan `srcdoc`, `blob:` o `data:`: no
  cargan una página del servidor, así que la cabecera no los afecta.
- No puedo saber si un sitio externo (por ejemplo una landing en otro dominio) incrusta
  `/ordenar`, `/carta` o `/domicilio` en un iframe. Si lo hace, dejaría de verse: avísame y se
  agrega su prefijo a `FRAME_EXEMPT_PREFIXES`.

### CSP de la Consola v2+

```
default-src 'self'; script-src 'self'; style-src 'self' https://fonts.googleapis.com;
font-src 'self' https://fonts.gstatic.com; img-src 'self' https:; connect-src 'self';
object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'self'
```

- Sin `unsafe-inline` ni `unsafe-eval` (ni en scripts ni en estilos).
- `img-src https:` es para el logo de cada empresa en la Ficha (los logos válidos son
  `https://…` o rutas propias).
- Para cumplirla se quitó el único código en línea que tenían las dos páginas de v2+: el
  `onerror` del logo pasó a `logoFallback()` en `admin_v2plus.js` y `admin_v2plus_login.js`
  (mismo resultado: si el logo no carga se ve "CX").

## 2. CSP para el resto de la plataforma: informe (NO aplicada)

Hoy no se puede poner una CSP estricta en el resto sin romper pantallas. Lo que habría que
cambiar, de mayor a menor esfuerzo:

| Dónde | Qué lo impide | Qué cambiar |
|---|---|---|
| `client.js` (42 mil líneas) | ~607 atributos `style="…"` en plantillas, ~50 `<style>` creados con JS, 2 manejadores `on…=` en línea, 3 `document.write` | mover los `style=` a clases o a `el.style` (CSSOM, que la CSP sí permite); los `<style>` dinámicos a hojas `.css` estáticas o a un nonce; quitar los `on…=` |
| `admin_v2.js` | ~116 `style=`, 1 `on…=` en línea, `admin_v2.html` con 1 `onerror` | igual que arriba (Admin V2 no se toca en esta fase) |
| `mini_panel.js` | ~65 `style=`, 12 `<style>` dinámicos, 3 `<script>` y 5 `document.write` en ventanas de impresión, 1 `onload="print()"` | imprimir con iframe oculto + `contentWindow.print()` como ya hace `hsp_cashier.js` |
| `brand_inject.py` | inyecta `<script>window.__CX_BRAND__=…</script>` en cada panel | servir la marca como JSON en un `<script type="application/json">` (no ejecutable) o con nonce por petición |
| `admin_v2_routes.py`, `client_routes.py`, `main.py` (página de IP bloqueada) | `<style>` en línea en HTML armado en Python | mover a `.css` o usar nonce |
| `materials_webapp.html` | 1 `<script>` en línea y 1 `<style>`; carga `https://telegram.org/js/telegram-web-app.js` | sacar el script a un `.js`; permitir `https://telegram.org` en `script-src` |
| Mini paneles (`hsp_*.js`, `hospitality_order.js`, `hsp_menu_kit.js`, `hsp_alerts.js`, `carta_qr.js`) | pocos `style=` (1 a 5 por archivo) y 1 `<style>` dinámico cada uno | los más fáciles: se pueden cerrar primero |
| Servicios externos | `fonts.googleapis.com` (`hsp_brand.js`), `translate.google.com` (`client_google_translate.js`), `api.qrserver.com` (imágenes QR en `client.js`), Twilio (`twilio.min.js`), `wa.me` (solo enlaces) | listarlos en `script-src` / `img-src` / `connect-src` según el caso |

Ningún archivo usa `eval` ni `new Function`, lo que facilita el camino. Orden sugerido:
mini paneles → `materials_webapp` → `brand_inject.py` → `client.js` por módulos. Mientras
tanto se puede activar `Content-Security-Policy-Report-Only` para medir sin bloquear.

## 3. Auditoría XSS de los mini paneles

Archivos: `hsp_cashier.js`, `hsp_waiter.js`, `hsp_kitchen.js`, `hospitality_order.js`,
`mini_panel.js` (más `hsp_menu_kit.js` y `hsp_alerts.js`, que pintan datos de esos mismos
paneles). Método: se extrajo cada interpolación `${…}` de cada plantilla que termina en
`innerHTML`, `insertAdjacentHTML` o `document.write`, y se revisó a mano cada una que lleva
datos escritos por un usuario (nombres de producto, cliente, mesero o empleado; notas,
observaciones y términos de pedido; direcciones de domicilio; nombres de mesa; textos de
concursos y asambleas; soportes de venta).

### Corregidos (1 hueco, 4 líneas)

| Archivo | Función | Hueco | Corrección | Prueba |
|---|---|---|---|---|
| `mini_panel.js` | `salesOpenFile022G`, `salesPrintFile022G` | `file.file_data` (soporte o guía de una venta, subido por otro usuario) se escribía sin escapar en `<iframe src="…">` / `<img src="…">` de una ventana nueva **del mismo origen** (`window.open("")`). El servidor (`mini_panel_sales.py`) acepta cualquier texto de hasta 6 MB. Una carga `x" onerror="…` ejecutaba código al pulsar "Ver soporte" o "Imprimir guía". | `h(file.file_data)`, el mismo escape del archivo. Un soporte normal (`data:image/…;base64,…`) se ve igual. | `tests/mini_panel_support_file_xss.test.cjs` (con `<img src=x onerror=…>`) |

### Revisados sin hueco

- `hsp_kitchen.js`: comandas, notas, observaciones, mesero y personal → todo con `h`; los
  avisos pasan por `hsp_alerts.js`, que también escapa.
- `hsp_waiter.js`: mesas, carrito, notas, términos → `h` y `Kit.cartLineLabel` (escapa).
- `hsp_cashier.js`: mesas, meseros, domicilios (dirección, notas, repartidor), cobrados,
  Z e impresión → `h` en todo; las imágenes de carta usan URLs armadas con
  `encodeURIComponent` (no pueden cerrar el atributo).
- `hospitality_order.js` (QR público): carta, cuenta de mesa, canciones, concursos, votos,
  asambleas → `h`; los colores de marca van a un `<style>` por `textContent` (no es HTML) y
  ahora además se validan al guardar.
- `mini_panel.js`: notas, cotizaciones, ventas, referencias, transporte, solicitudes, cierre
  del día → `h`, o `textContent` cuando no es HTML.

### Pendientes (fuera del alcance de "solo innerHTML" o fuera de estos archivos)

1. `mini_panel.js` · `salesDownloadFile022G`: pone `file.file_data` en `a.href` y hace
   `click()`. Un `javascript:` ahí se ejecutaría. No es `innerHTML`; el arreglo correcto es
   validar en el servidor que `file_data` empiece por `data:` (`mini_panel_sales.py`).
2. `client.js` · `cxSalesOpenFile022G` (y su descarga): el mismo patrón que el hueco corregido,
   en el panel del cliente. No estaba en la lista de esta auditoría.
3. Validar `file_data` en el servidor (`data:` + tipo de imagen/PDF) cerraría 1 y 2 de raíz.

## 4. Validación de marca al guardar

`PUT /api/v1/companies/{id}/experience/branding` **y** `PUT /api/v1/companies/{id}/branding`
(escriben el mismo lugar; dejar uno abierto sería un atajo). Responde **400** con el motivo:

- `logo_url`: vacío, `https://…` o ruta propia `/…`. Nunca `javascript:`, `data:`, `http:`,
  `//otro-sitio`, ni comillas, `<`, `>`, `\` o espacios.
- Colores (`primary_color`, `secondary_color`, `background_color`, `text_color`,
  `gradient_*`, `color_*`, `card_color`, `button_color`, `success_color`, también dentro de
  `custom_css_json`): solo hex `#RGB` o `#RRGGBB`.
- `font_family` / `fontFamily`: solo `Inter, Manrope, Sora, Space Grotesk, Rajdhani,
  Orbitron, Poppins, Montserrat` (antes se cambiaba en silencio a Inter).
- `gradient_angle` / `gradientAngle`: número finito.

**Lo que ya está guardado no se rompe**: la lectura (`GET …/experience`, `GET …/branding`, la
marca de los paneles) no cambió; solo se rechaza al guardar.

**Atención:** el botón "Subir logo" de Admin V2 convierte la imagen en `data:` y la guarda en
`logo_url`. Con esta regla ese guardado **ahora responde 400**. Las URL `https://` y las rutas
propias siguen funcionando. El siguiente paso para subir logos es el bucket de objetos (no más
bytes en Postgres). Ver "Decisión pendiente" en el resumen al dueño.

**Cuántos valores guardados no cumplen:** no pude contarlos: la lectura de la base de
producción desde esta sesión está bloqueada. Para contarlos (solo lectura):

```
railway run -s Postgres py -3.11 scripts/consola_v2plus_preflight.py
```

## 5. Hallazgos de autenticación vistos al construir la Ficha (NO corregidos aquí)

Endpoints de `/api/v1` que la Consola v2+ usa con el mismo contrato que Admin V2 y que **no
exigen sesión** en el servidor (forman parte del barrido de ~360 endpoints abiertos):

- `company_modules.py`: `GET /companies/{id}/modules`, `POST /companies/{id}/modules/{code}/activate`
  y `/deactivate`. Cualquiera que conozca un `company_id` puede encender o apagar módulos de esa
  empresa, incluido `mini_panel` con su asignación.
- `packages.py`: `GET /packages`, `GET /packages/{id}` y `GET /packages/{id}/mini-panel-settings`.

Cerrarlos cambia permisos de endpoints existentes (regla 2 de esta fase), así que van al barrido.
