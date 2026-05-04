# CLONEXA 013-R3 — PAYROLL CLOSE FINAL FIX

## Objetivo
Corregir el 500 al cerrar periodo de nómina.

## Causa confirmada
La tabla `payroll_periods` ya existía parcialmente y tenía columna `id` NOT NULL sin DEFAULT.
El INSERT no enviaba `id`, por eso PostgreSQL rechazaba el cierre:

`null value in column "id" of relation "payroll_periods" violates not-null constraint`

## Cambios
- `app/api/v1/endpoints/payroll.py`
  - Asegura DEFAULT `gen_random_uuid()` en `payroll_periods.id`.
  - Asegura DEFAULT `gen_random_uuid()` en `payroll_period_items.id`.
  - En cierre de periodo genera UUID explícito para `payroll_periods.id`.
  - En items de periodo genera UUID explícito para `payroll_period_items.id`.
  - No toca Bot, CRM, Workforce ni client.js.

## Validación esperada
- `/health` responde OK.
- Nómina calcula periodo.
- Cerrar periodo no genera 500.
- La nómina cerrada aparece en historial.
