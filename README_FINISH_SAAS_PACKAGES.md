# CLONEXA SaaS packages/modules finish fix

Este patch corrige el estado parcial:

- Alembic no veía `0002`.
- La tabla `modules` no existía.
- El seed fallaba con `relation "modules" does not exist`.
- `/api/v1/modules` y `/api/v1/packages` daban `404` porque los routers no estaban registrados.

## Archivos críticos

- `migrations/versions/0002_create_packages_modules.py`
- `app/models/saas.py`
- `app/schemas/saas.py`
- `app/services/saas_packages.py`
- `app/api/v1/endpoints/modules.py`
- `app/api/v1/endpoints/packages.py`
- `app/api/v1/endpoints/company_modules.py`
- `scripts/seed_clonexa_packages.py`
- `scripts/apply_saas_finish_fix.py`
- `scripts/verify_saas_layer.py`

## Aplicación

Copia los archivos sobre el repo y ejecuta:

```bash
python scripts/apply_saas_finish_fix.py
alembic history
alembic upgrade head
alembic current
python scripts/seed_clonexa_packages.py
python scripts/verify_saas_layer.py
```

En Docker:

```bash
docker compose -p clonexa exec api python scripts/apply_saas_finish_fix.py
docker compose -p clonexa exec api alembic history
docker compose -p clonexa exec api alembic upgrade head
docker compose -p clonexa exec api alembic current
docker compose -p clonexa exec api python scripts/seed_clonexa_packages.py
docker compose -p clonexa exec api python scripts/verify_saas_layer.py
```

## Registro manual de routers

Si prefieres no correr el script, asegúrate de que `app/api/v1/router.py` tenga:

```python
from app.api.v1.endpoints import company_modules, modules, packages
```

Y debajo de los routers existentes:

```python
api_router.include_router(modules.router, prefix="/modules", tags=["modules"])
api_router.include_router(packages.router, prefix="/packages", tags=["packages"])
api_router.include_router(company_modules.router, prefix="/companies", tags=["company-modules"])
```

Esto genera:

- `GET /api/v1/modules`
- `POST /api/v1/modules`
- `GET /api/v1/packages`
- `POST /api/v1/packages`
- `GET /api/v1/packages/{package_id}`
- `GET /api/v1/companies/{company_id}/modules`
- `POST /api/v1/companies/{company_id}/activate-package`

## Registro manual de modelos

`app/models/__init__.py` debe tener:

```python
from app.models.saas import (
    Module,
    Package,
    PackageModule,
    CompanyModule,
    CompanyPackageAssignment,
)
```

## main.py

Debe existir una inclusión equivalente a:

```python
app.include_router(api_router, prefix=settings.API_V1_PREFIX)
```

o:

```python
app.include_router(api_router, prefix="/api/v1")
```

No crees rutas fuera de `/api/v1`.

## Validación esperada

```bash
alembic history
# 0001 -> 0002 (head), create packages modules

alembic current
# 0002

curl http://localhost:8000/api/v1/modules
curl http://localhost:8000/api/v1/packages
```

## Activar paquete

```bash
curl -X POST "http://localhost:8000/api/v1/companies/<COMPANY_ID>/activate-package" \
  -H "Content-Type: application/json" \
  -d '{"package_code":"field_pro_usa","settings":{}}'
```
