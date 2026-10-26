"""Menu video: remasterizado y clips (Pillow + ffmpeg, sin IA) y utilidades.

- Foto -> remasterizada vertical 3:4, maximo 1080 px, WebP; la original se
  guarda aparte (misma foto, sin metadatos).
- 1 foto (Acercamiento, Paneo) y 2 fotos (Frente a perfil): clip de 3 s,
  540x960, 25 fps, H.264 sin audio, menos de 400 KB, con portada WebP; el
  bucle no salta (el ultimo instante es el primero).
- Foto dañada, vacia o que no es imagen: error controlado.
"""
from __future__ import annotations

import io
import random
from datetime import datetime, timezone

import pytest
from PIL import Image, ImageChops, ImageDraw, ImageFilter

from app.services import menu_media as mm
from app.services import menu_video as mv

pytestmark = pytest.mark.skipif(mm.ffmpeg_path() is None, reason="sin ffmpeg en este equipo")


def dish_photo(seed: int, w: int = 1600, h: int = 1200, fmt: str = "JPEG") -> bytes:
    """Un "plato" de prueba: plato blanco con comida de colores sobre una mesa."""
    rnd = random.Random(seed)
    image = Image.new("RGB", (w, h), (120, 95, 70))
    draw = ImageDraw.Draw(image)
    cx, cy = w * (0.35 + 0.2 * rnd.random()), h * 0.55
    draw.ellipse((cx - w * 0.25, cy - h * 0.32, cx + w * 0.25, cy + h * 0.32), fill=(236, 236, 230))
    for _ in range(160):
        x, y, r = cx + rnd.uniform(-w * 0.17, w * 0.17), cy + rnd.uniform(-h * 0.22, h * 0.22), rnd.uniform(8, 40)
        draw.ellipse((x - r, y - r, x + r, y + r), fill=(rnd.randint(140, 240), rnd.randint(40, 170), rnd.randint(10, 90)))
    image = image.filter(ImageFilter.GaussianBlur(1.1))
    out = io.BytesIO()
    image.save(out, fmt, **({"quality": 90} if fmt == "JPEG" else {}))
    return out.getvalue()


def test_remasterizada_vertical_y_la_original_se_guarda():
    image = mm.load(dish_photo(1))
    original, w, h = mm.normalize(image)
    assert Image.open(io.BytesIO(original)).format == "WEBP" and (w, h) == (1600, 1200), "original: la misma foto"
    result = mm.remaster(image)
    assert Image.open(io.BytesIO(result.data)).format == "WEBP"
    assert result.height <= 1080 and abs(result.width / result.height - 3 / 4) < 0.01, "vertical 3:4, maximo 1080"
    assert ImageChops.difference(result.image.resize((60, 80)), mm.crop_vertical(image, (0.5, 0.5)).resize((60, 80))).getbbox(), \
        "la remasterizada cambia luz/color"


def test_el_recorte_sigue_al_plato():
    image = mm.load(dish_photo(3, w=2400, h=1000))
    cx, _cy = mm.dish_center(image)
    assert 0.3 < cx < 0.7


def _check_clip(clip: mm.Clip):
    info = mm.probe(clip.video)
    assert info["width"] == 540 and info["height"] == 960
    assert info["fps"] == 25.0 and abs(info["seconds"] - 3.0) < 0.05
    assert info["h264"] and not info["audio"]
    assert len(clip.video) < 400 * 1024, len(clip.video)
    assert clip.video[4:8] == b"ftyp"
    assert clip.video.find(b"moov") < clip.video.find(b"mdat"), "faststart: el indice va antes de los datos"
    poster = Image.open(io.BytesIO(clip.poster))
    assert poster.format == "WEBP" and poster.size == (540, 960)


@pytest.mark.parametrize("style,expected", [("auto", "zoom"), ("zoom", "zoom"), ("pan", "pan"), ("front_side", "zoom")])
def test_clip_con_una_foto(style, expected):
    front = mm.remaster(mm.load(dish_photo(4))).image
    clip = mm.make_clip(front, None, style)
    assert clip.style == expected, "Frente a perfil sin perfil cae en Acercamiento"
    _check_clip(clip)


def test_clip_con_dos_fotos_frente_a_perfil():
    front = mm.remaster(mm.load(dish_photo(5))).image
    side = mm.remaster(mm.load(dish_photo(6))).image
    clip = mm.make_clip(front, side, "auto")
    assert clip.style == "front_side"
    _check_clip(clip)


@pytest.mark.parametrize("style", ["zoom", "pan", "front_side"])
def test_el_bucle_no_salta(style):
    front = mm.compose(mm.remaster(mm.load(dish_photo(7))).image)
    side = mm.compose(mm.remaster(mm.load(dish_photo(8))).image)
    first, last = mm.frame_at(style, 0.0, front, side), mm.frame_at(style, 1.0, front, side)
    assert ImageChops.difference(first, last).getbbox() is None


@pytest.mark.parametrize("raw,message", [
    (b"", "vacía"),
    (b"esto no es una foto", "dañada"),
    (dish_photo(9)[:4000], "dañada"),
    (b"<svg xmlns='http://www.w3.org/2000/svg'></svg>", "dañada"),
])
def test_foto_dañada_error_controlado(raw, message):
    with pytest.raises(mm.MediaRejected) as error:
        mm.load(raw)
    assert message in str(error.value)


def test_foto_muy_pequeña():
    with pytest.raises(mm.MediaRejected):
        mm.load(dish_photo(10, w=120, h=100))


def test_png_con_transparencia_sale_en_rgb():
    image = Image.new("RGBA", (400, 400), (0, 0, 0, 0))
    out = io.BytesIO()
    image.save(out, "PNG")
    assert mm.load(out.getvalue()).mode == "RGB"


# ------------------------------------------------------------ utilidades
@pytest.mark.parametrize("value,expected", [("$ 12.500", 12500), ("12,500", 12500), (28000, 28000), ("15.9", 15.9),
                                             ("1.250.000", 1250000), ("", None), ("gratis", None), (None, None)])
def test_precio_de_la_carta(value, expected):
    assert mv.price_of(value) == expected


def test_emparejar_fotos_por_nombre():
    dishes = [{"ref": "a", "nombre": "Lomo saltado"}, {"ref": "b", "nombre": "Ají de gallina"}, {"ref": "c", "nombre": "Limonada de coco"}]
    assert mv.match_photo("lomo-saltado.jpg", dishes) == ("a", "front")
    assert mv.match_photo("LOMO_SALTADO_perfil.JPG", dishes) == ("a", "side")
    assert mv.match_photo("aji de gallina 2.png", dishes) == ("b", "side")
    assert mv.match_photo("IMG_2231.jpg", dishes) == (None, "front")
    assert mv.match_photo("limonada-coco-frente.webp", dishes) == ("c", "front")


def test_tabla_limpia_con_ref_estable():
    table = mv.clean_table({"categorias": [{"nombre": "entradas", "subcategorias": [{"nombre": "frías"}]}],
                            "platos": [{"categoria": "Entradas", "subcategoria": "Frías", "nombre": "  Ceviche  ", "precio": "$ 24.000",
                                        "opciones": ["Picante", {"nombre": "Sin cebolla"}]},
                                       {"nombre": ""}, {"categoria": "", "nombre": "Pan"}]})
    assert [c["nombre"] for c in table["categorias"]] == ["ENTRADAS", "OTROS"]
    ceviche = table["platos"][0]
    assert ceviche["nombre"] == "Ceviche" and ceviche["precio"] == 24000 and ceviche["opciones"] == "Picante, Sin cebolla"
    assert len(table["platos"]) == 2 and table["platos"][1]["categoria"] == "OTROS"
    again = mv.clean_table(table)
    assert [d["ref"] for d in again["platos"]] == [d["ref"] for d in table["platos"]], "el ref no cambia al editar"


def test_mes_del_cupo_en_hora_de_bogota():
    # 1 de noviembre 03:00 UTC = 31 de octubre 22:00 en Bogota
    assert mv.month_key(datetime(2026, 11, 1, 3, 0, tzinfo=timezone.utc)) == "2026-10"
    assert mv.month_key(datetime(2026, 11, 1, 5, 0, tzinfo=timezone.utc)) == "2026-11"


def test_el_clip_usa_la_foto_completa_sin_recortar_el_plato():
    image = mm.load(dish_photo(11, w=2400, h=1200))
    for use in (True, False):
        src = mm.clip_source(image, use)
        assert abs(src.width / src.height - 2.0) < 0.01, "misma proporción que la original: nada se corta"
        assert max(src.size) <= 1440
    assert ImageChops.difference(mm.clip_source(image, True), mm.clip_source(image, False)).getbbox(), "con remasterizado cambia luz y color"
