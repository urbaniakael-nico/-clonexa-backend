# PATCH MANIFEST — CLONEXA 015B-R4 INVENTORY MOVEMENTS QUANTITY FIX

Files:
- app/api/v1/endpoints/inventory.py
- README_INVENTORY_015B_R4_MOVEMENTS_QUANTITY_FIX.md

Purpose:
- Fix inventory create 500 caused by legacy inventory_movements.quantity NOT NULL.
- Insert both quantity_delta and quantity.
- Normalize/drop legacy movement NOT NULL constraints defensively.
