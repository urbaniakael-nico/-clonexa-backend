# CLONEXA 015C-R6C — Material Returns Order State Fix

Corrige que el botón Registrar devolución no tome la orden seleccionada.

Cambios:
- Conserva la orden seleccionada en estado de frontend (`window.__cxMaterialsReturnOrder`).
- El checklist guarda `data-material-return-selected-order`.
- Cada Label/SKU marcado incluye `data-material-return-unit-order`.
- El POST envía `order_number` también en body.
- Backend acepta `payload.order_number` como fallback.
- No toca Web App, Bot, Inventario ni Admin V2.
