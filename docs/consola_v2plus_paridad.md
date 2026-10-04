# Consola v2+ · Inventario de paridad con Admin V2

Fuente: lectura de `app/web/admin_v2.js` y `app/web/admin_v2.html` (Admin V2 no se modifica).
Objetivo: cada acción de Admin V2 existe en v2+ y hace **exactamente** lo mismo: mismo
endpoint, mismo método y mismo cuerpo. Solo cambian el diseño y el orden.

- Las rutas se escriben con `{}` donde Admin V2 interpola una variable (`${companyId}`,
  `${API}` = `/api/v1`). `cxJsonRequest(path)` antepone `/api/v1`.
- `tests/admin_v2plus_parity_inventory.test.cjs` extrae de `admin_v2.js` **todas** las
  llamadas (`apiGet/apiPost/apiPut/apiPatch`, `cxJsonRequest` y `fetch`) y falla si alguna
  ruta no aparece en esta tabla. Así ninguna función se pierde en el camino.
- **Estado en v2+**: `migrado`, `pendiente · Fase N`, `no aplica` (con el motivo) o
  `no se migra a v2+ · decisión del dueño`. Paridad: ver la sección "Paridad".

## Vistas y pestañas de Admin V2

| Vista (`data-view`) | Contenido |
|---|---|
| `dashboard` | contadores, actividad de mini paneles por empresa, accesos rápidos |
| `companies` | lista con filtros, crear empresa, Ficha (Company Command Center) |
| `users` | Acceso Maestro global (dueño de cada empresa) |
| `packages` | catálogo y builder de paquetes, mini-panel-settings |
| `modules` | catálogo global de módulos (crear, eliminar, filtros) |
| `access` | links de acceso por empresa (portal, mini paneles, QR) |
| `health` | salud del sistema y sesiones de Admin V2 |
| `landing` | analítica de la landing |
| `crm` | panel sin entrada en el menú (`data-view-panel="crm"`) |

Pestañas de la Ficha (`data-detail-tab`): `resumen`, `módulos`, `paquete`, `branding`,
`accesos`, `reset`. El renderizador también tiene `usuarios` y `crm`, pero no están en la
lista visible: Admin V2 las devuelve a `resumen` (ver "Hallazgos en Admin V2").

## Acciones con petición al servidor

| ID | Dónde en v2 | Acción (`data-*` / formulario) | Función v2 | Petición | Cuerpo | Estado en v2+ |
|---|---|---|---|---|---|---|
| D01 | Dashboard | actividad por empresa (ventas) | `loadCompanyActivity023A` | `GET /api/v1/mini-panel-sales/companies/{}/summary?panel_type=sales` | — | no aplica · reemplazado por `/admin-v2/api/overview` (Centro de mando) |
| D02 | Dashboard | actividad por empresa (cotizaciones) | `loadCompanyActivity023A` | `GET /api/v1/mini-panel-quotes/companies/{}/summary?panel_type=all` | — | no aplica · reemplazado por `/admin-v2/api/overview` |
| D03 | Dashboard | actividad por empresa (notas) | `loadCompanyActivity023A` | `GET /api/v1/mini-panel-notes/companies/{}/summary?panel_type=sales` | — | no aplica · reemplazado por `/admin-v2/api/overview` |
| D04 | Dashboard | actividad por empresa (referencias) | `loadCompanyActivity023A` | `GET /api/v1/references-v1/companies/{}/summary` | — | no aplica · reemplazado por `/admin-v2/api/overview` |
| H01 | Salud | estado del sistema (`#healthRefreshBtn`) | `loadHealth` | `GET /health` | — | pendiente · Fase 3 (Salud) |
| H02 | Salud | estado del sistema (respaldo) | `loadHealth` | `GET /api/v1/health` | — | pendiente · Fase 3 (Salud) |
| H03 | Salud | sesiones de Admin V2 (`data-refresh-admin-v2-sessions`) | `loadAdminV2Sessions026H` | `GET /admin-v2/api/sessions` | — | pendiente · Fase 3 (Salud) |
| H04 | Salud | cerrar sesión de Admin V2 (`data-close-admin-v2-session`) | `closeAdminV2Session026H` | `POST /admin-v2/api/sessions/{}/close` | `{}` | pendiente · Fase 3 (Salud) |
| L01 | Landing | analítica (`data-refresh-landing-analytics`, `#landingFilters025S`, `data-reset-landing-filters`) | `loadLandingAnalytics025R` | `GET /api/v1/landing-analytics/summary?{}` | — | pendiente · Fase 3 (Landing analytics) |
| C01 | Empresas | lista | `loadCompanies` | `GET /api/v1/companies` | — | pendiente · Fase 2 (commit 4, Empresas) |
| C02 | Empresas | crear empresa (`#createCompanyForm`) | `createCompany` | `POST /api/v1/companies` | `{name, slug, timezone, plan}` | pendiente · Fase 2 (commit 4, Empresas) |
| C03 | Empresas | alta del dueño en el mismo flujo de crear | `createCompany` | `POST /api/v1/companies/{}/users` | `{name, full_name, email, password, temporary_password, role:"company_admin", status:"active", must_change_password:true}` | pendiente · Fase 2 (commit 4, Empresas) |
| C04 | Empresas / Ficha | cambiar estado (`data-company-status` + `data-status`) y archivar (`data-archive-company`, estado `deleted`) | `updateCompanyStatus` (1.er intento) | `PATCH /api/v1/companies/{}/status` | `{status}` | pendiente · Fase 2 (commit 4, Empresas) |
| C05 | Empresas / Ficha | mismo flujo, 2.º intento si el 1.º falla | `updateCompanyStatus` | `PATCH /api/v1/companies/{}` | `{status}` | pendiente · Fase 2 (commit 4, Empresas) |
| C06 | Empresas / Ficha | mismo flujo, 3.er intento si el 2.º falla | `updateCompanyStatus` | `PUT /api/v1/companies/{}` | `{status}` | pendiente · Fase 2 (commit 4, Empresas) |
| F01 | Ficha · Resumen / Módulos | módulos de la empresa | `loadCompanyModules` | `GET /api/v1/companies/{}/modules?enabled_only=false` | — | pendiente · Fase 2 (commit 5, Ficha) |
| F02 | Ficha · Paquete | catálogo de paquetes | `loadPackages` | `GET /api/v1/packages` | — | pendiente · Fase 2 (commit 5, Ficha) |
| F03 | Ficha · Paquete | detalle de cada paquete | `loadPackages` | `GET /api/v1/packages/{}` | — | pendiente · Fase 2 (commit 5, Ficha) |
| F04 | Ficha · Paquete | activar paquete (`#activatePackageForm`) y paquete al crear empresa | `activateCompanyPackage` | `POST /api/v1/companies/{}/activate-package` | `{package_code, settings:{}}` | pendiente · Fase 2 (commit 5, Ficha) |
| U01 | Acceso Maestro / Ficha | usuarios de la empresa | `loadCompanyUsers` | `GET /api/v1/companies/{}/users` | — | pendiente · Fase 2 (commit 5, Ficha · Usuarios y accesos) |
| U02 | Acceso Maestro | crear acceso maestro (`#createUserForm`) | `createCompanyUser` | `POST /api/v1/companies/{}/users` | igual que C03 | pendiente · Fase 2 (commit 5, Ficha · Usuarios y accesos) |
| U03 | Acceso Maestro | clave temporal (`data-reset-password`, `data-owner-reset-form`, `data-owner-reset-input`) | `resetCompanyUserPassword` | `POST /api/v1/companies/{}/users/{}/reset-password` | `{password}` si se escribió una; si no `{}` | pendiente · Fase 2 (commit 5, Ficha · Usuarios y accesos) |
| U04 | Acceso Maestro | desbloquear (`data-unlock-user`) | `unlockCompanyUser` | `POST /api/v1/companies/{}/users/{}/unlock` | `{}` | pendiente · Fase 2 (commit 5, Ficha · Usuarios y accesos) |
| U05 | Acceso Maestro | activar / desactivar (`data-toggle-user` + `data-status`) | `toggleCompanyUser` | `PUT /api/v1/companies/{}/users/{}` | `{status}` | pendiente · Fase 2 (commit 5, Ficha · Usuarios y accesos) |
| A01 | Ficha · Accesos | política de acceso por IP | `loadCompanyAccessPolicy026G` | `GET /api/v1/companies/{}/access-policy` | — | pendiente · Fase 2 (commit 5, Ficha · Usuarios y accesos) |
| A02 | Ficha · Accesos | guardar política de acceso (`#companyIpAccessPolicyForm026G`) | `saveCompanyAccessPolicy026G` | `PUT /api/v1/companies/{}/access-policy` | `{enabled, scopes:{<scope>:{enabled, allowed_ips[]}}}` | pendiente · Fase 2 (commit 5, Ficha · Usuarios y accesos) |
| A03 | Ficha · Accesos | política de sesión | `loadCompanySessionPolicy026H` | `GET /api/v1/companies/{}/session-policy` | — | pendiente · Fase 2 (commit 5, Ficha · Usuarios y accesos) |
| A04 | Ficha · Accesos | guardar política de sesión (`#companySessionPolicyForm026H`) | `saveCompanySessionPolicy026H` | `PUT /api/v1/companies/{}/session-policy` | `{enabled, mode, scopes:{<scope>:{enabled, max_sessions}}}` | pendiente · Fase 2 (commit 5, Ficha · Usuarios y accesos) |
| A05 | Ficha · Accesos | sesiones abiertas (`data-refresh-access-sessions`) | `loadCompanyAccessSessions026H` | `GET /api/v1/companies/{}/access-sessions?include_closed=true` | — | pendiente · Fase 2 (commit 5, Ficha · Usuarios y accesos) |
| A06 | Ficha · Accesos | cerrar una sesión (`data-close-access-session`) | `closeCompanySession026H` | `POST /api/v1/companies/{}/access-sessions/{}/close` | `{}` | pendiente · Fase 2 (commit 5, Ficha · Usuarios y accesos) |
| A07 | Ficha · Accesos | cerrar todas (`data-close-company-sessions`) | `closeAllCompanySessions026H` | `POST /api/v1/companies/{}/access-sessions/close` | `{}` | pendiente · Fase 2 (commit 5, Ficha · Usuarios y accesos) |
| B01 | Ficha · Branding / CRM | experiencia (branding + CRM) | `loadCompanyExperience` | `GET /api/v1/companies/{}/experience` | — | pendiente · Fase 2 (commit 5, Ficha · resumen de marca) |
| B02 | Ficha · Branding | guardar branding (`#brandingForm`, `data-branding-*`) | `saveBranding` | `PUT /api/v1/companies/{}/experience/branding` | campos del formulario (`cxReadBrandingForm`) | pendiente · Fase 3 (Estudio de marca) |
| B03 | Ficha · Branding | restaurar valores (`data-ensure-defaults`) | `ensureDefaults` | `POST /api/v1/companies/{}/experience/ensure-defaults` | `{}` | pendiente · Fase 3 (Estudio de marca) |
| T01 | Ficha · Accesos (Bot) | configuración Telegram | `loadTelegramBotConfig` | `GET /api/v1/bots/companies/{}/telegram` | — | pendiente · Fase 2 (commit 5, Ficha · Bots) |
| T02 | Ficha · Accesos (Bot) | estado del webhook | `loadTelegramBotConfig` | `GET /api/v1/company-bots-v1/companies/{}/telegram/status` | — | pendiente · Fase 2 (commit 5, Ficha · Bots) |
| T03 | Ficha · Accesos (Bot) | guardar bot (`#telegramBotConfigForm`, `data-bot-flow-company`) | `saveTelegramBotConfig` | `PUT /api/v1/bots/companies/{}/telegram` | campos del formulario con `token` y `name` recortados y **sin** `flow_code` | pendiente · Fase 2 (commit 5, Ficha · Bots) |
| T04 | Ficha · Accesos (Bot) | probar (`data-test-telegram-bot`) | `testTelegramBotConfig` | `POST /api/v1/bots/companies/{}/telegram/test` | `{}` | pendiente · Fase 2 (commit 5, Ficha · Bots) |
| T05 | Ficha · Accesos (Bot) | activar webhook / listener (`data-start-telegram-listener`) | `startTelegramBotListener` | `POST /api/v1/company-bots-v1/companies/{}/telegram/activate-webhook` | `{flow_code}` | pendiente · Fase 2 (commit 5, Ficha · Bots) |
| T06 | Ficha · Accesos (Bot) | desactivar (`data-deactivate-telegram-bot`) | `deactivateTelegramBotConfig` | `POST /api/v1/bots/companies/{}/telegram/deactivate` | `{}` | pendiente · Fase 2 (commit 5, Ficha · Bots) |
| R01 | Ficha · Reset operativo | simular (`data-reset-dry-run`) y ejecutar (`data-reset-execute`, `data-reset-confirm-slug`, `data-reset-confirm-text`, `data-reset-scope`) | `runCompanyOperationalReset` | `POST /api/v1/companies/{}/operational-reset` | `{dry_run, scopes[], confirm_slug, confirm_text}` | pendiente · Fase 2 (commit 5, Ficha · Datos) |
| M01 | Módulos | catálogo global | `loadModules` | `GET /api/v1/modules` | — | pendiente · Fase 3 (Catálogo · Módulos) |
| M02 | Módulos | crear módulo global | `cxBindModuleManagementEvents` | `POST /api/v1/modules` | `{code, name, description, category, is_active:true}` | pendiente · Fase 3 (Catálogo · Módulos) |
| M03 | Módulos | eliminar módulo global (`data-cx-module-delete`, escribir el código) | `cxBindModuleManagementEvents` | `DELETE /api/v1/modules/{}?confirm={}` | — | pendiente · Fase 3 (Catálogo · Módulos, limpieza) |
| M04 | Ficha · Módulos | encender / apagar módulo (`data-cx-company-module-toggle` + `data-action`) | `cxBindModuleManagementEvents` | `POST /api/v1/companies/{}/modules/{}/{}` | `{settings:{}}` | pendiente · Fase 2 (commit 5, Ficha · encender/apagar) |
| M05 | Ficha · Módulos | configuración QR (`#companyQrConfigForm025N`) | `cxSaveCompanyQrConfig025N` | `POST /api/v1/companies/{}/modules/{}/activate` | `{settings:{qr_config}}` | pendiente · Fase 3 (Interruptores: configuración QR) |
| P01 | Paquetes | ajustes de mini panel del paquete | `loadPackageMiniPanelSettings` | `GET /api/v1/packages/{}/mini-panel-settings` | — | pendiente · Fase 3 (Catálogo · Paquetes) |
| P02 | Paquetes | guardar ajustes de mini panel | `savePackageMiniPanelSettings` | `PUT /api/v1/packages/{}/mini-panel-settings` | `mini_panel` del builder | pendiente · Fase 3 (Catálogo · Paquetes) |
| P03 | Paquetes | editar paquete (`data-package-builder-edit`, `data-builder-*`) | `cxSavePackageFromBuilder` | `PUT /api/v1/packages/{}` | `package_payload` | pendiente · Fase 3 (Catálogo · Paquetes) |
| P04 | Paquetes | crear paquete (`data-package-builder-form`) | `cxSavePackageFromBuilder` | `POST /api/v1/packages` | `package_payload` | pendiente · Fase 3 (Catálogo · Paquetes) |
| W01 | Ficha · Módulos (pedidos por mesero) | productos para porciones | `cxEnsureProductPickerOptions030S` | `GET /api/v1/hospitality/companies/{}/inventory-lite?limit=500` | — | no se migra a v2+ · decisión del dueño |
| W02 | Ficha · Módulos (cx-wo) | meseros | `loadCompanyWaiterOrderingMeseroUsers030S` | `GET /api/v1/companies/{}/mini-panel-users?panel_type=mesero` | — | no se migra a v2+ · decisión del dueño |
| W03 | Ficha · Módulos (cx-wo) | porciones | `loadCompanyWaiterOrderingPortions030S` | `GET /api/v1/companies/{}/waiter-ordering/portions` | — | no se migra a v2+ · decisión del dueño |
| W04 | Ficha · Módulos (cx-wo) | meta diaria del mesero (`data-cx-wo-mesero-goal`) | `cxSaveMeseroDailyGoal030S` | `PUT /api/v1/companies/{}/waiter-ordering/mesero-users/{}/daily-goal` | `{daily_goal}` | no se migra a v2+ · decisión del dueño |
| W05 | Ficha · Módulos (cx-wo) | foto de producto (`data-cx-wo-product-image`) | `cxSaveProductImage030S` | `POST /api/v1/companies/{}/waiter-ordering/products/{}/image` | `FormData` (imagen) | no se migra a v2+ · decisión del dueño |
| W06 | Ficha · Módulos (cx-wo) | grupo de porciones (`data-cx-wo-portion-save`) | `cxSaveWaiterOrderingPortionGroup030S` | `PUT /api/v1/companies/{}/waiter-ordering/portions/{}` | `{group_label, members}` | no se migra a v2+ · decisión del dueño |
| W07 | Ficha · Módulos (cx-wo) | categorías | `loadCompanyWaiterOrderingCategories026K` | `GET /api/v1/companies/{}/waiter-ordering/categories` | — | no se migra a v2+ · decisión del dueño |
| W08 | Ficha · Módulos (cx-wo) | usuarios de cocina | `loadCompanyWaiterOrderingCocinaUsers026K` | `GET /api/v1/companies/{}/mini-panel-users?panel_type=cocina` | — | no se migra a v2+ · decisión del dueño |
| W09 | Ficha · Módulos (cx-wo) | configuración (`#companyWaiterOrderingForm026K`) | `cxSaveCompanyWaiterOrderingConfig026K` | `POST /api/v1/companies/{}/modules/waiter_ordering/activate` | `{settings}` | no se migra a v2+ · decisión del dueño |
| W10 | Ficha · Módulos (cx-wo) | categoría (`data-cx-wo-category`) | `cxSaveCompanyWaiterOrderingCategory026K` | `PUT /api/v1/companies/{}/waiter-ordering/categories/{}` | `{station, …}` | no se migra a v2+ · decisión del dueño |
| W11 | Ficha · Módulos (cx-wo) | foto de categoría | `cxSaveCompanyWaiterOrderingCategory026K` | `POST /api/v1/companies/{}/waiter-ordering/categories/{}/image` | `FormData` (imagen) | no se migra a v2+ · decisión del dueño |
| W12 | Ficha · Módulos (cx-wo) | estaciones de cocina (`data-cx-wo-cocina-user`) | `cxSaveCompanyWaiterOrderingCocinaStations026K` | `PUT /api/v1/companies/{}/waiter-ordering/cocina-users/{}/stations` | `{stations}` | no se migra a v2+ · decisión del dueño |
| N01 | Ficha · Módulos (nómina Colombia) | parámetros (`data-payco-admin-load`) | `cxPayCoAdminLoad048O` | `GET /api/v1/payroll-co/params` | — | pendiente · Fase 3 (Nómina Colombia, payco) |
| N02 | Ficha · Módulos (payco) | plantilla del año (`data-payco-admin-new`) | `cxPayCoAdminLoad048O` | `GET /api/v1/payroll-co/params/{}/template` | — | pendiente · Fase 3 (payco) |
| N03 | Ficha · Módulos (payco) | guardar año (`data-payco-admin-save`, `data-payco-admin-form`) | `cxPayCoAdminLoad048O` | `PUT /api/v1/payroll-co/params/{}` | parámetros del año | pendiente · Fase 3 (payco) |
| S01 | Ficha (corte de sesiones, 048Q) | política de corte diario (`data-sess-policy-048q`) | `cxSessPolicyPanel048Q` | `GET /api/v1/workforce-sessions/companies/{}/policy` | — | pendiente · Fase 3 (Interruptores) |
| S02 | Ficha (corte de sesiones, 048Q) | guardar corte (`data-sess-policy-form-048q`) | `cxSessPolicyPanel048Q` | `PUT /api/v1/workforce-sessions/companies/{}/policy` | `{cutoff_time, alert_after_hours}` | pendiente · Fase 3 (Interruptores) |
| X01 | Ficha · Módulos (mini paneles R6B) | asignación de mini paneles | `loadRemoteConfig022A` | `GET /api/v1/companies/{}/modules?enabled_only=true` | — | pendiente · Fase 2 (commit 5, Ficha · mini paneles) |
| X02 | Ficha · Módulos (mini paneles R6B) | guardar asignación (`data-cx-mp-r6b-*`) | `saveRemote` | `POST /api/v1/companies/{}/modules/mini_panel/activate` | `{settings:{mini_panel_modules}}` | pendiente · Fase 2 (commit 5, Ficha · mini paneles) |
| Z01 | Barra superior | cerrar sesión (`data-admin-v2-logout`) | `bindEvents` | `POST /admin-v2/logout` | — | pendiente · Fase 3 (Accesos y sesiones) |

## Acciones sin petición al servidor

| ID | Dónde en v2 | Acción | Qué hace | Estado en v2+ |
|---|---|---|---|---|
| N-01 | todas | `data-view`, `data-nav-view` | cambia de vista | migrado (menú de v2+) |
| N-02 | Empresas | `data-company-filter` (Visibles / Todas / Activas / Inactivas / Archivadas) | filtra la lista | pendiente · Fase 2 (commit 4, Empresas) |
| N-03 | Empresas | `data-select-company` (+ `data-detail-tab`) | abre la Ficha en una pestaña | pendiente · Fase 2 (commit 5, Ficha) |
| N-04 | Ficha | `data-detail-tab` | cambia de pestaña | pendiente · Fase 2 (commit 5, Ficha) |
| N-05 | Empresas | `data-generate-create-owner-password` | genera la clave temporal del dueño al crear | pendiente · Fase 2 (commit 4, Empresas) |
| N-06 | Acceso Maestro | `data-generate-password-for-form` | genera clave en el formulario | pendiente · Fase 2 (commit 5, Ficha) |
| N-07 | varios | `data-copy` (ID, email, clave, links, IP, health) | copia al portapapeles | pendiente · Fase 2 (commits 4-5, por pantalla) |
| N-08 | varios | `data-open-client` | abre `/client?company_id=…` (vista previa como empresa) | migrado ("Entrar como empresa" en el Centro de mando) |
| N-09 | Acceso Maestro | `data-master-access-company`, `data-master-access-clear`, `#masterAccessFilters025Y` | elige empresa / filtra la vista global de dueños | pendiente · Fase 3 (Acceso Maestro global); dentro de la Ficha · Fase 2 (commit 5) |
| N-10 | Ficha · Branding | `data-branding-palette`, `data-branding-color`, `data-branding-hex`, `data-branding-basic`, `data-open-branding-preview`, `data-close-branding-preview` | paleta y vista previa | pendiente · Fase 3 (Estudio de marca) |
| N-11 | Ficha · Accesos | links por empresa (portal, mini paneles por rol, QR) con `data-copy` | arma y copia links | pendiente · Fase 2 (commit 5, "Copiar links") |
| N-12 | Módulos | `data-reset-module-filters`, `data-cx-company-module-filter`, `data-cx-company-module-search`, `data-cx-module-info` | filtros y ayuda del catálogo | pendiente · Fase 3 (Catálogo · Módulos) |
| N-13 | Paquetes | `data-package-builder-reset`, `data-builder-mini-*`, `data-package-mini-summary` | estado del builder | pendiente · Fase 3 (Catálogo · Paquetes) |
| N-14 | Ficha · Módulos | `data-cx-wo-product-picker` | ayudas de cx-wo (elegir productos para porciones) | no se migra a v2+ · decisión del dueño |
| N-16 | Ficha · Módulos (nómina Colombia) | `data-payco-switch-048r` | interruptor de payco (antes iba junto con N-14) | pendiente · Fase 3 (Nómina Colombia) |
| N-15 | Barra superior | `#refreshBtn`, `#openAdminLegacyBtn`, `#openClientBtn`, `#newCompanyFocusBtn` | refrescar, abrir `/admin` y `/client`, ir a crear empresa | migrado (Refrescar y "+ Nueva empresa" en el Centro de mando) |

## Decisiones del dueño (Fase 2)

- **La consola de mando no configura la operación del cliente.** Pedidos por mesero
  (W01–W12: categorías, imágenes de estación, porciones, imágenes de producto, cocina y
  cantidades, estaciones de cocineros, meta del mesero) y sus ayudas (N-14) **no se migran a
  v2+**. Siguen en Admin V2 (ver la sección siguiente).
- **Las ventas de los clientes no son un dato del Centro de mando.** Varias empresas no
  registran ventas sino producción o conexión; medirlas por ventas las marcaba "dormidas" por
  error. La señal de vida es la **conexión** (commit 3). Por eso D01–D04 siguen en "no aplica".
- **Empresas Demo y Registradas** (commit 4): `companies.settings_json.kind`, sin migración de
  esquema. Clonar como demo y eliminar definitivo son acciones nuevas, sin equivalente en v2.
- **Ficha sin configuración operativa** (commit 5): en módulos y mini paneles solo se enciende
  y apaga. La marca completa es la Fase 3 (Estudio de marca).

## Configuración que hoy solo existe en Admin V2

Verificado en el código: **ni `app/web/client.js` ni `app/api/v1/endpoints/carta.py` cubren**
estas cuatro configuraciones. El panel del cliente solo usa de `waiter-ordering` el documento
de venta (`sale-document/config`, `sale-document/reprint`) y la lectura de imágenes de
producto. No tienen equivalente en el panel del cliente:

| Configuración | Filas de este inventario | Dónde vive hoy |
|---|---|---|
| estación por categoría y por cocinero | W07, W10, W08, W12 | Admin V2 · Ficha · Módulos (cx-wo) |
| meta diaria del mesero | W02, W04 | Admin V2 · Ficha · Módulos (cx-wo) |
| grupos de porciones | W01, W03, W06 (y N-14) | Admin V2 · Ficha · Módulos (cx-wo) |
| cocina y cantidades | W09 (`settings` de `waiter_ordering`) | Admin V2 · Ficha · Módulos (cx-wo) |

**Siguen disponibles en Admin V2** hasta que se decida moverlas al panel del cliente o
retirarlas. No se borran. La Ficha de v2+ deja un enlace discreto "Configuración avanzada en
Admin V2" para llegar a ellas.

## Fases

- **Fase 2** (este trabajo, 6 commits): 1) este inventario · 2) seguridad de base (cabeceras,
  CSP de v2+, XSS de mini paneles, validación de marca) · 3) Centro de mando por conexión ·
  4) Empresas (Demos y Registradas, crear, estado, archivar, cambiar de tipo, clonar como demo,
  eliminar definitivo) · 5) Ficha de empresa (resumen, paquete, encender/apagar módulos y mini
  paneles, usuarios y accesos, bots, datos, resumen de marca) · 6) Auditoría (nuevo, sin
  equivalente en v2).
- **Fase 3**: Estudio de marca · Interruptores (incluida la configuración QR y el corte de
  sesiones) · Catálogo de Paquetes y Módulos · Acceso Maestro global · Salud · Landing ·
  Nómina Colombia (payco) · Paleta Ctrl+K.

## Paridad

Paridad = filas `migrado` ÷ filas que no son `no aplica` ni `no se migra a v2+`. La prueba
`tests/admin_v2plus_parity_inventory.test.cjs` revisa que cada ruta de `admin_v2.js` tenga
fila, que cada fila tenga un estado válido y que ninguna fila apunte a una ruta que ya no
existe.

## Hallazgos en Admin V2 (reportados, no corregidos)

1. `updateCompanyStatus` reintenta con `PATCH /companies/{id}` y luego `PUT /companies/{id}`
   ante **cualquier** error del primer intento (incluidos 400, 401 o 422), no solo cuando la
   ruta no existe. Un rechazo de validación puede terminar en otra ruta, y el mensaje que ve
   el usuario es el del último intento, no el real. v2+ lo replica tal cual por paridad.
2. El manejador principal de `data-open-client` abre `/client` **sin** `company_id`. Funciona
   solo porque un segundo manejador (bloque `CLONEXA_CLIENT_COMPANY_ID_ROUTING_R2`) captura el
   clic antes y detiene la propagación. Si ese bloque se quita, se rompe.
3. Las pestañas `usuarios` y `crm` existen en `renderCompanyDetailTab` pero no en la lista
   visible: cualquier enlace a ellas cae en `resumen`. El CRM solo se ve en la vista `crm`.
4. Hay textos con codificación doble (mojibake) en la interfaz: `Ã¢â‚¬â€`, `Ã¢â‚¬Â¦`,
   `cargÃƒÂ³`, `estÃƒÂ¡` (por ejemplo en `truncate`, en el plan vacío "—" y en avisos).
5. Archivar empresa solo pide escribir el slug (no hay simulación previa ni confirmación final
   adicional); el reset operativo sí tiene simulación, slug, texto y confirmación final.
6. La asignación de mini paneles (bloque R6B) guarda primero en `localStorage` y luego en el
   servidor con `fetch` sin revisar la respuesta: si el servidor rechaza, la pantalla queda
   mostrando una asignación que no se guardó.
