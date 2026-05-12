import json
import uuid

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.models.saas import Module, Package, PackageModule
from app.schemas.saas import PackageCreate, PackageOut, PackageWithModulesOut
from app.services.saas_packages import get_package_with_modules_or_404

router = APIRouter()


# CLONEXA_019A_R1_PACKAGE_MINI_PANEL_CAPABILITIES_START
MINI_PANEL_PACKAGE_TYPES = {
    "store": "Tiendas",
    "sales": "Ventas",
    "logistics": "Logística",
    "inventory": "Inventarios",
    "other": "Otros",
}

MINI_PANEL_USER_LIMITS = {1, 3, 5, 10, 15}


def _normalize_package_mini_panel_settings(raw: dict[str, Any] | None = None) -> dict[str, Any]:
    source = raw if isinstance(raw, dict) else {}
    raw_types = source.get("types") if isinstance(source.get("types"), dict) else {}

    types: dict[str, dict[str, Any]] = {}
    for code, label in MINI_PANEL_PACKAGE_TYPES.items():
        current = raw_types.get(code) if isinstance(raw_types.get(code), dict) else {}
        enabled = bool(current.get("enabled", False))
        users_allowed = current.get("users_allowed", 0)
        try:
            users_allowed = int(users_allowed)
        except Exception:
            users_allowed = 0
        if users_allowed not in MINI_PANEL_USER_LIMITS:
            users_allowed = 1 if enabled else 0

        types[code] = {
            "enabled": enabled,
            "label": label,
            "users_allowed": users_allowed if enabled else 0,
            "login_template": f"/mini-panel/login?company_id={{company_id}}&type={code}",
        }

    return {
        "enabled": bool(source.get("enabled", False)),
        "types": types,
    }


async def _ensure_package_feature_settings_storage(db: AsyncSession) -> None:
    await db.execute(text("""
        CREATE TABLE IF NOT EXISTS package_feature_settings (
            package_id uuid NOT NULL REFERENCES packages(id) ON DELETE CASCADE,
            feature_code varchar(80) NOT NULL,
            settings_json jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (package_id, feature_code)
        )
    """))


async def _get_package_or_404_basic(db: AsyncSession, package_id: uuid.UUID) -> Package:
    result = await db.execute(select(Package).where(Package.id == package_id))
    package = result.scalar_one_or_none()
    if not package:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="package_not_found")
    return package


async def _read_package_mini_panel_settings(db: AsyncSession, package_id: uuid.UUID) -> dict[str, Any]:
    await _get_package_or_404_basic(db, package_id)
    await _ensure_package_feature_settings_storage(db)

    result = await db.execute(
        text("""
            SELECT settings_json
            FROM package_feature_settings
            WHERE package_id = CAST(:package_id AS uuid)
              AND feature_code = 'mini_panel'
            LIMIT 1
        """),
        {"package_id": str(package_id)},
    )
    row = result.mappings().first()
    raw = row["settings_json"] if row else {}

    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:
            raw = {}

    settings = _normalize_package_mini_panel_settings(raw)
    return {
        "package_id": str(package_id),
        "feature_code": "mini_panel",
        "mini_panel": settings,
        **settings,
    }


async def _write_package_mini_panel_settings(
    db: AsyncSession,
    package_id: uuid.UUID,
    payload: dict[str, Any],
) -> dict[str, Any]:
    await _get_package_or_404_basic(db, package_id)
    await _ensure_package_feature_settings_storage(db)

    source = payload.get("mini_panel") if isinstance(payload.get("mini_panel"), dict) else payload
    settings = _normalize_package_mini_panel_settings(source if isinstance(source, dict) else {})

    await db.execute(
        text("""
            INSERT INTO package_feature_settings (
                package_id,
                feature_code,
                settings_json,
                created_at,
                updated_at
            )
            VALUES (
                CAST(:package_id AS uuid),
                'mini_panel',
                CAST(:settings_json AS jsonb),
                now(),
                now()
            )
            ON CONFLICT (package_id, feature_code)
            DO UPDATE SET
                settings_json = EXCLUDED.settings_json,
                updated_at = now()
        """),
        {
            "package_id": str(package_id),
            "settings_json": json.dumps(settings, ensure_ascii=False),
        },
    )

    await db.commit()
    return await _read_package_mini_panel_settings(db, package_id)
# CLONEXA_019A_R1_PACKAGE_MINI_PANEL_CAPABILITIES_END


def serialize_package_with_modules(package: Package) -> PackageWithModulesOut:
    modules = [link.module for link in package.module_links if link.module]
    data = PackageOut.model_validate(package).model_dump()
    data["modules"] = modules
    return PackageWithModulesOut.model_validate(data)


@router.get("", response_model=list[PackageOut])
async def list_packages(
    db: AsyncSession = Depends(get_db),
    active_only: bool = False,
) -> list[Package]:
    stmt = select(Package).order_by(Package.code.asc())
    if active_only:
        stmt = stmt.where(Package.is_active.is_(True))
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.post("", response_model=PackageWithModulesOut, status_code=status.HTTP_201_CREATED)
async def create_package(
    payload: PackageCreate,
    db: AsyncSession = Depends(get_db),
) -> PackageWithModulesOut:
    existing = await db.execute(select(Package.id).where(Package.code == payload.code))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="package_code_already_exists")

    package = Package(
        code=payload.code,
        name=payload.name,
        description=payload.description,
        is_active=payload.is_active,
    )
    db.add(package)
    await db.flush()

    if payload.module_codes:
        module_result = await db.execute(select(Module).where(Module.code.in_(payload.module_codes)))
        modules = list(module_result.scalars().all())
        found_codes = {m.code for m in modules}
        missing = sorted(set(payload.module_codes) - found_codes)
        if missing:
            await db.rollback()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": "modules_not_found", "module_codes": missing},
            )

        for module in modules:
            db.add(PackageModule(package_id=package.id, module_id=module.id, settings={}))

    await db.commit()
    package = await get_package_with_modules_or_404(db, package.id)
    return serialize_package_with_modules(package)




# CLONEXA_019A_R1_PACKAGE_MINI_PANEL_CAPABILITIES_ENDPOINTS_START
@router.get("/{package_id}/mini-panel-settings")
async def get_package_mini_panel_settings(
    package_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await _read_package_mini_panel_settings(db, package_id)


@router.put("/{package_id}/mini-panel-settings")
async def update_package_mini_panel_settings(
    package_id: uuid.UUID,
    payload: dict[str, Any] = Body(...),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await _write_package_mini_panel_settings(db, package_id, payload)
# CLONEXA_019A_R1_PACKAGE_MINI_PANEL_CAPABILITIES_ENDPOINTS_END

@router.get("/{package_id}", response_model=PackageWithModulesOut)
async def get_package(
    package_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> PackageWithModulesOut:
    package = await get_package_with_modules_or_404(db, package_id)
    return serialize_package_with_modules(package)
