"""Produccion v2 (interruptor production_v2 del modulo production; hoy solo Velvet).

Un solo calculo (insights) para la pantalla y el PDF. No cambia nada de lo que ya
calcula Produccion: reusa sessions_summary (tiempo efectivo del equipo por
referencia, sin pausas y topado por nomina), references_v2.reference_groups
(meta = suma de cortes, producido y pendiente por talla), los movimientos de corte
(despliegue = envio a Bombon) y el bruto de nomina del periodo.

El taller trabaja por LOTE (referencia): todas las cifras son del equipo o del lote.
Nunca se calcula ni se muestra productividad por persona.

Cuando no hay datos suficientes una cifra dice "Sin datos aun" (status sin_datos)
con el motivo, en vez de mostrar un numero enganoso.
"""
from __future__ import annotations

import io
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

MODULE = "production"
SWITCH = "production_v2"
PRESETS = ("week", "month", "quarter", "custom")
MAX_DAYS = 366
LONG_SESSION_MIN = 12 * 60
NO_TIME_DAYS = 5
LOW_PROGRESS = 0.5
RECENT_DAYS = 30
SECTIONS = ("corte", "bordado", "taller", "lavado", "otro")


def _json(value: Any) -> dict:
    import json

    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return {}
    return value if isinstance(value, dict) else {}


async def is_on(db: AsyncSession, company_id: Any) -> bool:
    row = (await db.execute(text("""
        SELECT cm.enabled, cm.settings FROM company_modules cm JOIN modules m ON m.id = cm.module_id
        WHERE cm.company_id::text = :c AND lower(m.code) = :m LIMIT 1
    """), {"c": str(company_id), "m": MODULE})).mappings().first()
    return bool(row and row["enabled"] and _json(row["settings"]).get(SWITCH) is True)


# ---------------------------------------------------------------- periodo
def period(preset: str, today: date, date_from: Optional[str] = None, date_to: Optional[str] = None) -> tuple[date, date]:
    """Semana (lunes a hoy), Mes (dia 1 a hoy), Trimestre (inicio del trimestre a hoy)
    o Personalizado (maximo 366 dias)."""
    preset = preset if preset in PRESETS else "week"
    if preset == "week":
        return today - timedelta(days=today.weekday()), today
    if preset == "month":
        return today.replace(day=1), today
    if preset == "quarter":
        return date(today.year, 3 * ((today.month - 1) // 3) + 1, 1), today
    try:
        start = date.fromisoformat(str(date_from or ""))
        end = date.fromisoformat(str(date_to or ""))
    except ValueError:
        raise ValueError("fechas_invalidas") from None
    if end < start:
        start, end = end, start
    if (end - start).days >= MAX_DAYS:
        raise ValueError("rango_maximo_366_dias")
    return start, end


def bucket_of(day: date, by_month: bool) -> date:
    return day.replace(day=1) if by_month else day - timedelta(days=day.weekday())


def buckets(start: date, end: date) -> tuple[list[date], bool]:
    by_month = (end - start).days > 92
    out, cur = [], bucket_of(start, by_month)
    while cur <= end:
        out.append(cur)
        cur = (cur.replace(day=28) + timedelta(days=4)).replace(day=1) if by_month else cur + timedelta(days=7)
    return out, by_month


def _sin(reason: str) -> dict:
    return {"status": "sin_datos", "value": None, "reason": reason}


# ---------------------------------------------------------------- calculo puro
def build(*, start: date, end: date, today: date, groups: list[dict], key_by_id: dict, moves: list[dict], closures: list[dict],
          first_session: dict, last_session: dict, team_seconds: int, time_by_ref: list[dict], live: dict,
          labor_gross: Optional[float], time_by_person: Optional[list[dict]] = None) -> dict:
    """moves: {reference_id, kind, quantity, event_date, size?, section?} (ingreso, novedad, despliegue);
    closures: {key, quantity, day}; first_session/last_session: {key: date};
    time_by_ref: {key, name, seconds, active}; time_by_person: {key, person, seconds}
    (horas del equipo en el lote: participacion, nunca prendas por persona)."""
    from app.services.references_v2 import group_key

    in_period = lambda d: d is not None and start <= d <= end  # noqa: E731
    gmap = {g["key"]: g for g in groups}
    name_of = {g["key"]: g["name"] for g in groups}
    for t in time_by_ref:
        name_of.setdefault(t["key"], t["name"])

    def key_of_move(m: dict) -> Optional[str]:
        return key_by_id.get(m["reference_id"])

    deployed_all: dict[str, int] = {}
    deployed_period = 0
    first_cut: dict[str, date] = {}
    last_move: dict[str, date] = {}
    cuts_by_key: dict[str, dict] = {}
    news_by_key: dict[str, dict[str, int]] = {}
    for m in moves:
        k = key_of_move(m)
        if not k:
            continue
        d = m["event_date"]
        last_move[k] = max(last_move.get(k, d), d)
        if m["kind"] == "novedad":
            sec = m.get("section") if m.get("section") in SECTIONS else "otro"
            news = news_by_key.setdefault(k, {})
            news[sec] = news.get(sec, 0) + int(m["quantity"])
        elif m["kind"] == "despliegue":
            deployed_all[k] = deployed_all.get(k, 0) + int(m["quantity"])
            if in_period(d):
                deployed_period += int(m["quantity"])
        elif m["kind"] == "ingreso":
            first_cut[k] = min(first_cut.get(k, d), d)
            day_cuts = cuts_by_key.setdefault(k, {}).setdefault(d, {})
            size = str(m.get("size") or "")
            day_cuts[size] = day_cuts.get(size, 0) + int(m["quantity"])

    closed_period = 0
    closed_keys: set[str] = set()
    last_close: dict[str, date] = {}
    for c in closures:
        last_close[c["key"]] = max(last_close.get(c["key"], c["day"]), c["day"])
        if in_period(c["day"]):
            closed_period += int(c["quantity"])
            closed_keys.add(c["key"])

    secs_by_key = {t["key"]: int(t["seconds"]) for t in time_by_ref}
    people_by_key: dict[str, dict[str, int]] = {}
    for t in time_by_person or []:
        if int(t.get("seconds") or 0) > 0:
            bucket = people_by_key.setdefault(t["key"], {})
            bucket[t["person"]] = bucket.get(t["person"], 0) + int(t["seconds"])

    def people_of(k: str) -> list[dict]:
        return [{"name": n, "seconds": s} for n, s in sorted(people_by_key.get(k, {}).items(), key=lambda kv: (-kv[1], kv[0].lower()))]
    active_by_key: dict[str, int] = {}
    for p in live.get("live", []):
        if p.get("reference_name"):
            k = group_key(p["reference_name"])
            active_by_key[k] = active_by_key.get(k, 0) + 1

    # ---- lotes
    lots = []
    for g in groups:
        k = g["key"]
        if g["meta"] <= 0 and not active_by_key.get(k) and not secs_by_key.get(k):
            continue
        starts = [d for d in (first_cut.get(k), first_session.get(k)) if d]
        lasts = [d for d in (last_move.get(k), last_close.get(k), last_session.get(k)) if d]
        started = min(starts) if starts else None
        last = max(lasts) if lasts else None
        bot_active = any(line.get("bot_active") for line in g["lines"])
        in_process = g["pending"] > 0 and (active_by_key.get(k) or bot_active or (last and (today - last).days <= RECENT_DAYS))
        done = g["meta"] > 0 and g["produced"] >= g["meta"]
        lots.append({
            "key": k, "name": g["name"], "meta": g["meta"], "closed": g["produced"], "pending": g["pending"], "received": g["received"],
            # Por enviar solo para lotes manejados con cortes (Referencias v2), donde existe el envio a Bombon.
            "sent": deployed_all.get(k, 0), "to_send": max(g["produced"] - deployed_all.get(k, 0), 0) if k in first_cut or k in deployed_all else None,
            "started": started.isoformat() if started else None, "days_open": (today - started).days + 1 if started else None,
            "last_activity": last.isoformat() if last else None, "team_seconds": secs_by_key.get(k, 0), "working_now": active_by_key.get(k, 0),
            "in_process": bool(in_process), "done": done, "last_close": last_close.get(k).isoformat() if last_close.get(k) else None,
            "bot_active": bot_active, "last_session": last_session.get(k).isoformat() if last_session.get(k) else None,
            "sizes": [{"size": line["size"], "meta": line["meta"], "received": int(line.get("received") or 0), "closed": line["produced"],
                       "pending": line["pending"]} for line in g["lines"] if line.get("reference_id") or line.get("received")],
            "cuts": [{"date": d.isoformat(), "sizes": [{"size": sz, "quantity": q} for sz, q in sorted(v.items())], "quantity": sum(v.values())}
                     for d, v in sorted(cuts_by_key.get(k, {}).items())],
            "news": [{"section": sec, "quantity": news_by_key[k][sec]} for sec in SECTIONS if news_by_key.get(k, {}).get(sec)],
            "team": [p["name"] for p in people_of(k)], "people": people_of(k),
        })

    # Promedio de dias por lote: los completados en el periodo; si no hay, todos los completados.
    def spans(items: list[dict]) -> list[int]:
        return [(date.fromisoformat(lot["last_close"]) - date.fromisoformat(lot["started"])).days + 1 for lot in items]

    done_all = [lot for lot in lots if lot["done"] and lot["last_close"] and lot["started"]]
    finished = [lot for lot in done_all if in_period(date.fromisoformat(lot["last_close"]))]
    avg_ref = spans(finished) or spans(done_all)
    avg_days = round(sum(avg_ref) / len(avg_ref), 1) if avg_ref else None
    for lot in lots:
        lot["late"] = bool(avg_days and lot["days_open"] and not lot["done"] and lot["days_open"] > avg_days)
    lots_in_process = sorted([lot for lot in lots if lot["in_process"]], key=lambda lot: (-lot["working_now"], -(lot["team_seconds"] or 0), lot["name"].lower()))

    # ---- seis cifras
    kpis: dict[str, dict] = {}
    kpis["workshop_now"] = {"status": "ok", "value": live.get("working", 0) + live.get("paused", 0), "working": live.get("working", 0),
                            "paused": live.get("paused", 0), "lots": len({k for k in active_by_key})}
    if not closures:
        kpis["closed"] = _sin("Aún no hay cierres registrados.")
    else:
        kpis["closed"] = {"status": "ok", "value": closed_period, "lots": len(closed_keys)}
    has_deploys = any(m["kind"] == "despliegue" for m in moves)
    if not has_deploys:
        kpis["sent"] = _sin("Aún no hay envíos a Bombón registrados en Referencias.")
    else:
        to_send = sum(lot["to_send"] or 0 for lot in lots if lot["to_send"] is not None)
        kpis["sent"] = {"status": "ok", "value": deployed_period, "to_send": to_send}
    if not finished:
        kpis["days_per_lot"] = _sin("Ningún lote se completó en el periodo.")
    else:
        kpis["days_per_lot"] = {"status": "ok", "value": round(sum(spans(finished)) / len(finished), 1), "lots": len(finished)}
    if closed_period <= 0:
        kpis["team_hours_per_garment"] = _sin("Sin prendas cerradas en el periodo.")
        kpis["labor_per_garment"] = _sin("Sin prendas cerradas en el periodo.")
    else:
        kpis["team_hours_per_garment"] = (_sin("Sin tiempo de equipo registrado en el periodo.") if team_seconds <= 0 else
                                          {"status": "ok", "value": round(team_seconds / closed_period / 60, 1), "team_minutes": round(team_seconds / 60)})
        kpis["labor_per_garment"] = (_sin("Sin nómina calculada en el periodo.") if not labor_gross or labor_gross <= 0 else
                                     {"status": "ok", "value": round(labor_gross / closed_period, 2), "labor": round(labor_gross, 2)})

    # ---- cerradas vs enviadas por semana o mes
    keys, by_month = buckets(start, end)
    series = {b: {"bucket": b.isoformat(), "closed": 0, "sent": 0} for b in keys}
    for c in closures:
        if in_period(c["day"]):
            series[bucket_of(c["day"], by_month)]["closed"] += int(c["quantity"])
    for m in moves:
        if m["kind"] == "despliegue" and in_period(m["event_date"]) and key_of_move(m):
            series[bucket_of(m["event_date"], by_month)]["sent"] += int(m["quantity"])

    # ---- tiempo del equipo por referencia (participacion, no productividad)
    total = sum(secs_by_key.values()) or 0
    share = [{"key": k, "name": name_of.get(k, k), "seconds": s, "percent": round(s * 100 / total, 1) if total else 0, "people": people_of(k)}
             for k, s in sorted(secs_by_key.items(), key=lambda kv: -kv[1]) if s > 0]

    # ---- alertas
    alerts = []
    for p in live.get("live", []):
        if (p.get("elapsed_minutes") or 0) >= LONG_SESSION_MIN:
            alerts.append({"kind": "long_session", "level": "danger", "reference": p.get("reference_name") or "", "minutes": p["elapsed_minutes"]})
    open_news: dict[str, dict] = {}
    for lot in lots:
        progress = lot["closed"] / lot["meta"] if lot["meta"] else 0
        if lot["in_process"] and lot["late"] and progress < LOW_PROGRESS:
            alerts.append({"kind": "slow_lot", "level": "danger", "reference": lot["name"], "days": lot["days_open"], "avg": avg_days,
                           "percent": round(progress * 100)})
        if lot["pending"] > 0:
            for n in lot["news"]:
                item = open_news.setdefault(n["section"], {"quantity": 0, "refs": []})
                item["quantity"] += n["quantity"]
                item["refs"].append(lot["name"])
        if lot["bot_active"] and lot["pending"] > 0 and not lot["working_now"]:
            last = date.fromisoformat(lot["last_session"]) if lot["last_session"] else None
            if last is None or (today - last).days >= NO_TIME_DAYS:
                alerts.append({"kind": "no_recent_time", "level": "info", "reference": lot["name"], "days": (today - last).days if last else None})
        if lot["to_send"]:
            alerts.append({"kind": "not_sent", "level": "warning", "reference": lot["name"], "quantity": lot["to_send"]})
    for sec in SECTIONS:
        if sec in open_news:
            alerts.append({"kind": "open_news", "level": "warning", "reference": ", ".join(open_news[sec]["refs"]), "section": sec,
                           "quantity": open_news[sec]["quantity"]})

    return {
        "period": {"from": start.isoformat(), "to": end.isoformat(), "by": "month" if by_month else "week"},
        "data_check": {"closures_total": len(closures), "closures_period": sum(1 for c in closures if in_period(c["day"])),
                       "cut_movements": len(moves), "deploys": sum(1 for m in moves if m["kind"] == "despliegue"),
                       "team_minutes_period": round(team_seconds / 60), "lots": len(lots)},
        "kpis": kpis,
        "lots_in_process": lots_in_process,
        "live": [{"name": p["name"], "status": p["status"], "reference": p.get("reference_name"), "since": p.get("since"),
                  "elapsed_minutes": p.get("elapsed_minutes")} for p in live.get("live", [])],
        "series": list(series.values()),
        "team_time": {"total_seconds": total, "by_reference": share},
        "alerts": alerts,
    }


# ---------------------------------------------------------------- datos
async def insights(db: AsyncSession, company_id: str, start: date, end: date, today: date) -> dict:
    from app.api.v1.endpoints import production_v1 as prod
    from app.services import crm_lab, references_v2
    from app.services.references_v2 import group_key

    cid = str(company_id)
    tz = prod._tz052c().key
    groups = await references_v2.reference_groups(db, cid)
    rows = (await db.execute(text("SELECT id, name FROM product_references WHERE company_id = :c"), {"c": cid})).mappings().all()
    key_by_id = {r["id"]: group_key(r["name"]) for r in rows}
    moves = [dict(r) for r in (await db.execute(text("""
        SELECT reference_id, kind, size, section, quantity, event_date FROM reference_cut_movements
        WHERE company_id = :c AND voided_at IS NULL AND kind IN ('ingreso', 'novedad', 'despliegue')
    """), {"c": cid})).mappings().all()]
    closures = []
    for r in (await db.execute(text("""
        SELECT COALESCE(reference_id, '') AS reference_id, COALESCE(reference_name, '') AS reference_name, COALESCE(quantity_finished, 0) AS q,
               (closed_at AT TIME ZONE CAST(:tz AS text))::date AS day
        FROM reference_production_closures WHERE company_id = :c
    """), {"c": cid, "tz": tz})).mappings().all():
        closures.append({"key": key_by_id.get(r["reference_id"]) or group_key(r["reference_name"]), "quantity": int(r["q"]), "day": r["day"]})
    first_session, last_session = {}, {}
    for r in (await db.execute(text("""
        SELECT reference_name, min((started_at AT TIME ZONE CAST(:tz AS text))::date) AS first,
               max((COALESCE(ended_at, started_at) AT TIME ZONE CAST(:tz AS text))::date) AS last
        FROM reference_work_sessions WHERE company_id = :c GROUP BY reference_name
    """), {"c": cid, "tz": tz})).mappings().all():
        k = group_key(r["reference_name"])
        first_session[k] = min(first_session.get(k, r["first"]), r["first"])
        last_session[k] = max(last_session.get(k, r["last"]), r["last"])
    sessions = await prod.sessions_summary(db, cid, start, end)
    time_by_ref: dict[str, dict] = {}
    for t in sessions.get("time_by_reference", []):
        k = group_key(t.get("reference_name"))
        item = time_by_ref.setdefault(k, {"key": k, "name": t.get("reference_name") or "", "seconds": 0, "active": 0})
        item["seconds"] += int(t.get("total_effective_seconds") or 0)
        item["active"] += int(t.get("active_sessions") or 0)
    time_by_person = [{"key": group_key(t.get("reference_name")), "person": (t.get("employee_name") or "").strip() or "—",
                       "seconds": int(t.get("effective_seconds") or 0)} for t in sessions.get("time_by_operator_reference", [])]
    live = await crm_lab.team(db, cid)
    closed_period = sum(c["quantity"] for c in closures if start <= c["day"] <= end)
    labor = await labor_gross(db, company_id, start, end) if closed_period > 0 else None
    return build(start=start, end=end, today=today, groups=groups, key_by_id=key_by_id, moves=moves, closures=closures,
                 first_session=first_session, last_session=last_session, team_seconds=int(sessions.get("total_effective_seconds_period") or 0),
                 time_by_ref=list(time_by_ref.values()), live=live, labor_gross=labor, time_by_person=time_by_person)


async def labor_gross(db: AsyncSession, company_id: Any, start: date, end: date) -> Optional[float]:
    """Bruto de nomina del EQUIPO en el periodo (el mismo calculo de Nomina)."""
    from uuid import UUID

    try:
        from app.api.v1.endpoints.payroll import calculate_period_snapshot

        snap = await calculate_period_snapshot(db, UUID(str(company_id)), start, end)
        totals = snap.get("totals") if isinstance(snap.get("totals"), dict) else {}
        value = totals.get("gross_amount")
        if value is None:
            value = sum(float(r.get("gross_amount") or 0) for r in snap.get("rows") or snap.get("employees") or [] if isinstance(r, dict))
        return float(value or 0)
    except Exception:  # noqa: BLE001 - sin nomina, la cifra dice "Sin datos aun"
        await db.rollback()
        return None


# ---------------------------------------------------------------- PDF
def hm(minutes: Any) -> str:
    m = max(0, round(float(minutes or 0)))
    return f"{m // 60} h {m % 60:02d} min"


def build_pdf(ins: dict, company: dict, logo_reader=None) -> bytes:
    """Carta, fondo blanco, logo del panel inicial, periodo y "Pagina X de Y";
    textos traducidos al idioma de la empresa (pdf_i18n)."""
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfbase.pdfmetrics import stringWidth
    from reportlab.pdfgen import canvas

    from app.services import pdf_i18n
    from app.services import company_locale
    from app.services.reports_v2 import fmt_day, money

    tz = company_locale.current_zone()
    fmt_date = lambda v: fmt_day(v, tz)  # noqa: E731

    tr = pdf_i18n.tr
    width, height = letter
    margin = 46
    ink, soft, line = (0.07, 0.09, 0.15), (0.38, 0.42, 0.5), (0.85, 0.87, 0.9)
    page_word, of_word = tr("Página"), tr("de")
    footer = f"{company.get('name') or ''} · {tr('Producción')}"

    class Numbered(canvas.Canvas):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            self._pages = []

        def showPage(self):
            self._pages.append(dict(self.__dict__))
            self._startPage()

        def save(self):
            total = len(self._pages)
            for state in self._pages:
                self.__dict__.update(state)
                self.setFont("Helvetica", 8)
                self.setFillColorRGB(*soft)
                self.drawRightString(width - margin, 24, f"{page_word} {self._pageNumber} {of_word} {total}")
                self.drawString(margin, 24, footer)
                canvas.Canvas.showPage(self)
            canvas.Canvas.save(self)

    buf = io.BytesIO()
    c = Numbered(buf, pagesize=letter)
    y = height - margin

    def ensure(space: float) -> None:
        nonlocal y
        if y - space < margin + 20:
            c.showPage()
            y = height - margin

    def fit(value: Any, size: float, maxw: float, font: str = "Helvetica") -> str:
        s = str(tr(str(value)) if value is not None else "")
        while s and stringWidth(s, font, size) > maxw:
            s = s[:-2] + "…" if len(s) > 2 else ""
        return s

    def section(title: str) -> None:
        nonlocal y
        ensure(44)
        y -= 10
        c.setFont("Helvetica-Bold", 11)
        c.setFillColorRGB(*ink)
        c.drawString(margin, y, tr(title))
        y -= 6
        c.setStrokeColorRGB(*line)
        c.line(margin, y, width - margin, y)
        y -= 14

    def note(message: str) -> None:
        nonlocal y
        ensure(16)
        c.setFont("Helvetica", 9)
        c.setFillColorRGB(*soft)
        c.drawString(margin, y, fit(message, 9, width - 2 * margin))
        y -= 14

    def table(headers: list, rows: list, widths: list, aligns: list) -> None:
        nonlocal y
        total_w = width - 2 * margin
        cols = [w * total_w for w in widths]

        def head() -> None:
            nonlocal y
            c.setFont("Helvetica-Bold", 8)
            c.setFillColorRGB(*soft)
            x = margin
            for h_, w, a in zip(headers, cols, aligns):
                label = fit(h_, 8, w - 4, "Helvetica-Bold")
                (c.drawRightString(x + w - 2, y, label) if a == "r" else c.drawString(x + 2, y, label))
                x += w
            y -= 12

        ensure(30)
        head()
        for r in rows:
            if y - 14 < margin + 20:
                c.showPage()
                y = height - margin
                head()
            c.setFont("Helvetica", 8.5)
            c.setFillColorRGB(*ink)
            x = margin
            for v, w, a in zip(r, cols, aligns):
                s = fit(v, 8.5, w - 4)
                (c.drawRightString(x + w - 2, y, s) if a == "r" else c.drawString(x + 2, y, s))
                x += w
            y -= 13

    # encabezado
    if logo_reader is not None:
        try:
            c.drawImage(logo_reader, margin, y - 40, width=44, height=44, preserveAspectRatio=True, mask="auto")
        except Exception:  # noqa: BLE001
            pass
    left = margin + (54 if logo_reader is not None else 0)
    c.setFont("Helvetica-Bold", 16)
    c.setFillColorRGB(*ink)
    c.drawString(left, y - 14, fit(f"{company.get('name') or ''} · {tr('Producción')}", 16, width - margin - left, "Helvetica-Bold"))
    c.setFont("Helvetica", 9.5)
    c.setFillColorRGB(*soft)
    p = ins["period"]
    c.drawString(left, y - 30, f"{tr('Periodo')}: {fmt_date(p['from'])} – {fmt_date(p['to'])}")
    y -= 58

    k = ins["kpis"]

    def val(key: str, render) -> str:
        item = k.get(key) or {}
        return tr("Sin datos aún") if item.get("status") != "ok" else render(item)

    section("Cifras del periodo")
    table(["Cifra", "Valor", "Detalle"], [
        [tr("En el taller ahora"), val("workshop_now", lambda i: str(i["value"])),
         tr("{w} trabajando · {p} en pausa · {l} lotes").replace("{w}", str(k["workshop_now"]["working"])).replace("{p}", str(k["workshop_now"]["paused"])).replace("{l}", str(k["workshop_now"]["lots"]))],
        [tr("Prendas cerradas"), val("closed", lambda i: str(i["value"])), tr("{n} lotes").replace("{n}", str(k["closed"].get("lots", 0))) if k["closed"].get("status") == "ok" else tr(k["closed"]["reason"])],
        [tr("Enviadas a Bombón"), val("sent", lambda i: str(i["value"])), tr("{n} cerradas por enviar").replace("{n}", str(k["sent"].get("to_send", 0))) if k["sent"].get("status") == "ok" else tr(k["sent"]["reason"])],
        [tr("Días por lote"), val("days_per_lot", lambda i: str(i["value"])), tr("{n} lotes completos").replace("{n}", str(k["days_per_lot"].get("lots", 0))) if k["days_per_lot"].get("status") == "ok" else tr(k["days_per_lot"]["reason"])],
        [tr("Horas-equipo por prenda"), val("team_hours_per_garment", lambda i: hm(i["value"])), "" if k["team_hours_per_garment"].get("status") == "ok" else tr(k["team_hours_per_garment"]["reason"])],
        [tr("Mano de obra por prenda"), val("labor_per_garment", lambda i: money(i["value"])), tr("Nómina del equipo: {m}").replace("{m}", money(k["labor_per_garment"]["labor"])) if k["labor_per_garment"].get("status") == "ok" else tr(k["labor_per_garment"]["reason"])],
    ], [0.3, 0.2, 0.5], ["l", "r", "l"])

    section("Lotes en proceso")
    if ins["lots_in_process"]:
        table(["Referencia", "Meta", "Cerradas", "Pendiente", "Enviadas", "Días", "Tiempo del equipo"],
              [[lot["name"], lot["meta"], lot["closed"], lot["pending"], lot["sent"], lot["days_open"] or "—", hm((lot["team_seconds"] or 0) / 60)]
               for lot in ins["lots_in_process"]], [0.3, 0.09, 0.11, 0.11, 0.11, 0.08, 0.2], ["l", "r", "r", "r", "r", "r", "r"])
    else:
        note(tr("Sin lotes en proceso."))

    section("Cerradas vs enviadas")
    table(["Semana" if ins["period"]["by"] == "week" else "Mes", "Cerradas", "Enviadas"],
          [[fmt_date(s["bucket"]), s["closed"], s["sent"]] for s in ins["series"]], [0.5, 0.25, 0.25], ["l", "r", "r"])

    section("Tiempo del equipo por referencia")
    note(tr("Participación del tiempo del equipo, no productividad."))
    if ins["team_time"]["by_reference"]:
        table(["Referencia", "Tiempo del equipo", "Participación"],
              [[r["name"], hm(r["seconds"] / 60), f"{r['percent']}%"] for r in ins["team_time"]["by_reference"]], [0.5, 0.25, 0.25], ["l", "r", "r"])
    else:
        note(tr("Sin tiempo del equipo en el periodo."))

    section("Alertas")
    if ins["alerts"]:
        for a in ins["alerts"]:
            note(f"• {alert_text(a, tr)}")
    else:
        note(tr("Sin alertas."))
    c.showPage()  # cierra la ultima pagina (Numbered la numera al guardar)
    c.save()
    return buf.getvalue()


SECTION_LABEL = {"corte": "Corte", "bordado": "Bordado", "taller": "Taller", "lavado": "Lavado", "otro": "Otro"}


def alert_text(a: dict, tr=lambda s: s) -> str:
    ref = a.get("reference") or ""
    if a["kind"] == "long_session":
        return tr("{ref}: hay una sesión abierta hace más de 12 h (¿se olvidó cerrar?)").replace("{ref}", ref)
    if a["kind"] == "slow_lot":
        return (tr("{ref}: {d} días abierto (promedio {a}) y {p}% cerrado").replace("{ref}", ref).replace("{d}", str(a["days"]))
                .replace("{a}", str(a["avg"])).replace("{p}", str(a["percent"])))
    if a["kind"] == "open_news":
        return (tr("Novedades en {s}: {n} prendas ({ref})").replace("{s}", tr(SECTION_LABEL.get(a["section"], a["section"])))
                .replace("{n}", str(a["quantity"])).replace("{ref}", ref))
    if a["kind"] == "no_recent_time":
        if a.get("days") is None:
            return tr("{ref}: referencia activa sin tiempo registrado").replace("{ref}", ref)
        return tr("{ref}: referencia activa sin tiempo registrado hace {d} días").replace("{ref}", ref).replace("{d}", str(a["days"]))
    return tr("{ref}: {n} prendas cerradas sin enviar a Bombón").replace("{ref}", ref).replace("{n}", str(a.get("quantity", 0)))
