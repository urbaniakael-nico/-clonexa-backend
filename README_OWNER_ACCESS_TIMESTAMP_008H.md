# CLONEXA 008H — Owner Access Timestamp Surgical Fix

## Problema corregido

La creación de Acceso Maestro fallaba con error de integridad porque `company_users.created_at` y `company_users.updated_at` llegaban como `NULL`.

Este patch modifica únicamente `create_company_user` para asignar timestamps UTC antes del `commit`.

## Archivos incluidos

- `app/services/auth_service.py`
- `scripts/verify_owner_access_timestamp_008h.py`
- `README_OWNER_ACCESS_TIMESTAMP_008H.md`
- `PATCH_MANIFEST.md`

## Qué NO toca

- Migraciones
- Dockerfile
- docker-compose.yml
- Login visual
- Client Portal
- Admin V2 visual
- Admin clásico
- Field Engine
- CRM Builder
- Flujo de archive/delete

## Aplicar

```powershell
cd "C:\Users\valef\OneDrive\Desktop\CLONEXA\clonexa_backend"

Expand-Archive -Path "$env:USERPROFILE\Downloads\clonexa_owner_access_timestamp_fix_008h.zip" -DestinationPath . -Force

Get-ChildItem -Path . -Recurse -Directory -Filter "__pycache__" |
  Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

docker compose -p clonexa up --build -d
```

## Validar backend

```powershell
Start-Sleep -Seconds 15

docker compose -p clonexa logs --tail=220 api

curl.exe http://127.0.0.1:8000/health
curl.exe http://127.0.0.1:8000/api/v1/companies
```

## Ejecutar verificación

```powershell
docker compose -p clonexa exec api python scripts/verify_owner_access_timestamp_008h.py
```

Resultado esperado:

```text
✅ OWNER ACCESS CREATED
✅ TIMESTAMPS OK
✅ PASSWORD HASH OK
✅ OWNER ACCESS TIMESTAMP 008H PASSED
```

## Prueba manual

1. Abrir `http://localhost:8000/admin-v2`.
2. Presionar `Ctrl + F5`.
3. Seleccionar una empresa sin Acceso Maestro.
4. Crear Acceso Maestro con nombre, email y contraseña temporal.
5. Confirmar que cambia a `Acceso Maestro: OK`.
6. Refrescar navegador.
7. Confirmar que sigue guardado.
8. Abrir `http://localhost:8000/login`.
9. Entrar con email y contraseña temporal.
10. Confirmar que login acepta el acceso o exige cambio de clave.
