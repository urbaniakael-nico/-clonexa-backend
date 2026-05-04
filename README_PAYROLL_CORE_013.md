# CLONEXA 013 — Nómina Base / Payroll Core

## Objetivo
Crear el módulo cliente `/client → Nómina` enlazado al `module_code = payroll`.

## Alcance
- Frontend operativo en `app/web/client.js`.
- Solo aparece si el módulo `payroll` está activo para la empresa.
- Lee empleados desde Workforce / Personal.
- Lee turnos cerrados desde Asistencia / Bot.
- Calcula ordinarias, extras, bruto, descuentos de corte y total estimado.
- Exporta CSV.

## Reglas aplicadas
- Nómina no captura datos: consume datos de Workforce, Bot y Asistencia.
- Descuento 1 y Descuento 2 se aplican una sola vez por corte por colaborador.
- Core sigue oculto como módulo operativo.
- No toca Admin V2.
- No toca backend.
- No toca base de datos ni migraciones.

## Validación
- `node --check app/web/client.js`
- `/health`
- Activar módulo `payroll` en Admin V2.
- Abrir `/client?company_id=<id>`.
- Click en Nómina.
