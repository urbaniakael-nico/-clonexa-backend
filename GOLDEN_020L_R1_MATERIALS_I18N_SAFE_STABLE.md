# GOLDEN_020L_R1_MATERIALS_I18N_SAFE_STABLE_2026_05_08_113759

Estado blindado:

- Panel cliente estable.
- Dashboard i18n seguro funcionando.
- Inventario i18n seguro funcionando.
- GPS i18n seguro funcionando.
- Bots i18n seguro funcionando.
- CRM Campo i18n seguro funcionando.
- Reportes i18n seguro funcionando en R3.
- KPIs i18n seguro funcionando en R3.
- Materiales i18n seguro funcionando en R1.
- Ajustes funcional.
- Cerrar sesión funcional.
- No se toca client.js.
- No hay language_guard.
- No hay workforce_i18n activo.

Scripts activos:

- app/web/client_dashboard_i18n_safe.js
- app/web/client_inventory_i18n_safe.js
- app/web/client_gps_i18n_safe.js
- app/web/client_bots_i18n_safe.js
- app/web/client_crm_i18n_safe.js
- app/web/client_reports_i18n_safe.js
- app/web/client_kpis_i18n_safe.js
- app/web/client_materials_i18n_safe.js

Regla de avance:

- Módulo simple: script externo seguro + diccionario completo.
- Módulo medio/complejo: entrar directo con super diccionario.
- No tocar client.js.
- No tocar Ajustes.
- No tocar navegación global.
- No usar language_guard.
- No blindar si existe mezcla de idiomas.

Siguiente fase:

- 020M Nómina / Payroll i18n seguro.
- 020N Workforce / Personal i18n quirúrgico.
