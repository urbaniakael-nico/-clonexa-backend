# CLONEXA CRM Builder Microfix 002-D

Patch quirúrgico para que CRM Builder muestre datos reales por empresa.

## Archivos incluidos

- `scripts/diagnose_company_experience.py`
- `scripts/repair_company_experience_db.py`
- `scripts/force_seed_company_experience_defaults.py`
- `app/api/v1/endpoints/company_experience.py`
- `app/services/company_experience.py`
- `app/web/admin.js`

No incluye migraciones, Dockerfile, docker-compose, requirements, `admin.html` ni `admin.css`.

## Aplicación

Desde:

```bash
cd C:\Users\valef\OneDrive\Desktop\CLONEXA\clonexa_backend
```

Descomprimir el ZIP sobre el repo.

Luego:

```bash
docker compose -p clonexa down
docker compose -p clonexa up --build -d
```

## Reparación y seed

```bash
docker compose -p clonexa exec -T api python scripts/repair_company_experience_db.py
docker compose -p clonexa exec -T api python scripts/force_seed_company_experience_defaults.py
docker compose -p clonexa exec -T api python scripts/diagnose_company_experience.py
```

## Validación API

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/api/v1/companies
curl http://127.0.0.1:8000/api/v1/modules
curl http://127.0.0.1:8000/api/v1/packages
curl http://127.0.0.1:8000/api/v1/companies/cbb61ef8-2f1a-4b3b-8bb1-2a6297de987c/experience
```

## Validación en Admin

1. Abrir `http://localhost:8000/admin`
2. Seleccionar Voltage.
3. Click en `Configurar CRM`.
4. Validar filas reales en:
   - Launchpad
   - Widgets
   - Secciones
   - Acciones rápidas
   - Campos configurables
   - Alertas
   - Vista previa Panel Empresa

Si algún array está vacío, usar `Regenerar defaults`.

## Importante

Este patch no toca migraciones `0001`, `0002` ni `0003`.
No crea `0004`.
No borra datos.
No rediseña el Admin Console.
