"""Juegos en vivo (interruptor loyalty_games): reglas puras.

- Ruleta: el numero esta en el rango, no repite y avisa al agotarse.
- Memoria: el tablero es igual para todos en la ronda; solo se revela la cara
  volteada; parejas y tiempos en el servidor; ranking por parejas y luego tiempo.
- Trivia: 1 pregunta por nivel; las no respondidas vuelven con otro orden de
  opciones; las mal respondidas no vuelven; fuera de 10 s (+1) se rechaza;
  desempate por tiempo; quien no termina pierde (sin podio).
- Documento: HMAC, nunca el numero; firmas de ronda y jugador.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.services import loyalty_games_engine as eng

NOW = datetime(2026, 10, 17, 2, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def secret(monkeypatch):
    monkeypatch.setenv("LOYALTY_GAMES_SECRET", "test-secret-for-games")


# ---------------------------------------------------------------- ruleta
def test_roulette_in_range_never_repeats_and_warns_when_exhausted():
    drawn: set[int] = set()
    for _ in range(50):
        n = eng.pick_number(1, 50, drawn)
        assert 1 <= n <= 50 and n not in drawn
        drawn.add(n)
    assert drawn == set(range(1, 51))
    with pytest.raises(eng.GameError) as exc:
        eng.pick_number(1, 50, drawn)
    assert exc.value.code == "numeros_agotados"
    with pytest.raises(eng.GameError):
        eng.pick_number(10, 5, set())


# ---------------------------------------------------------------- memoria
def test_board_is_the_same_for_everyone_in_the_round_and_has_five_pairs():
    a, b = eng.board(123456789), eng.board(123456789)
    assert a == b and len(a) == 10 and len(set(a)) == 5 and all(a.count(x) == 2 for x in a)
    assert set(a) <= set(eng.ICONS)
    assert any(eng.board(s) != a for s in range(1, 20)), "otra ronda, otro tablero"


def test_only_flipped_faces_are_revealed():
    seed = 42
    cards = eng.board(seed)
    p = eng.memory_start()
    assert eng.memory_public(p, seed)["faces"] == {}, "sin voltear no se ve ninguna cara"
    p, r = eng.memory_flip(p, seed, 0, 500)
    assert r["faces"] == {"0": cards[0]} and r["match"] is None
    assert eng.memory_public(p, seed)["faces"] == {"0": cards[0]}
    other = next(i for i in range(10) if cards[i] != cards[0])
    p, r = eng.memory_flip(p, seed, other, 900)
    assert r["match"] is False and set(r["faces"]) == {"0", str(other)}
    assert eng.memory_public(p, seed)["faces"] == {}, "un error vuelve a tapar las dos"
    twin = next(i for i in range(1, 10) if cards[i] == cards[0])
    p, _ = eng.memory_flip(p, seed, 0, 1200)
    p, r = eng.memory_flip(p, seed, twin, 1500)
    assert r["match"] is True and p["pairs"] == 1 and p["pair_ms"] == [1500]
    pub = eng.memory_public(p, seed)
    assert set(pub["faces"]) == {"0", str(twin)} and len(pub["faces"]) == 2
    with pytest.raises(eng.GameError):
        eng.memory_flip(p, seed, twin, 1600)
    with pytest.raises(eng.GameError):
        eng.memory_flip(p, seed, 10, 1600)


def _solve(seed, times):
    cards = eng.board(seed)
    p = eng.memory_start()
    seen = set()
    k = 0
    for i in range(10):
        if i in seen:
            continue
        j = next(x for x in range(i + 1, 10) if cards[x] == cards[i])
        seen |= {i, j}
        p, _ = eng.memory_flip(p, seed, i, times[k])
        p, _ = eng.memory_flip(p, seed, j, times[k])
        k += 1
        if k == len(times):
            break
    return p


def test_memory_ranking_by_pairs_then_who_got_there_first():
    seed = 7
    players = [
        {"id": "a", "display_name": "Ana", "joined_at": "1", "progress": _solve(seed, [1000, 2000, 3000])},
        {"id": "b", "display_name": "Beto", "joined_at": "2", "progress": _solve(seed, [900, 1800, 2500])},
        {"id": "c", "display_name": "Cami", "joined_at": "3", "progress": _solve(seed, [500, 800, 1000, 1200])},
        {"id": "d", "display_name": "Dani", "joined_at": "4", "progress": eng.memory_start()},
    ]
    assert [r["name"] for r in eng.live_ranking("memory", players)] == ["Cami", "Beto", "Ana", "Dani"]
    final = {p["id"]: p for p in eng.final_places("memory", players)}
    assert (final["c"]["place"], final["b"]["place"], final["a"]["place"]) == (1, 2, 3)
    assert final["d"]["place"] is None, "con 0 parejas no entra al podio"
    players[0]["hidden"] = True
    assert [r["name"] for r in eng.live_ranking("memory", players)] == ["Cami", "Beto", "Dani"], "quitado de la pantalla"


# ---------------------------------------------------------------- trivia
BANK = [{"id": f"q{lv}{i}", "level": lv, "active": True} for lv in eng.LEVELS for i in range(4)]


def test_one_question_per_level_and_same_for_the_round():
    qids = eng.pick_questions(BANK, 99)
    assert [q[1] for q in qids] == ["1", "2", "3", "4", "5"] and qids == eng.pick_questions(BANK, 99)
    bank = [q for q in BANK if q["level"] != 3] + [{"id": "off", "level": 3, "active": False}]
    with pytest.raises(eng.GameError) as exc:
        eng.pick_questions(bank, 1)
    assert exc.value.code == "falta_pregunta_nivel_3"


def test_unanswered_come_back_with_another_order_and_wrong_ones_do_not():
    qids = eng.pick_questions(BANK, 5)
    p = eng.trivia_start(qids)
    t = NOW
    orders = {}

    def show(p, t):
        p = eng.trivia_tick(p, t)
        orders.setdefault(p["current"]["qid"], []).append(p["current"]["order"])
        return p

    p = show(p, t)  # 1: bien
    p, ok = eng.trivia_answer(p, qids[0], p["current"]["order"].index(0), t + timedelta(seconds=3))
    assert ok
    t += timedelta(seconds=3)
    p = show(p, t)  # 2: mal
    p, ok = eng.trivia_answer(p, qids[1], p["current"]["order"].index(1), t + timedelta(seconds=2))
    assert not ok
    t += timedelta(seconds=2)
    p = show(p, t)  # 3: no responde
    assert p["current"]["qid"] == qids[2]
    for expected in (qids[3], qids[4]):  # 4 y 5 llegan solas al vencerse la anterior
        t += timedelta(seconds=12)
        p = show(p, t)
        assert p["current"]["qid"] == expected and p["lap"] == 1
    t += timedelta(seconds=12)
    p = show(p, t)  # vuelta 2: solo las no contestadas (3, 4, 5); la 2 (mal) no vuelve
    assert p["lap"] == 2 and p["current"]["qid"] == qids[2] and qids[1] not in p["pending"]
    lap2 = []
    for _ in range(3):
        cur = p["current"]
        lap2.append(cur["qid"])
        assert orders[cur["qid"]][-1] != orders[cur["qid"]][0], "vuelve con las opciones en otro orden"
        p, _ = eng.trivia_answer(p, cur["qid"], cur["order"].index(0), t + timedelta(seconds=2))
        t += timedelta(seconds=2)
        if not eng.trivia_done(p):
            p = show(p, t)
    assert lap2 == qids[2:]
    assert eng.trivia_done(p) and eng.trivia_correct(p) == 4 and p["current"] is None


def test_answer_outside_ten_seconds_plus_one_is_rejected():
    p = eng.trivia_tick(eng.trivia_start(["a", "b"]), NOW)
    cur = p["current"]
    eng.trivia_answer(p, cur["qid"], 0, NOW + timedelta(milliseconds=10_900))  # dentro de la tolerancia
    with pytest.raises(eng.GameError) as exc:
        eng.trivia_answer(p, cur["qid"], 0, NOW + timedelta(milliseconds=11_100))
    assert exc.value.code == "fuera_de_tiempo"
    with pytest.raises(eng.GameError):
        eng.trivia_answer(p, "b", 0, NOW)
    assert eng.remaining_ms(p, NOW + timedelta(seconds=4)) == 6000


def test_trivia_ranking_ties_break_by_time_and_unfinished_lose():
    players = [
        {"id": "a", "display_name": "Ana", "score": 4, "score_ms": 90_000, "finished_at": NOW, "joined_at": "1"},
        {"id": "b", "display_name": "Beto", "score": 4, "score_ms": 70_000, "finished_at": NOW, "joined_at": "2"},
        {"id": "c", "display_name": "Cami", "score": 5, "score_ms": 150_000, "finished_at": NOW, "joined_at": "3"},
        {"id": "d", "display_name": "Dani", "score": 3, "score_ms": None, "finished_at": None, "joined_at": "4"},
    ]
    final = {p["id"]: p for p in eng.final_places("trivia", players)}
    assert (final["c"]["place"], final["b"]["place"], final["a"]["place"]) == (1, 2, 3)
    assert final["d"] == {"id": "d", "result": "lost", "place": None}, "con preguntas pendientes: perdio"


# ---------------------------------------------------------------- documento y firmas
def test_document_is_only_an_hmac_and_tokens_are_signed():
    h1 = eng.document_hmac("cid", "1.023.456.789")
    assert h1 == eng.document_hmac("cid", "1023456789") and len(h1) == 64 and "1023456789" not in h1
    assert h1 != eng.document_hmac("otra", "1023456789"), "por empresa"
    assert h1 != eng.document_hmac("cid", "1023456788")
    with pytest.raises(eng.GameError):
        eng.clean_document("12")
    tok = eng.sign("round", "abc")
    assert eng.unsign("round", tok) == "abc"
    assert eng.unsign("player", tok) is None, "un token de ronda no sirve como jugador"
    assert eng.unsign("round", tok[:-1] + ("0" if tok[-1] != "0" else "1")) is None
    assert eng.clean_name("  <b>Camila</b>   la del bar que gana siempre ") == "bCamila/b la del bar"
