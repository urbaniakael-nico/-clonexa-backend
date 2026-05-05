# CLONEXA 014A — GPS Bot Gate

Objetivo:
- Si el módulo GPS está activo para una empresa, el bot exige ubicación real de Telegram antes de iniciar turno.
- Si GPS no está activo, el flujo de turno sigue igual.
- No toca CRM, Nómina, Workforce, Admin V2 ni client.js.

Cambio principal:
- app/api/v1/endpoints/bots.py

Reglas:
- module_code = gps activo => /entrada queda pendiente hasta recibir location.
- La ubicación se registra como evento gps_location con latitude/longitude.
- Después de recibir ubicación, se registra check_in.
- La solicitud pendiente se guarda por company_id + telegram_user_id.
- Si GPS está inactivo, no se pide ubicación.

Validación:
1. Activar GPS para la empresa desde Admin V2.
2. En Telegram tocar Iniciar turno.
3. El bot debe pedir compartir ubicación.
4. Compartir ubicación.
5. El bot debe iniciar turno con GPS validado.
6. Desactivar GPS y probar otra empresa: debe iniciar turno normal.
