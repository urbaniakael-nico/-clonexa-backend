# CLONEXA 011A3-R2 — Telegram Multi-Bot Stable Listener

Objetivo:
- Evitar que un bot de una empresa interrumpa el listener de otro bot.
- Evitar deadlocks por polling inmediato/concurrente.
- Mantener un listener independiente por company_id.
- Mantener offset de Telegram por empresa en config_json.
- Relevantar automáticamente los bots activos al reiniciar API.

Archivos incluidos:
- app/api/v1/endpoints/bots.py
- app/main.py

Cambios clave:
- Lock por company_id para serializar getUpdates por bot.
- Errores transitorios no desactivan el bot.
- Se elimina poll inmediato dentro del endpoint Iniciar escucha.
- El listener procesa en su propio ciclo.
- bootstrap_telegram_listeners() levanta listeners con listener_enabled=true al startup.
- Desactivar bot solo apaga ese bot, no afecta los demás.

No incluye:
- Migraciones.
- Cambios en /client.
- Cambios en Admin V2.
- Cambios en tokens.
