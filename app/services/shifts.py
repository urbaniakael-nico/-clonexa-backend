"""Turnos (modulo shifts): datos, malla, publicacion y cambios de turno.

Generico (cualquier empresa con el modulo activo), todo por company_id. Usa los
empleados ACTIVOS de Personal y sus roles (employee_roles); no toca Personal ni
nomina. La logica de reglas y armado vive en shifts_engine (funciones puras).
- Armar: reemplaza solo el BORRADOR de la semana; una semana publicada no se rearma.
- Publicar: la semana pasa a publicada y cada colaborador con bot recibe su semana.
- Cambio de turno (solo el supervisor lo crea): candidatos -> envio por bot ->
  aceptar (se aplica a la malla) / rechazar o vencer (pasa al siguiente) ->
  lista agotada = sin cubrir. El vencimiento corre en el servidor
  (expire_loop, un candado en la base) y se calcula desde la base.
"""
from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Optional
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import shifts_engine as eng

log = logging.getLogger("clonexa.shifts")
MODULE = "shifts"
ADVISORY_LOCK_ID = 540540
OWNER_ROLES = {"company_admin", "admin_empresa", "dueno", "dueño", "owner", "propietario"}
DIRECTOR_ROLES = {"gerencia", "director"}
SUPERVISOR_ROLES = {"supervisor"}
PANEL_ROLES = OWNER_ROLES | DIRECTOR_ROLES | SUPERVISOR_ROLES
DEFAULT_TEMPLATES = [("Mañana", "M", "06:00", "14:00", "#f59e0b"), ("Tarde", "T", "14:00", "22:00", "#3b82f6"), ("Noche", "N", "22:00", "06:00", "#7c3aed")]
HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


class Invalid(ValueError):
    def __init__(self, field: str, message: str):
        super().__init__(message)
        self.field = field
        self.message = message


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _hhmm(value: Any) -> time:
    try:
        h, m = str(value or "").strip().split(":")[:2]
        return time(int(h), int(m))
    except Exception:
        raise Invalid("time", "hora inválida (HH:MM)") from None


def _json(value: Any, default: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return default
    return default if value is None else value


# ----------------------------------------------------------------- empresa y acceso
async def module_on(db: AsyncSession, company_id: Any) -> bool:
    row = (await db.execute(text("""
        SELECT cm.enabled FROM company_modules cm JOIN modules m ON m.id = cm.module_id
        WHERE cm.company_id::text = :c AND m.code = :m LIMIT 1
    """), {"c": str(company_id), "m": MODULE})).first()
    return bool(row and row[0])


def role_of(user_role: Any) -> str:
    return str(user_role or "").strip().lower()


def can_view(role: str) -> bool:
    return role in PANEL_ROLES


def can_create_change(role: str) -> bool:
    return role in SUPERVISOR_ROLES


async def zone(db: AsyncSession, company_id: Any) -> ZoneInfo:
    from app.services import company_locale

    return company_locale.zone((await company_locale.get_company_locale(db, company_id))["timezone"])


# ----------------------------------------------------------------- configuracion
async def employees(db: AsyncSession, company_id: Any) -> list[eng.Employee]:
    rows = (await db.execute(text("""
        SELECT id::text AS id, full_name, role, COALESCE(telegram_user_id, '') AS telegram_user_id
        FROM employees WHERE company_id::text = :c AND lower(COALESCE(status, 'active')) = 'active'
        ORDER BY lower(full_name), id
    """), {"c": str(company_id)})).mappings().all()
    return [eng.Employee(r["id"], r["full_name"] or "", str(r["role"] or "").strip().lower(), bool(str(r["telegram_user_id"]).strip())) for r in rows]


async def company_weekly_cap_hours(db: AsyncSession, company_id: Any) -> float:
    """El tope de Personal/nomina de la empresa (client_settings.payroll.ordinary_hours_limit); si no, 48."""
    row = (await db.execute(text("SELECT settings_json FROM companies WHERE id::text = :c"), {"c": str(company_id)})).mappings().first()
    payroll = ((_json(row["settings_json"], {}) or {}).get("client_settings") or {}).get("payroll") if row else {}
    try:
        return float((payroll or {}).get("ordinary_hours_limit") or 48)
    except (TypeError, ValueError):
        return 48.0


async def templates(db: AsyncSession, company_id: Any, include_inactive: bool = True) -> list[eng.Template]:
    rows = (await db.execute(text("""
        SELECT id::text AS id, code, name, start_time, end_time, color, active FROM shift_templates
        WHERE company_id::text = :c ORDER BY position, start_time, id
    """), {"c": str(company_id)})).mappings().all()
    out = [eng.Template(r["id"], r["code"], r["name"], r["start_time"], r["end_time"], r["color"], bool(r["active"])) for r in rows]
    return out if include_inactive else [t for t in out if t.active]


async def rules(db: AsyncSession, company_id: Any) -> tuple[eng.Rules, dict]:
    row = (await db.execute(text("SELECT * FROM shift_rules WHERE company_id::text = :c"), {"c": str(company_id)})).mappings().first()
    default_cap = await company_weekly_cap_hours(db, company_id)
    raw = {
        "min_rest_hours": int(row["min_rest_hours"]) if row else 12,
        "days_off_per_week": int(row["days_off_per_week"]) if row else 1,
        "max_consecutive_days": int(row["max_consecutive_days"]) if row else 6,
        "weekly_hours_cap": float(row["weekly_hours_cap"]) if row and row["weekly_hours_cap"] is not None else None,
        "max_consecutive_nights": int(row["max_consecutive_nights"]) if row else 3,
        "response_hours": float(row["response_hours"]) if row else 2.0,
        "default_weekly_hours_cap": default_cap,
    }
    cap = raw["weekly_hours_cap"] if raw["weekly_hours_cap"] is not None else default_cap
    return eng.Rules(raw["min_rest_hours"], raw["days_off_per_week"], raw["max_consecutive_days"], int(round(cap * 60)),
                     raw["max_consecutive_nights"], raw["response_hours"]), raw


async def coverage(db: AsyncSession, company_id: Any) -> dict:
    rows = (await db.execute(text("SELECT template_id::text AS t, role, min_people FROM shift_coverage WHERE company_id::text = :c"),
                             {"c": str(company_id)})).mappings().all()
    return {(r["t"], r["role"]): int(r["min_people"]) for r in rows}


async def ensure_defaults(db: AsyncSession, company_id: Any) -> None:
    """La primera vez: tres plantillas de ejemplo (Mañana, Tarde, Noche) que la empresa edita."""
    if (await db.execute(text("SELECT 1 FROM shift_templates WHERE company_id::text = :c LIMIT 1"), {"c": str(company_id)})).first():
        return
    for n, (name, code, a, b, color) in enumerate(DEFAULT_TEMPLATES):
        await db.execute(text("""
            INSERT INTO shift_templates (company_id, name, code, start_time, end_time, color, position)
            VALUES (CAST(:c AS uuid), :n, :code, :a, :b, :color, :p)
        """), {"c": str(company_id), "n": name, "code": code, "a": _hhmm(a), "b": _hhmm(b), "color": color, "p": n})
    await db.commit()


def validate_config(raw: dict, roles: set[str]) -> dict:
    if not isinstance(raw, dict):
        raise Invalid("config", "datos inválidos")
    tpls = []
    for i, t in enumerate(raw.get("templates") or []):
        name = str(t.get("name") or "").strip()
        code = str(t.get("code") or "").strip().upper()
        if not name or len(name) > 60:
            raise Invalid("templates", "cada turno necesita un nombre")
        if not code or len(code) > 4:
            raise Invalid("templates", "cada turno necesita un código de 1 a 4 letras")
        start, end = _hhmm(t.get("start")), _hhmm(t.get("end"))
        if start == end:
            raise Invalid("templates", f"el turno {name} empieza y termina a la misma hora")
        color = str(t.get("color") or "#3b82f6")
        if not HEX.match(color):
            raise Invalid("templates", "color inválido")
        tid = str(t.get("id") or "") or None
        if tid:
            uuid.UUID(tid)
        tpls.append({"id": tid, "name": name, "code": code, "start": start, "end": end, "color": color, "active": t.get("active") is not False, "position": i})
    if len({t["code"] for t in tpls}) != len(tpls):
        raise Invalid("templates", "dos turnos tienen el mismo código")
    r = raw.get("rules") or {}

    def pick(key: str, low: float, high: float, cast=int, allow_none: bool = False):
        value = r.get(key)
        if value in (None, "") and allow_none:
            return None
        try:
            value = cast(value)
        except (TypeError, ValueError):
            raise Invalid(key, "valor inválido") from None
        if not low <= value <= high:
            raise Invalid(key, "valor fuera de rango")
        return value

    rules_out = {"min_rest_hours": pick("min_rest_hours", 0, 48), "days_off_per_week": pick("days_off_per_week", 0, 6),
                 "max_consecutive_days": pick("max_consecutive_days", 1, 14), "weekly_hours_cap": pick("weekly_hours_cap", 1, 112, float, True),
                 "max_consecutive_nights": pick("max_consecutive_nights", 1, 14), "response_hours": pick("response_hours", 0.25, 72, float)}
    cov = []
    for c in raw.get("coverage") or []:
        role = str(c.get("role") or "").strip().lower()
        if role not in roles:
            raise Invalid("coverage", f"el rol {role or '—'} no es de esta empresa")
        n = int(c.get("min") or 0)
        if not 0 <= n <= 50:
            raise Invalid("coverage", "mínimo de personas fuera de rango")
        cov.append({"template_ref": c.get("template_id") or c.get("template_code"), "role": role, "min": n})
    return {"templates": tpls, "rules": rules_out, "coverage": cov}


async def save_config(db: AsyncSession, company_id: Any, raw: dict, actor: str) -> None:
    from app.services import employee_roles

    config = await employee_roles.load_config(db, company_id)
    known = {e.role for e in await employees(db, company_id)} | set(employee_roles.codes())
    if config:
        known |= {str(r.get("code") or "") for r in config.get("roles") or []}
    data = validate_config(raw, known)
    cid = str(company_id)
    existing = {t.id for t in await templates(db, company_id)}
    by_code: dict[str, str] = {}
    for t in data["templates"]:
        if t["id"] and t["id"] in existing:
            await db.execute(text("""
                UPDATE shift_templates SET name = :n, code = :code, start_time = :a, end_time = :b, color = :color, active = :act,
                       position = :p, updated_at = now() WHERE company_id = CAST(:c AS uuid) AND id = CAST(:i AS uuid)
            """), {"n": t["name"], "code": t["code"], "a": t["start"], "b": t["end"], "color": t["color"], "act": t["active"], "p": t["position"], "c": cid, "i": t["id"]})
            by_code[t["code"]] = t["id"]
        else:
            new_id = (await db.execute(text("""
                INSERT INTO shift_templates (company_id, name, code, start_time, end_time, color, active, position)
                VALUES (CAST(:c AS uuid), :n, :code, :a, :b, :color, :act, :p) RETURNING id::text
            """), {"c": cid, "n": t["name"], "code": t["code"], "a": t["start"], "b": t["end"], "color": t["color"], "act": t["active"], "p": t["position"]})).scalar()
            by_code[t["code"]] = new_id
    r = data["rules"]
    await db.execute(text("""
        INSERT INTO shift_rules (company_id, min_rest_hours, days_off_per_week, max_consecutive_days, weekly_hours_cap, max_consecutive_nights, response_hours, updated_by, updated_at)
        VALUES (CAST(:c AS uuid), :a, :b, :d, :e, :f, :g, :by, now())
        ON CONFLICT (company_id) DO UPDATE SET min_rest_hours = EXCLUDED.min_rest_hours, days_off_per_week = EXCLUDED.days_off_per_week,
            max_consecutive_days = EXCLUDED.max_consecutive_days, weekly_hours_cap = EXCLUDED.weekly_hours_cap,
            max_consecutive_nights = EXCLUDED.max_consecutive_nights, response_hours = EXCLUDED.response_hours, updated_by = EXCLUDED.updated_by, updated_at = now()
    """), {"c": cid, "a": r["min_rest_hours"], "b": r["days_off_per_week"], "d": r["max_consecutive_days"], "e": r["weekly_hours_cap"],
           "f": r["max_consecutive_nights"], "g": r["response_hours"], "by": actor[:200]})
    await db.execute(text("DELETE FROM shift_coverage WHERE company_id = CAST(:c AS uuid)"), {"c": cid})
    valid_ids = set(by_code.values()) | existing
    for c in data["coverage"]:
        ref = str(c["template_ref"] or "")
        tid = ref if ref in valid_ids else by_code.get(ref.upper())
        if not tid or c["min"] <= 0:
            continue
        await db.execute(text("""
            INSERT INTO shift_coverage (company_id, template_id, role, min_people) VALUES (CAST(:c AS uuid), CAST(:t AS uuid), :r, :n)
            ON CONFLICT (company_id, template_id, role) DO UPDATE SET min_people = EXCLUDED.min_people
        """), {"c": cid, "t": tid, "r": c["role"], "n": c["min"]})
    await db.commit()


# ----------------------------------------------------------------- malla
async def assignments(db: AsyncSession, company_id: Any, start: date, end: date) -> list[dict]:
    rows = (await db.execute(text("""
        SELECT id::text AS id, employee_id::text AS employee_id, work_date, week_start, template_id::text AS template_id, status
        FROM shift_assignments WHERE company_id::text = :c AND work_date BETWEEN :a AND :b ORDER BY work_date, employee_id
    """), {"c": str(company_id), "a": start, "b": end})).mappings().all()
    return [dict(r) for r in rows]


def _sched(rows: list[dict]) -> dict:
    return {(r["employee_id"], r["work_date"]): r["template_id"] for r in rows}


async def week_status(db: AsyncSession, company_id: Any, week_start: date) -> str:
    rows = (await db.execute(text("""
        SELECT status, count(*) FROM shift_assignments WHERE company_id::text = :c AND week_start = :w GROUP BY status
    """), {"c": str(company_id), "w": week_start})).all()
    statuses = {r[0] for r in rows}
    return "published" if "published" in statuses else "draft" if "draft" in statuses else "empty"


async def build_draft(db: AsyncSession, company_id: Any, week_start: date) -> dict:
    week_start = eng.monday(week_start)
    if await week_status(db, company_id, week_start) == "published":
        raise Invalid("week", "la semana ya está publicada: se cambia con Cambio de turno")
    tz = await zone(db, company_id)
    emps, tpls, (rl, _), cov = await employees(db, company_id), await templates(db, company_id), await rules(db, company_id), await coverage(db, company_id)
    previous = _sched(await assignments(db, company_id, week_start - timedelta(days=7), week_start - timedelta(days=1)))
    plan = eng.build_week(emps, tpls, rl, cov, previous, week_start, tz)
    await db.execute(text("DELETE FROM shift_assignments WHERE company_id = CAST(:c AS uuid) AND week_start = :w AND status = 'draft'"),
                     {"c": str(company_id), "w": week_start})
    for (eid, d), tid in sorted(plan.assignments.items()):
        await db.execute(text("""
            INSERT INTO shift_assignments (company_id, employee_id, work_date, week_start, template_id, status)
            VALUES (CAST(:c AS uuid), CAST(:e AS uuid), :d, :w, CAST(:t AS uuid), 'draft')
        """), {"c": str(company_id), "e": eid, "d": d, "w": week_start, "t": tid})
    await db.commit()
    return {"assignments": len(plan.assignments), "gaps": plan.gaps}


async def week_view(db: AsyncSession, company_id: Any, week_start: date) -> dict:
    week_start = eng.monday(week_start)
    tz = await zone(db, company_id)
    emps, tpls, (rl, _), cov = await employees(db, company_id), await templates(db, company_id), await rules(db, company_id), await coverage(db, company_id)
    rows = await assignments(db, company_id, week_start, week_start + timedelta(days=6))
    previous = _sched(await assignments(db, company_id, week_start - timedelta(days=7), week_start - timedelta(days=1)))
    week = _sched(rows)
    analysis = eng.analyze(emps, tpls, rl, cov, previous, week, week_start, tz)
    return {"week_start": week_start.isoformat(), "status": await week_status(db, company_id, week_start),
            "days": [d.isoformat() for d in eng.week_days(week_start)],
            "assignments": [{**r, "work_date": r["work_date"].isoformat(), "week_start": r["week_start"].isoformat()} for r in rows],
            "analysis": analysis}


# ----------------------------------------------------------------- bot (avisos)
SHIFT_TEXT = {
    "es": {"week": "📅 Tus turnos de la semana del {start}:\n{lines}", "off": "Libre", "none": "Aún no tienes turnos publicados.",
           "proposal": "🔁 Te proponen cubrir el turno {shift}, {day}, {hours} (cambio de {owner}).",
           "proposal_swap": "🔁 Te proponen cambiar tu turno {other} por el turno {shift}, {day}, {hours} (cambio con {owner}).",
           "yes": "✅ Acepto", "no": "❌ No puedo", "accepted": "✅ Cambio confirmado: {who} queda con el turno {shift}, {day}.",
           "declined": "Gracias, se lo propondremos a otra persona.", "gone": "Esta propuesta ya no está vigente.",
           "uncovered": "⚠️ El turno {shift} del {day} quedó sin cubrir: nadie de la lista pudo.", "next": "↪️ {who} no tomó el turno {shift} del {day}; se le propone a {next}."},
    "en": {"week": "📅 Your shifts for the week of {start}:\n{lines}", "off": "Off", "none": "You have no published shifts yet.",
           "proposal": "🔁 You are asked to cover the shift {shift}, {day}, {hours} (change for {owner}).",
           "proposal_swap": "🔁 You are asked to swap your shift {other} for the shift {shift}, {day}, {hours} (swap with {owner}).",
           "yes": "✅ I accept", "no": "❌ I can't", "accepted": "✅ Change confirmed: {who} now has the shift {shift}, {day}.",
           "declined": "Thanks, we will offer it to someone else.", "gone": "This proposal is no longer active.",
           "uncovered": "⚠️ The shift {shift} on {day} is uncovered: nobody on the list could take it.", "next": "↪️ {who} did not take the shift {shift} on {day}; it is offered to {next}."},
    "fr": {"week": "📅 Tes services de la semaine du {start} :\n{lines}", "off": "Repos", "none": "Tu n'as pas encore de services publiés.",
           "proposal": "🔁 On te propose de couvrir le service {shift}, {day}, {hours} (changement pour {owner}).",
           "proposal_swap": "🔁 On te propose d'échanger ton service {other} contre le service {shift}, {day}, {hours} (échange avec {owner}).",
           "yes": "✅ J'accepte", "no": "❌ Je ne peux pas", "accepted": "✅ Changement confirmé : {who} prend le service {shift}, {day}.",
           "declined": "Merci, nous le proposerons à quelqu'un d'autre.", "gone": "Cette proposition n'est plus valable.",
           "uncovered": "⚠️ Le service {shift} du {day} n'est pas couvert : personne de la liste n'a pu.", "next": "↪️ {who} n'a pas pris le service {shift} du {day} ; il est proposé à {next}."},
}
DAYS = {"es": ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"], "en": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"], "fr": ["lun", "mar", "mer", "jeu", "ven", "sam", "dim"]}


def st(lang: str, key: str, **kw: Any) -> str:
    table = SHIFT_TEXT.get(lang) or SHIFT_TEXT["es"]
    return (table.get(key) or SHIFT_TEXT["es"][key]).format(**kw)


def day_label(d: date, lang: str) -> str:
    return f"{DAYS.get(lang, DAYS['es'])[d.weekday()]} {d.day:02d}/{d.month:02d}"


def hours_label(t: eng.Template) -> str:
    return f"{t.start.strftime('%H:%M')}–{t.end.strftime('%H:%M')}"


async def _bot(db: AsyncSession, company_id: Any) -> Optional[str]:
    try:
        from app.api.v1.endpoints import bots

        row = await bots.get_telegram_instance(db, uuid.UUID(str(company_id)))
        if row is None or not row.bot_token_encrypted or row.status == "inactive":
            return None
        return bots.decrypt_token(row.bot_token_encrypted)
    except Exception:
        log.exception("bot de la empresa no disponible company=%s", company_id)
        return None


async def employee_contact(db: AsyncSession, company_id: Any, employee_id: str) -> dict:
    row = (await db.execute(text("""
        SELECT e.full_name, e.role, COALESCE(e.telegram_user_id, '') AS tg, COALESCE(l.language, '') AS lang
        FROM employees e LEFT JOIN shift_bot_languages l ON l.company_id = e.company_id AND l.employee_id = e.id
        WHERE e.company_id::text = :c AND e.id::text = :e
    """), {"c": str(company_id), "e": employee_id})).mappings().first()
    if not row:
        return {"name": "", "telegram": "", "lang": "es"}
    lang = row["lang"]
    if row["tg"]:
        try:
            from app.api.v1.endpoints import bots

            manual = (await db.execute(text("""SELECT language FROM company_telegram_user_preferences
                WHERE company_id::text = :c AND telegram_user_id = :t LIMIT 1"""), {"c": str(company_id), "t": row["tg"]})).scalar()
            lang = bots._lang(manual) if manual else (lang or "es")
        except Exception:
            lang = lang or "es"
    return {"name": row["full_name"] or "", "telegram": row["tg"], "lang": lang if lang in SHIFT_TEXT else "es", "role": row["role"]}


async def remember_language(db: AsyncSession, company_id: Any, employee_id: Any, language: str) -> None:
    """Idioma del celular del colaborador (lo ve el bot en cada mensaje) para los avisos de Turnos."""
    if language not in SHIFT_TEXT:
        return
    await db.execute(text("""
        INSERT INTO shift_bot_languages (company_id, employee_id, language, updated_at) VALUES (CAST(:c AS uuid), CAST(:e AS uuid), :l, now())
        ON CONFLICT (company_id, employee_id) DO UPDATE SET language = EXCLUDED.language, updated_at = now()
    """), {"c": str(company_id), "e": str(employee_id), "l": language})


async def send(db: AsyncSession, company_id: Any, employee_id: str, build, reply_markup: Optional[dict] = None, token: Optional[str] = None) -> bool:
    """Manda un mensaje del bot a un colaborador (si tiene Telegram). build(lang) arma el texto."""
    contact = await employee_contact(db, company_id, employee_id)
    if not contact["telegram"]:
        return False
    token = token or await _bot(db, company_id)
    if not token:
        return False
    from app.api.v1.endpoints import bots

    markup = reply_markup(contact["lang"]) if callable(reply_markup) else reply_markup
    await bots._send_telegram_message(token, contact["telegram"], build(contact["lang"]), reply_markup=markup)
    return True


def week_text(lang: str, week_start: date, mine: dict, tmap: dict) -> str:
    lines = []
    for d in eng.week_days(week_start):
        t = tmap.get(mine.get(d))
        lines.append(f"• {day_label(d, lang)}: {f'{t.name} ({t.code}) {hours_label(t)}' if t else st(lang, 'off')}")
    return st(lang, "week", start=day_label(week_start, lang), lines="\n".join(lines))


async def publish(db: AsyncSession, company_id: Any, week_start: date) -> dict:
    week_start = eng.monday(week_start)
    status = await week_status(db, company_id, week_start)
    if status == "empty":
        raise Invalid("week", "no hay malla para publicar: arma la semana primero")
    await db.execute(text("""
        UPDATE shift_assignments SET status = 'published', updated_at = now() WHERE company_id = CAST(:c AS uuid) AND week_start = :w AND status = 'draft'
    """), {"c": str(company_id), "w": week_start})
    await db.commit()
    tmap = {t.id: t for t in await templates(db, company_id)}
    rows = await assignments(db, company_id, week_start, week_start + timedelta(days=6))
    token = await _bot(db, company_id)
    sent, without = 0, []
    for e in await employees(db, company_id):
        mine = {r["work_date"]: r["template_id"] for r in rows if r["employee_id"] == e.id}
        if not mine:
            continue
        if await send(db, company_id, e.id, lambda lang, m=mine: week_text(lang, week_start, m, tmap), token=token):
            sent += 1
        else:
            without.append(e.name)
    return {"published": True, "sent": sent, "without_bot": without}


async def my_week_text(db: AsyncSession, company_id: Any, employee_id: str, lang: str, today: date) -> str:
    """"Mis turnos" del bot: la semana publicada en curso (y la siguiente si ya esta publicada)."""
    tmap = {t.id: t for t in await templates(db, company_id)}
    out = []
    for ws in (eng.monday(today), eng.monday(today) + timedelta(days=7)):
        rows = [r for r in await assignments(db, company_id, ws, ws + timedelta(days=6)) if r["status"] == "published" and r["employee_id"] == employee_id]
        if rows:
            out.append(week_text(lang, ws, {r["work_date"]: r["template_id"] for r in rows}, tmap))
    return "\n\n".join(out) or st(lang, "none")


# ----------------------------------------------------------------- cambio de turno
async def _stats(db: AsyncSession, company_id: Any, emps: list[eng.Employee], tz: ZoneInfo) -> dict:
    """Asistencia (dias con entrada) y puntualidad (entradas a tiempo frente a su turno publicado)
    de los ultimos 30 dias segun Personal, y cambios de turno recientes."""
    since = _now() - timedelta(days=30)
    rows = (await db.execute(text("""
        SELECT employee_id::text AS e, occurred_at FROM workforce_attendance_events
        WHERE company_id::text = :c AND event_type = 'check_in' AND occurred_at >= :s
    """), {"c": str(company_id), "s": since})).mappings().all()
    days: dict[str, set] = {}
    first_in: dict[tuple, datetime] = {}
    for r in rows:
        local = r["occurred_at"].astimezone(tz)
        days.setdefault(r["e"], set()).add(local.date())
        key = (r["e"], local.date())
        if key not in first_in or local < first_in[key]:
            first_in[key] = local
    tmap = {t.id: t for t in await templates(db, company_id)}
    on_time: dict[str, int] = {}
    for a in await assignments(db, company_id, (since.astimezone(tz)).date(), _now().astimezone(tz).date()):
        t = tmap.get(a["template_id"])
        got = first_in.get((a["employee_id"], a["work_date"]))
        if t and got and a["status"] == "published":
            start, _ = eng.bounds(t, a["work_date"], tz)
            if got <= start + timedelta(minutes=10):
                on_time[a["employee_id"]] = on_time.get(a["employee_id"], 0) + 1
    changes = (await db.execute(text("""
        SELECT log FROM shift_change_requests WHERE company_id::text = :c AND created_at >= :s AND status = 'accepted'
    """), {"c": str(company_id), "s": since})).scalars().all()
    changed: dict[str, int] = {}
    for entries in changes:
        for ev in _json(entries, []):
            if ev.get("kind") == "accepted" and ev.get("employee_id"):
                changed[ev["employee_id"]] = changed.get(ev["employee_id"], 0) + 1
    return {e.id: {"attendance": len(days.get(e.id, ())), "punctuality": on_time.get(e.id, 0), "changes": changed.get(e.id, 0)} for e in emps}


async def proposal(db: AsyncSession, company_id: Any, assignment_id: str) -> dict:
    row = (await db.execute(text("""
        SELECT id::text AS id, employee_id::text AS employee_id, work_date, week_start, template_id::text AS template_id, status
        FROM shift_assignments WHERE company_id::text = :c AND id::text = :a
    """), {"c": str(company_id), "a": str(assignment_id)})).mappings().first()
    if not row:
        raise Invalid("assignment", "turno no encontrado")
    if row["status"] != "published":
        raise Invalid("assignment", "solo se cambian turnos de una semana publicada")
    tz = await zone(db, company_id)
    emps, tpls, (rl, _) = await employees(db, company_id), await templates(db, company_id), await rules(db, company_id)
    ws = row["week_start"]
    sched = _sched(await assignments(db, company_id, ws - timedelta(days=7), ws + timedelta(days=13)))
    out = eng.candidates((row["employee_id"], row["work_date"]), emps, tpls, rl, sched, ws, tz, await _stats(db, company_id, emps, tz))
    return {"assignment": {**dict(row), "work_date": row["work_date"].isoformat(), "week_start": ws.isoformat()}, **out}


def _log(entries: list, kind: str, **kw: Any) -> list:
    return [*entries, {"at": _now().isoformat(), "kind": kind, **kw}]


async def create_change(db: AsyncSession, company_id: Any, assignment_id: str, actor: str) -> dict:
    prop = await proposal(db, company_id, assignment_id)
    a = prop["assignment"]
    open_one = (await db.execute(text("""
        SELECT 1 FROM shift_change_requests WHERE company_id::text = :c AND assignment_id::text = :a AND status IN ('pending', 'waiting') LIMIT 1
    """), {"c": str(company_id), "a": a["id"]})).first()
    if open_one:
        raise Invalid("assignment", "ese turno ya tiene un cambio en curso")
    new_id = (await db.execute(text("""
        INSERT INTO shift_change_requests (company_id, assignment_id, requester_employee_id, work_date, template_id, candidates, status, log, created_by)
        VALUES (CAST(:c AS uuid), CAST(:a AS uuid), CAST(:e AS uuid), :d, CAST(:t AS uuid), CAST(:cand AS jsonb), 'pending', CAST(:log AS jsonb), :by) RETURNING id::text
    """), {"c": str(company_id), "a": a["id"], "e": a["employee_id"], "d": date.fromisoformat(a["work_date"]), "t": a["template_id"],
           "cand": json.dumps(prop["candidates"], ensure_ascii=False),
           "log": json.dumps(_log([], "created", by=actor[:200], candidates=len(prop["candidates"])), ensure_ascii=False), "by": actor[:200]})).scalar()
    await db.commit()
    return {"id": new_id, **prop}


async def change(db: AsyncSession, company_id: Any, change_id: str) -> Optional[dict]:
    row = (await db.execute(text("""
        SELECT id::text AS id, assignment_id::text AS assignment_id, requester_employee_id::text AS requester_employee_id, work_date,
               template_id::text AS template_id, candidates, current_index, status, uncovered, deadline_at, log, created_by, created_at, resolved_at
        FROM shift_change_requests WHERE company_id::text = :c AND id::text = :i
    """), {"c": str(company_id), "i": str(change_id)})).mappings().first()
    if not row:
        return None
    out = dict(row)
    out["candidates"], out["log"] = _json(out["candidates"], []), _json(out["log"], [])
    return out


async def list_changes(db: AsyncSession, company_id: Any) -> list[dict]:
    ids = (await db.execute(text("SELECT id::text FROM shift_change_requests WHERE company_id::text = :c ORDER BY created_at DESC LIMIT 100"),
                            {"c": str(company_id)})).scalars().all()
    return [await change(db, company_id, i) for i in ids]


async def _update(db: AsyncSession, company_id: Any, ch: dict, **fields: Any) -> None:
    sets = ", ".join(f"{k} = :{k}" if k not in ("log", "candidates") else f"{k} = CAST(:{k} AS jsonb)" for k in fields)
    params = {k: (json.dumps(v, ensure_ascii=False) if k in ("log", "candidates") else v) for k, v in fields.items()}
    await db.execute(text(f"UPDATE shift_change_requests SET {sets}, updated_at = now() WHERE company_id::text = :c AND id::text = :i"),
                     {**params, "c": str(company_id), "i": ch["id"]})


async def _offer(db: AsyncSession, company_id: Any, ch: dict, index: int, now: Optional[datetime] = None) -> dict:
    """Propone el turno al candidato `index` (por bot si lo tiene) o deja el cambio sin cubrir."""
    now = now or _now()
    tmap = {t.id: t for t in await templates(db, company_id)}
    t = tmap.get(ch["template_id"])
    day = ch["work_date"]
    if index >= len(ch["candidates"]):
        last = ch["log"][-1]["kind"] if ch["log"] else ""
        status = "expired" if last == "expired" else "rejected"
        log_ = _log(ch["log"], "uncovered")
        await _update(db, company_id, ch, status=status, uncovered=True, current_index=None, deadline_at=None, log=log_, resolved_at=now)
        await db.commit()
        await _notify_supervisors(db, company_id, lambda lang: st(lang, "uncovered", shift=t.name if t else "", day=day_label(day, lang)))
        return {**ch, "status": status, "uncovered": True}
    cand = ch["candidates"][index]
    _, rl_raw = await rules(db, company_id)
    deadline = now + timedelta(hours=float(rl_raw["response_hours"]))
    owner = (await employee_contact(db, company_id, ch["requester_employee_id"]))["name"]
    other = tmap.get(cand.get("swap_template_id") or "")
    markup = lambda lang: {"inline_keyboard": [[{"text": st(lang, "yes"), "callback_data": f"clx:shift:yes:{ch['id']}:{index}"},  # noqa: E731
                                                {"text": st(lang, "no"), "callback_data": f"clx:shift:no:{ch['id']}:{index}"}]]}

    def build(lang: str) -> str:
        if cand["kind"] == "swap" and other:
            return st(lang, "proposal_swap", other=other.name, shift=t.name, day=day_label(day, lang), hours=hours_label(t), owner=owner)
        return st(lang, "proposal", shift=t.name, day=day_label(day, lang), hours=hours_label(t), owner=owner)

    sent = await send(db, company_id, cand["employee_id"], build, reply_markup=markup)
    log_ = _log(ch["log"], "offered", employee_id=cand["employee_id"], name=cand["name"], index=index, bot=sent)
    await _update(db, company_id, ch, status="waiting", current_index=index, deadline_at=deadline, log=log_)
    await db.commit()
    return {**ch, "status": "waiting", "current_index": index, "deadline_at": deadline, "log": log_}


async def start(db: AsyncSession, company_id: Any, change_id: str) -> dict:
    ch = await change(db, company_id, change_id)
    if not ch:
        raise Invalid("change", "cambio no encontrado")
    if ch["status"] != "pending":
        raise Invalid("change", "este cambio ya se envió")
    if not ch["candidates"]:
        raise Invalid("change", "no hay candidatos válidos para enviar")
    return await _offer(db, company_id, ch, 0)


async def _notify_supervisors(db: AsyncSession, company_id: Any, build) -> None:
    for e in await employees(db, company_id):
        if e.role in SUPERVISOR_ROLES:
            await send(db, company_id, e.id, build)


async def respond(db: AsyncSession, company_id: Any, change_id: str, employee_id: str, index: int, accept: bool, via: str, actor: str = "",
                  now: Optional[datetime] = None) -> dict:
    """Respuesta del candidato actual (por el bot o registrada a mano por el supervisor)."""
    now = now or _now()
    ch = await change(db, company_id, change_id)
    if not ch or ch["status"] != "waiting" or ch["current_index"] != index:
        return {"ok": False, "reason": "gone"}
    cand = ch["candidates"][index]
    if str(cand["employee_id"]) != str(employee_id):
        return {"ok": False, "reason": "gone"}
    tmap = {t.id: t for t in await templates(db, company_id)}
    t = tmap.get(ch["template_id"])
    if not accept:
        ch["log"] = _log(ch["log"], "rejected", employee_id=employee_id, name=cand["name"], via=via, by=actor[:200])
        await _update(db, company_id, ch, log=ch["log"])
        await db.commit()
        nxt = ch["candidates"][index + 1]["name"] if index + 1 < len(ch["candidates"]) else ""
        if nxt:
            await _notify_supervisors(db, company_id, lambda lang: st(lang, "next", who=cand["name"], shift=t.name, day=day_label(ch["work_date"], lang), next=nxt))
        return {"ok": True, "result": "next", **(await _offer(db, company_id, ch, index + 1, now))}
    # Acepta: se revalida con la malla de hoy (pudo cambiar) y se aplica.
    a = (await db.execute(text("""
        SELECT employee_id::text AS employee_id, work_date, week_start, template_id::text AS template_id FROM shift_assignments
        WHERE company_id::text = :c AND id::text = :i
    """), {"c": str(company_id), "i": ch["assignment_id"]})).mappings().first()
    tz = await zone(db, company_id)
    emps, tpls, (rl, _) = await employees(db, company_id), await templates(db, company_id), await rules(db, company_id)
    if not a or a["employee_id"] != ch["requester_employee_id"]:
        return {"ok": False, "reason": "gone"}
    ws = a["week_start"]
    sched = _sched(await assignments(db, company_id, ws - timedelta(days=7), ws + timedelta(days=13)))
    check = eng.candidates((a["employee_id"], a["work_date"]), emps, tpls, rl, sched, ws, tz, limit=50)
    still = next((c for c in check["candidates"] if c["employee_id"] == employee_id and c["kind"] == cand["kind"]), None)
    if not still:
        ch["log"] = _log(ch["log"], "invalid", employee_id=employee_id, name=cand["name"])
        await _update(db, company_id, ch, log=ch["log"])
        await db.commit()
        return {"ok": True, "result": "next", **(await _offer(db, company_id, ch, index + 1, now))}
    if cand["kind"] == "cover":
        await db.execute(text("""UPDATE shift_assignments SET employee_id = CAST(:e AS uuid), updated_at = now()
            WHERE company_id::text = :c AND id::text = :i"""), {"e": employee_id, "c": str(company_id), "i": ch["assignment_id"]})
    else:
        other_tid = sched[(employee_id, a["work_date"])]
        await db.execute(text("""UPDATE shift_assignments SET template_id = CAST(:t AS uuid), updated_at = now()
            WHERE company_id::text = :c AND employee_id::text = :e AND work_date = :d"""), {"t": other_tid, "c": str(company_id), "e": a["employee_id"], "d": a["work_date"]})
        await db.execute(text("""UPDATE shift_assignments SET template_id = CAST(:t AS uuid), updated_at = now()
            WHERE company_id::text = :c AND employee_id::text = :e AND work_date = :d"""), {"t": ch["template_id"], "c": str(company_id), "e": employee_id, "d": a["work_date"]})
    ch["log"] = _log(ch["log"], "accepted", employee_id=employee_id, name=cand["name"], via=via, by=actor[:200])
    await _update(db, company_id, ch, status="accepted", deadline_at=None, log=ch["log"], resolved_at=now)
    await db.commit()
    msg = lambda lang: st(lang, "accepted", who=cand["name"], shift=t.name, day=day_label(a["work_date"], lang))  # noqa: E731
    for who in {ch["requester_employee_id"], employee_id}:
        await send(db, company_id, who, msg)
    await _notify_supervisors(db, company_id, msg)
    return {"ok": True, "result": "accepted"}


async def cancel(db: AsyncSession, company_id: Any, change_id: str, actor: str) -> dict:
    ch = await change(db, company_id, change_id)
    if not ch or ch["status"] not in ("pending", "waiting"):
        raise Invalid("change", "este cambio ya terminó")
    await _update(db, company_id, ch, status="cancelled", deadline_at=None, log=_log(ch["log"], "cancelled", by=actor[:200]), resolved_at=_now())
    await db.commit()
    return {"ok": True}


async def expire_due(db: AsyncSession, now: Optional[datetime] = None) -> int:
    """Propuestas vencidas (de todas las empresas): pasan al siguiente candidato."""
    now = now or _now()
    rows = (await db.execute(text("""
        SELECT company_id::text AS c, id::text AS i FROM shift_change_requests WHERE status = 'waiting' AND deadline_at IS NOT NULL AND deadline_at <= :n
        ORDER BY deadline_at LIMIT 50
    """), {"n": now})).mappings().all()
    for r in rows:
        ch = await change(db, r["c"], r["i"])
        if not ch or ch["status"] != "waiting":
            continue
        cand = ch["candidates"][ch["current_index"]]
        ch["log"] = _log(ch["log"], "expired", employee_id=cand["employee_id"], name=cand["name"])
        await _update(db, r["c"], ch, log=ch["log"])
        await db.commit()
        await _offer(db, r["c"], ch, ch["current_index"] + 1, now)
    return len(rows)


async def expire_loop() -> None:
    """Cada minuto; con varias replicas solo una corre (candado en la base)."""
    import asyncio

    from app.core.database import AsyncSessionLocal

    while True:
        try:
            async with AsyncSessionLocal() as db:
                if (await db.execute(text("SELECT to_regclass('shift_change_requests')"))).scalar():
                    locked = (await db.execute(text("SELECT pg_try_advisory_lock(:id)"), {"id": ADVISORY_LOCK_ID})).scalar()
                    if locked:
                        try:
                            n = await expire_due(db)
                            if n:
                                log.info("Turnos: %s propuestas vencidas pasaron al siguiente candidato", n)
                        finally:
                            await db.execute(text("SELECT pg_advisory_unlock(:id)"), {"id": ADVISORY_LOCK_ID})
                            await db.commit()
        except Exception as exc:  # nunca tumba el servidor
            log.warning("Turnos: revision de vencimientos no pudo correr: %s", exc)
        await asyncio.sleep(60)


def start_expire_loop() -> None:
    import asyncio

    asyncio.get_event_loop().create_task(expire_loop())
