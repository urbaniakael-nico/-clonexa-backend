# CLONEXA AUTH PASSWORD FIX 007

Microfix para estabilizar el flujo de contraseñas de usuarios por empresa.

## Incluye

- Servicio de hashing/verificación consistente.
- Login con control de intentos fallidos.
- Bloqueo temporal por 15 minutos al quinto intento fallido.
- Reset password desde Admin/API.
- Cambio obligatorio de contraseña.
- Unlock de usuario.
- Seed idempotente de usuarios demo.
- Script de verificación real del flujo.

## Aplicar

```powershell
cd C:\Users\valef\OneDrive\Desktop\CLONEXA\clonexa_backend
unzip clonexa_auth_password_fix_007.zip -d .
docker compose -p clonexa down
docker compose -p clonexa up --build -d
```

## Validar

```powershell
docker compose -p clonexa exec -T api python scripts/verify_auth_password_flow.py
```

Resultado esperado:

```text
CLONEXA AUTH PASSWORD FLOW CHECK
company: Voltage
user: admin@voltage.com
reset password: OK
temporary login: OK
change password: OK
old password rejected: OK
new password accepted: OK
restore dev password: OK
unlock user: OK
status: OK
```

## Login manual restaurado

Después del script, el usuario queda con la contraseña de desarrollo:

```text
admin@voltage.com
Clonexa2026!Voltage
```

## Endpoints validados

```text
POST /api/v1/auth/login
GET  /api/v1/auth/me
POST /api/v1/auth/change-password
POST /api/v1/companies/{company_id}/users/{user_id}/reset-password
POST /api/v1/companies/{company_id}/users/{user_id}/unlock
```

No incluye migraciones, cambios visuales ni cambios al Field Engine.
