"""Tarjeta PNG de los cortes (whatsapp_group_reports, 073A): todos los nombres visibles y sin cortes.

render() devuelve el layout de cada nombre dibujado; aqui se prueba que estan TODOS, completos
(las lineas juntas son el nombre), dentro de la imagen y sin chocar entre si, con 25 y 31 personas,
con 0 sin conectar, con personas en pausa, nombres largos con tildes y turnos de mas de 12 h."""
from __future__ import annotations

import io
import re
from pathlib import Path

from PIL import Image

from app.services import group_reports as gr
from app.services import group_reports_card as card

FIRST = ["Ángela", "José", "María", "Juan Reinaldo", "Jairo de Jesús", "Ñeco", "Sofía", "Héctor", "Begoña", "Iván", "Raúl", "Zoë"]
LAST = ["Núñez Peña", "Perdomo Pérez", "Agreda Sarabia", "Lobaina Correa", "Gutiérrez", "Vaca Quiroz", "Muñoz", "Ibáñez Ortúzar"]


def people(n: int) -> list[str]:
    return [f"{FIRST[i % len(FIRST)]} {LAST[(i * 3) % len(LAST)]} {i + 1}" for i in range(n)]


def check(png: bytes, layout: dict, expected: list[str]) -> Image.Image:
    img = Image.open(io.BytesIO(png))
    assert img.size == (1080, layout["height"]) and img.mode == "RGB"
    drawn = [n["text"] for n in layout["names"]]
    assert sorted(drawn) == sorted(expected), "todos los nombres, sin '+N mas'"
    for n in layout["names"]:
        x0, y0, x1, y1 = n["box"]
        assert 0 <= x0 < x1 <= 1080 and 0 <= y0 < y1 <= layout["height"], n
        assert "".join(n["lines"]).replace(" ", "") == n["text"].replace(" ", ""), f"nombre cortado: {n}"
    boxes = [n["box"] for n in layout["names"]]
    for i, a in enumerate(boxes):
        for b in boxes[i + 1:]:
            overlap = a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]
            assert not overlap, (a, b)
    return img


def entry(connected, missing, paused=()):
    return {"type": "checkin", "company": "VOLTAGE", "operation": "Alabama", "subtitle": "Lunes 09/11 · Entrada 6:00 a. m. CT · Corte 6:30 a. m.",
            "connected": [[n, n in paused] for n in connected], "missing": missing}


def test_entrada_25_personas_con_pausa_y_tildes():
    names = people(25)
    missing, connected = names[:3], names[3:]
    png, layout = card.render(entry(connected, missing, paused={connected[2]}))
    img = check(png, layout, names)
    left = [n for n in layout["names"] if n["column"] == "left"]
    assert [n["text"] for n in left] == missing, "los que faltan, a la izquierda y en orden"
    paused = next(n for n in layout["names"] if n["text"] == connected[2])
    x0, y0, x1, y1 = paused["box"]
    yellow = [img.getpixel((x, y)) for x in range(int(x0) + 18, int(x0) + 40) for y in range(int(y0) + 10, int(y1) - 10)]
    assert any(p == card.YELLOW for p in yellow), "⏸ en amarillo"
    red_chip = next(n for n in left)["box"]
    assert img.getpixel((int(red_chip[0]) + 4, int(red_chip[1]) + 20)) == card.RED_CHIP


def test_entrada_31_personas_varias_columnas_y_alto_crece():
    small_png, small = card.render(entry(people(25)[3:], people(25)[:3]))
    names = people(31)
    png, layout = card.render(entry(names[5:], names[:5]))
    check(png, layout, names)
    assert layout["height"] > small["height"]
    right = [n for n in layout["names"] if n["column"] == "right"]
    assert len({n["box"][0] for n in right}) == 2, "conectados en dos columnas angostas"


def test_entrada_todos_conectados():
    names = people(31)
    png, layout = card.render(entry(names, []))
    img = check(png, layout, names)
    assert not [n for n in layout["names"] if n["column"] == "left"]
    # el cuadro verde grande "Todos conectados" queda debajo de la barra
    first = min(n["box"][1] for n in layout["names"])
    assert any(img.getpixel((540, y)) == card.GREEN_BOX for y in range(int(first) - 300, int(first) - 60))


def test_nombres_muy_largos_no_se_cortan():
    longest = "María de los Ángeles Pérez Núñez de la Concepción Ibáñez Ortúzar"
    weird = "Supercalifragilisticoespialidosoextraordinarioñandú Pérez"
    png, layout = card.render(entry(people(20) + [longest], [weird]))
    check(png, layout, people(20) + [longest, weird])
    assert len(next(n for n in layout["names"] if n["text"] == longest)["lines"]) >= 2


def test_salida_horas_abiertas_y_rojo_sobre_12_h():
    done = people(20)
    still = [["Hector Sandoval Machuca", 13 * 60 + 5, "13 h 05 min"], ["Ana Ruiz", 9 * 60, "9 h"]]
    png, layout = card.render({"type": "checkout", "company": "VOLTAGE", "operation": "Virginia", "subtitle": "Lunes 09/11 · Salida 5:00 p. m. ET · Corte 5:30 p. m.",
                               "done": done, "still": still})
    img = check(png, layout, done + ["Hector Sandoval Machuca · 13 h 05 min", "Ana Ruiz · 9 h"])
    left = {n["text"]: n["box"] for n in layout["names"] if n["column"] == "left"}
    long_box, ok_box = left["Hector Sandoval Machuca · 13 h 05 min"], left["Ana Ruiz · 9 h"]
    assert img.getpixel((int(long_box[0]) + 4, int(long_box[1]) + 20)) == card.RED_CHIP, "más de 12 h en rojo"
    assert img.getpixel((int(ok_box[0]) + 4, int(ok_box[1]) + 20)) == card.AMBER_CHIP


def test_salida_todos_cerraron():
    png, layout = card.render({"type": "checkout", "company": "VOLTAGE", "operation": "Virginia", "subtitle": "x", "done": people(25), "still": []})
    check(png, layout, people(25))


def test_nombres_limpios_y_pies_de_foto_en_lista():
    assert gr.clean_name(' "Eduardo Pablo Lores Londres " ') == "Eduardo Pablo Lores Londres"
    assert gr.clean_name("Mauricio Escobar argote`") == "Mauricio Escobar Argote"
    assert gr.clean_name("jairo DE jesús perdomo pérez") == "Jairo de Jesús Perdomo Pérez"
    assert gr.clean_name("ana-maría o'brien") == "Ana-María O'Brien"
    caption = gr.checkin_text("*VOLTAGE · Alabama · Entrada*", "Lun 09/11 · 6:30 a. m. CT", [("A", False)] * 22,
                              ["Brandon Via Illanes", "Giselle Reyna", "Hector Sandoval Machuca"])
    assert caption == ("*VOLTAGE · Alabama · Entrada*\nLun 09/11 · 6:30 a. m. CT\n\n❌ *Sin conectar / Not connected (3):*\n"
                       "1. Brandon Via Illanes\n2. Giselle Reyna\n3. Hector Sandoval Machuca\n\n✅ Conectados / Connected: 22 de 25")
    out = gr.checkout_text("*VOLTAGE · Alabama · Salida*", "Lun 09/11 · 5:30 p. m. CT", ["A"] * 20, [("Hector Sandoval", 13 * 60), ("Ana Ruiz", 60)])
    assert "1. Hector Sandoval · 13 h 🔴\n2. Ana Ruiz · 1 h" in out and out.endswith("✅ Ya cerraron / Clocked out: 20 de 22")


def test_n8n_manda_imagen_y_si_falla_el_texto():
    flow = Path("ops/n8n/voltage_group_reports_flow.py").read_text(encoding="utf-8")
    assert "'image' : 'document'" in flow, "PNG como imagen con pie de foto"
    assert '"Fallo la imagen"' in flow and '"WhatsApp texto (respaldo)"' in flow, "si la imagen falla, llega el texto"
    assert re.search(r'node\("Descargar".*?onError="continueRegularOutput"', flow, re.S), "si no se pudo dibujar, se manda el texto"
    assert flow.count('"emailType": "html"') >= 2 and "mail_html" in flow and "b.html ? String(b.text" in flow, "correo a los dueños en HTML"
