# CLONEXA 009E-R1 — Client Tenant by Company ID + UTF-8 Display Fix

## Qué corrige

- Admin V2 abre `/client` usando `company_id` real por empresa.
- `/client?company_id=<uuid>` carga la empresa indicada por URL y no depende de la última sesión/localStorage.
- Permite abrir varias pestañas de `/client` para empresas distintas sin pisarse entre sí.
- `/client` carga branding desde `/api/v1/companies/{company_id}/experience`.
- Admin V2 conserva textos en UTF-8 y evita mojibake visible.
- No toca auth, Acceso Maestro, backend sensible, migraciones ni Docker.

## Archivos modificados

- `app/web/admin_v2.js`
- `app/web/client.js`

## Aplicar

```powershell
cd "C:\Users\valef\OneDrive\Desktop\CLONEXA\clonexa_backend"

Expand-Archive -Path "$env:USERPROFILE\Downloads\clonexa_client_tenant_company_id_009e_r1.zip" -DestinationPath . -Force

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

## Validar en navegador

1. Abrir `http://localhost:8000/admin-v2`.
2. Ctrl + Shift + R.
3. Seleccionar Urbania y usar “Abrir /client”.
4. Confirmar URL: `/client?company_id=<urbania_id>`.
5. Seleccionar Voltage y usar “Abrir /client”.
6. Confirmar URL: `/client?company_id=<voltage_id>`.
7. Abrir ambas en pestañas distintas.
8. Confirmar que cada pestaña mantiene empresa, nombre y branding propios al refrescar.

## Criterio de aceptación

- Admin V2 sigue estable.
- Acceso Maestro sigue funcionando.
- Branding Studio sigue funcionando.
- CRM preview sigue funcionando.
- `/client?company_id=...` manda sobre cualquier última sesión.
- No aparecen caracteres corruptos visibles en Admin V2.
