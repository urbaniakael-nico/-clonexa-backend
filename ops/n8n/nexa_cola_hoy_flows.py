"""2026-11-13 · Telegram mas liviano + prospeccion por demanda + mensajes sin el nombre del dueno (n8n).

Cambia SOLO estos flujos (exporta su JSON a respaldos-clonexa\\n8n\\<fecha>\\ antes y despues):
- "Nexa - Cola asistida": L-V 8:30 un solo mensaje "Cola de hoy" con el boton "Abrir la cola" y L-V 17:00 el
  resumen (antes: un mensaje con 5 botones por negocio). Los botones viejos (pa:/pv:) siguen funcionando.
- "Nexa - Prospección": no avisa por Telegram si hoy no busco (hay suficientes prospectos listos).
- "Nexa - WhatsApp ventas": "alguien del equipo de Clonexa" en vez del nombre del dueno.
El codigo de los dos primeros vive en nexa_prospeccion_flows.py (una sola fuente).
Secretos: referencias\\n8n-key.txt y nexa-ingest-token.txt (nunca se imprimen).
Uso (despues de desplegar el backend): py -3.11 ops/n8n/nexa_cola_hoy_flows.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import nexa_prospeccion_flows as npf  # noqa: E402
import nexa_v2_flows as v2  # noqa: E402

WA_REPLACE = [
    ("responde que Nicolás, del equipo de Clonexa, le escribe", "responde que alguien del equipo de Clonexa le escribe"),
    ("Nicolás, del equipo de Clonexa, te escribe", "Alguien del equipo de Clonexa te escribe"),
    ("Nicolás, del equipo de Clonexa, te confirma", "Alguien del equipo de Clonexa te confirma"),
    ("Nicolás from Clonexa will message", "Someone from the Clonexa team will message"),
    ("Nicolás from Clonexa will confirm", "Someone from the Clonexa team will confirm"),
]


def patch_wa_names(flow: dict) -> dict:
    """Reemplaza el nombre del dueno en el codigo de los nodos (texto exacto, nada mas)."""
    raw = json.dumps({"nodes": flow["nodes"], "connections": flow["connections"]}, ensure_ascii=False)
    for old, new in WA_REPLACE:
        raw = raw.replace(json.dumps(old, ensure_ascii=False)[1:-1], json.dumps(new, ensure_ascii=False)[1:-1])
    return json.loads(raw)


def main() -> None:
    cred = v2.backend_credential()
    secret = npf.hook_secret()
    existing = {w["name"]: w for w in v2.all_workflows()}
    targets = [npf.F_COLA, npf.F_PROSP, npf.F_WA]
    for name in targets:
        print("respaldo antes", npf.save_export(v2.call("GET", f"/workflows/{existing[name]['id']}"), "antes").name)
    err = (existing.get("Nexa - Errores") or {}).get("id")
    settings = {"errorWorkflow": err} if err else {}
    cf = npf.flow_cola(cred, secret)
    v2.upsert(npf.F_COLA, cf.nodes, cf.conns, settings, True, existing)
    pf = npf.flow_prospeccion(cred, secret)
    v2.upsert(npf.F_PROSP, pf.nodes, pf.conns, settings, True, existing)
    wa = v2.call("GET", f"/workflows/{existing[npf.F_WA]['id']}")
    patched = patch_wa_names(wa)
    if "Nicol" in json.dumps(patched, ensure_ascii=False):
        print("aviso: quedo una mencion del nombre en WhatsApp ventas (revisar a mano)")
    npf.put_existing(wa, patched)
    for name in targets:
        print("respaldo despues", npf.save_export(v2.call("GET", f"/workflows/{existing[name]['id']}"), "despues").name)


if __name__ == "__main__":
    main()
