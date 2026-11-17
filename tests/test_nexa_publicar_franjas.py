"""Nexa - Publicar del dia: franjas AM (11:30) y PM (19:00) desde el 17/11/2026, y filas sin AM/PM
(L/M/V 12:00) como antes. Ejecuta con Node el JavaScript real de los nodos "Entrada" y "Elegir pieza"."""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ops" / "n8n"))
import nexa_v2_flows as npf  # noqa: E402

NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="sin node")

FLOW = npf.flow_publicar("secreto-archivo", "secreto-webhook")
NODES = {n["name"]: n for n in FLOW.nodes}
HEADER = ["Fecha", "Día", "Formato", "Módulo", "Tema", "Gancho", "IG", "LI", "TT", "Hashtags", "Archivo", "Estado", "Enlaces"]


def fila(fecha, formato, estado, tema):
    return [fecha, "", formato, "", tema, "", "", "", "", "", tema + ".mp4", estado, ""]


CAL = [HEADER,
       fila("17/11/2026", "AM · Anuncio visual", "Aprobado", "am-hoy"),
       fila("17/11/2026", "PM · Reel En vivo 15 s", "Aprobado", "pm-hoy"),
       fila("18/11/2026", "PM · Reel", "Aprobado", "pm-manana"),
       fila("25/11/2026", "Anuncio visual", "Aprobado", "sin-franja"),
       fila("16/12/2026", "Anuncio (plan B)", "Listo para aprobar", "plan-b")]


def run_js(code: str, executed: dict, run_index: int = 0):
    """Corre el codigo de un nodo Code con un $() falso: executed = {nodo: [json, ...]}."""
    harness = """
const EXEC = %s;
const $ = n => {
  const v = EXEC[n];
  if (!v) return { isExecuted: false, first: () => { throw new Error('no ejecutado ' + n); }, last: () => { throw new Error('no ejecutado ' + n); }, all: () => { throw new Error('no ejecutado ' + n); } };
  return { isExecuted: true, first: () => ({ json: v[0] }), last: () => ({ json: v[v.length - 1] }), all: () => v.map(j => ({ json: j })) };
};
const $runIndex = %d;
const out = (function () { %s })();
process.stdout.write(JSON.stringify(out));
""" % (json.dumps(executed), run_index, code)
    r = subprocess.run([NODE, "-e", harness], capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)[0]["json"]


def entrada(trigger: str | None, query: dict | None = None):
    executed = {trigger: [{}]} if trigger else {}
    if query is not None:
        executed["Simular o probar (enlace)"] = [{"query": query}]
    return run_js(NODES["Entrada"]["parameters"]["jsCode"], executed)


def elegir(fecha: str, franja: str, hechas=()):
    executed = {"Entrada": [{"fecha": fecha, "simular": False, "todas": False, "franja": franja}],
                "Leer calendario": [{"values": CAL}], "Archivos en Drive": [{"files": []}]}
    if hechas:
        executed["Fila publicada"] = [{"fila": f} for f in hechas]
    return run_js(NODES["Elegir pieza"]["parameters"]["jsCode"], executed)


def test_tres_disparadores_en_hora_bogota():
    crons = {n["name"]: n["parameters"]["rule"]["interval"][0]["expression"] for n in FLOW.nodes if n["type"].endswith("scheduleTrigger")}
    assert crons == {"Cada día 11:30 (AM)": "30 11 * * *", "L, M y V 12:00": "0 12 * * 1,3,5", "Cada día 19:00 (PM)": "0 19 * * *"}
    for name in crons:
        assert FLOW.conns[name]["main"][0][0]["node"] == "Entrada"


def test_la_franja_sale_del_disparador():
    assert entrada("Cada día 11:30 (AM)")["franja"] == "am"
    assert entrada("Cada día 19:00 (PM)")["franja"] == "pm"
    assert entrada("L, M y V 12:00")["franja"] == "sin"


def test_simulacion_por_enlace_con_o_sin_franja():
    assert entrada(None, {"k": "secreto-webhook", "fecha": "17/11/2026"})["franja"] == "todas"
    assert entrada(None, {"k": "secreto-webhook", "fecha": "17/11/2026", "franja": "pm"})["franja"] == "pm"


def test_am_y_pm_publican_solo_su_fila_y_una_vez():
    am = elegir("2026-11-17", "am")
    assert am["nada"] is False and am["tema"] == "am-hoy" and am["otras"] == 0
    pm = elegir("2026-11-17", "pm")
    assert pm["nada"] is False and pm["tema"] == "pm-hoy" and pm["otras"] == 0
    # ya publicada en esta ejecucion -> no se repite
    again = elegir("2026-11-17", "am", hechas=[am["fila"]])
    assert again["nada"] is True and again["primera"] is False


def test_filas_sin_am_pm_siguen_a_las_12_y_las_franjas_no_las_toman():
    assert elegir("2026-11-25", "sin")["tema"] == "sin-franja"
    assert elegir("2026-11-25", "am")["nada"] is True
    assert elegir("2026-11-17", "sin")["nada"] is True


def test_sin_filas_en_la_franja_no_avisa_nada_que_publicar():
    vacia = elegir("2026-11-26", "am")
    assert vacia["nada"] is True and vacia["silencio"] is True
    # hay fila PM manana pero no AM: la franja AM calla; la PM si avisaria si no estuviera aprobada
    assert elegir("2026-11-18", "am")["silencio"] is True
    assert "!$json.silencio" in NODES["¿Primera vuelta?"]["parameters"]["conditions"]["conditions"][0]["leftValue"]


def test_si_falta_el_archivo_de_la_fila_no_toma_el_de_otra_fila_del_mismo_dia():
    # La fila AM nombra un archivo que no esta en Drive; el reel de la PM del mismo dia si esta.
    executed = {"Entrada": [{"fecha": "2026-11-17", "simular": False, "todas": False, "franja": "am"}],
                "Leer calendario": [{"values": CAL}],
                "Archivos en Drive": [{"files": [{"id": "x", "name": "2026-11-17 pm-hoy.mp4", "mimeType": "video/mp4"}]}]}
    am = run_js(NODES["Elegir pieza"]["parameters"]["jsCode"], executed)
    assert am["tema"] == "am-hoy" and am["kind"] == "nada" and am["file_id"] == ""
    executed["Entrada"] = [{"fecha": "2026-11-17", "simular": False, "todas": False, "franja": "pm"}]
    pm = run_js(NODES["Elegir pieza"]["parameters"]["jsCode"], executed)
    assert pm["file_name"] == "2026-11-17 pm-hoy.mp4"
