# CLONEXA 015C-R5 — Telegram Web App Material Cart

PUBLIC_BASE_URL aplicado para pruebas:

https://reported-papers-catalogue-vii.trycloudflare.com

## Cambios
- Bot deja de usar callbacks para selección de materiales.
- Bot envía botón Telegram Web App: "Abrir inventario".
- Web App `/webapp/materials` lista inventario real.
- Buscador por nombre/referencia/tamaño.
- Cantidad por material.
- Carrito visual.
- Confirmación crea orden MAT-... en Materiales.
- Inventario NO se descuenta al confirmar. Se descuenta al Entregar desde Materiales.

## Archivos
- app/api/v1/endpoints/bots.py
- app/api/v1/endpoints/materials_webapp.py
- app/api/v1/router.py
- app/main.py
- app/web/materials_webapp.html
- app/web/materials_webapp_routes.py
