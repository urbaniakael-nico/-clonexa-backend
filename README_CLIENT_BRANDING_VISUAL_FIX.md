# CLONEXA Client Branding Visual Fix 005B

Micro-patch visual y funcional para:

- hacer editable el branding real desde Admin Console,
- aplicar colores al Client Portal,
- elevar `/client` a estética SaaS premium futurista,
- mantener Field Engine Phase 1 funcionando.

## Aplicar

```bash
cd C:\Users\valef\OneDrive\Desktop\CLONEXA\clonexa_backend
unzip clonexa_client_branding_visual_fix_005b.zip -d .
docker compose -p clonexa down
docker compose -p clonexa up --build -d
```

## Reparar defaults de branding

```bash
docker compose -p clonexa exec -T api python scripts/repair_branding_defaults.py
docker compose -p clonexa exec -T api python scripts/verify_client_branding_ui.py
```

Para forzar el preset visual en empresas existentes:

```bash
docker compose -p clonexa exec -T api sh -lc "FORCE_BRANDING_DEFAULTS=true python scripts/repair_branding_defaults.py"
```

## Validar

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/api/v1/companies
```

Entrar a:

```text
http://localhost:8000/login
http://localhost:8000/client
http://localhost:8000/admin
```

Credenciales Voltage:

```text
admin@voltage.com
Clonexa2026!Voltage
```

En Admin Console:

```text
Voltage -> Configurar CRM -> Branding -> cambiar color principal -> Guardar branding -> abrir /client
```

El Client Portal debe aplicar el color guardado y mantener operativos:

- Técnicos
- Inventario / Materiales
- Billing
