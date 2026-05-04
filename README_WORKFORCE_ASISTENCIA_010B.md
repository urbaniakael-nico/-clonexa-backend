# CLONEXA 010B — Workforce Asistencia MVP

Objetivo:
Agregar el botón **Asistencia** al lado de **Historial** dentro de Workforce / Personal.

Botones esperados:
`+ Agregar fila | Guardar cambios | Historial | Asistencia | Volver`

Funcionalidad incluida:
- Vista Asistencia dentro del contexto Workforce.
- Lista empleados activos/no archivados de la empresa.
- Acciones: Entrada, Pausa, Reanudar, Salida.
- Estado actual por empleado.
- Eventos persistidos en PostgreSQL.
- Tabla de estado actual persistida.
- CSV de asistencia.
- Safety-net backend: crea tablas si Alembic no alcanzó a correr.

Validación:
1. Abrir `/client?company_id=<empresa>`.
2. Entrar a Personal.
3. Confirmar botón Asistencia al lado de Historial.
4. Entrar a Asistencia.
5. Registrar Entrada.
6. Ver estado Trabajando.
7. Registrar Pausa.
8. Ver estado En pausa.
9. Reanudar.
10. Registrar Salida.
