# CLONEXA CRM Builder Functionality Fix

Patch funcional para completar el Capítulo 3 sin rediseñar el Admin Console aprobado.

## Qué corrige

- Error `relation "company_crm_launchpad_cards" does not exist`.
- Launchpad vacío.
- Widgets vacíos.
- Secciones vacías.
- Acciones rápidas vacías.
- Campos configurables vacíos.
- Alertas vacías.
- CRUD completo del CRM Builder.
- Preview del Panel Empresa usando datos reales.
- Defaults idempotentes por engine: field, hospitality, retail, production.

## Archivos principales

- `migrations/versions/0003_create_company_experience.py`
- `migrations/versions/0004_fix_company_experience_missing_tables.py`
- `app/models/experience.py`
- `app/schemas/experience.py`
- `app/services/company_experience.py`
- `app/api/v1/endpoints/company_experience.py`
- `app/web/admin_experience.css`
- `app/web/admin_experience.js`
- `scripts/apply_crm_builder_functionality_fix.py`
- `scripts/seed_company_experience_defaults.py`
- `scripts/verify_company_experience.py`

## Aplicar

```bash
cd C:\Users\valef\OneDrive\Desktop\CLONEXA\clonexa_backend
unzip clonexa_crm_builder_functionality_fix_patch.zip -d .
python scripts/apply_crm_builder_functionality_fix.py
alembic upgrade head
python scripts/seed_company_experience_defaults.py
python scripts/verify_company_experience.py
```

## Docker

```bash
docker compose -p clonexa down
docker compose -p clonexa up --build -d

docker compose -p clonexa exec api python scripts/apply_crm_builder_functionality_fix.py
docker compose -p clonexa exec api alembic upgrade head
docker compose -p clonexa exec api python scripts/seed_company_experience_defaults.py
docker compose -p clonexa exec api python scripts/verify_company_experience.py
```

## Validación API

```bash
curl http://localhost:8000/health
curl http://localhost:8000/api/v1/companies
curl http://localhost:8000/api/v1/companies/<company_id>/experience
curl -X POST http://localhost:8000/api/v1/companies/<company_id>/experience/ensure-defaults
```

## Validación Admin

1. Abrir `http://localhost:8000/admin`
2. Seleccionar Voltage.
3. Click `Configurar CRM` o botón flotante `CRM Builder`.
4. Ver Launchpad, Widgets, Secciones, Acciones, Campos y Alertas con datos.
5. Crear tarjeta nueva.
6. Guardar.
7. Refrescar.
8. Confirmar persistencia.
9. Eliminar.
10. Regenerar defaults.
11. Confirmar que no duplica.

## Alembic

Resultado esperado:

```bash
alembic current
# 0004
```

`0004` es una reparación no destructiva para bases que ya estaban en `0003` pero sin todas las tablas.
