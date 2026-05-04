# CLONEXA Field Engine — Voltage Phase 1

Patch pequeño para activar la primera fase funcional del Field Engine en Voltage.

## Incluye

- Migración `0005_create_field_engine.py`
- Modelos SQLAlchemy Field
- Schemas Pydantic v2
- Servicio de negocio con reglas de stock
- Endpoints `/api/v1/field/*`
- Seed demo Voltage
- Conexión de `/client` para:
  - Técnicos
  - Inventario / Materiales
  - Billing

## Aplicar

```bash
cd C:\Users\valef\OneDrive\Desktop\CLONEXA\clonexa_backend
unzip clonexa_field_engine_voltage_phase1_004.zip -d .
docker compose -p clonexa down
docker compose -p clonexa up --build -d
docker compose -p clonexa exec -T api alembic upgrade head
docker compose -p clonexa exec -T api python scripts/seed_voltage_field_demo.py
```

## Validar API

```bash
curl http://127.0.0.1:8000/health
```

PowerShell:

```powershell
$body = @{
  email = "admin@voltage.com"
  password = "Clonexa2026!Voltage"
} | ConvertTo-Json

$login = Invoke-RestMethod `
  -Uri "http://127.0.0.1:8000/api/v1/auth/login" `
  -Method POST `
  -ContentType "application/json" `
  -Body $body

$token = $login.access_token

Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/field/summary" -Headers @{ Authorization = "Bearer $token" }
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/field/technicians" -Headers @{ Authorization = "Bearer $token" }
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/field/materials" -Headers @{ Authorization = "Bearer $token" }
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/field/billing-projects" -Headers @{ Authorization = "Bearer $token" }
```

## Validar UI

1. Abrir `http://localhost:8000/login`
2. Entrar con `admin@voltage.com / Clonexa2026!Voltage`
3. Abrir `/client`
4. Click en:
   - Técnicos
   - Inventario / Materiales
   - Billing

## Reglas implementadas

- Solo supervisores pueden solicitar material.
- `issued` resta stock disponible y aumenta stock en campo.
- `used` descuenta stock del técnico y stock global en campo.
- `returned good` devuelve a disponible.
- `returned damaged` pasa a dañado.
- `lost` descuenta stock del técnico y stock global en campo.
- Ningún movimiento puede dejar stock negativo.
