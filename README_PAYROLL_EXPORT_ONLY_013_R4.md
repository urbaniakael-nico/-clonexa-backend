# CLONEXA 013-R4 — Payroll Export Only

Objetivo:
- Quitar cierre/guardado de periodo desde /client → Nómina.
- Evitar el error 500 causado por el endpoint de cierre.
- Mantener cálculo de periodo y exportación CSV como cierre operativo.
- No tocar backend, bots, CRM ni Workforce.

Resultado:
- /client → Nómina muestra Calcular periodo y Exportar CSV.
- No aparece Cerrar periodo.
- No aparece Nóminas cerradas.
- El cliente guarda el corte exportando CSV.
