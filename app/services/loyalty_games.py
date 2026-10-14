"""Juegos en vivo de Fidelizacion (interruptor loyalty_games del modulo loyalty).

Generico para cualquier empresa, todo por company_id. No toca Fidelizacion de
siempre (sorteos, pollas, votaciones), Hospitality, pedidos ni musica.
- Dia de juego = la jornada de la empresa (business_day: 18:00-04:00 es una noche).
- Ruleta: numero elegido con secrets ANTES de la animacion y guardado; no repite
  en la noche por rango (indice unico).
- Memoria y trivia: registro (QR de la ronda) -> en juego (todos a la vez) ->
  cerrado (a los 2 / 3 min, calculado desde la base; tambien el barman cierra).
- Validar ganador: HMAC del documento digitado contra el del puesto; nunca se
  muestra ni se guarda el numero. Purga del HMAC y los 4 digitos a los 30 dias.
"""
from __future__ import annotations

import json
import logging
import secrets
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import loyalty_games_engine as eng
from app.services.loyalty_games_engine import GameError

log = logging.getLogger("clonexa.loyalty_games")
MODULE = "loyalty"
FLAG = "loyalty_games"
PURGE_DAYS = 30
PURGE_LOCK_ID = 540541
SEED_FILE = Path(__file__).with_name("loyalty_games_seed.json")
ADMIN_ROLES = {"company_admin", "admin_empresa", "dueno", "dueño", "owner", "propietario", "admin"}
BARMAN_ROLES = {"barman", "bartender", "cantinero"}
DEFAULTS = {
    "memory_seconds": 120,
    "trivia_seconds": 180,
    "roulette_ranges": [{"min": 1, "max": 50, "prize": ""}, {"min": 1, "max": 100, "prize": ""}],
    "prizes": {"memory": "", "trivia": "", "roulette": ""},
    "texts": {"claim": "Reclama con tu documento", "consent": "Autorizo el tratamiento de mis datos para este concurso"},
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _json(value: Any, default: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return default
    return default if value is None else value


# ---------------------------------------------------------------- interruptor y zona
async def is_on(db: AsyncSession, company_id: Any) -> bool:
    row = (await db.execute(text("""
        SELECT cm.enabled, cm.settings FROM company_modules cm JOIN modules m ON m.id = cm.module_id
        WHERE cm.company_id::text = :c AND lower(m.code) = :m LIMIT 1
    """), {"c": str(company_id), "m": MODULE})).mappings().first()
    return bool(row and row["enabled"] and _json(row["settings"], {}).get(FLAG) is True)


async def company_clock(db: AsyncSession, company_id: Any) -> tuple[ZoneInfo, Optional[dict], str]:
    from app.services import business_day, company_locale

    loc = await company_locale.get_company_locale(db, company_id)
    row = (await db.execute(text("SELECT settings_json FROM companies WHERE id::text = :c"), {"c": str(company_id)})).mappings().first()
    cfg = business_day.config(row["settings_json"] if row else None)
    return company_locale.zone(loc["timezone"]), cfg, loc.get("language") or "es"


async def game_day(db: AsyncSession, company_id: Any, now: Optional[datetime] = None) -> date:
    from app.services import business_day

    tz, cfg, _ = await company_clock(db, company_id)
    return business_day.business_date(now or _now(), tz, cfg)


# ---------------------------------------------------------------- ajustes
async def settings(db: AsyncSession, company_id: Any) -> dict:
    row = (await db.execute(text("SELECT settings FROM loyalty_game_settings WHERE company_id::text = :c"), {"c": str(company_id)})).mappings().first()
    saved = _json(row["settings"], {}) if row else {}
    out = json.loads(json.dumps(DEFAULTS))
    for k, v in (saved or {}).items():
        if k in ("prizes", "texts") and isinstance(v, dict):
            out[k].update({kk: str(vv)[:160] for kk, vv in v.items() if kk in out[k]})
        elif k in out:
            out[k] = v
    return out


def validate_settings(raw: dict) -> dict:
    if not isinstance(raw, dict):
        raise GameError("datos_invalidos", 422)
    out = {}
    for key, low, high in (("memory_seconds", 30, 600), ("trivia_seconds", 60, 900)):
        try:
            value = int(raw.get(key, DEFAULTS[key]))
        except (TypeError, ValueError):
            raise GameError(f"{key}_invalido", 422) from None
        if not low <= value <= high:
            raise GameError(f"{key}_fuera_de_rango", 422)
        out[key] = value
    ranges = []
    for r in raw.get("roulette_ranges") or []:
        try:
            lo, hi = int(r.get("min")), int(r.get("max"))
        except (TypeError, ValueError):
            raise GameError("rango_invalido", 422) from None
        if not (0 <= lo < hi <= 9999):
            raise GameError("rango_invalido", 422)
        ranges.append({"min": lo, "max": hi, "prize": str(r.get("prize") or "")[:160]})
    if not ranges or len(ranges) > 8:
        raise GameError("rangos_requeridos", 422)
    out["roulette_ranges"] = ranges
    out["prizes"] = {k: str((raw.get("prizes") or {}).get(k) or "")[:160] for k in DEFAULTS["prizes"]}
    out["texts"] = {k: (str((raw.get("texts") or {}).get(k) or "").strip()[:160] or DEFAULTS["texts"][k]) for k in DEFAULTS["texts"]}
    return out


async def save_settings(db: AsyncSession, company_id: Any, raw: dict, actor: str) -> dict:
    data = validate_settings(raw)
    await db.execute(text("""
        INSERT INTO loyalty_game_settings (company_id, settings, updated_by, updated_at) VALUES (CAST(:c AS uuid), CAST(:s AS jsonb), :by, now())
        ON CONFLICT (company_id) DO UPDATE SET settings = EXCLUDED.settings, updated_by = EXCLUDED.updated_by, updated_at = now()
    """), {"c": str(company_id), "s": json.dumps(data, ensure_ascii=False), "by": actor[:200]})
    await db.commit()
    return await settings(db, company_id)


async def screen_token(db: AsyncSession, company_id: Any, regenerate: bool = False) -> str:
    row = (await db.execute(text("SELECT screen_token FROM loyalty_game_settings WHERE company_id::text = :c"), {"c": str(company_id)})).mappings().first()
    token = row["screen_token"] if row else None
    if regenerate or not token:
        token = secrets.token_urlsafe(24)
        await db.execute(text("""
            INSERT INTO loyalty_game_settings (company_id, screen_token, updated_at) VALUES (CAST(:c AS uuid), :t, now())
            ON CONFLICT (company_id) DO UPDATE SET screen_token = EXCLUDED.screen_token, updated_at = now()
        """), {"c": str(company_id), "t": token})
        await db.commit()
    return str(token)


async def company_by_screen_token(db: AsyncSession, token: str) -> Optional[str]:
    clean = str(token or "").strip()[:64]
    if len(clean) < 20:
        return None
    cid = (await db.execute(text("SELECT company_id::text FROM loyalty_game_settings WHERE screen_token = :t"), {"t": clean})).scalar()
    return cid if cid and await is_on(db, cid) else None


# ---------------------------------------------------------------- banco de preguntas
def seed_questions() -> list[dict]:
    return json.loads(SEED_FILE.read_text(encoding="utf-8"))["questions"]


async def ensure_bank(db: AsyncSession, company_id: Any) -> int:
    """La primera vez: copia el banco inicial como DATOS de la empresa (luego se edita)."""
    if (await db.execute(text("SELECT 1 FROM loyalty_trivia_questions WHERE company_id::text = :c LIMIT 1"), {"c": str(company_id)})).first():
        return 0
    rows = seed_questions()
    for q in rows:
        await db.execute(text("""
            INSERT INTO loyalty_trivia_questions (company_id, level, question, correct_answer, wrong_1, wrong_2)
            VALUES (CAST(:c AS uuid), :l, :q, :a, :b, :d)
        """), {"c": str(company_id), "l": q["level"], "q": q["question"], "a": q["correct"], "b": q["wrong"][0], "d": q["wrong"][1]})
    await db.commit()
    return len(rows)


async def questions(db: AsyncSession, company_id: Any) -> list[dict]:
    rows = (await db.execute(text("""
        SELECT id::text AS id, level, question, correct_answer, wrong_1, wrong_2, active FROM loyalty_trivia_questions
        WHERE company_id::text = :c ORDER BY level, created_at, id
    """), {"c": str(company_id)})).mappings().all()
    return [dict(r) for r in rows]


def validate_question(raw: dict) -> dict:
    try:
        level = int(raw.get("level"))
    except (TypeError, ValueError):
        raise GameError("nivel_invalido", 422) from None
    if level not in eng.LEVELS:
        raise GameError("nivel_invalido", 422)
    out = {"level": level}
    for key, limit in (("question", 240), ("correct_answer", 120), ("wrong_1", 120), ("wrong_2", 120)):
        value = " ".join(str(raw.get(key) or "").split())
        if not value or len(value) > limit:
            raise GameError(f"{key}_invalido", 422)
        out[key] = value
    if len({out["correct_answer"].lower(), out["wrong_1"].lower(), out["wrong_2"].lower()}) < 3:
        raise GameError("opciones_repetidas", 422)
    out["active"] = raw.get("active") is not False
    return out


async def save_question(db: AsyncSession, company_id: Any, raw: dict, question_id: Optional[str] = None) -> dict:
    q = validate_question(raw)
    params = {**q, "c": str(company_id)}
    if question_id:
        res = await db.execute(text("""
            UPDATE loyalty_trivia_questions SET level = :level, question = :question, correct_answer = :correct_answer, wrong_1 = :wrong_1,
                   wrong_2 = :wrong_2, active = :active, updated_at = now()
            WHERE company_id::text = :c AND id::text = :i RETURNING id::text
        """), {**params, "i": str(question_id)})
        new_id = res.scalar()
        if not new_id:
            raise GameError("pregunta_no_encontrada", 404)
    else:
        new_id = (await db.execute(text("""
            INSERT INTO loyalty_trivia_questions (company_id, level, question, correct_answer, wrong_1, wrong_2, active)
            VALUES (CAST(:c AS uuid), :level, :question, :correct_answer, :wrong_1, :wrong_2, :active) RETURNING id::text
        """), params)).scalar()
    await db.commit()
    return next(x for x in await questions(db, company_id) if x["id"] == new_id)


# ---------------------------------------------------------------- ruleta
async def spin(db: AsyncSession, company_id: Any, range_min: int, range_max: int, prize: str, actor: str, now: Optional[datetime] = None) -> dict:
    now = now or _now()
    day = await game_day(db, company_id, now)
    # Un giro a la vez por empresa, rango y noche (el indice unico respalda el "no repite").
    await db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": f"roulette:{company_id}:{day}:{range_min}:{range_max}"})
    drawn = set((await db.execute(text("""
        SELECT number FROM loyalty_roulette_draws WHERE company_id::text = :c AND game_day = :d AND range_min = :a AND range_max = :b
    """), {"c": str(company_id), "d": day, "a": range_min, "b": range_max})).scalars().all())
    number = eng.pick_number(range_min, range_max, drawn)
    draw_id = (await db.execute(text("""
        INSERT INTO loyalty_roulette_draws (company_id, game_day, range_min, range_max, number, prize, spun_by, spun_at)
        VALUES (CAST(:c AS uuid), :d, :a, :b, :n, :p, :by, :at) RETURNING id::text
    """), {"c": str(company_id), "d": day, "a": range_min, "b": range_max, "n": number, "p": str(prize or "")[:160], "by": actor[:200], "at": now})).scalar()
    await db.commit()
    return {"id": draw_id, "number": number, "prize": prize or "", "range_min": range_min, "range_max": range_max, "game_day": day.isoformat(),
            "drawn": sorted(drawn | {number}), "left": (range_max - range_min + 1) - len(drawn) - 1, "spun_at": now.isoformat()}


async def draws(db: AsyncSession, company_id: Any, day: Optional[date] = None, limit: int = 200) -> list[dict]:
    sql = """SELECT id::text AS id, game_day, range_min, range_max, number, prize, spun_by, spun_at FROM loyalty_roulette_draws
             WHERE company_id::text = :c {day} ORDER BY spun_at DESC LIMIT :l"""
    params: dict = {"c": str(company_id), "l": limit}
    if day:
        params["d"] = day
    rows = (await db.execute(text(sql.format(day="AND game_day = :d" if day else "")), params)).mappings().all()
    return [{**dict(r), "game_day": r["game_day"].isoformat(), "spun_at": r["spun_at"].isoformat()} for r in rows]


# ---------------------------------------------------------------- rondas
async def round_row(db: AsyncSession, company_id: Any, round_id: Any, lock: bool = False) -> Optional[dict]:
    try:
        uuid.UUID(str(round_id))
    except ValueError:
        return None
    row = (await db.execute(text(f"""
        SELECT * FROM loyalty_game_rounds WHERE company_id::text = :c AND id::text = :i {'FOR UPDATE' if lock else ''}
    """), {"c": str(company_id), "i": str(round_id)})).mappings().first()
    return dict(row) if row else None


async def open_round(db: AsyncSession, company_id: Any, kind: str, prize: str, actor: str, now: Optional[datetime] = None) -> dict:
    if kind not in ("memory", "trivia"):
        raise GameError("tipo_invalido", 422)
    now = now or _now()
    live = (await db.execute(text("""
        SELECT 1 FROM loyalty_game_rounds WHERE company_id::text = :c AND status IN ('registration', 'playing') AND (ends_at IS NULL OR ends_at > :n) LIMIT 1
    """), {"c": str(company_id), "n": now})).first()
    if live:
        raise GameError("ya_hay_una_ronda_activa")
    conf = await settings(db, company_id)
    seed = eng.new_seed()
    qids: list[str] = []
    if kind == "trivia":
        await ensure_bank(db, company_id)
        qids = eng.pick_questions(await questions(db, company_id), seed)
    rid = (await db.execute(text("""
        INSERT INTO loyalty_game_rounds (company_id, kind, status, prize, seed, game_day, duration_seconds, question_ids, created_by, created_at, updated_at)
        VALUES (CAST(:c AS uuid), :k, 'registration', :p, :s, :d, :dur, CAST(:q AS jsonb), :by, :n, :n) RETURNING id::text
    """), {"c": str(company_id), "k": kind, "p": str(prize or conf["prizes"].get(kind) or "")[:160], "s": seed, "d": await game_day(db, company_id, now),
           "dur": conf["memory_seconds"] if kind == "memory" else conf["trivia_seconds"], "q": json.dumps(qids), "by": actor[:200], "n": now})).scalar()
    await db.commit()
    return await round_row(db, company_id, rid)


async def start_round(db: AsyncSession, company_id: Any, round_id: Any, now: Optional[datetime] = None) -> dict:
    now = now or _now()
    r = await round_row(db, company_id, round_id, lock=True)
    if not r:
        raise GameError("ronda_no_encontrada", 404)
    if r["status"] != "registration":
        raise GameError("la_ronda_no_esta_en_registro")
    ends = now + timedelta(seconds=int(r["duration_seconds"]))
    await db.execute(text("""
        UPDATE loyalty_game_rounds SET status = 'playing', started_at = :n, ends_at = :e, updated_at = :n WHERE company_id::text = :c AND id::text = :i
    """), {"n": now, "e": ends, "c": str(company_id), "i": str(round_id)})
    start = eng.memory_start() if r["kind"] == "memory" else eng.trivia_start(_json(r["question_ids"], []))
    await db.execute(text("""
        UPDATE loyalty_game_players SET progress = CAST(:p AS jsonb), updated_at = :n WHERE company_id::text = :c AND round_id::text = :i
    """), {"p": json.dumps(start), "n": now, "c": str(company_id), "i": str(round_id)})
    await db.commit()
    return await round_row(db, company_id, round_id)


async def players(db: AsyncSession, company_id: Any, round_id: Any) -> list[dict]:
    rows = (await db.execute(text("""
        SELECT id::text AS id, display_name, document_last4, hidden, progress, score, score_ms, finished_at, result, place, validated_at, joined_at
        FROM loyalty_game_players WHERE company_id::text = :c AND round_id::text = :i ORDER BY joined_at, id
    """), {"c": str(company_id), "i": str(round_id)})).mappings().all()
    return [{**dict(r), "progress": _json(r["progress"], {})} for r in rows]


async def close_round(db: AsyncSession, company_id: Any, round_id: Any, now: Optional[datetime] = None, reason: str = "manual") -> dict:
    now = now or _now()
    r = await round_row(db, company_id, round_id, lock=True)
    if not r:
        raise GameError("ronda_no_encontrada", 404)
    if r["status"] in ("closed", "cancelled"):
        return r
    if r["status"] == "registration":
        await db.execute(text("""UPDATE loyalty_game_rounds SET status = 'cancelled', closed_at = :n, updated_at = :n
            WHERE company_id::text = :c AND id::text = :i"""), {"n": now, "c": str(company_id), "i": str(round_id)})
        await db.commit()
        return await round_row(db, company_id, round_id)
    closed_at = min(now, r["ends_at"]) if r["ends_at"] and reason == "time" else now
    plist = await players(db, company_id, round_id)
    places = eng.final_places(r["kind"], plist)
    for p in places:
        await db.execute(text("""UPDATE loyalty_game_players SET result = :r, place = :pl, updated_at = :n
            WHERE company_id::text = :c AND id::text = :i"""), {"r": p["result"], "pl": p["place"], "n": now, "c": str(company_id), "i": p["id"]})
    names = {p["id"]: p["display_name"] for p in plist}
    podium = [{"place": p["place"], "id": p["id"], "name": names[p["id"]]} for p in sorted((x for x in places if x["place"]), key=lambda x: x["place"])][:3]
    await db.execute(text("""UPDATE loyalty_game_rounds SET status = 'closed', closed_at = :n, results = CAST(:res AS jsonb), updated_at = :n
        WHERE company_id::text = :c AND id::text = :i"""), {"n": closed_at, "res": json.dumps(podium, ensure_ascii=False), "c": str(company_id), "i": str(round_id)})
    await db.commit()
    return await round_row(db, company_id, round_id)


async def refresh(db: AsyncSession, company_id: Any, r: Optional[dict], now: Optional[datetime] = None) -> Optional[dict]:
    """Cierre por tiempo calculado desde la base (sobrevive reinicios)."""
    now = now or _now()
    if r and r["status"] == "playing" and r["ends_at"] and now >= r["ends_at"]:
        return await close_round(db, company_id, r["id"], now, reason="time")
    return r


async def hide_player(db: AsyncSession, company_id: Any, round_id: Any, player_id: Any) -> None:
    res = await db.execute(text("""UPDATE loyalty_game_players SET hidden = true, updated_at = now()
        WHERE company_id::text = :c AND round_id::text = :r AND id::text = :i RETURNING id"""), {"c": str(company_id), "r": str(round_id), "i": str(player_id)})
    if not res.first():
        raise GameError("jugador_no_encontrado", 404)
    await db.commit()


# ---------------------------------------------------------------- jugadores (pagina publica)
def round_token(round_id: Any) -> str:
    return eng.sign("round", str(round_id))


def player_token(player_id: Any) -> str:
    return eng.sign("player", str(player_id))


async def round_by_token(db: AsyncSession, token: str) -> Optional[dict]:
    rid = eng.unsign("round", token)
    if not rid:
        return None
    try:
        uuid.UUID(rid)
    except ValueError:
        return None
    row = (await db.execute(text("SELECT * FROM loyalty_game_rounds WHERE id::text = :i"), {"i": rid})).mappings().first()
    if not row or not await is_on(db, row["company_id"]):
        return None
    return dict(row)


async def join(db: AsyncSession, r: dict, name: str, document: str, consent: bool, now: Optional[datetime] = None) -> dict:
    now = now or _now()
    if r["status"] != "registration":
        raise GameError("registro_cerrado")
    if consent is not True:
        raise GameError("consentimiento_requerido", 422)
    clean_name = eng.clean_name(name)
    doc = eng.clean_document(document)
    digest = eng.document_hmac(r["company_id"], doc)
    taken = (await db.execute(text("SELECT 1 FROM loyalty_game_players WHERE company_id = :c AND round_id = :r AND document_hmac = :h"),
                              {"c": r["company_id"], "r": r["id"], "h": digest})).first()
    if taken:
        raise GameError("documento_ya_juega")
    pid = (await db.execute(text("""
        INSERT INTO loyalty_game_players (company_id, round_id, display_name, document_hmac, document_last4, consent, consent_at, joined_at, updated_at)
        VALUES (:c, :r, :n, :h, :l4, true, :t, :t, :t) RETURNING id::text
    """), {"c": r["company_id"], "r": r["id"], "n": clean_name, "h": digest, "l4": doc[-4:], "t": now})).scalar()
    await db.commit()
    return {"player_token": player_token(pid), "name": clean_name}


async def player_by_token(db: AsyncSession, r: dict, token: str, lock: bool = False) -> Optional[dict]:
    pid = eng.unsign("player", token)
    if not pid:
        return None
    try:
        uuid.UUID(pid)
    except ValueError:
        return None
    row = (await db.execute(text(f"""SELECT * FROM loyalty_game_players WHERE company_id = :c AND id::text = :i AND round_id = :r {'FOR UPDATE' if lock else ''}"""),
                            {"c": r["company_id"], "i": pid, "r": r["id"]})).mappings().first()
    return {**dict(row), "progress": _json(row["progress"], {})} if row else None


def _elapsed_ms(r: dict, now: datetime) -> int:
    return int((now - r["started_at"]).total_seconds() * 1000) if r.get("started_at") else 0


async def _save_progress(db: AsyncSession, p: dict, progress: dict, now: datetime, **fields: Any) -> None:
    sets = ", ".join(f"{k} = :{k}" for k in fields)
    await db.execute(text(f"""UPDATE loyalty_game_players SET progress = CAST(:pr AS jsonb), updated_at = :n{', ' + sets if sets else ''}
        WHERE id = :i AND company_id = :c"""), {"pr": json.dumps(progress, ensure_ascii=False), "n": now, "i": p["id"], "c": p["company_id"], **fields})


def _playing(r: dict, now: datetime) -> None:
    if r["status"] != "playing" or (r["ends_at"] and now >= r["ends_at"]):
        raise GameError("ronda_no_en_juego")


async def flip(db: AsyncSession, r: dict, token: str, index: int, now: Optional[datetime] = None) -> dict:
    now = now or _now()
    _playing(r, now)
    if r["kind"] != "memory":
        raise GameError("tipo_invalido", 422)
    p = await player_by_token(db, r, token, lock=True)
    if not p:
        raise GameError("jugador_invalido", 403)
    if p["finished_at"]:
        raise GameError("ya_terminaste")
    progress, answer = eng.memory_flip(p["progress"], int(r["seed"]), index, _elapsed_ms(r, now))
    fields: dict = {"score": progress["pairs"], "score_ms": (progress["pair_ms"] or [None])[-1]}
    if progress["pairs"] >= eng.PAIRS:
        fields["finished_at"] = now
    await _save_progress(db, p, progress, now, **fields)
    await db.commit()
    return answer


async def trivia_state(db: AsyncSession, r: dict, token: str, now: Optional[datetime] = None) -> dict:
    """Avanza la trivia del jugador (pregunta vencida -> siguiente) y devuelve la pregunta en curso, sin la respuesta."""
    now = now or _now()
    _playing(r, now)
    p = await player_by_token(db, r, token, lock=True)
    if not p:
        raise GameError("jugador_invalido", 403)
    if p["finished_at"]:
        await db.rollback()
        return {"done": True, "correct": int(p["score"] or 0)}
    progress = eng.trivia_tick(p["progress"], now)
    if progress != p["progress"]:
        await _save_progress(db, p, progress, now)
        await db.commit()
    else:
        await db.rollback()
    return await _question_view(db, r, progress, now)


async def _question_view(db: AsyncSession, r: dict, progress: dict, now: datetime) -> dict:
    cur = progress.get("current")
    if not cur:
        return {"done": eng.trivia_done(progress), "correct": eng.trivia_correct(progress)}
    q = (await db.execute(text("""SELECT question, correct_answer, wrong_1, wrong_2, level FROM loyalty_trivia_questions
        WHERE company_id = :c AND id::text = :i"""), {"c": r["company_id"], "i": cur["qid"]})).mappings().first()
    opts = [q["correct_answer"], q["wrong_1"], q["wrong_2"]] if q else ["", "", ""]
    total = len(_json(r["question_ids"], []))
    return {"done": False, "question": {"id": cur["qid"], "text": q["question"] if q else "", "level": q["level"] if q else None,
                                        "options": [opts[i] for i in cur["order"]], "remaining_ms": eng.remaining_ms(progress, now), "limit_ms": eng.QUESTION_MS},
            "answered": total - len(progress.get("pending") or []), "total": total, "lap": progress.get("lap", 1), "correct": eng.trivia_correct(progress)}


async def answer(db: AsyncSession, r: dict, token: str, qid: str, choice: int, now: Optional[datetime] = None) -> dict:
    now = now or _now()
    _playing(r, now)
    if r["kind"] != "trivia":
        raise GameError("tipo_invalido", 422)
    p = await player_by_token(db, r, token, lock=True)
    if not p:
        raise GameError("jugador_invalido", 403)
    progress, ok = eng.trivia_answer(p["progress"], str(qid), choice, now)
    fields: dict = {"score": eng.trivia_correct(progress)}
    if eng.trivia_done(progress):
        fields["finished_at"] = now
        fields["score_ms"] = _elapsed_ms(r, now)
    await _save_progress(db, p, progress, now, **fields)
    await db.commit()
    return {"ok": ok, "done": eng.trivia_done(progress), "correct": fields["score"]}


async def me(db: AsyncSession, r: dict, token: str, now: Optional[datetime] = None) -> dict:
    now = now or _now()
    p = await player_by_token(db, r, token)
    if not p:
        raise GameError("jugador_invalido", 403)
    out: dict = {"name": p["display_name"], "status": r["status"], "kind": r["kind"], "now": now.isoformat(),
                 "ends_at": r["ends_at"].isoformat() if r["ends_at"] else None, "hidden": p["hidden"]}
    if r["status"] == "closed":
        out["result"] = {"result": p["result"], "place": p["place"], "score": int(p["score"] or 0)}
    if r["kind"] == "memory" and r["status"] in ("playing", "closed") and p["progress"]:
        out["memory"] = eng.memory_public(p["progress"], int(r["seed"]))
    if r["kind"] == "trivia" and p["progress"]:
        out["trivia"] = {"answered": len(p["progress"].get("answers") or {}), "total": len(_json(r["question_ids"], [])),
                         "correct": eng.trivia_correct(p["progress"]), "done": bool(p["finished_at"])}
    return out


# ---------------------------------------------------------------- validar ganador
async def validate_winner(db: AsyncSession, company_id: Any, round_id: Any, place: int, document: str, actor: str) -> dict:
    r = await round_row(db, company_id, round_id)
    if not r:
        raise GameError("ronda_no_encontrada", 404)
    if r["status"] != "closed":
        raise GameError("la_ronda_no_esta_cerrada")
    row = (await db.execute(text("""SELECT id, display_name, document_hmac FROM loyalty_game_players
        WHERE company_id::text = :c AND round_id::text = :r AND place = :p AND result = 'ranked'"""),
                            {"c": str(company_id), "r": str(round_id), "p": int(place)})).mappings().first()
    if not row:
        raise GameError("puesto_sin_ganador", 404)
    if not row["document_hmac"]:
        raise GameError("datos_purgados")
    match = secrets.compare_digest(row["document_hmac"], eng.document_hmac(company_id, document))
    if match:
        await db.execute(text("UPDATE loyalty_game_players SET validated_at = now(), validated_by = :by WHERE company_id::text = :c AND id = :i"),
                         {"by": actor[:200], "c": str(company_id), "i": row["id"]})
        await db.commit()
    return {"match": match, "name": row["display_name"] if match else None, "place": int(place)}


# ---------------------------------------------------------------- purga
async def purge(db: AsyncSession, now: Optional[datetime] = None) -> int:
    """Borra el HMAC del documento y los 4 digitos de quien jugo hace mas de 30 dias (todas las empresas)."""
    now = now or _now()
    res = await db.execute(text("""UPDATE loyalty_game_players SET document_hmac = NULL, document_last4 = NULL
        WHERE document_hmac IS NOT NULL AND joined_at < :t"""), {"t": now - timedelta(days=PURGE_DAYS)})
    await db.commit()
    return int(res.rowcount or 0)


async def purge_loop() -> None:
    import asyncio

    from app.core.database import AsyncSessionLocal

    while True:
        try:
            async with AsyncSessionLocal() as db:
                if (await db.execute(text("SELECT to_regclass('loyalty_game_players')"))).scalar():
                    if (await db.execute(text("SELECT pg_try_advisory_lock(:id)"), {"id": PURGE_LOCK_ID})).scalar():
                        try:
                            n = await purge(db)
                            if n:
                                log.info("Juegos en vivo: %s documentos purgados (30 dias)", n)
                        finally:
                            await db.execute(text("SELECT pg_advisory_unlock(:id)"), {"id": PURGE_LOCK_ID})
                            await db.commit()
        except Exception as exc:  # nunca tumba el servidor
            log.warning("Juegos en vivo: la purga no pudo correr: %s", exc)
        await asyncio.sleep(3600)


def start_purge_loop() -> None:
    import asyncio

    asyncio.get_event_loop().create_task(purge_loop())


# ---------------------------------------------------------------- vistas
ROULETTE_HOLD = timedelta(seconds=20)


def focus_of(view: Optional[dict], round_changed: Optional[datetime], spun_at: Optional[datetime], now: datetime) -> str:
    """Que muestra la pantalla: un giro de los ultimos 20 s manda (anima y muestra el numero);
    si no, la ronda activa; si no hay ronda activa, lo mas reciente de la noche."""
    if spun_at and now - spun_at <= ROULETTE_HOLD:
        return "roulette"
    if view and view["status"] in ("registration", "playing"):
        return "round"
    if spun_at and (not view or not round_changed or spun_at > round_changed):
        return "roulette"
    return "round" if view else "idle"


def round_view(r: Optional[dict], plist: list[dict], now: datetime) -> Optional[dict]:
    if not r:
        return None
    visible = [p for p in plist if not p.get("hidden")]
    return {
        "id": str(r["id"]), "kind": r["kind"], "status": r["status"], "prize": r["prize"], "game_day": r["game_day"].isoformat(),
        "started_at": r["started_at"].isoformat() if r["started_at"] else None, "ends_at": r["ends_at"].isoformat() if r["ends_at"] else None,
        "closed_at": r["closed_at"].isoformat() if r["closed_at"] else None, "duration_seconds": int(r["duration_seconds"]),
        "players": [{"id": p["id"], "name": p["display_name"]} for p in visible], "count": len(visible),
        "ranking": eng.live_ranking(r["kind"], plist) if r["status"] in ("playing", "closed") else [],
        "podium": _json(r["results"], []) if r["status"] == "closed" else [],
        "token": round_token(r["id"]),
    }


async def latest_round(db: AsyncSession, company_id: Any) -> Optional[dict]:
    row = (await db.execute(text("""SELECT * FROM loyalty_game_rounds WHERE company_id::text = :c AND kind <> 'roulette'
        ORDER BY created_at DESC LIMIT 1"""), {"c": str(company_id)})).mappings().first()
    return dict(row) if row else None


async def live_state(db: AsyncSession, company_id: Any, now: Optional[datetime] = None) -> dict:
    """Lo que dibuja la pantalla del bar (y el panel en vivo): pocas consultas."""
    now = now or _now()
    day = await game_day(db, company_id, now)
    r = await refresh(db, company_id, await latest_round(db, company_id), now)
    if r and r["game_day"] != day and r["status"] in ("closed", "cancelled"):
        r = None
    plist = await players(db, company_id, r["id"]) if r else []
    last = (await db.execute(text("""SELECT id::text AS id, range_min, range_max, number, prize, spun_by, spun_at FROM loyalty_roulette_draws
        WHERE company_id::text = :c AND game_day = :d ORDER BY spun_at DESC LIMIT 1"""), {"c": str(company_id), "d": day})).mappings().first()
    roulette = None
    if last:
        drawn = (await db.execute(text("""SELECT number FROM loyalty_roulette_draws WHERE company_id::text = :c AND game_day = :d
            AND range_min = :a AND range_max = :b ORDER BY spun_at"""), {"c": str(company_id), "d": day, "a": last["range_min"], "b": last["range_max"]})).scalars().all()
        roulette = {**dict(last), "spun_at": last["spun_at"].isoformat(), "drawn": list(drawn)}
    view = round_view(r, plist, now)
    focus = focus_of(view, r["updated_at"] if r else None, last["spun_at"] if last else None, now)
    return {"now": now.isoformat(), "game_day": day.isoformat(), "focus": focus, "round": view, "roulette": roulette,
            "active": bool(view and view["status"] in ("registration", "playing"))}
