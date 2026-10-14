"""Juegos en vivo (interruptor loyalty_games): reglas puras, sin base de datos.

- Ruleta: el numero lo elige `secrets` entre los que NO han salido esa noche en
  ese rango; si no queda ninguno, avisa.
- Memoria: 10 cartas (5 parejas) con iconos de bar y musica, IGUALES para todos
  en la ronda (semilla de la ronda). La cara solo se conoce al voltear: el
  progreso guarda posiciones, el servidor responde la cara de esa carta.
- Trivia: 5 preguntas (una por nivel), 3 opciones en orden al azar; 10 s por
  pregunta (+1 s de red); las no respondidas vuelven en otra vuelta con otro
  orden; una respondida (bien o mal) ya no vuelve.
- Ranking: memoria = mas parejas y, si empatan, quien llego antes a ese numero;
  trivia = mas aciertos y, si empatan, menos tiempo total. Con 0 parejas (o
  trivia sin terminar) no hay podio.
- Documento: HMAC-SHA256 con un secreto del servidor; nunca el numero.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import random
import re
import secrets
from datetime import datetime
from typing import Any, Optional

# Rondas de antes (sin config de reglas): 5 parejas con estos 12 iconos. Se
# conservan tal cual para que un tablero ya repartido no cambie.
LEGACY_ICONS = ["🍸", "🎸", "🎤", "🍺", "🎷", "🥃", "🎹", "🎧", "🍹", "🥁", "🎺", "🍷"]
LEGACY_PAIRS = 5
# Reglas 2: 20 iconos claramente distintos de bar, musica y rock; nunca se repite uno entre parejas.
ICONS = ["🍸", "🎸", "🎤", "🍺", "🎷", "🥃", "🎹", "🎧", "🍹", "🥁", "🎺", "🍷", "🎻", "💿", "🍾", "🤘", "🎼", "📻", "🔥", "🍋"]
PAIR_OPTIONS = (5, 7, 10, 13, 15)
PAIR_SECONDS = {5: 120, 7: 150, 10: 210, 13: 270, 15: 300}
QUESTION_MS = 10_000
GRACE_MS = 1_000
LEVELS = (1, 2, 3, 4, 5)


class GameError(ValueError):
    def __init__(self, code: str, status: int = 409):
        super().__init__(code)
        self.code = code
        self.status = status


# ---------------------------------------------------------------- firmas
def _key() -> bytes:
    configured = os.getenv("LOYALTY_GAMES_SECRET")
    if configured:
        return configured.encode("utf-8")
    from app.web import admin_v2_routes as v2

    return hmac.new(v2._session_secret(), b"clonexa-loyalty-games-v1", hashlib.sha256).digest()


def sign(kind: str, value: str) -> str:
    sig = hmac.new(_key(), f"{kind}:{value}".encode("utf-8"), hashlib.sha256).hexdigest()[:24]
    return f"{value}.{sig}"


def unsign(kind: str, token: str) -> Optional[str]:
    value, _, sig = str(token or "").strip().rpartition(".")
    if not value or not sig or len(token) > 120:
        return None
    return value if hmac.compare_digest(sign(kind, value), f"{value}.{sig}") else None


def clean_document(raw: Any) -> str:
    doc = re.sub(r"[^0-9A-Za-z]", "", str(raw or "")).upper()
    if not 5 <= len(doc) <= 15:
        raise GameError("documento_invalido", 422)
    return doc


def document_hmac(company_id: Any, raw: Any) -> str:
    doc = clean_document(raw)
    return hmac.new(_key(), f"doc:{company_id}:{doc}".encode("utf-8"), hashlib.sha256).hexdigest()


def clean_name(raw: Any) -> str:
    name = re.sub(r"\s+", " ", str(raw or "")).strip()
    name = re.sub(r"[<>]", "", name)
    if not name:
        raise GameError("nombre_requerido", 422)
    return name[:20]


def new_seed() -> int:
    return secrets.randbits(62)


# ---------------------------------------------------------------- ruleta
def pick_number(range_min: int, range_max: int, drawn: set[int]) -> int:
    if range_min > range_max or range_max - range_min > 9999:
        raise GameError("rango_invalido", 422)
    free = [n for n in range(range_min, range_max + 1) if n not in drawn]
    if not free:
        raise GameError("numeros_agotados")
    return secrets.choice(free)


# ---------------------------------------------------------------- memoria
def board(seed: int, pairs: Optional[int] = None) -> list[str]:
    """Tablero de la ronda (igual para todos). pairs=None: el de las rondas de
    antes (5 parejas, 12 iconos), identico al que ya se repartio."""
    rnd = random.Random(int(seed))
    if pairs is None:
        icons = rnd.sample(LEGACY_ICONS, LEGACY_PAIRS)
    else:
        if int(pairs) not in PAIR_OPTIONS:
            raise GameError("parejas_invalidas", 422)
        icons = rnd.sample(ICONS, int(pairs))
    cards = icons * 2
    rnd.shuffle(cards)
    return cards


def pairs_of(config: Optional[dict]) -> Optional[int]:
    """Parejas guardadas en la ronda; None = ronda de antes (5)."""
    value = (config or {}).get("pairs")
    return int(value) if value else None


def memory_start() -> dict:
    return {"matched": [], "open": None, "pairs": 0, "pair_ms": [], "flips": 0}


def memory_flip(progress: dict, seed: int, index: int, elapsed_ms: int, pairs: Optional[int] = None) -> tuple[dict, dict]:
    """Voltea `index`. Devuelve (progreso nuevo, respuesta con SOLO las caras volteadas)."""
    cards = board(seed, pairs)
    if not isinstance(index, int) or not 0 <= index < len(cards):
        raise GameError("carta_invalida", 422)
    p = {**memory_start(), **(progress or {})}
    p["matched"] = list(p["matched"])
    p["pair_ms"] = list(p["pair_ms"])
    if index in p["matched"]:
        raise GameError("carta_ya_encontrada")
    p["flips"] += 1
    if p["open"] is None or p["open"] == index:
        p["open"] = index
        return p, {"faces": {str(index): cards[index]}, "open": index, "match": None, "pairs": p["pairs"]}
    first = p["open"]
    match = cards[first] == cards[index]
    p["open"] = None
    if match:
        p["matched"] += [first, index]
        p["pairs"] += 1
        p["pair_ms"].append(int(elapsed_ms))
    return p, {"faces": {str(first): cards[first], str(index): cards[index]}, "open": None, "match": match, "pairs": p["pairs"]}


def memory_public(progress: dict, seed: int, pairs: Optional[int] = None) -> dict:
    """Lo que ve el jugador: solo las caras de las parejas encontradas y la carta abierta."""
    cards = board(seed, pairs)
    p = {**memory_start(), **(progress or {})}
    faces = {str(i): cards[i] for i in p["matched"]}
    if p["open"] is not None:
        faces[str(p["open"])] = cards[p["open"]]
    return {"size": len(cards), "faces": faces, "matched": list(p["matched"]), "open": p["open"], "pairs": p["pairs"], "total_pairs": len(cards) // 2}


def memory_key(player: dict) -> tuple:
    p = player.get("progress") or {}
    pairs = int(p.get("pairs") or 0)
    reached = (p.get("pair_ms") or [0])[-1] if pairs else 10**12
    return (-pairs, reached, str(player.get("joined_at") or ""), str(player.get("id")))


# ---------------------------------------------------------------- trivia
def pick_questions(bank: list[dict], seed: int) -> list[str]:
    """Una pregunta activa por nivel (1..5), al azar con la semilla de la ronda."""
    rnd = random.Random(int(seed))
    out = []
    for level in LEVELS:
        pool = sorted(str(q["id"]) for q in bank if int(q["level"]) == level and q.get("active", True))
        if not pool:
            raise GameError(f"falta_pregunta_nivel_{level}")
        out.append(rnd.choice(pool))
    return out


def trivia_start(question_ids: list[str]) -> dict:
    return {"pending": list(question_ids), "queue": list(question_ids), "lap": 1, "current": None, "answers": {}, "orders": {}}


def _ms(a: datetime, b: datetime) -> int:
    return int((b - a).total_seconds() * 1000)


def _order(previous: Optional[list[int]]) -> list[int]:
    options = [[0, 1, 2], [0, 2, 1], [1, 0, 2], [1, 2, 0], [2, 0, 1], [2, 1, 0]]
    if previous:
        options = [o for o in options if o != list(previous)]
    return list(secrets.choice(options))


def trivia_tick(progress: dict, now: datetime) -> dict:
    """Si la pregunta actual ya paso sus 10 s (+1), queda sin contestar (vuelve en
    la siguiente vuelta). Si no hay pregunta en curso, presenta la siguiente."""
    p = {**progress, "pending": list(progress.get("pending") or []), "queue": list(progress.get("queue") or []),
         "answers": dict(progress.get("answers") or {}), "orders": dict(progress.get("orders") or {})}
    cur = p.get("current")
    if cur and _ms(datetime.fromisoformat(cur["shown_at"]), now) > QUESTION_MS + GRACE_MS:
        p["current"] = None
    if p.get("current") or not p["pending"]:
        return p
    if not p["queue"]:
        p["queue"] = list(p["pending"])
        p["lap"] = int(p.get("lap") or 1) + 1
    qid = p["queue"].pop(0)
    order = _order(p["orders"].get(qid))
    p["orders"][qid] = order
    p["current"] = {"qid": qid, "order": order, "shown_at": now.isoformat()}
    return p


def trivia_answer(progress: dict, qid: str, choice: int, now: datetime) -> tuple[dict, bool]:
    cur = progress.get("current")
    if not cur or cur["qid"] != str(qid):
        raise GameError("pregunta_no_vigente")
    if not isinstance(choice, int) or not 0 <= choice <= 2:
        raise GameError("opcion_invalida", 422)
    elapsed = _ms(datetime.fromisoformat(cur["shown_at"]), now)
    if elapsed > QUESTION_MS + GRACE_MS:
        raise GameError("fuera_de_tiempo")
    ok = cur["order"][choice] == 0
    p = {**progress, "pending": [q for q in progress["pending"] if q != str(qid)], "answers": {**progress.get("answers", {}), str(qid): {"ok": ok, "ms": elapsed}},
         "current": None}
    return p, ok


def trivia_done(progress: dict) -> bool:
    return not (progress or {}).get("pending")


def trivia_correct(progress: dict) -> int:
    return sum(1 for a in (progress or {}).get("answers", {}).values() if a.get("ok"))


def trivia_key(player: dict) -> tuple:
    return (-int(player.get("score") or 0), int(player.get("score_ms") or 10**12), str(player.get("joined_at") or ""), str(player.get("id")))


def remaining_ms(progress: dict, now: datetime) -> int:
    cur = (progress or {}).get("current")
    if not cur:
        return 0
    return max(0, QUESTION_MS - _ms(datetime.fromisoformat(cur["shown_at"]), now))


# ---------------------------------------------------------------- trivia de 10 (reglas 2)
TRIVIA_PER_LEVEL = 2
TRIVIA_GOAL = 10


def pick_questions_v2(bank: list[dict], seed: int, per_level: int = TRIVIA_PER_LEVEL) -> list[str]:
    """2 preguntas activas por nivel (1..5), en orden de nivel, al azar con la semilla de la ronda."""
    rnd = random.Random(int(seed))
    out = []
    for level in LEVELS:
        pool = sorted(str(q["id"]) for q in bank if int(q["level"]) == level and q.get("active", True))
        if len(pool) < per_level:
            raise GameError(f"falta_pregunta_nivel_{level}")
        out += rnd.sample(pool, per_level)
    return out


def trivia2_start(question_ids: list[str], levels: dict) -> dict:
    slots = [{"qid": q, "level": int(levels.get(q, 0)), "ok": False, "replaced": 0} for q in question_ids]
    return {"v": 2, "slots": slots, "seen": list(question_ids), "queue": list(range(len(slots))), "lap": 1, "current": None,
            "orders": {}, "correct": 0, "notes": [], "last_ok_ms": None, "done_ms": None}


def _open_slots(p: dict) -> list[int]:
    return [i for i, sl in enumerate(p["slots"]) if not sl["ok"] and not sl.get("dead")]


def trivia2_finished(p: dict) -> bool:
    return int((p or {}).get("correct") or 0) >= TRIVIA_GOAL


def trivia2_stuck(p: dict) -> bool:
    """Sin 10/10 y sin preguntas que hacer (banco agotado): espera el cierre."""
    return not trivia2_finished(p) and not _open_slots(p) and not p.get("current")


def _copy2(p: dict) -> dict:
    return {**p, "slots": [dict(x) for x in p["slots"]], "seen": list(p["seen"]), "queue": list(p["queue"]), "orders": dict(p.get("orders") or {}),
            "notes": list(p.get("notes") or [])}


def trivia2_tick(progress: dict, now: datetime) -> dict:
    """Pregunta vencida (10 s + 1) -> queda sin contestar y vuelve en la siguiente
    vuelta con otro orden. Sin pregunta en curso: presenta la siguiente."""
    p = _copy2(progress)
    cur = p.get("current")
    if cur and _ms(datetime.fromisoformat(cur["shown_at"]), now) > QUESTION_MS + GRACE_MS:
        p["current"] = None
    if p.get("current") or trivia2_finished(p):
        return p
    open_slots = _open_slots(p)
    if not open_slots:
        return p
    p["queue"] = [i for i in p["queue"] if i in open_slots]
    if not p["queue"]:
        p["queue"] = open_slots
        p["lap"] = int(p.get("lap") or 1) + 1
    i = p["queue"].pop(0)
    qid = p["slots"][i]["qid"]
    order = _order(p["orders"].get(qid))
    p["orders"][qid] = order
    p["current"] = {"slot": i, "qid": qid, "order": order, "shown_at": now.isoformat()}
    return p


def replacement(bank: list[dict], seen: list[str], level: int) -> Optional[dict]:
    """Una pregunta activa NUEVA para el jugador: del mismo nivel o, si no queda, del nivel mas cercano."""
    seen_set = set(seen)
    fresh = [q for q in bank if q.get("active", True) and str(q["id"]) not in seen_set]
    if not fresh:
        return None
    best = min(abs(int(q["level"]) - level) for q in fresh)
    near = sorted((q for q in fresh if abs(int(q["level"]) - level) == best), key=lambda q: (int(q["level"]), str(q["id"])))
    return secrets.choice(near)


def trivia2_answer(progress: dict, qid: str, choice: int, now: datetime, elapsed_ms: int, bank: list[dict]) -> tuple[dict, bool]:
    """Correcta: suma (meta 10). Fallada: esa pregunta se cambia por una nueva del
    mismo nivel que el jugador no haya visto (o de un nivel cercano, anotado)."""
    cur = progress.get("current")
    if not cur or cur["qid"] != str(qid):
        raise GameError("pregunta_no_vigente")
    if not isinstance(choice, int) or not 0 <= choice <= 2:
        raise GameError("opcion_invalida", 422)
    if _ms(datetime.fromisoformat(cur["shown_at"]), now) > QUESTION_MS + GRACE_MS:
        raise GameError("fuera_de_tiempo")
    p = _copy2(progress)
    slot = p["slots"][cur["slot"]]
    ok = cur["order"][choice] == 0
    p["current"] = None
    if ok:
        slot["ok"] = True
        p["correct"] = int(p.get("correct") or 0) + 1
        p["last_ok_ms"] = int(elapsed_ms)
        if trivia2_finished(p):
            p["done_ms"] = int(elapsed_ms)
        return p, True
    new = replacement(bank, p["seen"], int(slot["level"]))
    if new is None:
        slot["dead"] = True
        return p, False
    if int(new["level"]) != int(slot["level"]):
        p["notes"].append({"slot": cur["slot"], "wanted_level": int(slot["level"]), "used_level": int(new["level"]), "qid": str(new["id"])})
    slot["qid"] = str(new["id"])
    slot["replaced"] = int(slot.get("replaced") or 0) + 1
    p["seen"].append(str(new["id"]))
    return p, False


def trivia2_key(player: dict) -> tuple:
    """10/10 primero por menor tiempo; despues mas aciertos y menor tiempo."""
    p = player.get("progress") or {}
    if trivia2_finished(p):
        return (0, int(p.get("done_ms") or 0), 0, str(player.get("joined_at") or ""), str(player.get("id")))
    last = p.get("last_ok_ms")
    return (1, -int(p.get("correct") or 0), int(last) if last is not None else 10**12, str(player.get("joined_at") or ""), str(player.get("id")))


# ---------------------------------------------------------------- 7 diferencias
def diff_key(player: dict) -> tuple:
    """Mas diferencias; si empatan, menor tiempo (tiempo real + castigos)."""
    ms = player.get("score_ms")
    return (-int(player.get("score") or 0), int(ms) if ms is not None else 10**12, str(player.get("joined_at") or ""), str(player.get("id")))


# ---------------------------------------------------------------- cierre
def final_places(kind: str, players: list[dict], rules: int = 1) -> list[dict]:
    """Puestos finales. Memoria y diferencias: todos con al menos 1 acierto.
    Trivia de antes: solo quien termino las 5 (los demas pierden). Trivia de 10:
    primero los 10/10 por tiempo, luego mas aciertos y tiempo; sin puesto = "timeout"."""
    out = []
    visible = [p for p in players if not p.get("hidden")]
    if kind == "memory":
        ranked = sorted([p for p in visible if int((p.get("progress") or {}).get("pairs") or 0) > 0], key=memory_key)
    elif kind == "differences":
        ranked = sorted([p for p in visible if int(p.get("score") or 0) > 0], key=diff_key)
    elif rules >= 2:
        ranked = sorted([p for p in visible if int((p.get("progress") or {}).get("correct") or 0) > 0], key=trivia2_key)
    else:
        ranked = sorted([p for p in visible if p.get("finished_at")], key=trivia_key)
    places = {str(p["id"]): i + 1 for i, p in enumerate(ranked)}
    for p in players:
        pid = str(p["id"])
        if pid in places:
            out.append({"id": pid, "result": "ranked", "place": places[pid]})
        elif kind == "trivia" and rules >= 2:
            out.append({"id": pid, "result": "timeout", "place": None})
        elif kind == "trivia" and not p.get("finished_at"):
            out.append({"id": pid, "result": "lost", "place": None})
        else:
            out.append({"id": pid, "result": "unranked", "place": None})
    return out


def live_ranking(kind: str, players: list[dict], rules: int = 1) -> list[dict]:
    visible = [p for p in players if not p.get("hidden")]
    if kind == "memory":
        key = memory_key
    elif kind == "differences":
        key = diff_key
    elif rules >= 2:
        key = trivia2_key
    else:
        key = lambda p: (-int(p.get("score") or 0), 0 if p.get("finished_at") else 1, int(p.get("score_ms") or 10**12),  # noqa: E731
                         str(p.get("joined_at") or ""), str(p.get("id")))
    out = []
    for i, p in enumerate(sorted(visible, key=key)):
        prog = p.get("progress") or {}
        out.append({"id": str(p["id"]), "name": p["display_name"], "rank": i + 1,
                    "score": int(prog.get("pairs") or 0) if kind == "memory" else int(p.get("score") or 0),
                    "done": bool(p.get("finished_at")), "ms": p.get("score_ms")})
    return out
