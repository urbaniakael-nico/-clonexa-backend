# CLONEXA 015B-R2 — INVENTORY 500 FINAL FIX

Corrige el 500 de Inventario causado por una tabla local `inventory_items` creada por un patch anterior sin la columna `name_reference`.

## Corrige
- GET `/api/v1/inventory/companies/{company_id}/items` sin 500.
- POST crear material sin 500.
- Tabla incompleta se auto-normaliza sin borrar datos.
- Acepta payload actual `name_reference` / `min_stock`.
- Acepta payload legacy `name` / `reference` / `minimum_stock`.
- Stock actual sigue siendo solo lectura.
- Entradas siguen creando movimiento.
