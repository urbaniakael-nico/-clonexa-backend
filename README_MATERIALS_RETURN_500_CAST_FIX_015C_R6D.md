# CLONEXA 015C-R6D — Materials Return 500 Cast Fix

Corrige el 500 al registrar devolución seleccionada.

Causa real:
PostgreSQL/asyncpg marcaba `AmbiguousParameterError` porque el parámetro `:status`
se usaba al mismo tiempo para actualizar una columna `varchar` y compararse contra
un literal `text` dentro de un CASE.

Cambio:
- En `return_selected_material_units`, el UPDATE de `material_requests` castea:
  - `CAST(:status AS varchar)`
  - `CAST(:return_note AS text)`

No toca:
- Web App Telegram
- Bot
- Inventario
- Admin V2
- Client UI salvo consumo existente
