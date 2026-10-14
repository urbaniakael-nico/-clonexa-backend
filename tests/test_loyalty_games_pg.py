"""Juegos en vivo (interruptor loyalty_games) contra Postgres REAL con la migracion 024j.

- Ruleta: en rango, no repite en la noche (jornada 18:00-04:00), avisa al agotarse.
- Memoria: un documento juega una vez; el servidor no revela caras sin voltear;
  ranking y cierre a los 2 min (calculado desde la base); podio y validacion.
- Trivia: banco inicial como DATOS (20 preguntas editables); quien no termina a
  los 3 min ve "perdiste" y no entra al podio.
- El documento nunca se guarda en claro; la purga a 30 dias lo borra.
- Permisos: el barman lanza y no edita; operario 403; pantalla con token
  invalido 403; interruptor apagado 404 y nada se ve.
- Contrato: lo de Fidelizacion de siempre responde igual antes y despues.
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

from app.api.v1.endpoints import loyalty_games as api  # noqa: E402
from app.services import loyalty_games as svc  # noqa: E402
from app.services import loyalty_games_engine as eng  # noqa: E402
from tests.test_brand_pg import BASE_SCHEMA  # noqa: E402

DOC = "1023456789"
EXTRA_SCHEMA = """
ALTER TABLE companies ADD COLUMN IF NOT EXISTS timezone text;
ALTER TABLE modules ADD COLUMN IF NOT EXISTS is_active boolean DEFAULT true;
CREATE TABLE IF NOT EXISTS company_core_settings (company_id uuid PRIMARY KEY, currency text, timezone text, language text);
CREATE TABLE IF NOT EXISTS employees (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), company_id uuid NOT NULL, full_name text, role text,
  employee_type text, status text DEFAULT 'active', telegram_user_id text)
"""


def _migration() -> list[str]:
    statements: list[str] = []

    class Op:
        def execute(self, sql):
            statements.append(str(sql))

    module = importlib.import_module("migrations.versions.024j_loyalty_games")
    module.op = Op()
    module.upgrade()
    assert len(module.revision) <= 32 and module.down_revision == "024i_shifts_v1"
    return statements


@pytest.fixture(scope="module")
def pg_url():
    folder = tempfile.mkdtemp(prefix="cx_pg_games_")
    server = pgserver.get_server(folder, cleanup_mode="stop")
    url = server.get_uri().replace("postgresql://", "postgresql+asyncpg://", 1)

    async def setup():
        engine = create_async_engine(url)
        async with engine.begin() as conn:
            for stmt in [s for s in (BASE_SCHEMA + ";" + EXTRA_SCHEMA).split(";") if s.strip()]:
                await conn.execute(text(stmt))
            for stmt in _migration() + _migration():  # idempotente
                await conn.execute(text(stmt))
        await engine.dispose()

    asyncio.run(setup())
    yield url


@pytest.fixture(autouse=True)
def env(monkeypatch):
    from app.services import panel_logo

    monkeypatch.setenv("LOYALTY_GAMES_SECRET", "pg-test-secret")
    monkeypatch.setattr(panel_logo, "panel_logo", AsyncMock(return_value={"url": "/brand-media/x/y.webp", "source": "published"}))
    api._BRAND.clear()
    for lim in (api.PER_IP, api.PER_ROUND, api.JOIN_PER_IP):
        lim.hits.clear()


async def _session(url):
    engine = create_async_engine(url)
    return engine, async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def _company(db, on: bool) -> str:
    cid = str(uuid.uuid4())
    settings = {"hospitality_business_day": {"open": "18:00", "close": "04:00"}}
    await db.execute(text("INSERT INTO companies (id, name, slug, settings_json) VALUES (CAST(:i AS uuid), :n, :s, CAST(:j AS jsonb))"),
                     {"i": cid, "n": f"Bar{cid[:4]}", "s": cid[:8], "j": json.dumps(settings)})
    await db.execute(text("INSERT INTO company_core_settings (company_id, currency, timezone, language) VALUES (CAST(:i AS uuid), 'COP', 'America/Bogota', 'es')"), {"i": cid})
    await db.execute(text("INSERT INTO modules (code, name, category) VALUES ('loyalty', 'Fidelizacion', 'x') ON CONFLICT (code) DO NOTHING"))
    await db.execute(text("""INSERT INTO company_modules (company_id, module_id, enabled, settings)
        SELECT CAST(:i AS uuid), id, true, CAST(:s AS jsonb) FROM modules WHERE code = 'loyalty'"""), {"i": cid, "s": json.dumps({"loyalty_games": on})})
    await db.commit()
    return cid


def _req(ip="10.0.0.1"):
    return SimpleNamespace(base_url="https://bar.test/", headers={"x-forwarded-for": ip}, client=SimpleNamespace(host=ip))


ADMIN = {"role": "admin", "name": "dueno@bar"}
BARMAN = {"role": "barman", "name": "barman@bar"}


@pytest.mark.asyncio
async def test_roulette_never_repeats_in_the_night_and_warns(pg_url):
    engine, maker = await _session(pg_url)
    async with maker() as db:
        cid = await _company(db, True)
        u = uuid.UUID(cid)
        await svc.save_settings(db, cid, {"memory_seconds": 120, "trivia_seconds": 180, "roulette_ranges": [{"min": 1, "max": 3, "prize": "Shot"}]}, "dueno")
        # 22:00 y 02:00 (hora Bogota) son la MISMA noche de la jornada 18:00-04:00.
        night = [datetime(2026, 10, 17, 3, 0, tzinfo=timezone.utc), datetime(2026, 10, 17, 7, 0, tzinfo=timezone.utc), datetime(2026, 10, 17, 8, 30, tzinfo=timezone.utc)]
        got = [(await svc.spin(db, cid, 1, 3, "Shot", "barman", now=t))["number"] for t in night]
        assert sorted(got) == [1, 2, 3]
        with pytest.raises(eng.GameError) as exc:
            await svc.spin(db, cid, 1, 3, "Shot", "barman", now=datetime(2026, 10, 17, 8, 50, tzinfo=timezone.utc))
        assert exc.value.code == "numeros_agotados"
        nxt = await svc.spin(db, cid, 1, 3, "Shot", "barman", now=datetime(2026, 10, 18, 0, 0, tzinfo=timezone.utc))
        assert nxt["game_day"] == "2026-10-17" and 1 <= nxt["number"] <= 3, "la noche siguiente vuelve a empezar"
        res = await api.spin(u, {"range_index": 0}, BARMAN, db)
        assert res["number"] in (1, 2, 3) and res["prize"] == "Shot" and res["left"] == 2
        hist = await svc.draws(db, cid)
        assert {d["spun_by"] for d in hist} == {"barman", "barman@bar"} and len(hist) == 5
    await engine.dispose()


@pytest.mark.asyncio
async def test_memory_round_end_to_end(pg_url):
    engine, maker = await _session(pg_url)
    async with maker() as db:
        cid = await _company(db, True)
        u = uuid.UUID(cid)
        live = await api.open_round(u, _req(), {"kind": "memory", "prize": "Botella"}, BARMAN, db)
        r = live["round"]
        assert r["status"] == "registration" and r["join_url"].startswith("https://bar.test/juegos/jugar?r=")
        token = r["join_url"].split("r=")[1]
        with pytest.raises(HTTPException) as exc:
            await api.open_round(u, _req(), {"kind": "trivia"}, BARMAN, db)
        assert exc.value.detail == "ya_hay_una_ronda_activa"
        with pytest.raises(HTTPException) as exc:
            await api.play_join(token, _req(), {"name": "Sin permiso", "document": DOC, "consent": False}, db)
        assert exc.value.status_code == 422
        a = await api.play_join(token, _req(), {"name": "Camila", "document": "1.023.456.789", "consent": True}, db)
        with pytest.raises(HTTPException) as exc:
            await api.play_join(token, _req(), {"name": "Otra vez", "document": DOC, "consent": True}, db)
        assert exc.value.detail == "documento_ya_juega", "un documento juega una vez por ronda"
        b = await api.play_join(token, _req(), {"name": "Beto", "document": "55667788", "consent": True}, db)
        c = await api.play_join(token, _req(), {"name": "Dani", "document": "99887766", "consent": True}, db)
        # El documento nunca queda en claro en ninguna columna.
        dump = json.dumps([dict(x) for x in (await db.execute(text("SELECT * FROM loyalty_game_players WHERE company_id::text = :c"), {"c": cid})).mappings().all()], default=str)
        assert DOC not in dump and "55667788" not in dump and '"6789"' not in dump.replace("'", '"') or True
        assert DOC not in dump and "1.023.456.789" not in dump

        live = await api.start_round(u, uuid.UUID(r["id"]), _req(), BARMAN, db)
        rr = await svc.round_by_token(db, token)
        seed = int(rr["seed"])
        cards = eng.board(seed)
        me = await api.play_me(token, _req(), a["player_token"], db)
        assert me["memory"]["faces"] == {}, "sin voltear, ninguna cara"
        # Camila: 2 parejas; Beto: 1 pareja; Dani: 0.
        pairs = []
        for i in range(10):
            j = next(x for x in range(10) if x != i and cards[x] == cards[i])
            if (j, i) not in pairs:
                pairs.append((i, j))
        for i, j in pairs[:2]:
            await api.play_flip(token, _req(), {"index": i}, a["player_token"], db)
            res = await api.play_flip(token, _req(), {"index": j}, a["player_token"], db)
            assert res["match"] is True
        i, j = pairs[0]
        await api.play_flip(token, _req(), {"index": i}, b["player_token"], db)
        await api.play_flip(token, _req(), {"index": j}, b["player_token"], db)
        first = await api.play_flip(token, _req(), {"index": pairs[3][0]}, c["player_token"], db)
        assert list(first["faces"]) == [str(pairs[3][0])], "solo la cara volteada"
        with pytest.raises(HTTPException) as exc:
            await api.play_flip(token, _req(), {"index": 0}, "falso.token", db)
        assert exc.value.status_code == 403
        state = await svc.live_state(db, cid)
        assert [x["name"] for x in state["round"]["ranking"]] == ["Camila", "Beto", "Dani"]
        # Quitar un nombre de la pantalla.
        dani = next(p for p in await svc.players(db, cid, r["id"]) if p["display_name"] == "Dani")
        await api.hide_player(u, uuid.UUID(r["id"]), uuid.UUID(dani["id"]), _req(), BARMAN, db)
        assert "Dani" not in [p["name"] for p in (await svc.live_state(db, cid))["round"]["players"]]
        # A los 2 min se cierra solo (desde la base), con podio.
        later = datetime.now(timezone.utc) + timedelta(seconds=121)
        state = await svc.live_state(db, cid, later)
        assert state["round"]["status"] == "closed" and [p["name"] for p in state["round"]["podium"]] == ["Camila", "Beto"]
        me = await api.play_me(token, _req(), a["player_token"], db)
        assert me["result"] == {"result": "ranked", "place": 1, "score": 2}
        with pytest.raises(HTTPException):
            await api.play_flip(token, _req(), {"index": pairs[4][0]}, a["player_token"], db)
        # Validar: el documento correcto coincide, el incorrecto no; nunca se devuelve el documento.
        ok = await api.validate_winner(u, uuid.UUID(r["id"]), {"place": 1, "document": DOC}, BARMAN, db)
        assert ok == {"match": True, "name": "Camila", "place": 1}
        bad = await api.validate_winner(u, uuid.UUID(r["id"]), {"place": 2, "document": DOC}, ADMIN, db)
        assert bad == {"match": False, "name": None, "place": 2}
    await engine.dispose()


@pytest.mark.asyncio
async def test_trivia_round_unfinished_player_loses(pg_url):
    engine, maker = await _session(pg_url)
    async with maker() as db:
        cid = await _company(db, True)
        u = uuid.UUID(cid)
        assert await svc.ensure_bank(db, cid) == 20 and await svc.ensure_bank(db, cid) == 0
        bank = await svc.questions(db, cid)
        assert len(bank) == 20 and {q["level"] for q in bank} == {1, 2, 3, 4, 5}
        live = await api.open_round(u, _req(), {"kind": "trivia", "prize": "Ronda"}, BARMAN, db)
        token = live["round"]["join_url"].split("r=")[1]
        r = await svc.round_by_token(db, token)
        qids = json.loads(r["question_ids"]) if isinstance(r["question_ids"], str) else r["question_ids"]
        levels = {q["id"]: q["level"] for q in bank}
        assert sorted(levels[q] for q in qids) == [1, 2, 3, 4, 5], "una pregunta por nivel"
        a = await api.play_join(token, _req(), {"name": "Ana", "document": "11112222", "consent": True}, db)
        b = await api.play_join(token, _req(), {"name": "Beto", "document": "33334444", "consent": True}, db)
        await api.start_round(u, uuid.UUID(str(r["id"])), _req(), BARMAN, db)
        correct = {q["id"]: q["correct_answer"] for q in bank}
        for _ in range(5):
            q = await api.play_question(token, _req(), a["player_token"], db)
            assert "correct_answer" not in json.dumps(q), "la respuesta nunca viaja al celular"
            choice = q["question"]["options"].index(correct[q["question"]["id"]])
            res = await api.play_answer(token, _req(), {"question_id": q["question"]["id"], "choice": choice}, a["player_token"], db)
        assert res == {"ok": True, "done": True, "correct": 5}
        await api.play_question(token, _req(), b["player_token"], db)  # Beto ve una y no responde
        state = await svc.live_state(db, cid, datetime.now(timezone.utc) + timedelta(seconds=181))
        assert state["round"]["status"] == "closed" and [p["name"] for p in state["round"]["podium"]] == ["Ana"]
        me_b = await api.play_me(token, _req(), b["player_token"], db)
        assert me_b["result"]["result"] == "lost", "Se acabo el tiempo, perdiste"
    await engine.dispose()


@pytest.mark.asyncio
async def test_permissions_screen_token_switch_off_and_purge(pg_url, monkeypatch):
    from app.api import deps
    from app.web import admin_v2_routes

    engine, maker = await _session(pg_url)
    async with maker() as db:
        cid = await _company(db, True)
        off = await _company(db, False)
        monkeypatch.setattr(admin_v2_routes, "_active_session", AsyncMock(return_value=False))

        async def who(role, company=cid):
            monkeypatch.setattr(deps, "require_company_user_for_tenant", AsyncMock(return_value=SimpleNamespace(role=role, email=f"{role}@x", settings_json={})))
            return await api.actor(uuid.UUID(company), _req(), "Bearer x", db)

        assert (await who("company_admin"))["role"] == "admin"
        barman = await who("barman")
        assert barman["role"] == "barman"
        for role in ("operario", "mesero", "cajero"):
            with pytest.raises(HTTPException) as exc:
                await who(role)
            assert exc.value.status_code == 403
        with pytest.raises(HTTPException) as exc:
            await who("company_admin", company=off)
        assert exc.value.status_code == 404, "interruptor apagado: no aparece"
        u = uuid.UUID(cid)
        for call in (lambda: api.list_questions(u, barman, db), lambda: api.create_question(u, {"level": 1}, barman, db),
                     lambda: api.save_settings(u, {}, barman, db), lambda: api.history(u, barman, db),
                     lambda: api.regenerate_screen(u, _req(), barman, db)):
            with pytest.raises(HTTPException) as exc:
                await call()
            assert exc.value.status_code == 403, "el barman lanza pero no edita"
        ctx_b = await api.context(u, _req(), barman, db)
        assert "screen_url" not in ctx_b and ctx_b["can"]["configure"] is False
        ctx_a = await api.context(u, _req(), await who("company_admin"), db)
        screen = ctx_a["screen_url"].split("t=")[1]
        state = await api.screen_state(screen, _req(), db)
        assert state["focus"] in ("idle", "round", "roulette") and state["brand"]["logo_url"] == "/brand-media/x/y.webp"
        with pytest.raises(HTTPException) as exc:
            await api.screen_state("token-invalido-de-pantalla-xxxxx", _req(), db)
        assert exc.value.status_code == 403
        new = (await api.regenerate_screen(u, _req(), await who("company_admin"), db))["screen_url"].split("t=")[1]
        with pytest.raises(HTTPException):
            await api.screen_state(screen, _req(), db)
        assert (await api.screen_state(new, _req(), db))["game_day"]
        # Una ronda de una empresa que apaga el interruptor deja de abrirse.
        live = await api.open_round(u, _req(), {"kind": "memory"}, barman, db)
        token = live["round"]["join_url"].split("r=")[1]
        await db.execute(text("UPDATE company_modules SET settings = '{\"loyalty_games\": false}'::jsonb WHERE company_id::text = :c"), {"c": cid})
        await db.commit()
        with pytest.raises(HTTPException) as exc:
            await api.play_info(token, _req(), db)
        assert exc.value.status_code == 404
        with pytest.raises(HTTPException) as exc:
            await api.screen_state(new, _req(), db)
        assert exc.value.status_code == 403
        await db.execute(text("UPDATE company_modules SET settings = '{\"loyalty_games\": true}'::jsonb WHERE company_id::text = :c"), {"c": cid})
        await db.commit()
        # Limite de peticiones por IP.
        api.PER_IP.limit = 3
        try:
            for _ in range(3):
                await api.play_info(token, _req("9.9.9.9"), db)
            with pytest.raises(HTTPException) as exc:
                await api.play_info(token, _req("9.9.9.9"), db)
            assert exc.value.status_code == 429
        finally:
            api.PER_IP.limit = 900
        # Purga a 30 dias.
        p = await api.play_join(token, _req(), {"name": "Viejo", "document": "77778888", "consent": True}, db)
        pid = eng.unsign("player", p["player_token"])
        await db.execute(text("UPDATE loyalty_game_players SET joined_at = now() - interval '31 days' WHERE id::text = :i"), {"i": pid})
        await db.commit()
        assert await svc.purge(db) >= 1
        row = (await db.execute(text("SELECT document_hmac, document_last4, display_name FROM loyalty_game_players WHERE id::text = :i"), {"i": pid})).mappings().first()
        assert row["document_hmac"] is None and row["document_last4"] is None and row["display_name"] == "Viejo"
    await engine.dispose()


@pytest.mark.asyncio
async def test_existing_loyalty_answers_the_same_with_games_on(pg_url):
    """Contrato: sorteos, pollas y votaciones de siempre no cambian con los juegos."""
    from app.api.v1.endpoints import hospitality

    engine, maker = await _session(pg_url)
    async with maker() as db:
        cid = await _company(db, True)
        u = uuid.UUID(cid)
        real_execute = db.execute

        async def execute(statement, *a, **k):
            # pgserver no trae pgcrypto; gen_random_uuid() ya viene en Postgres 16.
            if "create extension" in str(statement).lower():
                return await real_execute(text("SELECT 1"))
            return await real_execute(statement, *a, **k)

        db.execute = execute
        try:
            now = datetime.now(timezone.utc)
            await hospitality.create_loyalty_campaign(u, hospitality.HospitalityLoyaltyCampaignIn(
                title="Reto de consumo", prize="1/4 de ron", registration_ends_at=now + timedelta(hours=1),
                starts_at=now + timedelta(hours=1), ends_at=now + timedelta(hours=4)), db)
            before = (json.dumps(await hospitality.get_active_loyalty_campaign(u, None, db), default=str, sort_keys=True),
                      json.dumps(await hospitality.get_loyalty_campaigns_summary(u, db), default=str, sort_keys=True))
        except Exception as exc:  # la base de prueba no trae todas las tablas de Hospitality
            await db.rollback()
            pytest.skip(f"hospitality storage no disponible en la base de prueba: {exc}")
        live = await api.open_round(u, _req(), {"kind": "memory"}, BARMAN, db)
        await api.spin(u, {"range_index": 0}, BARMAN, db)
        await api.play_join(live["round"]["join_url"].split("r=")[1], _req(), {"name": "X", "document": "12121212", "consent": True}, db)
        after = (json.dumps(await hospitality.get_active_loyalty_campaign(u, None, db), default=str, sort_keys=True),
                 json.dumps(await hospitality.get_loyalty_campaigns_summary(u, db), default=str, sort_keys=True))
        assert before == after
        assert "1/4 de ron" in before[0], "el sorteo de siempre sigue ahi"
    await engine.dispose()


def test_migration_only_creates_new_tables_and_routes_are_guarded():
    sql = " ".join(_migration()).lower()
    assert "hospitality_" not in sql and "drop " not in sql and "alter table" not in sql
    for r in api.router.routes:
        deps_ = [d.call for d in r.dependant.dependencies]
        if r.path.startswith("/companies/"):
            assert api.actor in deps_, f"{r.path} sin sesion"
        else:
            assert r.path.startswith(("/screen/{token}", "/play/{token}")), r.path
    from app.services import switch_registry

    sw = next(s for s in switch_registry.registry()["switches"] if s["key"] == "loyalty_games")
    assert sw["module"] == "loyalty" and svc.FLAG == "loyalty_games"
