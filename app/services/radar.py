"""NEXUS · Radar de innovacion de Clonexa (interno: sin company_id; solo Admin V2 / v2+ y n8n).

Una sola fuente: el backend. Telegram (NEXUS) y la consola leen y cambian lo mismo.
- Puntaje = impacto vs esfuerzo vs costo (0-100); se ordena por puntaje.
- No repetir: una idea con la misma huella, un titulo parecido o la misma fuente principal en los ultimos 90 dias se
  descarta.
- Tope de gasto: maximo 3 informes a pedido por dia (Bogota). El semanal (lunes 8:00) no cuenta.
- Un informe "corriendo" de hace mas de 20 minutos se da por fallido (n8n se cayo).
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

BOGOTA = timezone(timedelta(hours=-5))
STATES = ("nueva", "me_interesa", "backlog", "en_curso", "hecha", "descartada")
STATE_LABEL = {"nueva": "Nueva", "me_interesa": "⭐ Me interesa", "backlog": "🗂 Backlog", "en_curso": "En curso", "hecha": "Hecha",
               "descartada": "✖ Descartada"}
LEVELS = ("alto", "medio", "bajo")
CATEGORIES = ("herramientas", "competencia", "fondos", "normas", "nichos", "otra")
CATEGORY_LABEL = {"herramientas": "Herramientas y APIs", "competencia": "Competencia", "fondos": "Fondos y convocatorias",
                  "normas": "Leyes y normas", "nichos": "Ideas por nicho", "otra": "Otra"}
DAILY_ON_DEMAND = 3
DEDUP_DAYS = 90
STALE_MIN = 20
IDEAS_WEEKLY, IDEAS_ON_DEMAND = 5, 3
STOP = {"de", "la", "el", "los", "las", "y", "en", "para", "con", "por", "del", "un", "una", "a", "al", "que", "se", "su", "sus",
        "o", "lo", "es", "como", "mas", "the", "of", "and", "to", "for", "in", "on", "nuevo", "nueva"}


def now() -> datetime:
    return datetime.now(timezone.utc)


def today(at: Optional[datetime] = None) -> date:
    return (at or now()).astimezone(BOGOTA).date()


def fold(v: Any) -> str:
    raw = unicodedata.normalize("NFD", str(v or "")).encode("ascii", "ignore").decode("ascii").lower()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", raw).split())


def words(title: str) -> set[str]:
    return {w for w in fold(title).split() if len(w) > 2 and w not in STOP}


def fingerprint(title: str) -> str:
    return hashlib.sha256(" ".join(sorted(words(title))).encode()).hexdigest()


def similar(a: str, b: str, threshold: float = 0.55) -> bool:
    wa, wb = words(a), words(b)
    if not wa or not wb:
        return False
    return len(wa & wb) / len(wa | wb) >= threshold


def score(impacto: str, esfuerzo: str, costo: str, fecha_limite: Optional[date] = None, at: Optional[date] = None) -> int:
    """0-100: el impacto pesa mas; menos esfuerzo y menos costo suben. Una convocatoria que cierra pronto suma un poco."""
    imp = {"alto": 3, "medio": 2, "bajo": 1}.get(impacto, 2)
    ef = {"bajo": 3, "medio": 2, "alto": 1}.get(esfuerzo, 2)
    co = {"bajo": 3, "medio": 2, "alto": 1}.get(costo, 2)
    raw = imp * 5 + ef * 3 + co * 2            # 10..30
    pts = round(100 * (raw - 10) / 20)
    if fecha_limite and at and 0 <= (fecha_limite - at).days <= 21:
        pts = min(100, pts + 5)
    return int(pts)


def norm_url(u: str) -> str:
    u = (u or "").strip().split("#")[0].rstrip("/")
    return re.sub(r"^https?://(www\.)?", "", u.lower())


def esc(v: Any) -> str:
    return str(v or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ---------------------------------------------------------------- base
async def _rows(db: AsyncSession, sql: str, params: Optional[dict] = None) -> list[dict]:
    return [dict(r) for r in (await db.execute(text(sql), params or {})).mappings().all()]


async def _one(db: AsyncSession, sql: str, params: Optional[dict] = None) -> Optional[dict]:
    r = (await db.execute(text(sql), params or {})).mappings().first()
    return dict(r) if r else None


def _iso(v: Any) -> Any:
    return v.isoformat() if isinstance(v, (datetime, date)) else v


def public_idea(r: dict) -> dict:
    out = {k: _iso(v) for k, v in r.items() if k not in ("huella",)}
    out["estado_label"] = STATE_LABEL.get(r.get("estado"), r.get("estado"))
    out["categoria_label"] = CATEGORY_LABEL.get(r.get("categoria"), r.get("categoria") or "")
    out["fuentes"] = [f for f in (r.get("fuentes") or []) if isinstance(f, dict) and str(f.get("url", "")).startswith(("https://", "http://"))]
    return out


IDEA_COLS = """id, informe_id, titulo, resumen, por_que, categoria, nicho, fuentes, impacto, esfuerzo, costo, costo_estimado, puntaje,
    fecha_limite, estado, notas, huella, tg_message_id, created_at, updated_at"""


# ---------------------------------------------------------------- temas
async def temas(db: AsyncSession, active_only: bool = False) -> list[dict]:
    rows = await _rows(db, "SELECT id, clave, nombre, descripcion, activo, orden, updated_at FROM radar_temas"
                       + (" WHERE activo" if active_only else "") + " ORDER BY orden, id")
    return [{k: _iso(v) for k, v in r.items()} for r in rows]


async def save_tema(db: AsyncSession, data: dict, tema_id: Optional[int] = None) -> dict:
    nombre = " ".join(str(data.get("nombre") or "").split())[:120]
    desc = " ".join(str(data.get("descripcion") or "").split())[:600]
    if len(nombre) < 3:
        raise ValueError("nombre_corto")
    if tema_id is None:
        clave = ("-".join(fold(nombre).split())[:30] or "tema") + "-" + hashlib.sha1(nombre.encode()).hexdigest()[:6]
        row = await _one(db, """INSERT INTO radar_temas (clave, nombre, descripcion, activo, orden)
                                VALUES (:c, :n, :d, :a, COALESCE((SELECT MAX(orden) + 1 FROM radar_temas), 0))
                                ON CONFLICT (clave) DO NOTHING RETURNING id""",
                         {"c": clave, "n": nombre, "d": desc, "a": bool(data.get("activo", True))})
        if not row:
            raise ValueError("tema_repetido")
        tema_id = row["id"]
    else:
        row = await _one(db, """UPDATE radar_temas SET nombre = :n, descripcion = :d, activo = :a, updated_at = now()
                                WHERE id = :i RETURNING id""", {"i": tema_id, "n": nombre, "d": desc, "a": bool(data.get("activo", True))})
        if not row:
            raise LookupError("no_existe")
    await db.commit()
    return next(t for t in await temas(db) if t["id"] == tema_id)


# ---------------------------------------------------------------- informes
async def _expire_stale(db: AsyncSession) -> None:
    await db.execute(text("""UPDATE radar_informes SET estado = 'fallido', error = 'sin respuesta de n8n', terminado_at = now()
                             WHERE estado = 'corriendo' AND created_at < now() - make_interval(mins => :m)"""), {"m": STALE_MIN})


async def on_demand_today(db: AsyncSession, at: Optional[datetime] = None) -> int:
    row = await _one(db, "SELECT COUNT(*)::int AS n FROM radar_informes WHERE tipo = 'a_pedido' AND fecha = :d AND estado <> 'rechazado'",
                     {"d": today(at)})
    return row["n"] if row else 0


async def start_report(db: AsyncSession, *, tipo: str, tema: str = "", origen: str = "cron", at: Optional[datetime] = None) -> dict:
    """Abre un informe (estado 'corriendo'). A pedido: maximo 3 por dia (tope de gasto)."""
    await _expire_stale(db)
    tipo = "a_pedido" if tipo == "a_pedido" else "semanal"
    if tipo == "a_pedido":
        used = await on_demand_today(db, at)
        if used >= DAILY_ON_DEMAND:
            await db.commit()
            return {"ok": False, "motivo": "tope_diario", "usados": used,
                    "mensaje": f"⛔ Ya van {used} informes a pedido hoy (máximo {DAILY_ON_DEMAND}). El próximo, mañana."}
    running = await _one(db, "SELECT id FROM radar_informes WHERE estado = 'corriendo' LIMIT 1")
    if running:
        await db.commit()
        return {"ok": False, "motivo": "ya_corriendo", "mensaje": "⏳ NEXUS ya está investigando un informe; espera a que termine."}
    row = await _one(db, """INSERT INTO radar_informes (fecha, tipo, origen, tema) VALUES (:d, :t, :o, :tema) RETURNING id""",
                     {"d": today(at), "t": tipo, "o": (origen or "cron")[:12], "tema": " ".join(str(tema or "").split())[:300]})
    await db.commit()
    return {"ok": True, "informe_id": row["id"], "tipo": tipo, "n": IDEAS_WEEKLY if tipo == "semanal" else IDEAS_ON_DEMAND}


async def fail_report(db: AsyncSession, informe_id: int, error: str) -> dict:
    await db.execute(text("""UPDATE radar_informes SET estado = 'fallido', error = :e, terminado_at = now()
                             WHERE id = :i AND estado = 'corriendo'"""), {"i": informe_id, "e": (error or "error")[:300]})
    await db.commit()
    return {"ok": True}


async def recent_titles(db: AsyncSession, days: int = DEDUP_DAYS) -> list[dict]:
    return await _rows(db, """SELECT titulo, huella, fuentes FROM radar_ideas WHERE created_at >= now() - make_interval(days => :d)
                              ORDER BY created_at DESC LIMIT 400""", {"d": days})


def is_repeated(idea: dict, recent: list[dict]) -> bool:
    fp = fingerprint(idea["titulo"])
    first = norm_url(((idea.get("fuentes") or [{}])[0] or {}).get("url", ""))
    for r in recent:
        if r["huella"] == fp or similar(idea["titulo"], r["titulo"]):
            return True
        rf = norm_url(((r.get("fuentes") or [{}])[0] or {}).get("url", "")) if r.get("fuentes") else ""
        if first and rf and first == rf:
            return True
    return False


async def save_report(db: AsyncSession, informe_id: int, ideas: list[dict], *, discarded: int, usage: dict,
                      at: Optional[datetime] = None) -> dict:
    """Guarda las ideas ya validadas (con fuente). Descarta las repetidas de los ultimos 90 dias. Ordena por puntaje."""
    inf = await _one(db, "SELECT id, tipo, tema, estado FROM radar_informes WHERE id = :i", {"i": informe_id})
    if not inf:
        raise LookupError("no_existe")
    if inf["estado"] != "corriendo":
        raise ValueError("informe_cerrado")
    recent = await recent_titles(db)
    limit = IDEAS_WEEKLY if inf["tipo"] == "semanal" else IDEAS_ON_DEMAND
    d0 = today(at)
    kept, repeated = [], 0
    for idea in ideas:
        if is_repeated(idea, recent + [{"titulo": k["titulo"], "huella": fingerprint(k["titulo"]), "fuentes": k["fuentes"]} for k in kept]):
            repeated += 1
            continue
        idea["puntaje"] = score(idea["impacto"], idea["esfuerzo"], idea["costo"], idea.get("fecha_limite"), d0)
        kept.append(idea)
    kept.sort(key=lambda i: -i["puntaje"])
    kept = kept[:limit]
    ids = []
    for i in kept:
        row = await _one(db, f"""INSERT INTO radar_ideas (informe_id, titulo, resumen, por_que, categoria, nicho, fuentes, impacto, esfuerzo,
                                costo, costo_estimado, puntaje, fecha_limite, huella)
                                VALUES (:inf, :t, :r, :p, :c, :n, CAST(:f AS jsonb), :im, :ef, :co, :ce, :pt, :fl, :h) RETURNING id""",
                         {"inf": informe_id, "t": i["titulo"][:160], "r": i.get("resumen", "")[:600], "p": i.get("por_que", "")[:600],
                          "c": i.get("categoria", "otra")[:40], "n": i.get("nicho", "")[:30], "f": json.dumps(i["fuentes"], ensure_ascii=False),
                          "im": i["impacto"], "ef": i["esfuerzo"], "co": i["costo"], "ce": i.get("costo_estimado", "")[:120],
                          "pt": i["puntaje"], "fl": i.get("fecha_limite"), "h": fingerprint(i["titulo"])})
        ids.append(row["id"])
    await db.execute(text("""UPDATE radar_informes SET estado = 'listo', n_ideas = :n, descartadas = :d, tokens_in = :ti, tokens_out = :to,
                             busquedas = :b, costo_usd = :c, modelo = :m, terminado_at = now() WHERE id = :i"""),
                     {"i": informe_id, "n": len(ids), "d": discarded + repeated, "ti": int(usage.get("input_tokens", 0)),
                      "to": int(usage.get("output_tokens", 0)), "b": int(usage.get("busquedas", 0)), "c": float(usage.get("costo_usd", 0)),
                      "m": str(usage.get("modelo", ""))[:40]})
    await db.commit()
    return {"ids": ids, "repetidas": repeated, "descartadas": discarded}


async def informes(db: AsyncSession, limit: int = 30) -> list[dict]:
    await _expire_stale(db)
    await db.commit()
    rows = await _rows(db, """SELECT id, fecha, tipo, origen, tema, estado, n_ideas, descartadas, tokens_in, tokens_out, busquedas,
                              costo_usd::float AS costo_usd, modelo, error, created_at, terminado_at
                              FROM radar_informes ORDER BY id DESC LIMIT :l""", {"l": max(1, min(200, limit))})
    return [{k: _iso(v) for k, v in r.items()} for r in rows]


# ---------------------------------------------------------------- ideas
async def ideas(db: AsyncSession, *, estado: str = "", categoria: str = "", estados: Optional[list[str]] = None, limit: int = 200) -> list[dict]:
    where, p = ["TRUE"], {"l": max(1, min(500, limit))}
    if estado in STATES:
        where.append("estado = :e")
        p["e"] = estado
    if estados:
        where.append("estado = ANY(CAST(:es AS text[]))")
        p["es"] = [e for e in estados if e in STATES]
    if categoria in CATEGORIES:
        where.append("categoria = :c")
        p["c"] = categoria
    rows = await _rows(db, f"SELECT {IDEA_COLS} FROM radar_ideas WHERE {' AND '.join(where)} ORDER BY puntaje DESC, id DESC LIMIT :l", p)
    return [public_idea(r) for r in rows]


async def idea(db: AsyncSession, idea_id: int) -> Optional[dict]:
    r = await _one(db, f"SELECT {IDEA_COLS} FROM radar_ideas WHERE id = :i", {"i": idea_id})
    return public_idea(r) if r else None


async def update_idea(db: AsyncSession, idea_id: int, *, estado: Optional[str] = None, notas: Optional[str] = None) -> dict:
    if estado is not None and estado not in STATES:
        raise ValueError("estado_invalido")
    sets, p = ["updated_at = now()"], {"i": idea_id}
    if estado is not None:
        sets.append("estado = :e")
        p["e"] = estado
    if notas is not None:
        sets.append("notas = :n")
        p["n"] = str(notas)[:2000]
    row = await _one(db, f"UPDATE radar_ideas SET {', '.join(sets)} WHERE id = :i RETURNING id", p)
    if not row:
        raise LookupError("no_existe")
    await db.commit()
    return await idea(db, idea_id)


async def set_message_id(db: AsyncSession, idea_id: int, message_id: int) -> None:
    await db.execute(text("UPDATE radar_ideas SET tg_message_id = :m WHERE id = :i"), {"i": idea_id, "m": int(message_id)})
    await db.commit()


async def counts(db: AsyncSession) -> dict:
    rows = await _rows(db, "SELECT estado, COUNT(*)::int AS n FROM radar_ideas GROUP BY estado")
    out = {s: 0 for s in STATES}
    out.update({r["estado"]: r["n"] for r in rows})
    return out


async def log_ignored(db: AsyncSession, chat_hash: str, tipo: str = "") -> None:
    if re.fullmatch(r"[0-9a-f]{64}", chat_hash or ""):
        await db.execute(text("INSERT INTO radar_ignorados (chat_hash, tipo) VALUES (:h, :t)"), {"h": chat_hash, "t": (tipo or "")[:20]})
        await db.commit()


# ---------------------------------------------------------------- textos de Telegram (NEXUS)
LEVEL_TXT = {"alto": "alto", "medio": "medio", "bajo": "bajo"}


def idea_message(i: dict) -> str:
    src = (i.get("fuentes") or [{}])[0]
    lim = f"\n⏳ Cierra: {i['fecha_limite']}" if i.get("fecha_limite") else ""
    return (f"💡 <b>{esc(i['titulo'])}</b> · {i['puntaje']} pts\n{esc(i.get('resumen'))}\n\n"
            f"<b>Por qué nos sirve:</b> {esc(i.get('por_que'))}\n"
            f"Impacto {LEVEL_TXT.get(i['impacto'], i['impacto'])} · Esfuerzo {LEVEL_TXT.get(i['esfuerzo'], i['esfuerzo'])} · "
            f"Costo {LEVEL_TXT.get(i['costo'], i['costo'])}{(' (' + esc(i['costo_estimado']) + ')') if i.get('costo_estimado') else ''}{lim}\n"
            f"📎 <a href=\"{esc(src.get('url'))}\">{esc(src.get('titulo') or src.get('url'))}</a> ({esc(src.get('fecha'))})\n"
            f"Estado: {STATE_LABEL.get(i.get('estado'), i.get('estado'))} · #I{i['id']}")[:4000]


def idea_buttons(i: dict) -> dict:
    return {"interesa": f"rx:me_interesa:{i['id']}", "backlog": f"rx:backlog:{i['id']}", "descartar": f"rx:descartada:{i['id']}"}


def telegram_item(i: dict) -> dict:
    return {"id": i["id"], "mensaje": idea_message(i), "botones": idea_buttons(i), "message_id": i.get("tg_message_id")}


def list_message(items: list[dict], title: str) -> str:
    if not items:
        return f"<b>{esc(title)}</b>\nSin ideas aún."
    lines = [f"<b>{esc(title)}</b> · {len(items)}"]
    for i in items[:25]:
        lines.append(f"• {esc(i['titulo'])} · {i['puntaje']} pts · {STATE_LABEL.get(i['estado'], i['estado'])} · #I{i['id']}")
    return "\n".join(lines)[:4000]


HELP = ("🛰️ <b>NEXUS · Radar de innovación de Clonexa</b>\n"
        "/radar &lt;tema&gt; · informe a pedido sobre ese tema (máximo 3 al día)\n"
        "/ideas · ideas nuevas y las que te interesan\n"
        "/backlog · ideas en backlog y en curso\n"
        "/ayuda · esta lista\n"
        "Cada lunes 8:00 a. m. llega el Radar de la semana (5 ideas).")


# ---------------------------------------------------------------- oficina 3D (copia viva)
def next_monday_8(at: Optional[datetime] = None) -> datetime:
    b = (at or now()).astimezone(BOGOTA)
    days = (7 - b.weekday()) % 7
    cand = (b + timedelta(days=days)).replace(hour=8, minute=0, second=0, microsecond=0)
    if cand <= b:
        cand += timedelta(days=7)
    return cand


async def office_snapshot(db: AsyncSession, at: Optional[datetime] = None) -> dict:
    """Estado REAL para el area Innovacion de la oficina: NEXUS investigando/esperando/error, top 3 del ultimo informe,
    conteos por estado y el proximo informe. Sin datos de ejemplo."""
    await _expire_stale(db)
    await db.commit()
    last = await _one(db, "SELECT id, estado, n_ideas, created_at FROM radar_informes ORDER BY id DESC LIMIT 1")
    running = await _one(db, "SELECT id FROM radar_informes WHERE estado = 'corriendo' LIMIT 1")
    done = await _one(db, "SELECT id FROM radar_informes WHERE estado = 'listo' ORDER BY id DESC LIMIT 1")
    top = []
    if done:
        top = [{"titulo": r["titulo"], "impacto": r["impacto"], "esfuerzo": r["esfuerzo"], "estado": r["estado"],
                "estado_label": STATE_LABEL.get(r["estado"], r["estado"]), "puntaje": r["puntaje"],
                "fecha_limite": _iso(r["fecha_limite"])}
               for r in await _rows(db, """SELECT titulo, impacto, esfuerzo, estado, puntaje, fecha_limite FROM radar_ideas
                                           WHERE informe_id = :i ORDER BY puntaje DESC LIMIT 3""", {"i": done["id"]})]
    c = await counts(db)
    state = "work" if running else "err" if last and last["estado"] == "fallido" else "wait" if last else "nodata"
    nm = next_monday_8(at)
    return {"state": state, "top": top, "counts": c, "nuevas": c.get("nueva", 0),
            "next_at": nm.isoformat(), "next_label": f"lunes {nm.day:02d}/{nm.month:02d} 8:00",
            "last_failed": bool(last and last["estado"] == "fallido")}
