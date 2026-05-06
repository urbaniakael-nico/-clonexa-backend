PATCH: 015C-R6D Materials Return 500 Cast Fix

Files:
- app/api/v1/endpoints/materials.py

Purpose:
- Fix 500 on POST /api/v1/materials/companies/{company_id}/orders/{order_number}/return-selected
- Fix asyncpg AmbiguousParameterError inconsistent types text versus character varying.

Validation:
- python -m py_compile app/api/v1/endpoints/materials.py
- docker compose -p clonexa up --build -d
- curl /health
- Register selected return from /client -> Materiales.
