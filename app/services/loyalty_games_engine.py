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

ICONS = ["🍸", "🎸", "🎤", "🍺", "🎷", "🥃", "🎹", "🎧", "🍹", "🥁", "🎺", "🍷"]
PAIRS = 5
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
def board(seed: int) -> list[str]:
    rnd = random.Random(int(seed))
    icons = rnd.sample(ICONS, PAIRS)
    cards = icons * 2
    rnd.shuffle(cards)
    return cards


def memory_start() -> dict:
    return {"matched": [], "open": None, "pairs": 0, "pair_ms": [], "flips": 0}


def memory_flip(progress: dict, seed: int, index: int, elapsed_ms: int) -> tuple[dict, dict]:
    """Voltea `index`. Devuelve (progreso nuevo, respuesta con SOLO las caras volteadas)."""
    cards = board(seed)
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


def memory_public(progress: dict, seed: int) -> dict:
    """Lo que ve el jugador: solo las caras de las parejas encontradas y la carta abierta."""
    cards = board(seed)
    p = {**memory_start(), **(progress or {})}
    faces = {str(i): cards[i] for i in p["matched"]}
    if p["open"] is not None:
        faces[str(p["open"])] = cards[p["open"]]
    return {"size": len(cards), "faces": faces, "matched": list(p["matched"]), "open": p["open"], "pairs": p["pairs"], "total_pairs": PAIRS}


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


# ---------------------------------------------------------------- cierre
def final_places(kind: str, players: list[dict]) -> list[dict]:
    """Puestos finales. Memoria: todos con al menos 1 pareja. Trivia: solo quien
    termino las 5; quien tenga pendientes pierde (sin ranking ni podio)."""
    out = []
    visible = [p for p in players if not p.get("hidden")]
    if kind == "memory":
        ranked = sorted([p for p in visible if int((p.get("progress") or {}).get("pairs") or 0) > 0], key=memory_key)
    else:
        ranked = sorted([p for p in visible if p.get("finished_at")], key=trivia_key)
    places = {str(p["id"]): i + 1 for i, p in enumerate(ranked)}
    for p in players:
        pid = str(p["id"])
        if pid in places:
            out.append({"id": pid, "result": "ranked", "place": places[pid]})
        elif kind == "trivia" and not p.get("finished_at"):
            out.append({"id": pid, "result": "lost", "place": None})
        else:
            out.append({"id": pid, "result": "unranked", "place": None})
    return out


def live_ranking(kind: str, players: list[dict]) -> list[dict]:
    visible = [p for p in players if not p.get("hidden")]
    key = memory_key if kind == "memory" else (lambda p: (-int(p.get("score") or 0), 0 if p.get("finished_at") else 1, int(p.get("score_ms") or 10**12),
                                                          str(p.get("joined_at") or ""), str(p.get("id"))))
    out = []
    for i, p in enumerate(sorted(visible, key=key)):
        prog = p.get("progress") or {}
        out.append({"id": str(p["id"]), "name": p["display_name"], "rank": i + 1,
                    "score": int(prog.get("pairs") or 0) if kind == "memory" else int(p.get("score") or 0),
                    "done": bool(p.get("finished_at")), "ms": p.get("score_ms")})
    return out
