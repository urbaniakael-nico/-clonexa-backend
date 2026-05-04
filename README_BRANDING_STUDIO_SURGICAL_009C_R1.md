# CLONEXA 009C-R1 — Branding Studio Surgical Fix

## Qué corrige

Este patch agrega un **Branding Studio visual real** dentro de Admin V2 sin tocar backend, Auth, Acceso Maestro, `/client`, `/login`, migraciones ni Docker.

Parte desde la base GOLDEN funcional:

- API LIVE
- Empresas cargan
- Acceso Maestro funciona
- Crear Acceso Maestro funciona
- No usa `new FormData`
- No reintroduce botón inline `Acceso Maestro`
- Sidebar mantiene `Acceso Maestro`, no `Usuarios`

## Qué agrega

En `Empresa → Branding`:

- Paletas visuales clicables
- Editor de colores con `input type="color"` + HEX sincronizado
- Fondos tornasol / futuristas con gradientes CSS
- Vista previa viva del panel cliente
- Modal `Ver así quedará`
- Guardar branding usando endpoints existentes

En `Empresa → CRM`:

- Preview visual real del panel cliente con branding aplicado
- Datos técnicos de empresa, slug, paquete, módulos, `/client`, preset y fondo

## Archivos incluidos

- `app/web/admin_v2.js`
- `README_BRANDING_STUDIO_SURGICAL_009C_R1.md`
- `PATCH_MANIFEST.md`

## Nota técnica

No se incluye `admin_v2.css` para evitar sobrescribir el CSS GOLDEN actual.  
Los estilos del Branding Studio se inyectan desde `admin_v2.js` mediante `injectBrandingStudioStyles()`, de forma aislada y con prefijo `cx-`.

## Aplicar

```powershell
cd "C:\Users\valef\OneDrive\Desktop\CLONEXA\clonexa_backend"

Expand-Archive -Path "$env:USERPROFILE\Downloads\clonexa_branding_studio_surgical_009c_r1.zip" -DestinationPath . -Force

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

1. Abrir `http://localhost:8000/admin-v2`
2. Presionar `Ctrl + Shift + R`
3. Entrar a `Empresas`
4. Seleccionar empresa
5. Ir a `Branding`

Debe verse:

- Paletas visuales
- Editor de colores
- Fondos tornasol / futuristas
- Vista previa del panel cliente
- Botón `Ver así quedará`
- Botón `Guardar branding`

## Validar GOLDEN

Confirmar:

- Sidebar dice `Acceso Maestro`
- No existe botón inline `Acceso Maestro` en filas de empresas
- Crear Acceso Maestro sigue funcionando
- Dashboard sigue funcionando
- Archivar/desactivar sigue funcionando
- No aparece error `FormData`

## Persistencia

El guardado intenta usar:

1. `PUT /api/v1/companies/{company_id}/experience/branding`
2. fallback: `PUT /api/v1/companies/{company_id}/branding`

Si el backend responde error, la UI muestra mensaje y no simula éxito.
