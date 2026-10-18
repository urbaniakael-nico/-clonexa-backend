"""Terminar ahora / Cancelar y reiniciar (Juegos en vivo y Retos para las mesas) y
nombre al entrar a la mesa por QR (interruptor qr_welcome_name), contra Postgres REAL.

- Terminar ahora: memoria, trivia y 7 diferencias cierran con el ranking actual y
  podio; consumo cierra con los pedidos hasta ese momento; la polla cierra los
  pronosticos y pasa a "Poner marcador final"; el concurso aplica su regla.
- Cancelar y reiniciar: sin ganador, libera el espacio, la pantalla del bar queda
  en espera, el jugador ve la ronda cancelada y queda en el historial (hora y quien).
- Permisos: barman si, operario no.
- Bienvenida: el nombre se pide al activar la mesa y no se vuelve a pedir; "Ahora
  no" deja el nombre por defecto; el nombre llega a barra, cocina y Reportes (con
  busqueda); la frase editable se guarda; sin el interruptor el QR queda igual.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

pgserver = pytest.importorskip("pgserver")

from sqlalchemy import text  # noqa: E402

from app.api.v1.endpoints import hospitality as hsp  # noqa: E402
from app.api.v1.endpoints import loyalty_games as games_api  # noqa: E402
from app.api.v1.endpoints import loyalty_retos as retos_api  # noqa: E402
from app.api.v1.endpoints import waiter_ordering  # noqa: E402
from app.services import loyalty_games as games  # noqa: E402
from app.services import loyalty_retos as svc  # noqa: E402
from app.services.loyalty_retos import RetoError  # noqa: E402
from tests.test_loyalty_retos_pg import (  # noqa: E402,F401
    CODE, _company, _iso, _order, _past, _polla, _predict, _session, _tables, _vote, env, pg_url,
)

BARMAN = {"role": "barman", "name": "barman@bar"}


def _req(ip="1.1.1.1"):
    return SimpleNamespace(base_url="https://bar.test/", headers={"x-forwarded-for": ip}, client=SimpleNamespace(host=ip))


async def _play(db, cid, kind, scores):
    """Abre, inscribe un jugador por puntaje y arranca. Devuelve la ronda y los jugadores."""
    r = await games.open_round(db, cid, kind, "Botella", "barman@bar")
    token = games.round_token(r["id"])
    pids = []
    for i, _ in enumerate(scores):
        p = await games_api.play_join(token, _req(f"9.9.9.{i}"), {"name": f"Jugador {i}", "document": f"5555000{i}", "consent": True}, db)
        pids.append(games.eng.unsign("player", p["player_token"]))
    await games.start_round(db, cid, r["id"])
    for pid, score in zip(pids, scores):
        progress = {"memory": {"pairs": score, "pair_ms": [1000 * (k + 1) for k in range(score)]},
                    "trivia": {"v": 2, "correct": score, "done_ms": None, "last_ok_ms": 5000 * score},
                    "differences": {"found": [], "found_ms": [], "misses": 0, "penalty_ms": 0}}[kind]
        await db.execute(text("UPDATE loyalty_game_players SET score = :s, score_ms = :ms, progress = CAST(:p AS jsonb) WHERE id::text = :i"),
                         {"s": score, "ms": 1000 * score, "p": json.dumps(progress), "i": pid})
    await db.commit()
    return r, token, pids


# ---------------------------------------------------------------- Juegos en vivo
@pytest.mark.asyncio
async def test_end_now_closes_each_game_with_the_current_ranking(pg_url):
    engine, maker = await _session(pg_url)
    async with maker() as db:
        cid = await _company(db)
        u = uuid.UUID(cid)
        for kind in ("memory", "trivia", "differences"):
            r, token, pids = await _play(db, cid, kind, [2, 5])
            live = await games_api.close_round(u, uuid.UUID(str(r["id"])), _req(), BARMAN, db)  # "Terminar ahora"
            assert live["round"]["status"] == "closed", kind
            podium = live["round"]["podium"]
            assert podium[0]["place"] == 1 and podium[0]["name"] == "Jugador 1", f"{kind}: gana el de mejor resultado"
            me = await games.me(db, await games.round_row(db, cid, r["id"]), games.player_token(pids[1]))
            assert me["result"]["place"] == 1
    await engine.dispose()


@pytest.mark.asyncio
async def test_cancel_and_reset_a_game_round(pg_url, monkeypatch):
    from app.api import deps
    from app.web import admin_v2_routes

    engine, maker = await _session(pg_url)
    async with maker() as db:
        cid = await _company(db)
        u = uuid.UUID(cid)
        r, token, pids = await _play(db, cid, "memory", [3, 1])
        live = await games_api.cancel_round(u, uuid.UUID(str(r["id"])), _req(), BARMAN, db)
        assert live["round"] is None and live["active"] is False, "la pantalla del bar vuelve a en espera"
        row = await games.round_row(db, cid, r["id"])
        assert row["status"] == "cancelled" and row["cancelled_by"] == "barman@bar" and row["cancelled_at"]
        places = (await db.execute(text("SELECT count(*) FROM loyalty_game_players WHERE round_id::text = :r AND place IS NOT NULL"), {"r": str(r["id"])})).scalar()
        assert places == 0, "sin ganador"
        me = await games.me(db, row, games.player_token(pids[0]))
        assert me["status"] == "cancelled", "el jugador ve que se canceló"
        assert (await games_api.play_info(token, _req(), db))["status"] == "cancelled"
        screen = (await games.live_state(db, cid))
        assert screen["focus"] in ("idle", "roulette") and screen["round"] is None
        again = await games.open_round(db, cid, "trivia", "", "barman@bar")  # libera el espacio
        assert again["status"] == "registration"
        with pytest.raises(games.GameError):
            await games.cancel_round(db, cid, r["id"], "otro")  # ya estaba cancelada
        hist = await games_api.history(u, {"role": "admin", "name": "dueno"}, db)
        cancelled = next(x for x in hist["rounds"] if x["id"] == str(r["id"]))
        assert cancelled["status"] == "cancelled" and cancelled["cancelled_by"] == "barman@bar"
        # Permisos: barman si (arriba); operario de otra area no.
        monkeypatch.setattr(admin_v2_routes, "_active_session", AsyncMock(return_value=False))
        monkeypatch.setattr(deps, "require_company_user_for_tenant", AsyncMock(return_value=SimpleNamespace(role="operario", email="op@x", settings_json={})))
        for guard in (games_api.actor, retos_api.actor):
            with pytest.raises(HTTPException) as exc:
                await guard(u, _req(), "Bearer x", db)
            assert exc.value.status_code == 403
    await engine.dispose()


# ---------------------------------------------------------------- Retos
@pytest.mark.asyncio
async def test_end_now_for_each_reto(pg_url):
    engine, maker = await _session(pg_url)
    async with maker() as db:
        cid = await _company(db)
        await _tables(db, cid, "Mesa 1", "Mesa 2", "Mesa 3")
        now = datetime.now(timezone.utc)
        # Consumo: gana con los pedidos hasta ese momento (los de despues no cuentan).
        c = await svc.create(db, cid, {"type": "consumption", "prize": "Ron", "registration_ends_at": _iso(now + timedelta(minutes=5)),
                                       "starts_at": _iso(now + timedelta(minutes=5)), "ends_at": _iso(now + timedelta(hours=3))}, "dueno")
        for t in ("Mesa 1", "Mesa 2"):
            await hsp.join_loyalty_campaign(uuid.UUID(cid), uuid.UUID(c["id"]), hsp.HospitalityLoyaltyParticipantIn(table=t, team_name=t), db)
        await db.execute(text("UPDATE hospitality_loyalty_campaigns SET starts_at = now() - interval '1 hour', registration_ends_at = now() - interval '1 hour' WHERE id::text = :i"), {"i": c["id"]})
        await db.commit()
        await _order(db, cid, "Mesa 1", 30000, now - timedelta(minutes=10))
        await _order(db, cid, "Mesa 2", 20000, now - timedelta(minutes=5))
        await _order(db, cid, "Mesa 2", 90000, now + timedelta(minutes=30))  # despues de terminar: no cuenta
        ended = await svc.close_now(db, cid, c["id"], "barman@bar")
        assert ended["status"] == "closed" and ended["winner"]["table_number"] == "Mesa 1"
        # Polla: cierra los pronosticos y pasa a "Poner marcador final".
        p = await svc.create(db, cid, _polla(now), "dueno")
        await _predict(db, cid, p["id"], "Mesa 1", 1, 0)
        assert "close_now" in p["actions"]
        closed = await svc.close_now(db, cid, p["id"], "barman@bar")
        assert closed["status"] == "active" and closed["stage"] == "playing" and closed["actions"] == ["set_score", "cancel"]
        with pytest.raises(HTTPException) as exc:
            await _predict(db, cid, p["id"], "Mesa 2", 2, 0)
        assert exc.value.detail == "pronosticos_cerrados"
        with pytest.raises(RetoError):
            await svc.close_now(db, cid, p["id"], "barman@bar")
        assert (await svc.set_score(db, cid, p["id"], 1, 0, "dueno"))["winner"]["table_number"] == "Mesa 1"
        # Concurso: aplica su regla (mas votos).
        v = await svc.create(db, cid, {"type": "vote_poll", "prize": "x", "vote_mode": "participants", "description": "¿?", "options": ["Ana", "Beto"],
                                       "ends_at": _iso(now + timedelta(hours=1))}, "dueno")
        await _vote(db, cid, v["id"], "Mesa 1", "option_2")
        assert (await svc.close_now(db, cid, v["id"], "dueno"))["winner"]["label"] == "Beto"
    await engine.dispose()


@pytest.mark.asyncio
async def test_cancel_and_reset_each_reto(pg_url):
    engine, maker = await _session(pg_url)
    async with maker() as db:
        cid = await _company(db, games_on=True)
        u = uuid.UUID(cid)
        await _tables(db, cid, "Mesa 1", "Mesa 2")
        now = datetime.now(timezone.utc)
        specs = {
            "consumption": {"type": "consumption", "prize": "Ron", "registration_ends_at": _iso(now + timedelta(minutes=5)),
                            "starts_at": _iso(now + timedelta(minutes=5)), "ends_at": _iso(now + timedelta(hours=3))},
            "score_pool": _polla(now),
            "vote_poll": {"type": "vote_poll", "prize": "x", "vote_mode": "yes_no", "description": "¿?", "secret_answer": "yes", "ends_at": _iso(now + timedelta(hours=1))},
        }
        for t, spec in specs.items():
            r = await svc.create(db, cid, spec, "dueno")
            assert "cancel" in r["actions"]
            out = await retos_api.cancel(u, uuid.UUID(r["id"]), BARMAN, db)
            assert out["status"] == "cancelled" and out["winner"] is None and out["prize_status"] == "" and out["closed_by"] == "barman@bar"
            qr = await hsp.get_active_loyalty_campaign(u, "Mesa 1", db)
            key = {"consumption": "campaign", "score_pool": "score_campaign", "vote_poll": "vote_campaign"}[t]
            assert qr[key] is None, f"{t}: el QR deja de mostrarlo"
            again = await svc.create(db, cid, spec, "dueno")  # libera el espacio
            assert again["status"] == "active"
            with pytest.raises(RetoError):
                await svc.cancel(db, cid, r["id"], "otro")
            await svc.cancel(db, cid, again["id"], "dueno")
        hist = await svc.history(db, cid)
        assert [h["status"] for h in hist[:6]] == ["cancelled"] * 6 and hist[0]["closed_by"] and hist[0]["closed_at"]
        # Polla empatada con desempate abierto: cancelar tambien cancela la ronda.
        p = await svc.create(db, cid, _polla(now), "dueno")
        for t in ("Mesa 1", "Mesa 2"):
            await _predict(db, cid, p["id"], t, 1, 1)
        await _past(db, p["id"], predictions_close_at=1)
        await svc.set_score(db, cid, p["id"], 1, 1, "dueno")
        tb = (await svc.open_tiebreak(db, cid, p["id"], "memory", "dueno"))["tiebreak"]
        await svc.cancel(db, cid, p["id"], "dueno")
        assert (await games.round_row(db, cid, tb["round_id"]))["status"] == "cancelled"
        assert (await svc.state(db, cid, "admin"))["active"]["score_pool"] is None
    await engine.dispose()


# ---------------------------------------------------------------- Bienvenida con nombre
async def _qr_company(db, welcome: bool) -> str:
    cid = await _company(db)
    await db.execute(text("ALTER TABLE company_modules ADD COLUMN IF NOT EXISTS updated_at timestamptz NOT NULL DEFAULT now()"))
    import importlib

    guests = importlib.import_module("migrations.versions.021n_qr_table_guests")  # invitados "Persona N" (carta de bar)
    guests.op = SimpleNamespace(execute=lambda q: statements.append(str(q)))
    statements: list[str] = []
    guests.upgrade()
    for stmt in statements:
        await db.execute(text(stmt))
    for code, settings in (("qr", {"qr_bar_menu": True}), ("hospitality", {"qr_welcome_name": welcome})):
        await db.execute(text("INSERT INTO modules (code, name, category) VALUES (:c, :c, 'x') ON CONFLICT (code) DO NOTHING"), {"c": code})
        await db.execute(text("""INSERT INTO company_modules (company_id, module_id, enabled, settings)
            SELECT CAST(:i AS uuid), id, true, CAST(:s AS jsonb) FROM modules WHERE code = :c"""), {"i": cid, "c": code, "s": json.dumps(settings)})
    await db.commit()
    await _tables(db, cid, "Mesa 4")
    return cid


def _account(name="", account="qr_account_a"):
    return hsp.HospitalityTableAccessVerifyIn(table="Mesa 4", access_code=CODE, account_id=account, customer=name)


async def _qr_order(db, cid, customer="", account="qr_account_a"):
    return await hsp.create_hospitality_order(uuid.UUID(cid), hsp.HospitalityOrderCreateIn(
        table="Mesa 4", customer=customer, account_id=account, source="qr", access_code=CODE,
        items=[hsp.HospitalityOrderItemIn(name="Cerveza", quantity=1, unit_price=9000)]), db, None)


@pytest.mark.asyncio
async def test_welcome_name_off_keeps_the_qr_as_today(pg_url):
    engine, maker = await _session(pg_url)
    async with maker() as db:
        cid = await _qr_company(db, welcome=False)
        u = uuid.UUID(cid)
        access = await hsp.get_hospitality_table_access(u, "Mesa 4", db)
        assert access["ui"] == {"bar_menu": True}, "sin el interruptor, la misma respuesta de siempre"
        await _qr_order(db, cid, "Laura<b>x</b> con un nombre larguisimo de mas de treinta")
        row = (await db.execute(text("SELECT customer_name, metadata FROM hospitality_orders WHERE company_id::text = :c"), {"c": cid})).mappings().first()
        assert "guest_name" not in (row["metadata"] if isinstance(row["metadata"], dict) else json.loads(row["metadata"]))
        assert row["customer_name"].startswith("Laura<b>"), "el nombre se guarda como siempre"
        with pytest.raises(HTTPException) as exc:
            await hsp.get_qr_welcome(u, db, {"admin_v2": True, "role": "admin_v2"})
        assert exc.value.status_code == 404
        out = await hsp._hsp_mark_guest_search(db, u, {"event_search": {"events": []}})
        assert "guest_search" not in out["event_search"]
    await engine.dispose()


@pytest.mark.asyncio
async def test_welcome_name_flow_and_where_the_name_shows(pg_url):
    engine, maker = await _session(pg_url)
    async with maker() as db:
        cid = await _qr_company(db, welcome=True)
        u = uuid.UUID(cid)
        access = await hsp.get_hospitality_table_access(u, "Mesa 4", db)
        ui = access["ui"]
        assert ui["welcome_name"] is True and ui["bar_menu"] is True and ui["name_max"] == 30
        assert ui["welcome_text"] == hsp.QR_WELCOME_DEFAULT and ui["welcome_custom"] is False and "[bar]" in ui["welcome_text"]
        # Al activar la mesa: el nombre (sin HTML, max. 30) queda en la sesion del invitado.
        acc = await hsp.get_hospitality_table_account(u, _account("<i>Laura</i>  María de los Ángeles Restrepo Vélez"), db)
        guest = (await db.execute(text("SELECT name FROM hospitality_table_guests WHERE company_id::text = :c AND account_id = 'qr_account_a'"), {"c": cid})).scalar()
        assert guest == "Laura María de los Ángeles Res" and len(guest) == 30 and "<" not in guest
        assert acc["ok"] is True
        # Al pedir ya no se pide el nombre (el QR manda vacio): sale el de la bienvenida.
        await _qr_order(db, cid, "")
        # "Ahora no": otro celular de la misma mesa queda con el nombre por defecto.
        await hsp.get_hospitality_table_account(u, _account("", "qr_account_b"), db)
        await _qr_order(db, cid, "", "qr_account_b")
        rows = (await db.execute(text("SELECT * FROM hospitality_orders WHERE company_id::text = :c ORDER BY created_at"), {"c": cid})).mappings().all()
        meta = [r["metadata"] if isinstance(r["metadata"], dict) else json.loads(r["metadata"]) for r in rows]
        assert [r["customer_name"] for r in rows] == [guest, "Persona 2"], "cada celular con su nombre; sin nombre, el de siempre"
        assert [m["guest_name"] for m in meta] == [guest, "Persona 2"]
        # 056C: el nombre queda FIJO; cambiarlo desde el QR da 409 (lo corrige el bar: test_qr_guest_name_fixed_pg).
        with pytest.raises(HTTPException) as exc:
            await hsp.get_hospitality_table_account(u, _account("Laura"), db)
        assert exc.value.status_code == 409
        await db.rollback()
        rows = (await db.execute(text("SELECT * FROM hospitality_orders WHERE company_id::text = :c ORDER BY created_at"), {"c": cid})).mappings().all()
        first = rows[0]
        m0 = first["metadata"] if isinstance(first["metadata"], dict) else json.loads(first["metadata"])
        people = first["people"] if isinstance(first["people"], list) else json.loads(first["people"])
        assert first["customer_name"] == guest and m0["guest_name"] == guest and people[0]["name"] == guest, "barra (personas) y cocina"
        # Cocina: "Laura · Mesa 4".
        comanda = waiter_ordering._comanda(hsp._payload(first), set())
        assert comanda["guest_name"] == guest and comanda["table_number"] == "Mesa 4"
        # Reportes: el evento trae los nombres de los invitados y la pantalla busca por nombre.
        event = hsp._hsp_event_payload([hsp._payload(r) for r in rows], event_id="e1", event_type="qr", location="Mesa 4")
        assert event["guest_names"] == [guest, "Persona 2"]
        out = await hsp._hsp_mark_guest_search(db, u, {"event_search": {"events": [event]}})
        assert out["event_search"]["guest_search"] is True
        # Frase editable (solo dueno/admin): se guarda, sin HTML, max. 160; vacia = por defecto.
        owner, worker = {"admin_v2": False, "role": "company_admin"}, {"admin_v2": False, "role": "mesero"}
        saved = await hsp.save_qr_welcome(u, hsp.HospitalityQrWelcomeIn(text="<b>¡Hola!</b> Bienvenido a [bar] 🎸 ¿Tu nombre?"), db, owner)
        assert saved["text"] == "¡Hola! Bienvenido a [bar] 🎸 ¿Tu nombre?"
        assert (await hsp.get_qr_welcome(u, db, worker))["text"] == saved["text"]
        ui = (await hsp.get_hospitality_table_access(u, "Mesa 4", db))["ui"]
        assert ui["welcome_text"] == saved["text"] and ui["welcome_custom"] is True
        with pytest.raises(HTTPException) as exc:
            await hsp.save_qr_welcome(u, hsp.HospitalityQrWelcomeIn(text="x" * 161), db, owner)
        assert exc.value.status_code == 422
        with pytest.raises(HTTPException) as exc:
            await hsp._qr_welcome_writer(worker)
        assert exc.value.status_code == 403, "solo el dueno o el admin guarda"
        await hsp.save_qr_welcome(u, hsp.HospitalityQrWelcomeIn(text=""), db, owner)
        assert (await hsp.get_hospitality_table_access(u, "Mesa 4", db))["ui"]["welcome_text"] == hsp.QR_WELCOME_DEFAULT
        settings = (await db.execute(text("""SELECT cm.settings FROM company_modules cm JOIN modules m ON m.id = cm.module_id
            WHERE cm.company_id::text = :c AND m.code = 'hospitality'"""), {"c": cid})).scalar()
        settings = settings if isinstance(settings, dict) else json.loads(settings)
        assert settings == {"qr_welcome_name": True}, "guardar no toca las demas claves"
    await engine.dispose()


def test_routes_need_a_session_and_switch_is_registered():
    for r in hsp.router.routes:
        if r.path.endswith("/qr-welcome"):
            calls = [d.call for d in r.dependant.dependencies]
            assert hsp._qr_welcome_reader in calls or hsp._qr_welcome_writer in calls, r.path
    paths = {r.path for r in games_api.router.routes} | {r.path for r in retos_api.router.routes}
    assert "/companies/{company_id}/rounds/{round_id}/cancel" in paths and "/companies/{company_id}/retos/{reto_id}/cancel" in paths
    from app.services import switch_registry

    sw = next(s for s in switch_registry.registry()["switches"] if s["key"] == "qr_welcome_name")
    assert sw["module"] == "hospitality" and sw["group"] == "QR" and hsp.QR_WELCOME_SETTING == "qr_welcome_name"
    import importlib

    module = importlib.import_module("migrations.versions.024n_loyalty_cancel")
    assert len(module.revision) <= 32 and module.down_revision == "024m_loyalty_retos_v2"
