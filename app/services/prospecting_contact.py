"""Canales de contacto de la prospeccion de Nexa que NO son correo (interno de Clonexa, sin company_id).

- COLA ASISTIDA (Instagram / Facebook): Nexa NO envia nada. Cada dia habil arma hasta 15 negocios (configurable)
  con el texto ya escrito; el dueno lo copia y lo envia A MANO desde la cuenta de Clonexa. Los botones de
  Telegram solo registran lo que el dueno hizo: Enviado (cuenta como contacto: 1 por semana y seguimiento unico
  a los 7 dias), Saltar, No contactar (baja permanente en TODOS los canales).
- RUTA DE VISITAS: hasta 20 negocios de una zona (incluidos los "por verificar"), ordenados por cercania, con
  "Abrir en Google Maps". Marcar "Visitado" registra el contacto.
- WhatsApp publicado: nunca se usa para escribir en frio (solo se muestra en la ficha).

Ley 2300 de 2023: lunes a viernes 8:00-17:00 hora Bogota (sin festivos), maximo 1 contacto por semana por
negocio (contando correo, mensaje asistido y visita), mensaje + 1 seguimiento y nada mas, baja inmediata.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import prospecting as ps
from app.services import prospecting_email as pe
from app.services import prospecting_niches as pn

ASSISTED_CHANNELS = ("instagram", "facebook")
NETWORK_LABEL = {"instagram": "Instagram", "facebook": "Facebook"}
ROUTE_LIMIT = 20
VISIT_COOLDOWN_DAYS = 30


def _esc(v: Any) -> str:
    return str(v or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _base_ok_sql() -> str:
    """Comun a la cola asistida: abierto, sin baja ni exclusion (lugar, correo o red), sin respuesta."""
    return f"""NOT p.is_test AND p.status NOT IN ('baja', 'respondio', 'demo', 'cliente')
               AND p.business_status IN ('', 'OPERATIONAL') AND p.replied_at IS NULL AND p.unsubscribed_at IS NULL
               AND NOT EXISTS (SELECT 1 FROM prospect_exclusions x WHERE (x.kind = 'place' AND x.value = p.place_id)
                               OR (x.kind = 'email' AND p.email <> '' AND x.value = lower(p.email)))
               AND NOT {ps.SOCIAL_EXCLUDED_SQL}"""


def assisted_eligible_sql() -> str:
    return _base_ok_sql() + """
               AND p.vigencia <> 'por_verificar'
               AND (p.channels ? 'instagram' OR p.channels ? 'facebook')
               AND (p.last_contacted_at IS NULL OR p.last_contacted_at < :week_ago)"""


def _network(channels: dict) -> Optional[str]:
    for n in ASSISTED_CHANNELS:
        if (channels or {}).get(n, {}).get("url"):
            return n
    return None


def assisted_url(p: dict, network: str, settings: dict) -> str:
    return pe.demo_url(settings.get("landing_url") or pe.DEFAULT_LANDING, p.get("zone_slug") or "", p.get("business_type") or "",
                       p.get("code") or "", source=network)


def render_assisted(p: dict, *, followup: bool, settings: dict) -> dict:
    network = _network(p.get("channels") or {}) or "instagram"
    niche = p.get("niche") or pn.niche_of(p.get("business_type") or "")
    url = assisted_url(p, network, settings)
    return {"network": network, "profile_url": ((p.get("channels") or {}).get(network) or {}).get("url", ""),
            "text": pn.assisted_text(name=p.get("name") or "", niche=niche, url=url, followup=followup), "url": url}


def telegram_item(item: dict) -> dict:
    """Mensaje de Telegram de un negocio de la cola (HTML) + datos de los 5 botones."""
    kind = "Seguimiento (unico)" if item["kind"] == "seguimiento" else "Primer mensaje"
    msg = (f"📲 <b>{_esc(item['name'])}</b>\n{_esc(item['nicho'])} · {_esc(item['tipo'])} · {_esc(item['zona'])}\n"
           f"{NETWORK_LABEL.get(item['network'], item['network'])} · {kind} · #A{item['contact_id']}\n\n"
           f"<pre>{_esc(item['text'])}</pre>\n\nCópialo, ábrele el perfil y envíalo tú. Luego toca ✅ Enviado.")
    return {"mensaje": msg[:4000], "perfil": item["profile_url"], "id": item["contact_id"],
            "botones": {"copiar": f"pa:copiar:{item['contact_id']}", "enviado": f"pa:enviado:{item['contact_id']}",
                        "saltar": f"pa:saltar:{item['contact_id']}", "bloquear": f"pa:bloquear:{item['contact_id']}"}}


async def _queue_items(db: AsyncSession, day) -> list[dict]:
    rows = await ps._rows(db, """
        SELECT c.id AS contact_id, c.kind, c.status, c.channel AS network, c.detail, p.id::text AS prospect_id, p.name, p.business_type,
               p.niche, z.name AS zona
        FROM prospect_contacts c JOIN prospects p ON p.id = c.prospect_id LEFT JOIN prospect_zones z ON z.id = p.zone_id
        WHERE c.local_date = :d AND c.channel IN ('instagram', 'facebook') AND c.kind IN ('inicial', 'seguimiento')
        ORDER BY c.id""", {"d": day})
    out = []
    for r in rows:
        d = r.pop("detail") or {}
        out.append({**r, "text": d.get("texto", ""), "profile_url": d.get("perfil", ""), "tipo": ps.TYPE_LABEL.get(r["business_type"], ""),
                    "nicho": pn.NICHES.get(r["niche"], {}).get("label", ""), "zona": r["zona"] or ""})
    return out


async def build_assisted_queue(db: AsyncSession, at: Optional[datetime] = None, *, test_only: bool = False) -> dict:
    """Cola del dia (idempotente por fecha). Seguimientos vencidos primero; luego negocios de prioridad 1, con
    vigencia activa, SIN correo (los que tienen correo van por correo) y sin ningun contacto previo."""
    t = at or ps.now()
    b = ps.bogota(t)
    day = b.date()
    if not ps.is_business_day(day):
        return {"items": [], "motivo": "festivo" if day.weekday() < 5 else "fin_de_semana", "nuevos": 0}
    cfg = await ps.get_settings(db)
    if not (int(cfg["window_start"]) <= b.hour < int(cfg["window_end"])) and not test_only:
        return {"items": await _queue_items(db, day), "motivo": "fuera_de_horario", "nuevos": 0}
    # lo de dias anteriores que no se marco, vence (vuelve a ser elegible otro dia)
    await db.execute(text("""UPDATE prospect_contacts SET status = 'vencido' WHERE status = 'pendiente'
                             AND channel IN ('instagram', 'facebook') AND local_date < :d"""), {"d": day})
    existing = await _queue_items(db, day)
    if existing and not test_only:
        await db.commit()
        return {"items": existing, "motivo": "", "nuevos": 0}
    limit = int(cfg["assisted_daily_limit"])
    params = {"week_ago": t - timedelta(days=ps.WEEK_DAYS), "follow_cut": t - timedelta(days=ps.FOLLOWUP_DAYS), "lim": limit, "d": day}
    test_sql = "p.is_test AND p.place_id LIKE 'clonexa-prueba-%'" if test_only else ""
    base = (_base_ok_sql().replace("NOT p.is_test AND ", "") + """ AND (p.channels ? 'instagram' OR p.channels ? 'facebook')""") \
        if test_only else assisted_eligible_sql()
    already = "TRUE" if test_only else "NOT EXISTS (SELECT 1 FROM prospect_contacts q WHERE q.prospect_id = p.id AND q.local_date = :d AND q.channel IN ('instagram', 'facebook'))"
    follow = [] if test_only else await ps._rows(db, f"""
        SELECT p.id::text AS id, 'seguimiento' AS kind FROM prospects p WHERE {base} AND {already}
          AND p.assisted_count = 1 AND p.assisted_followup_at IS NULL AND p.assisted_first_at <= :follow_cut
        ORDER BY p.assisted_first_at LIMIT :lim""", params)
    params["lim"] = max(0, limit - len(follow))
    prio = "CASE " + " ".join(f"WHEN p.niche = '{k}' THEN {pn.priority(k) if k != 'restaurante' else 3}" for k in pn.NICHES) + " ELSE 9 END"
    fresh_where = (f"{test_sql} AND {base}" if test_only else
                   f"""{base} AND p.assisted_count = 0 AND p.email = '' AND p.contact_count = 0 AND p.last_contacted_at IS NULL
                       AND p.visit_count = 0""")
    fresh = await ps._rows(db, f"""
        SELECT p.id::text AS id, 'inicial' AS kind FROM prospects p WHERE {fresh_where} AND {already}
        ORDER BY {prio}, CASE WHEN p.vigencia = 'activo' THEN 0 ELSE 1 END, p.created_at LIMIT :lim""", params) if params["lim"] else []
    n = 0
    for it in follow + fresh:
        p = await ps.prospect_by(db, "id", it["id"])
        r = render_assisted(p, followup=it["kind"] == "seguimiento", settings=cfg)
        if not r["profile_url"]:
            continue
        cid = await ps.log_contact(db, p["id"], r["network"], it["kind"], status="pendiente",
                                   detail={"texto": r["text"], "perfil": r["profile_url"], "enlace": r["url"], "prueba": test_only})
        await db.execute(text("UPDATE prospect_contacts SET local_date = :d WHERE id = :i"), {"d": day, "i": cid})
        n += 1
    await db.commit()
    items = await _queue_items(db, day)
    if test_only:
        items = [i for i in items if i["prospect_id"] in {x["id"] for x in fresh}]
    return {"items": items, "motivo": "" if items else "sin_prospectos", "nuevos": n}


ACTION_TEXT = {
    "enviado": "✅ Enviado: quedó registrado (cuenta como el contacto de la semana; seguimiento único en 7 días si no responde).",
    "saltar": "⏭ Saltado: no se registró contacto; puede volver a la cola otro día.",
    "bloquear": "🚫 No contactar: quedó en la lista de exclusión permanente (correo, Instagram, Facebook y visitas).",
}


async def assisted_action(db: AsyncSession, contact_id: int, action: str, at: Optional[datetime] = None) -> dict:
    """Lo que el dueno toco en Telegram. Devuelve {ok, mensaje, editar, texto?}."""
    t = at or ps.now()
    c = await ps._one(db, """SELECT id, prospect_id::text AS pid, channel, kind, status, local_date, detail FROM prospect_contacts
                            WHERE id = :i AND channel IN ('instagram', 'facebook')""", {"i": contact_id})
    if not c:
        raise LookupError("no_existe")
    if action == "copiar":
        return {"ok": True, "editar": False, "texto": (c["detail"] or {}).get("texto", ""), "mensaje": "Texto listo para copiar."}
    if c["status"] != "pendiente":
        return {"ok": False, "editar": True, "mensaje": f"Este mensaje ya estaba {c['status']}."}
    p = await ps.prospect_by(db, "id", c["pid"])
    if action == "saltar":
        await db.execute(text("UPDATE prospect_contacts SET status = 'saltado' WHERE id = :i"), {"i": contact_id})
        await db.commit()
        return {"ok": True, "editar": True, "mensaje": ACTION_TEXT["saltar"]}
    if action == "bloquear":
        await ps.unsubscribe(db, p, reason="no_contactar", channel=c["channel"])
        return {"ok": True, "editar": True, "mensaje": ACTION_TEXT["bloquear"]}
    if action != "enviado":
        raise ValueError("accion_invalida")
    cfg = await ps.get_settings(db)
    if not ps.in_legal_window(t, int(cfg["window_start"]), int(cfg["window_end"])):
        return {"ok": False, "editar": False, "mensaje": "⏰ Fuera del horario legal (lunes a viernes 8:00 a 17:00, sin festivos): "
                "no lo envíes ahora. Queda en la cola de hoy y vence si no se envía."}
    if c["local_date"] != ps.bogota(t).date():
        await db.execute(text("UPDATE prospect_contacts SET status = 'vencido' WHERE id = :i"), {"i": contact_id})
        await db.commit()
        return {"ok": False, "editar": True, "mensaje": "Este mensaje era de otro día: venció (no lo envíes)."}
    is_test = bool(p and p.get("is_test"))
    ok = await ps._one(db, f"SELECT 1 AS x FROM prospects p WHERE p.id = CAST(:i AS uuid) AND "
                           f"{_base_ok_sql().replace('NOT p.is_test AND ', '') if is_test else _base_ok_sql()}"
                           " AND (p.last_contacted_at IS NULL OR p.last_contacted_at < :week_ago)",
                       {"i": c["pid"], "week_ago": t - timedelta(days=ps.WEEK_DAYS)})
    if not ok:
        await db.execute(text("UPDATE prospect_contacts SET status = 'cancelado' WHERE id = :i"), {"i": contact_id})
        await db.commit()
        return {"ok": False, "editar": True, "mensaje": "🚫 Ya no se puede: el negocio se dio de baja, respondió o ya tuvo un contacto esta semana. No lo envíes."}
    await db.execute(text("UPDATE prospect_contacts SET status = 'enviado', sent_at = :t WHERE id = :i"), {"i": contact_id, "t": t})
    follow = ", assisted_followup_at = :t" if c["kind"] == "seguimiento" else ""
    await db.execute(text(f"""UPDATE prospects SET assisted_count = assisted_count + 1, assisted_first_at = COALESCE(assisted_first_at, :t),
                              last_contacted_at = :t{follow}, updated_at = now() WHERE id = CAST(:p AS uuid)"""), {"p": c["pid"], "t": t})
    await ps._promote(db, c["pid"], "contactado")
    await db.commit()
    return {"ok": True, "editar": True, "mensaje": ACTION_TEXT["enviado"]}


# ---------------------------------------------------------------- ruta de visitas
async def route_of_day(db: AsyncSession, zone_id: int, *, niche: str = "", limit: int = ROUTE_LIMIT,
                       start: Optional[tuple[float, float]] = None, at: Optional[datetime] = None) -> dict:
    zone = await ps._one(db, f"SELECT {ps.ZONE_COLS} FROM prospect_zones WHERE id = :i", {"i": zone_id})
    if not zone:
        raise LookupError("zona_no_existe")
    t = at or ps.now()
    params: dict[str, Any] = {"z": zone_id, "week_ago": t - timedelta(days=ps.WEEK_DAYS),
                              "visit_cut": t - timedelta(days=VISIT_COOLDOWN_DAYS)}
    extra = ""
    if niche in pn.NICHES:
        extra = " AND p.niche = :n"
        params["n"] = niche
    rows = await ps._rows(db, f"""
        SELECT p.id::text AS id, p.code, p.place_id, p.name, p.address, p.lat, p.lng, p.niche, p.business_type, p.vigencia, p.status,
               p.phone
        FROM prospects p
        WHERE p.zone_id = :z AND p.lat IS NOT NULL AND {_base_ok_sql()}
          AND (p.last_contacted_at IS NULL OR p.last_contacted_at < :week_ago)
          AND (p.last_visit_at IS NULL OR p.last_visit_at < :visit_cut){extra}
        LIMIT 400""", params)
    origin = start or (zone["center_lat"], zone["center_lng"])
    stops = pn.order_route(origin, rows, limit=max(1, min(ROUTE_LIMIT, limit)))
    for s in stops:
        s["maps_url"] = pn.maps_place_url(s["name"], s["place_id"], s["lat"], s["lng"])
        s["nicho"] = pn.NICHES.get(s["niche"], {}).get("label", "")
        s["tipo"] = ps.TYPE_LABEL.get(s["business_type"], "")
        s.pop("place_id", None)
    return {"zone": {k: zone[k] for k in ("id", "slug", "name", "center_lat", "center_lng")}, "start": list(origin), "stops": stops,
            "route_url": pn.maps_route_url(origin, stops), "total_m": stops[-1]["acumulado_m"] if stops else 0,
            "fecha": ps.bogota(t).date().isoformat()}


def route_telegram(route: dict) -> dict:
    z = route["zone"]
    head = (f"🗺️ <b>Ruta del día · {_esc(z['name'])}</b> ({route['fecha']})\n{len(route['stops'])} negocios, "
            f"~{round(route['total_m'] / 1000, 1)} km a pie. Incluye los \"por verificar\" (confirma si siguen abiertos).\n"
            "Visitas de lunes a viernes, 8:00 a 17:00. Toca ✅ Visitado en cada uno.")
    stops = [{"code": s["code"], "mensaje": (f"{s['orden']}. <b>{_esc(s['name'])}</b>{' · por verificar' if s['vigencia'] == 'por_verificar' else ''}\n"
                                             f"{_esc(s['nicho'])} · {_esc(s['tipo'])}\n📍 {_esc(s['address'])}"),
              "maps_url": s["maps_url"], "callback": f"pv:visitado:{s['code']}"} for s in route["stops"]]
    return {"cabecera": head, "ruta_url": route["route_url"], "paradas": stops}


async def mark_visited(db: AsyncSession, *, prospect_id: str = "", code: str = "", at: Optional[datetime] = None,
                       by: str = "consola") -> dict:
    t = at or ps.now()
    p = await ps.prospect_by(db, "id", prospect_id) if prospect_id else await ps.prospect_by(db, "code", (code or "").upper())
    if not p:
        raise LookupError("no_existe")
    cfg = await ps.get_settings(db)
    if not ps.in_legal_window(t, int(cfg["window_start"]), int(cfg["window_end"])):
        return {"ok": False, "mensaje": "⏰ Fuera del horario legal (lunes a viernes 8:00 a 17:00): la visita no se registra."}
    if p["status"] == "baja":
        return {"ok": False, "mensaje": "🚫 Este negocio está en la lista de exclusión: no se visita."}
    if p.get("last_visit_at") and p["last_visit_at"] > t - timedelta(hours=12):
        return {"ok": True, "mensaje": f"✅ {p['name']} ya estaba marcado como visitado hoy.", "repetido": True}
    last = p.get("last_contacted_at")
    if last and last > t - timedelta(days=ps.WEEK_DAYS):
        return {"ok": False, "mensaje": "Ya tuvo un contacto esta semana (correo, mensaje o visita): la visita queda para otra semana."}
    await ps.log_contact(db, p["id"], "visita", "visita", status="registrado", detail={"por": by[:20]})
    await db.execute(text("""UPDATE prospects SET visit_count = visit_count + 1, last_visit_at = :t, last_contacted_at = :t, updated_at = now()
                             WHERE id = CAST(:i AS uuid)"""), {"i": p["id"], "t": t})
    await ps._promote(db, p["id"], "contactado")
    await db.commit()
    return {"ok": True, "mensaje": f"✅ Visitado: {p['name']} (contacto registrado).", "repetido": False}
