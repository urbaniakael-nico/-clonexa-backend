"""n8n "Oficina - Estado": NO guardar las ejecuciones exitosas (saveDataSuccessExecution = none).

Corre cada pocos segundos; guardar cada ejecucion exitosa llena la base de n8n sin servir de nada (los errores si se
guardan). Antes de cambiarlo exporta el flujo tal cual a respaldos-clonexa\\n8n\\<fecha>\\ (nexa_v2_flows.backup).
Solo toca los ajustes: nodos y conexiones quedan iguales. Nunca imprime la clave de la API.

    py -3.11 ops/n8n/oficina_estado_ajustes.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import nexa_v2_flows as v2  # noqa: E402  (API de n8n y respaldo)

NAME = "Oficina - Estado"
WANT = {"saveDataSuccessExecution": "none", "saveDataErrorExecution": "all", "saveManualExecutions": False}


def main() -> None:
    found = next((w for w in v2.all_workflows() if w["name"] == NAME), None)
    if not found:
        sys.exit(f"No existe el flujo {NAME!r} en n8n.")
    cur = v2.call("GET", f"/workflows/{found['id']}")
    v2.backup(cur)
    print("respaldo guardado en", v2.BACKUPS)
    settings = dict(cur.get("settings") or {})
    if all(settings.get(k) == v for k, v in WANT.items()):
        print(NAME, found["id"], "ya no guarda ejecuciones exitosas: sin cambios")
        return
    settings.update(WANT)
    active = bool(cur.get("active"))
    if active:
        v2.call("POST", f"/workflows/{found['id']}/deactivate")
    try:
        v2.call("PUT", f"/workflows/{found['id']}", v2.body_of(cur["name"], cur["nodes"], cur["connections"], settings))
    finally:
        if active:
            v2.call("POST", f"/workflows/{found['id']}/activate")
    after = (v2.call("GET", f"/workflows/{found['id']}").get("settings") or {})
    print(NAME, found["id"], "saveDataSuccessExecution =", after.get("saveDataSuccessExecution"), "| activo:", active)


if __name__ == "__main__":
    main()
