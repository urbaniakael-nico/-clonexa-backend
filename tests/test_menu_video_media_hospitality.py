"""Menu video: remasterizado y clips (Pillow + OpenCV + ffmpeg, sin IA) y utilidades.

- Foto -> remasterizada (original guardada aparte); el recorte 3:4 solo si el
  plato completo cabe: nunca corta el plato.
- Camino 2 (foto): 720x1280, 25 fps, 3 s, H.264 sin audio, faststart,
  < 600 KB, con portada. Anima UNA foto (con 3 fotos NO hay pase de fotos).
  Cada estilo (Vida, Acercamiento, Giro suave, Paneo, Brillo, Automatico) es
  suave, vuelve exacto al inicio (bucle sin salto) y el plato completo nunca
  sale del cuadro ni baja a la tarjeta del precio. Foto horizontal, vertical
  y cuadrada; relleno con la misma foto difuminada (nunca negro).
- Camino 1 (video): vertical, horizontal y HEVC de iPhone -> estabilizado,
  color corregido, fondo desenfocado, 3 s en bucle sin salto, plato a ~38 %
  del alto y nunca cortado, < 1 MB; mas de 30 s o 150 MB -> mensaje claro.
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
from tests import menu_video_fixtures as fx

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


STYLES = ["vida", "zoom", "giro", "paneo", "brillo"]


@pytest.mark.parametrize("style", STYLES)
@pytest.mark.parametrize("w,h", [(1600, 1000), (1000, 1600), (1200, 1200)], ids=["horizontal", "vertical", "cuadrada"])
def test_el_plato_completo_siempre_visible_y_arriba_de_la_tarjeta(w, h, style):
    image = mm.clip_source(mm.load(dish_photo(4, w=w, h=h, cx=0.5, cy=0.6)), True)
    shot = mm.compose(image)
    W, H = shot.canvas.size
    x0, y0, x1, y1 = shot.photo_box
    assert x0 >= 0 and y0 >= 0 and x1 <= W and y1 <= H, "la foto ENTERA cabe en el cuadro"
    assert y1 <= H * 0.70 + 1, "la foto queda encima de la tarjeta del precio"
    dx0, dy0, dx1, dy1 = shot.dish_box
    for frame in range(0, 76, 3):
        zoom, center, angle = mm.frame_geometry(shot, style, frame / 75)
        assert 1.0 <= zoom <= mm.MAX_ZOOM + 1e-9 and abs(angle) <= 3.0 + 1e-9
        left, top, right, bottom = mm.view_box(shot, zoom, center)
        # al girar (max 3°) el plato redondo casi no cambia de caja: margen del 3 %
        tol = (dx1 - dx0) * 0.03 * (1 if angle else 0) + 1
        assert dx0 >= left - tol and dy0 >= top - tol and dx1 <= right + tol and dy1 <= bottom + tol, (style, frame, "el plato nunca sale del cuadro")
    # nunca bordes negros: arriba y abajo va la misma foto difuminada
    frame0 = mm.style_frame(shot, style, 0.37)
    for box in ((0, 0, mm.CLIP_W, 40), (0, mm.CLIP_H - 40, mm.CLIP_W, mm.CLIP_H), (0, 0, 30, mm.CLIP_H), (mm.CLIP_W - 30, 0, mm.CLIP_W, mm.CLIP_H)):
        mean = ImageStat.Stat(frame0.crop(box)).mean
        assert sum(mean) / 3 > 25, f"franja negra en {box}: {mean}"
    assert abs(mm.DISH_Y * H - (y0 + (y1 - y0) * 0.6)) < H * 0.06 or y0 == 0, "plato a ~38 % del alto"


def _check_clip(clip: mm.Clip, limit: int = 600 * 1024):
    info = mm.probe(clip.video)
    assert info["width"] == 720 and info["height"] == 1280
    assert info["fps"] == 25.0 and abs(info["seconds"] - 3.0) < 0.05
    assert info["h264"] and not info["audio"]
    assert len(clip.video) < limit, len(clip.video)
    assert clip.video[4:8] == b"ftyp"
    assert clip.video.find(b"moov") < clip.video.find(b"mdat"), "faststart: el indice va antes de los datos"
    poster = Image.open(io.BytesIO(clip.poster))
    assert poster.format == "WEBP" and poster.size == (720, 1280)


def _smooth_loop(video: bytes) -> tuple[float, float]:
    frames = fx.frames_of(video)
    steps = [fx.diff(frames[i], frames[i + 1]) for i in range(len(frames) - 1)]
    return fx.diff(frames[-1], frames[0]), max(steps)


@pytest.mark.parametrize("style", STYLES + ["auto"])
def test_cada_estilo_da_3_s_suaves_en_bucle_sin_salto(style):
    image = mm.clip_source(mm.load(dish_photo(12)), True)
    clip = mm.make_clip([image], style=style, background="desenfocar")
    _check_clip(clip)
    assert clip.style in STYLES and (style == "auto" or clip.style == style)
    shot = mm.compose(image, background="desenfocar")
    # el ultimo instante vuelve exacto al primero (curvas que regresan: sin salto)
    assert ImageChops.difference(mm.style_frame(shot, clip.style, 0.0), mm.style_frame(shot, clip.style, 1.0)).getbbox() is None
    loop, step = _smooth_loop(clip.video)
    assert step < 6, f"movimiento brusco: {step}"
    assert loop <= max(step * 1.6, 1.0), f"el bucle salta: {loop} vs {step}"


def test_con_3_fotos_no_hay_pase_de_fotos():
    a, b, c = (mm.clip_source(mm.load(dish_photo(40 + i, w=(1600, 1000, 1200)[i], h=(1000, 1600, 1200)[i])), True) for i in range(3))
    three = mm.make_clip([a, b, c], style="vida")
    one = mm.make_clip([a], style="vida")
    assert three.sources == one.sources and len(three.sources) == 1, "solo se anima la foto principal"
    f3, f1 = fx.frames_of(three.video), fx.frames_of(one.video)
    assert len(f3) == len(f1) == 75
    assert max(fx.diff(x, y) for x, y in zip(f3, f1)) < 2.5, "las otras fotos NUNCA entran al video"


def test_automatico_elige_por_la_forma_de_la_foto():
    wide = mm.load(dish_photo(50, w=2000, h=1100, cx=0.5, cy=0.5))
    assert mm.resolve_style("auto", wide, mm.compose(wide)) == "paneo"
    centered = mm.load(fx.jpeg(fx.plate_image(900, 900, plate=0.7, cx=0.5, cy=0.5)))
    shot = mm.compose(centered)
    assert shot.round_center and mm.resolve_style("auto", centered, shot) == "giro"
    off = mm.load(dish_photo(51, w=1000, h=1400, cx=0.3, cy=0.3))
    assert mm.resolve_style("auto", off, mm.compose(off)) == "vida"
    assert mm.resolve_style("suave") == "vida" and mm.resolve_style("front_side") == "vida", "los estilos viejos pasan a Vida"


@pytest.mark.parametrize("mode", ["desenfocar", "oscurecer"])
def test_fondo_fuera_del_plato(mode):
    image = mm.load(fx.jpeg(fx.plate_image(1200, 900, plate=0.5)))
    dish = mm.detect_dish(image)
    out = mm.apply_background(image, dish, mode)
    corner = (0, 0, 150, 150)
    center = (int(dish.cx * 1200) - 40, int(dish.cy * 900) - 40, int(dish.cx * 1200) + 40, int(dish.cy * 900) + 40)
    assert ImageChops.difference(out.crop(center), image.crop(center)).getbbox() is None, "el plato no se toca"
    assert ImageChops.difference(out.crop(corner), image.crop(corner)).getbbox(), "el fondo sí cambia"
    assert mm.apply_background(image, mm.CENTER, mode) is image, "sin saber dónde está el plato no se toca nada"


# ---------------------------------------------------- Camino 1: subir video
@pytest.mark.parametrize("kind,hevc", [("vertical", False), ("horizontal", False), ("vertical", True)], ids=["vertical", "horizontal", "iphone-hevc"])
def test_camino_1_video_estabilizado_color_fondo_y_bucle(kind, hevc):
    raw = fx.dish_video(kind, seconds=6, hevc=hevc, audio=True)
    if hevc:
        assert mm.inspect_video(raw)["codec"] == "hevc"
    clip = mm.make_video_clip(raw, "desenfocar")
    _check_clip(clip, limit=1024 * 1024)
    assert clip.stabilizer in ("vidstab", "deshake") and clip.style == "video" and clip.background == "desenfocar"
    assert clip.speed > 1.0, "la vuelta de 6 s se acelera para caber en 3 s"
    loop, step = _smooth_loop(clip.video)
    assert loop <= max(step * 2.0, 1.5), f"el bucle salta: {loop} vs {step}"
    # el plato completo, arriba de la tarjeta del precio (~38 % del alto), nunca cortado
    poster = Image.open(io.BytesIO(clip.poster)).convert("RGB")
    dish = mm.detect_dish(poster)
    assert dish.source in ("plato", "color")
    assert abs(dish.cy - mm.DISH_Y) < 0.08, dish
    assert dish.cy + dish.h / 2 <= 0.70 and dish.cy - dish.h / 2 >= 0 and dish.cx - dish.w / 2 >= 0 and dish.cx + dish.w / 2 <= 1, dish


def test_camino_1_velocidad_y_tramo():
    raw = fx.dish_video("vertical", seconds=8, audio=False)
    slow = mm.make_video_clip(raw, "ninguno", "lento")
    fast = mm.make_video_clip(raw, "ninguno", "rapido")
    assert slow.speed < fast.speed
    part = mm.make_video_clip(raw, "ninguno", "normal", start=2.0, length=3.0)
    assert part.speed == 1.0, "un tramo de 3 s cabe tal cual en el bucle"


def test_camino_1_limites_con_mensaje_claro():
    with pytest.raises(mm.MediaRejected, match="máximo es 30 s"):
        mm.inspect_video(fx.long_video(31))
    with pytest.raises(mm.MediaRejected, match="150 MB"):
        mm.check_video_size(150 * 1024 * 1024 + 1)
    with pytest.raises(mm.MediaRejected, match="MP4 o MOV"):
        mm.inspect_video(b"esto no es un video" * 10)
    assert mm.inspect_video(fx.dish_video("vertical", seconds=2, audio=False))["seconds"] == pytest.approx(2.0, abs=0.2)


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
    assert mv.match_photo("lomo-saltado.jpg", dishes) == ("a", "main")
    assert mv.match_photo("LOMO_SALTADO_perfil.JPG", dishes) == ("a", "gallery")
    assert mv.match_photo("aji de gallina 2.png", dishes) == ("b", "gallery")
    assert mv.match_photo("IMG_2231.jpg", dishes) == (None, "main")
    assert mv.match_photo("limonada-coco-frente.webp", dishes) == ("c", "main")
    assert mv.match_photo("pizza-hawaiana-desde-arriba.jpg", dishes) == ("d", "gallery")
    assert mv.match_photo("pizza hawaiana cenital.jpg", dishes) == ("d", "gallery")


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
