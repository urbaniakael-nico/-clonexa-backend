# CLONEXA 011A-2 — Bot Telegram Auto Listener

## Objetivo

Eliminar la dependencia de PowerShell para leer mensajes del bot de Telegram.

## Resultado

Admin V2 → Empresa → Accesos → Bot Telegram queda con:

- Guardar token
- Probar conexión
- Iniciar escucha
- Desactivar bot

## Reglas respetadas

- Admin V2 solo configura estado técnico del bot.
- No se muestran últimos mensajes ni últimos eventos en Admin V2.
- Desactivar bot apaga la operación del bot y cancela la escucha.
- Los eventos siguen llegando a Workforce → Asistencia / Bitácora.
- No se toca /client ni Personal/Historial/Asistencia.
- No se exponen tokens.

## Endpoints agregados

POST /api/v1/bots/companies/{company_id}/telegram/listener/start

## Endpoint existente conservado

POST /api/v1/bots/companies/{company_id}/telegram/poll

Se mantiene como diagnóstico interno/manual, no como operación normal.

## Validación esperada

1. Admin V2 → Empresa → Accesos.
2. Bot Telegram conectado.
3. Clic en Iniciar escucha.
4. Enviar /entrada desde Telegram.
5. El evento aparece en /client → Personal → Asistencia.
