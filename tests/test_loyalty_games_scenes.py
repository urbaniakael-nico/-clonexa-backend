"""7 diferencias: escenas Bar y Concierto con diferencias CLARAS (medidas pixel a pixel).

- Solo se ofrecen Bar y Concierto; las escenas de antes se siguen dibujando para
  que una ronda abierta antes del cambio termine con su escena y diferencias.
- Bar: 35-50 personas y mas de 120 objetos. Concierto: 90-110 personas en 5 filas.
- Cada escena con 20+ candidatas. Ninguna es solo de tono: los cambios de color
  tienen Delta E >= 35 y las demas cambian un objeto, atributo o letra.
- Cada diferencia: area minima ~0,3 % de la imagen (caja de lo que cambia),
  claramente visible (Delta E >= 20) y nada cambia fuera de su zona.
- Por ronda se eligen 7 con la semilla: iguales para todos en la ronda, distintas
  entre rondas; maximo 4 en personas; nunca 2 en la misma persona u objeto; en
  zonas distintas de la rejilla 3x3 y separadas.
"""
from __future__ import annotations

import math

import pytest

from app.services import loyalty_games_scenes as sc

V2 = ("pub", "concert")
ALL_V2 = [(s, d) for s in V2 for d in sorted(sc.scene(s)[1])]
ALLOWED = {"hat", "glasses", "shirt", "arm", "hair", "object", "text", "color"}


@pytest.fixture(scope="module")
def bases():
    return {s: sc.render(s) for s in V2}


def test_only_bar_and_concert_are_offered_and_old_scenes_still_render():
    assert sc.OFFERED == {"pub": "Bar", "concert": "Concierto"} and sc.DEFAULT_SCENE == "pub"
    for old in ("bar", "stage", "jukebox", "cards"):
        assert old not in sc.OFFERED
        assert sc.png(old, tuple(sc.choose_legacy(old, 7)))[:8] == b"\x89PNG\r\n\x1a\n", "una ronda de antes sigue dibujandose"


def test_people_and_objects_counts():
    assert 35 <= sc.people_count("pub") <= 50
    assert 90 <= sc.people_count("concert") <= 110
    els, _ = sc.scene("pub")
    people_parts = sum(1 for e in els if "." in e["id"] and e["id"].split(".")[0] in {x["id"].split(".")[0] for x in els if x["id"].endswith(".head")})
    assert len(els) - people_parts > 120, "mas de 120 objetos en el Bar"
    for s in V2:
        _, cands = sc.scene(s)
        assert len(cands) >= 20, f"{s}: {len(cands)} candidatas"
        assert {c.kind for c in cands.values()} <= ALLOWED
        assert sum(1 for c in cands.values() if not c.people) >= 8, "suficientes objetos y letreros"


@pytest.mark.parametrize("scene_id,diff_id", ALL_V2)
def test_every_difference_is_clear_big_enough_and_in_its_zone(bases, scene_id, diff_id):
    op = sc.scene(scene_id)[1][diff_id]
    st = sc.diff_stats(scene_id, diff_id, bases[scene_id])
    assert st["bbox_pct"] >= 0.3, f"area {st['bbox_pct']:.2f} %"
    assert st["p90_de"] >= 20, f"poco visible ({st['p90_de']:.1f})"
    assert st["outside"] == 0, "cambia algo fuera de su zona"
    color = getattr(op, "color", None)
    if op.kind in ("shirt", "color") or color:
        assert color and sc.delta_e(*color) >= 35, f"cambio de color de solo tono ({color})"
    else:
        assert getattr(op, "touch", ()) or getattr(op, "adds", ()), "cambia un objeto, atributo o letra"


def test_seven_by_seed_same_for_the_round_different_between_rounds():
    for s in V2:
        _, cands = sc.scene(s)
        seen = set()
        for seed in range(0, 4000, 41):
            ids = sc.choose(s, seed)
            assert ids == sc.choose(s, seed), "mismas para todos en la ronda"
            seen.add(tuple(sorted(ids)))
            zones = [sc.zone(s, d) for d in ids]
            assert len(ids) == 7 and len({cands[d].target for d in ids}) == 7, "nunca 2 en la misma persona u objeto"
            assert sum(1 for d in ids if cands[d].people) <= 4, "maximo 4 en personas"
            assert len({sc.cell_of(z) for z in zones}) == 7, "en zonas distintas"
            for a in zones:
                for b in zones:
                    if a is not b:
                        assert math.hypot(a["cx"] - b["cx"], a["cy"] - b["cy"]) >= sc.MIN_SEPARATION_V2
        assert len(seen) > 80, "distintas entre rondas"


def test_hit_is_fair_inside_the_crowd():
    ids = sc.choose("concert", 11)
    for d in ids:
        z = sc.zone("concert", d)
        x, y = z["cx"] / sc.W, z["cy"] / sc.H
        assert sc.hit("concert", ids, [], x, y)["id"] == d
        edge = (z["cx"] + z["r"] + sc.HIT_TOLERANCE + 2) / sc.W
        assert sc.hit("concert", [d], [], edge, y) is None


def test_images_are_png_and_differ():
    ids = tuple(sc.choose("pub", 3))
    a, b = sc.png("pub"), sc.png("pub", ids)
    assert a[:8] == b"\x89PNG\r\n\x1a\n" and a != b and len(a) < 700_000
