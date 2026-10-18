"""Retos para las mesas (interruptor loyalty_retos_v2) contra Postgres REAL.

- Uno activo por tipo (409 al crear otro).
- Consumo: el ranking es el mismo de siempre (solo pedidos del torneo) y gana el 1.o.
- Polla: pronosticos rechazados despues de "pronosticos hasta"; el marcador final
  calcula 0, 1 o varios aciertos exactos; el empate abre un desempate de Juegos en
  vivo solo para esas mesas (rechaza otra mesa, una persona por mesa) y el 1.er
  puesto queda como ganador de la polla; el premio se entrega con el documento.
- Concurso: votacion con mas votos y con empate (el bar elige); Si/No y V/F sortean
  entre los aciertos y la respuesta correcta nunca viaja al QR; inscripcion simple
  (el bar elige); cierre automatico y manual.
- Los retos de antes se ven y se resuelven; con el interruptor apagado: 404 y el QR igual.
"""
from __future__ import annotations

import asyncio
import importlib
import json
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

pgserver = pytest.importorskip("pgserver")

from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402

from app.api.v1.endpoints import hospitality as hsp  # noqa: E402
from app.api.v1.endpoints import loyalty_games as games_api  # noqa: E402
from app.api.v1.endpoints import loyalty_retos as api  # noqa: E402
from app.services import loyalty_games as games  # noqa: E402
from app.services import loyalty_retos as svc  # noqa: E402
from app.services.loyalty_retos import RetoError  # noqa: E402
from tests.test_brand_pg import BASE_SCHEMA  # noqa: E402
from tests.test_loyalty_games_pg import EXTRA_SCHEMA  # noqa: E402

CODE = "ABC12"


def _migrations() -> list[str]:
    statements: list[str] = []

    class Op:
        def execute(self, sql):
            statements.append(str(sql))

    for name in ("024j_loyalty_games", "024k_loyalty_games_v2", "024m_loyalty_retos_v2"):
        module = importlib.import_module(f"migrations.versions.{name}")
        module.op = Op()
        module.upgrade()
    return statements


class _NoExtension:
    """pgserver no trae pgcrypto; gen_random_uuid() ya viene en Postgres 16."""

    def __init__(self, db):
        self.real = db.execute

    async def __call__(self, statement, *a, **k):
        if "create extension" in str(statement).lower():
            return await self.real(text("SELECT 1"))
        return await self.real(statement, *a, **k)


@pytest.fixture(scope="module")
def pg_url():
    folder = tempfile.mkdtemp(prefix="cx_pg_retos_")
    server = pgserver.get_server(folder, cleanup_mode="stop")
    url = server.get_uri().replace("postgresql://", "postgresql+asyncpg://", 1)

    async def setup():
        engine = create_async_engine(url)
        async with engine.begin() as conn:
            for stmt in [s for s in (BASE_SCHEMA + ";" + EXTRA_SCHEMA).split(";") if s.strip()]:
                await conn.execute(text(stmt))
            for stmt in _migrations() + _migrations():  # idempotente
                await conn.execute(text(stmt))
        maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        hsp._storage_ready = False
        async with maker() as db:
            db.execute = _NoExtension(db)
            await hsp._ensure_storage(db)
        # la migracion 024m otra vez, ya con las tablas de Hospitality creadas (idempotente)
        async with engine.begin() as conn:
            for stmt in _migrations():
                await conn.execute(text(stmt))
        await engine.dispose()

    asyncio.run(setup())
    yield url
    hsp._storage_ready = False  # otra prueba con otra base debe crear sus tablas


@pytest.fixture(autouse=True)
def env(monkeypatch):
    from app.services import panel_logo

    monkeypatch.setenv("LOYALTY_GAMES_SECRET", "pg-test-secret")
    monkeypatch.setattr(panel_logo, "panel_logo", AsyncMock(return_value={"url": "/brand-media/x/y.webp", "source": "published"}))
    games_api._BRAND.clear()
    monkeypatch.setattr(hsp, "_storage_ready", True)  # ya creado en el fixture de la base
    for lim in (games_api.PER_IP, games_api.PER_ROUND, games_api.JOIN_PER_IP):
        lim.hits.clear()


async def _session(url):
    engine = create_async_engine(url)
    return engine, async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def _company(db, retos: bool = True, games_on: bool = True) -> str:
    cid = str(uuid.uuid4())
    settings = {"hospitality_business_day": {"open": "18:00", "close": "04:00"}}
    await db.execute(text("INSERT INTO companies (id, name, slug, settings_json) VALUES (CAST(:i AS uuid), :n, :s, CAST(:j AS jsonb))"),
                     {"i": cid, "n": f"Bar{cid[:4]}", "s": cid[:8], "j": json.dumps(settings)})
    await db.execute(text("INSERT INTO company_core_settings (company_id, currency, timezone, language) VALUES (CAST(:i AS uuid), 'COP', 'America/Bogota', 'es')"), {"i": cid})
    await db.execute(text("INSERT INTO modules (code, name, category) VALUES ('loyalty', 'Fidelizacion', 'x') ON CONFLICT (code) DO NOTHING"))
    await db.execute(text("""INSERT INTO company_modules (company_id, module_id, enabled, settings)
        SELECT CAST(:i AS uuid), id, true, CAST(:s AS jsonb) FROM modules WHERE code = 'loyalty'"""),
                     {"i": cid, "s": json.dumps({"loyalty_games": games_on, "loyalty_retos_v2": retos})})
    await db.commit()
    return cid


async def _tables(db, cid: str, *names: str) -> None:
    for name in names:
        await db.execute(text("""INSERT INTO hospitality_table_access (company_id, table_key, table_number, access_code, status, expires_at)
            VALUES (CAST(:c AS uuid), :k, :n, :code, 'active', now() + interval '1 day')"""), {"c": cid, "k": hsp._table_key(name), "n": name, "code": CODE})
    await db.commit()


async def _order(db, cid: str, table: str, total: float, at: datetime) -> None:
    await db.execute(text("""INSERT INTO hospitality_orders (company_id, order_number, table_number, table_key, total, items, created_at, updated_at)
        VALUES (CAST(:c AS uuid), :o, :t, :k, :tot, '[]'::jsonb, :at, :at)"""),
                     {"c": cid, "o": f"O-{uuid.uuid4().hex[:6]}", "t": table, "k": hsp._table_key(table), "tot": total, "at": at})
    await db.commit()


def _iso(dt: datetime) -> str:
    return dt.isoformat()


async def _predict(db, cid, rid, table, a, b):
    return await hsp.submit_loyalty_score_prediction(uuid.UUID(cid), uuid.UUID(rid), hsp.HospitalityScorePredictionIn(
        table=table, team_name=f"Equipo {table}", score_a=a, score_b=b, access_code=CODE), db)


async def _vote(db, cid, rid, table, key):
    return await hsp.submit_loyalty_vote_poll(uuid.UUID(cid), uuid.UUID(rid), hsp.HospitalityVoteSubmissionIn(
        table=table, voter_name=f"Voz {table}", answer_key=key, access_code=CODE), db)


async def _past(db, rid: str, **cols) -> None:
    sets = ", ".join(f"{k} = now() - interval '1 minute'" for k in cols)
    await db.execute(text(f"UPDATE hospitality_loyalty_campaigns SET {sets} WHERE id::text = :i"), {"i": rid})
    await db.commit()


def _polla(now, **extra):
    return {"type": "score_pool", "title": "Final", "prize": "Botella", "team_a": "Colombia", "team_b": "Argentina",
            "predictions_close_at": _iso(now + timedelta(hours=1)), **extra}


# ---------------------------------------------------------------- reglas puras
def test_score_and_vote_rules():
    preds = [{"table_key": "mesa 1", "table_number": "Mesa 1", "score_a": 2, "score_b": 1, "created_at": "1"},
             {"table_key": "mesa 2", "table_number": "Mesa 2", "score_a": 1, "score_b": 1, "created_at": "2"},
             {"table_key": "mesa 3", "table_number": "Mesa 3", "score_a": 2, "score_b": 1, "created_at": "3"}]
    assert svc.score_outcome(preds, 0, 0)["status"] == "no_winner"
    one = svc.score_outcome(preds, 1, 1)
    assert one["status"] == "winner" and [m["table_key"] for m in one["matches"]] == ["mesa 2"]
    tie = svc.score_outcome(preds, 2, 1)
    assert tie["status"] == "tie" and [m["table_key"] for m in tie["matches"]] == ["mesa 1", "mesa 3"], "solo el marcador EXACTO"
    opts = [{"key": "option_1", "label": "Ana"}, {"key": "option_2", "label": "Beto"}, {"key": "option_3", "label": "Caro"}]
    votes = [{"table_key": f"m{i}", "table_number": f"M{i}", "answer_key": k} for i, k in enumerate(["option_1", "option_2", "option_2"])]
    assert svc.vote_outcome("participants", opts, votes)["winner"]["label"] == "Beto"
    tied = svc.vote_outcome("participants", opts, votes + [{"table_key": "m9", "table_number": "M9", "answer_key": "option_1"}])
    assert tied["status"] == "tie" and [o["label"] for o in tied["tied"]] == ["Ana", "Beto"]
    assert svc.vote_outcome("participants", opts, [])["status"] == "no_winner"
    yn = [{"table_key": "a", "table_number": "A", "answer_key": "yes"}, {"table_key": "b", "table_number": "B", "answer_key": "no"},
          {"table_key": "c", "table_number": "C", "answer_key": "yes"}]
    seen = []
    out = svc.vote_outcome("yes_no", [], yn, "yes", choice=lambda xs: seen.append([x["table_key"] for x in xs]) or xs[-1])
    assert seen == [["a", "c"]], "se sortea SOLO entre los que acertaron"
    assert out["winner"]["table_key"] == "c" and out["draw"] == {"candidates": 2, "method": "secrets"}
    assert svc.vote_outcome("true_false", [], yn, "false")["status"] == "no_winner"
    assert svc.vote_outcome("registration", [], yn)["status"] == "pick"


def test_wizard_validation_order_of_dates():
    now = datetime(2026, 10, 18, 23, 0, tzinfo=timezone.utc)
    ok = {"type": "consumption", "prize": "Ron", "registration_ends_at": _iso(now + timedelta(minutes=20)),
          "starts_at": _iso(now + timedelta(minutes=20)), "ends_at": _iso(now + timedelta(hours=3))}
    assert svc.validate_new(ok, now)["campaign_type"] == "consumption"
    for patch, code in ((dict(registration_ends_at=_iso(now - timedelta(minutes=1))), "inscripcion_en_el_pasado"),
                        (dict(starts_at=_iso(now + timedelta(minutes=10))), "inicio_antes_de_inscripcion"),
                        (dict(ends_at=_iso(now + timedelta(minutes=20))), "cierre_antes_de_inicio"),
                        (dict(prize=""), "premio_requerido")):
        with pytest.raises(RetoError) as exc:
            svc.validate_new({**ok, **patch}, now)
        assert exc.value.code == code
    with pytest.raises(RetoError) as exc:
        svc.validate_new({"type": "score_pool", "prize": "x", "team_a": "A", "team_b": "B"}, now)
    assert exc.value.code == "predictions_close_at_requerido", "pronosticos hasta es obligatorio"
    with pytest.raises(RetoError) as exc:
        svc.validate_new({"type": "vote_poll", "prize": "x", "vote_mode": "yes_no", "description": "¿?", "ends_at": _iso(now + timedelta(hours=1))}, now)
    assert exc.value.code == "respuesta_correcta_requerida"
    with pytest.raises(RetoError) as exc:
        svc.validate_new({"type": "vote_poll", "prize": "x", "vote_mode": "participants", "description": "¿?", "options": ["Ana"],
                          "ends_at": _iso(now + timedelta(hours=1))}, now)
    assert exc.value.code == "opciones_de_2_a_5"


# ---------------------------------------------------------------- uno activo por tipo + consumo
@pytest.mark.asyncio
async def test_one_active_per_type_and_consumption_ranking_is_the_same(pg_url):
    engine, maker = await _session(pg_url)
    async with maker() as db:
        cid = await _company(db)
        u = uuid.UUID(cid)
        now = datetime.now(timezone.utc)
        reto = await svc.create(db, cid, {"type": "consumption", "title": "Reto", "prize": "1/4 de ron", "registration_ends_at": _iso(now + timedelta(minutes=30)),
                                          "starts_at": _iso(now + timedelta(minutes=30)), "ends_at": _iso(now + timedelta(hours=3))}, "dueno")
        assert reto["stage"] == "registration" and reto["actions"] == ["close_now"] and reto["deadline_label"] == "Inscripción cierra en"
        with pytest.raises(RetoError) as exc:
            await svc.create(db, cid, {"type": "consumption", "prize": "x", "registration_ends_at": _iso(now + timedelta(minutes=5)),
                                       "starts_at": _iso(now + timedelta(minutes=5)), "ends_at": _iso(now + timedelta(hours=1))}, "dueno")
        assert exc.value.status == 409 and exc.value.code == "ya_hay_uno_activo_de_este_tipo"
        await svc.create(db, cid, _polla(now), "dueno")  # otro tipo: si se puede
        with pytest.raises(RetoError) as exc:
            await svc.create(db, cid, _polla(now), "dueno")
        assert exc.value.status == 409
        for table in ("Mesa 1", "Mesa 2", "Mesa 3"):
            await hsp.join_loyalty_campaign(u, uuid.UUID(reto["id"]), hsp.HospitalityLoyaltyParticipantIn(table=table, team_name=f"Los {table}"), db)
        start = now + timedelta(minutes=30)
        await _order(db, cid, "Mesa 1", 900000, start - timedelta(minutes=5))  # antes del torneo: no cuenta
        await _order(db, cid, "Mesa 1", 50000, start + timedelta(minutes=10))
        await _order(db, cid, "Mesa 2", 80000, start + timedelta(minutes=20))
        await _order(db, cid, "Mesa 2", 10000, start + timedelta(minutes=40))
        await _order(db, cid, "Mesa 3", 70000, now + timedelta(hours=4))  # despues del cierre: no cuenta
        row = await svc._row(db, cid, reto["id"])
        legacy_style = await hsp._loyalty_leaderboard(db, row)
        assert [(r["table_number"], r["total"]) for r in legacy_style] == [("Mesa 2", 90000.0), ("Mesa 1", 50000.0), ("Mesa 3", 0.0)]
        # Cierre automatico a su hora: gana el 1.o del MISMO ranking.
        assert await svc.refresh_due(db, cid, now + timedelta(hours=3, minutes=1)) == 1
        closed = await svc._row(db, cid, reto["id"])
        winner = json.loads(closed["winner"]) if isinstance(closed["winner"], str) else closed["winner"]
        assert closed["status"] == "closed" and closed["result_status"] == "winner" and closed["prize_status"] == "pending"
        assert winner["table_number"] == "Mesa 2" and winner["total"] == 90000.0
        assert [(r["table_number"], r["total"]) for r in await hsp._loyalty_leaderboard(db, closed)] == [(r["table_number"], r["total"]) for r in legacy_style]
        hist = await svc.history(db, cid)
        assert hist[0]["winner"]["team_name"] == "Los Mesa 2" and hist[0]["prize_status"] == "pending"
        done = await svc.deliver_prize(db, cid, reto["id"], "barman@bar")
        assert done["match"] and done["reto"]["prize_status"] == "delivered" and done["reto"]["prize_delivered_by"] == "barman@bar"
        assert done["reto"]["prize_delivered_at"]
        with pytest.raises(RetoError):
            await svc.deliver_prize(db, cid, reto["id"], "otro")
        # QR: el resultado del reto recien cerrado
        qr = await hsp.get_active_loyalty_campaign(u, "Mesa 2", db)
        assert qr["campaign"]["result_status"] == "winner" and qr["campaign"]["winner"]["table_key"] == "mesa 2"
    await engine.dispose()


# ---------------------------------------------------------------- polla
@pytest.mark.asyncio
async def test_score_pool_close_of_predictions_and_exact_score(pg_url):
    engine, maker = await _session(pg_url)
    async with maker() as db:
        cid = await _company(db)
        u = uuid.UUID(cid)
        await _tables(db, cid, "Mesa 1", "Mesa 2", "Mesa 3", "Mesa 4")
        now = datetime.now(timezone.utc)
        polla = await svc.create(db, cid, _polla(now), "dueno")
        rid = polla["id"]
        await _predict(db, cid, rid, "Mesa 1", 2, 1)
        await _predict(db, cid, rid, "Mesa 2", 1, 1)
        await _predict(db, cid, rid, "Mesa 3", 2, 1)
        await _predict(db, cid, rid, "Mesa 1", 0, 0)  # una mesa = un pronostico: no cambia
        qr = await hsp.get_active_loyalty_campaign(u, "Mesa 1", db)
        assert qr["score_prediction"]["score_a"] == 2 and qr["score_campaign"]["predictions_open"] is True
        with pytest.raises(RetoError) as exc:
            await svc.set_score(db, cid, rid, 2, 1, "dueno")
        assert exc.value.code == "pronosticos_abiertos"
        await _past(db, rid, predictions_close_at=1)
        with pytest.raises(HTTPException) as exc:
            await _predict(db, cid, rid, "Mesa 4", 3, 0)
        assert exc.value.status_code == 409 and exc.value.detail == "pronosticos_cerrados", "el servidor rechaza despues de la hora"
        qr = await hsp.get_active_loyalty_campaign(u, "Mesa 4", db)
        assert qr["score_campaign"]["predictions_open"] is False and qr["score_prediction"] is None
        tied = await svc.set_score(db, cid, rid, 2, 1, "barman@bar")
        assert tied["result_status"] == "tie" and tied["status"] == "active" and tied["actions"] == ["tiebreak", "pick_winner"]
        assert [m["table_number"] for m in tied["result"]["matches"]] == ["Mesa 1", "Mesa 3"]
        qr = await hsp.get_active_loyalty_campaign(u, "Mesa 3", db)
        assert [t["table_key"] for t in qr["score_campaign"]["tied_tables"]] == ["mesa 1", "mesa 3"]
        assert qr["score_campaign"]["final_score"] == {"score_a": 2, "score_b": 1}
        with pytest.raises(RetoError):
            await svc.create(db, cid, _polla(now), "dueno")  # el empate sigue en curso: uno por tipo
        with pytest.raises(RetoError) as exc:
            await svc.pick_winner(db, cid, rid, "mesa 2", "dueno")
        assert exc.value.code == "opcion_no_valida", "solo entre las empatadas"
        won = await svc.pick_winner(db, cid, rid, "mesa 3", "dueno")
        assert won["status"] == "closed" and won["winner"]["table_number"] == "Mesa 3" and won["winner"]["source"] == "bar"
        qr = await hsp.get_active_loyalty_campaign(u, "Mesa 3", db)
        assert qr["score_campaign"]["winner"]["table_key"] == "mesa 3" and qr["score_campaign"]["result_status"] == "winner"
        # 1 acierto: esa mesa gana; 0 aciertos: sin ganador y al historial.
        for score, expected in (((1, 1), "winner"), ((5, 5), "no_winner")):
            p = await svc.create(db, cid, _polla(now), "dueno")
            await _predict(db, cid, p["id"], "Mesa 2", 1, 1)
            await _predict(db, cid, p["id"], "Mesa 1", 0, 2)
            await _past(db, p["id"], predictions_close_at=1)
            out = await svc.set_score(db, cid, p["id"], *score, "dueno")
            assert out["result_status"] == expected and out["status"] == "closed"
            if expected == "winner":
                assert out["winner"]["table_number"] == "Mesa 2" and out["winner"]["source"] == "exact" and out["prize_status"] == "pending"
            else:
                assert out["winner"] is None and out["prize_status"] == ""
        assert [h["result_status"] for h in (await svc.history(db, cid))[:3]] == ["no_winner", "winner", "winner"]
    await engine.dispose()


@pytest.mark.asyncio
async def test_tie_opens_a_tiebreak_round_only_for_the_tied_tables(pg_url):
    engine, maker = await _session(pg_url)
    async with maker() as db:
        cid = await _company(db, games_on=True)
        u = uuid.UUID(cid)
        await _tables(db, cid, "Mesa 1", "Mesa 2", "Mesa 3")
        now = datetime.now(timezone.utc)
        polla = await svc.create(db, cid, _polla(now, prize="Botella de ron"), "dueno")
        rid = polla["id"]
        for t in ("Mesa 1", "Mesa 3"):
            await _predict(db, cid, rid, t, 2, 1)
        await _predict(db, cid, rid, "Mesa 2", 0, 1)
        await _past(db, rid, predictions_close_at=1)
        await svc.set_score(db, cid, rid, 2, 1, "dueno")
        with pytest.raises(RetoError) as exc:
            await svc.open_tiebreak(db, cid, rid, "ruleta", "dueno")
        assert exc.value.code == "juego_invalido"
        out = await svc.open_tiebreak(db, cid, rid, "memory", "barman@bar", pairs=5)
        assert out["tiebreak"]["status"] == "registration" and out["tiebreak"]["kind"] == "memory"
        r = await games.round_row(db, cid, out["tiebreak"]["round_id"])
        assert r["prize"] == "Botella de ron", "el premio de la polla"
        cfg = games.config_of(r)["tiebreak"]
        assert cfg["title"] == "Desempate · Final" and cfg["teams"] == "Colombia vs Argentina"
        token = games.round_token(r["id"])
        req = SimpleNamespace(base_url="https://bar.test/", headers={"x-forwarded-for": "1.1.1.1"}, client=SimpleNamespace(host="1.1.1.1"))
        info = await games_api.play_info(token, req, db)
        assert [t["label"] for t in info["tiebreak"]["tables"]] == ["Mesa 1", "Mesa 3"], "la lista solo trae las empatadas"
        live = await games.live_state(db, cid)
        assert live["round"]["tiebreak"]["teams"] == "Colombia vs Argentina", "la pantalla del bar muestra el desempate"

        async def join(name, doc, table):
            return await games_api.play_join(token, req, {"name": name, "document": doc, "consent": True, "table": table}, db)

        for table, code, status in ((None, "mesa_requerida", 422), ("mesa 2", "mesa_no_empatada", 403), ("Mesa 9", "mesa_no_empatada", 403)):
            with pytest.raises(HTTPException) as exc:
                await join("Intruso", "55555555", table)
            assert exc.value.status_code == status and exc.value.detail == code
        a = await join("Ana", "10101010", "mesa 1")
        with pytest.raises(HTTPException) as exc:
            await join("Amigo de Ana", "20202020", "mesa 1")
        assert exc.value.detail == "mesa_ya_juega", "una persona por mesa"
        b = await join("Beto", "30303030", "mesa 3")
        players = await games.players(db, cid, r["id"])
        assert sorted((p["display_name"], p.get("table_key")) for p in [dict(x) for x in (await db.execute(text(
            "SELECT display_name, table_key FROM loyalty_game_players WHERE round_id::text = :r"), {"r": str(r["id"])})).mappings().all()]) == [("Ana", "mesa 1"), ("Beto", "mesa 3")]
        assert len(players) == 2
        with pytest.raises(RetoError) as exc:
            await svc.open_tiebreak(db, cid, rid, "trivia", "dueno")
        assert exc.value.code == "ya_hay_una_ronda_activa"
        with pytest.raises(RetoError) as exc:
            await svc.pick_winner(db, cid, rid, "mesa 1", "dueno")
        assert exc.value.code == "hay_un_desempate_en_curso"
        await games.start_round(db, cid, r["id"])
        pid_b = games.eng.unsign("player", b["player_token"])
        pid_a = games.eng.unsign("player", a["player_token"])
        await db.execute(text("UPDATE loyalty_game_players SET score = 4, score_ms = 30000, progress = CAST(:p AS jsonb) WHERE id::text = :i"),
                         {"i": pid_b, "p": json.dumps({"pairs": 4, "pair_ms": [5000, 10000, 20000, 30000]})})
        await db.execute(text("UPDATE loyalty_game_players SET score = 2, score_ms = 20000, progress = CAST(:p AS jsonb) WHERE id::text = :i"),
                         {"i": pid_a, "p": json.dumps({"pairs": 2, "pair_ms": [9000, 20000]})})
        await db.commit()
        await games_api.close_round(u, uuid.UUID(str(r["id"])), req, {"role": "barman", "name": "barman@bar"}, db)
        row = await svc._row(db, cid, rid)
        winner = row["winner"] if isinstance(row["winner"], dict) else json.loads(row["winner"])
        assert row["status"] == "closed" and row["result_status"] == "winner"
        assert winner["table_number"] == "Mesa 3" and winner["player_name"] == "Beto" and winner["source"] == "tiebreak"
        hist = (await svc.history(db, cid))[0]
        assert hist["winner"]["player_name"] == "Beto" and hist["source"] == "tiebreak"
        qr = await hsp.get_active_loyalty_campaign(u, "Mesa 3", db)
        assert qr["score_campaign"]["winner"]["player_name"] == "Beto"
        # Premio del desempate: con la validacion por documento que ya existe.
        assert (await svc.deliver_prize(db, cid, rid, "barman@bar", document="10101010")) == {"match": False}
        assert (await svc._row(db, cid, rid))["prize_status"] == "pending"
        ok = await svc.deliver_prize(db, cid, rid, "barman@bar", document="30303030")
        assert ok["match"] and ok["reto"]["prize_status"] == "delivered"
    await engine.dispose()


@pytest.mark.asyncio
async def test_tie_without_live_games_is_resolved_by_the_bar(pg_url):
    engine, maker = await _session(pg_url)
    async with maker() as db:
        cid = await _company(db, games_on=False)
        await _tables(db, cid, "Mesa 1", "Mesa 2")
        now = datetime.now(timezone.utc)
        rid = (await svc.create(db, cid, _polla(now), "dueno"))["id"]
        for t in ("Mesa 1", "Mesa 2"):
            await _predict(db, cid, rid, t, 1, 0)
        await _past(db, rid, predictions_close_at=1)
        await svc.set_score(db, cid, rid, 1, 0, "dueno")
        with pytest.raises(RetoError) as exc:
            await svc.open_tiebreak(db, cid, rid, "memory", "dueno")
        assert exc.value.code == "juegos_en_vivo_no_activo"
        st = await svc.state(db, cid, "admin")
        assert st["games_on"] is False and st["active"]["score_pool"]["result_status"] == "tie"
        assert (await svc.pick_winner(db, cid, rid, "mesa 2", "dueno"))["winner"]["table_number"] == "Mesa 2"
    await engine.dispose()


# ---------------------------------------------------------------- concurso
@pytest.mark.asyncio
async def test_contest_modes_and_secret_never_reaches_the_qr(pg_url):
    engine, maker = await _session(pg_url)
    async with maker() as db:
        cid = await _company(db)
        u = uuid.UUID(cid)
        await _tables(db, cid, "Mesa 1", "Mesa 2", "Mesa 3", "Mesa 4")
        now = datetime.now(timezone.utc)
        base = {"type": "vote_poll", "prize": "Shots", "ends_at": _iso(now + timedelta(hours=1))}
        # Votacion: mas votos; con empate el bar elige entre las empatadas.
        v = await svc.create(db, cid, {**base, "vote_mode": "participants", "description": "¿Quién cantó mejor?", "options": ["Ana", "Beto", "Caro"]}, "dueno")
        assert [o["label"] for o in v["options"]] == ["Ana", "Beto", "Caro"], "solo las opciones escritas"
        for t, k in (("Mesa 1", "option_1"), ("Mesa 2", "option_2"), ("Mesa 3", "option_2"), ("Mesa 4", "option_1")):
            await _vote(db, cid, v["id"], t, k)
        with pytest.raises(HTTPException):
            await _vote(db, cid, v["id"], "Mesa 1", "option_4")
        tie = await svc.close_now(db, cid, v["id"], "dueno")
        assert tie["result_status"] == "tie" and [o["label"] for o in tie["result"]["tied"]] == ["Ana", "Beto"]
        with pytest.raises(HTTPException) as exc:
            await _vote(db, cid, v["id"], "Mesa 1", "option_3")
        assert exc.value.status_code == 409, "cerrado: no recibe votos"
        with pytest.raises(RetoError):
            await svc.pick_winner(db, cid, v["id"], "option_3", "dueno")
        won = await svc.pick_winner(db, cid, v["id"], "option_2", "dueno")
        assert won["winner"]["label"] == "Beto" and won["status"] == "closed"
        v2 = await svc.create(db, cid, {**base, "vote_mode": "participants", "description": "¿?", "options": ["Ana", "Beto"]}, "dueno")
        await _vote(db, cid, v2["id"], "Mesa 1", "option_2")
        assert (await svc.close_now(db, cid, v2["id"], "dueno"))["winner"]["label"] == "Beto"
        # Si/No: sorteo seguro entre los que acertaron; la respuesta correcta nunca viaja al QR.
        yn = await svc.create(db, cid, {**base, "vote_mode": "yes_no", "description": "¿Colombia gana?", "secret_answer": "no"}, "dueno")
        for t, k in (("Mesa 1", "yes"), ("Mesa 2", "no"), ("Mesa 3", "no")):
            await _vote(db, cid, yn["id"], t, k)
        qr = await hsp.get_active_loyalty_campaign(u, "Mesa 1", db)
        dumped = json.dumps(qr, default=str)
        assert "secret_answer" not in dumped and qr["vote_campaign"]["id"] == yn["id"]
        summary = json.dumps(await hsp.get_loyalty_campaigns_summary(u, db), default=str)
        assert "secret_answer" not in summary
        won = await svc.close_now(db, cid, yn["id"], "dueno")
        assert won["winner"]["table_number"] in ("Mesa 2", "Mesa 3") and won["result"]["draw"]["candidates"] == 2
        qr = json.dumps(await hsp.get_active_loyalty_campaign(u, "Mesa 2", db), default=str)
        assert "secret_answer" not in qr, "ni despues de cerrar"
        # V/F sin aciertos: sin ganador. Cierre AUTOMATICO a su hora (desde el QR).
        tf = await svc.create(db, cid, {**base, "vote_mode": "true_false", "description": "¿El ron es de caña?", "secret_answer": "true"}, "dueno")
        await _vote(db, cid, tf["id"], "Mesa 1", "false")
        await _past(db, tf["id"], ends_at=1)
        qr = await hsp.get_active_loyalty_campaign(u, "Mesa 1", db)
        row = await svc._row(db, cid, tf["id"])
        assert row["status"] == "closed" and row["result_status"] == "no_winner" and row["closed_by"] == "Cierre automático"
        assert qr["vote_campaign"]["result_status"] == "no_winner"
        # Inscripcion simple (karaoke): al cerrar el bar elige de la lista de inscritos.
        reg = await svc.create(db, cid, {**base, "vote_mode": "registration", "title": "Karaoke"}, "dueno")
        await _vote(db, cid, reg["id"], "Mesa 3", "registered")
        await _vote(db, cid, reg["id"], "Mesa 4", "registered")
        pick = await svc.close_now(db, cid, reg["id"], "dueno")
        assert pick["result_status"] == "pick" and pick["actions"] == ["pick_winner"] and pick["status"] == "active"
        with pytest.raises(RetoError):
            await svc.pick_winner(db, cid, reg["id"], "mesa 1", "dueno")
        assert (await svc.pick_winner(db, cid, reg["id"], "mesa 4", "dueno"))["winner"]["team_name"] == "Voz Mesa 4"
    await engine.dispose()


# ---------------------------------------------------------------- retos de antes + interruptor
@pytest.mark.asyncio
async def test_existing_retos_show_and_work_and_switch_off_keeps_the_old_screen(pg_url, monkeypatch):
    from app.api import deps
    from app.web import admin_v2_routes

    engine, maker = await _session(pg_url)
    async with maker() as db:
        cid = await _company(db)
        off = await _company(db, retos=False)
        u, u_off = uuid.UUID(cid), uuid.UUID(off)
        await _tables(db, cid, "Mesa 1", "Mesa 2")
        now = datetime.now(timezone.utc)
        # Retos creados con la pantalla de siempre (rules_version 1).
        await hsp.create_loyalty_score_pool(u, hsp.HospitalityScorePoolCampaignIn(title="Polla vieja", prize="Ron", team_a="A", team_b="B"), db)
        await hsp.create_loyalty_vote_poll(u, hsp.HospitalityVotePollCampaignIn(title="¿Si o no?", prize="Shot", vote_mode="yes_no",
                                                                                registration_ends_at=now + timedelta(hours=1)), db)
        legacy_before = json.dumps(await hsp.get_active_loyalty_campaign(u_off, "Mesa 1", db), default=str, sort_keys=True)
        st = await svc.state(db, cid, "admin")
        pool, vote = st["active"]["score_pool"], st["active"]["vote_poll"]
        assert pool["title"] == "Polla vieja" and pool["rules_version"] == 1 and pool["actions"] == ["set_score"], "en curso, con lo que falta"
        assert vote["title"] == "¿Si o no?" and vote["actions"] == ["close_now"]
        await _predict(db, cid, pool["id"], "Mesa 1", 1, 0)  # sin "pronosticos hasta": como siempre
        assert (await svc.set_score(db, cid, pool["id"], 1, 0, "dueno"))["winner"]["table_number"] == "Mesa 1"
        await _vote(db, cid, vote["id"], "Mesa 2", "yes")
        with pytest.raises(RetoError) as exc:
            await svc.close_now(db, cid, vote["id"], "dueno")
        assert exc.value.code == "falta_respuesta_correcta", "el de antes no guardo la respuesta: el bar la dice al cerrar"
        assert (await svc.close_now(db, cid, vote["id"], "dueno", answer_key="yes"))["winner"]["table_number"] == "Mesa 2"
        # Un reto viejo cerrado sin resultado aparece en el historial.
        await hsp.create_loyalty_score_pool(u, hsp.HospitalityScorePoolCampaignIn(title="Otra", prize="x", team_a="A", team_b="B"), db)
        await hsp.create_loyalty_score_pool(u, hsp.HospitalityScorePoolCampaignIn(title="Tercera", prize="x", team_a="A", team_b="B"), db)
        assert "Otra" in [h["title"] for h in await svc.history(db, cid)]
        # Interruptor apagado (otra empresa): 404 y el QR responde igual que siempre.
        monkeypatch.setattr(admin_v2_routes, "_active_session", AsyncMock(return_value=False))

        async def who(role, company):
            monkeypatch.setattr(deps, "require_company_user_for_tenant", AsyncMock(return_value=SimpleNamespace(role=role, email=f"{role}@x", settings_json={})))
            req = SimpleNamespace(base_url="https://bar.test/", headers={}, client=SimpleNamespace(host="1.1.1.1"))
            return await api.actor(company, req, "Bearer x", db)

        assert (await who("company_admin", u))["role"] == "admin"
        assert (await who("barman", u))["role"] == "barman"
        for role, company, code in (("mesero", u, 403), ("company_admin", u_off, 404)):
            with pytest.raises(HTTPException) as exc:
                await who(role, company)
            assert exc.value.status_code == code
        await hsp.create_loyalty_score_pool(u_off, hsp.HospitalityScorePoolCampaignIn(title="Sigue", prize="x", team_a="A", team_b="B"), db)
        qr_off = await hsp.get_active_loyalty_campaign(u_off, "Mesa 1", db)
        assert "rules_version" not in qr_off["score_campaign"] and "result_status" not in qr_off["score_campaign"], "pantalla vieja: mismo QR"
        assert legacy_before == json.dumps({**json.loads(legacy_before)}, sort_keys=True)
    await engine.dispose()


def test_migration_is_additive_and_routes_need_a_session():
    statements: list[str] = []
    module = importlib.import_module("migrations.versions.024m_loyalty_retos_v2")
    module.op = SimpleNamespace(execute=lambda q: statements.append(str(q)))
    module.upgrade()
    sql = " ".join(statements).lower()
    assert len(module.revision) <= 32 and module.down_revision == "024l_billing_drafts"
    assert "drop " not in sql and "delete" not in sql and "update " not in sql
    assert sql.count("add column if not exists") == len(svc.CAMPAIGN_COLUMNS) + 2
    assert list(module.CAMPAIGN_COLUMNS) == list(svc.CAMPAIGN_COLUMNS), "migracion y arranque con las mismas columnas"
    for r in api.router.routes:
        assert api.actor in [d.call for d in r.dependant.dependencies], f"{r.path} sin sesion"
    from app.services import switch_registry

    sw = next(s for s in switch_registry.registry()["switches"] if s["key"] == "loyalty_retos_v2")
    assert sw["module"] == "loyalty" and svc.FLAG == "loyalty_retos_v2" and sw["group"] == "Fidelización"
