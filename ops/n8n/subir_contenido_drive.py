"""Sube las piezas de Nexa (OneDrive\\Desktop\\nexa-escenas\\_contenido) a Google Drive "Nexa / Contenido",
la carpeta que leen la vista previa y el publicador, con el nombre que reconocen: "AAAA-MM-DD <archivo>".

Dos modos:
  py -3.11 ops/n8n/subir_contenido_drive.py --hoja
      Lee el calendario y sube el archivo de cada fila AM/PM de hoy en adelante que todavia no este en
      Drive (la ruta de la columna Archivo, relativa a OneDrive\\Desktop).
  py -3.11 ops/n8n/subir_contenido_drive.py --carpeta "C:\\Users\\valef\\OneDrive\\Desktop\\nexa-escenas\\_contenido\\2026-11-23" [--desde 2026-11-24] [--hasta 2026-11-30]
      Sube los archivos de la carpeta; la fecha sale del dia del nombre ("martes-24-..." -> 2026-11-24;
      el mes y el ano salen del nombre de la carpeta y si el dia es menor, es el mes siguiente).

Los carruseles (subcarpetas con laminas .png/.jpg) se suben como carpeta con sus laminas. Nunca duplica:
si ya hay un archivo con ese nombre en la carpeta destino, lo deja. Usa un flujo temporal de n8n con la
credencial de Drive del publicador y lo borra al terminar. La clave de n8n se lee de
C:\\Users\\valef\\Desktop\\referencias\\n8n-key.txt (no se imprime). --simular muestra el plan sin subir nada.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import mimetypes
import re
import secrets
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import nexa_v2_flows as v2  # noqa: E402

ROOT = "10cWifMMbdgD_7Cq-Cr4Cyao93ymxV5je"  # Nexa / Contenido
SHEET = "1A0qx99Pw4vk3EwC_qdi4XkLBWxmBysSKxJIggGKSpwg"
ONEDRIVE = Path(r"C:\Users\valef\OneDrive\Desktop")
PUBLICADOR = "b8Tj5g1BRhYiyr4k"
MEDIA = {".mp4", ".mov", ".png", ".jpg", ".jpeg"}
DAY = re.compile(r"^(?:lunes|martes|miercoles|miércoles|jueves|viernes|sabado|sábado|domingo)-(\d{1,2})-", re.I)


def fecha_de(nombre: str, carpeta: str) -> str | None:
    """'martes-24-x.mp4' en la carpeta '2026-11-23' -> '2026-11-24' (mes siguiente si el dia es menor)."""
    m, c = DAY.match(nombre), re.match(r"(\d{4})-(\d{2})-(\d{2})", carpeta)
    if not m or not c:
        return None
    y, mo, d0, d = int(c.group(1)), int(c.group(2)), int(c.group(3)), int(m.group(1))
    if d < d0:
        mo, y = (1, y + 1) if mo == 12 else (mo + 1, y)
    try:
        return dt.date(y, mo, d).isoformat()
    except ValueError:
        return None


def flujo_temporal() -> tuple[str, str]:
    pub = v2.call("GET", f"/workflows/{PUBLICADOR}")
    cred = next(n["credentials"] for n in pub["nodes"] if n["name"] == "Archivos en Drive")
    path = "tmp-contenido-" + secrets.token_hex(8)
    drive = {"authentication": "predefinedCredentialType", "nodeCredentialType": "googleDriveOAuth2Api"}
    cond = lambda cid, expr: {"conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose"},
                                             "conditions": [{"id": cid, "leftValue": "={{ " + expr + " }}", "rightValue": "",
                                                             "operator": {"type": "boolean", "operation": "true", "singleValue": True}}],
                                             "combinator": "and"}, "options": {}}
    q = "={{ \"'\" + $json.query.parent + \"' in parents and trashed=false and name = '\" + $json.query.name.replace(/'/g, \"\\\\'\") + \"'\" }}"
    nodes = [
        {"id": "h", "name": "Hook", "type": "n8n-nodes-base.webhook", "typeVersion": 2, "position": [0, 0], "webhookId": path,
         "parameters": {"httpMethod": "POST", "path": path, "responseMode": "lastNode", "options": {"binaryPropertyName": "data", "rawBody": True}}},
        {"id": "e", "name": "Existe", "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2, "position": [200, 0], "credentials": cred,
         "parameters": {"method": "GET", "url": "https://www.googleapis.com/drive/v3/files", **drive, "sendQuery": True,
                        "queryParameters": {"parameters": [{"name": "q", "value": q}, {"name": "fields", "value": "files(id,name)"}]}, "options": {}}},
        {"id": "n", "name": "¿Nuevo?", "type": "n8n-nodes-base.if", "typeVersion": 2, "position": [400, 0], "parameters": cond("c1", "($json.files || []).length === 0")},
        {"id": "y", "name": "Ya estaba", "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [600, 200],
         "parameters": {"jsCode": "return [{ json: { ya: true, id: $('Existe').first().json.files[0].id } }];"}},
        {"id": "f", "name": "¿Carpeta?", "type": "n8n-nodes-base.if", "typeVersion": 2, "position": [600, 0], "parameters": cond("c2", "$('Hook').first().json.query.folder === '1'")},
        {"id": "c", "name": "Crear carpeta", "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2, "position": [800, -100], "credentials": cred,
         "parameters": {"method": "POST", "url": "https://www.googleapis.com/drive/v3/files", **drive, "sendBody": True, "specifyBody": "json",
                        "jsonBody": "={{ JSON.stringify({ name: $('Hook').first().json.query.name, mimeType: 'application/vnd.google-apps.folder', parents: [$('Hook').first().json.query.parent] }) }}",
                        "options": {}}},
        {"id": "a", "name": "Archivo", "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [800, 100],
         "parameters": {"jsCode": "return [{ json: { name: $('Hook').first().json.query.name }, binary: $('Hook').first().binary }];"}},
        {"id": "s", "name": "Subir", "type": "n8n-nodes-base.googleDrive", "typeVersion": 3, "position": [1000, 100], "credentials": cred,
         "parameters": {"name": "={{ $json.name }}", "driveId": {"__rl": True, "mode": "list", "value": "My Drive"},
                        "folderId": {"__rl": True, "mode": "id", "value": "={{ $('Hook').first().json.query.parent }}"}, "inputDataFieldName": "data", "options": {}}},
    ]
    link = lambda a, b, out=0: conns.setdefault(a, {"main": [[], []]})["main"][out].append({"node": b, "type": "main", "index": 0})
    conns: dict = {}
    link("Hook", "Existe"); link("Existe", "¿Nuevo?"); link("¿Nuevo?", "¿Carpeta?", 0); link("¿Nuevo?", "Ya estaba", 1)
    link("¿Carpeta?", "Crear carpeta", 0); link("¿Carpeta?", "Archivo", 1); link("Archivo", "Subir")
    wid = v2.call("POST", "/workflows", {"name": "TEMP - subir contenido a Drive (se borra)", "nodes": nodes, "connections": conns,
                                         "settings": {"executionOrder": "v1"}})["id"]
    v2.call("POST", f"/workflows/{wid}/activate")
    time.sleep(2)
    return wid, path


def enviar(path: str, name: str, parent: str, data: bytes = b"", folder: bool = False) -> dict:
    mime = "application/json" if folder else (mimetypes.guess_type(name)[0] or "application/octet-stream")
    url = f"{v2.BASE}/webhook/{path}?" + urllib.parse.urlencode({"name": name, "parent": parent, "folder": "1" if folder else "0"})
    req = urllib.request.Request(url, data=data or b"{}", method="POST", headers={"Content-Type": mime})
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.loads(r.read() or b"{}")


def leer_hoja() -> list[list[str]]:
    """Lee el calendario con otro flujo temporal (solo lectura)."""
    pub = v2.call("GET", f"/workflows/{PUBLICADOR}")
    cred = next(n["credentials"] for n in pub["nodes"] if n["name"] == "Archivos en Drive")
    path = "tmp-hoja-" + secrets.token_hex(8)
    wf = {"name": "TEMP - leer calendario (se borra)", "settings": {"executionOrder": "v1"},
          "nodes": [{"id": "h", "name": "Hook", "type": "n8n-nodes-base.webhook", "typeVersion": 2, "position": [0, 0], "webhookId": path,
                     "parameters": {"httpMethod": "GET", "path": path, "responseMode": "lastNode", "options": {}}},
                    {"id": "r", "name": "Leer", "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2, "position": [200, 0], "credentials": cred,
                     "parameters": {"method": "GET", "url": f"https://sheets.googleapis.com/v4/spreadsheets/{SHEET}/values/Calendario!A1:M800",
                                    "authentication": "predefinedCredentialType", "nodeCredentialType": "googleDriveOAuth2Api", "options": {}}}],
          "connections": {"Hook": {"main": [[{"node": "Leer", "type": "main", "index": 0}]]}}}
    wid = v2.call("POST", "/workflows", wf)["id"]
    try:
        v2.call("POST", f"/workflows/{wid}/activate")
        time.sleep(2)
        with urllib.request.urlopen(f"{v2.BASE}/webhook/{path}", timeout=120) as r:
            return json.loads(r.read() or b"{}").get("values", [])
    finally:
        _borrar(wid)


def _borrar(wid: str) -> None:
    try:
        v2.call("POST", f"/workflows/{wid}/deactivate")
    except Exception:
        pass
    v2.call("DELETE", f"/workflows/{wid}")


def plan_hoja() -> list[tuple[Path, str]]:
    hoy = (dt.datetime.utcnow() - dt.timedelta(hours=5)).date().isoformat()
    plan = []
    for r in leer_hoja()[1:]:
        r = (r + [""] * 13)[:13]
        m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", r[0])
        if not m or not re.match(r"\s*(AM|PM)\s*·", r[2], re.I) or not r[10]:
            continue
        iso = f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
        if iso < hoy or r[11].strip().lower() in ("publicado", "descartado"):
            continue
        local = ONEDRIVE / r[10]
        if local.exists():
            plan.append((local, f"{iso} {local.name}"))
        else:
            print(f"  (falta en OneDrive) {r[0]} {r[2][:30]}: {r[10]}")
    return plan


def plan_carpeta(carpeta: Path, desde: str, hasta: str) -> list[tuple[Path, str]]:
    plan = []
    for p in sorted(carpeta.iterdir()):
        iso = fecha_de(p.name, carpeta.name)
        if not iso or iso < desde or iso > hasta:
            continue
        if p.is_dir() or p.suffix.lower() in MEDIA:
            plan.append((p, f"{iso} {p.name}"))
    return plan


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--hoja", action="store_true")
    g.add_argument("--carpeta")
    ap.add_argument("--desde", default="0000-00-00")
    ap.add_argument("--hasta", default="9999-99-99")
    ap.add_argument("--simular", action="store_true")
    a = ap.parse_args()
    plan = plan_hoja() if a.hoja else plan_carpeta(Path(a.carpeta), a.desde, a.hasta)
    # una vez por nombre (dos filas pueden usar el mismo archivo el mismo dia)
    plan = list({name: (p, name) for p, name in plan}.values())
    if not plan:
        print("Nada que subir.")
        return
    for p, name in plan:
        print(f"  {'carpeta' if p.is_dir() else 'archivo'}: {name}")
    if a.simular:
        return
    wid, path = flujo_temporal()
    try:
        for p, name in plan:
            if p.is_dir():
                out = enviar(path, name, ROOT, folder=True)
                print(("ya estaba: " if out.get("ya") else "carpeta creada: ") + name)
                for img in sorted(x for x in p.iterdir() if x.suffix.lower() in {".png", ".jpg", ".jpeg"}):
                    o = enviar(path, img.name, out["id"], img.read_bytes())
                    print(f"    {'ya estaba' if o.get('ya') else 'subida'}: {img.name}")
            else:
                out = enviar(path, name, ROOT, p.read_bytes())
                print(("ya estaba: " if out.get("ya") else f"subido ({p.stat().st_size // 1024} KB): ") + name)
    finally:
        _borrar(wid)
        print("flujo temporal borrado")


if __name__ == "__main__":
    main()
