# CLONEXA 015B-R1 — Inventory Create/List 500 Hotfix

Corrige el 500 en `/api/v1/inventory/companies/{company_id}/items`.

Causa cubierta:
- Evita depender de `gen_random_uuid()` en PostgreSQL.
- Genera UUID desde Python para `inventory_items` e `inventory_movements`.
- No borra datos.
- No toca Bot, Materiales, CRM, Workforce ni Admin V2.
