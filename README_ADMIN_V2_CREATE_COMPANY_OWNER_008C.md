# CLONEXA Admin V2 — Crear empresa con Acceso Maestro 008C

Micro-patch frontend para completar el alta SaaS desde Admin Console V2.

## Qué cambia

- En el formulario Crear empresa se agrega el bloque Acceso Maestro.
- Al crear empresa ahora ejecuta:
  1. Crear tenant.
  2. Activar paquete seleccionado, si aplica.
  3. Crear acceso maestro `company_admin`.
  4. Mostrar email y clave temporal con botones de copia.
  5. Recargar dashboard, empresas y detalle.
  6. Seleccionar automáticamente la empresa creada.

## Archivos incluidos

- `app/web/admin_v2.js`
- `README_ADMIN_V2_CREATE_COMPANY_OWNER_008C.md`
- `PATCH_MANIFEST.md`

## Aplicar

```powershell
cd C:\Users\valef\OneDrive\Desktop\CLONEXA\clonexa_backend
unzip clonexa_admin_v2_create_company_owner_008c.zip -d .
docker compose -p clonexa down
docker compose -p clonexa up --build -d
```

## Validar

Abrir:

```text
http://localhost:8000/admin-v2
```

Crear empresa demo:

```text
Nombre: Clonexa Test Company
Slug: clonexa-test-company
Nombre encargado: Test Owner
Email: admin@clonexatest.com
Clave temporal: usar generada
```

Resultado esperado:

- La empresa aparece en el listado.
- El Acceso Maestro aparece como OK.
- Se muestra email y clave temporal.
- La clave se puede copiar.
- Login funciona en `/login` con el email y la clave temporal.

## Notas

- No incluye cambios de estilos.
- No incluye cambios backend.
- No incluye migraciones.
- No toca `/client`, `/login`, Admin clásico, Field Engine ni CRM Builder.
