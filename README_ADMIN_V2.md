# CLONEXA Admin Console V2

Nueva consola administrativa paralela disponible en:

```text
http://localhost:8000/admin-v2
```

No reemplaza `/admin`. No toca migraciones ni datos.

## Archivos incluidos

```text
app/web/admin_v2.html
app/web/admin_v2.css
app/web/admin_v2.js
app/web/admin_v2_routes.py
scripts/apply_admin_v2_route.py
scripts/verify_admin_v2.py
README_ADMIN_V2.md
PATCH_MANIFEST.md
```

## Aplicar en PowerShell

```powershell
cd C:\Users\valef\OneDrive\Desktop\CLONEXA\clonexa_backend
unzip clonexa_admin_console_v2_phase1.zip -d .
python scripts/apply_admin_v2_route.py
```

## Aplicar en Docker

```powershell
docker compose -p clonexa down
docker compose -p clonexa up --build -d
docker compose -p clonexa exec -T api python scripts/verify_admin_v2.py
```

Si el contenedor ya estaba arriba, también puedes registrar la ruta antes de reconstruir:

```powershell
python scripts/apply_admin_v2_route.py
docker compose -p clonexa up --build -d
```

## Validaciones

```powershell
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/api/v1/companies
curl http://127.0.0.1:8000/api/v1/packages
curl http://127.0.0.1:8000/api/v1/modules
curl http://127.0.0.1:8000/admin-v2
```

Abrir en navegador:

```text
http://localhost:8000/admin-v2
http://localhost:8000/admin
http://localhost:8000/client
```

## Funciones V2 incluidas

- Dashboard con métricas reales.
- Empresas reales desde `/api/v1/companies`.
- Paquetes reales desde `/api/v1/packages`.
- Módulos reales desde `/api/v1/modules`.
- Módulos activos por empresa desde `/api/v1/companies/{company_id}/modules`.
- Detalle de empresa con tabs internas.
- Usuarios de acceso si los endpoints existen.
- Crear usuario, reset password, unlock y activar/desactivar si los endpoints existen.
- Activar paquete en empresa.
- Resumen CRM / branding si `/experience` existe.
- Health del sistema.
- Accesos rápidos a `/admin`, `/client`, `/docs`, `/login`.

## Seguridad del patch

No incluye:

```text
migrations
Dockerfile
docker-compose.yml
login
client
field engine
```

No usa imports prohibidos:

```text
import prohibido de base de datos
import prohibido de Company
```
