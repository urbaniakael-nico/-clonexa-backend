# GOLDEN_020O_R2_CLIENT_PORTAL_I18N_COMPLETE_STABLE_2026_05_08_125530

Estado blindado:

PANEL CLIENTE I18N COMPLETO Y ESTABLE

Módulos validados:
- Dashboard
- Inventario
- GPS
- Bots
- CRM Campo
- Reportes
- KPIs
- Materiales
- Nómina / Payroll
- Workforce / Staff
- Workforce History
- Workforce Attendance
- Core Settings / Ajustes
- Cerrar sesión

Scripts i18n activos:
- app/web/client_dashboard_i18n_safe.js
- app/web/client_inventory_i18n_safe.js
- app/web/client_gps_i18n_safe.js
- app/web/client_bots_i18n_safe.js
- app/web/client_crm_i18n_safe.js
- app/web/client_reports_i18n_safe.js
- app/web/client_kpis_i18n_safe.js
- app/web/client_materials_i18n_safe.js
- app/web/client_payroll_i18n_safe.js
- app/web/client_workforce_i18n_safe.js
- app/web/client_workforce_history_i18n_safe.js
- app/web/client_core_settings_i18n_safe.js

Estado técnico:
- No se toca client.js.
- No se usa language_guard.
- No se bloquea carga del portal.
- Los scripts trabajan solo sobre su módulo visible.
- Core Settings tiene traducción propia del núcleo.
- El idioma se conserva desde clonexa_client_language.
- Aplica a empresas actuales y empresas nuevas.
- Los módulos existentes activados en nuevas empresas heredan este comportamiento.

Regla SaaS obligatoria para nuevos módulos:
- Todo módulo nuevo debe traer i18n desde nacimiento.
- Crear archivo externo client_<module>_i18n_safe.js.
- Usar super diccionario ES / EN / FR.
- Detectar pantalla por data attributes, clases o texto único.
- No tocar client.js.
- No tocar navegación global.
- No tocar Ajustes.
- No blindar si existe mezcla de idiomas.

Siguiente fase:
- Chequeo general módulo por módulo.
- Luego continuar creación/activación de módulos faltantes usando plantilla i18n obligatoria.
