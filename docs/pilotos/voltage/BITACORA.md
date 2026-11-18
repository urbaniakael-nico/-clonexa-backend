# Bitácora del piloto VOLTAGE

Fuente única de verdad del piloto. Empresa VOLTAGE: `f1e8f774-f052-49ca-880a-268805f07db0`
(slug `voltage_operation`). La 76974191 (ex-Urbania) está archivada: no tocar.

Operaciones (lugares de trabajo): **Virginia** (America/New_York, ET) y **Alabama**
(America/Chicago, CT). Bot de Telegram: @VOLTAGRBOT.

> Este archivo se creó el 2026-11-17. Lo anterior se resume desde las notas del proyecto;
> el detalle está en los commits citados.

## Estado actual (2026-11-18)

| Tema | Estado |
| --- | --- |
| Nómina EE. UU. (`us_payroll`, FLSA) | Encendida solo en VOLTAGE desde 2026-11-03 (b7f949f). Overtime > 40 h por semana laboral, pausas sin pago, hora del lugar. Tarifas pendientes (el dinero sale "Pendiente"). |
| Semana laboral y corte (por operación, desde 2026-11-18) | **Virginia**: domingo 00:00 a sábado 23:59 ET; corte cada 2 semanas con ancla domingo 01/11/2026 (01-14 nov, 15-28 nov, 29 nov-12 dic, 13-26 dic…). **Alabama**: lunes 00:00 a domingo 23:59 CT; ancla lunes 02/11/2026 (02-15 nov, 16-29 nov, 30 nov-13 dic…). |
| Límite de turno abierto | 15 h (otras empresas 12 h). |
| Ajustes masivos de horas | Alabama 2-3 nov (lote `alabama-2026-11-02-03`, reemplazado por el de 02-14 nov), Alabama 02-14 nov (lote `alabama-2026-11-02-14`, 25 personas) Virginia 01-14 nov (lote `virginia-2026-11-01-14`, 11 personas) y Virginia 01-14 nov parte 2 (lote `virginia-2026-11-01-14-b`: 4 personas más, resto en 0, turnos sin cerrar). |
| Pendiente | Tarifas por hora. NICOLAS GOMEZ (prueba) sigue como trabajador activo: el dueño decide si se archiva. |

## Historial

### 2026-11-01 a 2026-11-13 (resumen)
- 2026-11-01: lugares de trabajo (`work_locations`) solo VOLTAGE (90fa1be, a18b5c3).
- 2026-11-02: bot marcación con GPS + aviso de turno abierto (1b2fbc3); GPS al cerrar turno (60c122a, f0ec0eb).
- 2026-11-03: Nómina EE. UU. (b7f949f) y rediseño por operación (063A). Límite 15 h (9f5cc42). Ajuste Alabama 2-3 nov a 24 personas (bebdc70).
- 2026-11-03: Board de gerencia (b1e2e53). 2026-11-04: Líder de operación v2 (b7c0f81), Finalizar sin bucles (9f025c5).
- 2026-11-09: Horario de la semana (bc5d247). Avisos WhatsApp al grupo (fc3f542), en vivo desde 2026-11-10.

### 2026-11-17 — Cortes de pago cada 2 semanas + ajuste masivo Alabama 02-14 nov

**Commits en `main`:** `19d5d78` (cortes, 080A) y `fcf17da` (script de ajuste). Despliegue Railway
`1785ef65` en línea, `/health` 200. CI completo en verde antes del push.

**1) Cortes de pago (solo VOLTAGE, configurable por empresa)**
- Ajuste guardado en `us_payroll_rules` (settings del módulo payroll):
  `{"week_start_day": "monday", "pay_period": {"type": "biweekly", "anchor": "2026-11-02"}}`.
  Script `scripts/voltage_cortes_pago.py --apply` (auditoría en `admin_audit_log`, `--undo` disponible).
  Sin ese ajuste, una empresa sigue igual que antes.
- Regla pura: `app/services/us_time.py` (`cut_for`, `cut_label`, `cut_info`).
- Nómina (/client): "Quincena" ahora es **"Corte (2 semanas)"**: abre el corte actual, muestra
  "Corte 16/11 – 29/11 · Corte actual", tiene flechas ‹ › y un selector con los cortes desde el
  02/11 hasta 2 después del actual. "Semana" usa lunes a domingo. "Personalizado" sigue igual.
  En el detalle de la persona: "Semana 1: X pagables · regulares · overtime" y "Semana 2: …"
  (el overtime se cuenta por semana y se suma), y el chip "Ajuste masivo" en los días ajustados.
- PDF: título "Nómina · Corte 02/11 - 15/11" y tabla "horas por semana del corte". CSV: filas
  "Semana 1 (02/11-08/11)" y "Semana 2 (09/11-15/11)" antes del total de cada persona.
- Bot (resumen al finalizar turno): nueva línea "🗓 Corte 16/11 - 29/11: X h" que arranca en cero
  el lunes del corte a las 00:00 de la operación (Alabama CT, Virginia ET); "Semana: X de 40 h"
  arranca el lunes. Consulta de nómina por chat: "quincena" o "corte" = corte actual.
  Nada registrado se borra; solo cambia desde dónde se suma.

**2) Ajuste masivo Alabama 02/11-14/11/2026 (semanas de prueba del bot)**
- Script `scripts/ajuste_alabama_02_14_nov_2026.py` (PRUEBA por defecto, `--apply --expected N`, `--verify`, `--undo`).
- Personas: las **25** activas de Alabama (el pedido decía 24; la diferencia es Giselle del Carmen
  Reyna, que no estaba en el ajuste del 2-3 nov). El dueño confirmó: aplicar a todas, menos
  Brandon Patrick Via Illanes y Giselle del Carmen Reyna el 09, 10 y 11 nov.
  "Brandon Via Illanes" archivado (duplicado) no se tocó.
- Aviso dado al dueño: Hector Sandoval Machuca tenía 32 h del bot (7 días sin marcar) y quedó con 111.5 h.
- Resultado: 269 persona-día, 987 marcaciones reemplazadas (bot y ajuste del 2-3 nov), 1076 nuevas
  con origen `ajuste_masivo`. El turno por confirmar de José Dimas Morales (05/11, 30 h 19) quedó
  reemplazado por la tabla. Nadie tenía horas el 07, 08 ni el 15 nov.
- Verificado en producción (`--verify`): las 25 cuadran. 23 personas: 111:30 pagables = 51:30
  (11:30 OT) + 60:00 (20:00 OT) → 80 regulares + 31:30 overtime. Brandon y Giselle: 80:00 = 51:30
  (11:30 OT) + 28:30 (0 OT) → 68:30 + 11:30. Pausas 1 h por día trabajado. Total Alabama del corte:
  2369:55 → 2724:30 pagables; overtime 454:11 → 747:30.
- Corte 16-29 nov sin cambios (14 662 min antes y después): son horas reales del bot.
- Respaldo: tabla `workforce_attendance_adjustments`, lote `alabama-2026-11-02-14` (una fila por
  persona y día con antes/después, fecha y motivo "Ajuste masivo semanas de prueba bot…").
  Auditoría de la empresa: `admin_audit_log`, path `/scripts/ajuste_alabama_02_14_nov_2026/apply`.
- **Revertir:** `railway run -s Postgres py -3.11 scripts/ajuste_alabama_02_14_nov_2026.py --undo`
  (vuelve todo a como estaba, incluido el ajuste del 2-3 nov). El `--undo` del ajuste viejo se niega
  mientras este esté activo.

### 2026-11-18 — Cortes por operación (Virginia domingo a sábado) + ajuste Virginia 01-14 nov

**Commits en `main`:** `ea920d1` (main verde: prueba del menú con TikTok; incluye la bitácora `7dce666`),
`dc068f3` (cortes por operación, 081A), `204c5a9` (script Virginia), `1ea9b55` (fix: el periodo por
operación solo se pasa cuando viene), `10437cb` (prueba con un "999" que salía por azar en un uuid).
CI completo en verde; despliegue Railway `ccd7a263` en línea, `/health` 200.

**1) Semana y corte por operación**
- `us_payroll_rules.places` = `{"c09efe34-…" (Virginia): {"week_start_day": "sunday", "pay_period": {"type": "biweekly", "anchor": "2026-11-01"}}}`.
  Alabama no tiene ajuste propio: usa el de la empresa (lunes, ancla 02/11). Guardado con
  `scripts/voltage_cortes_pago.py --apply` (auditoría, `--undo`).
- Overtime FLSA por la semana laboral de la operación de cada persona.
- Nómina: "Semana" y "Corte (2 semanas)" se calculan por persona con la semana o el corte de SU
  operación. Con "Ambas operaciones" se ve "Virginia: Corte 01/11 – 14/11 · Alabama: Corte 02/11 – 15/11"
  y el selector junta los dos; filtrando una operación, el selector muestra solo sus cortes. Detalle de
  la persona con Semana 1 / Semana 2 y sus fechas. PDF/CSV con las fechas de cada operación.
- Bot (trabajador), Board y Líder de operación (supervisor): semana y corte de la operación. Virginia
  reinicia el domingo 00:00 ET (corte 15/11, 29/11, 13/12…), Alabama el lunes 00:00 CT. Un turno que
  cruza el cambio de corte cuenta entero en el corte donde empezó (en el contador del bot).

**2) Ajuste Virginia 01/11-14/11/2026 (tabla del supervisor)**
- Script `scripts/ajuste_virginia_01_14_nov_2026.py` (PRUEBA por defecto, `--apply --expected 11`, `--verify`, `--undo`).
- Nombres en el sistema: Helen Omonte Villca, Kewin Mauricio Rios Lindo, Jose Julian Cardenas Beltran,
  Luis Vladimir Rodriguez Ortiz, Kerim Gigliola Munoz Rojas, Roberto Carlos Camacho Rondal, Mery Rondal
  Rocha, Yessenia Ortiz Garcia, Jesus Castellon Escobar, Jhoselin Vasquez Mercado, Jacob Cameron Lopez.
  "luis Miguel Rodriguez Aponte" es otra persona (sin marcaciones): no se tocó ni se unió.
- Resultado: 96 persona-día, 230 marcaciones reemplazadas, 382 nuevas (`ajuste_masivo`). 9 turnos por
  confirmar del rango quedaron reemplazados; ningún turno abierto viejo; nadie de los 11 tenía horas el 15/11.
- Antes → después (pagables / regulares / overtime): total 734:13 / 648:06 / 86:07 → **1024:00 / 760:00 / 264:00**.
  Verificado en producción (`--verify`): las 11 cuadran con la tabla, semanas 01-07 y 08-14.
- Sin cambios: Alabama corte 02-15 (2724:30 / 747:30 overtime) y Virginia corte 15-28 (lo del bot).
- Otras 7 personas de Virginia con horas del bot en 01-14/11, NO tocadas (decide el dueño): Diego
  Alejandro Ruiz Chavez, Jaime David Marca Rioz, Mijail Navor Illanes Salas, NICOLAS GOMEZ, Noe Daniel
  Ponce Mamani, Oscar Diaz Vargas, Oscar Julio Anez Fernandez.
- Respaldo: `workforce_attendance_adjustments`, lote `virginia-2026-11-01-14`, motivo "ajuste Virginia
  tabla supervisor 01-14/11". Auditoría: `admin_audit_log`, `/scripts/ajuste_virginia_01_14_nov_2026/apply`.
- **Revertir:** `railway run -s Postgres py -3.11 scripts/ajuste_virginia_01_14_nov_2026.py --undo`

### 2026-11-18 — Ajuste Virginia 01-14 nov, parte 2 (lote `virginia-2026-11-01-14-b`)

Solo script (sin cambios de la app): `scripts/ajuste_virginia_01_14_nov_2026_b.py` (PRUEBA por defecto,
`--apply --expected 15`, `--verify`, `--undo`), con sus pruebas. El lote de la primera parte no se tocó.

- 4 personas más por la tabla del supervisor (entrada 6:00, almuerzo 12:00-12:30 sin pago):
  | Persona (sistema) | Antes (bot) pag/reg/OT | Después pag/reg/OT | Semanas 01-07 / 08-14 |
  | --- | --- | --- | --- |
  | Diego Alejandro Ruiz Chavez | 73:12 / 73:12 / 0 | 108:00 / 80:00 / 28:00 | 60:00 / 48:00 |
  | Jaime David Marca Rioz | 18:50 / 18:50 / 0 | 24:00 / 24:00 / 0 | 24:00 / 0 |
  | Noe Daniel Ponce Mamani | 83:49 / 80:00 / 3:49 | 83:55 / 80:00 / 3:55 | 42:55 / 41:00 |
  | Mijail Navor Illanes Salas | 50:28 / 40:00 / 10:28 | 90:00 / 78:00 / 12:00 | 38:00 / 52:00 |
- En 0 para el corte 01-14 (solo sus marcaciones; la persona y su estado no cambian): Oscar Diaz Vargas
  (tenía 25:51), Oscar Julio Anez Fernandez (7:24), NICOLAS GOMEZ (0:16, prueba; sigue como trabajador
  activo) e Ismael Camino Mendoza (0:00 pagables, una entrada sin salida; apareció en la PRUEBA).
- Turnos sin cerrar del primer corte: 0 por quitar en Virginia y 0 en Alabama (los ajustes anteriores
  ya los habían reemplazado); ningún estado del bot "en turno" con un turno del primer corte.
- Resultado: 36 persona-día, 108 marcaciones reemplazadas, 116 nuevas (`ajuste_masivo`). Correrlo de
  nuevo no cambia nada.
- Verificado en producción: Virginia corte 01-14 = **1329:55 / 1022:00 / 307:55** (15 personas con
  horas); Alabama corte 02-15 = **2724:30 / 1977:00 / 747:30** (25). Virginia 15-28 y Alabama 16-29: lo del bot.
- Respaldo: `workforce_attendance_adjustments`, lote `virginia-2026-11-01-14-b`. Auditoría:
  `admin_audit_log`, `/scripts/ajuste_virginia_01_14_nov_2026_b/apply`.
- **Revertir (solo esta parte):** `railway run -s Postgres py -3.11 scripts/ajuste_virginia_01_14_nov_2026_b.py --undo`
