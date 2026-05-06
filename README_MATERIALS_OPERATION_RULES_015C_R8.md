# CLONEXA 015C-R8 — Materials Operation Rules

Incluye reglas operativas para Materiales:
- Devolución disponible hasta 48h después de entrega.
- Consigna disponible hasta 24h después de entrega.
- Consigna parcial/total sin movimiento de inventario.
- Detalle de orden con observaciones.
- CSV con opción de depurar órdenes cerradas/no gestionables.
- Depuración por `archived_at/exported_at`, sin borrado físico.
- Mantiene devolución checklist y Web App funcional.

Archivos:
- app/api/v1/endpoints/materials.py
- app/web/client.js
