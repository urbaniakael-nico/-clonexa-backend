# CLONEXA 009D — Branding Persistence + CRM Apply Fix

## Qué corrige

Este patch agrega persistencia real para el Branding Studio cuando el frontend llama:

- `GET /api/v1/companies/{company_id}/experience`
- `PUT /api/v1/companies/{company_id}/experience/branding`

También mantiene endpoints fallback:

- `GET /api/v1/companies/{company_id}/branding`
- `PUT /api/v1/companies/{company_id}/branding`

El objetivo es corregir el error:

```text
No se pudo guardar branding: Not Found
```

## Archivos incluidos

```text
app/api/v1/endpoints/companies.py
README_BRANDING_PERSISTENCE_009D.md
PATCH_MANIFEST.md
```

## Qué NO toca

- `auth_service.py`
- `company_users.py`
- Acceso Maestro
- Login
- Client Portal
- Dashboard
- Migraciones
- Dockerfile
- docker-compose.yml
- requirements.txt

## Persistencia

El branding se guarda por empresa usando la columna JSON disponible en `companies`, en este orden:

1. `settings_json`
2. `experience_json`
3. `metadata_json`
4. `branding_json`

No crea migraciones ni tablas nuevas.

## Aplicar

```powershell
cd "C:\Users\valef\OneDrive\Desktop\CLONEXA\clonexa_backend"

Expand-Archive -Path "$env:USERPROFILE\Downloads\clonexa_branding_persistence_009d.zip" -DestinationPath . -Force

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

## Validar branding por curl

```powershell
$companyId = "<COMPANY_ID>"

$payload = @{
  logo_url = ""
  primary_color = "#2563eb"
  secondary_color = "#00ff88"
  background_color = "#05070a"
  text_color = "#f8fafc"
  visual_preset = "field_ops_dark"
  background_style = "aurora_boreal"
  theme_mode = "dark"
} | ConvertTo-Json

curl.exe -i -X PUT "http://127.0.0.1:8000/api/v1/companies/$companyId/experience/branding" `
  -H "Content-Type: application/json" `
  --data-binary $payload

curl.exe "http://127.0.0.1:8000/api/v1/companies/$companyId/experience"
```

## Validar en Admin V2

1. Abrir `http://localhost:8000/admin-v2`
2. `Ctrl + Shift + R`
3. Empresas → seleccionar empresa → Branding
4. Seleccionar paleta Voltage Field
5. Guardar branding
6. Network debe mostrar:
   - `PUT /api/v1/companies/{company_id}/experience/branding 200 OK`
7. Refrescar navegador
8. Branding conserva valores
9. Ir a CRM
10. Preview usa colores guardados

## Resultado esperado

- Guardar branding ya no responde 404.
- PUT branding responde 200.
- Refrescar mantiene cambios.
- CRM usa colores guardados.
- Admin V2 GOLDEN no se rompe.
- Acceso Maestro sigue funcionando.
