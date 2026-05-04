# Clonexa Backend

Backend base ejecutable de Clonexa.

## Stack

- FastAPI
- PostgreSQL
- SQLAlchemy async
- Alembic
- Redis preparado
- Multiempresa por `company_id`
- Event Engine idempotente
- Workforce Engine base
- Bot Gateway preparado
- CRM Read Model inicial

## Ejecutar

```bash
cp .env.example .env
docker compose up --build
```

Aplicar migraciones dentro del contenedor:

```bash
docker compose exec api alembic upgrade head
```

Crear datos iniciales:

```bash
docker compose exec api python scripts/bootstrap_local.py
```

Abrir API:

```text
http://localhost:8000/docs
http://localhost:8000/health
```

## Endpoints principales

```text
GET  /health
POST /api/v1/companies
GET  /api/v1/companies
POST /api/v1/employees
GET  /api/v1/employees?company_id=<uuid>
POST /api/v1/events
POST /api/v1/shifts/start
POST /api/v1/shifts/pause
POST /api/v1/shifts/resume
POST /api/v1/shifts/lunch/start
POST /api/v1/shifts/lunch/end
POST /api/v1/shifts/end
GET  /api/v1/crm/overview?company_id=<uuid>
GET  /api/v1/crm/active-employees?company_id=<uuid>
POST /api/v1/bots/telegram/{company_id}/webhook
```

## Principios implementados

- Toda tabla operativa usa `company_id`
- `work_events` tiene idempotencia por `company_id + event_id`
- `work_sessions` mantiene los bloques de trabajo
- `employee_current_status` alimenta CRM
- Bots envÃ­an eventos, no contienen negocio

