# CLONEXA

Backend FastAPI + Postgres, desplegado en Railway (proyecto `merry-simplicity`, entorno `production`). Todo push a `main` despliega automáticamente a producción — tratar `main` como rama de producción.

## Ubicación del código

- Hospitality vive en `app/api/v1/endpoints/hospitality.py`.
- El frontend del panel es un solo archivo: `app/web/client.js`.

## Convenciones de `client.js`

- Las funciones llevan un sufijo de versión (ej: `cxHspTableCard034B`).
- El código nuevo usa un sufijo nuevo; no renombrar funciones existentes.

## Multi-tenant

- Toda consulta SQL debe filtrar por `company_id`.
- Nunca devolver datos de otro tenant.

## Flujo de commit y push (autonomía condicionada)

Tengo autonomía para hacer commit y push a `main`, con una condición obligatoria:

- Antes de cada push, correr:
  - `python -m pytest tests -k hospitality`
  - `node --test tests/`
- Si algo falla: NO hacer push. Corregir primero o reportar al usuario.
- Cada cambio nuevo debe venir con sus pruebas.
- Después de cada push, resumir en español qué cambió y el hash del commit.

## Reglas de seguridad

- Nunca guardar tokens, contraseñas ni archivos `.env` en el repo.
- Nunca usar `git push --force` ni reescribir el historial de `main`.

## Idioma

- Responder siempre en español.
