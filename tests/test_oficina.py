"""Oficina 3D (Consola v2+): reglas puras, sin base de datos.

- Estados de agentes con respuestas SIMULADAS de n8n: corriendo, exito reciente, error, inactivo,
  pendiente de configurar, flujo que no existe y n8n caido (gris "sin datos", nunca inventado).
- Cache de n8n: 30 s, nunca mas de 2 consultas por minuto, la pagina recibe la ultima respuesta al
  instante (stale-while-revalidate) y n8n caido o lento -> "sin datos".
- Plantillas por empresa, privacidad del personal, VOLTAGE maximo 5 por operacion + "+N", dia del bar
  18:00-04:00, representantes sin dinero, archivos del editor (tipo real y tamaño) y la pagina (CSP).
"""
from __future__ import annotations

import asyncio
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from app.services import oficina as of
from app.services import oficina_data as od

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 11, 10, 20, 0, tzinfo=timezone.utc)  # 15:00 en Bogota


def flow(name, *, active=True, running=False, status="success", minutes_ago=60, runs=3, errors=0):
    at = (NOW - timedelta(minutes=minutes_ago)).isoformat() if status else None
    return {"name": name, "active": active, "running": running, "today_runs": runs, "today_errors": errors,
            "last": {"status": status, "started_at": at, "stopped_at": at} if status else None,
            "last_ok_at": at if status == "success" else None, "last_error_at": at if status == "error" else None}


def n8n(*flows, **extra):
    return {"ok": True, "workflows": list(flows), "recent": [], **extra}


def state_of(agents, agent_id):
    return next(a for a in agents if a["id"] == agent_id)


# ------------------------------------------------------------------ estados
def test_corriendo_ahora_es_trabajando():
    agents = of.build_agents(n8n(flow("Nexa - Bot de comandos", running=True, minutes_ago=300)), {}, NOW)
    a = state_of(agents, "asistente")
    assert a["state"] == "work" and "corriendo ahora" in " ".join(a["today"])
    assert a["source"] == 'Flujo "Nexa - Bot de comandos"'


def test_exito_en_los_ultimos_15_min_es_trabajando_y_despues_cafe():
    assert of.flow_state(flow("x", minutes_ago=14), NOW) == "work"
    assert of.flow_state(flow("x", minutes_ago=16), NOW) == "wait"
    agents = of.build_agents(n8n(flow("Nexa - Plan B", minutes_ago=200)), {}, NOW)
    assert state_of(agents, "planb")["state"] == "wait"


def test_ultima_ejecucion_con_error_es_error():
    agents = of.build_agents(n8n(flow("Nexa - Correos", status="error", minutes_ago=5, errors=1),
                                 flow("Nexa - Correos prospección", minutes_ago=2)), {}, NOW)
    a = state_of(agents, "correos")
    assert a["state"] == "err"
    assert "1 con error" in " ".join(a["today"])
    assert a["source"] == 'Flujos "Nexa - Correos" y "Nexa - Correos prospección"'


def test_inactivo_es_en_entrenamiento_y_tiktok_pendiente_tambien():
    agents = of.build_agents(n8n(flow("Nexa - Leads DEMO", active=False), flow("Nexa - TikTok", status=None, runs=0)), {}, NOW)
    assert state_of(agents, "comunidad")["state"] == "train"
    tiktok = state_of(agents, "tiktok")
    assert tiktok["state"] == "train" and "claves de producción" in tiktok["today"][0]


def test_flujo_que_no_existe_queda_sin_datos():
    agents = of.build_agents(n8n(), {"lector": ["Cola de Menú video: 2 clips en cola · 0 hechos hoy"]}, NOW)
    lector = state_of(agents, "lector")
    assert lector["state"] == "nodata"
    assert lector["today"][0] == "Sin datos: el flujo no existe en n8n"
    assert "no existe en n8n" in lector["source"] and lector["flows"] == [{"name": "Clonexa - Leer carta", "exists": False, "active": False}]


def test_n8n_caido_deja_a_todos_los_agentes_en_gris():
    agents = of.build_agents({"ok": False, "error": "n8n no respondió."}, {"ventas": ["2 conversaciones con mensajes hoy"]}, NOW)
    for a in agents:
        if a["id"] == "director":
            continue
        assert a["state"] == "nodata", a["id"]
    assert state_of(agents, "ventas")["today"][0] == "Sin datos de n8n (no respondió)"
    assert of.n8n_feed({"ok": False}, NOW) == []


def test_nombres_de_flujo_sin_tildes_coinciden():
    agents = of.build_agents(n8n(flow("VOLTAGE envios", minutes_ago=3)), {}, NOW)
    assert state_of(agents, "mensajero")["state"] == "work"


def test_calendario_y_reporte_de_la_hoja():
    data = n8n(calendar={"ok": True, "ready": 3, "approved": 2, "week_pieces": 2, "next": {"fecha": "11/11/2026", "formato": "Anuncio", "tema": "Turnos"}},
               report={"ok": False})
    agents = of.build_agents(data, {}, NOW)
    creativo = state_of(agents, "creativo")
    assert creativo["state"] == "work" and creativo["today"][0] == "2 piezas en el calendario esta semana"
    assert state_of(agents, "analista")["state"] == "nodata", "sin la pestaña no se inventa nada"
    data["report"] = {"ok": True, "last_date": "2026-11-03", "rows": 4}
    assert state_of(of.build_agents(data, {}, NOW), "analista")["state"] == "wait"


def test_quince_agentes_con_el_mapeo_exacto():
    assert len(of.AGENTS) == 15
    flows = {a["id"]: a["flows"] for a in of.AGENTS}
    assert flows["contenido"] == ["Nexa - Vista previa", "Nexa - Publicar del día"]
    assert flows["guardian"] == ["Nexa - Errores"] and flows["archivista"] == ["VOLTAGE timesheets"]


def test_actividad_en_vivo_solo_ejecuciones_reales_de_los_agentes():
    data = n8n(recent=[{"workflow": "Nexa - Plan B", "status": "error", "stopped_at": (NOW - timedelta(minutes=3)).isoformat()},
                       {"workflow": "Nexa - Prueba guion", "status": "success", "stopped_at": NOW.isoformat()},
                       {"workflow": "Nexa - Correos", "status": "success", "stopped_at": (NOW - timedelta(days=2)).isoformat()}])
    feed = of.n8n_feed(data, NOW)
    assert [e["text"] for e in feed] == ["⚠️ <b>Nexa - Plan B</b> falló"] and feed[0]["kind"] == "error"


# ------------------------------------------------------------------ cache de n8n
def test_cache_de_30_s_y_maximo_2_por_minuto(monkeypatch):
    monkeypatch.setenv(of.ENV_URL, "https://n8n.test/webhook/oficina-estado")
    monkeypatch.setenv(of.ENV_SECRET, "s" * 30)
    clock = {"t": 1000.0}
    calls = []

    async def fetch(url, secret):
        calls.append(clock["t"])
        return {"ok": True, "workflows": []}

    cache = of.N8nCache(fetch=fetch, clock=lambda: clock["t"])

    async def go():
        first = await cache.get()
        assert first["ok"] and len(calls) == 1
        for step in range(60):  # 60 consultas de la pagina en 1 minuto
            clock["t"] += 1
            await cache.get()
            await asyncio.sleep(0)
        await asyncio.sleep(0)
    asyncio.run(go())
    assert len(calls) <= 3 and len([c for c in calls if c - calls[0] < 60]) <= 2


def test_respuesta_instantanea_con_cache_vencida(monkeypatch):
    monkeypatch.setenv(of.ENV_URL, "https://n8n.test/x")
    monkeypatch.setenv(of.ENV_SECRET, "s" * 30)
    clock = {"t": 0.0}

    async def slow(url, secret):
        await asyncio.sleep(0.3)
        return {"ok": True, "workflows": [], "n": clock["t"]}

    cache = of.N8nCache(fetch=slow, clock=lambda: clock["t"])

    async def go():
        await cache.get()
        clock["t"] = 31
        t0 = asyncio.get_running_loop().time()
        stale = await cache.get()
        took = asyncio.get_running_loop().time() - t0
        assert stale["n"] == 0 and took < 0.05, "devuelve la ultima respuesta sin esperar a n8n"
        await asyncio.sleep(0.4)
        assert (await cache.get())["n"] == 31
    asyncio.run(go())


@pytest.mark.parametrize("error", [RuntimeError("n8n respondió 502"), asyncio.TimeoutError(), ValueError("json")])
def test_n8n_caido_o_raro_es_sin_datos(monkeypatch, error):
    monkeypatch.setenv(of.ENV_URL, "https://n8n.test/x")
    monkeypatch.setenv(of.ENV_SECRET, "s" * 30)

    async def boom(url, secret):
        raise error

    data = asyncio.run(of.N8nCache(fetch=boom).get())
    assert data["ok"] is False and data["error"] == "n8n no respondió."


def test_sin_variables_no_consulta(monkeypatch):
    monkeypatch.delenv(of.ENV_URL, raising=False)
    monkeypatch.delenv(of.ENV_SECRET, raising=False)

    async def never(url, secret):
        raise AssertionError("no debe llamar")

    assert asyncio.run(of.N8nCache(fetch=never).get())["ok"] is False


# ------------------------------------------------------------------ pisos y personal
def test_plantilla_de_las_empresas_vivas_y_deducida():
    assert of.deduce_template("d63cf68c-be5b-4a30-aee4-341973018db1", set(), has_locations=False, overnight=False) == "taller"
    assert of.deduce_template("7625872c-f941-4479-a27b-f8443be953c5", set(), has_locations=False, overnight=False) == "restaurante"
    assert of.deduce_template("21a3065e-38ee-4fc3-96ed-ae1707a3b8e4", set(), has_locations=False, overnight=False) == "bar"
    assert of.deduce_template("f1e8f774-f052-49ca-880a-268805f07db0", set(), has_locations=False, overnight=False) == "campo"
    other = "11111111-1111-1111-1111-111111111111"
    assert of.deduce_template(other, {"workforce"}, has_locations=True, overnight=False) == "campo"
    assert of.deduce_template(other, {"references"}, has_locations=False, overnight=False) == "taller"
    assert of.deduce_template(other, {"hospitality"}, has_locations=False, overnight=True) == "bar"
    assert of.deduce_template(other, {"carta"}, has_locations=False, overnight=False) == "restaurante"
    assert of.deduce_template(other, {"workforce"}, has_locations=False, overnight=False) is None, "se elige en la oficina"


@pytest.mark.parametrize("full,short", [("Ana María Pérez Gómez", "Ana P."), ("JUAN RAMIREZ", "Juan R."), ("Luisa Fernanda Rojas", "Luisa F."),
                                        ("Noel", "Noel"), ("", "")])
def test_primer_nombre_e_inicial(full, short):
    assert of.short_name(full) == short


def test_personal_con_privacidad_y_uniforme():
    rows = [{"employee_id": "e1", "employee_name": "Ana María Pérez Gómez", "employee_role": "mesero", "status": "working"},
            {"employee_id": "e2", "employee_name": "Carlos Díaz", "employee_role": "cocina", "status": "on_break"}]
    out = of.staff_out(rows, "restaurante", "nombre")
    assert [p["label"] for p in out["visible"]] == ["Ana P. · Mesero", "Carlos D. · Cocina"]
    assert [p["uniform"] for p in out["visible"]] == ["mesero", "cocina"] and out["visible"][1]["paused"] is True
    only_role = of.staff_out(rows, "restaurante", "cargo")
    assert [p["label"] for p in only_role["visible"]] == ["Mesero", "Cocina"]
    text = repr(only_role)
    assert "Ana" not in text and "Pérez" not in text and "e1" not in text, "ni nombre ni id"


def test_voltage_maximo_5_por_operacion_y_mas_n():
    rows = [{"employee_id": f"v{i}", "employee_name": f"Tec {i}", "employee_role": "tecnico", "status": "working", "work_location_name": "Virginia"} for i in range(8)]
    rows += [{"employee_id": f"a{i}", "employee_name": f"Al {i}", "employee_role": "", "status": "working", "work_location_name": "Alabama"} for i in range(3)]
    out = of.staff_out(rows, "campo", "nombre")
    ops = {o["name"]: o for o in out["ops"]}
    assert ops["Virginia"]["total"] == 8 and len(ops["Virginia"]["visible"]) == 5 and ops["Virginia"]["extra"] == 3
    assert ops["Alabama"]["extra"] == 0 and out["extra"] == 3 and out["total"] == 11
    assert {p["uniform"] for p in out["visible"]} == {"tecnico"}


def test_taller_maximo_10_maquinas():
    rows = [{"employee_id": f"t{i}", "employee_name": f"Op {i}", "employee_role": "operaria", "status": "working"} for i in range(13)]
    out = of.staff_out(rows, "taller", "nombre")
    assert len(out["visible"]) == 10 and out["extra"] == 3 and out["visible"][0]["uniform"] == "costura"


@pytest.mark.parametrize("role,template,uniform", [("domiciliario", "restaurante", "domiciliario"), ("Barman", "bar", "barman"), ("DJ", "bar", "dj"),
                                                   ("cajera", "restaurante", "caja"), ("operario", "campo", "tecnico"), ("supervisor", "taller", "costura"),
                                                   ("supervisor", "general", "")])
def test_uniforme_por_cargo(role, template, uniform):
    assert of.uniform_for(role, template) == uniform


def test_dia_del_bar_de_18_a_04():
    tz = ZoneInfo("America/Bogota")
    cfg = of.BAR_DEFAULT_DAY
    at_2am = datetime(2026, 11, 12, 2, 0, tzinfo=tz)
    start, end, label = of.jornada(at_2am, tz, cfg)
    assert (start, end) == (datetime(2026, 11, 11, 18, 0, tzinfo=tz), datetime(2026, 11, 12, 4, 0, tzinfo=tz))
    assert label == "Jornada 18:00–04:00"
    start, end, _ = of.jornada(datetime(2026, 11, 12, 17, 0, tzinfo=tz), tz, cfg)
    assert start == datetime(2026, 11, 12, 18, 0, tzinfo=tz), "a las 17:00 aun no abre: la jornada de esta noche"
    start, end, label = of.jornada(datetime(2026, 11, 12, 17, 0, tzinfo=tz), tz, None)
    assert (start.hour, end - start, label) == (0, timedelta(days=1), "Hoy")


def test_minutos_trabajados_sin_pausas():
    s = datetime(2026, 11, 10, 5, 0, tzinfo=timezone.utc)
    ev = [{"employee_id": "a", "type": "check_in", "at": s + timedelta(hours=1)}, {"employee_id": "a", "type": "break_start", "at": s + timedelta(hours=3)},
          {"employee_id": "a", "type": "break_end", "at": s + timedelta(hours=3, minutes=30)}, {"employee_id": "a", "type": "check_out", "at": s + timedelta(hours=5)},
          {"employee_id": "b", "type": "check_out", "at": s + timedelta(hours=2)}]
    assert od.minutes_worked(ev, s, s + timedelta(hours=6), {"b": True}) == 3 * 60 + 30 + 2 * 60
    assert od.minutes_worked([], s, s + timedelta(minutes=90), {"c": True}) == 90, "turno abierto desde ayer cuenta desde el inicio del dia"


def test_orden_de_pisos_guardado_y_nuevas_al_final():
    companies = [{"id": "a", "created_at": "2026-01-01"}, {"id": "b", "created_at": "2026-02-01"}, {"id": "c", "created_at": "2026-03-01"}]
    assert [c["id"] for c in od.order_floors(companies, {"c": {"orden": 0}, "a": {"orden": 1}})] == ["c", "a", "b"]


def test_representantes_sin_dinero():
    source = (ROOT / "app/services/oficina_data.py").read_text(encoding="utf-8")
    labels = re.findall(r'\["([^"]+)", ', source)
    assert labels, "las cifras tienen etiqueta"
    for label in labels:
        assert not re.search(r"venta|\$|cop|usd|dinero|total|ingreso|propina|pago", label, re.I), label
    for sql in re.findall(r'"""(.*?)"""', source, re.S):
        assert "SUM(" not in sql.upper(), "ninguna consulta suma dinero"
        if "hospitality_orders" in sql:
            assert not re.search(r"\btotal\b|payment|tip", sql), "las consultas de pedidos no leen dinero"


# ------------------------------------------------------------------ editor
def test_editor_sin_imagen_ni_modelo_y_logo_por_su_firma():
    """Fase 1.5: el editor ya no valida archivos (las subidas responden 410); solo queda reconocer el logo
    del panel inicial por su firma real."""
    assert not hasattr(of, "check_file") and not hasattr(of, "file_url")
    assert "imagen" not in of.STYLES and "modelo" not in of.STYLES and "capa" not in of.ACCESSORIES
    assert of.sniff_image(b"\x89PNG\r\n\x1a\n" + b"\0" * 10) == ("image/png", "png")
    assert of.sniff_image(b"<svg onload=alert(1)>") is None


def test_campos_del_personaje_y_claves():
    out = of.clean_character({"nombre": "  Nexa <b>Pro</b> ", "estilo": "lego", "color_ropa": "#AABBCC", "accesorio": "casco", "otro": 1})
    assert out == {"nombre": "Nexa bPro/b", "estilo": "lego", "color_ropa": "#aabbcc", "accesorio": "casco"}
    assert of.clean_character({"cuerpo": "robusto", "peinado": "rizado"}) == {"cuerpo": "robusto", "peinado": "rizado"}
    for bad in ({"estilo": "batman"}, {"estilo": "imagen"}, {"estilo": "modelo"}, {"color_ropa": "red"}, {"accesorio": "espada"},
                {"accesorio": "capa"}, {"cuerpo": "gigante"}, {"peinado": "mohicano"}):
        with pytest.raises(of.Rejected):
            of.clean_character(bad)
    assert of.check_key("agente:ventas") == "agente:ventas" and of.check_key("plantilla:dj") == "plantilla:dj"
    for bad in ("agente:batman", "plantilla:astronauta", "persona:xyz", "../../x", ""):
        with pytest.raises(of.Rejected):
            of.check_key(bad)


# ------------------------------------------------------------------ pagina
def test_pagina_sin_codigo_en_linea_y_csp_con_hash_del_importmap():
    from app.web import oficina_routes as routes

    html = (ROOT / "app/web/oficina/oficina.html").read_text(encoding="utf-8")
    scripts = re.findall(r"<script(?![^>]*\bsrc=)([^>]*)>", html)
    assert scripts == [' type="importmap"'], "el unico script en linea es el importmap"
    assert not re.search(r"\son[a-z]+\s*=", html) and " style=" not in html
    csp = routes.page_csp(html)
    assert "'unsafe-inline'" not in csp and "cdn" not in html.lower()
    assert routes.importmap_hash(html) in csp
    assert '"three":"/admin-v2plus/oficina/vendor/three/build/three.module.js"' in html


def test_three_es_la_copia_fija_0_160_0():
    """Mismos bytes que el paquete three@0.160.0 de npm (integridad sha512 verificada al copiarlo)."""
    import hashlib

    expected = {
        "build/three.module.js": "76dea8151bc9352aef3528b4262e249b2604f62543828328db978d060d61a495",
        "examples/jsm/environments/RoomEnvironment.js": "e21f41b7ef2016f2984a5d27850b42dffa797a6a194a138e288b06576d765a7b",
        "examples/jsm/geometries/RoundedBoxGeometry.js": "d20aeaf7077c459a8d952d215738d7b44fba028440bb862d84b622a34f0c80bb",
        "examples/jsm/libs/meshopt_decoder.module.js": "01f48524f4bac6141eaba07e94cc36e7ee56f311796fa6117c159842941b0468",
        "examples/jsm/loaders/GLTFLoader.js": "d073b438e6a07e1359741dd5d6c76c953420cc0d4fd84eb1bdde94315540e6a3",
        "examples/jsm/loaders/RGBELoader.js": "f0e87d0008d9484d31358b32befd1bf80e4301f77573cc9a7cf7d871cc3f64b4",
        "examples/jsm/math/SimplexNoise.js": "9b8d541b77b0ddc79afaa6a1de8941452c191b8b9006f04e7b8fc422e2b263f7",
        "examples/jsm/postprocessing/EffectComposer.js": "d234e578618fa816955ebdc059c049c577e203e650e33cf22bde3f232c29e669",
        "examples/jsm/postprocessing/GTAOPass.js": "5140b7cc63800381ced45bef3a7a55c471f4be3cd9eb70b947e7ebfbe92658c2",
        "examples/jsm/postprocessing/MaskPass.js": "328cf7db0da5d9be83ffe39d54b01d5ac1fddf108cc98182ddbb056f5c8b537f",
        "examples/jsm/postprocessing/OutputPass.js": "13817fc7a87f662d29d2c5e00f44d3a4588c9afac4a372de0cacb0e44e368ffd",
        "examples/jsm/postprocessing/Pass.js": "b3c6128340eaa37e40a6a2f1b738e894c855239417d50959759b34a2b5e89f92",
        "examples/jsm/postprocessing/RenderPass.js": "1c90c085312871c4bcdccfcf519499c6276dd503363fcf7cb7f703add45cf4a2",
        "examples/jsm/postprocessing/ShaderPass.js": "3b28a1ee27e0eb96c0eab137a1f442ccf127a926904eced2d51e125ec44af781",
        "examples/jsm/postprocessing/UnrealBloomPass.js": "8f09315c0cec117a0ca2494d3e3586035b3c4323d6dcb037537cc51b04c3cdba",
        "examples/jsm/shaders/CopyShader.js": "4e3346db194db56a596cd074e9bdb39fb5eb52040c333e0d29dc4eb1324d3b1d",
        "examples/jsm/shaders/GTAOShader.js": "94edb1040c7b5e859b17c2817782c8e895118a2d824ed162cab187aa32cc5a15",
        "examples/jsm/shaders/LuminosityHighPassShader.js": "3d841cc594a0c1767d1b0185720b32761a0133c5f1b70b56658e28f2fb9b7900",
        "examples/jsm/shaders/OutputShader.js": "53a52e430c27bc36ceaab8ae90a2b4af7b02672d7ee4b29d6ba3c28e09c92c2a",
        "examples/jsm/shaders/PoissonDenoiseShader.js": "3dab419b23529f8fd59e2713458502f9f51d2dd3af3e1285dc671fcc451d49fb",
        "examples/jsm/utils/BufferGeometryUtils.js": "9be041e96308775d00e2695cc607645b9a9b64fd7c0e759dd8f7c00a8d92becb",
        "examples/jsm/utils/SkeletonUtils.js": "83748c5072a5ce96e9d68d8efda908a1f1a06c0b5fd2618edc3e54a361a8fd5b",
    }
    from app.web import oficina_routes as routes

    assert set(expected) == routes.THREE
    for rel, sha in expected.items():
        assert hashlib.sha256((ROOT / "app/web/vendor/three-0.160.0" / rel).read_bytes()).hexdigest() == sha, rel
