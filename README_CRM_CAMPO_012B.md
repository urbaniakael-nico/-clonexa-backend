# CLONEXA 012B — CRM Campo / Vista Operativa en Vivo

## Objetivo
Activar el módulo `crm` en `/client` como pantalla funcional independiente.

## Regla de módulo
- Solo aparece si `module_code = "crm"` está activo para la empresa.
- No captura datos.
- Lee eventos reales de Asistencia / Bot / Panel.
- No se mezcla con Workforce, Bots, Nómina, KPIs ni Materiales.

## Qué incluye
- Vista `/client -> CRM Campo`.
- KPIs operativos:
  - Trabajando
  - En pausa
  - Fuera de turno
  - Eventos hoy
- Estado por empleado:
  - Empleado
  - Rol
  - Estado
  - Última acción
  - Última interacción
  - Canal
- Feed operativo:
  - Fecha / hora
  - Empleado
  - Evento
  - Canal
  - Módulo
  - Detalle
- Alertas básicas:
  - Pausas largas
  - Bot no operativo

## Fuentes de datos
- `/api/v1/employees?company_id=<id>&include_archived=true`
- `/api/v1/employees/attendance/history?company_id=<id>&limit=150`
- `/api/v1/bots/companies/<id>/telegram`

## Archivos modificados
- `app/web/client.js`

## Validación
1. Activar `crm` para una empresa en Admin V2.
2. Abrir `/client?company_id=<id>`.
3. Confirmar que aparece CRM Campo.
4. Hacer clic en CRM Campo.
5. Ver datos reales alimentados por eventos del bot/bitácora.
6. Desactivar `crm`.
7. Confirmar que desaparece del panel cliente.
