"""Mensajes nuevos de prospeccion (2026-11-13): firmados como CLONEXA, sin el nombre del dueno.

Cada nicho arma su texto con {negocio} y {enlace}; seguimiento unico con {gancho}; todos terminan con la linea
de baja; enlace corto por nicho; bumeran solo para restaurante, bar, taller y campo.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.services import prospecting_contact as pc
from app.services import prospecting_messages as pm
from app.services import prospecting_niches as pn

ROOT = Path(__file__).resolve().parents[1]
FIRST_LINE = {"restaurante": "¡Hola, Parrilla Don Tito! 👋🔥", "bar": "¡Qué más, Parrilla Don Tito! 🍻", "taller": "¡Hola, Parrilla Don Tito! 🧵✨",
              "campo": "¡Hola, Parrilla Don Tito! ⚡", "tienda": "¡Hola, Parrilla Don Tito! 🛒", "transporte": "¡Hola, Parrilla Don Tito! 🚚"}
LETTER = {"restaurante": "r", "bar": "b", "taller": "t", "campo": "c", "tienda": "s", "transporte": "l"}


@pytest.mark.parametrize("niche", list(pm.TEMPLATES))
def test_cada_nicho_arma_su_texto_con_negocio_y_enlace(niche):
    msg = pm.text(name="  Parrilla   Don Tito ", niche=niche, code="AB12CD", followup=False)
    lines = msg.split("\n")
    assert lines[0] == FIRST_LINE[niche]
    assert lines[1] == "Somos CLONEXA 🚀"
    assert f"👉 clonexa.com.co/{LETTER[niche]}/AB12CD" in lines
    assert lines[-1] == "Si no quieren más mensajes, respondan NO."
    assert "{" not in msg and "}" not in msg
    assert "\n\n" in msg, "saltos de línea tal cual (bloques)"
    assert ("Así 👆" in msg) == (niche in ("restaurante", "bar")), "tienda sin 'Así 👆'"
    assert "Síganos: @clonexaapp" in msg
    assert ("TikTok @clonexxa" in msg) == (niche == "restaurante")


@pytest.mark.parametrize("niche,gancho", list(pm.GANCHO.items()))
def test_seguimiento_unico_con_su_gancho(niche, gancho):
    msg = pm.text(name="Bar La 80", niche=niche, code="X", followup=True)
    assert msg == ("¡Hola de nuevo, Bar La 80! 👋\nSomos CLONEXA. Les dejamos otro ejemplo de " + gancho + " 👆\n"
                   "Si quieren verlo con su negocio, respondan SÍ y se lo mostramos en 2 minutos 🙌\nSi no, no les escribimos más.")


def test_ninguna_plantilla_menciona_al_dueno_y_todas_terminan_con_la_baja():
    for t in [*pm.TEMPLATES.values(), pm.FOLLOWUP, *pm.SUBJECT.values()]:
        assert "Nicol" not in t and "Gómez" not in t
    for t in pm.TEMPLATES.values():
        assert t.endswith("Si no quieren más mensajes, respondan NO.")
    for f in ("prospecting_messages.py", "prospecting_email.py", "prospecting_niches.py", "prospecting_contact.py"):
        assert "Nicolás" not in (ROOT / "app" / "services" / f).read_text(encoding="utf-8"), f
    assert pn.assisted_text(name="X", niche="bar", url="clonexa.com.co/b/1", followup=False).startswith("¡Qué más, X! 🍻")


def test_enlace_corto_y_bumeranes_por_nicho():
    assert pm.short_link("campo", "P7Q2LM") == "clonexa.com.co/c/P7Q2LM"
    assert pm.short_link("tienda", "P7Q2LM", scheme=True) == "https://clonexa.com.co/s/P7Q2LM"
    assert pm.short_link("otro", "Z") == "clonexa.com.co/r/Z"
    assert {n for n in pm.TEMPLATES if pm.has_boomerang(n)} == {"restaurante", "bar", "taller", "campo"}
    assert pm.subject(name="Parrilla Don Tito", niche="restaurante", followup=False) == "Parrilla Don Tito: su carta en video con QR 🎥"
    assert pm.subject(name="Always Pub", niche="bar", followup=False) == "Always Pub: su bar en vivo en 3D 🎮"


def test_cola_asistida_usa_el_mensaje_nuevo():
    p = {"name": "Always Pub", "business_type": "bar", "niche": "bar", "code": "SXFB3W",
         "channels": {"instagram": {"value": "@alwayspub", "url": "https://www.instagram.com/alwayspub"}}}
    r = pc.render_assisted(p, followup=False, settings={})
    assert r["network"] == "instagram" and r["profile_url"] == "https://www.instagram.com/alwayspub"
    assert r["text"].startswith("¡Qué más, Always Pub! 🍻") and "👉 clonexa.com.co/b/SXFB3W" in r["text"]
    assert r["url"] == "https://clonexa.com.co/b/SXFB3W"
    assert pc.render_assisted(p, followup=True, settings={})["text"].startswith("¡Hola de nuevo, Always Pub! 👋")
