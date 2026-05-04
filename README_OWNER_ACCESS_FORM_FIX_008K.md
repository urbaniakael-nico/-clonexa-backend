# CLONEXA 008K — Owner Access Form Capture + Create Fix

## Qué corrige
Este micro-patch conecta el formulario existente de **Acceso Maestro** en Admin V2 con el endpoint real:

`POST /api/v1/companies/{company_id}/users`

Corrige:
- Captura real de nombre del encargado.
- Captura real de email.
- Captura real de contraseña temporal.
- Payload compatible con backend: `name`, `full_name`, `email`, `password`, `temporary_password`, `role`, `status`, `must_change_password`.
- Manejo visible de errores si backend responde error.
- Recarga de usuarios de la empresa después del POST.
- Mantiene empresa seleccionada y vista de detalle.
- No simula éxito.

## Archivos incluidos
- `app/web/admin_v2.js`
- `README_OWNER_ACCESS_FORM_FIX_008K.md`
- `PATCH_MANIFEST.md`

## Qué NO toca
- Backend
- Migraciones
- CSS
- `/client`
- `/login`
- `/admin` clásico
- Field Engine
- Dockerfile
- docker-compose.yml

## Aplicar

```powershell
cd "C:\Users\valef\OneDrive\Desktop\CLONEXA\clonexa_backend"

Expand-Archive -Path "$env:USERPROFILE\Downloads\clonexa_owner_access_form_fix_008k.zip" -DestinationPath . -Force

Get-ChildItem -Path . -Recurse -Directory -Filter "__pycache__" |
  Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

docker compose -p clonexa up --build -d
```

## Validar API

```powershell
curl.exe http://127.0.0.1:8000/health
curl.exe http://127.0.0.1:8000/api/v1/companies
```

## Validar en Admin V2

1. Abrir `http://localhost:8000/admin-v2`.
2. Presionar `Ctrl + Shift + R`.
3. Ir a **Empresas**.
4. Seleccionar una empresa sin Acceso Maestro.
5. Abrir tab/sección **Acceso Maestro**.
6. Completar:
   - Nombre del encargado
   - Email
   - Contraseña temporal
7. Click **Crear acceso maestro**.
8. Debe aparecer **Acceso Maestro: OK** y mostrar el email.
9. Refrescar navegador.
10. El acceso debe seguir guardado.

## Login

Entrar en:

`http://localhost:8000/login`

Usar el email y contraseña temporal creados.
