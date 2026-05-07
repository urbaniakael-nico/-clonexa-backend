# GOLDEN_020D_R1_DASHBOARD_I18N_SAFE_STABLE_2026_05_07_183825

Estado blindado:

- Panel cliente estable.
- Módulo Ajustes funcional.
- Botón Ajustes visible.
- Botón Cerrar sesión visible.
- Core Settings estable.
- Dashboard i18n seguro externo funcionando.
- No se modifica client.js para traducción.
- Script seguro activo: app/web/client_dashboard_i18n_safe.js
- Carga desde client.html después de client_core_settings.js.

Regla:
- No usar Google Translate embebido.
- No usar runtime global invasivo.
- No hacer regex masivo sobre client.js.
- Todo i18n futuro debe ser externo seguro o refactor nativo controlado por módulo.

Siguiente fase:
- 020E Workforce / Personal i18n seguro.
