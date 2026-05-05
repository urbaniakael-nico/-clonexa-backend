# CLONEXA 015B-R4 Inventory Movements Quantity Fix

Corrige el 500 al crear inventario causado por columna legacy `inventory_movements.quantity NOT NULL`.

- Mantiene `quantity_delta` como campo operativo nuevo.
- Agrega/actualiza `quantity` para compatibilidad legacy.
- Relaja NOT NULL de columnas legacy de movimientos.
- No toca frontend, bots, CRM, materiales ni nómina.
