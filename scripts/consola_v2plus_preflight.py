"""Consola v2+ · conteos previos, SOLO LECTURA (nunca escribe).

Uso (con la variable DATABASE_PUBLIC_URL del servicio Postgres de Railway):

    railway run -s Postgres py -3.11 scripts/consola_v2plus_preflight.py

Imprime:
1. Cuantas marcas guardadas no cumplen la validacion nueva (logo, colores,
   fuente, angulo) y de que tipo son los logos (https, ruta, data:, otro).
2. Como quedaria cada empresa con la migracion de tipo (registrada | demo).
3. Tamaño de la base frente al limite de 500 MB.
La sesion se abre con default_transaction_read_only=on y no imprime la URL.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

LIVE_COMPANY_IDS = {
    "7625872c-f941-4479-a27b-f8443be953c5",  # ASADERO EL SOCIO
    "21a3065e-38ee-4fc3-96ed-ae1707a3b8e4",  # The Time Machine
    "d63cf68c-be5b-4a30-aee4-341973018db1",  # Velvet
}


def _store(raw):
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            return {}
    return raw if isinstance(raw, dict) else {}


def _branding(store: dict) -> dict:
    for candidate in (store.get("branding"), store.get("company_branding"),
                      (store.get("experience") or {}).get("branding") if isinstance(store.get("experience"), dict) else None):
        if isinstance(candidate, dict) and candidate:
            return candidate
    return {}


def _problems(branding: dict) -> list[str]:
    from fastapi import HTTPException

    from app.api.v1.endpoints.companies import validate_branding_payload

    try:
        validate_branding_payload(branding)
        return []
    except HTTPException as error:
        return [str(error.detail)]


def _logo_kind(value) -> str:
    text = str(value or "").strip()
    if not text:
        return "vacio"
    if text.startswith("https://"):
        return "https"
    if text.startswith("data:"):
        return "data:"
    if text.startswith("/"):
        return "ruta propia"
    return "otro"


async def main() -> None:
    import asyncpg

    url = (os.environ.get("DATABASE_PUBLIC_URL") or os.environ.get("DATABASE_URL") or "").replace("postgresql+asyncpg://", "postgresql://")
    if not url:
        raise SystemExit("Falta DATABASE_PUBLIC_URL (corre con: railway run -s Postgres ...)")
    conn = await asyncpg.connect(url, server_settings={"default_transaction_read_only": "on"}, timeout=30)
    try:
        rows = await conn.fetch("SELECT id::text AS id, name, slug, status, settings_json FROM companies ORDER BY name")
        bad, kinds = [], {}
        groups = {"registrada": [], "demo": []}
        for row in rows:
            store = _store(row["settings_json"])
            branding = _branding(store)
            kind = _logo_kind(branding.get("logo_url"))
            kinds[kind] = kinds.get(kind, 0) + 1
            problems = _problems(branding) if branding else []
            if problems:
                bad.append((row["slug"], problems[0]))
            current = store.get("kind")
            target = "registrada" if row["id"] in LIVE_COMPANY_IDS else "demo"
            groups[target].append(f"{row['name']} ({row['slug']}, {row['status']}, id {row['id'][:8]}"
                                  f"{', hoy kind=' + str(current) if current else ''})")
        print("== 1. Marcas guardadas que NO cumplen la validacion nueva:", len(bad))
        for slug, problem in bad:
            print(f"   - {slug}: {problem}")
        print("   Logos por tipo:", json.dumps(kinds, ensure_ascii=False))
        print("\n== 2. Tipo de empresa tras la migracion 023a_company_kind")
        for name in ("registrada", "demo"):
            print(f"   {name.upper()} ({len(groups[name])})")
            for line in groups[name]:
                print("     -", line)
        size = await conn.fetchval("SELECT pg_database_size(current_database())")
        print(f"\n== 3. Base de datos: {size / 1024 / 1024:.1f} MB de 500 MB")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
