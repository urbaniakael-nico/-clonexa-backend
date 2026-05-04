# CLONEXA Admin V2 Company Archive 008D

Micro-patch frontend para Admin Console V2.

## Qué agrega

- Filtro de empresas: activas + inactivas, activas, inactivas, archivadas y todas.
- Desactivar empresa: `status = inactive`.
- Reactivar empresa: `status = active`.
- Eliminar empresa como soft archive: `status = deleted`.
- Confirmación fuerte por slug antes de archivar.
- No hace hard delete físico.
- No toca migraciones, backend, Docker, `/client`, `/login`, Field Engine ni CRM Builder.

## Aplicar

```powershell
cd C:\Users\valef\OneDrive\Desktop\CLONEXA\clonexa_backend
unzip clonexa_admin_v2_company_archive_008d.zip -d .
docker compose -p clonexa down
docker compose -p clonexa up --build -d
```

## Validar

```powershell
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/api/v1/companies
```

Abrir:

```text
http://localhost:8000/admin-v2
```

## Flujo esperado

1. Crear empresa demo con Acceso Maestro.
2. Desactivar empresa.
3. Reactivar empresa.
4. Eliminar / archivar empresa escribiendo el slug exacto.
5. Ver que desaparece del filtro principal.
6. Cambiar filtro a Archivadas.
7. Reactivar empresa archivada.

## Nota backend

Este patch intenta usar endpoints seguros existentes, en este orden:

1. `PATCH /api/v1/companies/{company_id}/status`
2. `PATCH /api/v1/companies/{company_id}`
3. `PUT /api/v1/companies/{company_id}`

Nunca llama `DELETE`.
Si tu backend todavía no tiene actualización de status de empresa, Admin V2 mostrará un error local sin romper la consola.
