# Sesiones que no se cierran solas · informe y propuesta (NO aplicada)

Afectaría a **todas las empresas**: la decide el dueño.

## Qué pasa hoy (verificado en código y en producción)

Cada inicio de sesión crea una fila en `clonexa_access_sessions` con `status = 'active'`
(`app/services/access_sessions.py`, `register_access_session`). Una sesión pasa a `closed`
**solo** en estos casos:

| Cuándo | Dónde | Alcance |
|---|---|---|
| El usuario pulsa "Salir" | `auth.py` (portal), `admin_v2_routes.py` (Admin V2) | esa sesión |
| Admin V2 la cierra (una o todas) | `companies.py` · `close_access_session` / `close_company_access_sessions` | manual |
| Se supera el límite de la política de sesión | `register_access_session` | solo si la empresa tiene la política **encendida** |
| Mesero, cocina o caja entran en otro equipo | `close_other_sessions_for_subject` | mini paneles de un solo equipo |
| Un supervisor termina el turno de alguien | `company_users.py` (`closed_from_supervisor`) | mini panel |
| Corte diario | `session_cutoff.py` (`run_company_cutoff`) | **solo `scope = 'mini_panel'`** |

**No existe ningún vencimiento** para las sesiones del portal (`scope = 'client'`) ni de
Admin V2. El token JWT sí vence (`ACCESS_TOKEN_EXPIRE_MINUTES`, por defecto 480 min), pero
la fila queda `active` para siempre si la persona cierra el navegador sin pulsar "Salir".

**The Time Machine (producción, 2026-10-04):** 84 sesiones registradas. Las **42 abiertas
son todas del portal (`client`) y de un solo usuario**, creadas a lo largo de dos meses
(la más vieja hace ~61 días); 36 llevan más de 7 días sin actividad. Las otras 42 se
cerraron con "Salir". No hay nadie conectado: son sesiones huérfanas. El usuario no puede
usarlas (su token ya venció), pero inflan "Sesiones abiertas" y, si la empresa enciende la
política de límite de sesiones, ocupan cupo y pueden expulsar o bloquear un ingreso nuevo.

## Mientras tanto (ya hecho, solo pantalla)

En la consola, "Sesiones abiertas" cuenta solo las que tuvieron actividad en las últimas
24 horas; las demás se muestran aparte como "sin actividad" (Centro de mando, Ficha ·
Resumen y Ficha · Usuarios y accesos). No se cerró ni se cambió ninguna sesión.

## Propuesta: cierre automático por inactividad

1. **Regla:** una sesión `active` cuyo `last_seen_at` tiene más de **X horas** pasa a
   `closed` con `closed_reason = 'expirada_por_inactividad'` y `closed_at = now()`.
2. **X recomendado = 24 h** para todos los alcances (`client`, `mini_panel`, `admin_v2`).
   Es mayor que la vida del token (8 h), así que **nadie que esté trabajando pierde su
   sesión**: si la sesión lleva 24 h sin una sola petición, su token ya no sirve. Las de
   Admin V2 ya vencen a las 8 h por cookie; cerrar su fila solo ordena el registro.
3. **Dónde:** dentro del ciclo que ya existe del corte diario (`start_cutoff_loop`), como
   un paso aparte que corre cada hora con un solo `UPDATE … WHERE status = 'active' AND
   last_seen_at < now() - interval 'X hours'` (usa el índice existente
   `ix_clonexa_access_sessions_scope_status`). No toca `mini_panel_work_sessions` ni la
   asistencia: solo los registros de sesión.
4. **Interruptor:** variable de entorno `CLONEXA_SESSION_IDLE_HOURS` (vacía o `0` =
   apagado). Se enciende primero con 72 h, se mira una semana y luego se baja a 24 h.
5. **Opcional:** al iniciar sesión en el portal, cerrar las sesiones del mismo usuario y
   mismo equipo que ya estén vencidas (hoy solo lo hacen mesero, cocina y caja).
6. **Pruebas:** no cierra sesiones con actividad reciente; cierra solo las de más de X
   horas; no toca otras empresas ni otros estados; apagado no hace nada.

Efecto esperado en The Time Machine: 40 de 42 "abiertas" pasarían a cerradas la primera
hora; las 2 recientes siguen igual.
