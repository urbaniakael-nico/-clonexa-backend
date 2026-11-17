# Bitácora del piloto VOLTAGE

Fuente única de verdad del piloto. Empresa VOLTAGE: `f1e8f774-f052-49ca-880a-268805f07db0`
(slug `voltage_operation`). La 76974191 (ex-Urbania) está archivada: no tocar.

Operaciones (lugares de trabajo): **Virginia** (America/New_York, ET) y **Alabama**
(America/Chicago, CT). Bot de Telegram: @VOLTAGRBOT.

> Este archivo se creó el 2026-11-17. Lo anterior se resume desde las notas del proyecto;
> el detalle está en los commits citados.

## Estado actual (2026-11-17)

| Tema | Estado |
| --- | --- |
| Nómina EE. UU. (`us_payroll`, FLSA) | Encendida solo en VOLTAGE desde 2026-11-03 (b7f949f). Overtime > 40 h por semana laboral, pausas sin pago, hora del lugar. Tarifas pendientes (el dinero sale "Pendiente"). |
| Semana laboral | **Lunes 00:00 a domingo 23:59** (hora de cada operación) desde 2026-11-17. Antes: domingo. |
| Corte de pago | **Cada 2 semanas, lunes a domingo, ancla lunes 02/11/2026**: 02-15 nov, 16-29 nov, 30 nov-13 dic, 14-27 dic… |
| Límite de turno abierto | 15 h (otras empresas 12 h). |
| Ajustes masivos de horas | Alabama 2-3 nov (lote `alabama-2026-11-02-03`, reemplazado después por el de 02-14 nov) y Alabama 02-14 nov (lote `alabama-2026-11-02-14`). |
| Pendiente | Virginia: ajuste de horas (va después). Tarifas por hora. |

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
