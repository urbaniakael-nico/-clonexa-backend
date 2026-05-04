# CLONEXA 013-R1 — Payroll Periods / Historial de Nómina

Este patch convierte Nómina en módulo histórico consultable.

## Incluye

- `/client → Nómina` con:
  - cálculo de periodo abierto
  - cierre de periodo
  - historial de nóminas cerradas
  - consulta de nóminas antiguas
  - CSV por periodo
- Backend `/api/v1/payroll/...`
- Tablas seguras creadas bajo demanda:
  - `payroll_periods`
  - `payroll_period_items`

## Regla

- Workforce entrega empleados, tarifas y descuentos.
- Bot/Asistencia entrega turnos cerrados.
- Nómina calcula y congela cortes.
- Descuento 1 + Descuento 2 se aplica una sola vez por corte.
- Una nómina cerrada no se recalcula aunque después cambien tarifas o descuentos.
