# CLONEXA 011A3-R1 — Bot UX Flow Fix

Corrige el flujo del bot Telegram:

- El menú ahora es lógico por estado del turno.
- Sin texto "también puedes escribir comandos".
- Sin botón Estado.
- Sin botón Venta.
- Selector de idioma evita spam si se oprime muchas veces.
- Si el idioma ya estaba configurado, no vuelve a duplicar menú.
- Sin turno: solo Iniciar turno + Idioma.
- Trabajando: Pausa + Finalizar turno + opciones internas activas que encajan.
- En pausa: Retomar labores + Finalizar turno + Idioma.
- Al finalizar turno muestra resumen de horas:
  - tiempo bruto
  - pausas no pagables
  - tiempo pagable
  - horas ordinarias
  - horas extra
  - valor acumulado según tarifas del empleado.

No toca Admin V2, módulos, token, listeners ni configuración de empresas.
