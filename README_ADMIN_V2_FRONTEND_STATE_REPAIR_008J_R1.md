# CLONEXA 008J-R1 — Admin V2 Frontend State Repair

## Qué corrige

Este micro-patch corrige únicamente el estado/render frontend de `Admin Console V2`.

Problema corregido:

- Cards del dashboard en `—`.
- Estado inferior en `Verificando`.
- Hora en `Sin actualizar`.
- La API respondía 200, pero `admin_v2.js` no actualizaba estado global ni renderizaba datos.

## Archivos incluidos

```text
app/web/admin_v2.js
README_ADMIN_V2_FRONTEND_STATE_REPAIR_008J_R1.md
PATCH_MANIFEST.md
```

## Qué NO toca

```text
backend
companies.py
auth_service.py
company_users.py
migrations
Dockerfile
docker-compose.yml
client
login
admin viejo
CSS
```

## Aplicar en PowerShell

```powershell
cd "C:\Users\valef\OneDrive\Desktop\CLONEXA\clonexa_backend"

Expand-Archive -Path "$env:USERPROFILE\Downloads\clonexa_admin_v2_frontend_state_repair_008j_r1.zip" -DestinationPath . -Force

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

## Validar visual

Abrir:

```text
http://localhost:8000/admin-v2
```

Presionar `Ctrl + F5`.

Resultado esperado:

```text
Dashboard muestra números reales.
Empresas > 0.
Paquetes > 0.
Módulos > 0.
API = LIVE.
Última actualización = hora local.
Estado inferior no queda en Verificando.
```

## Validar lifecycle

Desde Admin V2:

```text
Desactivar empresa -> PATCH /api/v1/companies/{id}/status 200
Reactivar empresa -> PATCH /api/v1/companies/{id}/status 200
Eliminar / archivar -> PATCH /api/v1/companies/{id}/archive 200
```

No hace hard delete.
