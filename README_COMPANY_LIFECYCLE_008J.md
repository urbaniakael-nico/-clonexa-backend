# CLONEXA 008J — Company Lifecycle Fix

## Qué corrige

Este patch agrega persistencia real para el ciclo de vida de empresas desde Admin V2:

- Desactivar empresa: `status = inactive`
- Reactivar empresa: `status = active`
- Eliminar empresa: `status = archived`

**Eliminar no borra físicamente la empresa.** Es soft archive.

## Archivos modificados

- `app/api/v1/endpoints/companies.py`
- `app/web/admin_v2.js`

## Qué NO toca

- No toca migraciones.
- No toca Dockerfile.
- No toca docker-compose.yml.
- No toca auth.
- No toca Acceso Maestro.
- No toca `/client`.
- No toca `/login`.
- No toca Admin clásico.
- No hace hard delete.

## Aplicar

```powershell
cd "C:\Users\valef\OneDrive\Desktop\CLONEXA\clonexa_backend"

Expand-Archive -Path "$env:USERPROFILE\Downloads\clonexa_company_lifecycle_008j.zip" -DestinationPath . -Force

Get-ChildItem -Path . -Recurse -Directory -Filter "__pycache__" |
  Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

docker compose -p clonexa up --build -d
```

## Validar API

```powershell
curl.exe http://127.0.0.1:8000/health
curl.exe http://127.0.0.1:8000/api/v1/companies
curl.exe http://127.0.0.1:8000/api/v1/packages
curl.exe http://127.0.0.1:8000/api/v1/modules
```

## Validar status por curl

```powershell
$companyId = "<ID_DE_EMPRESA_DE_PRUEBA>"

$payload = @{ status = "inactive" } | ConvertTo-Json
curl.exe -i -X PATCH "http://127.0.0.1:8000/api/v1/companies/$companyId/status" `
  -H "Content-Type: application/json" `
  --data-binary $payload

$payload = @{ status = "active" } | ConvertTo-Json
curl.exe -i -X PATCH "http://127.0.0.1:8000/api/v1/companies/$companyId/status" `
  -H "Content-Type: application/json" `
  --data-binary $payload

curl.exe -i -X PATCH "http://127.0.0.1:8000/api/v1/companies/$companyId/archive"

curl.exe -i -X PATCH "http://127.0.0.1:8000/api/v1/companies/$companyId/restore"
```

## Validar desde Admin V2

Abrir:

```text
http://localhost:8000/admin-v2
```

Pruebas:

1. Selecciona una empresa de prueba.
2. Click **Desactivar**.
3. Refresca navegador.
4. Debe seguir `inactive`.
5. Click **Reactivar**.
6. Debe volver a `active`.
7. Click **Eliminar / archivar**.
8. Escribe el slug exacto.
9. Debe quedar `archived`.
10. Cambia filtro a **Archivadas**.
11. Debe verse la empresa archivada.
12. Reactivar debe devolverla a la lista principal.

## Nota de producto

`DELETE /api/v1/companies/{company_id}` también se comporta como soft archive para evitar pérdida física de datos.
