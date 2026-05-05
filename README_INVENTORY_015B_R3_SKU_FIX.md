# CLONEXA 015B-R3 Inventory SKU Fix

Corrige el 500 de Inventario causado por columnas legacy NOT NULL (`sku`) creadas por migraciones anteriores.

- Mantiene stock actual como solo lectura.
- Crea `sku/name/reference` con el mismo valor de `name_reference` para compatibilidad.
- Relaja NOT NULL legacy en columnas heredadas de inventario.
- No toca frontend, bot, CRM, materiales ni nómina.
