# CLONEXA 008G — Admin V2 Persistence Fix

Este patch corrige persistencia real en Admin Console V2:

- Crear empresa + Acceso Maestro guarda `company_users`.
- Crear Acceso Maestro en empresa existente guarda `company_users`.
- `created_at` y `updated_at` quedan poblados.
- Desactivar empresa persiste `status = inactive`.
- Eliminar / archivar empresa persiste `status = archived`.
- No hay hard delete físico.
- Admin V2 espera respuesta real del backend y muestra errores si un paso falla.

## Archivos incluidos

- `app/web/admin_v2.js`
- `app/services/auth_service.py`
- `app/api/v1/endpoints/company_users.py`
- `app/api/v1/endpoints/companies.py`
- `scripts/verify_admin_v2_persistence_008g.py`
- `README_ADMIN_V2_PERSISTENCE_FIX_008G.md`
- `PATCH_MANIFEST.md`

## Backup recomendado antes de aplicar

```powershell
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backup = "backup_admin_v2_persistence_008g_$stamp"
New-Item -ItemType Directory -Path $backup -Force
Copy-Item app\web\admin_v2.js $backup -Force
Copy-Item app\services\auth_service.py $backup -Force
Copy-Item app\api\v1\endpoints\company_users.py $backup -Force
Copy-Item app\api\v1\endpoints\companies.py $backup -Force
```

## Aplicar ZIP desde PowerShell

```powershell
cd "C:\Users\valef\OneDrive\Desktop\CLONEXA\clonexa_backend"

Expand-Archive -Path "$env:USERPROFILE\Downloads\clonexa_admin_v2_persistence_fix_008g.zip" -DestinationPath . -Force

Get-ChildItem -Path . -Recurse -Directory -Filter "__pycache__" |
  Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

docker compose -p clonexa up --build -d

Start-Sleep -Seconds 12

docker compose -p clonexa logs --tail=220 api
```

## Validar backend

```powershell
curl.exe http://127.0.0.1:8000/health
curl.exe http://127.0.0.1:8000/api/v1/companies
curl.exe http://127.0.0.1:8000/api/v1/packages
curl.exe http://127.0.0.1:8000/api/v1/modules
```

## Validar persistencia

```powershell
docker compose -p clonexa exec -T api sh -lc "PYTHONPATH=/app python scripts/verify_admin_v2_persistence_008g.py"
```

Resultado esperado:

```text
✅ OWNER ACCESS PERSISTENCE OK
✅ COMPANY STATUS INACTIVE OK
✅ COMPANY ARCHIVE OK
✅ ADMIN V2 PERSISTENCE 008G PASSED
```

## Validar UI

Abrir:

```text
http://localhost:8000/admin-v2
```

Presionar `Ctrl + F5`.

Prueba manual:

1. Crear empresa nueva con Acceso Maestro.
2. Confirmar que queda `Acceso Maestro: OK`.
3. Confirmar que aparece email del acceso.
4. Entrar por `/login` con email y contraseña temporal.
5. Crear empresa sin acceso, entrar a detalle y crear Acceso Maestro.
6. Confirmar que queda guardado.
7. Presionar Desactivar y refrescar; debe seguir `inactive`.
8. Presionar Eliminar / archivar y confirmar con slug.
9. Refrescar; debe quedar `archived` o desaparecer de vista activa.

## Qué NO toca

- No toca `/client`.
- No toca `/login`.
- No toca `/admin` clásico.
- No crea migraciones.
- No toca Dockerfile.
- No toca docker-compose.yml.
- No borra datos.
- No hace hard delete.
