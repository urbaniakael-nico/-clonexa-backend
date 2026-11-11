"""Oficina 3D fase 1.5 (piso realista): reglas puras, recursos, licencias y presupuesto por piso.

- Distribucion automatica con el numero real de mesas; lo guardado manda; validacion del modo arquitecto.
- Paleta: estudio > panel inicial > neutra con aviso; neon siempre legible sobre el salon oscuro.
- Dia del bar 18:00-04:00 (luces bajas fuera de horario salvo actividad).
- Globos de tareas del personal; without_money quita cualquier campo de dinero.
- LICENCIAS.md cubre cada recurso servido; el piso del bar pesa menos de 25 MB; todo CC0.
- El motor realista: solo el propio backend (sin CDN), sin estilos ni manejadores en linea, sin carga de imagenes.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from app.services import brand_theme as bt
from app.services import oficina as of
from app.services import oficina_vivo as ov

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "app/web/oficina/recursos"


def test_distribucion_automatica_con_las_mesas_reales():
    tables = [f"Mesa {i}" for i in range(1, 11)]
    lay = ov.auto_layout(tables)
    mesas = [k for k in lay["items"] if k.startswith("mesa:")]
    assert len(mesas) == 10 and set(ov.FIXED) <= set(lay["items"])
    W, D = lay["room"]["W"], lay["room"]["D"]
    for k, (x, z, _r) in lay["items"].items():
        assert -W / 2 <= x <= W / 2 and -D / 2 <= z <= D / 2, k
    spots = [tuple(lay["items"][k][:2]) for k in mesas]
    assert len(set(spots)) == 10, "ninguna mesa encima de otra"
    big = ov.auto_layout([f"Mesa {i}" for i in range(1, 31)])
    assert big["room"]["D"] > D, "con mas mesas el salon crece"


def test_lo_guardado_manda_y_las_mesas_nuevas_caen_solas():
    tables = ["Mesa 1", "Mesa 2", "Mesa 3"]
    saved = ov.clean_layout({"items": {"mesa:Mesa 1": [1, 2, 7.0], "barra": [-50, 0, 0]}}, tables)
    assert saved["items"]["barra"][0] == -ov.room(3)["W"] / 2, "se ajusta al borde"
    assert abs(saved["items"]["mesa:Mesa 1"][2] - (7.0 - 2 * 3.141592653589793)) < 1e-3
    merged = ov.merge_layout(tables + ["Mesa 4"], saved)
    assert merged["custom"] and merged["items"]["mesa:Mesa 1"][:2] == [1, 2] and "mesa:Mesa 4" in merged["items"]
    assert ov.merge_layout(tables, {})["custom"] is False
    for bad in ({"items": {"mesa:Mesa 9": [0, 0, 0]}}, {"items": {"x": [0, 0, 0]}}, {"items": {"dj": [0, 0]}}, {"items": {"dj": [0, float("nan"), 0]}}, []):
        with pytest.raises(of.Rejected):
            ov.clean_layout(bad, tables)


def test_paleta_del_estudio_panel_o_neutra_y_neon_legible():
    tokens = bt.make_tokens(bt.palette("#14082e", "#7c3aed", "#0b0b10", "#f5f5f5"))
    p = ov.palette(tokens, None)
    assert p["source"] == "estudio" and p["warning"] is None and p["colors"]["primary"] == "#14082e"
    assert bt.contrast(p["accent"], ov.ROOM_DARK) >= 3 and bt.contrast(p["accent2"], ov.ROOM_DARK) >= 3
    assert bt.contrast(p["screen_text"], p["screen_bg"]) >= 4.5, "texto de las pantallas legible"
    panel = ov.palette(None, {"primary_color": "#FF5500", "logo_url": ""})
    assert panel["source"] == "panel" and panel["colors"]["primary"] == "#ff5500" and panel["warning"] == ov.NO_BRAND
    neutral = ov.palette(None, {})
    assert neutral["source"] == "neutra" and neutral["warning"] == "⚠ Configura la marca en el Estudio de marca" and neutral["colors"] == ov.NEUTRAL
    assert ov.legacy_branding({"company_branding": {"primary_color": "#123456"}}) == {"primary_color": "#123456"}
    assert ov.legacy_branding('{"experience": {"branding": {"logo_url": "x"}}}') == {"logo_url": "x"}
    assert ov.legacy_logo_bytes({"logo_url": "data:image/svg+xml;base64,PHN2Zz4="}) is None, "solo PNG/JPG/WebP reales"


def test_dia_del_bar_y_luces():
    tz = ZoneInfo("America/Bogota")
    at = lambda h: datetime(2026, 11, 12, h, 0, tzinfo=tz)  # noqa: E731
    assert ov.business(at(20), tz, None, False)["open"] is True
    assert ov.business(at(3), tz, None, False)["open"] is True
    closed = ov.business(at(11), tz, None, False)
    assert closed["open"] is False and closed["lights"] == "low" and closed["sign"] == "Cerrado · abre 18:00"
    busy = ov.business(at(11), tz, None, True)
    assert busy["lights"] == "on" and busy["activity_off_hours"] is True, "si hay actividad fuera de horario se muestra igual"
    assert ov.business(at(19), tz, {"open": "20:00", "close": "02:00"}, False)["sign"] == "Cerrado · abre 20:00"


def test_globos_de_tareas_del_personal():
    now = datetime.now(timezone.utc)
    staff = [{"key": "a", "label": "Carlos R. · Barman", "role": "Barman", "uniform": "barman", "paused": False},
             {"key": "b", "label": "Diana L. · Mesera", "role": "Mesera", "uniform": "mesero", "paused": False},
             {"key": "c", "label": "DJ", "role": "DJ", "uniform": "dj", "paused": False},
             {"key": "d", "label": "Caja", "role": "Caja", "uniform": "caja", "paused": True}]
    orders = [{"id": "1", "table": "Mesa 7", "state": "nuevo", "items": 3, "at": (now - timedelta(minutes=2)).isoformat(), "updated_at": now.isoformat()},
              {"id": "2", "table": "Mesa 2", "state": "entregado", "items": 1, "at": now.isoformat(), "updated_at": now.isoformat()}]
    t = {p["key"]: p["task"] for p in ov.tasks(staff, orders, 2, "La Bicicleta", now)}
    assert t == {"a": "Preparando 3 productos · Mesa 7", "b": "Llevando pedido · Mesa 2", "c": "Mezclando · La Bicicleta", "d": "En pausa · café"}
    old = [dict(orders[1], updated_at=(now - timedelta(minutes=10)).isoformat())]
    assert ov.tasks(staff[1:2], old, 1, None, now)[0]["task"] == "Atendiendo 1 mesa"
    assert ov.table_label("", "mesa-7", ["Mesa 7"]) == "Mesa 7" and ov.table_label("Terraza", "t1", ["Mesa 1"]) == "Terraza"


def test_without_money_quita_todo_campo_de_dinero():
    dirty = {"orders": [{"items": 2, "total": 9, "unit_price": 5, "subtotal": 3}], "kpis": [["Mesas abiertas", "1"]], "precio": 1, "tip": 2,
             "nested": {"sales": 1, "ok": True}}
    assert ov.without_money(dirty) == {"orders": [{"items": 2}], "kpis": [["Mesas abiertas", "1"]], "nested": {"ok": True}}


def test_copia_viva_no_lee_dinero_en_sql():
    source = (ROOT / "app/services/oficina_vivo.py").read_text(encoding="utf-8")
    for sql in re.findall(r'"""(.*?)"""', source, re.S):
        if "hospitality_orders" in sql or "jsonb_array_elements" in sql:
            assert not re.search(r"\btotal\b|price|subtotal|payment|tip", sql, re.I), "las consultas de pedidos no leen dinero"
    assert "customer_name" not in source and "display_name" not in source, "clientes anonimos"


def _manifest() -> dict:
    return json.loads((RES / "manifest.json").read_text(encoding="utf-8"))


def test_licencias_cubren_todos_los_recursos_y_son_cc0():
    man = _manifest()
    lic = (ROOT / "docs/oficina/LICENCIAS.md").read_text(encoding="utf-8")
    on_disk = sorted(p.relative_to(RES).as_posix() for p in RES.rglob("*") if p.is_file() and p.name != "manifest.json")
    assert on_disk == sorted(man["files"]), "todo lo que se sirve esta en el manifiesto"
    for f in on_disk:
        assert f"`{f}`" in lic, f"{f} sin licencia en LICENCIAS.md"
        src = man["sources"][f]
        assert src["license"] == "CC0 1.0" and src["url"].startswith(("https://polyhaven.com/a/", "https://quaternius.com/")), f
        assert src["authors"], f"{f} sin autor"
    assert "MIT" in lic and "three.js" in lic


def test_presupuesto_de_25_mb_por_piso():
    from app.web import oficina_routes as routes

    man = _manifest()
    used = routes.floor_bytes("bar")
    assert 0 < used <= routes.FLOOR_BUDGET == 25 * 1024 * 1024, used
    assert used == sum(man["files"][f]["bytes"] for f in man["templates"]["bar"])
    for f, meta in man["files"].items():
        assert (RES / f).stat().st_size == meta["bytes"], f
        if f.endswith(".glb"):
            head = (RES / f).read_bytes()
            assert head[:4] == b"glTF" and b"EXT_meshopt_compression" in head[:20000], f"{f} sin meshopt"
            assert b"image/jpeg" not in head[:20000] and b"image/png" not in head[:20000], f"{f} con texturas sin pasar a WebP"
        if f.startswith("texturas/"):
            assert f.endswith(".webp")


def test_motor_realista_sin_cdn_sin_codigo_en_linea_y_sin_cargar_imagenes():
    real = (ROOT / "app/web/oficina/oficina_real.js").read_text(encoding="utf-8")
    rules = (ROOT / "app/web/oficina/oficina_real_rules.js").read_text(encoding="utf-8")
    imports = re.findall(r"^import .* from '([^']+)';$", real, re.M)
    from app.web import oficina_routes as routes

    for imp in imports:
        assert imp == "three" or imp.startswith("three/addons/") or imp == "/admin-v2plus/oficina/real_reglas.js", imp
        if imp.startswith("three/addons/"):
            assert "examples/jsm/" + imp.removeprefix("three/addons/") in routes.THREE, imp
    assert "import " not in rules, "las reglas no dependen de nada"
    for body in (real, rules):
        assert not re.search(r"https?://(cdn|unpkg|jsdelivr|fonts|raw\.)", body, re.I)
        assert ' style="' not in body and not re.search(r"<[a-z][^>]*\son[a-z]+=", body, re.I)
        assert 'type="file"' not in body and "FileReader" not in body
    app_js = (ROOT / "app/web/oficina/oficina_app.js").read_text(encoding="utf-8")
    assert 'type="file"' not in app_js and "personajes/archivo" not in app_js and "Modelo 3D" not in app_js and "Imagen como cara" not in app_js
    assert "import('/admin-v2plus/oficina/real.js')" in app_js, "el motor realista se carga solo al abrir ese piso"
    assert "AgXToneMapping" in real and "GTAOPass" in real and "UnrealBloomPass" in real and "MeshoptDecoder" in real and "RGBELoader" in real
    assert "crossFadeTo" in real and "AnimationMixer" in real and "SkeletonUtils" in real
