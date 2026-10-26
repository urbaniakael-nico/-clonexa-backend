"""Empresa demo "Brasa & Maíz" de punta a punta por Menú video (producción).

Usa los MISMOS servicios que la consola v2+ (app.services.menu_video): crea
la demo (si no existe) con Carta, mesero/QR y carta_video encendido; sube la
carta en PDF inventada al bucket y la manda a leer a n8n (si n8n no responde,
llena la tabla a mano, como en la consola); empareja las fotos por nombre de
archivo, deja los clips en la cola (los procesa el servidor de producción),
publica (combinar) y activa la Mesa 1 para probar el QR.

Datos 100 % inventados. Fotos de Pexels (ops/demo/brasa-y-maiz/fuentes-fotos.json).
Uso (variables del backend + base publica):
  railway run --service=-clonexa-backend py -3.11 scripts/menu_video_demo.py <carpeta_fotos>
con DATABASE_URL apuntando a la URL publica de Postgres (postgresql+asyncpg://).
Nunca imprime secretos.
"""
from __future__ import annotations

import asyncio
import json
import os
import secrets
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
DEMO = ROOT / "ops" / "demo" / "brasa-y-maiz"
NAME, SLUG = "Brasa & Maíz (demo)", "brasa-y-maiz-demo"
BASE_URL = os.getenv("CX_PUBLIC_BASE", "https://clonexa-backend-production.up.railway.app")


async def ensure_company(db, text) -> str:
    row = (await db.execute(text("SELECT id::text AS id FROM companies WHERE slug = :s"), {"s": SLUG})).mappings().first()
    if row:
        return row["id"]
    cid = str(uuid.uuid4())
    await db.execute(text("""
        INSERT INTO companies (id, name, slug, status, timezone, plan, settings_json, created_at, updated_at)
        VALUES (CAST(:i AS uuid), :n, :s, 'active', 'America/Bogota', 'standard', CAST(:j AS jsonb), now(), now())
    """), {"i": cid, "n": NAME, "s": SLUG, "j": json.dumps({"kind": "demo", "nota": "Demo de Menú video, datos inventados"})})
    return cid


async def ensure_module(db, text, cid: str, code: str, settings: dict) -> None:
    mod = (await db.execute(text("SELECT id::text AS id FROM modules WHERE LOWER(code) = :c"), {"c": code})).mappings().first()
    if not mod:
        raise SystemExit(f"No existe el módulo {code} en la base.")
    found = (await db.execute(text("SELECT id FROM company_modules WHERE company_id = CAST(:c AS uuid) AND module_id = CAST(:m AS uuid)"),
                              {"c": cid, "m": mod["id"]})).first()
    if found:
        await db.execute(text("""
            UPDATE company_modules SET enabled = true, settings = COALESCE(settings, '{}'::jsonb) || CAST(:s AS jsonb), updated_at = now()
            WHERE company_id = CAST(:c AS uuid) AND module_id = CAST(:m AS uuid)
        """), {"c": cid, "m": mod["id"], "s": json.dumps(settings)})
    else:
        await db.execute(text("""
            INSERT INTO company_modules (id, company_id, module_id, enabled, settings, activated_at, created_at, updated_at)
            VALUES (CAST(:i AS uuid), CAST(:c AS uuid), CAST(:m AS uuid), true, CAST(:s AS jsonb), now(), now(), now())
        """), {"i": str(uuid.uuid4()), "c": cid, "m": mod["id"], "s": json.dumps(settings)})


async def main(photos_dir: str) -> None:
    from sqlalchemy import text

    from app.core.database import AsyncSessionLocal
    from app.services import menu_video as mv

    fuentes = json.loads((DEMO / "fuentes-fotos.json").read_text(encoding="utf-8"))
    by_file = {f["archivo"]: f for f in fuentes["fotos"]}
    async with AsyncSessionLocal() as db:
        cid = await ensure_company(db, text)
        await ensure_module(db, text, cid, "carta", {mv.FLAG: True, mv.QUOTA_NEW_KEY: 3, mv.QUOTA_CHANGES_KEY: 3})
        await ensure_module(db, text, cid, "waiter_ordering", {})
        settings = (await mv.carta_module(db, cid))["settings"]
        qr_token = settings.get("qr_token") or secrets.token_urlsafe(24)
        await ensure_module(db, text, cid, "carta", {"qr_token": qr_token})
        await db.commit()
        print(f"Empresa demo: {NAME} ({cid})")

        # 2) importar: la carta en PDF al bucket privado y a n8n
        t0 = time.perf_counter()
        pdf = (DEMO / "carta-brasa-y-maiz.pdf").read_bytes()
        import_id = str(uuid.uuid4())
        key = f"menuvideo-import/{cid}/{import_id}/0.pdf"
        await asyncio.to_thread(mv._put, key, pdf, "application/pdf", True)
        files = [{"tipo": "pdf", "nombre": "carta-brasa-y-maiz.pdf", "media_type": "application/pdf", "key": key, "size": len(pdf)}]
        await db.execute(text("""
            INSERT INTO menu_video_imports (id, company_id, status, source, files, table_data)
            VALUES (CAST(:i AS uuid), CAST(:c AS uuid), 'leyendo', 'archivos', CAST(:f AS jsonb), '{"categorias":[],"platos":[]}'::jsonb)
        """), {"i": import_id, "c": cid, "f": json.dumps(files)})
        await db.commit()
        ok, why = await mv.call_n8n(mv.read_webhook_url(), {
            "job_id": import_id, "company_id": cid, "callback_url": f"{BASE_URL}/api/v1/menu-video/import-callback",
            "archivos": [{"tipo": "pdf", "nombre": files[0]["nombre"], "media_type": "application/pdf", "url": mv.presign(key, 900)}]})
        print(f"n8n: {'recibió la carta' if ok else 'no disponible: ' + why}")
        current = None
        for _ in range(60 if ok else 0):
            await asyncio.sleep(3)
            current = await mv.get_import(db, cid, import_id)
            await db.commit()
            if current and current["status"] != "leyendo":
                break
        if current and current["status"] == "lista":
            print(f"Lectura con Claude: {len(current['table_data']['platos'])} platos en {time.perf_counter() - t0:.0f} s")
        else:
            reason = (current or {}).get("error") or why or "sin respuesta"
            print(f"Lectura automática no disponible ({reason}). Se llena la tabla a mano, como en la consola.")
            manual = json.loads((DEMO / "carta-manual.json").read_text(encoding="utf-8"))
            await mv.save_table(db, cid, import_id, manual, status="lista", error=None)
            await db.execute(text("UPDATE menu_video_imports SET source = 'manual' WHERE id = CAST(:i AS uuid)"), {"i": import_id})
            await db.commit()
            current = await mv.get_import(db, cid, import_id)
        dishes = current["table_data"]["platos"]

        # 3) fotos por plato, emparejadas por nombre de archivo
        matched = 0
        for name in sorted(os.listdir(photos_dir)):
            ref, role = mv.match_photo(name, dishes)
            if not ref:
                print(f"  sin plato: {name}")
                continue
            src = by_file.get(name, {})
            await mv.save_photo(db, cid, ref, role, Path(photos_dir, name).read_bytes(), name,
                                meta={"import_id": import_id, "fuente": src.get("fuente"), "licencia": src.get("licencia")})
            await db.commit()
            matched += 1
        print(f"Fotos emparejadas por nombre: {matched} de {len(dishes)} platos")

        # 4) remasterizar y clips: los procesa la cola del servidor
        for d in dishes:
            if (await mv.dish_media(db, cid, d["ref"]) or {}).get("front_original"):
                await mv.enqueue(db, cid, d["ref"], "auto")
        await db.commit()
        refs = [d["ref"] for d in dishes]
        for _ in range(100):
            jobs = await mv.jobs_for(db, cid, refs)
            await db.commit()
            if jobs and all(j["status"] in ("listo", "error") for j in jobs.values()):
                break
            await asyncio.sleep(4)
        jobs = await mv.jobs_for(db, cid, refs)
        done = [j for j in jobs.values() if j["status"] == "listo"]
        print(f"Clips listos: {len(done)}; errores: {[j['error'] for j in jobs.values() if j['status'] == 'error']}")
        if done:
            n = len(done)
            avg = lambda k: sum(j["result"].get(k, 0) for j in done) / n  # noqa: E731
            print(f"  promedio en producción: total {avg('total_ms') / 1000:.2f} s, remaster {avg('front_remaster_ms') / 1000:.2f} s, "
                  f"clip {avg('clip_ms') / 1000:.2f} s, peso {avg('clip_bytes') / 1024:.0f} KB (máx {max(j['result'].get('clip_bytes', 0) for j in done) / 1024:.0f} KB)")

        # 5) publicar = combinar
        plan = await mv.plan_publish(db, cid, current["table_data"])
        print(f"Plan: {plan['counts']['new']} platos nuevos, {plan['counts']['updated']} actualizados, 0 borrados")
        summary = await mv.publish(db, cid, import_id, current["table_data"])
        await db.commit()
        print(f"Publicado: {summary['new']} nuevos, {summary['updated']} actualizados, {summary['deleted']} borrados")

        # Mesa 1 activa para probar el QR (código de una mesa demo)
        code = "".join(secrets.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(5))
        await db.execute(text("""
            UPDATE hospitality_table_access SET status = 'closed', updated_at = now()
            WHERE company_id = CAST(:c AS uuid) AND table_key = 'mesa 1' AND status = 'active'
        """), {"c": cid})
        await db.execute(text("""
            INSERT INTO hospitality_table_access (company_id, table_key, table_number, access_code, status, activated_at, expires_at,
                                                  closes_with_table, created_at, updated_at)
            VALUES (CAST(:c AS uuid), 'mesa 1', 'Mesa 1', :code, 'active', now(), now() + interval '30 days', false, now(), now())
        """), {"c": cid, "code": code})
        await db.commit()
        print(f"QR de la mesa: {BASE_URL}/ordenar?company_id={cid}&mesa=Mesa%201  (clave de la mesa demo: {code})")
        print(f"QR de la carta: {BASE_URL}/carta-qr?t={qr_token}")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1]))
