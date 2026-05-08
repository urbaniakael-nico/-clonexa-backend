# GOLDEN_020F_R1_INVENTORY_I18N_SAFE_STABLE_2026_05_07_191858

Estado blindado:

- Panel cliente estable.
- Dashboard i18n seguro funcionando.
- Inventario i18n seguro funcionando.
- Ajustes funcional.
- Cerrar sesión funcional.
- No se toca client.js.
- No hay language_guard.
- No hay workforce_i18n activo.
- Script activo:
  - app/web/client_dashboard_i18n_safe.js
  - app/web/client_inventory_i18n_safe.js

Regla:
- Cada módulo nuevo se traduce con script externo seguro.
- El script solo actúa si su módulo está visible.
- No debe tocar Ajustes.
- No debe tocar navegación global.
- No debe bloquear carga.

Siguiente fase recomendada:
- 020G GPS i18n seguro.
