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

## Interruptor por empresa (obligatorio)

- Toda función nueva o cambio visual debe ir detrás de un interruptor por empresa, apagado por defecto, y activarse solo para la empresa que lo pidió.
- Los arreglos de seguridad y errores pueden aplicar a todas, pero debes avisarme antes de hacer push indicando que afectan a todas las empresas.

## Migraciones (alembic)

- Los revision id de alembic deben tener máximo 32 caracteres.

## Espacio en base de datos

- La base tiene 500 MB y hoy usa ~235 MB. Antes de guardar cualquier dato pesado nuevo (imágenes, archivos, adjuntos), avísame primero: el siguiente paso es un bucket de objetos, no más bytes en Postgres.

## Flujo de commit y push (autonomía condicionada)

Tengo autonomía para hacer commit y push a `main`, con una condición obligatoria:

- Antes de cada push, correr:
  - `python -m pytest tests -k hospitality`
  - `node --test tests/`
- Si algo falla: NO hacer push. Corregir primero o reportar al usuario.
- Cada cambio nuevo debe venir con sus pruebas.
- Después de cada push, resumir en español qué cambió y el hash del commit.
- Después de cada push, recuérdame verificar el despliegue en Railway.

## Reglas de seguridad

- Nunca guardar tokens, contraseñas ni archivos `.env` en el repo.
- Nunca usar `git push --force` ni reescribir el historial de `main`.
- Todo endpoint nuevo debe exigir sesión válida desde el primer día (Admin V2, usuario de empresa, o el rol de mini panel que corresponda — mesero, cocina, caja, etc.), validado en el servidor, no solo en la pantalla. Nunca agregar un endpoint sin autenticación: estamos cerrando un barrido de ~360 endpoints que quedaron abiertos por no seguir esto desde el inicio.

## Idioma

- Responder siempre en español.
