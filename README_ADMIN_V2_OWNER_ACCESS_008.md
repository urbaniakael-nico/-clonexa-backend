# CLONEXA Admin V2 Owner Access 008

Este patch reordena Admin Console V2 para que la sección de usuarios sea **Acceso Maestro**.

## Qué cambia

- Admin V2 administra el acceso principal del dueño o encargado.
- El personal operativo se gestiona desde el panel de la empresa.
- Se muestra un único acceso maestro por empresa, priorizando `role = company_admin`.
- Permite crear Acceso Maestro si falta.
- Permite regenerar clave temporal.
- Permite copiar email y clave.
- Permite desbloquear acceso.
- Permite activar o desactivar si el endpoint está disponible.
- La consola no queda en blanco si falla `/users`, `/experience` o endpoints opcionales.

## Archivos incluidos

- `app/web/admin_v2.html`
- `app/web/admin_v2.css`
- `app/web/admin_v2.js`
- `scripts/verify_admin_v2_owner_access.py`
- `README_ADMIN_V2_OWNER_ACCESS_008.md`
- `PATCH_MANIFEST.md`

## Aplicar

```powershell
cd C:\Users\valef\OneDrive\Desktop\CLONEXA\clonexa_backend
unzip clonexa_admin_v2_owner_access_008.zip -d .
docker compose -p clonexa down
docker compose -p clonexa up --build -d
```

## Verificar

```powershell
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/api/v1/companies
curl http://127.0.0.1:8000/api/v1/companies/cbb61ef8-2f1a-4b3b-8bb1-2a6297de987c/users
docker compose -p clonexa exec -T api sh -lc "PYTHONPATH=/app python scripts/verify_admin_v2_owner_access.py"
```

## Validación visual

Abrir:

```text
http://localhost:8000/admin-v2
```

Revisar:

- Menú lateral: **Acceso Maestro**.
- Empresa Voltage muestra `admin@voltage.com`.
- Se puede regenerar clave.
- Se puede copiar la clave temporal.
- Se puede desbloquear el acceso.
- Si faltan usuarios, aparece botón **Crear Acceso Maestro**.
