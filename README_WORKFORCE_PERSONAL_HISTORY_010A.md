# CLONEXA 010A — Workforce Personal Historial

## Objetivo

Agregar la opción **Historial** dentro del módulo **Workforce / Personal**.

La barra queda:

```text
+ Agregar fila | Guardar cambios | Historial | Volver
```

El historial permite consultar cambios de personal por rango de fechas, búsqueda, tipo de evento y exportación CSV.

## Qué incluye

- Nueva tabla PostgreSQL: `workforce_personnel_history`
- Backfill inicial de empleados existentes como `employee_baseline`
- Registro automático cuando se crea personal
- Registro automático cuando se edita personal
- Registro automático cuando se activa/inactiva/archiva/restaura personal
- Endpoint `GET /api/v1/employees/history`
- Endpoint `GET /api/v1/employees/history/{employee_id}`
- Vista nueva en `/client` dentro del módulo Personal
- Botón Historial al lado de `+ Agregar fila`, `Guardar cambios`, `Volver`
- Filtros por fecha, búsqueda y evento
- Exportación CSV del historial filtrado

## Archivos modificados

```text
app/api/v1/endpoints/employees.py
app/models/__init__.py
app/web/client.js
```

## Archivos nuevos

```text
app/models/workforce_personnel_history.py
app/schemas/workforce_personnel_history.py
alembic/versions/010a_workforce_personnel_history.py
```

## Aplicación

Desde PowerShell:

```powershell
cd "C:\Users\valef\OneDrive\Desktop\CLONEXA\clonexa_backend"

$Stamp = Get-Date -Format "yyyy_MM_dd_HHmmss"
$Backup = "..\backup_010a_workforce_personal_history_$Stamp"
New-Item -ItemType Directory -Force -Path $Backup | Out-Null

Copy-Item ".\app\api\v1\endpoints\employees.py" "$Backup\employees.py" -Force
Copy-Item ".\app\models\__init__.py" "$Backup\models__init__.py" -Force
Copy-Item ".\app\web\client.js" "$Backup\client.js" -Force
Copy-Item ".\alembic\versions" "$Backup\alembic_versions" -Recurse -Force

Expand-Archive -Path "$env:USERPROFILE\Downloads\clonexa_workforce_personal_history_010a.zip" -DestinationPath . -Force

docker compose -p clonexa up --build -d

Start-Sleep -Seconds 12

docker compose -p clonexa logs --tail=180 api
curl.exe http://127.0.0.1:8000/health
```

## Validación API

Usar un `company_id` real:

```powershell
curl.exe "http://127.0.0.1:8000/api/v1/employees/history?company_id=76974191-1dc6-4eb4-9b19-7d1e9ad82946&limit=20"
```

## Validación visual

1. Abrir `/client?company_id=<ID_EMPRESA>`
2. Entrar a Personal
3. Confirmar barra:
   `+ Agregar fila | Guardar cambios | Historial | Volver`
4. Click en Historial
5. Ver filtros Desde / Hasta / Buscar / Evento
6. Confirmar registros iniciales existentes como `Registro inicial`
7. Editar un empleado
8. Guardar
9. Entrar otra vez a Historial
10. Confirmar evento `Empleado editado`
11. Exportar CSV

## Reglas

- No usa `docker compose down -v`
- No borra datos
- No toca Admin V2
- No toca paquetes/módulos
- No crea módulo SaaS nuevo
- Historial queda dentro de Workforce / Personal
