# CLONEXA 013-R2 — Payroll Period Close Hotfix

Corrige error 500 al cerrar periodo de nómina.

Incluye:
- Serialización segura de UUID, Decimal, fechas, jsonb y listas.
- Validación segura de employee_id antes de insertar payroll_period_items.
- Parámetros numéricos enviados de forma segura a PostgreSQL.
- Reconsulta de periodo cerrado con UUID normalizado.

No toca:
- client.js
- Admin V2
- Bots
- CRM
- Workforce
- Base de datos existente
