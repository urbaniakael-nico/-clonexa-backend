# CLONEXA 009C — Branding Studio funcional

Este patch convierte la pestaña **Branding** de Admin V2 en un Branding Studio visual real:

- Paletas visuales clicables.
- Editor de colores con `input type=color` + HEX sincronizado.
- Fondos tornasol / futuristas en CSS.
- Vista previa viva del panel cliente.
- Modal “Ver así quedará”.
- CRM / Panel Empresa con preview visual aplicada.
- Defaults por empresa/engine para empresas existentes y nuevas.

## Archivos incluidos

- `app/web/admin_v2.js`
- `app/web/admin_v2.css`
- `README_BRANDING_STUDIO_FUNCTIONAL_009C.md`
- `PATCH_MANIFEST.md`

## Qué NO toca

- `auth_service.py`
- `company_users.py`
- `/client`
- `/login`
- migraciones
- Dockerfile
- docker-compose.yml
- requirements.txt

## Aplicar

```powershell
cd "C:\Users\valef\OneDrive\Desktop\CLONEXA\clonexa_backend"

Expand-Archive -Path "$env:USERPROFILE\Downloads\clonexa_branding_studio_functional_009c.zip" -DestinationPath . -Force

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

1. Abrir `http://localhost:8000/admin-v2`.
2. Presionar `Ctrl + Shift + R`.
3. Ir a `Empresas`.
4. Seleccionar una empresa.
5. Abrir tab `Branding`.
6. Verificar que ya no aparece formulario plano.
7. Seleccionar `Tornasol Futurista`.
8. Cambiar colores con los pickers.
9. Seleccionar un fondo holográfico/tornasol.
10. Click `Ver así quedará`.
11. Guardar branding.
12. Refrescar.
13. Abrir tab `CRM`.
14. Confirmar preview visual aplicada.

## Endpoints usados

Primario:
- `GET /api/v1/companies/{company_id}/experience`
- `PUT /api/v1/companies/{company_id}/experience/branding`

Fallback:
- `PUT /api/v1/companies/{company_id}/branding`

Si el backend no persiste branding todavía, la UI mostrará preview local y reportará error al guardar.
