CLONEXA 012A — CLIENT BOTS MINIMAL MODULE + MODULE VISIBILITY FIX

Cambios:
- /client muestra solo módulos activos visibles por empresa.
- core/Núcleo queda oculto en /client como módulo operativo.
- Personal y botón Agregar personal solo aparecen si workforce está activo.
- Bots queda vinculado por module_code=bots + company_id.
- /client → Bots muestra estado, canal, usuario Telegram y nombre interno editable.
- El cliente no ve token, logs, mensajes, eventos ni configuración técnica.

Validación:
- Desactivar workforce en Admin V2 debe ocultar Personal y Agregar personal en /client.
- Activar bots debe mostrar tarjeta Bots.
- Click en Bots debe abrir módulo minimal.
- Guardar nombre debe actualizar company_bot_instances.name.
