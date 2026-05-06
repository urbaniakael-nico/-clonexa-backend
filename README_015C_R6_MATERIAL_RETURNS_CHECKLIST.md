# CLONEXA 015C-R6 — Materiales Devoluciones Checklist por Orden

## Objetivo
Reemplaza la devolución manual por un buscador de órdenes y checklist real de Label/SKU entregados.

## Cambios
- /client → Materiales:
  - Número de orden funciona como buscador.
  - El botón Devolución precarga y consulta la orden.
  - Carga materiales de la orden agrupados.
  - Cada material se despliega con flecha.
  - Cada unidad entregada muestra checkbox.
  - Solo los checkboxes seleccionados se devuelven.
  - El campo de labels/SKU manual desaparece.

- Backend Materiales:
  - GET /api/v1/materials/companies/{company_id}/returns/search?q=
  - GET /api/v1/materials/companies/{company_id}/returns/orders/{order_number}
  - POST /api/v1/materials/companies/{company_id}/returns acepta unit_ids.
  - Devuelve múltiples líneas bajo el mismo número de orden.
  - Suma inventario por cada unidad seleccionada.
  - Actualiza material_order_units a returned.
  - Actualiza material_requests a returned_partial o returned.
