"""Juegos en vivo de Fidelizacion (interruptor loyalty_games). Tres puertas:

- Panel (/companies/{id}/...): sesion de Admin V2 o de un usuario de la empresa.
  Dueno/admin: configura, edita el banco de preguntas, ve el historial y valida.
  Barman: lanza los juegos (girar, abrir registro, iniciar, cerrar, quitar un
  nombre) y valida al ganador; NO edita el banco ni la configuracion.
- Pantalla del bar (/screen/{token}/...): token secreto que el admin regenera;
  solo lectura.
- Jugadores (/play/{token}/...): token firmado de la ronda (el QR) y, al
  inscribirse, token firmado del jugador; limite de peticiones por IP y por ronda.
Con el interruptor apagado (o token invalido) responde 403/404 y no muestra nada.
"""
from __future__ import annotations

import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.services import loyalty_games as svc
from app.services.loyalty_games_engine import GameError

router = APIRouter()
OFF = "Juegos en vivo no está activo para esta empresa."


def _err(exc: GameError) -> HTTPException:
    return HTTPException(status_code=exc.status, detail=exc.code)


# ---------------------------------------------------------------- limite de peticiones (un solo worker)
class RateLimit:
    def __init__(self, limit: int, window: float):
        self.limit, self.window = limit, window
        self.hits: dict[str, deque] = defaultdict(deque)

    def allow(self, key: str, now: Optional[float] = None) -> bool:
        now = time.monotonic() if now is None else now
        q = self.hits[key]
        while q and now - q[0] > self.window:
            q.popleft()
        if len(q) >= self.limit:
            return False
        q.append(now)
        if len(self.hits) > 20000:  # nunca crece sin limite
            for k in [k for k, v in list(self.hits.items()) if not v][:10000]:
                self.hits.pop(k, None)
        return True


# Todo el bar suele salir por la misma IP del wifi: el limite por IP es amplio;
# el de la ronda frena abusos sobre una ronda. Inscribirse tiene su propio limite.
PER_IP = RateLimit(900, 10.0)
PER_ROUND = RateLimit(4000, 10.0)
JOIN_PER_IP = RateLimit(60, 60.0)


def _ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for") or ""
    return (forwarded.split(",")[0].strip() or (request.client.host if request.client else "") or "?")[:64]


def _limit(request: Request, round_key: str, join: bool = False) -> None:
    ip = _ip(request)
    if not PER_IP.allow(ip) or not PER_ROUND.allow(round_key) or (join and not JOIN_PER_IP.allow(ip)):
        raise HTTPException(status_code=429, detail="demasiadas_peticiones")


# ---------------------------------------------------------------- marca de la empresa (cache corto)
_BRAND: dict[str, tuple[float, dict]] = {}


async def brand(db: AsyncSession, company_id: Any) -> dict:
    """Nombre, logo y colores del panel inicial (misma regla que panel_logo), idioma y zona."""
    key = str(company_id)
    hit = _BRAND.get(key)
    if hit and time.monotonic() - hit[0] < 60:
        return hit[1]
    from sqlalchemy import text

    from app.services import brand_store, brand_theme, company_locale, panel_logo

    name = (await db.execute(text("SELECT name FROM companies WHERE id::text = :c"), {"c": key})).scalar() or ""
    logo = (await panel_logo.panel_logo(db, company_id))["url"]
    primary, secondary = "#7c3aed", "#f59e0b"
    try:
        tokens = await brand_store.published_tokens(db, key)
        if tokens:
            values = brand_theme.portal_values(tokens)
        else:
            from app.api.v1.endpoints.companies import _get_company_or_404, _read_company_branding

            values = _read_company_branding(await _get_company_or_404(db, company_id))
        primary = values.get("primary_color") or primary
        secondary = values.get("secondary_color") or secondary
    except Exception:
        await db.rollback()
    loc = await company_locale.get_company_locale(db, company_id)
    out = {"name": name, "logo_url": logo, "primary": primary, "secondary": secondary, "language": loc.get("language") or "es", "timezone": loc["timezone"]}
    _BRAND[key] = (time.monotonic(), out)
    return out


# ---------------------------------------------------------------- panel
async def actor(company_id: UUID, request: Request, authorization: Optional[str] = Header(default=None),
                db: AsyncSession = Depends(get_db)) -> dict:
    from app.web.admin_v2_routes import _active_session

    if await _active_session(request, db):
        who = {"role": "admin", "name": "Admin V2"}
    else:
        from app.api.deps import require_company_user_for_tenant

        user = await require_company_user_for_tenant(db, authorization, company_id)
        who = {"role": await effective_role(db, company_id, user), "name": str(getattr(user, "email", "") or "usuario")}
    if not await svc.is_on(db, company_id):
        raise HTTPException(status_code=404, detail=OFF)
    if who["role"] not in ("admin", "barman"):
        raise HTTPException(status_code=403, detail="Juegos en vivo: tu rol no puede abrir este panel.")
    return who


async def effective_role(db: AsyncSession, company_id: UUID, user: Any) -> str:
    role = str(getattr(user, "role", "") or "").strip().lower()
    if role in svc.ADMIN_ROLES:
        return "admin"
    if role in svc.BARMAN_ROLES:
        return "barman"
    settings = getattr(user, "settings_json", None)
    mini = (settings or {}).get("mini_panel") if isinstance(settings, dict) else None
    employee_id = str((mini or {}).get("employee_id") or "").strip() if isinstance(mini, dict) else ""
    if employee_id:
        from sqlalchemy import text

        emp_role = (await db.execute(text("""SELECT lower(COALESCE(role, '')) FROM employees
            WHERE company_id::text = :c AND id::text = :e AND lower(COALESCE(status, 'active')) = 'active'"""), {"c": str(company_id), "e": employee_id})).scalar()
        if emp_role in svc.BARMAN_ROLES:
            return "barman"
    return "other"


def _admin(who: dict) -> None:
    if who["role"] != "admin":
        raise HTTPException(status_code=403, detail="Juegos en vivo: solo el dueño o el administrador cambian esto.")


def _base(request: Request) -> str:
    return str(request.base_url).rstrip("/")


def _live_extra(request: Request, live: dict) -> dict:
    if live.get("round"):
        live["round"]["join_url"] = f"{_base(request)}/juegos/jugar?r={live['round']['token']}"
    return live


@router.get("/companies/{company_id}/context")
async def context(company_id: UUID, request: Request, who: dict = Depends(actor), db: AsyncSession = Depends(get_db)) -> dict:
    await svc.ensure_bank(db, company_id)
    out = {"role": who["role"], "can": {"configure": who["role"] == "admin", "launch": True, "validate": True},
           "settings": await svc.settings(db, company_id), "brand": await brand(db, company_id),
           "live": _live_extra(request, await svc.live_state(db, company_id))}
    if who["role"] == "admin":
        out["screen_url"] = f"{_base(request)}/juegos/pantalla?t={await svc.screen_token(db, company_id)}"
    return out


@router.get("/companies/{company_id}/live")
async def live(company_id: UUID, request: Request, who: dict = Depends(actor), db: AsyncSession = Depends(get_db)) -> dict:
    state = _live_extra(request, await svc.live_state(db, company_id))
    if state.get("round"):
        plist = await svc.players(db, company_id, state["round"]["id"])
        state["round"]["all_players"] = [{"id": p["id"], "name": p["display_name"], "hidden": p["hidden"], "result": p["result"], "place": p["place"],
                                          "validated": bool(p["validated_at"])} for p in plist]
    return state


@router.put("/companies/{company_id}/settings")
async def save_settings(company_id: UUID, body: dict = Body(...), who: dict = Depends(actor), db: AsyncSession = Depends(get_db)) -> dict:
    _admin(who)
    try:
        return await svc.save_settings(db, company_id, body, who["name"])
    except GameError as exc:
        raise _err(exc) from None


@router.post("/companies/{company_id}/screen/regenerate")
async def regenerate_screen(company_id: UUID, request: Request, who: dict = Depends(actor), db: AsyncSession = Depends(get_db)) -> dict:
    """Cambia el enlace de la pantalla del bar: el anterior deja de servir."""
    _admin(who)
    return {"screen_url": f"{_base(request)}/juegos/pantalla?t={await svc.screen_token(db, company_id, regenerate=True)}"}


@router.get("/companies/{company_id}/questions")
async def list_questions(company_id: UUID, who: dict = Depends(actor), db: AsyncSession = Depends(get_db)) -> dict:
    _admin(who)
    await svc.ensure_bank(db, company_id)
    return {"items": await svc.questions(db, company_id)}


@router.post("/companies/{company_id}/questions")
async def create_question(company_id: UUID, body: dict = Body(...), who: dict = Depends(actor), db: AsyncSession = Depends(get_db)) -> dict:
    _admin(who)
    try:
        return await svc.save_question(db, company_id, body)
    except GameError as exc:
        raise _err(exc) from None


@router.put("/companies/{company_id}/questions/{question_id}")
async def update_question(company_id: UUID, question_id: UUID, body: dict = Body(...), who: dict = Depends(actor), db: AsyncSession = Depends(get_db)) -> dict:
    _admin(who)
    try:
        return await svc.save_question(db, company_id, body, str(question_id))
    except GameError as exc:
        raise _err(exc) from None


@router.get("/companies/{company_id}/history")
async def history(company_id: UUID, who: dict = Depends(actor), db: AsyncSession = Depends(get_db)) -> dict:
    _admin(who)
    from sqlalchemy import text

    rows = (await db.execute(text("""SELECT id::text AS id, kind, status, prize, game_day, created_by, created_at, started_at, closed_at, results
        FROM loyalty_game_rounds WHERE company_id::text = :c ORDER BY created_at DESC LIMIT 60"""), {"c": str(company_id)})).mappings().all()
    counts = {str(r[0]): (int(r[1]), int(r[2])) for r in (await db.execute(text("""SELECT round_id, count(*), count(validated_at)
        FROM loyalty_game_players WHERE company_id::text = :c GROUP BY round_id"""), {"c": str(company_id)})).all()}
    from app.api.v1.endpoints.reports import serialize

    rounds = [{**dict(r), "players": counts.get(r["id"], (0, 0))[0], "validated": counts.get(r["id"], (0, 0))[1]} for r in rows]
    return {"rounds": serialize(rounds), "draws": await svc.draws(db, company_id)}


@router.post("/companies/{company_id}/roulette/spin")
async def spin(company_id: UUID, body: dict = Body(...), who: dict = Depends(actor), db: AsyncSession = Depends(get_db)) -> dict:
    conf = await svc.settings(db, company_id)
    try:
        index = int(body.get("range_index", 0))
        rng = conf["roulette_ranges"][index]
    except (TypeError, ValueError, IndexError):
        raise HTTPException(status_code=422, detail="rango_invalido") from None
    prize = str(body.get("prize") if body.get("prize") is not None else (rng.get("prize") or conf["prizes"].get("roulette") or ""))
    try:
        return await svc.spin(db, company_id, int(rng["min"]), int(rng["max"]), prize, who["name"])
    except GameError as exc:
        raise _err(exc) from None


@router.post("/companies/{company_id}/rounds")
async def open_round(company_id: UUID, request: Request, body: dict = Body(...), who: dict = Depends(actor), db: AsyncSession = Depends(get_db)) -> dict:
    try:
        await svc.open_round(db, company_id, str(body.get("kind") or ""), body.get("prize"), who["name"])
    except GameError as exc:
        raise _err(exc) from None
    return await live(company_id, request, who, db)


@router.post("/companies/{company_id}/rounds/{round_id}/start")
async def start_round(company_id: UUID, round_id: UUID, request: Request, who: dict = Depends(actor), db: AsyncSession = Depends(get_db)) -> dict:
    try:
        await svc.start_round(db, company_id, round_id)
    except GameError as exc:
        raise _err(exc) from None
    return await live(company_id, request, who, db)


@router.post("/companies/{company_id}/rounds/{round_id}/close")
async def close_round(company_id: UUID, round_id: UUID, request: Request, who: dict = Depends(actor), db: AsyncSession = Depends(get_db)) -> dict:
    try:
        await svc.close_round(db, company_id, round_id)
    except GameError as exc:
        raise _err(exc) from None
    return await live(company_id, request, who, db)


@router.post("/companies/{company_id}/rounds/{round_id}/players/{player_id}/hide")
async def hide_player(company_id: UUID, round_id: UUID, player_id: UUID, request: Request, who: dict = Depends(actor),
                      db: AsyncSession = Depends(get_db)) -> dict:
    try:
        await svc.hide_player(db, company_id, round_id, player_id)
    except GameError as exc:
        raise _err(exc) from None
    return await live(company_id, request, who, db)


@router.post("/companies/{company_id}/rounds/{round_id}/validate")
async def validate_winner(company_id: UUID, round_id: UUID, body: dict = Body(...), who: dict = Depends(actor), db: AsyncSession = Depends(get_db)) -> dict:
    """Compara el HMAC del documento digitado con el del puesto. Nunca devuelve el documento."""
    try:
        return await svc.validate_winner(db, company_id, round_id, int(body.get("place") or 0), str(body.get("document") or ""), who["name"])
    except GameError as exc:
        raise _err(exc) from None
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail="datos_invalidos") from None


# ---------------------------------------------------------------- pantalla del bar (solo lectura)
async def _screen_company(db: AsyncSession, token: str) -> str:
    cid = await svc.company_by_screen_token(db, token)
    if not cid:
        raise HTTPException(status_code=403, detail="pantalla_no_autorizada")
    return cid


@router.get("/screen/{token}/state")
async def screen_state(token: str, request: Request, db: AsyncSession = Depends(get_db)) -> dict:
    cid = await _screen_company(db, token)
    _limit(request, f"screen:{cid}")
    state = _live_extra(request, await svc.live_state(db, cid))
    if state.get("round"):
        state["round"].pop("token", None)
    return {**state, "brand": await brand(db, cid), "texts": (await svc.settings(db, cid))["texts"]}


@router.get("/screen/{token}/qr.svg")
async def screen_qr(token: str, request: Request, r: str = "", db: AsyncSession = Depends(get_db)) -> Response:
    import io

    import segno

    cid = await _screen_company(db, token)
    row = await svc.round_row(db, cid, r)
    if not row or row["status"] != "registration":
        raise HTTPException(status_code=404, detail="sin_registro_abierto")
    buf = io.BytesIO()
    segno.make(f"{_base(request)}/juegos/jugar?r={svc.round_token(row['id'])}", error="m").save(buf, kind="svg", scale=10, border=2, dark="#0b0a14", light="#ffffff")
    return Response(buf.getvalue(), media_type="image/svg+xml", headers={"Cache-Control": "no-store"})


# ---------------------------------------------------------------- jugadores (pagina publica del QR)
async def _round(db: AsyncSession, token: str, request: Request, join: bool = False) -> dict:
    r = await svc.round_by_token(db, token)
    if not r:
        raise HTTPException(status_code=404, detail="ronda_no_encontrada")
    _limit(request, f"round:{r['id']}", join)
    return await svc.refresh(db, r["company_id"], r) or r


@router.get("/play/{token}")
async def play_info(token: str, request: Request, db: AsyncSession = Depends(get_db)) -> dict:
    r = await _round(db, token, request)
    conf = await svc.settings(db, r["company_id"])
    return {"kind": r["kind"], "status": r["status"], "prize": r["prize"], "duration_seconds": int(r["duration_seconds"]),
            "ends_at": r["ends_at"].isoformat() if r["ends_at"] else None, "now": datetime.now(timezone.utc).isoformat(),
            "brand": await brand(db, r["company_id"]), "texts": conf["texts"]}


@router.post("/play/{token}/join")
async def play_join(token: str, request: Request, body: dict = Body(...), db: AsyncSession = Depends(get_db)) -> dict:
    r = await _round(db, token, request, join=True)
    try:
        return await svc.join(db, r, str(body.get("name") or ""), str(body.get("document") or ""), body.get("consent") is True)
    except GameError as exc:
        raise _err(exc) from None


@router.get("/play/{token}/me")
async def play_me(token: str, request: Request, x_player_token: str = Header(default=""), db: AsyncSession = Depends(get_db)) -> dict:
    r = await _round(db, token, request)
    try:
        return await svc.me(db, r, x_player_token)
    except GameError as exc:
        raise _err(exc) from None


@router.post("/play/{token}/flip")
async def play_flip(token: str, request: Request, body: dict = Body(...), x_player_token: str = Header(default=""), db: AsyncSession = Depends(get_db)) -> dict:
    r = await _round(db, token, request)
    try:
        return await svc.flip(db, r, x_player_token, body.get("index"))
    except GameError as exc:
        raise _err(exc) from None


@router.post("/play/{token}/question")
async def play_question(token: str, request: Request, x_player_token: str = Header(default=""), db: AsyncSession = Depends(get_db)) -> dict:
    r = await _round(db, token, request)
    try:
        return await svc.trivia_state(db, r, x_player_token)
    except GameError as exc:
        raise _err(exc) from None


@router.post("/play/{token}/answer")
async def play_answer(token: str, request: Request, body: dict = Body(...), x_player_token: str = Header(default=""), db: AsyncSession = Depends(get_db)) -> dict:
    r = await _round(db, token, request)
    try:
        return await svc.answer(db, r, x_player_token, str(body.get("question_id") or ""), body.get("choice"))
    except GameError as exc:
        raise _err(exc) from None
