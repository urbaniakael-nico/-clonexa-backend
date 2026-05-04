# CLONEXA 013-R2 — Payroll Close Fix + Bot Corte Acumulado

Incluye:
- Fix de payroll_periods/payroll_period_items cuando la tabla ya existía incompleta.
- Evita error `column period_start does not exist`.
- El bot al cerrar turno muestra acumulado del corte/quincena, no solo la jornada.
- El descuento del corte se aplica una sola vez al acumulado.
- Reduce deadlocks del listener Telegram evitando updates constantes de `company_bot_instances` cuando no hay mensajes.

Archivos:
- app/api/v1/endpoints/payroll.py
- app/api/v1/endpoints/bots.py
