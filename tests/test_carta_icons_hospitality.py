"""Galería de íconos de carta de Clonexa (iconos_carta_clonexa, piloto The Time Machine).

Tabla única, reconocimiento por la primera palabra (plural, mayúsculas, tildes),
prioridad foto > elegido > reconocido > genérico, SVG propios (peso y sin
scripts), servidos con caché larga, migración aditiva que enciende solo TTM.
"""
from __future__ import annotations

import importlib
import json
import re
from pathlib import Path

import pytest

from app.services import carta_icons as ci
from app.services import switch_registry
from app.web import brand_assets
from app.web.safe_static import is_allowed_file

ROOT = Path(__file__).resolve().parents[1]
ICON_DIR = ROOT / "app" / "web" / "assets" / "iconos-carta"
TTM = "21a3065e-38ee-4fc3-96ed-ae1707a3b8e4"


@pytest.mark.parametrize("name,key", [
    ("Aguardiente", "aguardiente"), ("Hidratante", "hidratante"), ("Paquete", "paquete"), ("Tiket", "tiket"), ("Ron", "ron"),
    ("Shot", "shot"), ("Tequila", "tequila"), ("Whiskey", "whiskey"), ("Vodka", "vodka"), ("Agua", "agua"), ("Cerveza", "cerveza"),
    ("Chiclets", "chiclets"), ("Cigarrillo", "cigarrillo"), ("Gaseosa", "gaseosa"),
    # plural, mayúsculas, tildes y sinónimos
    ("Aguardientes", "aguardiente"), ("AGUARDIENTE", "aguardiente"), ("Papitas", "paquete"), ("Aguardiente Antioqueño 375", "aguardiente"),
    ("Antioqueño", "aguardiente"), ("Guaro tapa roja", "aguardiente"), ("Suero oral", "hidratante"), ("Boleta general", "tiket"),
    ("Cover", "tiket"), ("Entradas", "tiket"), ("Whisky Old Parr", "whiskey"), ("Old Parr", "whiskey"), ("Cigarrillos Marlboro", "cigarrillo"),
    ("Agua Cristal", "agua"), ("Cervezas", "cerveza"), ("Poker lata", "cerveza"), ("Chupitos", "shot"), ("José Cuervo", "tequila"),
    ("Postobón manzana", "gaseosa"), ("Maní", "paquete"), ("¡Shot!", "shot"), ("  ron  medellín ", "ron"),
])
def test_cada_palabra_saca_su_icono(name, key):
    found, _word = ci.recognize(name)
    assert found == key, name
    r = ci.resolve(name)
    assert r["source"] == "auto" and r["key"] == key and r["url"] == f"/assets/iconos-carta/{key}.svg?v={ci.VERSION}"


@pytest.mark.parametrize("name,word", [("Hookah menta", "hookah"), ("Coctel de la casa", "coctel"), ("", ""), ("123", "123")])
def test_palabra_desconocida_va_al_generico_nunca_al_plato(name, word):
    r = ci.resolve(name)
    assert r["source"] == "generic" and r["key"] == "bebida"
    assert r["url"].startswith("/assets/iconos-carta/bebida-generica.svg")
    assert r["word"] == word
    assert "🍽" not in json.dumps(r, ensure_ascii=False)


def test_prioridad_foto_elegido_reconocido_generico():
    photo = "/api/v1/companies/x/waiter-ordering/products/y/image"
    assert ci.resolve("Aguardiente", icono_key="ron", photo_url=photo)["source"] == "photo"
    m = ci.resolve("Aguardiente", icono_key="ron")
    assert (m["source"], m["key"]) == ("manual", "ron")
    assert m["auto"]["key"] == "aguardiente", "la vista previa sabe qué saldría en automático"
    assert ci.resolve("Aguardiente", icono_key=None)["source"] == "auto"
    assert ci.resolve("Aguardiente", icono_key="")["source"] == "auto", "Volver al automático = vacío"
    assert ci.resolve("Aguardiente", icono_key="no-existe")["source"] == "auto", "una clave rara no rompe"
    assert ci.resolve("Hookah", icono_key="bebida")["source"] == "manual", "el genérico también se puede elegir"


def test_categoria_toma_el_elegido_que_mas_se_repite_o_el_reconocido():
    items = [{"icon": ci.resolve("Paquete papas")}, {"icon": ci.resolve("Paquete x", icono_key="chiclets")},
             {"icon": ci.resolve("Paquete y", icono_key="chiclets")}, {"icon": ci.resolve("Paquete z", icono_key="agua")}]
    assert ci.category_icon(items, "Paquete")["key"] == "chiclets"
    assert ci.category_icon([{"icon": ci.resolve("Ron viejo")}], "Ron") == {"source": "auto", "url": ci.url("ron"), "key": "ron"}
    assert ci.category_icon([], "Hookah")["key"] == "bebida"


def test_tabla_en_un_solo_lugar_sin_palabras_repetidas_y_con_su_svg():
    seen: dict[str, str] = {}
    for key, label, file, words in ci.ICONS:
        assert (ICON_DIR / file).is_file(), file
        for w in words:
            assert w == ci.first_word(w), f"{w}: escribir sin tildes y en minúscula"
            assert w not in seen, f"{w} está en {seen.get(w)} y en {key}"
            seen[w] = key
    assert len(ci.ICONS) == 14 and ci.GENERIC[2] == "bebida-generica.svg"
    assert [g["key"] for g in ci.gallery()][-1] == "bebida"
    # menuEmoji (JS) y first_word (Python) leen igual la primera palabra
    js = (ROOT / "app" / "web" / "hsp_menu_kit.js").read_text(encoding="utf-8")
    assert '.replace(/[^a-z0-9ñ\\s]/g, " ")' in js and 'first.replace(/es$/, ""), first.replace(/s$/, "")' in js


def test_svg_propios_livianos_y_sin_scripts():
    files = sorted(ICON_DIR.glob("*.svg"))
    assert len(files) == 15
    total = sum(f.stat().st_size for f in files)
    assert total < 40_000, f"peso total {total} bytes"
    for f in files:
        body = f.read_text(encoding="utf-8")
        assert body.lstrip().startswith("<svg") and 'viewBox="0 0 120 120"' in body
        assert not re.search(r"<script|\son[a-z]+=|href=|<image|<foreignObject", body, re.I), f.name


def test_servidos_como_estaticos_con_cache_larga():
    assert is_allowed_file("iconos-carta/agua.svg", allowed_dirs=frozenset({"brand", "iconos-carta"}))
    assert not is_allowed_file("iconos-carta/x.json", allowed_dirs=frozenset({"brand", "iconos-carta"}))
    assert brand_assets.CachedAssets(directory=str(ROOT / "app" / "web" / "assets")).allowed_dirs >= {"brand", "iconos-carta"}
    from fastapi.testclient import TestClient
    import app.main as app_main
    r = TestClient(app_main.app).get(ci.url("aguardiente"))
    assert r.status_code == 200 and r.headers["cache-control"] == brand_assets.CACHE_LONG
    assert r.headers["content-type"].startswith("image/svg")
    assert TestClient(app_main.app).get("/assets/iconos-carta/../../hospitality.py").status_code == 404


def test_interruptor_registrado_en_qr_y_apagado_por_defecto():
    reg = json.loads((ROOT / "app" / "services" / "switch_registry.json").read_text(encoding="utf-8"))
    switch_registry.validate(reg)
    sw = next(s for s in reg["switches"] if s["key"] == "iconos_carta_clonexa")
    assert sw["module"] == "qr" and sw["group"] == "QR" and ci.SETTING == sw["key"]
    assert switch_registry.company_state({"qr": {"enabled": True, "settings": {}}})["iconos_carta_clonexa"]["on"] is False


def test_migracion_aditiva_idempotente_y_solo_the_time_machine():
    mod = importlib.import_module("migrations.versions.025r_iconos_carta")
    assert len(mod.revision) <= 32 and mod.down_revision == "025q_nexus_radar"
    statements: list[str] = []

    class Op:
        def execute(self, sql):
            statements.append(str(sql))

    mod.op = Op()
    mod.upgrade()
    sql = "\n".join(statements)
    assert "ADD COLUMN IF NOT EXISTS icono_key" in sql and "CREATE TABLE IF NOT EXISTS carta_icon_misses" in sql
    assert "DROP" not in sql.upper() and "DELETE" not in sql.upper()
    assert sql.count(TTM) == 1 and '"iconos_carta_clonexa": true' in sql
    assert re.findall(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", sql) == [TTM], "ninguna otra empresa"
