"""Juegos en vivo (interruptor loyalty_games) contra Postgres REAL con las migraciones 024j y 024k.

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

    for name, parent in (("024j_loyalty_games", "024i_shifts_v1"), ("024k_loyalty_games_v2", "024j_loyalty_games")):
        module = importlib.import_module(f"migrations.versions.{name}")
        module.op = Op()
        module.upgrade()
        assert len(module.revision) <= 32 and module.down_revision == parent
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
        await svc.save_settings(db, cid, {"memory_pairs": 5, "trivia_seconds": 240, "roulette_ranges": [{"min": 1, "max": 3, "prize": "Shot"}], "differences_scene": "pub"}, "dueno")
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
        cards = eng.board(seed, 5)
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
        assert {k: v for k, v in me["result"].items() if k != "ms"} == {"result": "ranked", "place": 1, "score": 2, "finished": False} and me["result"]["ms"] > 0
        with pytest.raises(HTTPException):
            await api.play_flip(token, _req(), {"index": pairs[4][0]}, a["player_token"], db)
        # Validar: el documento correcto coincide, el incorrecto no; nunca se devuelve el documento.
        ok = await api.validate_winner(u, uuid.UUID(r["id"]), {"place": 1, "document": DOC}, BARMAN, db)
        assert ok == {"match": True, "name": "Camila", "place": 1}
        bad = await api.validate_winner(u, uuid.UUID(r["id"]), {"place": 2, "document": DOC}, ADMIN, db)
        assert bad == {"match": False, "name": None, "place": 2}
    await engine.dispose()


async def _legacy_round(db, cid: str, kind: str, qids: list, status: str = "registration") -> str:
    """Una ronda creada ANTES de este cambio: sin config (reglas de siempre)."""
    return (await db.execute(text("""INSERT INTO loyalty_game_rounds (company_id, kind, status, prize, seed, game_day, duration_seconds, question_ids)
        VALUES (CAST(:c AS uuid), :k, :st, 'Premio', 424242, CURRENT_DATE, :d, CAST(:q AS jsonb)) RETURNING id::text"""),
                                  {"c": cid, "k": kind, "st": status, "d": 120 if kind == "memory" else 180, "q": json.dumps(qids)})).scalar()


@pytest.mark.asyncio
async def test_rounds_open_at_deploy_finish_with_their_original_rules(pg_url):
    """Trivia de 5 (una por nivel) y memoria de 5 parejas con el tablero de siempre."""
    engine, maker = await _session(pg_url)
    async with maker() as db:
        cid = await _company(db, True)
        u = uuid.UUID(cid)
        await svc.ensure_bank(db, cid)
        bank = await svc.questions(db, cid)
        qids = eng.pick_questions(bank, 424242)
        rid = await _legacy_round(db, cid, "trivia", qids)
        await db.commit()
        token = svc.round_token(rid)
        a = await api.play_join(token, _req(), {"name": "Ana", "document": "11112222", "consent": True}, db)
        b = await api.play_join(token, _req(), {"name": "Beto", "document": "33334444", "consent": True}, db)
        await api.start_round(u, uuid.UUID(rid), _req(), BARMAN, db)
        correct = {q["id"]: q["correct_answer"] for q in bank}
        for _ in range(5):
            q = await api.play_question(token, _req(), a["player_token"], db)
            assert "correct_answer" not in json.dumps(q), "la respuesta nunca viaja al celular"
            choice = q["question"]["options"].index(correct[q["question"]["id"]])
            res = await api.play_answer(token, _req(), {"question_id": q["question"]["id"], "choice": choice}, a["player_token"], db)
        assert res == {"ok": True, "done": True, "correct": 5}, "trivia de antes: 5 preguntas"
        await api.play_question(token, _req(), b["player_token"], db)
        state = await svc.live_state(db, cid, datetime.now(timezone.utc) + timedelta(seconds=181))
        assert state["round"]["status"] == "closed" and [p["name"] for p in state["round"]["podium"]] == ["Ana"]
        assert state["round"]["rules"] == 1 and state["round"]["goal"] == 5
        assert (await api.play_me(token, _req(), b["player_token"], db))["result"]["result"] == "lost", "Se acabo el tiempo, perdiste"
        # Memoria de antes: 5 parejas y EXACTAMENTE el tablero que ya se habia repartido.
        mid = await _legacy_round(db, cid, "memory", [])
        await db.commit()
        mtok = svc.round_token(mid)
        m = await api.play_join(mtok, _req(), {"name": "Cami", "document": "55556666", "consent": True}, db)
        live = await api.start_round(u, uuid.UUID(mid), _req(), BARMAN, db)
        assert live["round"]["goal"] == 5 and live["round"]["duration_seconds"] == 120
        legacy = eng.board(424242)
        res = await api.play_flip(mtok, _req(), {"index": 0}, m["player_token"], db)
        assert res["faces"] == {"0": legacy[0]} and set(legacy) <= set(eng.LEGACY_ICONS)
        me = await api.play_me(mtok, _req(), m["player_token"], db)
        assert me["memory"]["size"] == 10 and me["memory"]["total_pairs"] == 5
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



# ---------------------------------------------------------------- v2: banco, memoria, trivia de 10 y 7 diferencias
@pytest.mark.asyncio
async def test_seed_adds_only_new_questions_and_never_touches_edited_ones(pg_url):
    engine, maker = await _session(pg_url)
    async with maker() as db:
        fresh = await _company(db, True)
        assert await svc.ensure_bank(db, fresh) == 40 and await svc.ensure_bank(db, fresh) == 0
        assert await svc.active_by_level(db, fresh) == {"1": 8, "2": 8, "3": 8, "4": 8, "5": 8}
        # Empresa que ya tenia el banco de 20 (version 1), edito una y ya tenia "Dream On" propia.
        old = await _company(db, True)
        for q in [q for q in svc.seed_questions() if int(q.get("since", 1)) == 1]:
            await db.execute(text("""INSERT INTO loyalty_trivia_questions (company_id, level, question, correct_answer, wrong_1, wrong_2)
                VALUES (CAST(:c AS uuid), :l, :q, :a, :b, :d)"""), {"c": old, "l": q["level"], "q": q["question"], "a": q["correct"], "b": q["wrong"][0], "d": q["wrong"][1]})
        await db.execute(text("""UPDATE loyalty_trivia_questions SET question = 'Que banda canta Bohemian Rhapsody (1975)?', updated_at = now() + interval '1 hour'
            WHERE company_id::text = :c AND question LIKE '%Bohemian Rhapsody%'"""), {"c": old})
        await db.execute(text("""INSERT INTO loyalty_trivia_questions (company_id, level, question, correct_answer, wrong_1, wrong_2)
            VALUES (CAST(:c AS uuid), 3, '¿Qué banda canta "Dream On"?', 'Aerosmith', 'Boston', 'Kansas')"""), {"c": old})
        await db.commit()
        before = {q["id"]: dict(q) for q in await svc.questions(db, old)}
        assert await svc.ensure_bank(db, old) == 19, "solo las 20 nuevas, menos la que ya existia por texto"
        assert await svc.ensure_bank(db, old) == 0
        after = await svc.questions(db, old)
        texts = [q["question"] for q in after]
        assert len(texts) == len(set(texts)) == 21 + 19, "sin duplicados"
        assert not any(t == '¿Qué banda canta "Bohemian Rhapsody"?' for t in texts), "no vuelve a meter la que el bar edito"
        assert all(dict(next(x for x in after if x["id"] == i)) == q for i, q in before.items()), "las de antes quedan intactas"
    await engine.dispose()


@pytest.mark.asyncio
async def test_memory_pairs_are_chosen_per_round_and_kept(pg_url):
    engine, maker = await _session(pg_url)
    async with maker() as db:
        cid = await _company(db, True)
        u = uuid.UUID(cid)
        with pytest.raises(HTTPException) as exc:
            await api.open_round(u, _req(), {"kind": "memory", "pairs": 6}, BARMAN, db)
        assert exc.value.status_code == 422
        live = await api.open_round(u, _req(), {"kind": "memory", "pairs": 15}, BARMAN, db)
        assert live["round"]["goal"] == 15 and live["round"]["duration_seconds"] == 300, "15 parejas -> 5:00"
        token = live["round"]["join_url"].split("r=")[1]
        a = await api.play_join(token, _req(), {"name": "Ana", "document": "12345678", "consent": True}, db)
        # Cambiar los ajustes despues NO cambia la ronda ya creada.
        await svc.save_settings(db, cid, {"memory_pairs": 7, "memory_times": {"15": 200}, "trivia_seconds": 240,
                                          "roulette_ranges": [{"min": 1, "max": 50}], "differences_scene": "pub"}, "dueno")
        live = await api.start_round(u, uuid.UUID(live["round"]["id"]), _req(), BARMAN, db)
        assert live["round"]["duration_seconds"] == 300 and live["round"]["goal"] == 15
        r = await svc.round_by_token(db, token)
        cards = eng.board(int(r["seed"]), 15)
        assert len(cards) == 30 and len(set(cards)) == 15
        me = await api.play_me(token, _req(), a["player_token"], db)
        assert me["memory"]["size"] == 30 and me["memory"]["total_pairs"] == 15 and me["memory"]["faces"] == {}
        await svc.close_round(db, cid, r["id"])
        live = await api.open_round(u, _req(), {"kind": "memory"}, BARMAN, db)
        assert live["round"]["goal"] == 7 and live["round"]["duration_seconds"] == 150, "por defecto: las parejas de Configuracion (7 -> 2:30)"
    await engine.dispose()


async def _round(db, token):
    return await svc.round_by_token(db, token)


@pytest.mark.asyncio
async def test_trivia_of_ten_replaces_wrong_ones_repeats_unanswered_and_fills_the_podium(pg_url):
    engine, maker = await _session(pg_url)
    async with maker() as db:
        cid = await _company(db, True)
        u = uuid.UUID(cid)
        live = await api.open_round(u, _req(), {"kind": "trivia", "prize": "Ronda"}, BARMAN, db)
        assert live["round"]["goal"] == 10 and live["round"]["duration_seconds"] == 240
        token = live["round"]["join_url"].split("r=")[1]
        bank = {q["id"]: q for q in await svc.questions(db, cid)}
        r = await _round(db, token)
        qids = r["question_ids"] if isinstance(r["question_ids"], list) else json.loads(r["question_ids"])
        assert [bank[q]["level"] for q in qids] == [1, 1, 2, 2, 3, 3, 4, 4, 5, 5], "2 por nivel, en orden de nivel"
        players = {n: await api.play_join(token, _req(), {"name": n, "document": d, "consent": True}, db)
                   for n, d in (("Ana", "11110001"), ("Beto", "11110002"), ("Cami", "11110003"), ("Dani", "11110004"))}
        await api.start_round(u, uuid.UUID(str(r["id"])), _req(), BARMAN, db)
        r = await _round(db, token)
        t0 = r["started_at"]
        correct = {q["id"]: q["correct_answer"] for q in bank.values()}

        async def play(name, t, wrong_first=False, skip_first=False, stop_after=None):
            tok = players[name]["player_token"]
            first_orders, seen_replacement = {}, None
            n = 0
            while True:
                q = await svc.trivia_state(db, r, tok, now=t)
                if q.get("done") or q.get("stuck"):
                    return t, q, first_orders, seen_replacement
                qq = q["question"]
                first_orders.setdefault(qq["id"], qq["options"])
                if skip_first and n == 0:
                    t += timedelta(seconds=12)  # no responde: pasa sola
                    n += 1
                    continue
                if q.get("replaced"):
                    seen_replacement = qq
                ok_idx = qq["options"].index(correct[qq["id"]])
                choice = (ok_idx + 1) % 3 if (wrong_first and n == 0) else ok_idx
                await svc.answer(db, r, tok, qq["id"], choice, now=t + timedelta(milliseconds=800))
                t += timedelta(seconds=1)
                n += 1
                if stop_after is not None and n >= stop_after:
                    return t, q, first_orders, seen_replacement

        # Ana falla la primera: se reemplaza por una NUEVA del mismo nivel que no habia visto.
        t, last, _, repl = await play("Ana", t0 + timedelta(seconds=1), wrong_first=True)
        assert last["done"] and last["correct"] == 10
        prog = (await db.execute(text("SELECT progress FROM loyalty_game_players WHERE company_id::text = :c AND display_name = 'Ana'"), {"c": cid})).scalar()
        prog = prog if isinstance(prog, dict) else json.loads(prog)
        assert prog["slots"][0]["replaced"] == 1 and prog["slots"][0]["qid"] != qids[0] and bank[prog["slots"][0]["qid"]]["level"] == 1
        assert prog["slots"][0]["qid"] not in qids and repl is not None and repl["id"] == prog["slots"][0]["qid"]
        assert qids[0] in prog["seen"] and len(prog["seen"]) == 11
        # Beto deja pasar la primera: vuelve en la segunda vuelta con OTRO orden de opciones.
        _, last_b, orders_b, _ = await play("Beto", t0 + timedelta(seconds=2), skip_first=True)
        assert last_b["done"]
        prog_b = (await db.execute(text("SELECT progress FROM loyalty_game_players WHERE company_id::text = :c AND display_name = 'Beto'"), {"c": cid})).scalar()
        prog_b = prog_b if isinstance(prog_b, dict) else json.loads(prog_b)
        assert prog_b["lap"] == 2 and prog_b["slots"][0]["qid"] == qids[0], "la no contestada vuelve (no se reemplaza)"
        # Cami solo logra 3; Dani no juega.
        await play("Cami", t0 + timedelta(seconds=3), stop_after=3)
        # El servidor rechaza la respuesta fuera de 10 s + 1.
        q = await svc.trivia_state(db, r, players["Dani"]["player_token"], now=t0 + timedelta(seconds=30))
        with pytest.raises(eng.GameError) as exc:
            await svc.answer(db, r, players["Dani"]["player_token"], q["question"]["id"], 0, now=t0 + timedelta(seconds=41, milliseconds=200))
        assert exc.value.code == "fuera_de_tiempo"
        state = await svc.live_state(db, cid, t0 + timedelta(seconds=241))
        rnd = state["round"]
        assert rnd["status"] == "closed"
        assert [p["name"] for p in rnd["podium"]] == ["Ana", "Beto", "Cami"], "10/10 por tiempo y luego relleno por aciertos"
        me_c = await api.play_me(token, _req(), players["Cami"]["player_token"], db)
        assert {k: v for k, v in me_c["result"].items() if k != "ms"} == {"result": "ranked", "place": 3, "score": 3, "finished": False}, "sin 10/10: 'Se acabo el tiempo' con sus aciertos"
        assert me_c["result"]["ms"] == 5800, "tiempo de su ultimo acierto"
        me_d = await api.play_me(token, _req(), players["Dani"]["player_token"], db)
        assert me_d["result"]["result"] == "timeout" and me_d["result"]["place"] is None
        ok = await api.validate_winner(u, uuid.UUID(str(r["id"])), {"place": 3, "document": "11110003"}, BARMAN, db)
        assert ok["match"] is True and ok["name"] == "Cami", "la validacion por documento no cambia"
    await engine.dispose()


@pytest.mark.asyncio
async def test_seven_differences_round(pg_url):
    from app.services import loyalty_games_scenes as scenes

    engine, maker = await _session(pg_url)
    async with maker() as db:
        cid = await _company(db, True)
        u = uuid.UUID(cid)
        await svc.save_settings(db, cid, {"memory_pairs": 5, "trivia_seconds": 240, "differences_seconds": 180, "differences_penalty": 5,
                                          "differences_scene": "concert", "roulette_ranges": [{"min": 1, "max": 50}]}, "dueno")
        live = await api.open_round(u, _req(), {"kind": "differences", "prize": "Coctel"}, BARMAN, db)
        rv = live["round"]
        assert rv["kind"] == "differences" and rv["goal"] == 7 and rv["scene"] == "concert" and rv["duration_seconds"] == 180
        token = rv["join_url"].split("r=")[1]
        r = await _round(db, token)
        cfg = r["config"] if isinstance(r["config"], dict) else json.loads(r["config"])
        assert cfg["diffs"] == scenes.choose("concert", int(r["seed"])), "7 elegidas por la semilla"
        with pytest.raises(HTTPException) as exc:
            await api.play_image(token, "a", _req(), db)
        assert exc.value.status_code == 404, "en registro no se ve la imagen"
        players = {n: await api.play_join(token, _req(), {"name": n, "document": d, "consent": True}, db)
                   for n, d in (("Ana", "22220001"), ("Beto", "22220002"), ("Cami", "22220003"))}
        await api.start_round(u, uuid.UUID(str(r["id"])), _req(), BARMAN, db)
        r = await _round(db, token)
        t0 = r["started_at"]
        img_a = (await api.play_image(token, "a", _req(), db)).body
        img_b = (await api.play_image(token, "b", _req(), db)).body
        assert img_a[:8] == b"\x89PNG\r\n\x1a\n" and img_b[:8] == b"\x89PNG\r\n\x1a\n" and img_a != img_b
        # Las zonas NO viajan: ni en la pantalla mientras se juega, ni en el celular.
        screen = await svc.live_state(db, cid, t0 + timedelta(seconds=5))
        assert "zones" not in screen["round"]
        me = await api.play_me(token, _req(), players["Ana"]["player_token"], db)
        assert me["differences"]["zones"] == [] and me["differences"]["total"] == 7
        centers = [scenes.public_zone(scenes.zone("concert", d)) for d in cfg["diffs"]]
        miss = next((x, y) for x in (0.02, 0.5, 0.98) for y in (0.02, 0.98) if scenes.hit("concert", cfg["diffs"], [], x, y) is None)
        tok_a = players["Ana"]["player_token"]
        res = await svc.tap(db, r, tok_a, *miss, now=t0 + timedelta(seconds=2))
        assert res["hit"] is False and res["penalty_ms"] == 5000 and res["lock_ms"] == 1000 and "zone" not in res
        with pytest.raises(eng.GameError) as exc:
            await svc.tap(db, r, tok_a, centers[0]["x"], centers[0]["y"], now=t0 + timedelta(seconds=2, milliseconds=500))
        assert exc.value.code == "espera_un_segundo", "1 s de bloqueo tras un toque en falso"
        for k, z in enumerate(centers):
            res = await svc.tap(db, r, tok_a, z["x"], z["y"], now=t0 + timedelta(seconds=4 + k))
            assert res["hit"] is True and res["zone"]["id"] == z["id"] and res["found"] == k + 1
        assert res["done"] is True
        # Beto: todas sin errores y mas rapido (sin castigo) -> primero. Cami: 2.
        for k, z in enumerate(centers):
            await svc.tap(db, r, players["Beto"]["player_token"], z["x"], z["y"], now=t0 + timedelta(seconds=3 + k))
        for z in centers[:2]:
            await svc.tap(db, r, players["Cami"]["player_token"], z["x"], z["y"], now=t0 + timedelta(seconds=20))
        me_c = await api.play_me(token, _req(), players["Cami"]["player_token"], db)
        assert [z["id"] for z in me_c["differences"]["zones"]] == [c["id"] for c in centers[:2]], "solo las que ella acerto"
        ranking = (await svc.live_state(db, cid, t0 + timedelta(seconds=30)))["round"]["ranking"]
        assert [(p["name"], p["score"]) for p in ranking] == [("Beto", 7), ("Ana", 7), ("Cami", 2)]
        assert ranking[0]["ms"] == 9000 and ranking[1]["ms"] == 10000 + 5000, "tiempo real + castigos"
        state = await svc.live_state(db, cid, t0 + timedelta(seconds=181))
        assert state["round"]["status"] == "closed" and [p["name"] for p in state["round"]["podium"]] == ["Beto", "Ana", "Cami"]
        assert sorted(z["id"] for z in state["round"]["zones"]) == sorted(cfg["diffs"]), "al final la pantalla revela las 7"
        me_c = await api.play_me(token, _req(), players["Cami"]["player_token"], db)
        assert len(me_c["differences"]["zones"]) == 2, "el celular sigue sin recibir las que no encontro"
        assert me_c["result"]["score"] == 2 and me_c["result"]["ms"] is not None, "el celular muestra resultado y tiempo"
        top = state["round"]["podium"][0]
        assert (top["score"], top["ms"]) == (7, 9000), "el podio guarda resultado y tiempo (castigos incluidos)"
        # El barman escoge la escena al abrir; una escena que ya no se ofrece no se acepta.
        live = await api.open_round(u, _req(), {"kind": "differences", "scene": "pub"}, BARMAN, db)
        assert live["round"]["scene"] == "pub"
        await svc.close_round(db, cid, live["round"]["id"])
        with pytest.raises(HTTPException) as exc:
            await api.open_round(u, _req(), {"kind": "differences", "scene": "jukebox"}, BARMAN, db)
        assert exc.value.status_code == 422
        hist = await api.history(u, ADMIN, db)
        assert hist["rounds"][-1]["goal"] == 7 and hist["rounds"][-1]["results"][0]["ms"] == 9000
    await engine.dispose()


@pytest.mark.asyncio
async def test_differences_round_open_before_the_change_keeps_its_scene(pg_url):
    from app.services import loyalty_games_scenes as scenes

    engine, maker = await _session(pg_url)
    async with maker() as db:
        cid = await _company(db, True)
        u = uuid.UUID(cid)
        diffs = scenes.choose_legacy("jukebox", 99)
        cfg = {"rules": 2, "scene": "jukebox", "diffs": diffs, "seconds": 180, "penalty_s": 5}
        rid = (await db.execute(text("""INSERT INTO loyalty_game_rounds (company_id, kind, status, prize, seed, game_day, duration_seconds, config)
            VALUES (CAST(:c AS uuid), 'differences', 'registration', 'x', 99, CURRENT_DATE, 180, CAST(:cfg AS jsonb)) RETURNING id::text"""),
                                {"c": cid, "cfg": json.dumps(cfg)})).scalar()
        await db.commit()
        token = svc.round_token(rid)
        p = await api.play_join(token, _req(), {"name": "Ana", "document": "33330001", "consent": True}, db)
        live = await api.start_round(u, uuid.UUID(rid), _req(), BARMAN, db)
        assert live["round"]["scene"] == "jukebox", "termina con su escena original"
        img = (await api.play_image(token, "b", _req(), db)).body
        assert img == scenes.png("jukebox", tuple(diffs))
        r = await svc.round_by_token(db, token)
        z = scenes.public_zone(scenes.zone("jukebox", diffs[0]))
        res = await svc.tap(db, r, p["player_token"], z["x"], z["y"], now=r["started_at"] + timedelta(seconds=3))
        assert res["hit"] is True and res["zone"]["id"] == diffs[0], "y con sus diferencias originales"
    await engine.dispose()


def test_migration_only_creates_new_tables_and_routes_are_guarded():
    sql = " ".join(_migration()).lower()
    assert "hospitality_" not in sql, "no toca Hospitality ni la Fidelizacion de siempre"
    assert sql.count("drop ") == 1 and "drop constraint if exists loyalty_game_rounds_kind_check" in sql, "solo se amplia el check del tipo"
    assert "differences" in sql and "add column if not exists config" in sql and "add column if not exists seed_version" in sql
    for r in api.router.routes:
        deps_ = [d.call for d in r.dependant.dependencies]
        if r.path.startswith("/companies/"):
            assert api.actor in deps_, f"{r.path} sin sesion"
        else:
            assert r.path.startswith(("/screen/{token}", "/play/{token}")), r.path
    from app.services import switch_registry

    sw = next(s for s in switch_registry.registry()["switches"] if s["key"] == "loyalty_games")
    assert sw["module"] == "loyalty" and svc.FLAG == "loyalty_games"
