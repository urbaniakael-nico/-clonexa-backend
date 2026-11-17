"""Despliega en n8n lo de "Publicar en TikTok" (sin tocar el resto de flujos Nexa):

1. Respaldo y DESACTIVA el flujo viejo "Nexa - TikTok" (sandbox: guardaba los tokens sin cifrar en n8n).
2. Crea/actualiza "Nexa - TikTok callback": webhook tiktok-callback -> backend (/api/v1/tiktok/n8n/callback)
   -> el navegador vuelve a la consola con "Cuenta conectada".
3. Actualiza "Nexa - Mostrar pieza": la vista previa de cada video suma el boton "Publicar en TikTok" que
   abre la pantalla con la pieza precargada (registrar la pieza NO publica nada).

Respaldo antes/despues en respaldos-clonexa\\n8n\\<fecha>\\. Requiere el backend desplegado con /api/v1/tiktok.
Uso: py -3.11 ops/n8n/tiktok_flows.py [--revisar]
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import nexa_v2_flows as v2  # noqa: E402

OLD_TIKTOK = "Nexa - TikTok"


def main() -> None:
    revisar = "--revisar" in sys.argv
    existing = {w["name"]: w for w in v2.all_workflows()}
    errores = existing.get("Nexa - Errores")
    common = {"errorWorkflow": errores["id"]} if errores else {}
    old = existing.get(OLD_TIKTOK)
    print("flujo viejo:", OLD_TIKTOK, "activo" if old and old.get("active") else "(no esta o ya inactivo)")
    print("se actualiza: Nexa - Mostrar pieza; se crea/actualiza: Nexa - TikTok callback")
    if revisar:
        return
    backend_cred = v2.backend_credential()
    secret_archivo = v2._secret("nexa-archivo-secret.txt")
    if old:
        full = v2.call("GET", f"/workflows/{old['id']}")
        v2.backup(full)
        if full.get("active"):
            v2.call("POST", f"/workflows/{old['id']}/deactivate")
        print("desactivado", OLD_TIKTOK, "(respaldo guardado)")
    v2.upsert("Nexa - TikTok callback", *v2._nc(v2.flow_tiktok_callback(backend_cred)), common, True, existing)
    v2.upsert("Nexa - Mostrar pieza", *v2._nc(v2.flow_mostrar(secret_archivo, backend_cred)), common, True, existing)
    for name in ("Nexa - TikTok callback", "Nexa - Mostrar pieza"):   # respaldo "despues"
        v2.backup(v2.call("GET", f"/workflows/{existing[name]['id']}"))


if __name__ == "__main__":
    main()
