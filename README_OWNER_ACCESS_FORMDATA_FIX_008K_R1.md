# CLONEXA 008K-R1 — Owner Access FormData Runtime Fix + Remove Row Shortcut

## Qué corrige

Este micro-patch corrige el error runtime:

```text
TypeError: Failed to construct 'FormData':
parameter 1 is not of type 'HTMLFormElement'
```

El problema ocurría al crear el **Acceso Maestro** desde Admin V2. El handler intentaba usar `FormData(form)` con un elemento que no era un `HTMLFormElement`, por eso el flujo se rompía antes de enviar el `POST`.

## Cambios incluidos

- `app/web/admin_v2.js`
  - Captura nombre, email y contraseña temporal desde inputs visibles usando selectores robustos.
  - Envía `POST /api/v1/companies/{company_id}/users` con JSON real.
  - No simula éxito si el backend falla.
  - Recarga usuarios/detalle manteniendo la empresa seleccionada.
  - Mantiene el tab **Acceso Maestro**.
  - Elimina el botón inline redundante **Acceso Maestro** del listado de empresas.
  - Conserva el tab **Acceso Maestro** dentro del detalle de empresa.
  - Agrega compatibilidad para handlers antiguos `createCompanyUser(...)` si existieran en el HTML.

## Qué NO toca

- No toca backend.
- No toca migraciones.
- No toca CSS.
- No toca `/client`.
- No toca `/login`.
- No toca dashboard, paquetes, módulos, CRM ni health.

## Aplicar

```powershell
cd "C:\Users\valef\OneDrive\Desktop\CLONEXA\clonexa_backend"

Expand-Archive -Path "$env:USERPROFILE\Downloads\clonexa_owner_access_formdata_fix_008k_r1.zip" -DestinationPath . -Force

Get-ChildItem -Path . -Recurse -Directory -Filter "__pycache__" |
  Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

docker compose -p clonexa up --build -d
```

## Validar

Abrir:

```text
http://localhost:8000/admin-v2
```

Hacer `Ctrl + Shift + R`.

Validación manual:

1. Ir a **Empresas**.
2. Confirmar que en la fila de empresa ya no aparece el botón inline **Acceso Maestro**.
3. Abrir una empresa sin acceso maestro.
4. Ir al tab **Acceso Maestro**.
5. Llenar:
   - Nombre: `NICOLAS GOMEZ`
   - Email: `urbania.kael@gmail.com`
   - Contraseña temporal: `Clonexa-urban-demo-kr70!`
6. Click en **Crear acceso maestro**.
7. La consola no debe mostrar error `FormData`.
8. Network debe mostrar:
   - `POST /api/v1/companies/{company_id}/users`
9. El POST debe responder `200` o `201`.
10. La UI debe mostrar:
   - `Acceso Maestro: OK`
   - `urbania.kael@gmail.com`
11. Refrescar navegador.
12. Confirmar que el acceso sigue guardado.

## Criterio de aceptación

- No aparece error `FormData`.
- Sí aparece `POST /users` en Network.
- El acceso maestro se guarda.
- Al refrescar, el acceso sigue visible.
- No se elimina el tab Acceso Maestro del detalle.
- No se toca backend.
