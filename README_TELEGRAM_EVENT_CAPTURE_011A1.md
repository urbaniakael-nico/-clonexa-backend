# CLONEXA 011A-1 — Telegram Bot Event Capture MVP

## Objetivo

Capturar mensajes reales desde Telegram usando el token configurado en Admin V2 y convertirlos en eventos operativos visibles en:

`/client → Personal → Asistencia`

## Alcance

- No toca Admin V2 visual.
- No toca Personal.
- No toca Historial.
- No crea CRM.
- No crea Materiales.
- Usa el módulo Bots para capturar.
- Usa Asistencia como bitácora operativa.
- Aísla todo por `company_id`.

## Endpoint nuevo

```text
POST /api/v1/bots/companies/{company_id}/telegram/poll
```

Este endpoint usa `getUpdates` de Telegram. Es ideal para local porque `localhost` no puede recibir webhooks públicos sin túnel.

## Comandos soportados

```text
/start
/whoami
/entrada
/pausa
/reanudar
/salida
/observacion texto
/material texto
/estado
```

## Flujo de prueba

1. En Telegram, abre el bot configurado en Admin V2.
2. Escribe `/whoami`.
3. Copia el Telegram ID que responde.
4. En `/client → Personal`, pega ese ID en la columna Telegram ID del empleado.
5. Guarda.
6. En Telegram escribe `/entrada`.
7. Ejecuta el polling:

```powershell
$CompanyId = "cbb61ef8-2f1a-4b3b-8bb1-2a6297de987c"
curl.exe -X POST "http://127.0.0.1:8000/api/v1/bots/companies/$CompanyId/telegram/poll?limit=20&send_replies=true"
```

8. Abre `/client → Personal → Asistencia`.
9. Debe aparecer el evento.

## Loop local opcional

```powershell
$CompanyId = "cbb61ef8-2f1a-4b3b-8bb1-2a6297de987c"
while ($true) {
  curl.exe -X POST "http://127.0.0.1:8000/api/v1/bots/companies/$CompanyId/telegram/poll?limit=20&send_replies=true"
  Start-Sleep -Seconds 3
}
```

## Resultado esperado

Telegram → Bot CLONEXA → Empleado por Telegram ID → Evento operativo → Asistencia / Bitácora.

## Notas

- El token no se imprime ni se expone.
- El offset de Telegram se guarda en `company_bot_instances.config_json.telegram_update_offset`.
- Si un empleado no está vinculado, el bot responde con su Telegram ID.
- `/material texto` se registra como `module_code=materials`.
- `/observacion texto` se registra como evento operativo de Workforce.
