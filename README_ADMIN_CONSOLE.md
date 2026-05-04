# CLONEXA ADMIN CONSOLE MVP

Consola web premium servida directamente por FastAPI.

## Agrega

- `GET /admin`
- Static local en `/admin-static`
- UI futurista dark premium sin CDN
- Consumo de endpoints existentes:
  - `GET /health`
  - `GET /api/v1/companies`
  - `GET /api/v1/packages`
  - `GET /api/v1/modules`
  - `GET /api/v1/companies/{company_id}/modules`
  - `POST /api/v1/companies`
  - `POST /api/v1/companies/{company_id}/activate-package`

## Archivos creados

- `app/web/admin_routes.py`
- `app/web/admin.html`
- `app/web/admin.css`
- `app/web/admin.js`
- `app/web/__init__.py`
- `app/web/assets/.gitkeep`
- `scripts/apply_admin_console_patch.py`
- `scripts/verify_admin_console.py`

## Instalación local

Desde la raíz del repo:

```bash
unzip clonexa_admin_console_patch.zip -d .
python scripts/apply_admin_console_patch.py
python scripts/verify_admin_console.py
```

Levanta Docker:

```bash
docker compose -p clonexa up --build
```

Abre:

```text
http://localhost:8000/admin
```

## Instalación dentro de Docker

```bash
docker compose -p clonexa exec api python scripts/apply_admin_console_patch.py
docker compose -p clonexa exec api python scripts/verify_admin_console.py
docker compose -p clonexa restart api
```

## Validación

```bash
curl http://localhost:8000/health
curl http://localhost:8000/api/v1/companies
curl http://localhost:8000/api/v1/packages
curl http://localhost:8000/api/v1/modules
curl http://localhost:8000/admin
```

## Logo

Si tienes logo, cópialo aquí:

```text
app/web/assets/clonexa-logo.png
```

Si no existe, la UI muestra wordmark textual premium `CLONEXA`.

## Garantías del patch

- No modifica migraciones `0001` ni `0002`.
- No borra datos.
- No agrega autenticación.
- No crea Next.js todavía.
- No rompe `/docs`.
- El patch sobre `app/main.py` es idempotente.
- Crea backup `app/main.py.bak_admin_console` si modifica `main.py`.
