"""Menu video: remasterizado y clips (Pillow + OpenCV + ffmpeg, sin IA) y utilidades.

- Foto -> remasterizada (original guardada aparte); el recorte 3:4 solo si el
  plato completo cabe: nunca corta el plato.
- Clip v2: 720x1280, 25 fps, 3 s, H.264 sin audio, faststart, < 600 KB, con
  portada del plato completo. La foto ENTERA cabe en el cuadro (relleno con la
  misma foto difuminada, nunca negro); el plato queda arriba (~38 % del alto)
  y nunca sale del cuadro ni baja a la tarjeta del precio, ni en el
  acercamiento maximo (8 %). Fotos horizontal, vertical y cuadrada.
- 1, 2 y 3 fotos (desde arriba -> frente -> perfil): 3 s en bucle sin salto.
- Deteccion del plato (circulo/elipse); si falla, el centro sin cortar.
- Foto dañada, vacia o que no es imagen: error controlado.
"""
from __future__ import annotations

import io
import random
from datetime import datetime, timezone

import pytest
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageStat

from app.services import menu_media as mm
from app.services import menu_video as mv

pytestmark = pytest.mark.skipif(mm.ffmpeg_path() is None, reason="sin ffmpeg en este equipo")


def dish_photo(seed: int, w: int = 1600, h: int = 1200, fmt: str = "JPEG", cx: float | None = None, cy: float = 0.55) -> bytes:
    """Un "plato" de prueba: plato blanco redondo con comida de colores sobre una mesa."""
    rnd = random.Random(seed)
    image = Image.new("RGB", (w, h), (120, 95, 70))
    draw = ImageDraw.Draw(image)
    cx = w * (cx if cx is not None else 0.35 + 0.2 * rnd.random())
    cy = h * cy
    r = min(w, h) * 0.3
    draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(236, 236, 230), outline=(200, 200, 196), width=6)
    for _ in range(160):
        x, y, rr = cx + rnd.uniform(-r * 0.6, r * 0.6), cy + rnd.uniform(-r * 0.6, r * 0.6), rnd.uniform(6, r * 0.12)
        draw.ellipse((x - rr, y - rr, x + rr, y + rr), fill=(rnd.randint(140, 240), rnd.randint(40, 170), rnd.randint(10, 90)))
    image = image.filter(ImageFilter.GaussianBlur(1.1))
    out = io.BytesIO()
    image.save(out, fmt, **({"quality": 90} if fmt == "JPEG" else {}))
    return out.getvalue()


def test_remasterizada_y_la_original_se_guarda():
    image = mm.load(dish_photo(1))
    original, w, h = mm.normalize(image)
    assert Image.open(io.BytesIO(original)).format == "WEBP" and (w, h) == (1600, 1200), "original: la misma foto"
    result = mm.remaster(image)
    assert Image.open(io.BytesIO(result.data)).format == "WEBP" and result.height <= 1080


def test_el_remasterizado_no_corta_un_plato_ancho():
    # plato que ocupa casi todo el ancho de una foto horizontal: el 3:4 lo cortaria
    raw = dish_photo(2, w=2000, h=1000, cx=0.5, cy=0.5)
    image = mm.load(raw)
    dish = mm.detect_dish(image)
    out = mm.safe_crop(image, mm.Dish(dish.cx, dish.cy, 0.95, 0.9, "plato"))
    assert out.size == image.size, "si el plato no cabe en 3:4, la foto entera"


def test_detecta_el_plato_y_si_falla_el_centro():
    image = mm.load(dish_photo(3, w=1600, h=1200, cx=0.3, cy=0.45))
    dish = mm.detect_dish(image)
    assert dish.source in ("plato", "color")
    assert abs(dish.cx - 0.3) < 0.12 and abs(dish.cy - 0.45) < 0.12, dish
    flat = Image.new("RGB", (800, 600), (128, 128, 128))
    assert mm.detect_dish(flat) == mm.CENTER, "sin plato ni color: el centro (y no se corta nada)"


@pytest.mark.parametrize("w,h", [(1600, 1000), (1000, 1600), (1200, 1200)], ids=["horizontal", "vertical", "cuadrada"])
def test_el_plato_completo_siempre_visible_y_arriba_de_la_tarjeta(w, h):
    image = mm.clip_source(mm.load(dish_photo(4, w=w, h=h, cx=0.5, cy=0.6)), True)
    shot = mm.compose(image)
    W, H = shot.canvas.size
    x0, y0, x1, y1 = shot.photo_box
    assert x0 >= 0 and y0 >= 0 and x1 <= W and y1 <= H, "la foto ENTERA cabe en el cuadro"
    assert y1 <= H * 0.70 + 1, "la foto queda encima de la tarjeta del precio"
    for frame in range(0, 75, 3):
        z = mm.zoom_at(shot, frame / 75)
        assert 1.0 <= z <= mm.MAX_ZOOM + 1e-9
        left, top, right, bottom = mm.view_box(shot, z)
        dx0, dy0, dx1, dy1 = shot.dish_box
        assert dx0 >= left - 1 and dy0 >= top - 1 and dx1 <= right + 1 and dy1 <= bottom + 1, "el plato nunca sale del cuadro"
    # nunca bordes negros: arriba y abajo va la misma foto difuminada
    frame0 = mm.render(shot, 1.0)
    for box in ((0, 0, mm.CLIP_W, 40), (0, mm.CLIP_H - 40, mm.CLIP_W, mm.CLIP_H)):
        mean = ImageStat.Stat(frame0.crop(box)).mean
        assert sum(mean) / 3 > 25, f"franja negra en {box}: {mean}"
    assert abs(mm.DISH_Y * H - (y0 + (y1 - y0) * 0.6)) < H * 0.06 or y0 == 0, "plato a ~38 % del alto"


def _check_clip(clip: mm.Clip):
    info = mm.probe(clip.video)
    assert info["width"] == 720 and info["height"] == 1280
    assert info["fps"] == 25.0 and abs(info["seconds"] - 3.0) < 0.05
    assert info["h264"] and not info["audio"]
    assert len(clip.video) < 600 * 1024, len(clip.video)
    assert clip.video[4:8] == b"ftyp"
    assert clip.video.find(b"moov") < clip.video.find(b"mdat"), "faststart: el indice va antes de los datos"
    poster = Image.open(io.BytesIO(clip.poster))
    assert poster.format == "WEBP" and poster.size == (720, 1280)


@pytest.mark.parametrize("n", [1, 2, 3])
def test_clip_con_1_2_y_3_fotos(n):
    photos = [mm.clip_source(mm.load(dish_photo(10 + i, w=(1600, 1000, 1200)[i], h=(1000, 1600, 1200)[i])), True) for i in range(n)]
    clip = mm.make_clip(photos)
    assert clip.style == "suave" and len(clip.sources) == n
    _check_clip(clip)


@pytest.mark.parametrize("n", [1, 2, 3])
def test_el_bucle_no_salta(n):
    shots = [mm.compose(mm.clip_source(mm.load(dish_photo(20 + i)), True)) for i in range(n)]
    total = mm.CLIP_FPS * mm.CLIP_SECONDS
    assert ImageChops.difference(mm.frame_at(shots, 0, total), mm.frame_at(shots, total, total)).getbbox() is None
    if n > 1:
        # el fundido entre fotos dura ~0,3 s
        fade = mm.CLIP_FPS * mm.FADE_SECONDS
        seg = total / n
        assert ImageChops.difference(mm.frame_at(shots, int(seg), total), mm.frame_at(shots, int(seg + fade) + 1, total)).getbbox()


def test_compatibilidad_make_clip_frente_y_perfil():
    a = mm.clip_source(mm.load(dish_photo(30)), True)
    b = mm.clip_source(mm.load(dish_photo(31)), True)
    assert len(mm.make_clip(a, b, "front_side").sources) == 2


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


def test_el_clip_usa_la_foto_completa_sin_recortar_el_plato():
    image = mm.load(dish_photo(11, w=2400, h=1200))
    for use in (True, False):
        src = mm.clip_source(image, use)
        assert abs(src.width / src.height - 2.0) < 0.01, "misma proporción que la original: nada se corta"
        assert max(src.size) <= 1600
    assert ImageChops.difference(mm.clip_source(image, True), mm.clip_source(image, False)).getbbox(), "con remasterizado cambia luz y color"


# ------------------------------------------------------------ utilidades
@pytest.mark.parametrize("value,expected", [("$ 12.500", 12500), ("12,500", 12500), (28000, 28000), ("15.9", 15.9),
                                             ("1.250.000", 1250000), ("", None), ("gratis", None), (None, None)])
def test_precio_de_la_carta(value, expected):
    assert mv.price_of(value) == expected


def test_emparejar_fotos_por_nombre():
    dishes = [{"ref": "a", "nombre": "Lomo saltado"}, {"ref": "b", "nombre": "Ají de gallina"}, {"ref": "c", "nombre": "Limonada de coco"},
              {"ref": "d", "nombre": "Pizza hawaiana"}]
    assert mv.match_photo("lomo-saltado.jpg", dishes) == ("a", "front")
    assert mv.match_photo("LOMO_SALTADO_perfil.JPG", dishes) == ("a", "side")
    assert mv.match_photo("aji de gallina 2.png", dishes) == ("b", "side")
    assert mv.match_photo("IMG_2231.jpg", dishes) == (None, "front")
    assert mv.match_photo("limonada-coco-frente.webp", dishes) == ("c", "front")
    assert mv.match_photo("pizza-hawaiana-desde-arriba.jpg", dishes) == ("d", "top")
    assert mv.match_photo("pizza hawaiana cenital.jpg", dishes) == ("d", "top")


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
