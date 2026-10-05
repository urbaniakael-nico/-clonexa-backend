"""Consola v2+ · Empresas: acciones NUEVAS (no existen en Admin V2).

- POST /admin-v2/api/companies/{id}/kind         cambiar tipo (demo | registrada)
- POST /admin-v2/api/companies/{id}/clone-demo   clonar como demo (solo configuracion)
- POST /admin-v2/api/companies/{id}/purge        eliminar definitivo (simulacion y ejecucion)

Todas exigen la sesion de Admin V2 validada en el servidor
(_require_admin_v2_session); sin ella responden 401 JSON. Crear, cambiar
estado y archivar NO estan aqui: v2+ usa los mismos endpoints de Admin V2.

Candados:
- Las tres empresas vivas (company_kind.LIVE_COMPANY_IDS) nunca se eliminan
  desde la consola (403) ni pasan a demo (403).
- Demo -> registrada exige confirm=true.
- Eliminar: demos en cualquier estado; registradas solo si estan archivadas;
  ejecutar exige confirm_name igual al nombre exacto. Todo en una transaccion.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.services import company_kind as kinds
from app.services import company_lifecycle as lifecycle
from app.web import admin_v2_routes as v2

router = APIRouter()


async def require_session(request: Request, db: AsyncSession) -> None:
    """_require_admin_v2_session de Admin V2, pero en JSON (401) para la API."""
    try:
        await v2._require_admin_v2_session(request, db)
    except HTTPException as error:
        raise HTTPException(status_code=401, detail="Sesión de Admin V2 requerida.") from error


async def session_required(request: Request, db: AsyncSession = Depends(get_db)) -> None:
    """Dependencia: corre ANTES de leer el cuerpo (sin sesion, 401 y nada mas)."""
    await require_session(request, db)


GUARD = [Depends(session_required)]


def _json(data: dict, status_code: int = 200) -> JSONResponse:
    return v2._no_store(JSONResponse(data, status_code=status_code))


def _uuid(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Empresa no encontrada.") from exc


async def load_company(db: AsyncSession, company_id: uuid.UUID) -> dict:
    row = (await db.execute(text(
        "SELECT id::text AS id, name, slug, status, settings_json FROM companies WHERE id = CAST(:id AS uuid)"
    ), {"id": str(company_id)})).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Empresa no encontrada.")
    company = dict(row)
    company["kind"] = kinds.resolve_kind(company["id"], company.get("settings_json"))
    return company


def store_for(db: AsyncSession) -> lifecycle.Store:
    return lifecycle.PgStore(db)


async def _audit(request: Request, **detail: Any) -> None:
    """Detalle corto para la auditoria (commit 6). Nunca rompe la accion."""
    try:
        from app.services import admin_audit

        admin_audit.attach_detail(request, **detail)
    except Exception:
        pass


# ---------------------------------------------------- actividad (Ficha) ---
@router.get("/admin-v2/api/companies/{company_id}/activity", include_in_schema=False, dependencies=GUARD)
async def company_activity(company_id: str, db: AsyncSession = Depends(get_db)):
    """Solo lectura: ingresos de 14 dias, resumen de sesiones y usuarios por panel de ESA empresa."""
    from app.services.company_activity import company_activity as build

    cid = _uuid(company_id)
    await load_company(db, cid)  # 404 si no existe
    return _json(await build(db, str(cid)))


# ------------------------------------------- catalogo y salud (Fase 3) ---
@router.get("/admin-v2/api/catalog/usage", include_in_schema=False, dependencies=GUARD)
async def catalog_usage(db: AsyncSession = Depends(get_db)):
    """Solo lectura: empresas por paquete; por modulo, paquetes y empresas encendidas."""
    from app.services.console_catalog import catalog_usage as build

    return _json(await build(db))


@router.get("/admin-v2/api/health/security", include_in_schema=False, dependencies=GUARD)
async def health_security(request: Request, db: AsyncSession = Depends(get_db)):
    """Solo lectura: variables de seguridad presentes (sin valores), cierre automatico de
    sesiones y un estimado de endpoints sin sesion."""
    from app.services.console_catalog import security_status

    return _json(await security_status(db, request.app, master_access_mode=v2.master_access_mode()))


@router.get("/admin-v2/api/switches", include_in_schema=False, dependencies=GUARD)
async def switches_matrix(db: AsyncSession = Depends(get_db)):
    """Solo lectura: registro de interruptores y su estado por empresa no archivada.
    Solo devuelve las claves registradas, nunca el resto de settings."""
    from app.services.switch_registry import matrix

    return _json(await matrix(db))


# ------------------------------------------------------- auditoria ---
@router.get("/admin-v2/api/audit", include_in_schema=False, dependencies=GUARD)
async def audit_log(request: Request, company_id: str = "", date_from: str = "", date_to: str = "", action: str = "",
                    limit: int = 100, db: AsyncSession = Depends(get_db)):
    """Escrituras de la consola maestra, filtradas por empresa, fecha (dia en Bogota) y accion."""
    from app.services import admin_audit

    try:
        entries = await admin_audit.list_entries(db, company_id=company_id, date_from=date_from, date_to=date_to,
                                                 action=action, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _json({"ok": True, "entries": entries, "retention_days": admin_audit.RETENTION_DAYS})


# ------------------------------------------------------------ tipo ---
class KindRequest(BaseModel):
    kind: str
    confirm: bool = False


@router.post("/admin-v2/api/companies/{company_id}/kind", include_in_schema=False, dependencies=GUARD)
async def change_kind(company_id: str, payload: KindRequest, request: Request, db: AsyncSession = Depends(get_db)):
    cid = _uuid(company_id)
    target = str(payload.kind or "").strip().lower()
    if target not in kinds.KINDS:
        raise HTTPException(status_code=400, detail="Tipo inválido. Usa demo o registrada.")
    company = await load_company(db, cid)
    if target == kinds.DEMO and kinds.is_protected(company["id"]):
        raise HTTPException(status_code=403, detail="Esta empresa está protegida: no puede pasar a demo.")
    if target == kinds.REGISTERED and company["kind"] == kinds.DEMO and not payload.confirm:
        return _json({"ok": False, "confirmation_required": True,
                      "detail": f"Confirma que {company['name']} pasa de demo a registrada."}, 409)
    await db.execute(text("""
        UPDATE companies
        SET settings_json = jsonb_set(COALESCE(settings_json, '{}'::jsonb), '{kind}', to_jsonb(CAST(:kind AS text)), true),
            updated_at = NOW()
        WHERE id = CAST(:id AS uuid)
    """), {"id": str(cid), "kind": target})
    await db.commit()
    await _audit(request, company_name=company["name"], kind_from=company["kind"], kind_to=target)
    return _json({"ok": True, "company_id": company["id"], "kind": target, "previous_kind": company["kind"]})


# ---------------------------------------------------------- clonar ---
class CloneRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    slug: str = Field(min_length=1, max_length=120)
    timezone: Optional[str] = None
    owner_full_name: str = Field(min_length=1, max_length=200)
    owner_email: str = Field(min_length=3, max_length=255)
    owner_password: str = Field(min_length=8, max_length=72)


async def create_demo_company_and_owner(db: AsyncSession, source: dict, payload: CloneRequest) -> tuple[uuid.UUID, str]:
    """Empresa demo nueva + su dueño, en la transaccion abierta (sin commit)."""
    from app.models.auth import CompanyUser
    from app.models.core import Company
    from app.services.auth_service import get_user_by_email, hash_password, normalize_email

    slug = payload.slug.strip().lower()
    if (await db.execute(select(Company.id).where(Company.slug == slug))).first():
        raise HTTPException(status_code=409, detail="Ya existe una empresa con ese slug.")
    email = normalize_email(payload.owner_email)
    if await get_user_by_email(db, email):
        raise HTTPException(status_code=409, detail="El email del dueño ya existe.")
    now = datetime.now(timezone.utc)
    origin = (await db.execute(select(Company).where(Company.id == uuid.UUID(source["id"])))).scalar_one()
    new_id = uuid.uuid4()
    db.add(Company(
        id=new_id, name=payload.name.strip(), slug=slug, status="active",
        timezone=payload.timezone or getattr(origin, "timezone", None) or "America/Bogota",
        plan=getattr(origin, "plan", None) or "standard",
        settings_json=lifecycle.clone_settings(source.get("settings_json"), source["id"]),
        created_at=now, updated_at=now,
    ))
    await db.flush()
    db.add(CompanyUser(
        company_id=new_id, email=email, password_hash=hash_password(payload.owner_password),
        full_name=payload.owner_full_name.strip() or email, role="company_admin", status="active",
        must_change_password=True, failed_login_attempts=0, locked_until=None, settings_json={},
        created_at=now, updated_at=now, last_password_reset_at=now,
    ))
    await db.flush()
    return new_id, email


@router.post("/admin-v2/api/companies/{company_id}/clone-demo", include_in_schema=False, dependencies=GUARD)
async def clone_demo(company_id: str, payload: CloneRequest, request: Request, db: AsyncSession = Depends(get_db)):
    source = await load_company(db, _uuid(company_id))
    try:
        new_id, email = await create_demo_company_and_owner(db, source, payload)
        copied = await lifecycle.clone_config(store_for(db), source["id"], new_id)
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    await _audit(request, company_name=source["name"], new_company_id=str(new_id), new_company_name=payload.name.strip(),
                 copied_rows=sum(copied.values()))
    return _json({"ok": True, "company_id": str(new_id), "kind": kinds.DEMO, "source_company_id": source["id"],
                  "owner_email": email, "temporary_password": payload.owner_password, "copied": copied,
                  "copied_tables": list(lifecycle.CLONE_TABLES)})


# --------------------------------------------------------- eliminar ---
class PurgeRequest(BaseModel):
    dry_run: bool = True
    confirm_name: Optional[str] = None


def purge_lock(company: dict) -> Optional[tuple[int, str]]:
    if kinds.is_protected(company["id"]):
        return 403, "Empresa protegida: las tres empresas vivas no se eliminan nunca desde la consola."
    archived = str(company.get("status") or "").lower() in ("archived", "deleted")
    if company["kind"] == kinds.REGISTERED and not archived:
        return 409, "Una empresa registrada solo se puede eliminar si está archivada."
    return None


@router.post("/admin-v2/api/companies/{company_id}/purge", include_in_schema=False, dependencies=GUARD)
async def purge_company(company_id: str, payload: PurgeRequest, request: Request, db: AsyncSession = Depends(get_db)):
    company = await load_company(db, _uuid(company_id))
    lock = purge_lock(company)
    if lock:
        raise HTTPException(status_code=lock[0], detail=lock[1])
    store = store_for(db)
    if payload.dry_run:
        plan = await lifecycle.purge_plan(store, company["id"])
        return _json({"ok": True, "dry_run": True, "executed": False, "company_id": company["id"],
                      "company_name": company["name"], "kind": company["kind"], "tables": plan,
                      "total_rows": sum(t["rows"] for t in plan),
                      "kept_tables": sorted(lifecycle.PURGE_KEEP_TABLES - {"companies"}),
                      "confirmation_required": {"confirm_name": company["name"]}})
    if (payload.confirm_name or "") != company["name"]:
        raise HTTPException(status_code=400, detail="Escribe el nombre exacto de la empresa para eliminarla.")
    try:
        deleted = await lifecycle.purge_execute(store, company["id"])
        await db.commit()
    except lifecycle.PurgeBlocked as error:
        await db.rollback()
        raise HTTPException(status_code=409, detail=f"No se pudo eliminar sin romper llaves foráneas en: {error}. "
                                                    "No se borró nada.") from error
    except Exception:
        await db.rollback()
        raise
    total = sum(t["rows"] for t in deleted)
    # Fase 4: sus imagenes de marca en el bucket se borran tambien. La base ya
    # quedo limpia; si el bucket no responde se informa y no se revierte nada.
    bucket = {"deleted": 0, "error": ""}
    try:
        import asyncio

        from app.services import brand_media

        bucket["deleted"] = await asyncio.to_thread(brand_media.delete_company, company["id"])
    except Exception as error:  # nunca rompe un purge ya hecho
        bucket["error"] = "No se pudieron borrar sus imágenes del bucket; quedan para limpieza manual."
        import logging

        logging.getLogger("clonexa.admin_v2plus").warning("purge: bucket de marca sin limpiar company=%s: %s", company["id"], type(error).__name__)
    await _audit(request, company_name=company["name"], deleted_rows=total, deleted_tables=len(deleted), bucket_images=bucket["deleted"])
    return _json({"ok": True, "dry_run": False, "executed": True, "company_id": company["id"],
                  "company_name": company["name"], "tables": deleted, "total_rows": total, "bucket": bucket})
