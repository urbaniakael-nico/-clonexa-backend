# CLONEXA Owner Access Timestamp Fix 008E

Este microfix corrige la creación de `company_users` para que `created_at` y `updated_at` nunca queden en `NULL`.

## Archivos incluidos

- `app/services/auth_service.py`
- `app/api/v1/endpoints/company_users.py`
- `scripts/verify_owner_access_creation.py`
- `README_OWNER_ACCESS_TIMESTAMP_FIX_008E.md`
- `PATCH_MANIFEST.md`

## Aplicar

```powershell
cd C:\Users\valef\OneDrive\Desktop\CLONEXA\clonexa_backend
unzip clonexa_owner_access_timestamp_fix_008e.zip -d .
docker compose -p clonexa down
docker compose -p clonexa up --build -d
```

## Validar

```powershell
curl http://127.0.0.1:8000/health
docker compose -p clonexa exec -T api sh -lc "PYTHONPATH=/app python scripts/verify_owner_access_creation.py"
```

## Resultado esperado

```text
CLONEXA OWNER ACCESS CREATION CHECK
owner access created: OK
created_at: OK
updated_at: OK
status: OK
```

## Alcance

- No incluye migraciones.
- No toca frontend.
- No toca Docker.
- No toca Field Engine.
- No toca CRM Builder.
