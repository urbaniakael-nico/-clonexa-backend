# CLONEXA — Admin V2 Dashboard Binding Fix 008J-R3

## Qué corrige

Micro-patch frontend para que Admin Console V2 vuelva a pintar correctamente:

- Cards superiores del dashboard.
- Estado API inferior.
- Última actualización.
- Refresh después de desactivar/reactivar/archivar.

El backend 008J ya funciona. Este patch no toca backend.

## Archivos incluidos

- `app/web/admin_v2.js`
- `README_ADMIN_V2_DASHBOARD_BINDING_FIX_008J_R3.md`
- `PATCH_MANIFEST.md`

## Qué NO toca

- Backend
- `companies.py`
- `auth_service.py`
- `company_users.py`
- Migraciones
- Dockerfile
- docker-compose
- CSS
- `/client`
- `/login`
- `/admin` clásico

## Aplicación

```powershell
cd "C:\Users\valef\OneDrive\Desktop\CLONEXA\clonexa_backend"

Expand-Archive -Path "$env:USERPROFILE\Downloads\clonexa_admin_v2_dashboard_binding_fix_008j_r3.zip" -DestinationPath . -Force

Get-ChildItem -Path . -Recurse -Directory -Filter "__pycache__" |
  Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

docker compose -p clonexa up --build -d
```

## Validación API

```powershell
curl.exe http://127.0.0.1:8000/health
curl.exe http://127.0.0.1:8000/api/v1/companies
curl.exe http://127.0.0.1:8000/api/v1/packages
curl.exe http://127.0.0.1:8000/api/v1/modules
```

## Validación visual

Abrir:

```text
http://localhost:8000/admin-v2
```

Presionar `Ctrl + Shift + R`.

Resultado esperado:

- Dashboard ya no muestra `—`.
- Empresas muestra cantidad real.
- Paquetes muestra cantidad real.
- Módulos muestra cantidad real.
- Activas muestra cantidad real.
- API muestra `LIVE`.
- Refresh muestra hora local.
- Estado inferior muestra:
  - `ESTADO API`
  - `LIVE`
  - `Última actualización HH:MM:SS`

Los 404 de logo/favion no bloquean el panel.

## Acciones conservadas

- Desactivar empresa sigue llamando `PATCH /api/v1/companies/{id}/status`.
- Reactivar empresa sigue llamando `PATCH /api/v1/companies/{id}/status`.
- Archivar empresa sigue llamando `PATCH /api/v1/companies/{id}/archive`.
- Acceso Maestro no se modifica.
