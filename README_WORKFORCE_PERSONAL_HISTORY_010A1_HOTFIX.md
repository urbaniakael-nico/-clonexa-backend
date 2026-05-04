# CLONEXA 010A.1 — Workforce Personal Historial Hotfix

## Objetivo
Corregir el error `Internal Server Error` en la vista Historial de Personal y hacer que el historial sea funcional de inmediato.

## Qué corrige
- Evita 500 si Alembic no creó la tabla `workforce_personnel_history`.
- Crea la tabla e índices de forma idempotente desde el endpoint como red de seguridad.
- Genera registros base para empleados existentes, incluyendo archivados.
- Permite buscar por nombre, rol, estado, evento y notas.
- Si la tabla de auditoría falla, devuelve un fallback desde `employees` para que la pantalla no quede rota.

## Archivo incluido
- app/api/v1/endpoints/employees.py

## Validación
1. Abrir `/client?company_id=<empresa>`.
2. Ir a Personal.
3. Entrar a Historial.
4. Buscar por un empleado archivado, por ejemplo `santiago`.
5. Debe aparecer al menos un `Registro inicial` o `Registro actual`.
6. Editar/archivar/activar un empleado.
7. Volver a Historial y validar el evento.
