# CLONEXA 011A3-R4 — Bot cierre limpio + datos para Nómina

Corrige el mensaje de cierre de turno del bot:

- No muestra operaciones matemáticas.
- No muestra fórmula ni desglose técnico al trabajador.
- Muestra: feliz descanso, horas ordinarias, horas extra, proyección pago, descuento del corte y total estimado.
- Toma valores desde Workforce/Personal:
  - hourly_rate_regular
  - hourly_rate_extra
  - deduction_1
  - deduction_2
- Los descuentos se tratan como descuento del corte/periodo, no como descuento por jornada.
- Guarda payload estructurado `payroll_projection` en el evento `check_out` para preparar el módulo Nómina.

Archivos:
- app/api/v1/endpoints/bots.py
