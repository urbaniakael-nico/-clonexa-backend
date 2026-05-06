# PATCH MANIFEST — 016A-R2 KPIs Realtime True Data

Archivos:
- app/api/v1/endpoints/kpis.py
- app/web/client.js
- README_KPIS_REALTIME_TRUE_DATA_016A_R2.md

Validaciones realizadas:
- node --check app/web/client.js
- python -m py_compile app/api/v1/endpoints/kpis.py

Notas:
- El error de datos falsos venía de usar created_at de payroll_period_items como filtro principal.
- La fuente correcta para KPI de nómina es el cálculo vivo del módulo payroll y/o periodos cerrados por period_start/period_end.
