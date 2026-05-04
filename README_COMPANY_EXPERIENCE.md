# CLONEXA Capítulo 3 — CRM Builder / Panel Empresa

Patch funcional para agregar al Admin Console aprobado el builder operativo del Panel Empresa.

## Qué agrega

- Migración `0003_create_company_experience.py`
- Modelos SQLAlchemy para experiencia por empresa
- Schemas Pydantic
- Servicio idempotente de defaults por engine
- Endpoints bajo `/api/v1/companies`
- CRM Builder dentro de `/admin`
- Preview del Panel Empresa con:
  - Launchpad
  - Widgets
  - Secciones
  - Acciones rápidas
  - Campos configurables
  - Alertas
  - Branding / colores / visual preset / idioma

## No toca

- `migrations/versions/0001_core_tables.py`
- `migrations/versions/0002_create_packages_modules.py`
- datos existentes
- endpoints existentes
- estética general aprobada del Admin Console

## Aplicar

```bash
cd C:\Users\valef\OneDrive\Desktop\CLONEXA\clonexa_backend
unzip clonexa_chapter3_client_panel_builder_patch.zip -d .
python scripts/apply_company_experience_patch.py
alembic upgrade head
python scripts/verify_company_experience.py
```

## En Docker

```bash
docker compose -p clonexa down
docker compose -p clonexa up --build -d
docker compose -p clonexa exec api python scripts/apply_company_experience_patch.py
docker compose -p clonexa exec api alembic upgrade head
docker compose -p clonexa exec api alembic current
docker compose -p clonexa exec api python scripts/verify_company_experience.py
```

## Validar API

```bash
curl http://localhost:8000/health
curl http://localhost:8000/api/v1/companies
curl http://localhost:8000/api/v1/companies/<company_id>/experience
curl http://localhost:8000/api/v1/companies/<company_id>/launchpad-cards
curl http://localhost:8000/api/v1/companies/<company_id>/crm-widgets
curl http://localhost:8000/api/v1/companies/<company_id>/crm-sections
curl http://localhost:8000/api/v1/companies/<company_id>/crm-actions
curl http://localhost:8000/api/v1/companies/<company_id>/field-configs
curl http://localhost:8000/api/v1/companies/<company_id>/alert-rules
```

## Validar UI

Abrir:

```text
http://localhost:8000/admin
```

Flujo:

1. Seleccionar `Voltage`.
2. Click `Configurar CRM`.
3. Ver `Launchpad` con Técnicos, GPS, Inventario, Nómina.
4. Ver widgets Voltage.
5. Ver campos configurables de técnico.
6. Cambiar color principal en `Branding`.
7. Guardar.
8. Ir a `Vista previa Panel Empresa`.
9. Refrescar y confirmar persistencia.

Repetir con:
- Radio Despecho → hospitality
- Mundo Case → retail
- Velvet → production

## Defaults por engine

### Field / Voltage

Launchpad:
- Abrir CRM Field
- KPIs Field
- Técnicos
- GPS
- Tareas / Solicitudes
- Inventario / Materiales
- Nómina Quincenal
- Billing
- Reportes
- Configuración

### Hospitality / Radio Despecho

Launchpad:
- Abrir Panel Barman
- KPIs Bar
- Mesas
- Pedidos
- Inventario
- Clientes / Puntos
- QR / WhatsApp
- Cierre de Día
- Configuración

### Retail / Mundo Case

Launchpad:
- Abrir CRM Retail
- KPIs Retail
- Tiendas
- Personal
- Ventas
- Solicitudes
- Bodega
- Nómina
- Cierres
- Configuración

### Production / Velvet

Launchpad:
- Abrir CRM Producción
- KPIs Producción
- Operarios
- Referencias
- Producción
- Nómina Quincenal
- Reportes
- Configuración
