# CLONEXA 011A3-R3 — Bot Listener Commit/Offset + Menú sin saludo repetido

Corrige:
- Persistencia inmediata de cambios de turno antes de responder al usuario.
- Offset de Telegram avanzado por cada update para evitar reprocesar callbacks viejos.
- Un fallo de un update no detiene el listener completo.
- El bot no saluda en cada acción; saluda solo en /start, /whoami o selección inicial de idioma.
- Después de cada acción muestra solo el siguiente menú lógico.
- Reduce spam: no envía mensaje adicional de “procesando” en cada tap; mantiene chat action.
