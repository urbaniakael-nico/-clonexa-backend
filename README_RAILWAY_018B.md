# CLONEXA — Railway Deploy Notes

## Service architecture

Deploy CLONEXA once.

One backend handles:

- /admin-v2
- /client
- /login
- /docs
- /health
- /api/v1/*
- /webapp/materials

All companies live in the same PostgreSQL database separated by company_id.

## Railway services

Project:
CLONEXA-PROD

Services:
- clonexa-api
- postgres
- redis optional/future

## Required variables

DATABASE_URL=${{Postgres.DATABASE_URL}}
ENVIRONMENT=production
PUBLIC_BASE_URL=https://<railway-domain-or-custom-domain>
CLONEXA_PUBLIC_BASE_URL=https://<railway-domain-or-custom-domain>
SECRET_KEY=<strong-secret>
JWT_SECRET_KEY=<same-strong-secret>
CLONEXA_JWT_SECRET=<same-strong-secret>
CORS_ORIGINS=https://<railway-domain-or-custom-domain>

Optional:
REDIS_URL=${{Redis.REDIS_URL}}

## Runtime

Dockerfile uses:

CMD ["/app/scripts/start.sh"]

railway.json runs the migrations as pre-deploy command, in a separate container, before the
new deployment starts. If they fail, the deployment stops there and the current one stays live:

alembic upgrade head

start.sh only starts the app:

uvicorn app.main:app --host 0.0.0.0 --port $PORT

The service has a volume at /data, so Railway never runs two deployments at once: the old
container stops before the new one starts, even with the healthcheck. An app that fails at
boot (not a migration) still causes downtime until a rollback.

## Important

Do not use Cloudflare trycloudflare URL in production.
PUBLIC_BASE_URL must be Railway/custom domain for Telegram Web App.
Do not deploy one backend per company.
