# Patch notes

## Archivos incluidos

- `alembic/versions/0002_create_packages_modules.py`
- `app/models/saas.py`
- `app/schemas/saas.py`
- `app/services/saas_packages.py`
- `app/api/v1/endpoints/modules.py`
- `app/api/v1/endpoints/packages.py`
- `app/api/v1/endpoints/company_modules.py`
- `scripts/seed_clonexa_packages.py`
- `README_SAAS_PACKAGES.md`

## Decisiones técnicas

- `modules` y `packages` son globales.
- `company_modules` y `company_package_assignments` son multiempresa.
- Activar paquete desactiva otros paquetes activos de la empresa.
- Activar paquete vuelve a habilitar módulos existentes sin duplicar.
- `settings` usa `JSONB`.
- Seed idempotente usando `ON CONFLICT`.
- La activación usa `AsyncSession`.
- Swagger mostrará tags `modules`, `packages` y `company-modules`.

## Ajustes esperados si tu estructura difiere

Los imports asumen:

```python
from app.db.base import Base
from app.api.deps import get_db
from app.models.company import Company
```

Si tu repo usa nombres diferentes para `Base`, `get_db` o `Company`, cambia solo esas líneas de import.
