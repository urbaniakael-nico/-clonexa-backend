"""Retos para las mesas (interruptor loyalty_retos_v2 del modulo loyalty).

Rediseno de "Sorteos de consumo" con logica de inicio a fin y ganador, sobre las
MISMAS tablas de Fidelizacion (hospitality_loyalty_*). Todo por company_id.
- Maximo UN reto activo por tipo (consumo, polla, concurso), validado aqui.
- Consumo: el ranking es el de siempre (hospitality._loyalty_leaderboard: solo
  pedidos creados durante el torneo). Al cerrar gana el 1.er puesto con consumo.
- Polla: pronosticos hasta predictions_close_at; "Poner marcador final" calcula
  los aciertos EXACTOS: 0 = sin ganador, 1 = gana, 2+ = empate (desempate con
  Juego en vivo si loyalty_games esta activo; si no, el bar elige).
- Concurso: votacion = mas votos (empate: el bar elige entre las empatadas);
  Si/No y V/F = sorteo seguro (secrets) entre los que acertaron la respuesta
  secreta, que nunca sale al QR; inscripcion simple = el bar elige.
- Premio de cada ganador: pendiente -> entregado (hora y quien).
Los retos de antes (rules_version 1) siguen igual; solo cambian si el bar los
resuelve desde la pantalla nueva.
"""
from __future__ import annotations

import json
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

MODULE = "loyalty"
FLAG = "loyalty_retos_v2"
RULES = 2
TYPES = ("consumption", "score_pool", "vote_poll")
VOTE_MODES = ("registration", "yes_no", "true_false", "participants")
SECRET_KEYS = {"yes_no": ("yes", "no"), "true_false": ("true", "false")}
RECENT_RESULT = timedelta(hours=6)  # el QR muestra el resultado de un reto cerrado durante 6 h
MAX_AHEAD = timedelta(days=45)
POOL_KEEP = timedelta(days=30)  # la polla queda activa hasta el marcador final (como antes)
GAME_KINDS = ("memory", "trivia", "differences")

# Las mismas columnas de la migracion 024m (tambien en el arranque de Hospitality).
CAMPAIGN_COLUMNS = (
    "rules_version integer NOT NULL DEFAULT 1",
    "predictions_close_at timestamptz NULL",
    "secret_answer_key varchar(40) NOT NULL DEFAULT ''",
    "result_status varchar(20) NOT NULL DEFAULT ''",
    "result jsonb NOT NULL DEFAULT '{}'::jsonb",
    "winner jsonb NULL",
    "closed_at timestamptz NULL",
    "closed_by varchar(200) NULL",
    "prize_status varchar(20) NOT NULL DEFAULT ''",
    "prize_delivered_at timestamptz NULL",
    "prize_delivered_by varchar(200) NULL",
    "tiebreak_round_id uuid NULL",
)


class RetoError(Exception):
    def __init__(self, code: str, status: int = 409):
        super().__init__(code)
        self.code = code
        self.status = status


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _json(value: Any, default: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return default
    return default if value is None else value


def _aware(value: Any) -> Optional[datetime]:
    if value is None or value == "":
        return None
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            raise RetoError("fecha_invalida", 422) from None
    if not isinstance(value, datetime):
        raise RetoError("fecha_invalida", 422)
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _iso(value: Any) -> Optional[str]:
    return value.astimezone(timezone.utc).isoformat() if isinstance(value, datetime) else None


def _clean(value: Any, limit: int) -> str:
    return " ".join(str(value or "").split())[:limit]


def _hsp():
    from app.api.v1.endpoints import hospitality

    return hospitality


# ---------------------------------------------------------------- interruptor
async def is_on(db: AsyncSession, company_id: Any) -> bool:
    row = (await db.execute(text("""
        SELECT cm.enabled, cm.settings FROM company_modules cm JOIN modules m ON m.id = cm.module_id
        WHERE cm.company_id::text = :c AND lower(m.code) = :m LIMIT 1
    """), {"c": str(company_id), "m": MODULE})).mappings().first()
    return bool(row and row["enabled"] and _json(row["settings"], {}).get(FLAG) is True)


# ---------------------------------------------------------------- reglas (puras)
def score_outcome(predictions: list[dict], score_a: int, score_b: int) -> dict:
    """Solo el marcador EXACTO gana. Una mesa = un pronostico (indice unico)."""
    a, b = int(score_a), int(score_b)
    hits = sorted((p for p in predictions if int(p["score_a"]) == a and int(p["score_b"]) == b), key=lambda p: str(p.get("created_at") or ""))
    status = "no_winner" if not hits else "winner" if len(hits) == 1 else "tie"
    return {"status": status, "score_a": a, "score_b": b, "predictions": len(predictions),
            "matches": [{"table_key": p["table_key"], "table_number": p["table_number"], "team_name": p.get("team_name") or p["table_number"]} for p in hits]}


def _vote_table(v: dict) -> dict:
    return {"kind": "table", "table_key": v["table_key"], "table_number": v["table_number"], "team_name": v.get("voter_name") or v["table_number"],
            "label": v.get("voter_name") or v["table_number"]}


def vote_outcome(mode: str, options: list[dict], votes: list[dict], secret: str = "", choice=secrets.choice) -> dict:
    """Ganador del concurso segun su tipo. `choice` es el aleatorio seguro del servidor."""
    if mode == "participants":
        counts = {o["key"]: 0 for o in options}
        for v in votes:
            if v.get("answer_key") in counts:
                counts[v["answer_key"]] += 1
        table = [{"key": o["key"], "label": o["label"], "count": counts[o["key"]]} for o in options]
        top = max(counts.values(), default=0)
        if top == 0:
            return {"status": "no_winner", "counts": table, "votes": len(votes)}
        leaders = [o for o in table if o["count"] == top]
        if len(leaders) == 1:
            o = leaders[0]
            return {"status": "winner", "counts": table, "votes": len(votes), "source": "votes",
                    "winner": {"kind": "option", "key": o["key"], "label": o["label"], "votes": top}}
        return {"status": "tie", "counts": table, "votes": len(votes), "tied": [{"key": o["key"], "label": o["label"], "votes": top} for o in leaders]}
    if mode in SECRET_KEYS:
        right = [v for v in votes if v.get("answer_key") == secret]
        if not right:
            return {"status": "no_winner", "answers": len(votes), "correct": 0}
        picked = choice(sorted(right, key=lambda v: v["table_key"]))
        return {"status": "winner", "answers": len(votes), "correct": len(right), "source": "draw",
                "draw": {"candidates": len(right), "method": "secrets"}, "winner": _vote_table(picked)}
    if not votes:
        return {"status": "no_winner", "registered": 0}
    return {"status": "pick", "registered": len(votes)}


def stage_of(row: dict, now: datetime) -> dict:
    """Etapa en la linea de tiempo (Inscripcion -> En juego -> Resultado), su
    cuenta regresiva y el boton de LO QUE FALTA."""
    t, status, rs = row["campaign_type"], row["status"], row.get("result_status") or ""
    if status != "active":
        return {"stage": "result", "deadline": None, "deadline_label": "", "actions": ["deliver"] if row.get("prize_status") == "pending" else []}
    if rs in ("tie", "pick"):
        acts = ["tiebreak", "pick_winner"] if t == "score_pool" else ["pick_winner"]
        return {"stage": "result", "deadline": None, "deadline_label": "", "actions": [*acts, "cancel"]}
    if t == "consumption":
        reg, starts, ends = _aware(row.get("registration_ends_at")), _aware(row["starts_at"]), _aware(row["ends_at"])
        if reg and now < reg:
            return {"stage": "registration", "deadline": _iso(reg), "deadline_label": "Inscripción cierra en", "actions": ["close_now", "cancel"]}
        if now < starts:
            return {"stage": "playing", "deadline": _iso(starts), "deadline_label": "El torneo empieza en", "actions": ["close_now", "cancel"]}
        return {"stage": "playing", "deadline": _iso(ends), "deadline_label": "El torneo cierra en", "actions": ["close_now", "cancel"]}
    if t == "score_pool":
        close = _aware(row.get("predictions_close_at"))
        if close and now < close:
            return {"stage": "registration", "deadline": _iso(close), "deadline_label": "Pronósticos cierran en", "actions": ["close_now", "cancel"]}
        return {"stage": "playing", "deadline": None, "deadline_label": "", "actions": ["set_score", "cancel"]}
    ends = _aware(row["ends_at"])
    mode = row.get("vote_mode") or "registration"
    label = "Inscripción cierra en" if mode == "registration" else "Votación cierra en" if mode == "participants" else "Respuestas cierran en"
    return {"stage": "registration", "deadline": _iso(ends), "deadline_label": label, "actions": ["close_now", "cancel"]}


# ---------------------------------------------------------------- lectura
async def _row(db: AsyncSession, company_id: Any, reto_id: Any, lock: bool = False) -> dict:
    try:
        uuid.UUID(str(reto_id))
    except ValueError:
        raise RetoError("reto_no_encontrado", 404) from None
    row = (await db.execute(text(f"""SELECT * FROM hospitality_loyalty_campaigns WHERE company_id::text = :c AND id::text = :i
        {'FOR UPDATE' if lock else ''}"""), {"c": str(company_id), "i": str(reto_id)})).mappings().first()
    if not row:
        raise RetoError("reto_no_encontrado", 404)
    return dict(row)


async def active_of_type(db: AsyncSession, company_id: Any, campaign_type: str) -> Optional[dict]:
    row = (await db.execute(text("""SELECT * FROM hospitality_loyalty_campaigns WHERE company_id::text = :c AND status = 'active'
        AND campaign_type = :t ORDER BY starts_at DESC, created_at DESC LIMIT 1"""), {"c": str(company_id), "t": campaign_type})).mappings().first()
    return dict(row) if row else None


async def recent_result(db: AsyncSession, company_id: Any, campaign_type: str, now: Optional[datetime] = None) -> Optional[dict]:
    """El ultimo reto ya resuelto (con resultado) de las ultimas 6 h: el QR muestra el resultado."""
    now = now or _now()
    row = (await db.execute(text("""SELECT * FROM hospitality_loyalty_campaigns WHERE company_id::text = :c AND campaign_type = :t
        AND status = 'closed' AND result_status <> '' AND closed_at > :since ORDER BY closed_at DESC LIMIT 1"""),
                            {"c": str(company_id), "t": campaign_type, "since": now - RECENT_RESULT})).mappings().first()
    return dict(row) if row else None


def public_fields(row: dict, now: Optional[datetime] = None) -> dict:
    """Lo que el QR de la mesa puede ver de un reto nuevo. Nunca la respuesta secreta."""
    now = now or _now()
    close = _aware(row.get("predictions_close_at"))
    result = _json(row.get("result"), {}) or {}
    winner = _json(row.get("winner"), None)
    out: dict = {
        "rules_version": int(row.get("rules_version") or 1),
        "predictions_close_at": _iso(close),
        "predictions_open": bool(row.get("status") == "active" and not row.get("result_status") and (close is None or now < close)),
        "predictions_seconds_left": max(int((close - now).total_seconds()), 0) if close else None,
        "result_status": row.get("result_status") or "",
        "closed_at": _iso(row.get("closed_at")),
        "winner": None,
        "final_score": None,
        "tied_tables": [],
    }
    if winner:
        out["winner"] = {k: winner.get(k) for k in ("kind", "table_key", "table_number", "team_name", "player_name", "label") if winner.get(k) is not None}
    if row["campaign_type"] == "score_pool" and "score_a" in result:
        out["final_score"] = {"score_a": int(result["score_a"]), "score_b": int(result["score_b"])}
    if row.get("result_status") == "tie" and row["campaign_type"] == "score_pool":
        out["tied_tables"] = [{"table_key": m["table_key"], "table_number": m["table_number"]} for m in result.get("matches") or []]
    return out


async def _tiebreak_info(db: AsyncSession, company_id: Any, row: dict) -> Optional[dict]:
    rid = row.get("tiebreak_round_id")
    if not rid:
        return None
    r = (await db.execute(text("""SELECT id::text AS id, kind, status, (SELECT count(*) FROM loyalty_game_players p WHERE p.round_id = g.id
        AND p.company_id = g.company_id) AS players FROM loyalty_game_rounds g WHERE company_id::text = :c AND id::text = :i"""),
                          {"c": str(company_id), "i": str(rid)})).mappings().first()
    return {"round_id": r["id"], "kind": r["kind"], "status": r["status"], "players": int(r["players"] or 0)} if r else None


async def view(db: AsyncSession, row: dict, now: Optional[datetime] = None, panel: bool = True) -> dict:
    """Tarjeta del panel: lo de siempre (misma forma que Hospitality) + etapa, resultado y premio."""
    now = now or _now()
    hsp = _hsp()
    t = row["campaign_type"]
    if t == "consumption":
        board = await hsp._loyalty_leaderboard(db, row)
        out = hsp._campaign_payload(row, board)
        participants = len(board)
    elif t == "score_pool":
        preds = await hsp._score_pool_predictions(db, row)
        out = hsp._score_pool_payload(row, preds)
        participants = len(preds)
    else:
        votes = await hsp._vote_poll_votes(db, row)
        out = hsp._vote_poll_payload(row, votes)
        participants = len(votes)
    out.update(public_fields(row, now))
    out.update(stage_of(row, now))
    out.update({
        "participants": participants,
        "result": _json(row.get("result"), {}) or {},
        "winner": _json(row.get("winner"), None),
        "closed_by": row.get("closed_by") or "",
        "prize_status": row.get("prize_status") or "",
        "prize_delivered_at": _iso(row.get("prize_delivered_at")),
        "prize_delivered_by": row.get("prize_delivered_by") or "",
        "tiebreak": await _tiebreak_info(db, row["company_id"], row),
    })
    if panel:
        out["secret_answer_key"] = row.get("secret_answer_key") or ""
    return out


# ---------------------------------------------------------------- crear
def _when(raw: dict, key: str, required: bool = True) -> Optional[datetime]:
    value = _aware(raw.get(key))
    if required and value is None:
        raise RetoError(f"{key}_requerido", 422)
    return value


def validate_new(raw: dict, now: datetime) -> dict:
    """Valida el asistente (Que -> Cuando). Devuelve las columnas a insertar."""
    if not isinstance(raw, dict):
        raise RetoError("datos_invalidos", 422)
    t = str(raw.get("type") or "")
    if t not in TYPES:
        raise RetoError("tipo_invalido", 422)
    defaults = {"consumption": "Reto de consumo", "score_pool": "Polla de marcador", "vote_poll": "Concurso"}
    out: dict = {"campaign_type": t, "title": _clean(raw.get("title"), 160) or defaults[t], "prize": _clean(raw.get("prize"), 220),
                 "description": _clean(raw.get("description"), 700), "team_a": "", "team_b": "", "vote_mode": "", "options": [],
                 "secret_answer_key": "", "predictions_close_at": None}
    if not out["prize"]:
        raise RetoError("premio_requerido", 422)

    def future(dt: datetime, code: str) -> None:
        if dt <= now:
            raise RetoError(code, 422)
        if dt > now + MAX_AHEAD:
            raise RetoError("fecha_muy_lejana", 422)

    if t == "consumption":
        reg, starts, ends = _when(raw, "registration_ends_at"), _when(raw, "starts_at"), _when(raw, "ends_at")
        future(reg, "inscripcion_en_el_pasado")
        if starts < reg:
            raise RetoError("inicio_antes_de_inscripcion", 422)
        if ends <= starts:
            raise RetoError("cierre_antes_de_inicio", 422)
        future(ends, "cierre_en_el_pasado")
        out.update({"registration_ends_at": reg, "starts_at": starts, "ends_at": ends})
    elif t == "score_pool":
        out["team_a"], out["team_b"] = _clean(raw.get("team_a"), 120), _clean(raw.get("team_b"), 120)
        if not out["team_a"] or not out["team_b"]:
            raise RetoError("equipos_requeridos", 422)
        if out["team_a"].lower() == out["team_b"].lower():
            raise RetoError("equipos_iguales", 422)
        close = _when(raw, "predictions_close_at")
        future(close, "pronosticos_en_el_pasado")
        out.update({"predictions_close_at": close, "registration_ends_at": close, "starts_at": now, "ends_at": close + POOL_KEEP})
    else:
        mode = str(raw.get("vote_mode") or "registration")
        if mode not in VOTE_MODES:
            raise RetoError("tipo_de_concurso_invalido", 422)
        hsp = _hsp()
        out["vote_mode"] = mode
        if mode == "participants":
            names = [_clean(x, 120) for x in (raw.get("options") or []) if _clean(x, 120)]
            if len(names) < 2 or len(names) > 5:
                raise RetoError("opciones_de_2_a_5", 422)
            if len({n.lower() for n in names}) != len(names):
                raise RetoError("opciones_repetidas", 422)
            out["options"] = hsp._vote_poll_options(mode, names)[: len(names)]
        else:
            out["options"] = hsp._vote_poll_options(mode, [])
        if mode in SECRET_KEYS:
            secret = str(raw.get("secret_answer") or "")
            if secret not in SECRET_KEYS[mode]:
                raise RetoError("respuesta_correcta_requerida", 422)
            out["secret_answer_key"] = secret
        if mode != "registration" and not _clean(raw.get("description"), 700):
            raise RetoError("pregunta_requerida", 422)
        ends = _when(raw, "ends_at")
        future(ends, "cierre_en_el_pasado")
        out.update({"registration_ends_at": ends, "starts_at": now, "ends_at": ends})
    return out


async def create(db: AsyncSession, company_id: Any, raw: dict, actor: str, now: Optional[datetime] = None) -> dict:
    now = now or _now()
    data = validate_new(raw, now)
    # Uno activo por tipo: el candado serializa dos "Publicar" al mismo tiempo.
    await db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": f"retos:{company_id}:{data['campaign_type']}"})
    await refresh_due(db, company_id, now, commit=False)
    if await active_of_type(db, company_id, data["campaign_type"]):
        await db.rollback()
        raise RetoError("ya_hay_uno_activo_de_este_tipo", 409)
    rid = (await db.execute(text("""
        INSERT INTO hospitality_loyalty_campaigns (company_id, title, prize, description, campaign_type, team_a, team_b, vote_mode, options,
            registration_ends_at, starts_at, ends_at, status, rules_version, predictions_close_at, secret_answer_key, created_at, updated_at)
        VALUES (CAST(:c AS uuid), :title, :prize, :description, :campaign_type, :team_a, :team_b, :vote_mode, CAST(:options AS jsonb),
            :registration_ends_at, :starts_at, :ends_at, 'active', :rules, :predictions_close_at, :secret_answer_key, :n, :n)
        RETURNING id::text
    """), {**data, "options": json.dumps(data["options"], ensure_ascii=False), "c": str(company_id), "rules": RULES, "n": now})).scalar()
    await db.commit()
    return await view(db, await _row(db, company_id, rid), now)


# ---------------------------------------------------------------- resolver
async def _finish(db: AsyncSession, company_id: Any, row: dict, outcome: dict, actor: str, now: datetime) -> None:
    """Guarda el resultado. Ganador o sin ganador: el reto cierra (historial). Empate o
    "elegir": sigue en curso esperando al bar."""
    status = outcome["status"]
    winner = outcome.pop("winner", None)
    if winner:
        winner["source"] = outcome.get("source") or winner.get("source") or ""
    closed = status in ("winner", "no_winner")
    await db.execute(text("""
        UPDATE hospitality_loyalty_campaigns SET result_status = :rs, result = CAST(:res AS jsonb), winner = CAST(:w AS jsonb),
            status = CASE WHEN :closed THEN 'closed' ELSE status END, closed_at = CASE WHEN :closed THEN :n ELSE closed_at END,
            closed_by = CASE WHEN :closed THEN :by ELSE closed_by END, prize_status = CASE WHEN CAST(:w AS jsonb) IS NOT NULL THEN 'pending' ELSE prize_status END,
            rules_version = GREATEST(rules_version, :rules), updated_at = :n
        WHERE company_id::text = :c AND id::text = :i
    """), {"rs": status, "res": json.dumps(outcome, ensure_ascii=False, default=str), "w": json.dumps(winner, ensure_ascii=False) if winner else None,
           "closed": closed, "n": now, "by": actor[:200], "rules": RULES, "c": str(company_id), "i": str(row["id"])})


async def _consumption_outcome(db: AsyncSession, row: dict) -> dict:
    board = await _hsp()._loyalty_leaderboard(db, row)  # el ranking de siempre
    top = [{"rank": r["rank"], "table_key": r["table_key"], "table_number": r["table_number"], "team_name": r["team_name"], "total": r["total"],
            "orders_count": r["orders_count"]} for r in board[:5]]
    if not board or float(board[0]["total"] or 0) <= 0:
        return {"status": "no_winner", "participants": len(board), "top": top}
    w = board[0]
    return {"status": "winner", "participants": len(board), "top": top, "source": "consumption",
            "winner": {"kind": "table", "table_key": w["table_key"], "table_number": w["table_number"], "team_name": w["team_name"], "label": w["team_name"],
                       "total": w["total"], "orders_count": w["orders_count"]}}


async def _vote_outcome_for(db: AsyncSession, row: dict, secret: str) -> dict:
    hsp = _hsp()
    mode = hsp._vote_poll_mode(row.get("vote_mode"))
    options = hsp._vote_poll_options(mode, _json(row.get("options"), []))
    if mode == "participants":
        saved = _json(row.get("options"), []) or []
        options = options[: len(saved)] if saved else options
    votes = await hsp._vote_poll_votes(db, row)
    return vote_outcome(mode, options, votes, secret)


async def close_now(db: AsyncSession, company_id: Any, reto_id: Any, actor: str, answer_key: Optional[str] = None,
                    now: Optional[datetime] = None, reason: str = "manual") -> dict:
    """Consumo: cierra el torneo y guarda al ganador. Concurso: cierra la votacion o la
    inscripcion y aplica la regla de su tipo. (La polla se cierra con el marcador final.)"""
    now = now or _now()
    row = await _row(db, company_id, reto_id, lock=True)
    if row["status"] != "active" or row.get("result_status"):
        await db.rollback()
        raise RetoError("el_reto_ya_tiene_resultado")
    t = row["campaign_type"]
    if t == "score_pool":
        close = _aware(row.get("predictions_close_at"))
        if close and close <= now:
            await db.rollback()
            raise RetoError("pronosticos_ya_cerrados")
        await db.execute(text("""UPDATE hospitality_loyalty_campaigns SET predictions_close_at = :n, registration_ends_at = LEAST(registration_ends_at, :n),
            rules_version = GREATEST(rules_version, :rules), updated_at = :n WHERE company_id::text = :c AND id::text = :i"""),
                         {"n": now, "rules": RULES, "c": str(company_id), "i": str(row["id"])})
        await db.commit()
        return await view(db, await _row(db, company_id, reto_id), now)
    secret = row.get("secret_answer_key") or ""
    if t == "vote_poll":
        mode = _hsp()._vote_poll_mode(row.get("vote_mode"))
        if mode in SECRET_KEYS and not secret:
            # Concurso de antes (sin respuesta guardada): el bar la dice al cerrar.
            if answer_key not in SECRET_KEYS[mode]:
                await db.rollback()
                raise RetoError("falta_respuesta_correcta", 422)
            secret = str(answer_key)
    end = _aware(row["ends_at"])
    cut = min(now, end) if reason == "time" else now
    if reason == "manual" and end > now:
        # Cerrar ahora = el torneo, la inscripcion o la votacion terminan en este momento.
        await db.execute(text("""UPDATE hospitality_loyalty_campaigns SET ends_at = :n, registration_ends_at = LEAST(registration_ends_at, :n),
            secret_answer_key = :s, updated_at = :n WHERE company_id::text = :c AND id::text = :i"""),
                         {"n": cut, "s": secret, "c": str(company_id), "i": str(row["id"])})
        row["ends_at"] = cut
    elif secret != (row.get("secret_answer_key") or ""):
        await db.execute(text("UPDATE hospitality_loyalty_campaigns SET secret_answer_key = :s WHERE company_id::text = :c AND id::text = :i"),
                         {"s": secret, "c": str(company_id), "i": str(row["id"])})
    outcome = await _consumption_outcome(db, row) if t == "consumption" else await _vote_outcome_for(db, row, secret)
    outcome["closed"] = reason
    await _finish(db, company_id, row, outcome, actor, now)
    await db.commit()
    return await view(db, await _row(db, company_id, reto_id), now)


async def set_score(db: AsyncSession, company_id: Any, reto_id: Any, score_a: Any, score_b: Any, actor: str, now: Optional[datetime] = None) -> dict:
    now = now or _now()
    try:
        a, b = int(score_a), int(score_b)
    except (TypeError, ValueError):
        raise RetoError("marcador_invalido", 422) from None
    if not (0 <= a <= 99 and 0 <= b <= 99):
        raise RetoError("marcador_invalido", 422)
    row = await _row(db, company_id, reto_id, lock=True)
    if row["campaign_type"] != "score_pool":
        await db.rollback()
        raise RetoError("no_es_una_polla", 422)
    if row["status"] != "active" or row.get("result_status"):
        await db.rollback()
        raise RetoError("el_reto_ya_tiene_resultado")
    close = _aware(row.get("predictions_close_at"))
    if close and now < close:
        await db.rollback()
        raise RetoError("pronosticos_abiertos")
    outcome = score_outcome(await _hsp()._score_pool_predictions(db, row), a, b)
    if outcome["status"] == "winner":
        m = outcome["matches"][0]
        outcome["source"] = "exact"
        outcome["winner"] = {"kind": "table", **m, "label": m["team_name"]}
    await _finish(db, company_id, row, outcome, actor, now)
    await db.commit()
    return await view(db, await _row(db, company_id, reto_id), now)


async def pick_winner(db: AsyncSession, company_id: Any, reto_id: Any, key: str, actor: str, now: Optional[datetime] = None) -> dict:
    """El bar elige: entre las opciones empatadas (votacion), entre los inscritos
    (inscripcion simple) o entre las mesas empatadas de la polla."""
    now = now or _now()
    row = await _row(db, company_id, reto_id, lock=True)
    rs = row.get("result_status") or ""
    if row["status"] != "active" or rs not in ("tie", "pick"):
        await db.rollback()
        raise RetoError("no_hay_que_elegir")
    result = _json(row.get("result"), {}) or {}
    key = str(key or "")
    winner = None
    if row["campaign_type"] == "score_pool":
        m = next((m for m in result.get("matches") or [] if m["table_key"] == key), None)
        if m:
            winner = {"kind": "table", **m, "label": m["team_name"]}
    elif rs == "tie":
        o = next((o for o in result.get("tied") or [] if o["key"] == key), None)
        if o:
            winner = {"kind": "option", **o}
    else:
        v = next((v for v in await _hsp()._vote_poll_votes(db, row) if v["table_key"] == key), None)
        if v:
            winner = _vote_table(v)
    if not winner:
        await db.rollback()
        raise RetoError("opcion_no_valida", 422)
    if row.get("tiebreak_round_id"):
        live = (await db.execute(text("""SELECT 1 FROM loyalty_game_rounds WHERE company_id::text = :c AND id::text = :i
            AND status IN ('registration', 'playing')"""), {"c": str(company_id), "i": str(row["tiebreak_round_id"])})).first()
        if live:
            await db.rollback()
            raise RetoError("hay_un_desempate_en_curso")
    outcome = {**result, "status": "winner", "source": "bar", "chosen_by": actor[:200], "winner": winner}
    await _finish(db, company_id, row, outcome, actor, now)
    await db.commit()
    return await view(db, await _row(db, company_id, reto_id), now)


async def cancel(db: AsyncSession, company_id: Any, reto_id: Any, actor: str, now: Optional[datetime] = None) -> dict:
    """Cancelar y reiniciar: anula el reto SIN ganador y libera el espacio para otro
    del mismo tipo. El QR deja de mostrarlo; queda en el historial como Cancelado
    con hora y quien. Si tenia un desempate abierto en Juegos en vivo, tambien se cancela."""
    now = now or _now()
    row = await _row(db, company_id, reto_id, lock=True)
    if row["status"] != "active":
        await db.rollback()
        raise RetoError("el_reto_ya_termino")
    await db.execute(text("""UPDATE hospitality_loyalty_campaigns SET status = 'cancelled', result_status = 'cancelled', winner = NULL, prize_status = '',
        closed_at = :n, closed_by = :by, ends_at = LEAST(ends_at, :n), rules_version = GREATEST(rules_version, :rules), updated_at = :n
        WHERE company_id::text = :c AND id::text = :i"""), {"n": now, "by": actor[:200], "rules": RULES, "c": str(company_id), "i": str(row["id"])})
    await db.commit()
    if row.get("tiebreak_round_id"):
        from app.services import loyalty_games as games
        from app.services.loyalty_games_engine import GameError

        try:
            await games.cancel_round(db, company_id, row["tiebreak_round_id"], actor, now)
        except GameError:
            await db.rollback()  # ya habia terminado
    return await view(db, await _row(db, company_id, reto_id), now)


# ---------------------------------------------------------------- desempate con Juego en vivo
async def open_tiebreak(db: AsyncSession, company_id: Any, reto_id: Any, kind: str, actor: str, pairs: Optional[int] = None,
                        scene: Optional[str] = None, now: Optional[datetime] = None) -> dict:
    from app.services import loyalty_games as games
    from app.services.loyalty_games_engine import GameError

    now = now or _now()
    if not await games.is_on(db, company_id):
        raise RetoError("juegos_en_vivo_no_activo", 409)
    if kind not in GAME_KINDS:
        raise RetoError("juego_invalido", 422)
    row = await _row(db, company_id, reto_id)
    if row["campaign_type"] != "score_pool" or row["status"] != "active" or row.get("result_status") != "tie":
        raise RetoError("la_polla_no_esta_empatada")
    matches = (_json(row.get("result"), {}) or {}).get("matches") or []
    tiebreak = {"campaign_id": str(row["id"]), "title": f"Desempate · {row.get('title') or 'Polla'}", "teams": f"{row.get('team_a')} vs {row.get('team_b')}",
                "tables": [{"key": m["table_key"], "label": m["table_number"], "team": m.get("team_name") or m["table_number"]} for m in matches]}
    try:
        r = await games.open_round(db, company_id, kind, row.get("prize") or "", actor, now=now, pairs=pairs, scene=scene, tiebreak=tiebreak)
    except GameError as exc:
        raise RetoError(exc.code, exc.status) from None
    await db.execute(text("UPDATE hospitality_loyalty_campaigns SET tiebreak_round_id = CAST(:r AS uuid), updated_at = :n WHERE company_id::text = :c AND id::text = :i"),
                     {"r": str(r["id"]), "n": now, "c": str(company_id), "i": str(row["id"])})
    await db.commit()
    return await view(db, await _row(db, company_id, reto_id), now)


async def on_tiebreak_closed(db: AsyncSession, company_id: Any, game_round: dict) -> None:
    """Al cerrar la ronda de desempate: el 1.er puesto es el ganador de la polla
    (mesa y jugador). Sin 1.er puesto, la polla sigue empatada."""
    tb = (_json(game_round.get("config"), {}) or {}).get("tiebreak") or {}
    if not tb.get("campaign_id") or game_round.get("status") != "closed":
        return
    p = (await db.execute(text("""SELECT display_name, table_key, table_number FROM loyalty_game_players
        WHERE company_id::text = :c AND round_id::text = :r AND place = 1 AND result = 'ranked' LIMIT 1"""),
                          {"c": str(company_id), "r": str(game_round["id"])})).mappings().first()
    if not p:
        return
    try:
        row = await _row(db, company_id, tb["campaign_id"], lock=True)
    except RetoError:
        return
    if row["status"] != "active" or row.get("result_status") != "tie" or str(row.get("tiebreak_round_id")) != str(game_round["id"]):
        await db.rollback()
        return
    result = _json(row.get("result"), {}) or {}
    m = next((m for m in result.get("matches") or [] if m["table_key"] == p["table_key"]), {})
    winner = {"kind": "table", "table_key": p["table_key"], "table_number": p["table_number"], "team_name": m.get("team_name") or p["table_number"],
              "player_name": p["display_name"], "label": m.get("team_name") or p["table_number"], "round_id": str(game_round["id"])}
    outcome = {**result, "status": "winner", "source": "tiebreak", "winner": winner}
    await _finish(db, company_id, row, outcome, "Juego en vivo", _now())
    await db.commit()


# ---------------------------------------------------------------- premio
async def deliver_prize(db: AsyncSession, company_id: Any, reto_id: Any, actor: str, document: Optional[str] = None,
                        now: Optional[datetime] = None) -> dict:
    """Pendiente -> entregado. Si gano en el desempate, primero la validacion por
    documento que ya existe en Juegos en vivo (HMAC; el numero nunca se guarda)."""
    now = now or _now()
    row = await _row(db, company_id, reto_id, lock=True)
    winner = _json(row.get("winner"), None)
    if not winner or row.get("prize_status") != "pending":
        await db.rollback()
        raise RetoError("no_hay_premio_pendiente")
    if winner.get("source") == "tiebreak" and winner.get("round_id"):
        from app.services import loyalty_games as games
        from app.services.loyalty_games_engine import GameError

        await db.rollback()
        try:
            check = await games.validate_winner(db, company_id, winner["round_id"], 1, str(document or ""), actor)
        except GameError as exc:
            raise RetoError(exc.code, exc.status) from None
        if not check["match"]:
            return {"match": False}
        row = await _row(db, company_id, reto_id, lock=True)
        if row.get("prize_status") != "pending":
            await db.rollback()
            raise RetoError("no_hay_premio_pendiente")
    await db.execute(text("""UPDATE hospitality_loyalty_campaigns SET prize_status = 'delivered', prize_delivered_at = :n, prize_delivered_by = :by,
        updated_at = :n WHERE company_id::text = :c AND id::text = :i"""), {"n": now, "by": actor[:200], "c": str(company_id), "i": str(reto_id)})
    await db.commit()
    return {"match": True, "reto": await view(db, await _row(db, company_id, reto_id), now)}


# ---------------------------------------------------------------- cierre automatico
async def refresh_due(db: AsyncSession, company_id: Any, now: Optional[datetime] = None, commit: bool = True) -> int:
    """Cierra a su hora (calculado desde la base) los retos nuevos de consumo y
    concurso. Los de antes (rules_version 1) no se tocan solos."""
    now = now or _now()
    due = (await db.execute(text("""SELECT id::text FROM hospitality_loyalty_campaigns WHERE company_id::text = :c AND status = 'active'
        AND rules_version >= 2 AND result_status = '' AND campaign_type IN ('consumption', 'vote_poll') AND ends_at <= :n"""),
                            {"c": str(company_id), "n": now})).scalars().all()
    done = 0
    for rid in due:
        row = await _row(db, company_id, rid, lock=True)
        if row["status"] != "active" or row.get("result_status"):
            continue
        outcome = await _consumption_outcome(db, row) if row["campaign_type"] == "consumption" else await _vote_outcome_for(db, row, row.get("secret_answer_key") or "")
        outcome["closed"] = "time"
        await _finish(db, company_id, row, outcome, "Cierre automático", now)
        done += 1
    if done and commit:
        await db.commit()
    return done


# ---------------------------------------------------------------- pantalla
async def history(db: AsyncSession, company_id: Any, limit: int = 40) -> list[dict]:
    rows = (await db.execute(text("""SELECT id::text AS id, campaign_type, title, prize, team_a, team_b, vote_mode, status, result_status, result, winner,
            prize_status, prize_delivered_at, prize_delivered_by, closed_at, closed_by, created_at, updated_at, ends_at
        FROM hospitality_loyalty_campaigns WHERE company_id::text = :c AND status <> 'active'
        ORDER BY COALESCE(closed_at, updated_at) DESC LIMIT :l"""), {"c": str(company_id), "l": limit})).mappings().all()
    out = []
    for r in rows:
        res = _json(r["result"], {}) or {}
        out.append({"id": r["id"], "type": r["campaign_type"], "title": r["title"], "status": r["status"], "prize": r["prize"], "team_a": r["team_a"], "team_b": r["team_b"],
                    "vote_mode": r["vote_mode"], "result_status": r["result_status"] or "", "winner": _json(r["winner"], None),
                    "final_score": {"score_a": res["score_a"], "score_b": res["score_b"]} if "score_a" in res else None,
                    "source": res.get("source") or "", "prize_status": r["prize_status"] or "", "prize_delivered_at": _iso(r["prize_delivered_at"]),
                    "prize_delivered_by": r["prize_delivered_by"] or "", "closed_at": _iso(r["closed_at"] or r["updated_at"]), "closed_by": r["closed_by"] or ""})
    return out


async def state(db: AsyncSession, company_id: Any, role: str, now: Optional[datetime] = None) -> dict:
    from app.services import business_day, company_locale
    from app.services import loyalty_games as games

    now = now or _now()
    await refresh_due(db, company_id, now)
    loc = await company_locale.get_company_locale(db, company_id)
    settings = (await db.execute(text("SELECT settings_json FROM companies WHERE id::text = :c"), {"c": str(company_id)})).scalar()
    active = {}
    for t in TYPES:
        row = await active_of_type(db, company_id, t)
        active[t] = await view(db, row, now) if row else None
    return {"now": now.isoformat(), "role": role, "timezone": loc["timezone"], "language": loc.get("language") or "es", "currency": loc.get("currency") or "COP",
            "business_day": business_day.public(business_day.config(settings)), "games_on": await games.is_on(db, company_id),
            "active": active, "history": await history(db, company_id)}
