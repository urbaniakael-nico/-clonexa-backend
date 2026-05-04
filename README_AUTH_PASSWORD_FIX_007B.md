# CLONEXA Auth Password Fix 007B

Microfix para estabilizar hash, reset y cambio de contraseña.

## Aplicar

```powershell
cd C:\Users\valef\OneDrive\Desktop\CLONEXA\clonexa_backend
unzip clonexa_auth_password_fix_007b.zip -d .
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
company slug: voltage
user: admin@voltage.com
reset password: OK
temporary login: OK
change password: OK
old password rejected: OK
new password accepted: OK
restore dev password: OK
status: OK
```

El script deja restaurado el login local:

```text
admin@voltage.com
Clonexa2026!Voltage
```

## Alcance

- Corrige `hash_password`.
- Corrige `verify_password`.
- Impide usar hashes como contraseña plana.
- Impide passwords bcrypt mayores a 72 bytes sin truncar silenciosamente.
- Corrige reset para devolver solo contraseña temporal limpia.
- Corrige change-password para guardar hash nuevo y limpiar bloqueo.
- No toca migraciones, visuales, Field Engine ni CRM Builder.
