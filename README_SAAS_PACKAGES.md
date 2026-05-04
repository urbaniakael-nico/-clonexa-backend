# CLONEXA SaaS Packages & Modules

Esta extensión agrega la capa SaaS de módulos y paquetes activos por empresa.

## Tablas nuevas

- `modules`
- `packages`
- `package_modules`
- `company_modules`
- `company_package_assignments`

Los módulos y paquetes son globales. Las activaciones son por empresa con `company_id`.

## Registrar modelos

En `app/db/base.py` o donde importes modelos para Alembic, agrega:

```python
from app.models.saas import Module, Package, PackageModule, CompanyModule, CompanyPackageAssignment  # noqa
```

## Registrar routers

En `app/api/v1/router.py`:

```python
from fastapi import APIRouter

from app.api.v1.endpoints import company_modules, modules, packages

api_router = APIRouter()

api_router.include_router(modules.router, prefix="/modules", tags=["modules"])
api_router.include_router(packages.router, prefix="/packages", tags=["packages"])
api_router.include_router(company_modules.router, prefix="/companies", tags=["company-modules"])
```

Si tu archivo ya tiene `api_router`, no lo reemplaces completo: solo importa los tres módulos y agrega los `include_router`.

## Migración

Revisa el `down_revision` en:

```text
alembic/versions/0002_create_packages_modules.py
```

Debe apuntar al revision actual de tu migración inicial. Luego ejecuta:

```bash
docker compose -p clonexa exec api alembic upgrade head
```

o local:

```bash
alembic upgrade head
```

## Seed idempotente

Dentro del contenedor:

```bash
docker compose -p clonexa exec api python scripts/seed_clonexa_packages.py
```

Local:

```bash
python scripts/seed_clonexa_packages.py
```

El seed se puede correr múltiples veces. No duplica módulos, paquetes ni relaciones.

## Endpoints nuevos

```http
GET  /api/v1/modules
POST /api/v1/modules

GET  /api/v1/packages
POST /api/v1/packages
GET  /api/v1/packages/{package_id}

GET  /api/v1/companies/{company_id}/modules
POST /api/v1/companies/{company_id}/activate-package
```

## Activar paquete para Voltage

Primero obtén el ID de Voltage:

```http
GET /api/v1/companies
```

Luego activa:

```bash
curl -X POST "http://localhost:8000/api/v1/companies/<VOLTAGE_COMPANY_ID>/activate-package" \
  -H "Content-Type: application/json" \
  -d '{"package_code":"field_pro_usa","settings":{}}'
```

## Paquetes base

- `field_pro_usa` → Voltage
- `hospitality_pro` → Radio Despecho
- `retail_ops` → Mundo Case
- `production_pro` → Velvet

## Validación

```bash
docker compose -p clonexa up --build
```

Luego abre:

```text
http://localhost:8000/docs
http://localhost:8000/api/v1/modules
http://localhost:8000/api/v1/packages
```
