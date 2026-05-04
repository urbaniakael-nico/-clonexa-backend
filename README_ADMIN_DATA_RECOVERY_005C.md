# CLONEXA Admin Console Data Recovery 005C

Micro-patch quirúrgico para recuperar el data layer de `/admin` sin migraciones y sin rediseñar la consola.

## Archivos incluidos

- `app/web/admin.js`
- `scripts/verify_admin_console_data.py`
- `README_ADMIN_DATA_RECOVERY_005C.md`
- `PATCH_MANIFEST.md`

## Qué recupera

- Carga real de empresas desde `/api/v1/companies`
- Carga real de paquetes desde `/api/v1/packages`
- Carga real de módulos desde `/api/v1/modules`
- Health real desde `/health`
- Contadores reales
- Tabla de empresas
- Detalle de empresa
- Módulos activos por empresa
- Activación de paquete por empresa
- Creación de empresa
- Usuarios de acceso si los endpoints existen
- Botón `Configurar CRM` sin bloquear la consola si `experience` falla

## Aplicar

```bash
cd C:\Users\valef\OneDrive\Desktop\CLONEXA\clonexa_backend
unzip clonexa_admin_console_data_recovery_005c.zip -d .
docker compose -p clonexa down
docker compose -p clonexa up --build -d
```

## Validar API

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/api/v1/companies
curl http://127.0.0.1:8000/api/v1/modules
curl http://127.0.0.1:8000/api/v1/packages
```

## Validar datos internos

```bash
docker compose -p clonexa exec -T api python scripts/verify_admin_console_data.py
```

Salida esperada:

```text
CLONEXA ADMIN DATA CHECK
companies: 4
modules: <mayor a 0>
packages: 4
company_users: <según entorno>
status: OK
```

## Validar navegador

Abrir:

```text
http://localhost:8000/admin
```

Debe verse:

- Total empresas real.
- Total paquetes real.
- Total módulos real.
- Empresas activas real.
- Tabla con Voltage, Radio Despecho, Mundo Case y Velvet.
- Detalle al seleccionar empresa.
- Módulos activos.
- Usuarios de acceso o mensaje claro si el endpoint no está disponible.
- Botón Configurar CRM operativo sin bloquear el resto de la consola.
