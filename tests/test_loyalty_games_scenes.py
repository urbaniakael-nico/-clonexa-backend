"""7 diferencias: las escenas son detalladas y "super dificiles" pero justas.

Se mide de verdad, pixel a pixel (imagen A contra imagen B ya dibujadas):
- cada escena tiene 60+ formas y 15+ diferencias candidatas;
- cada diferencia: zona entre ~1 % y 3 % de la imagen; cambia al menos 0,08 %
  de los pixeles (visible con atencion y zoom); diferencia de color perceptible
  (Delta E >= 8); los cambios de tono son sutiles (Delta E entre 8 y 15); y
  NADA cambia fuera de su zona;
- por ronda se eligen 7 con la semilla, en 7 zonas distintas de la rejilla 3x3
  y separadas; el acierto se valida en el servidor con un radio justo.
"""
from __future__ import annotations

import math

import pytest

from app.services import loyalty_games_scenes as sc

ALL = [(s, d) for s in sc.SCENES for d in sorted(sc.scene(s)[1])]


@pytest.fixture(scope="module")
def bases():
    return {s: sc.render(s) for s in sc.SCENES}


def test_scenes_are_detailed_and_offer_enough_candidates():
    for s in sc.SCENES:
        els, cands = sc.scene(s)
        assert len(els) >= 60, f"{s}: {len(els)} formas"
        assert len(cands) >= 15, f"{s}: {len(cands)} candidatas"
        assert len({sc.cell_of(sc.zone(s, d)) for d in cands}) == 9, f"{s}: candidatas en las 9 zonas"
    assert set(sc.SCENES) == {"bar", "stage", "jukebox", "cards"}


@pytest.mark.parametrize("scene_id,diff_id", ALL)
def test_every_difference_has_minimum_area_and_color_and_stays_in_its_zone(bases, scene_id, diff_id):
    st = sc.diff_stats(scene_id, diff_id, bases[scene_id])
    assert 1.0 <= st["zone_pct"] <= 3.0, f"zona {st['zone_pct']:.2f} %"
    assert st["area_pct"] >= 0.08, f"area cambiada {st['area_pct']:.3f} %"
    assert st["p90_de"] >= 8, f"diferencia de color {st['p90_de']:.1f}"
    assert st["outside"] == 0, "cambia algo fuera de su zona"
    if st["recolor_de"] is not None:
        assert 8 <= st["recolor_de"] <= 15, f"tono {st['recolor_de']}"


def test_seven_are_chosen_by_seed_in_different_zones_and_far_apart():
    for s in sc.SCENES:
        for seed in range(0, 3000, 37):
            ids = sc.choose(s, seed)
            assert ids == sc.choose(s, seed), "determinista"
            zones = [sc.zone(s, d) for d in ids]
            assert len(ids) == 7 and len({sc.cell_of(z) for z in zones}) == 7
            for a in zones:
                for b in zones:
                    if a is not b:
                        assert math.hypot(a["cx"] - b["cx"], a["cy"] - b["cy"]) >= sc.MIN_SEPARATION
    assert sc.pick_scene(["cards"], 5) == "cards" and sc.pick_scene([], 5) in sc.SCENES


def test_hit_radius_is_small_and_fair():
    ids = sc.choose("bar", 11)
    for d in ids:
        z = sc.zone("bar", d)
        x, y = z["cx"] / sc.W, z["cy"] / sc.H
        assert sc.hit("bar", ids, [], x, y)["id"] == d, "en el centro acierta"
        edge = (z["cx"] + z["r"] + sc.HIT_TOLERANCE + 2) / sc.W
        assert sc.hit("bar", [d], [], edge, y) is None, "un poco por fuera, no"
        assert sc.hit("bar", ids, [d], x, y) is None or sc.hit("bar", ids, [d], x, y)["id"] != d, "una ya encontrada no cuenta dos veces"


def test_images_are_png_and_a_differs_from_b():
    ids = tuple(sc.choose("jukebox", 3))
    a, b = sc.png("jukebox"), sc.png("jukebox", ids)
    assert a[:8] == b"\x89PNG\r\n\x1a\n" and b[:8] == b"\x89PNG\r\n\x1a\n" and a != b
    assert len(a) < 400_000, "imagen liviana"
