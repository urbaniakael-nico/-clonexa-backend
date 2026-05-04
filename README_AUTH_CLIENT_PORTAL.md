# CLONEXA Auth + Client Portal 003

Patch pequeño para agregar:

- Tabla `company_users`
- JWT stateless
- Login en `/login`
- Client Portal Shell en `/client`
- Endpoints `/api/v1/auth/*`
- Endpoints `/api/v1/companies/{company_id}/users`
- Seed de usuarios demo para Voltage, Radio Despecho, Mundo Case y Velvet
- Gestión básica de usuarios desde Admin Console

## Aplicar

```bash
cd C:\Users\valef\OneDrive\Desktop\CLONEXA\clonexa_backend
unzip clonexa_auth_client_portal_003.zip -d .
docker compose -p clonexa down
docker compose -p clonexa up --build -d
```

## Migración y seed

```bash
docker compose -p clonexa exec -T api alembic current
docker compose -p clonexa exec -T api alembic upgrade head
docker compose -p clonexa exec -T api python scripts/seed_company_users.py
```

## Variables recomendadas

Agregar al `.env` o `.env.example`:

```env
CLONEXA_JWT_SECRET=change-me-in-production
ACCESS_TOKEN_EXPIRE_MINUTES=480
```

## Validar API

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/api/v1/companies
```

PowerShell login Voltage:

```powershell
$body = @{
  email = "admin@voltage.com"
  password = "Clonexa2026!Voltage"
} | ConvertTo-Json

$login = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/auth/login" -Method POST -ContentType "application/json" -Body $body
$token = $login.access_token
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/auth/me" -Headers @{ Authorization = "Bearer $token" }
```

## Credenciales iniciales

- Voltage: `admin@voltage.com` / `Clonexa2026!Voltage`
- Radio Despecho: `admin@radiodespecho.com` / `Clonexa2026!Radio`
- Mundo Case: `admin@mundocase.com` / `Clonexa2026!Mundo`
- Velvet: `admin@velvet.com` / `Clonexa2026!Velvet`

Todos quedan con `must_change_password=true`.

## Web

- `http://localhost:8000/login`
- `http://localhost:8000/client`
- `http://localhost:8000/admin`

## Nota de seguridad

Cambiar `CLONEXA_JWT_SECRET` antes de producción.
