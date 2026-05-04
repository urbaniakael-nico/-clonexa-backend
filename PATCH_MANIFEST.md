PATCH: 010B-R2 ASISTENCIA COMO BITÁCORA OPERATIVA

Incluye:
- client.js: cambia Asistencia de CRM/estado actual a bitácora filtrable.
- employees.py: extiende attendance/history como bitácora operativa con filtros.
- employees.py: agrega POST /api/v1/employees/attendance/events para captura desde bot/panel/QR.
- workforce_attendance.py: extiende modelo de eventos.
- workforce_attendance.py schema: extiende salida de evento.
- Alembic: agrega columnas de bitácora sin borrar datos.

No toca:
- Admin V2
- Login
- Paquetes
- Módulos SaaS
- Personal base
- Historial administrativo
