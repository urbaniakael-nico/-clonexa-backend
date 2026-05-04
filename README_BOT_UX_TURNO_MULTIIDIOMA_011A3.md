# CLONEXA 011A3 — Bot UX + Turno Core + Multiidioma

## Objetivo

Mejorar el bot Telegram sin romper el flujo multiempresa ya funcionando.

Incluye:

- Selector de idioma: Español / English / Français.
- Menú con botones inline en Telegram.
- Flujo obligatorio de turno para todos los bots:
  - Iniciar turno
  - Pausa
  - Retomar labores
  - Finalizar turno
  - Estado
- Pausas marcadas como tiempo no pagable.
- Opciones dinámicas según módulos activos:
  - materials -> Solicitar material
  - gps -> Ubicación
  - field -> Tarea
  - production -> Producción
  - sales/retail -> Venta
- Mensaje de procesamiento si el bot tarda.
- Eventos siguen cayendo en Asistencia / Bitácora.
- Admin V2 no se satura con eventos operativos.

## Reglas implementadas

- Todo empleado debe iniciar turno antes de ejecutar acciones operativas.
- En pausa solo puede retomar labores o finalizar turno.
- Pausa y retomar no suman como tiempo pagable.
- Los módulos extra no reemplazan el turno; se agregan dentro del turno.
- Si un módulo no está activo para la empresa, el bot bloquea esa acción.
- Comandos siguen funcionando como respaldo.

## Comandos compatibles

- /start
- /whoami
- /idioma
- /entrada
- /inicio_turno
- /pausa
- /reanudar
- /retomar
- /salida
- /finalizar_turno
- /observacion texto
- /material texto
- /ubicacion
- /tarea
- /produccion
- /venta texto
- /estado

## Archivos incluidos

- app/api/v1/endpoints/bots.py
- alembic/versions/011a3_bot_ux_turno_multiidioma.py
