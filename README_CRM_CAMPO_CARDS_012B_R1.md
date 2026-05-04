# CLONEXA 012B-R1 — CRM Campo Cards Operativas

## Objetivo

Corrige CRM Campo para que sea una vista operativa en vivo, sin tabla, sin buscador, sin feed de eventos.

## Cambios

- Cards superiores:
  - Activos
  - En pausa
  - Nucleo/modulo asignado 1
  - Nucleo/modulo asignado 2
- Tarjetas por colaborador:
  - Nombre
  - Estado
  - Cronometro de labor / funcion
  - Campo modulo 1
  - Campo modulo 2
- Corrige calculo de estado:
  - check_in / break_end = Activo
  - break_start = En pausa
  - check_out = Fuera de turno
- El tipo de evento manda sobre el status del registro para evitar inconsistencias.
- El CRM no captura datos; lee eventos reales de Asistencia/Bot.

## Archivos

- app/web/client.js
