# CLONEXA 010B-R2 — Asistencia como Bitácora Operativa

Objetivo:
- Reencuadrar Asistencia dentro de Workforce como bitácora operativa/auditoría.
- Quitar la vista tipo CRM de estado actual de empleados.
- Mantener Personal e Historial funcionando.
- Preparar datos para CRM, Nómina, KPIs, Materiales, GPS y Reportes.

Decisión:
- Asistencia = registros históricos de interacciones del personal.
- CRM Campo = operación en vivo.
- Nómina = cálculo.
- KPIs = indicadores.
- Materiales = gestión de solicitudes.
- Bots = canal de captura.

Archivos:
- app/web/client.js
- app/api/v1/endpoints/employees.py
- app/models/workforce_attendance.py
- app/schemas/workforce_attendance.py
- alembic/versions/010b_r2_asistencia_bitacora_operativa.py

Validación:
curl.exe "http://127.0.0.1:8000/api/v1/employees/attendance/history?company_id=76974191-1dc6-4eb4-9b19-7d1e9ad82946&limit=20"
