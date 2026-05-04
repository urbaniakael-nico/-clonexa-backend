# CLONEXA 011A-0 — Admin V2 Telegram Bot Token Config

Objetivo:
- Agregar en Admin V2 → Empresa → Accesos una tarjeta "Bot Telegram".
- Guardar token de Telegram por company_id.
- Probar conexión contra Telegram getMe.
- Mostrar token siempre enmascarado.
- Preparar la empresa para captura real de eventos por bot.

Incluye:
- app/web/admin_v2.js
- app/api/v1/endpoints/bots.py
- app/models/company_bot_instance.py
- app/models/__init__.py
- app/schemas/bot.py
- alembic/versions/011a0_company_bot_instances.py

Reglas:
- No toca /client.
- No toca Personal, Historial ni Asistencia.
- No toca Admin V2 fuera del tab Accesos.
- No expone el token completo al frontend.
- El token queda asociado a company_id y channel=telegram.

Validación:
1. /health responde.
2. Admin V2 abre.
3. Empresa → Accesos muestra Bot Telegram.
4. Guardar token funciona.
5. Probar conexión valida getMe.
6. Al refrescar, el token sale enmascarado.
