# CLONEXA Modules UX Improvement — Active Bar + Search

## Qué corrige

Mejora la pestaña **Módulos** dentro del detalle por empresa en Admin V2, sin tocar backend, Acceso Maestro, Branding, Login, Client routing ni paquetes.

Incluye:

- Barra superior **Módulos activos** con contador dinámico.
- Chips visuales de módulos activos con nombre en español y sigla.
- Buscador visual con lupa para filtrar por nombre, slug, descripción, categoría e intención.
- Keywords frontend para búsquedas como:
  - agregar personal
  - nomina / nómina
  - ubicacion / ubicación
  - materiales
  - pedidos
  - qr
- Filtros rápidos:
  - Todos
  - Activos
  - Inactivos
- Grid de catálogo con estado Activo/Inactivo.
- Botones:
  - Activar
  - Desactivar
  - Info
- Actualización en vivo después de activar/desactivar.
- Nombres visibles en español.

## Archivos incluidos

- `app/web/admin_v2.js`
- `README_MODULES_UX_IMPROVEMENT.md`
- `PATCH_MANIFEST.md`

## Aplicar

```powershell
cd "C:\Users\valef\OneDrive\Desktop\CLONEXA\clonexa_backend"

Expand-Archive -Path "$env:USERPROFILE\Downloads\clonexa_modules_ux_improvement_active_search.zip" -DestinationPath . -Force

Get-ChildItem -Path . -Recurse -Directory -Filter "__pycache__" |
  Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

docker compose -p clonexa up --build -d
```

## Validar

```powershell
curl.exe http://127.0.0.1:8000/health
curl.exe http://127.0.0.1:8000/api/v1/companies
curl.exe http://127.0.0.1:8000/api/v1/modules
```

Luego:

1. Abrir `http://localhost:8000/admin-v2`.
2. Entrar a **Empresas**.
3. Seleccionar una empresa.
4. Abrir tab **Módulos**.
5. Validar que arriba aparece **Módulos activos** con contador.
6. Buscar:
   - `agregar personal`
   - `nomina`
   - `ubicacion`
   - `materiales`
   - `pedidos`
   - `qr`
7. Validar filtros **Todos / Activos / Inactivos**.
8. Validar que activar/desactivar refresca barra superior y grid.

## Notas técnicas

Este patch no toca backend. Para toggles de módulos usa rutas existentes de forma tolerante:

- `POST /api/v1/companies/{company_id}/modules`
- `PUT/PATCH /api/v1/companies/{company_id}/modules/{module_code}`
- `DELETE /api/v1/companies/{company_id}/modules/{module_code}` como fallback para desactivar

Si tu backend usa una ruta distinta para activar/desactivar módulos, ajusta solo la función `tryCompanyModuleToggleEndpoint`.
